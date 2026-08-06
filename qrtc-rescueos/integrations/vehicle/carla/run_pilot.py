from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from typing import Any

import yaml

from integrations.vehicle.blocked_route import load_scenario
from integrations.vehicle.carla.adapter import CarlaVehicleAdapter
from integrations.vehicle.carla.blocked_route import run_denied_case
from integrations.vehicle.carla.fault_injection import spawn_blocking_obstacle


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as source:
        return yaml.safe_load(source)


def run(config_path: str | Path, scenario_path: str | Path, output_dir: str | Path) -> dict:
    try:
        import carla
    except ImportError as error:
        raise RuntimeError(
            "CARLA 0.9.16 client is required; add its target directory to PYTHONPATH"
        ) from error

    config = load_config(config_path)
    scenario = load_scenario(scenario_path)
    server = config["server"]
    _require_server(
        server["host"],
        int(server["port"]),
        float(server["timeout_seconds"]),
    )
    client = carla.Client(server["host"], int(server["port"]))
    client.set_timeout(float(server["timeout_seconds"]))
    world = client.load_world(config["world"]["map"])
    original_settings = world.get_settings()
    actors: list[Any] = []

    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = float(config["world"]["fixed_delta_seconds"])
        settings.no_rendering_mode = bool(config["world"]["no_rendering_mode"])
        world.apply_settings(settings)
        world.set_weather(getattr(carla.WeatherParameters, config["world"]["weather"]))

        blueprint = world.get_blueprint_library().find(config["vehicle"]["blueprint"])
        spawn_points = world.get_map().get_spawn_points()
        spawn_point = spawn_points[int(config["vehicle"]["spawn_point_index"])]
        vehicle = world.try_spawn_actor(blueprint, spawn_point)
        if vehicle is None:
            raise RuntimeError("Unable to spawn CARLA ego vehicle")
        actors.append(vehicle)

        _reach_initial_speed(world, vehicle, config["vehicle"], carla.VehicleControl)
        obstacle = spawn_blocking_obstacle(world, vehicle, config["fault"])
        actors.append(obstacle)
        adapter = CarlaVehicleAdapter(world, vehicle, scenario, config, obstacle=obstacle)
        actors.extend(_attach_sensors(world, vehicle, adapter, config["sensors"], carla))
        world.tick()

        result = run_denied_case(
            scenario,
            adapter,
            seed=int(config["experiment"]["seed"]),
            thresholds=config["acceptance_thresholds"],
        )
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        result.write_jsonl(destination / "denied-seed-1.jsonl")
        summary = {
            "scenario_id": result.scenario_id,
            "simulator": "native_carla",
            "carla_client_version": client.get_client_version(),
            "carla_server_version": client.get_server_version(),
            "case": "denied",
            "acceptance_passed": result.events[0]["acceptance"]["all_passed"],
            "event": result.events[0],
        }
        (destination / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return summary
    finally:
        for actor in reversed(actors):
            actor.destroy()
        world.apply_settings(original_settings)


def _require_server(host: str, port: int, timeout_seconds: float) -> None:
    try:
        with socket.create_connection((host, port), timeout=min(timeout_seconds, 2.0)):
            return
    except OSError as error:
        raise RuntimeError(
            f"CARLA server is not reachable at {host}:{port}; start a GPU-backed "
            "CARLA 0.9.16 server before running the physics pilot"
        ) from error


def _reach_initial_speed(world: Any, vehicle: Any, config: dict, control_factory: Any) -> None:
    target = float(config["target_speed_mps"])
    for _ in range(int(config["warmup_max_ticks"])):
        velocity = vehicle.get_velocity()
        speed = (velocity.x**2 + velocity.y**2 + velocity.z**2) ** 0.5
        if speed >= target:
            return
        vehicle.apply_control(control_factory(throttle=0.25, steer=0.0, brake=0.0))
        world.tick()
    raise RuntimeError("Ego vehicle did not reach the preregistered initial speed")


def _attach_sensors(world: Any, vehicle: Any, adapter: Any, config: dict, carla: Any) -> list[Any]:
    sensors = []
    for blueprint_id, callback in (
        (config["collision_blueprint"], adapter.record_collision),
        (config["lane_invasion_blueprint"], adapter.record_lane_invasion),
    ):
        blueprint = world.get_blueprint_library().find(blueprint_id)
        sensor = world.spawn_actor(blueprint, carla.Transform(), attach_to=vehicle)
        sensor.listen(callback)
        sensors.append(sensor)
    return sensors


def main() -> None:
    parser = argparse.ArgumentParser(description="Run denied blocked-route semantics in CARLA")
    parser.add_argument("--config", default="integrations/vehicle/carla/config.yaml")
    parser.add_argument("--scenario", default="scenarios/blocked_route_v1.json")
    parser.add_argument("--output", default="artifacts/vehicle_pilot_carla")
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.scenario, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()