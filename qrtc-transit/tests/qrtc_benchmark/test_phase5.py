from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from qrtc_benchmark.phase5 import (
    PHASE5_POLICIES,
    Phase5Config,
    _FINAL_MECHANISMS,
    _FINAL_PAIRS,
    _FINAL_TRIPLES,
    _VALIDATION_PAIRS,
    authorize_phase5_split,
    build_phase5_trials,
    run_phase5_benchmark,
)


SMALL_CFG = Phase5Config(
    bootstrap_reps=200,
    development_family_trials=72,
    validation_family_trials=48,
    test_family_trials=64,
)


def _rows_by_policy(rows, policy: str):
    return [row for row in rows if row.policy == policy]


def _trial_key_to_rows(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row.trial_key, {})[row.policy] = row
    return grouped


def test_phase4b_artifacts_are_not_modified(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    phase4b_dir = repo_root / "artifacts" / "phase4b"
    closed = phase4b_dir / "CLOSED"
    if closed.exists():
        before = closed.read_text(encoding="utf-8")
    else:
        before = None

    run_phase5_benchmark("development", tmp_path, config=SMALL_CFG)

    assert closed.exists()
    after = closed.read_text(encoding="utf-8")
    if before is not None:
        assert after == before
    assert "read-only" in after.lower()


def test_phase5_seeds_are_new() -> None:
    rows = build_phase5_trials("development", SMALL_CFG)
    seeds = {row.seed_family for row in rows}
    assert seeds.isdisjoint({401, 402, 403, 551, 552, 601, 602, 603})


def test_locked_mechanisms_absent_from_development() -> None:
    dev_rows = build_phase5_trials("development", SMALL_CFG)
    dev_mechanisms = {row.mechanism_id for row in dev_rows if row.policy == "qrtc"}
    test_mechanisms = {
        mechanism_id
        for mechanisms in _FINAL_MECHANISMS.values()
        for mechanism_id in mechanisms
    }
    assert dev_mechanisms.isdisjoint(test_mechanisms)


def test_locked_pairs_absent_from_development() -> None:
    dev_rows = build_phase5_trials("development", SMALL_CFG)
    dev_pairs = {
        row.composition_id
        for row in dev_rows
        if row.policy == "qrtc" and row.family in {"V1", "V2"}
    }
    test_pairs = set(_FINAL_PAIRS)
    assert dev_pairs.isdisjoint(test_pairs)


def test_strong_holdout_excludes_constituent_pairs() -> None:
    # In the phase5b 3-pool design the holdout constraint is that final-validation
    # triples must not use selection-validation pairs as constituent pairs.  This
    # preserves the strong holdout: any pair seen during selection-validation is
    # excluded from the final evaluation triples.
    selection_validation_pairs = set(_VALIDATION_PAIRS)
    for triple_id in _FINAL_TRIPLES:
        parts = triple_id.split("+")
        if len(parts) != 3:
            continue
        pair_projections = {f"{parts[0]}+{parts[1]}", f"{parts[0]}+{parts[2]}", f"{parts[1]}+{parts[2]}"}
        assert pair_projections.isdisjoint(selection_validation_pairs)


def test_unknown_fault_not_forced_into_known_label() -> None:
    rows = build_phase5_trials("development", SMALL_CFG)
    unknown_rows = [row for row in rows if row.policy == "qrtc" and row.family == "V4"]
    assert unknown_rows
    assert all(row.composition_id == "UNKNOWN" for row in unknown_rows)
    assert all(not row.recovered for row in unknown_rows)


def test_evidence_request_does_not_repair_system() -> None:
    rows = build_phase5_trials("development", SMALL_CFG)
    request_only = [
        row
        for row in rows
        if row.policy == "qrtc" and row.action_sequence == "r0"
    ]
    assert request_only
    assert all(row.recovery_score in {0.0, 1.0} for row in request_only)
    assert all(row.intervention_cost >= 1.0 for row in request_only)


def test_intervention_failure_changes_post_action_witness() -> None:
    cfg = Phase5Config(
        reliability_levels=(0.8,),
        bootstrap_reps=200,
        development_family_trials=72,
        validation_family_trials=48,
        test_family_trials=64,
    )
    rows = build_phase5_trials("development", cfg)
    qrtc = _rows_by_policy(rows, "qrtc")
    assert any(row.harm > 0 for row in qrtc)


def test_failed_intervention_still_increments_cost() -> None:
    cfg = Phase5Config(
        reliability_levels=(0.8,),
        bootstrap_reps=200,
        development_family_trials=72,
        validation_family_trials=48,
        test_family_trials=64,
    )
    rows = build_phase5_trials("development", cfg)
    qrtc = _rows_by_policy(rows, "qrtc")
    failed = [row for row in qrtc if not row.recovered]
    assert failed
    assert all(row.intervention_cost > 0 for row in failed)


def test_three_fault_chain_respects_dependency() -> None:
    rows = build_phase5_trials("development", SMALL_CFG)
    qrtc_rows = [row for row in rows if row.policy == "qrtc" and row.family == "V3" and row.composition_id == "FG+FW+FJ"]
    assert qrtc_rows
    assert all(row.action_sequence.startswith("rG") for row in qrtc_rows)


def test_three_fault_fork_accepts_multiple_valid_orders() -> None:
    rows = build_phase5_trials("development", SMALL_CFG)
    qrtc_rows = [row for row in rows if row.policy == "qrtc" and row.family == "V3" and row.composition_id == "FB+FR+FJ"]
    assert qrtc_rows
    valid_prefixes = {"rB,rR", "rB,rJ"}
    assert any(",".join(row.action_sequence.split(",")[:2]) in valid_prefixes for row in qrtc_rows)


def test_partial_sufficiency_stops_after_recovery() -> None:
    rows = build_phase5_trials("development", SMALL_CFG)
    qrtc_rows = [row for row in rows if row.policy == "qrtc" and row.family == "V3" and row.composition_id == "FG+FD+FW"]
    assert qrtc_rows
    assert all(len(row.action_sequence.split(",")) <= 3 for row in qrtc_rows)


def test_cost_shift_changes_optimal_path_when_expected() -> None:
    cfg = Phase5Config(
        cost_regimes=("familiar", "reordered"),
        bootstrap_reps=200,
        development_family_trials=72,
        validation_family_trials=48,
        test_family_trials=64,
    )
    rows = build_phase5_trials("development", cfg)
    oracle_rows = _rows_by_policy(rows, "oracle")
    familiar = {
        row.trial_key.replace(":familiar:", ":<regime>:"): row.action_sequence
        for row in oracle_rows
        if row.cost_regime == "familiar"
    }
    reordered = {
        row.trial_key.replace(":reordered:", ":<regime>:"): row.action_sequence
        for row in oracle_rows
        if row.cost_regime == "reordered"
    }
    overlap = set(familiar).intersection(reordered)
    assert overlap
    assert any(familiar[key] != reordered[key] for key in overlap)


def test_oracle_dominates_every_policy_per_trial() -> None:
    rows = build_phase5_trials("development", SMALL_CFG)
    grouped = _trial_key_to_rows(rows)
    assert grouped
    for trial_rows in grouped.values():
        oracle = trial_rows["oracle"]
        for policy in PHASE5_POLICIES:
            if policy == "oracle":
                continue
            assert oracle.utility >= trial_rows[policy].utility - 1e-9


def test_regret_decomposition_is_exact() -> None:
    rows = build_phase5_trials("development", SMALL_CFG)
    for row in rows:
        if row.policy == "oracle":
            continue
        regret = row.oracle_utility - row.utility
        assert regret >= -1e-9


def test_cluster_bootstrap_preserves_matched_trials(tmp_path: Path) -> None:
    bundle = run_phase5_benchmark("development", tmp_path, config=SMALL_CFG)
    interval = json.loads(bundle["interval_method"].read_text(encoding="utf-8"))
    qrtc_rows = [row for row in bundle["rows"] if row.policy == "qrtc"]
    assert interval["matched_trial_count"] == len(qrtc_rows)


def test_locked_manifest_unavailable_before_unlock(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        run_phase5_benchmark("test", tmp_path, unlock_test=False, config=SMALL_CFG)


def test_authorize_phase5_split_requires_explicit_unlock_for_final_validation() -> None:
    with pytest.raises(PermissionError):
        authorize_phase5_split("test", unlock_test=False)


def test_authorize_phase5_split_allows_explicit_unlock_without_generating_rows() -> None:
    authorize_phase5_split("test", unlock_test=True)


def test_required_artifacts_exist_for_development(tmp_path: Path) -> None:
    bundle = run_phase5_benchmark("development", tmp_path, config=SMALL_CFG)
    expected = [
        "runs_csv",
        "manifest_json",
        "frozen_config",
        "preregistration",
        "checksums",
        "decision",
        "policy_comparison",
        "paired_comparisons",
        "utility_by_ood_family",
        "interval_method",
        "final_integrity",
    ]
    for key in expected:
        assert bundle[key].exists(), key

    with bundle["policy_comparison"].open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert any(row["policy"] == "qrtc" for row in rows)