from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Callable


def _vehicle_control(**values: float) -> Any:
    try:
        import carla
    except ImportError as error:
        raise RuntimeError(
            "CARLA Python API is unavailable; add its installation directory to PYTHONPATH"
        ) from error
    return carla.VehicleControl(**values)


class CarlaVehicleAdapter:
    """Translate CARLA state and commands without owning RescueOS policy semantics."""

    def __init__(
        self,
        world: Any,
        vehicle: Any,
        scenario: dict,
        config: dict,
        *,
        obstacle: Any | None = None,
        control_factory: Callable[..., Any] = _vehicle_control,
    ) -> None:
        self._world = world
        self._vehicle = vehicle
        self._scenario = deepcopy(scenario)
        self._config = config
        self._obstacle = obstacle
        self._control_factory = control_factory
        self._controller = "baseline_v2"
        self._stopped = False
        self._collisions = 0
        self._lane_invasions = 0
        self._traffic_rule_violations = 0
        self._fault_location: Any | None = None
        self._speed_at_fault_detection: float | None = None
        self._minimum_clearance_m: float | None = None
        self._minimum_ttc_s: float | None = None
        self._braking_distance_m: float | None = None
        self._trajectory: list[dict[str, float]] = []

    def record_collision(self, _event: Any) -> None:
        self._collisions += 1

    def record_lane_invasion(self, _event: Any) -> None:
        self._lane_invasions += 1

    def mark_fault_detected(self) -> None:
        self._fault_location = self._vehicle.get_location()
        self._speed_at_fault_detection = self._speed_mps()
        self._sample_trajectory()

    def observe(self) -> dict:
        self._sample_trajectory()
        location = self._vehicle.get_location()
        return {
            "position": {"x": location.x, "y": location.y, "z": location.z},
            "route": list(self._scenario["route"]),
            "route_graph": deepcopy(self._scenario["route_graph"]),
            "blocked_edges": deepcopy(self._scenario["blocked_edges"]),
            "controller": self._controller,
            "stopped": self._stopped,
            "collision": self._collisions > 0,
            "physics": self.physics_metrics(),
        }

    def apply(self, action: dict) -> dict:
        action_type = action["type"]
        if action_type == "controlled_stop":
            return self._controlled_stop()
        if action_type == "handoff":
            return {
                "executed": False,
                "succeeded": False,
                "collision": self._collisions > 0,
                "reason": "CARLA V1 route-following specialist is not implemented",
            }
        raise ValueError(f"Unsupported vehicle action: {action_type}")

    def safe_stop(self) -> None:
        self._controller = "baseline_v2"
        self._controlled_stop()

    def physics_metrics(self) -> dict[str, Any]:
        return {
            "collisions": self._collisions,
            "lane_invasions": self._lane_invasions,
            "minimum_time_to_collision_s": self._minimum_ttc_s,
            "minimum_obstacle_clearance_m": self._minimum_clearance_m,
            "speed_at_fault_detection_mps": self._speed_at_fault_detection,
            "final_speed_mps": self._speed_mps(),
            "braking_distance_m": self._braking_distance_m,
            "route_completed": False,
            "traffic_rule_violations": self._traffic_rule_violations,
            "trajectory": list(self._trajectory),
        }

    def _controlled_stop(self) -> dict:
        stop_config = self._config["controlled_stop"]
        start = self._vehicle.get_location()
        control = self._control_factory(throttle=0.0, steer=0.0, brake=1.0)
        for _ in range(int(stop_config["max_ticks"])):
            self._vehicle.apply_control(control)
            self._world.tick()
            self._sample_trajectory()
            if self._speed_mps() <= float(stop_config["speed_threshold_mps"]):
                break

        end = self._vehicle.get_location()
        self._braking_distance_m = self._distance(start, end)
        self._stopped = self._speed_mps() <= float(stop_config["speed_threshold_mps"])
        return {
            "executed": True,
            "succeeded": self._stopped and self._collisions == 0,
            "collision": self._collisions > 0,
        }

    def _sample_trajectory(self) -> None:
        location = self._vehicle.get_location()
        speed = self._speed_mps()
        sample = {
            "x": float(location.x),
            "y": float(location.y),
            "z": float(location.z),
            "speed_mps": speed,
        }
        if not self._trajectory or sample != self._trajectory[-1]:
            self._trajectory.append(sample)

        if self._obstacle is None:
            return
        clearance = self._distance(location, self._obstacle.get_location())
        self._minimum_clearance_m = (
            clearance
            if self._minimum_clearance_m is None
            else min(self._minimum_clearance_m, clearance)
        )
        if speed > 0.0:
            ttc = clearance / speed
            self._minimum_ttc_s = (
                ttc if self._minimum_ttc_s is None else min(self._minimum_ttc_s, ttc)
            )

    def _speed_mps(self) -> float:
        velocity = self._vehicle.get_velocity()
        return math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)

    @staticmethod
    def _distance(left: Any, right: Any) -> float:
        return math.sqrt(
            (left.x - right.x) ** 2
            + (left.y - right.y) ** 2
            + (left.z - right.z) ** 2
        )