from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from rescueos.core.distinctions import ActionKind, BeliefState, PlannerDecision, Task
from rescueos.audit.event_log import AuditEventLog
from rescueos.experiments.routed_v4_benchmark import (
    _graph_invalid_first_action,
    run_routed_v4,
)
from rescueos.policies.routed_hybrid_qrtc import (
    PublicIncrementalUtilityRouter,
    RoutedHybridQRTCPolicy,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _record(health: float, v2_action: str, v3_action: str, increment: float) -> dict:
    return {
        "public_observation": {
            "distinction_health": {"timing": health},
            "confidence": health,
            "unknown_probability": 1.0 - health,
        },
        "history_length": 0.0,
        "v2_action": v2_action,
        "v3_action": v3_action,
        "v2_expected_utility": 0.4,
        "v3_expected_utility": 0.8,
        "incremental_utility": increment,
    }


def _decision(action_id: str, utility: float) -> PlannerDecision:
    return PlannerDecision(
        action_id=action_id,
        kind=ActionKind.REPAIR,
        expected_utility=utility,
        expected_recovery_probability=0.8,
        expected_cost=0.1,
        reason=action_id,
        lost_distinctions=("timing",),
        candidate_utilities={action_id: utility},
        unknown_fault_probability=0.2,
        safety_gate="pass",
    )


class _FixedPolicy:
    def __init__(self, decision: PlannerDecision) -> None:
        self.decision = decision

    def choose(self, belief, task, history) -> PlannerDecision:
        return self.decision


def test_router_parameters_use_only_public_fields() -> None:
    router = PublicIncrementalUtilityRouter.fit(
        [
            _record(0.2, "fallback", "specialist", 0.5),
            _record(0.3, "fallback", "specialist", 0.4),
            _record(0.8, "fallback", "fallback", 0.0),
        ],
        lcb_z=1.0,
        threshold=0.0,
    )
    serialized = repr(router.parameters())

    assert "mechanism_id" not in serialized
    assert "mechanism_family" not in serialized
    assert "hidden_parameters" not in serialized
    assert "fault_id" not in serialized
    assert "oracle" not in serialized


def test_routed_policy_uses_strict_lcb_and_defaults_to_v2() -> None:
    router = PublicIncrementalUtilityRouter.fit(
        [
            _record(0.2, "fallback", "specialist", 0.6),
            _record(0.2, "fallback", "specialist", 0.6),
            _record(0.2, "fallback", "specialist", 0.6),
        ],
        lcb_z=0.0,
        threshold=0.0,
    )
    belief = BeliefState(
        distinction_health={"timing": 0.2},
        fault_probabilities={},
        unknown_probability=0.8,
        confidence=0.2,
    )
    task = Task("task", {"timing": 0.8}, 0.1)
    routed = RoutedHybridQRTCPolicy(
        _FixedPolicy(_decision("fallback", 0.4)),
        _FixedPolicy(_decision("specialist", 0.8)),
        router,
    )

    specialist = routed.choose(belief, task, [])
    fallback = RoutedHybridQRTCPolicy(
        routed._v2,
        routed._v3,
        replace(router, threshold=10.0),
    ).choose(belief, task, [])

    assert specialist.action_id == "specialist"
    assert "route=specialist" in specialist.reason
    assert fallback.action_id == "fallback"
    assert "route=v2_fallback" in fallback.reason


def test_routed_v4_requires_frozen_one_shot_protocol(tmp_path: Path) -> None:
    protocol = json.loads((REPO_ROOT / "configs" / "adaptive_v4_protocol.json").read_text())
    protocol["one_shot_execution"] = False
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")

    with pytest.raises(ValueError, match="frozen and one-shot"):
        run_routed_v4(
            REPO_ROOT / "configs" / "communication_system.yaml",
            REPO_ROOT / "configs" / "development_mechanisms.json",
            REPO_ROOT / "configs" / "hidden_mechanisms.json",
            REPO_ROOT / "configs" / "hidden_mechanisms.lock.json",
            REPO_ROOT / "configs" / "adaptive_v4_fresh_mechanisms.json",
            path,
        )


def test_routed_v4_rejects_reused_mechanism_ids(tmp_path: Path) -> None:
    fresh = json.loads((REPO_ROOT / "configs" / "adaptive_v4_fresh_mechanisms.json").read_text())
    fresh["mechanisms"][0]["mechanism_id"] = "dev_gain_dropout"
    path = tmp_path / "fresh.json"
    path.write_text(json.dumps(fresh), encoding="utf-8")

    with pytest.raises(ValueError, match="disjoint"):
        run_routed_v4(
            REPO_ROOT / "configs" / "communication_system.yaml",
            REPO_ROOT / "configs" / "development_mechanisms.json",
            REPO_ROOT / "configs" / "hidden_mechanisms.json",
            REPO_ROOT / "configs" / "hidden_mechanisms.lock.json",
            path,
            REPO_ROOT / "configs" / "adaptive_v4_protocol.json",
        )


def test_graph_validity_accepts_registered_evidence_action() -> None:
    row = {"first_action": "inspect_receiver"}

    assert not _graph_invalid_first_action(row, AuditEventLog(), {"inspect_receiver"})