from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from rescueos import RESULT_NAME
from rescueos.adapters.simulator import SimulatorAdapter
from rescueos.audit.event_log import AuditEventLog
from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.loader import load_system_spec
from rescueos.compiler.schema import CompiledGraph
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController, RescueResult
from rescueos.core.distinctions import Intervention, Task
from rescueos.core.transition import TransitionModel
from rescueos.policies import greedy, oracle, qrtc, qrtc_untyped
from rescueos.simulator.communication_link import CommunicationLinkSimulator
from rescueos.simulator.fault_injector import Fault


POLICIES = {
    "qrtc": qrtc.build_policy,
    "qrtc_untyped": qrtc_untyped.build_policy,
    "greedy": greedy.build_policy,
    "oracle": oracle.build_policy,
}


def run_benchmark(
    spec_path: str | Path,
    *,
    max_faults: int = 6,
    runs_per_k: int = 24,
    max_actions: int = 4,
    seed: int = 11,
    fault_bank_path: str | Path | None = None,
    lambda_cost: float = 0.05,
    eta_actions: float = 0.02,
    beta_harm: float = 0.25,
    min_delta_vs_nonoracle: float = 0.0,
    max_harm_rate: float = 0.05,
    max_unsafe_rate: float = 0.05,
    max_unsafe_unknown_rate: float = 0.05,
    require_strict_unknown_superiority: bool = False,
    baseline_policy: str | None = None,
) -> dict[str, Any]:
    spec = load_system_spec(spec_path)
    if not spec.tasks:
        raise ValueError("System spec must include at least one task")

    task = spec.tasks[0]
    graph = compile_graph(spec)
    interventions = list(spec.interventions)
    distinction_pool = _distinction_pool(task)
    fault_bank = _load_fault_bank(fault_bank_path)

    trials: list[dict[str, Any]] = []
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)

    for k in range(1, max_faults + 1):
        for run_index, trial_seed, faults, scenario_id, scenario_meta in _scenario_iter(
            k=k,
            runs_per_k=runs_per_k,
            seed=seed,
            fault_bank=fault_bank,
            distinction_pool=distinction_pool,
        ):

            for policy_name, policy_builder in POLICIES.items():
                result = _run_single_policy(
                    interventions=interventions,
                    task=task,
                    faults=faults,
                    policy_builder=policy_builder,
                    seed=trial_seed,
                    max_actions=max_actions,
                    graph=graph,
                    typed_graph_access=policy_name == "qrtc",
                )
                row = {
                    "result_name": RESULT_NAME,
                    "policy": policy_name,
                    "k_faults": k,
                    "trial_id": f"k{k}-run{run_index:03d}",
                    "scenario_id": scenario_id,
                    "scenario_source": scenario_meta["source"],
                    "is_unknown_fault": float(bool(scenario_meta["is_unknown_fault"])),
                    "is_adversarial_unknown": float(
                        bool(scenario_meta["is_adversarial_unknown"])
                    ),
                    "status": result.status,
                    "recovered": float(result.status == "recovered"),
                    "task_loss": result.task_loss,
                    "actions_executed": result.actions_executed,
                    "total_cost": _sum_history_field(result, "cost"),
                    "total_harm": _sum_history_field(result, "harm"),
                    "utility": _utility(
                        result=result,
                        lambda_cost=lambda_cost,
                        eta_actions=eta_actions,
                        beta_harm=beta_harm,
                    ),
                    "unsafe_event": float(_unsafe_event(result)),
                    "harm_event": float(_harm_event(result)),
                    "abstain_event": float(result.status == "abstained"),
                    "missed_rescue_event": float(_missed_rescue(result, task)),
                    "seed": trial_seed,
                }
                trials.append(row)
                grouped[(policy_name, k)].append(row)

    summary: list[dict[str, Any]] = []
    for (policy_name, k), rows in sorted(grouped.items()):
        n = len(rows)
        summary.append(
            {
                "result_name": RESULT_NAME,
                "policy": policy_name,
                "k_faults": k,
                "n_trials": n,
                "recovery_rate": sum(r["recovered"] for r in rows) / n,
                "mean_task_loss": sum(r["task_loss"] for r in rows) / n,
                "mean_actions": sum(r["actions_executed"] for r in rows) / n,
                "mean_cost": sum(r["total_cost"] for r in rows) / n,
                "mean_harm": sum(r["total_harm"] for r in rows) / n,
                "mean_utility": sum(r["utility"] for r in rows) / n,
                "unsafe_rate": sum(r["unsafe_event"] for r in rows) / n,
                "harm_rate": sum(r["harm_event"] for r in rows) / n,
                "abstain_rate": sum(r["abstain_event"] for r in rows) / n,
                "missed_rescue_rate": sum(r["missed_rescue_event"] for r in rows) / n,
                "unknown_trial_count": int(sum(r["is_unknown_fault"] for r in rows)),
                "unsafe_unknown_rate": _conditional_rate(
                    rows,
                    event_field="unsafe_event",
                    condition_field="is_unknown_fault",
                ),
                "harm_unknown_rate": _conditional_rate(
                    rows,
                    event_field="harm_event",
                    condition_field="is_unknown_fault",
                ),
                "adversarial_unknown_trial_count": int(
                    sum(r["is_adversarial_unknown"] for r in rows)
                ),
                "unsafe_adversarial_unknown_rate": _conditional_rate(
                    rows,
                    event_field="unsafe_event",
                    condition_field="is_adversarial_unknown",
                ),
            }
        )

    acceptance = _build_acceptance_report(
        summary=summary,
        min_delta_vs_nonoracle=min_delta_vs_nonoracle,
        max_harm_rate=max_harm_rate,
        max_unsafe_rate=max_unsafe_rate,
        max_unsafe_unknown_rate=max_unsafe_unknown_rate,
        require_strict_unknown_superiority=require_strict_unknown_superiority,
        baseline_policy=baseline_policy,
    )

    return {
        "config": {
            "result_name": RESULT_NAME,
            "spec_path": str(spec_path),
            "max_faults": max_faults,
            "runs_per_k": runs_per_k,
            "max_actions": max_actions,
            "seed": seed,
            "policies": sorted(POLICIES.keys()),
            "fault_bank_path": str(fault_bank_path) if fault_bank_path else None,
            "graph_checksum": graph.checksum,
            "utility_weights": {
                "lambda_cost": lambda_cost,
                "eta_actions": eta_actions,
                "beta_harm": beta_harm,
            },
            "acceptance_targets": {
                "min_delta_vs_nonoracle": min_delta_vs_nonoracle,
                "max_harm_rate": max_harm_rate,
                "max_unsafe_rate": max_unsafe_rate,
                "max_unsafe_unknown_rate": max_unsafe_unknown_rate,
                "require_strict_unknown_superiority": require_strict_unknown_superiority,
                "baseline_policy": baseline_policy,
            },
        },
        "summary": summary,
        "acceptance": acceptance,
        "trials": trials,
    }


