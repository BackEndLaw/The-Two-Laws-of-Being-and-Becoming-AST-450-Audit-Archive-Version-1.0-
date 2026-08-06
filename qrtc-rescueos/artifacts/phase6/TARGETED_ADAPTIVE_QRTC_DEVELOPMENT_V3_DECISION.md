# Targeted Adaptive QRTC Development v3 Decision

**Development acceptance: DO NOT ADVANCE.**

- Preregistered protocol commit: `3912547`
- Finite calibration reporting correction: `d23031a`
- Primary policy: `conservative_hybrid_qrtc`
- Primary comparator: `hybrid_qrtc_v2`, selected as the strongest non-oracle over the complete LOFO development run
- Matched trials per policy: `128`
- Independent clusters: `16`, balanced as four per family
- Family-stratified bootstrap: `2,000` resamples, seed `2450`
- `validation_authorized: false`
- `hardware_actuation_enabled: false`
- `hardware_gate: NOT READY`

## Primary result

The conservative temporal residual policy did not improve aggregate utility over the strongest comparator:

`delta_u = -0.009414`, 95% paired interval `[-0.051523, 0.032773]`.

The interval was sufficiently precise, but neither the point estimate nor lower bound was positive.

## Family transfer

| Held-out family | Delta U | 95% interval | Decision |
|---|---:|---:|---|
| clock drift | +0.122031 | [0.036563, 0.253125] | improved |
| burst attenuation | -0.001562 | [-0.004687, 0.000000] | no improvement |
| gain dropout | -0.076250 | [-0.190156, -0.008906] | regressed |
| phase coupling | -0.081875 | [-0.163750, 0.000000] | no improvement |

## Clock-drift diagnosis

The targeted correction resolved the v2 clock-drift calibration failure:

- graph Brier: `0.252267`;
- conservative Brier: `0.216858`;
- Brier improvement: `0.035409`;
- ECE: `0.085985`;
- recovery: `1.0`;
- first-action oracle agreement: `0.90625`;
- evidence-request rate: `0.09375`;
- stopping rate: `0.0`;
- unsafe rate: `0.0`.

The clock-drift v2 failure was therefore consistent with residual bias and overuse of evidence, not graph coverage or insufficient willingness to act. Public temporal response features plus support-aware shrinkage corrected that family without a family label.

## Remaining failure

Calibration improved in all four families and all calibration limits passed. The development gate remains closed because aggregate advantage was negative and benefit was not broadly distributed. Gain dropout and phase coupling still triggered evidence on every trial and lost utility through lower recovery and higher cost relative to v2 hybrid.

This result does not freeze the policy or authorize validation or hardware activation.