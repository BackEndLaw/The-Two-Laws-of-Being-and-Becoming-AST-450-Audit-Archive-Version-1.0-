from __future__ import annotations

# Phase V-B Controller Selection Rule — pure typed decision function.
#
# Selection criteria (frozen, not tuned from results):
#
#   Superiority: paired utility delta vs greedy_gain with bootstrap lower bound > 0.0
#   Ranking:     highest mean utility → lowest unsafe rate → lowest mean harm →
#                lowest mean cost → highest recovery rate → lexical controller ID
#
# Outcomes:
#   provisional_selection  — exactly one superior eligible deployable candidate
#   no_controller_selected — no superior eligible candidate OR no eligible candidate
#
# Oracle: can never be selected.
from dataclasses import dataclass
from enum import Enum
from typing import Any

from qrtc_benchmark.eligibility import CandidateMetrics, EligibilityResult
from qrtc_benchmark.selection_protocol import DEPLOYABLE_MANDATORY_CANDIDATES

# ── Outcome types ──────────────────────────────────────────────────────────────


class SelectionOutcome(str, Enum):
    PROVISIONAL_SELECTION = "provisional_selection"
    NO_CONTROLLER_SELECTED = "no_controller_selected"


# ── Selection result ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SelectionResult:
    """Output of the selection rule."""

    outcome: SelectionOutcome
    selected_id: str | None
    eligible_ids: list[str]
    superior_ids: list[str]
    disqualified: dict[str, list[str]]
    ranking_details: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "selected_id": self.selected_id,
            "eligible_ids": list(self.eligible_ids),
            "superior_ids": list(self.superior_ids),
            "disqualified": {k: list(v) for k, v in self.disqualified.items()},
            "ranking_details": list(self.ranking_details),
        }


# ── Superiority test ───────────────────────────────────────────────────────────


def _is_superior(metrics: CandidateMetrics) -> bool:
    """Return True when the bootstrap lower bound vs greedy_gain is strictly > 0.0."""
    ci_low = metrics.bootstrap_vs_greedy.get("ci_low", None)
    if ci_low is None:
        return False
    return float(ci_low) > 0.0


# ── Ranking key ────────────────────────────────────────────────────────────────


def _ranking_key(
    metrics: CandidateMetrics,
) -> tuple[float, float, float, float, float, str]:
    """Lower is better for rank position 1 (the winner).

    Tiebreak order:
    1. highest mean utility  → negate for ascending sort
    2. lowest unsafe rate
    3. lowest mean harm
    4. lowest mean cost
    5. highest recovery rate → negate for ascending sort
    6. lexical controller ID
    """
    return (
        -metrics.mean_utility,
        metrics.unsafe_commitment_rate,
        metrics.mean_harm,
        metrics.mean_intervention_cost,
        -metrics.recovery_rate,
        metrics.controller_id,
    )


# ── Selection rule ─────────────────────────────────────────────────────────────


def select_controller(
    all_metrics: list[CandidateMetrics],
    eligibility_results: dict[str, EligibilityResult],
    *,
    oracle_id: str = "oracle",
    deployable_mandatory: tuple[str, ...] = DEPLOYABLE_MANDATORY_CANDIDATES,
) -> SelectionResult:
    """Pure typed selection decision function.

    Parameters
    ----------
    all_metrics:
        Metrics for every candidate (including oracle).  Only deployable
        mandatory candidates are considered for selection.
    eligibility_results:
        Pre-computed eligibility results (from ``check_all_eligibility``).
    oracle_id:
        Controller ID of the oracle; it can never be selected.
    deployable_mandatory:
        Ordered tuple of deployable mandatory candidate IDs.

    Returns
    -------
    SelectionResult
    """
    metrics_by_id = {m.controller_id: m for m in all_metrics}

    # Build disqualification map (for non-eligible candidates).
    disqualified: dict[str, list[str]] = {}
    eligible_ids: list[str] = []

    for cid in deployable_mandatory:
        if cid == oracle_id:
            disqualified[cid] = ["oracle is non-deployable and never eligible to win"]
            continue
        er = eligibility_results.get(cid)
        if er is None:
            disqualified[cid] = ["eligibility result missing"]
            continue
        if er.eligible:
            eligible_ids.append(cid)
        else:
            disqualified[cid] = list(er.disqualification_reasons)

    if not eligible_ids:
        return SelectionResult(
            outcome=SelectionOutcome.NO_CONTROLLER_SELECTED,
            selected_id=None,
            eligible_ids=[],
            superior_ids=[],
            disqualified=disqualified,
            ranking_details=[],
        )

    # Identify superior candidates among eligible.
    superior_candidates: list[CandidateMetrics] = []
    for cid in eligible_ids:
        m = metrics_by_id.get(cid)
        if m is None:
            continue
        if _is_superior(m):
            superior_candidates.append(m)

    superior_ids = [m.controller_id for m in superior_candidates]

    if not superior_candidates:
        return SelectionResult(
            outcome=SelectionOutcome.NO_CONTROLLER_SELECTED,
            selected_id=None,
            eligible_ids=eligible_ids,
            superior_ids=[],
            disqualified=disqualified,
            ranking_details=[],
        )

    # Rank by the tie-breaking key.
    ranked = sorted(superior_candidates, key=_ranking_key)
    ranking_details = [
        {
            "rank": idx + 1,
            "controller_id": m.controller_id,
            "mean_utility": m.mean_utility,
            "unsafe_commitment_rate": m.unsafe_commitment_rate,
            "mean_harm": m.mean_harm,
            "mean_intervention_cost": m.mean_intervention_cost,
            "recovery_rate": m.recovery_rate,
            "bootstrap_ci_low_vs_greedy": m.bootstrap_vs_greedy.get("ci_low"),
        }
        for idx, m in enumerate(ranked)
    ]

    winner = ranked[0]

    return SelectionResult(
        outcome=SelectionOutcome.PROVISIONAL_SELECTION,
        selected_id=winner.controller_id,
        eligible_ids=eligible_ids,
        superior_ids=superior_ids,
        disqualified=disqualified,
        ranking_details=ranking_details,
    )
