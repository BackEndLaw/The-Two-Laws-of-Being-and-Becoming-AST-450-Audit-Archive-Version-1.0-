# Step 5 Packaging Closure Report

**Date:** 2026-08-03  
**Protocol:** phase5b-selection-v1  
**Controller:** phase5b-rule-policy-v1  
**Status:** PASS

---

## 1. setuptools Version

### Runtime environment (clean-room venv)

```
setuptools: not installed in runtime environment
```

The installed wheel (`qrtc_transit-0.1.0`) does not declare `setuptools` as a runtime
dependency and `setuptools` is absent from the clean-room virtual environment.  This is
correct: `setuptools` is a **build-time** dependency only (declared as
`build-system.requires = ["setuptools>=69"]`).

### Build environment (`python -m build` isolated build venv)

```
setuptools: 83.0.0
```

`python -m build` creates its own isolated venv to run the build backend.  The version
resolved there was **setuptools 83.0.0**, satisfying the `>=69` lower bound declared in
`pyproject.toml`.

---

## 2. Frozen-Artifact Distribution Gap — Resolution

**Option B (explicit two-artifact distribution)** was adopted.

The release bundle contains:

```
qrtc_transit-0.1.0-py3-none-any.whl      ← RescueOS Advisor wheel
phase5b-rule-policy-v1/manifest.json      ← frozen controller bundle (unchanged)
release_manifest.json                     ← binding both SHA-256 hashes
```

The wheel does **not** embed the frozen controller artifact.  The artifact is supplied as
a separate, versioned release asset whose SHA-256 is bound by the release manifest.

### Release manifest hashes

| Asset | SHA-256 |
|-------|---------|
| `qrtc_transit-0.1.0-py3-none-any.whl` | `c3a37c7a3e134d73523bc2d073732b871902a65606563dd2b1d6986a16b0b7c0` |
| `phase5b-rule-policy-v1/manifest.json` | `3a5845cbcda7260497050dfd027787fa06d0e3f02dc49e23d7ea2af8a868bcc1` |
| `decision_checksum` | `2928653190c53335bd7b78862283d1118aba3b63c83eb0126f3b63c8c0f12f47` |

---

## 3. Clean-Room Verification

### Environment isolation

- The clean-room venv was created at `/tmp/step5-cleanroom-new/venv`, completely separate
  from the source checkout.
- `PYTHONPATH` was unset.  The working directory was the clean-room root, not the source
  repository.
- The wheel was installed with
  `pip install /tmp/step5-release-bundle/qrtc_transit-0.1.0-py3-none-any.whl`.
- The controller artifact was read from `/tmp/step5-release-bundle/phase5b-rule-policy-v1/manifest.json`
  (the release bundle copy), **not** from the source repository.

### Load path confirmed

```
qrtc_benchmark loaded from:
  /tmp/step5-cleanroom-new/venv/lib/python3.12/site-packages/qrtc_benchmark/controller_artifact.py
```

The path does **not** contain the source repository root; no source files were accessed
during the clean-room run.

### Verification results

| Check | Result |
|-------|--------|
| Wheel installed from release bundle only | PASS |
| `qrtc_benchmark` loaded from installed wheel, not source repo | PASS |
| Artifact SHA-256 matches release manifest | PASS (`3a5845...bcc1`) |
| Bundle schema validated (`rescueos-selected-controller-bundle-v1`) | PASS |
| `authority == recommend_only` | PASS |
| `hardware_actuation_enabled == false` | PASS |
| Decision checksum matches | PASS (`29286531...f47`) |
| No retraining (`registry_lookup_only_no_retraining`) | PASS |
| Physical actuation unavailable | PASS |

---

## 4. Structured Advisor Output

The reproducibility probe was executed against the frozen controller in the clean-room.
Full structured output:

