# Sprint 3 Completion Record

Sprint 1: finite-model adequacy kernel

Sprint 2: operational Transit chain

Sprint 3: configurable, persistent command-line MVP

## Tests

- total passed: 33
- acceptance criteria mapped:
  - 1. Valid versioned policy loads successfully: [tests/test_policy.py::test_valid_versioned_policy_loads_successfully](tests/test_policy.py#L13)
  - 2. Missing or unknown component references fail before Transit begins: [tests/test_policy.py::test_missing_component_references_fail_before_transit_begins](tests/test_policy.py#L33)
  - 3. Policy files cannot cause dynamic code execution: [tests/test_policy.py::test_policy_files_cannot_execute_code](tests/test_policy.py#L25)
  - 4. Duplicate registry identifiers are rejected: [tests/test_policy.py::test_duplicate_registry_identifiers_are_rejected](tests/test_policy.py#L43)
  - 5. A successful Transit is durably persisted: [tests/test_evidence_store.py::test_successful_transit_is_durably_persisted](tests/test_evidence_store.py#L19)
  - 6. Failed Transit retains its stage-specific evidence: [tests/test_evidence_store.py::test_failed_transit_retains_stage_specific_evidence](tests/test_evidence_store.py#L32)
  - 7. Raw predecessor content is absent from default evidence storage: [tests/test_evidence_store.py::test_successful_transit_is_durably_persisted](tests/test_evidence_store.py#L19)
  - 8. Event records form a verifiable hash chain: [tests/test_evidence_store.py::test_successful_transit_is_durably_persisted](tests/test_evidence_store.py#L19)
  - 9. Modifying a stored event breaks chain verification: [tests/test_evidence_store.py::test_tampering_breaks_chain_verification](tests/test_evidence_store.py#L48)
  - 10. CLI exit codes identify terminal outcomes correctly: [tests/test_cli.py::test_cli_exit_codes_identify_key_and_guard_rejections](tests/test_cli.py#L29) and [tests/test_cli.py::test_cli_invalid_policy_returns_invocation_error](tests/test_cli.py#L86)
  - 11. Inspection works after process restart: [tests/test_evidence_store.py::test_successful_transit_is_durably_persisted](tests/test_evidence_store.py#L19)
  - 12. Analysis replay reproduces deterministic Gate and Boat outputs: [tests/test_replay.py::test_analysis_replay_reproduces_deterministic_gate_and_boat_outputs](tests/test_replay.py#L19)
  - 13. Replay reports nondeterministic or unavailable operations honestly: [tests/test_replay.py::test_replay_reports_nondeterministic_operations_honestly](tests/test_replay.py#L26)
  - 14. Delivery retries require an explicit policy: [tests/test_replay.py::test_analysis_replay_reproduces_deterministic_gate_and_boat_outputs](tests/test_replay.py#L19)
  - 15. Destination realization supports an idempotency key based on transit_id: [tests/test_replay.py::test_destination_realization_uses_idempotency_key](tests/test_replay.py#L63)
  - 16. All 19 existing tests remain green: full `pytest` run (33 passed total)
- policy validation: [tests/test_policy.py::test_valid_versioned_policy_loads_successfully](tests/test_policy.py#L13)
- persistence restart test: [tests/test_evidence_store.py::test_successful_transit_is_durably_persisted](tests/test_evidence_store.py#L19)
- tamper-evidence test: [tests/test_evidence_store.py::test_tampering_breaks_chain_verification](tests/test_evidence_store.py#L48)
- replay test: [tests/test_replay.py::test_analysis_replay_reproduces_deterministic_gate_and_boat_outputs](tests/test_replay.py#L19)
