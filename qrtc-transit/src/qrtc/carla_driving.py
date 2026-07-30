from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any

from qrtc.carla_live import CarlaLiveConfig, _restore_world_settings


@dataclass(frozen=True)
class CarlaDrivingConfig(CarlaLiveConfig):
    tick_count: int = 200
    braking_tick_count: int = 40
    target_speed_mps: float = 6.0
    route_spacing_m: float = 2.0
    route_waypoint_count: int = 25
    traffic_vehicle_count: int = 3
    traffic_manager_port: int = 8000
    traffic_seed: int = 450
    waypoint_tolerance_m: float = 3.0
    min_route_progress: float = 0.6
    max_speed_mps: float = 12.0
    max_longitudinal_accel_mps2: float = 12.0
    max_lateral_accel_mps2: float = 10.0
    max_final_speed_mps: float = 0.75


def _env_int(
    env: dict[str, str], name: str, default: int, minimum: int = 0
) -> int:
    value = int(env.get(name, default))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _env_float(
    env: dict[str, str],
    name: str,
    default: float,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float:
    value = float(env.get(name, default))
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be a finite value >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def load_driving_config(env: dict[str, str] | None = None) -> CarlaDrivingConfig:
    values = dict(os.environ if env is None else env)
    defaults = CarlaDrivingConfig()
    tick_count = _env_int(
        values, "QRTC_CARLA_DRIVING_TICK_COUNT", defaults.tick_count, minimum=2
    )
    braking_ticks = _env_int(
        values,
        "QRTC_CARLA_BRAKING_TICK_COUNT",
        defaults.braking_tick_count,
        minimum=1,
    )
    if braking_ticks >= tick_count:
        raise ValueError(
            "QRTC_CARLA_BRAKING_TICK_COUNT must be less than "
            "QRTC_CARLA_DRIVING_TICK_COUNT"
        )

    return CarlaDrivingConfig(
        host=values.get("QRTC_CARLA_HOST", defaults.host),
        port=_env_int(values, "QRTC_CARLA_PORT", defaults.port, minimum=1),
        timeout_seconds=_env_float(
            values,
            "QRTC_CARLA_TIMEOUT_SECONDS",
            defaults.timeout_seconds,
            minimum=0.1,
        ),
        tick_count=tick_count,
        spawn_point_index=_env_int(
            values, "QRTC_CARLA_SPAWN_INDEX", defaults.spawn_point_index
        ),
        fixed_delta_seconds=_env_float(
            values,
            "QRTC_CARLA_FIXED_DELTA_SECONDS",
            defaults.fixed_delta_seconds,
            minimum=0.001,
        ),
        vehicle_blueprint_filter=values.get(
            "QRTC_CARLA_VEHICLE_BLUEPRINT",
            defaults.vehicle_blueprint_filter,
        ),
        braking_tick_count=braking_ticks,
        target_speed_mps=_env_float(
            values, "QRTC_CARLA_TARGET_SPEED_MPS", defaults.target_speed_mps, 0.1
        ),
        route_spacing_m=_env_float(
            values, "QRTC_CARLA_ROUTE_SPACING_M", defaults.route_spacing_m, 0.5
        ),
        route_waypoint_count=_env_int(
            values,
            "QRTC_CARLA_ROUTE_WAYPOINT_COUNT",
            defaults.route_waypoint_count,
            minimum=2,
        ),
        traffic_vehicle_count=_env_int(
            values,
            "QRTC_CARLA_TRAFFIC_VEHICLE_COUNT",
            defaults.traffic_vehicle_count,
        ),
        traffic_manager_port=_env_int(
            values,
            "QRTC_CARLA_TRAFFIC_MANAGER_PORT",
            defaults.traffic_manager_port,
            minimum=1,
        ),
        traffic_seed=_env_int(
            values, "QRTC_CARLA_TRAFFIC_SEED", defaults.traffic_seed
        ),
        waypoint_tolerance_m=_env_float(
            values,
            "QRTC_CARLA_WAYPOINT_TOLERANCE_M",
            defaults.waypoint_tolerance_m,
            0.1,
        ),
        min_route_progress=_env_float(
            values,
            "QRTC_CARLA_MIN_ROUTE_PROGRESS",
            defaults.min_route_progress,
            0.0,
            1.0,
        ),
        max_speed_mps=_env_float(
            values, "QRTC_CARLA_MAX_SPEED_MPS", defaults.max_speed_mps, 0.1
        ),
        max_longitudinal_accel_mps2=_env_float(
            values,
            "QRTC_CARLA_MAX_LONGITUDINAL_ACCEL_MPS2",
            defaults.max_longitudinal_accel_mps2,
            0.1,
        ),
        max_lateral_accel_mps2=_env_float(
            values,
            "QRTC_CARLA_MAX_LATERAL_ACCEL_MPS2",
            defaults.max_lateral_accel_mps2,
            0.1,
        ),
        max_final_speed_mps=_env_float(
            values,
            "QRTC_CARLA_MAX_FINAL_SPEED_MPS",
            defaults.max_final_speed_mps,
        ),
    )


def _distance(first: Any, second: Any) -> float:
    return math.sqrt(
        (first.x - second.x) ** 2
        + (first.y - second.y) ** 2
        + (first.z - second.z) ** 2
    )


def _speed(velocity: Any) -> float:
    return math.sqrt(
        velocity.x * velocity.x
        + velocity.y * velocity.y
        + velocity.z * velocity.z
    )


def _steering_command(transform: Any, target_location: Any) -> float:
    bearing = math.degrees(
        math.atan2(
            target_location.y - transform.location.y,
            target_location.x - transform.location.x,
        )
    )
    error = (bearing - transform.rotation.yaw + 180.0) % 360.0 - 180.0
    return max(-0.65, min(0.65, error / 45.0))


def _build_route(world_map: Any, spawn_location: Any, config: CarlaDrivingConfig):
    waypoint = world_map.get_waypoint(spawn_location)
    if waypoint is None:
        raise RuntimeError("ego spawn point is not on a CARLA road")
    route = [waypoint]
    for _ in range(config.route_waypoint_count - 1):
        candidates = route[-1].next(config.route_spacing_m)
        if not candidates:
            break
        waypoint = min(
            candidates,
            key=lambda item: (
                int(getattr(item, "road_id", 0)),
                int(getattr(item, "lane_id", 0)),
                float(item.transform.location.x),
                float(item.transform.location.y),
            ),
        )
        route.append(waypoint)
    if len(route) < 2:
        raise RuntimeError("unable to construct a route from the ego spawn point")
    return route


def evaluate_driving_metrics(
    telemetry: list[dict[str, Any]],
    *,
    collision_count: int,
    route_progress: float,
    traffic_requested: int,
    traffic_spawned: int,
    config: CarlaDrivingConfig,
) -> dict[str, Any]:
    if not telemetry:
        raise ValueError("telemetry must not be empty")
    checks = {
        "collision_free": collision_count == 0,
        "route_following": route_progress >= config.min_route_progress,
        "traffic_spawned": traffic_spawned == traffic_requested,
        "speed_limit": max(item["speed_mps"] for item in telemetry)
        <= config.max_speed_mps,
        "longitudinal_acceleration": max(
            abs(item["longitudinal_accel_mps2"]) for item in telemetry
        )
        <= config.max_longitudinal_accel_mps2,
        "lateral_acceleration": max(
            abs(item["lateral_accel_mps2"]) for item in telemetry
        )
        <= config.max_lateral_accel_mps2,
        "braking": telemetry[-1]["speed_mps"] <= config.max_final_speed_mps,
        "on_road": all(item["on_road"] for item in telemetry),
    }
    return {"passed": all(checks.values()), "checks": checks}


def run_live_driving_test(
    config: CarlaDrivingConfig, carla_module: Any | None = None
) -> dict[str, Any]:
    carla = carla_module
    if carla is None:
        import carla as imported_carla  # type: ignore[import-not-found]

        carla = imported_carla

    client = carla.Client(config.host, config.port)
    client.set_timeout(config.timeout_seconds)
    world: Any | None = None
    traffic_manager: Any | None = None
    actors: list[Any] = []
    traffic: list[Any] = []
    collisions: list[int] = []
    telemetry: list[dict[str, Any]] = []
    original_sync_mode = False
    original_fixed_delta_seconds: float | None = None

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
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = config.fixed_delta_seconds
        world.apply_settings(settings)

        spawn_points = world_map.get_spawn_points()
        if not spawn_points:
            raise RuntimeError("no CARLA spawn points available on the current map")
        spawn_index = config.spawn_point_index % len(spawn_points)
        spawn_point = spawn_points[spawn_index]
        blueprints = world.get_blueprint_library().filter(
            config.vehicle_blueprint_filter
        )
        if not blueprints:
            raise RuntimeError(
                f"no vehicle blueprint matched '{config.vehicle_blueprint_filter}'"
            )
        blueprint = min(blueprints, key=lambda item: item.id)
        ego_vehicle = world.try_spawn_actor(blueprint, spawn_point)
        if ego_vehicle is None:
            raise RuntimeError(f"unable to spawn ego vehicle at index {spawn_index}")
        actors.append(ego_vehicle)
        ego_vehicle.set_autopilot(False)

        route = _build_route(world_map, spawn_point.location, config)
        collision_sensor = world.spawn_actor(
            world.get_blueprint_library().find("sensor.other.collision"),
            carla.Transform(),
            attach_to=ego_vehicle,
        )
        actors.append(collision_sensor)
        collision_sensor.listen(lambda event: collisions.append(int(event.frame)))

        if config.traffic_vehicle_count:
            traffic_manager = client.get_trafficmanager(config.traffic_manager_port)
            traffic_manager.set_synchronous_mode(True)
            traffic_manager.set_random_device_seed(config.traffic_seed)
            traffic_blueprints = sorted(
                world.get_blueprint_library().filter("vehicle.*"),
                key=lambda item: item.id,
            )
            candidates = [
                point
                for index, point in enumerate(spawn_points)
                if index != spawn_index
                and _distance(point.location, spawn_point.location) >= 15.0
            ]
            for index, point in enumerate(candidates):
                if len(traffic) >= config.traffic_vehicle_count:
                    break
                actor = world.try_spawn_actor(
                    traffic_blueprints[index % len(traffic_blueprints)], point
                )
                if actor is not None:
                    actor.set_autopilot(True, config.traffic_manager_port)
                    traffic.append(actor)
                    actors.append(actor)

        route_index = 1
        previous_velocity = ego_vehicle.get_velocity()
        for tick in range(config.tick_count):
            transform = ego_vehicle.get_transform()
            velocity = ego_vehicle.get_velocity()
            speed = _speed(velocity)
            braking = tick >= config.tick_count - config.braking_tick_count

            while (
                route_index < len(route) - 1
                and _distance(
                    transform.location, route[route_index].transform.location
                )
                <= config.waypoint_tolerance_m
            ):
                route_index += 1

            steer = _steering_command(
                transform, route[route_index].transform.location
            )
            if braking:
                control = carla.VehicleControl(
                    throttle=0.0, steer=steer * 0.25, brake=1.0
                )
            else:
                speed_error = config.target_speed_mps - speed
                control = carla.VehicleControl(
                    throttle=max(0.0, min(0.65, speed_error * 0.25)),
                    steer=steer,
                    brake=max(0.0, min(0.5, -speed_error * 0.2)),
                )
            ego_vehicle.apply_control(control)
            world.tick()

            snapshot = world.get_snapshot()
            transform = ego_vehicle.get_transform()
            velocity = ego_vehicle.get_velocity()
            speed = _speed(velocity)
            acceleration_x = (
                velocity.x - previous_velocity.x
            ) / config.fixed_delta_seconds
            acceleration_y = (
                velocity.y - previous_velocity.y
            ) / config.fixed_delta_seconds
            yaw = math.radians(transform.rotation.yaw)
            longitudinal = acceleration_x * math.cos(yaw) + acceleration_y * math.sin(
                yaw
            )
            lateral = -acceleration_x * math.sin(yaw) + acceleration_y * math.cos(
                yaw
            )
            on_road = (
                world_map.get_waypoint(
                    transform.location,
                    project_to_road=False,
                    lane_type=carla.LaneType.Driving,
                )
                is not None
            )
            telemetry.append(
                {
                    "frame": int(snapshot.frame),
                    "x": float(transform.location.x),
                    "y": float(transform.location.y),
                    "z": float(transform.location.z),
                    "yaw": float(transform.rotation.yaw),
                    "speed_mps": float(speed),
                    "longitudinal_accel_mps2": float(longitudinal),
                    "lateral_accel_mps2": float(lateral),
                    "throttle": float(control.throttle),
                    "steer": float(control.steer),
                    "brake": float(control.brake),
                    "on_road": on_road,
                    "collision_count": len(collisions),
                }
            )
            previous_velocity = velocity

        route_progress = min(1.0, route_index / (len(route) - 1))
        assessment = evaluate_driving_metrics(
            telemetry,
            collision_count=len(collisions),
            route_progress=route_progress,
            traffic_requested=config.traffic_vehicle_count,
            traffic_spawned=len(traffic),
            config=config,
        )
        return {
            "host": config.host,
            "port": config.port,
            "map": world_map.name,
            "initial_frame": int(initial_snapshot.frame),
            "final_frame": int(telemetry[-1]["frame"]),
            "tick_count": config.tick_count,
            "spawn_point_index": spawn_index,
            "vehicle_blueprint": blueprint.id,
            "route_waypoint_count": len(route),
            "route_progress": route_progress,
            "traffic_requested": config.traffic_vehicle_count,
            "traffic_spawned": len(traffic),
            "collision_count": len(collisions),
            "collisions": collisions,
            "assessment": assessment,
            "telemetry": telemetry,
        }
    finally:
        if traffic_manager is not None:
            traffic_manager.set_synchronous_mode(False)
        for actor in reversed(actors):
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


def driving_result_json(config: CarlaDrivingConfig | None = None) -> str:
    result = run_live_driving_test(config or load_driving_config())
    return json.dumps(result, indent=2, sort_keys=True)
