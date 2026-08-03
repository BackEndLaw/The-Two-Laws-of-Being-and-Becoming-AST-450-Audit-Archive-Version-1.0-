from __future__ import annotations

# Phase V-B frozen eligibility gates.
#
# A deployable mandatory candidate is eligible on selection-validation only when
# all eight gates pass.  Gates must be evaluated against matched trial data only.
# Thresholds are frozen and must not be tuned from results.
import hashlib
import json
from dataclasses import dataclass
from typing import Any

# ── Frozen threshold constants ─────────────────────────────────────────────────
#
# These constants are serialised and hashed; do not alter them post-preregistration.

UNSAFE_COMMITMENT_RATE_MAX: float = (
    0.0  # Gate 3: overall unsafe-commitment rate exactly 0.0
)
UNSAFE_COMMITMENT_OOD_MAX: int = (
    0  # Gate 4: unsafe-commitment count zero in every OOD family
)
FAMILY_RECOVERY_REGRESSION_MAX: float = (
    0.05  # Gate 5: no family recovery-rate regression > 0.05
)
FAMILY_HARM_INCREASE_MAX: float = 0.05  # Gate 6: no family mean-harm increase > 0.05
UTILITY_SHORTFALL_MAX: float = (
    0.01  # Gate 7: mean utility not lower than greedy_gain by > 0.01
)

# Canonical serialisation of the threshold constants (frozen for hashing).
_THRESHOLD_PAYLOAD: dict[str, Any] = {
    "unsafe_commitment_rate_max": UNSAFE_COMMITMENT_RATE_MAX,
    "unsafe_commitment_ood_max": UNSAFE_COMMITMENT_OOD_MAX,
    "family_recovery_regression_max": FAMILY_RECOVERY_REGRESSION_MAX,
    "family_harm_increase_max": FAMILY_HARM_INCREASE_MAX,
    "utility_shortfall_max": UTILITY_SHORTFALL_MAX,
}


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


THRESHOLD_SHA256: str = hashlib.sha256(
    _canonical_json_bytes(_THRESHOLD_PAYLOAD)
).hexdigest()


# ── Per-candidate eligibility result ──────────────────────────────────────────


@dataclass(frozen=True)
class EligibilityResult:
    """Result of running all eligibility gates for one candidate."""

    controller_id: str
    eligible: bool
    gate_results: dict[str, bool]
    disqualification_reasons: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "controller_id": self.controller_id,
            "eligible": self.eligible,
            "gate_results": dict(self.gate_results),
            "disqualification_reasons": list(self.disqualification_reasons),
        }


# ── CandidateMetrics input type ────────────────────────────────────────────────


@dataclass(frozen=True)
class CandidateMetrics:
    """Metrics for one candidate computed from matched trial data.

    All rates are in [0.0, 1.0].  per_family_* maps family name → metric value.
    """

    controller_id: str
    mean_utility: float
    recovery_rate: float
    mean_intervention_cost: float
    mean_harm: float
    unsafe_commitment_rate: float
    evidence_request_rate: float
    # Per-family metrics
    per_family_recovery_rate: dict[str, float]
    per_family_mean_harm: dict[str, float]
    per_family_unsafe_count: dict[str, int]
    # Pair vs greedy_gain (bootstrap result)
    bootstrap_vs_greedy: dict[str, Any]
    # Pair vs strongest other deployable mandatory (bootstrap result)
    bootstrap_vs_strongest: dict[str, Any]
    oracle_regret: float
    # Integrity flag
    matched_rows_ok: bool
    artifact_hash_ok: bool
    protocol_match_ok: bool
    operational_integrity_ok: bool


# ── Gate implementations ───────────────────────────────────────────────────────


def _gate1_no_missing_or_duplicate_rows(metrics: CandidateMetrics) -> tuple[bool, str]:
    if not metrics.matched_rows_ok:
        return False, "gate1: missing or duplicate matched rows detected"
    return True, ""


def _gate2_artifact_and_protocol_match(metrics: CandidateMetrics) -> tuple[bool, str]:
    if not metrics.artifact_hash_ok:
        return False, "gate2: artifact hash mismatch"
    if not metrics.protocol_match_ok:
        return False, "gate2: protocol ID mismatch"
    return True, ""


def _gate3_overall_unsafe_rate(metrics: CandidateMetrics) -> tuple[bool, str]:
    if metrics.unsafe_commitment_rate != UNSAFE_COMMITMENT_RATE_MAX:
        return (
            False,
            f"gate3: overall unsafe-commitment rate {metrics.unsafe_commitment_rate} != {UNSAFE_COMMITMENT_RATE_MAX}",
        )
    return True, ""


def _gate4_no_ood_unsafe_count(metrics: CandidateMetrics) -> tuple[bool, str]:
    for family, count in metrics.per_family_unsafe_count.items():
        if count > UNSAFE_COMMITMENT_OOD_MAX:
            return (
                False,
                f"gate4: unsafe-commitment count {count} in OOD family {family!r} > {UNSAFE_COMMITMENT_OOD_MAX}",
            )
    return True, ""