```json
{
  "task_status": "complete",
  "recommendation": {
    "type": "action_sequence",
    "action_sequence": ["rG", "rW", "rJ"],
    "authority": "recommend_only"
  },
  "causal_path": {
    "case_family": "V3",
    "dependency_type": "chain",
    "relation_type": "independent",
    "required_actions": ["rG", "rW", "rJ"],
    "causal_graph_sha256": "1fdebca70dea89b3062917c64e0b79efc38dcf256f45671d79a6790831be2714",
    "graph_admissible": true
  },
  "uncertainty": {
    "reliability": 1.0,
    "unknown_fault": false,
    "evidence_initially_insufficient": false
  },
  "score": {
    "severity": 0.5,
    "noise": 0.1
  },
  "graph_admissibility": "admitted",
  "human_required_execution_authority": "recommend_only",
  "hardware_actuation_enabled": false,
  "audit_checksum": {
    "decision_sha256": "2928653190c53335bd7b78862283d1118aba3b63c83eb0126f3b63c8c0f12f47",
    "controller_artifact_sha256": "3a5845cbcda7260497050dfd027787fa06d0e3f02dc49e23d7ea2af8a868bcc1",
    "reproducibility_probe_sha256": "4a412e45fc67a6e686821370f18c0f82c40f9fbcd7f99bd0a81a7287826c594d"
  }
}
```

Field mapping to required Advisor output elements:

| Required element | Field | Value |
|-----------------|-------|-------|
| Task status | `task_status` | `complete` |
| Recommendation | `recommendation.action_sequence` | `["rG", "rW", "rJ"]` |
| Causal path / explanation | `causal_path` | V3 chain, causal_graph_sha256 bound |
| Expected utility / score | `score.severity`, `score.noise` | 0.5 / 0.1 |
| Uncertainty | `uncertainty.reliability` | 1.0 |
| Graph admissibility | `graph_admissibility` | `admitted` |
| Human-required execution authority | `human_required_execution_authority` | `recommend_only` |
| Audit / evidence checksum | `audit_checksum.decision_sha256` | `29286531...f47` |

The transit CLI smoke test also completed successfully:

```
stage: witnessed
delivery: delivered
```

(Full JSON output omitted; policy_version, schema_version, encoding_version, route_version,
authorization, guard_decisions, delivery_evidence, candidate_successor, stabilization_result,
and witness_record with integrity_verified=true and stabilized=true are all present in the
output.)

---

## 5. Installation and Loading Instructions

```bash
# 1. Verify release assets
sha256sum qrtc_transit-0.1.0-py3-none-any.whl
# expected: c3a37c7a3e134d73523bc2d073732b871902a65606563dd2b1d6986a16b0b7c0

sha256sum phase5b-rule-policy-v1/manifest.json
# expected: 3a5845cbcda7260497050dfd027787fa06d0e3f02dc49e23d7ea2af8a868bcc1

# 2. Install in a fresh virtual environment (no source repository required)
python3 -m venv /path/to/cleanroom-venv
/path/to/cleanroom-venv/bin/python -m pip install qrtc_transit-0.1.0-py3-none-any.whl

# 3. Load and verify the frozen controller
python3 - <<'PY'
import json, hashlib, sys
from pathlib import Path
import qrtc_benchmark.controller_artifact as ca

artifact_path = Path("phase5b-rule-policy-v1/manifest.json")
artifact_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
assert artifact_sha == "3a5845cbcda7260497050dfd027787fa06d0e3f02dc49e23d7ea2af8a868bcc1"

payload = json.loads(artifact_path.read_text())
bundle, controller = ca.load_selected_controller_bundle(payload)

decision_sha = ca.selected_controller_decision_checksum(bundle, controller)
assert decision_sha == "2928653190c53335bd7b78862283d1118aba3b63c83eb0126f3b63c8c0f12f47"
assert bundle.hardware_actuation_enabled is False
assert bundle.authority == "recommend_only"
print("All checks passed")
PY
```

---

## 6. Step 5 Status

**Step 5 PASSED.**

- The frozen controller bundle was loaded exclusively from the release asset copy, not
  from the source repository.
- All four SHA-256 checksums (wheel, artifact, decision, causal graph) verified.
- No retraining or policy recalculation occurred.
- Physical actuation remains unavailable (`hardware_actuation_enabled=false`,
  `authority=recommend_only`).
- The structured Advisor output contains all required fields.
- Controller contents were not modified.

Next stage: **Release RescueOS Advisor, then select one physical communication-link test bench.**  
Physical testing should begin with real hardware in observation-only bench mode.
