from __future__ import annotations

from rescueos.core.distinctions import ActionOutcome, Task
from rescueos.simulator.communication_link import CommunicationLinkSimulator


class SimulatorAdapter:
    def __init__(self, simulator: CommunicationLinkSimulator) -> None:
        self._simulator = simulator

    def observe(self) -> dict:
        return self._simulator.observe()

    def evaluate_task(self, task: Task) -> float:
        return self._simulator.evaluate_task(task)

    def apply(self, action_id: str) -> ActionOutcome:
        return self._simulator.apply(action_id)

    def emergency_stop(self) -> None:
        self._simulator.emergency_stop()
