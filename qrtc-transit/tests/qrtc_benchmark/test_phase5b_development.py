"""Tests for Phase V-B Development Comparison (Stage 1).

Covers:
- DevelopmentResultV1 schema validation
- load_development_result fail-closed validation
- run_development_comparison output structure
- artifact integrity
- forbidden splits not generated
- no controller selected
- reproducibility check
- repository scan: no validation/test rows in artifacts
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from qrtc_benchmark.phase5 import Phase5Config
from qrtc_benchmark.phase5b_development import (
    run_development_comparison,
    verify_reproducibility,
)
from qrtc_benchmark.result_schema import (
    _DEVELOPMENT_OUTCOME,
    DEVELOPMENT_RESULT_SCHEMA,
    DevelopmentResultV1,
    DevelopmentResultValidationError,
    load_development_result,
)
from qrtc_benchmark.selection_protocol import (
    IMPLEMENTATION_COMMIT,
    MANDATORY_CANDIDATES,
    PROTOCOL_ID,
    PROTOCOL_PHASE_REVISION,
    compute_protocol_hashes,
)

# ── Path helpers ───────────────────────────────────────────────────────────────

_PROTOCOL_DIR = (
    Path(__file__).parent.parent.parent
    / "artifacts"
    / "protocols"
    / "phase5b-selection-v1"
)


def _small_config() -> Phase5Config:
    """Return a tiny Phase5Config for fast unit tests."""
    return Phase5Config(development_family_trials=20, bootstrap_reps=10)


# ── DevelopmentResultV1 validation tests ──────────────────────────────────────


def _valid_payload() -> dict:
    protocol_hash = compute_protocol_hashes().protocol_declaration_sha256
    return {
        "result_schema": DEVELOPMENT_RESULT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": protocol_hash,
        "phase_revision": PROTOCOL_PHASE_REVISION,
        "stage": "development",
        "outcome": _DEVELOPMENT_OUTCOME,
        "selected_id": None,
        "authority": "recommend_only",
        "hardware_actuation_enabled": False,
        "selection_validation_status": "not_executed",
        "final_validation_status": "locked_not_executed",
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "source_commit": "0" * 40,
        "input_hashes": {"test": "a" * 64},
        "run_trial_count": 100,
        "metrics_summary": {},
        "bootstrap_comparisons": {},
        "integrity_all_passed": True,
        "integrity_notes": [],
    }


def test_load_development_result_roundtrip() -> None:
    payload = _valid_payload()
    result = load_development_result(payload)
    assert result.outcome == _DEVELOPMENT_OUTCOME
    assert result.selected_id is None
    assert result.result_schema == DEVELOPMENT_RESULT_SCHEMA
    assert result.stage == "development"
    assert result.selection_validation_status == "not_executed"
    assert result.final_validation_status == "locked_not_executed"
    assert result.authority == "recommend_only"
    assert result.hardware_actuation_enabled is False


def test_load_development_result_wrong_schema() -> None:
    payload = _valid_payload()
    payload["result_schema"] = "rescueos-selection-result-v1"
    with pytest.raises(DevelopmentResultValidationError, match="result_schema"):
        load_development_result(payload)


def test_load_development_result_wrong_stage() -> None:
    payload = _valid_payload()
    payload["stage"] = "selection-validation"
    with pytest.raises(DevelopmentResultValidationError, match="stage"):
        load_development_result(payload)


def test_load_development_result_wrong_outcome() -> None:
    payload = _valid_payload()
    payload["outcome"] = "provisional_selection"
    with pytest.raises(DevelopmentResultValidationError, match="outcome"):
        load_development_result(payload)


def test_load_development_result_non_null_selected_id() -> None:
    payload = _valid_payload()
    payload["selected_id"] = "qrtc"
    with pytest.raises(
        DevelopmentResultValidationError, match="selected_id must be null"
    ):
        load_development_result(payload)


def test_load_development_result_wrong_authority() -> None:
    payload = _valid_payload()
    payload["authority"] = "executive"
    with pytest.raises(DevelopmentResultValidationError, match="authority"):
        load_development_result(payload)


def test_load_development_result_hardware_actuation_enabled() -> None:
    payload = _valid_payload()
    payload["hardware_actuation_enabled"] = True
    with pytest.raises(
        DevelopmentResultValidationError, match="hardware_actuation_enabled"
    ):
        load_development_result(payload)


def test_load_development_result_wrong_selection_validation_status() -> None:
    payload = _valid_payload()
    payload["selection_validation_status"] = "executed"
    with pytest.raises(
        DevelopmentResultValidationError, match="selection_validation_status"
    ):
        load_development_result(payload)


def test_load_development_result_wrong_final_validation_status() -> None:
    payload = _valid_payload()
    payload["final_validation_status"] = "executed"
    with pytest.raises(
        DevelopmentResultValidationError, match="final_validation_status"
    ):
        load_development_result(payload)


def test_load_development_result_missing_fields() -> None:
    payload = _valid_payload()
    del payload["outcome"]
    with pytest.raises(DevelopmentResultValidationError, match="missing"):
        load_development_result(payload)


def test_load_development_result_extra_fields() -> None:
    payload = _valid_payload()
    payload["extra_field"] = "oops"
    with pytest.raises(DevelopmentResultValidationError, match="extra"):
        load_development_result(payload)


def test_load_development_result_bad_protocol_hash() -> None:
    payload = _valid_payload()
    payload["protocol_hash"] = "b" * 64
    with pytest.raises(DevelopmentResultValidationError, match="protocol_hash"):
        load_development_result(payload)


def test_load_development_result_wrong_protocol_id() -> None:
    payload = _valid_payload()
    payload["protocol_id"] = "other-protocol"
    with pytest.raises(DevelopmentResultValidationError, match="protocol_id"):
        load_development_result(payload)


def test_load_development_result_negative_trial_count() -> None:
    payload = _valid_payload()
    payload["run_trial_count"] = -1
    with pytest.raises(DevelopmentResultValidationError, match="run_trial_count"):
        load_development_result(payload)


def test_load_development_result_invalid_input_hash() -> None:
    payload = _valid_payload()
    payload["input_hashes"] = {"bad": "not-a-hex-hash"}
    with pytest.raises(DevelopmentResultValidationError, match="input_hashes"):
        load_development_result(payload)


# ── Integration tests for run_development_comparison ──────────────────────────


def test_run_development_comparison_basic() -> None:
    """run_development_comparison produces a valid DevelopmentResultV1."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        result = run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=output_dir,
            config=_small_config(),
        )
    assert isinstance(result, DevelopmentResultV1)
    assert result.outcome == _DEVELOPMENT_OUTCOME
    assert result.selected_id is None
    assert result.selection_validation_status == "not_executed"
    assert result.final_validation_status == "locked_not_executed"
    assert result.integrity_all_passed is True
    assert result.run_trial_count > 0


