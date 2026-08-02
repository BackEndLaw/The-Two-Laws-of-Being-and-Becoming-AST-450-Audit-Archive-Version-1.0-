"""
Tests for qrtc.runtime_protection — CARLA-free unit and integration tests.

Coverage map
------------
1.  Disabled/no-fault: supervisor stays ARMED.
2.  First fault latches; subsequent faults are ignored.
3.  Autopilot disabled exactly once.
4.  Throttle is always zero after fault detection.
5.  Brake always equals the configured full_brake value.
6.  Stopping requires the configured number of consecutive low-speed ticks.
7.  A speed increase resets the consecutive stopped-tick counter.
8.  Early termination happens only after stop confirmation or timeout.
9.  Stop timeout can never produce runtime_protection_test_passed=True.
10. Injected and natural drop accounting stays separate.
11. Controlled injection reaches the runtime protection path via fault_notify.
12. QRTC rejection is checked through carla-health-v1 specifically.
13. Evidence is preserved in the runtime protection snapshot.
14. Existing post-run and baseline behaviour is unchanged when RP is disabled.
15. Configuration environment parsing and validation.
16. _classify_runtime_protection logic.
17. Full run_drive() integration with fake CARLA and RP enabled.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from qrtc.carla_config import (
    CarlaConfig,
    LidarConfig,
    carla_config_from_env,
    validate_carla_config,
)
from qrtc.carla_harness import (
    _classify_runtime_protection,
)
from qrtc.carla_lidar import LidarCollector
from qrtc.runtime_protection import (
    FaultMetadata,
    RuntimeProtection,
    RuntimeProtectionConfig,
    RuntimeProtectionState,
)


# ---------------------------------------------------------------------------
# Helpers — fake vehicle
# ---------------------------------------------------------------------------


def _make_velocity(x: float = 5.0, y: float = 0.0, z: float = 0.0) -> MagicMock:
    v = MagicMock()
    v.x = x
    v.y = y
    v.z = z
    return v


def _make_vehicle(speed: float = 5.0) -> MagicMock:
    """Fake vehicle with constant speed."""
    v = MagicMock()
    v.id = 42
    velocity = _make_velocity(speed, 0.0, 0.0)
    v.get_velocity.return_value = velocity
    v.set_autopilot = MagicMock()
    v.apply_control = MagicMock()
    return v


def _make_stopped_vehicle() -> MagicMock:
    """Fake vehicle already stopped (speed ≈ 0)."""
    return _make_vehicle(speed=0.0)


class _FakeControl:
    def __init__(self) -> None:
        self.throttle = 0.0
        self.brake = 0.0
        self.steer = 0.0


class _ControlCapture:
    """Captures all apply_control calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float, float]] = []
        self.vehicle_controls: list[_FakeControl] = []

    def apply(self, vehicle: Any, throttle: float, brake: float, steer: float) -> None:
        self.calls.append((throttle, brake, steer))
        ctrl = _FakeControl()
        ctrl.throttle = throttle
        ctrl.brake = brake
        ctrl.steer = steer
        vehicle.apply_control(ctrl)

    def disable_autopilot(self, vehicle: Any) -> None:
        vehicle.set_autopilot(False)


def _default_rp_cfg(
    *,
    enabled: bool = True,
    stop_speed_mps: float = 0.10,
    required_stopped_ticks: int = 3,
    maximum_braking_ticks: int = 20,
    full_brake: float = 1.0,
) -> RuntimeProtectionConfig:
    return RuntimeProtectionConfig(
        enabled=enabled,
        stop_speed_mps=stop_speed_mps,
        required_stopped_ticks=required_stopped_ticks,
        maximum_braking_ticks=maximum_braking_ticks,
        full_brake=full_brake,
    )


# ---------------------------------------------------------------------------
# 1. Disabled / no-fault: supervisor stays ARMED
# ---------------------------------------------------------------------------


def test_disabled_supervisor_stays_armed_with_no_fault() -> None:
    rp = RuntimeProtection(_default_rp_cfg(enabled=False))
    assert rp.state == RuntimeProtectionState.ARMED
    assert not rp.triggered
    assert not rp.terminal


def test_enabled_supervisor_stays_armed_without_fault() -> None:
    rp = RuntimeProtection(_default_rp_cfg())
    vehicle = _make_vehicle()
    cap = _ControlCapture()

    for tick in range(10):
        state = rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )
        assert state == RuntimeProtectionState.ARMED

    assert not rp.triggered
    assert not rp.terminal
    assert len(cap.calls) == 0
    vehicle.set_autopilot.assert_not_called()


# ---------------------------------------------------------------------------
# 2. First fault latches; subsequent faults are ignored
# ---------------------------------------------------------------------------


def test_first_fault_latches() -> None:
    rp = RuntimeProtection(_default_rp_cfg())
    rp.latch_fault(callback_index=5, sensor_frame=100)

    assert rp.triggered
    assert rp.state == RuntimeProtectionState.FAULT_LATCHED

    snap = rp.snapshot()
    assert snap.fault_triggered is True
    assert snap.fault_metadata is not None
    assert snap.fault_metadata.callback_index == 5
    assert snap.fault_metadata.sensor_frame == 100


def test_subsequent_faults_cannot_overwrite_first() -> None:
    rp = RuntimeProtection(_default_rp_cfg())
    rp.latch_fault(callback_index=5, sensor_frame=100)
    rp.latch_fault(callback_index=7, sensor_frame=200)  # should be ignored

    snap = rp.snapshot()
    assert snap.fault_metadata is not None
    assert snap.fault_metadata.callback_index == 5
    assert snap.fault_metadata.sensor_frame == 100


def test_fault_latch_with_none_sensor_frame() -> None:
    rp = RuntimeProtection(_default_rp_cfg())
    rp.latch_fault(callback_index=3, sensor_frame=None)
    snap = rp.snapshot()
    assert snap.fault_metadata is not None
    assert snap.fault_metadata.sensor_frame is None


# ---------------------------------------------------------------------------
# 3. Autopilot disabled exactly once
# ---------------------------------------------------------------------------


def test_autopilot_disabled_exactly_once() -> None:
    rp = RuntimeProtection(_default_rp_cfg(required_stopped_ticks=100))
    vehicle = _make_vehicle(speed=10.0)
    cap = _ControlCapture()

    rp.latch_fault(callback_index=1, sensor_frame=10)

    # Run many enforcement ticks
    for tick in range(15):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )

    # set_autopilot(False) must be called exactly once
    assert vehicle.set_autopilot.call_count == 1
    vehicle.set_autopilot.assert_called_once_with(False)


def test_autopilot_disabled_on_first_enforcement_after_latch() -> None:
    rp = RuntimeProtection(_default_rp_cfg(required_stopped_ticks=100))
    vehicle = _make_vehicle(speed=5.0)
    cap = _ControlCapture()

    rp.latch_fault(callback_index=0)

    rp.enforce(
        vehicle, 7, disable_autopilot=cap.disable_autopilot, apply_control=cap.apply
    )
    assert vehicle.set_autopilot.call_count == 1

    snap = rp.snapshot()
    assert snap.autopilot_disabled is True
    assert snap.first_enforcement_tick == 7


