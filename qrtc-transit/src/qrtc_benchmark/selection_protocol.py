from __future__ import annotations

# Phase V-B Controller Selection Protocol v1
#
# Protocol ID: phase5b-selection-v1
# State:       preregistered_not_executed
# Phase rev:   phase5b
#
# This module contains:
#  - Canonical frozen protocol declaration
#  - Authoritative semantic declarations derived from Phase5Config / phase5.py
#  - Deterministic serialisation helpers
#  - Checksum utilities
#
# IMPORTANT: Do not import anything that generates experiment data here.
# This module MUST remain side-effect free on import.
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from qrtc_benchmark.controllers import MANDATORY_CONTROLLER_IDS
from qrtc_benchmark.phase5 import (
    _DEVELOPMENT_MECHANISMS,
    _DEVELOPMENT_PAIRS,
    _DEVELOPMENT_TRIPLES,
    _FINAL_MECHANISMS,
    _FINAL_PAIRS,
    _FINAL_TRIPLES,
    _VALIDATION_MECHANISMS,
    _VALIDATION_PAIRS,
    _VALIDATION_TRIPLES,
    SPLIT_SEEDS,
    Phase5Config,
    Phase5Family,
    Phase5Intervention,
    Phase5RelationType,
)

# ── Protocol identity ──────────────────────────────────────────────────────────

PROTOCOL_ID: str = "phase5b-selection-v1"
PROTOCOL_STATE: str = "preregistered_not_executed"
PROTOCOL_PHASE_REVISION: str = "phase5b"

#: The immutable main-branch commit containing the merged rescueos-controller-v1 APIs (PR #22).
IMPLEMENTATION_COMMIT: str = "6aa56a7abae975274e95a9ba2941fe2002794592"

# ── Mandatory candidates (exactly as specified) ────────────────────────────────
#   - oracle is mandatory but non-deployable and never eligible to win.
#   - qrtc is identified as provisional primary only; no automatic preference.
MANDATORY_CANDIDATES: tuple[str, ...] = (
    MANDATORY_CONTROLLER_IDS  # qrtc, qrtc_no_abstention, qrtc_untyped, greedy_gain, oracle
)

#: Deployable mandatory candidates (oracle excluded).
DEPLOYABLE_MANDATORY_CANDIDATES: tuple[str, ...] = tuple(
    cid for cid in MANDATORY_CANDIDATES if cid != "oracle"
)

#: Optional descriptive baselines — excluded from eligibility and winner selection.
OPTIONAL_BASELINE_IDS: tuple[str, ...] = (
    "end_to_end",
    "highest_stage_posterior",
    "cheapest_first",
    "random",
)

# ── Split declarations ─────────────────────────────────────────────────────────
#   Authoritative split alias/name pairs with their roles.

SPLIT_ALIASES: dict[str, str] = {
    "development": "development",
    "validation": "selection-validation",
    "test": "final-validation",
}

SPLIT_SEEDS_FROZEN: dict[str, tuple[int, ...]] = {
    key: tuple(values) for key, values in SPLIT_SEEDS.items()
}

# ── Authoritative Phase5Config constants ──────────────────────────────────────
#: All numeric/configuration constants from the authoritative Phase5Config().
_CFG = Phase5Config()

LAMBDA_COST: float = _CFG.lambda_cost
BETA_HARM: float = _CFG.beta_harm
GAMMA_UNSAFE: float = _CFG.gamma_unsafe
MAX_ACTIONS: int = _CFG.max_actions
BOOTSTRAP_REPS: int = _CFG.bootstrap_reps
BOOTSTRAP_SEED: int = _CFG.bootstrap_seed
RELIABILITY_LEVELS: tuple[float, ...] = _CFG.reliability_levels
COST_REGIMES: tuple[str, ...] = _CFG.cost_regimes
DEVELOPMENT_FAMILY_TRIALS: int = _CFG.development_family_trials
VALIDATION_FAMILY_TRIALS: int = _CFG.validation_family_trials
TEST_FAMILY_TRIALS: int = _CFG.test_family_trials

# ── Mechanisms, pairs, triples ─────────────────────────────────────────────────

DEVELOPMENT_MECHANISMS: dict[str, tuple[str, ...]] = {
    family.value: _DEVELOPMENT_MECHANISMS[family] for family in Phase5Family
}
VALIDATION_MECHANISMS: dict[str, tuple[str, ...]] = {
    family.value: _VALIDATION_MECHANISMS[family] for family in Phase5Family
}
FINAL_MECHANISMS: dict[str, tuple[str, ...]] = {
    family.value: _FINAL_MECHANISMS[family] for family in Phase5Family
}

DEVELOPMENT_PAIRS: tuple[str, ...] = _DEVELOPMENT_PAIRS
VALIDATION_PAIRS: tuple[str, ...] = _VALIDATION_PAIRS
FINAL_PAIRS: tuple[str, ...] = _FINAL_PAIRS

DEVELOPMENT_TRIPLES: tuple[str, ...] = _DEVELOPMENT_TRIPLES
VALIDATION_TRIPLES: tuple[str, ...] = _VALIDATION_TRIPLES
FINAL_TRIPLES: tuple[str, ...] = _FINAL_TRIPLES

# ── Controller version ─────────────────────────────────────────────────────────
from qrtc_benchmark.controllers import CONTROLLER_VERSION

CONTROLLER_VERSIONS: dict[str, str] = {
    cid: CONTROLLER_VERSION for cid in MANDATORY_CANDIDATES
}

# ── Deterministic serialisation helpers ───────────────────────────────────────


