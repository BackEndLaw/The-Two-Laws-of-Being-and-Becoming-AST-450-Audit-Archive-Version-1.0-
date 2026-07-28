from __future__ import annotations

import random
from typing import Iterable

from rescueos.core.distinctions import ActionKind, ActionOutcome, Intervention, Task
from rescueos.simulator.fault_injector import Fault, apply_faults
from rescueos.simulator.observations import make_snapshot


class CommunicationLinkSimulator:
    def __init__(
        self,
        interventions: Iterable[Intervention],
        *,
        seed: int = 0,
        initial_health: dict[str, float] | None = None,
        faults: list[Fault] | None = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._interventions = {action.action_id: action for action in interventions}
        self._base_health = initial_health or {
            "decoded_message": 1.0,
            "confidence": 1.0,
            "timing": 1.0,
            "symbol_estimate": 1.0,
            "received_amplitude": 1.0,
            "received_phase": 1.0,
            "encoded_amplitude": 1.0,
            "encoded_phase": 1.0,
            "symbol_identity": 1.0,
        }
        self._faults = faults or []
        self._health = apply_faults(self._base_health, self._faults)
        self._stopped = False

    def observe(self) -> dict:
        confidence = float(self._health.get("confidence", 0.0))
        unknown_probability = max(0.0, 1.0 - confidence)
        fault_probabilities = {fault.fault_id: min(1.0, fault.severity) for fault in self._faults}
        return make_snapshot(
            distinction_health=self._health,
            confidence=confidence,
            unknown_probability=unknown_probability,
            fault_probabilities=fault_probabilities,
        )

    def evaluate_task(self, task: Task) -> float:
        shortfalls = []
        for distinction, requirement in task.required_distinctions.items():
            health = float(self._health.get(distinction, 0.0))
            shortfalls.append(max(0.0, float(requirement) - health))
        if not shortfalls:
            return 1.0
        return sum(shortfalls) / len(shortfalls)

    def apply(self, action_id: str) -> ActionOutcome:
        if self._stopped:
            raise RuntimeError("System is emergency-stopped")

        if action_id not in self._interventions:
            raise KeyError(f"Undeclared action: {action_id}")

        action = self._interventions[action_id]
        succeeded = self._rng.random() <= action.success_probability

        if action.kind == ActionKind.EVIDENCE:
            self._health["confidence"] = min(1.0, self._health.get("confidence", 0.0) + 0.1)

        if action.kind == ActionKind.REPAIR and succeeded:
            for distinction in action.restores:
                self._health[distinction] = min(1.0, self._health.get(distinction, 0.0) + 0.35)
            if "decoded_message" not in action.restores and "confidence" in action.restores:
                self._health["decoded_message"] = min(
                    1.0,
                    self._health.get("decoded_message", 0.0) + 0.15,
                )

        unsafe = action.kind == ActionKind.REPAIR and self._rng.random() < action.harm_risk
        harm = 1.0 if unsafe else 0.0
        observation = self.observe()
        return ActionOutcome(
            action_id=action.action_id,
            succeeded=succeeded,
            task_loss=0.0,
            cost=action.cost,
            harm=harm,
            unsafe=unsafe,
            observation=observation,
        )

    def emergency_stop(self) -> None:
        self._stopped = True
