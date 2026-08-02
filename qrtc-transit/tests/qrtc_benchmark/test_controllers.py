from __future__ import annotations

import pytest

from qrtc_benchmark import controllers
from qrtc_benchmark.phase5 import (
    INTERVENTION_COSTS_BASE,
    Phase5Config,
    Phase5Family,
    Phase5Intervention,
    Phase5OODCase,
    Phase5RelationType,
    _policy_action_sequence,
    _select_oracle_sequence,
)
from qrtc_benchmark.phase5 import DependencyType as Phase5DependencyType


def _costs() -> dict[Phase5Intervention, float]:
    return dict(INTERVENTION_COSTS_BASE)


def _case(
    *,
    family: Phase5Family,
    relation: Phase5RelationType,
    dependency: Phase5DependencyType,
    unknown_fault: bool,
    required: tuple[Phase5Intervention, ...],
) -> Phase5OODCase:
    return Phase5OODCase(
        family=family,
        mechanism_id="m1",
        composition_id="c1",
        relation_type=relation,
        criterion="PI1",
        severity=0.5,
        noise=0.1,
        dependency_type=dependency,
        unknown_fault=unknown_fault,
        evidence_initially_insufficient=unknown_fault,
        required_actions=required,
    )


def test_controller_registry_classification_and_candidate_sets() -> None:
    registry = controllers.controller_registry()
    assert set(registry) == set(controllers.ALL_CONTROLLER_IDS)

    mandatory = controllers.mandatory_selection_controllers()
    optional = controllers.optional_descriptive_baselines()

    assert [item.controller_id for item in mandatory] == list(
        controllers.MANDATORY_CONTROLLER_IDS
    )
    assert [item.controller_id for item in optional] == list(
        controllers.OPTIONAL_DESCRIPTIVE_BASELINE_IDS
    )

    assert registry["qrtc"].role is controllers.ControllerRole.PRIMARY
    assert registry["qrtc_no_abstention"].role is controllers.ControllerRole.ABLATION
    assert registry["qrtc_untyped"].role is controllers.ControllerRole.ABLATION
    assert registry["greedy_gain"].role is controllers.ControllerRole.BASELINE
    assert registry["oracle"].role is controllers.ControllerRole.ORACLE
    assert not registry["oracle"].deployable
    assert all(item.authority == "recommend_only" for item in registry.values())


def test_unknown_controller_id_fails_closed() -> None:
    with pytest.raises(controllers.UnknownControllerError):
        controllers.get_controller("does-not-exist")


def test_policy_wrapper_and_controller_parity_for_known_policies() -> None:
    costs = _costs()
    seed = 123
    reliability = 0.8
    cases = [
        _case(
            family=Phase5Family.V4_UNKNOWN_FAULT,
            relation=Phase5RelationType.INDEPENDENT,
            dependency=Phase5DependencyType.NONE,
            unknown_fault=True,
            required=(),
        ),
        _case(
            family=Phase5Family.V3_THREE_FAULT,
            relation=Phase5RelationType.INDEPENDENT,
            dependency=Phase5DependencyType.CHAIN,
            unknown_fault=False,
            required=(
                Phase5Intervention.rG,
                Phase5Intervention.rW,
                Phase5Intervention.rJ,
            ),
        ),
        _case(
            family=Phase5Family.V3_THREE_FAULT,
            relation=Phase5RelationType.INDEPENDENT,
            dependency=Phase5DependencyType.FORK,
            unknown_fault=False,
            required=(
                Phase5Intervention.rB,
                Phase5Intervention.rR,
                Phase5Intervention.rJ,
            ),
        ),
        _case(
            family=Phase5Family.V3_THREE_FAULT,
            relation=Phase5RelationType.INDEPENDENT,
            dependency=Phase5DependencyType.PARTIAL_SUFFICIENCY,
            unknown_fault=False,
            required=(
                Phase5Intervention.rG,
                Phase5Intervention.rD,
                Phase5Intervention.rW,
            ),
        ),
        _case(
            family=Phase5Family.V2_UNSEEN_PAIR,
            relation=Phase5RelationType.STRICT_MASKING,
            dependency=Phase5DependencyType.NONE,
            unknown_fault=False,
            required=(
                Phase5Intervention.rB,
                Phase5Intervention.rR,
                Phase5Intervention.rJ,
            ),
        ),
        _case(
            family=Phase5Family.V2_UNSEEN_PAIR,
            relation=Phase5RelationType.SYNERGISTIC,
            dependency=Phase5DependencyType.NONE,
            unknown_fault=False,
            required=(
                Phase5Intervention.rD,
                Phase5Intervention.rW,
            ),
        ),
    ]

    for case in cases:
        for policy in controllers.ALL_CONTROLLER_IDS:
            if policy == "oracle":
                continue
            from_registry = controllers.select_policy_action_sequence(
                policy=policy,
                case=case,
                reliability=reliability,
                costs=costs,
                seed=seed,
            )
            from_wrapper = _policy_action_sequence(
                policy=policy,
                case=case,
                reliability=reliability,
                costs=costs,
                seed=seed,
            )
            assert from_registry == from_wrapper