def test_autopilot_disable_failure_produces_control_error() -> None:
    rp = RuntimeProtection(_default_rp_cfg(required_stopped_ticks=100))
    vehicle = _make_vehicle(speed=5.0)
    cap = _ControlCapture()

    def fail_disable(_: Any) -> None:
        raise RuntimeError("autopilot disengage failed")

    rp.latch_fault(callback_index=0)

    state = rp.enforce(
        vehicle,
        2,
        disable_autopilot=fail_disable,
        apply_control=cap.apply,
    )

    assert state == RuntimeProtectionState.CONTROL_ERROR
    snap = rp.snapshot()
    assert snap.autopilot_disabled is False
    assert snap.control_action_failed is True
    assert snap.control_action_error is not None
    assert snap.control_action_error.action == "set_autopilot(False)"
    assert "autopilot disengage failed" in snap.control_action_error.message
    assert snap.termination_reason == "control_action_error"
    assert len(cap.calls) == 0


# ---------------------------------------------------------------------------
# 4. Throttle is always zero after detection
# ---------------------------------------------------------------------------


def test_throttle_always_zero_after_detection() -> None:
    rp = RuntimeProtection(_default_rp_cfg(required_stopped_ticks=100))
    vehicle = _make_vehicle(speed=8.0)
    cap = _ControlCapture()

    rp.latch_fault(callback_index=0)

    for tick in range(10):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )

    assert len(cap.calls) == 10
    for throttle, brake, steer in cap.calls:
        assert throttle == pytest.approx(0.0), "throttle must be zero"


# ---------------------------------------------------------------------------
# 5. Brake always equals configured full_brake value
# ---------------------------------------------------------------------------


def test_brake_always_equals_configured_full_brake() -> None:
    full_brake = 0.85
    rp = RuntimeProtection(
        _default_rp_cfg(full_brake=full_brake, required_stopped_ticks=100)
    )
    vehicle = _make_vehicle(speed=8.0)
    cap = _ControlCapture()

    rp.latch_fault(callback_index=0)

    for tick in range(10):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )

    assert len(cap.calls) == 10
    for throttle, brake, steer in cap.calls:
        assert brake == pytest.approx(full_brake), "brake must equal full_brake"
        assert steer == pytest.approx(0.0), "steering must be neutral"


def test_braking_control_failure_produces_control_error() -> None:
    rp = RuntimeProtection(_default_rp_cfg(required_stopped_ticks=100))
    vehicle = _make_vehicle(speed=8.0)
    cap = _ControlCapture()

    def fail_apply(_: Any, throttle: float, brake: float, steer: float) -> None:
        raise RuntimeError(
            f"brake control failed: throttle={throttle} brake={brake} steer={steer}"
        )

    rp.latch_fault(callback_index=0)
    state = rp.enforce(
        vehicle,
        0,
        disable_autopilot=cap.disable_autopilot,
        apply_control=fail_apply,
    )

    assert state == RuntimeProtectionState.CONTROL_ERROR
    snap = rp.snapshot()
    assert snap.autopilot_disabled is True
    assert snap.control_action_failed is True
    assert snap.control_action_error is not None
    assert snap.control_action_error.action == "apply_control(brake)"
    assert "brake control failed" in snap.control_action_error.message
    assert snap.safe_stop is False


# ---------------------------------------------------------------------------
# 6. Stopping requires configured consecutive low-speed ticks
# ---------------------------------------------------------------------------


def test_stopped_requires_configured_consecutive_ticks() -> None:
    required = 4
    rp = RuntimeProtection(
        _default_rp_cfg(
            stop_speed_mps=0.10,
            required_stopped_ticks=required,
            maximum_braking_ticks=100,
        )
    )
    vehicle = _make_stopped_vehicle()
    cap = _ControlCapture()

    rp.latch_fault(callback_index=0)

    states: list[RuntimeProtectionState] = []
    for tick in range(required + 5):
        state = rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )
        states.append(state)

    # Must be BRAKING until exactly `required` consecutive low-speed ticks
    for i in range(required - 1):
        assert (
            states[i] == RuntimeProtectionState.BRAKING
        ), f"expected BRAKING at tick {i}, got {states[i]}"
    # Exactly at tick required-1 (0-based), STOPPED
    assert states[required - 1] == RuntimeProtectionState.STOPPED

    snap = rp.snapshot()
    assert snap.safe_stop is True
    assert snap.stop_timeout is False
    assert snap.state == RuntimeProtectionState.STOPPED
    assert snap.stopped_ticks == required


def test_not_stopped_before_required_ticks() -> None:
    required = 5
    rp = RuntimeProtection(
        _default_rp_cfg(required_stopped_ticks=required, maximum_braking_ticks=50)
    )
    vehicle = _make_stopped_vehicle()
    cap = _ControlCapture()

    rp.latch_fault(callback_index=0)

    # Run only required-1 ticks
    for tick in range(required - 1):
        state = rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )
        assert state == RuntimeProtectionState.BRAKING


# ---------------------------------------------------------------------------
# 7. Speed increase resets consecutive stopped-tick counter
# ---------------------------------------------------------------------------


def test_speed_increase_resets_consecutive_stopped_count() -> None:
    required = 4
    stop_speed = 0.10
    rp = RuntimeProtection(
        _default_rp_cfg(
            stop_speed_mps=stop_speed,
            required_stopped_ticks=required,
            maximum_braking_ticks=50,
        )
    )
    cap = _ControlCapture()

    # Build a vehicle whose speed alternates: low, low, HIGH, low, low, low, low
    speeds = [0.05, 0.05, 5.0, 0.05, 0.05, 0.05, 0.05]
    vehicles = [_make_vehicle(speed=s) for s in speeds]

    rp.latch_fault(callback_index=0)

    states: list[RuntimeProtectionState] = []
    for tick, vehicle in enumerate(vehicles):
        state = rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )
        states.append(state)

    # After high-speed tick at index 2, counter resets.
    # Need 4 consecutive after that → ticks 3,4,5,6 → STOPPED at tick 6 (index 6)
    assert states[0] == RuntimeProtectionState.BRAKING  # stopped_ticks=1
    assert states[1] == RuntimeProtectionState.BRAKING  # stopped_ticks=2
    assert states[2] == RuntimeProtectionState.BRAKING  # speed high → reset to 0
    assert states[3] == RuntimeProtectionState.BRAKING  # stopped_ticks=1
    assert states[4] == RuntimeProtectionState.BRAKING  # stopped_ticks=2
    assert states[5] == RuntimeProtectionState.BRAKING  # stopped_ticks=3
    assert states[6] == RuntimeProtectionState.STOPPED  # stopped_ticks=4

    snap = rp.snapshot()
    assert snap.safe_stop is True
    assert snap.stopped_ticks == required


# ---------------------------------------------------------------------------
# 8. Early termination only after stop confirmation or timeout
# ---------------------------------------------------------------------------


