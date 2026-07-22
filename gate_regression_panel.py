"""
Gate Regression Panel Analysis (A, B, C, D)
Validates: Noise_pre → Clarity_post ∆G framework

Panels:
  A: Mechanism validation (Noise_pre effects on Q(ρ) components)
  B: Gate effect (post-Gate descriptive)
  C: Integrated model (pre-Gate predictors + Gate delta)
  D: PHI as amplifier (if PHI pre-Gate)

All leakage-controlled: Panels A, C use pre-Gate predictors only.
"""

import pandas as pd
import numpy as np
from scipy.stats import spearmanr
from statsmodels.formula.api import ols
from statsmodels.stats.outliers_influence import variance_inflation_factor
import warnings

warnings.filterwarnings('ignore', category=FutureWarning)


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
  truthy = {"1", "true", "yes", "y", "viable", "alive", "return"}
  falsy = {"0", "false", "no", "n", "dead", "deceased", "nonviable", "no_return", "irreversible"}
  if text in truthy:
    return True
  if text in falsy:
    return False
  return None


def infer_branch_state(df_in):
  """
  Build branch-state labels from explicit viability/death fields when present.

  Returns:
    (branch_series, source_label)
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
    if col in df_in.columns:
      parsed = df_in[col].apply(parse_boolish)
      labels = parsed.map({True: "Return", False: "NoReturn"}).fillna("Undetermined")
      return labels, f"direct:{col}"

  for col in death_cols:
    if col in df_in.columns:
      parsed = df_in[col].apply(parse_boolish)
      labels = parsed.map({True: "NoReturn", False: "Return"}).fillna("Undetermined")
      return labels, f"death:{col}"

  for col in irreversible_cols:
    if col in df_in.columns:
      parsed = df_in[col].apply(parse_boolish)
      labels = parsed.map({True: "NoReturn", False: "Return"}).fillna("Undetermined")
      return labels, f"irreversible:{col}"

  labels = pd.Series(["Undetermined"] * len(df_in), index=df_in.index)
  return labels, "unavailable"

# Load data
df = pd.read_csv('remainder_quality_analysis_v2.csv')
df['Branch_State'], branch_source = infer_branch_state(df)

print("\n" + "=" * 90)
print("GATE ∆G REGRESSION PANEL ANALYSIS")
print("=" * 90)
print(f"\nSample: n={len(df)}")
print(f"Outcome: Reboot_Quality (Clean=1, Corrupt=0)")
print(f"  Clean: {(df['Reboot_Quality']==1).sum()} cases")
print(f"  Corrupt: {(df['Reboot_Quality']==0).sum()} cases")
print(f"Branch evidence source: {branch_source}")
print("Branch-state distribution:")
print(df['Branch_State'].value_counts(dropna=False).to_string())

# ============================================================================
# PANEL A: MECHANISM VALIDATION (Pre-Gate Noise Effects)
# ============================================================================

print("\n" + "=" * 90)
print("PANEL A: NOISE MECHANISM VALIDATION (Pre-Gate Predictors Only)")
print("=" * 90)

# A1: Noise components vs Q(ρ)
print("\n[A1] Qρ ~ CL + AV + DD")
print("-" * 90)
model_a1 = ols('Q_rho ~ CL + AV + DD', data=df).fit()
print(model_a1.summary().tables[1])
print(f"R²: {model_a1.rsquared:.4f}  Adj-R²: {model_a1.rsquared_adj:.4f}  F-stat: {model_a1.fvalue:.4f}  p: {model_a1.f_pvalue:.6f}")

# A2: Noise_raw (sum) vs Q(ρ)
print("\n[A2] Qρ ~ Noise_pre_raw")
print("-" * 90)
model_a2 = ols('Q_rho ~ Noise_pre_raw', data=df).fit()
print(model_a2.summary().tables[1])
print(f"R²: {model_a2.rsquared:.4f}  Adj-R²: {model_a2.rsquared_adj:.4f}")

# A3: Noise components vs CID
print("\n[A3] CID ~ CL + AV + DD")
print("-" * 90)
model_a3 = ols('CID ~ CL + AV + DD', data=df).fit()
print(model_a3.summary().tables[1])
print(f"R²: {model_a3.rsquared:.4f}  Adj-R²: {model_a3.rsquared_adj:.4f}")

# A4: Noise components vs ECC
print("\n[A4] ECC ~ CL + AV + DD")
print("-" * 90)
model_a4 = ols('ECC ~ CL + AV + DD', data=df).fit()
print(model_a4.summary().tables[1])
print(f"R²: {model_a4.rsquared:.4f}  Adj-R²: {model_a4.rsquared_adj:.4f}")

# A5: Noise components vs CAC
print("\n[A5] CAC ~ CL + AV + DD")
print("-" * 90)
model_a5 = ols('CAC ~ CL + AV + DD', data=df).fit()
print(model_a5.summary().tables[1])
print(f"R²: {model_a5.rsquared:.4f}  Adj-R²: {model_a5.rsquared_adj:.4f}")

# Summary of Panel A
print("\n" + "-" * 90)
print("PANEL A SUMMARY: Expected Noise Effects")
print("-" * 90)
print("Hypothesis: AV (fragility) and DD (structural gaps) should NEGATIVE suppress Q(ρ)")
print("            CL (dimension mismatch) likely confounded with behavioral diversity\n")
panel_a_summary = pd.DataFrame({
    'Model': ['A1: Qρ ~ CL+AV+DD', 'A2: Qρ ~ Noise_raw', 'A3: CID ~ CL+AV+DD', 
              'A4: ECC ~ CL+AV+DD', 'A5: CAC ~ CL+AV+DD'],
    'R²': [model_a1.rsquared, model_a2.rsquared, model_a3.rsquared, 
           model_a4.rsquared, model_a5.rsquared],
    'F-stat': [model_a1.fvalue, model_a2.fvalue, model_a3.fvalue, 
               model_a4.fvalue, model_a5.fvalue],
    'p-value': [model_a1.f_pvalue, model_a2.f_pvalue, model_a3.f_pvalue, 
                model_a4.f_pvalue, model_a5.f_pvalue]
})
print(panel_a_summary.to_string(index=False))

# ============================================================================
# PANEL B: GATE EFFECT (Post-Gate Descriptive)
# ============================================================================

print("\n" + "=" * 90)
print("PANEL B: GATE EFFECT VALIDATION (Post-Gate Outcome)")
print("=" * 90)
print("(Using post-Gate labels for outcome validation only)")

# B1: ∆G predicts Reboot_Quality
print("\n[B1] Reboot_Quality ~ ∆G (continuous)")
print("-" * 90)
# Standardize ΔG for clarity
df['DG_std'] = (df['ΔG'] - df['ΔG'].mean()) / df['ΔG'].std()
model_b1 = ols('Reboot_Quality ~ DG_std', data=df).fit()
print(model_b1.summary().tables[1])
print(f"R²: {model_b1.rsquared:.4f}  Adj-R²: {model_b1.rsquared_adj:.4f}")

# B2: ∆G by outcome regime (ANOVA-like)
print("\n[B2] ∆G by Outcome Regime (Descriptive Breakdown)")
print("-" * 90)
for outcome in ["FR", "CR", "PR", "SR", "MR"]:
    g = df[df["Outcome"] == outcome]
    if len(g):
        print(f"  {outcome}: n={len(g):3d}  ∆G mean={g['ΔG'].mean():+.4f} (sd={g['ΔG'].std():.4f})  "
              f"Clean={g['Reboot_Quality'].sum()}/{len(g)}")

# B3: Clarity_post vs Q(ρ)
print("\n[B3] Qρ ~ Clarity_post_ordinal")
print("-" * 90)
model_b3 = ols('Q_rho ~ Clarity_post_ordinal', data=df).fit()
print(model_b3.summary().tables[1])
print(f"R²: {model_b3.rsquared:.4f}  Adj-R²: {model_b3.rsquared_adj:.4f}")

# ============================================================================
# PANEL C: INTEGRATED MODEL (Pre-Gate + Gate Delta)
# ============================================================================

print("\n" + "=" * 90)
print("PANEL C: INTEGRATED MODEL (Pre-Gate Predictors + Gate Delta)")
print("=" * 90)

# C1: Full Q(ρ) model
print("\n[C1] Qρ ~ CID + ECC + CAC + Noise_pre_raw")
print("-" * 90)
model_c1 = ols('Q_rho ~ CID + ECC + CAC + Noise_pre_raw', data=df).fit()
print(model_c1.summary().tables[1])
print(f"R²: {model_c1.rsquared:.4f}  Adj-R²: {model_c1.rsquared_adj:.4f}")

# C2: Adding ∆G to full model
print("\n[C2] Qρ ~ CID + ECC + CAC + Noise_pre_raw + ∆G")
print("-" * 90)
model_c2 = ols('Q_rho ~ CID + ECC + CAC + Noise_pre_raw + ΔG', data=df).fit()
print(model_c2.summary().tables[1])
print(f"R²: {model_c2.rsquared:.4f}  Adj-R²: {model_c2.rsquared_adj:.4f}")

# Compare models
print("\n[C2 vs C1] Model Comparison (ΔG Incremental Validity)")
print("-" * 90)
f_stat = ((model_c2.ssr - model_c1.ssr) / (len(model_c2.params) - len(model_c1.params))) / \
         (model_c2.ssr / (len(df) - len(model_c2.params)))
p_val = 1 - pd.Series([f_stat]).apply(lambda x: 
         pd.DataFrame([[1]]).eval(f"F({len(model_c2.params) - len(model_c1.params)}, {len(df) - len(model_c2.params)})")[0]
         if hasattr(pd, 'F') else 0).iloc[0]
print(f"  ∆ R²: {model_c2.rsquared - model_c1.rsquared:.6f}")
print(f"  F-increment: {f_stat:.4f}")
print(f"  Interpretation: Adding ∆G {'adds' if f_stat > 2 else 'does not add'} much value beyond CID+ECC+CAC+Noise_pre")

# C3: Reboot_Quality with full predictors
print("\n[C3] Reboot_Quality ~ Qρ + ∆G")
print("-" * 90)
model_c3 = ols('Reboot_Quality ~ Q_rho + ΔG', data=df).fit()
print(model_c3.summary().tables[1])
print(f"R²: {model_c3.rsquared:.4f}  Adj-R²: {model_c3.rsquared_adj:.4f}")

# ============================================================================
# PANEL D: PHI AS AMPLIFIER (if Φ exists and is pre-Gate)
# ============================================================================

print("\n" + "=" * 90)
print("PANEL D: PHI (Φ) AS REGULATOR AMPLIFIER")
print("=" * 90)

if "Φ" in df.columns or "Phi" in df.columns:
    phi_col = "Φ" if "Φ" in df.columns else "Phi"
    df_phi = df.copy()
    df_phi['Phi_val'] = df_phi[phi_col]
    
    # D1: PHI direct effect
    print(f"\n[D1] Qρ ~ CID + ECC + CAC + Noise_pre_raw + Phi")
    print("-" * 90)
    model_d1 = ols('Q_rho ~ CID + ECC + CAC + Noise_pre_raw + Phi_val', data=df_phi).fit()
    print(model_d1.summary().tables[1])
    print(f"R²: {model_d1.rsquared:.4f}  Adj-R²: {model_d1.rsquared_adj:.4f}")
    
    # D2: PHI × ECC interaction
    print(f"\n[D2] Qρ ~ CID + ECC + CAC + Phi + (Phi × ECC)")
    print("-" * 90)
    df_phi['Phi_ECC'] = df_phi['Phi_val'] * df_phi['ECC']
    model_d2 = ols('Q_rho ~ CID + ECC + CAC + Phi_val + Phi_ECC', data=df_phi).fit()
    print(model_d2.summary().tables[1])
    print(f"R²: {model_d2.rsquared:.4f}  Adj-R²: {model_d2.rsquared_adj:.4f}")
    
    # D3: PHI × CAC interaction
    print(f"\n[D3] Qρ ~ CID + ECC + CAC + Phi + (Phi × CAC)")
    print("-" * 90)
    df_phi['Phi_CAC'] = df_phi['Phi_val'] * df_phi['CAC']
    model_d3 = ols('Q_rho ~ CID + ECC + CAC + Phi_val + Phi_CAC', data=df_phi).fit()
    print(model_d3.summary().tables[1])
    print(f"R²: {model_d3.rsquared:.4f}  Adj-R²: {model_d3.rsquared_adj:.4f}")
    
    print(f"\nPanel D Summary:")
    print(f"  PHI direct effect: {'Significant' if model_d1.pvalues.get('Phi_val', 1) < 0.05 else 'Not significant'}")
    print(f"  PHI × ECC interaction: {'Significant' if model_d2.pvalues.get('Phi_ECC', 1) < 0.05 else 'Not significant'}")
    print(f"  PHI × CAC interaction: {'Significant' if model_d3.pvalues.get('Phi_CAC', 1) < 0.05 else 'Not significant'}")

else:
    print("\nNote: Φ column not found. Skipping Panel D.")

# ============================================================================
# PANEL E: BRANCH / VIABILITY LAYER (if explicit branch evidence exists)
# ============================================================================

print("\n" + "=" * 90)
print("PANEL E: BRANCH / VIABILITY LAYER")
print("=" * 90)

branch_known_mask = df['Branch_State'].isin(['Return', 'NoReturn'])
if branch_known_mask.any() and df.loc[branch_known_mask, 'Branch_State'].nunique() > 1:
  df_e = df.loc[branch_known_mask].copy()
  df_e['NoReturn'] = (df_e['Branch_State'] == 'NoReturn').astype(int)
  df_e['DG_x_NoReturn'] = df_e['DG_std'] * df_e['NoReturn']

  print("\n[E1] Reboot_Quality ~ ∆G + NoReturn + (∆G × NoReturn)")
  print("-" * 90)
  model_e1 = ols('Reboot_Quality ~ DG_std + NoReturn + DG_x_NoReturn', data=df_e).fit()
  print(model_e1.summary().tables[1])
  print(f"R²: {model_e1.rsquared:.4f}  Adj-R²: {model_e1.rsquared_adj:.4f}")

  print("\n[E2] Mean ∆G by branch state")
  print("-" * 90)
  for state in ['Return', 'NoReturn']:
    grp = df_e[df_e['Branch_State'] == state]
    if len(grp):
      print(f"  {state:8s}: n={len(grp):3d}  ∆G mean={grp['ΔG'].mean():+.4f} (sd={grp['ΔG'].std():.4f})")
else:
  print("No explicit viability/death field detected with both Return and NoReturn states.")
  print("Panel E skipped to avoid circular inference from outcome labels.")

# ============================================================================
# SUMMARY & INTERPRETATION
# ============================================================================

print("\n" + "=" * 90)
print("REGRESSION PANEL SUMMARY & INTERPRETATION")
print("=" * 90)

print("""
PANEL A (Noise Mechanism):
  ✓ Expected: AV (fragility) and DD (gaps) NEGATIVE suppress Q(ρ) components
  ✓ CL (Bio-Cog mismatch) may be confounded with behavioral diversity
  → If AV, DD significant and negative: mechanism validated

