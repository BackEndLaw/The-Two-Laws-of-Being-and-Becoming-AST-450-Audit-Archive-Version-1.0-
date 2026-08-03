from __future__ import annotations

# Phase V-B canonical result schema: rescueos-selection-result-v1
#
# This module defines:
#   - SelectionResultV1 — the typed result record
#   - load_selection_result — fail-closed loader/validator
#
# Supported outcomes: provisional_selection, no_controller_selected only.
# Reject: unknown/missing/extra fields, invalid hashes, fabricated or
# ineligible selections, oracle selection, preregistration mismatches.
#
# IMPORTANT: no real result may be created in this PR.  Use synthetic
# fixtures only.
import json
import re
from dataclasses import dataclass
from typing import Any

from qrtc_benchmark.selection_protocol import (
    IMPLEMENTATION_COMMIT,
    MANDATORY_CANDIDATES,
    PROTOCOL_ID,
    PROTOCOL_PHASE_REVISION,
    canonical_json_bytes,
    compute_protocol_hashes,
)

RESULT_SCHEMA: str = "rescueos-selection-result-v1"

_VALID_OUTCOMES: frozenset[str] = frozenset(
    {"provisional_selection", "no_controller_selected"}
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "result_schema",
        "protocol_id",
        "protocol_hash",
        "phase_revision",
        "stage",
        "input_hashes",
        "implementation_commit",
        "metrics_summary",
        "eligibility_reasons",
        "bootstrap_comparisons",
        "selected_id",
        "oracle_ceiling",
        "authority",
        "hardware_actuation_enabled",
        "final_validation_status",
        "outcome",
    }
)

_VALID_STAGES: frozenset[str] = frozenset({"development", "selection-validation"})


class SelectionResultValidationError(ValueError):
    """Raised when a selection result fails schema validation."""


@dataclass(frozen=True)
class SelectionResultV1:
    """Canonical rescueos-selection-result-v1 record.

    Fields are validated against the frozen preregistration on load.
    """

    result_schema: str
    protocol_id: str
    protocol_hash: str
    phase_revision: str
    stage: str
    input_hashes: dict[str, str]
    implementation_commit: str
    metrics_summary: dict[str, Any]
    eligibility_reasons: dict[str, Any]
    bootstrap_comparisons: dict[str, Any]
    selected_id: str | None
    oracle_ceiling: dict[str, Any]
    authority: str
    hardware_actuation_enabled: bool
    final_validation_status: str
    outcome: str

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "result_schema": self.result_schema,
                "protocol_id": self.protocol_id,
                "protocol_hash": self.protocol_hash,
                "phase_revision": self.phase_revision,
                "stage": self.stage,
                "input_hashes": self.input_hashes,
                "implementation_commit": self.implementation_commit,
                "metrics_summary": self.metrics_summary,
                "eligibility_reasons": self.eligibility_reasons,
                "bootstrap_comparisons": self.bootstrap_comparisons,
                "selected_id": self.selected_id,
                "oracle_ceiling": self.oracle_ceiling,
                "authority": self.authority,
                "hardware_actuation_enabled": self.hardware_actuation_enabled,
                "final_validation_status": self.final_validation_status,
                "outcome": self.outcome,
            }
        )


def _validate_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SelectionResultValidationError(f"invalid {field}: expected 64-hex string")
    return value


def _validate_commit(value: object, field: str) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise SelectionResultValidationError(f"invalid {field}: expected 40-hex commit")
    return value


def _check_fields(payload: dict[str, object]) -> None:
    missing = sorted(_REQUIRED_FIELDS - set(payload))
    extra = sorted(set(payload) - _REQUIRED_FIELDS)
    if missing or extra:
        raise SelectionResultValidationError(
            f"result schema field mismatch (missing={missing}, extra={extra})"
        )


