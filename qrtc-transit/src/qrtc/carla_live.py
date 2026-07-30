from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CarlaLiveConfig:
    host: str = "127.0.0.1"
    port: int = 2000
    timeout_seconds: float = 5.0
    tick_count: int = 20
    spawn_point_index: int = 0
    fixed_delta_seconds: float = 0.05
    vehicle_blueprint_filter: str = "vehicle.tesla.model3"


def _env_int(
    env: dict[str, str], name: str, default: int, minimum: int | None = None
) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    value = int(raw)
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _env_float(
    env: dict[str, str], name: str, default: float, minimum: float | None = None
) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    value = float(raw)
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _env_bool(env: dict[str, str], name: str, default: bool = False) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def live_testing_required(env: dict[str, str] | None = None) -> bool:
    values = dict(os.environ if env is None else env)
    return _env_bool(values, "QRTC_CARLA_LIVE_REQUIRED", default=False)


def load_live_config(env: dict[str, str] | None = None) -> CarlaLiveConfig:
    values = dict(os.environ if env is None else env)
    return CarlaLiveConfig(
        host=values.get("QRTC_CARLA_HOST", "127.0.0.1"),
        port=_env_int(values, "QRTC_CARLA_PORT", 2000, minimum=1),
        timeout_seconds=_env_float(
            values, "QRTC_CARLA_TIMEOUT_SECONDS", 5.0, minimum=0.1
        ),
        tick_count=_env_int(values, "QRTC_CARLA_TICK_COUNT", 20, minimum=1),
        spawn_point_index=_env_int(values, "QRTC_CARLA_SPAWN_INDEX", 0, minimum=0),
        fixed_delta_seconds=_env_float(
            values, "QRTC_CARLA_FIXED_DELTA_SECONDS", 0.05, minimum=0.001
        ),
        vehicle_blueprint_filter=values.get(
            "QRTC_CARLA_VEHICLE_BLUEPRINT", "vehicle.tesla.model3"
        ),
    )


def _restore_world_settings(
    world: Any, *, synchronous_mode: bool, fixed_delta_seconds: float | None
) -> None:
    restore_settings = world.get_settings()
    restore_settings.synchronous_mode = synchronous_mode
    restore_settings.fixed_delta_seconds = fixed_delta_seconds
    world.apply_settings(restore_settings)


def run_live_smoke(config: CarlaLiveConfig, carla_module: Any | None = None) -> dict[str, Any]:
    carla = carla_module
    if carla is None:
        import carla as imported_carla  # type: ignore[import-not-found]

        carla = imported_carla

    client = carla.Client(config.host, config.port)
    client.set_timeout(config.timeout_seconds)

    world: Any | None = None
    original_sync_mode = False
    original_fixed_delta_seconds: float | None = None
    actors: list[Any] = []
    collisions: list[int] = []
    telemetry: list[dict[str, Any]] = []

    try:
        try:
            world = client.get_world()
            world_map = world.get_map()
            initial_snapshot = world.get_snapshot()
        except Exception as error:
            raise RuntimeError(
                f"unable to connect to CARLA at {config.host}:{config.port} "
                f"within {config.timeout_seconds:.1f}s ({error})"
            ) from error

        original_settings = world.get_settings()
        original_sync_mode = bool(original_settings.synchronous_mode)
        original_fixed_delta_seconds = original_settings.fixed_delta_seconds

        sync_settings = world.get_settings()
        sync_settings.synchronous_mode = True
        sync_settings.fixed_delta_seconds = config.fixed_delta_seconds
        world.apply_settings(sync_settings)

        spawn_points = world_map.get_spawn_points()
        if not spawn_points:
            raise RuntimeError("no CARLA spawn points available on the current map")

        blueprints = world.get_blueprint_library().filter(
            config.vehicle_blueprint_filter
        )
        if not blueprints:
            raise RuntimeError(
                f"no vehicle blueprint matched '{config.vehicle_blueprint_filter}'"
            )
        blueprint = min(blueprints, key=lambda bp: bp.id)

        spawn_index = config.spawn_point_index % len(spawn_points)
        spawn_point = spawn_points[spawn_index]
        ego_vehicle = world.try_spawn_actor(blueprint, spawn_point)
        if ego_vehicle is None:
            raise RuntimeError(
                "unable to spawn ego vehicle at "
                f"index {spawn_index} ({config.vehicle_blueprint_filter})"
            )
        actors.append(ego_vehicle)
        ego_vehicle.set_autopilot(False)

        collision_blueprint = world.get_blueprint_library().find("sensor.other.collision")
        collision_sensor = world.spawn_actor(
            collision_blueprint,
            carla.Transform(),
            attach_to=ego_vehicle,
        )
        actors.append(collision_sensor)
        collision_sensor.listen(lambda event: collisions.append(int(event.frame)))

        for _ in range(config.tick_count):
            ego_vehicle.apply_control(carla.VehicleControl(throttle=0.2, steer=0.0, brake=0.0))
            world.tick()
            snapshot = world.get_snapshot()
            transform = ego_vehicle.get_transform()
            velocity = ego_vehicle.get_velocity()
            speed_mps = math.sqrt(
                velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z
            )
            telemetry.append(
                {
                    "frame": int(snapshot.frame),
                    "x": float(transform.location.x),
                    "y": float(transform.location.y),
                    "z": float(transform.location.z),
                    "yaw": float(transform.rotation.yaw),
                    "speed_mps": float(speed_mps),
                    "collision_count": len(collisions),
                }
            )

        return {
            "host": config.host,
            "port": config.port,
            "map": world_map.name,
            "initial_frame": int(initial_snapshot.frame),
            "final_frame": int(telemetry[-1]["frame"]) if telemetry else int(initial_snapshot.frame),
            "tick_count": config.tick_count,
            "spawn_point_index": spawn_index,
            "vehicle_blueprint": blueprint.id,
            "collision_count": len(collisions),
            "collisions": collisions,
            "telemetry": telemetry,
        }
    finally:
        for actor in reversed(actors):
            if actor is None:
                continue
            try:
                stop = getattr(actor, "stop", None)
                if callable(stop):
                    stop()
            except RuntimeError:
                pass
            try:
                actor.destroy()
            except RuntimeError:
                pass

        if world is not None:
            _restore_world_settings(
                world,
                synchronous_mode=original_sync_mode,
                fixed_delta_seconds=original_fixed_delta_seconds,
            )


def smoke_result_json(config: CarlaLiveConfig | None = None) -> str:
    result = run_live_smoke(config or load_live_config())
    return json.dumps(result, indent=2, sort_keys=True)
