"""Unit tests for qrtc.carla_lidar — lidar processing and evidence."""
from __future__ import annotations

import math
import threading
import time
from unittest.mock import MagicMock

import pytest

from qrtc.carla_lidar import (
    LidarCollector,
    LidarFrameEvidence,
    build_lidar_summary,
    compute_speed_mps,
    process_lidar_points,
)


# ---------------------------------------------------------------------------
# Speed calculation
# ---------------------------------------------------------------------------

def test_speed_zero_velocity() -> None:
    assert compute_speed_mps(0.0, 0.0, 0.0) == pytest.approx(0.0)


def test_speed_unit_forward() -> None:
    assert compute_speed_mps(1.0, 0.0, 0.0) == pytest.approx(1.0)


def test_speed_3d() -> None:
    # 3-4-5 right triangle
    assert compute_speed_mps(3.0, 4.0, 0.0) == pytest.approx(5.0)


def test_speed_pythagoras_3d() -> None:
    assert compute_speed_mps(1.0, 1.0, 1.0) == pytest.approx(math.sqrt(3.0))


# ---------------------------------------------------------------------------
# Empty scan
# ---------------------------------------------------------------------------

def test_empty_lidar_scan_produces_none_stats() -> None:
    ev = process_lidar_points([])
    assert ev.point_count == 0
    assert ev.finite_count == 0
    assert ev.invalid_count == 0
    assert ev.range_min is None
    assert ev.range_max is None
    assert ev.range_mean is None
    assert ev.range_p10 is None
    assert ev.range_p50 is None
    assert ev.range_p90 is None
    assert ev.nearest_overall is None
    assert ev.nearest_front is None
    for sector in ("front", "rear", "left", "right"):
        assert ev.sector_counts[sector] == 0
        assert ev.sector_nearest[sector] is None


# ---------------------------------------------------------------------------
# Non-finite / malformed samples
# ---------------------------------------------------------------------------

def test_all_non_finite_points_counted_as_invalid() -> None:
    points = [
        (float("nan"), 0.0, 0.0),
        (float("inf"), 0.0, 0.0),
        (0.0, float("-inf"), 0.0),
        (float("nan"), float("nan"), float("nan")),
    ]
    ev = process_lidar_points(points)
    assert ev.point_count == 4
    assert ev.invalid_count == 4
    assert ev.finite_count == 0
    assert ev.nearest_overall is None


def test_mixed_finite_and_non_finite() -> None:
    points = [
        (5.0, 0.0, 0.0),        # finite, front, r=5
        (float("nan"), 0.0, 0.0),  # invalid
        (0.0, -3.0, 0.0),       # finite, right, r=3
    ]
    ev = process_lidar_points(points)
    assert ev.point_count == 3
    assert ev.invalid_count == 1
    assert ev.finite_count == 2
    assert ev.nearest_overall == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Statistical correctness
# ---------------------------------------------------------------------------

def test_single_point_statistics() -> None:
    ev = process_lidar_points([(10.0, 0.0, 0.0)])
    assert ev.range_min == pytest.approx(10.0)
    assert ev.range_max == pytest.approx(10.0)
    assert ev.range_mean == pytest.approx(10.0)
    assert ev.range_p50 == pytest.approx(10.0)
    assert ev.nearest_front == pytest.approx(10.0)


def test_two_points_mean_and_percentiles() -> None:
    # Two points directly forward at 2m and 8m
    ev = process_lidar_points([(2.0, 0.0, 0.0), (8.0, 0.0, 0.0)])
    assert ev.range_mean == pytest.approx(5.0)
    assert ev.range_min == pytest.approx(2.0)
    assert ev.range_max == pytest.approx(8.0)
    # p50 of [2, 8] = 5.0
    assert ev.range_p50 == pytest.approx(5.0)


def test_range_min_is_nearest_overall() -> None:
    points = [(1.0, 0.0, 0.0), (10.0, 0.0, 0.0), (5.0, 0.0, 0.0)]
    ev = process_lidar_points(points)
    assert ev.nearest_overall == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Sector assignment
# ---------------------------------------------------------------------------

def test_forward_points_go_to_front_sector() -> None:
    ev = process_lidar_points([(5.0, 0.0, 0.0)])
    assert ev.sector_counts["front"] == 1
    assert ev.sector_counts["rear"] == 0


def test_negative_x_goes_to_rear_sector() -> None:
    ev = process_lidar_points([(-5.0, 0.0, 0.0)])
    assert ev.sector_counts["rear"] == 1


def test_positive_y_goes_to_left_sector() -> None:
    # x=0, y positive → atan2(y,x) = 90° → left
    ev = process_lidar_points([(0.0, 5.0, 0.0)])
    assert ev.sector_counts["left"] == 1


def test_negative_y_goes_to_right_sector() -> None:
    # x=0, y negative → atan2(-y,x) = -90° → right
    ev = process_lidar_points([(0.0, -5.0, 0.0)])
    assert ev.sector_counts["right"] == 1


