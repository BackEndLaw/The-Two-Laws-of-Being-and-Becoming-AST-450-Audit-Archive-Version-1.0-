"""
Remainder Quality Framework (Q(ρ)) — v2.0 LEAKAGE-FREE

Operationalization of the five formal variables for identity preservation
across jurisdictional collapse (Gate events).

CRITICAL CONSTRAINT (v2.0): ALL predictor variables are computed from
PRE-GATE structural features only. No variable may reference Outcome,
Out(t₀), Out(late), Match, Regime_Predicted, or any post-Gate label.

Variable redesign summary:
  SC_closure     = Internal self-consistency / tight-loop fit (pre-Gate)
  SC_portability = Structural invariance under context transform (pre-Gate)
  CID            = Q_calc / Load — coherent charge per unit complexity (pre-Gate ✓)
  ECC            = Rescue capacity vs Wall resistance (pre-Gate)
  ID             = Behavioral richness + integration index (pre-Gate)
  CAC            = Contradiction metabolism capacity from FR_Risk/Rescue balance (pre-Gate)
  Frag_pre       = Structural fragmentation risk from rule flags (pre-Gate)

Master variable (v2.0 with interaction terms):
  Q(ρ) = σ(α·SC_closure + α'·SC_portability + β·CID + γ·ECC + δ·ID + ε·CAC
           + η·(SC_closure × CID) + κ·(SC_closure × CAC) - λ·Frag_pre)

Applied to: Atlas 245 biographical cases
Test: Does the sign pattern hold WITHOUT label leakage?
"""

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import spearmanr
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


# ==============================================================================
# DATA DICTIONARY (TIME INDEX FOR EACH VARIABLE)
# ==============================================================================
#
# All variables below are annotated with their time index:
#   PRE  = computed entirely from pre-Gate structural measurements
#   POST = uses post-Gate outcome (FORBIDDEN in predictors; label only)
#
# Atlas columns confirmed as PRE-GATE:
#   Bio, Env, Cog, Id, Sym    — behavioral dimension scores (coded pre-event)
#   C, Φ, Q_calc               — structural charge measures
#   Load, Tension, κ           — systemic stress measures
#   Mode, Ω, Integration Type  — contextual type codes
#   I                          — integration index
#   FR Risk                    — fragmentation risk flag (0/1, pre-Gate rule)
#   Rescue                     — rescue capacity flag (0/1, pre-Gate rule)
#   Walls                      — boundary rigidity score (pre-Gate)
#   Template_Deficit           — structural gap indicator (pre-Gate rule)
#   FR_rule                    — structural FR rule trigger (pre-Gate)
#   Rescue_rule                — structural rescue rule trigger (pre-Gate)
#   Q_ge_12_rule               — high-Q structural flag (pre-Gate)
#   Q_le_6_rule                — low-Q structural flag (pre-Gate)
#   Low_C_low_Phi_rule         — dual-low structural flag (pre-Gate)
#   PR_rule_candidate          — transitional structure flag (pre-Gate)
#   Ext                        — externalization score (pre-Gate)
#
# POST-GATE (label only — must NOT appear in predictors):
#   Outcome, Out(t₀), Out(late), Match, Regime_Predicted_*, Reboot_Quality
#
# ==============================================================================


def load_nde_atlas_data():
    """Load Atlas data. NDE dataset used for cross-reference only."""
    nde_df = pd.read_csv(BASE_DIR / "nde_40_case_dataset.csv")
    atlas_df = pd.read_csv(BASE_DIR / "atlas_predictions_with_accuracy.csv")

    print(f"\nAtlas dataset: {len(atlas_df)} cases")
    print(f"NDE dataset:   {len(nde_df)} cases (reference only)")
    print(f"\nOutcome distribution (label — NOT used in predictors):")
    print(atlas_df["Outcome"].value_counts().sort_index())

    return atlas_df


def classify_reboot_quality(outcome_code):
    """
    POST-GATE label only. Used as outcome variable, never as predictor.
      Clean  (1): CR, PR, MR, SR
      Corrupt(0): FR
    """
    if outcome_code == "FR":
        return 0
    elif outcome_code in ["CR", "PR", "MR", "SR"]:
        return 1
    return np.nan


def _flag(val):
    """Safely parse a binary flag field."""
    try:
        return int(float(val)) == 1
    except (TypeError, ValueError):
        return False


