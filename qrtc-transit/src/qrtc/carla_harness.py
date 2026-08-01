"""
qrtc.carla_harness
==================
Optional CARLA autonomous-drive harness for the QRTC-Transit project.

CARLA is an *optional* dependency.  If the ``carla`` Python package is not
installed the module can still be imported; a clear message is printed and
:func:`run_drive` returns a nonzero exit code.

Environment variables (all optional):
  CARLA_HOST         Server hostname  (default: 127.0.0.1)
  CARLA_PORT         Server port      (default: 2000)
  CARLA_TM_PORT      Traffic Manager port (default: 8000)
  CARLA_TIMEOUT      Client timeout in seconds (default: 15)
  CARLA_TICKS        Number of simulation ticks to run (default: 300)
  CARLA_SPAWN_POINT  Preferred spawn-point index (default: 0)
  CARLA_OUTPUT       Path for JSON evidence file
                     (default: carla-live-drive-result.json)
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 2000
_DEFAULT_TM_PORT = 8000
_DEFAULT_TIMEOUT = 15.0
_DEFAULT_TICKS = 300
_DEFAULT_SPAWN_POINT = 0
_DEFAULT_OUTPUT = "carla-live-drive-result.json"

_FIXED_DELTA_SECONDS = 0.05
_PREFERRED_BLUEPRINT = "vehicle.tesla.model3"
_AUTOPILOT_SPEED_KMH = 30.0
_RECORD_EVERY_N_TICKS = 10


@dataclass
class HarnessConfig:
    """All tunable parameters for :func:`run_drive`, drawn from env-vars."""

    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    tm_port: int = _DEFAULT_TM_PORT
    timeout: float = _DEFAULT_TIMEOUT
    ticks: int = _DEFAULT_TICKS
    spawn_point_index: int = _DEFAULT_SPAWN_POINT
    output_path: Path = field(default_factory=lambda: Path(_DEFAULT_OUTPUT))

    @classmethod
    def from_env(cls) -> "HarnessConfig":
        """Build a config from environment variables, falling back to defaults."""
        return cls(
            host=os.environ.get("CARLA_HOST", _DEFAULT_HOST),
            port=int(os.environ.get("CARLA_PORT", _DEFAULT_PORT)),
            tm_port=int(os.environ.get("CARLA_TM_PORT", _DEFAULT_TM_PORT)),
            timeout=float(os.environ.get("CARLA_TIMEOUT", _DEFAULT_TIMEOUT)),
            ticks=int(os.environ.get("CARLA_TICKS", _DEFAULT_TICKS)),
            spawn_point_index=int(
                os.environ.get("CARLA_SPAWN_POINT", _DEFAULT_SPAWN_POINT)
            ),
            output_path=Path(os.environ.get("CARLA_OUTPUT", _DEFAULT_OUTPUT)),
        )


# ---------------------------------------------------------------------------
# Evidence types
# ---------------------------------------------------------------------------


@dataclass
class FrameRecord:
    """One telemetry sample captured during the drive loop."""

    tick: int
    frame: int
    x: float
    y: float
    z: float
    yaw: float
    speed_ms: float
    collision_count: int


@dataclass
class DriveResult:
    """Full evidence emitted by a single harness run."""

    host: str
    port: int
    map_name: str
    vehicle_blueprint: str
    ticks_requested: int
    ticks_completed: int
    collision_events_total: int
    records: list[FrameRecord] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "map_name": self.map_name,
            "vehicle_blueprint": self.vehicle_blueprint,
            "ticks_requested": self.ticks_requested,
            "ticks_completed": self.ticks_completed,
            "collision_events_total": self.collision_events_total,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
            "records": [
                {
                    "tick": r.tick,
                    "frame": r.frame,
                    "x": r.x,
                    "y": r.y,
                    "z": r.z,
                    "yaw": r.yaw,
                    "speed_ms": r.speed_ms,
                    "collision_count": r.collision_count,
                }
                for r in self.records
            ],
        }


# ---------------------------------------------------------------------------
# Helpers (CARLA-independent — unit-testable without a live simulator)
# ---------------------------------------------------------------------------


def pick_blueprint(blueprint_library: Any, preferred: str = _PREFERRED_BLUEPRINT) -> Any:
    """
    Return a blueprint from *blueprint_library*.

    Prefers *preferred*; if absent falls back to the first vehicle blueprint
    sorted deterministically by ``id``.
    """
    preferred_bp = blueprint_library.find(preferred)
    if preferred_bp is not None:
        return preferred_bp

    vehicles = sorted(blueprint_library.filter("vehicle.*"), key=lambda bp: bp.id)
    if not vehicles:
        raise RuntimeError("No vehicle blueprints available in this CARLA world.")
    return vehicles[0]


def pick_spawn_transform(spawn_transforms: list[Any], preferred_index: int) -> Any:
    """
    Return a spawn :class:`carla.Transform` from *spawn_transforms*.

    Tries *preferred_index* first; if out of range falls back to index 0.
    Returns ``None`` when the list is empty.
    """
    if not spawn_transforms:
        return None
    if 0 <= preferred_index < len(spawn_transforms):
        return spawn_transforms[preferred_index]
    return spawn_transforms[0]


def compute_speed_ms(velocity: Any) -> float:
    """Return the scalar speed in m/s from a CARLA ``Vector3D`` velocity."""
    return math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)


def write_evidence(result: DriveResult, output_path: Path) -> None:
    """Serialise *result* to *output_path* as JSON."""
    output_path.write_text(
        json.dumps(result.as_dict(), indent=2, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Core drive loop
# ---------------------------------------------------------------------------


def _import_carla() -> Any:
    """
    Import and return the ``carla`` module.

    Raises :class:`ImportError` with a helpful installation message when the
    package is not available.
    """
    try:
        import carla  # type: ignore[import-untyped]  # noqa: PLC0415

        return carla
    except ImportError as exc:
        raise ImportError(
            "The 'carla' package is not installed.  Install the CARLA Python\n"
            "wheel that ships with your CARLA server, for example:\n\n"
            "  python -m pip install "
            ".\\PythonAPI\\carla\\dist\\<wheel-filename>.whl\n\n"
            "CARLA 0.9.16 ships a CPython 3.12 wheel on Windows.\n"
            "See qrtc-transit/README.md for full instructions."
        ) from exc


def run_drive(config: HarnessConfig | None = None) -> int:
    """
    Execute a bounded CARLA autonomous drive and write JSON evidence.

    Parameters
    ----------
    config:
        If ``None``, :meth:`HarnessConfig.from_env` is called automatically.

    Returns
    -------
    int
        Exit code: 0 on success, nonzero on any failure.
    """
    if config is None:
        config = HarnessConfig.from_env()

    # Lazy import — keeps CARLA optional for normal CI.
    try:
        carla = _import_carla()
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = DriveResult(
        host=config.host,
        port=config.port,
        map_name="",
        vehicle_blueprint="",
        ticks_requested=config.ticks,
        ticks_completed=0,
        collision_events_total=0,
    )

    vehicle = None
    collision_sensor = None
    traffic_manager = None
    world = None
    original_settings = None
    collision_count: list[int] = [0]

    def _on_collision(_event: Any) -> None:  # noqa: ANN401
        collision_count[0] += 1

    start_time = time.monotonic()

    try:
        # --- connection -------------------------------------------------------
        try:
            client = carla.Client(config.host, config.port)
            client.set_timeout(config.timeout)
            world = client.get_world()
        except Exception as exc:
            result.error = f"connection failed: {exc}"
            print(result.error, file=sys.stderr)
            return 1

        # --- world / TM metadata ----------------------------------------------
        carla_map = world.get_map()
        result.map_name = carla_map.name

        blueprint_library = world.get_blueprint_library()
        traffic_manager = client.get_trafficmanager(config.tm_port)
        original_settings = world.get_settings()

        # --- blueprint selection ----------------------------------------------
        try:
            blueprint = pick_blueprint(blueprint_library)
        except RuntimeError as exc:
            result.error = f"blueprint selection failed: {exc}"
            print(result.error, file=sys.stderr)
            return 1

        result.vehicle_blueprint = blueprint.id

        # --- spawn ------------------------------------------------------------
        spawn_transforms = world.get_map().get_spawn_points()
        transform = pick_spawn_transform(spawn_transforms, config.spawn_point_index)
        if transform is None:
            result.error = "no spawn points available in this map"
            print(result.error, file=sys.stderr)
            return 1

        vehicle = None
        for candidate_transform in [transform] + [
            t for t in spawn_transforms if t is not transform
        ]:
            try:
                vehicle = world.spawn_actor(blueprint, candidate_transform)
                break
            except Exception:
                continue

        if vehicle is None:
            result.error = "failed to spawn vehicle at any available spawn point"
            print(result.error, file=sys.stderr)
            return 1

        # --- collision sensor (no camera — minimal GPU usage) -----------------
        sensor_bp = blueprint_library.find("sensor.other.collision")
        collision_sensor = world.spawn_actor(
            sensor_bp, carla.Transform(), attach_to=vehicle
        )
        collision_sensor.listen(_on_collision)

        # --- synchronous mode -------------------------------------------------
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = _FIXED_DELTA_SECONDS
        world.apply_settings(settings)

        traffic_manager.set_synchronous_mode(True)
        traffic_manager.set_global_distance_to_leading_vehicle(2.5)

        # --- autopilot --------------------------------------------------------
        traffic_manager.vehicle_percentage_speed_difference(
            vehicle, 100.0 - _AUTOPILOT_SPEED_KMH / 1.4  # approximate normalisation
        )
        vehicle.set_autopilot(True, config.tm_port)

        # --- tick loop --------------------------------------------------------
        try:
            for tick_index in range(config.ticks):
                frame = world.tick()

                if tick_index % _RECORD_EVERY_N_TICKS == 0:
                    transform_snapshot = vehicle.get_transform()
                    velocity = vehicle.get_velocity()
                    speed = compute_speed_ms(velocity)
                    result.records.append(
                        FrameRecord(
                            tick=tick_index,
                            frame=frame,
                            x=round(transform_snapshot.location.x, 4),
                            y=round(transform_snapshot.location.y, 4),
                            z=round(transform_snapshot.location.z, 4),
                            yaw=round(transform_snapshot.rotation.yaw, 4),
                            speed_ms=round(speed, 4),
                            collision_count=collision_count[0],
                        )
                    )

                result.ticks_completed = tick_index + 1

        except Exception as exc:
            result.error = f"tick loop failed at tick {result.ticks_completed}: {exc}"
            print(result.error, file=sys.stderr)
            # fall through to finally for cleanup, then return 1 below

    finally:
        # --- cleanup (always runs) -------------------------------------------
        if vehicle is not None:
            try:
                vehicle.set_autopilot(False)
            except Exception:
                pass

        if collision_sensor is not None:
            try:
                collision_sensor.stop()
                collision_sensor.destroy()
            except Exception:
                pass

        if vehicle is not None:
            try:
                vehicle.destroy()
            except Exception:
                pass

        if traffic_manager is not None:
            try:
                traffic_manager.set_synchronous_mode(False)
            except Exception:
                pass

        if world is not None and original_settings is not None:
            try:
                world.apply_settings(original_settings)
            except Exception:
                pass

    result.elapsed_seconds = round(time.monotonic() - start_time, 3)
    result.collision_events_total = collision_count[0]

    # --- write evidence -------------------------------------------------------
    try:
        write_evidence(result, config.output_path)
    except OSError as exc:
        print(f"failed to write evidence to {config.output_path}: {exc}", file=sys.stderr)
        return 1

    print(
        f"Drive complete: {result.ticks_completed}/{result.ticks_requested} ticks, "
        f"{result.collision_events_total} collision events, "
        f"evidence written to {config.output_path}",
        file=sys.stdout,
    )

    if result.error is not None:
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """
    Command-line entry point for ``carla-live-drive``.

    All configuration is via environment variables; ``argv`` is accepted for
    future extension but currently unused.
    """
    return run_drive()


if __name__ == "__main__":
    raise SystemExit(main())
