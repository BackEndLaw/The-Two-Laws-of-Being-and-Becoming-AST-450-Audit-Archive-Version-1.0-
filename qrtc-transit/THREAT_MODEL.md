# Threat Model

## Protected Assets

- Transit outcome integrity.
- Policy identity and version traceability.
- Evidence event history.
- Redacted handling of sensitive fields.

## Trust Boundaries

- Policy and input files are untrusted until validated.
- Registry content is trusted only after startup snapshot binding.
- Destination and delivery are external side-effect boundaries.

## Adversaries Considered

- Hostile predecessor input.
- Malformed or malicious policy files.
- Unauthorized policy substitution.
- Compromised registered components.
- Payload tampering and replay attempts.
- Concurrent writers and crash interruption.
- Evidence database mutation.
- Resource exhaustion.

## Non-Goals

- Host root compromise protection.
- Physical hardware-enforced one-way channels.

## Security Semantics

tamper-evident evidence != truthful evidence != tamper-proof storage.

A valid hash chain indicates internal consistency with the stored sequence and trust anchor. It does not, by itself, prove truth of original observations.