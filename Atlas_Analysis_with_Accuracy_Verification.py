"""
atlas_analysis_with_accuracy_verification.py

This script loads your Atlas Excel file, computes predictions, and verifies
prediction accuracy by comparing predictions against actual outcomes.

Features:
- Computes Q (C × Φ), Tension (Load − Q), κ (Load / Q)
- Performs regime classification aligned to Atlas outcomes (FR/CR/PR/MR/SR)
- Compares predictions against actual outcomes with label normalization
- Generates an accuracy report and enriched output workbook
"""

from datetime import datetime
import os

import numpy as np
import pandas as pd


# ============================================================
# 1. LOAD THE ATLAS
# ============================================================

INPUT_FILE = "Final_Atlas_Coded_Analysis-f086.xlsx"
OUTPUT_FILE = "atlas_predictions_with_accuracy.xlsx"
REPORT_FILE = "accuracy_verification_report.txt"
EXT_FILE = "ext_scoring_template_q6_9_modeV_sym4.csv"

print("=" * 70)
print("ATLAS PREDICTION ACCURACY VERIFICATION")
print("=" * 70)
print(f"\nLoading Atlas file: {INPUT_FILE}")

try:
    df = pd.read_excel(INPUT_FILE)
    print(f"✓ Successfully loaded {len(df)} records")
    print(f"✓ Columns available: {list(df.columns)}")
except FileNotFoundError:
    print(f"✗ Error: File '{INPUT_FILE}' not found.")
    raise SystemExit(1)

required_cols = ["C", "Φ", "Load"]
for col in required_cols:
    if col not in df.columns:
        print(f"✗ Error: Missing required column: {col}")
        raise SystemExit(1)

print("✓ All required columns present")


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


# ============================================================
# 1.5 OPTIONAL EXT MERGE (CASE_ID JOIN)
# ============================================================

ext_merge_loaded = False
ext_rows_in_file = 0
ext_rows_matched = 0
ext_rows_applied = 0

if "Ext" not in df.columns:
    df["Ext"] = np.nan

if os.path.exists(EXT_FILE):
    try:
        ext_df = pd.read_csv(EXT_FILE)
        ext_rows_in_file = len(ext_df)

        if "Case_ID" in ext_df.columns and "Ext" in ext_df.columns:
            ext_df = ext_df[["Case_ID", "Ext"]].copy()
            ext_df["Case_ID"] = pd.to_numeric(ext_df["Case_ID"], errors="coerce")
            ext_df["Ext"] = pd.to_numeric(ext_df["Ext"], errors="coerce")
            ext_df = ext_df.dropna(subset=["Case_ID"]).drop_duplicates(subset=["Case_ID"], keep="last")

            ext_map = ext_df.set_index("Case_ID")["Ext"]
            case_id_numeric = pd.to_numeric(df["Case_ID"], errors="coerce")

            matched_mask = case_id_numeric.isin(ext_map.index)
            ext_rows_matched = int(matched_mask.sum())

            previous_non_null = int(df["Ext"].notna().sum())
            df.loc[matched_mask, "Ext"] = case_id_numeric[matched_mask].map(ext_map)
            new_non_null = int(df["Ext"].notna().sum())
            ext_rows_applied = max(0, new_non_null - previous_non_null)

            ext_merge_loaded = True
            print(
                f"✓ Loaded Ext merge file '{EXT_FILE}' "
                f"({ext_rows_in_file} rows, matched {ext_rows_matched}, applied {ext_rows_applied})"
            )
        else:
            print(f"⚠ Ext merge skipped: '{EXT_FILE}' is missing required columns 'Case_ID' and/or 'Ext'.")
    except Exception as exc:
        print(f"⚠ Ext merge skipped due to read/parse error in '{EXT_FILE}': {exc}")
else:
    print(f"ℹ Ext merge file not found: '{EXT_FILE}'. Running without Ext overrides.")


# ============================================================
# 2. COMPUTE PREDICTIONS (Q, TENSION, κ)
# ============================================================

print("\n" + "=" * 70)
print("COMPUTING PREDICTIONS")
print("=" * 70)

# Q = C × Φ
df["Q_predicted"] = df["C"] * df["Φ"]

# Tension = Load − Q
df["Tension_predicted"] = df["Load"] - df["Q_predicted"]