def _run_single_policy(
    *,
    interventions: list[Intervention],
    task: Task,
    faults: list[Fault],
    policy_builder,
    seed: int,
    max_actions: int,
    graph: CompiledGraph,
    typed_graph_access: bool,
) -> RescueResult:
    transition_model = TransitionModel(graph)
    simulator = CommunicationLinkSimulator(
        interventions,
        seed=seed,
        faults=faults,
        graph=graph,
        transition_model=transition_model,
    )
    adapter = SimulatorAdapter(
        simulator,
        oracle_observations=policy_builder is oracle.build_policy,
    )
    if typed_graph_access:
        planner = policy_builder(
            interventions,
            graph=graph,
            transition_model=transition_model,
        )
    else:
        planner = policy_builder(interventions)
    controller = RescueController(
        adapter=adapter,
        inference=SimpleBeliefUpdater(),
        planner=planner,
        audit_log=AuditEventLog(),
    )
    return controller.rescue(task, max_actions=max_actions)


def _distinction_pool(task: Task) -> list[str]:
    # Bias synthetic faults toward task-critical distinctions first.
    task_required = list(task.required_distinctions.keys())
    extended = [
        "timing",
        "symbol_estimate",
        "received_amplitude",
        "received_phase",
        "encoded_amplitude",
        "encoded_phase",
    ]
    ordered = task_required + [item for item in extended if item not in task_required]
    return ordered


def _generate_faults(k: int, seed: int, distinction_pool: list[str]) -> list[Fault]:
    rng = random.Random(seed)
    faults: list[Fault] = []
    for index in range(k):
        distinction = distinction_pool[index % len(distinction_pool)]
        severity = rng.uniform(0.2, 0.55)
        faults.append(
            Fault(
                fault_id=f"fault_k{k}_{index}_{distinction}",
                affected_distinctions=(distinction,),
                severity=severity,
            )
        )
    return faults


