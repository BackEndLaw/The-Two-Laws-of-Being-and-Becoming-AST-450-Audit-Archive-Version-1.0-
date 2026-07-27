from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from qrtc.config import load_input_document
from qrtc.evidence_store import EvidenceStore
from qrtc.pipeline import execute_configured_transit
from qrtc.policy import load_policy_document
from qrtc.registry import build_default_registry

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _store_one(tmp_path: Path) -> tuple[EvidenceStore, str]:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_record = load_input_document(EXAMPLES / "telemetry-input.json")
    configured, outcome = execute_configured_transit(
        policy, input_record, build_default_registry()
    )
    store = EvidenceStore(tmp_path / "hash-chain.sqlite3")
    store.record_transit(
        policy,
        input_record,
        configured.request,
        outcome,
        policy_hash=configured.policy_digest,
        registry_snapshot_id=configured.registry_snapshot_id,
        resolved_components=configured.resolved_component_ids,
    )
    return store, outcome.transit_id


def test_mutation_removal_reordering_insertion_and_splicing_fail(
    tmp_path: Path,
) -> None:
    store, transit_id = _store_one(tmp_path / "mutation")
    assert store.verify_chain(transit_id)

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE stage_events SET payload_json = ? WHERE transit_id = ? AND sequence_number = 1",
            (json.dumps({"changed": True}), transit_id),
        )
        connection.commit()
    assert not EvidenceStore(store.path).verify_chain(transit_id)

    removed_store, removed_transit = _store_one(tmp_path / "removed")
    with sqlite3.connect(removed_store.path) as connection:
        connection.execute(
            "DELETE FROM stage_events WHERE transit_id = ? AND sequence_number = 2",
            (removed_transit,),
        )
        connection.commit()
    assert not EvidenceStore(removed_store.path).verify_chain(removed_transit)

    inserted_store, inserted_transit = _store_one(tmp_path / "inserted")
    with sqlite3.connect(inserted_store.path) as connection:
        connection.execute(
            """
            INSERT INTO stage_events (
                transit_id, sequence_number, event_type, stage, occurred_at,
                component_id, previous_hash, event_hash, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inserted_transit,
                99,
                "injected",
                "encoded",
                "2026-01-01T00:00:00+00:00",
                "evil",
                "x",
                "y",
                json.dumps({"injected": True}),
            ),
        )
        connection.commit()
    assert not EvidenceStore(inserted_store.path).verify_chain(inserted_transit)

    reordered_store, reordered_transit = _store_one(tmp_path / "reordered")
    with sqlite3.connect(reordered_store.path) as connection:
        first = connection.execute(
            "SELECT payload_json FROM stage_events WHERE transit_id = ? AND sequence_number = 3",
            (reordered_transit,),
        ).fetchone()[0]
        second = connection.execute(
            "SELECT payload_json FROM stage_events WHERE transit_id = ? AND sequence_number = 4",
            (reordered_transit,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE stage_events SET payload_json = ? WHERE transit_id = ? AND sequence_number = 3",
            (second, reordered_transit),
        )
        connection.execute(
            "UPDATE stage_events SET payload_json = ? WHERE transit_id = ? AND sequence_number = 4",
            (first, reordered_transit),
        )
        connection.commit()
    assert not EvidenceStore(reordered_store.path).verify_chain(reordered_transit)

    spliced_store, first_id = _store_one(tmp_path / "spliced")
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    second_input = load_input_document(EXAMPLES / "telemetry-input.json")
    second_input = second_input.__class__(
        transit_id="telemetry-other",
        principal=second_input.principal,
        destination=second_input.destination,
        expiration=second_input.expiration,
        interface_projection=dict(second_input.interface_projection),
        context=dict(second_input.context),
    )
    configured, outcome = execute_configured_transit(
        policy, second_input, build_default_registry()
    )
    spliced_store.record_transit(
        policy,
        second_input,
        configured.request,
        outcome,
        policy_hash=configured.policy_digest,
        registry_snapshot_id=configured.registry_snapshot_id,
        resolved_components=configured.resolved_component_ids,
    )
    with sqlite3.connect(spliced_store.path) as connection:
        donor = connection.execute(
            "SELECT payload_json FROM stage_events WHERE transit_id = ? AND sequence_number = 0",
            ("telemetry-other",),
        ).fetchone()[0]
        connection.execute(
            "UPDATE stage_events SET payload_json = ? WHERE transit_id = ? AND sequence_number = 0",
            (donor, first_id),
        )
        connection.commit()
    assert not EvidenceStore(spliced_store.path).verify_chain(first_id)
