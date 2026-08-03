from __future__ import annotations

import json
import os
import re
import tempfile
import tomllib
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from qrtc_benchmark import controllers
from qrtc_benchmark.eligibility import THRESHOLD_SHA256
from qrtc_benchmark.eligibility import _THRESHOLD_PAYLOAD as ELIGIBILITY_THRESHOLD_PAYLOAD
from qrtc_benchmark.phase5 import (
    INTERVENTION_COSTS_BASE,
    DependencyType,
    Phase5Config,
    Phase5Family,
    Phase5Intervention,
    Phase5OODCase,
    Phase5RelationType,
)

ARTIFACT_SCHEMA = "rescueos-controller-v1"
SELECTED_BUNDLE_SCHEMA = "rescueos-selected-controller-bundle-v1"
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


@dataclass(frozen=True)
class SelectedControllerBundle:
    artifact_schema: str
    controller_manifest: dict[str, object]
    controller_manifest_sha256: str
    source_commit: str
    source_base_commit: str
    causal_graph: dict[str, object]
    causal_graph_sha256: str
    action_allowlist: dict[str, object]
    action_allowlist_sha256: str
    controller_parameters: dict[str, object]
    controller_parameters_sha256: str
    decision_thresholds: dict[str, object]
    decision_thresholds_sha256: str
    observation_schema: dict[str, object]
    observation_schema_sha256: str
    action_schema: dict[str, object]
    action_schema_sha256: str
    dependency_lock: dict[str, object]
    dependency_lock_sha256: str
    selection_references: dict[str, object]
    selection_references_sha256: str
    reproducibility_probe: dict[str, object]
    reproducibility_probe_sha256: str
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


def canonical_configuration_payload(
    controller: controllers.ControllerDefinition,
) -> dict[str, object]:
    return {
        "controller_id": controller.controller_id,
        "controller_version": controller.controller_version,
        "role": controller.role.value,
        "deployable": controller.deployable,
        "authority": controller.authority,
        "hardware_actuation_enabled": False,
    }


def canonical_implementation_payload(
    controller: controllers.ControllerDefinition,
) -> dict[str, object]:
    source_path = Path(controllers.__file__).resolve()
    return {
        "controller_id": controller.controller_id,
        "controller_version": controller.controller_version,
        "implementation_module": "qrtc_benchmark.controllers",
        "implementation_source_sha256": _sha256_hex(source_path.read_bytes()),
    }


def canonical_controller_parameters_payload(
    controller: controllers.ControllerDefinition,
) -> dict[str, object]:
    policy_kind = "rule_based_static_registry"
    learned_tables: None = None
    if controller.controller_id == "qrtc":
        rules: tuple[str, ...] = (
            "unknown_fault -> [r0]",
            "V3 chain -> ordered required actions up to 3",
            "V3 fork -> root action plus cheapest downstream action",
            "V3 partial_sufficiency -> root action plus cheapest downstream action",
            "strict_masking -> ordered required actions up to 3",
            "synergistic -> all ordered required actions",
            "fallback -> single cheapest required action",
        )
    elif controller.controller_id == "qrtc_no_abstention":
        rules = (
            "unknown_fault -> cheapest non-r0 action",
            "otherwise -> first required action or r0",
        )
    elif controller.controller_id == "qrtc_untyped":
        rules = (
            "unknown_fault -> [r0]",
            "otherwise -> up to 2 unique required actions sorted by (cost, action_id)",
        )
    elif controller.controller_id == "greedy_gain":
        rules = (
            "unknown_fault -> [rB]",
            "otherwise -> first required action or r0",
        )
    else:
        rules = ("controller-specific static selection rules",)
    return {
        "controller_id": controller.controller_id,
        "controller_version": controller.controller_version,
        "policy_kind": policy_kind,
        "learned_tables": learned_tables,
        "rules": list(rules),
    }


