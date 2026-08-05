"""
SDR telemetry record types.

``SdrTelemetry`` is the canonical record produced by the receiver-side collection
process (GNU Radio, SoapySDR, or similar) before any schema mapping is applied.
All fields are typed; callers must validate before constructing an instance.

No transmitter-control fields appear in this module.  The telemetry record is
strictly a *receiver observation*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime


class SdrTelemetryValidationError(ValueError):
    """Raised when an ``SdrTelemetry`` field is out of range or incoherent."""


@dataclass(frozen=True)
class SdrTelemetry:
    """Single SDR receiver observation window.

    Fields
    ------
    rssi_dbm:
        Received signal strength indication in dBm.  Typically in the range
        -120 to 0 dBm.  Must be a finite float; ``math.nan`` is rejected.
    snr_db:
        Signal-to-noise ratio in dB.  Typically -20 to 40 dB.  Must be finite.
        Use ``evidence_initially_insufficient=True`` if SNR is unmeasurable.
    ber:
        Bit error rate, dimensionless, in [0.0, 1.0].  ``None`` when not
        available for this window (e.g., un-framed raw IQ; use ``ber=None``
        and set ``packet_loss_rate`` instead).
    packet_loss_rate:
        Fraction of frames lost, dimensionless, in [0.0, 1.0].  ``None`` when
        not available.  At least one of ``ber`` or ``packet_loss_rate`` must
        be non-None for the mapping to produce a meaningful ``noise`` estimate.
    source_timestamp_utc:
        UTC datetime at which the receiver hardware produced this measurement.
    ingestion_timestamp_utc:
        UTC datetime at which this record was written to the harness buffer.
    window_duration_s:
        Integration / averaging window in seconds.  Must be > 0.
    is_valid:
        ``True`` if all measured fields are within the expected operating range
        and no measurement fault was flagged by the radio driver.
    is_stale:
        ``True`` if ``ingestion_timestamp_utc - source_timestamp_utc`` exceeds
        the protocol-defined maximum staleness threshold.
    is_malformed:
        ``True`` if the record was parsed from a byte stream that contained
        framing errors, CRC failures, or missing mandatory fields.
    scenario_id:
        Identifier of the bench scenario currently active (e.g., "A-baseline").
        Used for audit correlation only; does not affect the mapping.
    trial_id:
        Identifier of the specific trial within the scenario.
        Used for audit correlation only; does not affect the mapping.
    """

    rssi_dbm: float
    snr_db: float
    ber: float | None
    packet_loss_rate: float | None
    source_timestamp_utc: datetime
    ingestion_timestamp_utc: datetime
    window_duration_s: float
    is_valid: bool
    is_stale: bool
    is_malformed: bool
    scenario_id: str
    trial_id: str

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not math.isfinite(self.rssi_dbm):
            raise SdrTelemetryValidationError(
                f"rssi_dbm must be finite, got {self.rssi_dbm!r}"
            )
        if not math.isfinite(self.snr_db):
            raise SdrTelemetryValidationError(
                f"snr_db must be finite, got {self.snr_db!r}"
            )
        if self.ber is not None and not (0.0 <= self.ber <= 1.0):
            raise SdrTelemetryValidationError(
                f"ber must be in [0, 1], got {self.ber!r}"
            )
        if self.packet_loss_rate is not None and not (
            0.0 <= self.packet_loss_rate <= 1.0
        ):
            raise SdrTelemetryValidationError(
                f"packet_loss_rate must be in [0, 1], got {self.packet_loss_rate!r}"
            )
        if not (self.window_duration_s > 0):
            raise SdrTelemetryValidationError(
                f"window_duration_s must be > 0, got {self.window_duration_s!r}"
            )
        if self.source_timestamp_utc.tzinfo is None:
            raise SdrTelemetryValidationError(
                "source_timestamp_utc must be timezone-aware"
            )
        if self.ingestion_timestamp_utc.tzinfo is None:
            raise SdrTelemetryValidationError(
                "ingestion_timestamp_utc must be timezone-aware"
            )


@dataclass(frozen=True)
class SdrMappingConfig:
    """Configuration for the ``SdrObservationMapper``.

    All numeric parameters must be set from the frozen physical-test protocol
    before the bench run begins.  They must not be adjusted after observing any
    Advisor output.

    Fields
    ------
    rssi_baseline_dbm:
        RSSI measured at the receiver during the warm-up period with 0 dB
        attenuation and no injected impairments.  Determined empirically
        before any test trial; recorded in the bench protocol.
    rssi_noise_floor_dbm:
        Receiver noise floor in dBm.  From manufacturer specification for the
        exact RTL-SDR hardware revision and frequency in use.
    min_window_duration_s:
        Minimum valid observation window.  Records with ``window_duration_s``
        below this value set ``evidence_initially_insufficient=True``.
    ambiguous_snr_low_db:
        Lower bound of the ambiguous SNR band (inclusive).  Records whose
        ``snr_db`` falls in ``[ambiguous_snr_low_db, ambiguous_snr_high_db]``
        and are otherwise valid will set ``evidence_initially_insufficient=True``.
    ambiguous_snr_high_db:
        Upper bound of the ambiguous SNR band (inclusive).
    max_staleness_s:
        Maximum permitted lag between ``source_timestamp_utc`` and
        ``ingestion_timestamp_utc`` in seconds.
    """

    rssi_baseline_dbm: float
    rssi_noise_floor_dbm: float
    min_window_duration_s: float = 0.5
    ambiguous_snr_low_db: float = 0.0
    ambiguous_snr_high_db: float = 3.0
    max_staleness_s: float = 2.0

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self.rssi_noise_floor_dbm >= self.rssi_baseline_dbm:
            raise SdrTelemetryValidationError(
                "rssi_noise_floor_dbm must be less than rssi_baseline_dbm"
            )
        dynamic_range = self.rssi_baseline_dbm - self.rssi_noise_floor_dbm
        if dynamic_range <= 0:
            raise SdrTelemetryValidationError(
                f"dynamic_range_db must be > 0, got {dynamic_range!r}"
            )
        if self.min_window_duration_s <= 0:
            raise SdrTelemetryValidationError("min_window_duration_s must be > 0")
        if self.ambiguous_snr_low_db > self.ambiguous_snr_high_db:
            raise SdrTelemetryValidationError(
                "ambiguous_snr_low_db must be <= ambiguous_snr_high_db"
            )
        if self.max_staleness_s <= 0:
            raise SdrTelemetryValidationError("max_staleness_s must be > 0")

    @property
    def dynamic_range_db(self) -> float:
        return self.rssi_baseline_dbm - self.rssi_noise_floor_dbm
