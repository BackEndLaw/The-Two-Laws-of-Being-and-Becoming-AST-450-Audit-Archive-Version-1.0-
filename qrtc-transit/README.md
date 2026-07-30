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

### Private Windows Self-Hosted Runner

The manual `QRTC CARLA Driving Manual Run` workflow runs only on a Windows x64
self-hosted runner carrying the `carla` label. It is not triggered by pushes or
pull requests.

1. In the repository, open **Settings → Actions → Runners → New self-hosted
   runner**, select **Windows x64**, and run GitHub's displayed PowerShell
   commands on the private CARLA computer.
2. During runner configuration, add the custom label `carla`. Treat the
   short-lived registration token as a secret: enter it only on that computer
   and never save it in the repository, workflow, logs, or screenshots.
3. Start the runner with `.\run.cmd`. Alternatively, from an elevated shell,
   install and start it as a service using the service commands supplied with
   the downloaded runner. Confirm that GitHub reports it as **Idle**.
4. Install Python 3.11, an official CARLA Python wheel matching the simulator
   build, and the project on that computer:
   - `python -m pip install <path-to-matching-carla-wheel>`
   - From `qrtc-transit`, `python -m pip install -e ".[dev,carla-live]"`
   - Confirm the same `python` available to the runner can execute
     `python -c "import carla"`.
5. Start CARLA on the runner computer with
   `CarlaUE4.exe -carla-rpc-port=2000`. If CARLA runs on another private host,
   allow TCP ports 2000–2002 only on the private network.
6. Open **Actions → QRTC CARLA Driving Manual Run → Run workflow**. Keep the
   default host `127.0.0.1` when CARLA and the runner share a computer;
   otherwise enter CARLA's private LAN or VPN address.
7. Download the `qrtc-carla-driving-<run_id>` artifact from the completed run.
   Its JSON records collision frames and count, route completion, individual
   gate decisions and overall pass/fail status, and per-frame telemetry for
   replay evidence.

Use this runner only with trusted, private repositories and workflows. Restrict
repository access to trusted collaborators, keep the runner and CARLA patched,
and do not expose CARLA RPC or the runner host directly to the public internet.
