"""
Focused tests for the CARLA-specific QRTC policy integration.

These tests cover:
- Successful CARLA projection acceptance with a configurable principal
- Rejection for an unauthorized/mismatched principal
- Rejection for incomplete ticks
- Rejection for missing/invalid lidar evidence when lidar is enabled
- Rejection for NaN/infinite/negative telemetry
- Existing equipment telemetry policy behavior remains unchanged
- Detailed authorization/guard reasons in submission results
- Accepted and rejected outcomes are persisted in the evidence database
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from qrtc.carla_config import CarlaConfig
from qrtc.carla_telemetry import (
    QrtcProjection,
    QrtcSubmissionResult,
    build_qrtc_projection,
    submit_to_qrtc_pipeline,
)
from qrtc.evidence_store import EvidenceStore
from qrtc.registry import (
    _CARLA_RECOGNIZED_STATUSES,
    _carla_health_guard,
    _carla_schema_guard,
    build_default_registry,
)
from qrtc.transit import TransitEnvelope, AuthorizationDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CARLA_POLICY_PATH = str(
    Path(__file__).resolve().parents[1] / "examples" / "carla-policy.json"
)
_TELEMETRY_POLICY_PATH = str(
    Path(__file__).resolve().parents[1] / "examples" / "telemetry-policy.json"
)


def _completed_report(
    principal: str = "BackEndLaw",
    ticks: int = 300,
    lidar_enabled: bool = True,
    lidar_frames: int = 300,
    collision_count: int = 0,
    displacement_m: float = 42.0,
    mean_speed_mps: float = 5.0,
    max_speed_mps: float = 8.0,
    status: str = "completed",
    ticks_completed: int | None = None,
) -> dict[str, Any]:
    """Return a valid completed CARLA run report."""
    if ticks_completed is None:
        ticks_completed = ticks
    return {
        "run_id": "test-carla-run-001",
        "run_timestamp_utc": "2026-08-01T19:13:53+00:00",
        "status": status,
        "client_version": "0.9.16",
        "server_version": "0.9.16",
        "map_name": "Carla/Maps/Town10HD_Opt",
        "blueprint": "vehicle.tesla.model3",
        "actor_id": 28,
        "actor_type_id": "vehicle.tesla.model3",
        "spawn_point_index": 0,
        "ticks_requested": ticks,
        "ticks_completed": ticks_completed,
        "missing_data_count": 0,
        "principal": principal,
        "destination": "carla-drive-record",
        "config": CarlaConfig(ticks=ticks).as_dict(),
        "summary": {
            "collision_count": collision_count,
            "displacement_m": displacement_m,
            "mean_speed_mps": mean_speed_mps,
            "max_speed_mps": max_speed_mps,
        },
        "collision_events": [],
        "samples": [],
        "lidar_summary": {
            "frames_received": lidar_frames if lidar_enabled else 0,
            "frames_dropped": 0,
            "callback_errors": 0,
            "total_points": 176167 if lidar_enabled else 0,
            "total_invalid": 0,
            "nearest_obstacle_overall": 2.55 if lidar_enabled else None,
            "nearest_obstacle_front": 4.37 if lidar_enabled else None,
            "mean_nearest_front": 4.81 if lidar_enabled else None,
        },
        "lidar_frame_evidence": [],
    }


def _make_envelope(interface: dict[str, Any]) -> TransitEnvelope:
    """Wrap interface fields in a minimal TransitEnvelope for guard testing."""
    auth = AuthorizationDecision(
        qualified=True,
        key_id="carla-key-v1",
        policy_version="1.0.0",
        reason="test",
        principal="BackEndLaw",
    )
    return TransitEnvelope(
        transit_id="test-id",
        principal="BackEndLaw",
        predecessor_class="carla-telemetry",
        declared_future="carla-drive-evidence",
        destination="carla-drive-record",
        policy_version="1.0.0",
        route_version="carla-drive-route-v1",
        schema_version="carla-interface-v1",
        encoding_version="canonical-json-v1",
        authorization=auth,
        interface=interface,
    )


def _projection_for(
    report: dict[str, Any],
    principal: str = "BackEndLaw",
    destination: str = "carla-drive-record",
) -> QrtcProjection:
    base = build_qrtc_projection(report, principal=principal, destination=destination)
    return base


# ---------------------------------------------------------------------------
# carla-policy.json loads correctly
# ---------------------------------------------------------------------------


def test_carla_policy_file_exists() -> None:
    assert Path(_CARLA_POLICY_PATH).exists(), "carla-policy.json not found in examples/"


def test_carla_policy_has_distinct_component_ids() -> None:
    from qrtc.policy import load_policy_document

    policy = load_policy_document(_CARLA_POLICY_PATH)
    assert policy.policy_id == "carla-drive-transit"
    assert policy.key_policy == "carla-key-v1"
    assert policy.gate == "carla-gate-v1"
    assert "carla-schema-v1" in policy.guards
    assert "carla-health-v1" in policy.guards
    assert policy.boat_schema == "carla-interface-v1"
    assert policy.realizer == "carla-drive-record-v1"
    assert policy.stabilizer == "carla-persistence-v1"
    assert policy.witness_policy == "carla-witness-v1"


def test_carla_policy_components_differ_from_telemetry_policy() -> None:
    from qrtc.policy import load_policy_document

    carla_p = load_policy_document(_CARLA_POLICY_PATH)
    tel_p = load_policy_document(_TELEMETRY_POLICY_PATH)
    assert carla_p.key_policy != tel_p.key_policy
    assert carla_p.gate != tel_p.gate
    assert set(carla_p.guards).isdisjoint(set(tel_p.guards))
    assert carla_p.realizer != tel_p.realizer
    assert carla_p.stabilizer != tel_p.stabilizer


# ---------------------------------------------------------------------------
# Default registry contains CARLA components
# ---------------------------------------------------------------------------


def test_registry_has_carla_key_policy() -> None:
    reg = build_default_registry(carla_principal="BackEndLaw")
    assert "carla-key-v1" in reg.key_policies


def test_registry_has_carla_gate() -> None:
    reg = build_default_registry(carla_principal="BackEndLaw")
    assert "carla-gate-v1" in reg.gates


def test_registry_has_carla_guards() -> None:
    reg = build_default_registry(carla_principal="BackEndLaw")
    assert "carla-schema-v1" in reg.guards
    assert "carla-health-v1" in reg.guards


def test_registry_has_carla_boat() -> None:
    reg = build_default_registry(carla_principal="BackEndLaw")
    assert "carla-json-v1" in reg.boats


def test_registry_has_carla_realizer_and_stabilizer() -> None:
    reg = build_default_registry(carla_principal="BackEndLaw")
    assert "carla-drive-record-v1" in reg.realizers
    assert "carla-persistence-v1" in reg.stabilizers


def test_existing_equipment_telemetry_components_unchanged() -> None:
    reg = build_default_registry()
    assert "telemetry-key-v1" in reg.key_policies
    assert "telemetry-gate-v1" in reg.gates
    assert "telemetry-schema-v1" in reg.guards
    assert "telemetry-ranges-v1" in reg.guards
    assert "canonical-json-v1" in reg.boats
    assert "alarm-record-v1" in reg.realizers
    assert "alarm-persistence-v1" in reg.stabilizers


# ---------------------------------------------------------------------------
# CARLA schema guard unit tests
# ---------------------------------------------------------------------------


def _valid_schema_iface() -> dict[str, Any]:
    return {
        "status": "completed",
        "ticks_requested": 300,
        "ticks_completed": 300,
        "collision_count": 0,
        "missing_data_count": 0,
    }


def test_carla_schema_guard_accepts_valid() -> None:
    env = _make_envelope(_valid_schema_iface())
    assert _carla_schema_guard(env) is True


@pytest.mark.parametrize("status", sorted(_CARLA_RECOGNIZED_STATUSES))
def test_carla_schema_guard_accepts_all_recognized_statuses(status: str) -> None:
    iface = _valid_schema_iface()
    iface["status"] = status
    # For non-completed statuses, ticks_completed need not equal ticks_requested
    if status != "completed":
        iface["ticks_completed"] = 0
    env = _make_envelope(iface)
    assert _carla_schema_guard(env) is True


def test_carla_schema_guard_rejects_unknown_status() -> None:
    iface = _valid_schema_iface()
    iface["status"] = "flying"
    env = _make_envelope(iface)
    assert _carla_schema_guard(env) is False


def test_carla_schema_guard_rejects_missing_status() -> None:
    iface = _valid_schema_iface()
    del iface["status"]
    env = _make_envelope(iface)
    assert _carla_schema_guard(env) is False


def test_carla_schema_guard_rejects_zero_ticks_requested() -> None:
    iface = _valid_schema_iface()
    iface["ticks_requested"] = 0
    env = _make_envelope(iface)
    assert _carla_schema_guard(env) is False


def test_carla_schema_guard_rejects_negative_ticks_requested() -> None:
    iface = _valid_schema_iface()
    iface["ticks_requested"] = -1
    env = _make_envelope(iface)
    assert _carla_schema_guard(env) is False


def test_carla_schema_guard_rejects_incomplete_completed_run() -> None:
    iface = _valid_schema_iface()
    iface["ticks_completed"] = 299  # One tick short
    env = _make_envelope(iface)
    assert _carla_schema_guard(env) is False


def test_carla_schema_guard_rejects_negative_collision_count() -> None:
    iface = _valid_schema_iface()
    iface["collision_count"] = -1
    env = _make_envelope(iface)
    assert _carla_schema_guard(env) is False


def test_carla_schema_guard_rejects_negative_missing_data() -> None:
    iface = _valid_schema_iface()
    iface["missing_data_count"] = -5
    env = _make_envelope(iface)
    assert _carla_schema_guard(env) is False


# ---------------------------------------------------------------------------
# CARLA health guard unit tests
# ---------------------------------------------------------------------------


def _valid_health_iface() -> dict[str, Any]:
    return {
        "displacement_m": 42.0,
        "mean_speed_mps": 5.0,
        "max_speed_mps": 8.0,
        "lidar_enabled": True,
        "lidar_frames_received": 300,
        "lidar_frames_dropped": 0,
        "lidar_callback_errors": 0,
        "ticks_completed": 300,
        "lidar_nearest_obstacle_m": 2.55,
        "lidar_nearest_front_m": 4.37,
    }


def test_carla_health_guard_accepts_valid() -> None:
    env = _make_envelope(_valid_health_iface())
    assert _carla_health_guard(env) is True


def test_carla_health_guard_accepts_lidar_disabled() -> None:
    iface = _valid_health_iface()
    iface["lidar_enabled"] = False
    iface["lidar_frames_received"] = 0
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is True


def test_carla_health_guard_rejects_negative_displacement() -> None:
    iface = _valid_health_iface()
    iface["displacement_m"] = -1.0
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is False


def test_carla_health_guard_rejects_nan_displacement() -> None:
    iface = _valid_health_iface()
    iface["displacement_m"] = math.nan
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is False


def test_carla_health_guard_rejects_inf_displacement() -> None:
    iface = _valid_health_iface()
    iface["displacement_m"] = math.inf
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is False


def test_carla_health_guard_rejects_nan_mean_speed() -> None:
    iface = _valid_health_iface()
    iface["mean_speed_mps"] = math.nan
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is False


def test_carla_health_guard_rejects_negative_max_speed() -> None:
    iface = _valid_health_iface()
    iface["max_speed_mps"] = -0.1
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is False


def test_carla_health_guard_accepts_none_speeds() -> None:
    iface = _valid_health_iface()
    iface["mean_speed_mps"] = None
    iface["max_speed_mps"] = None
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is True


def test_carla_health_guard_rejects_lidar_zero_frames_when_enabled() -> None:
    iface = _valid_health_iface()
    iface["lidar_enabled"] = True
    iface["lidar_frames_received"] = 0
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is False


def test_carla_health_guard_rejects_nan_lidar_nearest() -> None:
    iface = _valid_health_iface()
    iface["lidar_nearest_obstacle_m"] = math.nan
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is False


def test_carla_health_guard_rejects_negative_lidar_nearest_front() -> None:
    iface = _valid_health_iface()
    iface["lidar_nearest_front_m"] = -0.5
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is False


def test_carla_health_guard_accepts_none_lidar_nearest_when_enabled() -> None:
    iface = _valid_health_iface()
    iface["lidar_nearest_obstacle_m"] = None
    iface["lidar_nearest_front_m"] = None
    env = _make_envelope(iface)
    assert _carla_health_guard(env) is True


# ---------------------------------------------------------------------------
# End-to-end submission: acceptance
# ---------------------------------------------------------------------------


def test_carla_submission_accepted_with_correct_principal(tmp_path: Path) -> None:
    """A completed, valid CARLA run is accepted when principal matches the key."""
    report = _completed_report(principal="BackEndLaw")
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.submitted is True
    assert result.status == "accepted"
    assert result.evidence_preserved is True
    assert result.transit_id is not None


def test_carla_submission_accepted_default_principal(tmp_path: Path) -> None:
    """Default principal 'carla-operator' is accepted when both sides use the same value."""
    report = _completed_report(principal="carla-operator")
    proj = _projection_for(report, principal="carla-operator")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="carla-operator",
    )
    assert result.submitted is True
    assert result.status == "accepted"


def test_carla_submission_populates_authorization_reason_on_accept(
    tmp_path: Path,
) -> None:
    """Accepted result exposes the authorization reason string."""
    report = _completed_report(principal="BackEndLaw")
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.authorization_reason is not None
    assert isinstance(result.authorization_reason, str)
    assert len(result.authorization_reason) > 0


def test_carla_submission_populates_guard_reasons_on_accept(tmp_path: Path) -> None:
    """Accepted result exposes guard decision records."""
    report = _completed_report(principal="BackEndLaw")
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert len(result.guard_reasons) >= 2
    for gr in result.guard_reasons:
        assert "guard_id" in gr
        assert "qualified" in gr
        assert "reason" in gr
        assert gr["qualified"] is True


# ---------------------------------------------------------------------------
# End-to-end submission: rejection — wrong principal
# ---------------------------------------------------------------------------


def test_carla_submission_rejected_mismatched_principal(tmp_path: Path) -> None:
    """A projection with the wrong principal is rejected by the key."""
    report = _completed_report(principal="BackEndLaw")
    # Key authorises "BackEndLaw" but projection carries "some-other-operator"
    proj = _projection_for(report, principal="some-other-operator")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.submitted is True
    assert result.status == "rejected"
    assert result.failure_stage == "rejected_by_key"
    assert result.evidence_preserved is True


def test_carla_rejection_by_key_has_authorization_reason(tmp_path: Path) -> None:
    """REJECTED_BY_KEY result exposes the authorization failure reason."""
    report = _completed_report(principal="BackEndLaw")
    proj = _projection_for(report, principal="wrong-principal")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.failure_stage == "rejected_by_key"
    assert result.authorization_reason is not None
    assert isinstance(result.failure_reason, str)
    assert len(result.failure_reason) > 0


# ---------------------------------------------------------------------------
# End-to-end submission: rejection — incomplete ticks
# ---------------------------------------------------------------------------


def test_carla_submission_rejected_incomplete_ticks(tmp_path: Path) -> None:
    """A 'completed' run with fewer ticks_completed than ticks_requested is rejected."""
    report = _completed_report(
        principal="BackEndLaw", ticks=300, ticks_completed=250, status="completed"
    )
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.submitted is True
    assert result.status == "rejected"
    assert result.failure_stage == "rejected_by_guard"
    assert result.evidence_preserved is True


# ---------------------------------------------------------------------------
# End-to-end submission: rejection — lidar health failure
# ---------------------------------------------------------------------------


def test_carla_submission_rejected_zero_lidar_frames_when_enabled(
    tmp_path: Path,
) -> None:
    """Lidar enabled but zero frames received → health guard rejects."""
    report = _completed_report(
        principal="BackEndLaw", lidar_enabled=True, lidar_frames=0
    )
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.submitted is True
    assert result.status == "rejected"
    assert result.failure_stage == "rejected_by_guard"
    assert result.evidence_preserved is True


def test_runtime_protection_partial_run_qualifies_schema_and_fails_health(
    tmp_path: Path,
) -> None:
    report = _completed_report(
        principal="BackEndLaw",
        ticks=300,
        ticks_completed=151,
        status="partial",
        lidar_frames=150,
    )
    report["lidar_summary"].update(
        {
            "frames_dropped": 1,
            "natural_drops": 0,
            "injected_drops": 1,
            "callback_errors": 0,
        }
    )
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.status == "rejected"
    assert result.evidence_preserved is True
    assert any(
        reason["guard_id"] == "carla-schema-v1" and reason["qualified"] is True
        for reason in result.guard_reasons
    )
    assert any(
        reason["guard_id"] == "carla-health-v1" and reason["qualified"] is False
        for reason in result.guard_reasons
    )


# ---------------------------------------------------------------------------
# End-to-end submission: rejection — NaN/infinite/negative telemetry
# ---------------------------------------------------------------------------


def test_carla_submission_rejected_nan_displacement(tmp_path: Path) -> None:
    """A projection with NaN displacement is rejected by the health guard."""
    report = _completed_report(principal="BackEndLaw", displacement_m=42.0)
    proj_base = build_qrtc_projection(
        report, principal="BackEndLaw", destination="carla-drive-record"
    )
    # Replace displacement_m with NaN
    bad_iface = dict(proj_base.interface_projection)
    bad_iface["displacement_m"] = math.nan
    proj = QrtcProjection(
        transit_id=proj_base.transit_id,
        principal=proj_base.principal,
        destination=proj_base.destination,
        expiration=datetime(2099, 1, 1, tzinfo=UTC),
        interface_projection=bad_iface,
        context=proj_base.context,
        config_digest=proj_base.config_digest,
        evidence_digest=proj_base.evidence_digest,
    )
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.submitted is True
    assert result.status == "rejected"
    assert result.failure_stage == "rejected_by_guard"


def test_carla_submission_rejected_negative_displacement(tmp_path: Path) -> None:
    report = _completed_report(principal="BackEndLaw", displacement_m=-5.0)
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.submitted is True
    assert result.status == "rejected"
    assert result.failure_stage == "rejected_by_guard"


# ---------------------------------------------------------------------------
# Guard reasons appear in rejection results
# ---------------------------------------------------------------------------


def test_guard_reasons_present_on_guard_rejection(tmp_path: Path) -> None:
    """Rejected-by-guard result includes guard_reasons with the failing guard."""
    report = _completed_report(
        principal="BackEndLaw", ticks=300, ticks_completed=1, status="completed"
    )
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.failure_stage == "rejected_by_guard"
    assert len(result.guard_reasons) >= 1
    failing = result.guard_reasons[-1]
    assert failing["qualified"] is False
    assert len(failing["reason"]) > 0


# ---------------------------------------------------------------------------
# as_dict includes new fields (backward-compatible)
# ---------------------------------------------------------------------------


def test_submission_result_as_dict_includes_new_fields() -> None:
    result = QrtcSubmissionResult(
        submitted=True,
        transit_id="run-1",
        status="rejected",
        failure_stage="rejected_by_key",
        failure_reason="authorization failed",
        db_path="test.sqlite3",
        evidence_preserved=True,
        authorization_reason="identity mismatch",
        guard_reasons=(
            {"guard_id": "carla-schema-v1", "qualified": False, "reason": "x"},
        ),
    )
    d = result.as_dict()
    assert d["authorization_reason"] == "identity mismatch"
    assert len(d["guard_reasons"]) == 1
    assert d["guard_reasons"][0]["guard_id"] == "carla-schema-v1"


def test_submission_result_as_dict_backward_compatible_defaults() -> None:
    """QrtcSubmissionResult without new fields uses empty defaults."""
    result = QrtcSubmissionResult(
        submitted=False,
        transit_id="run-1",
        status="rejected",
        failure_stage="policy_load",
        failure_reason="not found",
        db_path="test.sqlite3",
        evidence_preserved=False,
    )
    d = result.as_dict()
    assert d["authorization_reason"] is None
    assert d["guard_reasons"] == []


# ---------------------------------------------------------------------------
# Evidence persisted for both accepted and rejected outcomes
# ---------------------------------------------------------------------------


def test_accepted_outcome_persisted_in_evidence_db(tmp_path: Path) -> None:
    """Accepted transit is stored in the evidence database."""
    db = str(tmp_path / "evidence.sqlite3")
    report = _completed_report(principal="BackEndLaw")
    proj = _projection_for(report, principal="BackEndLaw")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=db,
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.status == "accepted"
    assert result.evidence_preserved is True
    store = EvidenceStore(db)
    record = store.load_transit(result.transit_id)
    assert record.transit_id == result.transit_id
    assert record.failure_state is None


def test_rejected_outcome_persisted_in_evidence_db(tmp_path: Path) -> None:
    """Rejected transit is also stored in the evidence database."""
    db = str(tmp_path / "evidence.sqlite3")
    report = _completed_report(principal="BackEndLaw")
    # Wrong principal triggers key rejection
    proj = _projection_for(report, principal="wrong-principal")
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=db,
        policy_path=_CARLA_POLICY_PATH,
        carla_principal="BackEndLaw",
    )
    assert result.status == "rejected"
    assert result.evidence_preserved is True
    store = EvidenceStore(db)
    record = store.load_transit(result.transit_id)
    assert record.transit_id == result.transit_id
    assert record.failure_state is not None


# ---------------------------------------------------------------------------
# Existing equipment telemetry policy still works (no regression)
# ---------------------------------------------------------------------------


def test_equipment_telemetry_policy_accepted_unchanged(tmp_path: Path) -> None:
    """The original telemetry-policy.json still accepts equipment telemetry."""
    from qrtc.carla_config import CarlaConfig
    from qrtc.carla_telemetry import build_qrtc_projection

    report = {
        "run_id": "equip-test-001",
        "run_timestamp_utc": "2026-08-01T00:00:00+00:00",
        "status": "completed",
        "client_version": "0.9.16",
        "server_version": "0.9.16",
        "map_name": "Town01",
        "blueprint": "vehicle.tesla.model3",
        "actor_id": 1,
        "actor_type_id": "vehicle.tesla.model3",
        "spawn_point_index": 0,
        "ticks_requested": 10,
        "ticks_completed": 10,
        "missing_data_count": 0,
        "principal": "authorized-operator",
        "destination": "alarm-record",
        "config": CarlaConfig().as_dict(),
        "summary": {
            "collision_count": 0,
            "displacement_m": 10.0,
            "mean_speed_mps": 3.0,
            "max_speed_mps": 5.0,
        },
        "collision_events": [],
        "samples": [],
        "lidar_summary": {
            "frames_received": 0,
            "frames_dropped": 0,
            "callback_errors": 0,
            "total_points": 0,
            "total_invalid": 0,
            "nearest_obstacle_overall": None,
            "nearest_obstacle_front": None,
            "mean_nearest_front": None,
        },
        "lidar_frame_evidence": [],
    }
    proj_base = build_qrtc_projection(
        report, principal="authorized-operator", destination="alarm-record"
    )
    iface = dict(proj_base.interface_projection)
    iface["temperature"] = 72
    iface["pressure"] = 110
    iface["alarm_state"] = False
    iface["equipment_id"] = "equip-001"
    proj = QrtcProjection(
        transit_id=proj_base.transit_id,
        principal="authorized-operator",
        destination="alarm-record",
        expiration=datetime(2099, 1, 1, tzinfo=UTC),
        interface_projection=iface,
        context=proj_base.context,
        config_digest=proj_base.config_digest,
        evidence_digest=proj_base.evidence_digest,
    )
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_TELEMETRY_POLICY_PATH,
    )
    assert result.submitted is True
    assert result.status == "accepted"


def test_equipment_telemetry_policy_guard_rejection_unchanged(tmp_path: Path) -> None:
    """Equipment telemetry policy still rejects when temperature/pressure missing."""
    from qrtc.carla_config import CarlaConfig
    from qrtc.carla_telemetry import build_qrtc_projection

    report = {
        "run_id": "equip-test-002",
        "run_timestamp_utc": "2026-08-01T00:00:00+00:00",
        "status": "completed",
        "client_version": "0.9.16",
        "server_version": "0.9.16",
        "map_name": "Town01",
        "blueprint": "vehicle.tesla.model3",
        "actor_id": 1,
        "actor_type_id": "vehicle.tesla.model3",
        "spawn_point_index": 0,
        "ticks_requested": 10,
        "ticks_completed": 10,
        "missing_data_count": 0,
        "principal": "authorized-operator",
        "destination": "alarm-record",
        "config": CarlaConfig().as_dict(),
        "summary": {
            "collision_count": 0,
            "displacement_m": 10.0,
            "mean_speed_mps": 3.0,
            "max_speed_mps": 5.0,
        },
        "collision_events": [],
        "samples": [],
        "lidar_summary": {
            "frames_received": 0,
            "frames_dropped": 0,
            "callback_errors": 0,
            "total_points": 0,
            "total_invalid": 0,
            "nearest_obstacle_overall": None,
            "nearest_obstacle_front": None,
            "mean_nearest_front": None,
        },
        "lidar_frame_evidence": [],
    }
    proj_base = build_qrtc_projection(
        report, principal="authorized-operator", destination="alarm-record"
    )
    # No temperature/pressure — guard should reject
    proj = QrtcProjection(
        transit_id=proj_base.transit_id,
        principal="authorized-operator",
        destination="alarm-record",
        expiration=datetime(2099, 1, 1, tzinfo=UTC),
        interface_projection=dict(proj_base.interface_projection),
        context=proj_base.context,
        config_digest=proj_base.config_digest,
        evidence_digest=proj_base.evidence_digest,
    )
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=_TELEMETRY_POLICY_PATH,
    )
    assert result.submitted is True
    assert result.status == "rejected"
    assert result.failure_stage == "rejected_by_guard"
