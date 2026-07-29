# RescueOS CARLA Vehicle Pilot V1

## Status

```text
BLOCKED_INFRASTRUCTURE:
  insufficient Docker storage in GitHub Codespace
```

This is neither `FAILED_IMPLEMENTATION` nor `CARLA_PASSED`. No GPU-backed CARLA server is available in this container.

The CARLA 0.9.16 Python client is installed and import-verified. `CarlaVehicleAdapter`, blocked-route fault injection, collision and lane-invasion sensors, denied-case RescueOS semantics, physics measurements, semantic replay checks, and preregistered acceptance thresholds are implemented. Three focused tests pass against a deterministic fake CARLA world.

No CARLA physics run has completed. This directory does not contain a CARLA Witness or passing CARLA `summary.json`, and no CARLA collision or safety claim may be made from the local contract tests.

## Server Requirement

Run a CARLA 0.9.16 server on a GPU-backed x86-64 host. Port `2000` is occupied by an unrelated service in the current development container, so this experiment is pinned to port `2100`:

```bash
docker run --rm --privileged --gpus all --network host \
  carlasim/carla:0.9.16 \
  /bin/bash CarlaUE4.sh -RenderOffScreen -nosound \
  -quality-level=Low -carla-rpc-port=2100
```

The official image is approximately 8.64 GB compressed. A Docker launch was attempted, but extraction failed with exit code 125 and `no space left on device` while expanding the largest layer. Container creation and the NVIDIA runtime check were never reached. Docker root is `/var/lib/docker` on a 32 GB filesystem. Docker cleaned the failed image, leaving no images, containers, build cache, or partial layers visible to `docker system df`; about 19 GB remained free afterward. No prune was needed.

The complete local suite passed 89 tests, diagnostics were clean, and the frozen graph-pilot manifest still verified all 22 entries.

## Client Run

With the server listening on `127.0.0.1:2100`, run from `qrtc-rescueos`:

```bash
PYTHONPATH=.:/workspaces/.carla-python-0.9.16 \
  /usr/bin/python3 -m integrations.vehicle.carla.run_pilot \
  --config integrations/vehicle/carla/config.yaml \
  --scenario scenarios/blocked_route_v1.json \
  --output artifacts/vehicle_pilot_carla
```

The first executable case is Gate denial followed by a controlled physical stop. Authorized route following and failed handoff remain intentionally unavailable, and the adapter refuses to report an executed specialist handoff until that controller exists.

## Preregistered Denied Gate

- collisions: at most 0;
- lane invasions: at most 0;
- speed at fault detection: 2.5 to 3.5 m/s;
- stopped speed: at most 0.1 m/s;
- braking distance: at most 15 m;
- minimum obstacle clearance: at least 1 m;
- minimum time to collision: at least 1 s;
- Gate decision latency: at most 100 ms;
- baseline authority retained with no specialist Passage or Destination;
- complete Witness and matching semantic projection.

Trajectory replay tolerances are preregistered at 0.25 m position error and 0.1 m/s speed error, but trajectory replay is not evaluated in the first denied-case run.