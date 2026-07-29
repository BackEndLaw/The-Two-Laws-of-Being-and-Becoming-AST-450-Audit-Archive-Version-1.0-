from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Any, Iterable, Mapping

from rescueos.core.distinctions import BeliefState, PlannerDecision, Task
from rescueos.policies.hybrid_qrtc import _ridge_fit


@dataclass(frozen=True)
class IncrementalUtilityPrediction:
    mean: float
    uncertainty: float
    lower_confidence_bound: float
    support_distance: float


@dataclass(frozen=True)
class PublicIncrementalUtilityRouter:
    distinction_names: tuple[str, ...]
    action_names: tuple[str, ...]
    weights: tuple[float, ...]
    residual_uncertainty: float
    support_center: tuple[float, ...]
    support_scale: tuple[float, ...]
    lcb_z: float
    threshold: float

    @classmethod
    def fit(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        lcb_z: float,
        threshold: float,
        ridge: float = 1e-3,
    ) -> PublicIncrementalUtilityRouter:
        rows = list(records)
        distinctions = tuple(
            sorted(
                {
                    name
                    for row in rows
                    for name in row["public_observation"]["distinction_health"]
                }
            )
        )
        actions = tuple(
            sorted(
                {
                    str(row[action_field])
                    for row in rows
                    for action_field in ("v2_action", "v3_action")
                }
            )
        )
        matrix = [cls._features(row, distinctions, actions) for row in rows]
        targets = [float(row["incremental_utility"]) for row in rows]
        weights = tuple(_ridge_fit(matrix, targets, ridge))
        residuals = [
            target - sum(weight * value for weight, value in zip(weights, features))
            for target, features in zip(targets, matrix)
        ]
        center = tuple(
            statistics.fmean(row[index] for row in matrix)
            for index in range(len(matrix[0]))
        )
        scale = tuple(
            max(0.05, statistics.pstdev(row[index] for row in matrix))
            for index in range(len(matrix[0]))
        )
        return cls(
            distinctions,
            actions,
            weights,
            max(0.01, math.sqrt(statistics.fmean(value * value for value in residuals))),
            center,
            scale,
            lcb_z,
            threshold,
        )

    @staticmethod
    def _features(
        row: Mapping[str, Any],
        distinctions: tuple[str, ...],
        actions: tuple[str, ...],
    ) -> list[float]:
        observation = row["public_observation"]
        health = observation["distinction_health"]
        v2_action = str(row["v2_action"])
        v3_action = str(row["v3_action"])
        return [
            1.0,
            *(float(health.get(name, 0.0)) for name in distinctions),
            float(observation.get("confidence", 0.5)),
            float(observation.get("unknown_probability", 0.5)),
            float(row.get("history_length", 0.0)),
            float(row["v2_expected_utility"]),
            float(row["v3_expected_utility"]),
            float(row["v3_expected_utility"]) - float(row["v2_expected_utility"]),
            float(v2_action == v3_action),
            *(float(v2_action == action) for action in actions),
            *(float(v3_action == action) for action in actions),
        ]

    def predict(self, row: Mapping[str, Any]) -> IncrementalUtilityPrediction:
        features = self._features(row, self.distinction_names, self.action_names)
        mean = sum(weight * value for weight, value in zip(self.weights, features))
        support_distance = math.sqrt(
            statistics.fmean(
                ((value - center) / scale) ** 2
                for value, center, scale in zip(
                    features, self.support_center, self.support_scale
                )
            )
        )
        uncertainty = self.residual_uncertainty * (1.0 + support_distance)
        return IncrementalUtilityPrediction(
            mean=mean,
            uncertainty=uncertainty,
            lower_confidence_bound=mean - self.lcb_z * uncertainty,
            support_distance=support_distance,
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "distinction_names": list(self.distinction_names),
            "action_names": list(self.action_names),
            "weights": list(self.weights),
            "residual_uncertainty": self.residual_uncertainty,
            "support_center": list(self.support_center),
            "support_scale": list(self.support_scale),
            "lcb_z": self.lcb_z,
            "threshold": self.threshold,
        }


class RoutedHybridQRTCPolicy:
    def __init__(self, v2_policy, v3_policy, router: PublicIncrementalUtilityRouter) -> None:
        self._v2 = v2_policy
        self._v3 = v3_policy
        self._router = router

    def choose(self, belief: BeliefState, task: Task, history: list) -> PlannerDecision:
        v2 = self._v2.choose(belief, task, history)
        v3 = self._v3.choose(belief, task, history)
        public_observation = {
            "distinction_health": dict(belief.distinction_health),
            "confidence": belief.confidence,
            "unknown_probability": belief.unknown_probability,
        }
        prediction = self._router.predict(
            {
                "public_observation": public_observation,
                "history_length": min(1.0, len(history) / 4.0),
                "v2_action": v2.action_id,
                "v3_action": v3.action_id,
                "v2_expected_utility": v2.expected_utility,
                "v3_expected_utility": v3.expected_utility,
            }
        )
        activate = prediction.lower_confidence_bound > self._router.threshold
        selected = v3 if activate else v2
        route = "specialist" if activate else "v2_fallback"
        return PlannerDecision(
            action_id=selected.action_id,
            kind=selected.kind,
            expected_utility=selected.expected_utility,
            expected_recovery_probability=selected.expected_recovery_probability,
            expected_cost=selected.expected_cost,
            reason=(
                f"route={route};incremental_mean={prediction.mean:.6f};"
                f"incremental_lcb={prediction.lower_confidence_bound:.6f};"
                f"support_distance={prediction.support_distance:.6f};"
                f"selected={selected.reason}"
            ),
            lost_distinctions=selected.lost_distinctions,
            candidate_utilities=selected.candidate_utilities,
            unknown_fault_probability=selected.unknown_fault_probability,
            safety_gate=selected.safety_gate,
        )