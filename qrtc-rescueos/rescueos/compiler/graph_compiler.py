from __future__ import annotations

from collections import defaultdict
import hashlib
import heapq
import json

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

    first_producer = {
        produced: index
        for index, stage in reversed(tuple(enumerate(spec.stages)))
        for produced in stage.produces
    }
    parents: dict[str, set[str]] = {item: set() for item in distinctions}
    children: dict[str, set[str]] = {item: set() for item in distinctions}
    for index, stage in enumerate(spec.stages):
        for produced in stage.produces:
            if first_producer[produced] != index:
                continue
            for consumed in stage.consumes:
                if consumed == produced:
                    continue
                parents[produced].add(consumed)
                children[consumed].add(produced)

    topological_order = _topological_order(parents, children)
    task_ancestors = {
        task.task_id: frozenset(
            node
            for required in task.required_distinctions
            for node in _ancestors(required, parents)
        )
        for task in spec.tasks
    }
    action_targets = {
        action.action_id: frozenset(action.restores) for action in spec.interventions
    }
    action_reachability = {
        action_id: frozenset(
            node for target in targets for node in _descendants(target, children)
        )
        for action_id, targets in action_targets.items()
    }
    checksum_payload = {
        "order": topological_order,
        "parents": {node: sorted(values) for node, values in sorted(parents.items())},
        "tasks": {key: sorted(values) for key, values in sorted(task_ancestors.items())},
        "actions": {key: sorted(values) for key, values in sorted(action_reachability.items())},
    }
    checksum = hashlib.sha256(
        json.dumps(checksum_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

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
        topological_order=topological_order,
        task_ancestors=task_ancestors,
        action_targets=action_targets,
        action_reachability=action_reachability,
        distinction_parents={
            node: frozenset(values) for node, values in parents.items()
        },
        checksum=checksum,
    )


def _topological_order(
    parents: dict[str, set[str]],
    children: dict[str, set[str]],
) -> tuple[str, ...]:
    indegree = {node: len(values) for node, values in parents.items()}
    ready = [node for node, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[str] = []

    while ready:
        node = heapq.heappop(ready)
        ordered.append(node)
        for child in sorted(children[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)

    if len(ordered) != len(parents):
        raise ValueError("Distinction graph contains a cycle")
    return tuple(ordered)


def _ancestors(node: str, parents: dict[str, set[str]]) -> set[str]:
    result = {node}
    for parent in parents[node]:
        result.update(_ancestors(parent, parents))
    return result


def _descendants(node: str, children: dict[str, set[str]]) -> set[str]:
    result = {node}
    for child in children[node]:
        result.update(_descendants(child, children))
    return result
