from __future__ import annotations

from rescueos.core.distinctions import ActionKind, BeliefState, Intervention, Task
from rescueos.core.planner import BoundedLookaheadPlanner, PlannerConfig


def test_planner_never_selects_negative_utility_path_over_stop() -> None:
    task = Task("t", {"decoded_message": 0.9}, 0.05)
    belief = BeliefState(
        distinction_health={"decoded_message": 0.2},
        fault_probabilities={},
        unknown_probability=0.0,
        confidence=0.9,
    )
    expensive = Intervention(
        action_id="expensive",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=100.0,
        harm_risk=0.2,
        success_probability=0.1,
    )
    planner = BoundedLookaheadPlanner([expensive])

    decision = planner.choose(belief, task, history=[])
    assert decision.kind == ActionKind.STOP


def test_evidence_action_requires_positive_value_of_information() -> None:
    task = Task("t", {"decoded_message": 0.9}, 0.05)
    belief = BeliefState(
        distinction_health={"decoded_message": 0.88},
        fault_probabilities={},
        unknown_probability=0.01,
        confidence=0.99,
    )
    evidence = Intervention(
        action_id="inspect",
        kind=ActionKind.EVIDENCE,
        targets=frozenset({"receiver"}),
        restores=frozenset(),
        cost=10.0,
        information_channels=frozenset({"gain"}),
    )
    planner = BoundedLookaheadPlanner([evidence])

    decision = planner.choose(belief, task, history=[])
    assert decision.action_id == "stop"


def test_unknown_fault_can_block_high_risk_repair() -> None:
    task = Task("t", {"decoded_message": 0.9}, 0.05)
    belief = BeliefState(
        distinction_health={"decoded_message": 0.4},
        fault_probabilities={},
        unknown_probability=0.9,
        confidence=0.2,
    )
    repair = Intervention(
        action_id="unsafe_repair",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=0.2,
        harm_risk=0.1,
        success_probability=0.9,
    )
    evidence = Intervention(
        action_id="inspect",
        kind=ActionKind.EVIDENCE,
        targets=frozenset({"receiver"}),
        restores=frozenset(),
        cost=0.01,
        information_channels=frozenset({"gain"}),
    )
    planner = BoundedLookaheadPlanner([repair, evidence], PlannerConfig(unknown_threshold=0.5))

    decision = planner.choose(belief, task, history=[])
    assert decision.kind in {ActionKind.EVIDENCE, ActionKind.STOP, ActionKind.ABSTAIN}
    assert decision.action_id != "unsafe_repair"


def test_deterministic_tie_breaking() -> None:
    task = Task("t", {"decoded_message": 0.9}, 0.05)
    belief = BeliefState(
        distinction_health={"decoded_message": 0.1},
        fault_probabilities={},
        unknown_probability=0.0,
        confidence=1.0,
    )
    a = Intervention(
        action_id="a_action",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=1.0,
        harm_risk=0.0,
        success_probability=0.5,
    )
    b = Intervention(
        action_id="b_action",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=1.0,
        harm_risk=0.0,
        success_probability=0.5,
    )
    planner = BoundedLookaheadPlanner([b, a])

    decision1 = planner.choose(belief, task, history=[])
    decision2 = planner.choose(belief, task, history=[])
    assert decision1.action_id == "a_action"
    assert decision2.action_id == "a_action"


def test_typed_structure_rejects_attractive_task_irrelevant_repair() -> None:
    task = Task("t", {"decoded_message": 0.9}, 0.05)
    belief = BeliefState(
        distinction_health={"decoded_message": 0.1, "timing": 0.1},
        fault_probabilities={},
        unknown_probability=0.0,
        confidence=1.0,
    )
    relevant = Intervention(
        action_id="relevant",
        kind=ActionKind.REPAIR,
        targets=frozenset({"receiver"}),
        restores=frozenset({"decoded_message"}),
        cost=1.0,
        success_probability=0.6,
    )
    irrelevant = Intervention(
        action_id="irrelevant",
        kind=ActionKind.REPAIR,
        targets=frozenset({"transmitter"}),
        restores=frozenset({"timing"}),
        cost=0.1,
        success_probability=0.95,
    )

    typed = BoundedLookaheadPlanner([irrelevant, relevant])
    untyped = BoundedLookaheadPlanner(
        [irrelevant, relevant],
        PlannerConfig(typed_structure=False),
    )

    assert typed.choose(belief, task, history=[]).action_id == "relevant"
    assert untyped.choose(belief, task, history=[]).action_id == "irrelevant"
