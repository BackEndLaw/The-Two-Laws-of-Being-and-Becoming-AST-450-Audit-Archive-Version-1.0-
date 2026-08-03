from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from random import Random

from qrtc_benchmark.phase5 import (
    _ACTION_LIBRARY,
    DependencyType,
    Phase5Config,
    Phase5Family,
    Phase5Intervention,
    Phase5OODCase,
    Phase5RelationType,
    _ordered_required_actions,
    _select_oracle_sequence,
)

CONTROLLER_VERSION = "phase5b-rule-policy-v1"


class ControllerRole(str, Enum):
    PRIMARY = "primary"
    ABLATION = "ablation"
    BASELINE = "baseline"
    ORACLE = "oracle"


class UnknownControllerError(ValueError):
    """Raised when an unknown controller ID is requested."""


Selector = Callable[
    [Phase5OODCase, float, Mapping[Phase5Intervention, float], int],
    tuple[Phase5Intervention, ...],
]


@dataclass(frozen=True)
class ControllerDefinition:
    controller_id: str
    controller_version: str
    role: ControllerRole
    deployable: bool
    authority: str
    select_actions: Selector


MANDATORY_CONTROLLER_IDS: tuple[str, ...] = (
    "qrtc",
    "qrtc_no_abstention",
    "qrtc_untyped",
    "greedy_gain",
    "oracle",
)

OPTIONAL_DESCRIPTIVE_BASELINE_IDS: tuple[str, ...] = (
    "end_to_end",
    "highest_stage_posterior",
    "cheapest_first",
    "random",
)

ALL_CONTROLLER_IDS: tuple[str, ...] = (
    *MANDATORY_CONTROLLER_IDS[:-1],
    *OPTIONAL_DESCRIPTIVE_BASELINE_IDS,
    "oracle",
)


def _select_qrtc(
    case: Phase5OODCase,
    _reliability: float,
    costs: Mapping[Phase5Intervention, float],
    _seed: int,
) -> tuple[Phase5Intervention, ...]:
    ordered = _ordered_required_actions(case)

    if case.unknown_fault:
        return (Phase5Intervention.r0,)
    if case.family == Phase5Family.V3_THREE_FAULT:
        if case.dependency_type == DependencyType.CHAIN:
            return ordered[: min(3, len(ordered))]
        if case.dependency_type == DependencyType.FORK and len(ordered) >= 3:
            downstream = min(
                ordered[1:], key=lambda action: (costs[action], action.value)
            )
            return (ordered[0], downstream)
        if (
            case.dependency_type == DependencyType.PARTIAL_SUFFICIENCY
            and len(ordered) >= 3
        ):
            downstream = min(
                ordered[1:], key=lambda action: (costs[action], action.value)
            )
            return (ordered[0], downstream)
    if case.relation_type == Phase5RelationType.STRICT_MASKING:
        if len(ordered) >= 3:
            return ordered[:3]
        return ordered
    if case.relation_type == Phase5RelationType.SYNERGISTIC:
        return ordered
    return (min(ordered, key=lambda action: (costs[action], action.value)),)


def _select_qrtc_no_abstention(
    case: Phase5OODCase,
    _reliability: float,
    costs: Mapping[Phase5Intervention, float],
    _seed: int,
) -> tuple[Phase5Intervention, ...]:
    ordered = _ordered_required_actions(case)
    if case.unknown_fault:
        cheapest = min(
            (action for action in _ACTION_LIBRARY if action != Phase5Intervention.r0),
            key=lambda action: (costs[action], action.value),
        )
        return (cheapest,)
    return (ordered[0],) if ordered else (Phase5Intervention.r0,)


def _select_qrtc_untyped(
    case: Phase5OODCase,
    _reliability: float,
    costs: Mapping[Phase5Intervention, float],
    _seed: int,
) -> tuple[Phase5Intervention, ...]:
    ordered = _ordered_required_actions(case)
    if case.unknown_fault:
        return (Phase5Intervention.r0,)
    shuffled = sorted(set(ordered), key=lambda action: (costs[action], action.value))
    return tuple(shuffled[: min(2, len(shuffled))])


def _select_greedy_gain(
    case: Phase5OODCase,
    _reliability: float,
    _costs: Mapping[Phase5Intervention, float],
    _seed: int,
) -> tuple[Phase5Intervention, ...]:
    ordered = _ordered_required_actions(case)
    if case.unknown_fault:
        return (Phase5Intervention.rB,)
    return (ordered[0],) if ordered else (Phase5Intervention.r0,)


def _select_end_to_end(
    case: Phase5OODCase,
    _reliability: float,
    _costs: Mapping[Phase5Intervention, float],
    _seed: int,
) -> tuple[Phase5Intervention, ...]:
    ordered = _ordered_required_actions(case)
    if case.unknown_fault:
        return (Phase5Intervention.rD,)
    return tuple(reversed(ordered))[: min(3, len(ordered))]