def load_selection_result(
    payload_or_json: dict[str, object] | str | bytes,
) -> SelectionResultV1:
    """Fail-closed loader and validator for rescueos-selection-result-v1.

    Validates:
    - Correct schema name
    - No missing/extra fields
    - Protocol ID and hash match preregistration
    - Phase revision matches
    - Stage is development or selection-validation only
    - Outcome is a known value
    - selected_id is None when outcome is no_controller_selected
    - selected_id is never oracle
    - selected_id must be in MANDATORY_CANDIDATES when set
    - implementation_commit is 40-hex
    - protocol_hash is 64-hex and matches computed canonical hash
    - authority == "recommend_only"
    - hardware_actuation_enabled == False
    - final_validation_status == "locked_not_executed"
    """
    if isinstance(payload_or_json, (str, bytes)):
        payload = json.loads(payload_or_json)
    else:
        payload = payload_or_json

    if not isinstance(payload, dict):
        raise SelectionResultValidationError("result payload must be a JSON object")

    _check_fields(payload)

    # Schema version
    if payload["result_schema"] != RESULT_SCHEMA:
        raise SelectionResultValidationError(
            f"unsupported result_schema {payload['result_schema']!r}; expected {RESULT_SCHEMA!r}"
        )

    # Protocol identity
    if payload["protocol_id"] != PROTOCOL_ID:
        raise SelectionResultValidationError(
            f"protocol_id mismatch: got {payload['protocol_id']!r}, expected {PROTOCOL_ID!r}"
        )

    # Protocol hash — verify against canonical computed hash
    _validate_sha256(payload["protocol_hash"], "protocol_hash")
    expected_protocol_hash = compute_protocol_hashes().protocol_declaration_sha256
    if payload["protocol_hash"] != expected_protocol_hash:
        raise SelectionResultValidationError(
            "protocol_hash does not match canonical preregistration"
        )

    if payload["phase_revision"] != PROTOCOL_PHASE_REVISION:
        raise SelectionResultValidationError(
            f"phase_revision mismatch: got {payload['phase_revision']!r}"
        )

    # Stage
    if payload["stage"] not in _VALID_STAGES:
        raise SelectionResultValidationError(
            f"stage {payload['stage']!r} is not allowed; only {sorted(_VALID_STAGES)} are valid"
        )

    # Outcome
    if payload["outcome"] not in _VALID_OUTCOMES:
        raise SelectionResultValidationError(
            f"unknown outcome {payload['outcome']!r}; valid={sorted(_VALID_OUTCOMES)}"
        )

    # selected_id
    selected_id_raw = payload["selected_id"]
    if selected_id_raw is not None and not isinstance(selected_id_raw, str):
        raise SelectionResultValidationError("selected_id must be a string or null")

    if payload["outcome"] == "no_controller_selected" and selected_id_raw is not None:
        raise SelectionResultValidationError(
            "selected_id must be null when outcome is no_controller_selected"
        )

    if selected_id_raw == "oracle":
        raise SelectionResultValidationError("oracle cannot be selected")

    if selected_id_raw is not None and selected_id_raw not in MANDATORY_CANDIDATES:
        raise SelectionResultValidationError(
            f"selected_id {selected_id_raw!r} is not a mandatory candidate"
        )

    # Commit
    _validate_commit(payload["implementation_commit"], "implementation_commit")

    # Authority and hardware
    if payload["authority"] != "recommend_only":
        raise SelectionResultValidationError("authority must be recommend_only")
    if payload["hardware_actuation_enabled"] is not False:
        raise SelectionResultValidationError("hardware_actuation_enabled must be false")

    # Final validation lock
    if payload["final_validation_status"] != "locked_not_executed":
        raise SelectionResultValidationError(
            "final_validation_status must be locked_not_executed"
        )

    # input_hashes: all values must be 64-hex
    input_hashes_raw = payload["input_hashes"]
    if not isinstance(input_hashes_raw, dict):
        raise SelectionResultValidationError("input_hashes must be an object")
    for key, value in input_hashes_raw.items():
        _validate_sha256(value, f"input_hashes[{key!r}]")

    return SelectionResultV1(
        result_schema=str(payload["result_schema"]),
        protocol_id=str(payload["protocol_id"]),
        protocol_hash=str(payload["protocol_hash"]),
        phase_revision=str(payload["phase_revision"]),
        stage=str(payload["stage"]),
        input_hashes={str(k): str(v) for k, v in input_hashes_raw.items()},
        implementation_commit=str(payload["implementation_commit"]),
        metrics_summary=dict(payload["metrics_summary"]),  # type: ignore[arg-type]
        eligibility_reasons=dict(payload["eligibility_reasons"]),  # type: ignore[arg-type]
        bootstrap_comparisons=dict(payload["bootstrap_comparisons"]),  # type: ignore[arg-type]
        selected_id=selected_id_raw,
        oracle_ceiling=dict(payload["oracle_ceiling"]),  # type: ignore[arg-type]
        authority=str(payload["authority"]),
        hardware_actuation_enabled=False,
        final_validation_status=str(payload["final_validation_status"]),
        outcome=str(payload["outcome"]),
    )


def make_synthetic_no_selection_result(
    stage: str = "development",
    implementation_commit: str = IMPLEMENTATION_COMMIT,
) -> SelectionResultV1:
    """Return a synthetic no_controller_selected result for testing only.

    This result is NOT a real experiment outcome.  It is used exclusively
    in tests and CI smoke checks.  Do not use for actual selection.
    """
    if stage not in _VALID_STAGES:
        raise SelectionResultValidationError(f"stage {stage!r} is not a valid stage")
    protocol_hash = compute_protocol_hashes().protocol_declaration_sha256
    dummy_sha = "0" * 64
    return SelectionResultV1(
        result_schema=RESULT_SCHEMA,
        protocol_id=PROTOCOL_ID,
        protocol_hash=protocol_hash,
        phase_revision=PROTOCOL_PHASE_REVISION,
        stage=stage,
        input_hashes={"synthetic_input": dummy_sha},
        implementation_commit=implementation_commit,
        metrics_summary={},
        eligibility_reasons={},
        bootstrap_comparisons={},
        selected_id=None,
        oracle_ceiling={},
        authority="recommend_only",
        hardware_actuation_enabled=False,
        final_validation_status="locked_not_executed",
        outcome="no_controller_selected",
    )
