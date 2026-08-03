"""
SDR bench harness skeleton — offline / observation-only.

This module provides ``SdrBenchHarness``, an offline harness that:

1. Accepts ``SdrTelemetry`` records from the receiver side.
2. Maps each record to a ``Phase5OODCase`` via ``SdrObservationMapper``.
3. Passes the observation to the frozen Advisor
   (``qrtc_benchmark.controller_artifact``) and collects a recommendation.
4. Writes a checksummed audit record for every trial.
5. Enforces one-way data flow: the Advisor receives observations but cannot
   address a transmitter-control interface.

Architecture constraints (enforced by this module):
- The harness holds NO transmitter device handle, serial port, socket, or USB
  reference that could carry transmitter commands.
- The harness does NOT translate Advisor output into any HackRF or SDR TX command.
- ``advisor_transmitter_bytes`` is a counter that must remain **zero** throughout
  every bench run.  Any non-zero value is a protocol violation.
- The Advisor output is written to an in-memory audit log only; it is never
  forwarded to the bench harness transmitter control path.

Offline / physical modes
------------------------
In offline mode (the only mode available in this skeleton) the harness accepts
pre-recorded or synthetic ``SdrTelemetry`` objects.  Physical bench operation
requires separate transmitter-side software that runs as a distinct process.

This skeleton is used for:
- Schema plumbing tests (determinism, unit/range validation, rejection logic).
- Audit-record generation and checksum verification.
- Isolation proofs (zero advisor→TX bytes).

It does NOT produce physical-bench results and must not be cited as evidence of
physical performance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from qrtc_benchmark.controller_artifact import (
    SelectedControllerBundle,
    selected_controller_decision_checksum,
)
from qrtc_benchmark.controllers import ControllerDefinition
from qrtc_benchmark.phase5 import (
    INTERVENTION_COSTS_BASE,
    Phase5Intervention,
    Phase5OODCase,
)
from qrtc_sdr.observation_mapping import SdrObservationMapper, SdrObservationResult
from qrtc_sdr.telemetry import SdrTelemetry


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class AuditRecord:
    """Immutable audit record produced for every trial.

    ``advisor_transmitter_bytes`` must be zero.  Any non-zero value indicates a
    protocol violation and must be reported immediately.
    """

    trial_index: int
    scenario_id: str
    trial_id: str
    source_timestamp_utc: str
    ingestion_timestamp_utc: str
    harness_timestamp_utc: str
    mapping_result: str  # "mapped" or rejection reason
    observation_json: str | None  # JSON of Phase5OODCase, or null if rejected
    advisor_action_sequence: list[str] | None
    advisor_authority: str
    advisor_hardware_actuation_enabled: bool
    decision_sha256: str | None
    advisor_transmitter_bytes: int
    audit_record_sha256: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.audit_record_sha256 = self._compute_checksum()

    def _compute_checksum(self) -> str:
        payload = {
            "trial_index": self.trial_index,
            "scenario_id": self.scenario_id,
            "trial_id": self.trial_id,
            "source_timestamp_utc": self.source_timestamp_utc,
            "ingestion_timestamp_utc": self.ingestion_timestamp_utc,
            "harness_timestamp_utc": self.harness_timestamp_utc,
            "mapping_result": self.mapping_result,
            "observation_json": self.observation_json,
            "advisor_action_sequence": self.advisor_action_sequence,
            "advisor_authority": self.advisor_authority,
            "advisor_hardware_actuation_enabled": self.advisor_hardware_actuation_enabled,
            "decision_sha256": self.decision_sha256,
            "advisor_transmitter_bytes": self.advisor_transmitter_bytes,
        }
        return _sha256_hex(_canonical_json_bytes(payload))

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_index": self.trial_index,
            "scenario_id": self.scenario_id,
            "trial_id": self.trial_id,
            "source_timestamp_utc": self.source_timestamp_utc,
            "ingestion_timestamp_utc": self.ingestion_timestamp_utc,
            "harness_timestamp_utc": self.harness_timestamp_utc,
            "mapping_result": self.mapping_result,
            "observation_json": self.observation_json,
            "advisor_action_sequence": self.advisor_action_sequence,
            "advisor_authority": self.advisor_authority,
            "advisor_hardware_actuation_enabled": self.advisor_hardware_actuation_enabled,
            "decision_sha256": self.decision_sha256,
            "advisor_transmitter_bytes": self.advisor_transmitter_bytes,
            "audit_record_sha256": self.audit_record_sha256,
        }


def _observation_to_dict(case: Phase5OODCase) -> dict[str, Any]:
    return {
        "family": case.family.value,
        "mechanism_id": case.mechanism_id,
        "composition_id": case.composition_id,
        "relation_type": case.relation_type.value,
        "criterion": case.criterion,
        "severity": case.severity,
        "noise": case.noise,
        "dependency_type": case.dependency_type.value,
        "unknown_fault": case.unknown_fault,
        "evidence_initially_insufficient": case.evidence_initially_insufficient,
        "required_actions": [a.value for a in case.required_actions],
    }


class _AdvisorTransmitterInterface:
    """Null transmitter interface — proves that zero bytes are sent.

    The Advisor is given no endpoint, device handle, or socket that could carry
    transmitter commands.  This class exists solely to make the zero-byte
    constraint explicit and testable.
    """

    def __init__(self) -> None:
        self._bytes_sent = 0

    @property
    def bytes_sent(self) -> int:
        return self._bytes_sent

    def send(self, data: bytes) -> None:  # pragma: no cover
        # This method must never be called.  If it is, something has violated
        # the isolation constraint.
        self._bytes_sent += len(data)
        raise RuntimeError(
            "PROTOCOL VIOLATION: Advisor-originated transmitter-control traffic "
            f"({len(data)} bytes).  The harness must have zero TX bytes from the Advisor."
        )


class SdrBenchHarness:
    """Offline SDR bench harness skeleton.

    Parameters
    ----------
    mapper:
        Configured ``SdrObservationMapper`` with parameters fixed before any
        bench trial begins.
    bundle:
        Frozen ``SelectedControllerBundle`` loaded from the release asset.
    controller:
        Frozen ``ControllerDefinition`` loaded alongside the bundle.

    Usage
    -----
    ::

        harness = SdrBenchHarness(mapper, bundle, controller)
        for telemetry in offline_records:
            record = harness.process(telemetry)
            # record.advisor_transmitter_bytes must be zero
        assert harness.advisor_transmitter_bytes == 0
    """

    def __init__(
        self,
        mapper: SdrObservationMapper,
        bundle: SelectedControllerBundle,
        controller: ControllerDefinition,
    ) -> None:
        self._mapper = mapper
        self._bundle = bundle
        self._controller = controller
        self._tx_interface = _AdvisorTransmitterInterface()
        self._audit_log: list[AuditRecord] = []
        self._trial_counter = 0

    @property
    def advisor_transmitter_bytes(self) -> int:
        """Total bytes the Advisor attempted to send to the transmitter.

        Must be zero for the entire bench run.  Any non-zero value is a
        protocol violation.
        """
        return self._tx_interface.bytes_sent

    @property
    def audit_log(self) -> list[AuditRecord]:
        return list(self._audit_log)

    def process(self, telemetry: SdrTelemetry) -> AuditRecord:
        """Process one ``SdrTelemetry`` record through the full harness pipeline.

        Steps:
        1. Map telemetry to a ``Phase5OODCase``.
        2. If mapping succeeds, submit the case to the frozen Advisor.
        3. Compute ``decision_sha256`` from the Advisor output.
        4. Produce and log an ``AuditRecord``.

        The ``_AdvisorTransmitterInterface`` prevents any Advisor output from
        being forwarded to the transmitter.

        Returns the ``AuditRecord`` appended to ``self.audit_log``.
        """
        self._trial_counter += 1
        harness_ts = datetime.now(UTC).isoformat()

        mapping_result_obj: SdrObservationResult = self._mapper.map(telemetry)

        if mapping_result_obj.is_rejected:
            record = AuditRecord(
                trial_index=self._trial_counter,
                scenario_id=telemetry.scenario_id,
                trial_id=telemetry.trial_id,
                source_timestamp_utc=telemetry.source_timestamp_utc.isoformat(),
                ingestion_timestamp_utc=telemetry.ingestion_timestamp_utc.isoformat(),
                harness_timestamp_utc=harness_ts,
                mapping_result=mapping_result_obj.rejection_reason,
                observation_json=None,
                advisor_action_sequence=None,
                advisor_authority=self._bundle.authority,
                advisor_hardware_actuation_enabled=(
                    self._bundle.hardware_actuation_enabled
                ),
                decision_sha256=None,
                advisor_transmitter_bytes=self._tx_interface.bytes_sent,
            )
            self._audit_log.append(record)
            return record

        case = mapping_result_obj.case
        assert case is not None  # mapping_result_obj.is_rejected is False

        # Call the frozen controller.  The controller returns an action sequence.
        # We use a fixed reliability and seed for determinism; these are set by
        # the frozen protocol.
        reliability = 1.0
        seed = 0
        raw_params = self._bundle.controller_parameters
        action_costs_raw = (
            raw_params.get("action_costs") if isinstance(raw_params, dict) else None
        )
        costs: dict[Phase5Intervention, float]
        if isinstance(action_costs_raw, dict):
            costs = {
                Phase5Intervention(str(k)): float(v)
                for k, v in action_costs_raw.items()
            }
        else:
            costs = dict(INTERVENTION_COSTS_BASE)

        action_sequence = self._controller.select_actions(
            case, reliability, costs, seed
        )

        # Compute decision_sha256 from the Advisor output.
        decision_sha = selected_controller_decision_checksum(
            self._bundle, self._controller
        )

        # The Advisor output is written to the audit record only.
        # It is NOT forwarded to the transmitter interface.
        observation_dict = _observation_to_dict(case)
        observation_json = json.dumps(
            observation_dict, sort_keys=True, separators=(",", ":")
        )

        record = AuditRecord(
            trial_index=self._trial_counter,
            scenario_id=telemetry.scenario_id,
            trial_id=telemetry.trial_id,
            source_timestamp_utc=telemetry.source_timestamp_utc.isoformat(),
            ingestion_timestamp_utc=telemetry.ingestion_timestamp_utc.isoformat(),
            harness_timestamp_utc=harness_ts,
            mapping_result="mapped",
            observation_json=observation_json,
            advisor_action_sequence=[a.value for a in action_sequence],
            advisor_authority=self._bundle.authority,
            advisor_hardware_actuation_enabled=(
                self._bundle.hardware_actuation_enabled
            ),
            decision_sha256=decision_sha,
            advisor_transmitter_bytes=self._tx_interface.bytes_sent,
        )
        self._audit_log.append(record)
        return record
