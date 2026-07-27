from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from qrtc.transit import TransitStage


class DeliveryCertainty(str, Enum):
    SEND_PENDING = "send_pending"
    SEND_ATTEMPTED = "send_attempted"
    DELIVERY_CONFIRMED = "delivery_confirmed"
    DELIVERY_UNCERTAIN = "delivery_uncertain"


class IdempotencyResolution(str, Enum):
    FIRST_REALIZATION = "first_realization"
    REPEATED_IDENTICAL_REALIZATION = "repeated_identical_realization"
    CONFLICTING_REALIZATION = "conflicting_realization"


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    safe_to_automate: bool
    reason: str


def _length_prefixed(parts: Iterable[str]) -> bytes:
    encoded_parts = []
    for part in parts:
        encoded = part.encode("utf-8")
        encoded_parts.append(f"{len(encoded)}:".encode("ascii") + encoded)
    return b"|".join(encoded_parts)


def stage_idempotency_key(
    transit_id: str,
    stage: str,
    component_version: str,
    component_id: str = "",
    payload_digest: str = "",
) -> str:
    material = _length_prefixed(
        [transit_id, stage, component_id, component_version, payload_digest]
    )
    return hashlib.sha256(material).hexdigest()


def decide_recovery(stage: TransitStage) -> RecoveryDecision:
    decisions: dict[TransitStage, RecoveryDecision] = {
        TransitStage.AUTHORIZED: RecoveryDecision(
            action="recompute_gate",
            safe_to_automate=True,
            reason="authorization already persisted",
        ),
        TransitStage.GATED: RecoveryDecision(
            action="resume_guards",
            safe_to_automate=True,
            reason="gate output can be reevaluated without side effects",
        ),
        TransitStage.QUALIFIED: RecoveryDecision(
            action="recompute_encoding",
            safe_to_automate=True,
            reason="encoding is deterministic under the selected boat",
        ),
        TransitStage.ENCODED: RecoveryDecision(
            action="prepare_send",
            safe_to_automate=False,
            reason="delivery status cannot be inferred from encoded state alone",
        ),
        TransitStage.SEND_PENDING: RecoveryDecision(
            action="inspect_river_evidence",
            safe_to_automate=False,
            reason="pending send may have reached the river boundary",
        ),
        TransitStage.SEND_ATTEMPTED: RecoveryDecision(
            action="mark_delivery_uncertain_until_verified",
            safe_to_automate=False,
            reason="send attempt may or may not have been accepted",
        ),
        TransitStage.DELIVERY_CONFIRMED: RecoveryDecision(
            action="proceed_realization",
            safe_to_automate=True,
            reason="delivery confirmation allows destination processing",
        ),
        TransitStage.REALIZATION_PENDING: RecoveryDecision(
            action="query_destination_by_idempotency_key",
            safe_to_automate=False,
            reason="destination must confirm whether realization already occurred",
        ),
        TransitStage.REALIZED: RecoveryDecision(
            action="proceed_stabilization",
            safe_to_automate=True,
            reason="realization succeeded and stabilization is local",
        ),
        TransitStage.STABILIZATION_PENDING: RecoveryDecision(
            action="inspect_destination_state",
            safe_to_automate=False,
            reason="stabilization status must be externally verified",
        ),
        TransitStage.STABILIZED: RecoveryDecision(
            action="resume_witness_generation",
            safe_to_automate=True,
            reason="only witness persistence remains",
        ),
    }
    return decisions.get(
        stage,
        RecoveryDecision(
            action="manual_review",
            safe_to_automate=False,
            reason="no safe automated recovery policy is defined for this stage",
        ),
    )


@dataclass
class IdempotencyLedger:
    _entries: dict[str, str] = field(default_factory=dict)

    def register(self, key: str, digest: str) -> IdempotencyResolution:
        existing = self._entries.get(key)
        if existing is None:
            self._entries[key] = digest
            return IdempotencyResolution.FIRST_REALIZATION
        if existing == digest:
            return IdempotencyResolution.REPEATED_IDENTICAL_REALIZATION
        return IdempotencyResolution.CONFLICTING_REALIZATION