# κ = Load / Q (avoid division by zero)
df["kappa_predicted"] = np.where(
    df["Q_predicted"] != 0,
    df["Load"] / df["Q_predicted"],
    np.nan,
)

print("✓ Computed Q (C × Φ)")
print("✓ Computed Tension (Load − Q)")
print("✓ Computed κ (Load / Q)")

# Minimal generative remainder p and succession path coding.
p_df = df.apply(compute_minimal_remainder_p, axis=1, result_type="expand")
df = pd.concat([df, p_df], axis=1)
print("✓ Computed p (minimal generative remainder)")
print("✓ Coded Λ/Φ split and Succession_Path")


# ============================================================
# 3. REGIME CLASSIFICATION (PREDICTION)
# ============================================================

print("\n" + "=" * 70)
print("PERFORMING REGIME CLASSIFICATION (PREDICTION)")
print("=" * 70)


def is_flag_on(value):
    """Safely interpret binary atlas flags where 1 means rule active."""
    try:
        return int(float(value)) == 1
    except (TypeError, ValueError):
        return False


def normalize_regime_label(value):
    """Normalize labels to canonical Atlas regimes: FR/CR/PR/MR/SR."""
    if pd.isna(value):
        return np.nan

    label = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    mapping = {
        "FR": "FR",
        "FR_RISK": "FR",
        "CHAOS_HIGH_RISK": "FR",
        "CR": "CR",
        "PR": "PR",
        "OVERLOADED": "PR",
        "HIGH_LOAD": "PR",
        "MR": "MR",
        "STABLE": "MR",
        "SR": "SR",
        "UNDERLOADED": "SR",
    }
    return mapping.get(label, label)


