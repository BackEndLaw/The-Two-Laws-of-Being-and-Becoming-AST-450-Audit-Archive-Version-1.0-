# QRTC Transit

Formal kernel for QRTC Transit analysis.

This project compares an implemented Gate against a declared future family and classifies the relationship as exact, insufficient, excessive, or incomparable.

## CI and Dependency Audit

- Quality gates run on push and pull request for transit changes via [../.github/workflows/qrtc-transit-ci.yml](../.github/workflows/qrtc-transit-ci.yml).
- A scheduled dependency audit runs weekly (and can be run manually) via [../.github/workflows/qrtc-transit-audit.yml](../.github/workflows/qrtc-transit-audit.yml).

### Viewing Audit Artifacts

1. Open the repository Actions tab.
2. Select the "QRTC Transit Dependency Audit" workflow run.
3. Open the run artifacts named `qrtc-transit-pip-audit-<run_id>`.
4. Download and review:
	- `pip-audit.json`
	- `pip-audit-summary.md`

---

## CARLA Live-Drive Harness

`qrtc-transit` ships an opt-in, reusable harness for running bounded
synchronous drives in CARLA and emitting QRTC-compatible telemetry evidence.

All CARLA imports are **lazy**: the harness can be imported without CARLA
installed. Ordinary unit tests never require a simulator.

### Python version requirement

CARLA 0.9.16 ships a bundled `cp312` wheel that **requires CPython 3.12**.
Using any other Python version (3.11, 3.13 …) will fail at wheel installation
time.

### Windows setup (recommended path)

