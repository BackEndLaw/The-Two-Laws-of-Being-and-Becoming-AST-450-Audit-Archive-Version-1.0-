# CARLA Runtime-Protection Evidence — August 2, 2026

This directory archives the two live CARLA runs performed while validating
PR #13, which implemented opt-in runtime protection for LiDAR faults.

## Git references

- Pull request: #13
- Tested PR head: `a80fe7d18d1bc52437a8bf0c905dda8279e78e62`
- Merge commit on `main`: `5f30ef4a1295e479898b5d4f69cfd074e7b403c0`
- Merge timestamp: `2026-08-02T17:09:29Z`

## Automated regression result

The targeted regression command completed successfully:

- Tests passed: **270**
- Duration: **8.80 seconds**

The original regression command output was observed interactively and was
not redirected to a standalone log file. This statement records the observed
result; it is not represented as an original test-log artifact.

## Archived runs

### `runtime-protection-20260802-115027-a80fe7d18d1b`

Diagnostic run.

The injected LiDAR fault was observed, and QRTC rejected the resulting
evidence, but runtime protection did not activate because the live command
loaded a stale installed `qrtc` package rather than the source tree under
test.

This run is preserved as environment-diagnostic evidence. It is not the
final runtime-protection acceptance run.

### `runtime-protection-20260802-115622-a80fe7d18d1b`

Final successful runtime-protection acceptance run.

Confirmed behavior:

- LiDAR fault injected at callback index 150
- Runtime protection reached `stopped`
- Autopilot was disabled
- Braking control was applied
- Safe stop was confirmed
- Run terminated after 164 of 300 requested ticks
- No natural LiDAR drops
- No LiDAR callback errors
- QRTC status was `rejected`
- QRTC evidence was preserved
- Final result was `runtime_protection_pass`
- Harness exit code was 0

## Artifact files

Each run contains:

- `carla-result.json` — complete structured CARLA report
- `result-summary.json` — acceptance or diagnostic summary
- `qrtc-evidence.sqlite3` — persisted QRTC evidence database
- `terminal-output.txt` — exact bytes of the original `terminal.log`

The terminal files were renamed because the repository ignores `*.log`.
Only the filenames changed; their contents and SHA-256 hashes were preserved.

`sha256-manifest.json` records the filename mapping, file sizes, and hashes
for every archived artifact.

## Scope

This evidence validates simulator runtime protection in CARLA. It does not
constitute physical-vehicle certification.
