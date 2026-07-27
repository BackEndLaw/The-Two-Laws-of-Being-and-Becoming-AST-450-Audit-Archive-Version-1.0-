# Release Notes

## QRTC Transit 0.1.0-rc1 (local release candidate)

QRTC Transit is a local reference implementation for versioned, modeled digital transitions.
Its adequacy conclusions apply only to the declared finite model.
Its simulated River does not prove physical one-way enforcement, and its evidence chain provides tamper evidence rather than proof that observations were truthful.

### Scope

- Versioned policy validation and deterministic policy digest binding.
- Registry snapshot identity binding for resolved components.
- Evidence persistence with hash-chain verification.
- Typed failure handling and CLI exit-code mapping.
- Recovery and idempotency decision primitives for restart safety.
- Property, reliability, and adversarial validation suites.

### Residual Risks

- This project is not production security certification.
- Host compromise and full database plus anchor replacement are out of scope.
- Independent review and deployment-specific threat analysis remain required before production use.