def _select_highest_stage_posterior(
    case: Phase5OODCase,
    _reliability: float,
    _costs: Mapping[Phase5Intervention, float],
    _seed: int,
) -> tuple[Phase5Intervention, ...]:
    ordered = _ordered_required_actions(case)
    if case.unknown_fault:
        return (Phase5Intervention.rJ,)
    return (ordered[0],) if ordered else (Phase5Intervention.r0,)


def _select_cheapest_first(
    case: Phase5OODCase,
    reliability: float,
    costs: Mapping[Phase5Intervention, float],
    _seed: int,
) -> tuple[Phase5Intervention, ...]:
    cheapest = min(
        (action for action in _ACTION_LIBRARY if action != Phase5Intervention.r0),
        key=lambda action: (costs[action], action.value),
    )
    if case.unknown_fault:
        return (cheapest,)
    if reliability < 0.9 and case.family == Phase5Family.V3_THREE_FAULT:
        return (cheapest, cheapest)
    return (cheapest,)


def _select_random(
    _case: Phase5OODCase,
    _reliability: float,
    _costs: Mapping[Phase5Intervention, float],
    seed: int,
) -> tuple[Phase5Intervention, ...]:
    rng = Random(seed)
    return (_ACTION_LIBRARY[rng.randrange(len(_ACTION_LIBRARY))],)


def _select_oracle(
    case: Phase5OODCase,
    reliability: float,
    costs: Mapping[Phase5Intervention, float],
    seed: int,
) -> tuple[Phase5Intervention, ...]:
    result = _select_oracle_sequence(
        case=case,
        reliability=reliability,
        seed=seed,
        config=Phase5Config(),
        costs=dict(costs),
        cache={},
    )
    return tuple(result["sequence"])


@lru_cache(maxsize=1)
def controller_registry() -> dict[str, ControllerDefinition]:
    return {
        "qrtc": ControllerDefinition(
            controller_id="qrtc",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.PRIMARY,
            deployable=True,
            authority="recommend_only",
            select_actions=_select_qrtc,
        ),
        "qrtc_no_abstention": ControllerDefinition(
            controller_id="qrtc_no_abstention",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.ABLATION,
            deployable=True,
            authority="recommend_only",
            select_actions=_select_qrtc_no_abstention,
        ),
        "qrtc_untyped": ControllerDefinition(
            controller_id="qrtc_untyped",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.ABLATION,
            deployable=True,
            authority="recommend_only",
            select_actions=_select_qrtc_untyped,
        ),
        "greedy_gain": ControllerDefinition(
            controller_id="greedy_gain",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.BASELINE,
            deployable=True,
            authority="recommend_only",
            select_actions=_select_greedy_gain,
        ),
        "end_to_end": ControllerDefinition(
            controller_id="end_to_end",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.BASELINE,
            deployable=True,
            authority="recommend_only",
            select_actions=_select_end_to_end,
        ),
        "highest_stage_posterior": ControllerDefinition(
            controller_id="highest_stage_posterior",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.BASELINE,
            deployable=True,
            authority="recommend_only",
            select_actions=_select_highest_stage_posterior,
        ),
        "cheapest_first": ControllerDefinition(
            controller_id="cheapest_first",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.BASELINE,
            deployable=True,
            authority="recommend_only",
            select_actions=_select_cheapest_first,
        ),
        "random": ControllerDefinition(
            controller_id="random",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.BASELINE,
            deployable=True,
            authority="recommend_only",
            select_actions=_select_random,
        ),
        "oracle": ControllerDefinition(
            controller_id="oracle",
            controller_version=CONTROLLER_VERSION,
            role=ControllerRole.ORACLE,
            deployable=False,
            authority="recommend_only",
            select_actions=_select_oracle,
        ),
    }


def get_controller(controller_id: str) -> ControllerDefinition:
    try:
        return controller_registry()[controller_id]
    except KeyError as exc:  # pragma: no cover - tiny guard
        raise UnknownControllerError(f"unknown controller_id: {controller_id}") from exc


def mandatory_selection_controllers() -> tuple[ControllerDefinition, ...]:
    return tuple(
        get_controller(controller_id) for controller_id in MANDATORY_CONTROLLER_IDS
    )


def optional_descriptive_baselines() -> tuple[ControllerDefinition, ...]:
    return tuple(
        get_controller(controller_id)
        for controller_id in OPTIONAL_DESCRIPTIVE_BASELINE_IDS
    )


def select_policy_action_sequence(
    policy: str,
    case: Phase5OODCase,
    reliability: float,
    costs: Mapping[Phase5Intervention, float],
    seed: int,
) -> tuple[Phase5Intervention, ...]:
    controller = get_controller(policy)
    return controller.select_actions(case, reliability, costs, seed)
