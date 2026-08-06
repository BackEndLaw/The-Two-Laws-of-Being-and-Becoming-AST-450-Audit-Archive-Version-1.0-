from __future__ import annotations

from typing import Mapping

from rescueos.core.distinctions import (
    ActionKind,
    BeliefState,
    Intervention,
    PlannerDecision,
    Task,
)


class LearnedEndToEndPolicy:
    def __init__(
        self,
        interventions: list[Intervention],
        weights: Mapping[str, Mapping[str, float]],
    ) -> None:
        self._interventions = interventions
        self._weights = weights

    def choose(self, belief: BeliefState, task: Task, history: list) -> PlannerDecision:
        del history
        scored: list[tuple[float, Intervention]] = []
        for action in self._interventions:
            if action.kind not in {ActionKind.REPAIR, ActionKind.EVIDENCE}:
                continue
            score = sum(
                max(0.0, 1.0 - float(value))
                * float(self._weights.get(action.action_id, {}).get(name, 0.0))
                for name, value in belief.distinction_health.items()
            )
            score -= 0.05 * action.cost + 0.25 * action.harm_risk
            scored.append((score, action))

        scored.sort(key=lambda item: (-item[0], item[1].action_id))
        if not scored or scored[0][0] <= 0.0:
            return self._decision("stop", ActionKind.STOP, 0.0, belief, task)
        score, action = scored[0]
        return self._decision(action.action_id, action.kind, score, belief, task)

    @staticmethod
    def _decision(
        action_id: str,
        kind: ActionKind,
        score: float,
        belief: BeliefState,
        task: Task,
    ) -> PlannerDecision:
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
            expected_utility=score,
            expected_recovery_probability=max(0.0, min(1.0, score)),
            expected_cost=0.0,
            reason="Development-fitted public-observation score",
            lost_distinctions=lost,
            candidate_utilities={},
            unknown_fault_probability=belief.unknown_probability,
            safety_gate="passed",
        )