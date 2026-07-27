from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from qrtc.config import load_input_document
from qrtc.evidence_store import EvidenceStore
from qrtc.exceptions import IdempotencyConflictError
from qrtc.pipeline import execute_configured_transit
from qrtc.policy import load_policy_document
from qrtc.recovery import (
    IdempotencyLedger,
    IdempotencyResolution,
    stage_idempotency_key,
)
from qrtc.registry import build_default_registry

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_idempotency_ledger_distinguishes_first_repeat_and_conflict() -> None:
    ledger = IdempotencyLedger()
    key = stage_idempotency_key("t-1", "realized", "alarm-record-v1")

    first = ledger.register(key, "digest-a")
    repeat = ledger.register(key, "digest-a")
    conflict = ledger.register(key, "digest-b")

    assert first is IdempotencyResolution.FIRST_REALIZATION
    assert repeat is IdempotencyResolution.REPEATED_IDENTICAL_REALIZATION
    assert conflict is IdempotencyResolution.CONFLICTING_REALIZATION


def test_repeated_identical_idempotency_is_accepted(tmp_path: Path) -> None:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_record = load_input_document(EXAMPLES / "telemetry-input.json")
    configured, outcome = execute_configured_transit(
        policy, input_record, build_default_registry()
    )

    store = EvidenceStore(tmp_path / "idempotency.sqlite3")
    store.record_transit(policy, input_record, configured.request, outcome)

    repeated_outcome = replace(
        outcome,
        transit_id="telemetry-retry-identical",
        candidate_successor=replace(
            outcome.candidate_successor,
            transit_id="telemetry-retry-identical",
        )
        if outcome.candidate_successor is not None
        else None,
    )
    repeated_request = replace(
        configured.request, transit_id="telemetry-retry-identical"
    )
    repeated_input = replace(input_record, transit_id="telemetry-retry-identical")

    store.record_transit(policy, repeated_input, repeated_request, repeated_outcome)


def test_conflicting_idempotency_key_is_rejected(tmp_path: Path) -> None:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_record = load_input_document(EXAMPLES / "telemetry-input.json")
    configured, outcome = execute_configured_transit(
        policy, input_record, build_default_registry()
    )

    assert outcome.candidate_successor is not None

    store = EvidenceStore(tmp_path / "idempotency-conflict.sqlite3")
    store.record_transit(policy, input_record, configured.request, outcome)

    conflicting_outcome = replace(
        outcome,
        transit_id="telemetry-retry-conflict",
        candidate_successor=replace(
            outcome.candidate_successor,
            transit_id="telemetry-retry-conflict",
            payload_digest="different-payload-digest",
        ),
    )
    conflicting_request = replace(
        configured.request, transit_id="telemetry-retry-conflict"
    )
    conflicting_input = replace(input_record, transit_id="telemetry-retry-conflict")

    with pytest.raises(IdempotencyConflictError):
        store.record_transit(
            policy,
            conflicting_input,
            conflicting_request,
            conflicting_outcome,
        )
