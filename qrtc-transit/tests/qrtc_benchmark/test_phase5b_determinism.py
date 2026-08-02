"""Cross-process determinism tests for Phase V-B.

These tests run Phase V generation in separate subprocesses under multiple
different PYTHONHASHSEED values and assert that all output is byte-identical.
This directly validates that the _stable_hash refactoring has eliminated all
PYTHONHASHSEED-sensitive code paths.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


# A very small config that still exercises every family and every policy.
_DETERMINISM_CFG_ARGS = (
    "--bootstrap-reps=50",
    "--bootstrap-seed=9101",
)

# A Python script that generates the development split and prints checksums.
_WORKER_SCRIPT = """\
import hashlib, json, sys, tempfile
from pathlib import Path
from qrtc_benchmark.phase5 import Phase5Config, run_phase5_benchmark, build_phase5_trials

cfg = Phase5Config(
    bootstrap_reps=50,
    development_family_trials=24,
    validation_family_trials=16,
    test_family_trials=16,
)

with tempfile.TemporaryDirectory() as tmp:
    bundle = run_phase5_benchmark("development", Path(tmp), config=cfg)

    rows = bundle["rows"]
    # Collect identifiers and results for every row.
    row_ids = [
        (r.trial_id, r.split, r.family, r.mechanism_id, r.composition_id,
         r.policy, r.action_sequence, r.recovered, round(r.utility, 10))
        for r in rows
    ]

    # Collect manifest contents.
    manifest = json.loads(bundle["manifest_json"].read_text(encoding="utf-8"))

    # Collect checksums file content (relative-path-based, machine-independent).
    checksums_text = bundle["checksums"].read_text(encoding="utf-8")

    # Collect decision file content.
    decision = json.loads(bundle["decision"].read_text(encoding="utf-8"))

    result = {
        "row_count": len(row_ids),
        "row_ids_sha256": hashlib.sha256(
            json.dumps(row_ids, sort_keys=True).encode()
        ).hexdigest(),
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "checksums_sha256": hashlib.sha256(checksums_text.encode()).hexdigest(),
        "decision_sha256": hashlib.sha256(
            json.dumps(decision, sort_keys=True).encode()
        ).hexdigest(),
    }
    json.dump(result, sys.stdout)
"""


def _run_worker(seed: int) -> dict:
    """Run the worker script under a specific PYTHONHASHSEED and return parsed result."""
    env = {"PYTHONHASHSEED": str(seed), "PYTHONPATH": "src"}
    result = subprocess.run(
        [sys.executable, "-c", _WORKER_SCRIPT],
        capture_output=True,
        text=True,
        env={**_get_base_env(), **env},
        cwd=Path(__file__).resolve().parents[2],
        timeout=120,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Worker subprocess failed with PYTHONHASHSEED={seed}:\n"
            f"stdout: {result.stdout[:2000]}\n"
            f"stderr: {result.stderr[:2000]}"
        )
    return json.loads(result.stdout)


def _get_base_env() -> dict:
    """Return a clean environment suitable for subprocess workers."""
    import os

    return {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}


@pytest.mark.parametrize(
    "seeds",
    [
        (0, 1),
        (0, 42),
        (0, 12345),
        (1, 99),
    ],
)
def test_phase5b_cross_process_determinism(seeds: tuple[int, int]) -> None:
    """Phase V-B generation must produce identical output for any PYTHONHASHSEED pair."""
    seed_a, seed_b = seeds
    result_a = _run_worker(seed_a)
    result_b = _run_worker(seed_b)

    assert result_a["row_count"] == result_b["row_count"], (
        f"Row count differs: {result_a['row_count']} vs {result_b['row_count']} "
        f"(PYTHONHASHSEED {seed_a} vs {seed_b})"
    )
    assert result_a["row_ids_sha256"] == result_b["row_ids_sha256"], (
        f"Trial identities/results differ between PYTHONHASHSEED={seed_a} and "
        f"PYTHONHASHSEED={seed_b}.  "
        "This means a hash()-based selection path was not replaced."
    )
    assert (
        result_a["manifest_sha256"] == result_b["manifest_sha256"]
    ), "Manifests differ across PYTHONHASHSEED values."
    assert result_a["checksums_sha256"] == result_b["checksums_sha256"], (
        "Checksum files differ across PYTHONHASHSEED values.  "
        "Check that checksums use relative paths."
    )
    assert (
        result_a["decision_sha256"] == result_b["decision_sha256"]
    ), "Decision files differ across PYTHONHASHSEED values."


def test_phase5b_no_hash_dependency_in_source() -> None:
    """Confirm that no experiment-affecting built-in hash() remains in phase5.py."""
    import ast

    # __file__ is tests/qrtc_benchmark/test_phase5b_determinism.py
    # parents[0] = tests/qrtc_benchmark/
    # parents[1] = tests/
    # parents[2] = qrtc-transit/
    source_path = (
        Path(__file__).resolve().parents[2] / "src" / "qrtc_benchmark" / "phase5.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Detect bare hash(…) calls not inside _stable_hash itself.
            func = node.func
            if isinstance(func, ast.Name) and func.id == "hash":
                forbidden.append(f"line {node.lineno}: bare hash() call")

    assert not forbidden, (
        "Experiment-affecting built-in hash() calls found in phase5.py:\n"
        + "\n".join(forbidden)
    )
