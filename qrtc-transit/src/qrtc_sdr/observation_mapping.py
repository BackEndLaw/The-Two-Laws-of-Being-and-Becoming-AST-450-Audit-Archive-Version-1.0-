"""
SDR-to-RescueOS observation mapping.

Maps a ``SdrTelemetry`` record to a ``Phase5OODCase`` for ingestion by the frozen
RescueOS Advisor.  The mapping is governed by ``SdrMappingSpec``, which is loaded
from the versioned JSON specification committed at
``artifacts/sdr-bench-v1/observation-mapping-spec.json``.

Architecture constraints
------------------------
- This module does NOT import or modify the frozen controller, causal graph,
  thresholds, action allowlist, or Advisor schemas.
- The mapping is one-way: telemetry → observation.  No Advisor output flows back
  through this module to any transmitter-control interface.
- All mapping parameters must be fixed before any bench trial begins.  Changing
  parameters after observing Advisor outputs is prohibited.

Discrete schema values
----------------------
The frozen observation schema (``phase5-ood-case-v1``) uses the following
discrete severity and noise levels:

  SEVERITIES   = (0.25, 0.50, 0.75, 1.00)
  NOISE_LEVELS = (0.00, 0.05, 0.10, 0.20)

Continuous physical measurements are rounded to the nearest discrete value in
each set.  See ``_quantize`` for the rounding logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from qrtc_benchmark.phase5 import (
    NOISE_LEVELS,
    SEVERITIES,
    DependencyType,
    Phase5Family,
    Phase5Intervention,
    Phase5OODCase,
    Phase5RelationType,
)
from qrtc_sdr.telemetry import (
    SdrMappingConfig,
    SdrTelemetry,
)

# ---------------------------------------------------------------------------
# Mapping schema version — must match the committed JSON spec.
# ---------------------------------------------------------------------------
MAPPING_SCHEMA_VERSION = "sdr-observation-mapping-v1"

# ---------------------------------------------------------------------------
# SDR bench mechanism and composition identifiers.
#
# These strings identify the physical SDR causal chain in the Advisor's audit
# record.  They are *not* in any benchmark pool (development, validation, test)
# and do not affect controller training or validation.
# ---------------------------------------------------------------------------
SDR_MECHANISM_ID = "sdr_rf_path_loss"
SDR_COMPOSITION_NOMINAL = "FG+FW+FJ"  # path-loss → SNR → packet-loss chain
SDR_COMPOSITION_UNKNOWN = "UNKNOWN"

# Criterion identifiers (from the frozen schema).
CRITERION_RSSI = "PI1"  # binding criterion: receiver sensitivity / path loss
CRITERION_SNR = "PI2"  # binding criterion: SNR / link quality
CRITERION_PLR = "PI3"  # binding criterion: packet-loss rate / application reliability


class SdrMappingError(ValueError):
    """Raised when a telemetry record cannot be mapped to a valid observation."""


# ---------------------------------------------------------------------------
# Required-actions bands
#
# Maps from the discrete severity value to the ordered required-action tuple
# for a V3 (FG+FW+FJ) three-fault chain observation.
#
# Band definitions (inclusive):
#   severity >= 0.75  →  (rG, rW, rJ)  — major path loss; all three interventions needed
#   severity == 0.50  →  (rW, rJ)       — moderate loss; witness + jurisdiction
#   severity == 0.25  →  (rJ,)          — minor degradation; jurisdiction threshold only
#   (no observation below 0.25 severity is mapped to a degraded state)
# ---------------------------------------------------------------------------
_SEVERITY_TO_REQUIRED_ACTIONS: dict[float, tuple[Phase5Intervention, ...]] = {
    1.00: (Phase5Intervention.rG, Phase5Intervention.rW, Phase5Intervention.rJ),
    0.75: (Phase5Intervention.rG, Phase5Intervention.rW, Phase5Intervention.rJ),
    0.50: (Phase5Intervention.rW, Phase5Intervention.rJ),
    0.25: (Phase5Intervention.rJ,),
}


def _quantize(value: float, levels: tuple[float, ...]) -> float:
    """Round *value* to the nearest element of *levels*.

    Uses midpoint rounding: ties go to the higher level.  *levels* must be
    sorted in ascending order and non-empty.
    """
    return min(levels, key=lambda lvl: (abs(lvl - value), -lvl))


def _compute_severity(rssi_dbm: float, config: SdrMappingConfig) -> float:
    """Compute normalised severity from RSSI.

    severity = clamp( (baseline - rssi) / dynamic_range, 0.0, 1.0 )

    Then rounded to the nearest discrete SEVERITIES value.
    """
    raw = (config.rssi_baseline_dbm - rssi_dbm) / config.dynamic_range_db
    clamped = max(0.0, min(1.0, raw))
    return _quantize(clamped, SEVERITIES)


def _compute_noise(ber: float | None, packet_loss_rate: float | None) -> float:
    """Compute normalised noise from BER and/or packet-loss rate.

    Takes the maximum of the two available indicators, clamps to [0, 0.20]
    (the maximum discrete noise level), then rounds to the nearest
    NOISE_LEVELS value.
    """
    candidates = [v for v in (ber, packet_loss_rate) if v is not None]
    if not candidates:
        return 0.0
    raw = max(candidates)
    clamped = max(0.0, min(max(NOISE_LEVELS), raw))
    return _quantize(clamped, NOISE_LEVELS)


def _select_criterion(severity: float, noise: float) -> str:
    """Select the *binding* criterion identifier.

    Rules:
    - If severity is the dominant signal (>= noise*2), the binding constraint
      is receiver sensitivity → PI1.
    - If noise > severity, the binding constraint is packet-loss rate → PI3.
    - Otherwise SNR is the binding constraint → PI2.
    """
    if severity >= noise * 2:
        return CRITERION_RSSI
    if noise > severity:
        return CRITERION_PLR
    return CRITERION_SNR


def _is_stale(telemetry: SdrTelemetry, config: SdrMappingConfig) -> bool:
    lag = (
        telemetry.ingestion_timestamp_utc.replace(tzinfo=UTC)
        if telemetry.ingestion_timestamp_utc.tzinfo is None
        else telemetry.ingestion_timestamp_utc
    ) - (
        telemetry.source_timestamp_utc.replace(tzinfo=UTC)
        if telemetry.source_timestamp_utc.tzinfo is None
        else telemetry.source_timestamp_utc
    )
    return lag.total_seconds() > config.max_staleness_s


def _is_ambiguous_snr(snr_db: float, config: SdrMappingConfig) -> bool:
    return config.ambiguous_snr_low_db <= snr_db <= config.ambiguous_snr_high_db


@dataclass(frozen=True)
class SdrObservationResult:
    """Output of the mapping step.

    ``case`` is ``None`` when the telemetry record is rejected (stale, malformed,
    or otherwise unmappable).  ``rejection_reason`` is non-empty when ``case``
    is ``None``.
    """

    telemetry: SdrTelemetry
    case: Phase5OODCase | None
    rejection_reason: str = ""
    severity_raw: float = 0.0
    noise_raw: float = 0.0
    severity_quantized: float = 0.0
    noise_quantized: float = 0.0

    @property
    def is_rejected(self) -> bool:
        return self.case is None


class SdrObservationMapper:
    """Maps ``SdrTelemetry`` records to ``Phase5OODCase`` observations.

    Parameters
    ----------
    config:
        ``SdrMappingConfig`` fixed before the bench run begins.  Must not be
        changed after any Advisor output has been observed.
    """

    def __init__(self, config: SdrMappingConfig) -> None:
        self._config = config

    @property
    def config(self) -> SdrMappingConfig:
        return self._config

    def map(self, telemetry: SdrTelemetry) -> SdrObservationResult:
        """Map a single telemetry record to a ``Phase5OODCase``.

        Returns an ``SdrObservationResult``.  If the record is rejected, the
        ``case`` field is ``None`` and ``rejection_reason`` explains why.

        Rejection conditions (in priority order):
        1. ``is_malformed`` is True.
        2. ``is_stale`` is True (as flagged in the record, or detected by lag).
        3. ``is_valid`` is False.
        4. Computed staleness exceeds ``config.max_staleness_s``.
        """
        if telemetry.is_malformed:
            return SdrObservationResult(
                telemetry=telemetry,
                case=None,
                rejection_reason="malformed_record",
            )
        if telemetry.is_stale:
            return SdrObservationResult(
                telemetry=telemetry,
                case=None,
                rejection_reason="stale_flagged_by_source",
            )
        if not telemetry.is_valid:
            return SdrObservationResult(
                telemetry=telemetry,
                case=None,
                rejection_reason="invalid_record",
            )
        if _is_stale(telemetry, self._config):
            return SdrObservationResult(
                telemetry=telemetry,
                case=None,
                rejection_reason="stale_detected_by_lag",
            )

        severity_raw = (
            self._config.rssi_baseline_dbm - telemetry.rssi_dbm
        ) / self._config.dynamic_range_db
        severity_raw = max(0.0, min(1.0, severity_raw))

        noise_raw_candidates = [
            v for v in (telemetry.ber, telemetry.packet_loss_rate) if v is not None
        ]
        noise_raw = max(noise_raw_candidates) if noise_raw_candidates else 0.0

        severity = _compute_severity(telemetry.rssi_dbm, self._config)
        noise = _compute_noise(telemetry.ber, telemetry.packet_loss_rate)
        criterion = _select_criterion(severity, noise)

        # Determine family and evidence-sufficiency flags.
        evidence_insufficient = (
            _is_ambiguous_snr(telemetry.snr_db, self._config)
            or telemetry.window_duration_s < self._config.min_window_duration_s
        )

        # V4 (unknown fault) when degradation is severe but RSSI loss doesn't
        # explain it (i.e., packet loss far exceeds what path loss predicts).
        is_unknown = (
            noise_raw > 0.30 and severity_raw < 0.10 and not evidence_insufficient
        )

        if is_unknown:
            family = Phase5Family.V4_UNKNOWN_FAULT
            composition_id = SDR_COMPOSITION_UNKNOWN
            dependency = DependencyType.NONE
            relation_type = Phase5RelationType.INDEPENDENT
            required: tuple[Phase5Intervention, ...] = ()
        else:
            family = Phase5Family.V3_THREE_FAULT
            composition_id = SDR_COMPOSITION_NOMINAL
            dependency = DependencyType.CHAIN
            relation_type = Phase5RelationType.INDEPENDENT
            required = _SEVERITY_TO_REQUIRED_ACTIONS.get(
                severity,
                (Phase5Intervention.rJ,),
            )

        case = Phase5OODCase(
            family=family,
            mechanism_id=SDR_MECHANISM_ID,
            composition_id=composition_id,
            relation_type=relation_type,
            criterion=criterion,
            severity=severity,
            noise=noise,
            dependency_type=dependency,
            unknown_fault=is_unknown,
            evidence_initially_insufficient=evidence_insufficient,
            required_actions=required,
        )

        return SdrObservationResult(
            telemetry=telemetry,
            case=case,
            rejection_reason="",
            severity_raw=severity_raw,
            noise_raw=noise_raw,
            severity_quantized=severity,
            noise_quantized=noise,
        )


# ---------------------------------------------------------------------------
# Spec loading
# ---------------------------------------------------------------------------


def load_mapping_spec(spec_path: str | Path) -> dict[str, Any]:
    """Load and minimally validate the mapping-spec JSON document.

    Does NOT modify the frozen Advisor schemas.  Returns the raw dict for
    audit-record inclusion.
    """
    path = Path(spec_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SdrMappingError("mapping spec must be a JSON object")
    if raw.get("schema_version") != MAPPING_SCHEMA_VERSION:
        raise SdrMappingError(
            f"unsupported mapping spec schema_version: {raw.get('schema_version')!r}"
        )
    return raw


def config_from_spec(spec: dict[str, Any]) -> SdrMappingConfig:
    """Build an ``SdrMappingConfig`` from a loaded mapping-spec dict."""
    try:
        return SdrMappingConfig(
            rssi_baseline_dbm=float(spec["rssi_baseline_dbm"]),
            rssi_noise_floor_dbm=float(spec["rssi_noise_floor_dbm"]),
            min_window_duration_s=float(spec["min_window_duration_s"]),
            ambiguous_snr_low_db=float(spec["ambiguous_snr_low_db"]),
            ambiguous_snr_high_db=float(spec["ambiguous_snr_high_db"]),
            max_staleness_s=float(spec["max_staleness_s"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SdrMappingError(f"invalid mapping spec field: {exc}") from exc