def _load_fault_bank(path: str | Path | None) -> dict[int, list[dict[str, Any]]] | None:
    if path is None:
        return None
    bank_data = _load_yaml(path)
    scenarios = bank_data.get("scenarios", [])
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in scenarios:
        k = int(item["k_faults"])
        grouped[k].append(item)
    return dict(grouped)


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _scenario_iter(
    *,
    k: int,
    runs_per_k: int,
    seed: int,
    fault_bank: dict[int, list[dict[str, Any]]] | None,
    distinction_pool: list[str],
) -> list[tuple[int, int, list[Fault], str, dict[str, Any]]]:
    if fault_bank and k in fault_bank and fault_bank[k]:
        scenarios = fault_bank[k]
        selected = scenarios[:runs_per_k]
        built: list[tuple[int, int, list[Fault], str, dict[str, Any]]] = []
        for run_index, scenario in enumerate(selected):
            trial_seed = int(scenario.get("seed", seed + (1000 * k) + run_index))
            faults = _faults_from_bank_entry(scenario)
            scenario_id = str(scenario.get("id", f"bank-k{k}-{run_index:03d}"))
            tags = {str(tag).lower() for tag in scenario.get("tags", [])}
            meta = {
                "source": "locked_bank",
                "is_unknown_fault": ("unknown" in tags),
                "is_adversarial_unknown": ("adversarial_unknown" in tags),
            }
            built.append((run_index, trial_seed, faults, scenario_id, meta))
        return built

    fallback: list[tuple[int, int, list[Fault], str, dict[str, Any]]] = []
    for run_index in range(runs_per_k):
        trial_seed = seed + (1000 * k) + run_index
        faults = _generate_faults(k, trial_seed, distinction_pool)
        fallback.append(
            (
                run_index,
                trial_seed,
                faults,
                f"synthetic-k{k}-{run_index:03d}",
                {
                    "source": "synthetic",
                    "is_unknown_fault": False,
                    "is_adversarial_unknown": False,
                },
            )
        )
    return fallback


def _faults_from_bank_entry(entry: dict[str, Any]) -> list[Fault]:
    faults: list[Fault] = []
    for item in entry.get("faults", []):
        faults.append(
            Fault(
                fault_id=str(item["id"]),
                affected_distinctions=tuple(item.get("affected_distinctions", [])),
                severity=float(item.get("severity", 0.0)),
            )
        )
    return faults


def _utility(
    *,
    result: RescueResult,
    lambda_cost: float,
    eta_actions: float,
    beta_harm: float,
) -> float:
    recovered = 1.0 if result.status == "recovered" else 0.0
    total_cost = _sum_history_field(result, "cost")
    total_harm = _sum_history_field(result, "harm")
    return (
        recovered
        - lambda_cost * total_cost
        - eta_actions * float(result.actions_executed)
        - beta_harm * total_harm
    )


def _unsafe_event(result: RescueResult) -> bool:
    return any(bool(outcome.unsafe) for outcome in result.history)


def _harm_event(result: RescueResult) -> bool:
    return _sum_history_field(result, "harm") > 0.0


def _missed_rescue(result: RescueResult, task: Task) -> bool:
    return result.status != "recovered" and result.task_loss > task.recovery_threshold


def _build_acceptance_report(
    *,
    summary: list[dict[str, Any]],
    min_delta_vs_nonoracle: float,
    max_harm_rate: float,
    max_unsafe_rate: float,
    max_unsafe_unknown_rate: float,
    require_strict_unknown_superiority: bool,
    baseline_policy: str | None,
) -> dict[str, Any]:
    indexed: dict[tuple[str, int], dict[str, Any]] = {
        (row["policy"], int(row["k_faults"])): row for row in summary
    }
    k_values = sorted({int(row["k_faults"]) for row in summary})
    non_oracle_policies = [name for name in POLICIES if name != "oracle" and name != "qrtc"]
    if baseline_policy is not None and baseline_policy not in non_oracle_policies:
        choices = ", ".join(non_oracle_policies)
        raise ValueError(f"Baseline policy must be one of: {choices}")

    by_k: list[dict[str, Any]] = []
    all_pass = True

    for k in k_values:
        qrtc_row = indexed[("qrtc", k)]
        baseline_candidates = [indexed[(name, k)] for name in non_oracle_policies]
        strongest_nonoracle = (
            indexed[(baseline_policy, k)]
            if baseline_policy is not None
            else max(baseline_candidates, key=lambda row: row["mean_utility"])
        )

        delta_vs_nonoracle = qrtc_row["mean_utility"] - strongest_nonoracle["mean_utility"]
        pass_delta = delta_vs_nonoracle >= min_delta_vs_nonoracle
        pass_harm = qrtc_row["harm_rate"] <= max_harm_rate
        pass_unsafe = qrtc_row["unsafe_rate"] <= max_unsafe_rate
        qrtc_unsafe_unknown = float(qrtc_row["unsafe_unknown_rate"])
        strongest_unsafe_unknown = float(strongest_nonoracle["unsafe_unknown_rate"])
        pass_unsafe_unknown_threshold = qrtc_unsafe_unknown <= max_unsafe_unknown_rate
        pass_unsafe_unknown_superiority = (
            qrtc_unsafe_unknown < strongest_unsafe_unknown
            if require_strict_unknown_superiority
            else True
        )
        pass_all = (
            pass_delta
            and pass_harm
            and pass_unsafe
            and pass_unsafe_unknown_threshold
            and pass_unsafe_unknown_superiority
        )
        all_pass = all_pass and pass_all

        by_k.append(
            {
                "k_faults": k,
                "strongest_nonoracle": strongest_nonoracle["policy"],
                "delta_u_vs_nonoracle": delta_vs_nonoracle,
                "qrtc_harm_rate": qrtc_row["harm_rate"],
                "qrtc_unsafe_rate": qrtc_row["unsafe_rate"],
                "qrtc_unsafe_unknown_rate": qrtc_unsafe_unknown,
                "strongest_nonoracle_unsafe_unknown_rate": strongest_unsafe_unknown,
                "pass_delta": pass_delta,
                "pass_harm": pass_harm,
                "pass_unsafe": pass_unsafe,
                "pass_unsafe_unknown_threshold": pass_unsafe_unknown_threshold,
                "pass_unsafe_unknown_superiority": pass_unsafe_unknown_superiority,
                "pass_all": pass_all,
            }
        )

    return {
        "result_name": RESULT_NAME,
        "all_k_pass": all_pass,
        "by_k": by_k,
    }


