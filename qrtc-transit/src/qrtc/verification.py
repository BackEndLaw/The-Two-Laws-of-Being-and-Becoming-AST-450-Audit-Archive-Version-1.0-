from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from qrtc.limits import canonical_json, enforce_json_limits
from qrtc.policy import TransitPolicy
from qrtc.registry import FrozenComponentRegistry


@dataclass(frozen=True, order=True)
class ResolvedComponent:
    kind: str
    identifier: str
    implementation_version: str


def canonical_policy_bytes(policy: Mapping[str, Any]) -> bytes:
    enforce_json_limits(policy)
    return canonical_json(policy).encode("utf-8")


def policy_digest(policy: TransitPolicy | Mapping[str, Any]) -> str:
    policy_dict = (
        policy.as_dict() if isinstance(policy, TransitPolicy) else dict(policy)
    )
    return hashlib.sha256(canonical_policy_bytes(policy_dict)).hexdigest()


def resolved_components(
    registry: FrozenComponentRegistry,
) -> tuple[ResolvedComponent, ...]:
    return tuple(
        sorted(
            (
                ResolvedComponent(
                    kind=metadata.component_kind,
                    identifier=metadata.component_id,
                    implementation_version=metadata.version,
                )
                for metadata in registry.metadata.values()
            ),
            key=lambda component: (
                component.kind,
                component.identifier,
                component.implementation_version,
            ),
        )
    )


def registry_snapshot_id(registry: FrozenComponentRegistry) -> str:
    snapshot = [
        [
            component.kind,
            component.identifier,
            component.implementation_version,
        ]
        for component in resolved_components(registry)
    ]
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


def digest_stage_event(previous_hash: str, event: Mapping[str, Any]) -> str:
    payload = {
        "previous_hash": previous_hash,
        **event,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainVerificationResult:
    valid: bool
    reason: str
