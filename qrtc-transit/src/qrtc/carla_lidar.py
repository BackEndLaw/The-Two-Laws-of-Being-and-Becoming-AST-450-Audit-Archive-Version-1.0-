"""
CARLA live-drive harness — lidar callback processing.

Processes sensor.lidar.ray_cast callbacks without retaining unbounded raw
point-clouds. Derives compact evidence safe for long-running drives.

Thread-safety: LidarCollector.on_data is called from the CARLA sensor
callback thread; all shared state is protected by a threading.Lock.
"""
from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


# ---------------------------------------------------------------------------
# Sector helpers
# ---------------------------------------------------------------------------

# CARLA lidar point x=forward, y=left, z=up (right-hand, z-up).
# We split the horizontal plane into four quadrants.

def _azimuth_sector(x: float, y: float) -> str:
    """Return cardinal sector for a lidar point (x=forward, y=left)."""
    angle = math.degrees(math.atan2(y, x))
    # Normalise to [0, 360)
    angle = angle % 360.0
    if angle <= 45.0 or angle > 315.0:
        return "front"
    if 45.0 < angle <= 135.0:
        return "left"
    if 135.0 < angle <= 225.0:
        return "rear"
    return "right"


# ---------------------------------------------------------------------------
# Compact lidar evidence per frame
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LidarFrameEvidence:
    frame: int | None
    timestamp: float | None
    point_count: int
    finite_count: int
    invalid_count: int
    range_min: float | None
    range_max: float | None
    range_mean: float | None
    range_p10: float | None
    range_p50: float | None
    range_p90: float | None
    nearest_overall: float | None
    nearest_front: float | None
    sector_counts: dict[str, int]
    sector_nearest: dict[str, float | None]

    def as_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "timestamp": self.timestamp,
            "point_count": self.point_count,
            "finite_count": self.finite_count,
            "invalid_count": self.invalid_count,
            "range_min": self.range_min,
            "range_max": self.range_max,
            "range_mean": self.range_mean,
            "range_p10": self.range_p10,
            "range_p50": self.range_p50,
            "range_p90": self.range_p90,
            "nearest_overall": self.nearest_overall,
            "nearest_front": self.nearest_front,
            "sector_counts": self.sector_counts,
            "sector_nearest": self.sector_nearest,
        }


# ---------------------------------------------------------------------------
# Per-frame processing (pure, testable without CARLA)
# ---------------------------------------------------------------------------

_SECTORS = ("front", "rear", "left", "right")


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """Return the pct-th percentile (0–100) of a sorted list."""
    n = len(sorted_values)
    if n == 0:
        return None
    idx = pct / 100.0 * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def compute_speed_mps(velocity_x: float, velocity_y: float, velocity_z: float) -> float:
    """Return 3-D speed in m/s from velocity components."""
    return math.sqrt(velocity_x ** 2 + velocity_y ** 2 + velocity_z ** 2)


def process_lidar_points(
    raw_points: list[tuple[float, float, float]],
    frame: int | None = None,
    timestamp: float | None = None,
) -> LidarFrameEvidence:
    """
    Derive compact evidence from a list of (x, y, z) lidar points.

    Does not retain the raw points; input is consumed once and discarded.
    Handles empty scans and non-finite samples honestly.
    """
    total = len(raw_points)
    finite_ranges: list[float] = []
    invalid_count = 0

    sector_ranges: dict[str, list[float]] = {s: [] for s in _SECTORS}

    for x, y, z in raw_points:
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            invalid_count += 1
            continue
        r = math.sqrt(x * x + y * y + z * z)
        if not math.isfinite(r) or r < 0:
            invalid_count += 1
            continue
        finite_ranges.append(r)
        sector = _azimuth_sector(x, y)
        sector_ranges[sector].append(r)

    finite_ranges.sort()

    range_min: float | None = finite_ranges[0] if finite_ranges else None
    range_max: float | None = finite_ranges[-1] if finite_ranges else None
    range_mean: float | None = (
        sum(finite_ranges) / len(finite_ranges) if finite_ranges else None
    )

    sector_counts = {s: len(sector_ranges[s]) for s in _SECTORS}
    sector_nearest: dict[str, float | None] = {
        s: (min(sector_ranges[s]) if sector_ranges[s] else None) for s in _SECTORS
    }

    return LidarFrameEvidence(
        frame=frame,
        timestamp=timestamp,
        point_count=total,
        finite_count=len(finite_ranges),
        invalid_count=invalid_count,
        range_min=range_min,
        range_max=range_max,
        range_mean=range_mean,
        range_p10=_percentile(finite_ranges, 10),
        range_p50=_percentile(finite_ranges, 50),
        range_p90=_percentile(finite_ranges, 90),
        nearest_overall=range_min,
        nearest_front=sector_nearest.get("front"),
        sector_counts=sector_counts,
        sector_nearest=sector_nearest,
    )


