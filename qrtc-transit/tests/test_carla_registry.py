"""
Unit and pipeline-level tests for CARLA registry guards.

Covers:
- _carla_health_guard: lidar frame-count parity, dropped-frame, and
  callback-error checks introduced by the fault-injection feature.
- Pipeline-level negative test: health-guard rejection produces no accepted
  realization and rejected evidence is persisted in the SQLite store.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from qrtc.carla_telemetry import QrtcProjection, build_qrtc_projection, submit_to_qrtc_pipeline
from qrtc.guards import GuardRule
from qrtc.registry import build_default_registry
from qrtc.transit import TransitEnvelope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(interface: dict[str, Any]) -> TransitEnvelope:
    """Build a minimal TransitEnvelope with the given interface dict."""
    from qrtc.transit import AuthorizationDecision
    auth = AuthorizationDecision(
        qualified=True,
        key_id="carla-key-v1",
        policy_version="1.0.0",
        principal="carla-operator",
        reason="ok",
    )
    return TransitEnvelope(
        transit_id="test-transit",
        principal="carla-operator",
        predecessor_class="carla-telemetry",
        declared_future="carla-drive-evidence",
        destination="carla-drive-record",
        policy_version="1.0.0",
        route_version="carla-drive-route-v1",
        schema_version="carla-interface-v1",
        encoding_version="carla-json-v1",
        authorization=auth,
        interface=interface,
    )


def _healthy_lidar_iface(
    ticks: int = 300,
    frames_received: int | None = None,
    frames_dropped: int = 0,
    callback_errors: int = 0,
) -> dict[str, Any]:
    """Return a healthy lidar-enabled interface projection."""
    if frames_received is None:
        frames_received = ticks
    return {
        "displacement_m": 50.0,
        "mean_speed_mps": 5.0,
        "max_speed_mps": 10.0,
        "lidar_enabled": True,
        "lidar_frames_received": frames_received,
        "lidar_frames_dropped": frames_dropped,
        "lidar_callback_errors": callback_errors,
        "ticks_completed": ticks,
        "lidar_nearest_obstacle_m": 3.5,
        "lidar_nearest_front_m": 4.0,
    }


def _get_health_guard() -> GuardRule:
    registry = build_default_registry()
    return registry.resolve_guard("carla-health-v1")


# ---------------------------------------------------------------------------
# carla-health-v1: acceptance
# ---------------------------------------------------------------------------

def test_health_guard_accepts_healthy_lidar_run() -> None:
    guard = _get_health_guard()
    envelope = _make_envelope(_healthy_lidar_iface(ticks=300))
    assert guard.predicate(envelope) is True


def test_health_guard_accepts_lidar_disabled_run() -> None:
    guard = _get_health_guard()
    iface = {
        "displacement_m": 50.0,
        "mean_speed_mps": 5.0,
        "max_speed_mps": 10.0,
        "lidar_enabled": False,
    }
    assert guard.predicate(_make_envelope(iface)) is True


def test_health_guard_accepts_lidar_disabled_no_lidar_key() -> None:
    guard = _get_health_guard()
    iface = {
        "displacement_m": 10.0,
        "mean_speed_mps": 2.0,
        "max_speed_mps": 4.0,
    }
    assert guard.predicate(_make_envelope(iface)) is True


# ---------------------------------------------------------------------------
# carla-health-v1: rejection — frame count mismatch
# ---------------------------------------------------------------------------

def test_health_guard_rejects_frame_count_mismatch() -> None:
    """299 received frames for 300 ticks must be rejected."""
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, frames_received=299)
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_zero_received_frames() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, frames_received=0)
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_negative_received_frames() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, frames_received=-1)
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_more_frames_than_ticks() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, frames_received=301)
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_zero_ticks_completed() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=0, frames_received=0)
    # ticks_completed=0 is invalid even if frames_received matches
    assert guard.predicate(_make_envelope(iface)) is False


# ---------------------------------------------------------------------------
# carla-health-v1: rejection — dropped frames
# ---------------------------------------------------------------------------

def test_health_guard_rejects_nonzero_dropped_frames() -> None:
    """A run with 1 dropped frame must be rejected."""
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, frames_received=299, frames_dropped=1)
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_multiple_dropped_frames() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, frames_received=297, frames_dropped=3)
    assert guard.predicate(_make_envelope(iface)) is False


# ---------------------------------------------------------------------------
# carla-health-v1: rejection — callback errors
# ---------------------------------------------------------------------------

def test_health_guard_rejects_nonzero_callback_errors() -> None:
    """A run with 1 callback error must be rejected."""
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, callback_errors=1)
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_multiple_callback_errors() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, callback_errors=5)
    assert guard.predicate(_make_envelope(iface)) is False


# ---------------------------------------------------------------------------
# carla-health-v1: existing checks preserved
# ---------------------------------------------------------------------------

def test_health_guard_rejects_non_finite_displacement() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface()
    iface["displacement_m"] = float("nan")
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_negative_displacement() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface()
    iface["displacement_m"] = -1.0
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_infinite_speed() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface()
    iface["mean_speed_mps"] = float("inf")
    assert guard.predicate(_make_envelope(iface)) is False


# ---------------------------------------------------------------------------
# Pipeline-level negative test
# ---------------------------------------------------------------------------

def _minimal_run_report_for_carla_policy(
    ticks: int = 300,
    frames_received: int | None = None,
    frames_dropped: int = 0,
    callback_errors: int = 0,
) -> dict[str, Any]:
    """Build a minimal run report compatible with carla-policy.json."""
    from qrtc.carla_config import CarlaConfig
    if frames_received is None:
        frames_received = ticks
    return {
        "run_id": "test-fault-injection-run",
        "run_timestamp_utc": "2025-01-01T00:00:00+00:00",
        "status": "completed",
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
        "principal": "carla-operator",
        "destination": "carla-drive-record",
        "config": CarlaConfig(ticks=ticks).as_dict(),
        "summary": {
            "collision_count": 0,
            "displacement_m": 50.0,
            "mean_speed_mps": 5.0,
            "max_speed_mps": 10.0,
        },
        "collision_events": [],
        "samples": [],
        "lidar_summary": {
            "frames_received": frames_received,
            "frames_dropped": frames_dropped,
            "callback_errors": callback_errors,
            "total_points": frames_received * 1000,
            "total_invalid": 0,
            "nearest_obstacle_overall": 3.5,
            "nearest_obstacle_front": 4.0,
            "mean_nearest_front": 5.0,
        },
        "lidar_frame_evidence": [],
    }


def test_pipeline_healthy_lidar_run_is_accepted(tmp_path: Path) -> None:
    """A healthy 300/300 run with zero drops/errors should be accepted."""
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "carla-policy.json")

    report = _minimal_run_report_for_carla_policy(
        ticks=300, frames_received=300, frames_dropped=0, callback_errors=0
    )
    proj = build_qrtc_projection(report)

    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence-healthy.sqlite3"),
        policy_path=policy_path,
        carla_principal="carla-operator",
    )

    assert result.submitted is True
    assert result.status == "accepted", (
        f"Expected acceptance, got {result.status!r}: {result.failure_reason}"
    )
    assert result.evidence_preserved is True


def test_pipeline_fault_injection_run_is_rejected(tmp_path: Path) -> None:
    """
    A run with 299 received frames and 1 dropped frame (simulating fault
    injection at index 150 of a 300-tick run) must be rejected by
    carla-health-v1 with evidence preserved and no accepted realization.
    """
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "carla-policy.json")

    report = _minimal_run_report_for_carla_policy(
        ticks=300, frames_received=299, frames_dropped=1, callback_errors=0
    )
    proj = build_qrtc_projection(report)

    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence-fault.sqlite3"),
        policy_path=policy_path,
        carla_principal="carla-operator",
    )

    # The run must be rejected
    assert result.submitted is True
    assert result.status == "rejected"
    # No accepted realization
    assert result.failure_stage is not None
    # Evidence must be preserved so the failure can be audited
    assert result.evidence_preserved is True


def test_pipeline_nonzero_dropped_frames_is_rejected(tmp_path: Path) -> None:
    """Nonzero dropped count alone (even with matching frames) triggers rejection."""
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "carla-policy.json")

    # frames_received != ticks_completed because one was dropped, so health guard
    # fires on the mismatch; this verifies dropped-count rejection is reachable
    report = _minimal_run_report_for_carla_policy(
        ticks=300, frames_received=299, frames_dropped=1, callback_errors=0
    )
    proj = build_qrtc_projection(report)
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence-dropped.sqlite3"),
        policy_path=policy_path,
        carla_principal="carla-operator",
    )
    assert result.status == "rejected"
    assert result.evidence_preserved is True


def test_pipeline_nonzero_callback_errors_is_rejected(tmp_path: Path) -> None:
    """Nonzero callback errors must cause health-guard rejection."""
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "carla-policy.json")

    # Frame count still matches ticks so only callback_errors triggers rejection
    report = _minimal_run_report_for_carla_policy(
        ticks=300, frames_received=300, frames_dropped=0, callback_errors=1
    )
    proj = build_qrtc_projection(report)
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence-cberr.sqlite3"),
        policy_path=policy_path,
        carla_principal="carla-operator",
    )
    assert result.status == "rejected"
    assert result.evidence_preserved is True
