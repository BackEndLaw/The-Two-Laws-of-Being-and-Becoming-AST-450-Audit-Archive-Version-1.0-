from __future__ import annotations

from collections import defaultdict

from rescueos.compiler.schema import CompiledGraph, SystemSpec


def compile_graph(spec: SystemSpec) -> CompiledGraph:
    distinction_producers: dict[str, list[str]] = defaultdict(list)
    distinction_consumers: dict[str, list[str]] = defaultdict(list)
    distinctions = set()

    for stage in spec.stages:
        for item in stage.produces:
            distinction_producers[item].append(stage.stage_id)
            distinctions.add(item)
        for item in stage.consumes:
            distinction_consumers[item].append(stage.stage_id)
            distinctions.add(item)

    return CompiledGraph(
        distinctions=tuple(sorted(distinctions)),
        stage_ids=tuple(stage.stage_id for stage in spec.stages),
        distinction_producers={
            key: tuple(sorted(values)) for key, values in distinction_producers.items()
        },
        distinction_consumers={
            key: tuple(sorted(values)) for key, values in distinction_consumers.items()
        },
        task_ids=tuple(task.task_id for task in spec.tasks),
        intervention_ids=tuple(action.action_id for action in spec.interventions),
    )