1. **Install CPython 3.12** from [python.org](https://www.python.org/downloads/).

2. **Create and activate a virtual environment:**

   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install `qrtc-transit` in editable mode (dev extras):**

   ```powershell
   cd qrtc-transit
   pip install -e ".[dev]"
   ```

4. **Install the CARLA Python wheel** from your CARLA 0.9.16 installation
   (the `.whl` is inside the CARLA release archive):

   ```powershell
   pip install "C:\path\to\carla\PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl"
   ```

5. **Launch CARLA** (keep this window open — the simulator must stay running):

   ```powershell
   .\CarlaUE4.exe -carla-port=2000 -quality-level=Low -windowed -ResX=800 -ResY=600
   ```

   > **Note:** Cloud GitHub-hosted runners cannot reach a simulator bound
   > to `127.0.0.1` on your workstation. Live drives must be run locally.

### Running a drive

```powershell
# 100-tick quick drive with lidar disabled (low resource)
$env:CARLA_TICKS = "100"
$env:CARLA_LIDAR_ENABLED = "false"
carla-live-drive
```

Output is written to `carla-live-drive-result.json` by default.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `CARLA_HOST` | `127.0.0.1` | CARLA server hostname |
| `CARLA_PORT` | `2000` | CARLA server port |
| `CARLA_TM_PORT` | `8000` | Traffic Manager port |
| `CARLA_TIMEOUT` | `15` | Client timeout (seconds) |
| `CARLA_TICKS` | `300` | Number of simulation ticks |
| `CARLA_SPAWN_POINT` | `0` | Preferred spawn point index |
| `CARLA_OUTPUT` | `carla-live-drive-result.json` | Output JSON path |
| `CARLA_FIXED_DELTA` | `0.05` | Simulation fixed delta (seconds) |
| `CARLA_BLUEPRINT` | `vehicle.tesla.model3` | Preferred vehicle blueprint |
| `CARLA_PRINCIPAL` | `carla-operator` | QRTC principal |
| `CARLA_DESTINATION` | `carla-drive-record` | QRTC destination |
| `CARLA_SUBMIT_QRTC` | `false` | Submit evidence through QRTC pipeline |
| `CARLA_QRTC_DB` | `qrtc_evidence.sqlite3` | QRTC evidence database path |

#### Lidar variables

| Variable | Default | Description |
|---|---|---|
| `CARLA_LIDAR_ENABLED` | `true` | Attach lidar sensor |
| `CARLA_LIDAR_CHANNELS` | `16` | Number of lidar channels |
| `CARLA_LIDAR_RANGE` | `30.0` | Lidar range (metres) |
| `CARLA_LIDAR_POINTS_PER_SECOND` | `56000` | Points per second |
| `CARLA_LIDAR_ROTATION_FREQUENCY` | `10.0` | Rotation frequency (Hz) |
| `CARLA_LIDAR_UPPER_FOV` | `10.0` | Upper field of view (degrees) |
| `CARLA_LIDAR_LOWER_FOV` | `-30.0` | Lower field of view (degrees) |

**Lidar resource tradeoffs:** Increasing `CARLA_LIDAR_CHANNELS` or
`CARLA_LIDAR_POINTS_PER_SECOND` dramatically raises GPU/CPU load. The
defaults are conservative for low-resource live testing. For quick
validation passes (e.g., 100 ticks), consider setting
`CARLA_LIDAR_ENABLED=false`.

### Output files

| File | Description |
|---|---|
| `carla-live-drive-result.json` (default) | Full drive report including lidar summary, collision events, position samples, config snapshot, and optional QRTC submission result |
| `qrtc_evidence.sqlite3` (default, when `CARLA_SUBMIT_QRTC=true`) | QRTC evidence database with chain-verified transit records |

### Optional QRTC submission and replay

Set `CARLA_SUBMIT_QRTC=true` to project the drive evidence through the
QRTC transit pipeline and record it in the evidence database:

```powershell
$env:CARLA_SUBMIT_QRTC = "true"
$env:CARLA_QRTC_DB = "carla-evidence.sqlite3"
carla-live-drive
```

#### CARLA-specific policy

CARLA telemetry is validated through a **dedicated CARLA policy** at
`qrtc-transit/examples/carla-policy.json`.  This policy is entirely
separate from the legacy equipment telemetry policy
(`examples/telemetry-policy.json`) and uses distinct component
identifiers:

| Component | CARLA | Equipment Telemetry |
|---|---|---|
| Key policy | `carla-key-v1` | `telemetry-key-v1` |
| Gate | `carla-gate-v1` | `telemetry-gate-v1` |
| Schema guard | `carla-schema-v1` | `telemetry-schema-v1` |
| Health guard | `carla-health-v1` | `telemetry-ranges-v1` |
| Boat encoding | `carla-json-v1` | `canonical-json-v1` |
| Realizer | `carla-drive-record-v1` | `alarm-record-v1` |
| Stabilizer | `carla-persistence-v1` | `alarm-persistence-v1` |

The CARLA guards validate fields that are specific to vehicle drive
evidence:

- **carla-schema-v1** — checks `status` is a recognised completion state,
  `ticks_requested` is positive, `ticks_completed == ticks_requested` for a
  completed run, and `collision_count`/`missing_data_count` are nonnegative.
- **carla-health-v1** — checks `displacement_m`, `mean_speed_mps`, and
  `max_speed_mps` are finite and nonnegative; if lidar is enabled,
  `lidar_frames_received > 0` and nearest-range fields are finite and
  nonnegative when present.

#### Principal behaviour

The CARLA key policy authorises the **same principal** used to run the
drive.  The principal is set by the `CARLA_PRINCIPAL` environment variable
(default: `carla-operator`).

The harness sets `principal` in the run report from this variable, and
`submit_to_qrtc_pipeline` reads the same variable to configure the key
policy so that the authorised principal matches by construction:

```powershell
# Both the projection and the key use "BackEndLaw" — accepted.
$env:CARLA_PRINCIPAL = "BackEndLaw"
$env:CARLA_SUBMIT_QRTC = "true"
carla-live-drive
```

If the principal in the projection does not match the key policy the
submission is rejected with `REJECTED_BY_KEY` and the rejection reason is
recorded in the `authorization_reason` field of the result.

#### Expected accepted result

A successfully accepted submission produces a `qrtc_submission` section
in the JSON output similar to:

```json
{
  "submitted": true,
  "transit_id": "<run_id>",
  "status": "accepted",
  "failure_stage": null,
  "failure_reason": null,
  "db_path": "qrtc_evidence.sqlite3",
  "evidence_preserved": true,
  "authorization_reason": "identity, class, future, destination, expiration, and policy matched",
  "guard_reasons": [
    {"guard_id": "carla-schema-v1", "qualified": true, "reason": "CARLA schema accepted"},
    {"guard_id": "carla-health-v1", "qualified": true, "reason": "CARLA health accepted"}
  ]
}
```

#### Inspecting rejected or accepted transits

The result JSON always includes `failure_reason` (describing why the
submission was rejected), `authorization_reason`, and `guard_reasons`
(per-guard decisions with reasons):

```powershell
# Inspect a recorded transit
qrtc transit inspect <transit_id> --db carla-evidence.sqlite3

# Replay a recorded transit
qrtc transit replay  <transit_id> --db carla-evidence.sqlite3
```

Generated evidence is **always preserved** even when QRTC rejects the
submission.

### Running the test suite

```powershell
# Ordinary tests (no CARLA required)
pytest tests/

# Include the live CARLA test (requires running simulator)
pytest tests/ --live
```

The `--live` flag is required to run `test_live_carla_drive`. Without it,
that test skips automatically. The live test is **not** run in CI.

