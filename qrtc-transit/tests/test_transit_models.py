from datetime import UTC, datetime

from qrtc.transit import (
    AuthorizationDecision,
    DeliveryEvidence,
    DeliveryStatus,
    GuardDecision,
    TransitEnvelope,
    TransitOutcome,
    TransitRequest,
    TransitStage,
)


def test_transit_models_are_immutable_and_versioned() -> None:
    request = TransitRequest(
        transit_id="t-1",
        principal="alice",
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

    authorization = AuthorizationDecision(
        qualified=True,
        key_id="demo-key",
        policy_version="policy-v1",
        reason="matched",
        principal="alice",
    )
    envelope = TransitEnvelope(
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

    evidence = DeliveryEvidence(
        transit_id="t-1",
        route_id="route-v1",
        payload_digest="abc",
        sequence_number=1,
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        delivery_status=DeliveryStatus.DELIVERED,
    )

    outcome = TransitOutcome(
        transit_id="t-1",
        stage=TransitStage.WITNESSED,
        failure_state=None,
        policy_version="policy-v1",
        schema_version="schema-v1",
        encoding_version="json-v1",
        route_version="route-v1",
        route_id="route-v1",
        authorization=authorization,
        guard_decisions=(
            GuardDecision(
                qualified=True,
                guard_id="telemetry-schema",
                policy_version="policy-v1",
                reason="accepted",
            ),
        ),
        envelope=envelope,
        delivery_evidence=evidence,
    )

    assert request.interface["temperature"] == 64
    assert envelope.interface["temperature"] == 64
    assert outcome.is_success
    assert outcome.policy_version == "policy-v1"
    assert outcome.schema_version == "schema-v1"
    assert outcome.encoding_version == "json-v1"
    assert outcome.route_version == "route-v1"