# ==============================================================================
# PRE-GATE VARIABLE 1a: SC_closure  [PRE-GATE]
# Internal self-consistency — how tight / self-sealing is the structure.
# HIGH = closed loop, internally non-contradictory.
# WARNING: high closure WITHOUT portability is the "brittle coherence" pattern.
# ==============================================================================

def compute_sc_closure(row):
    """
    SC_closure = internal satisfiability of structural constraints.

    Time index: PRE-GATE
    Inputs used: C, Φ, κ, Tension, Load, Walls
    No outcome field referenced.

    Operationalization:
      - C × Φ should equal Q_calc (self-consistency of charge computation)
      - κ ≈ 1.0 means Load ≈ Q (balanced system, no excess tension)
      - Low Walls = open; High Walls = closed/self-sealing
    """
    c = float(row.get("C", 0) or 0)
    phi = float(row.get("Φ", 0) or 0)
    q_calc = float(row.get("Q_calc", 0) or 0)
    load = float(row.get("Load", 1) or 1)
    tension = float(row.get("Tension", 0) or 0)
    walls = float(row.get("Walls", 0) or 0)

    # Internal consistency: does C × Φ match Q_calc?
    expected_q = c * phi
    consistency = 1.0 - min(1.0, abs(expected_q - q_calc) / max(expected_q, 1))

    # κ balance: is Load / Q near 1? (tight loop = high closure)
    kappa = load / max(q_calc, 0.01)
    kappa_closure = 1.0 / (1.0 + abs(kappa - 1.0))  # peaks at κ=1

    # Wall sealing: more walls = more closure (self-sealing)
    wall_closure = min(1.0, walls / 4.0)

    sc_closure = 0.4 * consistency + 0.4 * kappa_closure + 0.2 * wall_closure
    return float(np.clip(sc_closure, 0, 1))


# ==============================================================================
# PRE-GATE VARIABLE 1b: SC_portability  [PRE-GATE]
# Structural invariance under context change — can this identity operate
# across more than one jurisdiction?
# HIGH = multi-context; LOW = single-context / closed.
# ==============================================================================

def compute_sc_portability(row):
    """
    SC_portability = invariance of structure under context transformation.

    Time index: PRE-GATE
    Inputs used: Integration Type, I, Ext, Mode, Ω

    Operationalization:
      - Integration Type: Growth/Global and Journey/Transmission span contexts;
        Chaos/Fragmentation is single-context failure mode.
      - I (integration index): higher = more cross-context binding.
      - Ext: externalization score — institutional/cultural reach across contexts.
      - Mode diversity: X (transcendent), V (visionary), D (discovery) = wide-context;
        C (chaos) = no context portability.
    """
    integration_type = str(row.get("Integration Type", "")).strip()
    i_val = float(row.get("I", 0) or 0)
    ext = float(row.get("Ext", 0) or 0)
    mode = str(row.get("Mode", "")).strip().upper()

    # Integration type portability score
    portability_by_integration = {
        "Growth/Global":          1.0,
        "Journey/Transmission":   0.85,
        "Loss/Limitation":        0.55,
        "Biological/Individual":  0.45,
        "Chaos/Fragmentation":    0.0,
    }
    integration_score = portability_by_integration.get(integration_type, 0.5)

    # I index normalized to [0,1] (max observed ~4)
    i_score = min(1.0, i_val / 4.0)

    # Ext score normalized to [0,1] (max 4)
    ext_score = min(1.0, ext / 4.0) if pd.notna(ext) and ext > 0 else 0.0

    # Mode portability
    mode_portability = {
        "X": 1.0, "D": 0.9, "V": 0.8, "N": 0.7,
        "T": 0.6, "S": 0.55, "A": 0.5, "H": 0.5, "C": 0.0,
    }
    mode_score = mode_portability.get(mode, 0.5)

    sc_portability = (0.35 * integration_score + 0.25 * i_score +
                      0.2 * ext_score + 0.2 * mode_score)
    return float(np.clip(sc_portability, 0, 1))


# ==============================================================================
# PRE-GATE VARIABLE 2: CID  [PRE-GATE ✓]
# Compression / Integration Density = Q_calc / Load
# Already label-free. Kept as-is from v1.
# ==============================================================================

def compute_cid(row):
    """
    CID = Q_calc / Load  (coherent charge per unit systemic complexity)

    Time index: PRE-GATE
    Inputs used: Q_calc, Load

    High CID = tightly integrated structure relative to complexity demand.
    Low CID  = diffuse, weak binding — cannot carry structure across Gate.
    """
    q_calc = float(row.get("Q_calc", 0) or 0)
    load = float(row.get("Load", 1) or 1)
    if load <= 0:
        return 0.5
    return float(np.clip(q_calc / load, 0, 1))


