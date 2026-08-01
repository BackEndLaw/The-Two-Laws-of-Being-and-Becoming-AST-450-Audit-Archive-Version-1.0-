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

The result JSON will include a `qrtc_submission` section with:
- `status` — `accepted` or `rejected`
- `failure_stage` / `failure_reason` — QRTC pipeline rejection details
- `transit_id` — the recorded transit identifier
- `db_path` — path to the evidence database

Inspect or replay recorded transits with the existing QRTC CLI:

```powershell
qrtc transit inspect <transit_id> --db carla-evidence.sqlite3
qrtc transit replay  <transit_id> --db carla-evidence.sqlite3
```

Generated evidence is **always preserved** even when QRTC rejects the submission.

### Running the test suite

```powershell
# Ordinary tests (no CARLA required)
pytest tests/

# Include the live CARLA test (requires running simulator)
pytest tests/ --live
```

The `--live` flag is required to run `test_live_carla_drive`. Without it,
that test skips automatically. The live test is **not** run in CI.

