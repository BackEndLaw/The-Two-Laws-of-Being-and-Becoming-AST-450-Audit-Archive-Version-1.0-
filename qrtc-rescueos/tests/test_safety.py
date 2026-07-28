from __future__ import annotations

from rescueos.adapters.simulator import SimulatorAdapter
from rescueos.audit.event_log import AuditEventLog
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController
from rescueos.core.distinctions import ActionKind, BeliefState, Intervention, Task
from rescueos.core.planner import BoundedLookaheadPlanner, PlannerConfig
from rescueos.simulator.communication_link import CommunicationLinkSimulator
from rescueos.simulator.fault_injector import Fault


def test_unknown_fault_can_trigger_abstention_or_evidence() -> None:
    task = Task("t", {"decoded_message": 0.9}, 0.05)
    belief = BeliefState(
        distinction_health={"decoded_message": 0.2},
        fault_probabilities={},
        unknown_probability=0.95,
        confidence=0.1,
    )
    repair = Intervention(
        action_id="repair",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=0.1,
        harm_risk=0.5,
        success_probability=0.95,
    )
    evidence = Intervention(
        action_id="inspect",
        kind=ActionKind.EVIDENCE,
        targets=frozenset({"receiver"}),
        restores=frozenset(),
        cost=0.01,
        information_channels=frozenset({"clock"}),
    )
    planner = BoundedLookaheadPlanner([repair, evidence], PlannerConfig(unknown_threshold=0.5))

    decision = planner.choose(belief, task, history=[])
    assert decision.kind in {ActionKind.EVIDENCE, ActionKind.STOP, ActionKind.ABSTAIN}


def test_no_action_outside_declared_intervention_library() -> None:
    intervention = Intervention(
        action_id="inspect",
        kind=ActionKind.EVIDENCE,
        targets=frozenset({"receiver"}),
        restores=frozenset(),
        cost=0.1,
        information_channels=frozenset({"clock"}),
    )
    sim = CommunicationLinkSimulator([intervention], seed=0)

    try:
        sim.apply("undeclared")
        assert False
    except KeyError:
        assert True


def test_simulator_records_realized_unsafe_events_separately_from_risk() -> None:
    safe = Intervention(
        action_id="safe_repair",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=0.1,
        harm_risk=0.0,
        success_probability=1.0,
    )
    unsafe = Intervention(
        action_id="unsafe_repair",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=0.1,
        harm_risk=1.0,
        success_probability=1.0,
    )
    sim = CommunicationLinkSimulator([safe, unsafe], seed=0)

    safe_outcome = sim.apply("safe_repair")
    unsafe_outcome = sim.apply("unsafe_repair")

    assert safe_outcome.unsafe is False
    assert safe_outcome.harm == 0.0
    assert unsafe_outcome.unsafe is True
    assert unsafe_outcome.harm == 1.0


def test_failed_intervention_updates_belief() -> None:
    updater = SimpleBeliefUpdater()
    task = Task("t", {"decoded_message": 0.9}, 0.05)
    observation = {
        "distinction_health": {"decoded_message": 0.3},
        "confidence": 0.8,
        "unknown_probability": 0.2,
        "fault_probabilities": {},
    }
    failed = type("Outcome", (), {"succeeded": False})()

    belief = updater.update(observation, [failed], task)
    assert belief.confidence < 0.8


def test_audit_log_reconstructs_every_decision() -> None:
    interventions = [
        Intervention(
            action_id="repair",
            kind=ActionKind.REPAIR,
            targets=frozenset({"receiver"}),
            restores=frozenset({"decoded_message", "confidence"}),
            cost=0.2,
            harm_risk=0.0,
            success_probability=1.0,
        )
    ]
    faults = [Fault("minor", ("decoded_message", "confidence"), 0.2)]
    sim = CommunicationLinkSimulator(interventions, seed=42, faults=faults)
    adapter = SimulatorAdapter(sim)
    log = AuditEventLog()
    controller = RescueController(
        adapter=adapter,
        inference=SimpleBeliefUpdater(),
        planner=BoundedLookaheadPlanner(interventions),
        audit_log=log,
    )

    controller.rescue(Task("t", {"decoded_message": 0.9, "confidence": 0.9}, 0.05), max_actions=2)
    assert log.reconstructable()