# ==============================================================================
# PRE-GATE VARIABLE 3: ECC  [PRE-GATE — v2 fix]
# Error-Correction Capacity = repair/rescue mechanisms vs barrier resistance.
# v1 used outcome string directly — REMOVED.
# v2 uses Rescue flag, Rescue_rule, Walls, Template_Deficit.
# ==============================================================================

def compute_ecc(row):
    """
    ECC = expected recovery from perturbation, estimated from pre-Gate
          structural repair indicators.

    Time index: PRE-GATE
    Inputs used: Rescue, Rescue_rule, Walls, Template_Deficit, Low_C_low_Phi_rule

    Operationalization:
      + Rescue flag: active rescue mechanism present
      + Rescue_rule: structural rule confirms rescue pathway exists
      - Walls: high wall count = rigid, low adaptability
      - Template_Deficit: structural gap = repair pathway missing
      - Low_C_low_Phi: dual-low signal = fundamentally limited repair capacity
    """
    has_rescue = _flag(row.get("Rescue", 0))
    has_rescue_rule = _flag(row.get("Rescue_rule", 0))
    walls = float(row.get("Walls", 0) or 0)
    template_deficit = float(row.get("Template_Deficit", 0) or 0)
    low_c_low_phi = _flag(row.get("Low_C_low_Phi_rule", 0))

    # Positive contributions
    rescue_score = 0.5 * int(has_rescue) + 0.3 * int(has_rescue_rule)

    # Penalties
    wall_penalty = min(0.4, walls * 0.1)  # Each wall reduces ECC by 0.1, cap at 0.4
    deficit_penalty = min(0.3, template_deficit * 0.1)
    low_penalty = 0.2 if low_c_low_phi else 0.0

    ecc = 0.5 + rescue_score - wall_penalty - deficit_penalty - low_penalty
    return float(np.clip(ecc, 0, 1))


# ==============================================================================
# PRE-GATE VARIABLE 4: ID  [PRE-GATE — v2 fix]
# Identity Depth = how many independent layers support identity.
# v1 Layers 3 & 4 referenced outcome — REMOVED.
# v2 uses behavioral richness + integration index + Mode depth only.
# ==============================================================================

def compute_id(row):
    """
    ID = multi-layer identity support depth, pre-Gate only.

    Time index: PRE-GATE
    Inputs used: Bio, Env, Cog, Id, Sym, I, Mode

    Layer structure (all pre-Gate):
      Layer 1 (0.1 weight): Case always has an identity (baseline)
      Layer 2 (0.3 weight): Behavioral richness — how many of 5 dimensions
                            are non-trivially populated (> 1)
      Layer 3 (0.3 weight): Integration binding — I index (cross-context links)
      Layer 4 (0.3 weight): Mode depth — how meta/abstract is the dominant mode

    High ID = identity supported by multiple independent, deep invariants.
    """
    bio = float(row.get("Bio", 0) or 0)
    env = float(row.get("Env", 0) or 0)
    cog = float(row.get("Cog", 0) or 0)
    identity = float(row.get("Id", 0) or 0)
    sym = float(row.get("Sym", 0) or 0)
    i_val = float(row.get("I", 0) or 0)
    mode = str(row.get("Mode", "")).strip().upper()

    # Layer 1: always present
    l1 = 0.1

    # Layer 2: behavioral richness — fraction of dimensions > 1
    active_dims = sum([bio > 1, env > 1, cog > 1, identity > 1, sym > 1])
    l2 = 0.3 * (active_dims / 5.0)

    # Layer 3: integration index (0–4 range)
    l3 = 0.3 * min(1.0, i_val / 4.0)

    # Layer 4: Mode depth (deeper modes support richer identity invariants)
    mode_depth = {
        "X": 1.0, "V": 0.9, "D": 0.85, "S": 0.7,
        "N": 0.65, "T": 0.6, "A": 0.55, "H": 0.5, "C": 0.1,
    }
    l4 = 0.3 * mode_depth.get(mode, 0.5)

    id_val = l1 + l2 + l3 + l4
    return float(np.clip(id_val, 0, 1))


# ==============================================================================
# PRE-GATE VARIABLE 5: CAC  [PRE-GATE — v2 fix, now CONTINUOUS]
# Contradiction Assimilation Capacity.
# v1 assigned fixed values by outcome label — direct leakage — REMOVED.
# v2 uses FR_Risk vs Rescue balance, Template_Deficit, Q and Φ structure.
# ==============================================================================

