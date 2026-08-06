from __future__ import annotations

from typing import Any, Mapping

from rescueos.core.distinctions import BeliefState, Task


class SimpleBeliefUpdater:
    """Belief updater backed by observation fields from adapter output."""

    def update(
        self,
        observation: Mapping[str, Any],
        history: list[Any],
        task: Task,
    ) -> BeliefState:
        distinction_health = observation.get("distinction_health", {})
        fault_probabilities = observation.get("fault_probabilities", {})

        confidence = float(observation.get("confidence", 0.5))
        confidence = min(1.0, max(0.0, confidence))

        if history:
            last_outcome = history[-1]
            if getattr(last_outcome, "succeeded", True) is False:
                confidence = max(0.0, confidence - 0.1)

        unknown_probability = observation.get("unknown_probability")
        if unknown_probability is None:
            unknown_probability = max(0.0, 1.0 - confidence)
        unknown_probability = min(1.0, max(0.0, float(unknown_probability)))

        return BeliefState(
            distinction_health=distinction_health,
            fault_probabilities=fault_probabilities,
            unknown_probability=unknown_probability,
            confidence=confidence,
            local_health=observation.get("local_health", distinction_health),
        )
