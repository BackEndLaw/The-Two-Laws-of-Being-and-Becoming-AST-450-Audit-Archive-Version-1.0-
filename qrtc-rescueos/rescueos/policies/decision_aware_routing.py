from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from rescueos.core.distinctions import (
    BeliefState,
    PlannerDecision,
    Task,
    TransitCommitment,
)
from rescueos.policies.routed_hybrid_qrtc import IncrementalUtilityPrediction


class DecisionRouter(Protocol):
    threshold: float

    def predict(self, row: Mapping[str, Any]) -> IncrementalUtilityPrediction: ...


@dataclass(frozen=True)
class DecisionAwareIncrementalUtilityRouter:
    _router: Any

    @property
    def threshold(self) -> float:
        return float(self._router.threshold)

    @classmethod
    def fit(
        cls,
        records: Iterable[Mapping[str, Any]],
        *,
        lcb_z: float,
        threshold: float,
        ridge: float = 1e-3,
    ) -> DecisionAwareIncrementalUtilityRouter:
        from rescueos.policies.routed_hybrid_qrtc import PublicIncrementalUtilityRouter

        rows = []
        for record in records:
            if record.get("label_scope") != "decision_counterfactual":
                raise ValueError("Decision-aware routing requires decision-counterfactual labels")
            if str(record["v2_action"]) == str(record["v3_action"]):
                continue
            rows.append(record)
        if not rows:
            raise ValueError("Decision-aware routing requires at least one disagreement record")
        return cls(
            PublicIncrementalUtilityRouter.fit(
                rows,
                lcb_z=lcb_z,
                threshold=threshold,
                ridge=ridge,
            )
        )

    def predict(self, row: Mapping[str, Any]) -> IncrementalUtilityPrediction:
        return self._router.predict(row)

    def parameters(self) -> dict[str, Any]:
        parameters = self._router.parameters()
        parameters["label_scope"] = "decision_counterfactual"
        parameters["agreement_rows_routable"] = False
        return parameters


class DecisionAwareRoutedPolicy:
    """Route only where the baseline and specialist propose different actions."""

    def __init__(self, v2_policy, v3_policy, router: DecisionRouter) -> None:
        self._v2 = v2_policy
        self._v3 = v3_policy
        self._router = router

    def choose(self, belief: BeliefState, task: Task, history: list) -> PlannerDecision:
        v2 = self._v2.choose(belief, task, history)
        v3 = self._v3.choose(belief, task, history)
        if v2.action_id == v3.action_id:
            return v2

        prediction = self._router.predict(
            {
                "public_observation": {
                    "distinction_health": dict(belief.distinction_health),
                    "confidence": belief.confidence,
                    "unknown_probability": belief.unknown_probability,
                },
                "decision_step": len(history),
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
                f"sition=disagreement;route={route};"
                f"incremental_mean={prediction.mean:.6f};"
                f"incremental_lcb={prediction.lower_confidence_bound:.6f};"
                f"support_distance={prediction.support_distance:.6f};"
                f"selected={selected.reason}"
            ),
            lost_distinctions=selected.lost_distinctions,
            candidate_utilities=selected.candidate_utilities,
            unknown_fault_probability=selected.unknown_fault_probability,
            safety_gate=selected.safety_gate,
            transit=TransitCommitment(
                candidate_branch="specialist_v3",
                gate_admitted=activate,
                passage_committed=activate,
                retained_jurisdiction=None if activate else "baseline_v2",
            ),
        )