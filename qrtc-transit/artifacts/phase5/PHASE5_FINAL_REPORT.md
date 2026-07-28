# Phase V Result: Primary Success, Strict Composite Gate Not Fully Met

## Completion summary

- Phase V-A tests: 18 passed
- Development trials: 9,600
- Locked-test matched trials: 9,216
- Locked-test clusters: 7,930

## Main results

- Strongest non-oracle: `qrtc_untyped`
- Development delta utility: +0.183198
- Validation delta utility: +0.171031
- Locked OOD delta utility: +0.175939
- Locked 95% cluster-bootstrap CI: [0.166435, 0.185157]
- Unknown-fault AUROC: 1.000
- Triple-fault recovery, QRTC: 0.875868
- Triple-fault recovery, strongest baseline: 0.496962
- Utility advantage at `p_success <= 0.80`: +0.106738
- Wrong-intervention harm: 0.027995
- Unknown-fault unsafe rate: 0.000 vs 0.000

Primary locked-test estimate:

`Delta_U_OOD = 0.1759386`

with

`CI_95 = [0.1664349, 0.1851574]`.

QRTC therefore outperformed the strongest evaluated non-oracle comparator on aggregate locked OOD utility.

## Triple-fault advantage

QRTC triple-fault recovery advantage over `qrtc_untyped`:

`0.8758681 - 0.4969618 = 0.3789063`

This supports a contribution from typed structure beyond generic utility optimization.

## Formal decision

Preregistered unsafe-rate condition:

`R_unsafe,QRTC < R_unsafe,best`

Observed:

`0 < 0` is false.

Literal decision:

Primary Phase V efficacy claim passes, but the full composite success gate does not.

Interpretation:

- This is a floor-effect tie (`R_unsafe,QRTC = R_unsafe,best = 0`), not evidence of worse safety.
- The strict inequality rule is preserved unchanged after locked inspection.

## Recommended final claim

On 9,216 matched locked OOD trials, QRTC exceeded the strongest non-oracle comparator, `qrtc_untyped`, by 0.175939 mean utility, with paired cluster-bootstrap 95% CI [0.166435, 0.185157]. The advantage replicated fresh validation, remained positive under moderate intervention uncertainty, and included higher triple-fault recovery. Unknown-fault AUROC was 1.0, wrong-intervention harm was below 0.05, and neither QRTC nor the strongest baseline made an unsafe unknown-fault intervention. Because the preregistered safety criterion required strict superiority rather than a zero-rate tie, the primary efficacy claim passed but the complete composite gate was not literally satisfied.

## Next benchmark direction: Phase V-B safety discrimination

- Prefer a safety noninferiority gate if the intended claim is preserved safety with utility gain.
- Increase unknown-fault challenge difficulty to avoid repeated zero-event floors.
- Report event-sensitive confidence intervals for unsafe rates even when event count is zero.

## Closure status

Phase V primary OOD claim passed strongly; one strict safety-superiority criterion tied at the zero-event floor.