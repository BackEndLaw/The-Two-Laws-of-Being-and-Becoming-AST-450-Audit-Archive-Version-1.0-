from __future__ import annotations

from rescueos.audit.explanation import build_explanation
from rescueos.core.distinctions import ActionKind, Intervention, PlannerDecision, Task
from rescueos.simulator.communication_link import CommunicationLinkSimulator
from rescueos.simulator.fault_injector import Fault


def test_simulator_faults_reduce_task_health() -> None:
    interventions = [
        Intervention(
            action_id="repair",
            kind=ActionKind.REPAIR,
            targets=frozenset({"receiver"}),
            restores=frozenset({"decoded_message", "confidence"}),
            cost=1.0,
            harm_risk=0.0,
            success_probability=1.0,
        )
    ]
    task = Task("t", {"decoded_message": 0.9, "confidence": 0.9}, 0.05)
    sim = CommunicationLinkSimulator(
        interventions,
        faults=[Fault("drop", ("decoded_message", "confidence"), 0.5)],
    )

    assert sim.evaluate_task(task) > 0.0


def test_simulator_repair_can_improve_state() -> None:
    interventions = [
        Intervention(
            action_id="repair",
            kind=ActionKind.REPAIR,
            targets=frozenset({"receiver"}),
            restores=frozenset({"decoded_message", "confidence"}),
            cost=1.0,
            harm_risk=0.0,
            success_probability=1.0,
        )
    ]
    task = Task("t", {"decoded_message": 0.9, "confidence": 0.9}, 0.05)
    sim = CommunicationLinkSimulator(
        interventions,
        faults=[Fault("drop", ("decoded_message", "confidence"), 0.5)],
    )

    before = sim.evaluate_task(task)
    sim.apply("repair")
    after = sim.evaluate_task(task)
    assert after < before


def test_explanation_contains_required_fields() -> None:
    decision = PlannerDecision(
        action_id="lower_data_rate",
        kind=ActionKind.REPAIR,
        expected_utility=0.7,
        expected_recovery_probability=0.9,
        expected_cost=1.5,
        reason="Highest expected utility",
        lost_distinctions=("timing", "confidence"),
        candidate_utilities={"lower_data_rate": 0.7},
        unknown_fault_probability=0.07,
        safety_gate="passed",
    )

    explanation = build_explanation("reliable_message", 0.31, decision)
    assert explanation["selected_action"] == "lower_data_rate"
    assert "lost_distinctions" in explanation
    assert "candidate_actions" in explanation