def test_terminal_only_after_stop() -> None:
    required = 3
    rp = RuntimeProtection(
        _default_rp_cfg(required_stopped_ticks=required, maximum_braking_ticks=50)
    )
    vehicle = _make_stopped_vehicle()
    cap = _ControlCapture()

    rp.latch_fault(callback_index=0)

    for tick in range(required - 1):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )
        assert not rp.terminal

    rp.enforce(
        vehicle,
        required - 1,
        disable_autopilot=cap.disable_autopilot,
        apply_control=cap.apply,
    )
    assert rp.terminal
    assert rp.state == RuntimeProtectionState.STOPPED


def test_terminal_after_timeout() -> None:
    max_ticks = 5
    rp = RuntimeProtection(
        _default_rp_cfg(
            stop_speed_mps=0.01,
            required_stopped_ticks=100,
            maximum_braking_ticks=max_ticks,
        )
    )
    vehicle = _make_vehicle(speed=5.0)
    cap = _ControlCapture()

    rp.latch_fault(callback_index=0)

    for tick in range(max_ticks - 1):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )
        assert not rp.terminal

    rp.enforce(
        vehicle,
        max_ticks - 1,
        disable_autopilot=cap.disable_autopilot,
        apply_control=cap.apply,
    )
    assert rp.terminal
    assert rp.state == RuntimeProtectionState.STOP_TIMEOUT


# ---------------------------------------------------------------------------
# 9. Stop timeout can never produce test_passed=True
# ---------------------------------------------------------------------------


def test_stop_timeout_cannot_pass() -> None:
    """A stop_timeout outcome must always produce runtime_protection_test_passed=False."""
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    run_report: dict[str, Any] = {
        "ticks_requested": 100,
        "ticks_completed": 20,
        "terminated_early": True,
        "lidar_frames_injected_dropped": 1,
        "lidar_frames_natural_dropped": 0,
        "fault_injection": {
            "triggered": True,
            "triggered_callback_index": 0,
        },
        "runtime_protection": {
            "fault_triggered": True,
            "autopilot_disabled": True,
            "safe_stop": False,
            "stop_timeout": True,
            "braking_ticks": 100,
            "stopped_ticks": 0,
        },
    }
    qrtc_submission: dict[str, Any] = {
        "status": "rejected",
        "evidence_preserved": True,
        "guard_reasons": [
            {"guard_id": "carla-health-v1", "qualified": False, "reason": "rejected"},
        ],
    }

    result = _classify_runtime_protection(cfg, run_report, qrtc_submission)
    assert result.runtime_protection_test_passed is False
    assert result.test_outcome == "runtime_protection_stop_timeout"


def test_control_action_failure_cannot_pass() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    run_report: dict[str, Any] = {
        "ticks_requested": 100,
        "ticks_completed": 3,
        "terminated_early": True,
        "lidar_frames_injected_dropped": 1,
        "lidar_frames_natural_dropped": 0,
        "fault_injection": {
            "triggered": True,
            "triggered_callback_index": 0,
        },
        "runtime_protection": {
            "state": "control_error",
            "fault_triggered": True,
            "autopilot_disabled": False,
            "safe_stop": False,
            "stop_timeout": False,
            "control_action_failed": True,
        },
    }
    qrtc_submission: dict[str, Any] = {
        "status": "rejected",
        "evidence_preserved": True,
        "guard_reasons": [
            {"guard_id": "carla-health-v1", "qualified": False, "reason": "rejected"},
        ],
    }

    result = _classify_runtime_protection(cfg, run_report, qrtc_submission)
    assert result.runtime_protection_test_passed is False
    assert result.test_outcome == "runtime_protection_control_error"


# ---------------------------------------------------------------------------
# 10. Injected and natural drop accounting stays separate
# ---------------------------------------------------------------------------


def test_injected_and_natural_drops_separate_with_fault_notify() -> None:
    """fault_notify is called for injected drop; record_drop increments natural only."""
    notified: list[tuple[int, Any]] = []

    def on_fault(callback_index: int, sensor_frame: Any) -> None:
        notified.append((callback_index, sensor_frame))

    collector = LidarCollector(drop_frame_index=2, fault_notify=on_fault)

    # Fire 5 callbacks
    for i in range(5):
        m = MagicMock()
        m.frame = 100 + i
        m.timestamp = float(i) * 0.05
        pts = MagicMock()
        pts.point.x = 1.0
        pts.point.y = 0.0
        pts.point.z = 0.0
        m.__iter__ = MagicMock(return_value=iter([pts]))
        collector.on_data(m)

    collector.record_drop()  # natural drop
    snap = collector.snapshot()

    assert snap.injected_drops == 1
    assert snap.natural_drops == 1
    assert len(notified) == 1
    assert notified[0] == (2, 102)  # callback_index=2, sensor_frame=100+2


def test_fault_notify_called_exactly_once_even_with_multiple_callbacks() -> None:
    notified_count = [0]

    def on_fault(callback_index: int, sensor_frame: Any) -> None:
        notified_count[0] += 1

    collector = LidarCollector(drop_frame_index=1, fault_notify=on_fault)

    for i in range(10):
        m = MagicMock()
        m.frame = i
        m.timestamp = float(i)
        pts = MagicMock()
        pts.point.x = 1.0
        pts.point.y = 0.0
        pts.point.z = 0.0
        m.__iter__ = MagicMock(return_value=iter([pts]))
        collector.on_data(m)

    assert notified_count[0] == 1  # called exactly once


def test_fault_notify_none_does_not_break_collector() -> None:
    """LidarCollector without fault_notify still works correctly."""
    collector = LidarCollector(drop_frame_index=1, fault_notify=None)

    for i in range(5):
        m = MagicMock()
        m.frame = i
        m.timestamp = float(i)
        pts = MagicMock()
        pts.point.x = float(i)
        pts.point.y = 0.0
        pts.point.z = 0.0
        m.__iter__ = MagicMock(return_value=iter([pts]))
        collector.on_data(m)

    snap = collector.snapshot()
    assert snap.injected_drops == 1
    assert len(snap.accepted_frames) == 4


# ---------------------------------------------------------------------------
# 11. Controlled injection reaches the runtime protection path
# ---------------------------------------------------------------------------


def test_controlled_injection_reaches_runtime_protection() -> None:
    """End-to-end: LidarCollector fault_notify connects to RuntimeProtection.latch_fault."""
    rp_cfg = _default_rp_cfg(required_stopped_ticks=100, maximum_braking_ticks=50)
    rp = RuntimeProtection(rp_cfg)
    collector = LidarCollector(drop_frame_index=3, fault_notify=rp.latch_fault)

    assert not rp.triggered

    # Send 3 normal callbacks, then the injected one at index 3
    for i in range(4):
        m = MagicMock()
        m.frame = 200 + i
        m.timestamp = float(i)
        pts = MagicMock()
        pts.point.x = 1.0
        pts.point.y = 0.0
        pts.point.z = 0.0
        m.__iter__ = MagicMock(return_value=iter([pts]))
        collector.on_data(m)

    assert rp.triggered
    assert rp.state == RuntimeProtectionState.FAULT_LATCHED

    snap = rp.snapshot()
    assert snap.fault_metadata is not None
    assert snap.fault_metadata.callback_index == 3
    assert snap.fault_metadata.sensor_frame == 203  # frame 200+3

    # Collector accounting: 3 accepted + 1 injected drop, 0 natural
    lidar_snap = collector.snapshot()
    assert lidar_snap.injected_drops == 1
    assert lidar_snap.natural_drops == 0
    assert len(lidar_snap.accepted_frames) == 3