def test_run_development_comparison_artifacts_created() -> None:
    """All expected artifact files are created."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=output_dir,
            config=_small_config(),
        )
        expected_files = [
            "development_result.json",
            "candidate_metrics.json",
            "candidate_metrics.csv",
            "family_metrics.json",
            "paired_comparisons.json",
            "phase5_runs.csv",
            "development_manifest.json",
            "run_manifest.json",
            "checksums.sha256",
            "DEVELOPMENT_REPORT.md",
        ]
        for fname in expected_files:
            assert (output_dir / fname).exists(), f"Missing artifact: {fname}"


def test_run_development_comparison_no_forbidden_splits() -> None:
    """No selection-validation or final-validation rows are generated."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=output_dir,
            config=_small_config(),
        )
        # Check no forbidden subdirectories
        for forbidden in (
            "selection-validation",
            "final-validation",
            "validation",
            "test",
        ):
            assert not (output_dir / forbidden).exists(), (
                f"Forbidden directory exists: {forbidden}"
            )
        # Scan trials CSV for forbidden split names
        runs_csv = output_dir / "phase5_runs.csv"
        content = runs_csv.read_text(encoding="utf-8")
        assert "selection-validation" not in content
        assert "final-validation" not in content


def test_run_development_comparison_all_mandatory_candidates() -> None:
    """All mandatory candidates appear in the metrics summary."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        result = run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=output_dir,
            config=_small_config(),
        )
    for cid in MANDATORY_CANDIDATES:
        assert cid in result.metrics_summary, (
            f"Missing candidate {cid!r} in metrics_summary"
        )


def test_run_development_comparison_development_result_roundtrip() -> None:
    """development_result.json can be loaded by load_development_result."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=output_dir,
            config=_small_config(),
        )
        payload = json.loads((output_dir / "development_result.json").read_text())
        validated = load_development_result(payload)
        assert validated.outcome == _DEVELOPMENT_OUTCOME
        assert validated.selected_id is None


