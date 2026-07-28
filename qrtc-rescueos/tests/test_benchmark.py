from __future__ import annotations

from pathlib import Path

from rescueos import RESULT_NAME
from rescueos.experiments.benchmark import POLICIES, run_benchmark


def test_benchmark_produces_policy_rows_for_each_k() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = run_benchmark(
        repo_root / "configs" / "communication_system.yaml",
        max_faults=2,
        runs_per_k=3,
        max_actions=2,
        seed=99,
    )

    summary = payload["summary"]
    trials = payload["trials"]

    assert payload["config"]["result_name"] == RESULT_NAME
    assert payload["acceptance"]["result_name"] == RESULT_NAME
    assert all(row["result_name"] == RESULT_NAME for row in summary)
    assert all(row["result_name"] == RESULT_NAME for row in trials)
    assert len(summary) == len(POLICIES) * 2
    assert len(trials) == len(POLICIES) * 2 * 3

    for row in summary:
        assert row["n_trials"] == 3
        assert 0.0 <= row["recovery_rate"] <= 1.0


def test_benchmark_uses_equal_trial_count_across_policies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = run_benchmark(
        repo_root / "configs" / "communication_system.yaml",
        max_faults=3,
        runs_per_k=2,
        max_actions=2,
        seed=7,
    )

    counts_by_k: dict[int, set[int]] = {}
    for row in payload["summary"]:
        k = int(row["k_faults"])
        counts_by_k.setdefault(k, set()).add(int(row["n_trials"]))

    for values in counts_by_k.values():
        assert values == {2}


def test_benchmark_supports_locked_fault_bank() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = run_benchmark(
        repo_root / "configs" / "communication_system.yaml",
        max_faults=2,
        runs_per_k=2,
        max_actions=2,
        seed=7,
        fault_bank_path=repo_root / "configs" / "fault_bank_locked.yaml",
    )

    scenario_ids = {row["scenario_id"] for row in payload["trials"]}
    assert "k1_s1" in scenario_ids
    assert "k2_s2" in scenario_ids

    unknown_trials = [row for row in payload["trials"] if row["is_unknown_fault"] == 1.0]
    adversarial_unknown_trials = [
        row for row in payload["trials"] if row["is_adversarial_unknown"] == 1.0
    ]
    assert unknown_trials
    assert adversarial_unknown_trials


def test_benchmark_emits_acceptance_report() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = run_benchmark(
        repo_root / "configs" / "communication_system.yaml",
        max_faults=2,
        runs_per_k=2,
        max_actions=2,
        seed=12,
    )

    acceptance = payload["acceptance"]
    assert "all_k_pass" in acceptance
    assert "by_k" in acceptance
    assert len(acceptance["by_k"]) == 2
    for row in acceptance["by_k"]:
        assert "pass_unsafe_unknown_threshold" in row
        assert "pass_unsafe_unknown_superiority" in row


def test_benchmark_can_lock_acceptance_to_greedy_baseline() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = run_benchmark(
        repo_root / "configs" / "communication_system.yaml",
        max_faults=2,
        runs_per_k=2,
        max_actions=2,
        seed=12,
        baseline_policy="greedy",
    )

    assert payload["config"]["acceptance_targets"]["baseline_policy"] == "greedy"
    assert all(
        row["strongest_nonoracle"] == "greedy"
        for row in payload["acceptance"]["by_k"]
    )
