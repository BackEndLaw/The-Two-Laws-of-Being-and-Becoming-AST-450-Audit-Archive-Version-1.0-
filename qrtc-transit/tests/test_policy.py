from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from qrtc.config import load_input_document
from qrtc.pipeline import build_configured_pipeline
from qrtc.policy import (
    PolicyValidationError,
    load_policy_document,
    validate_policy_document,
)
from qrtc.registry import (
    ComponentRegistry,
    PolicyResolutionError,
    build_default_registry,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_valid_versioned_policy_loads_successfully() -> None:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")

    assert policy.policy_id == "telemetry-transit"
    assert policy.policy_version == "1.0.0"
    assert policy.boat_encoding == "canonical-json-v1"


def test_policy_validation_rejects_unknown_fields() -> None:
    document = json.loads(
        (EXAMPLES / "telemetry-policy.json").read_text(encoding="utf-8")
    )
    document["unexpected"] = True

    with pytest.raises(PolicyValidationError):
        validate_policy_document(document)


def test_policy_files_cannot_execute_code(tmp_path: Path) -> None:
    malicious = tmp_path / "malicious-policy.json"
    malicious.write_text("import os\nos.system('echo unsafe')\n", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_policy_document(malicious)


def test_missing_component_references_fail_before_transit_begins() -> None:
    policy = load_policy_document(EXAMPLES / "telemetry-policy.json")
    input_record = load_input_document(EXAMPLES / "telemetry-input.json")

    bad_policy = replace(policy, guards=("telemetry-schema-v1", "missing-guard-v9"))

    with pytest.raises(PolicyResolutionError):
        build_configured_pipeline(bad_policy, input_record, build_default_registry())


def test_duplicate_registry_identifiers_are_rejected() -> None:
    registry = ComponentRegistry()

    registry.register_gate("duplicate-id", lambda request, auth: None)

    with pytest.raises(ValueError):
        registry.register_gate("duplicate-id", lambda request, auth: None)
