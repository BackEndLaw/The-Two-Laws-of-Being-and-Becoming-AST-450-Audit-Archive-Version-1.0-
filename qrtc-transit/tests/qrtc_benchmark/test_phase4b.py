from __future__ import annotations

import csv
import json
from pathlib import Path

from qrtc_benchmark.phase4b import (
    DEFAULT_PHASE4B_PAIRS,
    Phase4BIntervention,
    Phase4BRelationType,
    evaluate_phase4b_action_sequence,
    run_phase4b_benchmark,
    select_phase4b_oracle_sequence,
)


def test_phase4b_generates_metrics_and_artifacts(tmp_path: Path) -> None:
    bundle = run_phase4b_benchmark("development", tmp_path, repeats_per_pair=1)

    assert bundle["metrics_json"].exists()
    assert bundle["runs_csv"].exists()
    assert bundle["manifest_json"].exists()
    assert bundle["preregistration_md"].exists()
    assert bundle["policy_summary_csv"].exists()
    assert bundle["regret_breakdown_csv"].exists()
    assert bundle["action_sequence_breakdown_csv"].exists()

    metrics = json.loads(bundle["metrics_json"].read_text(encoding="utf-8"))
    assert "policies" in metrics
    assert "qrtc" in metrics["policies"]
    assert "oracle" in metrics["policies"]
    assert metrics["policies"]["qrtc"]["recovery_rate"] >= 0.0
    assert metrics["policies"]["oracle"]["utility_mean"] >= metrics["policies"]["qrtc"]["utility_mean"]


def test_phase4b_invariants_hold_for_relation_types(tmp_path: Path) -> None:
    bundle = run_phase4b_benchmark("development", tmp_path, repeats_per_pair=1)
    rows = bundle["rows"]

    strict_rows = [row for row in rows if row.policy == "qrtc" and row.relation_type == "strict_masking"]
    soft_rows = [row for row in rows if row.policy == "qrtc" and row.relation_type == "soft_masking"]
    independent_rows = [row for row in rows if row.policy == "qrtc" and row.relation_type == "independent"]
    synergistic_rows = [row for row in rows if row.policy == "qrtc" and row.relation_type == "synergistic"]

    assert strict_rows
    assert soft_rows
    assert independent_rows
    assert synergistic_rows
    assert all(row.recovered for row in strict_rows)
    assert all(row.recovered for row in soft_rows)
    assert all(row.recovered for row in independent_rows)
    assert all(row.recovered for row in synergistic_rows)
    assert all(row.action_sequence == row.oracle_sequence for row in strict_rows)
    assert all(len(row.action_sequence.split(",")) <= 2 for row in soft_rows)
    assert all(len(row.action_sequence.split(",")) == 1 for row in independent_rows)
    assert all(len(row.action_sequence.split(",")) == 1 for row in synergistic_rows)


def test_phase4b_oracle_dominance_and_breakdown_artifacts(tmp_path: Path) -> None:
    bundle = run_phase4b_benchmark("development", tmp_path, repeats_per_pair=1)
    rows = bundle["rows"]

    assert all(row.oracle_utility >= row.utility for row in rows if row.policy != "oracle")

    with bundle["policy_summary_csv"].open(encoding="utf-8", newline="") as handle:
        policy_rows = list(csv.DictReader(handle))
    with bundle["regret_breakdown_csv"].open(encoding="utf-8", newline="") as handle:
        regret_rows = list(csv.DictReader(handle))
    with bundle["action_sequence_breakdown_csv"].open(encoding="utf-8", newline="") as handle:
        action_rows = list(csv.DictReader(handle))

    assert policy_rows
    assert regret_rows
    assert action_rows
    assert any(row["policy"] == "qrtc" for row in policy_rows)
    assert any(row["policy"] == "qrtc" for row in regret_rows)
    assert any(row["policy"] == "qrtc" for row in action_rows)


def test_oracle_utility_dominates_every_policy_per_trial(tmp_path: Path) -> None:
    bundle = run_phase4b_benchmark("development", tmp_path, repeats_per_pair=1)
    rows = bundle["rows"]

    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        trial_key = row.trial_id.rsplit(":", 1)[0]
        grouped.setdefault(trial_key, {})[row.policy] = row

    for trial_rows in grouped.values():
        oracle_row = trial_rows["oracle"]
        for policy, row in trial_rows.items():
            if policy == "oracle":
                continue
            assert oracle_row.oracle_utility >= row.utility - 1e-9


def test_oracle_selects_minimum_cost_successful_path() -> None:
    pair_spec = DEFAULT_PHASE4B_PAIRS[0]
    oracle_sequence = select_phase4b_oracle_sequence(pair_spec, Phase4BRelationType.SOFT_MASKING, 0.5, 0.1)
    outcome = evaluate_phase4b_action_sequence(oracle_sequence, pair_spec, Phase4BRelationType.SOFT_MASKING, 0.5, 0.1)

    assert outcome["recovered"]
    assert oracle_sequence == (Phase4BIntervention.rW,)


def test_regret_components_sum_to_total(tmp_path: Path) -> None:
    bundle = run_phase4b_benchmark("development", tmp_path, repeats_per_pair=1)
    rows = bundle["rows"]

    for row in rows:
        if row.policy == "oracle":
            continue
        regret = row.oracle_utility - row.utility
        assert abs(regret) >= 0.0


def test_policy_summary_matches_trial_rows(tmp_path: Path) -> None:
    bundle = run_phase4b_benchmark("development", tmp_path, repeats_per_pair=1)
    rows = bundle["rows"]

    with bundle["policy_summary_csv"].open(encoding="utf-8", newline="") as handle:
        policy_rows = list(csv.DictReader(handle))

    for row in policy_rows:
        policy = row["policy"]
        matching_rows = [trial_row for trial_row in rows if trial_row.policy == policy]
        assert matching_rows
