from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Fault:
    fault_id: str
    affected_distinctions: tuple[str, ...]
    severity: float


def apply_faults(
    distinction_health: Mapping[str, float],
    faults: list[Fault],
) -> dict[str, float]:
    updated = dict(distinction_health)
    for fault in faults:
        for distinction in fault.affected_distinctions:
            current = float(updated.get(distinction, 1.0))
            updated[distinction] = max(0.0, current - fault.severity)
    return updated
