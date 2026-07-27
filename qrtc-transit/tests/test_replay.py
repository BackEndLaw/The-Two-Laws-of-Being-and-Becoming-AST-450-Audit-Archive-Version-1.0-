from __future__ import annotations

from pathlib import Path

from qrtc.boat import BoatCodec
from qrtc.config import load_input_document
from qrtc.destination import DefaultRealizer
from qrtc.evidence_store import EvidenceStore
from qrtc.pipeline import execute_configured_transit
from qrtc.policy import load_policy_document
from qrtc.registry import (
    ComponentMetadata,
    FrozenComponentRegistry,
    build_default_registry,
)
from qrtc.replay import ReplayEngine, ReplayStatus

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _record_success(tmp_path: Path):
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_record = load_input_document(EXAMPLES / "telemetry-input.json")
    configured, outcome = execute_configured_transit(
        policy, input_record, build_default_registry()
    )
    store = EvidenceStore(tmp_path / "replay.sqlite3")
    store.record_transit(policy, input_record, configured.request, outcome)
    return store, outcome


def test_analysis_replay_reproduces_deterministic_gate_and_boat_outputs(
    tmp_path: Path,
) -> None:
    store, outcome = _record_success(tmp_path)
    report = ReplayEngine(store, build_default_registry()).replay(outcome.transit_id)

    assert report.steps[0].status is ReplayStatus.REPRODUCED
    assert report.steps[1].status is ReplayStatus.INTENTIONALLY_NOT_REEXECUTED
    assert report.steps[3].status is ReplayStatus.REPRODUCED


def test_replay_reports_nondeterministic_operations_honestly(tmp_path: Path) -> None:
    store, outcome = _record_success(tmp_path)

    nondeterministic_registry = FrozenComponentRegistry(
        gates={"telemetry-gate-v1": lambda request, auth: None},
        guards={},
        boats={
            "canonical-json-v1": BoatCodec(
                schema_version="telemetry-interface-v1",
                encoding_version="canonical-json-v1",
            )
        },
        key_policies={},
        realizers={},
        stabilizers={},
        metadata={
            "telemetry-gate-v1": ComponentMetadata(
                component_id="telemetry-gate-v1",
                component_kind="gate",
                version="1.0.0",
                deterministic=False,
                replayable=False,
            ),
            "canonical-json-v1": ComponentMetadata(
                component_id="canonical-json-v1",
                component_kind="boat",
                version="1.0.0",
                deterministic=False,
                replayable=False,
            ),
        },
    )

    report = ReplayEngine(store, nondeterministic_registry).replay(outcome.transit_id)

    assert report.steps[0].status is ReplayStatus.UNAVAILABLE


def test_destination_realization_uses_idempotency_key() -> None:
    realizer = DefaultRealizer(
        destination="archive", policy_version="1.0.0", route_version="route-v1"
    )

    first = realizer.realize(
        {"temperature": 72},
        {},
        transit_id="t-1",
        route_id="route-v1",
        payload_digest="abc",
        idempotency_key="t-1",
    )
    second = realizer.realize(
        {"temperature": 72},
        {},
        transit_id="t-1",
        route_id="route-v1",
        payload_digest="abc",
        idempotency_key="t-1",
    )

    assert first.candidate_id == second.candidate_id
