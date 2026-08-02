from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from qrtc_benchmark.controller_artifact import (
    ARTIFACT_SCHEMA,
    ControllerArtifactValidationError,
    freeze_controller_artifact,
    load_controller_artifact,
)
from qrtc_benchmark.controllers import UnknownControllerError


def _valid_commit() -> str:
    return "a" * 40


def _freeze_payload(tmp_path: Path, controller_id: str = "qrtc") -> dict[str, object]:
    output = tmp_path / "controller.json"
    freeze_controller_artifact(
        controller_id=controller_id,
        implementation_commit=_valid_commit(),
        output_path=output,
    )
    return json.loads(output.read_text(encoding="utf-8"))


def test_freeze_round_trip_and_canonical_schema(tmp_path: Path) -> None:
    output = tmp_path / "controller.json"
    artifact = freeze_controller_artifact(
        controller_id="qrtc",
        implementation_commit=_valid_commit(),
        output_path=output,
    )
    loaded_artifact, loaded_controller = load_controller_artifact(output)
    assert loaded_artifact == artifact
    assert loaded_controller.controller_id == "qrtc"
    assert loaded_artifact.artifact_schema == ARTIFACT_SCHEMA


def test_freeze_rejects_unknown_controller_and_invalid_commit(tmp_path: Path) -> None:
    with pytest.raises(UnknownControllerError):
        freeze_controller_artifact(
            controller_id="missing",
            implementation_commit=_valid_commit(),
            output_path=tmp_path / "x.json",
        )

    with pytest.raises(ControllerArtifactValidationError):
        freeze_controller_artifact(
            controller_id="qrtc",
            implementation_commit="ABC",
            output_path=tmp_path / "x.json",
        )


def test_deployable_freeze_rejects_oracle(tmp_path: Path) -> None:
    with pytest.raises(ControllerArtifactValidationError):
        freeze_controller_artifact(
            controller_id="oracle",
            implementation_commit=_valid_commit(),
            output_path=tmp_path / "x.json",
            deployable_only=True,
        )


def test_default_loader_rejects_oracle_but_allow_flag_permits_it(
    tmp_path: Path,
) -> None:
    output = tmp_path / "oracle.json"
    freeze_controller_artifact(
        controller_id="oracle",
        implementation_commit=_valid_commit(),
        output_path=output,
    )

    with pytest.raises(ControllerArtifactValidationError):
        load_controller_artifact(output)

    artifact, controller = load_controller_artifact(
        output,
        allow_oracle=True,
        deployable_only=False,
    )
    assert artifact.controller_id == "oracle"
    assert controller.controller_id == "oracle"


def test_canonical_bytes_are_identical_across_processes_and_directories(
    tmp_path: Path,
) -> None:
    package_root = Path(__file__).resolve().parents[2]
    src_dir = package_root / "src"
    out_one = tmp_path / "a" / "controller.json"
    out_two = tmp_path / "b" / "controller.json"
    command = (
        "from pathlib import Path\n"
        "from qrtc_benchmark.controller_artifact import freeze_controller_artifact\n"
        "freeze_controller_artifact(controller_id='qrtc', implementation_commit='"
        + _valid_commit()
        + "', output_path=Path(r'{}'))\n"
    )

    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_dir)

    subprocess.run(
        [sys.executable, "-c", command.format(out_one)],
        cwd=package_root,
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "-c", command.format(out_two)],
        cwd=package_root,
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert out_one.read_bytes() == out_two.read_bytes()


def test_loader_rejects_hash_mismatches_individually(tmp_path: Path) -> None:
    payload = _freeze_payload(tmp_path)
    for field in (
        "causal_schema_sha256",
        "action_catalog_sha256",
        "configuration_sha256",
        "implementation_sha256",
    ):
        tampered = dict(payload)
        tampered[field] = "0" * 64
        with pytest.raises(ControllerArtifactValidationError):
            load_controller_artifact(tampered)


def test_loader_rejects_schema_version_and_field_tampering(tmp_path: Path) -> None:
    payload = _freeze_payload(tmp_path)

    bad_schema = dict(payload)
    bad_schema["artifact_schema"] = "wrong"
    with pytest.raises(ControllerArtifactValidationError):
        load_controller_artifact(bad_schema)

    bad_version = dict(payload)
    bad_version["controller_version"] = "phase5b-rule-policy-v0"
    with pytest.raises(ControllerArtifactValidationError):
        load_controller_artifact(bad_version)

    missing = dict(payload)
    del missing["authority"]
    with pytest.raises(ControllerArtifactValidationError):
        load_controller_artifact(missing)

    extra = dict(payload)
    extra["unknown"] = 1
    with pytest.raises(ControllerArtifactValidationError):
        load_controller_artifact(extra)


def test_loader_rejects_commit_hash_and_authority_hardware_tampering(
    tmp_path: Path,
) -> None:
    payload = _freeze_payload(tmp_path)

    bad_commit = dict(payload)
    bad_commit["implementation_commit"] = "A" * 40
    with pytest.raises(ControllerArtifactValidationError):
        load_controller_artifact(bad_commit)

    for field in (
        "causal_schema_sha256",
        "action_catalog_sha256",
        "configuration_sha256",
        "implementation_sha256",
    ):
        bad_hash = dict(payload)
        bad_hash[field] = "xyz"
        with pytest.raises(ControllerArtifactValidationError):
            load_controller_artifact(bad_hash)

    bad_authority = dict(payload)
    bad_authority["authority"] = "actuate"
    with pytest.raises(ControllerArtifactValidationError):
        load_controller_artifact(bad_authority)

    bad_hardware = dict(payload)
    bad_hardware["hardware_actuation_enabled"] = True
    with pytest.raises(ControllerArtifactValidationError):
        load_controller_artifact(bad_hardware)


def test_freeze_no_overwrite_and_atomic_write(tmp_path: Path) -> None:
    output = tmp_path / "controller.json"
    freeze_controller_artifact(
        controller_id="qrtc",
        implementation_commit=_valid_commit(),
        output_path=output,
    )
    with pytest.raises(FileExistsError):
        freeze_controller_artifact(
            controller_id="qrtc",
            implementation_commit=_valid_commit(),
            output_path=output,
            overwrite=False,
        )

    temp_files = [item for item in output.parent.iterdir() if ".tmp." in item.name]
    assert not temp_files

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["controller_id"] == "qrtc"
