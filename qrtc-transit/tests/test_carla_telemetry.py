"""Unit tests for qrtc.carla_telemetry — QRTC projection and submission."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from qrtc.carla_config import CarlaConfig
from qrtc.carla_telemetry import (
    QrtcProjection,
    QrtcSubmissionResult,
    _config_digest,
    _truncate_samples,
    build_qrtc_projection,
    submit_to_qrtc_pipeline,
)
from qrtc.limits import canonical_json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_run_report(
    ticks: int = 10,
    status: str = "completed",
    collision_count: int = 0,
) -> dict[str, Any]:
    return {
        "run_id": "test-run-001",
        "run_timestamp_utc": "2025-01-01T00:00:00+00:00",
        "status": status,
        "client_version": "0.9.16",
        "server_version": "0.9.16",
        "map_name": "Town01",
        "blueprint": "vehicle.tesla.model3",
        "actor_id": 42,
        "actor_type_id": "vehicle.tesla.model3",
        "spawn_point_index": 0,
        "ticks_requested": ticks,
        "ticks_completed": ticks,
        "missing_data_count": 0,
        "principal": "test-principal",
        "destination": "test-destination",
        "config": CarlaConfig().as_dict(),
        "summary": {
            "collision_count": collision_count,
            "displacement_m": 50.0,
            "mean_speed_mps": 5.0,
            "max_speed_mps": 10.0,
        },
        "collision_events": [],
        "samples": [
            {"x": float(i), "y": 0.0, "z": 0.0, "speed_mps": float(i)}
            for i in range(ticks)
        ],
        "lidar_summary": {
            "frames_received": 5,
            "frames_dropped": 0,
            "callback_errors": 0,
            "total_points": 100,
            "total_invalid": 2,
            "nearest_obstacle_overall": 3.5,
            "nearest_obstacle_front": 4.0,
            "mean_nearest_front": 5.0,
        },
        "lidar_frame_evidence": [],
    }


# ---------------------------------------------------------------------------
# build_qrtc_projection
# ---------------------------------------------------------------------------


def test_projection_inherits_run_id() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    assert proj.transit_id == "test-run-001"


def test_projection_interface_has_required_fields() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    iface = proj.interface_projection
    for field in (
        "run_id",
        "principal",
        "destination",
        "run_timestamp_utc",
        "map_name",
        "client_version",
        "server_version",
        "blueprint",
        "spawn_point_index",
        "fixed_delta",
        "ticks_requested",
        "ticks_completed",
        "collision_count",
        "displacement_m",
        "mean_speed_mps",
        "max_speed_mps",
        "lidar_enabled",
        "lidar_frames_received",
        "lidar_frames_dropped",
        "lidar_callback_errors",
        "lidar_nearest_obstacle_m",
        "lidar_nearest_front_m",
        "missing_data_count",
        "status",
    ):
        assert field in iface, f"missing field: {field}"


def test_projection_lidar_fields_populated() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    iface = proj.interface_projection
    assert iface["lidar_frames_received"] == 5
    assert iface["lidar_frames_dropped"] == 0
    assert iface["lidar_callback_errors"] == 0
    assert iface["lidar_nearest_obstacle_m"] == pytest.approx(3.5)
    assert iface["lidar_nearest_front_m"] == pytest.approx(4.0)


def test_projection_lidar_dropped_and_errors_sourced_from_summary() -> None:
    """lidar_frames_dropped and lidar_callback_errors come from lidar_summary."""
    report = _minimal_run_report()
    report["lidar_summary"]["frames_dropped"] = 1
    report["lidar_summary"]["callback_errors"] = 2
    proj = build_qrtc_projection(report)
    iface = proj.interface_projection
    assert iface["lidar_frames_dropped"] == 1
    assert iface["lidar_callback_errors"] == 2


def test_projection_collision_count() -> None:
    report = _minimal_run_report(collision_count=3)
    proj = build_qrtc_projection(report)
    assert proj.interface_projection["collision_count"] == 3


def test_projection_samples_bounded_by_max_samples() -> None:
    report = _minimal_run_report(ticks=50)
    proj = build_qrtc_projection(report, max_samples=5)
    assert len(proj.context["samples"]) == 5


def test_projection_samples_not_truncated_below_max() -> None:
    report = _minimal_run_report(ticks=3)
    proj = build_qrtc_projection(report, max_samples=10)
    assert len(proj.context["samples"]) == 3


def test_projection_context_contains_lidar_section() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    assert "carla_lidar" in proj.context
    lidar_ctx = proj.context["carla_lidar"]
    assert "summary" in lidar_ctx
    assert "per_frame_evidence" in lidar_ctx


def test_projection_context_contains_config_snapshot() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    assert "config_snapshot" in proj.context


def test_projection_overrides_principal_and_destination() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(
        report, principal="custom-principal", destination="custom-dest"
    )
    assert proj.principal == "custom-principal"
    assert proj.destination == "custom-dest"


def test_projection_config_digest_is_hex() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    assert len(proj.config_digest) == 64
    assert all(c in "0123456789abcdef" for c in proj.config_digest)


def test_projection_evidence_digest_is_hex() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    assert len(proj.evidence_digest) == 64
    assert all(c in "0123456789abcdef" for c in proj.evidence_digest)


def test_projection_as_input_dict_structure() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    d = proj.as_input_dict()
    for key in (
        "transit_id",
        "principal",
        "destination",
        "expiration",
        "interface_projection",
        "context",
    ):
        assert key in d, f"missing key: {key}"


def test_projection_as_dict_includes_digests() -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    d = proj.as_dict()
    assert "config_digest" in d
    assert "evidence_digest" in d


# ---------------------------------------------------------------------------
# Deterministic / canonical serialization
# ---------------------------------------------------------------------------


def test_config_digest_is_deterministic() -> None:
    cfg = CarlaConfig().as_dict()
    assert _config_digest(cfg) == _config_digest(cfg)


def test_same_report_same_projection_digest() -> None:
    report = _minimal_run_report()
    p1 = build_qrtc_projection(report)
    p2 = build_qrtc_projection(report)
    assert p1.config_digest == p2.config_digest
    assert p1.evidence_digest == p2.evidence_digest


def test_different_configs_different_digest() -> None:
    cfg1 = CarlaConfig(ticks=100).as_dict()
    cfg2 = CarlaConfig(ticks=200).as_dict()
    assert _config_digest(cfg1) != _config_digest(cfg2)


def test_canonical_json_is_stable() -> None:
    obj = {"b": 2, "a": 1, "c": [3, 1, 2]}
    assert canonical_json(obj) == canonical_json(obj)
    assert canonical_json(obj).startswith('{"a"')


# ---------------------------------------------------------------------------
# _truncate_samples
# ---------------------------------------------------------------------------


def test_truncate_samples_empty() -> None:
    assert _truncate_samples([], max_count=5) == []


def test_truncate_samples_no_truncation_needed() -> None:
    samples = [{"i": i} for i in range(3)]
    assert _truncate_samples(samples, max_count=5) == samples


def test_truncate_samples_truncates() -> None:
    samples = [{"i": i} for i in range(100)]
    result = _truncate_samples(samples, max_count=10)
    assert len(result) == 10


def test_truncate_samples_preserves_first_and_last_approximately() -> None:
    samples = [{"i": i} for i in range(100)]
    result = _truncate_samples(samples, max_count=10)
    assert result[0]["i"] == 0
    # last selected index should be near the end
    assert result[-1]["i"] >= 90


# ---------------------------------------------------------------------------
# QRTC submission — rejection/failure scenarios (no real CARLA needed)
# ---------------------------------------------------------------------------


def test_submit_no_policy_path_fails_gracefully(tmp_path: Path) -> None:
    report = _minimal_run_report()
    proj = build_qrtc_projection(report)
    # Pass an invalid policy path
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "test.sqlite3"),
        policy_path=str(tmp_path / "nonexistent-policy.json"),
    )
    assert result.submitted is False
    assert result.failure_stage is not None


def test_submission_result_as_dict_complete() -> None:
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
    for key in (
        "submitted",
        "transit_id",
        "status",
        "failure_stage",
        "failure_reason",
        "db_path",
        "evidence_preserved",
    ):
        assert key in d, f"missing key: {key}"


def test_submit_with_example_policy_accepted(tmp_path: Path) -> None:
    """
    Use the bundled telemetry-policy.json to verify that a projection with
    a compatible interface_projection is accepted end-to-end.

    This test does NOT require CARLA.  It builds a projection whose
    interface_projection matches the telemetry schema guard (needs
    ``temperature`` field) by supplying a custom report interface.
    The test demonstrates QRTC submission of CARLA-originated evidence.
    """
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "telemetry-policy.json")

    # The example policy/guard requires temperature and pressure fields.
    # We add them to verify the QRTC pipeline accepts the submission.
    report = _minimal_run_report()
    # Override the projection directly to add schema-required fields
    proj_base = build_qrtc_projection(report)
    iface_with_schema = dict(proj_base.interface_projection)
    iface_with_schema["temperature"] = 72
    iface_with_schema["pressure"] = 110
    iface_with_schema["alarm_state"] = False
    iface_with_schema["equipment_id"] = "carla-ego"

    proj = QrtcProjection(
        transit_id=proj_base.transit_id,
        principal="authorized-operator",
        destination="alarm-record",
        expiration=datetime(2099, 1, 1, tzinfo=UTC),
        interface_projection=iface_with_schema,
        context=proj_base.context,
        config_digest=proj_base.config_digest,
        evidence_digest=proj_base.evidence_digest,
    )

    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=policy_path,
    )
    assert result.submitted is True
    assert result.status == "accepted"
    assert result.transit_id is not None
    assert result.db_path is not None
    assert result.evidence_preserved is True


def test_submit_guard_rejection_reports_failure(tmp_path: Path) -> None:
    """
    A projection whose interface_projection is missing required fields
    should be rejected by the guard and the result should reflect this.
    """
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "telemetry-policy.json")

    report = _minimal_run_report()
    proj_base = build_qrtc_projection(report)
    # Do NOT add temperature — guard requires it
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
        policy_path=policy_path,
    )
    assert result.submitted is True
    assert result.status == "rejected"
    assert result.failure_stage is not None
    assert result.evidence_preserved is True
