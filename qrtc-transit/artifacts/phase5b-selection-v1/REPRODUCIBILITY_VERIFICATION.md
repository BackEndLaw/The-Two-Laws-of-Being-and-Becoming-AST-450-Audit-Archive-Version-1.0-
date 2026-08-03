# Phase V-B Development Comparison — Reproducibility Verification

**Protocol:** `phase5b-selection-v1`  
**Stage:** development  
**Outcome:** `development_completed_no_selection`  
**Selected controller:** none (null)

---

## Verification Summary

The Phase V-B development comparison was executed **twice** in separate processes with
varied `PYTHONHASHSEED` values to verify byte-for-byte determinism.

| Property | Value |
|----------|-------|
| Run 1 PYTHONHASHSEED | 42 |
| Run 2 PYTHONHASHSEED | 999 |
| Canonical files checked | 8 |
| Byte-identical files | 8 |
| **Reproducibility result** | **PASSED** |

---

## Canonical File Hashes (Run 1 — committed)

These are the SHA-256 hashes of all canonical artifacts in `development-run-1/`.
Run 2 produced byte-identical values for all files listed below.

```
491f30cc57bf3f0e628fd6f6c418394591e5e32f527a23d29a1327050cd1ce9d  development_result.json
78c21170f58f11fb074710b80158e0e18649fa26559ce1a84989222ce914d4ce  candidate_metrics.json
dbf3cc59da1ce27bffae145b40c45389f9cd79a3f9952e8f48f41f3716df9964  candidate_metrics.csv
4975cf206ded62455be8515a8d9f1cd88007b0863b62c9421cc0005a890967b1  family_metrics.json
2c388a35433665857655c4bb7601e799b337c426300623e35996b562f9c2dde5  paired_comparisons.json
e55dd1e0707060b256ed6052b53c85159685b2ca66d5b7dfba0f5f012dcf1f16  phase5_runs.csv
98cb6c5b86fa0a4c1facbe59733b2ade33467cb2cf8c2b322f9d00dad18d4bc2  development_manifest.json
8d9289f2014930e56b25fb58495ff58e717cbf554a3947656a702a13bb8b7d58  run_manifest.json
```

---

## Determinism Note

Phase V-B uses `_stable_hash()` (SHA-256 based, domain-separated) instead of Python's
built-in `hash()` for all experiment-affecting random selections.  Python's `hash()` is
randomised per-process via `PYTHONHASHSEED` and would produce non-reproducible results.
The Phase V-B implementation eliminates this dependency, guaranteeing byte-identical
outputs regardless of `PYTHONHASHSEED`.

---

## Source and Protocol

- **Source commit:** `02e06ce09d216d9217e7deab5c85e2c7c95a3acc`
- **Protocol ID:** `phase5b-selection-v1`
- **Protocol hash:** `fc6b86912182d216be4d381992732345cc5d6a38299d6c5946ab1b8fe2bfe77c`
- **Implementation commit:** `6aa56a7abae975274e95a9ba2941fe2002794592`

---

## Authoritative Statements

1. This is a **development comparison only**.
2. **No controller has been selected.**
3. **Selection-validation has NOT been executed.**
4. **Final-validation is LOCKED and has NOT been executed.**
5. Run 2 artifacts are not committed; only the canonical Run 1 artifacts are included.
