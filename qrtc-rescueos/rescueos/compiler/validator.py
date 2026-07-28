from __future__ import annotations

from collections import defaultdict

from rescueos.compiler.schema import StageSpec, SystemSpec
from rescueos.core.distinctions import ActionKind, Intervention, Task


class SpecValidationError(ValueError):
    pass


def validate_spec(spec: SystemSpec) -> None:
    if not spec.stages:
        raise SpecValidationError("Specification requires at least one stage")
    if not spec.tasks:
        raise SpecValidationError("Specification requires at least one task")

    _check_duplicate_stage_ids(spec.stages)
    _check_duplicate_task_ids(spec.tasks)
    _check_duplicate_intervention_ids(spec.interventions)

    known_distinctions = _collect_known_distinctions(spec.stages)
    stage_ids = {stage.stage_id for stage in spec.stages}

    _validate_tasks(spec.tasks, known_distinctions)
    _validate_interventions(spec.interventions, stage_ids, known_distinctions)

    if not spec.allow_feedback_cycles and _has_stage_cycle(spec.stages):
        raise SpecValidationError(
            "Circular distinction dependencies require explicit feedback semantics"
        )


def _check_duplicate_stage_ids(stages: tuple[StageSpec, ...]) -> None:
    ids = [stage.stage_id for stage in stages]
    if len(ids) != len(set(ids)):
        raise SpecValidationError("Duplicate stage ids are not allowed")


def _check_duplicate_task_ids(tasks: tuple[Task, ...]) -> None:
    ids = [task.task_id for task in tasks]
    if len(ids) != len(set(ids)):
        raise SpecValidationError("Duplicate task ids are not allowed")


def _check_duplicate_intervention_ids(interventions: tuple[Intervention, ...]) -> None:
    ids = [action.action_id for action in interventions]
    if len(ids) != len(set(ids)):
        raise SpecValidationError("Duplicate intervention ids are not allowed")


def _collect_known_distinctions(stages: tuple[StageSpec, ...]) -> set[str]:
    known = set()
    for stage in stages:
        known.update(stage.consumes)
        known.update(stage.produces)
    return known


def _validate_tasks(tasks: tuple[Task, ...], known_distinctions: set[str]) -> None:
    for task in tasks:
        if not 0.0 <= task.recovery_threshold <= 1.0:
            raise SpecValidationError(
                f"Task {task.task_id} has invalid recovery threshold"
            )

        if not task.required_distinctions:
            raise SpecValidationError(
                f"Task {task.task_id} must define required distinctions"
            )

        for name, requirement in task.required_distinctions.items():
            if name not in known_distinctions:
                raise SpecValidationError(
                    f"Task {task.task_id} references unknown distinction: {name}"
                )
            if not 0.0 <= float(requirement) <= 1.0:
                raise SpecValidationError(
                    f"Task {task.task_id} has impossible requirement for {name}"
                )


def _validate_interventions(
    interventions: tuple[Intervention, ...],
    stage_ids: set[str],
    known_distinctions: set[str],
) -> None:
    for action in interventions:
        if any(target not in stage_ids for target in action.targets):
            raise SpecValidationError(
                f"Intervention {action.action_id} targets a nonexistent stage"
            )

        if action.cost < 0:
            raise SpecValidationError(
                f"Intervention {action.action_id} has negative cost"
            )

        if not 0.0 <= action.harm_risk <= 1.0:
            raise SpecValidationError(
                f"Intervention {action.action_id} has invalid harm risk"
            )

        if not 0.0 <= action.success_probability <= 1.0:
            raise SpecValidationError(
                f"Intervention {action.action_id} has invalid success probability"
            )

        for distinction in action.restores:
            if distinction not in known_distinctions:
                raise SpecValidationError(
                    f"Intervention {action.action_id} restores unknown distinction: {distinction}"
                )

        if action.kind == ActionKind.REPAIR and not action.restores:
            raise SpecValidationError(
                f"Repair action {action.action_id} must restore at least one distinction"
            )

        if action.kind == ActionKind.EVIDENCE and not action.information_channels:
            raise SpecValidationError(
                f"Evidence action {action.action_id} requires information channels"
            )


def _has_stage_cycle(stages: tuple[StageSpec, ...]) -> bool:
    index_of = {stage.stage_id: idx for idx, stage in enumerate(stages)}

    produced_by: dict[str, list[str]] = defaultdict(list)
    for stage in stages:
        for distinction in stage.produces:
            produced_by[distinction].append(stage.stage_id)

    graph: dict[str, set[str]] = {stage.stage_id: set() for stage in stages}
    for stage in stages:
        stage_index = index_of[stage.stage_id]
        for consumed in stage.consumes:
            producers = produced_by.get(consumed, [])
            upstream = [producer for producer in producers if index_of[producer] < stage_index]

            if not upstream and producers:
                return True

            for producer in upstream:
                if producer != stage.stage_id:
                    graph[producer].add(stage.stage_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in graph[node]:
            if dfs(child):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(dfs(node) for node in graph)
