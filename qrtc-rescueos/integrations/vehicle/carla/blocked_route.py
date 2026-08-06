from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from typing import Any

from integrations.vehicle.blocked_route import PilotResult, run_blocked_route
from integrations.vehicle.carla.adapter import CarlaVehicleAdapter


def semantic_projection(event: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "gate_decision",
        "specialist_admitted",
        "retained_jurisdiction",
        "passage_committed",
        "passage_executed",
        "destination_realized",
        "fallback_invoked",
        "selected_action",
        "outcome",
    )
    return {field: event[field] for field in fields}


def run_denied_case(
    scenario: dict[str, Any],
    adapter: CarlaVehicleAdapter,
    *,
    seed: int,
    thresholds: dict[str, Any],
) -> PilotResult:
    adapter.mark_fault_detected()
    observation = adapter.observe()
    decision_started = perf_counter()
    blocked_edge = tuple(scenario["fault"]["edge"])
    route_edges = set(zip(observation["route"], observation["route"][1:]))
    gate_admitted = not (
        blocked_edge in route_edges
        and list(blocked_edge) in observation["blocked_edges"]
    )
    gate_latency_ms = (perf_counter() - decision_started) * 1000.0
    if gate_admitted:
        raise RuntimeError("Denied-case precondition did not produce Gate denial")

    result = run_blocked_route(
        scenario,
        seed=seed,
        specialist_admitted=False,
        adapter=adapter,
    )
    event = dict(result.events[0])
    physics = adapter.physics_metrics()
    physics["gate_decision_latency_ms"] = gate_latency_ms
    physics["handoff_latency_ms"] = None
    physics["fallback_activation_latency_ms"] = None
    event["physics"] = physics
    event["semantic_replay_agreement"] = semantic_projection(event) == {
        "gate_decision": "denied",
        "specialist_admitted": False,
        "retained_jurisdiction": "v2",
        "passage_committed": False,
        "passage_executed": False,
        "destination_realized": False,
        "fallback_invoked": False,
        "selected_action": "controlled_stop",
        "outcome": "safe",
    }
    event["trajectory_replay"] = "not_evaluated_in_denied_case_v1"
    event["acceptance"] = _denied_acceptance(event, thresholds)
    event["witness_complete"] = all(
        key in event
        for key in (
            "baseline_proposal",
            "specialist_proposal",
            "gate_decision",
            "passage_committed",
            "passage_executed",
            "destination_realized",
            "physics",
        )
    )
    return replace(result, events=(event,))


def _denied_acceptance(event: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, bool]:
    physics = event["physics"]
    checks = {
        "baseline_retained": event["retained_jurisdiction"] == "v2",
        "no_specialist_passage": not event["passage_executed"],
        "no_specialist_destination": not event["destination_realized"],
        "controlled_stop_succeeded": event["outcome"] == "safe",
        "collision_limit": physics["collisions"] <= thresholds["max_collisions"],
        "lane_invasion_limit": physics["lane_invasions"] <= thresholds["max_lane_invasions"],
        "stopping_distance_limit": (
            physics["braking_distance_m"] is not None
            and physics["braking_distance_m"] <= thresholds["max_stopping_distance_m"]
        ),
        "fault_detection_speed_range": (
            physics["speed_at_fault_detection_mps"]
            >= thresholds["minimum_fault_detection_speed_mps"]
            and physics["speed_at_fault_detection_mps"]
            <= thresholds["maximum_fault_detection_speed_mps"]
        ),
        "stopped_speed_limit": (
            physics["final_speed_mps"] <= thresholds["maximum_stopped_speed_mps"]
        ),
        "obstacle_clearance_limit": (
            physics["minimum_obstacle_clearance_m"] is not None
            and physics["minimum_obstacle_clearance_m"]
            >= thresholds["minimum_obstacle_clearance_m"]
        ),
        "time_to_collision_limit": (
            physics["minimum_time_to_collision_s"] is not None
            and physics["minimum_time_to_collision_s"]
            >= thresholds["minimum_time_to_collision_s"]
        ),
        "gate_latency_limit": (
            physics["gate_decision_latency_ms"] <= thresholds["max_gate_latency_ms"]
        ),
        "semantic_replay": event["semantic_replay_agreement"],
    }
    checks["all_passed"] = all(checks.values())
    return checks