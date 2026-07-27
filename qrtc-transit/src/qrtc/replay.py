from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from qrtc.config import TransitInputRecord, build_transit_request
from qrtc.evidence_store import EvidenceStore, StoredTransitRecord
from qrtc.exceptions import ResourceLimitError
from qrtc.limits import DEFAULT_LIMITS
from qrtc.policy import TransitPolicy
from qrtc.registry import FrozenComponentRegistry


class ReplayStatus(str, Enum):
    REPRODUCED = "reproduced"
    CHANGED = "changed"
    UNAVAILABLE = "unavailable"
    INTENTIONALLY_NOT_REEXECUTED = "intentionally_not_reexecuted"


@dataclass(frozen=True)
class ReplayStepResult:
    name: str
    status: ReplayStatus
    reason: str
    stored: dict[str, Any] | None = None
    replayed: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason": self.reason,
            "stored": self.stored,
            "replayed": self.replayed,
        }


@dataclass(frozen=True)
class ReplayPolicy:
    allow_delivery_retry: bool = False
    allow_realization_retry: bool = False
    replay_count: int = 1


@dataclass(frozen=True)
class ReplayReport:
    transit_id: str
    steps: tuple[ReplayStepResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "transit_id": self.transit_id,
            "steps": [step.as_dict() for step in self.steps],
        }


