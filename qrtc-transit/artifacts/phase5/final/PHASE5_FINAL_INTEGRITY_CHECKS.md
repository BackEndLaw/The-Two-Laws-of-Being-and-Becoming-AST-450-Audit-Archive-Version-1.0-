# Phase V Final Integrity Checks

## Execution lineage

- Validation split executed first and passed.
- Lock snapshot captured before test run:
	- `artifacts/phase5/commit.txt`
	- `artifacts/phase5/checksums.sha256`
- Locked test split executed once after successful validation.

## Locked test primary result

- Strongest non-oracle comparator: qrtc_untyped
- Primary delta (QRTC - qrtc_untyped): 0.175939
- Paired cluster-bootstrap CI: [0.166435, 0.185157]
- Matched trials: 9216
- Configuration clusters: 7930

## Domain and safety checks

- Unknown-fault AUROC (QRTC): 1.000000
- Unknown-fault AUPRC (QRTC): 1.000000
- Triple-fault recovery (QRTC): 0.875868
- Triple-fault recovery (strongest baseline): 0.496962
- Harm rate (`Hwrong`): 0.027995

## Criteria status

- Primary superiority criterion: pass
- No catastrophic domain failure criterion: pass
- Unknown-fault detection criterion: pass
- Triple-fault recovery criterion: pass
- Moderate intervention uncertainty criterion (`p_success <= 0.80`): pass
- Harm criterion (`Hwrong < 0.05`): pass
- Strict unsafe-rate inequality criterion (`Runsafe_QRTC < Runsafe_best_baseline`): not strictly satisfied because both rates are 0.0 (tie)
