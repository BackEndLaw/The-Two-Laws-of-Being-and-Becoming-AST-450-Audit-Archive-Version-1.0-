from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from qrtc_benchmark import controllers
from qrtc_benchmark.phase5 import (
    INTERVENTION_COSTS_BASE,
    DependencyType,
    Phase5Family,
    Phase5Intervention,
    Phase5RelationType,
)

ARTIFACT_SCHEMA = "rescueos-controller-v1"
DEFAULT_PROTOCOL_ID = "phase5b-selection-vNext"

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_FIELDS: tuple[str, ...] = (
    "artifact_schema",
    "controller_id",
    "controller_version",
    "implementation_commit",
    "protocol_id",
    "causal_schema_sha256",
    "action_catalog_sha256",
    "configuration_sha256",
    "implementation_sha256",
    "authority",
    "hardware_actuation_enabled",
)


class ControllerArtifactValidationError(ValueError):
    """Raised when a frozen controller artifact fails validation."""


@dataclass(frozen=True)
class ControllerArtifact:
    artifact_schema: str
    controller_id: str
    controller_version: str
    implementation_commit: str
    protocol_id: str
    causal_schema_sha256: str
    action_catalog_sha256: str
    configuration_sha256: str
    implementation_sha256: str
    authority: str
    hardware_actuation_enabled: bool

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(asdict(self))


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_hex(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def canonical_causal_schema_payload() -> dict[str, object]:
    return {
        "families": [family.value for family in Phase5Family],
        "relation_types": [relation.value for relation in Phase5RelationType],
        "dependency_types": [dependency.value for dependency in DependencyType],
        "unknown_fault_support": True,
    }


def canonical_action_catalog_payload() -> dict[str, object]:
    return {
        "actions": [action.value for action in Phase5Intervention],
        "base_costs": {
            action.value: INTERVENTION_COSTS_BASE[action]
            for action in sorted(INTERVENTION_COSTS_BASE, key=lambda item: item.value)
        },
    }


def canonical_configuration_payload(controller: controllers.ControllerDefinition) -> dict[str, object]:
    return {
        "controller_id": controller.controller_id,
        "controller_version": controller.controller_version,
        "role": controller.role.value,
        "deployable": controller.deployable,
        "authority": controller.authority,
        "hardware_actuation_enabled": False,
    }


def canonical_implementation_payload(controller: controllers.ControllerDefinition) -> dict[str, object]:
    source_path = Path(controllers.__file__).resolve()
    return {
        "controller_id": controller.controller_id,
        "controller_version": controller.controller_version,
        "implementation_module": "qrtc_benchmark.controllers",
        "implementation_source_sha256": _sha256_hex(source_path.read_bytes()),
    }


def _validate_required_field_set(payload: dict[str, object]) -> None:
    fields = set(payload)
    expected = set(_REQUIRED_FIELDS)
    missing = sorted(expected - fields)
    extra = sorted(fields - expected)
    if missing or extra:
        raise ControllerArtifactValidationError(
            f"invalid artifact fields (missing={missing}, extra={extra})"
        )


def _validate_sha(value: object, field: str, length_re: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not length_re.fullmatch(value):
        raise ControllerArtifactValidationError(f"invalid {field}")
    return value


def _atomic_write(path: Path, data: bytes, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", delete=False, dir=path.parent, prefix=f".{path.name}.tmp."
    ) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        temp_name = handle.name
    os.replace(temp_name, path)


def freeze_controller_artifact(
    *,
    controller_id: str,
    implementation_commit: str,
    protocol_id: str = DEFAULT_PROTOCOL_ID,
    output_path: Path | None = None,
    overwrite: bool = False,
    deployable_only: bool = False,
) -> ControllerArtifact:
    controller = controllers.get_controller(controller_id)
    if deployable_only and not controller.deployable:
        raise ControllerArtifactValidationError(
            f"controller {controller_id!r} is non-deployable"
        )

    _validate_sha(implementation_commit, "implementation_commit", _COMMIT_RE)

    artifact = ControllerArtifact(
        artifact_schema=ARTIFACT_SCHEMA,
        controller_id=controller.controller_id,
        controller_version=controller.controller_version,
        implementation_commit=implementation_commit,
        protocol_id=protocol_id,
        causal_schema_sha256=_sha256_hex(
            canonical_json_bytes(canonical_causal_schema_payload())
        ),
        action_catalog_sha256=_sha256_hex(
            canonical_json_bytes(canonical_action_catalog_payload())
        ),
        configuration_sha256=_sha256_hex(
            canonical_json_bytes(canonical_configuration_payload(controller))
        ),
        implementation_sha256=_sha256_hex(
            canonical_json_bytes(canonical_implementation_payload(controller))
        ),
        authority="recommend_only",
        hardware_actuation_enabled=False,
    )

    if output_path is not None:
        _atomic_write(output_path, artifact.canonical_bytes(), overwrite=overwrite)

    return artifact


def _validated_controller(payload: dict[str, object]) -> controllers.ControllerDefinition:
    controller_id = payload["controller_id"]
    if not isinstance(controller_id, str):
        raise ControllerArtifactValidationError("controller_id must be a string")
    try:
        return controllers.get_controller(controller_id)
    except controllers.UnknownControllerError as exc:
        raise ControllerArtifactValidationError("unknown controller_id") from exc


def load_controller_artifact(
    payload_or_path: dict[str, object] | Path,
    *,
    allow_oracle: bool = False,
    deployable_only: bool = True,
) -> tuple[ControllerArtifact, controllers.ControllerDefinition]:
    if isinstance(payload_or_path, Path):
        payload = json.loads(payload_or_path.read_text(encoding="utf-8"))
    else:
        payload = payload_or_path

    if not isinstance(payload, dict):
        raise ControllerArtifactValidationError("artifact payload must be an object")

    _validate_required_field_set(payload)

    if payload["artifact_schema"] != ARTIFACT_SCHEMA:
        raise ControllerArtifactValidationError("unsupported artifact_schema")

    controller = _validated_controller(payload)

    if payload["controller_version"] != controller.controller_version:
        raise ControllerArtifactValidationError("controller_version mismatch")

    _validate_sha(payload["implementation_commit"], "implementation_commit", _COMMIT_RE)
    _validate_sha(payload["causal_schema_sha256"], "causal_schema_sha256", _SHA256_RE)
    _validate_sha(payload["action_catalog_sha256"], "action_catalog_sha256", _SHA256_RE)
    _validate_sha(payload["configuration_sha256"], "configuration_sha256", _SHA256_RE)
    _validate_sha(payload["implementation_sha256"], "implementation_sha256", _SHA256_RE)

    if payload["authority"] != "recommend_only":
        raise ControllerArtifactValidationError("authority must be recommend_only")
    if payload["hardware_actuation_enabled"] is not False:
        raise ControllerArtifactValidationError(
            "hardware_actuation_enabled must be false"
        )

    if deployable_only and not controller.deployable:
        raise ControllerArtifactValidationError("non-deployable controller is not allowed")
    if controller.role is controllers.ControllerRole.ORACLE and not allow_oracle:
        raise ControllerArtifactValidationError("oracle loading requires explicit allow")

    expected_hashes = {
        "causal_schema_sha256": _sha256_hex(
            canonical_json_bytes(canonical_causal_schema_payload())
        ),
        "action_catalog_sha256": _sha256_hex(
            canonical_json_bytes(canonical_action_catalog_payload())
        ),
        "configuration_sha256": _sha256_hex(
            canonical_json_bytes(canonical_configuration_payload(controller))
        ),
        "implementation_sha256": _sha256_hex(
            canonical_json_bytes(canonical_implementation_payload(controller))
        ),
    }
    for field, expected in expected_hashes.items():
        if payload[field] != expected:
            raise ControllerArtifactValidationError(f"{field} mismatch")

    artifact = ControllerArtifact(
        artifact_schema=str(payload["artifact_schema"]),
        controller_id=str(payload["controller_id"]),
        controller_version=str(payload["controller_version"]),
        implementation_commit=str(payload["implementation_commit"]),
        protocol_id=str(payload["protocol_id"]),
        causal_schema_sha256=str(payload["causal_schema_sha256"]),
        action_catalog_sha256=str(payload["action_catalog_sha256"]),
        configuration_sha256=str(payload["configuration_sha256"]),
        implementation_sha256=str(payload["implementation_sha256"]),
        authority=str(payload["authority"]),
        hardware_actuation_enabled=bool(payload["hardware_actuation_enabled"]),
    )
    return artifact, controller
