from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qrtc.config import TransitInputRecord
from qrtc.exceptions import IdempotencyConflictError, ResourceLimitError
from qrtc.limits import DEFAULT_LIMITS, canonical_json, enforce_json_limits
from qrtc.policy import TransitPolicy
from qrtc.redaction import redact_mapping, redact_value
from qrtc.transit import TransitOutcome, TransitRequest
from qrtc.verification import ChainVerificationResult, digest_stage_event
from qrtc.verification import policy_digest as compute_policy_digest


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_json(value: Any) -> str:
    return canonical_json(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StageEvent:
    sequence_number: int
    event_type: str
    stage: str
    occurred_at: datetime
    component_id: str | None
    previous_hash: str
    event_hash: str
    payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence_number": self.sequence_number,
            "event_type": self.event_type,
            "stage": self.stage,
            "occurred_at": self.occurred_at.isoformat(),
            "component_id": self.component_id,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class StoredTransitRecord:
    transit_id: str
    current_status: str
    failure_state: str | None
    policy_id: str
    policy_version: str
    policy_digest: str
    registry_snapshot_id: str
    resolved_components: dict[str, str]
    route_version: str
    schema_version: str
    encoding_version: str
    route_id: str
    created_at: datetime
    updated_at: datetime
    request: dict[str, Any]
    outcome: dict[str, Any]
    stage_events: tuple[StageEvent, ...]
    header_hash: str
    chain_head: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "transit_id": self.transit_id,
            "current_status": self.current_status,
            "failure_state": self.failure_state,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "registry_snapshot_id": self.registry_snapshot_id,
            "resolved_components": dict(self.resolved_components),
            "route_version": self.route_version,
            "schema_version": self.schema_version,
            "encoding_version": self.encoding_version,
            "route_id": self.route_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "request": dict(self.request),
            "outcome": dict(self.outcome),
            "stage_history": [event.as_dict() for event in self.stage_events],
            "header_hash": self.header_hash,
            "chain_head": self.chain_head,
        }


class EvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS transits (
                    transit_id TEXT PRIMARY KEY,
                    policy_id TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    policy_digest TEXT NOT NULL,
                    registry_snapshot_id TEXT NOT NULL,
                    resolved_components_json TEXT NOT NULL,
                    route_version TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    encoding_version TEXT NOT NULL,
                    route_id TEXT NOT NULL,
                    current_status TEXT NOT NULL,
                    failure_state TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    outcome_json TEXT NOT NULL,
                    header_hash TEXT NOT NULL,
                    chain_head TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS stage_events (
                    transit_id TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    component_id TEXT,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (transit_id, sequence_number),
                    FOREIGN KEY (transit_id) REFERENCES transits(transit_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS destination_idempotency (
                    destination_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (destination_id, idempotency_key)
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (1, _utc_now().isoformat()),
            )
            connection.commit()

    def record_transit(
        self,
        policy: TransitPolicy,
        input_record: TransitInputRecord,
        request: TransitRequest,
        outcome: TransitOutcome,
        *,
        policy_hash: str | None = None,
        registry_snapshot_id: str = "local-registry",
        resolved_components: Mapping[str, str] | None = None,
    ) -> None:
        resolved_components = dict(resolved_components or {})
        effective_policy_hash = policy_hash or compute_policy_digest(policy)

        if len(outcome.guard_decisions) > DEFAULT_LIMITS.max_guards:
            raise ResourceLimitError(
                f"guard decision count exceeds limit: {len(outcome.guard_decisions)} > {DEFAULT_LIMITS.max_guards}"
            )

        if (
            outcome.candidate_successor is not None
            and len(outcome.candidate_successor.idempotency_key) > 512
        ):
            raise ResourceLimitError("idempotency key exceeds limit")

        events = self._build_stage_events(policy, input_record, request, outcome)
        header_hash = events[0].event_hash
        chain_head = events[-1].event_hash
        created_at = _utc_now().isoformat()

        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO transits (
                        transit_id, policy_id, policy_version, policy_digest, registry_snapshot_id,
                        resolved_components_json, route_version, schema_version,
                        encoding_version, route_id, current_status, failure_state,
                        created_at, updated_at, request_json, outcome_json, header_hash, chain_head
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        outcome.transit_id,
                        policy.policy_id,
                        outcome.policy_version,
                        effective_policy_hash,
                        registry_snapshot_id,
                        _canonical_json(resolved_components),
                        outcome.route_version,
                        outcome.schema_version,
                        outcome.encoding_version,
                        outcome.route_id,
                        outcome.stage.value,
                        None
                        if outcome.failure_state is None
                        else outcome.failure_state.value,
                        created_at,
                        created_at,
                        _canonical_json(
                            {
                                "policy_id": policy.policy_id,
                                "policy_version": policy.policy_version,
                                "predecessor_class": policy.predecessor_class,
                                "future_family": policy.future_family,
                                "key_policy": policy.key_policy,
                                "gate": policy.gate,
                                "guards": list(policy.guards),
                                "boat": {
                                    "schema": policy.boat_schema,
                                    "encoding": policy.boat_encoding,
                                },
                                "river": {"route": policy.river_route},
                                "realizer": policy.realizer,
                                "stabilizer": policy.stabilizer,
                                "witness_policy": policy.witness_policy,
                                "input": {
                                    "transit_id": input_record.transit_id,
                                    "principal": input_record.principal,
                                    "destination": input_record.destination,
                                    "expiration": input_record.expiration.isoformat(),
                                    "interface_projection": redact_mapping(
                                        dict(input_record.interface_projection)
                                    ),
                                    "context": redact_mapping(
                                        dict(input_record.context)
                                    ),
                                },
                            }
                        ),
                        _canonical_json(outcome.as_dict()),
                        header_hash,
                        chain_head,
                    ),
                )
                for event in events:
                    payload_json = _canonical_json(event.payload)
                    if (
                        len(payload_json.encode("utf-8"))
                        > DEFAULT_LIMITS.max_event_bytes
                    ):
                        raise ResourceLimitError(
                            f"stage event exceeds size limit: {event.event_type}"
                        )
                    connection.execute(
                        """
                        INSERT INTO stage_events (
                            transit_id, sequence_number, event_type, stage, occurred_at,
                            component_id, previous_hash, event_hash, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            outcome.transit_id,
                            event.sequence_number,
                            event.event_type,
                            event.stage,
                            event.occurred_at.isoformat(),
                            event.component_id,
                            event.previous_hash,
                            event.event_hash,
                            payload_json,
                        ),
                    )

                if outcome.candidate_successor is not None:
                    self._record_idempotency_outcome(connection, outcome)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _record_idempotency_outcome(
        self,
        connection: sqlite3.Connection,
        outcome: TransitOutcome,
    ) -> None:
        candidate = outcome.candidate_successor
        assert candidate is not None

        existing = connection.execute(
            """
            SELECT payload_digest, candidate_id
            FROM destination_idempotency
            WHERE destination_id = ? AND idempotency_key = ?
            """,
            (candidate.destination, candidate.idempotency_key),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO destination_idempotency (
                    destination_id, idempotency_key, payload_digest, candidate_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    candidate.destination,
                    candidate.idempotency_key,
                    candidate.payload_digest,
                    candidate.candidate_id,
                    _utc_now().isoformat(),
                ),
            )
            return

        existing_payload = str(existing["payload_digest"])
        existing_candidate = str(existing["candidate_id"])

        if existing_payload != candidate.payload_digest:
            raise IdempotencyConflictError(
                "idempotency key conflict: identical key with different payload"
            )

        if existing_candidate != candidate.candidate_id:
            raise IdempotencyConflictError(
                "idempotency key conflict: identical key with different candidate"
            )

    def load_transit(self, transit_id: str) -> StoredTransitRecord:
        with self._connect() as connection:
            transit_row = connection.execute(
                "SELECT * FROM transits WHERE transit_id = ?",
                (transit_id,),
            ).fetchone()
            if transit_row is None:
                raise LookupError(f"unknown transit_id: {transit_id}")

            event_rows = connection.execute(
                "SELECT * FROM stage_events WHERE transit_id = ? ORDER BY sequence_number ASC",
                (transit_id,),
            ).fetchall()

        return StoredTransitRecord(
            transit_id=transit_row["transit_id"],
            current_status=transit_row["current_status"],
            failure_state=transit_row["failure_state"],
            policy_id=transit_row["policy_id"],
            policy_version=transit_row["policy_version"],
            policy_digest=transit_row["policy_digest"],
            registry_snapshot_id=transit_row["registry_snapshot_id"],
            resolved_components=json.loads(transit_row["resolved_components_json"]),
            route_version=transit_row["route_version"],
            schema_version=transit_row["schema_version"],
            encoding_version=transit_row["encoding_version"],
            route_id=transit_row["route_id"],
            created_at=datetime.fromisoformat(transit_row["created_at"]),
            updated_at=datetime.fromisoformat(transit_row["updated_at"]),
            request=json.loads(transit_row["request_json"]),
            outcome=json.loads(transit_row["outcome_json"]),
            stage_events=tuple(
                StageEvent(
                    sequence_number=row["sequence_number"],
                    event_type=row["event_type"],
                    stage=row["stage"],
                    occurred_at=datetime.fromisoformat(row["occurred_at"]),
                    component_id=row["component_id"],
                    previous_hash=row["previous_hash"],
                    event_hash=row["event_hash"],
                    payload=json.loads(row["payload_json"]),
                )
                for row in event_rows
            ),
            header_hash=transit_row["header_hash"],
            chain_head=transit_row["chain_head"],
        )

    def inspect(self, transit_id: str) -> dict[str, Any]:
        return self.load_transit(transit_id).as_dict()

    def verify_chain(self, transit_id: str) -> bool:
        return self.verify_chain_detailed(transit_id).valid

    def verify_chain_detailed(self, transit_id: str) -> ChainVerificationResult:
        record = self.load_transit(transit_id)
        if not record.stage_events:
            return ChainVerificationResult(valid=False, reason="no stage events")

        previous_hash = ""
        for event in record.stage_events:
            expected_hash = digest_stage_event(
                previous_hash,
                {
                    "sequence_number": event.sequence_number,
                    "event_type": event.event_type,
                    "stage": event.stage,
                    "occurred_at": event.occurred_at.isoformat(),
                    "component_id": event.component_id,
                    "payload": dict(event.payload),
                },
            )
            if expected_hash != event.event_hash:
                return ChainVerificationResult(
                    valid=False,
                    reason=f"event hash mismatch at sequence {event.sequence_number}",
                )
            previous_hash = event.event_hash

        if previous_hash != record.chain_head:
            return ChainVerificationResult(valid=False, reason="chain head mismatch")

        return ChainVerificationResult(valid=True, reason="chain verified")

    def _build_stage_events(
        self,
        policy: TransitPolicy,
        input_record: TransitInputRecord,
        request: TransitRequest,
        outcome: TransitOutcome,
    ) -> list[StageEvent]:
        events: list[StageEvent] = []

        def append(
            event_type: str,
            stage: str,
            payload: Mapping[str, Any],
            component_id: str | None = None,
        ) -> None:
            safe_payload = redact_value(dict(payload))
            enforce_json_limits(safe_payload, DEFAULT_LIMITS)
            previous_hash = events[-1].event_hash if events else ""
            occurred_at = _utc_now()
            event = StageEvent(
                sequence_number=len(events),
                event_type=event_type,
                stage=stage,
                occurred_at=occurred_at,
                component_id=component_id,
                previous_hash=previous_hash,
                event_hash=digest_stage_event(
                    previous_hash,
                    {
                        "sequence_number": len(events),
                        "event_type": event_type,
                        "stage": stage,
                        "occurred_at": occurred_at.isoformat(),
                        "component_id": component_id,
                        "payload": safe_payload,
                    },
                ),
                payload=safe_payload,
            )
            events.append(event)

        append(
            "header",
            "requested",
            {
                "policy_id": policy.policy_id,
                "policy_version": policy.policy_version,
                "predecessor_class": policy.predecessor_class,
                "future_family": policy.future_family,
                "key_policy": policy.key_policy,
                "gate": policy.gate,
                "guards": list(policy.guards),
                "boat": {
                    "schema": policy.boat_schema,
                    "encoding": policy.boat_encoding,
                },
                "river": {"route": policy.river_route},
                "realizer": policy.realizer,
                "stabilizer": policy.stabilizer,
                "witness_policy": policy.witness_policy,
                "input": input_record.as_dict(),
            },
            component_id=policy.policy_id,
        )

        append(
            "authorization",
            outcome.stage.value,
            {
                "qualified": outcome.authorization.qualified,
                "key_id": outcome.authorization.key_id,
                "policy_version": outcome.authorization.policy_version,
                "reason": outcome.authorization.reason,
                "principal": outcome.authorization.principal,
            },
            component_id=policy.key_policy,
        )

        if outcome.envelope is not None:
            append(
                "gate",
                "gated",
                {
                    "transit_id": outcome.envelope.transit_id,
                    "principal": outcome.envelope.principal,
                    "predecessor_class": outcome.envelope.predecessor_class,
                    "declared_future": outcome.envelope.declared_future,
                    "destination": outcome.envelope.destination,
                    "policy_version": outcome.envelope.policy_version,
                    "route_version": outcome.envelope.route_version,
                    "schema_version": outcome.envelope.schema_version,
                    "encoding_version": outcome.envelope.encoding_version,
                },
                component_id=policy.gate,
            )

        for guard in outcome.guard_decisions:
            append(
                "guard",
                "qualified",
                {
                    "qualified": guard.qualified,
                    "guard_id": guard.guard_id,
                    "policy_version": guard.policy_version,
                    "reason": guard.reason,
                },
                component_id=guard.guard_id,
            )

        if outcome.canonical_bytes is not None:
            append(
                "encoding",
                "encoded",
                {
                    "payload_digest": outcome.payload_digest,
                    "schema_version": outcome.schema_version,
                    "encoding_version": outcome.encoding_version,
                },
                component_id=policy.boat_encoding,
            )

        if outcome.delivery_evidence is not None:
            append(
                "delivery",
                "delivered",
                outcome.delivery_evidence.as_dict(),
                component_id=policy.river_route,
            )

        if outcome.candidate_successor is not None:
            append(
                "realization",
                "realized",
                outcome.candidate_successor.as_dict(),
                component_id=policy.realizer,
            )

        if outcome.stabilization_result is not None:
            append(
                "stabilization",
                "stabilized",
                outcome.stabilization_result.as_dict(),
                component_id=policy.stabilizer,
            )

        if outcome.witness_record is not None:
            append(
                "witness",
                "witnessed",
                outcome.witness_record.as_dict(),
                component_id=policy.witness_policy,
            )

        return events