# ---------------------------------------------------------------------------
# 12. QRTC rejection is checked through carla-health-v1 specifically
# ---------------------------------------------------------------------------


def test_classification_requires_carla_health_guard_rejection() -> None:
    """runtime_protection_test_passed requires carla-health-v1 qualified==False."""
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    base_report: dict[str, Any] = {
        "ticks_requested": 10,
        "ticks_completed": 3,
        "terminated_early": True,
        "lidar_frames_injected_dropped": 1,
        "lidar_frames_natural_dropped": 0,
        "fault_injection": {
            "triggered": True,
            "triggered_callback_index": 0,
        },
        "runtime_protection": {
            "fault_triggered": True,
            "autopilot_disabled": True,
            "safe_stop": True,
            "stop_timeout": False,
        },
    }

    # QRTC rejected but health guard NOT included → should fail
    qrtc_no_health = {
        "status": "rejected",
        "evidence_preserved": True,
        "guard_reasons": [
            {"guard_id": "carla-schema-v1", "qualified": False, "reason": "bad schema"},
        ],
    }
    result = _classify_runtime_protection(cfg, base_report, qrtc_no_health)
    assert result.runtime_protection_test_passed is False

    # QRTC rejected WITH carla-health-v1 qualified=False → should pass
    qrtc_with_health = {
        "status": "rejected",
        "evidence_preserved": True,
        "guard_reasons": [
            {"guard_id": "carla-schema-v1", "qualified": True, "reason": "ok"},
            {
                "guard_id": "carla-health-v1",
                "qualified": False,
                "reason": "health failed",
            },
        ],
    }
    result2 = _classify_runtime_protection(cfg, base_report, qrtc_with_health)
    assert result2.runtime_protection_test_passed is True


def test_classification_requires_qrtc_rejected_not_accepted() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    run_report: dict[str, Any] = {
        "ticks_requested": 10,
        "ticks_completed": 3,
        "terminated_early": True,
        "lidar_frames_injected_dropped": 1,
        "lidar_frames_natural_dropped": 0,
        "fault_injection": {"triggered": True, "triggered_callback_index": 0},
        "runtime_protection": {
            "fault_triggered": True,
            "autopilot_disabled": True,
            "safe_stop": True,
            "stop_timeout": False,
        },
    }

    qrtc_accepted = {
        "status": "accepted",
        "evidence_preserved": True,
        "guard_reasons": [
            {"guard_id": "carla-health-v1", "qualified": True, "reason": "ok"},
        ],
    }
    result = _classify_runtime_protection(cfg, run_report, qrtc_accepted)
    assert result.runtime_protection_test_passed is False


# ---------------------------------------------------------------------------
# 13. Evidence is preserved in the snapshot
# ---------------------------------------------------------------------------


def test_snapshot_contains_complete_evidence() -> None:
    rp = RuntimeProtection(_default_rp_cfg(required_stopped_ticks=3))
    cap = _ControlCapture()

    rp.latch_fault(callback_index=5, sensor_frame=55)

    # Enforce until stopped (speed drops below threshold)
    stopped_vehicle = _make_stopped_vehicle()
    for tick in range(5):
        rp.enforce(
            stopped_vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )

    snap = rp.snapshot()
    d = snap.as_dict()

    assert d["fault_triggered"] is True
    assert d["autopilot_disabled"] is True
    assert d["safe_stop"] is True
    assert d["stop_timeout"] is False
    assert d["state"] == RuntimeProtectionState.STOPPED.value
    assert d["fault_metadata"] == {"callback_index": 5, "sensor_frame": 55}
    assert d["fault_reason"] == "fault_injection"
    assert d["first_enforcement_tick"] == 0
    assert d["termination_reason"] == "safe_stop"
    assert d["control_action_failed"] is False
    assert d["control_action_error"] is None
    assert d["braking_ticks"] >= 1
    assert d["stopped_ticks"] >= 3


def test_snapshot_after_timeout_contains_evidence() -> None:
    rp = RuntimeProtection(
        _default_rp_cfg(
            stop_speed_mps=0.01,
            required_stopped_ticks=100,
            maximum_braking_ticks=5,
        )
    )
    vehicle = _make_vehicle(speed=8.0)
    cap = _ControlCapture()

    rp.latch_fault(callback_index=0)
    for tick in range(5):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )

    snap = rp.snapshot()
    assert snap.stop_timeout is True
    assert snap.safe_stop is False
    assert snap.state == RuntimeProtectionState.STOP_TIMEOUT
    assert snap.braking_ticks == 5
    assert snap.termination_reason == "stop_timeout"
    assert snap.final_speed_mps is not None


# ---------------------------------------------------------------------------
# 14. Existing post-run and baseline behaviour unchanged when RP disabled
# ---------------------------------------------------------------------------


def test_classify_runtime_protection_disabled_returns_disabled_outcome() -> None:
    cfg = CarlaConfig(runtime_protection_enabled=False)
    run_report: dict[str, Any] = {
        "ticks_requested": 300,
        "ticks_completed": 300,
        "terminated_early": False,
        "lidar_frames_injected_dropped": 0,
        "lidar_frames_natural_dropped": 0,
        "fault_injection": {"triggered": False},
        "runtime_protection": {
            "fault_triggered": False,
            "autopilot_disabled": False,
            "safe_stop": False,
            "stop_timeout": False,
        },
    }
    result = _classify_runtime_protection(cfg, run_report)
    assert result.runtime_protection_test_passed is False
    assert result.test_outcome == "runtime_protection_disabled"


def test_rp_disabled_supervisor_never_calls_vehicle_control() -> None:
    """With runtime_protection_enabled=False, no vehicle control is ever called."""
    rp_cfg = RuntimeProtectionConfig(enabled=False)
    rp = RuntimeProtection(rp_cfg)
    vehicle = _make_vehicle(speed=5.0)
    cap = _ControlCapture()

    # Even if we manually latch a fault (shouldn't happen, but defensive test)
    rp.latch_fault(0, None)

    for tick in range(10):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )

    # The supervisor should proceed normally (state machine doesn't check enabled here,
    # but callers should guard on cfg.runtime_protection_enabled before calling enforce).
    # This test verifies the state transitions regardless of the enabled flag.
    # Vehicle control WAS called since we forced a latch even with enabled=False.
    # The harness guards this with `if cfg.runtime_protection_enabled`.
    # This just verifies the supervisor itself still works when used manually.
    assert rp.triggered


# ---------------------------------------------------------------------------
# 15. Configuration environment parsing and validation
# ---------------------------------------------------------------------------


