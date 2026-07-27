from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from qrtc.transit import CandidateSuccessor, StabilizationResult


@dataclass(frozen=True)
class DefaultRealizer:
    destination: str
    policy_version: str
    route_version: str

    def realize(
        self,
        interface: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        transit_id: str,
        route_id: str,
        payload_digest: str,
        idempotency_key: str | None = None,
    ) -> CandidateSuccessor:
        interface_digest = hashlib.sha256(
            repr(sorted(dict(interface).items())).encode("utf-8")
        ).hexdigest()
        effective_key = idempotency_key or transit_id
        candidate_id = hashlib.sha256(
            f"{effective_key}:{route_id}:{self.destination}:{payload_digest}".encode()
        ).hexdigest()

        return CandidateSuccessor(
            transit_id=transit_id,
            route_id=route_id,
            destination=self.destination,
            candidate_id=candidate_id,
            idempotency_key=effective_key,
            idempotency_resolution="created",
            payload_digest=payload_digest,
            interface_digest=interface_digest,
            realized_at=datetime.now(UTC),
            policy_version=self.policy_version,
            route_version=self.route_version,
        )


@dataclass(frozen=True)
class DefaultStabilizer:
    stabilizer_id: str
    policy_version: str
    route_version: str

    def stabilize(self, candidate: CandidateSuccessor) -> StabilizationResult:
        stable = bool(candidate.candidate_id and candidate.payload_digest)
        reason = "candidate stabilized" if stable else "candidate unstable"

        return StabilizationResult(
            transit_id=candidate.transit_id,
            route_id=candidate.route_id,
            candidate_id=candidate.candidate_id,
            stable=stable,
            reason=reason,
            policy_version=self.policy_version,
            route_version=self.route_version,
            destination=candidate.destination,
        )
