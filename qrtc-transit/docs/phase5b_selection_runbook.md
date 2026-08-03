# Phase V-B Controller Selection Protocol v1 — Runbook

**Protocol ID:** `phase5b-selection-v1`
**State:** `preregistered_not_executed`
**Phase revision:** `phase5b`
**Authority:** `recommend_only`

> **This PR executes no experiment and selects no winner.**
> The protocol is preregistered and frozen.  No controller has been selected.
> No final-validation data has been generated.

---

## Candidates

### Mandatory candidates (exact)

| Controller ID | Role | Deployable | Eligible to win |
|---|---|---|---|
| `qrtc` | provisional primary | ✓ | ✓ (if meets gates) |
| `qrtc_no_abstention` | ablation | ✓ | ✓ (if meets gates) |
| `qrtc_untyped` | ablation | ✓ | ✓ (if meets gates) |
| `greedy_gain` | baseline | ✓ | ✓ (if meets gates) |
| `oracle` | oracle | ✗ | **Never** |

- `oracle` is **non-deployable** and **never eligible to win** under any circumstances.
- `qrtc` is identified as **provisional primary only**; it receives no automatic preference.
  If another deployable mandatory candidate is superior under the selection rule, it may
  be selected instead.
- "Hybrid QRTC V2" is not an implemented controller and must not be referenced.

### Optional descriptive baselines (excluded from eligibility)

`end_to_end`, `highest_stage_posterior`, `cheapest_first`, `random` are **not eligible**
and are **excluded from winner selection**.

---

## Utility formula

```
utility = recovery_reward
        - lambda_cost   * intervention_cost
        - beta_harm     * harm
        - gamma_unsafe  * unsafe_commitment
```

**Frozen parameters** (from `Phase5Config`):

| Parameter | Value |
|---|---|
| `lambda_cost` | 0.05 |
| `beta_harm` | 0.25 |
| `gamma_unsafe` | 0.20 |
| `max_actions` | 4 |
| `bootstrap_reps` | 2000 |
| `bootstrap_seed` | 9101 |
| `reliability_levels` | 0.8, 1.0 |
| `cost_regimes` | familiar |

---

## Metric definitions

Each mandatory candidate is reported on:

- **mean utility** — mean of `utility` across all matched trials
- **recovery rate** — fraction of trials where `recovered == True`
- **mean intervention cost** — mean of `intervention_cost`
- **mean harm** — mean of `harm`
- **unsafe-commitment rate** — mean of `unsafe_commitment` (fraction in [0,1])
- **evidence-request / abstention rate** — fraction of trials with `evidence_requested == True`
- **per-family V1–V4 metrics** — all above metrics, broken down by OOD family
- **paired utility delta vs `greedy_gain`** — bootstrap mean + 95% CI
- **paired utility delta vs strongest other deployable mandatory** — bootstrap mean + 95% CI
- **oracle regret** — mean of `oracle_utility - utility`

All rates are in [0.0, 1.0].  Use **matched trial identities only**.

---

## Statistical method — Paired cluster bootstrap

Implemented as a pure typed function in `phase5.cluster_bootstrap_interval`.

- **Resampling unit:** matched scenario/trial cluster preserving all candidate rows.
  Cluster key: `(mechanism_id, composition_id, relation_type, criterion, severity, noise,
  cost_regime, intervention_reliability, seed_family)`.
- **Repetitions:** `bootstrap_reps = 2000` (from `Phase5Config`).
- **Seed:** `bootstrap_seed = 9101` (from `Phase5Config`).
- **Deterministic ordering:** clusters sorted before sampling; `Random(bootstrap_seed)`.
- **Interval type:** two-sided 95% percentile interval.
- **Output:** `mean_difference`, `ci_low`, `ci_high`.
- **Rejects:** missing or duplicate candidate rows.

---

## Stages

### Stage order (must not be skipped)

1. `development` — descriptive / error-detection only; **cannot select a winner**.
2. `selection-validation` — may produce a provisional selection under frozen rules.
3. `final-validation` — **locked and unavailable in this PR**.  Attempting to request
   final-validation execution unconditionally raises a typed `LockedStageError`.

Out-of-order execution, hash drift, incomplete artifacts, or any final-validation request
causes a fail-closed error.

### Stage aliases

| CLI `--split` | Internal name | Canonical name |
|---|---|---|
| `development` | `development` | `development` |
| `validation` | `validation` | `selection-validation` |
| `test` | `test` | `final-validation` |

### Seeds per stage

| Stage | Seeds |
|---|---|
| `development` | 701, 702, 703 |
| `selection-validation` (`validation`) | 751, 752 |
| `final-validation` (`test`) | 801, 802 |

---

## Frozen eligibility gates

A deployable mandatory candidate is **eligible** on selection-validation only when **all
eight gates pass** (evaluated against matched trial data):

| Gate | Condition |
|---|---|
| G1 | No missing or duplicate matched rows |
| G2 | No artifact / hash / protocol mismatch |
| G3 | Overall unsafe-commitment rate **exactly 0.0** |
| G4 | Unsafe-commitment count **zero** in every OOD family |
| G5 | No family recovery-rate **regression > 0.05** absolute vs `greedy_gain` |
| G6 | No family mean-harm **increase > 0.05** absolute vs `greedy_gain` |
| G7 | Overall mean utility **not lower than `greedy_gain` by more than 0.01** |
| G8 | Operational integrity checks pass |

**Thresholds are frozen** — they must not be tuned from results.
The threshold payload is serialised and its SHA-256 is recorded in `eligibility.py`.

---

## Selection rule

### Superiority criterion

A candidate is **superior** when the bootstrap lower bound of its paired utility delta
vs `greedy_gain` is **strictly > 0.0**.

### Ranking (tiebreak order)

