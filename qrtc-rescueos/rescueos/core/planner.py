from __future__ import annotations

from dataclasses import dataclass

from rescueos.compiler.schema import CompiledGraph
from rescueos.core.distinctions import (
    ActionKind,
    BeliefState,
    Intervention,
    PlannerDecision,
    Task,
)
from rescueos.core.transition import RealizedOutcome, SystemState, TransitionModel, evaluate_task
from rescueos.core.utility import expected_utility, value_of_information


@dataclass(frozen=True)
class PlannerConfig:
    lambda_cost: float = 0.05
    beta_harm: float = 0.25
    gamma_unsafe: float = 0.2
    unknown_threshold: float = 0.5
    max_depth: int = 4
    typed_structure: bool = True


class BoundedLookaheadPlanner:
    def __init__(
        self,
        interventions: list[Intervention],
        config: PlannerConfig | None = None,
        graph: CompiledGraph | None = None,
        transition_model: TransitionModel | None = None,
    ) -> None:
        self._interventions = interventions
        self._config = config or PlannerConfig()
        self._graph = graph or (transition_model.graph if transition_model is not None else None)
        self._transition_model = transition_model or TransitionModel(self._graph)
        if self._graph is not None and self._transition_model.graph_checksum != self._graph.checksum:
            raise ValueError("Planner and transition model graph checksums differ")

    @property
    def graph_checksum(self) -> str | None:
        return self._transition_model.graph_checksum

    def predict_actions(
        self,
        belief: BeliefState,
        task: Task,
    ) -> tuple[dict[str, float | str | bool], ...]:
        lost = tuple(sorted(self._lost_distinctions(belief, task)))
        predictions: list[dict[str, float | str | bool]] = []
        for action in self._interventions:
            graph_admissible = not (
                self._config.typed_structure
                and self._graph is not None
                and action.kind == ActionKind.REPAIR
                and not self._graph.action_can_influence(action.action_id, task.task_id)
            )
            score, recovery = self._score_action(action, belief, task, lost)
            predictions.append(
                {
                    "action_id": action.action_id,
                    "action_kind": action.kind.value,
                    "graph_admissible": graph_admissible,
                    "predicted_recovery": recovery,
                    "predicted_utility": score,
                }
            )
        return tuple(predictions)

    def choose(
        self,
        belief: BeliefState,
        task: Task,
        history: list,
    ) -> PlannerDecision:
        del history

        lost = tuple(sorted(self._lost_distinctions(belief, task)))
        current_recovery = 1.0 - self._task_loss(belief, task)
        stop_utility = expected_utility(
            recovery_probability=current_recovery,
            expected_cost=0.0,
            expected_harm=0.0,
            unsafe_probability=0.0,
            lambda_cost=self._config.lambda_cost,
            beta_harm=self._config.beta_harm,
            gamma_unsafe=self._config.gamma_unsafe,
        )

        candidates: list[tuple[float, PlannerDecision]] = []
        candidate_utilities: dict[str, float] = {"stop": stop_utility}

        for action in self._interventions:
            if (
                belief.unknown_probability >= self._config.unknown_threshold
                and action.kind == ActionKind.REPAIR
                and not action.certified_safe_under_unknown
            ):
                continue

            if action.kind == ActionKind.EVIDENCE:
                if not self._evidence_has_positive_voi(action, belief, current_recovery):
                    continue

            if (
                self._config.typed_structure
                and self._graph is not None
                and action.kind == ActionKind.REPAIR
                and not self._graph.action_can_influence(action.action_id, task.task_id)
            ):
                continue

            action_utility, expected_recovery = self._score_action(
                action,
                belief,
                task,
                lost,
            )
            candidate_utilities[action.action_id] = action_utility
            candidates.append(
                (
                    action_utility,
                    PlannerDecision(
                        action_id=action.action_id,
                        kind=action.kind,
                        expected_utility=action_utility,
                        expected_recovery_probability=expected_recovery,
                        expected_cost=action.cost,
                        reason=(
                            "Highest expected utility among actions restoring "
                            "task-relevant distinctions"
                        ),
                        lost_distinctions=lost,
                        candidate_utilities={},
                        unknown_fault_probability=belief.unknown_probability,
                        safety_gate="passed",
                    ),
                )
            )

        candidates.sort(key=lambda item: (-item[0], item[1].action_id))

        if not candidates or candidates[0][0] <= stop_utility:
            return PlannerDecision(
                action_id="stop",
                kind=ActionKind.STOP,
                expected_utility=stop_utility,
                expected_recovery_probability=current_recovery,
                expected_cost=0.0,
                reason="No action has positive advantage over stopping",
                lost_distinctions=lost,
                candidate_utilities=candidate_utilities,
                unknown_fault_probability=belief.unknown_probability,
                safety_gate="passed",
            )

        best = candidates[0][1]
        return PlannerDecision(
            action_id=best.action_id,
            kind=best.kind,
            expected_utility=best.expected_utility,
            expected_recovery_probability=best.expected_recovery_probability,
            expected_cost=best.expected_cost,
            reason=best.reason,
            lost_distinctions=lost,
            candidate_utilities=candidate_utilities,
            unknown_fault_probability=belief.unknown_probability,
            safety_gate="passed",
        )

    def _score_action(
        self,
        action: Intervention,
        belief: BeliefState,
        task: Task,
        lost_distinctions: tuple[str, ...],
    ) -> tuple[float, float]:
        if self._config.typed_structure and self._graph is not None:
            state = SystemState(
                local_health=dict(belief.local_health or belief.distinction_health),
                distinction_quality=dict(belief.distinction_health),
            )
            succeeded = self._transition_model.apply(
                state=state,
                action=action,
                realized_outcome=RealizedOutcome(succeeded=True),
            )
            failed = self._transition_model.apply(
                state=state,
                action=action,
                realized_outcome=RealizedOutcome(succeeded=False),
            )
            expected_loss = (
                action.success_probability * evaluate_task(succeeded, task)
                + (1.0 - action.success_probability) * evaluate_task(failed, task)
            )
            expected_recovery = max(0.0, 1.0 - expected_loss)
        elif self._config.typed_structure:
            overlap = len(set(lost_distinctions).intersection(action.restores))
            total_lost = len(lost_distinctions) if lost_distinctions else 1
            restored_fraction = overlap / total_lost
            current_recovery = 1.0 - self._task_loss(belief, task)
            expected_recovery = min(
                1.0,
                current_recovery + (restored_fraction * action.success_probability),
            )
        else:
            restored_fraction = 1.0 if action.kind == ActionKind.REPAIR else 0.0
            current_recovery = 1.0 - self._task_loss(belief, task)
            expected_recovery = min(
                1.0,
                current_recovery + (restored_fraction * action.success_probability),
            )
        unsafe_probability = action.harm_risk if action.kind == ActionKind.REPAIR else 0.0

        score = expected_utility(
            recovery_probability=expected_recovery,
            expected_cost=action.cost,
            expected_harm=action.harm_risk,
            unsafe_probability=unsafe_probability,
            lambda_cost=self._config.lambda_cost,
            beta_harm=self._config.beta_harm,
            gamma_unsafe=self._config.gamma_unsafe,
        )
        return score, expected_recovery

    def _evidence_has_positive_voi(
        self,
        action: Intervention,
        belief: BeliefState,
        current_recovery: float,
    ) -> bool:
        expected_best_without = current_recovery
        expected_best_with = min(
            1.0,
            current_recovery + 0.25 * belief.unknown_probability + 0.15 * (1.0 - belief.confidence),
        )
        voi = value_of_information(
            expected_best_with_evidence=expected_best_with,
            expected_best_without_evidence=expected_best_without,
            evidence_cost=action.cost,
        )
        return voi > 0.0

    @staticmethod
    def _task_loss(belief: BeliefState, task: Task) -> float:
        shortfalls: list[float] = []
        for name, requirement in task.required_distinctions.items():
            health = float(belief.distinction_health.get(name, 0.0))
            shortfalls.append(max(0.0, requirement - health))
        if not shortfalls:
            return 1.0
        return sum(shortfalls) / len(shortfalls)

    @staticmethod
    def _lost_distinctions(belief: BeliefState, task: Task) -> list[str]:
        missing = []
        for name, requirement in task.required_distinctions.items():
            if float(belief.distinction_health.get(name, 0.0)) < requirement:
                missing.append(name)
        return missing
