# Phase V-B Development Comparison Report

**Stage:** development  
**Outcome:** development_completed_no_selection  
**Selected controller:** none (null)  
**Selection-validation:** NOT EXECUTED  
**Final-validation:** LOCKED AND NOT EXECUTED  

---

## Protocol

- Protocol ID: `phase5b-selection-v1`
- Protocol hash: `fc6b86912182d216be4d381992732345cc5d6a38299d6c5946ab1b8fe2bfe77c`
- Phase revision: `phase5b`
- Implementation commit: `6aa56a7abae975274e95a9ba2941fe2002794592`
- Source commit: `02e06ce09d216d9217e7deab5c85e2c7c95a3acc`
- Development trials per family: 1200
- Total trial rows: 86400

---

## Integrity and Safety Diagnostics

All integrity checks passed: **YES**

---

## Candidate Metrics (descriptive — no selection applied)

| Candidate | Mean Utility | Recovery Rate | Mean Cost | Mean Harm | Unsafe% | Evidence% | Oracle Regret |
|-----------|-------------|---------------|-----------|-----------|---------|-----------|---------------|
| qrtc | 0.4052 | 0.6279 | 4.3221 | 0.0262 | 0.0000 | 0.2500 | 0.1045 |
| qrtc_no_abstention | 0.0850 | 0.3142 | 3.4610 | 0.2245 | 0.0000 | 0.0000 | 0.4248 |
| qrtc_untyped | 0.2222 | 0.4621 | 4.6527 | 0.0291 | 0.0000 | 0.2500 | 0.2876 |
| greedy_gain | -0.0025 | 0.3142 | 4.2110 | 0.2245 | 0.2500 | 0.0000 | 0.5123 |
| oracle | 0.5098 | 0.6649 | 3.0707 | 0.0063 | 0.0000 | 0.0000 | 0.0000 |

---

## Paired Bootstrap Comparisons (non-selective development diagnostics)

Strongest deployable non-oracle comparator: **qrtc_untyped**

All superiority intervals below are **non-selective development diagnostics**.  
They do NOT constitute a selection decision.  No controller has been selected.

| Comparison | Mean Δ | CI low | CI high |
|------------|--------|--------|---------|
| qrtc vs greedy_gain | 0.4078 | 0.3990 | 0.4163 |
| qrtc_no_abstention vs greedy_gain | 0.0875 | 0.0839 | 0.0908 |
| qrtc_untyped vs greedy_gain | 0.2247 | 0.2162 | 0.2331 |
| qrtc vs qrtc_untyped | 0.1831 | 0.1750 | 0.1921 |
| qrtc_no_abstention vs qrtc_untyped | -0.1372 | -0.1444 | -0.1301 |
| greedy_gain vs qrtc_untyped | -0.2247 | -0.2331 | -0.2162 |

---

## Authoritative Statements

1. This is a **development comparison only**.  No controller has been selected.
2. **Selection-validation has not been executed.**
3. **Final-validation is locked and has not been executed.**
4. No provisional winner has been declared.
5. The next stage (selection-validation) requires separate user authorization.