class ReplayEngine:
    def __init__(self, store: EvidenceStore, registry: FrozenComponentRegistry) -> None:
        self.store = store
        self.registry = registry

    def replay(
        self, transit_id: str, *, policy: ReplayPolicy | None = None
    ) -> ReplayReport:
        policy = policy or ReplayPolicy()
        if policy.replay_count > DEFAULT_LIMITS.max_replay_count:
            raise ResourceLimitError(
                f"replay_count exceeds limit: {policy.replay_count} > {DEFAULT_LIMITS.max_replay_count}"
            )
        record = self.store.load_transit(transit_id)
        input_record = _input_record_from_summary(record)
        transit_policy = _policy_from_summary(record)
        request = build_transit_request(transit_policy, input_record)

        steps = [
            self._replay_analysis(record, transit_policy, request),
            self._replay_delivery(record, policy),
            self._replay_realization(record, request, transit_policy, policy),
            self._reconstruct_evidence(record),
        ]
        return ReplayReport(transit_id=transit_id, steps=tuple(steps))

    def _replay_analysis(
        self,
        record: StoredTransitRecord,
        transit_policy: TransitPolicy,
        request,
    ) -> ReplayStepResult:
        gate_meta = self.registry.metadata.get(transit_policy.gate)
        boat_meta = self.registry.metadata.get(transit_policy.boat_encoding)
        if (
            gate_meta is None
            or boat_meta is None
            or not gate_meta.deterministic
            or not boat_meta.deterministic
        ):
            return ReplayStepResult(
                name="analysis",
                status=ReplayStatus.UNAVAILABLE,
                reason="gate or boat component is unavailable for deterministic replay",
                stored={
                    "gate": transit_policy.gate,
                    "boat": transit_policy.boat_encoding,
                },
            )

        gate = self.registry.resolve_gate(transit_policy.gate)
        boat = self.registry.resolve_boat(transit_policy.boat_encoding)
        auth = record.outcome["authorization"]
        from qrtc.transit import AuthorizationDecision

        replayed_envelope = gate(
            request,
            AuthorizationDecision(
                qualified=auth["qualified"],
                key_id=auth["key_id"],
                policy_version=auth["policy_version"],
                reason=auth["reason"],
                principal=auth["principal"],
            ),
        )
        replayed_encoded = boat.encode(replayed_envelope)

        stored_envelope = record.outcome.get("envelope")
        if stored_envelope is None:
            return ReplayStepResult(
                name="analysis",
                status=ReplayStatus.UNAVAILABLE,
                reason="stored outcome does not include an envelope",
            )

        reproduced = (
            stored_envelope["transit_id"] == replayed_envelope.transit_id
            and stored_envelope["declared_future"] == replayed_envelope.declared_future
            and record.outcome.get("payload_digest") == replayed_encoded.payload_digest
        )

        return ReplayStepResult(
            name="analysis",
            status=ReplayStatus.REPRODUCED if reproduced else ReplayStatus.CHANGED,
            reason="deterministic Gate and Boat outputs compared",
            stored={
                "envelope": stored_envelope,
                "payload_digest": record.outcome.get("payload_digest"),
            },
            replayed={
                "envelope": {
                    "transit_id": replayed_envelope.transit_id,
                    "principal": replayed_envelope.principal,
                    "predecessor_class": replayed_envelope.predecessor_class,
                    "declared_future": replayed_envelope.declared_future,
                    "destination": replayed_envelope.destination,
                    "policy_version": replayed_envelope.policy_version,
                    "route_version": replayed_envelope.route_version,
                    "schema_version": replayed_envelope.schema_version,
                    "encoding_version": replayed_envelope.encoding_version,
                    "payload_digest": replayed_envelope.payload_digest,
                },
                "payload_digest": replayed_encoded.payload_digest,
            },
        )

    def _replay_delivery(
        self, record: StoredTransitRecord, policy: ReplayPolicy
    ) -> ReplayStepResult:
        if not policy.allow_delivery_retry:
            return ReplayStepResult(
                name="delivery_retry",
                status=ReplayStatus.INTENTIONALLY_NOT_REEXECUTED,
                reason="delivery retry requires explicit policy",
                stored=record.outcome.get("delivery_evidence"),
            )

        return ReplayStepResult(
            name="delivery_retry",
            status=ReplayStatus.UNAVAILABLE,
            reason="delivery retry is not executed in the offline replay engine",
            stored=record.outcome.get("delivery_evidence"),
        )

    def _replay_realization(
        self,
        record: StoredTransitRecord,
        request,
        transit_policy: TransitPolicy,
        policy: ReplayPolicy,
    ) -> ReplayStepResult:
        if not policy.allow_realization_retry:
            return ReplayStepResult(
                name="realization_retry",
                status=ReplayStatus.INTENTIONALLY_NOT_REEXECUTED,
                reason="realization retry requires explicit policy",
                stored=record.outcome.get("candidate_successor"),
            )

        realizer_meta = self.registry.metadata.get(transit_policy.realizer)
        if realizer_meta is None or not realizer_meta.replayable:
            return ReplayStepResult(
                name="realization_retry",
                status=ReplayStatus.UNAVAILABLE,
                reason="realizer is unavailable for deterministic retry",
                stored=record.outcome.get("candidate_successor"),
            )

        realizer = self.registry.resolve_realizer(transit_policy.realizer)
        envelope = record.outcome.get("envelope")
        if envelope is None:
            return ReplayStepResult(
                name="realization_retry",
                status=ReplayStatus.UNAVAILABLE,
                reason="stored envelope unavailable",
            )

        candidate = realizer.realize(
            request.interface,
            request.context,
            transit_id=request.transit_id,
            route_id=record.route_id,
            payload_digest=record.outcome.get("payload_digest") or "",
            idempotency_key=request.transit_id,
        )
        stored = record.outcome.get("candidate_successor")
        reproduced = (
            stored is not None and stored.get("candidate_id") == candidate.candidate_id
        )

        return ReplayStepResult(
            name="realization_retry",
            status=ReplayStatus.REPRODUCED if reproduced else ReplayStatus.CHANGED,
            reason="idempotent realizer compared",
            stored=stored,
            replayed=candidate.as_dict(),
        )

    def _reconstruct_evidence(self, record: StoredTransitRecord) -> ReplayStepResult:
        return ReplayStepResult(
            name="evidence_reconstruction",
            status=ReplayStatus.REPRODUCED,
            reason="stored events reconstructed into a report",
            stored={"event_count": len(record.stage_events)},
            replayed=record.as_dict(),
        )


def _policy_from_summary(record: StoredTransitRecord) -> TransitPolicy:
    request = record.request
    return TransitPolicy(
        policy_id=record.policy_id,
        policy_version=record.policy_version,
        predecessor_class=request["predecessor_class"],
        future_family=request["future_family"],
        key_policy=request["key_policy"],
        gate=request["gate"],
        guards=tuple(request["guards"]),
        boat_schema=request["boat"]["schema"],
        boat_encoding=request["boat"]["encoding"],
        river_route=request["river"]["route"],
        realizer=request["realizer"],
        stabilizer=request["stabilizer"],
        witness_policy=request["witness_policy"],
    )


def _input_record_from_summary(record: StoredTransitRecord) -> TransitInputRecord:
    request = record.request["input"]
    return TransitInputRecord(
        transit_id=request["transit_id"],
        principal=request["principal"],
        destination=request["destination"],
        expiration=datetime.fromisoformat(request["expiration"]),
        interface_projection=request["interface_projection"],
        context=request.get("context", {}),
    )
