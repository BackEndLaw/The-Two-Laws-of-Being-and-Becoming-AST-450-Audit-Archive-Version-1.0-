from __future__ import annotations

from datetime import UTC, datetime

from qrtc.boat import BoatCodec
from qrtc.destination import DefaultRealizer, DefaultStabilizer
from qrtc.guards import GuardRule
from qrtc.key import TransitKey
from qrtc.pipeline import TransitPipeline, build_success_demo_pipeline
from qrtc.river import SimulatedDirectedRiver
from qrtc.transit import (
    StabilizationResult,
    TransitEnvelope,
    TransitFailureState,
    TransitRequest,
    TransitStage,
)


def _request() -> TransitRequest:
    return TransitRequest(
        transit_id="t-1",
        principal="authorized-operator",
        predecessor_class="equipment",
        declared_future="telemetry-payload",
        destination="archive",
        expiration=datetime(2099, 1, 1, tzinfo=UTC),
        policy_version="policy-v1",
        route_version="route-v1",
        schema_version="schema-v1",
        encoding_version="json-v1",
        interface={"temperature": 64, "pressure": 12},
    )


def test_valid_request_completes_transit_chain() -> None:
    pipeline = build_success_demo_pipeline()
    outcome = pipeline.execute(_request())

    assert outcome.stage is TransitStage.WITNESSED
    assert outcome.failure_state is None
    assert outcome.authorization.qualified
    assert outcome.envelope is not None
    assert outcome.canonical_bytes is not None
    assert outcome.payload_digest is not None
    assert outcome.delivery_evidence is not None
    assert outcome.candidate_successor is not None
    assert outcome.stabilization_result is not None
    assert outcome.witness_record is not None
    assert outcome.witness_record.facts


def test_key_rejection_prevents_gate_execution() -> None:
    gate_calls: list[str] = []

    key = TransitKey(
        key_id="demo-key",
        principal="authorized-operator",
        predecessor_class="equipment",
        declared_future="telemetry-payload",
        destination="archive",
        expiration=datetime(2099, 1, 1, tzinfo=UTC),
        policy_version="policy-v1",
    )
    river = SimulatedDirectedRiver(route_id="route-v1", sender_id="s", receiver_id="r")
    pipeline = TransitPipeline(
        key=key,
        gate=lambda request, auth: (
            gate_calls.append(request.transit_id)
            or TransitEnvelope(
                transit_id=request.transit_id,
                principal=request.principal,
                predecessor_class=request.predecessor_class,
                declared_future=request.declared_future,
                destination=request.destination,
                policy_version=request.policy_version,
                route_version=request.route_version,
                schema_version=request.schema_version,
                encoding_version=request.encoding_version,
                authorization=auth,
                interface=request.interface,
            )
        ),
        guards=(),
        boat=BoatCodec(schema_version="schema-v1", encoding_version="json-v1"),
        sender=river.sender(),
        receiver=river.receiver(),
        realizer=DefaultRealizer(
            destination="archive", policy_version="policy-v1", route_version="route-v1"
        ),
        stabilizer=DefaultStabilizer(
            stabilizer_id="stabilizer-v1",
            policy_version="policy-v1",
            route_version="route-v1",
        ),
    )

    outcome = pipeline.execute(
        _request().__class__(
            transit_id="t-1",
            principal="unauthorized",
            predecessor_class="equipment",
            declared_future="telemetry-payload",
            destination="archive",
            expiration=datetime(2099, 1, 1, tzinfo=UTC),
            policy_version="policy-v1",
            route_version="route-v1",
            schema_version="schema-v1",
            encoding_version="json-v1",
            interface={"temperature": 64},
        )
    )

    assert outcome.failure_state is TransitFailureState.REJECTED_BY_KEY
    assert not gate_calls
    assert outcome.envelope is None


def test_guard_rejection_prevents_encoding_and_transmission() -> None:
    pipeline = build_success_demo_pipeline()
    pipeline = TransitPipeline(
        key=pipeline.key,
        gate=pipeline.gate,
        guards=(
            GuardRule(
                guard_id="telemetry-schema",
                policy_version="policy-v1",
                predicate=lambda envelope: False,
                pass_reason="schema accepted",
                fail_reason="schema rejected",
            ),
        ),
        boat=pipeline.boat,
        sender=pipeline.sender,
        receiver=pipeline.receiver,
        realizer=pipeline.realizer,
        stabilizer=pipeline.stabilizer,
    )

    outcome = pipeline.execute(_request())

    assert outcome.failure_state is TransitFailureState.REJECTED_BY_GUARD
    assert outcome.canonical_bytes is None
    assert outcome.delivery_evidence is None


def test_payload_modification_causes_integrity_failure() -> None:
    pipeline = build_success_demo_pipeline()

    original_receiver = pipeline.receiver

    class TamperingReceiver:
        def receive(self):
            receipt = original_receiver.receive()
            tampered_envelope = receipt.envelope.with_payload(
                receipt.envelope.payload_bytes or b"",
                "tampered-digest",
            )
            return receipt.__class__(
                route_id=receipt.route_id,
                transit_id=receipt.transit_id,
                sequence_number=receipt.sequence_number,
                sent_at=receipt.sent_at,
                received_at=receipt.received_at,
                payload_digest=receipt.payload_digest,
                envelope=tampered_envelope,
                delivery_status=receipt.delivery_status,
            )

    pipeline = TransitPipeline(
        key=pipeline.key,
        gate=pipeline.gate,
        guards=pipeline.guards,
        boat=pipeline.boat,
        sender=pipeline.sender,
        receiver=TamperingReceiver(),
        realizer=pipeline.realizer,
        stabilizer=pipeline.stabilizer,
    )

    outcome = pipeline.execute(_request())

    assert outcome.failure_state is TransitFailureState.INTEGRITY_FAILED
    assert outcome.stage is TransitStage.DELIVERY_CONFIRMED
    assert outcome.candidate_successor is None


