# Routed Adaptive QRTC Development v4 Decision

**Development acceptance: DO NOT ADVANCE. Experimental series: STOPPED.**

- Preregistration and implementation commit: `7bd08ae`
- One-shot evidence and final decision commit: `bf1276e`
- Primary policy: `routed_hybrid_qrtc_v4`
- Frozen comparator: `hybrid_qrtc_v2`
- Positive mechanism families: `0`
- Router activation: none
- Tests: `70/70` passed
- Checksums: verified
- `validation_authorized: false`
- `hardware_actuation_enabled: false`
- `hardware_gate: NOT READY`

## Primary result

The preregistered router produced no utility improvement over frozen v2:

`delta_u_v4_minus_v2 = 0.0`, 95% paired interval `[0.0, 0.0]`.

The router never activated and used the v2 fallback on every fresh trial. V4 was
therefore behaviorally identical to v2 in this evaluation. This is not evidence
that the routing strategies are equivalent. It shows that the preregistered
positive-LCB activation rule was too conservative under the evaluated data.

## Reporting correction

The immutable one-shot result reported the graph-validity check as false because
the reporting predicate incorrectly required `inspect_receiver` to appear in the
repair candidate map. All 128 v4 first actions were this registered, graph-safe
evidence action.

The one-shot artifact was retained unchanged. The checksum-bound JSON decision
record reclassifies the evidence action as graph-valid and documents the reason.
This reporting correction does not change non-acceptance.

## Series conclusion

The development series established the following:

- **V1:** causal reachability was correct, but severe miscalibration caused
  systematic stopping.
- **V2:** adaptive residual learning produced strong aggregate gains with uneven
  family transfer.
- **V3:** the temporal specialist repaired clock drift without labels but harmed
  other families.
- **V4:** conservative routing prevented those harms by never activating, but
  delivered no improvement.

A safe specialist router needs better uncertainty discrimination, not post hoc
threshold relaxation. Under the frozen one-shot failure policy, this experimental
series is closed without tuning or rerunning v4.

Any continuation must begin as a new experimental program with fresh mechanisms,
a redesigned uncertainty model, and a new preregistration. It must not be treated
as a v4 threshold adjustment.

## Final status

V4 is not accepted. Validation is unauthorized. Hardware actuation remains
disabled and the hardware gate remains `NOT READY`.