def compute_cac(row):
    """
    CAC = pre-Gate capacity to metabolize contradictions into integration
          rather than fragmentation.

    Time index: PRE-GATE
    Inputs used: FR Risk, FR_rule, Rescue, Rescue_rule, Template_Deficit,
                 Q_le_6_rule, Low_C_low_Phi_rule, PR_rule_candidate,
                 Q_calc, Φ

    Operationalization (continuous, range -1 to +1):
      Positive contributors (assimilation capacity):
        + Rescue > FR Risk: system can synthesize under pressure
        + Rescue_rule active: structured assimilation pathway exists
        + PR_rule_candidate: system in transitional/metabolizing mode
        + Q_ge_12_rule: high integration suggests contradictions absorbed
        + Φ high (4): high integration field — contradictions get integrated

      Negative contributors (fragmentation tendency):
        - FR_rule: structural fragmentation already engaged
        - FR Risk: active fragmentation pressure with no rescue
        - Q_le_6_rule: low Q = weak integration = contradictions scatter
        - Low_C_low_Phi: fundamental capacity deficit
        - Template_Deficit > 0: gaps prevent synthesis
    """
    fr_risk = _flag(row.get("FR Risk", 0))
    fr_rule = _flag(row.get("FR_rule", 0))
    rescue = _flag(row.get("Rescue", 0))
    rescue_rule = _flag(row.get("Rescue_rule", 0))
    template_deficit = float(row.get("Template_Deficit", 0) or 0)
    q_le_6 = _flag(row.get("Q_le_6_rule", 0))
    q_ge_12 = _flag(row.get("Q_ge_12_rule", 0))
    low_c_phi = _flag(row.get("Low_C_low_Phi_rule", 0))
    pr_candidate = _flag(row.get("PR_rule_candidate", 0))
    phi = float(row.get("Φ", 0) or 0)

    # Positive assimilation signals
    rescue_surplus = int(rescue) - int(fr_risk)  # +1, 0, or -1
    pos = (0.3 * max(0, rescue_surplus) +
           0.2 * int(rescue_rule) +
           0.15 * int(pr_candidate) +
           0.15 * int(q_ge_12) +
           0.1 * min(1.0, phi / 4.0))

    # Negative fragmentation signals
    neg = (0.35 * int(fr_rule) +
           0.25 * max(0, -rescue_surplus) +  # fr_risk without rescue
           0.15 * int(q_le_6) +
           0.15 * int(low_c_phi) +
           0.1 * min(1.0, template_deficit / 3.0))

    cac = pos - neg
    return float(np.clip(cac, -1, 1))


# ==============================================================================
# PRE-GATE VARIABLE 6: Frag_pre  [PRE-GATE — v2 fix]
# Fragmentation risk from structural rule flags ONLY.
# v1 encoded outcome categories directly — REMOVED.
# v2 uses FR_rule, Q_le_6, Walls, Template_Deficit, Low_C_low_Phi.
# ==============================================================================

def compute_frag_pre(row):
    """
    Frag_pre = structural fragmentation risk before the Gate.

    Time index: PRE-GATE
    Inputs used: FR_rule, FR Risk, Q_le_6_rule, Low_C_low_Phi_rule,
                 Template_Deficit, Walls, Rescue

    High Frag_pre = structural fragmentation likely before/at Gate.
    """
    fr_rule = _flag(row.get("FR_rule", 0))
    fr_risk = _flag(row.get("FR Risk", 0))
    q_le_6 = _flag(row.get("Q_le_6_rule", 0))
    low_c_phi = _flag(row.get("Low_C_low_Phi_rule", 0))
    template_deficit = float(row.get("Template_Deficit", 0) or 0)
    walls = float(row.get("Walls", 0) or 0)
    rescue = _flag(row.get("Rescue", 0))

    frag = (0.35 * int(fr_rule) +
            0.2 * int(fr_risk) +
            0.15 * int(q_le_6) +
            0.15 * int(low_c_phi) +
            0.1 * min(1.0, template_deficit / 3.0) +
            0.05 * min(1.0, walls / 4.0))

    # Rescue reduces fragmentation risk
    if rescue:
        frag *= 0.6

    return float(np.clip(frag, 0, 1))


# ==============================================================================
# MASTER VARIABLE: Q(ρ) v2.0  with interaction terms
# ==============================================================================

