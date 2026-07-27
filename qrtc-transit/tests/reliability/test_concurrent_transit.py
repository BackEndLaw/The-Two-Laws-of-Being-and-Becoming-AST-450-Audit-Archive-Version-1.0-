from __future__ import annotations

import json
import threading
from pathlib import Path

from qrtc.config import load_input_document
from qrtc.evidence_store import EvidenceStore
from qrtc.pipeline import execute_configured_transit
from qrtc.policy import load_policy_document
from qrtc.registry import build_default_registry

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_concurrent_transits_preserve_separate_histories(tmp_path: Path) -> None:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    base_input = json.loads(
        (EXAMPLES / "telemetry-input.json").read_text(encoding="utf-8")
    )
    db_path = tmp_path / "concurrent.sqlite3"

    def worker(index: int) -> None:
        payload = dict(base_input)
        payload["transit_id"] = f"t-{index}"
        path = tmp_path / f"input-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        input_record = load_input_document(path)
        configured, outcome = execute_configured_transit(
            policy, input_record, build_default_registry()
        )
        store = EvidenceStore(db_path)
        store.record_transit(
            policy,
            input_record,
            configured.request,
            outcome,
            policy_hash=configured.policy_digest,
            registry_snapshot_id=configured.registry_snapshot_id,
            resolved_components=configured.resolved_component_ids,
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    store = EvidenceStore(db_path)
    for i in range(5):
        record = store.inspect(f"t-{i}")
        assert record["current_status"] == "witnessed"
        assert store.verify_chain(f"t-{i}")
