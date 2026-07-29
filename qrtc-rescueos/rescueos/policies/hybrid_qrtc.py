from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Any, Iterable, Mapping

from rescueos.compiler.schema import CompiledGraph
from rescueos.core.distinctions import (
    ActionKind,
    BeliefState,
    Intervention,
    PlannerDecision,
    Task,
)
from rescueos.core.planner import BoundedLookaheadPlanner
from rescueos.core.utility import expected_utility


@dataclass(frozen=True)
class ResidualPrediction:
    residual: float
    uncertainty: float


@dataclass(frozen=True)
class LearnedResidualActionModel:
    feature_names: tuple[str, ...]
    weights: Mapping[str, tuple[float, ...]]
    uncertainty: Mapping[str, float]

    @classmethod
    def fit(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        ridge: float = 1e-3,
    ) -> LearnedResidualActionModel:
        rows = list(records)
        feature_names = tuple(
            sorted(
                {
                    name
                    for row in rows
                    for name in row["public_observation"]["distinction_health"]
                }
            )
        )
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            if row["action_kind"] != ActionKind.REPAIR.value:
                continue
            grouped.setdefault(str(row["action_id"]), []).append(row)
        weights: dict[str, tuple[float, ...]] = {}
        uncertainty: dict[str, float] = {}
        for action_id, action_rows in grouped.items():
            matrix = [cls._features(row["public_observation"], feature_names) for row in action_rows]
            targets = [
                float(row["realized_recovery"]) - float(row["predicted_recovery"])
                for row in action_rows
            ]
            fitted = _ridge_fit(matrix, targets, ridge)
            residuals = [
                target - sum(weight * value for weight, value in zip(fitted, features))
                for target, features in zip(targets, matrix)
            ]
            weights[action_id] = tuple(fitted)
            uncertainty[action_id] = max(
                0.05,
                math.sqrt(statistics.fmean(value * value for value in residuals)),
            )
        return cls(feature_names, weights, uncertainty)

    @staticmethod
    def _features(
        observation: Mapping[str, Any], feature_names: tuple[str, ...]
    ) -> list[float]:
        health = observation.get("distinction_health", {})
        return [
            1.0,
            *(float(health.get(name, 0.0)) for name in feature_names),
            float(observation.get("confidence", 0.5)),
            float(observation.get("unknown_probability", 0.5)),
        ]

    def predict(
        self,
        observation: Mapping[str, Any],
        history: list[Any],
        action_id: str,
    ) -> ResidualPrediction:
        del history
        features = self._features(observation, self.feature_names)
        weights = self.weights.get(action_id)
        if weights is None:
            return ResidualPrediction(0.0, 1.0)
        residual = sum(weight * value for weight, value in zip(weights, features))
        return ResidualPrediction(residual, float(self.uncertainty[action_id]))

    def parameters(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "weights": {key: list(value) for key, value in sorted(self.weights.items())},
            "uncertainty": dict(sorted(self.uncertainty.items())),
        }


