from __future__ import annotations

from pathlib import Path

import pytest

from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.loader import load_system_spec
from rescueos.compiler.schema import StageSpec, SystemSpec
from rescueos.compiler.validator import SpecValidationError, validate_spec
from rescueos.core.distinctions import ActionKind, Intervention, Task


def test_compiler_loads_and_compiles_sample() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    spec = load_system_spec(repo_root / "configs" / "communication_system.yaml")
    graph = compile_graph(spec)

    assert "receiver" in graph.stage_ids
    assert "confidence" in graph.distinctions
    assert "reliable_message" in graph.task_ids


def test_compiler_rejects_unknown_distinction() -> None:
    spec = SystemSpec(
        name="bad",
        allow_feedback_cycles=False,
        stages=(
            StageSpec(stage_id="s", consumes=(), produces=("a",)),
        ),
        tasks=(
            Task(task_id="t", required_distinctions={"unknown": 0.9}, recovery_threshold=0.1),
        ),
        interventions=(),
    )
    with pytest.raises(SpecValidationError):
        validate_spec(spec)


def test_compiler_rejects_invalid_target_stage() -> None:
    spec = SystemSpec(
        name="bad",
        allow_feedback_cycles=False,
        stages=(
            StageSpec(stage_id="s", consumes=(), produces=("a",)),
        ),
        tasks=(Task(task_id="t", required_distinctions={"a": 0.9}, recovery_threshold=0.1),),
        interventions=(
            Intervention(
                action_id="r",
                kind=ActionKind.REPAIR,
                targets=frozenset({"missing"}),
                restores=frozenset({"a"}),
                cost=1.0,
            ),
        ),
    )
    with pytest.raises(SpecValidationError):
        validate_spec(spec)


def test_compiler_rejects_cycles_without_feedback_semantics() -> None:
    spec = SystemSpec(
        name="cycle",
        allow_feedback_cycles=False,
        stages=(
            StageSpec(stage_id="a", consumes=("y",), produces=("x",)),
            StageSpec(stage_id="b", consumes=("x",), produces=("y",)),
        ),
        tasks=(Task(task_id="t", required_distinctions={"x": 0.5}, recovery_threshold=0.1),),
        interventions=(
            Intervention(
                action_id="r",
                kind=ActionKind.REPAIR,
                targets=frozenset({"a"}),
                restores=frozenset({"x"}),
                cost=1.0,
            ),
        ),
    )
    with pytest.raises(SpecValidationError):
        validate_spec(spec)