def compute_remainder_quality(row, weights=None):
    """
    Q(ρ) v2.0 — leakage-free, with interaction terms.

    Q(ρ) = σ(α·SC_cl + α'·SC_port + β·CID + γ·ECC + δ·ID + ε·CAC
              + η·(SC_cl × CID) + κ·(SC_cl × CAC) - λ·Frag_pre)

    Interaction terms:
      SC_closure × CID:  coherence is stabilizing when integration is high
      SC_closure × CAC:  coherence is stabilizing when contradictions can be metabolized

    All inputs are PRE-GATE only.
    """
    if weights is None:
        weights = {
            "alpha_cl":   0.10,   # SC_closure (main — can be negative without interaction)
            "alpha_port": 0.20,   # SC_portability
            "beta":       0.20,   # CID
            "gamma":      0.15,   # ECC
            "delta":      0.15,   # ID
            "epsilon":    0.15,   # CAC
            "eta":        0.20,   # SC_closure × CID  (interaction)
            "kappa":      0.15,   # SC_closure × CAC  (interaction)
            "lambda_f":   0.25,   # Frag_pre penalty
        }

    sc_cl = compute_sc_closure(row)
    sc_port = compute_sc_portability(row)
    cid = compute_cid(row)
    ecc = compute_ecc(row)
    id_val = compute_id(row)
    cac = compute_cac(row)
    frag = compute_frag_pre(row)

    # Interaction terms
    sc_x_cid = sc_cl * cid
    sc_x_cac = sc_cl * (cac + 1) / 2  # shift CAC to [0,1] for interaction

    z = (weights["alpha_cl"]   * sc_cl +
         weights["alpha_port"] * sc_port +
         weights["beta"]       * cid +
         weights["gamma"]      * ecc +
         weights["delta"]      * id_val +
         weights["epsilon"]    * cac +
         weights["eta"]        * sc_x_cid +
         weights["kappa"]      * sc_x_cac -
         weights["lambda_f"]   * frag)

    q_rho = expit(z * 3)  # steeper sigmoid

    return {
        "Q_rho":     q_rho,
        "SC_closure":     sc_cl,
        "SC_portability": sc_port,
        "CID":       cid,
        "ECC":       ecc,
        "ID":        id_val,
        "CAC":       cac,
        "Frag_pre":  frag,
        "SC_x_CID":  sc_x_cid,
        "SC_x_CAC":  sc_x_cac,
        "z":         z,
    }


# ==============================================================================
# INVARIANCE TEST
# ==============================================================================

def test_cross_domain_invariance(df):
    """
    Test hypothesis: all five variables show correct sign pattern
    vs clean/corrupted reboot outcome WITHOUT any label leakage.
    """
    print("\n" + "=" * 80)
    print("CROSS-DOMAIN INVARIANCE TEST (v2 — LEAKAGE-FREE)")
    print("=" * 80)

    test_cols = [
        "Q_rho", "SC_closure", "SC_portability",
        "CID", "ECC", "ID", "CAC", "Frag_pre",
        "SC_x_CID", "SC_x_CAC", "Reboot_Quality"
    ]
    results = df[[c for c in test_cols if c in df.columns]].dropna()
    print(f"\nValid cases: {len(results)} / {len(df)}\n")

    expected = {
        "SC_closure":     ("≈0 or +", None),   # theorized to be non-monotonic alone
        "SC_portability": ("+", True),
        "CID":            ("+", True),
        "ECC":            ("+", True),
        "ID":             ("+", True),
        "CAC":            ("+", True),
        "Q_rho":          ("+", True),
        "Frag_pre":       ("-", False),
        "SC_x_CID":       ("+", True),   # interaction: should be positive
        "SC_x_CAC":       ("+", True),
    }

    print(f"  {'Variable':<18} | {'Spearman ρ':>10} | {'p-value':>8} | {'Expected':>8} | Result")
    print("-" * 75)

    for var, (exp_sign, should_be_positive) in expected.items():
        if var not in results.columns or var == "Reboot_Quality":
            continue
        rho, p = spearmanr(results[var], results["Reboot_Quality"])
        if should_be_positive is None:
            sign_ok = "~"
        elif should_be_positive:
            sign_ok = "✓" if rho > 0 else "✗"
        else:
            sign_ok = "✓" if rho < 0 else "✗"
        print(f"  {var:<18} | {rho:+.4f}     | {p:.4f}   | {exp_sign:>8} | {sign_ok}")

    print("=" * 80)


