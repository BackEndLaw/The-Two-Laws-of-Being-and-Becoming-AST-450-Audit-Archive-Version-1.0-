from __future__ import annotations

from pathlib import Path

from rescueos.experiments.development_benchmark import (
    BREAKDOWNS,
    COMPARATORS,
    POLICIES,
    cluster_bootstrap,
    cluster_differences,
    run_development_benchmark,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict:
    return run_development_benchmark(
        REPO_ROOT / "configs" / "communication_system.yaml",
        REPO_ROOT / "configs" / "development_mechanisms.json",
        REPO_ROOT / "configs" / "hidden_mechanisms.json",
        REPO_ROOT / "configs" / "hidden_mechanisms.lock.json",
        replicates=1,
        bootstrap_samples=100,
    )


def test_development_benchmark_runs_all_policies_on_matched_trials() -> None:
    payload = _payload()
    grouped: dict[tuple[str, int], set[tuple[str, int]]] = {}
    for row in payload["trials"]:
        key = (row["cluster_id"], row["replicate"])
        grouped.setdefault(key, set()).add((row["policy"], row["seed"]))

    assert payload["policies"] == list(POLICIES)
    assert payload["total_policy_runs"] == payload["matched_trial_count"] * len(POLICIES)
    assert all({policy for policy, _ in values} == set(POLICIES) for values in grouped.values())
    assert all(len({seed for _, seed in values}) == 1 for values in grouped.values())


def test_strongest_nonoracle_is_selected_from_complete_run() -> None:
    payload = _payload()
    utilities = {row["policy"]: row["utility"] for row in payload["overall"]}

    assert payload["strongest_nonoracle"] in COMPARATORS
    assert payload["strongest_nonoracle"] == max(COMPARATORS, key=utilities.get)


def test_development_benchmark_reports_required_breakdowns_and_diagnostics() -> None:
    payload = _payload()
    diagnostics = payload["precision_diagnostics"]

    assert set(payload["breakdowns"]) == set(BREAKDOWNS)
    assert diagnostics["matched_trial_count"] > 0
    assert diagnostics["independent_cluster_count"] > 0
    assert diagnostics["cluster_size_distribution"]["sizes"]
    assert diagnostics["paired_cluster_difference_sd"] >= 0.0
    assert diagnostics["per_mechanism_effects"]
    assert diagnostics["common_random_numbers"] is True
    assert diagnostics["width_drivers"]["correlated_random_streams"] is False
    assert payload["bootstrap"]["method"] == "paired cluster bootstrap"
    assert all(row["oracle_regret"] >= 0.0 for row in payload["trials"])
    assert all("signed_oracle_gap" in row for row in payload["trials"])
    assert payload["hardware_actuation_enabled"] is False
    assert payload["hardware_gate"] == "NOT READY"


def test_cluster_bootstrap_uses_cluster_level_paired_differences() -> None:
    rows = [
        {"cluster_id": "a", "policy": "qrtc", "utility": 1.0},
        {"cluster_id": "a", "policy": "baseline", "utility": 0.5},
        {"cluster_id": "b", "policy": "qrtc", "utility": 0.2},
        {"cluster_id": "b", "policy": "baseline", "utility": 0.4},
    ]
    differences = cluster_differences(rows, "qrtc", "baseline")
    interval = cluster_bootstrap(differences, samples=100, seed=7)

    assert differences == {"a": 0.5, "b": -0.2}
    assert interval["estimate"] == 0.15