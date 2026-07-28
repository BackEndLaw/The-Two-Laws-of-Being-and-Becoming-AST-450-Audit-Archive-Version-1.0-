# Phase V Plan: OOD and Physical Transfer

Date: 2026-07-28
Status: scaffold

## Objective

Demonstrate that QRTC policy superiority generalizes beyond Phase IV-B distribution and remains operational under hardware-realistic conditions, culminating in a physical LED-channel-detector experiment.

## Entry Criteria

- Phase IV-B validation passed on fresh held-out split.
- Phase IV-B locked test completed once with superiority claim supported.
- Freeze records available for Phase IV-B release artifacts.

## Workstreams

## 1) OOD Fault Composition

- Unseen fault-pair combinations not used in prior development/validation/test manifests.
- Three-fault combinations with predefined interaction templates (masking, independent, synergistic mixtures).
- Unknown-fault cases requiring abstention or evidence-request behavior.

Deliverables:

- `artifacts/phase5/ood_pair_manifest.json`
- `artifacts/phase5/ood_triplet_manifest.json`
- `artifacts/phase5/unknown_fault_manifest.json`

## 2) Shifted Severity and Noise

- Severity shifts beyond Phase IV-B grid, including tail values.
- Noise shifts with distributional drift and heteroskedastic regimes.
- Stress slices targeting calibration and intervention-cost sensitivity.

Deliverables:

- `artifacts/phase5/shifted_severity_noise_manifest.json`
- `artifacts/phase5/shifted_metrics_summary.csv`

## 3) Abstention and Safety Behavior

- Define abstention trigger criteria and acceptable abstention rates under unknown faults.
- Evaluate harm, false-order, and missed-recovery under abstain-enabled policies.
- Compare QRTC against non-oracle baselines under identical OOD splits.

Deliverables:

- `artifacts/phase5/abstention_policy_spec.md`
- `artifacts/phase5/abstention_eval_results.csv`

## 4) Hardware-in-the-Loop (HIL) Simulation

- Introduce timing jitter, sensor noise, channel perturbations, and actuator delays.
- Preserve frozen policy and tie-break logic during HIL evaluation.
- Estimate degradation bands versus software-only OOD performance.

Deliverables:

- `artifacts/phase5/hil_config.yaml`
- `artifacts/phase5/hil_results.csv`

## 5) Physical Transfer Experiment

- Build LED-channel-detector setup with controlled fault injection.
- Execute locked physical trial manifest once per release.
- Report outcomes without post-test tuning.

Deliverables:

- `artifacts/phase5/physical_protocol.md`
- `artifacts/phase5/physical_manifest.json`
- `artifacts/phase5/physical_results.csv`

## Metrics and Decision Rules

Primary comparison for each Phase V bundle:

$$
\Delta U = \bar{U}_{QRTC} - \bar{U}_{strongest\ nonoracle}
$$

Requirements:

- Positive $\Delta U$ with paired 95% CI excluding zero on matched trials.
- Harm and false-order rates within predefined safety bounds.
- Abstention behavior within policy bounds when unknown faults are present.

## Data Governance

- Any inspected validation-like split is reclassified as development-used.
- Fresh held-out manifests required after redesigns.
- One-time locked evaluations per release for OOD bundle and physical bundle.

## Milestones

1. Define OOD manifests and abstention spec.
2. Run software OOD benchmark bundle.
3. Run HIL bundle with frozen policy.
4. Execute locked physical manifest once.
5. Publish consolidated Phase V report.