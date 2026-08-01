"""
Unit tests for qrtc.carla_harness
==================================
All tests in this module run without a live CARLA simulator.  CARLA-specific
types are replaced with simple fake objects so that the helper functions and
cleanup logic can be exercised in ordinary CI.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from qrtc.carla_harness import (
    DriveResult,
    FrameRecord,
    HarnessConfig,
    _DEFAULT_HOST,
    _DEFAULT_OUTPUT,
    _DEFAULT_PORT,
    _DEFAULT_SPAWN_POINT,
    _DEFAULT_TICKS,
    _DEFAULT_TIMEOUT,
    _DEFAULT_TM_PORT,
    compute_speed_ms,
    pick_blueprint,
    pick_spawn_transform,
    run_drive,
    write_evidence,
)


# ---------------------------------------------------------------------------
# HarnessConfig.from_env
# ---------------------------------------------------------------------------


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "CARLA_HOST",
        "CARLA_PORT",
        "CARLA_TM_PORT",
        "CARLA_TIMEOUT",
        "CARLA_TICKS",
        "CARLA_SPAWN_POINT",
        "CARLA_OUTPUT",
    ):
        monkeypatch.delenv(var, raising=False)

    cfg = HarnessConfig.from_env()
    assert cfg.host == _DEFAULT_HOST
    assert cfg.port == _DEFAULT_PORT
    assert cfg.tm_port == _DEFAULT_TM_PORT
    assert cfg.timeout == _DEFAULT_TIMEOUT
    assert cfg.ticks == _DEFAULT_TICKS
    assert cfg.spawn_point_index == _DEFAULT_SPAWN_POINT
    assert cfg.output_path == Path(_DEFAULT_OUTPUT)


def test_config_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARLA_HOST", "192.168.1.10")
    monkeypatch.setenv("CARLA_PORT", "3000")
    monkeypatch.setenv("CARLA_TM_PORT", "9000")
    monkeypatch.setenv("CARLA_TIMEOUT", "30")
    monkeypatch.setenv("CARLA_TICKS", "50")
    monkeypatch.setenv("CARLA_SPAWN_POINT", "5")
    monkeypatch.setenv("CARLA_OUTPUT", "/tmp/my-result.json")

    cfg = HarnessConfig.from_env()
    assert cfg.host == "192.168.1.10"
    assert cfg.port == 3000
    assert cfg.tm_port == 9000
    assert cfg.timeout == 30.0
    assert cfg.ticks == 50
    assert cfg.spawn_point_index == 5
    assert cfg.output_path == Path("/tmp/my-result.json")


# ---------------------------------------------------------------------------
# pick_blueprint
# ---------------------------------------------------------------------------

class _FakeBlueprintLibrary:
    """Minimal fake blueprint library."""

    def __init__(self, blueprints: list[Any], preferred_id: str | None = None) -> None:
        self._blueprints = blueprints
        self._preferred_id = preferred_id

    def find(self, blueprint_id: str) -> Any | None:
        if blueprint_id == self._preferred_id:
            return next(
                (bp for bp in self._blueprints if bp.id == blueprint_id), None
            )
        return None

    def filter(self, pattern: str) -> list[Any]:
        prefix = pattern.rstrip("*")
        return [bp for bp in self._blueprints if bp.id.startswith(prefix)]


def _make_bp(bp_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=bp_id)


def test_pick_blueprint_returns_preferred_when_present() -> None:
    tesla = _make_bp("vehicle.tesla.model3")
    audi = _make_bp("vehicle.audi.a2")
    lib = _FakeBlueprintLibrary(
        [tesla, audi], preferred_id="vehicle.tesla.model3"
    )
    bp = pick_blueprint(lib)
    assert bp.id == "vehicle.tesla.model3"


def test_pick_blueprint_falls_back_deterministically() -> None:
    audi = _make_bp("vehicle.audi.a2")
    bmw = _make_bp("vehicle.bmw.grandtourer")
    lib = _FakeBlueprintLibrary([bmw, audi], preferred_id=None)
    bp = pick_blueprint(lib)
    # Should pick "vehicle.audi.a2" (alphabetically first)
    assert bp.id == "vehicle.audi.a2"


def test_pick_blueprint_raises_when_no_vehicles() -> None:
    lib = _FakeBlueprintLibrary([], preferred_id=None)
    with pytest.raises(RuntimeError, match="No vehicle blueprints"):
        pick_blueprint(lib)


# ---------------------------------------------------------------------------
# pick_spawn_transform
# ---------------------------------------------------------------------------


def test_pick_spawn_transform_returns_preferred_index() -> None:
    transforms = [SimpleNamespace(name="t0"), SimpleNamespace(name="t1"), SimpleNamespace(name="t2")]
    assert pick_spawn_transform(transforms, 1).name == "t1"


def test_pick_spawn_transform_falls_back_to_zero_on_out_of_range() -> None:
    transforms = [SimpleNamespace(name="t0"), SimpleNamespace(name="t1")]
    assert pick_spawn_transform(transforms, 99).name == "t0"


def test_pick_spawn_transform_returns_none_on_empty() -> None:
    assert pick_spawn_transform([], 0) is None


# ---------------------------------------------------------------------------
# compute_speed_ms
# ---------------------------------------------------------------------------


def test_compute_speed_ms_zero() -> None:
    v = SimpleNamespace(x=0.0, y=0.0, z=0.0)
    assert compute_speed_ms(v) == 0.0


def test_compute_speed_ms_known_value() -> None:
    # 3-4-5 triangle in x/y, z=0
    v = SimpleNamespace(x=3.0, y=4.0, z=0.0)
    assert math.isclose(compute_speed_ms(v), 5.0)


# ---------------------------------------------------------------------------
# write_evidence
# ---------------------------------------------------------------------------


def test_write_evidence_creates_valid_json(tmp_path: Path) -> None:
    result = DriveResult(
        host="127.0.0.1",
        port=2000,
        map_name="Town01",
        vehicle_blueprint="vehicle.tesla.model3",
        ticks_requested=10,
        ticks_completed=10,
        collision_events_total=0,
        records=[
            FrameRecord(tick=0, frame=1, x=1.0, y=2.0, z=0.0, yaw=0.0, speed_ms=3.0, collision_count=0)
        ],
        elapsed_seconds=0.5,
        error=None,
    )
    out = tmp_path / "evidence.json"
    write_evidence(result, out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["map_name"] == "Town01"
    assert data["ticks_completed"] == 10
    assert len(data["records"]) == 1
    assert data["records"][0]["speed_ms"] == 3.0


# ---------------------------------------------------------------------------
# run_drive — no CARLA module
# ---------------------------------------------------------------------------


def test_run_drive_returns_1_when_carla_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_drive must return 1 and print an install hint when carla is absent."""
    # Simulate carla not being importable
    monkeypatch.setitem(sys.modules, "carla", None)  # type: ignore[arg-type]

    cfg = HarnessConfig(
        host="127.0.0.1",
        port=2000,
        tm_port=8000,
        timeout=5.0,
        ticks=10,
        spawn_point_index=0,
        output_path=Path("/tmp/never-written.json"),
    )
    code = run_drive(cfg)
    assert code == 1


