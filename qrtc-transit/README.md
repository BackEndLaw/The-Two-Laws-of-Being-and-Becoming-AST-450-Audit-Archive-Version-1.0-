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

## Optional Live CARLA Smoke Harness

The CARLA integration is intentionally opt-in and excluded from the default pytest run.

1. Start a CARLA server separately (for example, CARLA UE server on your workstation) and keep it running.
	- On the Windows server, run `CarlaUE4.exe -carla-rpc-port=2000`.
	- In an elevated PowerShell window, allow CARLA's TCP ports on private networks:
	  `New-NetFirewallRule -DisplayName "CARLA TCP 2000-2002" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 2000-2002 -Profile Private`
	- Verify the listener on the Windows server:
	  `Test-NetConnection 10.0.0.70 -Port 2000`
2. Install qrtc-transit with optional live extras:
	- `pip install -e ".[dev,carla-live]"`
3. If `carla-live` resolution fails for your platform/version, install CARLA manually from an official CARLA Python wheel matching your simulator build, then install project dependencies normally:
	- `pip install -e ".[dev]"`
	- `pip install <path-or-url-to-carla-wheel>`
4. Configure optional environment variables (defaults shown):
	- `QRTC_CARLA_HOST=127.0.0.1`
	- `QRTC_CARLA_PORT=2000`
	- `QRTC_CARLA_TIMEOUT_SECONDS=5.0`
	- `QRTC_CARLA_TICK_COUNT=20`
	- `QRTC_CARLA_SPAWN_INDEX=0`
	- `QRTC_CARLA_FIXED_DELTA_SECONDS=0.05`
	- `QRTC_CARLA_VEHICLE_BLUEPRINT=vehicle.tesla.model3`
	- `QRTC_CARLA_LIVE_REQUIRED=true` (optional: fail instead of skip when server is unreachable)
5. Run the live pytest smoke test explicitly:
	- `PYTEST_ADDOPTS='' pytest -m "carla and integration" tests/integration/test_carla_live.py`
6. Or run the same smoke harness manually and capture JSON output for later QRTC evidence ingestion:
	- `qrtc-carla-smoke`
	- From another computer on the same private network:
	  `QRTC_CARLA_HOST=10.0.0.70 QRTC_CARLA_PORT=2000 qrtc-carla-smoke`

### Full Live Driving Test

The full test follows a route generated from the selected spawn point, exercises
steering and braking, adds autopilot traffic, records vehicle dynamics, and
reports an overall assessment with individual pass/fail checks.

- Run it with `qrtc-carla-driving`.
- Run its opt-in integration test with:
  `PYTEST_ADDOPTS='' pytest -m "carla and integration" tests/integration/test_carla_live_driving.py`
- General connection, timestep, spawn, and vehicle environment variables above
  also apply.
- Scenario controls:
  - `QRTC_CARLA_DRIVING_TICK_COUNT=200`
  - `QRTC_CARLA_BRAKING_TICK_COUNT=40`
  - `QRTC_CARLA_TARGET_SPEED_MPS=6.0`
  - `QRTC_CARLA_ROUTE_SPACING_M=2.0`
  - `QRTC_CARLA_ROUTE_WAYPOINT_COUNT=25`
  - `QRTC_CARLA_TRAFFIC_VEHICLE_COUNT=3`
  - `QRTC_CARLA_TRAFFIC_MANAGER_PORT=8000`
  - `QRTC_CARLA_TRAFFIC_SEED=450`
  - `QRTC_CARLA_WAYPOINT_TOLERANCE_M=3.0`
- Pass/fail thresholds:
  - `QRTC_CARLA_MIN_ROUTE_PROGRESS=0.6`
  - `QRTC_CARLA_MAX_SPEED_MPS=12.0`
  - `QRTC_CARLA_MAX_LONGITUDINAL_ACCEL_MPS2=12.0`
  - `QRTC_CARLA_MAX_LATERAL_ACCEL_MPS2=10.0`
  - `QRTC_CARLA_MAX_FINAL_SPEED_MPS=0.75`

Notes:
- The live test expects an already-running CARLA server and performs bounded low-speed ticks with cleanup of actors/world settings.
- GitHub Actions runners cannot reach a CARLA server on your local machine; this test is not run in default CI by design.
- For automated private-network runs, use a self-hosted runner on the CARLA server's LAN or connect the runner and server through a private VPN. Set `QRTC_CARLA_HOST` to the server's reachable LAN or VPN address.
- Do not expose CARLA's RPC ports directly to the public internet.
