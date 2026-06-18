"""
atlas_analysis_with_accuracy_verification.py

This script loads your Atlas Excel file, computes predictions, and verifies
100% prediction accuracy by comparing predictions against actual outcomes.

Features:
- Computes Q (C × Φ), Tension (Load − Q), κ (Load / Q)
- Performs regime classification using Gate–River Framework logic
- Compares predictions against actual outcomes
- Generates comprehensive accuracy report
- Outputs detailed analysis with accuracy metrics

To use:
1. Place this file in the same folder as your Excel file:
       Final_Atlas_Coded_Analysis-f086.xlsx
2. Run:
       python atlas_analysis_with_accuracy_verification.py
3. Outputs will be saved as:
       atlas_predictions_with_accuracy.xlsx
       accuracy_verification_report.txt
"""

import pandas as pd
import numpy as np
from datetime import datetime


# ============================================================
# 1. LOAD THE ATLAS
# ============================================================

INPUT_FILE = "Final_Atlas_Coded_Analysis-f086.xlsx"
OUTPUT_FILE = "atlas_predictions_with_accuracy.xlsx"
REPORT_FILE = "accuracy_verification_report.txt"

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
    exit(1)

# Check that required columns exist
required_cols = ["C", "Φ", "Load"]
for col in required_cols:
    if col not in df.columns:
        print(f"✗ Error: Missing required column: {col}")
        exit(1)

print("✓ All required columns present")


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

# κ = Load / Q  (avoid division by zero)
df["kappa_predicted"] = np.where(
    df["Q_predicted"] != 0,
    df["Load"] / df["Q_predicted"],
    np.nan
)

print("✓ Computed Q (C × Φ)")
print("✓ Computed Tension (Load − Q)")
print("✓ Computed κ (Load / Q)")


# ============================================================
# 3. REGIME CLASSIFICATION (PREDICTION)
# ============================================================

print("\n" + "=" * 70)
print("PERFORMING REGIME CLASSIFICATION (PREDICTION)")
print("=" * 70)

def classify_regime(row):
    """
    Classifies each case into a regime category using Gate–River Framework logic.
    
    Classification Rules:
    1. Chaos/Fragmentation mode → CHAOS_HIGH_RISK
    2. High FR Risk → FR_RISK
    3. High κ (>1.2) → OVERLOADED
    4. Low κ (<0.5) → UNDERLOADED
    5. Default → STABLE
    """
    mode = str(row.get("Mode", "")).strip()
    fr_risk = row.get("FR Risk", 0)
    kappa = row.get("kappa_predicted", np.nan)

    # Chaos/Fragmentation mode → highest risk
    if mode == "C":
        return "CHAOS_HIGH_RISK"

    # If FR Risk column indicates danger
    if pd.notna(fr_risk) and fr_risk > 0:
        return "FR_RISK"

    # High κ → overloaded system
    if pd.notna(kappa) and kappa > 1.2:
        return "OVERLOADED"

    # Low κ → underloaded system
    if pd.notna(kappa) and kappa < 0.5:
        return "UNDERLOADED"

    # Otherwise stable
    return "STABLE"


df["Regime_Predicted"] = df.apply(classify_regime, axis=1)
print("✓ Completed regime classification")
print(f"\nPredicted Regime Distribution:")
print(df["Regime_Predicted"].value_counts())


# ============================================================
# 4. ACCURACY VERIFICATION
# ============================================================

print("\n" + "=" * 70)
print("ACCURACY VERIFICATION")
print("=" * 70)

# Check if actual outcomes column exists
actual_outcome_cols = ["Regime_Actual", "Actual_Regime", "Outcome", "Regime", "Actual"]
actual_outcome_col = None

for col in actual_outcome_cols:
    if col in df.columns:
        actual_outcome_col = col
        print(f"✓ Found actual outcomes column: '{actual_outcome_col}'")
        break

if actual_outcome_col is None:
    print("\n⚠ WARNING: No actual outcomes column found.")
    print("Searched for: " + ", ".join(actual_outcome_cols))
    print("\nTo verify 100% accuracy, please ensure your Excel file contains")
    print("an actual outcomes column with one of these names:")
    for col in actual_outcome_cols:
        print(f"  - {col}")
    has_actuals = False
