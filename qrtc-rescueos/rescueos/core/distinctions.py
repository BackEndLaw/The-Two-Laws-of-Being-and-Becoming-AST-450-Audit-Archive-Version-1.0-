from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Mapping


class ActionKind(str, Enum):
    REPAIR = "repair"
    EVIDENCE = "evidence"
    ABSTAIN = "abstain"
    STOP = "stop"


@dataclass(frozen=True)
class Task:
    task_id: str
    required_distinctions: Mapping[str, float]
    recovery_threshold: float


@dataclass(frozen=True)
class Intervention:
    action_id: str
    kind: ActionKind
    targets: FrozenSet[str]
    restores: FrozenSet[str]
    cost: float
    harm_risk: float = 0.0
    success_probability: float = 1.0
    information_channels: FrozenSet[str] = field(default_factory=frozenset)
    certified_safe_under_unknown: bool = False


@dataclass(frozen=True)
class BeliefState:
    distinction_health: Mapping[str, float]
    fault_probabilities: Mapping[str, float]
    unknown_probability: float
    confidence: float
    local_health: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionOutcome:
    action_id: str
    succeeded: bool
    task_loss: float
    cost: float
    harm: float
    observation: Mapping[str, float]
    unsafe: bool = False


@dataclass(frozen=True)
class PlannerDecision:
    action_id: str
    kind: ActionKind
    expected_utility: float
    expected_recovery_probability: float
    expected_cost: float
    reason: str
    lost_distinctions: tuple[str, ...]
    candidate_utilities: Mapping[str, float]
    unknown_fault_probability: float
    safety_gate: str
