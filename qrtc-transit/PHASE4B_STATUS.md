# Phase IV-B Status: Historical / Unsupported

## Summary

`qrtc_benchmark/phase4b.py` is a **historical implementation** of the Phase IV-B
controller-selection benchmark. It is preserved as a read-only record, has no
packaged console entry point, and remains **unsupported** for new workflow
development. The preserved module and tests are still importable/runnable for
archival verification.

## Why Phase IV-B Remains Unsupported

`phase4b.py` imports `qrtc_benchmark.specification.CriterionId`, which was the
authoritative module defining the criterion-ID enumeration used in Phase IV-B
pair specifications.  That module was absent from the repository's `main` branch.

A **minimal stub** (`qrtc_benchmark/specification.py`) has been added to allow
`phase4b.py` to be imported without a `ModuleNotFoundError`. The stub recovers
only the three `CriterionId` members (`PI1`, `PI2`, `PI3`) that are referenced
explicitly in `DEFAULT_PHASE4B_PAIRS` — no new semantics have been invented.

## Protected Artifacts

The following Phase IV-B artifacts are **frozen and read-only**.  Do not modify,
regenerate, delete, or overwrite them:

```
qrtc-transit/artifacts/phase4b/
├── PHASE4B_FINAL_INTEGRITY_CHECKS.md
├── PHASE4B_VALIDATION_LOCKED_TEST_REPORT.md
├── commit.txt
├── development-v2/
├── test_locked/
├── validation-v1-failed/
└── validation_fresh/
```

## No Packaged Console Entry Point

Phase IV-B has no `[project.scripts]` entry in `pyproject.toml`.  The commands
`qrtc-benchmark-phase1` through `qrtc-benchmark-phase4` have been removed because
their runner modules (`run_phase1.py` … `run_phase4.py`) are absent from the
codebase.  Do not restore them without also restoring or correctly implementing
the underlying runner modules.

## Next Steps

If Phase IV-B is ever to regain supported workflow status, its authoritative
`specification.py` module must be recovered from repository history and verified
against the `PHASE4B_FINAL_INTEGRITY_CHECKS.md` checksums. This work belongs in
a dedicated follow-on PR — not in the Phase V reproducibility / package-repair
PR.