else:
    has_actuals = True
    print(f"\n✓ Found {len(df[actual_outcome_col].dropna())} actual outcomes")

# Calculate accuracy if actuals are available
if has_actuals:
    # Compare predictions vs actuals
    df["Match"] = df["Regime_Predicted"] == df[actual_outcome_col]
    
    matches = df["Match"].sum()
    total = len(df[actual_outcome_col].dropna())
    accuracy = (matches / total * 100) if total > 0 else 0
    
    print(f"\n{'='*70}")
    print("ACCURACY RESULTS")
    print(f"{'='*70}")
    print(f"Total Records with Actuals: {total}")
    print(f"Correct Predictions: {matches}")
    print(f"Incorrect Predictions: {total - matches}")
    print(f"\n*** PREDICTION ACCURACY: {accuracy:.2f}% ***")
    
    if accuracy == 100.0:
        print("\n✓✓✓ 100% PREDICTION ACCURACY VERIFIED ✓✓✓")
    
    # Confusion Matrix
    print(f"\n{'='*70}")
    print("CONFUSION MATRIX")
    print(f"{'='*70}")
    confusion = pd.crosstab(
        df[actual_outcome_col],
        df["Regime_Predicted"],
        margins=True
    )
    print(confusion)
    
    # Per-regime accuracy
    print(f"\n{'='*70}")
    print("PER-REGIME ACCURACY")
    print(f"{'='*70}")
    for regime in df[actual_outcome_col].unique():
        regime_mask = df[actual_outcome_col] == regime
        regime_matches = (df[regime_mask]["Regime_Predicted"] == regime).sum()
        regime_total = regime_mask.sum()
        regime_accuracy = (regime_matches / regime_total * 100) if regime_total > 0 else 0
        print(f"{regime:20s}: {regime_accuracy:6.2f}% ({regime_matches}/{regime_total})")

else:
    print("\nNote: Without actual outcomes, accuracy cannot be verified.")
    print("The predictions have been computed and saved to: " + OUTPUT_FILE)


# ============================================================
# 5. SAVE OUTPUT
# ============================================================

print(f"\n{'='*70}")
print("SAVING OUTPUT")
print(f"{'='*70}")

# Save enriched Excel file
df.to_excel(OUTPUT_FILE, index=False)
print(f"✓ Saved predictions to: {OUTPUT_FILE}")

# Generate text report
with open(REPORT_FILE, "w") as f:
    f.write("=" * 70 + "\n")
    f.write("ATLAS PREDICTION ACCURACY VERIFICATION REPORT\n")
    f.write("=" * 70 + "\n")
    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    f.write("SUMMARY\n")
    f.write("-" * 70 + "\n")
    f.write(f"Input File: {INPUT_FILE}\n")
    f.write(f"Total Records: {len(df)}\n")
    f.write(f"Output Files:\n")
    f.write(f"  - {OUTPUT_FILE}\n")
    f.write(f"  - {REPORT_FILE}\n\n")
    
    f.write("PREDICTIONS COMPUTED\n")
    f.write("-" * 70 + "\n")
    f.write("✓ Q = C × Φ\n")
    f.write("✓ Tension = Load − Q\n")
    f.write("✓ κ = Load / Q\n")
    f.write("✓ Regime Classification\n\n")
    
    f.write("REGIME DISTRIBUTION\n")
    f.write("-" * 70 + "\n")
    for regime, count in df["Regime_Predicted"].value_counts().items():
        f.write(f"{regime:20s}: {count:5d} records\n")
    f.write("\n")
    
    if has_actuals:
        f.write("ACCURACY VERIFICATION\n")
        f.write("-" * 70 + "\n")
        f.write(f"Total Records: {total}\n")
        f.write(f"Correct Predictions: {matches}\n")
        f.write(f"Accuracy: {accuracy:.2f}%\n")
        if accuracy == 100.0:
            f.write("\n✓✓✓ 100% PREDICTION ACCURACY VERIFIED ✓✓✓\n")
    else:
        f.write("NOTE: Actual outcomes not found. Accuracy verification not available.\n")
        f.write("To enable accuracy verification, add an actual outcomes column.\n")

print(f"✓ Saved report to: {REPORT_FILE}")

print(f"\n{'='*70}")
print("PROCESS COMPLETE")
print(f"{'='*70}\n")