def test_parity_fixtures_for_reference_policy_behavior() -> None:
    costs = _costs()

    unknown = _case(
        family=Phase5Family.V4_UNKNOWN_FAULT,
        relation=Phase5RelationType.INDEPENDENT,
        dependency=Phase5DependencyType.NONE,
        unknown_fault=True,
        required=(),
    )
    assert controllers.select_policy_action_sequence(
        "qrtc", unknown, 1.0, costs, 100
    ) == (Phase5Intervention.r0,)
    assert controllers.select_policy_action_sequence(
        "qrtc_no_abstention", unknown, 1.0, costs, 100
    ) == (Phase5Intervention.rJ,)
    assert controllers.select_policy_action_sequence(
        "qrtc_untyped", unknown, 1.0, costs, 100
    ) == (Phase5Intervention.r0,)

    chain = _case(
        family=Phase5Family.V3_THREE_FAULT,
        relation=Phase5RelationType.INDEPENDENT,
        dependency=Phase5DependencyType.CHAIN,
        unknown_fault=False,
        required=(
            Phase5Intervention.rG,
            Phase5Intervention.rW,
            Phase5Intervention.rJ,
        ),
    )
    assert controllers.select_policy_action_sequence("qrtc", chain, 1.0, costs, 100) == (
        Phase5Intervention.rG,
        Phase5Intervention.rW,
        Phase5Intervention.rJ,
    )

    fork = _case(
        family=Phase5Family.V3_THREE_FAULT,
        relation=Phase5RelationType.INDEPENDENT,
        dependency=Phase5DependencyType.FORK,
        unknown_fault=False,
        required=(
            Phase5Intervention.rB,
            Phase5Intervention.rR,
            Phase5Intervention.rJ,
        ),
    )
    assert controllers.select_policy_action_sequence("qrtc", fork, 1.0, costs, 100) == (
        Phase5Intervention.rB,
        Phase5Intervention.rJ,
    )

    partial = _case(
        family=Phase5Family.V3_THREE_FAULT,
        relation=Phase5RelationType.INDEPENDENT,
        dependency=Phase5DependencyType.PARTIAL_SUFFICIENCY,
        unknown_fault=False,
        required=(
            Phase5Intervention.rG,
            Phase5Intervention.rD,
            Phase5Intervention.rW,
        ),
    )
    assert controllers.select_policy_action_sequence("qrtc", partial, 1.0, costs, 100) == (
        Phase5Intervention.rG,
        Phase5Intervention.rW,
    )

    strict = _case(
        family=Phase5Family.V2_UNSEEN_PAIR,
        relation=Phase5RelationType.STRICT_MASKING,
        dependency=Phase5DependencyType.NONE,
        unknown_fault=False,
        required=(
            Phase5Intervention.rB,
            Phase5Intervention.rR,
            Phase5Intervention.rJ,
        ),
    )
    assert controllers.select_policy_action_sequence("qrtc", strict, 1.0, costs, 100) == (
        Phase5Intervention.rB,
        Phase5Intervention.rR,
        Phase5Intervention.rJ,
    )

    synergistic = _case(
        family=Phase5Family.V2_UNSEEN_PAIR,
        relation=Phase5RelationType.SYNERGISTIC,
        dependency=Phase5DependencyType.NONE,
        unknown_fault=False,
        required=(Phase5Intervention.rD, Phase5Intervention.rW),
    )
    assert controllers.select_policy_action_sequence(
        "qrtc", synergistic, 1.0, costs, 100
    ) == (Phase5Intervention.rD, Phase5Intervention.rW)

    ordinary = _case(
        family=Phase5Family.V2_UNSEEN_PAIR,
        relation=Phase5RelationType.INDEPENDENT,
        dependency=Phase5DependencyType.NONE,
        unknown_fault=False,
        required=(Phase5Intervention.rD, Phase5Intervention.rW),
    )
    assert controllers.select_policy_action_sequence("qrtc", ordinary, 1.0, costs, 100) == (
        Phase5Intervention.rW,
    )

    assert controllers.select_policy_action_sequence(
        "greedy_gain", ordinary, 1.0, costs, 100
    ) == (Phase5Intervention.rD,)
    assert controllers.select_policy_action_sequence(
        "greedy_gain", unknown, 1.0, costs, 100
    ) == (Phase5Intervention.rB,)


def test_oracle_controller_matches_oracle_selection_integration_boundary() -> None:
    costs = _costs()
    case = _case(
        family=Phase5Family.V3_THREE_FAULT,
        relation=Phase5RelationType.SOFT_MASKING,
        dependency=Phase5DependencyType.NONE,
        unknown_fault=False,
        required=(
            Phase5Intervention.rB,
            Phase5Intervention.rJ,
            Phase5Intervention.rR,
        ),
    )
    expected = _select_oracle_sequence(
        case=case,
        reliability=0.8,
        seed=404,
        config=Phase5Config(),
        costs=costs,
        cache={},
    )
    selected = controllers.select_policy_action_sequence("oracle", case, 0.8, costs, 404)
    assert selected == tuple(expected["sequence"])


def test_random_baseline_is_deterministic_when_exposed() -> None:
    costs = _costs()
    case = _case(
        family=Phase5Family.V1_UNSEEN_MECHANISM,
        relation=Phase5RelationType.INDEPENDENT,
        dependency=Phase5DependencyType.NONE,
        unknown_fault=False,
        required=(Phase5Intervention.rG,),
    )
    first = controllers.select_policy_action_sequence("random", case, 1.0, costs, 909)
    second = controllers.select_policy_action_sequence("random", case, 1.0, costs, 909)
    third = controllers.select_policy_action_sequence("random", case, 1.0, costs, 910)
    assert first == second
    assert first != third
