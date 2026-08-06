from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from integrations.vehicle.adapter import GraphVehicleAdapter, VehicleAdapter


@dataclass(frozen=True)
class PilotResult:
    scenario_id: str
    outcome: str
    events: tuple[dict[str, Any], ...]

    def write_jsonl(self, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in self.events),
            encoding="utf-8",
        )


def load_scenario(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as source:
        return json.load(source)


def run_blocked_route(
    scenario: dict[str, Any],
    *,
    seed: int,
    specialist_admitted: bool,
    execute_handoff: bool = True,
    handoff_succeeds: bool = True,
    adapter: VehicleAdapter | None = None,
) -> PilotResult:
    environment = adapter or GraphVehicleAdapter(scenario)
    observation = environment.observe()
    blocked_edge = tuple(scenario["fault"]["edge"])
    route_edges = set(zip(observation["route"], observation["route"][1:]))
    blocked_edge_detected = blocked_edge in route_edges and list(blocked_edge) in observation["blocked_edges"]

    baseline_proposal = {"type": "controlled_stop", "controller": "baseline_v2"}
    specialist_proposal = {
        "type": "handoff",
        "controller": "alternate_route",
        "route": list(scenario["alternate_route"]),
    }
    request_formed = blocked_edge_detected
    gate_admitted = request_formed and specialist_admitted
    passage_committed = gate_admitted
    handoff_requested = passage_committed and execute_handoff
    passage_executed = False
    destination_realized = False
    fallback_invoked = False

    if not gate_admitted:
        selected_action = baseline_proposal
        realized = environment.apply(selected_action)
        outcome = "safe" if realized["succeeded"] else "failed"
    elif not handoff_requested:
        selected_action = {"type": "none", "reason": "handoff_not_executed"}
        realized = {"executed": False, "succeeded": False, "collision": False}
        outcome = "pending"
    else:
        selected_action = {**specialist_proposal, "succeeds": handoff_succeeds}
        realized = environment.apply(selected_action)
        passage_executed = bool(realized["executed"])
        if realized["succeeded"]:
            destination_realized = True
            outcome = "route_resumed_safely"
        else:
            environment.safe_stop()
            fallback_invoked = True
            outcome = "safe_fallback"

    final_state = environment.observe()
    event = {
        "scenario_id": scenario["scenario_id"],
        "step": 0,
        "random_seed": seed,
        "initial_state": scenario["initial_state"],
        "blocked_edge": list(blocked_edge),
        "blocked_edge_detected": blocked_edge_detected,
        "request_formed": request_formed,
        "baseline_proposal": baseline_proposal,
        "specialist_proposal": specialist_proposal,
        "gate_decision": "admitted" if gate_admitted else "denied",
        "specialist_admitted": gate_admitted,
        "retained_jurisdiction": None if gate_admitted else "v2",
        "passage_committed": passage_committed,
        "handoff_requested": handoff_requested,
        "passage_executed": passage_executed,
        "destination_realized": destination_realized,
        "destination": "alternate-route controller active" if destination_realized else None,
        "selected_action": selected_action["type"],
        "action_succeeded": realized["succeeded"],
        "fallback_invoked": fallback_invoked,
        "outcome": outcome,
        "collision": final_state["collision"],
        "final_state": final_state,
        "witness_complete": True,
    }
    return PilotResult(scenario["scenario_id"], outcome, (event,))


def replay_trace(scenario: dict[str, Any], events: tuple[dict[str, Any], ...]) -> bool:
    if len(events) != 1:
        return False
    event = events[0]
    replayed = run_blocked_route(
        scenario,
        seed=event["random_seed"],
        specialist_admitted=event["specialist_admitted"],
        execute_handoff=event["passage_executed"],
        handoff_succeeds=event["action_succeeded"],
    )
    return replayed.events == events