Among eligible superior deployable mandatory candidates:

1. Highest **mean utility** (descending)
2. Lowest **unsafe-commitment rate** (ascending)
3. Lowest **mean harm** (ascending)
4. Lowest **mean intervention cost** (ascending)
5. Highest **recovery rate** (descending)
6. Lexical **controller ID** (ascending)

The top-ranked candidate is the `provisional_selection`.

### No-selection outcomes

- **None superior:** return `no_controller_selected`.
- **None eligible:** return `no_controller_selected` with machine-readable disqualification reasons.
- **Oracle selected:** impossible by design; oracle can never appear in the selection ranking.

---

## Oracle exclusion

Oracle is always excluded:

- `deployable = False` in the controller registry
- Never appears in `DEPLOYABLE_MANDATORY_CANDIDATES`
- Eligibility gate returns ineligible immediately
- Selection rule cannot select oracle
- Result schema loader raises `SelectionResultValidationError` if `selected_id == "oracle"`

---

## Hash verification

All protocol artifacts are committed under `artifacts/protocols/phase5b-selection-v1/`.

To verify locally:

```bash
cd qrtc-transit
python - <<'EOF'
import hashlib, json
from pathlib import Path
from qrtc_benchmark.selection_protocol import compute_protocol_hashes

# Verify canonical protocol hash matches preregistration
hashes = compute_protocol_hashes()
prereg = json.loads(
    Path("artifacts/protocols/phase5b-selection-v1/preregistration.json")
    .read_text(encoding="utf-8")
)
assert prereg["protocol_hash"] == hashes.protocol_declaration_sha256, "HASH MISMATCH"
print("Protocol hash verified:", hashes.protocol_declaration_sha256)

# Verify file checksums
lines = Path("artifacts/protocols/phase5b-selection-v1/checksums.sha256").read_text().splitlines()
for line in lines:
    digest, rel = line.split("  ", 1)
    path = Path("artifacts/protocols/phase5b-selection-v1") / rel
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == digest, f"CHECKSUM MISMATCH: {rel}"
    print(f"OK: {rel}")
print("All checksums verified.")
EOF
```

To verify candidate manifests:

```bash
cd qrtc-transit
python - <<'EOF'
from pathlib import Path
from qrtc_benchmark.controller_artifact import load_controller_artifact
from qrtc_benchmark.controllers import MANDATORY_CONTROLLER_IDS

for cid in MANDATORY_CONTROLLER_IDS:
    path = Path(f"artifacts/protocols/phase5b-selection-v1/manifests/{cid}.json")
    allow_oracle = cid == "oracle"
    artifact, ctrl = load_controller_artifact(
        path, allow_oracle=allow_oracle, deployable_only=not allow_oracle
    )
    print(f"OK: {cid} — {artifact.controller_version}")
EOF
```

---

## Dry-run commands

```bash
# Validate the protocol directory for the development stage (dry-run only):
qrtc-selection validate \
    --protocol-dir artifacts/protocols/phase5b-selection-v1 \
    --stage development \
    --output-dir /tmp/unused-output

# Print validation report as JSON:
qrtc-selection validate \
    --protocol-dir artifacts/protocols/phase5b-selection-v1 \
    --stage selection-validation \
    --output-dir /tmp/unused-output \
    --json

# Show help:
qrtc-selection --help
```

All `validate` invocations are **dry-run only**; no benchmark data is generated.

---

## Final-validation lock and narrow authorization

`qrtc-selection validate` remains locked for `final-validation`.

- Requesting `--stage final-validation` on the CLI raises `LockedStageError` (exit code 3).
- The `authorize_phase5_split("test")` guard in `phase5.py` raises `PermissionError`.
- Final-validation definitions are declared and hashed statically.
- `final_validation_status = "locked_not_executed"` is mandatory in all result records.

A separate one-time authorized runner now exists for the merged final-validation event:

```bash
python -m qrtc_benchmark.phase5b_final_validation \
  --protocol-dir artifacts/protocols/phase5b-selection-v1 \
  --artifacts-root artifacts/phase5b-selection-v1 \
  --output-dir artifacts/phase5b-selection-v1/final-validation-run-1 \
  --authorization artifacts/phase5b-selection-v1/final-validation-authorization-v1.json \
  --execution-index 1
```

This runner is fail-closed and requires the exact canonical authorization artifact.

---

## Result schema

Result records use schema `rescueos-selection-result-v1`.

Supported outcomes:
- `provisional_selection` — one superior eligible candidate found
- `no_controller_selected` — no superior or no eligible candidate

Use `load_selection_result()` from `qrtc_benchmark.result_schema` to load and validate.
The loader is fail-closed: unknown/missing/extra fields, invalid hashes, fabricated or
ineligible selections, oracle selection, and preregistration mismatches are all rejected.

---

## CI gates

This PR must pass:

```bash
pytest
mypy src
ruff check src tests
ruff format --check src tests
python -m build
```

Plus installed-wheel smoke for every declared console script and CodeQL/security validation.

---

## Protocol files

```
artifacts/protocols/phase5b-selection-v1/
├── preregistration.json          — canonical protocol declaration with hash
├── commit.txt                    — bound implementation commit (PR #22 merge)
├── frozen_semantic_declarations.json  — split/config/candidate declarations + hashes
├── checksums.sha256              — SHA-256 of all files (relative paths)
└── manifests/
    ├── qrtc.json                 — frozen rescueos-controller-v1 artifact
    ├── qrtc_no_abstention.json
    ├── qrtc_untyped.json
    ├── greedy_gain.json
    └── oracle.json               — non-deployable; never eligible
```

---

*This runbook documents frozen protocol execution controls, including the narrow authorized final-validation path for `qrtc` under recommend-only authority.*