# ---------------------------------------------------------------------------
# Named immutable snapshot from LidarCollector
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LidarCollectorSnapshot:
    """
    Immutable, thread-safe snapshot of LidarCollector state.

    All callback indices below are zero-based.

    ``accepted_frames`` is a copy of retained compact evidence (injected-drop
    callback excluded).
    ``natural_drops`` counts drops recorded via :meth:`LidarCollector.record_drop`
    (i.e. external/observed drops), not the injected one.
    ``injected_drops`` is 1 when fault injection triggered, 0 otherwise.
    ``fault_injection_enabled`` is ``True`` when ``drop_frame_index >= 0``.
    ``fault_injection_triggered`` is ``True`` when the configured callback was
    actually reached and discarded.
    ``requested_callback_index`` is the zero-based index requested for injection
    (``None`` when disabled).
    ``triggered_callback_index`` is the zero-based index at which injection fired
    (``None`` when not triggered).
    ``triggered_sensor_frame`` is the CARLA sensor frame number at injection
    (``None`` when not triggered).
    """
    callbacks_received: int
    accepted_frames: tuple[LidarFrameEvidence, ...]
    natural_drops: int
    injected_drops: int
    callback_errors: int
    fault_injection_enabled: bool
    fault_injection_triggered: bool
    requested_callback_index: Optional[int]
    triggered_callback_index: Optional[int]
    triggered_sensor_frame: Optional[int]


# ---------------------------------------------------------------------------
# Collector — integrates with CARLA sensor callback
# ---------------------------------------------------------------------------

