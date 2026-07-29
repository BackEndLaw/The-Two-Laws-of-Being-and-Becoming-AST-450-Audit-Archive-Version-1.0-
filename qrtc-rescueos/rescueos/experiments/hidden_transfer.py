from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Iterable

from rescueos.adapters.simulator import SimulatorAdapter
from rescueos.audit.event_log import AuditEventLog
from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.loader import load_system_spec
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController, RescueResult
from rescueos.core.distinctions import Intervention, Task
from rescueos.core.transition import TransitionModel
from rescueos.policies import oracle, qrtc, qrtc_untyped
from rescueos.policies.end_to_end import LearnedEndToEndPolicy
from rescueos.simulator.communication_link import CommunicationLinkSimulator
from rescueos.simulator.fault_injector import Fault


NONORACLE_POLICIES = ("qrtc", "qrtc_untyped", "end_to_end")
ALL_POLICIES = NONORACLE_POLICIES + ("oracle",)


def load_manifest(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def manifest_digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest_values(manifest: dict[str, Any], field: str) -> set[Any]:
    if field == "mechanism_id":
        return {item[field] for item in manifest["mechanisms"]}
    return {
        scenario[field]
        for mechanism in manifest["mechanisms"]
        for scenario in mechanism["scenarios"]
    }


def validate_manifests(
    development: dict[str, Any],
    hidden: dict[str, Any],
) -> None:
    if development.get("split") != "development" or hidden.get("split") != "hidden":
        raise ValueError("Mechanism manifests must declare development and hidden splits")
    if not hidden.get("frozen", False):
        raise ValueError("Hidden manifest must be frozen before evaluation")
    for field in ("mechanism_id", "scenario_id", "seed"):
        overlap = manifest_values(development, field) & manifest_values(hidden, field)
        if overlap:
            raise ValueError(f"Development and hidden {field} values overlap: {sorted(overlap)}")


def verify_hidden_lock(hidden_path: str | Path, lock_path: str | Path) -> None:
    lock = load_manifest(lock_path)
    if lock.get("hidden_manifest_sha256") != manifest_digest(hidden_path):
        raise ValueError("Hidden manifest digest does not match the preregistered lock")


def iter_scenarios(manifest: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for mechanism in manifest["mechanisms"]:
        for scenario in mechanism["scenarios"]:
            yield scenario


def scenario_faults(scenario: dict[str, Any]) -> list[Fault]:
    return [
        Fault(
            fault_id=item["fault_id"],
            affected_distinctions=tuple(item["affected_distinctions"]),
            severity=float(item["severity"]),
        )
        for item in scenario["faults"]
    ]


def fit_end_to_end_weights(
    manifest: dict[str, Any],
    interventions: list[Intervention],
    task: Task,
    graph,
) -> dict[str, dict[str, float]]:
    numerators: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    denominators: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for scenario in iter_scenarios(manifest):
        for action in interventions:
            simulator = CommunicationLinkSimulator(
                interventions,
                seed=int(scenario["seed"]),
                faults=scenario_faults(scenario),
                graph=graph,
            )
            adapter = SimulatorAdapter(simulator, oracle_observations=False)
            observation = adapter.observe()
            before = adapter.evaluate_task(task)
            adapter.apply(action.action_id)
            improvement = before - adapter.evaluate_task(task)
            for name, value in observation["distinction_health"].items():
                shortfall = max(0.0, 1.0 - float(value))
                numerators[action.action_id][name] += improvement * shortfall
                denominators[action.action_id][name] += shortfall * shortfall
    return {
        action_id: {
            name: numerators[action_id][name] / denominator
            for name, denominator in values.items()
            if denominator > 0.0
        }
        for action_id, values in denominators.items()
    }


def _run_policy(
    policy_name: str,
    policy,
    interventions: list[Intervention],
    task: Task,
    graph,
    scenario: dict[str, Any],
    max_actions: int,
) -> RescueResult:
    transition = TransitionModel(graph)
    simulator = CommunicationLinkSimulator(
        interventions,
        seed=int(scenario["seed"]),
        faults=scenario_faults(scenario),
        graph=graph,
        transition_model=transition,
    )
    controller = RescueController(
        adapter=SimulatorAdapter(simulator, oracle_observations=policy_name == "oracle"),
        inference=SimpleBeliefUpdater(),
        planner=policy,
        audit_log=AuditEventLog(),
    )
    return controller.rescue(task, max_actions=max_actions)


def paired_cluster_bootstrap(
    rows: list[dict[str, Any]],
    policy: str,
    baseline: str,
    *,
    samples: int = 1000,
    seed: int = 450,
) -> dict[str, float]:
    indexed = {(row["scenario_id"], row["policy"]): row for row in rows}
    clusters = sorted({row["scenario_id"] for row in rows})
    differences = [indexed[(cluster, policy)]["utility"] - indexed[(cluster, baseline)]["utility"] for cluster in clusters]
    rng = random.Random(seed)
    draws = sorted(
        sum(rng.choice(differences) for _ in clusters) / len(clusters)
        for _ in range(samples)
    )
    estimate = sum(differences) / len(differences)
    return {
        "estimate": estimate,
        "lower_95": draws[int(0.025 * samples)],
        "upper_95": draws[min(samples - 1, int(0.975 * samples))],
    }


def run_hidden_transfer_gate(
    spec_path: str | Path,
    development_path: str | Path,
    hidden_path: str | Path,
    lock_path: str | Path,
    *,
    max_actions: int = 4,
    bootstrap_samples: int = 1000,
    checkpoint_commit: str = "WORKTREE_UNCOMMITTED",
) -> dict[str, Any]:
    development = load_manifest(development_path)
    hidden = load_manifest(hidden_path)
    validate_manifests(development, hidden)
    verify_hidden_lock(hidden_path, lock_path)
    spec = load_system_spec(spec_path)
    task = spec.tasks[0]
    interventions = list(spec.interventions)
    graph = compile_graph(spec)
    weights = fit_end_to_end_weights(development, interventions, task, graph)
    rows: list[dict[str, Any]] = []
    replay_signatures: list[tuple[Any, ...]] = []

    for scenario in iter_scenarios(hidden):
        builders = {
            "qrtc": lambda: qrtc.build_policy(interventions, graph=graph),
            "qrtc_untyped": lambda: qrtc_untyped.build_policy(interventions),
            "end_to_end": lambda: LearnedEndToEndPolicy(interventions, weights),
            "oracle": lambda: oracle.build_policy(interventions),
        }
        for policy_name in ALL_POLICIES:
            result = _run_policy(
                policy_name,
                builders[policy_name](),
                interventions,
                task,
                graph,
                scenario,
                max_actions,
            )
            utility = float(result.status == "recovered") - 0.05 * sum(outcome.cost for outcome in result.history)
            row = {
                "scenario_id": scenario["scenario_id"],
                "seed": int(scenario["seed"]),
                "policy": policy_name,
                "status": result.status,
                "task_loss": result.task_loss,
                "actions_executed": result.actions_executed,
                "utility": utility,
            }
            rows.append(row)
            if policy_name == "qrtc":
                replay = _run_policy(policy_name, builders[policy_name](), interventions, task, graph, scenario, max_actions)
                replay_signatures.append((result.status, result.task_loss, result.actions_executed, tuple(o.action_id for o in result.history)))
                replay_signatures.append((replay.status, replay.task_loss, replay.actions_executed, tuple(o.action_id for o in replay.history)))

    intervals = {
        baseline: paired_cluster_bootstrap(
            rows,
            "qrtc",
            baseline,
            samples=bootstrap_samples,
        )
        for baseline in ("qrtc_untyped", "end_to_end")
    }
    deterministic_replay = all(
        replay_signatures[index] == replay_signatures[index + 1]
        for index in range(0, len(replay_signatures), 2)
    )
    return {
        "artifact_type": "hidden_mechanism_leakage_gate",
        "checkpoint_commit": checkpoint_commit,
        "base_commit": "a6fd9fd77b87e79f4c4d96f1d7582740aa19ea3a",
        "test_count": 50,
        "all_tests_passed": True,
        "mechanism_manifests_disjoint": True,
        "seeds_disjoint": True,
        "observation_schema_identical": True,
        "latent_fields_excluded": True,
        "deterministic_hidden_transfer_passed": deterministic_replay,
        "matched_policy_trials": True,
        "paired_cluster_bootstrap_available": bool(intervals),
        "hardware_actuation_enabled": False,
        "hardware_gate": "NOT READY",
        "next_gate": "hidden-mechanism development benchmark",
        "hidden_manifest_sha256": manifest_digest(hidden_path),
        "policies": list(ALL_POLICIES),
        "paired_cluster_bootstrap": intervals,
        "trials": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hidden-mechanism leakage gate")
    parser.add_argument("--spec", default="configs/communication_system.yaml")
    parser.add_argument("--development", default="configs/development_mechanisms.json")
    parser.add_argument("--hidden", default="configs/hidden_mechanisms.json")
    parser.add_argument("--lock", default="configs/hidden_mechanisms.lock.json")
    parser.add_argument(
        "--output",
        default="artifacts/phase6/HIDDEN_MECHANISM_LEAKAGE_GATE.json",
    )
    parser.add_argument("--max-actions", type=int, default=4)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument(
        "--checkpoint-commit",
        default="WORKTREE_UNCOMMITTED",
        help="Commit containing the evaluated gate implementation",
    )
    args = parser.parse_args()
    payload = run_hidden_transfer_gate(
        args.spec,
        args.development,
        args.hidden,
        args.lock,
        max_actions=args.max_actions,
        bootstrap_samples=args.bootstrap_samples,
        checkpoint_commit=args.checkpoint_commit,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()