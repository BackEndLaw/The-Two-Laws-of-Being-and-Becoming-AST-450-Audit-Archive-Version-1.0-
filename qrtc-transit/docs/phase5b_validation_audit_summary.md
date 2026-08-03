# Phase V-B Validation Audit Summary

**Protocol:** `phase5b-selection-v1`
**Validated controller:** `qrtc`
**Final outcome:** `final_validation_passed`
**Validated main commit:** `d4bc5b56d1dcfa88b413adc15b423aa09814d750`
**Summary date:** 2026-08-03

---

## 1. Scope and claim boundary

`qrtc` **passed the frozen simulated Phase V-B benchmark protocol** (`phase5b-selection-v1`).

This audit summary **does not** constitute and **must not** be interpreted as:

- production deployment approval;
- universal safety proof;
- physical-vehicle certification; or
- hardware-actuation authorization.

`qrtc` holds **recommend-only** authority. Hardware actuation remains **disabled**. Any deployment, advisor integration, physical testing, or actuation requires a new, separately reviewed protocol and explicit authorization.

---

## 2. Immutable chain of custody

| PR | Merge commit | Description |
|----|-------------|-------------|
| #21 | `408f56af50f1fe9e67e51b524e4645cf21dc6e52` | Phase V-B reproducibility / package repair |
| #22 | `6aa56a7abae975274e95a9ba2941fe2002794592` | Controller interface / frozen candidate artifacts |
| #24 | `748f1096168a4292705bc4d0b97ca35dde4dfd18` | Preregistered selection protocol |
| #25 | `390481e62500fda6e98559508c46134382b77736` | Development comparison — no selection |
| #26 | `54ac41b57af075dc2fa22cce66b6fe3ce7f5cffe` | Selection-validation — provisional `qrtc` selection |
| #27 | `d4bc5b56d1dcfa88b413adc15b423aa09814d750` | Authorized final validation |

---

## 3. Frozen identifiers and hashes

| Field | Value |
|-------|-------|
| Protocol ID | `phase5b-selection-v1` |
| Protocol hash | `fc6b86912182d216be4d381992732345cc5d6a38299d6c5946ab1b8fe2bfe77c` |
| Implementation commit | `6aa56a7abae975274e95a9ba2941fe2002794592` |
| Selection result SHA-256 | `a74a8b5e0e573e937bdcfa7ec72c63aef14ed3eb8bfce2631c15c09672518be5` |
| Authorization SHA-256 | `0a4c4861afeba2fd6c8327d0dc9eb53753db2a46f885eecd0a4424b34873d9a9` |
| Final result schema | `rescueos-final-validation-result-v1` |

### Canonical artifact paths

| Artifact | Repository-relative path |
|----------|--------------------------|
| Protocol preregistration | [`artifacts/protocols/phase5b-selection-v1/preregistration.json`](../artifacts/protocols/phase5b-selection-v1/preregistration.json) |
| Development report | [`artifacts/phase5b-selection-v1/development-run-1/DEVELOPMENT_REPORT.md`](../artifacts/phase5b-selection-v1/development-run-1/DEVELOPMENT_REPORT.md) |
| Selection-validation report | [`artifacts/phase5b-selection-v1/selection-validation-run-1/SELECTION_VALIDATION_REPORT.md`](../artifacts/phase5b-selection-v1/selection-validation-run-1/SELECTION_VALIDATION_REPORT.md) |
| Final-validation report | [`artifacts/phase5b-selection-v1/final-validation-run-1/FINAL_VALIDATION_REPORT.md`](../artifacts/phase5b-selection-v1/final-validation-run-1/FINAL_VALIDATION_REPORT.md) |
| Closure index (JSON) | [`artifacts/phase5b-selection-v1/closure_index.json`](../artifacts/phase5b-selection-v1/closure_index.json) |

---

## 4. Stage outcomes

| Stage | Outcome | Notes |
|-------|---------|-------|
| Development | `development_completed_no_selection` | Descriptive comparison only; no controller selected |
| Selection validation | `provisional_selection` — selected ID: `qrtc` | Provisional only; not a confirmation |
| Final validation | `final_validation_passed` | Benchmark confirmation of provisionally selected `qrtc` |

**Provisional selection** (PR #26) identified `qrtc` as the leading candidate under the frozen eligibility gates.
**Final validation** (PR #27) confirmed that `qrtc` passes all frozen final gates on the held-out final split.
These are distinct stages; provisional selection alone does not constitute benchmark confirmation.

---

## 5. Final metrics (`qrtc`, final-validation split)

| Metric | Value |
|--------|-------|
| Mean utility | `0.43377821180555554` |
| Recovery rate | `0.6231553819444444` |
| Mean harm | `0.024956597222222224` |
| Mean intervention cost | `3.6627604166666665` |
| Unsafe-commitment rate | `0.0` |
| Oracle regret | `0.0966796875` |
| Paired utility delta vs `greedy_gain` | `0.4267713758680555` |
| 95 % bootstrap CI | `[0.4155334499344119, 0.43790159035115805]` |
| Win rate vs `greedy_gain` | `0.8231336805555556` |
| All frozen final gates passed | `true` |

---

## 6. Reproducibility and integrity

- The **development** run was executed twice with registered `PYTHONHASHSEED` values `42` and `999`; output files were byte-identical across both executions.
- The **final-validation** run was likewise executed twice with `PYTHONHASHSEED=111` and `PYTHONHASHSEED=222`; output files were byte-identical across both executions.
- Prior frozen protocol and result artifacts (protocol preregistration, development results, selection-validation results) were checksum-verified before final validation ran and remained unchanged.

---

## 7. Operational status

- `qrtc` is **benchmark-confirmed** under `phase5b-selection-v1` with **recommend-only** authority.
- Hardware actuation remains **disabled**.
- Any deployment, advisor integration, physical testing, or actuation requires a **new, separately reviewed protocol and authorization**.
- **No additional Phase V-B experiment run** is authorized by this summary.