def test_send_failure_reports_send_pending_boundary() -> None:
    pipeline = build_success_demo_pipeline()

    class FailingSender:
        def __init__(self, route_id: str) -> None:
            self.river = type("RiverInfo", (), {"route_id": route_id})()

        def send(self, envelope):
            raise ValueError("send failed")

    pipeline = TransitPipeline(
        key=pipeline.key,
        gate=pipeline.gate,
        guards=pipeline.guards,
        boat=pipeline.boat,
        sender=FailingSender("route-v1"),
        receiver=pipeline.receiver,
        realizer=pipeline.realizer,
        stabilizer=pipeline.stabilizer,
    )

    outcome = pipeline.execute(_request())

    assert outcome.failure_state is TransitFailureState.DELIVERY_FAILED
    assert outcome.stage is TransitStage.SEND_PENDING


def test_realization_error_reports_realization_pending_boundary() -> None:
    pipeline = build_success_demo_pipeline()

    class FailingRealizer:
        destination = "archive"
        policy_version = "policy-v1"

        def realize(self, interface, context, **kwargs):
            raise RuntimeError("realization failed")

    pipeline = TransitPipeline(
        key=pipeline.key,
        gate=pipeline.gate,
        guards=pipeline.guards,
        boat=pipeline.boat,
        sender=pipeline.sender,
        receiver=pipeline.receiver,
        realizer=FailingRealizer(),
        stabilizer=pipeline.stabilizer,
    )

    outcome = pipeline.execute(_request())

    assert outcome.failure_state is TransitFailureState.REALIZATION_FAILED
    assert outcome.stage is TransitStage.REALIZATION_PENDING


def test_send_without_receive_confirmation_is_uncertain() -> None:
    pipeline = build_success_demo_pipeline()

    class FailingReceiver:
        def receive(self):
            raise LookupError("delivery confirmation unavailable")

    pipeline = TransitPipeline(
        key=pipeline.key,
        gate=pipeline.gate,
        guards=pipeline.guards,
        boat=pipeline.boat,
        sender=pipeline.sender,
        receiver=FailingReceiver(),
        realizer=pipeline.realizer,
        stabilizer=pipeline.stabilizer,
    )

    outcome = pipeline.execute(_request())

    assert outcome.failure_state is TransitFailureState.DELIVERY_UNCERTAIN
    assert outcome.stage is TransitStage.SEND_ATTEMPTED
    assert outcome.candidate_successor is None


def test_realization_without_stabilization_is_not_reported_as_success() -> None:
    pipeline = build_success_demo_pipeline()

    class FailingStabilizer:
        def stabilize(self, candidate):
            return StabilizationResult(
                transit_id=candidate.transit_id,
                route_id=candidate.route_id,
                candidate_id=candidate.candidate_id,
                stable=False,
                reason="not stable",
                policy_version=candidate.policy_version,
                route_version=candidate.route_version,
                destination=candidate.destination,
            )

    pipeline = TransitPipeline(
        key=pipeline.key,
        gate=pipeline.gate,
        guards=pipeline.guards,
        boat=pipeline.boat,
        sender=pipeline.sender,
        receiver=pipeline.receiver,
        realizer=pipeline.realizer,
        stabilizer=FailingStabilizer(),
    )

    outcome = pipeline.execute(_request())

    assert outcome.failure_state is TransitFailureState.STABILIZATION_FAILED
    assert outcome.stabilization_result is not None
    assert not outcome.stabilization_result.stable
    assert outcome.stage is TransitStage.REALIZED


def test_stabilizer_exception_reports_stabilization_pending_boundary() -> None:
    pipeline = build_success_demo_pipeline()

    class ErroringStabilizer:
        def stabilize(self, candidate):
            raise RuntimeError("stabilizer unavailable")

    pipeline = TransitPipeline(
        key=pipeline.key,
        gate=pipeline.gate,
        guards=pipeline.guards,
        boat=pipeline.boat,
        sender=pipeline.sender,
        receiver=pipeline.receiver,
        realizer=pipeline.realizer,
        stabilizer=ErroringStabilizer(),
    )

    outcome = pipeline.execute(_request())

    assert outcome.failure_state is TransitFailureState.STABILIZATION_FAILED
    assert outcome.stage is TransitStage.STABILIZATION_PENDING


def test_witness_records_are_categorized_and_redacted() -> None:
    outcome = build_success_demo_pipeline().execute(_request())
    witness = outcome.witness_record

    assert witness is not None
    categories = {fact.category.value for fact in witness.facts}
    assert categories == {"observed", "asserted", "derived", "unverified"}

    witness_payload = witness.as_dict()
    assert "interface" not in witness_payload
    assert "principal" not in witness_payload
    assert "credentials" not in witness_payload


def test_every_outcome_identifies_versions() -> None:
    outcome = build_success_demo_pipeline().execute(_request())

    assert outcome.policy_version == "policy-v1"
    assert outcome.schema_version == "schema-v1"
    assert outcome.encoding_version == "json-v1"
    assert outcome.route_version == "route-v1"
    assert outcome.witness_record is not None
    assert outcome.witness_record.policy_version == "policy-v1"
