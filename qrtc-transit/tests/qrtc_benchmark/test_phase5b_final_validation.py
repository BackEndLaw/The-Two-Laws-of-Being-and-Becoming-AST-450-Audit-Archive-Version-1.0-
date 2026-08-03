from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qrtc_benchmark.phase5b_final_validation import (
    AuthorizationValidationError,
    FinalValidationResultValidationError,
    load_final_validation_authorization,
    load_final_validation_result,
    run_final_validation,
    run_final_validation_preflight,
    verify_final_validation_reproducibility,
)
from qrtc_benchmark.selection_protocol import IMPLEMENTATION_COMMIT, PROTOCOL_ID

_ROOT = Path(__file__).resolve().parents[2]
_PROTOCOL_DIR = _ROOT / "artifacts" / "protocols" / PROTOCOL_ID
_ARTIFACTS_ROOT = _ROOT / "artifacts" / "phase5b-selection-v1"
_SELECTION_RESULT_PATH = (
    _ARTIFACTS_ROOT / "selection-validation-run-1" / "selection_result.json"
)
_SELECTION_SHA = hashlib.sha256(_SELECTION_RESULT_PATH.read_bytes()).hexdigest()


def _authorization_payload() -> dict[str, object]:
    return {
        "authorization_schema": "rescueos-final-validation-authorization-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": "fc6b86912182d216be4d381992732345cc5d6a38299d6c5946ab1b8fe2bfe77c",
        "selection_result_sha256": _SELECTION_SHA,
        "selected_controller_id": "qrtc",
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "source_base_commit": "54ac41b57af075dc2fa22cce66b6fe3ce7f5cffe",
        "stage": "final-validation",
        "authority": "recommend_only",
        "hardware_actuation_enabled": False,
        "one_time_execution_intent": "reproducibility_pair",
        "event_id": "phase5b-selection-v1-final-validation-run-1",
        "allowed_execution_indices": [1, 2],
    }


def test_authorization_loader_rejects_wrong_selected_controller() -> None:
    payload = _authorization_payload()
    payload["selected_controller_id"] = "greedy_gain"
    with pytest.raises(AuthorizationValidationError, match="selected_controller_id"):
        load_final_validation_authorization(payload)


def test_preflight_fails_closed_for_bad_authorization_hash(tmp_path: Path) -> None:
    payload = _authorization_payload()
    payload["selection_result_sha256"] = "0" * 64
    authorization_path = tmp_path / "auth.json"
    authorization_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(Exception, match="selection_result_sha256 mismatch"):
        run_final_validation_preflight(
            protocol_dir=_PROTOCOL_DIR,
            artifacts_root=_ARTIFACTS_ROOT,
            output_dir=tmp_path / "out",
            authorization_path=authorization_path,
            execution_index=1,
        )


def test_run_final_validation_creates_expected_artifacts(tmp_path: Path) -> None:
    authorization_path = tmp_path / "auth.json"
    authorization_path.write_text(
        json.dumps(_authorization_payload(), indent=2) + "\n", encoding="utf-8"
    )
    output_dir = tmp_path / "final-validation"
    result = run_final_validation(
        protocol_dir=_PROTOCOL_DIR,
        artifacts_root=_ARTIFACTS_ROOT,
        output_dir=output_dir,
        authorization_path=authorization_path,
        execution_index=1,
    )
    assert result.stage == "final-validation"
    assert result.selected_id == "qrtc"
    expected_files = {
        "final_validation_result.json",
        "selected_controller_metrics.json",
        "baseline_metrics.json",
        "oracle_metrics.json",
        "family_metrics.json",
        "final_gate_report.json",
        "paired_bootstrap_summary.json",
        "phase5_runs.csv",
        "run_manifest.json",
        "final_validation_manifest.json",
        "selected_controller_metrics.csv",
        "baseline_metrics.csv",
        "oracle_metrics.csv",
        "FINAL_VALIDATION_REPORT.md",
        "checksums.sha256",
    }
    assert expected_files.issubset({path.name for path in output_dir.iterdir()})


def test_final_result_loader_rejects_inconsistent_pass_outcome() -> None:
    payload = {
        "result_schema": "rescueos-final-validation-result-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": "fc6b86912182d216be4d381992732345cc5d6a38299d6c5946ab1b8fe2bfe77c",
        "authorization_sha256": "a" * 64,
        "bound_selection_result_sha256": _SELECTION_SHA,
        "phase_revision": "phase5b",
        "stage": "final-validation",
        "selected_id": "qrtc",
        "source_commit": "0" * 40,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "source_base_commit": "54ac41b57af075dc2fa22cce66b6fe3ce7f5cffe",
        "input_hashes": {"k": "a" * 64},
        "comparator_ids": ["greedy_gain", "oracle"],
        "metrics_summary": {},
        "family_metrics": {},
        "paired_bootstrap_vs_greedy": {},
        "oracle_regret": {},
        "final_gates": {"all_passed": False, "gate_results": {}},
        "outcome": "final_validation_passed",
        "outcome_reasons": ["x"],
        "authority": "recommend_only",
        "hardware_actuation_enabled": False,
        "deployment_approval": False,
        "physical_certification": False,
    }
    with pytest.raises(
        FinalValidationResultValidationError, match="inconsistent with gate failures"
    ):
        load_final_validation_result(payload, expected_selection_hash=_SELECTION_SHA)


def test_reproducibility_verifier_detects_identical_files(tmp_path: Path) -> None:
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"
    run1.mkdir()
    run2.mkdir()
    names = (
        "final_validation_result.json",
        "selected_controller_metrics.json",
        "baseline_metrics.json",
        "oracle_metrics.json",
        "family_metrics.json",
        "final_gate_report.json",
        "paired_bootstrap_summary.json",
        "phase5_runs.csv",
        "run_manifest.json",
        "final_validation_manifest.json",
        "selected_controller_metrics.csv",
        "baseline_metrics.csv",
        "oracle_metrics.csv",
        "FINAL_VALIDATION_REPORT.md",
        "checksums.sha256",
    )
    for name in names:
        (run1 / name).write_text("same\n", encoding="utf-8")
        (run2 / name).write_text("same\n", encoding="utf-8")
    passed, differences = verify_final_validation_reproducibility(run1, run2)
    assert passed
    assert differences == []
