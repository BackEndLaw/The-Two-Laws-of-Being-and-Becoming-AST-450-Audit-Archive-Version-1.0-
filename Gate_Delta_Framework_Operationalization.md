# Gate = Noise Reduction → Clarity ∆G Framework
## Leakage-Controlled Operationalization for Atlas 245-Case Biographical Study

**Date:** 2026-06-22  
**Status:** Ready for integration into `remainder_quality_framework.py`  
**Leakage control:** All Noise_pre computed from **pre-Gate structural fields only**; Clarity_post from **Out(t₀) only**.

---

## 1. PRE-GATE NOISE (Noisepre)

### Mapping to Atlas columns

From analysis of 245 cases, three structural contradictions reliably signal pre-Gate turbulence:

| Component | Atlas Column(s) | Type | Values | Interpretation |
|-----------|---------|------|--------|-----------------|
| **CL** (Contradiction Load) | `\|Bio - Cog\|` | Ordinal (0–3) | Δ = 0,1,2,3 | Behavioral dimension misalignment |
| **AV** (Affective Volatility) | `Low_C_low_Phi_rule` | Binary | 0/1 | Structural fragility signal |
| **DD** (Defensive Distortion) | `Template_Deficit + FR_rule` | Composite | 0–2 | Structural gap + fragmentation risk |

### Formula: Noise_pre (raw sum, then z-score normalize)

```
CL = |Bio - Cog|                                    # Contradiction load (0–3)
AV = Low_C_low_Phi_rule                             # Volatility flag (0–1)
DD = Template_Deficit + FR_rule                     # Defense+fragmentation (0–2)

Noise_pre_raw = CL + AV + DD                        # Sum: range 0–6

Noise_pre = z_score(Noise_pre_raw)                  # Standardize
            OR
            Noise_pre = (Noise_pre_raw / 6.0)      # Min-max [0,1]
```

### Distributions (n=245)

- **CL = |Bio - Cog|**: 
  - 0: 33 cases (13%)
  - 1: 75 cases (31%)
  - 2: 62 cases (25%)
  - 3: 75 cases (31%)
  
- **AV (Low_C_low_Phi_rule)**:
  - 0: 235 cases (96%)
  - 1: 10 cases (4%)

- **DD (Template_Deficit + FR_rule)**:
  - 0: 236 cases (96%)
  - 1: 9 cases (4%)
  - 2: 0 cases

- **Noise_pre_raw** (0–6 range, raw sum):
  - Mean ≈ 1.2, SD ≈ 1.1
  - Skewed right (most cases low-noise)

---

## 2. POST-GATE CLARITY (Clarity_post)

### Mapping to Atlas Out(t₀) outcomes

From post-Gate immediate outcome `Out(t₀)`, map to clarity ordinal:

| Outcome | Clarity Score | Interpretation | Count |
|---------|---------------|-----------------|-------|
| **FR** (Fragmentation Regime) | 0 | Incoherent, hostile collapse | 9 |
| **MR** (Mixed Regime) | 1 | Partial coherence, retained contradictions | 86 |
| **PR** (Possible Regime) | 2 | Emergent coherence, latent risk | 69 |
| **CR** (Coherent Regime) | 3 | Clean reboot, stable reordering | 18 |
| **SR** (Stable Regime) | 3 | Maximum coherence, aligned transformation | 63 |

### Formula: Clarity_post (ordinal)

```
Clarity_t0_map = {
    'FR': 0,
    'MR': 1,
    'PR': 2,
    'CR': 3,
    'SR': 3
}

Clarity_post = Clarity_t0_map[Out(t₀)]     # Ordinal [0, 3]
```

### Alternative: Binary "Clean" clarity

For robustness, also compute:
```
Clarity_post_binary = Is_Clean_CR_PR        # Binary: CR/PR/MR Clean vs FR Corrupt
                                             # Note: Is_Clean_CR_PR=1 for 87/245 (36%)
```

---

## 3. GATE MAGNITUDE: ∆G

### Definition

```
∆G = Clarity_post - Noise_pre

     = Clarity_t0_ordinal - z_score(Noise_pre_raw)
```

### Interpretation

- **∆G > 0**: Case experienced clarification (noise → coherence)
  - Larger ∆G → stronger Gate effect
  
- **∆G ≈ 0**: Case maintained steady state (low noise → low clarity gain; OR high noise → modest clarity)
  
- **∆G < 0**: Case deteriorated (paradoxical increase in noise post-Gate)
  - Should be rare; indicates either:
    - Pre-Gate structure was already coherent → no room for gain
    - Post-Gate collapse despite pre-Gate simplicity (test for true disconfirmation)

### Expected correlation with Q_ρ

**H1:** Cases with higher ∆G should also have higher Q_ρ (Remainder Quality).
- Q_ρ is a **pre-Gate coherence regulator**, so it should suppress Noise_pre.
- ∆G operationalizes what Q_ρ *enables*: the transition from noise → clarity.

---

## 4. PHENOMENOLOGY LAYER: Dream/Vision Type (optional, non-causal)

### Classification (from biographical text, independent of Gate ∆G)

Encode gate-adjacent phenomenology as categorical, **not as a predictor**:

