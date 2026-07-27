from __future__ import annotations

from pathlib import Path

from qrtc.config import load_input_document
from qrtc.evidence_store import EvidenceStore
from qrtc.pipeline import execute_configured_transit
from qrtc.policy import load_policy_document
from qrtc.registry import build_default_registry

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_restart_does_not_mutate_existing_stage_history(tmp_path: Path) -> None:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_record = load_input_document(EXAMPLES / "telemetry-input.json")
    configured, outcome = execute_configured_transit(
        policy, input_record, build_default_registry()
    )
    db_path = tmp_path / "recover.sqlite3"

    first_store = EvidenceStore(db_path)
    first_store.record_transit(
        policy,
        input_record,
        configured.request,
        outcome,
        policy_hash=configured.policy_digest,
        registry_snapshot_id=configured.registry_snapshot_id,
        resolved_components=configured.resolved_component_ids,
    )
    first_count = len(first_store.inspect(outcome.transit_id)["stage_history"])

    second_store = EvidenceStore(db_path)
    second_count = len(second_store.inspect(outcome.transit_id)["stage_history"])
    assert first_count == second_count