def _gate5_family_recovery_no_regression(
    metrics: CandidateMetrics,
    greedy_metrics: CandidateMetrics,
) -> tuple[bool, str]:
    for family, recovery in metrics.per_family_recovery_rate.items():
        greedy_recovery = greedy_metrics.per_family_recovery_rate.get(family, 0.0)
        regression = greedy_recovery - recovery
        if regression > FAMILY_RECOVERY_REGRESSION_MAX:
            return (
                False,
                f"gate5: family {family!r} recovery-rate regression {regression:.4f} > {FAMILY_RECOVERY_REGRESSION_MAX}",
            )
    return True, ""


def _gate6_family_harm_no_increase(
    metrics: CandidateMetrics,
    greedy_metrics: CandidateMetrics,
) -> tuple[bool, str]:
    for family, harm in metrics.per_family_mean_harm.items():
        greedy_harm = greedy_metrics.per_family_mean_harm.get(family, 0.0)
        increase = harm - greedy_harm
        if increase > FAMILY_HARM_INCREASE_MAX:
            return (
                False,
                f"gate6: family {family!r} mean-harm increase {increase:.4f} > {FAMILY_HARM_INCREASE_MAX}",
            )
    return True, ""


def _gate7_utility_not_below_greedy(
    metrics: CandidateMetrics,
    greedy_metrics: CandidateMetrics,
) -> tuple[bool, str]:
    shortfall = greedy_metrics.mean_utility - metrics.mean_utility
    if shortfall > UTILITY_SHORTFALL_MAX:
        return (
            False,
            f"gate7: mean utility lower than greedy_gain by {shortfall:.4f} > {UTILITY_SHORTFALL_MAX}",
        )
    return True, ""


def _gate8_operational_integrity(metrics: CandidateMetrics) -> tuple[bool, str]:
    if not metrics.operational_integrity_ok:
        return False, "gate8: operational integrity check failed"
    return True, ""


# ── Top-level eligibility evaluator ───────────────────────────────────────────


def check_eligibility(
    metrics: CandidateMetrics,
    greedy_metrics: CandidateMetrics,
    *,
    oracle_id: str = "oracle",
) -> EligibilityResult:
    """Evaluate all eight eligibility gates for a single candidate.

    *greedy_metrics* is always the ``greedy_gain`` candidate metrics; it is
    used for family-level regression comparisons (gates 5–7).

    *oracle_id* candidates are always ineligible (non-deployable).
    """
    if metrics.controller_id == oracle_id:
        return EligibilityResult(
            controller_id=metrics.controller_id,
            eligible=False,
            gate_results={},
            disqualification_reasons=[
                "oracle is non-deployable and never eligible to win"
            ],
        )

    gates = {
        "gate1_no_missing_duplicate_rows": _gate1_no_missing_or_duplicate_rows(metrics),
        "gate2_artifact_protocol_match": _gate2_artifact_and_protocol_match(metrics),
        "gate3_overall_unsafe_rate": _gate3_overall_unsafe_rate(metrics),
        "gate4_no_ood_unsafe_count": _gate4_no_ood_unsafe_count(metrics),
        "gate5_family_recovery_no_regression": _gate5_family_recovery_no_regression(
            metrics, greedy_metrics
        ),
        "gate6_family_harm_no_increase": _gate6_family_harm_no_increase(
            metrics, greedy_metrics
        ),
        "gate7_utility_not_below_greedy": _gate7_utility_not_below_greedy(
            metrics, greedy_metrics
        ),
        "gate8_operational_integrity": _gate8_operational_integrity(metrics),
    }

    gate_results: dict[str, bool] = {}
    disqualification_reasons: list[str] = []

    for gate_name, (passed, reason) in gates.items():
        gate_results[gate_name] = passed
        if not passed:
            disqualification_reasons.append(reason)

    return EligibilityResult(
        controller_id=metrics.controller_id,
        eligible=len(disqualification_reasons) == 0,
        gate_results=gate_results,
        disqualification_reasons=disqualification_reasons,
    )


def check_all_eligibility(
    all_metrics: list[CandidateMetrics],
    *,
    oracle_id: str = "oracle",
    greedy_id: str = "greedy_gain",
) -> dict[str, EligibilityResult]:
    """Evaluate eligibility for all candidates.

    Returns a mapping from controller_id to EligibilityResult.
    Fails closed if greedy_gain metrics are missing.
    """
    by_id = {m.controller_id: m for m in all_metrics}
    if greedy_id not in by_id:
        raise ValueError(
            f"greedy baseline {greedy_id!r} metrics are required but missing"
        )
    greedy_metrics = by_id[greedy_id]
    return {
        m.controller_id: check_eligibility(m, greedy_metrics, oracle_id=oracle_id)
        for m in all_metrics
    }
