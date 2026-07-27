from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from qrtc.boat import BoatCodec
from qrtc.config import TransitInputRecord, build_transit_request
from qrtc.destination import DefaultRealizer, DefaultStabilizer
from qrtc.exceptions import (
    DeliveryError,
    EncodingError,
    RealizationError,
    StabilizationError,
)
from qrtc.guards import GuardRule, evaluate_guards
from qrtc.key import TransitKey, authorize_transit
from qrtc.policy import TransitPolicy
from qrtc.recovery import stage_idempotency_key
from qrtc.registry import FrozenComponentRegistry, PolicyResolutionError
from qrtc.river import RiverReceiver, RiverSender, SimulatedDirectedRiver
from qrtc.transit import (
    AuthorizationDecision,
    DeliveryEvidence,
    DeliveryStatus,
    TransitEnvelope,
    TransitFailureState,
    TransitOutcome,
    TransitRequest,
    TransitStage,
)
from qrtc.verification import policy_digest, registry_snapshot_id
from qrtc.witness import build_witness_record

RECOVERABLE_STAGE_ERRORS = (
    DeliveryError,
    EncodingError,
    RealizationError,
    StabilizationError,
    KeyError,
    LookupError,
    TypeError,
    ValueError,
    RuntimeError,
)


@dataclass(frozen=True)
class TransitPipeline:
    key: TransitKey
    gate: Callable[[TransitRequest, AuthorizationDecision], TransitEnvelope]
    guards: tuple[GuardRule, ...]
    boat: BoatCodec
    sender: RiverSender
    receiver: RiverReceiver
    realizer: DefaultRealizer
    stabilizer: DefaultStabilizer
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def execute(self, request: TransitRequest) -> TransitOutcome:
        auth = authorize_transit(request, self.key, now=self.clock())
        if not auth.qualified:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.REQUESTED,
                    failure_state=TransitFailureState.REJECTED_BY_KEY,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=(),
                )
            )

        envelope = self.gate(request, auth)
        qualified_envelope = TransitEnvelope(
            transit_id=envelope.transit_id,
            principal=envelope.principal,
            predecessor_class=envelope.predecessor_class,
            declared_future=envelope.declared_future,
            destination=envelope.destination,
            policy_version=envelope.policy_version,
            route_version=envelope.route_version,
            schema_version=envelope.schema_version,
            encoding_version=envelope.encoding_version,
            authorization=envelope.authorization,
            interface=envelope.interface,
        )
        guard_decisions = evaluate_guards(qualified_envelope, self.guards)
        if guard_decisions and not guard_decisions[-1].qualified:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.QUALIFIED,
                    failure_state=TransitFailureState.REJECTED_BY_GUARD,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=guard_decisions,
                    envelope=qualified_envelope,
                )
            )

        try:
            encoded_envelope = self.boat.encode(qualified_envelope)
        except RECOVERABLE_STAGE_ERRORS:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.QUALIFIED,
                    failure_state=TransitFailureState.ENCODING_FAILED,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=guard_decisions,
                    envelope=qualified_envelope,
                )
            )

        try:
            send_receipt = self.sender.send(encoded_envelope)
        except RECOVERABLE_STAGE_ERRORS:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.SEND_PENDING,
                    failure_state=TransitFailureState.DELIVERY_FAILED,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=guard_decisions,
                    envelope=encoded_envelope,
                    canonical_bytes=encoded_envelope.payload_bytes,
                    payload_digest=encoded_envelope.payload_digest,
                )
            )

        try:
            receive_receipt = self.receiver.receive()
        except RECOVERABLE_STAGE_ERRORS:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.SEND_ATTEMPTED,
                    failure_state=TransitFailureState.DELIVERY_UNCERTAIN,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=guard_decisions,
                    envelope=encoded_envelope,
                    canonical_bytes=encoded_envelope.payload_bytes,
                    payload_digest=encoded_envelope.payload_digest,
                )
            )

        delivery_evidence = DeliveryEvidence(
            transit_id=send_receipt.transit_id,
            route_id=send_receipt.route_id,
            payload_digest=send_receipt.payload_digest,
            sequence_number=receive_receipt.sequence_number,
            sent_at=send_receipt.sent_at,
            received_at=receive_receipt.received_at,
            delivery_status=DeliveryStatus.DELIVERED,
        )

        received_envelope = receive_receipt.envelope
        if received_envelope.payload_digest != encoded_envelope.payload_digest:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.DELIVERY_CONFIRMED,
                    failure_state=TransitFailureState.INTEGRITY_FAILED,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=guard_decisions,
                    envelope=received_envelope,
                    canonical_bytes=encoded_envelope.payload_bytes,
                    payload_digest=encoded_envelope.payload_digest,
                    delivery_evidence=delivery_evidence,
                )
            )

        realization_idempotency_key = stage_idempotency_key(
            request.transit_id,
            TransitStage.REALIZATION_PENDING.value,
            self.realizer.policy_version,
            component_id=self.realizer.destination,
            payload_digest=received_envelope.payload_digest or "",
        )

        try:
            candidate = self.realizer.realize(
                received_envelope.interface,
                request.context,
                transit_id=request.transit_id,
                route_id=self.sender.river.route_id,
                payload_digest=received_envelope.payload_digest or "",
                idempotency_key=realization_idempotency_key,
            )
        except RECOVERABLE_STAGE_ERRORS:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.REALIZATION_PENDING,
                    failure_state=TransitFailureState.REALIZATION_FAILED,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=guard_decisions,
                    envelope=received_envelope,
                    canonical_bytes=encoded_envelope.payload_bytes,
                    payload_digest=encoded_envelope.payload_digest,
                    delivery_evidence=delivery_evidence,
                )
            )

        try:
            stabilization_result = self.stabilizer.stabilize(candidate)
        except RECOVERABLE_STAGE_ERRORS:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.STABILIZATION_PENDING,
                    failure_state=TransitFailureState.STABILIZATION_FAILED,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=guard_decisions,
                    envelope=received_envelope,
                    canonical_bytes=encoded_envelope.payload_bytes,
                    payload_digest=encoded_envelope.payload_digest,
                    delivery_evidence=delivery_evidence,
                    candidate_successor=candidate,
                )
            )

        if not stabilization_result.stable:
            return self._finalize(
                TransitOutcome(
                    transit_id=request.transit_id,
                    stage=TransitStage.REALIZED,
                    failure_state=TransitFailureState.STABILIZATION_FAILED,
                    policy_version=request.policy_version,
                    schema_version=request.schema_version,
                    encoding_version=request.encoding_version,
                    route_version=request.route_version,
                    route_id=self.sender.river.route_id,
                    authorization=auth,
                    guard_decisions=guard_decisions,
                    envelope=received_envelope,
                    canonical_bytes=encoded_envelope.payload_bytes,
                    payload_digest=encoded_envelope.payload_digest,
                    delivery_evidence=delivery_evidence,
                    candidate_successor=candidate,
                    stabilization_result=stabilization_result,
                )
            )

        return self._finalize(
            TransitOutcome(
                transit_id=request.transit_id,
                stage=TransitStage.WITNESSED,
                failure_state=None,
                policy_version=request.policy_version,
                schema_version=request.schema_version,
                encoding_version=request.encoding_version,
                route_version=request.route_version,
                route_id=self.sender.river.route_id,
                authorization=auth,
                guard_decisions=guard_decisions,
                envelope=received_envelope,
                canonical_bytes=encoded_envelope.payload_bytes,
                payload_digest=encoded_envelope.payload_digest,
                delivery_evidence=delivery_evidence,
                candidate_successor=candidate,
                stabilization_result=stabilization_result,
            )
        )

    def _finalize(self, outcome: TransitOutcome) -> TransitOutcome:
        return TransitOutcome(
            transit_id=outcome.transit_id,
            stage=outcome.stage,
            failure_state=outcome.failure_state,
            policy_version=outcome.policy_version,
            schema_version=outcome.schema_version,
            encoding_version=outcome.encoding_version,
            route_version=outcome.route_version,
            route_id=outcome.route_id,
            authorization=outcome.authorization,
            guard_decisions=outcome.guard_decisions,
            envelope=outcome.envelope,
            canonical_bytes=outcome.canonical_bytes,
            payload_digest=outcome.payload_digest,
            delivery_evidence=outcome.delivery_evidence,
            candidate_successor=outcome.candidate_successor,
            stabilization_result=outcome.stabilization_result,
            witness_record=build_witness_record(outcome),
        )


