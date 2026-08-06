from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from rescueos.core.distinctions import Intervention, Task


class PropagationState(Protocol):
    local_health: dict[str, float]
    distinction_quality: dict[str, float]


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]


@dataclass(frozen=True)
class SystemSpec:
    name: str
    allow_feedback_cycles: bool
    stages: tuple[StageSpec, ...]
    tasks: tuple[Task, ...]
    interventions: tuple[Intervention, ...]


@dataclass(frozen=True)
class CompiledGraph:
    distinctions: tuple[str, ...]
    stage_ids: tuple[str, ...]
    distinction_producers: dict[str, tuple[str, ...]]
    distinction_consumers: dict[str, tuple[str, ...]]
    task_ids: tuple[str, ...]
    intervention_ids: tuple[str, ...]
    topological_order: tuple[str, ...]
    task_ancestors: Mapping[str, frozenset[str]]
    action_targets: Mapping[str, frozenset[str]]
    action_reachability: Mapping[str, frozenset[str]]
    distinction_parents: Mapping[str, frozenset[str]]
    checksum: str

    def task_relevant_nodes(self, task_id: str) -> frozenset[str]:
        return self.task_ancestors.get(task_id, frozenset())

    def action_can_influence(self, action_id: str, task_id: str) -> bool:
        return bool(
            self.action_reachability.get(action_id, frozenset())
            & self.task_relevant_nodes(task_id)
        )

    def affected_nodes(self, action_id: str) -> frozenset[str]:
        return self.action_reachability.get(action_id, frozenset())

    def propagate(
        self,
        state: PropagationState,
        affected_nodes: frozenset[str],
    ) -> None:
        for node in self.topological_order:
            if node not in affected_nodes:
                continue
            parent_quality = (
                min(state.distinction_quality.get(parent, 0.0) for parent in self.distinction_parents[node])
                if self.distinction_parents[node]
                else 1.0
            )
            state.distinction_quality[node] = min(
                state.local_health.get(node, 0.0),
                parent_quality,
            )
