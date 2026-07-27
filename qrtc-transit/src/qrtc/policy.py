from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qrtc.exceptions import PolicyError
from qrtc.limits import DEFAULT_LIMITS, enforce_file_size, enforce_json_limits


class PolicyValidationError(PolicyError):
    pass


@dataclass(frozen=True)
class TransitPolicy:
    policy_id: str
    policy_version: str
    predecessor_class: str
    future_family: str
    key_policy: str
    gate: str
    guards: tuple[str, ...]
    boat_schema: str
    boat_encoding: str
    river_route: str
    realizer: str
    stabilizer: str
    witness_policy: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "predecessor_class": self.predecessor_class,
            "future_family": self.future_family,
            "key_policy": self.key_policy,
            "gate": self.gate,
            "guards": list(self.guards),
            "boat": {
                "schema": self.boat_schema,
                "encoding": self.boat_encoding,
            },
            "river": {"route": self.river_route},
            "realizer": self.realizer,
            "stabilizer": self.stabilizer,
            "witness_policy": self.witness_policy,
        }


def _require_string(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PolicyValidationError(f"{key} must be a non-empty string")
    return value


def validate_policy_document(document: Mapping[str, Any]) -> TransitPolicy:
    enforce_json_limits(document, DEFAULT_LIMITS)

    allowed_keys = {
        "policy_id",
        "policy_version",
        "predecessor_class",
        "future_family",
        "key_policy",
        "gate",
        "guards",
        "boat",
        "river",
        "realizer",
        "stabilizer",
        "witness_policy",
    }

    unexpected = set(document) - allowed_keys
    if unexpected:
        raise PolicyValidationError(f"unknown policy fields: {sorted(unexpected)!r}")

    required = allowed_keys
    missing = required - set(document)
    if missing:
        raise PolicyValidationError(f"missing policy fields: {sorted(missing)!r}")

    boat = document["boat"]
    river = document["river"]

    if not isinstance(boat, Mapping):
        raise PolicyValidationError("boat must be an object")
    if not isinstance(river, Mapping):
        raise PolicyValidationError("river must be an object")

    boat_keys = {"schema", "encoding"}
    river_keys = {"route"}
    if set(boat) != boat_keys:
        raise PolicyValidationError("boat must contain only schema and encoding")
    if set(river) != river_keys:
        raise PolicyValidationError("river must contain only route")

    guards = document["guards"]
    if not isinstance(guards, list) or not all(
        isinstance(item, str) and item.strip() for item in guards
    ):
        raise PolicyValidationError("guards must be a list of non-empty strings")
    if len(guards) > DEFAULT_LIMITS.max_guards:
        raise PolicyValidationError(
            f"guards exceed limit: {len(guards)} > {DEFAULT_LIMITS.max_guards}"
        )

    return TransitPolicy(
        policy_id=_require_string(document, "policy_id"),
        policy_version=_require_string(document, "policy_version"),
        predecessor_class=_require_string(document, "predecessor_class"),
        future_family=_require_string(document, "future_family"),
        key_policy=_require_string(document, "key_policy"),
        gate=_require_string(document, "gate"),
        guards=tuple(guards),
        boat_schema=_require_string(boat, "schema"),
        boat_encoding=_require_string(boat, "encoding"),
        river_route=_require_string(river, "route"),
        realizer=_require_string(document, "realizer"),
        stabilizer=_require_string(document, "stabilizer"),
        witness_policy=_require_string(document, "witness_policy"),
    )


def load_policy_document(path: str | Path) -> TransitPolicy:
    enforce_file_size(
        path, max_bytes=DEFAULT_LIMITS.max_policy_bytes, label="policy file"
    )
    with Path(path).open("r", encoding="utf-8") as file_handle:
        document = json.load(file_handle)

    if not isinstance(document, Mapping):
        raise PolicyValidationError("policy file must contain a JSON object")

    return validate_policy_document(document)
