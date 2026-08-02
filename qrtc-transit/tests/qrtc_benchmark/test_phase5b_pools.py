"""Tests verifying pairwise disjointness of all three Phase V-B experiment pools.

Pool 1 = development        (CLI: --split development)
Pool 2 = selection-valid.   (CLI: --split validation)
Pool 3 = final-valid.       (CLI: --split test)

All three pools must have:
  - Disjoint mechanism IDs
  - Disjoint pair IDs
  - Disjoint triple IDs
  - Disjoint seed families
"""
from __future__ import annotations

import pytest

from qrtc_benchmark.phase5 import (
    SPLIT_SEEDS,
    Phase5Config,
    Phase5Family,
    _DEVELOPMENT_MECHANISMS,
    _DEVELOPMENT_PAIRS,
    _DEVELOPMENT_TRIPLES,
    _FINAL_MECHANISMS,
    _FINAL_PAIRS,
    _FINAL_TRIPLES,
    _VALIDATION_MECHANISMS,
    _VALIDATION_PAIRS,
    _VALIDATION_TRIPLES,
    build_phase5_trials,
)

SMALL_CFG = Phase5Config(
    bootstrap_reps=50,
    development_family_trials=24,
    validation_family_trials=16,
    test_family_trials=16,
)


# ── Static pool-definition disjointness tests ─────────────────────────────────

def test_mechanism_ids_disjoint_dev_vs_validation() -> None:
    for family in Phase5Family:
        dev = set(_DEVELOPMENT_MECHANISMS[family])
        val = set(_VALIDATION_MECHANISMS[family])
        assert dev.isdisjoint(val), (
            f"Family {family}: development and selection-validation mechanism sets overlap: "
            f"{dev & val}"
        )


def test_mechanism_ids_disjoint_dev_vs_final() -> None:
    for family in Phase5Family:
        dev = set(_DEVELOPMENT_MECHANISMS[family])
        fin = set(_FINAL_MECHANISMS[family])
        assert dev.isdisjoint(fin), (
            f"Family {family}: development and final-validation mechanism sets overlap: "
            f"{dev & fin}"
        )


def test_mechanism_ids_disjoint_validation_vs_final() -> None:
    for family in Phase5Family:
        val = set(_VALIDATION_MECHANISMS[family])
        fin = set(_FINAL_MECHANISMS[family])
        assert val.isdisjoint(fin), (
            f"Family {family}: selection-validation and final-validation mechanism sets overlap: "
            f"{val & fin}"
        )


def test_pair_ids_disjoint_dev_vs_validation() -> None:
    dev = set(_DEVELOPMENT_PAIRS)
    val = set(_VALIDATION_PAIRS)
    assert dev.isdisjoint(val), (
        f"Development and selection-validation pair sets overlap: {dev & val}"
    )


def test_pair_ids_disjoint_dev_vs_final() -> None:
    dev = set(_DEVELOPMENT_PAIRS)
    fin = set(_FINAL_PAIRS)
    assert dev.isdisjoint(fin), (
        f"Development and final-validation pair sets overlap: {dev & fin}"
    )


def test_pair_ids_disjoint_validation_vs_final() -> None:
    val = set(_VALIDATION_PAIRS)
    fin = set(_FINAL_PAIRS)
    assert val.isdisjoint(fin), (
        f"Selection-validation and final-validation pair sets overlap: {val & fin}"
    )


def test_triple_ids_disjoint_dev_vs_validation() -> None:
    dev = set(_DEVELOPMENT_TRIPLES)
    val = set(_VALIDATION_TRIPLES)
    assert dev.isdisjoint(val), (
        f"Development and selection-validation triple sets overlap: {dev & val}"
    )


def test_triple_ids_disjoint_dev_vs_final() -> None:
    dev = set(_DEVELOPMENT_TRIPLES)
    fin = set(_FINAL_TRIPLES)
    assert dev.isdisjoint(fin), (
        f"Development and final-validation triple sets overlap: {dev & fin}"
    )


def test_triple_ids_disjoint_validation_vs_final() -> None:
    val = set(_VALIDATION_TRIPLES)
    fin = set(_FINAL_TRIPLES)
    assert val.isdisjoint(fin), (
        f"Selection-validation and final-validation triple sets overlap: {val & fin}"
    )


def test_triple_ids_have_no_duplicates_within_pool() -> None:
    for name, pool in [
        ("development", _DEVELOPMENT_TRIPLES),
        ("selection-validation", _VALIDATION_TRIPLES),
        ("final-validation", _FINAL_TRIPLES),
    ]:
        assert len(pool) == len(set(pool)), (
            f"Duplicate triple IDs found in {name} pool: "
            f"{[t for t in pool if pool.count(t) > 1]}"
        )


def test_seed_families_disjoint_across_pools() -> None:
    dev = set(SPLIT_SEEDS["development"])
    val = set(SPLIT_SEEDS["validation"])
    fin = set(SPLIT_SEEDS["test"])
    assert dev.isdisjoint(val), f"dev vs validation seeds overlap: {dev & val}"
    assert dev.isdisjoint(fin), f"dev vs test seeds overlap: {dev & fin}"
    assert val.isdisjoint(fin), f"validation vs test seeds overlap: {val & fin}"


