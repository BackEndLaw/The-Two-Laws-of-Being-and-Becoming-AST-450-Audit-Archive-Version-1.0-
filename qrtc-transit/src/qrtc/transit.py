from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any


class TransitStage(str, Enum):
    REQUESTED = "requested"
    AUTHORIZED = "authorized"
    GATED = "gated"
    QUALIFIED = "qualified"
    ENCODED = "encoded"
    SEND_PENDING = "send_pending"
    SEND_ATTEMPTED = "send_attempted"
    DELIVERY_CONFIRMED = "delivery_confirmed"
    DELIVERY_UNCERTAIN = "delivery_uncertain"
    REALIZATION_PENDING = "realization_pending"
    SENT = "sent"
    DELIVERED = "delivered"
    REALIZED = "realized"
    STABILIZATION_PENDING = "stabilization_pending"
    STABILIZED = "stabilized"
    WITNESSED = "witnessed"


class TransitFailureState(str, Enum):
    REJECTED_BY_KEY = "rejected_by_key"
    REJECTED_BY_GUARD = "rejected_by_guard"
    ENCODING_FAILED = "encoding_failed"
    DELIVERY_FAILED = "delivery_failed"
    DELIVERY_UNCERTAIN = "delivery_uncertain"
    INTEGRITY_FAILED = "integrity_failed"
    REALIZATION_FAILED = "realization_failed"
    STABILIZATION_FAILED = "stabilization_failed"


class DeliveryStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


@dataclass(frozen=True)
class TransitRequest:
    transit_id: str
    principal: str
    predecessor_class: str
    declared_future: str
    destination: str
    expiration: datetime
    policy_version: str
    route_version: str
    schema_version: str
    encoding_version: str
    interface: Mapping[str, Any]
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "interface", MappingProxyType(dict(self.interface)))
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True)
class AuthorizationDecision:
    qualified: bool
    key_id: str
    policy_version: str
    reason: str
    principal: str


@dataclass(frozen=True)
class GuardDecision:
    qualified: bool
    guard_id: str
    policy_version: str
    reason: str


@dataclass(frozen=True)
class TransitEnvelope:
    transit_id: str
    principal: str
    predecessor_class: str
    declared_future: str
    destination: str
    policy_version: str
    route_version: str
    schema_version: str
    encoding_version: str
    authorization: AuthorizationDecision
    interface: Mapping[str, Any]
    payload_bytes: bytes | None = None
    payload_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "interface", MappingProxyType(dict(self.interface)))

    def with_payload(
        self, payload_bytes: bytes, payload_digest: str
    ) -> TransitEnvelope:
        return replace(
            self,
            payload_bytes=payload_bytes,
            payload_digest=payload_digest,
        )


@dataclass(frozen=True)
class DeliveryEvidence:
    transit_id: str
    route_id: str
    payload_digest: str
    sequence_number: int
    sent_at: datetime
    received_at: datetime
    delivery_status: DeliveryStatus

    def as_dict(self) -> dict[str, Any]:
        return {
            "transit_id": self.transit_id,
            "route_id": self.route_id,
            "payload_digest": self.payload_digest,
            "sequence_number": self.sequence_number,
            "sent_at": self.sent_at.isoformat(),
            "received_at": self.received_at.isoformat(),
            "delivery_status": self.delivery_status.value,
        }


@dataclass(frozen=True)
class CandidateSuccessor:
    transit_id: str
    route_id: str
    destination: str
    candidate_id: str
    idempotency_key: str
    idempotency_resolution: str
    payload_digest: str
    interface_digest: str
    realized_at: datetime
    policy_version: str
    route_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "transit_id": self.transit_id,
            "route_id": self.route_id,
            "destination": self.destination,
            "candidate_id": self.candidate_id,
            "idempotency_key": self.idempotency_key,
            "idempotency_resolution": self.idempotency_resolution,
            "payload_digest": self.payload_digest,
            "interface_digest": self.interface_digest,
            "realized_at": self.realized_at.isoformat(),
            "policy_version": self.policy_version,
            "route_version": self.route_version,
        }


@dataclass(frozen=True)
class StabilizationResult:
    transit_id: str
    route_id: str
    candidate_id: str
    stable: bool
    reason: str
    policy_version: str
    route_version: str
    destination: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "transit_id": self.transit_id,
            "route_id": self.route_id,
            "candidate_id": self.candidate_id,
            "stable": self.stable,
            "reason": self.reason,
            "policy_version": self.policy_version,
            "route_version": self.route_version,
            "destination": self.destination,
        }


@dataclass(frozen=True)
class TransitOutcome:
    transit_id: str
    stage: TransitStage
    failure_state: TransitFailureState | None
    policy_version: str
    schema_version: str
    encoding_version: str
    route_version: str
    route_id: str
    authorization: AuthorizationDecision
    guard_decisions: tuple[GuardDecision, ...]
    envelope: TransitEnvelope | None = None
    canonical_bytes: bytes | None = None
    payload_digest: str | None = None
    delivery_evidence: DeliveryEvidence | None = None
    candidate_successor: CandidateSuccessor | None = None
    stabilization_result: StabilizationResult | None = None
    witness_record: Any | None = None

    @property
    def is_success(self) -> bool:
        return self.stage is TransitStage.WITNESSED and self.failure_state is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "transit_id": self.transit_id,
            "stage": self.stage.value,
            "failure_state": None
            if self.failure_state is None
            else self.failure_state.value,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
            "encoding_version": self.encoding_version,
            "route_version": self.route_version,
            "route_id": self.route_id,
            "authorization": {
                "qualified": self.authorization.qualified,
                "key_id": self.authorization.key_id,
                "policy_version": self.authorization.policy_version,
                "reason": self.authorization.reason,
                "principal": self.authorization.principal,
            },
            "guard_decisions": [
                {
                    "qualified": decision.qualified,
                    "guard_id": decision.guard_id,
                    "policy_version": decision.policy_version,
                    "reason": decision.reason,
                }
                for decision in self.guard_decisions
            ],
            "envelope": None
            if self.envelope is None
            else {
                "transit_id": self.envelope.transit_id,
                "principal": self.envelope.principal,
                "predecessor_class": self.envelope.predecessor_class,
                "declared_future": self.envelope.declared_future,
                "destination": self.envelope.destination,
                "policy_version": self.envelope.policy_version,
                "route_version": self.envelope.route_version,
                "schema_version": self.envelope.schema_version,
                "encoding_version": self.envelope.encoding_version,
                "payload_digest": self.envelope.payload_digest,
            },
            "canonical_bytes": None
            if self.canonical_bytes is None
            else self.canonical_bytes.hex(),
            "payload_digest": self.payload_digest,
            "delivery_evidence": None
            if self.delivery_evidence is None
            else self.delivery_evidence.as_dict(),
            "candidate_successor": None
            if self.candidate_successor is None
            else self.candidate_successor.as_dict(),
            "stabilization_result": None
            if self.stabilization_result is None
            else self.stabilization_result.as_dict(),
            "witness_record": None
            if self.witness_record is None
            else self.witness_record.as_dict(),
        }
