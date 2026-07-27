from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given
from hypothesis import strategies as st

from qrtc.kernel import AdequacyStatus, Future, analyze_gate

STATES = [
    {"required": 0, "irrelevant": 0},
    {"required": 0, "irrelevant": 1},
    {"required": 1, "irrelevant": 0},
    {"required": 1, "irrelevant": 1},
]

FUTURES = (Future(name="required", function=lambda state: state["required"]),)


def _future_partition_equal(a: dict[str, int], b: dict[str, int]) -> bool:
    return a["required"] == b["required"]


@given(st.lists(st.integers(min_value=0, max_value=2), min_size=4, max_size=4))
def test_exact_iff_partitions_equal(gate_outputs: list[int]) -> None:
    def gate(state: dict[str, int]) -> int:
        return gate_outputs[STATES.index(state)]

    report = analyze_gate(STATES, FUTURES, gate, max_witnesses=0)

    gate_pairs_equal = {
        (i, j): gate_outputs[i] == gate_outputs[j]
        for i in range(len(STATES))
        for j in range(i + 1, len(STATES))
    }
    future_pairs_equal = {
        (i, j): _future_partition_equal(STATES[i], STATES[j])
        for i in range(len(STATES))
        for j in range(i + 1, len(STATES))
    }

    partitions_equal = gate_pairs_equal == future_pairs_equal
    assert (report.status is AdequacyStatus.EXACT) == partitions_equal


@given(st.lists(st.integers(min_value=0, max_value=3), min_size=4, max_size=4))
def test_witness_limit_does_not_change_classification(gate_outputs: list[int]) -> None:
    def gate(state: dict[str, int]) -> int:
        return gate_outputs[STATES.index(state)]

    report_all = analyze_gate(STATES, FUTURES, gate, max_witnesses=20)
    report_none = analyze_gate(STATES, FUTURES, gate, max_witnesses=0)

    assert report_all.status is report_none.status
    assert report_all.insufficiency_count == report_none.insufficiency_count
    assert report_all.excess_count == report_none.excess_count
