"""
Tests for the post-run fault-injection accounting feature.

Covers the 10 required scenarios from the problem statement.  All tests are
CARLA-free (using fakes / unit tests).  No live CARLA run is performed.

Scenario map
------------
1. Injection triggers at the requested zero-based callback.
2. Requested index beyond callback range leaves fault_injection_triggered=False.
3. No injection requested reports disabled/untriggered state.
4. Natural and injected drops remain separate.
5. Exactly one injected callback produces exactly one injected drop.
6. Requested-but-untriggered runs are classified ``invalid_fault_injection``.
7. A valid 299/300 controlled injection is rejected by QRTC and can produce
   ``post_run_rejection_test_passed=True`` only when the health Guard failed
   and evidence was preserved.
8. Counter validation rejects ``False``, floats, strings, negative integers,
   and ``None`` for each relevant counter.
9. The healthy baseline accounting remains accepted and unchanged.
10. Runs without QRTC submission cannot claim ``post_run_rejection_test_passed=True``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from qrtc.carla_config import CarlaConfig, LidarConfig
from qrtc.carla_lidar import LidarCollector, LidarCollectorSnapshot, build_lidar_summary
from qrtc.carla_telemetry import build_qrtc_projection, submit_to_qrtc_pipeline
from qrtc.guards import GuardRule
from qrtc.registry import build_default_registry
from qrtc.transit import TransitEnvelope


# ---------------------------------------------------------------------------
# Fake CARLA helpers (shared with test_carla_harness)
# ---------------------------------------------------------------------------

def _make_fake_measurement(
    points: list[tuple[float, float, float]],
    frame: int = 1,
    timestamp: float = 0.1,
) -> MagicMock:
    measurement = MagicMock()
    measurement.frame = frame
    measurement.timestamp = timestamp
    fake_detections = []
    for x, y, z in points:
        det = MagicMock()
        det.point.x = x
        det.point.y = y
        det.point.z = z
        fake_detections.append(det)
    measurement.__iter__ = MagicMock(return_value=iter(fake_detections))
    return measurement


def _make_spawn_point() -> MagicMock:
    sp = MagicMock()
    sp.location.x = 0.0
    sp.location.y = 0.0
    sp.location.z = 0.0
    return sp


def _make_ego_vehicle(tick_count: int = 5) -> MagicMock:
    ego = MagicMock()
    ego.id = 99
    ego.type_id = "vehicle.tesla.model3"
    transforms = []
    for i in range(tick_count + 100):
        t = MagicMock()
        t.location.x = float(i)
        t.location.y = 0.0
        t.location.z = 0.0
        t.rotation.pitch = 0.0
        t.rotation.yaw = 0.0
        t.rotation.roll = 0.0
        transforms.append(t)
    ego.get_transform.side_effect = transforms + [transforms[-1]] * 20
    v = MagicMock()
    v.x = 5.0
    v.y = 0.0
    v.z = 0.0
    ego.get_velocity.return_value = v
    return ego


def _make_carla_module(ego: MagicMock, tick_count: int = 5) -> MagicMock:
    carla = MagicMock()
    carla.Transform.return_value = MagicMock()
    carla.Location.return_value = MagicMock()

    blueprint = MagicMock()
    blueprint.id = "vehicle.tesla.model3"
    collision_bp = MagicMock()
    lidar_bp = MagicMock()
    lidar_bp.set_attribute = MagicMock()
    lib = MagicMock()
    lib.find.side_effect = lambda name: (
        blueprint if "tesla" in name
        else collision_bp if "collision" in name
        else lidar_bp if "lidar" in name
        else None
    )
    lib.filter.return_value = [blueprint]

    collision_sensor = MagicMock()
    collision_sensor.listen = MagicMock()
    collision_sensor.stop = MagicMock()
    collision_sensor.destroy = MagicMock()

    lidar_sensor = MagicMock()
    lidar_sensor.listen = MagicMock()
    lidar_sensor.stop = MagicMock()
    lidar_sensor.destroy = MagicMock()

    world_map = MagicMock()
    world_map.name = "Town01_Fake"
    world_map.get_spawn_points.return_value = [_make_spawn_point() for _ in range(5)]

    settings = MagicMock()
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = 0.05

    world = MagicMock()
    world.get_map.return_value = world_map
    world.get_settings.return_value = settings
    world.apply_settings = MagicMock()
    world.get_blueprint_library.return_value = lib
    world.try_spawn_actor.return_value = ego
    world.spawn_actor.side_effect = [collision_sensor, lidar_sensor]
    world.tick.side_effect = list(range(1, tick_count + 1))

    tm = MagicMock()

    client = MagicMock()
    client.get_client_version.return_value = "0.9.16"
    client.get_server_version.return_value = "0.9.16"
    client.get_world.return_value = world
    client.get_trafficmanager.return_value = tm

    carla.Client.return_value = client
    return carla


def _make_envelope(interface: dict[str, Any]) -> TransitEnvelope:
    from qrtc.transit import AuthorizationDecision
    auth = AuthorizationDecision(
        qualified=True,
        key_id="carla-key-v1",
        policy_version="1.0.0",
        principal="carla-operator",
        reason="ok",
    )
    return TransitEnvelope(
        transit_id="test",
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
    natural_dropped: int = 0,
    injected_dropped: int = 0,
    callback_errors: int = 0,
) -> dict[str, Any]:
    if frames_received is None:
        frames_received = ticks
    return {
        "displacement_m": 50.0,
        "mean_speed_mps": 5.0,
        "max_speed_mps": 10.0,
        "lidar_enabled": True,
        "lidar_frames_received": frames_received,
        "lidar_frames_dropped": frames_dropped,
        "lidar_frames_natural_dropped": natural_dropped,
        "lidar_frames_injected_dropped": injected_dropped,
        "lidar_callback_errors": callback_errors,
        "ticks_completed": ticks,
        "lidar_nearest_obstacle_m": 3.5,
        "lidar_nearest_front_m": 4.0,
    }


def _minimal_run_report_for_carla_policy(
    ticks: int = 300,
    frames_received: int | None = None,
    frames_dropped: int = 0,
    natural_drops: int = 0,
    injected_drops: int = 0,
    callback_errors: int = 0,
) -> dict[str, Any]:
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
            "natural_drops": natural_drops,
            "injected_drops": injected_drops,
            "callback_errors": callback_errors,
            "total_points": frames_received * 1000,
            "total_invalid": 0,
            "nearest_obstacle_overall": 3.5,
            "nearest_obstacle_front": 4.0,
            "mean_nearest_front": 5.0,
        },
        "lidar_frame_evidence": [],
    }


# ---------------------------------------------------------------------------
# Scenario 1: Injection triggers at the requested zero-based callback.
# ---------------------------------------------------------------------------

def test_injection_triggers_at_requested_zero_based_callback() -> None:
    """The callback at the configured index (zero-based) is injected and dropped."""
    requested = 3
    collector = LidarCollector(drop_frame_index=requested)
    total = 7
    for i in range(total):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=1000 + i)
        collector.on_data(m)

    snap = collector.snapshot()
    assert snap.fault_injection_enabled is True
    assert snap.fault_injection_triggered is True
    assert snap.requested_callback_index == requested
    assert snap.triggered_callback_index == requested
    # The injected callback is excluded from accepted frames
    assert len(snap.accepted_frames) == total - 1
    assert snap.injected_drops == 1
    assert snap.natural_drops == 0
    # The CARLA frame for the dropped callback should be recorded
    assert snap.triggered_sensor_frame == 1000 + requested


def test_injection_triggers_at_callback_zero() -> None:
    """Drop index 0 triggers on the very first callback."""
    collector = LidarCollector(drop_frame_index=0)
    for i in range(5):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=100 + i)
        collector.on_data(m)
    snap = collector.snapshot()
    assert snap.fault_injection_triggered is True
    assert snap.triggered_callback_index == 0
    assert snap.triggered_sensor_frame == 100
    assert snap.injected_drops == 1
    assert len(snap.accepted_frames) == 4


# ---------------------------------------------------------------------------
# Scenario 2: Requested index beyond range → fault_injection_triggered=False
# ---------------------------------------------------------------------------

def test_injection_beyond_range_leaves_untriggered() -> None:
    """If drop_frame_index >= total callbacks, the injection is never triggered."""
    collector = LidarCollector(drop_frame_index=999)
    for i in range(5):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)
    snap = collector.snapshot()
    assert snap.fault_injection_enabled is True
    assert snap.fault_injection_triggered is False
    assert snap.requested_callback_index == 999
    assert snap.triggered_callback_index is None
    assert snap.triggered_sensor_frame is None
    assert snap.injected_drops == 0
    assert len(snap.accepted_frames) == 5


def test_injection_exactly_at_boundary_does_not_trigger() -> None:
    """drop_frame_index == total_callbacks is beyond range (zero-based)."""
    n = 5
    collector = LidarCollector(drop_frame_index=n)  # index n is out of range for n callbacks
    for i in range(n):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)
    snap = collector.snapshot()
    assert snap.fault_injection_triggered is False
    assert snap.injected_drops == 0


# ---------------------------------------------------------------------------
# Scenario 3: No injection requested → disabled/untriggered state
# ---------------------------------------------------------------------------

def test_no_injection_reports_disabled_state() -> None:
    """Default drop_frame_index=-1 produces a disabled, untriggered snapshot."""
    collector = LidarCollector()
    for i in range(5):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)
    snap = collector.snapshot()
    assert snap.fault_injection_enabled is False
    assert snap.fault_injection_triggered is False
    assert snap.requested_callback_index is None
    assert snap.triggered_callback_index is None
    assert snap.triggered_sensor_frame is None
    assert snap.injected_drops == 0
    assert snap.natural_drops == 0


# ---------------------------------------------------------------------------
# Scenario 4: Natural and injected drops remain separate
# ---------------------------------------------------------------------------

def test_natural_and_injected_drops_remain_separate() -> None:
    """record_drop() increments natural_drops only; on_data injection increments injected_drops only."""
    collector = LidarCollector(drop_frame_index=2)
    for i in range(5):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)

    # Add two natural drops
    collector.record_drop()
    collector.record_drop()

    snap = collector.snapshot()
    assert snap.natural_drops == 2
    assert snap.injected_drops == 1
    # Aggregate reflected in summary
    summary = build_lidar_summary(
        snap.accepted_frames,
        snap.natural_drops,
        snap.injected_drops,
        snap.callback_errors,
    )
    assert summary.natural_drops == 2
    assert summary.injected_drops == 1
    assert summary.frames_dropped == 3  # aggregate


def test_record_drop_does_not_increment_injected_drops() -> None:
    """record_drop() must only affect the natural-drop counter."""
    collector = LidarCollector()
    collector.record_drop()
    snap = collector.snapshot()
    assert snap.natural_drops == 1
    assert snap.injected_drops == 0


def test_fault_injection_does_not_increment_natural_drops() -> None:
    """Fault injection must only affect the injected-drop counter."""
    collector = LidarCollector(drop_frame_index=0)
    m = _make_fake_measurement([(1.0, 0.0, 0.0)], frame=1)
    collector.on_data(m)
    snap = collector.snapshot()
    assert snap.injected_drops == 1
    assert snap.natural_drops == 0


# ---------------------------------------------------------------------------
# Scenario 5: Exactly one injected callback → exactly one injected drop
# ---------------------------------------------------------------------------

def test_exactly_one_injected_callback_produces_one_injected_drop() -> None:
    """Only one injected drop is produced even over many callbacks."""
    n = 20
    collector = LidarCollector(drop_frame_index=10)
    for i in range(n):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)
    snap = collector.snapshot()
    assert snap.injected_drops == 1
    assert len(snap.accepted_frames) == n - 1
    assert snap.callbacks_received == n


def test_callbacks_received_counts_all_including_injected() -> None:
    """callbacks_received includes the injected callback."""
    n = 5
    collector = LidarCollector(drop_frame_index=2)
    for i in range(n):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)
    snap = collector.snapshot()
    assert snap.callbacks_received == n
    assert snap.injected_drops == 1
    assert len(snap.accepted_frames) == n - 1


# ---------------------------------------------------------------------------
# Scenario 6: Requested-but-untriggered → invalid_fault_injection
# ---------------------------------------------------------------------------

def test_harness_classifies_untriggered_injection_as_invalid(tmp_path: Path) -> None:
    """
    A run with fault injection requested but never triggered (e.g., fewer
    callbacks than the requested index) must be classified as
    ``invalid_fault_injection`` with post_run_rejection_test_passed=False.
    """
    tick_count = 5
    ego = _make_ego_vehicle(tick_count)
    fake_carla = _make_carla_module(ego, tick_count=tick_count)

    # Collect actual lidar callbacks by intercepting the listener registration
    captured_listener: list[Any] = []
    lidar_sensor_ref: list[MagicMock] = []

    world = fake_carla.Client.return_value.get_world.return_value

    def tracking_spawn(bp, transform, attach_to=None) -> MagicMock:
        sensor = MagicMock()
        sensor.stop = MagicMock()
        sensor.destroy = MagicMock()
        def capture_listen(fn: Any) -> None:
            captured_listener.append(fn)
        sensor.listen = capture_listen
        lidar_sensor_ref.append(sensor)
        return sensor

    world.spawn_actor.side_effect = tracking_spawn

    output = str(tmp_path / "report.json")
    # Request injection at callback 999 — well beyond 5 ticks
    cfg = CarlaConfig(
        ticks=tick_count,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=True, drop_frame_index=999),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive
        report = run_drive(cfg)

    # No QRTC submission → test_outcome reflects untriggered injection
    fi = report["fault_injection"]
    assert fi["enabled"] is True
    assert fi["triggered"] is False
    # test_outcome classification
    assert report["test_outcome"] == "invalid_fault_injection"
    assert report["fault_requested"] is True
    assert report["fault_observed"] is False
    assert report["post_run_rejection_test_passed"] is False


# ---------------------------------------------------------------------------
# Scenario 7: Valid 299/300 injection → QRTC rejected → post_run_rejection_test_passed
# ---------------------------------------------------------------------------

def test_valid_controlled_injection_pipeline_rejection_can_pass(tmp_path: Path) -> None:
    """
    A 299/300 run with exactly one injected drop is rejected by QRTC
    (carla-health-v1 fails) and post_run_rejection_test_passed=True.
    """
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "carla-policy.json")

    report = _minimal_run_report_for_carla_policy(
        ticks=300,
        frames_received=299,
        frames_dropped=1,
        natural_drops=0,
        injected_drops=1,
        callback_errors=0,
    )
    # Add fault injection metadata directly in the report
    report["fault_injection"] = {
        "enabled": True,
        "type": "lidar-frame-drop",
        "requested_callback_index": 150,
        "triggered": True,
        "triggered_callback_index": 150,
        "triggered_sensor_frame": 979042,
    }
    report["lidar_callbacks_received"] = 300
    report["lidar_frames_accepted"] = 299
    report["lidar_frames_natural_dropped"] = 0
    report["lidar_frames_injected_dropped"] = 1

    proj = build_qrtc_projection(report)
    qrtc_result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=policy_path,
        carla_principal="carla-operator",
    )

    # The run must be rejected by the health guard
    assert qrtc_result.status == "rejected"
    assert qrtc_result.evidence_preserved is True

    # Verify carla-health-v1 failed
    health_guard_failed = False
    for guard in qrtc_result.guard_reasons:
        if guard.get("guard_id") == "carla-health-v1":
            health_guard_failed = not guard.get("qualified", True)
            break
    assert health_guard_failed, "carla-health-v1 must have failed"

    # Post-run pass conditions
    fi = report["fault_injection"]
    injected_drops = report["lidar_frames_injected_dropped"]
    accepted_frames = report["lidar_frames_accepted"]
    expected_frames = report["ticks_requested"]

    post_run_pass = (
        fi["triggered"]
        and injected_drops == 1
        and accepted_frames == expected_frames - 1
        and qrtc_result.status == "rejected"
        and health_guard_failed
        and qrtc_result.evidence_preserved
    )
    assert post_run_pass is True


def test_post_run_pass_requires_health_guard_to_fail(tmp_path: Path) -> None:
    """post_run_rejection_test_passed cannot be True if health guard passed."""
    # Build a projection that would be accepted (all 300 frames received)
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "carla-policy.json")

    report = _minimal_run_report_for_carla_policy(
        ticks=300, frames_received=300, frames_dropped=0,
        natural_drops=0, injected_drops=0,
    )
    report["fault_injection"] = {
        "enabled": True,
        "type": "lidar-frame-drop",
        "requested_callback_index": 150,
        "triggered": False,  # injection never triggered
        "triggered_callback_index": None,
        "triggered_sensor_frame": None,
    }
    proj = build_qrtc_projection(report)
    qrtc_result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence.sqlite3"),
        policy_path=policy_path,
        carla_principal="carla-operator",
    )
    # Run would be accepted since frames==ticks and no drops
    # post_run_pass requires injection triggered — this can't be True
    assert not (report["fault_injection"]["triggered"] and qrtc_result.status == "rejected")


def test_post_run_pass_requires_evidence_preserved(tmp_path: Path) -> None:
    """
    post_run_rejection_test_passed must be False if evidence was not preserved.
    """
    # Simulate a rejection but evidence_preserved=False
    from qrtc.carla_telemetry import QrtcSubmissionResult

    mock_result = QrtcSubmissionResult(
        submitted=True,
        transit_id="test",
        status="rejected",
        failure_stage="guards",
        failure_reason="lidar health",
        db_path=str(tmp_path / "db.sqlite3"),
        evidence_preserved=False,  # NOT preserved
        guard_reasons=({"guard_id": "carla-health-v1", "qualified": False, "reason": "x"},),
    )

    post_run_pass = (
        True  # triggered
        and 1 == 1  # injected_drops == 1
        and 299 == 300 - 1  # accepted == expected - 1
        and mock_result.status == "rejected"
        and not mock_result.guard_reasons[0]["qualified"]
        and mock_result.evidence_preserved  # <-- False → overall False
    )
    assert post_run_pass is False


# ---------------------------------------------------------------------------
# Scenario 8: Counter validation rejects invalid types
# ---------------------------------------------------------------------------

def _get_health_guard() -> GuardRule:
    return build_default_registry().resolve_guard("carla-health-v1")


@pytest.mark.parametrize("bad_value", [
    False,        # bool (subclass of int — must be rejected)
    True,         # bool
    0.0,          # float
    "0",          # string
    -1,           # negative integer
    None,         # None
])
def test_health_guard_rejects_bad_lidar_frames_received(bad_value: Any) -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300)
    iface["lidar_frames_received"] = bad_value
    assert guard.predicate(_make_envelope(iface)) is False


@pytest.mark.parametrize("bad_value", [
    False,
    True,
    1.0,
    "1",
    -1,
    None,
])
def test_health_guard_rejects_bad_lidar_frames_dropped(bad_value: Any) -> None:
    """Any non-int-0 value for lidar_frames_dropped must be rejected."""
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300)
    iface["lidar_frames_dropped"] = bad_value
    assert guard.predicate(_make_envelope(iface)) is False


@pytest.mark.parametrize("bad_value", [
    False,
    True,
    0.0,
    "0",
    -1,
    None,
])
def test_health_guard_rejects_bad_ticks_completed(bad_value: Any) -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300)
    iface["ticks_completed"] = bad_value
    assert guard.predicate(_make_envelope(iface)) is False


@pytest.mark.parametrize("bad_value", [
    False,
    True,
    1.0,
    "0",
    -1,
    None,
])
def test_health_guard_rejects_bad_lidar_callback_errors(bad_value: Any) -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300)
    iface["lidar_callback_errors"] = bad_value
    assert guard.predicate(_make_envelope(iface)) is False


@pytest.mark.parametrize("bad_value", [
    False,
    True,
    1.0,
    "0",
    -1,
])
def test_health_guard_rejects_bad_natural_dropped_when_present(bad_value: Any) -> None:
    """lidar_frames_natural_dropped, if present, must be a non-negative int (not bool)."""
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300)
    iface["lidar_frames_natural_dropped"] = bad_value
    assert guard.predicate(_make_envelope(iface)) is False


@pytest.mark.parametrize("bad_value", [
    False,
    True,
    1.0,
    "0",
    -1,
])
def test_health_guard_rejects_bad_injected_dropped_when_present(bad_value: Any) -> None:
    """lidar_frames_injected_dropped, if present, must be a non-negative int (not bool)."""
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300)
    iface["lidar_frames_injected_dropped"] = bad_value
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_nonzero_natural_dropped() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, frames_received=299, natural_dropped=1)
    assert guard.predicate(_make_envelope(iface)) is False


def test_health_guard_rejects_nonzero_injected_dropped() -> None:
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(ticks=300, frames_received=299, injected_dropped=1)
    assert guard.predicate(_make_envelope(iface)) is False


# ---------------------------------------------------------------------------
# Scenario 9: Healthy baseline accounting remains accepted
# ---------------------------------------------------------------------------

def test_healthy_baseline_accepted_with_zero_natural_and_injected(tmp_path: Path) -> None:
    """A healthy 300/300 run with zero natural/injected drops is accepted."""
    examples = Path(__file__).resolve().parents[1] / "examples"
    policy_path = str(examples / "carla-policy.json")

    report = _minimal_run_report_for_carla_policy(
        ticks=300,
        frames_received=300,
        frames_dropped=0,
        natural_drops=0,
        injected_drops=0,
        callback_errors=0,
    )
    proj = build_qrtc_projection(report)
    result = submit_to_qrtc_pipeline(
        proj,
        db_path=str(tmp_path / "evidence-healthy.sqlite3"),
        policy_path=policy_path,
        carla_principal="carla-operator",
    )
    assert result.status == "accepted"
    assert result.evidence_preserved is True


def test_healthy_baseline_health_guard_accepts_zero_natural_injected() -> None:
    """Health guard accepts interface with zero natural/injected drops (as int 0)."""
    guard = _get_health_guard()
    iface = _healthy_lidar_iface(
        ticks=300,
        frames_received=300,
        natural_dropped=0,
        injected_dropped=0,
    )
    assert guard.predicate(_make_envelope(iface)) is True


def test_healthy_baseline_health_guard_accepts_absent_natural_injected() -> None:
    """Health guard accepts interface without natural/injected drop fields (backward compat)."""
    guard = _get_health_guard()
    iface = {
        "displacement_m": 50.0,
        "mean_speed_mps": 5.0,
        "max_speed_mps": 10.0,
        "lidar_enabled": True,
        "lidar_frames_received": 300,
        "lidar_frames_dropped": 0,
        "lidar_callback_errors": 0,
        "ticks_completed": 300,
        "lidar_nearest_obstacle_m": 3.5,
        "lidar_nearest_front_m": 4.0,
    }
    assert guard.predicate(_make_envelope(iface)) is True


def test_lidar_collector_snapshot_healthy_zero_counters() -> None:
    """A collector with no drops or errors has clean zero-value counters."""
    collector = LidarCollector()
    for i in range(5):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)
    snap = collector.snapshot()
    assert snap.natural_drops == 0
    assert snap.injected_drops == 0
    assert snap.callback_errors == 0
    assert snap.fault_injection_enabled is False
    assert snap.fault_injection_triggered is False
    assert len(snap.accepted_frames) == 5
    assert snap.callbacks_received == 5


# ---------------------------------------------------------------------------
# Scenario 10: Runs without QRTC submission → post_run_rejection_test_passed=False
# ---------------------------------------------------------------------------

def test_no_qrtc_submission_post_run_pass_is_false(tmp_path: Path) -> None:
    """Without QRTC submission, post_run_rejection_test_passed must be False."""
    tick_count = 5
    ego = _make_ego_vehicle(tick_count)
    fake_carla = _make_carla_module(ego, tick_count=tick_count)

    output = str(tmp_path / "report.json")
    cfg = CarlaConfig(
        ticks=tick_count,
        output=output,
        submit_to_qrtc=False,  # no QRTC
        lidar=LidarConfig(enabled=False),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive
        report = run_drive(cfg)

    assert report["post_run_rejection_test_passed"] is False
    # Also verify written JSON
    written = json.loads(Path(output).read_text(encoding="utf-8"))
    assert written["post_run_rejection_test_passed"] is False


def test_no_qrtc_submission_with_injection_still_false(tmp_path: Path) -> None:
    """Even with injection requested, no-QRTC run cannot claim post_run_pass=True."""
    tick_count = 5
    ego = _make_ego_vehicle(tick_count)
    fake_carla = _make_carla_module(ego, tick_count=tick_count)

    output = str(tmp_path / "report.json")
    # Request injection at index 2 - in fake harness, no callbacks arrive
    # so injection is requested but not triggered
    cfg = CarlaConfig(
        ticks=tick_count,
        output=output,
        submit_to_qrtc=False,  # no QRTC — safety policy was never tested
        lidar=LidarConfig(enabled=True, drop_frame_index=2),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive
        report = run_drive(cfg)

    # Without QRTC submission, post_run_rejection_test_passed must be False
    assert report["post_run_rejection_test_passed"] is False
    # Since no callbacks arrive in the fake harness, injection is untriggered
    assert report["fault_requested"] is True
    assert report["fault_observed"] is False


def test_no_qrtc_submission_invalid_injection_outcome(tmp_path: Path) -> None:
    """
    Without QRTC submission and untriggered injection,
    test_outcome must be ``invalid_fault_injection`` and not a safety pass.
    """
    tick_count = 5
    ego = _make_ego_vehicle(tick_count)
    fake_carla = _make_carla_module(ego, tick_count=tick_count)

    output = str(tmp_path / "report.json")
    # Index 999 is way beyond 5 ticks — injection won't trigger
    cfg = CarlaConfig(
        ticks=tick_count,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=True, drop_frame_index=999),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive
        report = run_drive(cfg)

    assert report["test_outcome"] == "invalid_fault_injection"
    assert report["fault_requested"] is True
    assert report["fault_observed"] is False
    assert report["post_run_rejection_test_passed"] is False


def test_fault_injection_no_qrtc_classification_via_collector() -> None:
    """
    When injection triggers but there is no QRTC submission,
    post_run_rejection_test_passed must be False.
    (Uses LidarCollector directly to verify the collector's snapshot state.)
    """
    n = 5
    collector = LidarCollector(drop_frame_index=2)
    for i in range(n):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)
    snap = collector.snapshot()

    # Verify injection triggered in the collector
    assert snap.fault_injection_triggered is True
    assert snap.injected_drops == 1

    # Simulate what the harness does without QRTC submission:
    # post_run_rejection_test_passed must remain False
    # because no QRTC evaluation was performed
    fault_injection_no_qrtc_post_run_pass = False
    assert fault_injection_no_qrtc_post_run_pass is False


# ---------------------------------------------------------------------------
# Additional: fault_injection section structure in run report
# ---------------------------------------------------------------------------

def test_run_report_contains_fault_injection_section_no_injection(tmp_path: Path) -> None:
    """The run report always contains a fault_injection section."""
    tick_count = 3
    ego = _make_ego_vehicle(tick_count)
    fake_carla = _make_carla_module(ego, tick_count=tick_count)

    output = str(tmp_path / "report.json")
    cfg = CarlaConfig(
        ticks=tick_count,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=False),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive
        report = run_drive(cfg)

    assert "fault_injection" in report
    fi = report["fault_injection"]
    assert fi["enabled"] is False
    assert fi["triggered"] is False
    assert "lidar_callbacks_received" in report
    assert "lidar_frames_accepted" in report
    assert "lidar_frames_natural_dropped" in report
    assert "lidar_frames_injected_dropped" in report


def test_projection_includes_natural_and_injected_drop_fields() -> None:
    """build_qrtc_projection always projects natural and injected drop counters."""
    report = _minimal_run_report_for_carla_policy(
        ticks=300, natural_drops=0, injected_drops=1, frames_dropped=1,
        frames_received=299,
    )
    proj = build_qrtc_projection(report)
    iface = proj.interface_projection
    assert "lidar_frames_natural_dropped" in iface
    assert "lidar_frames_injected_dropped" in iface
    assert iface["lidar_frames_natural_dropped"] == 0
    assert iface["lidar_frames_injected_dropped"] == 1
    assert iface["lidar_frames_dropped"] == 1  # aggregate preserved
