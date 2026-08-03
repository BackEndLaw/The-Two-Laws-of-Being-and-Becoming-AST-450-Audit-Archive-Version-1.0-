from __future__ import annotations

import json
from pathlib import Path

from qrtc_benchmark.phase5b_selection_validation import (
    run_selection_validation,
    run_selection_validation_preflight,
    verify_selection_validation_reproducibility,
)
from qrtc_benchmark.result_schema import SelectionResultV1, load_selection_result
from qrtc_benchmark.selection_protocol import PROTOCOL_ID, compute_protocol_hashes

_ROOT = Path(__file__).resolve().parents[2]
_PROTOCOL_DIR = _ROOT / "artifacts" / "protocols" / PROTOCOL_ID
_ARTIFACTS_ROOT = _ROOT / "artifacts" / "phase5b-selection-v1"


def test_selection_validation_preflight_passes(tmp_path: Path) -> None:
    report = run_selection_validation_preflight(
        protocol_dir=_PROTOCOL_DIR,
        artifacts_root=_ARTIFACTS_ROOT,
        output_dir=tmp_path / "unused-output",
    )
    assert report["status"] == "ok"
    assert report["protocol_id"] == PROTOCOL_ID
    assert report["stage"] == "selection-validation"


def test_run_selection_validation_creates_expected_artifacts(tmp_path: Path) -> None:
    result = run_selection_validation(
        protocol_dir=_PROTOCOL_DIR,
        artifacts_root=_ARTIFACTS_ROOT,
        output_dir=tmp_path / "selection-run",
    )
    assert isinstance(result, SelectionResultV1)
    expected_files = {
        "selection_result.json",
        "candidate_metrics.json",
        "candidate_metrics.csv",
        "family_metrics.json",
        "eligibility_report.json",
        "paired_comparisons.json",
        "phase5_runs.csv",
        "selection_validation_manifest.json",
        "run_manifest.json",
        "checksums.sha256",
        "SELECTION_VALIDATION_REPORT.md",
    }
    assert expected_files.issubset(
        {path.name for path in (tmp_path / "selection-run").iterdir()}
    )
    assert result.stage == "selection-validation"
    assert result.final_validation_status == "locked_not_executed"


def test_run_selection_validation_round_trips_canonical_result(tmp_path: Path) -> None:
    output_dir = tmp_path / "selection-run"
    run_selection_validation(
        protocol_dir=_PROTOCOL_DIR,
        artifacts_root=_ARTIFACTS_ROOT,
        output_dir=output_dir,
    )
    payload = json.loads(
        (output_dir / "selection_result.json").read_text(encoding="utf-8")
    )
    result = load_selection_result(payload)
    assert result.protocol_id == PROTOCOL_ID
    assert result.protocol_hash == compute_protocol_hashes().protocol_declaration_sha256
    assert result.source_commit


def test_selection_validation_reproducibility_verifier_detects_matching_runs(
    tmp_path: Path,
) -> None:
    run1 = tmp_path / "run-1"
    run2 = tmp_path / "run-2"
    run_selection_validation(
        protocol_dir=_PROTOCOL_DIR,
        artifacts_root=_ARTIFACTS_ROOT,
        output_dir=run1,
    )
    run_selection_validation(
        protocol_dir=_PROTOCOL_DIR,
        artifacts_root=_ARTIFACTS_ROOT,
        output_dir=run2,
    )
    passed, differences = verify_selection_validation_reproducibility(run1, run2)
    assert passed, differences
    assert differences == []