@dataclass
class LidarCollector:
    """
    Thread-safe collector for lidar callbacks.

    Attach with::

        sensor.listen(collector.on_data)

    Only compact evidence is retained; raw point clouds are discarded unless
    ``retain_raw=True`` and bounded by ``max_raw_frames``.

    ``drop_frame_index`` is a TEST-ONLY fault-injection parameter.  When set
    to a nonnegative integer, the callback at that zero-based index is
    intentionally discarded (``_injected_drops`` is incremented once) without
    processing or retaining the measurement.  Natural drops recorded via
    :meth:`record_drop` are tracked separately in ``_natural_drops``.  The
    default of ``-1`` disables fault injection entirely.
    """
    retain_raw: bool = False
    max_raw_frames: int = 10
    # TEST-ONLY fault injection.  -1 = disabled.
    drop_frame_index: int = -1
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _frames: list[LidarFrameEvidence] = field(default_factory=list, init=False, repr=False)
    _raw_buffer: deque[list[tuple[float, float, float]]] = field(
        default_factory=lambda: deque(maxlen=10), init=False, repr=False
    )
    _natural_drops: int = field(default=0, init=False, repr=False)
    _injected_drops: int = field(default=0, init=False, repr=False)
    _callback_errors: int = field(default=0, init=False, repr=False)
    _callback_counter: int = field(default=0, init=False, repr=False)
    _fault_injection_triggered: bool = field(default=False, init=False, repr=False)
    _triggered_callback_index: Optional[int] = field(default=None, init=False, repr=False)
    _triggered_sensor_frame: Optional[int] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        # Enforce max_raw_frames on the deque
        self._raw_buffer = deque(maxlen=self.max_raw_frames)

    def on_data(self, measurement: Any) -> None:  # noqa: ANN401
        """CARLA sensor callback — called from sensor thread."""
        # Atomically claim a zero-based callback index.  Also apply fault
        # injection when the index matches the configured drop target.
        with self._lock:
            callback_idx = self._callback_counter
            self._callback_counter += 1
            if self.drop_frame_index >= 0 and callback_idx == self.drop_frame_index:
                self._injected_drops += 1
                self._fault_injection_triggered = True
                self._triggered_callback_index = callback_idx
                # Capture the sensor frame number before discarding.
                self._triggered_sensor_frame = getattr(measurement, "frame", None)
                return

        try:
            # Lazily import carla so ordinary tests never require the package.
            frame: int | None = getattr(measurement, "frame", None)
            timestamp: float | None = getattr(measurement, "timestamp", None)
            # Extract points: CARLA LidarMeasurement is iterable over
            # carla.LidarDetection with attributes x, y, z.
            raw: list[tuple[float, float, float]] = [
                (float(p.point.x), float(p.point.y), float(p.point.z))
                for p in measurement
            ]
        except Exception:  # noqa: BLE001
            with self._lock:
                self._callback_errors += 1
            return

        evidence = process_lidar_points(raw, frame=frame, timestamp=timestamp)
        with self._lock:
            self._frames.append(evidence)
            if self.retain_raw:
                self._raw_buffer.append(raw)

    def snapshot(self) -> LidarCollectorSnapshot:
        """Return an immutable snapshot of all collector state under lock."""
        with self._lock:
            return LidarCollectorSnapshot(
                callbacks_received=self._callback_counter,
                accepted_frames=tuple(self._frames),
                natural_drops=self._natural_drops,
                injected_drops=self._injected_drops,
                callback_errors=self._callback_errors,
                fault_injection_enabled=self.drop_frame_index >= 0,
                fault_injection_triggered=self._fault_injection_triggered,
                requested_callback_index=(
                    self.drop_frame_index if self.drop_frame_index >= 0 else None
                ),
                triggered_callback_index=self._triggered_callback_index,
                triggered_sensor_frame=self._triggered_sensor_frame,
            )

    def record_drop(self) -> None:
        """Increment the natural-drop counter (external/observed drops only)."""
        with self._lock:
            self._natural_drops += 1


# ---------------------------------------------------------------------------
# Aggregate lidar health summary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LidarSummary:
    frames_received: int
    frames_dropped: int
    natural_drops: int
    injected_drops: int
    callback_errors: int
    total_points: int
    total_invalid: int
    nearest_obstacle_overall: float | None
    nearest_obstacle_front: float | None
    mean_nearest_front: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "frames_received": self.frames_received,
            "frames_dropped": self.frames_dropped,
            "natural_drops": self.natural_drops,
            "injected_drops": self.injected_drops,
            "callback_errors": self.callback_errors,
            "total_points": self.total_points,
            "total_invalid": self.total_invalid,
            "nearest_obstacle_overall": self.nearest_obstacle_overall,
            "nearest_obstacle_front": self.nearest_obstacle_front,
            "mean_nearest_front": self.mean_nearest_front,
        }


def build_lidar_summary(
    frames: Sequence[LidarFrameEvidence],
    natural_drops: int,
    injected_drops: int,
    callback_errors: int,
) -> LidarSummary:
    total_points = sum(f.point_count for f in frames)
    total_invalid = sum(f.invalid_count for f in frames)

    nearest_overall: float | None = None
    nearest_front: float | None = None
    front_nearest_values: list[float] = []

    for frm in frames:
        if frm.nearest_overall is not None:
            if nearest_overall is None or frm.nearest_overall < nearest_overall:
                nearest_overall = frm.nearest_overall
        if frm.nearest_front is not None:
            front_nearest_values.append(frm.nearest_front)
            if nearest_front is None or frm.nearest_front < nearest_front:
                nearest_front = frm.nearest_front

    mean_nearest_front: float | None = (
        sum(front_nearest_values) / len(front_nearest_values)
        if front_nearest_values
        else None
    )

    return LidarSummary(
        frames_received=len(frames),
        frames_dropped=natural_drops + injected_drops,
        natural_drops=natural_drops,
        injected_drops=injected_drops,
        callback_errors=callback_errors,
        total_points=total_points,
        total_invalid=total_invalid,
        nearest_obstacle_overall=nearest_overall,
        nearest_obstacle_front=nearest_front,
        mean_nearest_front=mean_nearest_front,
    )
