from __future__ import annotations

from qrtc.carla_driving import (
    CarlaDrivingConfig,
    evaluate_driving_metrics,
    load_driving_config,
)


def _telemetry(**overrides):
    sample = {
        "speed_mps": 0.5,
        "longitudinal_accel_mps2": 1.0,
        "lateral_accel_mps2": 1.0,
        "on_road": True,
    }
    sample.update(overrides)
    return [sample]


def test_load_driving_config_defaults() -> None:
    config = load_driving_config({})
    assert config.tick_count == 200
    assert config.braking_tick_count == 40
    assert config.target_speed_mps == 6.0
    assert config.traffic_vehicle_count == 3
    assert config.traffic_seed == 450
    assert config.min_route_progress == 0.6


def test_load_driving_config_from_env() -> None:
    config = load_driving_config(
        {
            "QRTC_CARLA_DRIVING_TICK_COUNT": "80",
            "QRTC_CARLA_BRAKING_TICK_COUNT": "20",
            "QRTC_CARLA_TARGET_SPEED_MPS": "4.5",
            "QRTC_CARLA_TRAFFIC_VEHICLE_COUNT": "2",
            "QRTC_CARLA_TRAFFIC_SEED": "123",
            "QRTC_CARLA_MIN_ROUTE_PROGRESS": "0.75",
        }
    )
    assert config.tick_count == 80
    assert config.braking_tick_count == 20
    assert config.target_speed_mps == 4.5
    assert config.traffic_vehicle_count == 2
    assert config.traffic_seed == 123
    assert config.min_route_progress == 0.75


def test_load_driving_config_rejects_invalid_braking_window() -> None:
    try:
        load_driving_config(
            {
                "QRTC_CARLA_DRIVING_TICK_COUNT": "20",
                "QRTC_CARLA_BRAKING_TICK_COUNT": "20",
            }
        )
    except ValueError as error:
        assert "BRAKING_TICK_COUNT" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_evaluate_driving_metrics_passes_valid_run() -> None:
    result = evaluate_driving_metrics(
        _telemetry(),
        collision_count=0,
        route_progress=1.0,
        traffic_requested=2,
        traffic_spawned=2,
        config=CarlaDrivingConfig(),
    )
    assert result["passed"]
    assert all(result["checks"].values())


def test_evaluate_driving_metrics_reports_each_failure() -> None:
    result = evaluate_driving_metrics(
        _telemetry(
            speed_mps=20.0,
            longitudinal_accel_mps2=20.0,
            lateral_accel_mps2=20.0,
            on_road=False,
        ),
        collision_count=1,
        route_progress=0.1,
        traffic_requested=2,
        traffic_spawned=1,
        config=CarlaDrivingConfig(),
    )
    assert not result["passed"]
    assert not any(result["checks"].values())
