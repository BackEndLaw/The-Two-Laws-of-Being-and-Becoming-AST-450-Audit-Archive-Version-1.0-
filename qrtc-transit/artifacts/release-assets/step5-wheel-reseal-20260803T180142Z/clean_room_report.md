# Step5 Wheel Reseal Clean-Room Report

- pip_check: No broken requirements found.
- controller_sha256: 3a5845cbcda7260497050dfd027787fa06d0e3f02dc49e23d7ea2af8a868bcc1
- decision_sha256: 2928653190c53335bd7b78862283d1118aba3b63c83eb0126f3b63c8c0f12f47
- authority: recommend_only
- hardware_actuation_enabled: False
- env_toggle_attempt_hardware_actuation_enabled: False
- state_loading_mode: registry_lookup_only_no_retraining
- source_repo_dependency: False
- qrtc_module: /tmp/step5-cleanroom-reseal/lib/python3.12/site-packages/qrtc/__init__.py
- qrtc_benchmark_module: /tmp/step5-cleanroom-reseal/lib/python3.12/site-packages/qrtc_benchmark/__init__.py

## Structured Advisor Smoke Case

```json
{
  "hardware_actuation_enabled": false,
  "human_required_execution_authority": "recommend_only",
  "recommendation": {
    "action_sequence": [
      "rG",
      "rW",
      "rJ"
    ],
    "authority": "recommend_only",
    "type": "action_sequence"
  },
  "task_status": "complete"
}
```
