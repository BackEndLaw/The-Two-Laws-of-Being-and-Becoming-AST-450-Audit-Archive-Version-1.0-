"""Tests for the Phase V-B closure index determinism and consistency.

These tests verify:
- The closure_index.json has the expected schema and all required fields.
- No actuation/deployment/certification flags are set to True.
- The controller ID is correct.
- All referenced artifact paths exist relative to the artifacts root.
- All artifact SHA-256 hashes in the index match the actual files on disk.
- The closure_index.sha256 checksum file matches the closure_index.json.
- Key fields are consistent with the canonical final_validation_result.json.
- Unknown fields are not silently accepted (strict schema check).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

_QRTC_TRANSIT_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACTS_ROOT = _QRTC_TRANSIT_ROOT / "artifacts" / "phase5b-selection-v1"
_CLOSURE_INDEX_PATH = _ARTIFACTS_ROOT / "closure_index.json"
_CLOSURE_SHA256_PATH = _ARTIFACTS_ROOT / "closure_index.sha256"
_FINAL_RESULT_PATH = (
    _ARTIFACTS_ROOT / "final-validation-run-1" / "final_validation_result.json"
)

# Required top-level fields in the closure index.
_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "protocol_id",
        "protocol_hash",
        "validated_controller_id",
        "validated_controller_version",
        "authority",
        "hardware_actuation_enabled",
        "deployment_approval",
        "physical_certification",
        "final_outcome",
        "final_result_schema",
        "validated_main_commit",
        "implementation_commit",
        "selection_result_sha256",
        "authorization_sha256",
        "stage_outcomes",
        "merge_commits",
        "artifacts",
        "headline_metrics",
        "all_final_gates_passed",
        "reproducibility",
    }
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


def _load_index() -> dict:  # type: ignore[type-arg]
    return json.loads(_CLOSURE_INDEX_PATH.read_bytes())


def test_closure_index_file_exists() -> None:
    assert _CLOSURE_INDEX_PATH.is_file(), "closure_index.json must exist"


def test_closure_sha256_file_exists() -> None:
    assert _CLOSURE_SHA256_PATH.is_file(), "closure_index.sha256 must exist"


def test_closure_index_is_valid_json() -> None:
    data = _load_index()
    assert isinstance(data, dict)


def test_closure_index_no_unknown_fields() -> None:
    data = _load_index()
    unknown = set(data.keys()) - _REQUIRED_FIELDS
    assert not unknown, f"Unexpected fields in closure_index.json: {unknown}"


def test_closure_index_no_missing_fields() -> None:
    data = _load_index()
    missing = _REQUIRED_FIELDS - set(data.keys())
    assert not missing, f"Missing fields in closure_index.json: {missing}"


def test_closure_index_schema() -> None:
    data = _load_index()
    assert data["schema"] == "rescueos-phase5b-closure-index-v1"


def test_closure_index_protocol_id() -> None:
    data = _load_index()
    assert data["protocol_id"] == "phase5b-selection-v1"


def test_closure_index_protocol_hash_format() -> None:
    data = _load_index()
    assert _HEX64_RE.match(data["protocol_hash"]), "protocol_hash must be 64 hex chars"


def test_closure_index_validated_controller_id() -> None:
    data = _load_index()
    assert data["validated_controller_id"] == "qrtc", (
        "validated_controller_id must be 'qrtc'"
    )


def test_closure_index_validated_controller_version() -> None:
    data = _load_index()
    assert data["validated_controller_version"] == "phase5b-rule-policy-v1", (
        "validated_controller_version must be 'phase5b-rule-policy-v1' (frozen controller "
        "implementation version), not the protocol ID"
    )


def test_closure_index_reproducibility_stage_keyed() -> None:
    """Reproducibility must be stage-keyed with correct seeds for each stage."""
    data = _load_index()
    repro = data["reproducibility"]
    assert "development" in repro, "reproducibility must contain 'development' key"
    assert "final_validation" in repro, (
        "reproducibility must contain 'final_validation' key"
    )
    assert repro["development"]["byte_identical_runs"] is True
    assert repro["development"]["registered_pythonhashseeds"] == [42, 999], (
        "development registered_pythonhashseeds must be [42, 999]"
    )
    assert repro["final_validation"]["byte_identical_runs"] is True
    assert repro["final_validation"]["registered_pythonhashseeds"] == [111, 222], (
        "final_validation registered_pythonhashseeds must be [111, 222]"
    )


def test_closure_index_actuation_disabled() -> None:
    data = _load_index()
    assert data["hardware_actuation_enabled"] is False, (
        "hardware_actuation_enabled must be false"
    )


def test_closure_index_deployment_approval_false() -> None:
    data = _load_index()
    assert data["deployment_approval"] is False, "deployment_approval must be false"


def test_closure_index_physical_certification_false() -> None:
    data = _load_index()
    assert data["physical_certification"] is False, (
        "physical_certification must be false"
    )


def test_closure_index_final_outcome() -> None:
    data = _load_index()
    assert data["final_outcome"] == "final_validation_passed"


def test_closure_index_authority() -> None:
    data = _load_index()
    assert data["authority"] == "recommend_only"


def test_closure_index_validated_main_commit_format() -> None:
    data = _load_index()
    assert _HEX40_RE.match(data["validated_main_commit"]), (
        "validated_main_commit must be 40 hex chars"
    )


def test_closure_index_implementation_commit_format() -> None:
    data = _load_index()
    assert _HEX40_RE.match(data["implementation_commit"]), (
        "implementation_commit must be 40 hex chars"
    )


def test_closure_index_selection_result_sha256_format() -> None:
    data = _load_index()
    assert _HEX64_RE.match(data["selection_result_sha256"]), (
        "selection_result_sha256 must be 64 hex chars"
    )


def test_closure_index_authorization_sha256_format() -> None:
    data = _load_index()
    assert _HEX64_RE.match(data["authorization_sha256"]), (
        "authorization_sha256 must be 64 hex chars"
    )


def test_closure_index_merge_commits_format() -> None:
    data = _load_index()
    commits = data["merge_commits"]
    assert isinstance(commits, dict), "merge_commits must be a dict"
    for pr, commit in commits.items():
        assert _HEX40_RE.match(commit), (
            f"merge_commits[{pr!r}] must be 40 hex chars, got {commit!r}"
        )


def test_closure_index_stage_outcomes() -> None:
    data = _load_index()
    outcomes = data["stage_outcomes"]
    assert outcomes["development"] == "development_completed_no_selection"
    assert outcomes["selection_validation"] == "provisional_selection"
    assert outcomes["final_validation"] == "final_validation_passed"


def test_closure_index_all_artifact_paths_exist() -> None:
    data = _load_index()
    artifacts = data["artifacts"]
    assert isinstance(artifacts, dict)
    for key, entry in artifacts.items():
        rel_path = entry["path"]
        abs_path = _QRTC_TRANSIT_ROOT / rel_path
        assert abs_path.is_file(), f"Artifact '{key}' path does not exist: {rel_path}"


def test_closure_index_artifact_sha256s_match() -> None:
    data = _load_index()
    artifacts = data["artifacts"]
    for key, entry in artifacts.items():
        rel_path = entry["path"]
        expected_sha = entry["sha256"]
        abs_path = _QRTC_TRANSIT_ROOT / rel_path
        actual_sha = hashlib.sha256(abs_path.read_bytes()).hexdigest()
        assert actual_sha == expected_sha, (
            f"SHA-256 mismatch for artifact '{key}' ({rel_path}): "
            f"expected {expected_sha}, got {actual_sha}"
        )


def test_closure_index_sha256_checksum_file_matches() -> None:
    """The closure_index.sha256 file must match the actual closure_index.json."""
    actual_sha = hashlib.sha256(_CLOSURE_INDEX_PATH.read_bytes()).hexdigest()
    line = _CLOSURE_SHA256_PATH.read_text(encoding="utf-8").strip()
    recorded_sha, _, name = line.partition("  ")
    assert name == "closure_index.json", (
        f"closure_index.sha256 must reference 'closure_index.json', got {name!r}"
    )
    assert recorded_sha == actual_sha, (
        f"closure_index.sha256 mismatch: recorded {recorded_sha}, actual {actual_sha}"
    )


def test_closure_index_consistent_with_final_result() -> None:
    """Key fields in closure_index.json must match the canonical final result."""
    index = _load_index()
    result = json.loads(_FINAL_RESULT_PATH.read_bytes())

    assert index["protocol_id"] == result["protocol_id"]
    assert index["protocol_hash"] == result["protocol_hash"]
    assert index["validated_controller_id"] == result["selected_id"]
    assert index["final_outcome"] == result["outcome"]
    assert index["final_result_schema"] == result["result_schema"]
    assert index["hardware_actuation_enabled"] == result["hardware_actuation_enabled"]
    assert index["deployment_approval"] == result["deployment_approval"]
    assert index["physical_certification"] == result["physical_certification"]
    assert index["authority"] == result["authority"]
    assert index["selection_result_sha256"] == result["bound_selection_result_sha256"]
    assert index["authorization_sha256"] == result["authorization_sha256"]
    assert index["implementation_commit"] == result["implementation_commit"]


def test_closure_index_headline_metrics_consistent_with_final_result() -> None:
    """Headline metrics in closure_index.json must match the final result."""
    index = _load_index()
    result = json.loads(_FINAL_RESULT_PATH.read_bytes())

    qrtc_metrics = result["metrics_summary"]["qrtc"]
    hm = index["headline_metrics"]
    assert hm["mean_utility"] == pytest.approx(qrtc_metrics["mean_utility"])
    assert hm["recovery_rate"] == pytest.approx(qrtc_metrics["recovery_rate"])
    assert hm["mean_harm"] == pytest.approx(qrtc_metrics["mean_harm"])
    assert hm["unsafe_commitment_rate"] == pytest.approx(
        qrtc_metrics["unsafe_commitment_rate"]
    )
    assert hm["oracle_regret"] == pytest.approx(qrtc_metrics["oracle_regret"])

    bootstrap = result["paired_bootstrap_vs_greedy"]
    assert hm["paired_utility_delta_vs_greedy_gain"] == pytest.approx(
        bootstrap["mean_difference"]
    )
    assert hm["paired_utility_ci_low"] == pytest.approx(bootstrap["ci_low"])
    assert hm["paired_utility_ci_high"] == pytest.approx(bootstrap["ci_high"])
    assert hm["win_rate_vs_greedy_gain"] == pytest.approx(bootstrap["win_rate"])


def test_closure_index_all_final_gates_passed_consistent() -> None:
    index = _load_index()
    result = json.loads(_FINAL_RESULT_PATH.read_bytes())
    assert index["all_final_gates_passed"] == result["final_gates"]["all_passed"]


def test_closure_index_determinism() -> None:
    """Re-reading and re-serializing the closure index produces identical bytes."""
    raw_bytes = _CLOSURE_INDEX_PATH.read_bytes()
    data = json.loads(raw_bytes)
    re_serialized = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    # The stored file must already be in canonical form.
    assert raw_bytes == re_serialized, (
        "closure_index.json is not in canonical (json.dumps indent=2) form; "
        "regenerate it with the canonical serializer"
    )