PANEL B (Gate Effect):
  ✓ Expected: Higher ∆G → higher Reboot_Quality (cleaner outcomes)
  ✓ FR cases should show lower ∆G; CR/SR cases higher ∆G
  → If ∆G significantly predicts outcome: Gate signal strong

PANEL C (Integration):
  ✓ Expected: ∆G adds minimal to full model (CID+ECC+CAC+Noise capture it)
  ✓ Or: ∆G is orthogonal signal (novel contribution)
  → Reveals whether Gate is redundant or independent mechanism

PANEL D (PHI Amplifier):
  ✓ Expected: PHI positive main effect; PHI×ECC, PHI×CAC positive interactions
  ✓ Suggests PHI amplifies rescue capacity (ECC) and contradiction metabolism (CAC)
  → If significant interactions: PHI is a noise-reduction regulator

KEY HYPOTHESIS:
  H1: Noise_pre suppresses Q(ρ) components [Expect negative in Panel A]
  H2: ∆G predicts clean reboot quality [Expect positive in Panel B]
  H3: ∆G is redundant with Q(ρ) model [Expect small ∆R² in Panel C]
  H4: PHI amplifies ECC, CAC [Expect positive interactions in Panel D]
""")

print("\n" + "=" * 90)
print("ANALYSIS COMPLETE")
print("=" * 90)
print("\nOutput: gate_regression_results.txt (optional save)")
print("Next: Compare against publication benchmark (98%+ accuracy expected)")
