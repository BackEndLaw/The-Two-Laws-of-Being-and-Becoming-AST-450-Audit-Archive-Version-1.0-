from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEY_MARKERS = (
    "password",
    "passphrase",
    "secret",
    "token",
    "credential",
    "private_key",
    "api_key",
    "authorization",
)


def redact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in mapping.items():
        normalized = key.lower()
        if any(marker in normalized for marker in SENSITIVE_KEY_MARKERS):
            redacted[key] = REDACTED
            continue
        redacted[key] = redact_value(value)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    return value
