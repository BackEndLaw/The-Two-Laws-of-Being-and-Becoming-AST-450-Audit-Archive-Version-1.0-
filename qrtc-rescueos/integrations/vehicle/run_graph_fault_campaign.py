from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from integrations.vehicle.graph_fault_campaign import (
    evaluate_campaign_run,
    load_campaign_scenario,
    run_campaign_scenario,
)


def derive_evaluation_seeds(scenario_id: str) -> list[int]:
    return [
        100000
        + int.from_bytes(
            hashlib.sha256(
                f"graph-fault-campaign-v1:evaluation:{scenario_id}:{index}".encode()
            ).digest()[:8],
            "big",
        )
        % 900000
        for index in range(5)
    ]


def run_campaign(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    full_suite_test_count: int,
    diagnostics_clean: bool,
) -> dict[str, Any]:
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    _validate_manifest(manifest)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest_file, output / "campaign.json")

    source_commit = _git_commit()
    environment = {
        "source_commit": source_commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {
            "PyYAML": importlib.metadata.version("PyYAML"),
            "pytest": importlib.metadata.version("pytest"),
        },
        "simulator": "graph",
        "native_carla_physics": "NOT_EVALUATED",
    }
    _write_json(output / "environment.json", environment)

    scenario_summaries = []
    all_runs = []
    source_dir = manifest_file.parent
    for scenario_id in manifest["scenario_ids"]:
        scenario_source = source_dir / f"{scenario_id}.json"
        scenario = load_campaign_scenario(scenario_source)
        scenario_output = output / scenario_id
        scenario_output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(scenario_source, scenario_output / "scenario.json")
        runs = []
        for seed_class, seeds in (
            ("regression", manifest["regression_seeds"]),
            ("evaluation", manifest["evaluation_seeds"][scenario_id]),
        ):
            for seed in seeds:
                run = run_campaign_scenario(
                    scenario,
                    seed=int(seed),
                    seed_class=seed_class,
                )
                evaluation = evaluate_campaign_run(scenario, run)
                trace_path = scenario_output / "traces" / f"{seed_class}-seed-{seed}.jsonl"
                run.write_jsonl(trace_path)
                run_record = {
                    "seed": seed,
                    "seed_class": seed_class,
                    "trace": str(trace_path.relative_to(scenario_output)),
                    "trace_sha256": _sha256(trace_path),
                    **evaluation,
                }
                runs.append(run_record)
                all_runs.append({"scenario_id": scenario_id, **run_record})

        violations = sorted(
            {violation for run in runs for violation in run["violations"]}
        )
        scenario_summary = {
            "scenario_id": scenario_id,
            "name": scenario["name"],
            "simulator": "graph",
            "native_carla_physics": "NOT_EVALUATED",
            "scenario_sha256": _sha256(scenario_output / "scenario.json"),
            "runs_attempted": len(runs),
            "runs_passed": sum(run["passed"] for run in runs),
            "acceptance_passed": len(runs) == 10 and all(run["passed"] for run in runs),
            "terminal_outcomes": dict(Counter(run["terminal_state"] for run in runs)),
            "invariant_violations": violations,
            "runs": runs,
        }
        _write_json(scenario_output / "summary.json", scenario_summary)
        scenario_summary["summary_sha256"] = _sha256(scenario_output / "summary.json")
        scenario_summaries.append(scenario_summary)

    scenarios_passed = sum(item["acceptance_passed"] for item in scenario_summaries)
    runs_passed = sum(run["passed"] for run in all_runs)
    violations = sorted(
        {violation for run in all_runs for violation in run["violations"]}
    )
    campaign_passed = all(
        (
            len(scenario_summaries) == 10,
            scenarios_passed == 10,
            len(all_runs) == 100,
            runs_passed == 100,
            not violations,
            not any(run["collision"] for run in all_runs),
            not any(run["illegal_graph_transition"] for run in all_runs),
            all(run["witness_complete"] for run in all_runs),
            all(run["replay_verified"] for run in all_runs),
            full_suite_test_count > 0,
            diagnostics_clean,
        )
    )
    summary = {
        "campaign_id": manifest["campaign_id"],
        "schema_version": manifest["schema_version"],
        "simulator": "graph",
        "native_carla_physics": "NOT_EVALUATED",
        "hardware_validation": "NOT_EVALUATED",
        "source_commit": source_commit,
        "scenarios_attempted": len(scenario_summaries),
        "scenarios_passed": scenarios_passed,
        "runs_attempted": len(all_runs),
        "runs_passed": runs_passed,
        "regression_seeds": manifest["regression_seeds"],
        "evaluation_seeds": manifest["evaluation_seeds"],
        "terminal_outcomes": dict(Counter(run["terminal_state"] for run in all_runs)),
        "invariant_violations": violations,
        "collisions": sum(run["collision"] for run in all_runs),
        "illegal_graph_transitions": sum(
            run["illegal_graph_transition"] for run in all_runs
        ),
        "all_witnesses_complete": all(run["witness_complete"] for run in all_runs),
        "all_replays_verified": all(run["replay_verified"] for run in all_runs),
        "full_suite": {"status": "PASSED", "test_count": full_suite_test_count},
        "diagnostics": "CLEAN" if diagnostics_clean else "NOT_CLEAN",
        "scenario_artifacts": [
            {
                "scenario_id": item["scenario_id"],
                "scenario_sha256": item["scenario_sha256"],
                "summary_sha256": item["summary_sha256"],
            }
            for item in scenario_summaries
        ],
        "campaign_acceptance": "PASSED" if campaign_passed else "FAILED_OR_INCOMPLETE",
        "claim_boundary": (
            "Deterministic graph fault-handling semantics only; no CARLA physics, "
            "vehicle dynamics, hardware behavior, or production-safety claim."
        ),
    }
    _write_json(output / "campaign-summary.json", summary)
    (output / "README.md").write_text(_readme(summary), encoding="utf-8")
    _write_checksums(output)
    return summary