# ---------------------------------------------------------------------------
# run_drive — connection failure
# ---------------------------------------------------------------------------


def _make_fake_carla_module(
    connect_raises: Exception | None = None,
    spawn_transforms: list[Any] | None = None,
    spawn_raises: Exception | None = None,
    ticks: int = 5,
) -> MagicMock:
    """
    Build a minimal fake ``carla`` module sufficient to drive run_drive through
    different code paths without a real simulator.
    """
    carla_mod = MagicMock(name="carla")

    # --- Transform ---
    fake_transform = MagicMock()
    fake_transform.location.x = 10.0
    fake_transform.location.y = 20.0
    fake_transform.location.z = 0.0
    fake_transform.rotation.yaw = 45.0
    carla_mod.Transform.return_value = fake_transform

    # --- World ---
    fake_world = MagicMock()
    fake_world.get_map.return_value.name = "Town03"
    fake_world.get_map.return_value.get_spawn_points.return_value = (
        spawn_transforms if spawn_transforms is not None else [fake_transform]
    )
    fake_world.get_settings.return_value = MagicMock()
    tick_counter = [0]

    def _tick() -> int:
        tick_counter[0] += 1
        return tick_counter[0]

    fake_world.tick.side_effect = _tick

    # --- Vehicle ---
    fake_vehicle = MagicMock()
    fake_vehicle.get_transform.return_value = fake_transform
    fake_velocity = MagicMock()
    fake_velocity.x = 3.0
    fake_velocity.y = 4.0
    fake_velocity.z = 0.0
    fake_vehicle.get_velocity.return_value = fake_velocity

    if spawn_raises is not None:
        fake_world.spawn_actor.side_effect = spawn_raises
    else:
        spawn_call_count = [0]

        def _spawn_actor(bp: Any, transform: Any, **kwargs: Any) -> Any:
            spawn_call_count[0] += 1
            # First call = vehicle, subsequent calls = sensor
            return fake_vehicle

        fake_world.spawn_actor.side_effect = _spawn_actor

    # --- Blueprint library ---
    tesla_bp = MagicMock()
    tesla_bp.id = "vehicle.tesla.model3"
    fake_lib = MagicMock()
    fake_lib.find.return_value = tesla_bp
    fake_lib.filter.return_value = [tesla_bp]
    fake_world.get_blueprint_library.return_value = fake_lib

    # --- Client ---
    fake_client = MagicMock()
    if connect_raises is not None:
        fake_client.get_world.side_effect = connect_raises
    else:
        fake_client.get_world.return_value = fake_world
    fake_client.get_trafficmanager.return_value = MagicMock()
    carla_mod.Client.return_value = fake_client

    return carla_mod


