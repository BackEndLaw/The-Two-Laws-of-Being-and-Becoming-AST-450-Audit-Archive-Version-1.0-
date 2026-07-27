from __future__ import annotations

import json
from pathlib import Path

from qrtc.config import load_input_document
from qrtc.evidence_store import EvidenceStore
from qrtc.pipeline import execute_configured_transit
from qrtc.policy import load_policy_document
from qrtc.registry import build_default_registry

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_sensitive_fields_are_redacted_in_persistence(tmp_path: Path) -> None:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_data = json.loads(
        (EXAMPLES / "telemetry-input.json").read_text(encoding="utf-8")
    )
    input_data["context"]["api_token"] = "secret-value"
    input_data["interface_projection"]["password"] = "secret-pass"

    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(input_data), encoding="utf-8")
    input_record = load_input_document(input_path)

    configured, outcome = execute_configured_transit(
        policy, input_record, build_default_registry()
    )
    store = EvidenceStore(tmp_path / "evidence.sqlite3")
    store.record_transit(
        policy,
        input_record,
        configured.request,
        outcome,
        policy_hash=configured.policy_digest,
        registry_snapshot_id=configured.registry_snapshot_id,
        resolved_components=configured.resolved_component_ids,
    )

    record = store.inspect(outcome.transit_id)
    assert record["request"]["input"]["context"]["api_token"] == "[REDACTED]"
    assert (
        record["request"]["input"]["interface_projection"]["password"] == "[REDACTED]"
    )