# ── Runtime disjointness tests (generated rows) ───────────────────────────────

def test_generated_mechanism_ids_disjoint_dev_vs_test() -> None:
    dev_rows = build_phase5_trials("development", SMALL_CFG)
    test_rows = build_phase5_trials("test", SMALL_CFG)
    dev_mechs = {r.mechanism_id for r in dev_rows if r.policy == "qrtc"}
    test_mechs = {r.mechanism_id for r in test_rows if r.policy == "qrtc"}
    assert dev_mechs.isdisjoint(test_mechs), (
        f"Generated mechanism IDs overlap between development and final-validation: "
        f"{dev_mechs & test_mechs}"
    )


def test_generated_mechanism_ids_disjoint_dev_vs_validation() -> None:
    dev_rows = build_phase5_trials("development", SMALL_CFG)
    val_rows = build_phase5_trials("validation", SMALL_CFG)
    dev_mechs = {r.mechanism_id for r in dev_rows if r.policy == "qrtc"}
    val_mechs = {r.mechanism_id for r in val_rows if r.policy == "qrtc"}
    assert dev_mechs.isdisjoint(val_mechs), (
        f"Generated mechanism IDs overlap between development and selection-validation: "
        f"{dev_mechs & val_mechs}"
    )


def test_generated_mechanism_ids_disjoint_validation_vs_test() -> None:
    val_rows = build_phase5_trials("validation", SMALL_CFG)
    test_rows = build_phase5_trials("test", SMALL_CFG)
    val_mechs = {r.mechanism_id for r in val_rows if r.policy == "qrtc"}
    test_mechs = {r.mechanism_id for r in test_rows if r.policy == "qrtc"}
    assert val_mechs.isdisjoint(test_mechs), (
        f"Generated mechanism IDs overlap between selection-validation and final-validation: "
        f"{val_mechs & test_mechs}"
    )


def test_generated_pair_ids_disjoint_all_three_pools() -> None:
    dev_rows = build_phase5_trials("development", SMALL_CFG)
    val_rows = build_phase5_trials("validation", SMALL_CFG)
    test_rows = build_phase5_trials("test", SMALL_CFG)

    # Only check V2 (unseen pair) family where composition_id is the pair.
    def pair_ids(rows, split):
        return {
            r.composition_id
            for r in rows
            if r.policy == "qrtc" and r.family == "V2"
        }

    dev_pairs = pair_ids(dev_rows, "development")
    val_pairs = pair_ids(val_rows, "validation")
    test_pairs = pair_ids(test_rows, "test")

    assert dev_pairs.isdisjoint(val_pairs), (
        f"V2 pair IDs overlap between development and selection-validation: {dev_pairs & val_pairs}"
    )
    assert dev_pairs.isdisjoint(test_pairs), (
        f"V2 pair IDs overlap between development and final-validation: {dev_pairs & test_pairs}"
    )
    assert val_pairs.isdisjoint(test_pairs), (
        f"V2 pair IDs overlap between selection-validation and final-validation: {val_pairs & test_pairs}"
    )


def test_generated_triple_ids_disjoint_all_three_pools() -> None:
    dev_rows = build_phase5_trials("development", SMALL_CFG)
    val_rows = build_phase5_trials("validation", SMALL_CFG)
    test_rows = build_phase5_trials("test", SMALL_CFG)

    def triple_ids(rows):
        return {
            r.composition_id
            for r in rows
            if r.policy == "qrtc" and r.family == "V3"
        }

    dev_triples = triple_ids(dev_rows)
    val_triples = triple_ids(val_rows)
    test_triples = triple_ids(test_rows)

    assert dev_triples.isdisjoint(val_triples), (
        f"Triple IDs overlap between development and selection-validation: {dev_triples & val_triples}"
    )
    assert dev_triples.isdisjoint(test_triples), (
        f"Triple IDs overlap between development and final-validation: {dev_triples & test_triples}"
    )
    assert val_triples.isdisjoint(test_triples), (
        f"Triple IDs overlap between selection-validation and final-validation: {val_triples & test_triples}"
    )


def test_final_validation_locked_without_unlock_flag(tmp_path) -> None:
    """Final-validation pool must raise PermissionError unless explicitly unlocked."""
    from qrtc_benchmark.phase5 import run_phase5_benchmark
    with pytest.raises(PermissionError):
        run_phase5_benchmark("test", tmp_path, unlock_test=False, config=SMALL_CFG)


def test_final_validation_gate_requires_explicit_unlock(tmp_path) -> None:
    """Passing unlock_test=True is the ONLY way to run final validation."""
    from qrtc_benchmark.phase5 import run_phase5_benchmark
    # This should NOT raise — the explicit flag was passed.
    bundle = run_phase5_benchmark("test", tmp_path, unlock_test=True, config=SMALL_CFG)
    assert bundle["runs_csv"].exists()