def canonical_json_bytes(payload: object) -> bytes:
    """Serialise *payload* deterministically (sorted keys, no spaces, UTF-8)."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ── Canonical semantic declaration ─────────────────────────────────────────────


def canonical_split_declaration() -> dict[str, Any]:
    """Return the authoritative split declaration payload.

    Covers:
    - Split alias/name pairs
    - Seeds per split
    - Mechanism IDs per family per split
    - Pair IDs per split
    - Triple IDs per split
    - Trial counts per split
    """
    return {
        "protocol_id": PROTOCOL_ID,
        "phase_revision": PROTOCOL_PHASE_REVISION,
        "split_aliases": SPLIT_ALIASES,
        "split_seeds": {k: list(v) for k, v in SPLIT_SEEDS_FROZEN.items()},
        "development_mechanisms": {
            k: list(v) for k, v in DEVELOPMENT_MECHANISMS.items()
        },
        "validation_mechanisms": {k: list(v) for k, v in VALIDATION_MECHANISMS.items()},
        "final_mechanisms": {k: list(v) for k, v in FINAL_MECHANISMS.items()},
        "development_pairs": list(DEVELOPMENT_PAIRS),
        "validation_pairs": list(VALIDATION_PAIRS),
        "final_pairs": list(FINAL_PAIRS),
        "development_triples": list(DEVELOPMENT_TRIPLES),
        "validation_triples": list(VALIDATION_TRIPLES),
        "final_triples": list(FINAL_TRIPLES),
        "development_family_trials": DEVELOPMENT_FAMILY_TRIALS,
        "validation_family_trials": VALIDATION_FAMILY_TRIALS,
        "test_family_trials": TEST_FAMILY_TRIALS,
    }


def canonical_config_declaration() -> dict[str, Any]:
    """Return the authoritative Phase V-B configuration parameter payload."""
    return {
        "protocol_id": PROTOCOL_ID,
        "phase_revision": PROTOCOL_PHASE_REVISION,
        "lambda_cost": LAMBDA_COST,
        "beta_harm": BETA_HARM,
        "gamma_unsafe": GAMMA_UNSAFE,
        "max_actions": MAX_ACTIONS,
        "bootstrap_reps": BOOTSTRAP_REPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "reliability_levels": list(RELIABILITY_LEVELS),
        "cost_regimes": list(COST_REGIMES),
        "utility_formula": (
            "utility = recovery_reward - lambda_cost * intervention_cost"
            " - beta_harm * harm - gamma_unsafe * unsafe_commitment"
        ),
    }


def canonical_candidate_declaration() -> dict[str, Any]:
    """Return the authoritative candidate roster payload."""
    return {
        "protocol_id": PROTOCOL_ID,
        "phase_revision": PROTOCOL_PHASE_REVISION,
        "mandatory_candidates": list(MANDATORY_CANDIDATES),
        "deployable_mandatory_candidates": list(DEPLOYABLE_MANDATORY_CANDIDATES),
        "optional_descriptive_baselines": list(OPTIONAL_BASELINE_IDS),
        "oracle_non_deployable": True,
        "oracle_never_eligible_to_win": True,
        "provisional_primary": "qrtc",
        "provisional_primary_note": (
            "qrtc is identified as provisional primary only; "
            "it receives no automatic preference in selection."
        ),
        "controller_versions": CONTROLLER_VERSIONS,
    }


def canonical_protocol_declaration() -> dict[str, Any]:
    """Return the full canonical protocol preregistration payload."""
    splits = canonical_split_declaration()
    config = canonical_config_declaration()
    candidates = canonical_candidate_declaration()
    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_state": PROTOCOL_STATE,
        "phase_revision": PROTOCOL_PHASE_REVISION,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "splits": splits,
        "config": config,
        "candidates": candidates,
        "final_validation_status": "locked_not_executed",
        "hardware_actuation_enabled": False,
        "authority": "recommend_only",
        "no_experiment_executed": True,
        "no_winner_selected": True,
    }


# ── Hash declarations ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProtocolHashes:
    """Deterministic SHA-256 hashes of canonical protocol sub-declarations."""

    split_declaration_sha256: str
    config_declaration_sha256: str
    candidate_declaration_sha256: str
    protocol_declaration_sha256: str


def compute_protocol_hashes() -> ProtocolHashes:
    """Compute and return deterministic hashes of all canonical declarations."""
    split_bytes = canonical_json_bytes(canonical_split_declaration())
    config_bytes = canonical_json_bytes(canonical_config_declaration())
    candidate_bytes = canonical_json_bytes(canonical_candidate_declaration())
    protocol_bytes = canonical_json_bytes(canonical_protocol_declaration())
    return ProtocolHashes(
        split_declaration_sha256=sha256_hex(split_bytes),
        config_declaration_sha256=sha256_hex(config_bytes),
        candidate_declaration_sha256=sha256_hex(candidate_bytes),
        protocol_declaration_sha256=sha256_hex(protocol_bytes),
    )


# ── Actions / families ─────────────────────────────────────────────────────────

ACTIONS: tuple[str, ...] = tuple(a.value for a in Phase5Intervention)
FAMILIES: tuple[str, ...] = tuple(f.value for f in Phase5Family)
RELATION_TYPES: tuple[str, ...] = tuple(r.value for r in Phase5RelationType)


# ── Metric names ───────────────────────────────────────────────────────────────

REQUIRED_METRICS: tuple[str, ...] = (
    "mean_utility",
    "recovery_rate",
    "mean_intervention_cost",
    "mean_harm",
    "unsafe_commitment_rate",
    "evidence_request_rate",
    "per_family_v1_metrics",
    "per_family_v2_metrics",
    "per_family_v3_metrics",
    "per_family_v4_metrics",
    "paired_utility_delta_vs_greedy_gain",
    "paired_utility_delta_vs_strongest_deployable",
    "oracle_regret",
)
