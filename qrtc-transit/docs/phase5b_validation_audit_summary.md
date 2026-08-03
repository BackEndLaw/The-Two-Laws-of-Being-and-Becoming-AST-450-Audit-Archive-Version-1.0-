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

---

## 8. Decision-focused test inventory for the current tree

This inventory is scoped to the **current frozen Phase V-B release claim boundary**:

- benchmark-confirmed `qrtc` under `phase5b-selection-v1`;
- **recommend-only** authority;
- **no hardware actuation**; and
- **no additional Phase V-B experiment run authorized**.

`Required?` therefore means **required to run now** for the current release decision, not
“valuable in the abstract.” Any row marked `No` may become `Yes` again if the scope expands
(for example, if controller selection is reopened, CARLA claims are added, or runtime
hardening becomes part of the first-release claim).

| Test | Path | Release claim protected | Selection or final validation? | Existing evidence? | Estimated cost | Required? | What decision changes if it fails? |
|---|---|---|---|---|---:|---|---|
| Selection protocol integrity | `tests/qrtc_benchmark/test_selection_protocol.py` | Frozen controller-selection rule and protocol integrity | Selection integrity | Yes | Low | Yes | The provisional-selection record is not credible, so the benchmark confirmation chain must be treated as invalid. |
| Selection-validation preflight / ancestry / scope | `tests/qrtc_benchmark/test_phase5b_selection_validation.py` | No leakage, valid ancestry, locked scope before expensive runs | Selection gate | Yes | Low | Yes | Stop any further benchmark execution because the selection-validation stage is not admissible. |
| Final-validation preflight / scope / authorization | `tests/qrtc_benchmark/test_phase5b_final_validation.py` | Final-validation integrity on the frozen held-out split | Final-validation gate | Yes | Low | Yes | The final-validation result cannot be accepted as valid release evidence. |
| Closure index / chain of custody | `tests/qrtc_benchmark/test_phase5b_closure_index.py` | Artifact closure, hash trail, and chain-of-custody integrity | Final validation / packaging | Yes | Low | Yes | The release evidence bundle cannot be trusted or audited as frozen. |
| Controller artifact integrity | `tests/qrtc_benchmark/test_controller_artifact.py` | Frozen controller artifact is complete and reproducible | Both | Yes | Low | Yes | The selected controller cannot be treated as frozen or reproducible for release. |
| Installed-wheel smoke | `tests/integration/test_package_smoke.py` | Frozen product installs, imports, and exposes working entry points | Packaging | Yes | Low | Yes | The frozen product is not reproducible as an installable package. |
| Release candidate smoke | `tests/integration/test_release_candidate.py` | Clean-room release flow runs end-to-end from the packaged CLI | Packaging | Yes | Low | Yes | The release candidate is not shippable as the claimed Advisor package. |
| Determinism / reproducibility | `tests/qrtc_benchmark/test_phase5b_determinism.py` | Benchmark results belong to the frozen controller and protocol | Both | Yes | Low | Yes | The reported result may not be reproducible enough to support the frozen release claim. |
| Pool / split partition checks | `tests/qrtc_benchmark/test_phase5b_pools.py` | Correct split boundaries and no selection/validation leakage | Selection and final-validation integrity | Yes | Low | Yes | The benchmark partitions are contaminated, so both comparison and final confirmation lose credibility. |
| Phase 5 benchmark result checks | `tests/qrtc_benchmark/test_phase5.py` | Utility, harm, recovery, and paired-comparison metrics are meaningful | Selection evidence | Partial | Medium | Yes | The numerical basis for the benchmark claim is unreliable, so the product claim must be revisited. |
| Candidate/controller behavior comparison | `tests/qrtc_benchmark/test_controllers.py` | Controller-comparison correctness while multiple viable candidates remain | Selection only | Partial | Low | No | None for the current frozen release unless controller selection is reopened. |
| Development benchmark checks | `tests/qrtc_benchmark/test_phase5b_development.py` | Descriptive comparison quality during open controller selection | Selection only | Yes | Medium | No | None for the current frozen release unless a new selection program is authorized. |
| Historical Phase IV-B benchmark tests | `tests/qrtc_benchmark/test_phase4b.py` | Archival verification of legacy benchmark code | Neither for the current claim | Yes | Medium | No | None for the current RescueOS Advisor release decision. |
| Core CLI / policy / kernel / replay / evidence invariants | `tests/test_cli.py`, `tests/test_policy.py`, `tests/test_kernel.py`, `tests/property/*.py`, `tests/test_pipeline.py`, `tests/test_replay.py`, `tests/test_transit_models.py`, `tests/test_evidence_store.py`, `tests/test_boat.py`, `tests/test_river.py` | General product correctness outside the narrow frozen release gates | Product/runtime | Yes | Medium | No | None immediately for the current benchmark release unless the first-release claim is broadened beyond packaging and frozen validation. |
| CARLA scenario and harness tests | `tests/test_carla_*` | CARLA-driving, LiDAR, telemetry, and harness behavior | Neither for the current frozen benchmark claim | Unknown | High | No | None unless CARLA performance becomes part of the first-release claim. |
| Runtime protection / fault-injection tests | `tests/test_runtime_protection.py`, `tests/test_fault_injection_accounting.py` | Physical runtime braking and fault-handling behavior | Product/runtime | Partial | Medium | No | None unless physical runtime protection is brought into release scope. |
| Broad reliability tests | `tests/reliability/*` | Crash recovery, idempotency, concurrency, and runtime fault tolerance | Product/runtime | Partial | Medium | No | None unless runtime fault tolerance becomes a first-release claim. |
| Broad security hardening tests | `tests/security/*` | Adversarial robustness, resource hardening, and redaction guarantees | Product/runtime | Partial | Medium | No | None unless the initial release claim explicitly includes these security guarantees. |

### Minimum run order under the current scope

1. Run the **cheap preflight / integrity** rows first.
2. If ancestry, scope, partition, or authorization checks fail, **stop**.
3. Run only the remaining `Required = Yes` rows needed to preserve:
   - final-validation integrity;
   - frozen artifact reproducibility; and
   - clean-room package verification.
4. Do **not** reopen broad controller comparison, CARLA expansion, or runtime-hardening test
   runs unless the release decision itself changes.
