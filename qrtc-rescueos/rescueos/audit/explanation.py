from __future__ import annotations

from rescueos.core.distinctions import PlannerDecision


def build_explanation(task_id: str, task_loss_before: float, decision: PlannerDecision) -> dict:
    return {
        "task": task_id,
        "task_loss_before": task_loss_before,
        "lost_distinctions": list(decision.lost_distinctions),
        "candidate_actions": dict(decision.candidate_utilities),
        "selected_action": decision.action_id,
        "reason": decision.reason,
        "expected_recovery_probability": decision.expected_recovery_probability,
        "expected_cost": decision.expected_cost,
        "unknown_fault_probability": decision.unknown_fault_probability,
        "safety_gate": decision.safety_gate,
    }
