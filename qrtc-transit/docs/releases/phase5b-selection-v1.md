# Release Notes Draft — `phase5b-selection-v1`

> **Status:** Draft only. No Git tag or GitHub release has been created.
> **Proposed tag:** `phase5b-selection-v1`
> **Target commit:** `d4bc5b56d1dcfa88b413adc15b423aa09814d750`

---

## Summary

`qrtc` **passed frozen Phase V-B benchmark validation** under protocol `phase5b-selection-v1`.

This is not a certification of safety, a production deployment approval, or a physical-vehicle certification. `qrtc` holds recommend-only authority. Hardware actuation remains disabled.

---

## What changed in this release series

| PR | Description |
|----|-------------|
| #21 | Phase V-B reproducibility / package repair |
| #22 | Controller interface / frozen candidate artifacts |
| #24 | Preregistered selection protocol (`phase5b-selection-v1`) |
| #25 | Development comparison — `development_completed_no_selection` |
| #26 | Selection-validation — provisional `qrtc` selection |
| #27 | Authorized final validation — `final_validation_passed` |

---

## Headline metrics (`qrtc`, final-validation split)

| Metric | Value |
|--------|-------|
| Mean utility | `0.43378` |
| Recovery rate | `0.62316` |
| Mean harm | `0.02496` |
| Unsafe-commitment rate | `0.0` |
| Oracle regret | `0.09668` |
| Paired utility delta vs `greedy_gain` | `+0.42677` |
| 95 % bootstrap CI | `[0.41553, 0.43790]` |
| Win rate vs `greedy_gain` | `0.82313` |
| All frozen final gates | passed |

---

## Immutable identifiers

| Field | Value |
|-------|-------|
| Protocol | `phase5b-selection-v1` |
| Protocol hash | `fc6b86912182d216be4d381992732345cc5d6a38299d6c5946ab1b8fe2bfe77c` |
| Implementation commit | `6aa56a7abae975274e95a9ba2941fe2002794592` |
| Selection result SHA-256 | `a74a8b5e0e573e937bdcfa7ec72c63aef14ed3eb8bfce2631c15c09672518be5` |
| Authorization SHA-256 | `0a4c4861afeba2fd6c8327d0dc9eb53753db2a46f885eecd0a4424b34873d9a9` |

---

## Reproducibility

Development and final-validation runs were each executed twice with `PYTHONHASHSEED=111` and `PYTHONHASHSEED=222`. All output files were byte-identical across both executions.

---

## Operational status

- Authority: **recommend-only**
- Hardware actuation: **disabled**
- Deployment approval: **false**
- Physical certification: **false**
- Any deployment, actuation, or physical testing requires a new, separately reviewed protocol and authorization.

---

## Key artifacts

- Protocol: [`artifacts/protocols/phase5b-selection-v1/preregistration.json`](../../artifacts/protocols/phase5b-selection-v1/preregistration.json)
- Development report: [`artifacts/phase5b-selection-v1/development-run-1/DEVELOPMENT_REPORT.md`](../../artifacts/phase5b-selection-v1/development-run-1/DEVELOPMENT_REPORT.md)
- Selection-validation report: [`artifacts/phase5b-selection-v1/selection-validation-run-1/SELECTION_VALIDATION_REPORT.md`](../../artifacts/phase5b-selection-v1/selection-validation-run-1/SELECTION_VALIDATION_REPORT.md)
- Final-validation report: [`artifacts/phase5b-selection-v1/final-validation-run-1/FINAL_VALIDATION_REPORT.md`](../../artifacts/phase5b-selection-v1/final-validation-run-1/FINAL_VALIDATION_REPORT.md)
- Closure audit summary: [`docs/phase5b_validation_audit_summary.md`](../phase5b_validation_audit_summary.md)
- Closure index (JSON): [`artifacts/phase5b-selection-v1/closure_index.json`](../../artifacts/phase5b-selection-v1/closure_index.json)