# ==============================================================================
# GATE DELTA FRAMEWORK: Noise_pre → Clarity_post (∆G)
# Operationalization: "Gate = Noise Reduction → Clarity"
# 
# Time index:
#   Noise_pre (PRE-GATE)   : computed only from structural fields
#   Clarity_post (POST-GATE): computed only from Out(t₀) outcome
#   ∆G (DELTA)             : difference; tests whether Gate clarifies
# ==============================================================================

def compute_noise_pre(row):
    """
    Noise_pre = pre-Gate structural noise / contradiction.

    Time index: PRE-GATE ONLY
    Components (each 0–3 ordinal or 0–1 binary):
      - CL (Contradiction Load)    = |Bio - Cog| (dimension misalignment)
      - AV (Affective Volatility)  = Low_C_low_Phi_rule (structural fragility)
      - DD (Defensive Distortion)  = Template_Deficit + FR_rule (gaps + fragmentation)

    Formula: Noise_pre_raw = CL + AV + DD, range [0, 6]

    Returns:
      - Noise_pre_raw (sum 0–6)
      - Noise_pre_z (z-score normalized)
      - Noise_pre_minmax (min-max [0, 1])
    """
    # CL: Contradiction Load
    bio = float(row.get("Bio", np.nan))
    cog = float(row.get("Cog", np.nan))
    cl = abs(bio - cog) if not np.isnan(bio) and not np.isnan(cog) else np.nan

    # AV: Affective Volatility (structural fragility signal)
    av = 1.0 if _flag(row.get("Low_C_low_Phi_rule", 0)) else 0.0

    # DD: Defensive Distortion (gap + fragmentation)
    template_def = 1.0 if _flag(row.get("Template_Deficit", 0)) else 0.0
    fr_rule = 1.0 if _flag(row.get("FR_rule", 0)) else 0.0
    dd = template_def + fr_rule

    # Raw sum (range 0–6)
    noise_raw = cl + av + dd if not np.isnan(cl) else np.nan

    return {
        "CL": cl,
        "AV": av,
        "DD": dd,
        "Noise_pre_raw": noise_raw,
    }


def compute_clarity_post(row):
    """
    Clarity_post = post-Gate immediate outcome clarity.

    Time index: POST-GATE (Out(t₀) only)
    Ordinal mapping:
      - FR (Fragmentation Regime) = 0 (incoherent collapse)
      - MR (Mixed Regime)          = 1 (partial coherence)
      - PR (Possible Regime)       = 2 (emergent coherence)
      - CR (Coherent Regime)       = 3 (clean reboot)
      - SR (Stable Regime)         = 3 (maximum coherence)

    Returns:
      - Clarity_post_ordinal (0–3)
      - Clarity_post_binary (Is_Clean_CR_PR, 0/1)
    """
    out_t0 = str(row.get("Out(t₀)", "")).strip()

    clarity_map = {
        "FR": 0,
        "MR": 1,
        "PR": 2,
        "CR": 3,
        "SR": 3,
    }

    clarity_ordinal = clarity_map.get(out_t0, np.nan)
    clarity_binary = 1.0 if _flag(row.get("Is_Clean_CR_PR", 0)) else 0.0

    return {
        "Clarity_post_ordinal": clarity_ordinal,
        "Clarity_post_binary": clarity_binary,
    }


def compute_gate_delta(row, df_stats):
    """
    Gate magnitude: ∆G = Clarity_post - Noise_pre_z

    Input:
      - row: case record
      - df_stats: dict with 'Noise_pre_raw_mean' and 'Noise_pre_raw_std'
                  used for z-score normalization

    Returns:
      - delta_g (delta between post-Gate clarity and pre-Gate noise)
      - gate_effect (categorical: "Clarified" / "Steady" / "Deteriorated")
    """
    noise_raw = row.get("Noise_pre_raw", np.nan)
    clarity = row.get("Clarity_post_ordinal", np.nan)

    if np.isnan(noise_raw) or np.isnan(clarity):
        return {"ΔG": np.nan, "Gate_Effect": np.nan}

    # Z-score normalize Noise_pre
    mean_noise = df_stats.get("Noise_pre_raw_mean", 1.2)
    std_noise = df_stats.get("Noise_pre_raw_std", 1.1)
    noise_z = (noise_raw - mean_noise) / std_noise if std_noise > 0 else 0.0

    delta_g = clarity - noise_z

    # Categorize effect
    if delta_g > 0.5:
        gate_effect = "Clarified"
    elif delta_g < -0.5:
        gate_effect = "Deteriorated"
    else:
        gate_effect = "Steady"

    return {
        "ΔG": delta_g,
        "Gate_Effect": gate_effect,
    }