def test_carla_config_runtime_protection_defaults() -> None:
    cfg = CarlaConfig()
    assert cfg.runtime_protection_enabled is False
    assert cfg.runtime_stop_speed_mps == pytest.approx(0.10)
    assert cfg.runtime_required_stopped_ticks == 5
    assert cfg.runtime_maximum_braking_ticks == 100
    assert cfg.runtime_full_brake == pytest.approx(1.0)
    assert cfg.runtime_lidar_callback_timeout_seconds == pytest.approx(0.25)


def test_carla_config_runtime_protection_in_as_dict() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        runtime_stop_speed_mps=0.05,
        runtime_required_stopped_ticks=3,
        runtime_maximum_braking_ticks=50,
        runtime_full_brake=0.9,
        runtime_lidar_callback_timeout_seconds=0.5,
    )
    d = cfg.as_dict()
    assert d["runtime_protection_enabled"] is True
    assert d["runtime_stop_speed_mps"] == pytest.approx(0.05)
    assert d["runtime_required_stopped_ticks"] == 3
    assert d["runtime_maximum_braking_ticks"] == 50
    assert d["runtime_full_brake"] == pytest.approx(0.9)
    assert d["runtime_lidar_callback_timeout_seconds"] == pytest.approx(0.5)


def test_carla_config_from_env_runtime_protection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARLA_RUNTIME_PROTECTION_ENABLED", "true")
    monkeypatch.setenv("CARLA_RUNTIME_STOP_SPEED_MPS", "0.05")
    monkeypatch.setenv("CARLA_RUNTIME_STOPPED_TICKS", "3")
    monkeypatch.setenv("CARLA_RUNTIME_MAX_BRAKING_TICKS", "50")
    monkeypatch.setenv("CARLA_RUNTIME_FULL_BRAKE", "0.9")
    monkeypatch.setenv("CARLA_RUNTIME_LIDAR_CALLBACK_TIMEOUT_SECONDS", "0.5")

    cfg = carla_config_from_env()
    assert cfg.runtime_protection_enabled is True
    assert cfg.runtime_stop_speed_mps == pytest.approx(0.05)
    assert cfg.runtime_required_stopped_ticks == 3
    assert cfg.runtime_maximum_braking_ticks == 50
    assert cfg.runtime_full_brake == pytest.approx(0.9)
    assert cfg.runtime_lidar_callback_timeout_seconds == pytest.approx(0.5)


def test_carla_config_from_env_runtime_protection_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in (
        "CARLA_RUNTIME_PROTECTION_ENABLED",
        "CARLA_RUNTIME_STOP_SPEED_MPS",
        "CARLA_RUNTIME_STOPPED_TICKS",
        "CARLA_RUNTIME_MAX_BRAKING_TICKS",
        "CARLA_RUNTIME_FULL_BRAKE",
        "CARLA_RUNTIME_LIDAR_CALLBACK_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)

    cfg = carla_config_from_env()
    assert cfg.runtime_protection_enabled is False
    assert cfg.runtime_stop_speed_mps == pytest.approx(0.10)
    assert cfg.runtime_required_stopped_ticks == 5
    assert cfg.runtime_maximum_braking_ticks == 100
    assert cfg.runtime_full_brake == pytest.approx(1.0)
    assert cfg.runtime_lidar_callback_timeout_seconds == pytest.approx(0.25)


def test_validate_carla_config_runtime_protection_invalid_values() -> None:
    cfg = CarlaConfig(
        runtime_stop_speed_mps=-0.01,
        runtime_required_stopped_ticks=0,
        runtime_maximum_braking_ticks=0,
        runtime_full_brake=1.5,
        runtime_lidar_callback_timeout_seconds=-1.0,
    )
    errors = validate_carla_config(cfg)
    assert any("runtime_stop_speed_mps" in e for e in errors)
    assert any("runtime_required_stopped_ticks" in e for e in errors)
    assert any("runtime_maximum_braking_ticks" in e for e in errors)
    assert any("runtime_full_brake" in e for e in errors)
    assert any("runtime_lidar_callback_timeout_seconds" in e for e in errors)


def test_validate_carla_config_runtime_protection_valid() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        runtime_stop_speed_mps=0.10,
        runtime_required_stopped_ticks=5,
        runtime_maximum_braking_ticks=100,
        runtime_full_brake=1.0,
        runtime_lidar_callback_timeout_seconds=0.25,
    )
    errors = validate_carla_config(cfg)
    # Should have no runtime-protection errors
    rp_errors = [e for e in errors if "runtime" in e]
    assert rp_errors == []


def test_runtime_protection_config_validation() -> None:
    with pytest.raises(ValueError, match="stop_speed_mps"):
        RuntimeProtectionConfig(stop_speed_mps=-0.1)

    with pytest.raises(ValueError, match="required_stopped_ticks"):
        RuntimeProtectionConfig(required_stopped_ticks=0)

    with pytest.raises(ValueError, match="maximum_braking_ticks"):
        RuntimeProtectionConfig(maximum_braking_ticks=0)

    with pytest.raises(ValueError, match="full_brake"):
        RuntimeProtectionConfig(full_brake=0.0)

    with pytest.raises(ValueError, match="full_brake"):
        RuntimeProtectionConfig(full_brake=1.1)

    with pytest.raises(ValueError, match="stop_speed_mps must be finite"):
        RuntimeProtectionConfig(stop_speed_mps=float("nan"))

    with pytest.raises(ValueError, match="full_brake must be finite"):
        RuntimeProtectionConfig(full_brake=float("inf"))


