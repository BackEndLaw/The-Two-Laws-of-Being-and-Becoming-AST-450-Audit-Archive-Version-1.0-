from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from qrtc.config import load_input_document
from qrtc.evidence_store import EvidenceStore
from qrtc.pipeline import execute_configured_transit
from qrtc.policy import load_policy_document
from qrtc.registry import build_default_registry

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _run_successful_transit(tmp_path: Path):
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_record = load_input_document(EXAMPLES / "telemetry-input.json")
    configured, outcome = execute_configured_transit(
        policy, input_record, build_default_registry()
    )
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.record_transit(policy, input_record, configured.request, outcome)
    return store, policy, input_record, configured, outcome


def test_successful_transit_is_durably_persisted(tmp_path: Path) -> None:
    store, _policy, _input_record, _configured, outcome = _run_successful_transit(
        tmp_path
    )

    reopened = EvidenceStore(store.path)
    record = reopened.inspect(outcome.transit_id)

    assert record["current_status"] == "witnessed"
    assert record["failure_state"] is None
    assert record["stage_history"]
    assert reopened.verify_chain(outcome.transit_id)
    assert "raw_predecessor" not in record["request"]["input"]
    assert record["request"]["input"]["interface_projection"]["temperature"] == 72


def test_failed_transit_retains_stage_specific_evidence(tmp_path: Path) -> None:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_document = json.loads(
        (EXAMPLES / "telemetry-input.json").read_text(encoding="utf-8")
    )
    input_document["interface_projection"].pop("pressure")

    bad_input_path = tmp_path / "bad-input.json"
    bad_input_path.write_text(json.dumps(input_document), encoding="utf-8")
    input_record = load_input_document(bad_input_path)

    configured, outcome = execute_configured_transit(
        policy, input_record, build_default_registry()
    )
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.record_transit(policy, input_record, configured.request, outcome)

    record = store.inspect(outcome.transit_id)

    assert record["current_status"] == "qualified"
    assert record["failure_state"] == "rejected_by_guard"
    assert any(event["event_type"] == "guard" for event in record["stage_history"])
    assert any(
        event["event_type"] == "authorization" for event in record["stage_history"]
    )


def test_tampering_breaks_chain_verification(tmp_path: Path) -> None:
    store, _policy, _input_record, _configured, outcome = _run_successful_transit(
        tmp_path
    )

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE stage_events SET payload_json = ? WHERE transit_id = ? AND sequence_number = 1",
            (json.dumps({"tampered": True}), outcome.transit_id),
        )
        connection.commit()

    reopened = EvidenceStore(store.path)
    assert not reopened.verify_chain(outcome.transit_id)