@dataclass(frozen=True)
class ConfiguredTransit:
    policy: TransitPolicy
    input_record: TransitInputRecord
    request: TransitRequest
    pipeline: TransitPipeline
    policy_digest: str
    registry_snapshot_id: str
    resolved_component_ids: dict[str, str]


def build_configured_pipeline(
    policy: TransitPolicy,
    input_record: TransitInputRecord,
    registry: FrozenComponentRegistry,
    *,
    clock: Callable[[], datetime] | None = None,
) -> ConfiguredTransit:
    key_factory = registry.resolve_key_policy(policy.key_policy)
    gate = registry.resolve_gate(policy.gate)
    guards = tuple(registry.resolve_guard(guard_id) for guard_id in policy.guards)
    boat = registry.resolve_boat(policy.boat_encoding)
    realizer = registry.resolve_realizer(policy.realizer)
    stabilizer = registry.resolve_stabilizer(policy.stabilizer)

    if boat.schema_version != policy.boat_schema:
        raise PolicyResolutionError(
            f"boat schema {boat.schema_version!r} does not match policy {policy.boat_schema!r}"
        )

    key = key_factory(policy, input_record)
    request = build_transit_request(policy, input_record)
    river = SimulatedDirectedRiver(
        route_id=policy.river_route,
        sender_id=f"{policy.river_route}:sender",
        receiver_id=f"{policy.river_route}:receiver",
    )

    pipeline = TransitPipeline(
        key=key,
        gate=gate,
        guards=guards,
        boat=boat,
        sender=river.sender(),
        receiver=river.receiver(),
        realizer=realizer,
        stabilizer=stabilizer,
        clock=clock or (lambda: datetime.now(UTC)),
    )

    return ConfiguredTransit(
        policy=policy,
        input_record=input_record,
        request=request,
        pipeline=pipeline,
        policy_digest=policy_digest(policy),
        registry_snapshot_id=registry_snapshot_id(registry),
        resolved_component_ids={
            "key_policy": policy.key_policy,
            "gate": policy.gate,
            "guards": ",".join(policy.guards),
            "boat_encoding": policy.boat_encoding,
            "realizer": policy.realizer,
            "stabilizer": policy.stabilizer,
            "witness_policy": policy.witness_policy,
        },
    )


