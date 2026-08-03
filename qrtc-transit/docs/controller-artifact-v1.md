# Controller Artifact v1 (`rescueos-controller-v1`)

This artifact freezes a controller identity for pre-selection workflows (default `protocol_id`: `phase5b-selection-vNext`). It is not a completed selection result.

## Manifest fields

```json
{
  "artifact_schema": "rescueos-controller-v1",
  "controller_id": "qrtc",
  "controller_version": "phase5b-rule-policy-v1",
  "implementation_commit": "<40-char commit SHA>",
  "protocol_id": "phase5b-selection-vNext",
  "causal_schema_sha256": "<64 lowercase hex>",
  "action_catalog_sha256": "<64 lowercase hex>",
  "configuration_sha256": "<64 lowercase hex>",
  "implementation_sha256": "<64 lowercase hex>",
  "authority": "recommend_only",
  "hardware_actuation_enabled": false
}
```

## Canonicalization and hash coverage

- Canonical JSON bytes: UTF-8, sorted keys, separators `(',', ':')`, no path-dependent fields.
- `causal_schema_sha256`: canonical payload containing Phase V-B families, relation types, dependency types, and unknown-fault support.
- `action_catalog_sha256`: canonical payload containing action IDs and base intervention costs.
- `configuration_sha256`: canonical payload containing controller ID/version, role, deployability, authority, and fixed `hardware_actuation_enabled=false`.
- `implementation_sha256`: canonical payload containing controller ID/version, implementation module identity, and SHA-256 of stable `src/qrtc_benchmark/controllers.py` source bytes.

Repeated generation with identical inputs produces byte-identical manifests across directories/processes.

## Freeze API / CLI

- Python API: `freeze_controller_artifact(...)`
- CLI:

```text
qrtc-controller freeze \
  --controller qrtc \
  --implementation-commit <40-char-lowercase-sha> \
  --protocol-id phase5b-selection-vNext \
  --output controller.json
```

Safety/behavior:
- unknown controller IDs are rejected;
- full lowercase 40-char commit SHA is required;
- no overwrite unless `--overwrite` is supplied;
- writes are atomic (`os.replace` from same-directory temp file);
- deployable mode (`--deployable-only`) rejects non-deployable controllers (for example `oracle`).

## Loader fail-closed behavior

`load_controller_artifact(...)` rejects and returns no usable controller when any of the following is invalid:

- schema mismatch;
- unknown/missing/extra fields;
- unknown controller ID;
- controller version mismatch;
- bad commit/hash formats;
- authority not `recommend_only`;
- `hardware_actuation_enabled` not `false`;
- recomputed causal/action/configuration/implementation hash mismatch;
- non-deployable controller in deployable-only mode;
- oracle without explicit `allow_oracle=True`.

No API in this artifact flow performs intervention/hardware actuation.
