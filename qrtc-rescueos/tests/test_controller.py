from __future__ import annotations

from rescueos.adapters.simulator import SimulatorAdapter
from rescueos.audit.event_log import AuditEventLog
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController
from rescueos.core.distinctions import ActionKind, Intervention, Task
from rescueos.core.planner import BoundedLookaheadPlanner
from rescueos.simulator.communication_link import CommunicationLinkSimulator
from rescueos.simulator.fault_injector import Fault


class CountingAdapter(SimulatorAdapter):
    def __init__(self, simulator: CommunicationLinkSimulator) -> None:
        super().__init__(simulator)
        self.evaluate_calls = 0
        self.apply_calls = 0

    def evaluate_task(self, task: Task) -> float:
        self.evaluate_calls += 1
        return super().evaluate_task(task)

    def apply(self, action_id: str):
        self.apply_calls += 1
        return super().apply(action_id)


def _task() -> Task:
    return Task("reliable_message", {"decoded_message": 0.99, "confidence": 0.90}, 0.05)


def _interventions() -> list[Intervention]:
    return [
        Intervention(
            action_id="lower_data_rate",
            kind=ActionKind.REPAIR,
            targets=frozenset({"transmitter", "receiver"}),
            restores=frozenset({"timing", "confidence", "decoded_message"}),
            cost=1.5,
            harm_risk=0.0,
            success_probability=1.0,
        ),
        Intervention(
            action_id="inspect_receiver",
            kind=ActionKind.EVIDENCE,
            targets=frozenset({"receiver"}),
            restores=frozenset(),
            cost=0.1,
            information_channels=frozenset({"gain"}),
        ),
    ]


def test_controller_stops_when_task_is_already_satisfied() -> None:
    sim = CommunicationLinkSimulator(_interventions(), seed=10)
    adapter = CountingAdapter(sim)
    controller = RescueController(
        adapter=adapter,
        inference=SimpleBeliefUpdater(),
        planner=BoundedLookaheadPlanner(_interventions()),
        audit_log=AuditEventLog(),
    )

    result = controller.rescue(_task(), max_actions=4)
    assert result.status == "recovered"
    assert result.actions_executed == 0
    assert adapter.apply_calls == 0


def test_controller_checks_recovery_after_every_action() -> None:
    faults = [Fault("drop", ("decoded_message", "confidence"), 0.2)]
    sim = CommunicationLinkSimulator(_interventions(), seed=2, faults=faults)
    adapter = CountingAdapter(sim)
    controller = RescueController(
        adapter=adapter,
        inference=SimpleBeliefUpdater(),
        planner=BoundedLookaheadPlanner(_interventions()),
        audit_log=AuditEventLog(),
    )

    result = controller.rescue(_task(), max_actions=4)
    assert result.status in {"recovered", "stopped", "abstained", "budget_exhausted"}
    assert adapter.evaluate_calls >= adapter.apply_calls + 1


def test_action_budget_is_never_exceeded() -> None:
    faults = [Fault("major", ("decoded_message", "confidence"), 0.8)]
    sim = CommunicationLinkSimulator(_interventions(), seed=1, faults=faults)
    adapter = CountingAdapter(sim)
    controller = RescueController(
        adapter=adapter,
        inference=SimpleBeliefUpdater(),
        planner=BoundedLookaheadPlanner(_interventions()),
        audit_log=AuditEventLog(),
    )

    result = controller.rescue(_task(), max_actions=2)
    assert result.actions_executed <= 2