def _sum_history_field(result: RescueResult, field: str) -> float:
    total = 0.0
    for outcome in result.history:
        total += float(getattr(outcome, field, 0.0))
    return total


def _conditional_rate(
    rows: list[dict[str, Any]],
    *,
    event_field: str,
    condition_field: str,
) -> float:
    conditioned = [row for row in rows if float(row[condition_field]) > 0.0]
    if not conditioned:
        return 0.0
    return sum(float(row[event_field]) for row in conditioned) / float(len(conditioned))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Run the {RESULT_NAME} k-fault policy benchmark"
    )
    parser.add_argument(
        "--spec",
        default="configs/communication_system.yaml",
        help="Path to system spec YAML",
    )
    parser.add_argument("--max-faults", type=int, default=6)
    parser.add_argument("--runs-per-k", type=int, default=24)
    parser.add_argument("--max-actions", type=int, default=4)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument(
        "--fault-bank",
        default=None,
        help="Optional YAML file with locked fault scenarios",
    )
    parser.add_argument("--lambda-cost", type=float, default=0.05)
    parser.add_argument("--eta-actions", type=float, default=0.02)
    parser.add_argument("--beta-harm", type=float, default=0.25)
    parser.add_argument("--min-delta-vs-nonoracle", type=float, default=0.0)
    parser.add_argument("--max-harm-rate", type=float, default=0.05)
    parser.add_argument("--max-unsafe-rate", type=float, default=0.05)
    parser.add_argument("--max-unsafe-unknown-rate", type=float, default=0.05)
    parser.add_argument(
        "--baseline-policy",
        choices=["qrtc_untyped", "greedy"],
        default=None,
        help="Use a fixed non-oracle acceptance comparator instead of the strongest by utility",
    )
    parser.add_argument(
        "--require-strict-unknown-superiority",
        action="store_true",
        help="Require QRTC unknown-fault unsafe rate to be strictly lower than strongest non-oracle",
    )
    parser.add_argument(
        "--outdir",
        default="artifacts/benchmark_runs",
        help="Directory for benchmark outputs",
    )
    args = parser.parse_args()

    payload = run_benchmark(
        args.spec,
        max_faults=args.max_faults,
        runs_per_k=args.runs_per_k,
        max_actions=args.max_actions,
        seed=args.seed,
        fault_bank_path=args.fault_bank,
        lambda_cost=args.lambda_cost,
        eta_actions=args.eta_actions,
        beta_harm=args.beta_harm,
        min_delta_vs_nonoracle=args.min_delta_vs_nonoracle,
        max_harm_rate=args.max_harm_rate,
        max_unsafe_rate=args.max_unsafe_rate,
        max_unsafe_unknown_rate=args.max_unsafe_unknown_rate,
        require_strict_unknown_superiority=args.require_strict_unknown_superiority,
        baseline_policy=args.baseline_policy,
    )

    outdir = Path(args.outdir)
    _write_csv(outdir / "trial_results.csv", payload["trials"])
    _write_csv(outdir / "summary.csv", payload["summary"])
    _write_json(outdir / "summary.json", payload)

    for row in payload["summary"]:
        line = (
            f"result_name={RESULT_NAME!r} policy={row['policy']} k={row['k_faults']} "
            f"recovery={row['recovery_rate']:.3f} "
            f"mean_u={row['mean_utility']:.3f} "
            f"mean_actions={row['mean_actions']:.2f}"
        )
        print(line)

    print(
        f"result_name={RESULT_NAME!r} "
        f"acceptance_all_k_pass={payload['acceptance']['all_k_pass']}"
    )


if __name__ == "__main__":
    main()
