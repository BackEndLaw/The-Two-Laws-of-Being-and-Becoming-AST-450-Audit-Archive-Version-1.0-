# Security Notes

QRTC Transit is a local reference implementation, not a production-hardened deployment profile.

## Security Posture

- Evidence chains are tamper-evident, not tamper-proof.
- Policy and registry identity are bound to each transit record via canonical digests.
- Resource limits are enforced for policy/input size, depth, guard count, event size, and replay count.
- Default evidence persistence redacts obvious secret-bearing keys.
- Typed product errors are translated to bounded CLI exit codes.

## Non-Goals

- Physical one-way guarantees.
- Host-level compromise resistance.
- Cryptographic signatures or key-management infrastructure.

## Operational Reminder

If an attacker can replace both the evidence database and the trust anchor used to verify it, they may generate a fresh internally consistent chain.