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

## CARLA Autonomous-Drive Harness

`qrtc-transit` ships an optional CARLA harness (`qrtc.carla_harness`) that
connects to a running CARLA simulator, spawns a vehicle, enables autopilot via
the Traffic Manager, runs a bounded drive loop, and writes structured JSON
evidence.

**CARLA is entirely optional.**  Normal installation and CI work without it;
the `carla` Python package is only imported when you actually invoke the
`carla-live-drive` command.

### Requirements

| Item | Requirement |
|------|-------------|
| CARLA server | 0.9.x (tested with 0.9.16) |
| Python | Match the bundled CARLA wheel — CARLA 0.9.16 ships a **CPython 3.12** wheel on Windows |
| CARLA Python wheel | Located at `PythonAPI\carla\dist\` inside your CARLA installation |

### Quick Start (Windows PowerShell)

**Step 1 — Start the CARLA server** (keep this window open):

```powershell
.\CarlaUE4.exe -carla-port=2000 -quality-level=Low -windowed -ResX=800 -ResY=600
```

**Step 2 — Install the CARLA Python wheel** (one-time):

```powershell
# Locate the wheel
Get-ChildItem -Recurse .\PythonAPI\carla\dist\*.whl

# Install it (replace with the actual filename shown above)
python -m pip install ".\PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl"
```

**Step 3 — Install qrtc-transit**:

```powershell
cd qrtc-transit
pip install -e .
```

**Step 4 — Run a short drive**:

```powershell
$env:CARLA_TICKS = "100"
carla-live-drive
```

JSON evidence is written to `carla-live-drive-result.json` in the current
working directory (override with `$env:CARLA_OUTPUT`).

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CARLA_HOST` | `127.0.0.1` | CARLA server hostname |
| `CARLA_PORT` | `2000` | CARLA server port |
| `CARLA_TM_PORT` | `8000` | Traffic Manager port |
| `CARLA_TIMEOUT` | `15` | Client timeout in seconds |
| `CARLA_TICKS` | `300` | Number of simulation ticks to run |
| `CARLA_SPAWN_POINT` | `0` | Preferred spawn-point index (falls back to index 0) |
| `CARLA_OUTPUT` | `carla-live-drive-result.json` | Path for the JSON evidence file |

### JSON Evidence Format

The output file contains:

```json
{
  "host": "127.0.0.1",
  "port": 2000,
  "map_name": "Town03",
  "vehicle_blueprint": "vehicle.tesla.model3",
  "ticks_requested": 300,
  "ticks_completed": 300,
  "collision_events_total": 0,
  "elapsed_seconds": 15.1,
  "error": null,
  "records": [
    {
      "tick": 0,
      "frame": 1042,
      "x": 12.3456,
      "y": -45.6789,
      "z": 0.1234,
      "yaw": 90.0,
      "speed_ms": 4.17,
      "collision_count": 0
    }
  ]
}
```

`records` are sampled every 10 ticks.  `error` is `null` on success.

### Running the Tests

Normal CI (no simulator required):

```powershell
pytest
```

Optional live smoke test (requires a running CARLA server):

```powershell
$env:CARLA_TICKS = "100"
pytest -m carla_live qrtc-transit/tests/test_carla_live.py -v
```

> **Note:** Cloud-hosted GitHub Actions runners cannot reach a CARLA simulator
> bound to your local `127.0.0.1`.  Live tests are excluded from the default
> CI run and must be triggered manually on a machine where CARLA is running.