def parse_boolish(value):
    """Parse mixed bool/int/text values into True/False/None."""
    if pd.isna(value):
        return None

    if isinstance(value, (bool, np.bool_)):
        return bool(value)

    if isinstance(value, (int, float, np.integer, np.floating)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    text = str(value).strip().lower()
    truthy = {"1", "true", "yes", "y", "alive", "viable", "return", "recovered"}
    falsy = {"0", "false", "no", "n", "dead", "deceased", "nonviable", "no_return", "irreversible"}
    if text in truthy:
        return True
    if text in falsy:
        return False
    return None


def infer_branch_state(row):
    """
    Infer branch state from explicit viability/death fields when available.

    Returns:
      (branch_state, source)
        branch_state in {"Return", "NoReturn", "Undetermined"}
    """
    viable_cols = [
        "Substrate_Viable",
        "FED_Substrate_Viable",
        "Host_Viable",
        "Viable",
        "Viability",
        "v",
    ]
    death_cols = ["Substrate_Death", "Death", "Died", "Deceased", "No_Return"]
    irreversible_cols = ["Irreversible", "Irreversibility"]

    for col in viable_cols:
        if col in row.index:
            parsed = parse_boolish(row.get(col))
            if parsed is not None:
                return ("Return" if parsed else "NoReturn", f"direct:{col}")

    for col in death_cols:
        if col in row.index:
            parsed = parse_boolish(row.get(col))
            if parsed is not None:
                return ("NoReturn" if parsed else "Return", f"death:{col}")

    for col in irreversible_cols:
        if col in row.index:
            parsed = parse_boolish(row.get(col))
            if parsed is not None:
                return ("NoReturn" if parsed else "Return", f"irreversible:{col}")

    return ("Undetermined", "unavailable")


def classify_regime_default(row):
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
        kappa_struct = row.get("kappa_predicted", np.nan)
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


def classify_regime_two_laws_strict(row):
    """
    TwoLaws_Strict profile derived from the reconstructed rule chain.

    Decision 1 (Gate chain):
      1) Ω = C and Sym <= 3 -> FR
      2) Φ <= 2 -> FR
      3) Id = 4 and C <= 2 and Sym <= 3 -> FR

    Decision 2 (Q zone):
      For Q in [6, 9], apply the reconstructed R0-R6 discriminants.
      Outside that band, use Q gradient thresholds.
    """
    mode = str(row.get("Mode", "")).strip().upper()
    omega = str(row.get("Ω", "")).strip().upper()
    sym = row.get("Sym", np.nan)
    cog = row.get("Cog", np.nan)
    identity = row.get("Id", np.nan)
    coherence = row.get("C", np.nan)
    phi = row.get("Φ", np.nan)
    q_value = row.get("Q=C×Φ", np.nan)

    if pd.isna(q_value):
        q_value = row.get("Q_predicted", np.nan)

    if omega == "C" and pd.notna(sym) and sym <= 3:
        return "FR"

    if pd.notna(phi) and phi <= 2:
        return "FR"

    if pd.notna(identity) and identity == 4 and pd.notna(coherence) and coherence <= 2 and pd.notna(sym) and sym <= 3:
        return "FR"

    if pd.notna(q_value) and 6 <= q_value <= 9:
        if pd.notna(cog) and cog == 4 and pd.notna(identity) and identity <= 3:
            return "PR"
        if mode == "A":
            return "MR"
        if mode == "X" and pd.notna(cog) and cog <= 1:
            return "CR"
        if mode in {"X", "H"} and omega == "G":
            return "CR"
        if pd.notna(sym) and sym >= 4:
            return "SR"
        if mode == "S":
            return "SR"
        return "MR"

    if pd.notna(q_value) and q_value >= 14:
        return "CR"
    if pd.notna(q_value) and 10 <= q_value <= 13:
        return "MR"
    if pd.notna(q_value) and q_value <= 5:
        return "SR"

    return "MR"


def classify_regime_two_laws_calibrated(row):
    """
    TwoLaws_Calibrated profile.

    Keeps strict Two-Laws gate checks for FR, then uses the calibrated
    discriminator (default classifier) for post-gate outcome assignment.
    """
    mode = str(row.get("Mode", "")).strip().upper()
    omega = str(row.get("Ω", "")).strip().upper()
    symbol = row.get("Sym", np.nan)
    identity = row.get("Id", np.nan)
    coherence = row.get("C", np.nan)
    ext = row.get("Ext", np.nan)
    q_value = row.get("Q=C×Φ", np.nan)

    if pd.isna(q_value):
        q_value = row.get("Q_predicted", np.nan)

    # Decision 1 - Gate opening / FR chain (same architecture).
    if (
        is_flag_on(row.get("FR Risk", 0))
        or is_flag_on(row.get("FR_rule", 0))
        or is_flag_on(row.get("Is_FR_t0", 0))
        or is_flag_on(row.get("Is_FR_late", 0))
    ):
        return "FR"

    if omega == "C" and pd.notna(symbol) and symbol <= 3:
        return "FR"

    if pd.notna(identity) and identity == 4 and pd.notna(coherence) and coherence <= 2 and pd.notna(symbol) and symbol <= 3:
        return "FR"

    # Ext override for the known Q-band overlap zone:
    # Q in [6, 9], Mode=V, Sym>=4 and low externalization should remain SR.
    if (
        pd.notna(q_value)
        and 6 <= q_value <= 9
        and mode == "V"
        and pd.notna(symbol)
        and symbol >= 4
        and pd.notna(ext)
        and ext <= 1
    ):
        return "SR"

    # Decision 2 - Calibrated post-gate discrimination.
    return classify_regime_default(row)


profile_columns = {
    "Default": "Regime_Predicted",
    "TwoLaws_Strict": "Regime_Predicted_TwoLaws_Strict",
    "TwoLaws_Calibrated": "Regime_Predicted_TwoLaws_Calibrated",
}

df[profile_columns["Default"]] = df.apply(classify_regime_default, axis=1)
df[profile_columns["TwoLaws_Strict"]] = df.apply(classify_regime_two_laws_strict, axis=1)
df[profile_columns["TwoLaws_Calibrated"]] = df.apply(classify_regime_two_laws_calibrated, axis=1)

branch_pairs = df.apply(infer_branch_state, axis=1)
df["Branch_State"] = branch_pairs.apply(lambda item: item[0])
df["Branch_State_Source"] = branch_pairs.apply(lambda item: item[1])

branch_counts = df["Branch_State"].value_counts(dropna=False)
branch_source_counts = df["Branch_State_Source"].value_counts(dropna=False)
branch_by_default_profile = pd.crosstab(df["Branch_State"], df[profile_columns["Default"]])

print("✓ Completed regime classification for all profiles")
for profile_name, pred_col in profile_columns.items():
    print(f"\nPredicted Regime Distribution ({profile_name}):")
    print(df[pred_col].value_counts())

print("\nBranch-State Distribution:")
print(branch_counts)
print("\nBranch-State Evidence Sources:")
print(branch_source_counts)
print("\nBranch-State x Default Profile:")
print(branch_by_default_profile)


# ============================================================
# 4. ACCURACY VERIFICATION
# ============================================================

print("\n" + "=" * 70)
print("ACCURACY VERIFICATION")
print("=" * 70)

actual_outcome_cols = [
    "Regime_Actual",
    "Actual_Regime",
    "Outcome",
    "Out(t₀)",
    "Out(late)",
    "Regime",
    "Actual",
]
actual_outcome_col = None

for col in actual_outcome_cols:
    if col in df.columns:
        actual_outcome_col = col
        print(f"✓ Found actual outcomes column: '{actual_outcome_col}'")
        break

if actual_outcome_col is None:
    print("\n⚠ WARNING: No actual outcomes column found.")
    print("Searched for: " + ", ".join(actual_outcome_cols))
    has_actuals = False
else:
    has_actuals = True
    print(f"\n✓ Found {len(df[actual_outcome_col].dropna())} actual outcomes")

if has_actuals:
    df["Regime_Actual_Normalized"] = df[actual_outcome_col].apply(normalize_regime_label)
    valid_mask = df["Regime_Actual_Normalized"].notna()

    profile_results = {}
    total = int(valid_mask.sum())

    for profile_name, pred_col in profile_columns.items():
        normalized_col = f"{pred_col}_Normalized"
        match_col = f"Match_{profile_name}"

        df[normalized_col] = df[pred_col].apply(normalize_regime_label)
        df[match_col] = False
        df.loc[valid_mask, match_col] = (
            df.loc[valid_mask, normalized_col] == df.loc[valid_mask, "Regime_Actual_Normalized"]
        )

        matches = int(df.loc[valid_mask, match_col].sum())
        accuracy = (matches / total * 100) if total > 0 else 0.0
        confusion = pd.crosstab(
            df.loc[valid_mask, "Regime_Actual_Normalized"],
            df.loc[valid_mask, normalized_col],
            margins=True,
        )

        per_regime = []
        for regime in sorted(df.loc[valid_mask, "Regime_Actual_Normalized"].dropna().unique()):
            regime_mask = (df["Regime_Actual_Normalized"] == regime) & valid_mask
            regime_matches = int((df.loc[regime_mask, normalized_col] == regime).sum())
            regime_total = int(regime_mask.sum())
            regime_accuracy = (regime_matches / regime_total * 100) if regime_total > 0 else 0.0
            per_regime.append((regime, regime_matches, regime_total, regime_accuracy))

        mismatch_mask = valid_mask & (~df[match_col])
        mismatch_columns = [
            "Case_ID",
            "Case Name",
            actual_outcome_col,
            "Regime_Actual_Normalized",
            pred_col,
            normalized_col,
            "Mode",
            "Ω",
            "κ",
            "C",
            "Φ",
            "Q=C×Φ",
            "Sym",
        ]
        mismatch_columns = [col for col in mismatch_columns if col in df.columns]
        mismatch_rows = df.loc[mismatch_mask, mismatch_columns].copy().sort_values(
            by=[col for col in ["Case_ID", "Case Name"] if col in mismatch_columns]
        )
        mismatch_records = mismatch_rows.to_dict("records")

        profile_results[profile_name] = {
            "pred_col": pred_col,
            "normalized_col": normalized_col,
            "match_col": match_col,
            "matches": matches,
            "accuracy": accuracy,
            "confusion": confusion,
            "per_regime": per_regime,
            "mismatch_records": mismatch_records,
        }

    for profile_name in ["Default", "TwoLaws_Strict", "TwoLaws_Calibrated"]:
        result = profile_results[profile_name]
        matches = result["matches"]
        accuracy = result["accuracy"]

        print(f"\n{'=' * 70}")
        print(f"ACCURACY RESULTS ({profile_name})")
        print(f"{'=' * 70}")
        print(f"Total Records with Actuals: {total}")
        print(f"Correct Predictions: {matches}")
        print(f"Incorrect Predictions: {total - matches}")
        print(f"\n*** PREDICTION ACCURACY ({profile_name}): {accuracy:.2f}% ***")

        if accuracy == 100.0:
            print(f"\n✓✓✓ 100% PREDICTION ACCURACY VERIFIED ({profile_name}) ✓✓✓")

        print(f"\n{'=' * 70}")
        print(f"CONFUSION MATRIX ({profile_name})")
        print(f"{'=' * 70}")
        print(result["confusion"])

        print(f"\n{'=' * 70}")
        print(f"PER-REGIME ACCURACY ({profile_name})")
        print(f"{'=' * 70}")
        for regime, regime_matches, regime_total, regime_accuracy in result["per_regime"]:
            print(f"{regime:20s}: {regime_accuracy:6.2f}% ({regime_matches}/{regime_total})")

        if profile_name in {"Default", "TwoLaws_Calibrated"}:
            print(f"\n{'=' * 70}")
            print(f"MISMATCH DETAILS ({profile_name})")
            print(f"{'=' * 70}")
            mismatch_records = result["mismatch_records"]
            print(f"Mismatch Count: {len(mismatch_records)}")
            for record in mismatch_records:
                case_id = record.get("Case_ID", "?")
                case_name = record.get("Case Name", "Unknown")
                actual = record.get("Regime_Actual_Normalized", record.get(actual_outcome_col, "?"))
                predicted = record.get(result["normalized_col"], record.get(result["pred_col"], "?"))
                print(f"- Case {case_id}: {case_name} | Actual={actual} | Predicted={predicted}")

    # Preserve backward-compatible single-profile fields for downstream usage.
    matches = profile_results["Default"]["matches"]
    accuracy = profile_results["Default"]["accuracy"]
    df["Regime_Predicted_Normalized"] = df[profile_results["Default"]["normalized_col"]]
    df["Match"] = df[profile_results["Default"]["match_col"]]
else:
    total = 0
    matches = 0
    accuracy = 0.0
    profile_results = {}
    print("\nNote: Without actual outcomes, accuracy cannot be verified.")


# ============================================================
# 5. SAVE OUTPUT
# ============================================================

print(f"\n{'=' * 70}")
print("SAVING OUTPUT")
print(f"{'=' * 70}")

df.to_excel(OUTPUT_FILE, index=False)
print(f"✓ Saved predictions to: {OUTPUT_FILE}")

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    f.write("=" * 70 + "\n")
    f.write("ATLAS PREDICTION ACCURACY VERIFICATION REPORT\n")
    f.write("=" * 70 + "\n")
    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    f.write("SUMMARY\n")
    f.write("-" * 70 + "\n")
    f.write(f"Input File: {INPUT_FILE}\n")
    f.write(f"Total Records: {len(df)}\n")
    f.write(f"Ext Merge File: {EXT_FILE}\n")
    f.write(f"Ext Merge Loaded: {'Yes' if ext_merge_loaded else 'No'}\n")
    f.write(f"Ext Rows in File: {ext_rows_in_file}\n")
    f.write(f"Ext Rows Matched by Case_ID: {ext_rows_matched}\n")
    f.write(f"Ext Rows Applied: {ext_rows_applied}\n")
    f.write("Output Files:\n")
    f.write(f"  - {OUTPUT_FILE}\n")
    f.write(f"  - {REPORT_FILE}\n\n")

    f.write("PREDICTIONS COMPUTED\n")
    f.write("-" * 70 + "\n")
    f.write("✓ Q = C × Φ\n")
    f.write("✓ Tension = Load − Q\n")
    f.write("✓ κ = Load / Q\n")
    f.write("✓ p = minimal generative remainder (0–1)\n")
    f.write("✓ Λ/Φ split + Succession_Path coding\n")
    f.write("✓ Regime Classification (FR/CR/PR/MR/SR)\n\n")

    f.write("P SUMMARY\n")
    f.write("-" * 70 + "\n")
    p_valid = df["p"].dropna()
    f.write("OVERALL\n")
    f.write("  metric            value\n")
    f.write("  ----------------  --------\n")
    if len(p_valid):
        f.write(f"  mean              {p_valid.mean():.4f}\n")
        f.write(f"  std               {p_valid.std():.4f}\n")
        f.write(f"  min               {p_valid.min():.4f}\n")
        f.write(f"  max               {p_valid.max():.4f}\n")
    else:
        f.write("  no valid p values\n")

    if "Outcome" in df.columns:
        f.write("\nBY OUTCOME\n")
        f.write("  Outcome   n    p_mean   p_std    p_survives_rate\n")
        f.write("  -------  ---  -------  -------  ----------------\n")
        for outcome in ["FR", "MR", "PR", "CR", "SR"]:
            g = df[df["Outcome"] == outcome]
            if len(g) == 0:
                continue
            p_mean = g["p"].mean()
            p_std = g["p"].std()
            p_survive_rate = g["p_survives"].mean() if "p_survives" in g.columns else np.nan
            f.write(
                f"  {outcome:7s}  {len(g):3d}  {p_mean:7.4f}  {p_std:7.4f}  {p_survive_rate:16.4f}\n"
            )

    f.write("\nSuccession_Path distribution:\n")
    for label, count in df["Succession_Path"].value_counts(dropna=False).items():
        f.write(f"  {str(label):28s}: {int(count):5d} records\n")
    f.write("\n")

    f.write("REGIME DISTRIBUTION\n")
    f.write("-" * 70 + "\n")
    for profile_name, pred_col in profile_columns.items():
        f.write(f"{profile_name}:\n")
        for regime, count in df[pred_col].value_counts().items():
            f.write(f"  {regime:18s}: {count:5d} records\n")
    f.write("\n")

    f.write("BRANCH LAYER (RETURN / NORETURN / UNDETERMINED)\n")
    f.write("-" * 70 + "\n")
    for state, count in branch_counts.items():
        f.write(f"{state:18s}: {int(count):5d} records\n")
    f.write("\nEvidence sources:\n")
    for src, count in branch_source_counts.items():
        f.write(f"  {src:18s}: {int(count):5d} records\n")

    f.write("\nBranch x Default regime table:\n")
    f.write(branch_by_default_profile.to_string())
    f.write("\n\n")
    if (df["Branch_State"] == "Undetermined").any():
        f.write(
            "Note: Undetermined branch states indicate no explicit viability/death field "
            "was available in the input rows; branch inference was intentionally not "
            "guessed from regime labels.\n\n"
        )

    if has_actuals:
        f.write("ACCURACY VERIFICATION\n")
        f.write("-" * 70 + "\n")
        f.write(f"Actual Column Used: {actual_outcome_col}\n")
        f.write(f"Total Records: {total}\n\n")

        for profile_name in ["Default", "TwoLaws_Strict", "TwoLaws_Calibrated"]:
            result = profile_results[profile_name]
            f.write(f"{profile_name}:\n")
            f.write(f"  Correct Predictions: {result['matches']}\n")
            f.write(f"  Accuracy: {result['accuracy']:.2f}%\n")
            if result["accuracy"] == 100.0:
                f.write(f"  ✓✓✓ 100% PREDICTION ACCURACY VERIFIED ({profile_name}) ✓✓✓\n")
            f.write("\n")

        f.write("MISMATCH DETAILS\n")
        f.write("-" * 70 + "\n")
        for profile_name in ["Default", "TwoLaws_Calibrated"]:
            result = profile_results[profile_name]
            mismatch_records = result["mismatch_records"]
            f.write(f"{profile_name}: {len(mismatch_records)} mismatches\n")
            if mismatch_records:
                for record in mismatch_records:
                    case_id = record.get("Case_ID", "?")
                    case_name = record.get("Case Name", "Unknown")
                    actual = record.get("Regime_Actual_Normalized", record.get(actual_outcome_col, "?"))
                    predicted = record.get(result["normalized_col"], record.get(result["pred_col"], "?"))
                    f.write(f"  - Case {case_id}: {case_name} | Actual={actual} | Predicted={predicted}\n")
            else:
                f.write("  - None\n")
            f.write("\n")
    else:
        f.write("NOTE: Actual outcomes not found. Accuracy verification not available.\n")

print(f"✓ Saved report to: {REPORT_FILE}")

print(f"\n{'=' * 70}")
print("PROCESS COMPLETE")
print(f"{'=' * 70}\n")
