# PR #12 Validation and Review Record

**Recorded:** August 2, 2026  
**Repository:** `BackEndLaw/The-Two-Laws-of-Being-and-Becoming-AST-450-Audit-Archive-Version-1.0-`  
**Pull request:** #12 — `fix: forward cfg.principal to submit_to_qrtc_pipeline to isolate run_drive() from ambient CARLA_PRINCIPAL`  
**Tested source commit:** `9fe40456965f8f347e82272f8d7a35bcf0d2c581`

## Review conclusion

PR #12 is approved from a code-review and live-validation perspective. No blocking code defect was identified.

The change explicitly passes `cfg.principal` to `submit_to_qrtc_pipeline()`. This prevents a stale ambient `CARLA_PRINCIPAL` environment variable from changing the authorization path after `CarlaConfig` has already been constructed.

The regression test deliberately sets a conflicting environment principal while configuring `principal="carla-operator"`, verifying that the configured value wins.

## Controlled validation outcome

```json
{
  "run_id": "0e06ba0f-4922-4ec2-89f4-3f6ff3c12fed",
  "test_outcome": "post_run_rejection_pass",
  "fault_injection_triggered": true,
  "requested_callback_index": 150,
  "triggered_callback_index": 150,
  "ticks_completed": 300,
  "lidar_callbacks_received": 300,
  "lidar_frames_accepted": 299,
  "lidar_frames_natural_dropped": 0,
  "lidar_frames_injected_dropped": 1,
  "lidar_callback_errors": 0,
  "schema_guard_qualified": true,
  "health_guard_qualified": false,
  "qrtc_status": "rejected",
  "evidence_preserved": true,
  "post_run_rejection_test_passed": true
}
```

Accounting invariant:

```text
300 callbacks = 299 accepted + 1 injected drop + 0 callback errors
```

Guard path:

```text
carla-schema-v1 qualified
→ carla-health-v1 rejected
→ QRTC rejected
→ evidence preserved
```

## Controlled-run evidence

Directory:

```text
vehicle_pilot/post-run-single-lidar-dropout-20260801-224932-9fe40456965f/
```

Artifacts:

- `carla-result.json`
- `guard-reasons.json`
- `qrtc-evidence.sqlite3`
- `result-summary.json`
- `terminal.log`
- `SHA256SUMS.txt`

The manifest hashes the five primary evidence artifacts and intentionally does not hash itself.

## Baseline evidence

The original 300-tick CARLA live-drive result is preserved at:

```text
vehicle_pilot/legacy/basic-300-tick-live-drive-20260801/
```

Files:

- `carla-live-drive-result.json`
- `SHA256SUMS.txt`

Recorded result properties:

- Status: `completed`
- Vehicle: `vehicle.tesla.model3`
- Actor ID: `26`
- Ticks: `300`
- Simulated duration: `15.0` seconds
- Displacement: `40.685302734375` meters
- Collisions: `0`

## Scope limitation

This validation establishes controlled **post-run LiDAR evidence rejection and evidence preservation** only.

It does not establish:

- immediate runtime fault detection;
- autopilot disengagement;
- braking-only control;
- bounded safe stopping;
- early runtime termination;
- physical-vehicle readiness.

Runtime protection must be implemented and validated separately.

## PR status at review time

At the time of review, PR #12 was open and marked draft. Its code was mergeable, but GitHub did not show a conclusive normal project CI result. The controlled live CARLA validation passed against the exact PR head commit.

PR #12 is stacked on PR #10, which is stacked on PR #9 and lower branches. The correction must be propagated through the stack deliberately so it is not lost by merging a lower PR independently.

Recommended sequence:

1. Run the focused regression test and relevant CARLA/QRTC unit suite.
2. Mark PR #12 ready for review.
3. Approve and merge PR #12 into its current base branch.
4. Recheck and merge PR #10 into PR #9's branch.
5. Continue through the lower stack in order until the complete corrected change reaches the default branch.

## Review verdict

```text
Code review: APPROVED — no blocking code findings
Controlled live validation: PASSED
Evidence preservation: COMPLETE
Remote archival: COMPLETE
PR #12 merge: pending normal stacked-PR process
Runtime protection: separate follow-up work
```
