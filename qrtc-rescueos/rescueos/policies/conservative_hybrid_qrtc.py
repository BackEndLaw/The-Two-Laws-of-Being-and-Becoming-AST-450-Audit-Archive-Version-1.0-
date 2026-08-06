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
from rescueos.policies.hybrid_qrtc import _ridge_fit


@dataclass(frozen=True)
class ConservativeResidualPrediction:
    residual: float
    raw_residual: float
    uncertainty: float
    support_distance: float
    alpha: float


@dataclass(frozen=True)
class ConservativeTemporalResidualModel:
    feature_names: tuple[str, ...]
    weights: Mapping[str, tuple[float, ...]]
    uncertainty: Mapping[str, float]
    support_center: Mapping[str, tuple[float, ...]]
    support_scale: Mapping[str, tuple[float, ...]]
    uncertainty_scale: float = 0.25
    support_distance_scale: float = 3.0

    @classmethod
    def fit(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        ridge: float = 1e-3,
        uncertainty_scale: float = 0.25,
        support_distance_scale: float = 3.0,
    ) -> ConservativeTemporalResidualModel:
        rows = [row for row in records if row["action_kind"] == ActionKind.REPAIR.value]
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
            grouped.setdefault(str(row["action_id"]), []).append(row)
        weights = {}
        uncertainty = {}
        centers = {}
        scales = {}
        for action_id, action_rows in grouped.items():
            matrix = [
                cls._features(
                    row["public_observation"],
                    row.get("public_history", []),
                    feature_names,
                )
                for row in action_rows
            ]
            targets = [
                float(row["realized_recovery"]) - float(row["predicted_recovery"])
                for row in action_rows
            ]
            fitted = _ridge_fit(matrix, targets, ridge)
            residuals = [
                target - sum(weight * value for weight, value in zip(fitted, features))
                for target, features in zip(targets, matrix)
            ]
            center = tuple(statistics.fmean(row[index] for row in matrix) for index in range(len(matrix[0])))
            scale = tuple(
                max(0.05, statistics.pstdev(row[index] for row in matrix))
                for index in range(len(matrix[0]))
            )
            weights[action_id] = tuple(fitted)
            uncertainty[action_id] = max(
                0.05,
                math.sqrt(statistics.fmean(value * value for value in residuals)),
            )
            centers[action_id] = center
            scales[action_id] = scale
        return cls(
            feature_names,
            weights,
            uncertainty,
            centers,
            scales,
            uncertainty_scale,
            support_distance_scale,
        )

    @staticmethod
    def _features(
        observation: Mapping[str, Any],
        history: list[Any],
        feature_names: tuple[str, ...],
    ) -> list[float]:
        health = observation.get("distinction_health", {})
        previous_observation = (
            getattr(history[-1], "observation", {}) if history else {}
        )
        previous_health = previous_observation.get("distinction_health", {})
        previous_confidence = float(previous_observation.get("confidence", observation.get("confidence", 0.5)))
        previous_unknown = float(previous_observation.get("unknown_probability", observation.get("unknown_probability", 0.5)))
        return [
            1.0,
            *(float(health.get(name, 0.0)) for name in feature_names),
            float(observation.get("confidence", 0.5)),
            float(observation.get("unknown_probability", 0.5)),
            *(float(health.get(name, 0.0)) - float(previous_health.get(name, health.get(name, 0.0))) for name in feature_names),
            float(observation.get("confidence", 0.5)) - previous_confidence,
            float(observation.get("unknown_probability", 0.5)) - previous_unknown,
            float(bool(history and getattr(history[-1], "succeeded", False))),
            min(1.0, len(history) / 4.0),
        ]

    def predict(
        self,
        observation: Mapping[str, Any],
        history: list[Any],
        action_id: str,
    ) -> ConservativeResidualPrediction:
        features = self._features(observation, history, self.feature_names)
        weights = self.weights.get(action_id)
        if weights is None:
            return ConservativeResidualPrediction(0.0, 0.0, 1.0, float("inf"), 0.0)
        raw_residual = sum(weight * value for weight, value in zip(weights, features))
        center = self.support_center[action_id]
        scale = self.support_scale[action_id]
        support_distance = math.sqrt(
            statistics.fmean(
                ((value - mean) / spread) ** 2
                for value, mean, spread in zip(features, center, scale)
            )
        )
        base_uncertainty = float(self.uncertainty[action_id])
        alpha = 1.0 / (
            1.0
            + base_uncertainty / self.uncertainty_scale
            + support_distance / self.support_distance_scale
        )
        alpha = min(1.0, max(0.0, alpha))
        return ConservativeResidualPrediction(
            residual=alpha * raw_residual,
            raw_residual=raw_residual,
            uncertainty=base_uncertainty * (1.0 + support_distance),
            support_distance=support_distance,
            alpha=alpha,
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "weights": {key: list(value) for key, value in sorted(self.weights.items())},
            "uncertainty": dict(sorted(self.uncertainty.items())),
            "support_center": {key: list(value) for key, value in sorted(self.support_center.items())},
            "support_scale": {key: list(value) for key, value in sorted(self.support_scale.items())},
            "uncertainty_scale": self.uncertainty_scale,
            "support_distance_scale": self.support_distance_scale,
        }


