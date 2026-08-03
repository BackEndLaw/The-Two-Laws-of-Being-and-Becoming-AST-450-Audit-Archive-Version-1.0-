# Phase V-B Selection-Validation — Reproducibility Verification

**Protocol:** `phase5b-selection-v1`  
**Stage:** selection-validation  
**Outcome:** `provisional_selection`  
**Selected controller:** `qrtc`

---

## Verification Summary

The Phase V-B selection-validation run was executed **twice** in separate processes with
distinct `PYTHONHASHSEED` values and produced byte-identical canonical artifacts.

| Property | Value |
|----------|-------|
| Run 1 PYTHONHASHSEED | 42 |
| Run 2 PYTHONHASHSEED | 999 |
| Canonical files checked | 10 |
| Byte-identical files | 10 |
| **Reproducibility result** | **PASSED** |

---

## Canonical File Hashes (Run 1 — committed)

Run 2 produced byte-identical values for every file listed below.

```
efbe62460d5ec2a769d64e6f9a83596d4375e78e9f0d52164452695262b84e88  selection_result.json
88c50adb7744b992f5c5714029f611c3a6850094ccffeee04c367efa7f425504  candidate_metrics.json
6378ea6c545dc424c8ade51e5a9c1c272fce07ff1745587a6e6d6ac3b3bad4aa  candidate_metrics.csv
6bfcf1cc4eafbd8851aa57b7b895ea812d3c6750ab13be7233f1f335ce32d5a0  family_metrics.json
b5637eb98de49ec450fa3235ea0ca826b391f3a6b5d2e0aa9441c1fd949d58c6  eligibility_report.json
4f7b05a7eebff3632872e8772ad8165ef7c5377915dbf2a700612cdde886534f  paired_comparisons.json
b1cc3d583e651d4434f576c8c86f1ee083fc5622f9b1c6f6f0e978090246aca4  phase5_runs.csv
7a20a04e83e803474e660d7117a7d3d738f5da6ce8775f75115eeb37f59046c0  selection_validation_manifest.json
08f080983a87789ce819f1e6575bb9d1ca23c12574647226380e260d60bbc609  run_manifest.json
80bb57e79348be6b86f6c72e98bc1981863fba7198cad92c27f9043fbd6505e2  SELECTION_VALIDATION_REPORT.md
```

---

## Source and Protocol

- **Source commit:** `bec2f2c7781f8ad357262b6357841ddf6e6abfb4`
- **Protocol ID:** `phase5b-selection-v1`
- **Protocol hash:** `fc6b86912182d216be4d381992732345cc5d6a38299d6c5946ab1b8fe2bfe77c`
- **Implementation commit:** `6aa56a7abae975274e95a9ba2941fe2002794592`

---

## Authoritative Statements

1. The executed stage was **selection-validation only** under the frozen preregistered protocol.
2. Any selected controller is **provisional only** and requires separate authorization before final-validation.
3. **Oracle is non-deployable** and was never eligible to win.
4. **Final-validation remained locked and was not executed.**
5. No hardware authority was granted.
6. Run 2 artifacts are not committed; only the canonical Run 1 artifacts are included.
