from __future__ import annotations

import math

import pytest

from qrtc.carla_live import live_testing_required, load_live_config, run_live_smoke


@pytest.mark.carla
@pytest.mark.integration
def test_carla_live_smoke() -> None:
    carla = pytest.importorskip("carla")
    config = load_live_config()

    try:
        result = run_live_smoke(config, carla_module=carla)
    except RuntimeError as error:
        if live_testing_required():
            pytest.fail(f"CARLA live testing was requested but failed: {error}")
        pytest.skip(f"CARLA server not reachable for optional live test: {error}")

    assert result["map"]
    assert result["tick_count"] == config.tick_count
    assert len(result["telemetry"]) == config.tick_count
    assert result["final_frame"] > result["initial_frame"]
    assert result["collision_count"] == 0

    for sample in result["telemetry"]:
        assert sample["frame"] >= result["initial_frame"]
        assert math.isfinite(sample["speed_mps"])
