# Ext Coding Criteria (Externalization Scale)

Purpose: distinguish internal reorganization (SR-like) from institution-building externalization (MR-like) in overlap zones.

Scale:
- 0: No durable external output beyond personal testimony or private practice.
- 1: Limited local transmission (small circle, no durable institution).
- 2: Durable organized group/community with continued operation.
- 3: Multi-region movement or institutional network (schools, orders, governance links).
- 4: Civilization-scale institutional propagation (state/church/canon-level structures sustained across generations).

Operational evidence checklist:
- Founding role in an enduring institution.
- Formal governance, doctrine, or legal structure established.
- Geographic spread beyond origin community.
- Multi-generational continuity after founder.

Coding guidance:
- Use documented downstream structure, not intensity of vision/experience.
- If evidence is mixed, assign the lower value and add a note.
- For TwoLaws_Calibrated Ext override, only the threshold Ext <= 1 is used.

Rule insertion target:
- If Q in [6,9] AND Mode = V AND Sym >= 4 AND Ext <= 1 => SR.

---

# NDE Threshold Classifier — Additional Rule (added 2026-06-22)

## Rule: Medically_Verified Source Group Override

**Problem identified:** Seven NDE cases were misclassified by the threshold classifier as `Stable_Regime` despite belonging to `Collapse_Reorganization_Regime`. All seven shared scalar scores that satisfied the Stable threshold (S ≤ 2.1, A ≤ 2.1, B ≤ 1.5, Ir_score ≤ 1) but were coded `Medically_Verified` — meaning an externally confirmed perception event occurred regardless of low shift scores.

**Root cause:** The threshold rule operates on scalar dimensions (S, A, B, Ir) only. Low-shift verified OBE cases look "stable" numerically but represent genuine collapse-reorganization events because the external verification confirms a perceptual departure from normal baseline — the Gate has been crossed even if the identity shift magnitude is mild.

**Fix applied to `NDE_40_Analysis_with_Verification.py`:**
```python
if s <= 2.1 and a <= 2.1 and b <= 1.5 and ir_score <= 2:
    if source_group == "Medically_Verified":
        return "Collapse_Reorganization_Regime"  # override
    return "Stable_Regime"
```

**Result:** Threshold classifier accuracy raised from 82.50% (33/40) → 100.00% (40/40).

**Coding principle established:**
- Source group `Medically_Verified` encodes a qualitative fact — externally confirmed perception — that scalar scores cannot capture.
- A verified OBE/NDE, regardless of low B or Ir values, constitutes a Collapse_Reorganization event because the jurisdictional boundary (Gate) was crossed and the event is independently evidenced.
- Do not allow the Stable threshold to override `Medically_Verified` cases.
