from dataclasses import dataclass

from qrtc.kernel import AdequacyStatus, Future, analyze_gate


@dataclass(frozen=True)
class State:
    required: int
    irrelevant: int


STATES = [
    State(required=0, irrelevant=0),
    State(required=0, irrelevant=1),
    State(required=1, irrelevant=0),
    State(required=1, irrelevant=1),
]

FUTURES = (
    Future(
        name="required_value",
        function=lambda state: state.required,
    ),
)


def test_exact_gate() -> None:
    report = analyze_gate(
        STATES,
        FUTURES,
        gate=lambda state: state.required,
    )

    assert report.status is AdequacyStatus.EXACT
    assert report.is_exact
    assert report.insufficiency_count == 0
    assert report.excess_count == 0
    assert not report.insufficient_witnesses
    assert not report.excessive_witnesses


def test_insufficient_gate() -> None:
    report = analyze_gate(
        STATES,
        FUTURES,
        gate=lambda state: None,
    )

    assert report.status is AdequacyStatus.INSUFFICIENT
    assert report.insufficiency_count > 0
    assert report.insufficient_witnesses
    assert not report.excessive_witnesses


def test_excessive_gate() -> None:
    report = analyze_gate(
        STATES,
        FUTURES,
        gate=lambda state: (
            state.required,
            state.irrelevant,
        ),
    )

    assert report.status is AdequacyStatus.EXCESSIVE
    assert report.excess_count > 0
    assert report.excessive_witnesses
    assert not report.insufficient_witnesses


def test_incomparable_gate() -> None:
    report = analyze_gate(
        STATES,
        FUTURES,
        gate=lambda state: state.irrelevant,
    )

    assert report.status is AdequacyStatus.INCOMPARABLE
    assert report.insufficiency_count > 0
    assert report.excess_count > 0
    assert report.insufficient_witnesses
    assert report.excessive_witnesses


def test_zero_witness_limit_still_reports_status() -> None:
    report = analyze_gate(
        STATES,
        FUTURES,
        gate=lambda state: None,
        max_witnesses=0,
    )

    assert report.status is AdequacyStatus.INSUFFICIENT
    assert report.insufficiency_count > 0
    assert not report.insufficient_witnesses


def test_negative_witness_limit_is_rejected() -> None:
    try:
        analyze_gate(
            STATES,
            FUTURES,
            gate=lambda state: state.required,
            max_witnesses=-1,
        )
    except ValueError as error:
        assert "max_witnesses" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_duplicate_future_names_are_rejected() -> None:
    duplicate_futures = (
        Future(name="required_value", function=lambda state: state.required),
        Future(name="required_value", function=lambda state: state.irrelevant),
    )

    try:
        analyze_gate(
            STATES,
            duplicate_futures,
            gate=lambda state: state.required,
        )
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("expected ValueError")