def test_sector_nearest_is_minimum_in_sector() -> None:
    points = [(10.0, 0.0, 0.0), (3.0, 0.0, 0.0), (7.0, 0.0, 0.0)]
    ev = process_lidar_points(points)
    assert ev.sector_nearest["front"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Frame metadata
# ---------------------------------------------------------------------------

def test_frame_and_timestamp_are_preserved() -> None:
    ev = process_lidar_points([(1.0, 0.0, 0.0)], frame=42, timestamp=3.14)
    assert ev.frame == 42
    assert ev.timestamp == pytest.approx(3.14)


def test_none_frame_and_timestamp_are_preserved() -> None:
    ev = process_lidar_points([(1.0, 0.0, 0.0)], frame=None, timestamp=None)
    assert ev.frame is None
    assert ev.timestamp is None


# ---------------------------------------------------------------------------
# as_dict completeness
# ---------------------------------------------------------------------------

def test_lidar_frame_evidence_as_dict_has_all_keys() -> None:
    ev = process_lidar_points([(1.0, 0.0, 0.0)], frame=1, timestamp=0.1)
    d = ev.as_dict()
    for key in (
        "frame", "timestamp", "point_count", "finite_count", "invalid_count",
        "range_min", "range_max", "range_mean",
        "range_p10", "range_p50", "range_p90",
        "nearest_overall", "nearest_front",
        "sector_counts", "sector_nearest",
    ):
        assert key in d, f"missing key: {key}"


# ---------------------------------------------------------------------------
# Collector — thread-safe on_data via fake measurement
# ---------------------------------------------------------------------------

def _make_fake_measurement(
    points: list[tuple[float, float, float]],
    frame: int = 1,
    timestamp: float = 0.1,
) -> MagicMock:
    """Build a fake carla.LidarMeasurement-like object."""
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


def test_collector_on_data_accumulates_evidence() -> None:
    collector = LidarCollector()
    m = _make_fake_measurement([(5.0, 0.0, 0.0), (3.0, 0.0, 0.0)], frame=10)
    collector.on_data(m)
    frames, dropped, errors = collector.snapshot()
    assert len(frames) == 1
    assert frames[0].point_count == 2
    assert frames[0].frame == 10
    assert dropped == 0
    assert errors == 0


def test_collector_handles_callback_error_gracefully() -> None:
    collector = LidarCollector()
    bad = MagicMock()
    bad.frame = 1
    bad.timestamp = 0.1
    bad.__iter__ = MagicMock(side_effect=RuntimeError("sensor exploded"))
    collector.on_data(bad)
    _, _, errors = collector.snapshot()
    assert errors == 1


def test_collector_snapshot_is_thread_safe() -> None:
    collector = LidarCollector()
    results: list[Exception] = []

    def writer(n: int) -> None:
        try:
            for i in range(n):
                m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
                collector.on_data(m)
        except Exception as exc:  # noqa: BLE001
            results.append(exc)

    threads = [threading.Thread(target=writer, args=(20,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not results
    frames, _, _ = collector.snapshot()
    assert len(frames) == 80  # 4 threads × 20 frames each


def test_collector_retain_raw_bounded() -> None:
    collector = LidarCollector(retain_raw=True, max_raw_frames=3)
    for i in range(10):
        m = _make_fake_measurement([(float(i), 0.0, 0.0)], frame=i)
        collector.on_data(m)
    # 10 compact frames stored
    frames, _, _ = collector.snapshot()
    assert len(frames) == 10
    # raw buffer is bounded to 3
    assert len(collector._raw_buffer) == 3


def test_collector_record_drop() -> None:
    collector = LidarCollector()
    collector.record_drop()
    collector.record_drop()
    _, dropped, _ = collector.snapshot()
    assert dropped == 2


# ---------------------------------------------------------------------------
# Build lidar summary
# ---------------------------------------------------------------------------

def test_lidar_summary_empty() -> None:
    summary = build_lidar_summary([], 0, 0)
    assert summary.frames_received == 0
    assert summary.nearest_obstacle_overall is None
    assert summary.nearest_obstacle_front is None
    assert summary.mean_nearest_front is None


def test_lidar_summary_computes_nearest() -> None:
    f1 = process_lidar_points([(10.0, 0.0, 0.0)], frame=1)
    f2 = process_lidar_points([(3.0, 0.0, 0.0)], frame=2)
    summary = build_lidar_summary([f1, f2], dropped=1, callback_errors=0)
    assert summary.nearest_obstacle_overall == pytest.approx(3.0)
    assert summary.nearest_obstacle_front == pytest.approx(3.0)
    assert summary.frames_dropped == 1
    assert summary.frames_received == 2


def test_lidar_summary_mean_nearest_front() -> None:
    f1 = process_lidar_points([(4.0, 0.0, 0.0)], frame=1)   # nearest_front=4
    f2 = process_lidar_points([(8.0, 0.0, 0.0)], frame=2)   # nearest_front=8
    summary = build_lidar_summary([f1, f2], 0, 0)
    assert summary.mean_nearest_front == pytest.approx(6.0)


def test_lidar_summary_as_dict_complete() -> None:
    summary = build_lidar_summary([], 0, 0)
    d = summary.as_dict()
    for key in (
        "frames_received", "frames_dropped", "callback_errors",
        "total_points", "total_invalid",
        "nearest_obstacle_overall", "nearest_obstacle_front", "mean_nearest_front",
    ):
        assert key in d, f"missing key: {key}"