```
Gate_Phenomenology_Type ∈ {
    'dream_lucid',           # Lucid dream / astral experience
    'vision_aesthetic',      # Visual pattern / aesthetic insight
    'music_note',            # Auditory / musical revelation
    'conceptual_reframe',    # Intellectual paradigm shift
    'somatic_stillness',     # Bodily peace / motor reset
    'social_relational',     # Presence of witness / loved one
    'time_table_insight',    # Temporal or scheduling revelation
    'other'
}

Gate_Phenomenology_Intensity ∈ [0, 3]   # Subjective salience
```

### Test (descriptive, not predictive)

After fitting Qρ ~ CID + ECC + CAC + Noise_pre:
1. Stratify by Gate_Phenomenology_Type
2. Ask: Does the residual variation correlate with type?
3. Expected: **No strong main effect** (mechanism is noise → clarity, not phenomenology type)
4. Possible interaction: Aesthetic/somatic types may *require* lower Noise_pre to manifest ∆G.

---

## 5. VALIDATION PANEL: Leakage-Free Regressions

### Panel A: Mechanism validation (Noise_pre effects)

```python
# All predictors = pre-Gate only

Qρ ~ Noise_pre 
     Expected: Negative (lower noise → higher quality regulator)

CID ~ Noise_pre 
     Expected: Negative (lower noise → higher coherent charge per complexity)

ECC ~ Noise_pre 
     Expected: Negative (lower noise → higher rescue-vs-wall ratio)

CAC ~ Noise_pre 
     Expected: Negative (lower noise → higher contradiction metabolism)
```

### Panel B: Gate effect (post-Gate descriptive)

```python
# Using post-Gate outcome (descriptive, not predictive)

Qρ ~ Clarity_post 
     Expected: Positive (coherent post-Gate → aligns with pre-Gate regulator)

∆G ~ Qρ 
     Expected: Positive (high-quality regulator enables larger clarity gain)
```

### Panel C: Integrated model (pre-Gate + Gate delta)

```python
# Leakage-safe: only pre-Gate predictors on pre-Gate outcome

Qρ ~ CID + ECC + CAC + Noise_pre

     Then ask: Does ∆G predict *residual* Qρ post-Gate?
     
Residual(Qρ) ~ ∆G + Gate_Phenomenology_Type
     Expected: ∆G positive; type effects weak unless interaction
```

### Panel D: PHI as regulator amplifier (if PHI is pre-Gate)

```python
Qρ ~ CID + ECC + CAC + Noise_pre + Φ 
     
     + interaction terms one at a time:
       PHI × ECC  (Does PHI strengthen rescue capacity?)
       PHI × CAC  (Does PHI enable contradiction metabolism?)
       
     Expected: Positive interactions if PHI is a "noise filter"
```

---

## 6. IMPLEMENTATION CHECKLIST

- [ ] **Compute Noise_pre** (raw + z-score) in Atlas dataframe
- [ ] **Compute Clarity_post** (ordinal from Out(t₀)) in Atlas dataframe
- [ ] **Compute ∆G** = Clarity_post - Noise_pre
- [ ] **Validate leakage:** Check that Noise_pre uses *only* pre-Gate columns
  - Forbidden in Noise_pre: Outcome, Out(t₀), Out(late), Match, Regime_*, Reboot_Quality
  - Allowed: Bio, Env, Cog, Id, Sym, C, Φ, Q_calc, Load, Tension, κ, Mode, Ω, I, Walls, Ext, etc.
- [ ] **Run Panel A regressions** (Noise_pre effects on Qρ components)
- [ ] **Run Panel B regressions** (∆G effects on post-Gate outcomes)
- [ ] **Prepare phenomenology stratification** (if biographical codes available)
- [ ] **Document all formulas** in final methods section

---

## 7. COLUMN INVENTORY FOR CODE

### Pre-Gate structural fields (safe for Noise_pre):
```
Bio, Env, Cog, Id, Sym,
C, Φ, Q_calc, Load, Tension, κ,
Mode, Ω, Integration Type, I,
FR Risk, Rescue, Walls, Template_Deficit,
FR_rule, Rescue_rule, Q_ge_12_rule, Q_le_6_rule, Low_C_low_Phi_rule, PR_rule_candidate,
Ext,
Q_predicted, Tension_predicted, kappa_predicted
```

### Post-Gate outcome fields (for Clarity_post and outcome validation only):
```
Outcome, Out(t₀), Out(late),
Is_FR_t0, Is_FR_late, Is_CR_t0, Is_PR_t0, Is_Clean_CR_PR,
Regime_Predicted, Regime_Predicted_TwoLaws_Strict, Regime_Predicted_TwoLaws_Calibrated,
Regime_Actual_Normalized, Match
```

### To compute Noise_pre:
```
Bio (scale 0–4)
Cog (scale 0–4)
Low_C_low_Phi_rule (binary 0/1)
Template_Deficit (binary 0/1)
FR_rule (binary 0/1)
```

---

## References

- **Atlas structural encoding:** case_zero.csv, atlas_predictions_with_accuracy.csv (245 biographical cases)
- **Outcome encoding:** Out(t₀) immediate post-Gate outcome; Out(late) long-term follow-up (if available)
- **Framework:** Two-Laws of Being & Becoming (AST-450 Audit Archive, v1.0)
- **Leakage control:** Pre-Gate predictors only; post-Gate outcomes descriptive/exploratory only

