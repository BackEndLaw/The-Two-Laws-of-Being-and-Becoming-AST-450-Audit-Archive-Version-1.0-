# QRTC Transit

Formal kernel for QRTC Transit analysis.

This project compares an implemented Gate against a declared future family and classifies the relationship as exact, insufficient, excessive, or incomparable.

## CI and Dependency Audit

- Quality gates run on push and pull request for transit changes via [../.github/workflows/qrtc-transit-ci.yml](../.github/workflows/qrtc-transit-ci.yml).
- A scheduled dependency audit runs weekly (and can be run manually) via [../.github/workflows/qrtc-transit-audit.yml](../.github/workflows/qrtc-transit-audit.yml).

### Viewing Audit Artifacts

1. Open the repository Actions tab.
2. Select the "QRTC Transit Dependency Audit" workflow run.
3. Open the run artifacts named `qrtc-transit-pip-audit-<run_id>`.
4. Download and review:
	- `pip-audit.json`
	- `pip-audit-summary.md`

## Phase V-B Benchmark Navigation

The following links allow a reviewer to trace the complete Phase V-B chain.

| Document | Path |
|----------|------|
| Preregistered protocol | [artifacts/protocols/phase5b-selection-v1/preregistration.json](artifacts/protocols/phase5b-selection-v1/preregistration.json) |
| Development report | [artifacts/phase5b-selection-v1/development-run-1/DEVELOPMENT_REPORT.md](artifacts/phase5b-selection-v1/development-run-1/DEVELOPMENT_REPORT.md) |
| Selection-validation report | [artifacts/phase5b-selection-v1/selection-validation-run-1/SELECTION_VALIDATION_REPORT.md](artifacts/phase5b-selection-v1/selection-validation-run-1/SELECTION_VALIDATION_REPORT.md) |
| Final-validation report | [artifacts/phase5b-selection-v1/final-validation-run-1/FINAL_VALIDATION_REPORT.md](artifacts/phase5b-selection-v1/final-validation-run-1/FINAL_VALIDATION_REPORT.md) |
| Closure audit summary | [docs/phase5b_validation_audit_summary.md](docs/phase5b_validation_audit_summary.md) |
| Release notes draft | [docs/releases/phase5b-selection-v1.md](docs/releases/phase5b-selection-v1.md) |
| Closure index (JSON) | [artifacts/phase5b-selection-v1/closure_index.json](artifacts/phase5b-selection-v1/closure_index.json) |