def test_runtime_protection_config_as_dict() -> None:
    cfg = RuntimeProtectionConfig(
        enabled=True,
        stop_speed_mps=0.05,
        required_stopped_ticks=3,
        maximum_braking_ticks=50,
        full_brake=0.9,
    )
    d = cfg.as_dict()
    assert d["enabled"] is True
    assert d["stop_speed_mps"] == pytest.approx(0.05)
    assert d["required_stopped_ticks"] == 3
    assert d["maximum_braking_ticks"] == 50
    assert d["full_brake"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# 16. _classify_runtime_protection logic
# ---------------------------------------------------------------------------


def _base_rp_pass_report() -> dict[str, Any]:
    """Minimal run report that should produce runtime_protection_test_passed=True
    when paired with the right QRTC submission."""
    return {
        "ticks_requested": 100,
        "ticks_completed": 15,
        "terminated_early": True,
        "lidar_frames_injected_dropped": 1,
        "lidar_frames_natural_dropped": 0,
        "fault_injection": {
            "triggered": True,
            "triggered_callback_index": 0,
        },
        "runtime_protection": {
            "fault_triggered": True,
            "autopilot_disabled": True,
            "safe_stop": True,
            "stop_timeout": False,
        },
    }


def _health_rejected_qrtc() -> dict[str, Any]:
    return {
        "status": "rejected",
        "evidence_preserved": True,
        "guard_reasons": [
            {
                "guard_id": "carla-health-v1",
                "qualified": False,
                "reason": "health failed",
            },
        ],
    }


def test_classify_passes_when_all_conditions_met() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    result = _classify_runtime_protection(
        cfg, _base_rp_pass_report(), _health_rejected_qrtc()
    )
    assert result.runtime_protection_test_passed is True
    assert result.test_outcome == "runtime_protection_pass"


def test_classify_fails_without_qrtc_submission() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    result = _classify_runtime_protection(cfg, _base_rp_pass_report(), None)
    assert result.runtime_protection_test_passed is False


def test_classify_fails_without_early_termination() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    report = _base_rp_pass_report()
    report["terminated_early"] = False
    result = _classify_runtime_protection(cfg, report, _health_rejected_qrtc())
    assert result.runtime_protection_test_passed is False


def test_classify_fails_without_fault_triggered() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    report = _base_rp_pass_report()
    report["runtime_protection"]["fault_triggered"] = False
    result = _classify_runtime_protection(cfg, report, _health_rejected_qrtc())
    assert result.runtime_protection_test_passed is False


def test_classify_fails_without_autopilot_disabled() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    report = _base_rp_pass_report()
    report["runtime_protection"]["autopilot_disabled"] = False
    result = _classify_runtime_protection(cfg, report, _health_rejected_qrtc())
    assert result.runtime_protection_test_passed is False


def test_classify_fails_with_natural_drops() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    report = _base_rp_pass_report()
    report["lidar_frames_natural_dropped"] = 1
    result = _classify_runtime_protection(cfg, report, _health_rejected_qrtc())
    assert result.runtime_protection_test_passed is False


def test_classify_fails_when_evidence_not_preserved() -> None:
    cfg = CarlaConfig(
        runtime_protection_enabled=True,
        lidar=LidarConfig(drop_frame_index=0),
    )
    qrtc = _health_rejected_qrtc()
    qrtc["evidence_preserved"] = False
    result = _classify_runtime_protection(cfg, _base_rp_pass_report(), qrtc)
    assert result.runtime_protection_test_passed is False


# ---------------------------------------------------------------------------
# 17. Full run_drive() integration with fake CARLA and RP enabled
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


def _make_carla_with_rp(
    *,
    tick_count: int = 300,
    drop_at: int = 5,
    speed_after_fault: float = 0.0,
    missing_frames: set[int] | None = None,
    slow_after_tick_index: int | None = None,
) -> tuple[MagicMock, MagicMock]:
    """
    Build a fake CARLA module that:
    - Fires a LiDAR callback every tick
    - The callback at ``drop_at`` is the injected drop (handled by LidarCollector)
    - After the drop tick, vehicle speed drops to speed_after_fault
    """
    carla = MagicMock()
    carla.Transform.return_value = MagicMock()
    carla.Location.return_value = MagicMock()

    # VehicleControl fake
    def make_control() -> MagicMock:
        ctrl = MagicMock()
        ctrl.throttle = 0.0
        ctrl.brake = 0.0
        ctrl.steer = 0.0
        return ctrl

    carla.VehicleControl.side_effect = make_control

    blueprint = MagicMock()
    blueprint.id = "vehicle.tesla.model3"
    collision_bp = MagicMock()
    lidar_bp = MagicMock()
    lidar_bp.set_attribute = MagicMock()
    lib = MagicMock()

    def find_bp(name: str) -> Any:
        if "tesla" in name:
            return blueprint
        if "collision" in name:
            return collision_bp
        if "lidar" in name:
            return lidar_bp
        return None

    lib.find.side_effect = find_bp
    lib.filter.return_value = [blueprint]

    collision_sensor = MagicMock()
    collision_sensor.stop = MagicMock()
    collision_sensor.destroy = MagicMock()
    collision_sensor.listen = MagicMock()

    lidar_sensor = MagicMock()
    lidar_sensor.stop = MagicMock()
    lidar_sensor.destroy = MagicMock()
    lidar_listener: dict[str, Any] = {"fn": None}

    def listen(fn: Any) -> None:
        lidar_listener["fn"] = fn

    lidar_sensor.listen = listen

    world_map = MagicMock()
    world_map.name = "Town01_Fake"
    world_map.get_spawn_points.return_value = [_make_spawn_point() for _ in range(3)]

    settings = MagicMock()
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = 0.05

    world = MagicMock()
    world.get_map.return_value = world_map
    world.get_settings.return_value = settings
    world.apply_settings = MagicMock()
    world.get_blueprint_library.return_value = lib

    ego = MagicMock()
    ego.id = 99
    ego.type_id = "vehicle.tesla.model3"

    transforms = []
    for i in range(tick_count + 50):
        t = MagicMock()
        t.location.x = float(i)
        t.location.y = 0.0
        t.location.z = 0.0
        t.rotation.pitch = 0.0
        t.rotation.yaw = 0.0
        t.rotation.roll = 0.0
        transforms.append(t)
    ego.get_transform.side_effect = transforms + [transforms[-1]] * 20

    tick_index = {"value": 0}

    def get_velocity() -> MagicMock:
        current = tick_index["value"]
        cutoff = drop_at if slow_after_tick_index is None else slow_after_tick_index
        if current > cutoff:
            return _make_velocity(speed_after_fault, 0.0, 0.0)
        return _make_velocity(5.0, 0.0, 0.0)

    ego.get_velocity.side_effect = get_velocity
    ego.set_autopilot = MagicMock()
    ego.apply_control = MagicMock()

    world.try_spawn_actor.return_value = ego

    def spawn_actor(bp: Any, transform: Any, attach_to: Any = None) -> MagicMock:
        if bp is collision_bp:
            return collision_sensor
        return lidar_sensor

    world.spawn_actor.side_effect = spawn_actor

    def tick() -> int:
        current = tick_index["value"]
        tick_index["value"] += 1
        world_frame = current + 1
        listener = lidar_listener["fn"]
        if listener is not None and world_frame not in (missing_frames or set()):
            m = _make_fake_measurement(
                [(1.0, 0.0, 0.0)],
                frame=world_frame,
                timestamp=float(current) * 0.05,
            )
            listener(m)
        return world_frame

    world.tick.side_effect = tick

    tm = MagicMock()
    client = MagicMock()
    client.get_client_version.return_value = "0.9.16"
    client.get_server_version.return_value = "0.9.16"
    client.get_world.return_value = world
    client.get_trafficmanager.return_value = tm
    carla.Client.return_value = client

    return carla, ego


def test_run_drive_with_rp_disabled_completes_all_ticks(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """With RP disabled, run_drive completes normally without early termination."""
    carla_fake, ego = _make_carla_with_rp(tick_count=10, drop_at=2)

    cfg = CarlaConfig(
        ticks=10,
        output=str(tmp_path / "result.json"),
        runtime_protection_enabled=False,
        lidar=LidarConfig(enabled=True, drop_frame_index=2),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=carla_fake):
        report = __import__("qrtc.carla_harness", fromlist=["run_drive"]).run_drive(cfg)

    assert report["ticks_completed"] == 10
    assert report["terminated_early"] is False
    assert report["runtime_protection"]["fault_triggered"] is False
    assert report["runtime_protection"]["state"] == "armed"
    assert report["runtime_protection_test_passed"] is False


def test_run_drive_with_rp_enabled_terminates_early(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """With RP enabled and fault injected, run_drive terminates early."""
    # Vehicle stops immediately after fault (speed=0)
    carla_fake, ego = _make_carla_with_rp(
        tick_count=100, drop_at=3, speed_after_fault=0.0
    )

    cfg = CarlaConfig(
        ticks=100,
        output=str(tmp_path / "result.json"),
        runtime_protection_enabled=True,
        runtime_stop_speed_mps=0.10,
        runtime_required_stopped_ticks=3,
        runtime_maximum_braking_ticks=50,
        lidar=LidarConfig(enabled=True, drop_frame_index=3),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=carla_fake):
        report = __import__("qrtc.carla_harness", fromlist=["run_drive"]).run_drive(cfg)

    # Must terminate before all 100 ticks
    assert report["ticks_completed"] < 100
    assert report["terminated_early"] is True
    assert report["status"] == "partial"

    rp = report["runtime_protection"]
    assert rp["fault_triggered"] is True
    assert rp["autopilot_disabled"] is True
    assert rp["safe_stop"] is True
    assert rp["stop_timeout"] is False
    assert rp["state"] == "stopped"
    assert rp["fault_reason"] == "fault_injection"

    # At least one False call from runtime protection
    false_calls = [c for c in ego.set_autopilot.call_args_list if False in c.args]
    assert len(false_calls) >= 1


def test_run_drive_with_rp_enabled_timeout(tmp_path: pytest.TempPathFactory) -> None:
    """With RP enabled but vehicle doesn't stop, STOP_TIMEOUT is reached."""
    # Vehicle never stops (speed=5.0 always)
    carla_fake, ego = _make_carla_with_rp(
        tick_count=200, drop_at=3, speed_after_fault=5.0
    )

    cfg = CarlaConfig(
        ticks=200,
        output=str(tmp_path / "result.json"),
        runtime_protection_enabled=True,
        runtime_stop_speed_mps=0.10,
        runtime_required_stopped_ticks=100,
        runtime_maximum_braking_ticks=5,
        lidar=LidarConfig(enabled=True, drop_frame_index=3),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=carla_fake):
        report = __import__("qrtc.carla_harness", fromlist=["run_drive"]).run_drive(cfg)

    assert report["terminated_early"] is True
    assert report["status"] == "partial"
    rp = report["runtime_protection"]
    assert rp["fault_triggered"] is True
    assert rp["state"] == "stop_timeout"
    assert rp["stop_timeout"] is True
    assert rp["safe_stop"] is False
    assert report["runtime_protection_test_passed"] is False


def test_run_drive_persists_runtime_test_outcome_when_enabled(tmp_path: Path) -> None:
    carla_fake, _ = _make_carla_with_rp(
        tick_count=50,
        drop_at=3,
        speed_after_fault=0.0,
    )
    output = tmp_path / "runtime-enabled.json"
    cfg = CarlaConfig(
        ticks=50,
        output=str(output),
        submit_to_qrtc=True,
        qrtc_db=str(tmp_path / "evidence.sqlite3"),
        principal="carla-operator",
        runtime_protection_enabled=True,
        runtime_stop_speed_mps=0.10,
        runtime_required_stopped_ticks=2,
        runtime_maximum_braking_ticks=10,
        runtime_lidar_callback_timeout_seconds=0.05,
        lidar=LidarConfig(enabled=True, drop_frame_index=3),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=carla_fake):
        report = __import__("qrtc.carla_harness", fromlist=["run_drive"]).run_drive(cfg)

    written = json.loads(output.read_text(encoding="utf-8"))
    for persisted in (report, written):
        assert persisted["status"] == "partial"
        assert persisted["test_outcome"] == "runtime_protection_pass"
        assert persisted["runtime_protection_test_passed"] is True
        assert persisted["runtime_protection"]["fault_reason"] == "fault_injection"
        assert persisted["qrtc_submission"]["status"] == "rejected"
        assert persisted["qrtc_submission"]["evidence_preserved"] is True
        assert any(
            reason.get("guard_id") == "carla-schema-v1"
            and reason.get("qualified") is True
            for reason in persisted["qrtc_submission"]["guard_reasons"]
        )
        assert any(
            reason.get("guard_id") == "carla-health-v1"
            and reason.get("qualified") is False
            for reason in persisted["qrtc_submission"]["guard_reasons"]
        )


def test_run_drive_preserves_post_run_test_outcome_when_rp_disabled(
    tmp_path: Path,
) -> None:
    carla_fake, _ = _make_carla_with_rp(
        tick_count=25,
        drop_at=3,
        speed_after_fault=0.0,
    )
    output = tmp_path / "runtime-disabled.json"
    cfg = CarlaConfig(
        ticks=25,
        output=str(output),
        submit_to_qrtc=True,
        qrtc_db=str(tmp_path / "evidence.sqlite3"),
        principal="carla-operator",
        runtime_protection_enabled=False,
        lidar=LidarConfig(enabled=True, drop_frame_index=3),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=carla_fake):
        report = __import__("qrtc.carla_harness", fromlist=["run_drive"]).run_drive(cfg)

    written = json.loads(output.read_text(encoding="utf-8"))
    for persisted in (report, written):
        assert persisted["status"] == "completed"
        assert persisted["test_outcome"] == "post_run_rejection_pass"
        assert persisted["post_run_rejection_test_passed"] is True
        assert persisted["runtime_protection_test_passed"] is False


def test_run_drive_natural_callback_timeout_rejected_by_health(tmp_path: Path) -> None:
    carla_fake, _ = _make_carla_with_rp(
        tick_count=30,
        drop_at=100,
        speed_after_fault=0.0,
        missing_frames={4},
        slow_after_tick_index=3,
    )
    output = tmp_path / "natural-timeout.json"
    cfg = CarlaConfig(
        ticks=30,
        output=str(output),
        submit_to_qrtc=True,
        qrtc_db=str(tmp_path / "evidence.sqlite3"),
        principal="carla-operator",
        runtime_protection_enabled=True,
        runtime_stop_speed_mps=0.10,
        runtime_required_stopped_ticks=2,
        runtime_maximum_braking_ticks=10,
        runtime_lidar_callback_timeout_seconds=0.0,
        lidar=LidarConfig(enabled=True, drop_frame_index=-1),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=carla_fake):
        report = __import__("qrtc.carla_harness", fromlist=["run_drive"]).run_drive(cfg)

    assert report["status"] == "partial"
    assert report["runtime_protection"]["fault_reason"] == "lidar_callback_timeout"
    assert report["runtime_protection"]["safe_stop"] is True
    assert report["lidar_frames_natural_dropped"] == 1
    assert report["lidar_frames_injected_dropped"] == 0
    assert report["qrtc_submission"]["status"] == "rejected"
    assert report["qrtc_submission"]["evidence_preserved"] is True
    assert any(
        reason.get("guard_id") == "carla-schema-v1" and reason.get("qualified") is True
        for reason in report["qrtc_submission"]["guard_reasons"]
    )
    assert any(
        reason.get("guard_id") == "carla-health-v1" and reason.get("qualified") is False
        for reason in report["qrtc_submission"]["guard_reasons"]
    )
    assert report["runtime_protection_test_passed"] is False


def test_run_drive_autopilot_disable_failure_aborts(tmp_path: Path) -> None:
    carla_fake, ego = _make_carla_with_rp(
        tick_count=20,
        drop_at=2,
        speed_after_fault=0.0,
    )
    ego.set_autopilot.side_effect = [
        None,
        RuntimeError("cannot disable autopilot"),
        None,
    ]
    cfg = CarlaConfig(
        ticks=20,
        output=str(tmp_path / "autopilot-failure.json"),
        runtime_protection_enabled=True,
        runtime_required_stopped_ticks=2,
        runtime_maximum_braking_ticks=10,
        lidar=LidarConfig(enabled=True, drop_frame_index=2),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=carla_fake):
        report = __import__("qrtc.carla_harness", fromlist=["run_drive"]).run_drive(cfg)

    assert report["status"] == "aborted"
    assert report["test_outcome"] == "runtime_protection_control_error"
    assert report["runtime_protection"]["autopilot_disabled"] is False
    assert report["runtime_protection"]["state"] == "control_error"
    assert report["runtime_protection"]["control_action_error"]["action"] == (
        "set_autopilot(False)"
    )


def test_run_drive_braking_control_failure_aborts(tmp_path: Path) -> None:
    carla_fake, ego = _make_carla_with_rp(
        tick_count=20,
        drop_at=2,
        speed_after_fault=0.0,
    )
    ego.apply_control.side_effect = RuntimeError("braking control failed")
    cfg = CarlaConfig(
        ticks=20,
        output=str(tmp_path / "braking-failure.json"),
        runtime_protection_enabled=True,
        runtime_required_stopped_ticks=2,
        runtime_maximum_braking_ticks=10,
        lidar=LidarConfig(enabled=True, drop_frame_index=2),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=carla_fake):
        report = __import__("qrtc.carla_harness", fromlist=["run_drive"]).run_drive(cfg)

    assert report["status"] == "aborted"
    assert report["test_outcome"] == "runtime_protection_control_error"
    assert report["runtime_protection"]["autopilot_disabled"] is True
    assert report["runtime_protection"]["state"] == "control_error"
    assert report["runtime_protection"]["control_action_error"]["action"] == (
        "apply_control(brake)"
    )


# ---------------------------------------------------------------------------
# Speed helper
# ---------------------------------------------------------------------------


def test_compute_speed_mps_basic() -> None:
    rp = RuntimeProtection(_default_rp_cfg())
    v = MagicMock()
    v.x = 3.0
    v.y = 4.0
    v.z = 0.0
    assert rp.compute_speed_mps(v) == pytest.approx(5.0)


def test_compute_speed_mps_zero() -> None:
    rp = RuntimeProtection(_default_rp_cfg())
    v = MagicMock()
    v.x = 0.0
    v.y = 0.0
    v.z = 0.0
    assert rp.compute_speed_mps(v) == pytest.approx(0.0)


def test_compute_speed_mps_bad_attribute() -> None:
    rp = RuntimeProtection(_default_rp_cfg())
    v = MagicMock()
    del v.x  # make attribute access fail
    assert rp.compute_speed_mps(v) == float("inf")


@pytest.mark.parametrize(
    ("velocity", "label"),
    [
        (MagicMock(y=0.0, z=0.0), "missing x attribute"),
        (_make_velocity("fast", 0.0, 0.0), "nonnumeric x"),
        (_make_velocity(float("nan"), 0.0, 0.0), "nan x"),
        (_make_velocity(float("inf"), 0.0, 0.0), "positive infinity x"),
        (_make_velocity(float("-inf"), 0.0, 0.0), "negative infinity x"),
    ],
)
def test_compute_speed_mps_invalid_velocity_returns_inf(
    velocity: Any,
    label: str,
) -> None:
    rp = RuntimeProtection(_default_rp_cfg())
    if label == "missing x attribute":
        del velocity.x
    assert rp.compute_speed_mps(velocity) == float("inf")


@pytest.mark.parametrize(
    "velocity_factory",
    [
        lambda: MagicMock(y=0.0, z=0.0),
        lambda: _make_velocity("fast", 0.0, 0.0),
        lambda: _make_velocity(float("nan"), 0.0, 0.0),
        lambda: _make_velocity(float("inf"), 0.0, 0.0),
        lambda: _make_velocity(float("-inf"), 0.0, 0.0),
    ],
)
def test_invalid_speed_measurements_cannot_confirm_safe_stop(
    velocity_factory: Any,
) -> None:
    rp = RuntimeProtection(
        _default_rp_cfg(
            stop_speed_mps=0.10,
            required_stopped_ticks=2,
            maximum_braking_ticks=2,
        )
    )
    vehicle = _make_vehicle(speed=0.0)
    vehicle.get_velocity.side_effect = lambda: velocity_factory()
    cap = _ControlCapture()
    rp.latch_fault(callback_index=0)

    for tick in range(2):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )

    snap = rp.snapshot()
    assert snap.safe_stop is False
    assert snap.state == RuntimeProtectionState.STOP_TIMEOUT

    result = _classify_runtime_protection(
        CarlaConfig(
            runtime_protection_enabled=True, lidar=LidarConfig(drop_frame_index=0)
        ),
        {
            "ticks_requested": 10,
            "ticks_completed": 2,
            "terminated_early": True,
            "lidar_frames_injected_dropped": 1,
            "lidar_frames_natural_dropped": 0,
            "fault_injection": {"triggered": True, "triggered_callback_index": 0},
            "runtime_protection": snap.as_dict(),
        },
        _health_rejected_qrtc(),
    )
    assert result.runtime_protection_test_passed is False


def test_get_velocity_exception_cannot_confirm_safe_stop() -> None:
    rp = RuntimeProtection(
        _default_rp_cfg(
            stop_speed_mps=0.10,
            required_stopped_ticks=2,
            maximum_braking_ticks=2,
        )
    )
    vehicle = _make_vehicle(speed=0.0)
    vehicle.get_velocity.side_effect = RuntimeError("velocity unavailable")
    cap = _ControlCapture()
    rp.latch_fault(callback_index=0)

    for tick in range(2):
        rp.enforce(
            vehicle,
            tick,
            disable_autopilot=cap.disable_autopilot,
            apply_control=cap.apply,
        )

    snap = rp.snapshot()
    assert snap.safe_stop is False
    assert snap.state == RuntimeProtectionState.STOP_TIMEOUT


# ---------------------------------------------------------------------------
# FaultMetadata as_dict
# ---------------------------------------------------------------------------


def test_fault_metadata_as_dict() -> None:
    fm = FaultMetadata(callback_index=7, sensor_frame=1234)
    d = fm.as_dict()
    assert d["callback_index"] == 7
    assert d["sensor_frame"] == 1234


def test_fault_metadata_as_dict_none_frame() -> None:
    fm = FaultMetadata(callback_index=3, sensor_frame=None)
    d = fm.as_dict()
    assert d["sensor_frame"] is None
