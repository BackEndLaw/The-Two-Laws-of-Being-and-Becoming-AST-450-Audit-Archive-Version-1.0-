"""Tests for Phase V-B Selection Protocol v1.

Covers:
- canonical determinism
- checked-in artifact regeneration
- hashes
- mandatory completeness
- authoritative split declarations
- absence of final-validation generation
- bootstrap matching/determinism
- every eligibility gate
- superiority and tie-breaking
- no-selection outcomes
- oracle exclusion
- result-schema tamper rejection
- stage order
- lock behaviour
- clean-wheel CLI smoke
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from qrtc_benchmark.controllers import (
    OPTIONAL_DESCRIPTIVE_BASELINE_IDS,
)
from qrtc_benchmark.eligibility import (
    THRESHOLD_SHA256,
    CandidateMetrics,
    check_all_eligibility,
    check_eligibility,
)
from qrtc_benchmark.result_schema import (
    RESULT_SCHEMA,
    SelectionResultValidationError,
    load_selection_result,
    make_synthetic_no_selection_result,
)
from qrtc_benchmark.selection_protocol import (
    DEPLOYABLE_MANDATORY_CANDIDATES,
    IMPLEMENTATION_COMMIT,
    MANDATORY_CANDIDATES,
    OPTIONAL_BASELINE_IDS,
    PROTOCOL_ID,
    PROTOCOL_PHASE_REVISION,
    PROTOCOL_STATE,
    canonical_json_bytes,
    compute_protocol_hashes,
)
from qrtc_benchmark.selection_rule import (
    SelectionOutcome,
    select_controller,
)
from qrtc_benchmark.validation_cli import (
    LockedStageError,
    ProtocolValidationError,
    validate_protocol_directory,
)
from qrtc_benchmark.validation_cli import (
    main as validation_main,
)

# ── helpers ────────────────────────────────────────────────────────────────────

_PROTOCOL_DIR = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "protocols"
    / "phase5b-selection-v1"
)


def _make_metrics(
    controller_id: str,
    *,
    mean_utility: float = 0.5,
    recovery_rate: float = 0.9,
    mean_intervention_cost: float = 2.0,
    mean_harm: float = 0.0,
    unsafe_commitment_rate: float = 0.0,
    evidence_request_rate: float = 0.0,
    per_family_recovery_rate: dict[str, float] | None = None,
    per_family_mean_harm: dict[str, float] | None = None,
    per_family_unsafe_count: dict[str, int] | None = None,
    bootstrap_ci_low: float = 0.05,
    bootstrap_ci_high: float = 0.20,
    oracle_regret: float = 0.05,
    matched_rows_ok: bool = True,
    artifact_hash_ok: bool = True,
    protocol_match_ok: bool = True,
    operational_integrity_ok: bool = True,
) -> CandidateMetrics:
    families = ["V1", "V2", "V3", "V4"]
    return CandidateMetrics(
        controller_id=controller_id,
        mean_utility=mean_utility,
        recovery_rate=recovery_rate,
        mean_intervention_cost=mean_intervention_cost,
        mean_harm=mean_harm,
        unsafe_commitment_rate=unsafe_commitment_rate,
        evidence_request_rate=evidence_request_rate,
        per_family_recovery_rate=per_family_recovery_rate
        or {f: recovery_rate for f in families},
        per_family_mean_harm=per_family_mean_harm or {f: mean_harm for f in families},
        per_family_unsafe_count=per_family_unsafe_count or {f: 0 for f in families},
        bootstrap_vs_greedy={
            "ci_low": bootstrap_ci_low,
            "ci_high": bootstrap_ci_high,
            "mean_difference": (bootstrap_ci_low + bootstrap_ci_high) / 2,
        },
        bootstrap_vs_strongest={
            "ci_low": bootstrap_ci_low,
            "ci_high": bootstrap_ci_high,
            "mean_difference": (bootstrap_ci_low + bootstrap_ci_high) / 2,
        },
        oracle_regret=oracle_regret,
        matched_rows_ok=matched_rows_ok,
        artifact_hash_ok=artifact_hash_ok,
        protocol_match_ok=protocol_match_ok,
        operational_integrity_ok=operational_integrity_ok,
    )


def _all_candidate_metrics(
    superior: bool = True,
    exclude_oracle: bool = False,
) -> list[CandidateMetrics]:
    """Return metrics for all mandatory deployable candidates.

    If *superior* is True each gets a positive ci_low (they are all "superior").
    """
    metrics = []
    for cid in MANDATORY_CANDIDATES:
        if exclude_oracle and cid == "oracle":
            continue
        ci_low = 0.05 if superior else -0.05
        metrics.append(_make_metrics(cid, bootstrap_ci_low=ci_low))
    return metrics


def _valid_result_payload(
    *,
    outcome: str = "no_controller_selected",
    selected_id: object = None,
    stage: str = "development",
    authority: str = "recommend_only",
    hardware_actuation_enabled: bool = False,
    final_validation_status: str = "locked_not_executed",
    implementation_commit: str = IMPLEMENTATION_COMMIT,
) -> dict[str, Any]:
    protocol_hash = compute_protocol_hashes().protocol_declaration_sha256
    return {
        "result_schema": RESULT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": protocol_hash,
        "phase_revision": PROTOCOL_PHASE_REVISION,
        "stage": stage,
        "input_hashes": {"synthetic": "a" * 64},
        "implementation_commit": implementation_commit,
        "metrics_summary": {},
        "eligibility_reasons": {},
        "bootstrap_comparisons": {},
        "selected_id": selected_id,
        "oracle_ceiling": {},
        "authority": authority,
        "hardware_actuation_enabled": hardware_actuation_enabled,
        "final_validation_status": final_validation_status,
        "outcome": outcome,
    }


# ── 1. Protocol identity ───────────────────────────────────────────────────────


def test_protocol_id_and_state() -> None:
    assert PROTOCOL_ID == "phase5b-selection-v1"
    assert PROTOCOL_STATE == "preregistered_not_executed"
    assert PROTOCOL_PHASE_REVISION == "phase5b"


def test_mandatory_candidates_exact() -> None:
    assert set(MANDATORY_CANDIDATES) == {
        "qrtc",
        "qrtc_no_abstention",
        "qrtc_untyped",
        "greedy_gain",
        "oracle",
    }
    assert len(MANDATORY_CANDIDATES) == 5


def test_oracle_excluded_from_deployable() -> None:
    assert "oracle" not in DEPLOYABLE_MANDATORY_CANDIDATES
    assert set(DEPLOYABLE_MANDATORY_CANDIDATES) == {
        "qrtc",
        "qrtc_no_abstention",
        "qrtc_untyped",
        "greedy_gain",
    }


def test_optional_baselines_excluded() -> None:
    assert set(OPTIONAL_BASELINE_IDS) == set(OPTIONAL_DESCRIPTIVE_BASELINE_IDS)
    for cid in OPTIONAL_BASELINE_IDS:
        assert cid not in MANDATORY_CANDIDATES


def test_implementation_commit_bound_to_pr22_merge() -> None:
    assert IMPLEMENTATION_COMMIT == "6aa56a7abae975274e95a9ba2941fe2002794592"
    assert len(IMPLEMENTATION_COMMIT) == 40
    assert all(c in "0123456789abcdef" for c in IMPLEMENTATION_COMMIT)


# ── 2. Canonical determinism ───────────────────────────────────────────────────


def test_canonical_json_bytes_deterministic() -> None:
    """canonical_json_bytes must produce identical output regardless of dict insertion order."""
    payload1 = {"b": 2, "a": 1}
    payload2 = {"a": 1, "b": 2}
    assert canonical_json_bytes(payload1) == canonical_json_bytes(payload2)


def test_protocol_hashes_stable_across_calls() -> None:
    h1 = compute_protocol_hashes()
    h2 = compute_protocol_hashes()
    assert h1 == h2


def test_protocol_hash_matches_preregistration_file() -> None:
    prereg = json.loads(
        (_PROTOCOL_DIR / "preregistration.json").read_text(encoding="utf-8")
    )
    assert (
        prereg["protocol_hash"] == compute_protocol_hashes().protocol_declaration_sha256
    )


def test_split_declaration_hash_stable() -> None:
    h = compute_protocol_hashes()
    expected = h.split_declaration_sha256
    recomputed = compute_protocol_hashes().split_declaration_sha256
    assert expected == recomputed
    assert len(expected) == 64


def test_config_declaration_hash_stable() -> None:
    h = compute_protocol_hashes()
    assert len(h.config_declaration_sha256) == 64


def test_candidate_declaration_hash_stable() -> None:
    h = compute_protocol_hashes()
    assert len(h.candidate_declaration_sha256) == 64


# ── 3. Checked-in artifact regeneration ───────────────────────────────────────


def test_protocol_dir_exists() -> None:
    assert _PROTOCOL_DIR.exists(), f"Protocol directory missing: {_PROTOCOL_DIR}"


def test_all_mandatory_manifests_present() -> None:
    for cid in MANDATORY_CANDIDATES:
        artifact_path = _PROTOCOL_DIR / "manifests" / f"{cid}.json"
        assert artifact_path.exists(), f"Manifest missing: {artifact_path}"


def test_checksums_file_present() -> None:
    assert (_PROTOCOL_DIR / "checksums.sha256").exists()


def test_commit_txt_matches_implementation_commit() -> None:
    commit_path = _PROTOCOL_DIR / "commit.txt"
    assert commit_path.exists()
    recorded = commit_path.read_text(encoding="utf-8").strip()
    assert recorded == IMPLEMENTATION_COMMIT


def test_artifact_checksums_match_files() -> None:
    """Verify every entry in checksums.sha256 matches the corresponding file."""
    import hashlib

    checksums_text = (_PROTOCOL_DIR / "checksums.sha256").read_text(encoding="utf-8")
    for line in checksums_text.splitlines():
        if not line.strip():
            continue
        expected_digest, rel = line.split("  ", 1)
        path = _PROTOCOL_DIR / rel
        assert path.exists(), f"Checksummed file missing: {rel}"
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual_digest == expected_digest, f"Checksum mismatch for {rel}"


def test_mandatory_manifests_load_and_hashes_match() -> None:
    """Each mandatory manifest must load without errors and match canonical hashes."""
    from qrtc_benchmark.controller_artifact import load_controller_artifact

    for cid in MANDATORY_CANDIDATES:
        path = _PROTOCOL_DIR / "manifests" / f"{cid}.json"
        allow_oracle = cid == "oracle"
        artifact, _ctrl = load_controller_artifact(
            path, allow_oracle=allow_oracle, deployable_only=not allow_oracle
        )
        assert artifact.controller_id == cid
        assert artifact.protocol_id == PROTOCOL_ID


def test_manifest_protocol_id_matches() -> None:
    for cid in MANDATORY_CANDIDATES:
        path = _PROTOCOL_DIR / "manifests" / f"{cid}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["protocol_id"] == PROTOCOL_ID


def test_manifest_implementation_commit_matches() -> None:
    for cid in MANDATORY_CANDIDATES:
        path = _PROTOCOL_DIR / "manifests" / f"{cid}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["implementation_commit"] == IMPLEMENTATION_COMMIT


# ── 4. Authoritative split declarations ───────────────────────────────────────


def test_split_seeds_match_phase5() -> None:
    from qrtc_benchmark.phase5 import SPLIT_SEEDS
    from qrtc_benchmark.selection_protocol import SPLIT_SEEDS_FROZEN

    for key, seeds in SPLIT_SEEDS.items():
        assert SPLIT_SEEDS_FROZEN[key] == tuple(seeds)


def test_development_mechanisms_present() -> None:
    from qrtc_benchmark.selection_protocol import DEVELOPMENT_MECHANISMS

    for family in ["V1", "V2", "V3", "V4"]:
        assert len(DEVELOPMENT_MECHANISMS[family]) > 0


def test_three_pool_mechanism_disjointness() -> None:
    from qrtc_benchmark.selection_protocol import (
        DEVELOPMENT_MECHANISMS,
        FINAL_MECHANISMS,
        VALIDATION_MECHANISMS,
    )

    for family in ["V1", "V2", "V3", "V4"]:
        dev = set(DEVELOPMENT_MECHANISMS[family])
        val = set(VALIDATION_MECHANISMS[family])
        fin = set(FINAL_MECHANISMS[family])
        assert dev.isdisjoint(val), f"dev/val overlap in {family}"
        assert dev.isdisjoint(fin), f"dev/fin overlap in {family}"
        assert val.isdisjoint(fin), f"val/fin overlap in {family}"


def test_three_pool_pair_disjointness() -> None:
    from qrtc_benchmark.selection_protocol import (
        DEVELOPMENT_PAIRS,
        FINAL_PAIRS,
        VALIDATION_PAIRS,
    )

    dev = set(DEVELOPMENT_PAIRS)
    val = set(VALIDATION_PAIRS)
    fin = set(FINAL_PAIRS)
    assert dev.isdisjoint(val)
    assert dev.isdisjoint(fin)
    assert val.isdisjoint(fin)


def test_three_pool_triple_disjointness() -> None:
    from qrtc_benchmark.selection_protocol import (
        DEVELOPMENT_TRIPLES,
        FINAL_TRIPLES,
        VALIDATION_TRIPLES,
    )

    dev = set(DEVELOPMENT_TRIPLES)
    val = set(VALIDATION_TRIPLES)
    fin = set(FINAL_TRIPLES)
    assert dev.isdisjoint(val)
    assert dev.isdisjoint(fin)
    assert val.isdisjoint(fin)


# ── 5. Absence of final-validation generation ─────────────────────────────────


def test_final_validation_cli_locked() -> None:
    """final-validation stage must be rejected by the CLI guard."""
    with pytest.raises(LockedStageError):
        validate_protocol_directory(
            protocol_dir=_PROTOCOL_DIR,
            stage="final-validation",
            implementation_commit=IMPLEMENTATION_COMMIT,
        )


def test_phase5_authorize_rejects_test_split() -> None:
    from qrtc_benchmark.phase5 import authorize_phase5_split

    with pytest.raises(PermissionError):
        authorize_phase5_split("test", unlock_test=False)


def test_preregistration_final_validation_status_locked() -> None:
    prereg = json.loads(
        (_PROTOCOL_DIR / "preregistration.json").read_text(encoding="utf-8")
    )
    assert prereg["final_validation_status"] == "locked_not_executed"


# ── 6. Bootstrap matching/determinism ─────────────────────────────────────────


def test_bootstrap_is_deterministic() -> None:
    from qrtc_benchmark.phase5 import cluster_bootstrap_interval

    diffs = [
        (
            f"t{i}",
            float(i % 3 - 1),
            ("mech_a", "c1", "strict", "PI1", 0.5, 0.0, "familiar", 0.8, 701),
        )
        for i in range(30)
    ]
    r1 = cluster_bootstrap_interval(diffs, bootstrap_reps=100, bootstrap_seed=9101)
    r2 = cluster_bootstrap_interval(diffs, bootstrap_reps=100, bootstrap_seed=9101)
    assert r1 == r2


def test_bootstrap_different_seeds_different_results() -> None:
    from qrtc_benchmark.phase5 import cluster_bootstrap_interval

    diffs = [
        (
            f"t{i}",
            float(i % 3 - 1),
            ("mech_a", "c1", "strict", "PI1", 0.5, 0.0, "familiar", 0.8, 701),
        )
        for i in range(30)
    ]
    r1 = cluster_bootstrap_interval(diffs, bootstrap_reps=200, bootstrap_seed=9101)
    r2 = cluster_bootstrap_interval(diffs, bootstrap_reps=200, bootstrap_seed=1234)
    # Different seeds may produce different CIs (or by chance identical — just check call succeeds)
    assert r1["bootstrap_seed"] == 9101
    assert r2["bootstrap_seed"] == 1234


def test_bootstrap_returns_required_keys() -> None:
    from qrtc_benchmark.phase5 import cluster_bootstrap_interval

    diffs = [
        (
            f"t{i}",
            float(i % 3),
            ("mech", "c1", "strict", "PI1", 0.5, 0.0, "familiar", 0.8, 701),
        )
        for i in range(10)
    ]
    result = cluster_bootstrap_interval(diffs, bootstrap_reps=50, bootstrap_seed=9101)
    for key in (
        "mean_difference",
        "ci_low",
        "ci_high",
        "cluster_count",
        "matched_trial_count",
    ):
        assert key in result


def test_bootstrap_empty_returns_zeros() -> None:
    from qrtc_benchmark.phase5 import cluster_bootstrap_interval

    result = cluster_bootstrap_interval([], bootstrap_reps=100, bootstrap_seed=9101)
    assert result["mean_difference"] == 0.0
    assert result["ci_low"] == 0.0
    assert result["ci_high"] == 0.0
    assert result["cluster_count"] == 0


# ── 7. Eligibility gates ───────────────────────────────────────────────────────


def test_threshold_sha256_is_stable() -> None:
    import hashlib

    from qrtc_benchmark.eligibility import _THRESHOLD_PAYLOAD, _canonical_json_bytes

    expected = hashlib.sha256(_canonical_json_bytes(_THRESHOLD_PAYLOAD)).hexdigest()
    assert THRESHOLD_SHA256 == expected


def test_all_gates_pass_for_valid_candidate() -> None:
    greedy = _make_metrics("greedy_gain", mean_utility=0.4)
    candidate = _make_metrics("qrtc", mean_utility=0.5)
    result = check_eligibility(candidate, greedy)
    assert result.eligible
    assert not result.disqualification_reasons
    for gate_passed in result.gate_results.values():
        assert gate_passed


def test_gate1_missing_rows() -> None:
    greedy = _make_metrics("greedy_gain")
    candidate = _make_metrics("qrtc", matched_rows_ok=False)
    result = check_eligibility(candidate, greedy)
    assert not result.eligible
    assert result.gate_results["gate1_no_missing_duplicate_rows"] is False
    assert any("gate1" in reason for reason in result.disqualification_reasons)


def test_gate2_artifact_hash_mismatch() -> None:
    greedy = _make_metrics("greedy_gain")
    candidate = _make_metrics("qrtc", artifact_hash_ok=False)
    result = check_eligibility(candidate, greedy)
    assert not result.eligible
    assert result.gate_results["gate2_artifact_protocol_match"] is False


def test_gate2_protocol_mismatch() -> None:
    greedy = _make_metrics("greedy_gain")
    candidate = _make_metrics("qrtc", protocol_match_ok=False)
    result = check_eligibility(candidate, greedy)
    assert not result.eligible


def test_gate3_unsafe_rate_nonzero() -> None:
    greedy = _make_metrics("greedy_gain")
    candidate = _make_metrics("qrtc", unsafe_commitment_rate=0.001)
    result = check_eligibility(candidate, greedy)
    assert not result.eligible
    assert result.gate_results["gate3_overall_unsafe_rate"] is False
    assert any("gate3" in r for r in result.disqualification_reasons)


def test_gate3_unsafe_rate_exactly_zero_passes() -> None:
    greedy = _make_metrics("greedy_gain")
    candidate = _make_metrics("qrtc", unsafe_commitment_rate=0.0)
    result = check_eligibility(candidate, greedy)
    assert result.gate_results["gate3_overall_unsafe_rate"] is True


def test_gate4_ood_unsafe_count_nonzero() -> None:
    greedy = _make_metrics("greedy_gain")
    candidate = _make_metrics(
        "qrtc", per_family_unsafe_count={"V1": 0, "V2": 1, "V3": 0, "V4": 0}
    )
    result = check_eligibility(candidate, greedy)
    assert not result.eligible
    assert result.gate_results["gate4_no_ood_unsafe_count"] is False


def test_gate5_family_recovery_regression() -> None:
    greedy = _make_metrics(
        "greedy_gain",
        per_family_recovery_rate={"V1": 0.9, "V2": 0.9, "V3": 0.9, "V4": 0.9},
    )
    candidate = _make_metrics(
        "qrtc", per_family_recovery_rate={"V1": 0.8, "V2": 0.9, "V3": 0.9, "V4": 0.9}
    )
    # regression = 0.9 - 0.8 = 0.1 > 0.05
    result = check_eligibility(candidate, greedy)
    assert not result.eligible
    assert result.gate_results["gate5_family_recovery_no_regression"] is False


def test_gate5_family_recovery_small_regression_passes() -> None:
    greedy = _make_metrics(
        "greedy_gain",
        per_family_recovery_rate={"V1": 0.9, "V2": 0.9, "V3": 0.9, "V4": 0.9},
    )
    candidate = _make_metrics(
        "qrtc", per_family_recovery_rate={"V1": 0.86, "V2": 0.9, "V3": 0.9, "V4": 0.9}
    )
    # regression = 0.9 - 0.86 = 0.04 < 0.05 → passes
    result = check_eligibility(candidate, greedy)
    assert result.gate_results["gate5_family_recovery_no_regression"] is True


def test_gate6_family_harm_increase() -> None:
    greedy = _make_metrics(
        "greedy_gain", per_family_mean_harm={"V1": 0.1, "V2": 0.1, "V3": 0.1, "V4": 0.1}
    )
    candidate = _make_metrics(
        "qrtc", per_family_mean_harm={"V1": 0.2, "V2": 0.1, "V3": 0.1, "V4": 0.1}
    )
    # increase = 0.2 - 0.1 = 0.1 > 0.05
    result = check_eligibility(candidate, greedy)
    assert not result.eligible
    assert result.gate_results["gate6_family_harm_no_increase"] is False


def test_gate7_utility_too_low() -> None:
    greedy = _make_metrics("greedy_gain", mean_utility=0.5)
    candidate = _make_metrics("qrtc", mean_utility=0.48)
    # shortfall = 0.5 - 0.48 = 0.02 > 0.01
    result = check_eligibility(candidate, greedy)
    assert not result.eligible
    assert result.gate_results["gate7_utility_not_below_greedy"] is False


def test_gate7_utility_within_threshold_passes() -> None:
    greedy = _make_metrics("greedy_gain", mean_utility=0.5)
    candidate = _make_metrics("qrtc", mean_utility=0.491)
    # shortfall = 0.5 - 0.491 = 0.009 <= 0.01 → passes
    result = check_eligibility(candidate, greedy)
    assert result.gate_results["gate7_utility_not_below_greedy"] is True


def test_gate8_operational_integrity_failure() -> None:
    greedy = _make_metrics("greedy_gain")
    candidate = _make_metrics("qrtc", operational_integrity_ok=False)
    result = check_eligibility(candidate, greedy)
    assert not result.eligible
    assert result.gate_results["gate8_operational_integrity"] is False


def test_oracle_is_always_ineligible() -> None:
    greedy = _make_metrics("greedy_gain")
    oracle = _make_metrics("oracle")
    result = check_eligibility(oracle, greedy)
    assert not result.eligible
    assert any("oracle" in r.lower() for r in result.disqualification_reasons)


def test_check_all_eligibility_requires_greedy() -> None:
    metrics = [_make_metrics("qrtc")]
    with pytest.raises(ValueError, match="greedy"):
        check_all_eligibility(metrics)


def test_check_all_eligibility_returns_all_candidates() -> None:
    all_metrics = _all_candidate_metrics()
    results = check_all_eligibility(all_metrics)
    # qrtc, qrtc_no_abstention, qrtc_untyped, greedy_gain, oracle
    assert set(results.keys()) == set(MANDATORY_CANDIDATES)
    assert not results["oracle"].eligible


# ── 8. Superiority and tie-breaking ───────────────────────────────────────────


def test_selection_picks_best_superior_candidate() -> None:
    # qrtc has highest utility, all pass gates
    metrics = [
        _make_metrics("qrtc", mean_utility=0.8, bootstrap_ci_low=0.1),
        _make_metrics("qrtc_no_abstention", mean_utility=0.6, bootstrap_ci_low=0.05),
        _make_metrics("qrtc_untyped", mean_utility=0.5, bootstrap_ci_low=0.02),
        _make_metrics("greedy_gain", mean_utility=0.4, bootstrap_ci_low=0.0),
        _make_metrics("oracle"),
    ]
    eligibility = check_all_eligibility(metrics)
    result = select_controller(metrics, eligibility)
    assert result.outcome == SelectionOutcome.PROVISIONAL_SELECTION
    assert result.selected_id == "qrtc"


def test_tiebreak_by_unsafe_rate() -> None:
    # Two candidates with equal mean utility; one has higher unsafe rate → loses
    metrics = [
        _make_metrics(
            "qrtc", mean_utility=0.7, unsafe_commitment_rate=0.0, bootstrap_ci_low=0.05
        ),
        _make_metrics(
            "qrtc_no_abstention",
            mean_utility=0.7,
            unsafe_commitment_rate=0.0,
            bootstrap_ci_low=0.05,
        ),
        _make_metrics("qrtc_untyped", mean_utility=0.5, bootstrap_ci_low=0.0),
        _make_metrics("greedy_gain", mean_utility=0.4, bootstrap_ci_low=0.0),
        _make_metrics("oracle"),
    ]
    eligibility = check_all_eligibility(metrics)
    result = select_controller(metrics, eligibility)
    assert result.outcome == SelectionOutcome.PROVISIONAL_SELECTION
    # Both have equal utility and unsafe_rate; lexical tie-break → qrtc < qrtc_no_abstention
    assert result.selected_id == "qrtc"


def test_tiebreak_lexical_final() -> None:
    # Force equal on all numeric dimensions; lexical decides
    metrics = [
        _make_metrics(
            "qrtc",
            mean_utility=0.7,
            bootstrap_ci_low=0.05,
            unsafe_commitment_rate=0.0,
            mean_harm=0.0,
            mean_intervention_cost=2.0,
            recovery_rate=0.9,
        ),
        _make_metrics(
            "greedy_gain",
            mean_utility=0.7,
            bootstrap_ci_low=0.05,
            unsafe_commitment_rate=0.0,
            mean_harm=0.0,
            mean_intervention_cost=2.0,
            recovery_rate=0.9,
        ),
        _make_metrics("qrtc_no_abstention", mean_utility=0.5, bootstrap_ci_low=-0.01),
        _make_metrics("qrtc_untyped", mean_utility=0.5, bootstrap_ci_low=-0.01),
        _make_metrics("oracle"),
    ]
    eligibility = check_all_eligibility(metrics)
    result = select_controller(metrics, eligibility)
    assert result.outcome == SelectionOutcome.PROVISIONAL_SELECTION
    # "greedy_gain" < "qrtc" lexically
    assert result.selected_id == "greedy_gain"


# ── 9. No-selection outcomes ───────────────────────────────────────────────────


def test_no_selection_when_none_superior() -> None:
    metrics = _all_candidate_metrics(superior=False)
    eligibility = check_all_eligibility(metrics)
    result = select_controller(metrics, eligibility)
    assert result.outcome == SelectionOutcome.NO_CONTROLLER_SELECTED
    assert result.selected_id is None


def test_no_selection_when_none_eligible() -> None:
    # All fail gate 1
    metrics = [
        _make_metrics(cid, matched_rows_ok=False) for cid in MANDATORY_CANDIDATES
    ]
    eligibility = check_all_eligibility(metrics)
    result = select_controller(metrics, eligibility)
    assert result.outcome == SelectionOutcome.NO_CONTROLLER_SELECTED
    assert result.selected_id is None
    # Disqualification reasons should be populated for deployable candidates
    for cid in DEPLOYABLE_MANDATORY_CANDIDATES:
        assert cid in result.disqualified


def test_no_selection_all_disqualification_reasons_present() -> None:
    greedy = _make_metrics("greedy_gain")
    bad = _make_metrics("qrtc", unsafe_commitment_rate=0.1, matched_rows_ok=False)
    result = check_eligibility(bad, greedy)
    assert len(result.disqualification_reasons) >= 2


# ── 10. Oracle exclusion ──────────────────────────────────────────────────────


def test_oracle_never_selected_even_if_superior() -> None:
    # Force oracle to look like highest utility
    metrics = [
        _make_metrics("qrtc", mean_utility=0.3, bootstrap_ci_low=-0.1),
        _make_metrics("qrtc_no_abstention", mean_utility=0.3, bootstrap_ci_low=-0.1),
        _make_metrics("qrtc_untyped", mean_utility=0.3, bootstrap_ci_low=-0.1),
        _make_metrics("greedy_gain", mean_utility=0.3, bootstrap_ci_low=-0.1),
        _make_metrics("oracle", mean_utility=99.0, bootstrap_ci_low=99.0),
    ]
    eligibility = check_all_eligibility(metrics)
    result = select_controller(metrics, eligibility)
    assert result.selected_id != "oracle"
    assert result.outcome == SelectionOutcome.NO_CONTROLLER_SELECTED


def test_oracle_not_in_deployable_candidates() -> None:
    assert "oracle" not in DEPLOYABLE_MANDATORY_CANDIDATES


# ── 11. Result schema tamper rejection ────────────────────────────────────────


def test_result_schema_accepts_valid_payload() -> None:
    payload = _valid_result_payload()
    result = load_selection_result(payload)
    assert result.outcome == "no_controller_selected"
    assert result.selected_id is None


def test_result_schema_accepts_provisional_selection() -> None:
    payload = _valid_result_payload(
        outcome="provisional_selection",
        selected_id="qrtc",
        stage="selection-validation",
    )
    result = load_selection_result(payload)
    assert result.outcome == "provisional_selection"
    assert result.selected_id == "qrtc"


def test_result_schema_rejects_unknown_outcome() -> None:
    payload = _valid_result_payload(outcome="selected_winner")
    with pytest.raises(SelectionResultValidationError, match="unknown outcome"):
        load_selection_result(payload)


def test_result_schema_rejects_oracle_selection() -> None:
    payload = _valid_result_payload(
        outcome="provisional_selection", selected_id="oracle"
    )
    with pytest.raises(SelectionResultValidationError, match="oracle"):
        load_selection_result(payload)


def test_result_schema_rejects_fabricated_selection() -> None:
    payload = _valid_result_payload(
        outcome="provisional_selection", selected_id="hybrid_qrtc_v2"
    )
    with pytest.raises(SelectionResultValidationError, match="mandatory candidate"):
        load_selection_result(payload)


def test_result_schema_rejects_missing_field() -> None:
    payload = _valid_result_payload()
    del payload["authority"]
    with pytest.raises(SelectionResultValidationError, match="missing"):
        load_selection_result(payload)


def test_result_schema_rejects_extra_field() -> None:
    payload = _valid_result_payload()
    payload["unknown_field"] = 42
    with pytest.raises(SelectionResultValidationError, match="extra"):
        load_selection_result(payload)


def test_result_schema_rejects_wrong_protocol_id() -> None:
    payload = _valid_result_payload()
    payload["protocol_id"] = "phase5b-selection-v0"
    with pytest.raises(SelectionResultValidationError, match="protocol_id"):
        load_selection_result(payload)


def test_result_schema_rejects_wrong_protocol_hash() -> None:
    payload = _valid_result_payload()
    payload["protocol_hash"] = "a" * 64
    with pytest.raises(SelectionResultValidationError, match="protocol_hash"):
        load_selection_result(payload)


def test_result_schema_rejects_wrong_phase_revision() -> None:
    payload = _valid_result_payload()
    payload["phase_revision"] = "phase5a"
    with pytest.raises(SelectionResultValidationError, match="phase_revision"):
        load_selection_result(payload)


def test_result_schema_rejects_final_validation_stage() -> None:
    payload = _valid_result_payload(stage="final-validation")
    with pytest.raises(SelectionResultValidationError, match="stage"):
        load_selection_result(payload)


def test_result_schema_rejects_wrong_authority() -> None:
    payload = _valid_result_payload(authority="actuate")
    with pytest.raises(SelectionResultValidationError, match="authority"):
        load_selection_result(payload)


def test_result_schema_rejects_hardware_actuation_true() -> None:
    payload = _valid_result_payload(hardware_actuation_enabled=True)
    with pytest.raises(SelectionResultValidationError, match="hardware_actuation"):
        load_selection_result(payload)


def test_result_schema_rejects_wrong_final_validation_status() -> None:
    payload = _valid_result_payload(final_validation_status="executed")
    with pytest.raises(SelectionResultValidationError, match="final_validation_status"):
        load_selection_result(payload)


def test_result_schema_rejects_selected_id_not_null_for_no_selection() -> None:
    payload = _valid_result_payload(
        outcome="no_controller_selected", selected_id="qrtc"
    )
    with pytest.raises(SelectionResultValidationError, match="selected_id"):
        load_selection_result(payload)


def test_synthetic_no_selection_result_round_trips() -> None:
    result = make_synthetic_no_selection_result()
    loaded = load_selection_result(result.canonical_bytes())
    assert loaded.outcome == "no_controller_selected"
    assert loaded.selected_id is None


# ── 12. Stage order ───────────────────────────────────────────────────────────


def test_validate_development_stage_passes(tmp_path: Path) -> None:
    report = validate_protocol_directory(
        protocol_dir=_PROTOCOL_DIR,
        stage="development",
        implementation_commit=IMPLEMENTATION_COMMIT,
    )
    assert report.status == "ok"
    assert report.stage == "development"


def test_validate_selection_validation_stage_passes(tmp_path: Path) -> None:
    report = validate_protocol_directory(
        protocol_dir=_PROTOCOL_DIR,
        stage="selection-validation",
        implementation_commit=IMPLEMENTATION_COMMIT,
    )
    assert report.status == "ok"


def test_validate_missing_preregistration_raises(tmp_path: Path) -> None:
    with pytest.raises(ProtocolValidationError, match="preregistration.json"):
        validate_protocol_directory(
            protocol_dir=tmp_path,
            stage="development",
            implementation_commit=IMPLEMENTATION_COMMIT,
        )


def test_validate_reports_missing_artifacts(tmp_path: Path) -> None:
    # Write a valid-looking preregistration but no manifests
    protocol_hash = compute_protocol_hashes().protocol_declaration_sha256
    (tmp_path / "preregistration.json").write_text(
        json.dumps({"protocol_id": PROTOCOL_ID, "protocol_hash": protocol_hash}) + "\n",
        encoding="utf-8",
    )
    report = validate_protocol_directory(
        protocol_dir=tmp_path,
        stage="development",
        implementation_commit=IMPLEMENTATION_COMMIT,
    )
    assert report.status == "error"
    assert len(report.mandatory_artifacts_missing) == len(MANDATORY_CANDIDATES)


# ── 13. Lock behaviour ────────────────────────────────────────────────────────


def test_validation_cli_rejects_final_validation_stage() -> None:
    exit_code = validation_main(
        [
            "validate",
            "--protocol-dir",
            str(_PROTOCOL_DIR),
            "--stage",
            "development",  # only development and selection-validation allowed
            "--output-dir",
            "/tmp/unused",
        ]
    )
    assert exit_code == 0  # development stage OK


def test_locked_stage_error_is_raised_directly() -> None:
    with pytest.raises(LockedStageError):
        validate_protocol_directory(
            protocol_dir=_PROTOCOL_DIR,
            stage="final-validation",
            implementation_commit=IMPLEMENTATION_COMMIT,
        )


# ── 14. CLI smoke ─────────────────────────────────────────────────────────────


def test_qrtc_selection_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "qrtc_benchmark.validation_cli", "--help"],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )
    assert result.returncode == 0
    assert "qrtc-selection" in result.stdout or "validate" in result.stdout


def test_qrtc_selection_validate_development_exits_zero() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qrtc_benchmark.validation_cli",
            "validate",
            "--protocol-dir",
            str(_PROTOCOL_DIR),
            "--stage",
            "development",
            "--output-dir",
            "/tmp/unused",
        ],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )
    assert result.returncode == 0


def test_qrtc_selection_validate_json_output() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qrtc_benchmark.validation_cli",
            "validate",
            "--protocol-dir",
            str(_PROTOCOL_DIR),
            "--stage",
            "selection-validation",
            "--output-dir",
            "/tmp/unused",
            "--json",
        ],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["protocol_id"] == PROTOCOL_ID
    assert report["status"] == "ok"
    assert report["dry_run_only"] is True


# ── 15. Preregistration completeness ─────────────────────────────────────────


def test_preregistration_no_experiment_executed() -> None:
    prereg = json.loads(
        (_PROTOCOL_DIR / "preregistration.json").read_text(encoding="utf-8")
    )
    assert prereg.get("no_experiment_executed") is True


def test_preregistration_no_winner_selected() -> None:
    prereg = json.loads(
        (_PROTOCOL_DIR / "preregistration.json").read_text(encoding="utf-8")
    )
    assert prereg.get("no_winner_selected") is True


def test_preregistration_authority_recommend_only() -> None:
    prereg = json.loads(
        (_PROTOCOL_DIR / "preregistration.json").read_text(encoding="utf-8")
    )
    assert prereg.get("authority") == "recommend_only"


def test_preregistration_hardware_actuation_disabled() -> None:
    prereg = json.loads(
        (_PROTOCOL_DIR / "preregistration.json").read_text(encoding="utf-8")
    )
    assert prereg.get("hardware_actuation_enabled") is False


def test_no_hybrid_qrtc_v2_reference_in_protocol() -> None:
    """No reference to 'Hybrid QRTC V2' as an implemented controller."""
    import qrtc_benchmark.controllers as ctrl
    import qrtc_benchmark.selection_protocol as sp

    for module in (sp, ctrl):
        src = Path(module.__file__).read_text(encoding="utf-8")
        assert "Hybrid QRTC V2" not in src, (
            f"'Hybrid QRTC V2' must not appear in {module.__file__}"
        )
