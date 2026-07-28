from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from rescueos.compiler.schema import StageSpec, SystemSpec
from rescueos.compiler.validator import validate_spec
from rescueos.core.distinctions import ActionKind, Intervention, Task


def load_system_spec(path: str | Path) -> SystemSpec:
    data = _load_yaml(path)

    system = data.get("system", {})
    stages = tuple(
        StageSpec(
            stage_id=item["id"],
            consumes=tuple(item.get("consumes", [])),
            produces=tuple(item.get("produces", [])),
        )
        for item in data.get("stages", [])
    )

    tasks = tuple(
        Task(
            task_id=item["id"],
            required_distinctions=item.get("required_distinctions", {}),
            recovery_threshold=float(item.get("recovery_threshold", 0.0)),
        )
        for item in data.get("tasks", [])
    )

    interventions = []
    for item in data.get("interventions", []):
        kind = ActionKind(item.get("kind", "repair"))
        interventions.append(
            Intervention(
                action_id=item["id"],
                kind=kind,
                targets=frozenset(item.get("targets", [])),
                restores=frozenset(item.get("restores", [])),
                cost=float(item.get("cost", 0.0)),
                harm_risk=float(item.get("harm_risk", 0.0)),
                success_probability=float(item.get("success_probability", 1.0)),
                information_channels=frozenset(item.get("information_channels", [])),
                certified_safe_under_unknown=bool(
                    item.get("certified_safe_under_unknown", False)
                ),
            )
        )

    spec = SystemSpec(
        name=system.get("name", "unnamed_system"),
        allow_feedback_cycles=bool(system.get("allow_feedback_cycles", False)),
        stages=stages,
        tasks=tasks,
        interventions=tuple(interventions),
    )
    validate_spec(spec)
    return spec


def _load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
