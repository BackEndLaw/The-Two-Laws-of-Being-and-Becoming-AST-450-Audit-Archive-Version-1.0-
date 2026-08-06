from __future__ import annotations

import random

from rescueos.core.distinctions import (
    ActionKind,
    BeliefState,
    Intervention,
    PlannerDecision,
    Task,
)


class RandomPolicy:
    def __init__(self, interventions: list[Intervention], *, seed: int) -> None:
        self._rng = random.Random(seed)
        self._actions = [
            action
            for action in interventions
            if action.kind in {ActionKind.REPAIR, ActionKind.EVIDENCE}
        ]

    def choose(self, belief: BeliefState, task: Task, history: list) -> PlannerDecision:
        del history
        if not self._actions:
            action_id, kind, cost = "stop", ActionKind.STOP, 0.0
        else:
            action = self._rng.choice(self._actions)
            action_id, kind, cost = action.action_id, action.kind, action.cost
        lost = tuple(
            sorted(
                name
                for name, required in task.required_distinctions.items()
                if float(belief.distinction_health.get(name, 0.0)) < float(required)
            )
        )
        return PlannerDecision(
            action_id=action_id,
            kind=kind,
            expected_utility=0.0,
            expected_recovery_probability=0.0,
            expected_cost=cost,
            reason="Seeded random development baseline",
            lost_distinctions=lost,
            candidate_utilities={},
            unknown_fault_probability=belief.unknown_probability,
            safety_gate="passed",
        )