def canonical_decision_thresholds_payload() -> dict[str, object]:
    config = Phase5Config()
    return {
        "utility_formula": {
            "lambda_cost": config.lambda_cost,
            "beta_harm": config.beta_harm,
            "gamma_unsafe": config.gamma_unsafe,
            "max_actions": config.max_actions,
            "bootstrap_reps": config.bootstrap_reps,
            "bootstrap_seed": config.bootstrap_seed,
            "reliability_levels": list(config.reliability_levels),
            "cost_regimes": list(config.cost_regimes),
        },
        "eligibility_thresholds": dict(ELIGIBILITY_THRESHOLD_PAYLOAD),
        "eligibility_thresholds_sha256": THRESHOLD_SHA256,
        "selection_superiority_rule": {
            "paired_bootstrap_ci_low_strictly_gt": 0.0,
            "comparison_baseline": "greedy_gain",
        },
    }


def canonical_observation_schema_payload() -> dict[str, object]:
    return {
        "schema_version": "phase5-ood-case-v1",
        "fields": [
            {"name": "family", "type": "enum", "values": [item.value for item in Phase5Family]},
            {"name": "mechanism_id", "type": "str"},
            {"name": "composition_id", "type": "str"},
            {
                "name": "relation_type",
                "type": "enum",
                "values": [item.value for item in Phase5RelationType],
            },
            {"name": "criterion", "type": "str"},
            {"name": "severity", "type": "float"},
            {"name": "noise", "type": "float"},
            {
                "name": "dependency_type",
                "type": "enum",
                "values": [item.value for item in DependencyType],
            },
            {"name": "unknown_fault", "type": "bool"},
            {"name": "evidence_initially_insufficient", "type": "bool"},
            {
                "name": "required_actions",
                "type": "list[enum]",
                "values": [item.value for item in Phase5Intervention],
            },
        ],
    }


def canonical_action_schema_payload() -> dict[str, object]:
    return {
        "schema_version": "phase5-intervention-sequence-v1",
        "max_actions": Phase5Config().max_actions,
        "action_ids": [action.value for action in Phase5Intervention],
    }


def _project_metadata(project_root: Path) -> dict[str, object]:
    pyproject_path = project_root / "pyproject.toml"
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    build_system = payload.get("build-system", {})
    return {
        "path": "pyproject.toml",
        "kind": "pyproject-dependency-declaration",
        "file_sha256": _sha256_hex(pyproject_path.read_bytes()),
        "dedicated_lock_file_present": False,
        "project_name": project.get("name"),
        "project_version": project.get("version"),
        "requires_python": project.get("requires-python"),
        "build_system_requires": list(build_system.get("requires", [])),
        "dev_dependencies": list(project.get("optional-dependencies", {}).get("dev", [])),
    }


def _reference_payload(path: Path, *, root: Path, extra: dict[str, object]) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_hex(raw),
        **extra,
    }


def _probe_case_payload() -> dict[str, object]:
    return {
        "family": Phase5Family.V3_THREE_FAULT.value,
        "mechanism_id": "freeze-probe-mechanism",
        "composition_id": "freeze-probe-composition",
        "relation_type": Phase5RelationType.INDEPENDENT.value,
        "criterion": "PI1",
        "severity": 0.5,
        "noise": 0.1,
        "dependency_type": DependencyType.CHAIN.value,
        "unknown_fault": False,
        "evidence_initially_insufficient": False,
        "required_actions": [
            Phase5Intervention.rG.value,
            Phase5Intervention.rW.value,
            Phase5Intervention.rJ.value,
        ],
    }


def _probe_case(payload: dict[str, object]) -> Phase5OODCase:
    return Phase5OODCase(
        family=Phase5Family(str(payload["family"])),
        mechanism_id=str(payload["mechanism_id"]),
        composition_id=str(payload["composition_id"]),
        relation_type=Phase5RelationType(str(payload["relation_type"])),
        criterion=str(payload["criterion"]),
        severity=float(payload["severity"]),
        noise=float(payload["noise"]),
        dependency_type=DependencyType(str(payload["dependency_type"])),
        unknown_fault=bool(payload["unknown_fault"]),
        evidence_initially_insufficient=bool(payload["evidence_initially_insufficient"]),
        required_actions=tuple(
            Phase5Intervention(str(item)) for item in payload["required_actions"]  # type: ignore[index]
        ),
    )


