"""
Unit tests for qrtc.carla_harness — actor/sensor cleanup and smoke tests.

All tests use fakes; no real CARLA simulator is required.

A live-marked test skeleton is included for explicit --live runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from qrtc.carla_config import CarlaConfig, LidarConfig
from qrtc.carla_harness import _displacement, _select_blueprint, _transform_snapshot


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_displacement_zero() -> None:
    assert _displacement((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)) == pytest.approx(0.0)


def test_displacement_unit() -> None:
    assert _displacement((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)) == pytest.approx(1.0)


def test_displacement_3d() -> None:
    # 3-4-5
    assert _displacement((0.0, 0.0, 0.0), (3.0, 4.0, 0.0)) == pytest.approx(5.0)


def test_transform_snapshot_computes_speed() -> None:
    transform = MagicMock()
    transform.location.x = 1.0
    transform.location.y = 2.0
    transform.location.z = 3.0
    transform.rotation.pitch = 0.0
    transform.rotation.yaw = 90.0
    transform.rotation.roll = 0.0

    velocity = MagicMock()
    velocity.x = 3.0
    velocity.y = 4.0
    velocity.z = 0.0

    snap = _transform_snapshot(transform, velocity)
    assert snap["speed_mps"] == pytest.approx(5.0)
    assert snap["x"] == pytest.approx(1.0)
    assert snap["yaw"] == pytest.approx(90.0)
    assert snap["vx"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Blueprint selection
# ---------------------------------------------------------------------------


def test_select_blueprint_finds_preferred() -> None:
    preferred_bp = MagicMock()
    preferred_bp.id = "vehicle.tesla.model3"
    library = MagicMock()
    library.find.return_value = preferred_bp

    result = _select_blueprint(library, "vehicle.tesla.model3")
    assert result is preferred_bp


def test_select_blueprint_falls_back_deterministically() -> None:
    bp_a = MagicMock()
    bp_a.id = "vehicle.audi.a2"
    bp_b = MagicMock()
    bp_b.id = "vehicle.bmw.grandtourer"

    library = MagicMock()
    library.find.return_value = None  # preferred not found
    library.filter.return_value = [bp_b, bp_a]  # unsorted

    result = _select_blueprint(library, "vehicle.tesla.model3")
    # Should pick the alphabetically first one
    assert result.id == "vehicle.audi.a2"


def test_select_blueprint_raises_when_no_vehicles() -> None:
    library = MagicMock()
    library.find.return_value = None
    library.filter.return_value = []

    with pytest.raises(RuntimeError, match="No vehicle blueprints"):
        _select_blueprint(library, "vehicle.tesla.model3")


# ---------------------------------------------------------------------------
# Fake CARLA world infrastructure
# ---------------------------------------------------------------------------


def _make_spawn_point() -> MagicMock:
    sp = MagicMock()
    sp.location.x = 0.0
    sp.location.y = 0.0
    sp.location.z = 0.0
    return sp


def _make_ego_vehicle() -> MagicMock:
    ego = MagicMock()
    ego.id = 99
    ego.type_id = "vehicle.tesla.model3"

    # Provide a moving transform for sampling
    transforms = []
    for i in range(400):
        t = MagicMock()
        t.location.x = float(i)
        t.location.y = 0.0
        t.location.z = 0.0
        t.rotation.pitch = 0.0
        t.rotation.yaw = 0.0
        t.rotation.roll = 0.0
        transforms.append(t)

    ego.get_transform.side_effect = transforms + [transforms[-1]] * 100
    v = MagicMock()
    v.x = 5.0
    v.y = 0.0
    v.z = 0.0
    ego.get_velocity.return_value = v
    return ego


def _make_carla_module(ego: MagicMock, tick_count: int = 5) -> MagicMock:
    """Build a fake carla module that simulates a short drive."""
    carla = MagicMock()

    # Location / Transform / etc. return normal MagicMocks
    carla.Transform.return_value = MagicMock()
    carla.Location.return_value = MagicMock()

    # Blueprint library
    blueprint = MagicMock()
    blueprint.id = "vehicle.tesla.model3"
    collision_bp = MagicMock()
    lidar_bp = MagicMock()
    lidar_bp.set_attribute = MagicMock()
    lib = MagicMock()
    lib.find.side_effect = lambda name: (
        blueprint
        if "tesla" in name
        else collision_bp
        if "collision" in name
        else lidar_bp
        if "lidar" in name
        else None
    )
    lib.filter.return_value = [blueprint]

    # Sensors
    collision_sensor = MagicMock()
    collision_sensor.listen = MagicMock()
    collision_sensor.stop = MagicMock()
    collision_sensor.destroy = MagicMock()

    lidar_sensor = MagicMock()
    lidar_sensor.listen = MagicMock()
    lidar_sensor.stop = MagicMock()
    lidar_sensor.destroy = MagicMock()

    # World
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

    # Traffic manager
    tm = MagicMock()

    # Client
    client = MagicMock()
    client.get_client_version.return_value = "0.9.16"
    client.get_server_version.return_value = "0.9.16"
    client.get_world.return_value = world
    client.get_trafficmanager.return_value = tm

    carla.Client.return_value = client
    return carla


# ---------------------------------------------------------------------------
# run_drive smoke test with fakes
# ---------------------------------------------------------------------------


def test_run_drive_completes_and_writes_report(tmp_path: Path) -> None:
    """run_drive should complete successfully using fake CARLA objects."""
    ego = _make_ego_vehicle()
    fake_carla = _make_carla_module(ego, tick_count=5)

    output = str(tmp_path / "test-report.json")
    cfg = CarlaConfig(
        ticks=5,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=False),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive

        report = run_drive(cfg)

    assert report["status"] == "completed"
    assert report["ticks_completed"] == 5
    assert report["map_name"] == "Town01_Fake"
    out = Path(output)
    assert out.exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["status"] == "completed"


def test_run_drive_cleanup_always_called(tmp_path: Path) -> None:
    """Cleanup must run even when tick loop raises an exception."""
    ego = _make_ego_vehicle()
    fake_carla = _make_carla_module(ego, tick_count=5)

    # Make tick raise after 2 ticks
    world = fake_carla.Client.return_value.get_world.return_value
    world.tick.side_effect = [1, 2, RuntimeError("tick failed")]

    output = str(tmp_path / "test-report.json")
    cfg = CarlaConfig(
        ticks=10,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=False),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive

        report = run_drive(cfg)

    # Partial data is retained
    assert report["ticks_completed"] == 2
    # Cleanup was called: set_autopilot(False) and destroy
    ego.set_autopilot.assert_called_with(False)
    ego.destroy.assert_called()


def test_run_drive_lidar_sensor_destroyed_in_cleanup(tmp_path: Path) -> None:
    """The lidar sensor must be stopped and destroyed in cleanup."""
    ego = _make_ego_vehicle()
    fake_carla = _make_carla_module(ego, tick_count=3)

    # Recover spawned sensors from side_effect
    spawned: list[MagicMock] = []

    def tracking_spawn(bp, transform, attach_to=None):
        result = MagicMock()
        result.listen = MagicMock()
        result.stop = MagicMock()
        result.destroy = MagicMock()
        spawned.append(result)
        return result

    fake_carla.Client.return_value.get_world.return_value.spawn_actor.side_effect = (
        tracking_spawn
    )

    output = str(tmp_path / "test-report.json")
    cfg = CarlaConfig(
        ticks=3,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=True),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive

        run_drive(cfg)

    # Both collision and lidar sensors should be destroyed
    for sensor in spawned:
        sensor.stop.assert_called()
        sensor.destroy.assert_called()


def test_run_drive_restores_world_settings(tmp_path: Path) -> None:
    """Original world settings must be restored in finally block."""
    ego = _make_ego_vehicle()
    fake_carla = _make_carla_module(ego, tick_count=3)

    world = fake_carla.Client.return_value.get_world.return_value
    original_settings = world.get_settings.return_value

    output = str(tmp_path / "test-report.json")
    cfg = CarlaConfig(
        ticks=3,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=False),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive

        run_drive(cfg)

    # apply_settings should be called at least twice:
    # once with synchronous mode settings, once to restore
    assert world.apply_settings.call_count >= 2
    # The last call should restore original settings
    world.apply_settings.assert_called_with(original_settings)


def test_run_drive_connection_failure_raises_system_exit(tmp_path: Path) -> None:
    """Connection failures should result in SystemExit(2)."""
    fake_carla = MagicMock()
    fake_carla.Client.side_effect = RuntimeError("connection refused")

    output = str(tmp_path / "test-report.json")
    cfg = CarlaConfig(
        ticks=5,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=False),
    )

    with patch("qrtc.carla_harness._require_carla", return_value=fake_carla):
        from qrtc.carla_harness import run_drive

        with pytest.raises(SystemExit) as exc_info:
            run_drive(cfg)
    assert exc_info.value.code == 2


def test_require_carla_raises_import_error_when_missing() -> None:
    """_require_carla must raise ImportError with guidance if carla is absent."""
    import builtins

    original_import = builtins.__import__

    def patched_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "carla":
            raise ImportError("No module named 'carla'")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=patched_import):
        from qrtc.carla_harness import _require_carla

        with pytest.raises(ImportError, match="CARLA Python API"):
            _require_carla()


def test_main_returns_zero_on_success(tmp_path: Path) -> None:
    """main() should return 0 when run_drive succeeds."""
    ego = _make_ego_vehicle()
    fake_carla = _make_carla_module(ego, tick_count=3)

    output = str(tmp_path / "test-report.json")

    with (
        patch("qrtc.carla_harness._require_carla", return_value=fake_carla),
        patch.dict(
            "os.environ",
            {
                "CARLA_TICKS": "3",
                "CARLA_OUTPUT": output,
                "CARLA_LIDAR_ENABLED": "false",
            },
        ),
    ):
        from qrtc.carla_harness import main

        code = main()

    assert code == 0


def test_main_returns_nonzero_on_config_error() -> None:
    with patch.dict("os.environ", {"CARLA_PORT": "0"}):
        from qrtc.carla_harness import main

        code = main()
    assert code != 0


# ---------------------------------------------------------------------------
# Live test placeholder (excluded unless --live is passed)
# ---------------------------------------------------------------------------


@pytest.mark.live
def test_live_carla_drive(tmp_path: Path) -> None:
    """
    Opt-in live test: requires a running CARLA server on 127.0.0.1:2000.

    Run with: pytest tests/test_carla_harness.py --live

    This test is automatically skipped during ordinary CI runs.
    CARLA must be installed (carla 0.9.16 cp312 wheel).
    """
    pytest.importorskip("carla", reason="carla package is not installed")

    output = str(tmp_path / "live-report.json")
    cfg = CarlaConfig(
        ticks=50,
        output=output,
        submit_to_qrtc=False,
        lidar=LidarConfig(enabled=True, channels=8, points_per_second=14_000),
    )

    from qrtc.carla_harness import run_drive

    report = run_drive(cfg)

    assert report["status"] == "completed"
    assert report["ticks_completed"] > 0
    assert Path(output).exists()