class HybridQRTCPolicy:
    def __init__(
        self,
        interventions: list[Intervention],
        graph: CompiledGraph,
        residual_model: LearnedResidualActionModel,
        *,
        uncertainty_penalty: float = 0.25,
        evidence_threshold: float = 0.25,
    ) -> None:
        self._interventions = interventions
        self._actions = {action.action_id: action for action in interventions}
        self._base = BoundedLookaheadPlanner(interventions, graph=graph)
        self._model = residual_model
        self._uncertainty_penalty = uncertainty_penalty
        self._evidence_threshold = evidence_threshold

    def choose(self, belief: BeliefState, task: Task, history: list) -> PlannerDecision:
        observation = {
            "distinction_health": dict(belief.distinction_health),
            "confidence": belief.confidence,
            "unknown_probability": belief.unknown_probability,
        }
        candidates: list[tuple[float, str, float, float]] = []
        predictions = self._base.predict_actions(belief, task)
        for prediction in predictions:
            if not bool(prediction["graph_admissible"]):
                continue
            action = self._actions[str(prediction["action_id"])]
            if action.kind != ActionKind.REPAIR:
                continue
            residual = self._model.predict(observation, history, action.action_id)
            recovery = min(
                1.0,
                max(0.0, float(prediction["predicted_recovery"]) + residual.residual),
            )
            score = expected_utility(
                recovery_probability=recovery,
                expected_cost=action.cost,
                expected_harm=action.harm_risk,
                unsafe_probability=action.harm_risk,
                lambda_cost=0.05,
                beta_harm=0.25,
                gamma_unsafe=0.2,
            ) - self._uncertainty_penalty * residual.uncertainty
            candidates.append((score, action.action_id, recovery, residual.uncertainty))
        candidates.sort(key=lambda item: (-item[0], item[1]))

        evidence_actions = [
            action for action in self._interventions if action.kind == ActionKind.EVIDENCE
        ]
        max_uncertainty = max((item[3] for item in candidates), default=1.0)
        already_gathered_evidence = any(
            outcome.action_id in {action.action_id for action in evidence_actions}
            for outcome in history
        )
        if (
            evidence_actions
            and not already_gathered_evidence
            and max_uncertainty >= self._evidence_threshold
        ):
            evidence = min(evidence_actions, key=lambda action: (action.cost, action.action_id))
            voi = 0.5 * max_uncertainty - 0.05 * evidence.cost
            if voi > 0.0:
                return self._decision(
                    evidence.action_id,
                    evidence.kind,
                    voi,
                    0.0,
                    evidence.cost,
                    belief,
                    "Residual uncertainty makes reversible evidence valuable",
                )

        if not candidates or candidates[0][0] <= 0.0:
            return self._decision(
                "stop",
                ActionKind.STOP,
                0.0,
                1.0 - self._task_loss(belief, task),
                0.0,
                belief,
                "No graph-admissible calibrated action has positive utility",
            )
        score, action_id, recovery, _ = candidates[0]
        action = self._actions[action_id]
        return self._decision(
            action_id,
            action.kind,
            score,
            recovery,
            action.cost,
            belief,
            "Graph-admissible action ranked by calibrated effect and uncertainty",
        )

    @staticmethod
    def _task_loss(belief: BeliefState, task: Task) -> float:
        return statistics.fmean(
            max(0.0, float(required) - float(belief.distinction_health.get(name, 0.0)))
            for name, required in task.required_distinctions.items()
        )

    @staticmethod
    def _decision(
        action_id: str,
        kind: ActionKind,
        score: float,
        recovery: float,
        cost: float,
        belief: BeliefState,
        reason: str,
    ) -> PlannerDecision:
        return PlannerDecision(
            action_id=action_id,
            kind=kind,
            expected_utility=score,
            expected_recovery_probability=recovery,
            expected_cost=cost,
            reason=reason,
            lost_distinctions=tuple(),
            candidate_utilities={},
            unknown_fault_probability=belief.unknown_probability,
            safety_gate="passed",
        )


def _ridge_fit(matrix: list[list[float]], targets: list[float], ridge: float) -> list[float]:
    width = len(matrix[0])
    system = [
        [
            sum(row[left] * row[right] for row in matrix)
            + (ridge if left == right else 0.0)
            for right in range(width)
        ]
        + [sum(row[left] * target for row, target in zip(matrix, targets))]
        for left in range(width)
    ]
    for pivot in range(width):
        swap = max(range(pivot, width), key=lambda index: abs(system[index][pivot]))
        system[pivot], system[swap] = system[swap], system[pivot]
        divisor = system[pivot][pivot]
        if abs(divisor) < 1e-12:
            continue
        system[pivot] = [value / divisor for value in system[pivot]]
        for row_index in range(width):
            if row_index == pivot:
                continue
            factor = system[row_index][pivot]
            system[row_index] = [
                value - factor * pivot_value
                for value, pivot_value in zip(system[row_index], system[pivot])
            ]
    return [system[index][-1] for index in range(width)]