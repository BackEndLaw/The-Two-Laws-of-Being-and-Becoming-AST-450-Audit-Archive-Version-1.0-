from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Any, Generic, TypeVar

State = TypeVar("State")

Gate = Callable[[State], Any]
FutureFunction = Callable[[State], Any]


class AdequacyStatus(str, Enum):
    EXACT = "exact"
    INSUFFICIENT = "insufficient"
    EXCESSIVE = "excessive"
    INCOMPARABLE = "incomparable"


@dataclass(frozen=True)
class Future(Generic[State]):
    """
    A named downstream behavior declared as part of the future family.
    """

    name: str
    function: FutureFunction[State]


@dataclass(frozen=True)
class Counterexample(Generic[State]):
    """
    A pair of predecessor states witnessing a mismatch between the actual
    Gate and the declared future family.
    """

    left_index: int
    right_index: int
    left: State
    right: State
    gate_left: Any
    gate_right: Any
    future_left: Mapping[str, Any]
    future_right: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "left_index": self.left_index,
            "right_index": self.right_index,
            "left": self.left,
            "right": self.right,
            "gate_left": self.gate_left,
            "gate_right": self.gate_right,
            "future_left": dict(self.future_left),
            "future_right": dict(self.future_right),
        }


@dataclass(frozen=True)
class AdequacyReport(Generic[State]):
    status: AdequacyStatus
    state_count: int
    pair_count: int
    insufficiency_count: int
    excess_count: int
    insufficient_witnesses: tuple[Counterexample[State], ...]
    excessive_witnesses: tuple[Counterexample[State], ...]
    scope_label: str = "Exact over the finite declared model—not universal exactness."

    @property
    def is_exact(self) -> bool:
        return self.status is AdequacyStatus.EXACT

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "scope": "finite-declared-model",
            "scope_label": self.scope_label,
            "state_count": self.state_count,
            "pair_count": self.pair_count,
            "insufficiency_count": self.insufficiency_count,
            "excess_count": self.excess_count,
            "insufficient_witnesses": [
                witness.as_dict() for witness in self.insufficient_witnesses
            ],
            "excessive_witnesses": [
                witness.as_dict() for witness in self.excessive_witnesses
            ],
        }


def evaluate_future(
    state: State,
    futures: Sequence[Future[State]],
) -> dict[str, Any]:
    return {future.name: future.function(state) for future in futures}


def future_equivalent(
    left: State,
    right: State,
    futures: Sequence[Future[State]],
) -> bool:
    """
    left ~F right iff every declared future has the same result
    for the two predecessor states.
    """

    return all(future.function(left) == future.function(right) for future in futures)


def gate_equivalent(
    left: State,
    right: State,
    gate: Gate[State],
) -> bool:
    """
    left ~G right iff the implemented Gate emits equal interfaces.
    """

    return gate(left) == gate(right)


@dataclass(frozen=True)
class _StateEvaluation(Generic[State]):
    state: State
    gate_value: Any
    future_values: dict[str, Any]


def _validate_futures(futures: Sequence[Future[State]]) -> None:
    names = [future.name for future in futures]
    if len(names) != len(set(names)):
        raise ValueError("future names must be unique")


def _evaluate_states(
    states: Sequence[State],
    futures: Sequence[Future[State]],
    gate: Gate[State],
) -> list[_StateEvaluation[State]]:
    return [
        _StateEvaluation(
            state=state,
            gate_value=gate(state),
            future_values=evaluate_future(state, futures),
        )
        for state in states
    ]


def classify_status(
    *,
    has_insufficiency: bool,
    has_excess: bool,
) -> AdequacyStatus:
    if has_insufficiency and has_excess:
        return AdequacyStatus.INCOMPARABLE

    if has_insufficiency:
        return AdequacyStatus.INSUFFICIENT

    if has_excess:
        return AdequacyStatus.EXCESSIVE

    return AdequacyStatus.EXACT


def analyze_gate(
    states: Iterable[State],
    futures: Sequence[Future[State]],
    gate: Gate[State],
    *,
    max_witnesses: int = 20,
) -> AdequacyReport[State]:
    """
    Compare the implemented Gate relation ~G with the declared-future
    relation ~F over a finite predecessor model.

    Insufficient:
        Gate merges states that a declared future distinguishes.

    Excessive:
        Gate distinguishes states that no declared future distinguishes.

    Exact:
        ~G = ~F over every modeled pair.

    Incomparable:
        Both insufficiency and excess occur.
    """

    if max_witnesses < 0:
        raise ValueError("max_witnesses must be non-negative")

    _validate_futures(futures)

    modeled_states = list(states)
    evaluations = _evaluate_states(modeled_states, futures, gate)

    insufficient: list[Counterexample[State]] = []
    excessive: list[Counterexample[State]] = []
    insufficiency_count = 0
    excess_count = 0
    pair_count = 0

    for (left_index, left), (right_index, right) in combinations(
        enumerate(evaluations),
        2,
    ):
        pair_count += 1

        gate_left = left.gate_value
        gate_right = right.gate_value

        gate_equal = gate_left == gate_right

        future_left = left.future_values
        future_right = right.future_values

        future_equal = future_left == future_right

        witness = Counterexample(
            left_index=left_index,
            right_index=right_index,
            left=left.state,
            right=right.state,
            gate_left=gate_left,
            gate_right=gate_right,
            future_left=future_left,
            future_right=future_right,
        )

        if gate_equal and not future_equal:
            insufficiency_count += 1
            if len(insufficient) < max_witnesses:
                insufficient.append(witness)

        if future_equal and not gate_equal:
            excess_count += 1
            if len(excessive) < max_witnesses:
                excessive.append(witness)

    status = classify_status(
        has_insufficiency=insufficiency_count > 0,
        has_excess=excess_count > 0,
    )

    return AdequacyReport(
        status=status,
        state_count=len(modeled_states),
        pair_count=pair_count,
        insufficiency_count=insufficiency_count,
        excess_count=excess_count,
        insufficient_witnesses=tuple(insufficient),
        excessive_witnesses=tuple(excessive),
    )
