from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from rescueos.core.distinctions import ActionOutcome, Task
from rescueos.simulator.communication_link import CommunicationLinkSimulator


NONORACLE_OBSERVATION_FIELDS = (
    "distinction_health",
    "confidence",
    "unknown_probability",
)


def project_policy_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "distinction_health": dict(observation.get("distinction_health", {})),
        "confidence": float(observation.get("confidence", 0.5)),
        "unknown_probability": float(observation.get("unknown_probability", 0.5)),
    }


class SimulatorAdapter:
    def __init__(
        self,
        simulator: CommunicationLinkSimulator,
        *,
        oracle_observations: bool = True,
    ) -> None:
        self._simulator = simulator
        self._oracle_observations = oracle_observations

    def observe(self) -> dict:
        observation = self._simulator.observe()
        if self._oracle_observations:
            return observation
        return project_policy_observation(observation)

    def evaluate_task(self, task: Task) -> float:
        return self._simulator.evaluate_task(task)

    def apply(self, action_id: str) -> ActionOutcome:
        outcome = self._simulator.apply(action_id)
        if self._oracle_observations:
            return outcome
        return replace(
            outcome,
            observation=project_policy_observation(outcome.observation),
        )

    def emergency_stop(self) -> None:
        self._simulator.emergency_stop()
