from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
from typing import Any


def _family_interval(
    differences: dict[str, float], *, samples: int, seed: int
) -> dict[str, float]:
    values = list(differences.values())
    rng = random.Random(seed)
    draws = sorted(
        statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples)
    )
    lower = draws[int(0.025 * samples)]
    upper = draws[min(samples - 1, int(0.975 * samples))]
    return {
        "estimate": statistics.fmean(values),
        "lower_95": lower,
        "upper_95": upper,
        "half_width": (upper - lower) / 2.0,
        "independent_clusters": len(values),
    }


def build_reporting_lock(payload: dict[str, Any], *, artifact_sha256: str) -> dict[str, Any]:
    comparator = str(payload["strongest_nonoracle"])
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in payload["trials"]:
        grouped[
            (str(row["mechanism_family"]), str(row["cluster_id"]), str(row["policy"]))
        ].append(float(row["utility"]))
    family_differences: dict[str, dict[str, float]] = defaultdict(dict)
    for family, cluster, policy in sorted(grouped):
        if policy != "hybrid_qrtc":
            continue
        family_differences[family][cluster] = (
            statistics.fmean(grouped[(family, cluster, "hybrid_qrtc")])
            - statistics.fmean(grouped[(family, cluster, comparator)])
        )
    samples = int(payload["bootstrap"]["resamples"])
    seed = int(payload["bootstrap"]["seed"])
    return {
        "artifact_type": "adaptive_qrtc_v2_reporting_lock",
        "source_artifact_sha256": artifact_sha256,
        "primary_comparison": {
            "policy": "hybrid_qrtc",
            "comparator": comparator,
            "comparator_selection": "strongest non-oracle by complete LOFO development mean utility",
            "aggregate": payload["primary_hybrid_delta"],
        },
        "design": payload["design"],
        "bootstrap": payload["bootstrap"],
        "per_family_intervals": {
            family: _family_interval(
                differences,
                samples=samples,
                seed=seed + index + 10,
            )
            for index, (family, differences) in enumerate(sorted(family_differences.items()))
        },
        "development_acceptance": False,
        "validation_authorized": False,
        "hardware_gate": "NOT READY",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lock adaptive QRTC v2 reporting metadata")
    parser.add_argument("--input", default="artifacts/phase6/ADAPTIVE_QRTC_DEVELOPMENT_V2.json")
    parser.add_argument("--output", default="artifacts/phase6/ADAPTIVE_QRTC_DEVELOPMENT_V2_REPORTING_LOCK.json")
    args = parser.parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    artifact_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    output = Path(args.output)
    output.write_text(
        json.dumps(build_reporting_lock(payload, artifact_sha256=artifact_sha256), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()