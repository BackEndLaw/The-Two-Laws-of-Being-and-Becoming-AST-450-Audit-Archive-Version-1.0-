from __future__ import annotations

import pytest

from rescueos.adapters.hardware import HardwareAdapter
from rescueos.audit.event_log import AuditEventLog
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController
from rescueos.core.distinctions import ActionKind, ActionOutcome, Intervention, Task
from rescueos.core.planner import BoundedLookaheadPlanner


def _task() -> Task:
    return Task("reliable_message", {"decoded_message": 0.9, "confidence": 0.9}, 0.05)


def _interventions() -> list[Intervention]:
    return [
        Intervention(
            action_id="repair",
            kind=ActionKind.REPAIR,
            targets=frozenset({"receiver"}),
            restores=frozenset({"decoded_message", "confidence"}),
            cost=0.1,
            harm_risk=0.0,
            success_probability=1.0,
        )
    ]


def test_hardware_placeholder_methods_raise_not_implemented() -> None:
    adapter = HardwareAdapter()

    with pytest.raises(NotImplementedError):
        adapter.observe()
    with pytest.raises(NotImplementedError):
        adapter.evaluate_task(_task())
    with pytest.raises(NotImplementedError):
        adapter.apply("repair")
    with pytest.raises(NotImplementedError):
        adapter.emergency_stop()


def test_controller_accepts_hardware_like_adapter_contract() -> None:
    class MockHardwareAdapter:
        def __init__(self) -> None:
            self._health = {"decoded_message": 0.2, "confidence": 0.95}

        def observe(self) -> dict:
            confidence = self._health["confidence"]
            return {
                "distinction_health": dict(self._health),
                "confidence": confidence,
                "unknown_probability": 1.0 - confidence,
                "fault_probabilities": {},
            }

        def evaluate_task(self, task: Task) -> float:
            shortfalls = []
            for name, requirement in task.required_distinctions.items():
                shortfalls.append(max(0.0, float(requirement) - self._health.get(name, 0.0)))
            return sum(shortfalls) / len(shortfalls)

        def apply(self, action_id: str) -> ActionOutcome:
            del action_id
            self._health["decoded_message"] = 1.0
            self._health["confidence"] = 1.0
            return ActionOutcome(
                action_id="repair",
                succeeded=True,
                task_loss=0.0,
                cost=0.1,
                harm=0.0,
                observation=self.observe(),
            )

        def emergency_stop(self) -> None:
            return None

    controller = RescueController(
        adapter=MockHardwareAdapter(),
        inference=SimpleBeliefUpdater(),
        planner=BoundedLookaheadPlanner(_interventions()),
        audit_log=AuditEventLog(),
    )

    result = controller.rescue(_task(), max_actions=2)
    assert result.status == "recovered"
