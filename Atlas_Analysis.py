"""
atlas_analysis.py

This script loads your Atlas Excel file, computes:
- Q (C × Φ)
- Tension (Load − Q)
- κ (Load / Q)
- Regime classification aligned to Atlas outcome codes (FR/CR/PR/MR/SR)

Then it saves a new enriched Excel file.

To use:
1. Place this file in the same folder as your Excel file:
       Final_Atlas_Coded_Analysis-f086.xlsx
2. Run:
       python Atlas_Analysis.py
3. Output will be saved as:
       atlas_analysis_output.xlsx
"""

from pathlib import Path

import numpy as np
import pandas as pd


# ------------------------------------------------------------
# 1. LOAD THE ATLAS
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "Final_Atlas_Coded_Analysis-f086.xlsx"
OUTPUT_FILE = BASE_DIR / "atlas_analysis_output.xlsx"

# Load the Excel file into a DataFrame
df = pd.read_excel(INPUT_FILE)

# Check that required columns exist
required_cols = ["C", "Φ", "Load"]
for col in required_cols:
    if col not in df.columns:
        raise ValueError(f"Missing required column: {col}")


# ------------------------------------------------------------
# 2. COMPUTE Q, TENSION, κ
# ------------------------------------------------------------


def _safe_float(value, default=np.nan):
    """Best-effort numeric cast that keeps NaN semantics stable."""
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_flag(value):
    """Interpret mixed numeric/text rule flags as 0/1."""
    try:
        return 1.0 if int(float(value)) == 1 else 0.0
    except (TypeError, ValueError):
        return 0.0


def compute_minimal_remainder_p(row):
    """
    Operationalize minimal generative remainder p in [0, 1].

        Concept mapping (strict successor-minimum):
            - Λ/Φ split signal: contradiction pressure where Load > Q
            - Survival carrier: minimal structural rescue capacity
            - Fragility drag: structural gaps/fragmentation

        Note:
            p-score intentionally excludes direct coherence/identity carryover terms
            (e.g., Q ratio, C, Φ) so p reflects minimal survivable organization,
            not persistence of prior identity.

    Returns dict for direct DataFrame expansion.
    """
    c = _safe_float(row.get("C", np.nan))
    phi = _safe_float(row.get("Φ", np.nan))
    load = _safe_float(row.get("Load", np.nan))

    if np.isnan(c) or np.isnan(phi) or np.isnan(load):
        return {
            "Lambda_Phi_Split": np.nan,
            "p": np.nan,
            "p_survives": np.nan,
            "Succession_Path": np.nan,
        }

    q = c * phi
    contradiction = max(0.0, load - q)
    contradiction_norm = np.clip(contradiction / max(load, 1.0), 0.0, 1.0)
    template_deficit = _safe_flag(row.get("Template_Deficit", 0))
    fr_rule = _safe_flag(row.get("FR_rule", 0))
    low_c_low_phi = _safe_flag(row.get("Low_C_low_Phi_rule", 0))

    rescue_signal = max(
        _safe_flag(row.get("Rescue", 0)),
        _safe_flag(row.get("Rescue_rule", 0)),
    )

    # Minimal surviving scaffold under collapse pressure.
    survival_capacity = np.clip(
        0.55 * rescue_signal
        + 0.25 * (1.0 - template_deficit)
        + 0.20 * (1.0 - fr_rule),
        0.0,
        1.0,
    )

    fragility = np.clip(
        0.45 * template_deficit + 0.35 * fr_rule + 0.20 * low_c_low_phi,
        0.0,
        1.0,
    )

    # Weighted score, then sigmoid to keep p bounded and smooth.
    p_score = (
        1.10 * survival_capacity
        - 1.10 * contradiction_norm
        - 0.85 * fragility
    )
    p_value = 1.0 / (1.0 + np.exp(-2.0 * p_score))

    split = 1.0 if contradiction > 0 else 0.0
    p_survives = 1.0 if (split == 1.0 and p_value >= 0.55) else 0.0

    if split == 0.0:
        succession_path = "No_Collapse_Basin"
    elif p_value >= 0.65:
        succession_path = "Succession_Potential"
    elif p_value >= 0.45:
        succession_path = "Residual_Continuity_Risk"
    else:
        succession_path = "Debris_or_Zombie_Continuity"

    return {
        "Lambda_Phi_Split": split,
        "p": float(np.clip(p_value, 0.0, 1.0)),
        "p_survives": p_survives,
        "Succession_Path": succession_path,
    }

# Q = C × Φ
df["Q_calc_python"] = df["C"] * df["Φ"]