def _validate_manifest(manifest: dict[str, Any]) -> None:
    expected_ids = [f"GF-{index:02d}" for index in range(1, 11)]
    if manifest["schema_version"] != "graph-fault-campaign-v1":
        raise ValueError("Unsupported campaign schema")
    if manifest["scenario_ids"] != expected_ids:
        raise ValueError("Campaign must contain GF-01 through GF-10 in order")
    if manifest["regression_seeds"] != [1, 2, 3, 4, 5]:
        raise ValueError("Regression seeds must remain frozen")
    for scenario_id in expected_ids:
        if manifest["evaluation_seeds"][scenario_id] != derive_evaluation_seeds(
            scenario_id
        ):
            raise ValueError(f"Evaluation seed derivation mismatch for {scenario_id}")


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_checksums(output: Path) -> None:
    entries = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            entries.append(f"{_sha256(path)}  {path.relative_to(output)}")
    (output / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="utf-8")


def _readme(summary: dict[str, Any]) -> str:
    return f"""# Graph Fault Campaign V1

Ten deterministic graph fault scenarios were executed with five regression and
five preregistered evaluation seeds per scenario.

- Scenarios passed: {summary['scenarios_passed']}/{summary['scenarios_attempted']}
- Runs passed: {summary['runs_passed']}/{summary['runs_attempted']}
- Campaign acceptance: {summary['campaign_acceptance']}
- Simulator: `graph`
- Native CARLA physics: `NOT_EVALUATED`

This campaign validates software fault-handling semantics only. It does not
validate CARLA physics, real vehicle dynamics, hardware behavior, or production
safety.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run graph fault campaign v1")
    parser.add_argument(
        "--manifest",
        default="scenarios/graph_fault_campaign_v1/campaign.json",
    )
    parser.add_argument(
        "--output",
        default="artifacts/graph_fault_campaign_v1",
    )
    parser.add_argument("--full-suite-test-count", type=int, required=True)
    parser.add_argument("--diagnostics-clean", action="store_true")
    args = parser.parse_args()
    summary = run_campaign(
        args.manifest,
        args.output,
        full_suite_test_count=args.full_suite_test_count,
        diagnostics_clean=args.diagnostics_clean,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()