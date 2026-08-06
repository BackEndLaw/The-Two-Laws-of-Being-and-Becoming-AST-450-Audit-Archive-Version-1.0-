from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


ARCHIVE_FILES = (
    "comparison.csv",
    "cluster_bootstrap.json",
    "mechanism_breakdown.csv",
    "manifest.json",
    "config.yaml",
    "environment.txt",
    "source_tree.diff",
    "DECISION.md",
)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot archive empty table: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _source_diff(repo_root: Path) -> str:
    paths = (
        "qrtc-rescueos/rescueos/experiments/development_benchmark.py",
        "qrtc-rescueos/rescueos/policies/random_policy.py",
        "qrtc-rescueos/tests/test_development_benchmark.py",
    )
    result = subprocess.run(
        ["git", "diff", "HEAD", "--", *paths],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to capture source diff")
    if not result.stdout:
        raise ValueError("Source-tree diff is empty")
    return result.stdout


def archive_failed_development(
    input_path: str | Path,
    output_directory: str | Path,
    *,
    repo_root: str | Path,
) -> Path:
    input_file = Path(input_path)
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    with input_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload["development_acceptance"]["proceed_to_fresh_validation"]:
        raise ValueError("Refusing to label an accepted experiment as failed")

    _write_csv(output / "comparison.csv", payload["overall"])
    _write_csv(output / "mechanism_breakdown.csv", payload["breakdowns"]["mechanism_family"])
    bootstrap = {
        "primary_delta_u_hidden": payload["primary_delta_u_hidden"],
        "delta_u_typed_minus_untyped": payload["delta_u_typed_minus_untyped"],
        "bootstrap": payload["bootstrap"],
        "precision_diagnostics": payload["precision_diagnostics"],
    }
    (output / "cluster_bootstrap.json").write_text(
        json.dumps(bootstrap, indent=2) + "\n", encoding="utf-8"
    )
    manifest = {
        "artifact_type": "failed_development_experiment_archive",
        "source_artifact": input_file.name,
        "development_acceptance": False,
        "validation_authorized": False,
        "hardware_gate": "NOT READY",
        "strongest_nonoracle": payload["strongest_nonoracle"],
        "matched_trial_count": payload["matched_trial_count"],
        "total_policy_runs": payload["total_policy_runs"],
        "policies": payload["policies"],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    config_lines = [
        "experiment_class: development_not_validation",
        f"bootstrap_resamples: {payload['bootstrap']['resamples']}",
        f"bootstrap_seed: {payload['bootstrap']['seed']}",
        f"cluster_definition: {payload['bootstrap']['cluster_definition']}",
        f"lambda_cost: {payload['utility_weights']['lambda_cost']}",
        f"eta_actions: {payload['utility_weights']['eta_actions']}",
        f"beta_harm: {payload['utility_weights']['beta_harm']}",
        "validation_authorized: false",
        "hardware_actuation_enabled: false",
    ]
    (output / "config.yaml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    environment = [
        f"python={sys.version.split()[0]}",
        f"implementation={platform.python_implementation()}",
        f"platform={platform.platform()}",
    ]
    (output / "environment.txt").write_text("\n".join(environment) + "\n", encoding="utf-8")
    (output / "source_tree.diff").write_text(
        _source_diff(Path(repo_root)), encoding="utf-8"
    )
    decision = """# Development Hidden v1 Decision

**Development acceptance: FAIL.**

- `development_acceptance: false`
- `validation_authorized: false`
- `hardware_gate: NOT READY`

QRTC did not establish a positive or sufficiently precise advantage over the strongest non-oracle development comparator. This archive is a failed development result, not a validation artifact, policy freeze, or authorization for hardware actuation.
"""
    (output / "DECISION.md").write_text(decision, encoding="utf-8")

    checksum_lines = []
    for name in ARCHIVE_FILES:
        digest = hashlib.sha256((output / name).read_bytes()).hexdigest()
        checksum_lines.append(f"{digest}  {name}")
    (output / "checksums.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive a failed development experiment")
    parser.add_argument(
        "--input",
        default="artifacts/phase6/HIDDEN_MECHANISM_DEVELOPMENT_BENCHMARK.json",
    )
    parser.add_argument(
        "--output",
        default="artifacts/rescueos_v0.1/development_hidden_v1_failed",
    )
    parser.add_argument("--repo-root", default="..")
    args = parser.parse_args()
    archive_failed_development(args.input, args.output, repo_root=args.repo_root)


if __name__ == "__main__":
    main()