def canonical_reproducibility_probe_payload(
    controller: controllers.ControllerDefinition,
) -> dict[str, object]:
    case_payload = _probe_case_payload()
    costs = {
        action.value: INTERVENTION_COSTS_BASE[action]
        for action in sorted(INTERVENTION_COSTS_BASE, key=lambda item: item.value)
    }
    reliability = 1.0
    seed = 123
    case = _probe_case(case_payload)
    sequence = controller.select_actions(
        case,
        reliability,
        {Phase5Intervention(key): float(value) for key, value in costs.items()},
        seed,
    )
    decision_payload = {
        "controller_id": controller.controller_id,
        "controller_version": controller.controller_version,
        "case": case_payload,
        "reliability": reliability,
        "seed": seed,
        "costs": costs,
        "action_sequence": [action.value for action in sequence],
    }
    return {
        "observation_schema_version": "phase5-ood-case-v1",
        "action_schema_version": "phase5-intervention-sequence-v1",
        "state_loading_mode": "registry_lookup_only_no_retraining",
        "case": case_payload,
        "reliability": reliability,
        "seed": seed,
        "costs": costs,
        "expected_action_sequence": [action.value for action in sequence],
        "decision_sha256": _sha256_hex(canonical_json_bytes(decision_payload)),
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


def _validated_controller(
    payload: dict[str, object],
) -> controllers.ControllerDefinition:
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
        raise ControllerArtifactValidationError(
            "non-deployable controller is not allowed"
        )
    if controller.role is controllers.ControllerRole.ORACLE and not allow_oracle:
        raise ControllerArtifactValidationError(
            "oracle loading requires explicit allow"
        )

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


def freeze_selected_controller_bundle(
    *,
    controller_id: str,
    implementation_commit: str,
    source_commit: str,
    source_base_commit: str,
    protocol_id: str,
    repository_root: Path,
    protocol_manifest_path: Path,
    selection_result_path: Path,
    selection_validation_report_path: Path,
    final_validation_authorization_path: Path,
    final_validation_result_path: Path,
    final_validation_report_path: Path,
    closure_index_path: Path,
    output_path: Path | None = None,
    overwrite: bool = False,
) -> SelectedControllerBundle:
    controller_manifest, controller = load_controller_artifact(protocol_manifest_path)
    _validate_sha(implementation_commit, "implementation_commit", _COMMIT_RE)
    _validate_sha(source_commit, "source_commit", _COMMIT_RE)
    _validate_sha(source_base_commit, "source_base_commit", _COMMIT_RE)
    if controller_manifest.controller_id != controller_id:
        raise ControllerArtifactValidationError("controller manifest controller_id mismatch")
    if controller_manifest.implementation_commit != implementation_commit:
        raise ControllerArtifactValidationError(
            "controller manifest implementation_commit mismatch"
        )
    if controller_manifest.protocol_id != protocol_id:
        raise ControllerArtifactValidationError("controller manifest protocol_id mismatch")

    selection_result = json.loads(selection_result_path.read_text(encoding="utf-8"))
    final_validation_result = json.loads(
        final_validation_result_path.read_text(encoding="utf-8")
    )
    authorization = json.loads(
        final_validation_authorization_path.read_text(encoding="utf-8")
    )
    closure_index = json.loads(closure_index_path.read_text(encoding="utf-8"))

    if selection_result.get("selected_id") != controller_id:
        raise ControllerArtifactValidationError("selection result selected_id mismatch")
    if final_validation_result.get("selected_id") != controller_id:
        raise ControllerArtifactValidationError(
            "final validation result selected_id mismatch"
        )
    if authorization.get("selected_controller_id") != controller_id:
        raise ControllerArtifactValidationError("authorization selected_controller_id mismatch")
    if closure_index.get("validated_controller_id") != controller_id:
        raise ControllerArtifactValidationError("closure index validated_controller_id mismatch")

    controller_manifest_payload = json.loads(
        protocol_manifest_path.read_text(encoding="utf-8")
    )
    causal_graph = canonical_causal_schema_payload()
    action_allowlist = canonical_action_catalog_payload()
    controller_parameters = canonical_controller_parameters_payload(controller)
    decision_thresholds = canonical_decision_thresholds_payload()
    observation_schema = canonical_observation_schema_payload()
    action_schema = canonical_action_schema_payload()
    dependency_lock = _project_metadata(repository_root)
    selection_references = {
        "protocol_preregistration": _reference_payload(
            repository_root / "artifacts" / "protocols" / protocol_id / "preregistration.json",
            root=repository_root,
            extra={"protocol_id": protocol_id},
        ),
        "protocol_controller_manifest": _reference_payload(
            protocol_manifest_path,
            root=repository_root,
            extra={
                "controller_id": controller_id,
                "controller_version": controller.controller_version,
            },
        ),
        "selection_result": _reference_payload(
            selection_result_path,
            root=repository_root,
            extra={
                "outcome": selection_result.get("outcome"),
                "selected_id": selection_result.get("selected_id"),
            },
        ),
        "selection_validation_report": _reference_payload(
            selection_validation_report_path,
            root=repository_root,
            extra={},
        ),
        "final_validation_authorization": _reference_payload(
            final_validation_authorization_path,
            root=repository_root,
            extra={
                "selected_controller_id": authorization.get("selected_controller_id"),
                "authority": authorization.get("authority"),
            },
        ),
        "final_validation_result": _reference_payload(
            final_validation_result_path,
            root=repository_root,
            extra={
                "outcome": final_validation_result.get("outcome"),
                "selected_id": final_validation_result.get("selected_id"),
                "source_commit": final_validation_result.get("source_commit"),
                "source_base_commit": final_validation_result.get("source_base_commit"),
                "implementation_commit": final_validation_result.get("implementation_commit"),
            },
        ),
        "final_validation_report": _reference_payload(
            final_validation_report_path,
            root=repository_root,
            extra={},
        ),
        "closure_index": _reference_payload(
            closure_index_path,
            root=repository_root,
            extra={
                "final_outcome": closure_index.get("final_outcome"),
                "validated_controller_id": closure_index.get("validated_controller_id"),
            },
        ),
    }
    reproducibility_probe = canonical_reproducibility_probe_payload(controller)

    bundle = SelectedControllerBundle(
        artifact_schema=SELECTED_BUNDLE_SCHEMA,
        controller_manifest=controller_manifest_payload,
        controller_manifest_sha256=_sha256_hex(
            canonical_json_bytes(controller_manifest_payload)
        ),
        source_commit=source_commit,
        source_base_commit=source_base_commit,
        causal_graph=causal_graph,
        causal_graph_sha256=_sha256_hex(canonical_json_bytes(causal_graph)),
        action_allowlist=action_allowlist,
        action_allowlist_sha256=_sha256_hex(canonical_json_bytes(action_allowlist)),
        controller_parameters=controller_parameters,
        controller_parameters_sha256=_sha256_hex(
            canonical_json_bytes(controller_parameters)
        ),
        decision_thresholds=decision_thresholds,
        decision_thresholds_sha256=_sha256_hex(
            canonical_json_bytes(decision_thresholds)
        ),
        observation_schema=observation_schema,
        observation_schema_sha256=_sha256_hex(
            canonical_json_bytes(observation_schema)
        ),
        action_schema=action_schema,
        action_schema_sha256=_sha256_hex(canonical_json_bytes(action_schema)),
        dependency_lock=dependency_lock,
        dependency_lock_sha256=_sha256_hex(canonical_json_bytes(dependency_lock)),
        selection_references=selection_references,
        selection_references_sha256=_sha256_hex(
            canonical_json_bytes(selection_references)
        ),
        reproducibility_probe=reproducibility_probe,
        reproducibility_probe_sha256=_sha256_hex(
            canonical_json_bytes(reproducibility_probe)
        ),
        authority="recommend_only",
        hardware_actuation_enabled=False,
    )
    if output_path is not None:
        _atomic_write(output_path, bundle.canonical_bytes(), overwrite=overwrite)
    return bundle


def _validate_bundle_hash(payload: dict[str, object], data_field: str, hash_field: str) -> None:
    expected = _sha256_hex(canonical_json_bytes(payload[data_field]))
    if payload[hash_field] != expected:
        raise ControllerArtifactValidationError(f"{hash_field} mismatch")


def _find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise ControllerArtifactValidationError("could not infer project root from artifact path")


def _verify_reference_hashes(selection_references: dict[str, object], project_root: Path) -> None:
    for name, value in selection_references.items():
        if not isinstance(value, dict):
            raise ControllerArtifactValidationError(f"selection reference {name!r} must be an object")
        rel = value.get("path")
        digest = value.get("sha256")
        if not isinstance(rel, str) or not isinstance(digest, str):
            raise ControllerArtifactValidationError(
                f"selection reference {name!r} missing path/sha256"
            )
        path = project_root / rel
        if not path.exists():
            raise ControllerArtifactValidationError(
                f"selection reference missing file: {rel}"
            )
        actual = _sha256_hex(path.read_bytes())
        if actual != digest:
            raise ControllerArtifactValidationError(
                f"selection reference hash mismatch: {rel}"
            )


def load_selected_controller_bundle(
    payload_or_path: dict[str, object] | Path,
) -> tuple[SelectedControllerBundle, controllers.ControllerDefinition]:
    bundle_path: Path | None = None
    if isinstance(payload_or_path, Path):
        bundle_path = payload_or_path
        payload = json.loads(payload_or_path.read_text(encoding="utf-8"))
    else:
        payload = payload_or_path

    if not isinstance(payload, dict):
        raise ControllerArtifactValidationError("selected controller bundle must be an object")
    if payload.get("artifact_schema") != SELECTED_BUNDLE_SCHEMA:
        raise ControllerArtifactValidationError("unsupported selected controller bundle schema")
    if payload.get("authority") != "recommend_only":
        raise ControllerArtifactValidationError("authority must be recommend_only")
    if payload.get("hardware_actuation_enabled") is not False:
        raise ControllerArtifactValidationError("hardware_actuation_enabled must be false")
    _validate_sha(payload.get("source_commit"), "source_commit", _COMMIT_RE)
    _validate_sha(payload.get("source_base_commit"), "source_base_commit", _COMMIT_RE)
    _validate_sha(
        payload.get("controller_manifest_sha256"),
        "controller_manifest_sha256",
        _SHA256_RE,
    )
    for field in (
        "causal_graph_sha256",
        "action_allowlist_sha256",
        "controller_parameters_sha256",
        "decision_thresholds_sha256",
        "observation_schema_sha256",
        "action_schema_sha256",
        "dependency_lock_sha256",
        "selection_references_sha256",
        "reproducibility_probe_sha256",
    ):
        _validate_sha(payload.get(field), field, _SHA256_RE)

    _validate_bundle_hash(payload, "controller_manifest", "controller_manifest_sha256")
    artifact, controller = load_controller_artifact(payload["controller_manifest"])
    if artifact.authority != "recommend_only":
        raise ControllerArtifactValidationError("embedded controller manifest authority mismatch")
    if artifact.hardware_actuation_enabled is not False:
        raise ControllerArtifactValidationError(
            "embedded controller manifest hardware flag mismatch"
        )

    for data_field, hash_field in (
        ("causal_graph", "causal_graph_sha256"),
        ("action_allowlist", "action_allowlist_sha256"),
        ("controller_parameters", "controller_parameters_sha256"),
        ("decision_thresholds", "decision_thresholds_sha256"),
        ("observation_schema", "observation_schema_sha256"),
        ("action_schema", "action_schema_sha256"),
        ("dependency_lock", "dependency_lock_sha256"),
        ("selection_references", "selection_references_sha256"),
        ("reproducibility_probe", "reproducibility_probe_sha256"),
    ):
        _validate_bundle_hash(payload, data_field, hash_field)

    if payload["causal_graph"] != canonical_causal_schema_payload():
        raise ControllerArtifactValidationError("causal_graph mismatch")
    if payload["action_allowlist"] != canonical_action_catalog_payload():
        raise ControllerArtifactValidationError("action_allowlist mismatch")
    if payload["controller_parameters"] != canonical_controller_parameters_payload(controller):
        raise ControllerArtifactValidationError("controller_parameters mismatch")
    if payload["decision_thresholds"] != canonical_decision_thresholds_payload():
        raise ControllerArtifactValidationError("decision_thresholds mismatch")
    if payload["observation_schema"] != canonical_observation_schema_payload():
        raise ControllerArtifactValidationError("observation_schema mismatch")
    if payload["action_schema"] != canonical_action_schema_payload():
        raise ControllerArtifactValidationError("action_schema mismatch")

    if bundle_path is not None:
        project_root = _find_project_root(bundle_path.resolve().parent)
        if payload["dependency_lock"] != _project_metadata(project_root):
            raise ControllerArtifactValidationError("dependency_lock mismatch")
        _verify_reference_hashes(payload["selection_references"], project_root)

    probe = payload["reproducibility_probe"]
    if probe != canonical_reproducibility_probe_payload(controller):
        raise ControllerArtifactValidationError("reproducibility_probe mismatch")

    bundle = SelectedControllerBundle(
        artifact_schema=str(payload["artifact_schema"]),
        controller_manifest=dict(payload["controller_manifest"]),
        controller_manifest_sha256=str(payload["controller_manifest_sha256"]),
        source_commit=str(payload["source_commit"]),
        source_base_commit=str(payload["source_base_commit"]),
        causal_graph=dict(payload["causal_graph"]),
        causal_graph_sha256=str(payload["causal_graph_sha256"]),
        action_allowlist=dict(payload["action_allowlist"]),
        action_allowlist_sha256=str(payload["action_allowlist_sha256"]),
        controller_parameters=dict(payload["controller_parameters"]),
        controller_parameters_sha256=str(payload["controller_parameters_sha256"]),
        decision_thresholds=dict(payload["decision_thresholds"]),
        decision_thresholds_sha256=str(payload["decision_thresholds_sha256"]),
        observation_schema=dict(payload["observation_schema"]),
        observation_schema_sha256=str(payload["observation_schema_sha256"]),
        action_schema=dict(payload["action_schema"]),
        action_schema_sha256=str(payload["action_schema_sha256"]),
        dependency_lock=dict(payload["dependency_lock"]),
        dependency_lock_sha256=str(payload["dependency_lock_sha256"]),
        selection_references=dict(payload["selection_references"]),
        selection_references_sha256=str(payload["selection_references_sha256"]),
        reproducibility_probe=dict(payload["reproducibility_probe"]),
        reproducibility_probe_sha256=str(payload["reproducibility_probe_sha256"]),
        authority=str(payload["authority"]),
        hardware_actuation_enabled=bool(payload["hardware_actuation_enabled"]),
    )
    return bundle, controller


def selected_controller_decision_checksum(
    bundle: SelectedControllerBundle,
    controller: controllers.ControllerDefinition,
) -> str:
    probe = bundle.reproducibility_probe
    case = _probe_case(dict(probe["case"]))  # type: ignore[arg-type]
    reliability = float(probe["reliability"])
    seed = int(probe["seed"])
    costs = {
        Phase5Intervention(str(key)): float(value)
        for key, value in dict(probe["costs"]).items()  # type: ignore[arg-type]
    }
    sequence = controller.select_actions(case, reliability, costs, seed)
    decision_payload = {
        "controller_id": controller.controller_id,
        "controller_version": controller.controller_version,
        "case": probe["case"],
        "reliability": reliability,
        "seed": seed,
        "costs": probe["costs"],
        "action_sequence": [action.value for action in sequence],
    }
    return _sha256_hex(canonical_json_bytes(decision_payload))
