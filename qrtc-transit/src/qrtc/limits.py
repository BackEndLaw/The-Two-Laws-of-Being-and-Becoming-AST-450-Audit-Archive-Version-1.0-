from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qrtc.exceptions import ResourceLimitError


@dataclass(frozen=True)
class ResourceLimits:
    max_policy_bytes: int = 256_000
    max_input_bytes: int = 1_000_000
    max_json_depth: int = 64
    max_guards: int = 64
    max_string_length: int = 100_000
    max_array_length: int = 10_000
    max_object_fields: int = 10_000
    max_event_bytes: int = 256_000
    max_replay_count: int = 10
    max_witnesses: int = 100
    max_transit_duration_seconds: int = 900
    max_river_queue_size: int = 10_000

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_LIMITS = ResourceLimits()


def enforce_file_size(path: str | Path, *, max_bytes: int, label: str) -> None:
    size = Path(path).stat().st_size
    if size > max_bytes:
        raise ResourceLimitError(f"{label} exceeds size limit: {size} > {max_bytes}")


def enforce_json_limits(value: Any, limits: ResourceLimits = DEFAULT_LIMITS) -> None:
    _enforce_value(value, depth=0, limits=limits)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _enforce_value(value: Any, *, depth: int, limits: ResourceLimits) -> None:
    if depth > limits.max_json_depth:
        raise ResourceLimitError(
            f"json depth exceeds limit: {depth} > {limits.max_json_depth}"
        )

    if isinstance(value, str):
        if len(value) > limits.max_string_length:
            raise ResourceLimitError(
                f"string length exceeds limit: {len(value)} > {limits.max_string_length}"
            )
        return

    if isinstance(value, Mapping):
        if len(value) > limits.max_object_fields:
            raise ResourceLimitError(
                f"object field count exceeds limit: {len(value)} > {limits.max_object_fields}"
            )
        for key, nested in value.items():
            _enforce_value(str(key), depth=depth + 1, limits=limits)
            _enforce_value(nested, depth=depth + 1, limits=limits)
        return

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if len(value) > limits.max_array_length:
            raise ResourceLimitError(
                f"array length exceeds limit: {len(value)} > {limits.max_array_length}"
            )
        for nested in value:
            _enforce_value(nested, depth=depth + 1, limits=limits)
        return

    # Primitive numbers/bools/None are accepted.
    return
