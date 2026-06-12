"""
atlas_analysis.py

This script loads your Atlas Excel file, computes:
- Q (C × Φ)
- Tension (Load − Q)
- κ (Load / Q)
- A simple regime classification

Then it saves a new enriched Excel file.

To use:
1. Place this file in the same folder as your Excel file:
       Final_Atlas_Coded_Analysis-f086.xlsx
2. Run:
       python atlas_analysis.py
3. Output will be saved as:
       atlas_analysis_output.xlsx
"""

import pandas as pd
import numpy as np


# ------------------------------------------------------------
# 1. LOAD THE ATLAS
# ------------------------------------------------------------

INPUT_FILE = "Final_Atlas_Coded_Analysis-f086.xlsx"
OUTPUT_FILE = "atlas_analysis_output.xlsx"

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

# Q = C × Φ
df["Q_calc_python"] = df["C"] * df["Φ"]

# Tension = Load − Q
df["Tension_python"] = df["Load"] - df["Q_calc_python"]

# κ = Load / Q  (avoid division by zero)
df["kappa_python"] = np.where(
    df["Q_calc_python"] != 0,
    df["Load"] / df["Q_calc_python"],
    np.nan
)


# ------------------------------------------------------------
# 3. SIMPLE REGIME CLASSIFICATION
# ------------------------------------------------------------
# This is a placeholder classifier.
# You can later replace it with your full Ω / Gate–River logic.

def classify_regime(row):
    """
    Classifies each case into a simple regime category.
    You can expand this into your full GRF engine later.
    """

    mode = str(row.get("Mode", "")).strip()
    fr_risk = row.get("FR Risk", 0)
    kappa = row.get("kappa_python", np.nan)

    # Chaos/Fragmentation mode → highest risk
    if mode == "C":
        return "CHAOS_HIGH_RISK"

    # If FR Risk column indicates danger
    if pd.notna(fr_risk) and fr_risk > 0:
        return "FR_RISK"

    # High κ → overloaded system
    if pd.notna(kappa) and kappa > 1.2:
        return "HIGH_LOAD"

    # Low κ → underloaded system
    if pd.notna(kappa) and kappa < 0.5:
        return "UNDERLOADED"

    # Otherwise stable
    return "STABLE"


df["Regime_Class"] = df.apply(classify_regime, axis=1)


# ------------------------------------------------------------
# 4. SAVE OUTPUT
# ------------------------------------------------------------

df.to_excel(OUTPUT_FILE, index=False)

print(f"Analysis complete. Output saved to: {OUTPUT
