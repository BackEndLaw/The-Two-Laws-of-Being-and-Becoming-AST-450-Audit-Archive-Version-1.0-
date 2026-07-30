from __future__ import annotations

import json

from qrtc import carla_live


def test_load_live_config_defaults() -> None:
    config = carla_live.load_live_config({})
    assert config.host == "120.0.0.1"
    assert config.port == 2000
    assert config.timeout_seconds == 5.0
    assert config.tick_count == 20
    assert config.spawn_point_index == 0
    assert config.fixed_delta_seconds == 0.05
    assert config.vehicle_blueprint_filter == "vehicle.tesla.model3"


def test_load_live_config_from_env() -> None:
    config = carla_live.load_live_config(
        {
            "QRTC_CARLA_HOST": "10.0.0.5",
            "QRTC_CARLA_PORT": "2100",
            "QRTC_CARLA_TIMEOUT_SECONDS": "9.5",
            "QRTC_CARLA_TICK_COUNT": "7",
            "QRTC_CARLA_SPAWN_INDEX": "3",
            "QRTC_CARLA_FIXED_DELTA_SECONDS": "0.1",
            "QRTC_CARLA_VEHICLE_BLUEPRINT": "vehicle.*",
        }
    )
    assert config.host == "10.0.0.5"
    assert config.port == 2100
    assert config.timeout_seconds == 9.5
    assert config.tick_count == 7
    assert config.spawn_point_index == 3
    assert config.fixed_delta_seconds == 0.1
    assert config.vehicle_blueprint_filter == "vehicle.*"


def test_load_live_config_rejects_invalid_values() -> None:
    try:
        carla_live.load_live_config({"QRTC_CARLA_TICK_COUNT": "0"})
    except ValueError as error:
        assert "QRTC_CARLA_TICK_COUNT" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_live_testing_required_flag() -> None:
    assert not carla_live.live_testing_required({})
    assert carla_live.live_testing_required({"QRTC_CARLA_LIVE_REQUIRED": "true"})
    assert carla_live.live_testing_required({"QRTC_CARLA_LIVE_REQUIRED": "1"})
    assert not carla_live.live_testing_required({"QRTC_CARLA_LIVE_REQUIRED": "0"})


def test_smoke_result_json_uses_runner(monkeypatch) -> None:
    def fake_run(config):
        assert config.host == "120.0.0.1"
        return {"ok": True}

    monkeypatch.setattr(carla_live, "run_live_smoke", fake_run)
    result = carla_live.smoke_result_json(carla_live.CarlaLiveConfig())
    assert json.loads(result) == {"ok": True}
