from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from qrtc.transit import TransitOutcome


class EvidenceCategory(str, Enum):
    OBSERVED = "observed"
    ASSERTED = "asserted"
    DERIVED = "derived"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class WitnessFact:
    name: str
    category: EvidenceCategory
    value: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "value": self.value,
        }


@dataclass(frozen=True)
class WitnessRecord:
    transit_id: str
    route_id: str
    policy_version: str
    schema_version: str
    encoding_version: str
    route_version: str
    status: str
    failure_state: str | None
    facts: tuple[WitnessFact, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "transit_id": self.transit_id,
            "route_id": self.route_id,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
            "encoding_version": self.encoding_version,
            "route_version": self.route_version,
            "status": self.status,
            "failure_state": self.failure_state,
            "facts": [fact.as_dict() for fact in self.facts],
        }


def build_witness_record(outcome: TransitOutcome) -> WitnessRecord:
    facts = (
        WitnessFact(
            name="authorization_qualified",
            category=EvidenceCategory.OBSERVED,
            value=outcome.authorization.qualified,
        ),
        WitnessFact(
            name="guard_decision_count",
            category=EvidenceCategory.OBSERVED,
            value=len(outcome.guard_decisions),
        ),
        WitnessFact(
            name="delivery_status",
            category=EvidenceCategory.OBSERVED,
            value=None
            if outcome.delivery_evidence is None
            else outcome.delivery_evidence.delivery_status.value,
        ),
        WitnessFact(
            name="policy_version",
            category=EvidenceCategory.ASSERTED,
            value=outcome.policy_version,
        ),
        WitnessFact(
            name="schema_version",
            category=EvidenceCategory.ASSERTED,
            value=outcome.schema_version,
        ),
        WitnessFact(
            name="encoding_version",
            category=EvidenceCategory.ASSERTED,
            value=outcome.encoding_version,
        ),
        WitnessFact(
            name="route_version",
            category=EvidenceCategory.ASSERTED,
            value=outcome.route_version,
        ),
        WitnessFact(
            name="integrity_verified",
            category=EvidenceCategory.DERIVED,
            value=outcome.failure_state is None,
        ),
        WitnessFact(
            name="stabilized",
            category=EvidenceCategory.DERIVED,
            value=bool(
                outcome.stabilization_result is not None
                and outcome.stabilization_result.stable
            ),
        ),
        WitnessFact(
            name="redacted_fields",
            category=EvidenceCategory.UNVERIFIED,
            value=("predecessor_state", "credentials", "raw_interface"),
        ),
    )

    return WitnessRecord(
        transit_id=outcome.transit_id,
        route_id=outcome.route_id,
        policy_version=outcome.policy_version,
        schema_version=outcome.schema_version,
        encoding_version=outcome.encoding_version,
        route_version=outcome.route_version,
        status=outcome.stage.value,
        failure_state=None
        if outcome.failure_state is None
        else outcome.failure_state.value,
        facts=facts,
    )
