from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rescueos.compiler.schema import CompiledGraph
from rescueos.core.distinctions import ActionKind, Intervention, Task


@dataclass
class SystemState:
    local_health: dict[str, float]
    distinction_quality: dict[str, float]

    @classmethod
    def from_health(cls, health: Mapping[str, float]) -> SystemState:
        values = {name: float(value) for name, value in health.items()}
        return cls(local_health=dict(values), distinction_quality=dict(values))

    def copy(self) -> SystemState:
        return SystemState(
            local_health=dict(self.local_health),
            distinction_quality=dict(self.distinction_quality),
        )


@dataclass(frozen=True)
class RealizedOutcome:
    succeeded: bool


class TransitionModel:
    def __init__(self, graph: CompiledGraph | None = None) -> None:
        self.graph = graph

    @property
    def graph_checksum(self) -> str | None:
        return self.graph.checksum if self.graph is not None else None

    def apply(
        self,
        state: SystemState,
        action: Intervention,
        realized_outcome: RealizedOutcome,
    ) -> SystemState:
        candidate = state.copy()

        if action.kind == ActionKind.REPAIR and realized_outcome.succeeded:
            for node in action.restores:
                candidate.local_health[node] = 1.0

        if action.kind == ActionKind.EVIDENCE and realized_outcome.succeeded:
            candidate.local_health["confidence"] = min(
                1.0,
                candidate.local_health.get("confidence", 0.0) + 0.1,
            )

        if self.graph is None:
            candidate.distinction_quality = dict(candidate.local_health)
        else:
            affected = self.graph.affected_nodes(action.action_id)
            if action.kind == ActionKind.EVIDENCE:
                affected = affected | frozenset({"confidence"})
            self.graph.propagate(candidate, affected)
        return candidate


def evaluate_task(state: SystemState, task: Task) -> float:
    shortfalls = [
        max(0.0, float(requirement) - state.distinction_quality.get(name, 0.0))
        for name, requirement in task.required_distinctions.items()
    ]
    if not shortfalls:
        return 1.0
    return sum(shortfalls) / len(shortfalls)