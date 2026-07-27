from __future__ import annotations

import json
from pathlib import Path

import pytest

import qrtc.policy as policy_module
from qrtc.cli import INTERNAL_ERROR_EXIT_CODE, main
from qrtc.exceptions import ResourceLimitError
from qrtc.limits import ResourceLimits, enforce_json_limits
from qrtc.registry import ComponentRegistry, build_default_registry
from qrtc.verification import (
    canonical_policy_bytes,
    policy_digest,
    registry_snapshot_id,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _base_policy() -> dict[str, object]:
    return {
        "policy_id": "telemetry-transit",
        "policy_version": "1.0.0",
        "predecessor_class": "equipment",
        "future_family": "telemetry-payload",
        "key_policy": "telemetry-key-v1",
        "gate": "telemetry-gate-v1",
        "guards": ["telemetry-schema-v1", "telemetry-ranges-v1"],
        "boat": {"schema": "telemetry-interface-v1", "encoding": "canonical-json-v1"},
        "river": {"route": "operations-route-v1"},
        "realizer": "alarm-record-v1",
        "stabilizer": "alarm-persistence-v1",
        "witness_policy": "telemetry-witness-v1",
    }


def test_equivalent_policies_have_identical_canonical_bytes() -> None:
    left = _base_policy()
    right = {
        "witness_policy": "telemetry-witness-v1",
        "stabilizer": "alarm-persistence-v1",
        "realizer": "alarm-record-v1",
        "river": {"route": "operations-route-v1"},
        "boat": {"encoding": "canonical-json-v1", "schema": "telemetry-interface-v1"},
        "guards": ["telemetry-schema-v1", "telemetry-ranges-v1"],
        "gate": "telemetry-gate-v1",
        "key_policy": "telemetry-key-v1",
        "future_family": "telemetry-payload",
        "predecessor_class": "equipment",
        "policy_version": "1.0.0",
        "policy_id": "telemetry-transit",
    }

    assert canonical_policy_bytes(left) == canonical_policy_bytes(right)
    assert policy_digest(left) == policy_digest(right)


def test_array_order_changes_policy_digest() -> None:
    left = _base_policy()
    right = _base_policy()
    right["guards"] = ["telemetry-ranges-v1", "telemetry-schema-v1"]

    assert policy_digest(left) != policy_digest(right)


def test_same_policy_identity_different_content_changes_digest() -> None:
    left = _base_policy()
    right = _base_policy()
    right["river"] = {"route": "operations-route-v2"}

    assert left["policy_id"] == right["policy_id"]
    assert left["policy_version"] == right["policy_version"]
    assert policy_digest(left) != policy_digest(right)


def test_registry_snapshot_is_deterministic() -> None:
    first = registry_snapshot_id(build_default_registry())
    second = registry_snapshot_id(build_default_registry())
    assert first == second


def test_registry_snapshot_changes_when_component_version_changes() -> None:
    def _gate(request: object, auth: object) -> object:
        return request

    first_builder = ComponentRegistry()
    first_builder.register_gate("gate", _gate, version="1.0.0")

    second_builder = ComponentRegistry()
    second_builder.register_gate("gate", _gate, version="2.0.0")

    assert registry_snapshot_id(first_builder.freeze()) != registry_snapshot_id(
        second_builder.freeze()
    )


def test_oversized_policy_fails_before_loading(tmp_path: Path) -> None:
    prior = policy_module.DEFAULT_LIMITS
    try:
        policy_module.DEFAULT_LIMITS = ResourceLimits(max_policy_bytes=16)
        path = tmp_path / "big-policy.json"
        path.write_text(json.dumps(_base_policy()), encoding="utf-8")

        with pytest.raises(ResourceLimitError):
            policy_module.load_policy_document(path)
    finally:
        policy_module.DEFAULT_LIMITS = prior


def test_excessive_json_depth_fails_safely() -> None:
    payload: object = "leaf"
    for _ in range(8):
        payload = {"x": payload}

    with pytest.raises(ResourceLimitError):
        enforce_json_limits(payload, ResourceLimits(max_json_depth=4))


def test_invalid_limits_are_rejected() -> None:
    with pytest.raises(ValueError):
        ResourceLimits(max_policy_bytes=0)

    with pytest.raises(ValueError):
        ResourceLimits(max_json_depth=-1)


def test_cli_unexpected_exception_maps_to_internal_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "evidence.sqlite3"

    def _raise(*_args: object, **_kwargs: object) -> tuple[object, object]:
        raise RuntimeError("boom")

    monkeypatch.setattr("qrtc.cli.execute_configured_transit", _raise)

    code = main(
        [
            "transit",
            "run",
            "--policy",
            str(EXAMPLES / "telemetry-policy.json"),
            "--input",
            str(EXAMPLES / "telemetry-input.json"),
            "--db",
            str(db_path),
        ]
    )

    assert code == INTERNAL_ERROR_EXIT_CODE
    stderr = capsys.readouterr().err
    assert "internal error" in stderr
    assert "Traceback" not in stderr
