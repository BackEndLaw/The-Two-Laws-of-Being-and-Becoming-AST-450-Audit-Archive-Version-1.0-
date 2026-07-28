from __future__ import annotations

from dataclasses import dataclass

from rescueos.core.distinctions import Intervention, Task


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
