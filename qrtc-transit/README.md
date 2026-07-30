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

Notes:
- The live test expects an already-running CARLA server and performs bounded low-speed ticks with cleanup of actors/world settings.
- GitHub Actions runners cannot reach a CARLA server on your local machine; this test is not run in default CI by design.
