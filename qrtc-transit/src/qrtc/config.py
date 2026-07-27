from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from qrtc.exceptions import PolicyError
from qrtc.limits import DEFAULT_LIMITS, enforce_file_size, enforce_json_limits
from qrtc.policy import TransitPolicy, load_policy_document
from qrtc.redaction import redact_mapping
from qrtc.transit import TransitRequest


@dataclass(frozen=True)
class TransitInputRecord:
    transit_id: str
    principal: str
    destination: str
    expiration: datetime
    interface_projection: Mapping[str, Any]
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interface_projection",
            MappingProxyType(dict(self.interface_projection)),
        )
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "transit_id": self.transit_id,
            "principal": self.principal,
            "destination": self.destination,
            "expiration": self.expiration.isoformat(),
            "interface_projection": dict(self.interface_projection),
            "context": dict(self.context),
        }


class InputValidationError(PolicyError):
    pass


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InputValidationError("expiration must be an ISO 8601 string")

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_input_document(path: str | Path) -> TransitInputRecord:
    enforce_file_size(
        path, max_bytes=DEFAULT_LIMITS.max_input_bytes, label="input file"
    )
    with Path(path).open("r", encoding="utf-8") as file_handle:
        document = json.load(file_handle)

    if not isinstance(document, Mapping):
        raise InputValidationError("input file must contain a JSON object")

    enforce_json_limits(document, DEFAULT_LIMITS)

    allowed_keys = {
        "transit_id",
        "principal",
        "destination",
        "expiration",
        "interface_projection",
        "context",
    }
    unexpected = set(document) - allowed_keys
    if unexpected:
        raise InputValidationError(f"unknown input fields: {sorted(unexpected)!r}")

    required = {
        "transit_id",
        "principal",
        "destination",
        "expiration",
        "interface_projection",
    }
    missing = required - set(document)
    if missing:
        raise InputValidationError(f"missing input fields: {sorted(missing)!r}")

    interface_projection = document["interface_projection"]
    if not isinstance(interface_projection, Mapping):
        raise InputValidationError("interface_projection must be an object")

    context = document.get("context", {})
    if not isinstance(context, Mapping):
        raise InputValidationError("context must be an object")

    # Never persist or emit obvious credential-like fields in clear text.
    sanitized_context = redact_mapping(dict(context))
    sanitized_projection = redact_mapping(dict(interface_projection))

    return TransitInputRecord(
        transit_id=str(document["transit_id"]),
        principal=str(document["principal"]),
        destination=str(document["destination"]),
        expiration=_parse_datetime(document["expiration"]),
        interface_projection=sanitized_projection,
        context=sanitized_context,
    )


def build_transit_request(
    policy: TransitPolicy, input_record: TransitInputRecord
) -> TransitRequest:
    return TransitRequest(
        transit_id=input_record.transit_id,
        principal=input_record.principal,
        predecessor_class=policy.predecessor_class,
        declared_future=policy.future_family,
        destination=input_record.destination,
        expiration=input_record.expiration,
        policy_version=policy.policy_version,
        route_version=policy.river_route,
        schema_version=policy.boat_schema,
        encoding_version=policy.boat_encoding,
        interface=dict(input_record.interface_projection),
        context=dict(input_record.context),
    )


def load_policy_and_input(
    policy_path: str | Path,
    input_path: str | Path,
) -> tuple[TransitPolicy, TransitInputRecord]:
    return load_policy_document(policy_path), load_input_document(input_path)
