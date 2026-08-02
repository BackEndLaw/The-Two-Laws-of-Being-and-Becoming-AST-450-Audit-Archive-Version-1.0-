"""
CARLA simulator runtime protection for LiDAR faults.

Implements an opt-in main-loop safety state machine that:
1. Latches a LiDAR fault from the sensor-side path.
2. Disables autopilot exactly once on the main simulation thread.
3. Applies braking-only commands on every protection tick.
4. Continues until confirmed stop or braking timeout.
5. Terminates the run early and preserves evidence for QRTC submission.

SAFETY SCOPE
------------
This is **simulator runtime protection only**.  It is NOT physical-vehicle
certification and does NOT claim physical deployment readiness.  Live CARLA
acceptance must still verify: configured stop threshold, braking deadline,
road conditions, timeout bounds, early termination, QRTC rejection, and
evidence preservation before drawing any safety conclusion.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class RuntimeProtectionState(str, Enum):
    ARMED = "armed"
    FAULT_LATCHED = "fault_latched"
    BRAKING = "braking"
    STOPPED = "stopped"
    STOP_TIMEOUT = "stop_timeout"
    CONTROL_ERROR = "control_error"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeProtectionConfig:
    """
    Immutable configuration for the runtime protection supervisor.

    Disabled by default so that all existing baseline and post-run behaviour
    is completely unchanged when ``enabled=False``.
    """

    enabled: bool = False
    stop_speed_mps: float = 0.10
    required_stopped_ticks: int = 5
    maximum_braking_ticks: int = 100
    full_brake: float = 1.0

    def __post_init__(self) -> None:
        if self.stop_speed_mps < 0.0:
            raise ValueError(f"stop_speed_mps must be >= 0, got {self.stop_speed_mps}")
        if not math.isfinite(self.stop_speed_mps):
            raise ValueError(
                f"stop_speed_mps must be finite, got {self.stop_speed_mps}"
            )
        if self.required_stopped_ticks < 1:
            raise ValueError(
                f"required_stopped_ticks must be >= 1, "
                f"got {self.required_stopped_ticks}"
            )
        if self.maximum_braking_ticks < 1:
            raise ValueError(
                f"maximum_braking_ticks must be >= 1, "
                f"got {self.maximum_braking_ticks}"
            )
        if not math.isfinite(self.full_brake):
            raise ValueError(f"full_brake must be finite, got {self.full_brake}")
        if not (0.0 < self.full_brake <= 1.0):
            raise ValueError(f"full_brake must be in (0, 1], got {self.full_brake}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "stop_speed_mps": self.stop_speed_mps,
            "required_stopped_ticks": self.required_stopped_ticks,
            "maximum_braking_ticks": self.maximum_braking_ticks,
            "full_brake": self.full_brake,
        }


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaultMetadata:
    callback_index: Optional[int]
    sensor_frame: Optional[int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "callback_index": self.callback_index,
            "sensor_frame": self.sensor_frame,
        }


@dataclass(frozen=True)
class ControlActionError:
    action: str
    message: str
    tick_index: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "message": self.message,
            "tick_index": self.tick_index,
        }


@dataclass(frozen=True)
class RuntimeProtectionSnapshot:
    """Immutable evidence snapshot from the runtime protection supervisor."""

    state: RuntimeProtectionState
    fault_triggered: bool
    autopilot_disabled: bool
    braking_ticks: int
    speed_at_detection_mps: Optional[float]
    final_speed_mps: Optional[float]
    stopped_ticks: int
    safe_stop: bool
    stop_timeout: bool
    first_enforcement_tick: Optional[int]
    fault_metadata: Optional[FaultMetadata]
    fault_reason: Optional[str]
    termination_reason: Optional[str]
    control_action_failed: bool
    control_action_error: Optional[ControlActionError]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "fault_triggered": self.fault_triggered,
            "autopilot_disabled": self.autopilot_disabled,
            "braking_ticks": self.braking_ticks,
            "speed_at_detection_mps": self.speed_at_detection_mps,
            "final_speed_mps": self.final_speed_mps,
            "stopped_ticks": self.stopped_ticks,
            "safe_stop": self.safe_stop,
            "stop_timeout": self.stop_timeout,
            "first_enforcement_tick": self.first_enforcement_tick,
            "fault_metadata": (
                None if self.fault_metadata is None else self.fault_metadata.as_dict()
            ),
            "fault_reason": self.fault_reason,
            "termination_reason": self.termination_reason,
            "control_action_failed": self.control_action_failed,
            "control_action_error": (
                None
                if self.control_action_error is None
                else self.control_action_error.as_dict()
            ),
        }


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------


class RuntimeProtection:
    """
    Thread-safe runtime protection supervisor.

    The sensor callback calls :meth:`latch_fault` (no vehicle control).
    The main simulation thread calls :meth:`enforce` after every synchronous
    tick; it manages autopilot, braking, and state transitions.

    SAFETY SCOPE
    ------------
    Simulator use only.  Not a physical-vehicle safety system.
    """

    def __init__(self, config: RuntimeProtectionConfig) -> None:
        self._cfg = config
        self._lock = threading.Lock()
        self._state = RuntimeProtectionState.ARMED
        self._fault_metadata: Optional[FaultMetadata] = None
        self._fault_reason: Optional[str] = None
        self._autopilot_disabled = False
        self._braking_ticks = 0
        self._stopped_ticks = 0
        self._speed_at_detection: Optional[float] = None
        self._final_speed: Optional[float] = None
        self._first_enforcement_tick: Optional[int] = None
        self._safe_stop = False
        self._stop_timeout = False
        self._termination_reason: Optional[str] = None
        self._control_action_error: Optional[ControlActionError] = None

    # ------------------------------------------------------------------
    # Sensor-thread API (no vehicle control)
    # ------------------------------------------------------------------

    def latch_fault(
        self,
        callback_index: Optional[int],
        sensor_frame: Optional[int] = None,
        *,
        reason: str = "fault_injection",
    ) -> None:
        """
        Latch the first fault from the sensor callback thread.

        Only the first call takes effect; subsequent calls are silently
        ignored.  This method MUST NOT call any CARLA vehicle control API.
        """
        with self._lock:
            if self._fault_metadata is not None:
                return
            self._fault_metadata = FaultMetadata(
                callback_index=callback_index,
                sensor_frame=sensor_frame,
            )
            self._fault_reason = reason
            self._state = RuntimeProtectionState.FAULT_LATCHED

    # ------------------------------------------------------------------
    # Main-thread read helpers
    # ------------------------------------------------------------------

    @property
    def triggered(self) -> bool:
        """True once a fault has been latched."""
        with self._lock:
            return self._fault_metadata is not None

    @property
    def terminal(self) -> bool:
        """True when the state machine has reached STOPPED or STOP_TIMEOUT."""
        with self._lock:
            return self._state in (
                RuntimeProtectionState.STOPPED,
                RuntimeProtectionState.STOP_TIMEOUT,
                RuntimeProtectionState.CONTROL_ERROR,
            )

    @property
    def state(self) -> RuntimeProtectionState:
        with self._lock:
            return self._state

    # ------------------------------------------------------------------
    # Speed helper (pure, testable)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_speed_mps(velocity: Any) -> float:
        """Compute 3-D speed in m/s from a velocity object with x, y, z."""
        try:
            vx = float(velocity.x)
            vy = float(velocity.y)
            vz = float(velocity.z)
        except (AttributeError, TypeError, ValueError):
            return math.inf
        if not all(math.isfinite(component) for component in (vx, vy, vz)):
            return math.inf
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        return speed if math.isfinite(speed) else math.inf

    def _record_control_action_error(
        self,
        *,
        action: str,
        tick_index: int,
        error: Exception,
    ) -> RuntimeProtectionState:
        with self._lock:
            self._safe_stop = False
            self._stop_timeout = False
            self._termination_reason = "control_action_error"
            self._control_action_error = ControlActionError(
                action=action,
                message=str(error),
                tick_index=tick_index,
            )
            self._state = RuntimeProtectionState.CONTROL_ERROR
            return self._state

    # ------------------------------------------------------------------
    # Main-thread enforcement
    # ------------------------------------------------------------------

    def enforce(
        self,
        vehicle: Any,
        tick_index: int,
        *,
        disable_autopilot: Callable[[Any], None],
        apply_control: Callable[[Any, float, float, float], None],
    ) -> RuntimeProtectionState:
        """
        Called on the main simulation thread after each synchronous tick.

        Parameters
        ----------
        vehicle:
            CARLA vehicle actor.
        tick_index:
            Zero-based simulation tick index (used to record first enforcement
            tick; not used for any time-based logic).
        disable_autopilot:
            ``callable(vehicle) -> None`` — called exactly once to disengage
            autopilot.  CARLA vehicle control APIs are only called from this
            main-thread context.
        apply_control:
            ``callable(vehicle, throttle, brake, steer) -> None`` — called on
            every enforcement tick to apply braking-only control.

        Returns
        -------
        RuntimeProtectionState
            The current state after enforcement.
        """
        with self._lock:
            state = self._state

        # Nothing to do while armed and no fault has been latched.
        if state == RuntimeProtectionState.ARMED:
            return state

        # Terminal states — no further action needed.
        if state in (
            RuntimeProtectionState.STOPPED,
            RuntimeProtectionState.STOP_TIMEOUT,
            RuntimeProtectionState.CONTROL_ERROR,
        ):
            return state

        # Transition FAULT_LATCHED → BRAKING: disable autopilot exactly once.
        if state == RuntimeProtectionState.FAULT_LATCHED:
            with self._lock:
                should_disable = not self._autopilot_disabled
            if should_disable:
                try:
                    disable_autopilot(vehicle)
                except Exception as exc:  # noqa: BLE001
                    return self._record_control_action_error(
                        action="set_autopilot(False)",
                        tick_index=tick_index,
                        error=exc,
                    )
                try:
                    detection_speed = self.compute_speed_mps(vehicle.get_velocity())
                except Exception:  # noqa: BLE001
                    detection_speed = math.inf
                with self._lock:
                    self._autopilot_disabled = True
                    self._first_enforcement_tick = tick_index
                    self._speed_at_detection = detection_speed
                    self._state = RuntimeProtectionState.BRAKING

        # Apply braking-only control every enforcement tick.
        try:
            apply_control(vehicle, 0.0, self._cfg.full_brake, 0.0)
        except Exception as exc:  # noqa: BLE001
            return self._record_control_action_error(
                action="apply_control(brake)",
                tick_index=tick_index,
                error=exc,
            )

        # Measure current speed.
        try:
            velocity = vehicle.get_velocity()
            speed = self.compute_speed_mps(velocity)
        except Exception:  # noqa: BLE001
            speed = math.inf

        with self._lock:
            self._braking_ticks += 1
            current_braking_ticks = self._braking_ticks

            if math.isfinite(speed) and speed <= self._cfg.stop_speed_mps:
                self._stopped_ticks += 1
            else:
                # Speed rose above threshold — reset consecutive stopped count.
                self._stopped_ticks = 0

            stopped_ticks = self._stopped_ticks

            # Check confirmed stop (consecutive low-speed ticks).
            if stopped_ticks >= self._cfg.required_stopped_ticks:
                self._final_speed = speed
                self._safe_stop = True
                self._termination_reason = "safe_stop"
                self._state = RuntimeProtectionState.STOPPED
                return RuntimeProtectionState.STOPPED

            # Check braking timeout.
            if current_braking_ticks >= self._cfg.maximum_braking_ticks:
                self._final_speed = speed
                self._safe_stop = False
                self._stop_timeout = True
                self._termination_reason = "stop_timeout"
                self._state = RuntimeProtectionState.STOP_TIMEOUT
                return RuntimeProtectionState.STOP_TIMEOUT

            return self._state

    # ------------------------------------------------------------------
    # Evidence snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> RuntimeProtectionSnapshot:
        """Return an immutable evidence snapshot of all supervisor state."""
        with self._lock:
            return RuntimeProtectionSnapshot(
                state=self._state,
                fault_triggered=self._fault_metadata is not None,
                autopilot_disabled=self._autopilot_disabled,
                braking_ticks=self._braking_ticks,
                speed_at_detection_mps=self._speed_at_detection,
                final_speed_mps=self._final_speed,
                stopped_ticks=self._stopped_ticks,
                safe_stop=self._safe_stop,
                stop_timeout=self._stop_timeout,
                first_enforcement_tick=self._first_enforcement_tick,
                fault_metadata=self._fault_metadata,
                fault_reason=self._fault_reason,
                termination_reason=self._termination_reason,
                control_action_failed=self._control_action_error is not None,
                control_action_error=self._control_action_error,
            )
