# Phase IV-B Held-Out Validation and Locked Test Report

Date: 2026-07-28

## Protocol Summary

- Development scaffold completed prior to held-out comparison.
- Competitive baselines evaluated on matched trials: `qrtc`, `end_to_end`, `greedy_gain`, `cheapest_first`, `highest_stage_posterior`, `random`, `oracle`.
- Benchmark freeze records:
  - commit pin: `artifacts/phase4b/commit.txt`
  - config checksum: `artifacts/phase4b/config.sha256`
  - policy checksum: `artifacts/phase4b/policy_code.sha256`
  - release checksum bundle: `artifacts/phase4b/release_checksums.sha256`

## Fresh Validation (Held-Out)

Source artifacts:

- `artifacts/phase4b/validation_fresh/validation/phase4b_metrics.json`
- `artifacts/phase4b/validation_fresh/validation/validation_comparison_table.csv`
- `artifacts/phase4b/validation_fresh/validation/validation_decision.json`

Primary comparison statistic (matched-trial paired analysis):

- strongest non-oracle policy: `greedy_gain`
- $\Delta U = \bar{U}_{QRTC} - \bar{U}_{strongest\ nonoracle} = 0.065625$
- paired 95% CI: $[0.059745,\ 0.071505]$
- matched pairs: $n=512$

Validation decision:

- **Pass** (delta positive and paired CI excludes zero).

Validation policy ranking by mean utility:

1. `oracle`: 0.8375
2. `qrtc`: 0.8375
3. `greedy_gain`: 0.771875
4. `end_to_end`: 0.509375
5. `highest_stage_posterior`: 0.4875
6. `cheapest_first`: -0.065625
7. `random`: -0.134765625

## Locked Held-Out Test (One-Time)

Source artifacts:

- `artifacts/phase4b/test_locked/test/phase4b_metrics.json`
- `artifacts/phase4b/test_locked/test/test_comparison_table.csv`
- `artifacts/phase4b/test_locked/test/locked_test_decision.json`

Primary claim statistic (matched-trial paired analysis):

- strongest non-oracle policy: `greedy_gain`
- $\Delta U = \bar{U}_{QRTC} - \bar{U}_{strongest\ nonoracle} = 0.075000$
- paired 95% CI: $[0.070667,\ 0.079333]$
- matched pairs: $n=1152$

Locked-test claim:

- **Supported**: $\bar{U}_{QRTC} > \bar{U}_{strongest\ nonoracle}$ on locked held-out trials, with CI excluding zero above.

Locked-test policy ranking by mean utility:

1. `oracle`: 0.8395833333333332
2. `qrtc`: 0.8395833333333332
3. `greedy_gain`: 0.7645833333333333
4. `end_to_end`: 0.5041666666666668
5. `highest_stage_posterior`: 0.4791666666666667
6. `cheapest_first`: 0.0125
7. `random`: -0.14375

## Reproducibility Note

All reported values are derived from frozen benchmark code/configuration and matched-trial paired comparisons saved in the listed artifact files.