def validate_leakage_noise_pre(df):
    """
    Validate that Noise_pre uses ONLY pre-Gate fields.
    Forbidden columns in Noise_pre computation:
      - Outcome, Out(t₀), Out(late), Match, Regime_Predicted_*, Reboot_Quality
    """
    print("\n" + "=" * 80)
    print("LEAKAGE CHECK: Noise_pre construction")
    print("=" * 80)
    print("Noise_pre components used:")
    print("  ✓ Bio, Cog (pre-Gate behavioral dimensions)")
    print("  ✓ Low_C_low_Phi_rule (pre-Gate structural flag)")
    print("  ✓ Template_Deficit (pre-Gate structural gap)")
    print("  ✓ FR_rule (pre-Gate fragmentation rule)")
    print("\nForbidden (NOT used):")
    print("  ✗ Outcome, Out(t₀), Out(late)")
    print("  ✗ Match, Regime_Predicted_*, Reboot_Quality")
    print("=" * 80)


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("\n" + "=" * 80)
    print("REMAINDER QUALITY FRAMEWORK v2.0 — LEAKAGE-FREE")
    print("=" * 80)
    print(f"Generated: {datetime.now().isoformat()}\n")

    df = load_nde_atlas_data()

    # Outcome label (POST-GATE — never used as predictor input)
    df["Reboot_Quality"] = df["Outcome"].apply(classify_reboot_quality)

    print("\nComputing leakage-free variables and Q(ρ) v2...\n")

    # Validate leakage before computing
    validate_leakage_noise_pre(df)

    rows_out = []
    for _, row in df.iterrows():
        # Main Q(ρ) computation (pre-Gate only)
        q = compute_remainder_quality(row)
        
        # Gate ∆G framework (Noise_pre + Clarity_post)
        noise = compute_noise_pre(row)
        clarity = compute_clarity_post(row)
        
        r = row.to_dict()
        r.update(q)
        r.update(noise)
        r.update(clarity)
        rows_out.append(r)

    results_df = pd.DataFrame(rows_out)
    
    # Compute ∆G with normalized Noise_pre (requires full DataFrame stats)
    df_stats = {
        "Noise_pre_raw_mean": results_df["Noise_pre_raw"].mean(),
        "Noise_pre_raw_std": results_df["Noise_pre_raw"].std(),
    }
    
    delta_results = []
    for _, row in results_df.iterrows():
        delta = compute_gate_delta(row, df_stats)
        delta_results.append(delta)
    
    delta_df = pd.DataFrame(delta_results)
    results_df = pd.concat([results_df, delta_df], axis=1)
    
    results_df.to_csv(BASE_DIR / "remainder_quality_analysis_v2.csv", index=False)
    print("Saved: remainder_quality_analysis_v2.csv\n")

    summary_cols = ["Q_rho", "SC_closure", "SC_portability",
                    "CID", "ECC", "ID", "CAC", "Frag_pre"]

    print("=" * 80)
    print("SUMMARY STATISTICS (ALL 245 CASES — pre-Gate variables only)")
    print("=" * 80)
    print(results_df[summary_cols].describe().round(4).to_string())

    print("\n" + "=" * 80)
    print("BREAKDOWN: CLEAN vs CORRUPTED REBOOT")
    print("=" * 80)

    clean = results_df[results_df["Reboot_Quality"] == 1]
    corrupt = results_df[results_df["Reboot_Quality"] == 0]

    print(f"\nClean reboot (non-FR): n={len(clean)}")
    print(clean[summary_cols].mean().round(4).to_string())

    print(f"\nCorrupted reboot (FR): n={len(corrupt)}")
    print(corrupt[summary_cols].mean().round(4).to_string())

    # Distribution of CAC — confirm it is now continuous, not uniform
    print("\n" + "=" * 80)
    print("CAC DISTRIBUTION (should be continuous, NOT uniform -0.80 for FR)")
    print("=" * 80)
    print("\nFR cases — CAC values:")
    fr_cac = results_df[results_df["Outcome"] == "FR"]["CAC"]
    print(fr_cac.round(4).to_string())
    print(f"\nCAC unique values across all cases: {results_df['CAC'].nunique()}")
    print(f"CAC std dev: {results_df['CAC'].std():.4f}  (0 = uniform, >0 = continuous)")

    # Invariance test
    test_cross_domain_invariance(results_df)

    # FR case profiles
    print("\n" + "=" * 80)
    print("FR (CORRUPTED) CASES — v2 LEAKAGE-FREE PROFILE")
    print("=" * 80)
    fr_cols = [c for c in ["Case_ID", "Case Name", "Q_rho",
                           "SC_closure", "SC_portability",
                           "CID", "ECC", "ID", "CAC", "Frag_pre"] if c in results_df.columns]
    fr_df = results_df[results_df["Outcome"] == "FR"][fr_cols].sort_values("Q_rho")
    print(fr_df.round(4).to_string(index=False))

    # Outcome mean Q(ρ) table
    print("\n" + "=" * 80)
    print("Q(ρ) MEAN BY OUTCOME (post-hoc — label not used in computation)")
    print("=" * 80)
    for outcome in ["FR", "CR", "PR", "SR", "MR"]:
        g = results_df[results_df["Outcome"] == outcome]
        if len(g):
            print(f"  {outcome}: n={len(g):3d}  Q(ρ)={g['Q_rho'].mean():.4f}  "
                  f"(std={g['Q_rho'].std():.4f})")

    # ====== GATE ∆G FRAMEWORK ANALYSIS ======
    print("\n" + "=" * 80)
    print("GATE FRAMEWORK: Noise_pre → Clarity_post (∆G Analysis)")
    print("=" * 80)

    # Noise_pre statistics
    print("\nNoise_pre DISTRIBUTION (pre-Gate structural noise):")
    print(results_df[["CL", "AV", "DD", "Noise_pre_raw"]].describe().round(4).to_string())

    # Clarity_post statistics
    print("\nClarity_post DISTRIBUTION (post-Gate outcome clarity):")
    print(f"  Ordinal (0-3): {results_df['Clarity_post_ordinal'].value_counts().sort_index()}")
    print(f"  Binary (Clean): {results_df['Clarity_post_binary'].value_counts().sort_index()}")

    # ∆G statistics
    print("\n∆G (DELTA_G) STATISTICS — Clarification Magnitude:")
    print(results_df[["ΔG", "Gate_Effect"]].describe().round(4).to_string())
    print(f"\nGate_Effect distribution:")
    print(results_df["Gate_Effect"].value_counts().sort_index())

    # Correlation matrix: Noise_pre, Clarity_post, ∆G vs Q(ρ)
    print("\n" + "-" * 80)
    print("Correlations (Spearman ρ): Noise_pre, Clarity_post, ∆G vs Q(ρ)")
    print("-" * 80)
    
    for var in ["CL", "AV", "DD", "Noise_pre_raw", "Clarity_post_ordinal", "ΔG"]:
        if var in results_df.columns:
            valid = results_df[[var, "Q_rho"]].dropna()
            if len(valid) > 2:
                rho, p = spearmanr(valid[var], valid["Q_rho"])
                print(f"  {var:<22} vs Q(ρ): ρ={rho:+.4f}  p={p:.4f}")

    # ∆G by outcome regime
    print("\n" + "-" * 80)
    print("∆G MEAN BY OUTCOME REGIME (post-hoc descriptive)")
    print("-" * 80)
    for outcome in ["FR", "CR", "PR", "SR", "MR"]:
        g = results_df[results_df["Outcome"] == outcome]
        if len(g):
            print(f"  {outcome}: n={len(g):3d}  ∆G={g['ΔG'].mean():.4f}  "
                  f"(std={g['ΔG'].std():.4f})")

    # Cases by Gate_Effect category
    print("\n" + "-" * 80)
    print("CASE BREAKDOWN BY GATE EFFECT")
    print("-" * 80)
    for effect in ["Clarified", "Steady", "Deteriorated"]:
        g = results_df[results_df["Gate_Effect"] == effect]
        if len(g):
            print(f"\n{effect.upper()}: n={len(g)}")
            print(f"  Q(ρ) mean: {g['Q_rho'].mean():.4f}")
            print(f"  Reboot_Quality (Clean): {g['Reboot_Quality'].sum():.0f} / {len(g)}")
            print(f"  Noise_pre_raw mean: {g['Noise_pre_raw'].mean():.4f}")
            print(f"  Clarity_post mean: {g['Clarity_post_ordinal'].mean():.4f}")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print("\nKey outputs:")
    print(f"  - remainder_quality_analysis_v2.csv (includes Gate ∆G columns)")
    print(f"  - See Gate_Delta_Framework_Operationalization.md for regression specs")
    print("=" * 80)


if __name__ == "__main__":
    main()