def test_run_drive_returns_1_on_connection_failure(tmp_path: Path) -> None:
    cfg = HarnessConfig(
        host="127.0.0.1",
        port=2000,
        tm_port=8000,
        timeout=5.0,
        ticks=5,
        spawn_point_index=0,
        output_path=tmp_path / "result.json",
    )
    fake_carla = _make_fake_carla_module(
        connect_raises=RuntimeError("connection refused")
    )
    with patch("qrtc.carla_harness._import_carla", return_value=fake_carla):
        code = run_drive(cfg)
    assert code == 1


def test_run_drive_returns_1_when_no_spawn_points(tmp_path: Path) -> None:
    cfg = HarnessConfig(
        host="127.0.0.1",
        port=2000,
        tm_port=8000,
        timeout=5.0,
        ticks=5,
        spawn_point_index=0,
        output_path=tmp_path / "result.json",
    )
    fake_carla = _make_fake_carla_module(spawn_transforms=[])
    with patch("qrtc.carla_harness._import_carla", return_value=fake_carla):
        code = run_drive(cfg)
    assert code == 1


def test_run_drive_success_writes_evidence(tmp_path: Path) -> None:
    out = tmp_path / "result.json"
    cfg = HarnessConfig(
        host="127.0.0.1",
        port=2000,
        tm_port=8000,
        timeout=5.0,
        ticks=10,
        spawn_point_index=0,
        output_path=out,
    )
    fake_carla = _make_fake_carla_module()
    with patch("qrtc.carla_harness._import_carla", return_value=fake_carla):
        code = run_drive(cfg)

    assert code == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["ticks_completed"] == 10
    assert data["vehicle_blueprint"] == "vehicle.tesla.model3"
    assert data["map_name"] == "Town03"
    assert data["error"] is None


def test_run_drive_cleanup_always_runs_on_tick_failure(tmp_path: Path) -> None:
    """Even when the tick loop raises, cleanup methods must be called."""
    out = tmp_path / "result.json"
    cfg = HarnessConfig(
        host="127.0.0.1",
        port=2000,
        tm_port=8000,
        timeout=5.0,
        ticks=100,
        spawn_point_index=0,
        output_path=out,
    )
    fake_carla = _make_fake_carla_module()
    # Make world.tick() raise after a couple of ticks
    call_count = [0]

    def _bad_tick() -> int:
        call_count[0] += 1
        if call_count[0] > 2:
            raise RuntimeError("simulator crashed")
        return call_count[0]

    fake_carla.Client.return_value.get_world.return_value.tick.side_effect = _bad_tick

    with patch("qrtc.carla_harness._import_carla", return_value=fake_carla):
        code = run_drive(cfg)

    # Should return 1 (error path) but still write the partial evidence file
    assert code == 1
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["error"] is not None
    assert "tick loop failed" in data["error"]
