from __future__ import annotations

import pytest

from rescueos.adapters.simulator import SimulatorAdapter
from rescueos.audit.event_log import AuditEventLog
from rescueos.compiler.graph_compiler import compile_graph
from rescueos.compiler.schema import StageSpec, SystemSpec
from rescueos.core.belief import SimpleBeliefUpdater
from rescueos.core.controller import RescueController
from rescueos.core.distinctions import ActionKind, BeliefState, Intervention, Task
from rescueos.core.planner import BoundedLookaheadPlanner
from rescueos.core.transition import RealizedOutcome, SystemState, TransitionModel
from rescueos.simulator.communication_link import CommunicationLinkSimulator


def _task() -> Task:
    return Task("deliver", {"output": 0.9}, 0.05)


def _repair(action_id: str, restores: str, target: str, cost: float = 0.1) -> Intervention:
    return Intervention(
        action_id=action_id,
        kind=ActionKind.REPAIR,
        targets=frozenset({target}),
        restores=frozenset({restores}),
        cost=cost,
        success_probability=1.0,
        certified_safe_under_unknown=True,
    )


def _spec() -> SystemSpec:
    return SystemSpec(
        name="linear_with_branch",
        allow_feedback_cycles=False,
        stages=(
            StageSpec("source", (), ("upstream",)),
            StageSpec("middle", ("upstream",), ("downstream",)),
            StageSpec("decision", ("downstream",), ("output",)),
            StageSpec("branch", ("upstream",), ("branch_output",)),
        ),
        tasks=(_task(),),
        interventions=(
            _repair("repair_upstream", "upstream", "source"),
            _repair("repair_downstream", "downstream", "middle"),
            _repair("repair_output", "output", "decision"),
            _repair("repair_branch", "branch_output", "branch"),
        ),
    )


def _state(upstream: float = 0.2, downstream: float = 1.0) -> SystemState:
    graph = compile_graph(_spec())
    state = SystemState.from_health(
        {
            "upstream": upstream,
            "downstream": downstream,
            "output": 1.0,
            "branch_output": 0.7,
            "confidence": 1.0,
        }
    )
    graph.propagate(state, frozenset(graph.topological_order))
    return state


def test_compiled_graph_contains_transitive_action_reachability() -> None:
    graph = compile_graph(_spec())

    assert graph.affected_nodes("repair_upstream") == frozenset(
        {"upstream", "downstream", "output", "branch_output"}
    )
    assert graph.action_can_influence("repair_upstream", "deliver")
    assert not graph.action_can_influence("repair_branch", "deliver")


def test_planner_and_simulator_graph_checksums_match() -> None:
    spec = _spec()
    graph = compile_graph(spec)
    transition = TransitionModel(graph)
    planner = BoundedLookaheadPlanner(
        list(spec.interventions), graph=graph, transition_model=transition
    )
    simulator = CommunicationLinkSimulator(
        spec.interventions, graph=graph, transition_model=transition
    )

    assert planner.graph_checksum == simulator.graph_checksum == graph.checksum


def test_upstream_repair_propagates_through_healthy_descendants() -> None:
    spec = _spec()
    graph = compile_graph(spec)
    repaired = TransitionModel(graph).apply(
        _state(), spec.interventions[0], RealizedOutcome(succeeded=True)
    )

    assert repaired.local_health["downstream"] == 1.0
    assert repaired.distinction_quality["output"] == 1.0


def test_upstream_repair_preserves_independent_downstream_fault() -> None:
    spec = _spec()
    repaired = TransitionModel(compile_graph(spec)).apply(
        _state(downstream=0.3), spec.interventions[0], RealizedOutcome(succeeded=True)
    )

    assert repaired.local_health["upstream"] == 1.0
    assert repaired.local_health["downstream"] == 0.3
    assert repaired.distinction_quality["output"] == 0.3


def test_downstream_repair_cannot_restore_missing_upstream_information() -> None:
    spec = _spec()
    repaired = TransitionModel(compile_graph(spec)).apply(
        _state(), spec.interventions[2], RealizedOutcome(succeeded=True)
    )

    assert repaired.local_health["output"] == 1.0
    assert repaired.distinction_quality["output"] == 0.2


def test_unrelated_branch_is_unchanged() -> None:
    spec = _spec()
    state = _state()
    before = state.distinction_quality["branch_output"]
    repaired = TransitionModel(compile_graph(spec)).apply(
        state, spec.interventions[1], RealizedOutcome(succeeded=True)
    )

    assert repaired.distinction_quality["branch_output"] == before
    assert repaired.local_health["branch_output"] == 0.7


def test_propagation_uses_topological_order() -> None:
    graph = compile_graph(_spec())
    state = _state()
    state.distinction_quality.update(upstream=0.4, downstream=1.0, output=1.0)

    graph.propagate(state, frozenset({"upstream", "downstream", "output"}))

    assert graph.topological_order.index("upstream") < graph.topological_order.index("output")
    assert state.distinction_quality["output"] == 0.2


def test_typed_planner_selects_relevant_upstream_repair() -> None:
    spec = _spec()
    graph = compile_graph(spec)
    state = _state()
    belief = BeliefState(
        distinction_health=state.distinction_quality,
        local_health=state.local_health,
        fault_probabilities={},
        unknown_probability=0.0,
        confidence=1.0,
    )
    planner = BoundedLookaheadPlanner(
        [spec.interventions[0], spec.interventions[3]], graph=graph
    )

    assert planner.choose(belief, _task(), []).action_id == "repair_upstream"


def test_typed_planner_accounts_for_downstream_blocker() -> None:
    spec = _spec()
    graph = compile_graph(spec)
    state = _state(downstream=0.3)
    belief = BeliefState(
        distinction_health=state.distinction_quality,
        local_health=state.local_health,
        fault_probabilities={},
        unknown_probability=0.0,
        confidence=1.0,
    )
    planner = BoundedLookaheadPlanner([spec.interventions[0]], graph=graph)

    decision = planner.choose(belief, _task(), [])

    assert decision.action_id == "repair_upstream"
    assert decision.expected_recovery_probability == pytest.approx(0.4)
    assert decision.expected_recovery_probability < 1.0 - _task().recovery_threshold


def test_deterministic_rollout_matches_simulator_transition() -> None:
    spec = _spec()
    graph = compile_graph(spec)
    transition = TransitionModel(graph)
    initial = _state()
    predicted = transition.apply(
        initial, spec.interventions[0], RealizedOutcome(succeeded=True)
    )
    simulator = CommunicationLinkSimulator(
        spec.interventions,
        initial_health=initial.local_health,
        graph=graph,
        transition_model=transition,
        seed=4,
    )

    simulator.apply("repair_upstream")

    assert simulator.state == predicted


def test_controller_stops_immediately_after_propagated_recovery() -> None:
    spec = _spec()
    graph = compile_graph(spec)
    transition = TransitionModel(graph)
    simulator = CommunicationLinkSimulator(
        spec.interventions,
        initial_health=_state().local_health,
        graph=graph,
        transition_model=transition,
    )
    controller = RescueController(
        adapter=SimulatorAdapter(simulator),
        inference=SimpleBeliefUpdater(),
        planner=BoundedLookaheadPlanner(
            list(spec.interventions), graph=graph, transition_model=transition
        ),
        audit_log=AuditEventLog(),
    )

    result = controller.rescue(_task(), max_actions=4)

    assert result.status == "recovered"
    assert result.actions_executed == 1