from pathlib import Path

import pytest

from integrations.vehicle.blocked_route import load_scenario, replay_trace, run_blocked_route
from integrations.vehicle.run_pilot import run_matrix


SCENARIO = Path(__file__).parents[1] / "scenarios" / "blocked_route_v1.json"


@pytest.fixture
def scenario() -> dict:
    return load_scenario(SCENARIO)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_denied_transfer_retains_baseline_with_replayable_witness(scenario: dict, seed: int) -> None:
    first = run_blocked_route(scenario, seed=seed, specialist_admitted=False)
    repeated = run_blocked_route(scenario, seed=seed, specialist_admitted=False)
    event = first.events[0]

    assert first.events == repeated.events
    assert event["blocked_edge_detected"] is True
    assert event["baseline_proposal"]["type"] == "controlled_stop"
    assert event["specialist_proposal"]["type"] == "handoff"
    assert event["gate_decision"] == "denied"
    assert event["retained_jurisdiction"] == "v2"
    assert event["passage_committed"] is False
    assert event["passage_executed"] is False
    assert event["destination_realized"] is False
    assert event["selected_action"] == "controlled_stop"
    assert event["outcome"] == "safe"
    assert event["collision"] is False
    assert replay_trace(scenario, first.events)


def test_admission_does_not_realize_destination_before_execution(scenario: dict) -> None:
    result = run_blocked_route(
        scenario,
        seed=1,
        specialist_admitted=True,
        execute_handoff=False,
    )
    event = result.events[0]

    assert event["specialist_admitted"] is True
    assert event["passage_committed"] is True
    assert event["passage_executed"] is False
    assert event["destination_realized"] is False
    assert event["collision"] is False
    assert replay_trace(scenario, result.events)


def test_executed_handoff_realizes_destination(scenario: dict) -> None:
    event = run_blocked_route(scenario, seed=2, specialist_admitted=True).events[0]

    assert event["passage_executed"] is True
    assert event["destination_realized"] is True
    assert event["destination"] == "alternate-route controller active"
    assert event["outcome"] == "route_resumed_safely"
    assert event["collision"] is False


def test_failed_handoff_invokes_safe_fallback_without_destination(scenario: dict) -> None:
    event = run_blocked_route(
        scenario,
        seed=3,
        specialist_admitted=True,
        handoff_succeeds=False,
    ).events[0]

    assert event["passage_executed"] is True
    assert event["action_succeeded"] is False
    assert event["destination_realized"] is False
    assert event["fallback_invoked"] is True
    assert event["final_state"]["stopped"] is True
    assert event["final_state"]["controller"] == "baseline_v2"
    assert event["collision"] is False


def test_matrix_writes_fixed_seed_replayable_witnesses(scenario: dict, tmp_path: Path) -> None:
    summary = run_matrix(SCENARIO, tmp_path)

    assert summary["acceptance_passed"] is True
    assert summary["carla_used"] is False
    assert len(summary["runs"]) == 10
    assert {run["mode"] for run in summary["runs"]} == {"denied", "authorized"}
    assert len(list(tmp_path.glob("*.jsonl"))) == 10
    assert (tmp_path / "summary.json").is_file()