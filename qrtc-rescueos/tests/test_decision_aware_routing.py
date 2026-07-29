from __future__ import annotations

from rescueos.audit.event_log import AuditEventLog
from rescueos.core.distinctions import (
    ActionKind,
    ActionOutcome,
    BeliefState,
    PlannerDecision,
    Task,
)
from rescueos.policies.decision_aware_routing import (
    DecisionAwareIncrementalUtilityRouter,
    DecisionAwareRoutedPolicy,
)
from rescueos.policies.routed_hybrid_qrtc import IncrementalUtilityPrediction


def _decision(action_id: str, utility: float = 0.5) -> PlannerDecision:
    return PlannerDecision(
        action_id=action_id,
        kind=ActionKind.EVIDENCE,
        expected_utility=utility,
        expected_recovery_probability=0.5,
        expected_cost=0.1,
        reason=action_id,
        lost_distinctions=("timing",),
        candidate_utilities={action_id: utility},
        unknown_fault_probability=0.4,
        safety_gate="passed",
    )


class _FixedPolicy:
    def __init__(self, decision: PlannerDecision) -> None:
        self._decision = decision

    def choose(self, belief, task, history) -> PlannerDecision:
        return self._decision


class _CountingRouter:
    threshold = 0.0

    def __init__(self, lower_confidence_bound: float = 1.0) -> None:
        self.calls: list[dict] = []
        self._lower_confidence_bound = lower_confidence_bound

    def predict(self, row) -> IncrementalUtilityPrediction:
        self.calls.append(dict(row))
        return IncrementalUtilityPrediction(
            mean=self._lower_confidence_bound,
            uncertainty=0.0,
            lower_confidence_bound=self._lower_confidence_bound,
            support_distance=0.0,
        )


def _belief() -> BeliefState:
    return BeliefState(
        distinction_health={"timing": 0.4},
        fault_probabilities={},
        unknown_probability=0.6,
        confidence=0.4,
    )


def test_agreement_bypasses_router() -> None:
    shared = _decision("inspect_receiver")
    router = _CountingRouter()
    policy = DecisionAwareRoutedPolicy(
        _FixedPolicy(shared),
        _FixedPolicy(shared),
        router,
    )

    selected = policy.choose(_belief(), Task("task", {"timing": 0.8}, 0.1), [])

    assert selected == shared
    assert router.calls == []


def test_disagreement_routes_with_actual_decision_step() -> None:
    router = _CountingRouter()
    policy = DecisionAwareRoutedPolicy(
        _FixedPolicy(_decision("fallback", 0.4)),
        _FixedPolicy(_decision("specialist", 0.8)),
        router,
    )

    selected = policy.choose(
        _belief(),
        Task("task", {"timing": 0.8}, 0.1),
        [object(), object()],
    )

    assert selected.action_id == "specialist"
    assert router.calls[0]["decision_step"] == 2
    assert router.calls[0]["history_length"] == 0.5
    assert "sition=disagreement" in selected.reason
    assert selected.transit is not None
    assert selected.transit.gate_admitted is True
    assert selected.transit.passage_committed is True
    assert selected.transit.passage_executed is False
    assert selected.transit.destination_realized is False
    assert selected.transit.ingress_erased is False


def test_denied_specialist_retains_v2_without_passage_or_destination() -> None:
    router = _CountingRouter(lower_confidence_bound=-1.0)
    policy = DecisionAwareRoutedPolicy(
        _FixedPolicy(_decision("fallback", 0.4)),
        _FixedPolicy(_decision("specialist", 0.8)),
        router,
    )

    selected = policy.choose(_belief(), Task("task", {"timing": 0.8}, 0.1), [])

    assert selected.action_id == "fallback"
    assert selected.transit is not None
    assert selected.transit.retained_jurisdiction == "baseline_v2"
    assert selected.transit.gate_admitted is False
    assert selected.transit.passage_committed is False
    assert selected.transit.passage_executed is False
    assert selected.transit.destination_branch is None
    assert selected.transit.destination_realized is False
    assert selected.transit.ingress_erased is False

    audit = AuditEventLog()
    audit.record_outcome(
        step=0,
        outcome=ActionOutcome(
            action_id=selected.action_id,
            succeeded=True,
            task_loss=0.0,
            cost=selected.expected_cost,
            harm=0.0,
            observation={"timing": 0.4},
        ),
        decision=selected,
    )
    witness = audit.outcomes[0]["transit_witness"]
    assert witness["gate_admitted"] is False
    assert witness["passage_committed"] is False
    assert witness["passage_executed"] is False
    assert witness["destination_realized"] is False
    assert witness["destination_branch"] is None
    assert witness["ingress_erased"] is False
    assert witness["v2_retained_jurisdiction"] is True


def test_witness_realizes_destination_only_after_executed_passage() -> None:
    router = _CountingRouter()
    policy = DecisionAwareRoutedPolicy(
        _FixedPolicy(_decision("fallback", 0.4)),
        _FixedPolicy(_decision("specialist", 0.8)),
        router,
    )
    selected = policy.choose(_belief(), Task("task", {"timing": 0.8}, 0.1), [])
    outcome = ActionOutcome(
        action_id=selected.action_id,
        succeeded=True,
        task_loss=0.0,
        cost=selected.expected_cost,
        harm=0.0,
        observation={"timing": 0.9},
    )
    audit = AuditEventLog()

    audit.record_outcome(step=0, outcome=outcome, decision=selected)

    witness = audit.outcomes[0]["transit_witness"]
    assert witness["gate_admitted"] is True
    assert witness["passage_committed"] is True
    assert witness["passage_executed"] is True
    assert witness["destination_realized"] is True
    assert witness["destination_branch"] == "specialist_v3"
    assert witness["resulting_action"] == "specialist"
    assert witness["action_succeeded"] is True
    assert witness["ingress_erased"] is True
    assert witness["v2_retained_jurisdiction"] is False


def _training_record(v2_action: str, v3_action: str, label_scope: str) -> dict:
    return {
        "label_scope": label_scope,
        "public_observation": {
            "distinction_health": {"timing": 0.4},
            "confidence": 0.4,
            "unknown_probability": 0.6,
        },
        "history_length": 0.5,
        "v2_action": v2_action,
        "v3_action": v3_action,
        "v2_expected_utility": 0.4,
        "v3_expected_utility": 0.8,
        "incremental_utility": 0.3,
    }


def test_fit_rejects_legacy_trajectory_labels() -> None:
    record = _training_record("fallback", "specialist", "full_trajectory")

    try:
        DecisionAwareIncrementalUtilityRouter.fit(
            [record], lcb_z=1.0, threshold=0.0
        )
    except ValueError as error:
        assert "decision-counterfactual" in str(error)
    else:
        raise AssertionError("legacy trajectory label was accepted")


def test_fit_excludes_agreement_rows() -> None:
    router = DecisionAwareIncrementalUtilityRouter.fit(
        [
            _training_record("shared", "shared", "decision_counterfactual"),
            _training_record("fallback", "specialist", "decision_counterfactual"),
        ],
        lcb_z=1.0,
        threshold=0.0,
    )

    assert "shared" not in router.parameters()["action_names"]
    assert router.parameters()["agreement_rows_routable"] is False