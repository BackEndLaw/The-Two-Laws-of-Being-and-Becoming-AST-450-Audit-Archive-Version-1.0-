"""
Tests for qrtc_sdr.observation_mapping.

Covers:
- Deterministic schema mapping (same input → same output on repeated calls).
- Unit and range validation (out-of-range fields are rejected at the telemetry level).
- Stale observation rejection (both source-flagged and lag-detected).
- Malformed observation rejection.
- Missing-data behaviour (None BER, None packet_loss_rate).
- Evidence-initially-insufficient flag (ambiguous SNR, short window).
- Unknown-fault detection (high PLR with low path loss).
- V3 family and action-sequence selection per severity band.
- Criterion selection rules.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from qrtc_benchmark.phase5 import (
    DependencyType,
    Phase5Family,
    Phase5Intervention,
    Phase5RelationType,
)
from qrtc_sdr.observation_mapping import (
    CRITERION_PLR,
    CRITERION_RSSI,
    CRITERION_SNR,
    SDR_COMPOSITION_NOMINAL,
    SDR_COMPOSITION_UNKNOWN,
    SDR_MECHANISM_ID,
    SdrObservationMapper,
    _compute_noise,
    _compute_severity,
    _quantize,
    _select_criterion,
)
from qrtc_sdr.telemetry import (
    SdrMappingConfig,
    SdrTelemetry,
    SdrTelemetryValidationError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_CONFIG = SdrMappingConfig(
    rssi_baseline_dbm=-40.0,
    rssi_noise_floor_dbm=-100.0,
    min_window_duration_s=0.5,
    ambiguous_snr_low_db=0.0,
    ambiguous_snr_high_db=3.0,
    max_staleness_s=2.0,
)

_T0 = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)


def _make_telemetry(
    rssi_dbm: float = -40.0,
    snr_db: float = 20.0,
    ber: float | None = 0.0,
    packet_loss_rate: float | None = 0.0,
    is_valid: bool = True,
    is_stale: bool = False,
    is_malformed: bool = False,
    lag_s: float = 0.1,
    window_s: float = 1.0,
    scenario_id: str = "A-baseline",
    trial_id: str = "t001",
) -> SdrTelemetry:
    src = _T0
    ing = _T0 + timedelta(seconds=lag_s)
    return SdrTelemetry(
        rssi_dbm=rssi_dbm,
        snr_db=snr_db,
        ber=ber,
        packet_loss_rate=packet_loss_rate,
        source_timestamp_utc=src,
        ingestion_timestamp_utc=ing,
        window_duration_s=window_s,
        is_valid=is_valid,
        is_stale=is_stale,
        is_malformed=is_malformed,
        scenario_id=scenario_id,
        trial_id=trial_id,
    )


# ---------------------------------------------------------------------------
# Unit tests: _quantize
# ---------------------------------------------------------------------------


def test_quantize_exact_match() -> None:
    from qrtc_benchmark.phase5 import SEVERITIES

    assert _quantize(0.25, SEVERITIES) == 0.25
    assert _quantize(0.75, SEVERITIES) == 0.75
    assert _quantize(1.00, SEVERITIES) == 1.00


def test_quantize_midpoint_rounds_to_higher() -> None:
    from qrtc_benchmark.phase5 import SEVERITIES

    # Midpoint between 0.25 and 0.50 is 0.375; should round to 0.50.
    assert _quantize(0.375, SEVERITIES) == 0.50


def test_quantize_rounds_down() -> None:
    from qrtc_benchmark.phase5 import SEVERITIES

    assert _quantize(0.26, SEVERITIES) == 0.25


def test_quantize_rounds_up() -> None:
    from qrtc_benchmark.phase5 import SEVERITIES

    assert _quantize(0.60, SEVERITIES) == 0.50


# ---------------------------------------------------------------------------
# Unit tests: _compute_severity
# ---------------------------------------------------------------------------


def test_severity_at_baseline_is_zero_quantized() -> None:
    # rssi == baseline → raw = 0 → quantized to nearest of (0.25, 0.50, 0.75, 1.00)
    # 0.0 → nearest is 0.25.
    sev = _compute_severity(-40.0, _BASE_CONFIG)
    from qrtc_benchmark.phase5 import SEVERITIES

    assert sev == _quantize(0.0, SEVERITIES)


def test_severity_at_noise_floor_is_one() -> None:
    sev = _compute_severity(-100.0, _BASE_CONFIG)
    assert sev == 1.00


def test_severity_midpoint() -> None:
    # -40 baseline, -100 floor, dynamic_range = 60 dB
    # rssi = -70 → raw = 30/60 = 0.5 → quantized = 0.50
    sev = _compute_severity(-70.0, _BASE_CONFIG)
    assert sev == 0.50


def test_severity_clamps_below_zero() -> None:
    # rssi above baseline → raw < 0 → clamped to 0 → quantized to 0.25
    sev = _compute_severity(-30.0, _BASE_CONFIG)
    from qrtc_benchmark.phase5 import SEVERITIES

    assert sev == _quantize(0.0, SEVERITIES)


def test_severity_clamps_above_one() -> None:
    # rssi far below noise floor → raw > 1 → clamped to 1.0 → quantized = 1.00
    sev = _compute_severity(-200.0, _BASE_CONFIG)
    assert sev == 1.00


# ---------------------------------------------------------------------------
# Unit tests: _compute_noise
# ---------------------------------------------------------------------------


def test_noise_from_ber_only() -> None:
    noise = _compute_noise(0.05, None)
    assert noise == 0.05


def test_noise_from_plr_only() -> None:
    noise = _compute_noise(None, 0.10)
    assert noise == 0.10


def test_noise_takes_max() -> None:
    noise = _compute_noise(0.02, 0.10)
    assert noise == 0.10


def test_noise_clamps_at_max_noise_level() -> None:
    # BER > 0.20 → clamped to 0.20 (the max NOISE_LEVEL)
    noise = _compute_noise(0.50, None)
    assert noise == 0.20


def test_noise_zero_when_both_none() -> None:
    noise = _compute_noise(None, None)
    assert noise == 0.0


# ---------------------------------------------------------------------------
# Unit tests: _select_criterion
# ---------------------------------------------------------------------------


def test_criterion_rssi_dominant() -> None:
    # severity = 0.75, noise = 0.10 → 0.75 >= 0.10*2 → PI1
    assert _select_criterion(0.75, 0.10) == CRITERION_RSSI


def test_criterion_plr_dominant() -> None:
    # severity = 0.10, noise = 0.20 → noise > severity → PI3
    assert _select_criterion(0.10, 0.20) == CRITERION_PLR


def test_criterion_snr_balanced() -> None:
    # severity = 0.25, noise = 0.20 → neither dominates → PI2
    assert _select_criterion(0.25, 0.20) == CRITERION_SNR


# ---------------------------------------------------------------------------
# Mapping tests: SdrObservationMapper
# ---------------------------------------------------------------------------


def test_mapper_rejects_malformed() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    t = _make_telemetry(is_malformed=True)
    result = mapper.map(t)
    assert result.is_rejected
    assert result.rejection_reason == "malformed_record"
    assert result.case is None


def test_mapper_rejects_stale_flagged() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    t = _make_telemetry(is_stale=True)
    result = mapper.map(t)
    assert result.is_rejected
    assert result.rejection_reason == "stale_flagged_by_source"


def test_mapper_rejects_invalid_record() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    t = _make_telemetry(is_valid=False)
    result = mapper.map(t)
    assert result.is_rejected
    assert result.rejection_reason == "invalid_record"


def test_mapper_rejects_stale_by_lag() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    t = _make_telemetry(lag_s=5.0)  # max_staleness_s = 2.0
    result = mapper.map(t)
    assert result.is_rejected
    assert result.rejection_reason == "stale_detected_by_lag"


def test_mapper_baseline_produces_v3_case() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    t = _make_telemetry(rssi_dbm=-40.0, snr_db=20.0, ber=0.0, packet_loss_rate=0.0)
    result = mapper.map(t)
    assert not result.is_rejected
    assert result.case is not None
    assert result.case.family == Phase5Family.V3_THREE_FAULT
    assert result.case.mechanism_id == SDR_MECHANISM_ID
    assert result.case.composition_id == SDR_COMPOSITION_NOMINAL
    assert result.case.dependency_type == DependencyType.CHAIN
    assert result.case.relation_type == Phase5RelationType.INDEPENDENT
    assert result.case.unknown_fault is False
    assert result.case.evidence_initially_insufficient is False


def test_mapper_high_severity_requires_rG_rW_rJ() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    # severity ≈ 0.75: rssi = -85, baseline=-40, floor=-100 → raw=(40-85)/60 = 0.75
    t = _make_telemetry(rssi_dbm=-85.0, snr_db=10.0, ber=0.01, packet_loss_rate=0.01)
    result = mapper.map(t)
    assert result.case is not None
    assert result.case.severity == 0.75
    assert Phase5Intervention.rG in result.case.required_actions
    assert Phase5Intervention.rW in result.case.required_actions
    assert Phase5Intervention.rJ in result.case.required_actions


def test_mapper_moderate_severity_requires_rW_rJ() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    # severity 0.50: rssi = -70, raw=(40-70)/60 = 0.50
    t = _make_telemetry(rssi_dbm=-70.0, snr_db=15.0, ber=0.01, packet_loss_rate=0.01)
    result = mapper.map(t)
    assert result.case is not None
    assert result.case.severity == 0.50
    assert result.case.required_actions == (
        Phase5Intervention.rW,
        Phase5Intervention.rJ,
    )


def test_mapper_ambiguous_snr_sets_evidence_insufficient() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    t = _make_telemetry(snr_db=1.5)  # in [0.0, 3.0]
    result = mapper.map(t)
    assert result.case is not None
    assert result.case.evidence_initially_insufficient is True


def test_mapper_short_window_sets_evidence_insufficient() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    t = _make_telemetry(window_s=0.1)  # below min_window_duration_s=0.5
    result = mapper.map(t)
    assert result.case is not None
    assert result.case.evidence_initially_insufficient is True


def test_mapper_unknown_fault_detection() -> None:
    mapper = SdrObservationMapper(_BASE_CONFIG)
    # Low path loss (rssi close to baseline → severity_raw ≈ 0.05)
    # but high PLR (noise_raw = 0.40 > 0.30)
    t = _make_telemetry(
        rssi_dbm=-43.0,  # 3 dB below baseline → severity_raw = 3/60 = 0.05
        snr_db=20.0,
        ber=None,
        packet_loss_rate=0.40,
    )
    result = mapper.map(t)
    assert result.case is not None
    assert result.case.family == Phase5Family.V4_UNKNOWN_FAULT
    assert result.case.unknown_fault is True
    assert result.case.composition_id == SDR_COMPOSITION_UNKNOWN


def test_mapper_is_deterministic() -> None:
    """Same input produces byte-identical output on repeated calls."""
    mapper = SdrObservationMapper(_BASE_CONFIG)
    t = _make_telemetry(rssi_dbm=-70.0, snr_db=15.0)
    r1 = mapper.map(t)
    r2 = mapper.map(t)
    assert r1.case == r2.case
    assert r1.rejection_reason == r2.rejection_reason
    assert r1.severity_quantized == r2.severity_quantized
    assert r1.noise_quantized == r2.noise_quantized


def test_mapper_deterministic_across_instances() -> None:
    """Two mapper instances with identical config produce identical output."""
    t = _make_telemetry(rssi_dbm=-55.0, snr_db=12.0, ber=0.03, packet_loss_rate=0.05)
    r1 = SdrObservationMapper(_BASE_CONFIG).map(t)
    r2 = SdrObservationMapper(_BASE_CONFIG).map(t)
    assert r1.case == r2.case


# ---------------------------------------------------------------------------
# Telemetry validation tests
# ---------------------------------------------------------------------------


def test_telemetry_rejects_nan_rssi() -> None:
    import math

    with pytest.raises(SdrTelemetryValidationError, match="rssi_dbm"):
        _make_telemetry(rssi_dbm=math.nan)


def test_telemetry_rejects_nan_snr() -> None:
    with pytest.raises(SdrTelemetryValidationError, match="snr_db"):
        _make_telemetry(snr_db=float("nan"))


def test_telemetry_rejects_ber_out_of_range() -> None:
    with pytest.raises(SdrTelemetryValidationError, match="ber"):
        _make_telemetry(ber=1.5)


def test_telemetry_rejects_plr_negative() -> None:
    with pytest.raises(SdrTelemetryValidationError, match="packet_loss_rate"):
        _make_telemetry(packet_loss_rate=-0.1)


def test_telemetry_rejects_zero_window() -> None:
    with pytest.raises(SdrTelemetryValidationError, match="window_duration_s"):
        _make_telemetry(window_s=0.0)


# ---------------------------------------------------------------------------
# Config validation tests
# ---------------------------------------------------------------------------


def test_config_rejects_inverted_rssi_range() -> None:
    with pytest.raises(SdrTelemetryValidationError):
        SdrMappingConfig(
            rssi_baseline_dbm=-100.0,
            rssi_noise_floor_dbm=-40.0,  # floor > baseline
        )


def test_config_rejects_inverted_snr_band() -> None:
    with pytest.raises(SdrTelemetryValidationError):
        SdrMappingConfig(
            rssi_baseline_dbm=-40.0,
            rssi_noise_floor_dbm=-100.0,
            ambiguous_snr_low_db=5.0,
            ambiguous_snr_high_db=2.0,
        )
