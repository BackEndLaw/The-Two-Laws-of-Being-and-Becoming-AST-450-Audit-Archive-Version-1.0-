# Phase IV-B Final Integrity Checks

Date: 2026-07-28

## Lineage Archive (Closed)

```
artifacts/phase4b/
├── validation-v1-failed/
├── development-v2/
├── validation_fresh/
├── test_locked/
├── frozen_config.yaml
├── commit.txt
└── checksums.sha256
```

## Explicit Provenance Statements

1. The first validation failed.
   - Evidence: `validation-v1-failed/validation_decision.json` (`validation_decision = fail`, `ΔU = -0.028125`).
2. The failed validation was not reused for final confirmation.
   - Evidence: final confirmation uses `validation_fresh/` and `test_locked/` artifacts.
3. Policy changes were developed using development evidence.
   - Evidence: redesign rationale documented in release report; fresh validation generated after redesign.
4. A fresh validation split was generated.
   - Evidence: `validation_fresh/validation/manifest.json` and `validation_fresh/validation/validation_decision.json`.
5. The revised policy passed fresh validation.
   - Evidence: `validation_fresh/validation/validation_decision.json` (`validation_decision = pass`).
6. Code and configuration were frozen.
   - Evidence: `commit.txt`, `frozen_config.yaml`, `checksums.sha256`.
7. The locked test was executed once in the finalized flow.
   - Evidence: single locked-test artifact bundle in `test_locked/test/` with decision file.
8. No post-test tuning occurred in the finalized release flow.
   - Evidence: locked-test decision and release commit were produced before closure reporting.

## Paired Interval Method Record (Locked Test)

Source: `interval_method_locked_test.json`

- Matched test trials: `n = 1152`
- Trial-level difference:
  - $d_i = U_{QRTC,i} - U_{greedy,i}$
- Comparator: `greedy_gain`

Deterministic paired CI (normal approximation):

- $\Delta U = 0.075000$
- $CI_{95\%} = [0.070667, 0.079333]$

Bootstrap records:

- Trial-level percentile bootstrap:
  - resampling unit: matched trial pairs
  - resamples: 10,000
  - seed: 20260728
  - CI: `[0.070747, 0.079253]`
- Clustered bootstrap by seed:
  - resampling unit: seed clusters
  - clusters: 3
  - resamples: 10,000
  - seed: 20260728
  - CI: `[0.075000, 0.075000]`
- Clustered bootstrap by configuration:
  - resampling unit: `(pair, relation_type, severity, noise)` clusters
  - clusters: 384
  - resamples: 10,000
  - seed: 20260728
  - CI: `[0.067448, 0.082552]`

## Success Conditions: Published Evidence

Primary policy table:

- `test_locked/test/test_comparison_table.csv`

Contains (including required items):

- recovery rate
- mean intervention cost
- harm rate
- oracle regret

Additional required diagnostics:

- first-action validity and false-order rate by relation type:
  - `locked_test_relation_type_comparison.csv`
- performance by relation type:
  - `locked_test_relation_type_comparison.csv`
- performance by noise:
  - `locked_test_noise_comparison.csv`
- performance by severity:
  - `locked_test_severity_comparison.csv`
- performance on unseen fault pairs:
  - `locked_test_unseen_pair_comparison.csv`

## Utility Decomposition

Source: `test_locked_delta_decomposition.json`

- $\Delta U = \Delta A_{recover} - \lambda \Delta C - \beta \Delta H$
- with $\lambda = 0.05$, $\beta = 0.25$:
  - $\Delta A_{recover} = 0.0$
  - $\Delta C = -1.5$
  - $\Delta H = 0.0$
  - implied $\Delta U = 0.075000$

Interpretation: locked-test utility gain is explained by lower intervention cost at equal recovery/harm versus `greedy_gain`.