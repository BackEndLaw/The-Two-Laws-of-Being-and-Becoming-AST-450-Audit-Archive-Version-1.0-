# Release Asset Status — qrtc_transit-0.1.0

**Date checked:** 2026-08-03
**Checked by:** Copilot Coding Agent
**Status:** RELEASE ASSET MISSING

---

## Findings

The Step 5 packaging closure (`STEP5_PACKAGING_CLOSURE.md`) records a successful
clean-room verification of the wheel on 2026-08-03. The wheel SHA-256 and all
associated checksums are confirmed correct in the release manifest.

However, the wheel was built during the Step 5 clean-room session and placed in
a temporary directory (`/tmp/step5-release-bundle/`). It was **never uploaded to
a durable, retrievable location**. Specifically:

- **Not in the repository**: `.whl` files are excluded by `.gitignore` (standard Python practice).
- **Not in GitHub Releases**: The two existing GitHub Releases (`v1.0.0`, `carla-runtime-protection-v1.0`) contain no wheel attachment for `qrtc-transit`.
- **Not in GitHub Actions artifacts**: The `qrtc-transit-ci.yml` workflow runs `python -m build` but has no `actions/upload-artifact` step.
- **Not on PyPI**: Package is not published to any public package index.

The wheel SHA-256 recorded in the release manifest is therefore unverifiable until
the wheel is rebuilt and its hash is compared against the record.

### Exact checksums from RELEASE_RECORD.json

| Asset | SHA-256 |
|---|---|
| `qrtc_transit-0.1.0-py3-none-any.whl` | `c3a37c7a3e134d73523bc2d073732b871902a65606563dd2b1d6986a16b0b7c0` |
| `phase5b-rule-policy-v1/manifest.json` | `3a5845cbcda7260497050dfd027787fa06d0e3f02dc49e23d7ea2af8a868bcc1` |
| `decision_checksum` | `2928653190c53335bd7b78862283d1118aba3b63c83eb0126f3b63c8c0f12f47` |

The controller artifact manifest **is** retrievable from the repository and its
SHA-256 has been verified:

```
sha256(artifacts/phase5b-selection-v1/selected-controller/manifest.json)
= 3a5845cbcda7260497050dfd027787fa06d0e3f02dc49e23d7ea2af8a868bcc1  ✓
```

### Decision checksum

The decision checksum was verified in the Step 5 clean-room run (STEP5_PACKAGING_CLOSURE.md,
section 3, "Decision checksum matches: PASS"). It cannot be independently verified in this
session without the wheel or a running `qrtc_benchmark` installation that can call
`selected_controller_decision_checksum()`.

---

## Resolution Path

**Do not rebuild the wheel until authorized.** The build is deterministic and the
expected output hash is known, but a silent substitution of a newly-built wheel
under the old checksum would violate the release-seal integrity protocol.

### Exact reproducible build command

The build requires Python 3.11+, setuptools ≥ 69, and the `build` package:

```bash
# From the qrtc-transit/ directory at commit d4bc5b56d1dcfa88b413adc15b423aa09814d750
# (the validated_main_commit in RELEASE_RECORD.json)

git checkout d4bc5b56d1dcfa88b413adc15b423aa09814d750
cd qrtc-transit
python3 -m venv /tmp/build-env
/tmp/build-env/bin/pip install "build>=1.2" "setuptools>=69"
/tmp/build-env/bin/python -m build --wheel --no-isolation
sha256sum dist/qrtc_transit-0.1.0-py3-none-any.whl
# Expected: c3a37c7a3e134d73523bc2d073732b871902a65606563dd2b1d6986a16b0b7c0
```

**Expected output files:**
- `qrtc-transit/dist/qrtc_transit-0.1.0-py3-none-any.whl`
- `qrtc-transit/dist/qrtc_transit-0.1.0.tar.gz`

### Durable release-asset location

The recommended durable location is a GitHub Release attached to the
`phase5b-selection-v1` tag at commit `d4bc5b56d1dcfa88b413adc15b423aa09814d750`:

```
Tag:              phase5b-selection-v1
Target commit:    d4bc5b56d1dcfa88b413adc15b423aa09814d750
Release assets:
  qrtc_transit-0.1.0-py3-none-any.whl  (SHA-256 verified after build)
  phase5b-rule-policy-v1/manifest.json  (SHA-256: 3a5845...bcc1, already in repo)
  release_manifest.json                 (already committed in repo)
```

### Authorization required

A human reviewer must:

1. Authorize the rebuild at the exact tagged commit.
2. Verify the rebuilt wheel SHA-256 matches
   `c3a37c7a3e134d73523bc2d073732b871902a65606563dd2b1d6986a16b0b7c0`.
3. If it matches: attach the wheel to the GitHub Release.
4. If it does not match: investigate the discrepancy; do not publish the wheel
   until the source of the difference is understood.

---

## Impact on Physical Bench

This missing asset does **not** block the desk-side prerequisite work (observation
mapping, protocol, harness skeleton, RF safety review, acquisition package). It
**does** block the pre-bench preflight Step 1 (release seal verification) from
being declared complete.

The physical bench (Phase 2) must not begin until the wheel is verified and
attached to a durable release location.
