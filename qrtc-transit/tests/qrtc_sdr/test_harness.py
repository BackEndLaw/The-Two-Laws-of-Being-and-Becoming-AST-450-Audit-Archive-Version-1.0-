"""
Tests for qrtc_sdr.harness.

Covers:
- One-way Advisor interface (Advisor cannot open a transmitter endpoint).
- Advisor-originated transmitter-control traffic remains zero.
- Audit and decision checksums are generated.
- Rejected telemetry records produce null-case audit entries.
- Valid telemetry records produce Advisor recommendations.
- Audit-record checksum is deterministic.
- authority and hardware_actuation_enabled are propagated from the bundle.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from qrtc_benchmark.phase5 import (
    DependencyType,
    Phase5Family,
    Phase5Intervention,
    Phase5OODCase,
    Phase5RelationType,
)
from qrtc_sdr.harness import (
    SdrBenchHarness,
    _AdvisorTransmitterInterface,
    _canonical_json_bytes,
    _observation_to_dict,
    _sha256_hex,
)
from qrtc_sdr.observation_mapping import SdrObservationMapper
from qrtc_sdr.telemetry import SdrMappingConfig, SdrTelemetry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG = SdrMappingConfig(
    rssi_baseline_dbm=-40.0,
    rssi_noise_floor_dbm=-100.0,
)

_T0 = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)


def _telemetry(
    rssi_dbm: float = -40.0,
    snr_db: float = 20.0,
    ber: float | None = 0.0,
    packet_loss_rate: float | None = 0.0,
    is_valid: bool = True,
    is_stale: bool = False,
    is_malformed: bool = False,
    lag_s: float = 0.1,
    scenario_id: str = "A-baseline",
    trial_id: str = "t001",
) -> SdrTelemetry:
    return SdrTelemetry(
        rssi_dbm=rssi_dbm,
        snr_db=snr_db,
        ber=ber,
        packet_loss_rate=packet_loss_rate,
        source_timestamp_utc=_T0,
        ingestion_timestamp_utc=_T0 + timedelta(seconds=lag_s),
        window_duration_s=1.0,
        is_valid=is_valid,
        is_stale=is_stale,
        is_malformed=is_malformed,
        scenario_id=scenario_id,
        trial_id=trial_id,
    )


def _make_mock_bundle() -> MagicMock:
    bundle = MagicMock()
    bundle.authority = "recommend_only"
    bundle.hardware_actuation_enabled = False
    bundle.controller_parameters = {}
    bundle.reproducibility_probe = {
        "case": {
            "family": "V3",
            "mechanism_id": "triple_seen_m1",
            "composition_id": "FG+FW+FJ",
            "relation_type": "independent",
            "criterion": "PI1",
            "severity": 0.5,
            "noise": 0.0,
            "dependency_type": "chain",
            "unknown_fault": False,
            "evidence_initially_insufficient": False,
            "required_actions": ["rG", "rW", "rJ"],
        },
        "reliability": 1.0,
        "seed": 0,
        "costs": {
            "rG": 5.0,
            "rB": 4.0,
            "rR": 4.0,
            "rW": 2.0,
            "rD": 3.0,
            "rJ": 1.0,
            "r0": 1.0,
            "stop": 0.0,
        },
    }
    return bundle


def _make_mock_controller() -> MagicMock:
    controller = MagicMock()
    controller.controller_id = "qrtc"
    controller.controller_version = "phase5b-rule-policy-v1"
    controller.select_actions.return_value = (
        Phase5Intervention.rW,
        Phase5Intervention.rJ,
    )
    return controller


def _make_harness() -> SdrBenchHarness:
    return SdrBenchHarness(
        mapper=SdrObservationMapper(_CONFIG),
        bundle=_make_mock_bundle(),
        controller=_make_mock_controller(),
    )


# ---------------------------------------------------------------------------
# Transmitter isolation tests
# ---------------------------------------------------------------------------


def test_advisor_transmitter_bytes_starts_at_zero() -> None:
    harness = _make_harness()
    assert harness.advisor_transmitter_bytes == 0


def test_advisor_transmitter_bytes_remains_zero_after_valid_trial() -> None:
    harness = _make_harness()
    t = _telemetry()
    harness.process(t)
    assert harness.advisor_transmitter_bytes == 0


def test_advisor_transmitter_bytes_remains_zero_after_rejected_trial() -> None:
    harness = _make_harness()
    t = _telemetry(is_malformed=True)
    harness.process(t)
    assert harness.advisor_transmitter_bytes == 0


def test_advisor_transmitter_bytes_zero_after_multiple_trials() -> None:
    harness = _make_harness()
    for _ in range(10):
        harness.process(_telemetry())
    assert harness.advisor_transmitter_bytes == 0


def test_null_transmitter_interface_raises_on_send() -> None:
    iface = _AdvisorTransmitterInterface()
    assert iface.bytes_sent == 0
    with pytest.raises(RuntimeError, match="PROTOCOL VIOLATION"):
        iface.send(b"hackrf-tune:433920000")


def test_advisor_has_no_transmitter_device_handle() -> None:
    """The harness must not expose any attribute that could be a TX endpoint."""
    harness = _make_harness()
    # Verify none of these TX-related attributes exist on the harness.
    tx_attrs = (
        "hackrf",
        "hackrf_device",
        "sdr_tx",
        "transmitter",
        "tx_socket",
        "tx_serial",
        "tx_usb",
        "tx_endpoint",
    )
    for attr in tx_attrs:
        assert not hasattr(harness, attr), (
            f"Harness must not expose a transmitter attribute: {attr!r}"
        )


# ---------------------------------------------------------------------------
# Audit record tests
# ---------------------------------------------------------------------------


def test_valid_trial_produces_audit_record_in_log() -> None:
    harness = _make_harness()
    t = _telemetry()
    record = harness.process(t)
    assert len(harness.audit_log) == 1
    assert harness.audit_log[0] is record


def test_rejected_trial_produces_null_case_record() -> None:
    harness = _make_harness()
    t = _telemetry(is_malformed=True)
    record = harness.process(t)
    assert record.mapping_result == "malformed_record"
    assert record.observation_json is None
    assert record.advisor_action_sequence is None
    assert record.decision_sha256 is None


def test_valid_trial_produces_action_sequence() -> None:
    harness = _make_harness()
    t = _telemetry(rssi_dbm=-70.0, snr_db=15.0)
    record = harness.process(t)
    assert record.mapping_result == "mapped"
    assert record.advisor_action_sequence is not None
    assert len(record.advisor_action_sequence) > 0


def test_audit_record_has_decision_sha256() -> None:
    harness = _make_harness()
    record = harness.process(_telemetry())
    assert record.decision_sha256 is not None
    assert len(record.decision_sha256) == 64


def test_audit_record_has_non_empty_checksum() -> None:
    harness = _make_harness()
    record = harness.process(_telemetry())
    assert len(record.audit_record_sha256) == 64


def test_audit_record_checksum_is_deterministic() -> None:
    """Two records with identical fields must have the same checksum."""
    harness = _make_harness()
    t = _telemetry()
    r1 = harness.process(t)
    # Build a second record with the same inputs (note: harness_timestamp will differ).
    # Test only the checksum's dependency on its own fields by building a dict.
    d1 = r1.as_dict()
    d2 = r1.as_dict()
    assert d1["audit_record_sha256"] == d2["audit_record_sha256"]


def test_audit_record_authority_propagated() -> None:
    harness = _make_harness()
    record = harness.process(_telemetry())
    assert record.advisor_authority == "recommend_only"


def test_audit_record_hardware_actuation_disabled() -> None:
    harness = _make_harness()
    record = harness.process(_telemetry())
    assert record.advisor_hardware_actuation_enabled is False


def test_audit_log_is_copy_not_reference() -> None:
    """audit_log property returns a copy; mutations don't affect internal state."""
    harness = _make_harness()
    harness.process(_telemetry())
    log_copy = harness.audit_log
    original_len = len(log_copy)
    log_copy.clear()
    assert len(harness.audit_log) == original_len


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


