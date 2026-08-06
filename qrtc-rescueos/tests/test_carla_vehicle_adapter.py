from __future__ import annotations

from dataclasses import dataclass

from integrations.vehicle.blocked_route import load_scenario
from integrations.vehicle.carla.adapter import CarlaVehicleAdapter
from integrations.vehicle.carla.blocked_route import run_denied_case
from integrations.vehicle.carla.run_pilot import _require_server, load_config

import pytest


@dataclass
class _Vector:
    x: float
    y: float = 0.0
    z: float = 0.0


class _Vehicle:
    def __init__(self) -> None:
        self.location = _Vector(0.0)
        self.velocity = _Vector(3.0)
        self.braking = False

    def get_location(self) -> _Vector:
        return self.location

    def get_velocity(self) -> _Vector:
        return self.velocity

    def apply_control(self, control: dict) -> None:
        self.braking = control["brake"] > 0.0


class _World:
    def __init__(self, vehicle: _Vehicle) -> None:
        self.vehicle = vehicle

    def tick(self) -> None:
        self.vehicle.location = _Vector(
            self.vehicle.location.x + self.vehicle.velocity.x * 0.05
        )
        if self.vehicle.braking:
            self.vehicle.velocity = _Vector(max(0.0, self.vehicle.velocity.x - 0.5))


def _control(**values: float) -> dict:
    return values


def test_denied_carla_contract_retains_baseline_and_stops() -> None:
    scenario = load_scenario("scenarios/blocked_route_v1.json")
    config = load_config("integrations/vehicle/carla/config.yaml")
    vehicle = _Vehicle()
    obstacle = _Vehicle()
    obstacle.location = _Vector(20.0)
    adapter = CarlaVehicleAdapter(
        _World(vehicle),
        vehicle,
        scenario,
        config,
        obstacle=obstacle,
        control_factory=_control,
    )

    result = run_denied_case(
        scenario,
        adapter,
        seed=1,
        thresholds=config["acceptance_thresholds"],
    )
    event = result.events[0]

    assert event["gate_decision"] == "denied"
    assert event["retained_jurisdiction"] == "v2"
    assert event["passage_executed"] is False
    assert event["destination_realized"] is False
    assert event["final_state"]["controller"] == "baseline_v2"
    assert event["final_state"]["stopped"] is True
    assert event["physics"]["collisions"] == 0
    assert event["semantic_replay_agreement"] is True
    assert event["acceptance"]["all_passed"] is True


def test_handoff_is_not_claimed_before_route_follower_exists() -> None:
    scenario = load_scenario("scenarios/blocked_route_v1.json")
    config = load_config("integrations/vehicle/carla/config.yaml")
    vehicle = _Vehicle()
    adapter = CarlaVehicleAdapter(
        _World(vehicle), vehicle, scenario, config, control_factory=_control
    )

    outcome = adapter.apply({"type": "handoff"})

    assert outcome["executed"] is False
    assert outcome["succeeded"] is False
    assert "not implemented" in outcome["reason"]


def test_missing_carla_server_fails_before_native_client() -> None:
    with pytest.raises(RuntimeError, match="CARLA server is not reachable"):
        _require_server("127.0.0.1", 1, 0.01)