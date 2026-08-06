from __future__ import annotations

from itertools import product

import pytest

from integrations.vehicle.blocked_route import load_scenario, replay_trace, run_blocked_route


@pytest.mark.parametrize(
    ("admitted", "execute_handoff", "handoff_succeeds"),
    list(product((False, True), repeat=3)),
)
def test_gate_passage_destination_invariants_hold_for_generated_decisions(
    admitted: bool,
    execute_handoff: bool,
    handoff_succeeds: bool,
) -> None:
    scenario = load_scenario("scenarios/blocked_route_v1.json")
    result = run_blocked_route(
        scenario,
        seed=17,
        specialist_admitted=admitted,
        execute_handoff=execute_handoff,
        handoff_succeeds=handoff_succeeds,
    )
    event = result.events[0]

    if not event["specialist_admitted"]:
        assert event["passage_executed"] is False
        assert event["destination_realized"] is False
        assert event["final_state"]["controller"] == "baseline_v2"
    if not event["passage_executed"]:
        assert event["destination_realized"] is False
    if event["destination_realized"]:
        assert event["specialist_admitted"] is True
        assert event["passage_executed"] is True
    if event["fallback_invoked"]:
        assert event["final_state"]["controller"] == "baseline_v2"
        assert event["final_state"]["stopped"] is True

    assert event["witness_complete"] is True
    assert replay_trace(scenario, result.events)


def test_denied_specialist_never_emits_handoff_command() -> None:
    scenario = load_scenario("scenarios/blocked_route_v1.json")

    class RecordingAdapter:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def observe(self) -> dict:
            return {
                "position": "B",
                "route": scenario["route"],
                "route_graph": scenario["route_graph"],
                "blocked_edges": scenario["blocked_edges"],
                "controller": "baseline_v2",
                "stopped": bool(self.actions),
                "collision": False,
            }

        def apply(self, action: dict) -> dict:
            self.actions.append(action["type"])
            return {"executed": True, "succeeded": True, "collision": False}

        def safe_stop(self) -> None:
            self.actions.append("safe_stop")

    adapter = RecordingAdapter()
    run_blocked_route(
        scenario,
        seed=19,
        specialist_admitted=False,
        adapter=adapter,
    )

    assert adapter.actions == ["controlled_stop"]