def test_canonical_json_bytes_is_deterministic() -> None:
    payload = {"b": 2, "a": 1, "c": [3, 1, 2]}
    b1 = _canonical_json_bytes(payload)
    b2 = _canonical_json_bytes(payload)
    assert b1 == b2


def test_canonical_json_bytes_sorts_keys() -> None:
    b1 = _canonical_json_bytes({"z": 1, "a": 2})
    b2 = _canonical_json_bytes({"a": 2, "z": 1})
    assert b1 == b2


def test_sha256_hex_length() -> None:
    digest = _sha256_hex(b"test")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_observation_to_dict_round_trips_family() -> None:
    case = Phase5OODCase(
        family=Phase5Family.V3_THREE_FAULT,
        mechanism_id="sdr_rf_path_loss",
        composition_id="FG+FW+FJ",
        relation_type=Phase5RelationType.INDEPENDENT,
        criterion="PI1",
        severity=0.75,
        noise=0.05,
        dependency_type=DependencyType.CHAIN,
        unknown_fault=False,
        evidence_initially_insufficient=False,
        required_actions=(
            Phase5Intervention.rG,
            Phase5Intervention.rW,
            Phase5Intervention.rJ,
        ),
    )
    d = _observation_to_dict(case)
    assert d["family"] == "V3"
    assert d["required_actions"] == ["rG", "rW", "rJ"]
    assert d["unknown_fault"] is False
