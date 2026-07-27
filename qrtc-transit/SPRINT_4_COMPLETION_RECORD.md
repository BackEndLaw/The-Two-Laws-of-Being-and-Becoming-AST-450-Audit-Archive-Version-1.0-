# Sprint 4 Completion Record

Sprint 4A
- Policy digest: canonical policy bytes and SHA-256 digest are bound to each persisted transit in [src/qrtc/verification.py](src/qrtc/verification.py) and [src/qrtc/evidence_store.py](src/qrtc/evidence_store.py).
- Registry snapshot: deterministic snapshot identity is derived from sorted resolved-component triples in [src/qrtc/verification.py](src/qrtc/verification.py).
- Resource limits: explicit limits and positive-integer validation are implemented in [src/qrtc/limits.py](src/qrtc/limits.py).
- Typed failures: product-level exception hierarchy and CLI translation live in [src/qrtc/exceptions.py](src/qrtc/exceptions.py) and [src/qrtc/cli.py](src/qrtc/cli.py).

Sprint 4B
- Recovery stages: explicit recovery decision mapping is implemented in [src/qrtc/recovery.py](src/qrtc/recovery.py).
- Delivery uncertainty: uncertain delivery state is preserved in [src/qrtc/transit.py](src/qrtc/transit.py) and [src/qrtc/pipeline.py](src/qrtc/pipeline.py).
- Realization idempotency: stage idempotency keying and conflict classification are implemented in [src/qrtc/recovery.py](src/qrtc/recovery.py), persisted in [src/qrtc/evidence_store.py](src/qrtc/evidence_store.py), and surfaced on realization records in [src/qrtc/transit.py](src/qrtc/transit.py).
- Concurrency validation: concurrent transit history checks are covered by [tests/reliability/test_concurrent_transit.py](tests/reliability/test_concurrent_transit.py).

Sprint 4C
- Adequacy property tests: [tests/property/test_kernel_properties.py](tests/property/test_kernel_properties.py).
- Canonical encoding property tests: [tests/property/test_canonical_encoding.py](tests/property/test_canonical_encoding.py).
- Hash-chain adversarial tests: [tests/property/test_hash_chain_properties.py](tests/property/test_hash_chain_properties.py).
- Redaction tests: [tests/security/test_evidence_redaction.py](tests/security/test_evidence_redaction.py).

Sprint 4D
- Type checking: `mypy src`.
- Linting: `ruff check src tests` and `ruff format --check src tests`.
- Build: `python -m build`.
- Clean installation: wheel build and package metadata checks are executed in the build pipeline.
- Dependency audit: `pip-audit .` locally and [../.github/workflows/qrtc-transit-audit.yml](../.github/workflows/qrtc-transit-audit.yml) in CI.
- CI environments: [../.github/workflows/qrtc-transit-ci.yml](../.github/workflows/qrtc-transit-ci.yml).

Validation
- Previous tests preserved: all prior Sprint 1-3 tests remain green.
- New tests: property, security, and reliability suites including identity/limit and recovery additions.
- Total passed: 64 passed.
- Acceptance criteria mapped: see section references above and [tests/integration/test_release_candidate.py](tests/integration/test_release_candidate.py).
- Known limitations: tamper-evident evidence does not, by itself, prove truthful observations or tamper-proof storage; full host compromise remains out of scope.
