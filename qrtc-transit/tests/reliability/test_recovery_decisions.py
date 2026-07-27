from __future__ import annotations

from qrtc.recovery import decide_recovery, stage_idempotency_key
from qrtc.transit import TransitStage


def test_decide_recovery_marks_send_attempt_as_not_safe_to_automate() -> None:
    decision = decide_recovery(TransitStage.SEND_ATTEMPTED)
    assert decision.action == "mark_delivery_uncertain_until_verified"
    assert decision.safe_to_automate is False


def test_decide_recovery_for_stabilized_resumes_witness() -> None:
    decision = decide_recovery(TransitStage.STABILIZED)
    assert decision.action == "resume_witness_generation"
    assert decision.safe_to_automate is True


def test_stage_idempotency_key_changes_when_payload_changes() -> None:
    base = stage_idempotency_key(
        "t-1",
        "realization",
        "1.0.0",
        component_id="alarm-record-v1",
        payload_digest="digest-a",
    )
    changed = stage_idempotency_key(
        "t-1",
        "realization",
        "1.0.0",
        component_id="alarm-record-v1",
        payload_digest="digest-b",
    )

    assert base != changed
