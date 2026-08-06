from __future__ import annotations

from typing import Any


def spawn_blocking_obstacle(world: Any, ego_vehicle: Any, config: dict) -> Any:
    try:
        import carla
    except ImportError as error:
        raise RuntimeError("CARLA Python API is required for fault injection") from error

    blueprint = world.get_blueprint_library().find(config["obstacle_blueprint"])
    ego_transform = ego_vehicle.get_transform()
    forward = ego_transform.get_forward_vector()
    distance = float(config["obstacle_distance_m"])
    location = ego_transform.location + carla.Location(
        x=forward.x * distance,
        y=forward.y * distance,
        z=0.2,
    )
    transform = carla.Transform(location, ego_transform.rotation)
    obstacle = world.try_spawn_actor(blueprint, transform)
    if obstacle is None:
        raise RuntimeError("Unable to spawn blocked-route obstacle")
    return obstacle