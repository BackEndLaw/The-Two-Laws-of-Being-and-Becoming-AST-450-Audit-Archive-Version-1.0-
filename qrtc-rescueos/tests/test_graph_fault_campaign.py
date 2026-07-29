from pathlib import Path

import pytest

from integrations.vehicle.graph_fault_campaign import (
    evaluate_campaign_run,
    load_campaign_scenario,
    replay_campaign_run,
    run_campaign_scenario,
)
from integrations.vehicle.run_graph_fault_campaign import (
    derive_evaluation_seeds,
    run_campaign,
)


SCENARIO_DIR = Path("scenarios/graph_fault_campaign_v1")
SCENARIOS = sorted(SCENARIO_DIR.glob("GF-*.json"))


def test_gf02_handoff_timeout_restores_safe_authority_without_passage() -> None:
    scenario = load_campaign_scenario("scenarios/graph_fault_campaign_v1/GF-02.json")

    run = run_campaign_scenario(scenario, seed=2, seed_class="regression")
    terminal = run.events[-1]

    assert terminal["admitted"] is True
    assert terminal["passage_requested"] is True
    assert terminal["passage_executed"] is False
    assert terminal["destination_realized"] is False
    assert terminal["fallback_invoked"] is True
    assert terminal["authority"] == "baseline_v2"
    assert terminal["terminal_state"] == "safe"
    assert all(event["authority_count"] == 1 for event in run.events)
    assert replay_campaign_run(scenario, run)


@pytest.mark.parametrize("scenario_path", SCENARIOS, ids=lambda path: path.stem)
def test_named_graph_fault_scenario_passes_declared_contract(
    scenario_path: Path,
) -> None:
    scenario = load_campaign_scenario(scenario_path)

    run = run_campaign_scenario(scenario, seed=23, seed_class="evaluation")
    evaluation = evaluate_campaign_run(scenario, run)

    assert evaluation["violations"] == []
    assert evaluation["passed"] is True
    assert evaluation["witness_complete"] is True
    assert evaluation["replay_verified"] is True
    assert evaluation["collision"] is False
    assert evaluation["illegal_graph_transition"] is False


def test_gf06_contains_delayed_and_missing_observation_subcases() -> None:
    scenario = load_campaign_scenario(SCENARIO_DIR / "GF-06.json")
    run = run_campaign_scenario(scenario, seed=6, seed_class="regression")

    subcases = {
        event["subcase"]
        for event in run.events
        if event["event"] == "observation_rejected"
    }

    assert subcases == {"GF-06A", "GF-06B"}


def test_evaluation_seed_derivation_is_frozen_before_execution() -> None:
    assert derive_evaluation_seeds("GF-02") == [
        300059,
        289401,
        689573,
        610440,
        832142,
    ]


def test_complete_campaign_writes_100_replay_verified_traces(tmp_path: Path) -> None:
    summary = run_campaign(
        SCENARIO_DIR / "campaign.json",
        tmp_path,
        full_suite_test_count=1,
        diagnostics_clean=True,
    )

    assert summary["campaign_acceptance"] == "PASSED"
    assert summary["scenarios_passed"] == 10
    assert summary["runs_passed"] == 100
    assert summary["invariant_violations"] == []
    assert summary["collisions"] == 0
    assert summary["illegal_graph_transitions"] == 0
    assert summary["all_witnesses_complete"] is True
    assert summary["all_replays_verified"] is True
    assert len(list(tmp_path.glob("GF-*/traces/*.jsonl"))) == 100
    assert (tmp_path / "SHA256SUMS").is_file()