def test_run_development_comparison_checksums_verify() -> None:
    """Checksums written by the runner are self-consistent."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=output_dir,
            config=_small_config(),
        )
        import hashlib

        checksums_text = (output_dir / "checksums.sha256").read_text(encoding="utf-8")
        for line in checksums_text.splitlines():
            line = line.strip()
            if not line:
                continue
            digest, rel_path = line.split("  ", 1)
            actual = hashlib.sha256((output_dir / rel_path).read_bytes()).hexdigest()
            assert actual == digest, f"Checksum mismatch for {rel_path}"


def test_run_development_comparison_no_winner_declared() -> None:
    """Development report explicitly states no controller was selected."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=output_dir,
            config=_small_config(),
        )
        report_text = (output_dir / "DEVELOPMENT_REPORT.md").read_text(encoding="utf-8")
        assert (
            "no controller" in report_text.lower()
            or "no_controller" in report_text.lower()
        )
        assert "selection-validation" in report_text.lower()
        assert "final-validation" in report_text.lower()


def test_run_development_comparison_paired_comparisons_non_selective_label() -> None:
    """All bootstrap comparison entries carry the non-selective label."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=output_dir,
            config=_small_config(),
        )
        comparisons = json.loads((output_dir / "paired_comparisons.json").read_text())
        for key, comp in comparisons.items():
            if key.startswith("_"):
                continue
            if isinstance(comp, dict) and "label" in comp:
                assert comp["label"] == "non-selective development diagnostic", (
                    f"Comparison {key!r} has wrong label: {comp['label']!r}"
                )


# ── Reproducibility tests ──────────────────────────────────────────────────────


def test_verify_reproducibility_passes_for_identical_runs() -> None:
    """verify_reproducibility returns True when both runs are identical."""
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        run1 = Path(tmp1)
        run2 = Path(tmp2)
        config = _small_config()
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=run1,
            config=config,
        )
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=run2,
            config=config,
        )
        passed, diffs = verify_reproducibility(run1, run2)
        assert passed, f"Reproducibility failed: {diffs}"
        assert diffs == []


def test_verify_reproducibility_fails_for_different_configs() -> None:
    """verify_reproducibility returns False when configs differ."""
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        run1 = Path(tmp1)
        run2 = Path(tmp2)
        cfg1 = Phase5Config(development_family_trials=15, bootstrap_reps=10)
        cfg2 = Phase5Config(development_family_trials=20, bootstrap_reps=10)
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=run1,
            config=cfg1,
        )
        run_development_comparison(
            protocol_dir=_PROTOCOL_DIR,
            output_dir=run2,
            config=cfg2,
        )
        passed, _diffs = verify_reproducibility(run1, run2)
        assert not passed


# ── Canonical artifact repository scan ─────────────────────────────────────────


def test_canonical_development_run1_no_forbidden_splits() -> None:
    """The committed development-run-1 artifacts contain no validation/test rows."""
    run1_dir = (
        Path(__file__).parent.parent.parent
        / "artifacts"
        / "phase5b-selection-v1"
        / "development-run-1"
    )
    if not run1_dir.exists():
        pytest.skip("development-run-1 not yet committed")

    runs_csv = run1_dir / "phase5_runs.csv"
    if runs_csv.exists():
        content = runs_csv.read_text(encoding="utf-8")
        assert "selection-validation" not in content, (
            "Forbidden split 'selection-validation' found in canonical trials"
        )
        assert "final-validation" not in content, (
            "Forbidden split 'final-validation' found in canonical trials"
        )


def test_canonical_development_run1_result_loads() -> None:
    """The committed development_result.json passes validation."""
    run1_dir = (
        Path(__file__).parent.parent.parent
        / "artifacts"
        / "phase5b-selection-v1"
        / "development-run-1"
    )
    if not run1_dir.exists():
        pytest.skip("development-run-1 not yet committed")

    result_path = run1_dir / "development_result.json"
    if not result_path.exists():
        pytest.skip("development_result.json not yet committed")

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    result = load_development_result(payload)
    assert result.outcome == _DEVELOPMENT_OUTCOME
    assert result.selected_id is None
    assert result.selection_validation_status == "not_executed"
    assert result.final_validation_status == "locked_not_executed"
    assert result.integrity_all_passed is True


def test_canonical_development_run1_checksums() -> None:
    """The committed checksums.sha256 verifies all canonical artifacts."""
    import hashlib

    run1_dir = (
        Path(__file__).parent.parent.parent
        / "artifacts"
        / "phase5b-selection-v1"
        / "development-run-1"
    )
    if not run1_dir.exists():
        pytest.skip("development-run-1 not yet committed")

    checksums_path = run1_dir / "checksums.sha256"
    if not checksums_path.exists():
        pytest.skip("checksums.sha256 not yet committed")

    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, rel_path = line.split("  ", 1)
        file_path = run1_dir / rel_path
        assert file_path.exists(), f"Referenced file missing: {rel_path}"
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual == digest, f"Checksum mismatch for {rel_path}"