# Tension = Load − Q
df["Tension_python"] = df["Load"] - df["Q_calc_python"]

# κ = Load / Q  (avoid division by zero)
df["kappa_python"] = np.where(
    df["Q_calc_python"] != 0,
    df["Load"] / df["Q_calc_python"],
    np.nan,
)

# Minimal generative remainder p and path annotation.
p_df = df.apply(compute_minimal_remainder_p, axis=1, result_type="expand")
df = pd.concat([df, p_df], axis=1)


# ------------------------------------------------------------
# 3. REGIME CLASSIFICATION (ATLAS-ALIGNED)
# ------------------------------------------------------------

def is_flag_on(value):
    """Safely interpret binary atlas flags where 1 means rule active."""
    try:
        return int(float(value)) == 1
    except (TypeError, ValueError):
        return False


def classify_regime(row):
    """
    Classify to Atlas outcome regimes:
      FR, CR, PR, MR, SR

    Priority:
    1) FR flags
    2) CR flag
    3) PR flag
    4) SR/MR split using calibrated signatures plus tie-break rules
    """
    mode = str(row.get("Mode", "")).strip().upper()
    omega = str(row.get("Ω", "")).strip().upper()
    kappa_struct = row.get("κ", np.nan)
    if pd.isna(kappa_struct):
        kappa_struct = row.get("kappa_python", np.nan)
    kappa_key = round(float(kappa_struct), 2) if pd.notna(kappa_struct) else None
    bio = row.get("Bio", np.nan)
    env = row.get("Env", np.nan)
    cog = row.get("Cog", np.nan)
    identity = row.get("Id", np.nan)
    symbol = row.get("Sym", np.nan)
    load = row.get("Load", np.nan)
    tension = row.get("Tension", np.nan)

    # Signatures where SR is dominant in the coded atlas.
    sr_signatures = {
        ("V", "J", 0.56),
        ("S", "L", 0.75),
        ("D", "G", 1.00),
        ("T", "L", 0.75),
        ("S", "L", 1.00),
        ("V", "B", 0.75),
        ("V", "B", 0.56),
        ("V", "L", 0.38),
        ("V", "L", 0.56),
        ("V", "L", 0.75),
        ("S", "J", 0.56),
        ("X", "L", 0.75),
        ("S", "J", 0.38),
        ("H", "G", 0.56),
        ("T", "J", 0.56),
        ("S", "C", 0.25),
        ("S", "L", 0.25),
        ("S", "B", 0.56),
        ("N", "L", 1.00),
        ("S", "L", 0.38),
        ("V", "B", 1.00),
        ("X", "J", 0.56),
        ("X", "L", 0.56),
    }

    if (
        is_flag_on(row.get("FR Risk", 0))
        or is_flag_on(row.get("FR_rule", 0))
        or is_flag_on(row.get("Is_FR_t0", 0))
        or is_flag_on(row.get("Is_FR_late", 0))
        or mode == "C"
    ):
        return "FR"

    if is_flag_on(row.get("Is_CR_t0", 0)):
        return "CR"

    if is_flag_on(row.get("Is_PR_t0", 0)):
        return "PR"

    # Disambiguate the remaining MR/SR boundary where coarse signatures overlap.
    if (mode, omega, kappa_key) == ("N", "L", 0.75):
        return "SR" if pd.notna(cog) and cog >= 3 else "MR"

    if (mode, omega, kappa_key) == ("V", "J", 0.75):
        return "SR" if cog == 3 else "MR"

    if (mode, omega, kappa_key) == ("N", "G", 1.00):
        return "SR" if (env == 2 and symbol == 4 and tension == 11) else "MR"

    if (mode, omega, kappa_key) == ("V", "B", 0.75):
        return "MR" if bio == 1 else "SR"

    if (mode, omega, kappa_key) == ("S", "L", 1.00):
        if cog == 3 and identity == 4 and symbol == 3 and load == 16:
            return "MR"
        return "SR"

    if (mode, omega, kappa_key) == ("V", "J", 0.56):
        if env in {1, 3}:
            return "SR"
        if env == 4:
            return "MR"
        if tension >= 12 and not (bio == 4 and cog == 3 and load == 17):
            return "SR"
        return "MR"

    if (mode, omega, kappa_key) in sr_signatures:
        return "SR"

    return "MR"


df["Regime_Class"] = df.apply(classify_regime, axis=1)


# ------------------------------------------------------------
# 4. SAVE OUTPUT
# ------------------------------------------------------------

df.to_excel(OUTPUT_FILE, index=False)
print(f"Analysis complete. Output saved to: {OUTPUT_FILE}")
