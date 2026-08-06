from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ObservationSnapshot:
    distinction_health: Mapping[str, float]
    confidence: float
    unknown_probability: float
    fault_probabilities: Mapping[str, float]


def make_snapshot(
    distinction_health: Mapping[str, float],
    confidence: float,
    unknown_probability: float,
    fault_probabilities: Mapping[str, float],
) -> dict:
    return {
        "distinction_health": dict(distinction_health),
        "confidence": float(confidence),
        "unknown_probability": float(unknown_probability),
        "fault_probabilities": dict(fault_probabilities),
    }
