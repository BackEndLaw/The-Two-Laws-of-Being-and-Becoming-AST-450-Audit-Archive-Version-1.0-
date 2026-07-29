from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path

from integrations.vehicle.blocked_route import load_scenario, replay_trace, run_blocked_route


def run_matrix(scenario_path: str | Path, output_dir: str | Path) -> dict:
    scenario_file = Path(scenario_path)
    scenario = load_scenario(scenario_file)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    runs = []

    for seed in (1, 2, 3, 4, 5):
        for mode, admitted in (("denied", False), ("authorized", True)):
            result = run_blocked_route(
                scenario,
                seed=seed,
                specialist_admitted=admitted,
            )
            repeated = run_blocked_route(
                scenario,
                seed=seed,
                specialist_admitted=admitted,
            )
            if result.events != repeated.events or not replay_trace(scenario, result.events):
                raise RuntimeError(f"Non-deterministic or unreplayable trace: {mode}, seed {seed}")

            trace_path = destination / f"{mode}-seed-{seed}.jsonl"
            result.write_jsonl(trace_path)
            event = result.events[0]
            runs.append(
                {
                    "mode": mode,
                    "seed": seed,
                    "outcome": result.outcome,
                    "collision": event["collision"],
                    "witness_complete": event["witness_complete"],
                    "replay_verified": True,
                    "trace": trace_path.name,
                    "sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
                }
            )

    summary = {
        "evidence_bundle_version": "vehicle-contract-v1",
        "scenario_id": scenario["scenario_id"],
        "simulator": "graph",
        "carla_used": False,
        "native_carla_status": "NOT_EVALUATED",
        "hardware_status": "NOT_EVALUATED",
        "git_commit": _git_commit(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dependencies": {
                "PyYAML": importlib.metadata.version("PyYAML"),
                "pytest": importlib.metadata.version("pytest"),
            },
        },
        "inputs": {
            "scenario": str(scenario_file),
            "scenario_sha256": hashlib.sha256(scenario_file.read_bytes()).hexdigest(),
        },
        "seeds": [1, 2, 3, 4, 5],
        "replay_verified": all(run["replay_verified"] for run in runs),
        "acceptance_passed": all(
            not run["collision"] and run["witness_complete"] and run["replay_verified"]
            for run in runs
        ),
        "runs": runs,
    }
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the blocked-route vehicle pilot")
    parser.add_argument(
        "--scenario",
        default="scenarios/blocked_route_v1.json",
        help="Blocked-route scenario JSON",
    )
    parser.add_argument(
        "--output",
        default="artifacts/vehicle_pilot",
        help="Directory for JSONL witnesses and summary",
    )
    args = parser.parse_args()
    summary = run_matrix(args.scenario, args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()