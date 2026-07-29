# RescueOS Graph-Only Vehicle Pilot V1

## Result

`blocked-route-v1` passed the graph-only pilot acceptance gate for denied and authorized transfers under fixed seeds 1, 2, 3, 4, and 5. All ten runs emitted complete replayable Witness traces and completed without a simulated collision.

This was a graph-only simulation, not a physics-based or physical-vehicle test.

## Reproduction

Run from the `qrtc-rescueos` directory:

```bash
PYTHONPATH=. /usr/bin/python3 -m integrations.vehicle.run_pilot \
  --scenario scenarios/blocked_route_v1.json \
  --output artifacts/vehicle_pilot
PYTHONPATH=. /usr/bin/python3 -m pytest -q
sha256sum -c artifacts/vehicle_pilot/SHA256SUMS
```

Expected pilot output:

- `acceptance_passed` is `true`;
- five denied runs have outcome `safe`;
- five authorized runs have outcome `route_resumed_safely`;
- all ten runs have `collision: false`, `witness_complete: true`, and `replay_verified: true`;
- the complete RescueOS suite reports 86 passing tests.

## Acceptance Rules

The blocked edge must be detected, both controller proposals recorded, and the Gate decision explicit. Denial must retain baseline authority without specialist Passage or Destination. Authorization must not realize a Destination before execution. Failed execution must invoke safe fallback, while completed execution must realize the alternate-route Destination. Every run must avoid collision, produce a complete Witness, reproduce from its seed and initial state, and replay exactly.

## Environment

- Base Git commit: `f2614fe2ff37a964a0a6662c3455dbc6e41c0f69`
- Branch at capture: `vehicle-simulation-pilot`
- Python: `3.12.3`
- pip: `24.0`
- OS: Ubuntu 24.04.4 LTS development container
- Kernel: `Linux 6.8.0-1052-azure x86_64`
- Seeds: `1, 2, 3, 4, 5`

The pilot source and artifacts were untracked at capture time. The base commit does not contain them; `SHA256SUMS` identifies the exact source, scenario, tests, and outputs used for this result. Create a commit and tag only after reviewing the intended versioned files.

## Artifact Layout

- `authorized-seed-*.jsonl`: admitted and executed handoff Witnesses.
- `denied-seed-*.jsonl`: denied handoff Witnesses with retained baseline authority.
- `summary.json`: acceptance result, per-run outcomes, and trace hashes.
- `pytest-output.txt`: full quiet-mode test output.
- `requirements-freeze.txt`: installed Python package versions.
- `ENVIRONMENT.txt`: command and platform capture.
- `SHA256SUMS`: explicit hashes for source, scenario, tests, and result artifacts.

## Limitations

This result does not establish CARLA, AWSIM, or ROS 2 integration; vehicle dynamics; real-time guarantees; sensor-noise robustness; hardware compatibility; track or road safety; statistical safety; production readiness; or superiority over another controller architecture.