def execute_configured_transit(
    policy: TransitPolicy,
    input_record: TransitInputRecord,
    registry: FrozenComponentRegistry,
    *,
    clock: Callable[[], datetime] | None = None,
) -> tuple[ConfiguredTransit, TransitOutcome]:
    configured = build_configured_pipeline(
        policy,
        input_record,
        registry,
        clock=clock,
    )
    outcome = configured.pipeline.execute(configured.request)
    return configured, outcome


def build_success_demo_pipeline() -> TransitPipeline:
    key = TransitKey(
        key_id="demo-key",
        principal="authorized-operator",
        predecessor_class="equipment",
        declared_future="telemetry-payload",
        destination="archive",
        expiration=datetime(2099, 1, 1, tzinfo=UTC),
        policy_version="policy-v1",
    )

    river = SimulatedDirectedRiver(
        route_id="route-v1",
        sender_id="sender-v1",
        receiver_id="receiver-v1",
    )

    guards = (
        GuardRule(
            guard_id="telemetry-schema",
            policy_version="policy-v1",
            predicate=lambda envelope: (
                envelope.interface.get("temperature") is not None
            ),
            pass_reason="schema accepted",
            fail_reason="temperature missing",
        ),
    )

    codec = BoatCodec(schema_version="schema-v1", encoding_version="json-v1")
    realizer = DefaultRealizer(
        destination="archive",
        policy_version="policy-v1",
        route_version="route-v1",
    )
    stabilizer = DefaultStabilizer(
        stabilizer_id="stabilizer-v1",
        policy_version="policy-v1",
        route_version="route-v1",
    )

    def gate(
        request: TransitRequest, authorization: AuthorizationDecision
    ) -> TransitEnvelope:
        return TransitEnvelope(
            transit_id=request.transit_id,
            principal=request.principal,
            predecessor_class=request.predecessor_class,
            declared_future=request.declared_future,
            destination=request.destination,
            policy_version=request.policy_version,
            route_version=request.route_version,
            schema_version=request.schema_version,
            encoding_version=request.encoding_version,
            authorization=authorization,
            interface=request.interface,
        )

    return TransitPipeline(
        key=key,
        gate=gate,
        guards=guards,
        boat=codec,
        sender=river.sender(),
        receiver=river.receiver(),
        realizer=realizer,
        stabilizer=stabilizer,
    )
