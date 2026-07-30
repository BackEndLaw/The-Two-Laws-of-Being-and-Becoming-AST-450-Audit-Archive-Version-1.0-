from __future__ import annotations

import pytest

from qrtc.carla_driving import load_driving_config, run_live_driving_test
from qrtc.carla_live import live_testing_required


@pytest.mark.carla
@pytest.mark.integration
def test_carla_live_driving() -> None:
    carla = pytest.importorskip("carla")
    config = load_driving_config()
    try:
        result = run_live_driving_test(config, carla_module=carla)
    except RuntimeError as error:
        if live_testing_required():
            pytest.fail(f"CARLA live driving testing was requested but failed: {error}")
        pytest.skip(f"CARLA server not reachable for optional live test: {error}")

    assert result["assessment"]["passed"], result["assessment"]["checks"]
    assert result["traffic_spawned"] == config.traffic_vehicle_count
    assert result["route_progress"] >= config.min_route_progress
    assert result["telemetry"][-1]["brake"] == 1.0