class ConservativeHybridQRTCPolicy:
    def __init__(
        self,
        interventions: list[Intervention],
        graph: CompiledGraph,
        residual_model: ConservativeTemporalResidualModel,
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
        candidates = []
        for prediction in self._base.predict_actions(belief, task):
            if not bool(prediction["graph_admissible"]):
                continue
            action = self._actions[str(prediction["action_id"])]
            if action.kind != ActionKind.REPAIR:
                continue
            residual = self._model.predict(observation, history, action.action_id)
            recovery = min(1.0, max(0.0, float(prediction["predicted_recovery"]) + residual.residual))
            score = expected_utility(
                recovery_probability=recovery,
                expected_cost=action.cost,
                expected_harm=action.harm_risk,
                unsafe_probability=action.harm_risk,
                lambda_cost=0.05,
                beta_harm=0.25,
                gamma_unsafe=0.2,
            ) - self._uncertainty_penalty * residual.uncertainty
            candidates.append((score, action.action_id, recovery, residual))
        candidates.sort(key=lambda item: (-item[0], item[1]))

        evidence_actions = [action for action in self._interventions if action.kind == ActionKind.EVIDENCE]
        already_gathered = any(
            outcome.action_id in {action.action_id for action in evidence_actions}
            for outcome in history
        )
        best_uncertainty = candidates[0][3].uncertainty if candidates else 1.0
        best_alpha = candidates[0][3].alpha if candidates else 0.0
        if evidence_actions and not already_gathered and best_uncertainty >= self._evidence_threshold and best_alpha < 0.75:
            evidence = min(evidence_actions, key=lambda action: (action.cost, action.action_id))
            voi = 0.5 * best_uncertainty * (1.0 - best_alpha) - 0.05 * evidence.cost
            if voi > 0.0:
                return self._decision(evidence, voi, 0.0, belief, "Public-signal shift makes reversible evidence valuable")
        if not candidates or candidates[0][0] <= 0.0:
            stop = Intervention("stop", ActionKind.STOP, frozenset(), frozenset(), 0.0)
            return self._decision(stop, 0.0, 0.0, belief, "Conservative fallback found no positive graph-valid action")
        score, action_id, recovery, residual = candidates[0]
        return self._decision(
            self._actions[action_id],
            score,
            recovery,
            belief,
            f"Graph-valid temporal residual with shrinkage alpha={residual.alpha:.6f}",
        )

    @staticmethod
    def _decision(
        action: Intervention,
        score: float,
        recovery: float,
        belief: BeliefState,
        reason: str,
    ) -> PlannerDecision:
        return PlannerDecision(
            action_id=action.action_id,
            kind=action.kind,
            expected_utility=score,
            expected_recovery_probability=recovery,
            expected_cost=action.cost,
            reason=reason,
            lost_distinctions=tuple(),
            candidate_utilities={},
            unknown_fault_probability=belief.unknown_probability,
            safety_gate="passed",
        )