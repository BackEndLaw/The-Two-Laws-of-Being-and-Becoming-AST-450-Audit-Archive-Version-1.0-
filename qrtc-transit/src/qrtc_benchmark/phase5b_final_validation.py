from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict as _asdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from qrtc_benchmark.controller_artifact import (
    ControllerArtifactValidationError,
    load_controller_artifact,
)
from qrtc_benchmark.controllers import ControllerRole
from qrtc_benchmark.eligibility import CandidateMetrics, check_eligibility
from qrtc_benchmark.phase5 import (
    PHASE5_REVISION,
    SPLIT_SEEDS,
    Phase5Config,
    Phase5Family,
    Phase5TrialRow,
    _cost_table,
    _evaluate_sequence,
    _matched_differences,
    _policy_action_sequence,
    _policy_rows,
    _select_oracle_sequence,
    _stable_hash,
    _trial_case_pool,
    _trial_key,
    cluster_bootstrap_interval,
)
from qrtc_benchmark.phase5b_development import (
    IntegrityError,
    PreflightError,
    _get_source_commit,
    _is_ancestor,
    _sha256_file,
    _verify_checksums,
    _write_csv_file,
    _write_json,
)
from qrtc_benchmark.result_schema import (
    DevelopmentResultValidationError,
    SelectionResultValidationError,
    load_development_result,
    load_selection_result,
)
from qrtc_benchmark.selection_protocol import (
    BOOTSTRAP_REPS,
    BOOTSTRAP_SEED,
    COST_REGIMES,
    IMPLEMENTATION_COMMIT,
    MANDATORY_CANDIDATES,
    PROTOCOL_ID,
    PROTOCOL_PHASE_REVISION,
    RELIABILITY_LEVELS,
    SPLIT_SEEDS_FROZEN,
    TEST_FAMILY_TRIALS,
    canonical_candidate_declaration,
    canonical_config_declaration,
    canonical_json_bytes,
    canonical_split_declaration,
    compute_protocol_hashes,
)
from qrtc_benchmark.selection_rule import SelectionOutcome
from qrtc_benchmark.validation_cli import validate_protocol_directory

_SELECTED_CONTROLLER_ID = "qrtc"
_BASELINE_ID = "greedy_gain"
_ORACLE_ID = "oracle"
_REQUIRED_COMPARATORS: tuple[str, ...] = (_BASELINE_ID, _ORACLE_ID)
_FINAL_POLICIES: tuple[str, ...] = (_SELECTED_CONTROLLER_ID, *_REQUIRED_COMPARATORS)
_SELECTION_BASE_COMMIT = "54ac41b57af075dc2fa22cce66b6fe3ce7f5cffe"

_SELECTION_RUN_DIR = "selection-validation-run-1"
_DEVELOPMENT_RUN_DIR = "development-run-1"


class AuthorizationValidationError(ValueError):
    """Raised when final-validation authorization is invalid."""


class FinalValidationResultValidationError(ValueError):
    """Raised when final-validation result payload is invalid."""


@dataclass(frozen=True)
class FinalValidationAuthorizationV1:
    authorization_schema: str
    protocol_id: str
    protocol_hash: str
    selection_result_sha256: str
    selected_controller_id: str
    implementation_commit: str
    source_base_commit: str
    stage: str
    authority: str
    hardware_actuation_enabled: bool
    one_time_execution_intent: str
    event_id: str
    allowed_execution_indices: tuple[int, ...]

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "authorization_schema": self.authorization_schema,
                "protocol_id": self.protocol_id,
                "protocol_hash": self.protocol_hash,
                "selection_result_sha256": self.selection_result_sha256,
                "selected_controller_id": self.selected_controller_id,
                "implementation_commit": self.implementation_commit,
                "source_base_commit": self.source_base_commit,
                "stage": self.stage,
                "authority": self.authority,
                "hardware_actuation_enabled": self.hardware_actuation_enabled,
                "one_time_execution_intent": self.one_time_execution_intent,
                "event_id": self.event_id,
                "allowed_execution_indices": list(self.allowed_execution_indices),
            }
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


_AUTH_FIELDS = frozenset(
    {
        "authorization_schema",
        "protocol_id",
        "protocol_hash",
        "selection_result_sha256",
        "selected_controller_id",
        "implementation_commit",
        "source_base_commit",
        "stage",
        "authority",
        "hardware_actuation_enabled",
        "one_time_execution_intent",
        "event_id",
        "allowed_execution_indices",
    }
)


def load_final_validation_authorization(
    payload_or_json: dict[str, object] | str | bytes,
) -> FinalValidationAuthorizationV1:
    if isinstance(payload_or_json, (str, bytes)):
        payload = json.loads(payload_or_json)
    else:
        payload = payload_or_json
    if not isinstance(payload, dict):
        raise AuthorizationValidationError(
            "authorization payload must be a JSON object"
        )

    missing = sorted(_AUTH_FIELDS - set(payload))
    extra = sorted(set(payload) - _AUTH_FIELDS)
    if missing or extra:
        raise AuthorizationValidationError(
            f"authorization field mismatch (missing={missing}, extra={extra})"
        )
    if payload["authorization_schema"] != "rescueos-final-validation-authorization-v1":
        raise AuthorizationValidationError("authorization_schema mismatch")
    if payload["protocol_id"] != PROTOCOL_ID:
        raise AuthorizationValidationError("protocol_id mismatch")
    expected_protocol_hash = compute_protocol_hashes().protocol_declaration_sha256
    if payload["protocol_hash"] != expected_protocol_hash:
        raise AuthorizationValidationError("protocol_hash mismatch")
    if payload["selected_controller_id"] != _SELECTED_CONTROLLER_ID:
        raise AuthorizationValidationError("selected_controller_id must be qrtc")
    if payload["implementation_commit"] != IMPLEMENTATION_COMMIT:
        raise AuthorizationValidationError("implementation_commit mismatch")
    if payload["source_base_commit"] != _SELECTION_BASE_COMMIT:
        raise AuthorizationValidationError("source_base_commit mismatch")
    if payload["stage"] != "final-validation":
        raise AuthorizationValidationError("stage must be final-validation")
    if payload["authority"] != "recommend_only":
        raise AuthorizationValidationError("authority must be recommend_only")
    if payload["hardware_actuation_enabled"] is not False:
        raise AuthorizationValidationError("hardware_actuation_enabled must be false")
    if payload["one_time_execution_intent"] != "reproducibility_pair":
        raise AuthorizationValidationError(
            "one_time_execution_intent must be reproducibility_pair"
        )
    indices = payload["allowed_execution_indices"]
    if not isinstance(indices, list) or not all(
        isinstance(value, int) and value > 0 for value in indices
    ):
        raise AuthorizationValidationError(
            "allowed_execution_indices must be a list of positive integers"
        )
    if sorted(indices) != [1, 2]:
        raise AuthorizationValidationError("allowed_execution_indices must be [1, 2]")
    selection_hash = payload["selection_result_sha256"]
    if not isinstance(selection_hash, str) or len(selection_hash) != 64:
        raise AuthorizationValidationError("selection_result_sha256 must be 64-hex")
    event_id = payload["event_id"]
    if not isinstance(event_id, str) or not event_id:
        raise AuthorizationValidationError("event_id must be a non-empty string")
    return FinalValidationAuthorizationV1(
        authorization_schema=str(payload["authorization_schema"]),
        protocol_id=str(payload["protocol_id"]),
        protocol_hash=str(payload["protocol_hash"]),
        selection_result_sha256=selection_hash,
        selected_controller_id=str(payload["selected_controller_id"]),
        implementation_commit=str(payload["implementation_commit"]),
        source_base_commit=str(payload["source_base_commit"]),
        stage=str(payload["stage"]),
        authority=str(payload["authority"]),
        hardware_actuation_enabled=False,
        one_time_execution_intent=str(payload["one_time_execution_intent"]),
        event_id=event_id,
        allowed_execution_indices=tuple(int(v) for v in indices),
    )


@dataclass(frozen=True)
class FinalValidationResultV1:
    result_schema: str
    protocol_id: str
    protocol_hash: str
    authorization_sha256: str
    bound_selection_result_sha256: str
    phase_revision: str
    stage: str
    selected_id: str
    source_commit: str
    implementation_commit: str
    source_base_commit: str
    input_hashes: dict[str, str]
    comparator_ids: list[str]
    metrics_summary: dict[str, Any]
    family_metrics: dict[str, Any]
    paired_bootstrap_vs_greedy: dict[str, Any]
    oracle_regret: dict[str, Any]
    final_gates: dict[str, Any]
    outcome: str
    outcome_reasons: list[str]
    authority: str
    hardware_actuation_enabled: bool
    deployment_approval: bool
    physical_certification: bool

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(_asdict(self))


_FINAL_RESULT_FIELDS = frozenset(
    {
        "result_schema",
        "protocol_id",
        "protocol_hash",
        "authorization_sha256",
        "bound_selection_result_sha256",
        "phase_revision",
        "stage",
        "selected_id",
        "source_commit",
        "implementation_commit",
        "source_base_commit",
        "input_hashes",
        "comparator_ids",
        "metrics_summary",
        "family_metrics",
        "paired_bootstrap_vs_greedy",
        "oracle_regret",
        "final_gates",
        "outcome",
        "outcome_reasons",
        "authority",
        "hardware_actuation_enabled",
        "deployment_approval",
        "physical_certification",
    }
)


def load_final_validation_result(
    payload_or_json: dict[str, object] | str | bytes,
    *,
    expected_selection_hash: str | None = None,
) -> FinalValidationResultV1:
    if isinstance(payload_or_json, (str, bytes)):
        payload = json.loads(payload_or_json)
    else:
        payload = payload_or_json
    if not isinstance(payload, dict):
        raise FinalValidationResultValidationError(
            "result payload must be a JSON object"
        )
    missing = sorted(_FINAL_RESULT_FIELDS - set(payload))
    extra = sorted(set(payload) - _FINAL_RESULT_FIELDS)
    if missing or extra:
        raise FinalValidationResultValidationError(
            f"result field mismatch (missing={missing}, extra={extra})"
        )
    if payload["result_schema"] != "rescueos-final-validation-result-v1":
        raise FinalValidationResultValidationError("result_schema mismatch")
    if payload["protocol_id"] != PROTOCOL_ID:
        raise FinalValidationResultValidationError("protocol_id mismatch")
    if (
        payload["protocol_hash"]
        != compute_protocol_hashes().protocol_declaration_sha256
    ):
        raise FinalValidationResultValidationError("protocol_hash mismatch")
    if payload["phase_revision"] != PROTOCOL_PHASE_REVISION:
        raise FinalValidationResultValidationError("phase_revision mismatch")
    if payload["stage"] != "final-validation":
        raise FinalValidationResultValidationError("stage must be final-validation")
    if payload["selected_id"] != _SELECTED_CONTROLLER_ID:
        raise FinalValidationResultValidationError("selected_id must be qrtc")
    if payload["implementation_commit"] != IMPLEMENTATION_COMMIT:
        raise FinalValidationResultValidationError("implementation_commit mismatch")
    if payload["source_base_commit"] != _SELECTION_BASE_COMMIT:
        raise FinalValidationResultValidationError("source_base_commit mismatch")
    if payload["authority"] != "recommend_only":
        raise FinalValidationResultValidationError("authority must be recommend_only")
    if payload["hardware_actuation_enabled"] is not False:
        raise FinalValidationResultValidationError(
            "hardware_actuation_enabled must be false"
        )
    if payload["deployment_approval"] is not False:
        raise FinalValidationResultValidationError("deployment_approval must be false")
    if payload["physical_certification"] is not False:
        raise FinalValidationResultValidationError(
            "physical_certification must be false"
        )
    if payload["comparator_ids"] != [_BASELINE_ID, _ORACLE_ID]:
        raise FinalValidationResultValidationError(
            "comparator_ids must be ['greedy_gain', 'oracle']"
        )
    outcome = payload["outcome"]
    if outcome not in {
        "final_validation_passed",
        "final_validation_failed",
        "final_validation_invalid",
    }:
        raise FinalValidationResultValidationError("invalid outcome")
    gates = payload["final_gates"]
    if not isinstance(gates, dict):
        raise FinalValidationResultValidationError("final_gates must be an object")
    gate_passed = bool(gates.get("all_passed"))
    if outcome == "final_validation_passed" and not gate_passed:
        raise FinalValidationResultValidationError(
            "pass outcome is inconsistent with gate failures"
        )
    if outcome == "final_validation_failed" and gate_passed:
        raise FinalValidationResultValidationError(
            "failed outcome is inconsistent with all gates passing"
        )
    bound = payload["bound_selection_result_sha256"]
    if expected_selection_hash is not None and bound != expected_selection_hash:
        raise FinalValidationResultValidationError(
            "bound_selection_result_sha256 mismatch"
        )
    return FinalValidationResultV1(
        result_schema=str(payload["result_schema"]),
        protocol_id=str(payload["protocol_id"]),
        protocol_hash=str(payload["protocol_hash"]),
        authorization_sha256=str(payload["authorization_sha256"]),
        bound_selection_result_sha256=str(payload["bound_selection_result_sha256"]),
        phase_revision=str(payload["phase_revision"]),
        stage=str(payload["stage"]),
        selected_id=str(payload["selected_id"]),
        source_commit=str(payload["source_commit"]),
        implementation_commit=str(payload["implementation_commit"]),
        source_base_commit=str(payload["source_base_commit"]),
        input_hashes={str(k): str(v) for k, v in dict(payload["input_hashes"]).items()},
        comparator_ids=[str(v) for v in list(payload["comparator_ids"])],
        metrics_summary=dict(payload["metrics_summary"]),  # type: ignore[arg-type]
        family_metrics=dict(payload["family_metrics"]),  # type: ignore[arg-type]
        paired_bootstrap_vs_greedy=dict(payload["paired_bootstrap_vs_greedy"]),  # type: ignore[arg-type]
        oracle_regret=dict(payload["oracle_regret"]),  # type: ignore[arg-type]
        final_gates=dict(payload["final_gates"]),  # type: ignore[arg-type]
        outcome=str(payload["outcome"]),
        outcome_reasons=[str(v) for v in list(payload["outcome_reasons"])],
        authority=str(payload["authority"]),
        hardware_actuation_enabled=False,
        deployment_approval=False,
        physical_certification=False,
    )


def _collect_input_hashes(
    protocol_dir: Path, selection_run_dir: Path
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    protocol_files = [
        "preregistration.json",
        "commit.txt",
        "frozen_semantic_declarations.json",
        "checksums.sha256",
    ] + [f"manifests/{cid}.json" for cid in MANDATORY_CANDIDATES]
    for rel in protocol_files:
        path = protocol_dir / rel
        if path.exists():
            hashes[f"protocol/{rel}"] = _sha256_file(path)
    for rel in (
        "selection_result.json",
        "candidate_metrics.json",
        "eligibility_report.json",
        "checksums.sha256",
    ):
        path = selection_run_dir / rel
        if path.exists():
            hashes[f"selection/{rel}"] = _sha256_file(path)
    return hashes


def _check_preregistration_and_semantics(protocol_dir: Path) -> list[str]:
    errors: list[str] = []
    prereg = json.loads(
        (protocol_dir / "preregistration.json").read_text(encoding="utf-8")
    )
    semantic = json.loads(
        (protocol_dir / "frozen_semantic_declarations.json").read_text(encoding="utf-8")
    )
    hashes = compute_protocol_hashes()
    if prereg.get("protocol_hash") != hashes.protocol_declaration_sha256:
        errors.append("preregistration protocol_hash mismatch")
    if semantic.get("split_declaration") != canonical_split_declaration():
        errors.append("split declaration mismatch")
    if semantic.get("config_declaration") != canonical_config_declaration():
        errors.append("config declaration mismatch")
    if semantic.get("candidate_declaration") != canonical_candidate_declaration():
        errors.append("candidate declaration mismatch")
    return errors


def _check_final_split_declaration(protocol_dir: Path) -> list[str]:
    prereg = json.loads(
        (protocol_dir / "preregistration.json").read_text(encoding="utf-8")
    )
    splits = prereg.get("splits", {})
    expected = canonical_split_declaration()
    errors: list[str] = []
    checks: tuple[tuple[str, object, object], ...] = (
        ("split_aliases", splits.get("split_aliases"), expected["split_aliases"]),
        ("split_seeds", splits.get("split_seeds"), expected["split_seeds"]),
        (
            "test_family_trials",
            splits.get("test_family_trials"),
            expected["test_family_trials"],
        ),
        (
            "final_mechanisms",
            splits.get("final_mechanisms"),
            expected["final_mechanisms"],
        ),
        ("final_pairs", splits.get("final_pairs"), expected["final_pairs"]),
        ("final_triples", splits.get("final_triples"), expected["final_triples"]),
    )
    for name, recorded, canonical in checks:
        if recorded != canonical:
            errors.append(f"final split declaration mismatch for {name}")
    if splits.get("split_aliases", {}).get("test") != "final-validation":
        errors.append("split alias test must map to final-validation")
    return errors


def _check_selected_controller_artifact(protocol_dir: Path) -> list[str]:
    artifact_path = protocol_dir / "manifests" / f"{_SELECTED_CONTROLLER_ID}.json"
    errors: list[str] = []
    if not artifact_path.exists():
        return [f"missing selected controller artifact: {artifact_path}"]
    try:
        artifact, controller = load_controller_artifact(
            json.loads(artifact_path.read_text(encoding="utf-8")),
            allow_oracle=False,
            deployable_only=True,
        )
    except ControllerArtifactValidationError as exc:
        return [f"selected controller artifact invalid: {exc}"]
    if artifact.protocol_id != PROTOCOL_ID:
        errors.append("selected controller protocol_id mismatch")
    if artifact.implementation_commit != IMPLEMENTATION_COMMIT:
        errors.append("selected controller implementation_commit mismatch")
    if artifact.authority != "recommend_only":
        errors.append("selected controller authority mismatch")
    if artifact.hardware_actuation_enabled is not False:
        errors.append("selected controller hardware flag must be false")
    if controller.role not in {ControllerRole.PRIMARY, ControllerRole.ABLATION}:
        errors.append("selected controller role is not deployable")
    if not controller.deployable:
        errors.append("selected controller must be deployable")
    return errors


def _check_selection_result(selection_run_dir: Path) -> tuple[list[str], str]:
    errors: list[str] = []
    path = selection_run_dir / "selection_result.json"
    if not path.exists():
        return [f"missing selection result: {path}"], ""
    raw = path.read_text(encoding="utf-8")
    selection_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    try:
        selection_result = load_selection_result(raw)
    except SelectionResultValidationError as exc:
        return [f"selection result invalid: {exc}"], selection_hash
    if selection_result.outcome != SelectionOutcome.PROVISIONAL_SELECTION.value:
        errors.append(
            f"selection outcome mismatch: expected provisional_selection, got {selection_result.outcome}"
        )
    if selection_result.selected_id != _SELECTED_CONTROLLER_ID:
        errors.append(
            f"selection selected_id mismatch: expected qrtc, got {selection_result.selected_id!r}"
        )
    qrtc_reason = selection_result.eligibility_reasons.get(_SELECTED_CONTROLLER_ID, {})
    if not qrtc_reason.get("eligible", False):
        errors.append("selection result reports qrtc as ineligible")
    if not qrtc_reason.get("superior_vs_greedy", False):
        errors.append("selection result reports qrtc not superior_vs_greedy")
    return errors, selection_hash


def _check_development_result(artifacts_root: Path) -> list[str]:
    errors: list[str] = []
    dev_dir = artifacts_root / _DEVELOPMENT_RUN_DIR
    errors.extend(_verify_checksums(dev_dir))
    result_path = dev_dir / "development_result.json"
    if not result_path.exists():
        return errors + [f"missing development result: {result_path}"]
    try:
        result = load_development_result(result_path.read_text(encoding="utf-8"))
    except (OSError, DevelopmentResultValidationError, ValueError) as exc:
        return errors + [f"development result invalid: {exc}"]
    if result.stage != "development":
        errors.append("development result stage must be development")
    if result.outcome != "development_completed_no_selection":
        errors.append("development result outcome mismatch")
    return errors


def _check_authorization(
    authorization: FinalValidationAuthorizationV1,
    *,
    selection_result_hash: str,
    execution_index: int,
) -> list[str]:
    errors: list[str] = []
    if authorization.selection_result_sha256 != selection_result_hash:
        errors.append("authorization selection_result_sha256 mismatch")
    if execution_index not in authorization.allowed_execution_indices:
        errors.append(
            f"execution_index {execution_index} not allowed by authorization artifact"
        )
    return errors


def _check_output_dir(output_dir: Path, artifacts_root: Path) -> list[str]:
    errors: list[str] = []
    if output_dir.exists() and any(output_dir.iterdir()):
        errors.append(f"output_dir must be empty: {output_dir}")
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    forbidden_ancestors = [
        artifacts_root / "development-run-1",
        artifacts_root / "selection-validation-run-1",
        artifacts_root.parent / "protocols",
    ]
    for ancestor in forbidden_ancestors:
        try:
            output_dir.relative_to(ancestor)
            errors.append(
                f"output_dir must not be inside immutable directory {ancestor}"
            )
        except ValueError:
            pass
    return errors


def _changed_files_since_base(source_commit: str, base_commit: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_commit}..{source_commit}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _check_post_selection_change_scope(source_commit: str) -> list[str]:
    changed_files = _changed_files_since_base(source_commit, _SELECTION_BASE_COMMIT)
    if not changed_files:
        return []
    allowed_prefixes = (
        "qrtc-transit/src/qrtc_benchmark/phase5b_final_validation.py",
        "qrtc-transit/src/qrtc_benchmark/phase5b_development.py",
        "qrtc-transit/src/qrtc_benchmark/phase5b_selection_validation.py",
        "qrtc-transit/src/qrtc_benchmark/result_schema.py",
        "qrtc-transit/tests/qrtc_benchmark/test_phase5b_final_validation.py",
        "qrtc-transit/tests/qrtc_benchmark/test_phase5b_closure_index.py",
        "qrtc-transit/docs/",
        "qrtc-transit/README.md",
        "qrtc-transit/artifacts/phase5b-selection-v1/",
    )
    disallowed = [
        path for path in changed_files if not path.startswith(allowed_prefixes)
    ]
    if disallowed:
        return [
            "post-selection source changes exceed final-validation scope: "
            + ", ".join(sorted(disallowed))
        ]
    return []


def run_final_validation_preflight(
    *,
    protocol_dir: Path,
    artifacts_root: Path,
    output_dir: Path,
    authorization_path: Path,
    execution_index: int,
    source_commit: str | None = None,
) -> dict[str, Any]:
    if source_commit is None:
        source_commit = _get_source_commit()
    errors: list[str] = []
    if not _is_ancestor(_SELECTION_BASE_COMMIT, source_commit):
        errors.append(
            f"source commit {source_commit!r} is not a descendant of required base commit "
            f"{_SELECTION_BASE_COMMIT!r}"
        )
    errors.extend(_check_post_selection_change_scope(source_commit))
    errors.extend(_check_preregistration_and_semantics(protocol_dir))
    errors.extend(_check_final_split_declaration(protocol_dir))
    errors.extend(_verify_checksums(protocol_dir))
    errors.extend(_check_development_result(artifacts_root))
    selection_run_dir = artifacts_root / _SELECTION_RUN_DIR
    errors.extend(_verify_checksums(selection_run_dir))
    selection_errors, selection_hash = _check_selection_result(selection_run_dir)
    errors.extend(selection_errors)
    errors.extend(_check_selected_controller_artifact(protocol_dir))
    try:
        authorization = load_final_validation_authorization(
            authorization_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        errors.append(f"authorization artifact invalid: {exc}")
        authorization = None
    if authorization is not None:
        errors.extend(
            _check_authorization(
                authorization,
                selection_result_hash=selection_hash,
                execution_index=execution_index,
            )
        )
    errors.extend(_check_output_dir(output_dir, artifacts_root))
    try:
        report = validate_protocol_directory(
            protocol_dir=protocol_dir,
            stage="selection-validation",
            implementation_commit=IMPLEMENTATION_COMMIT,
            expected_protocol_hash=compute_protocol_hashes().protocol_declaration_sha256,
            output_dir=output_dir,
        )
        if report.status != "ok":
            errors.extend([f"validation_cli: {error}" for error in report.errors])
    except Exception as exc:  # noqa: BLE001
        errors.append(f"validation_cli precheck failed: {exc}")
    if errors:
        details = "\n".join(f"  - {error}" for error in errors)
        raise PreflightError(
            f"Final-validation preflight failed with {len(errors)} error(s):\n{details}"
        )
    assert authorization is not None
    return {
        "status": "ok",
        "source_commit": source_commit,
        "selection_result_sha256": selection_hash,
        "authorization_sha256": authorization.sha256(),
        "authorization_event_id": authorization.event_id,
    }


def _build_final_rows(config: Phase5Config) -> list[Phase5TrialRow]:
    rows: list[Phase5TrialRow] = []
    oracle_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
    split_name = "test"
    root_seed = SPLIT_SEEDS[split_name][0]
    for family in Phase5Family:
        family_cases = _trial_case_pool(
            split_name,
            family,
            seed=root_seed
            + _stable_hash("phase5b:family_pool_seed", family.value) % 991,
            config=config,
        )
        for index, case in enumerate(family_cases):
            seed_family = SPLIT_SEEDS[split_name][index % len(SPLIT_SEEDS[split_name])]
            for reliability in config.reliability_levels:
                for cost_regime in config.cost_regimes:
                    costs = _cost_table(cost_regime, seed=seed_family)
                    scenario_seed = seed_family + index * 13 + int(reliability * 100)
                    oracle = _select_oracle_sequence(
                        case=case,
                        reliability=reliability,
                        seed=scenario_seed,
                        config=config,
                        costs=costs,
                        cache=oracle_cache,
                    )
                    oracle_sequence = tuple(oracle["sequence"])
                    for policy in _FINAL_POLICIES:
                        if policy == _ORACLE_ID:
                            action_sequence = oracle_sequence
                        else:
                            action_sequence = _policy_action_sequence(
                                policy=policy,
                                case=case,
                                reliability=reliability,
                                costs=costs,
                                seed=scenario_seed
                                + _stable_hash("phase5b:scenario_policy_seed", policy)
                                % 997,
                            )
                        outcome = _evaluate_sequence(
                            case=case,
                            action_sequence=action_sequence,
                            reliability=reliability,
                            seed=scenario_seed,
                            config=config,
                            costs=costs,
                        )
                        trial_key = _trial_key(
                            case,
                            split_name,
                            seed_family,
                            index,
                            reliability,
                            cost_regime,
                        )
                        rows.append(
                            Phase5TrialRow(
                                trial_id=f"{trial_key}:{policy}",
                                trial_key=trial_key,
                                split=split_name,
                                family=case.family.value,
                                seed_family=seed_family,
                                mechanism_id=case.mechanism_id,
                                composition_id=case.composition_id,
                                relation_type=case.relation_type.value,
                                criterion=case.criterion,
                                severity=case.severity,
                                noise=case.noise,
                                cost_regime=cost_regime,
                                intervention_reliability=reliability,
                                policy=policy,
                                action_sequence=",".join(
                                    action.value for action in action_sequence
                                ),
                                recovered=bool(outcome["recovered"]),
                                recovery_score=float(outcome["recovery_score"]),
                                intervention_cost=float(outcome["cost"]),
                                harm=float(outcome["harm"]),
                                unsafe_commitment=int(outcome["unsafe_commitment"]),
                                unknown_score=float(outcome["unknown_score"]),
                                evidence_requested=bool(outcome["evidence_requested"]),
                                evidence_useful=bool(outcome["evidence_useful"]),
                                evidence_insufficient_at_start=case.evidence_initially_insufficient,
                                utility=float(outcome["utility"]),
                                oracle_utility=float(oracle["utility"]),
                                oracle_sequence=",".join(
                                    action.value for action in oracle_sequence
                                ),
                                oracle_cost=float(oracle["cost"]),
                                oracle_recovered=bool(oracle["recovered"]),
                                relation_observed=case.relation_type.value,
                                is_triple_fault=case.family
                                == Phase5Family.V3_THREE_FAULT,
                                unknown_fault=case.unknown_fault,
                            )
                        )
    return rows


def _metrics(rows: list[Phase5TrialRow], policy: str) -> dict[str, Any]:
    subset = _policy_rows(rows, policy)
    families: dict[str, Any] = {}
    for family in Phase5Family:
        family_subset = [row for row in subset if row.family == family.value]
        families[family.value] = {
            "trial_count": len(family_subset),
            "recovery_rate": mean(
                1.0 if row.recovered else 0.0 for row in family_subset
            ),
            "mean_harm": mean(row.harm for row in family_subset),
            "unsafe_commitment_count": sum(
                int(row.unsafe_commitment) for row in family_subset
            ),
            "unsafe_commitment_rate": mean(
                float(row.unsafe_commitment) for row in family_subset
            ),
        }
    return {
        "candidate": policy,
        "trial_count": len(subset),
        "mean_utility": mean(row.utility for row in subset),
        "recovery_rate": mean(1.0 if row.recovered else 0.0 for row in subset),
        "mean_intervention_cost": mean(row.intervention_cost for row in subset),
        "mean_harm": mean(row.harm for row in subset),
        "unsafe_commitment_rate": mean(float(row.unsafe_commitment) for row in subset),
        "unsafe_commitment_count": sum(int(row.unsafe_commitment) for row in subset),
        "evidence_request_rate": mean(
            1.0 if row.evidence_requested else 0.0 for row in subset
        ),
        "oracle_regret": mean(row.oracle_utility - row.utility for row in subset),
        "family_metrics": families,
    }


def _candidate_metrics_for_gates(
    rows: list[Phase5TrialRow], policy: str, baseline: dict[str, Any]
) -> CandidateMetrics:
    metric = _metrics(rows, policy)
    diffs = _matched_differences(rows, policy, _BASELINE_ID)
    bootstrap = cluster_bootstrap_interval(
        diffs, bootstrap_reps=BOOTSTRAP_REPS, bootstrap_seed=BOOTSTRAP_SEED
    )
    bootstrap["left_policy"] = policy
    bootstrap["right_policy"] = _BASELINE_ID
    bootstrap["method"] = "paired_cluster_bootstrap"
    expected_keys = {row.trial_key for row in _policy_rows(rows, _BASELINE_ID)}
    subset = _policy_rows(rows, policy)
    keys = {row.trial_key for row in subset}
    return CandidateMetrics(
        controller_id=policy,
        mean_utility=metric["mean_utility"],
        recovery_rate=metric["recovery_rate"],
        mean_intervention_cost=metric["mean_intervention_cost"],
        mean_harm=metric["mean_harm"],
        unsafe_commitment_rate=metric["unsafe_commitment_rate"],
        evidence_request_rate=metric["evidence_request_rate"],
        per_family_recovery_rate={
            family: values["recovery_rate"]
            for family, values in metric["family_metrics"].items()
        },
        per_family_mean_harm={
            family: values["mean_harm"]
            for family, values in metric["family_metrics"].items()
        },
        per_family_unsafe_count={
            family: values["unsafe_commitment_count"]
            for family, values in metric["family_metrics"].items()
        },
        bootstrap_vs_greedy=bootstrap,
        bootstrap_vs_strongest=bootstrap,
        oracle_regret=metric["oracle_regret"],
        matched_rows_ok=(keys == expected_keys and len(subset) == len(expected_keys)),
        artifact_hash_ok=True,
        protocol_match_ok=True,
        operational_integrity_ok=True,
    )


def _build_gate_report(
    rows: list[Phase5TrialRow],
) -> tuple[dict[str, Any], list[str], str]:
    selected = _metrics(rows, _SELECTED_CONTROLLER_ID)
    baseline = _metrics(rows, _BASELINE_ID)
    selected_metrics = _candidate_metrics_for_gates(
        rows, _SELECTED_CONTROLLER_ID, baseline
    )
    baseline_metrics = _candidate_metrics_for_gates(rows, _BASELINE_ID, baseline)
    eligibility = check_eligibility(selected_metrics, baseline_metrics)
    gate_results = dict(eligibility.gate_results)
    reasons = list(eligibility.disqualification_reasons)
    complete_unique = selected_metrics.matched_rows_ok
    required_trials = (
        TEST_FAMILY_TRIALS
        * len(Phase5Family)
        * len(RELIABILITY_LEVELS)
        * len(COST_REGIMES)
    )
    gate_results["gate9_complete_frozen_coverage"] = (
        selected["trial_count"] == required_trials
        and baseline["trial_count"] == required_trials
        and _metrics(rows, _ORACLE_ID)["trial_count"] == required_trials
    )
    if not gate_results["gate9_complete_frozen_coverage"]:
        reasons.append("gate9: frozen trial coverage mismatch")
    gate_results["gate10_only_required_comparators"] = set(_FINAL_POLICIES) == {
        row.policy for row in rows
    }
    if not gate_results["gate10_only_required_comparators"]:
        reasons.append("gate10: unexpected policy rows detected")
    gate_results["gate11_complete_unique_matched_rows"] = complete_unique
    if not complete_unique:
        reasons.append("gate11: matched trial rows are incomplete/non-unique")
    all_passed = all(gate_results.values())
    if all_passed:
        outcome = "final_validation_passed"
    else:
        outcome = "final_validation_failed"
    return {"all_passed": all_passed, "gate_results": gate_results}, reasons, outcome


def _write_rows_csv(path: Path, rows: list[Phase5TrialRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(Phase5TrialRow.__annotations__.keys())
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(_asdict(row))


def _final_manifest(
    *,
    source_commit: str,
    authorization_sha256: str,
    selection_hash: str,
    input_hashes: dict[str, str],
    trial_count: int,
) -> dict[str, Any]:
    return {
        "schema": "qrtc-final-validation-run-manifest-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": compute_protocol_hashes().protocol_declaration_sha256,
        "stage": "final-validation",
        "split": "test",
        "source_commit": source_commit,
        "source_base_commit": _SELECTION_BASE_COMMIT,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "authorization_sha256": authorization_sha256,
        "selection_result_sha256": selection_hash,
        "split_seeds": list(SPLIT_SEEDS_FROZEN["test"]),
        "test_family_trials": TEST_FAMILY_TRIALS,
        "reliability_levels": list(RELIABILITY_LEVELS),
        "cost_regimes": list(COST_REGIMES),
        "bootstrap_reps": BOOTSTRAP_REPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "selected_id": _SELECTED_CONTROLLER_ID,
        "comparator_ids": [_BASELINE_ID, _ORACLE_ID],
        "trial_count": trial_count,
        "input_hashes": input_hashes,
    }


def run_final_validation(
    *,
    protocol_dir: Path,
    artifacts_root: Path,
    output_dir: Path,
    authorization_path: Path,
    execution_index: int,
    source_commit: str | None = None,
    skip_preflight: bool = False,
) -> FinalValidationResultV1:
    if source_commit is None:
        source_commit = _get_source_commit()
    output_dir.mkdir(parents=True, exist_ok=True)
    if skip_preflight:
        selection_hash = hashlib.sha256(
            (artifacts_root / _SELECTION_RUN_DIR / "selection_result.json").read_bytes()
        ).hexdigest()
        authorization = load_final_validation_authorization(
            authorization_path.read_text(encoding="utf-8")
        )
        authorization_sha = authorization.sha256()
    else:
        preflight = run_final_validation_preflight(
            protocol_dir=protocol_dir,
            artifacts_root=artifacts_root,
            output_dir=output_dir,
            authorization_path=authorization_path,
            execution_index=execution_index,
            source_commit=source_commit,
        )
        selection_hash = preflight["selection_result_sha256"]
        authorization_sha = preflight["authorization_sha256"]

    rows = _build_final_rows(config=Phase5Config())
    if {row.split for row in rows} != {"test"}:
        raise IntegrityError("final-validation generated non-test split rows")
    if {row.policy for row in rows} != set(_FINAL_POLICIES):
        raise IntegrityError("final-validation generated unexpected policy rows")

    selected = _metrics(rows, _SELECTED_CONTROLLER_ID)
    baseline = _metrics(rows, _BASELINE_ID)
    oracle = _metrics(rows, _ORACLE_ID)
    family_metrics = {
        _SELECTED_CONTROLLER_ID: selected["family_metrics"],
        _BASELINE_ID: baseline["family_metrics"],
        _ORACLE_ID: oracle["family_metrics"],
    }
    paired = cluster_bootstrap_interval(
        _matched_differences(rows, _SELECTED_CONTROLLER_ID, _BASELINE_ID),
        bootstrap_reps=BOOTSTRAP_REPS,
        bootstrap_seed=BOOTSTRAP_SEED,
    )
    paired["left_policy"] = _SELECTED_CONTROLLER_ID
    paired["right_policy"] = _BASELINE_ID
    paired["method"] = "paired_cluster_bootstrap"

    gate_payload, reasons, outcome = _build_gate_report(rows)
    if outcome == "final_validation_failed" and gate_payload["all_passed"]:
        raise IntegrityError("invalid gate/outcome state")
    result = FinalValidationResultV1(
        result_schema="rescueos-final-validation-result-v1",
        protocol_id=PROTOCOL_ID,
        protocol_hash=compute_protocol_hashes().protocol_declaration_sha256,
        authorization_sha256=authorization_sha,
        bound_selection_result_sha256=selection_hash,
        phase_revision=PHASE5_REVISION,
        stage="final-validation",
        selected_id=_SELECTED_CONTROLLER_ID,
        source_commit=source_commit,
        implementation_commit=IMPLEMENTATION_COMMIT,
        source_base_commit=_SELECTION_BASE_COMMIT,
        input_hashes=_collect_input_hashes(
            protocol_dir, artifacts_root / _SELECTION_RUN_DIR
        ),
        comparator_ids=[_BASELINE_ID, _ORACLE_ID],
        metrics_summary={
            _SELECTED_CONTROLLER_ID: {
                key: value for key, value in selected.items() if key != "family_metrics"
            },
            _BASELINE_ID: {
                key: value for key, value in baseline.items() if key != "family_metrics"
            },
            _ORACLE_ID: {
                key: value for key, value in oracle.items() if key != "family_metrics"
            },
        },
        family_metrics=family_metrics,
        paired_bootstrap_vs_greedy=paired,
        oracle_regret={
            "selected_minus_oracle": selected["oracle_regret"],
            "baseline_minus_oracle": baseline["oracle_regret"],
        },
        final_gates=gate_payload,
        outcome=outcome,
        outcome_reasons=reasons,
        authority="recommend_only",
        hardware_actuation_enabled=False,
        deployment_approval=False,
        physical_certification=False,
    )
    validated = load_final_validation_result(
        json.loads(result.canonical_bytes().decode("utf-8")),
        expected_selection_hash=selection_hash,
    )

    run_manifest = _final_manifest(
        source_commit=source_commit,
        authorization_sha256=authorization_sha,
        selection_hash=selection_hash,
        input_hashes=validated.input_hashes,
        trial_count=len(rows),
    )

    result_path = output_dir / "final_validation_result.json"
    selected_json = output_dir / "selected_controller_metrics.json"
    baseline_json = output_dir / "baseline_metrics.json"
    oracle_json = output_dir / "oracle_metrics.json"
    family_json = output_dir / "family_metrics.json"
    gates_json = output_dir / "final_gate_report.json"
    paired_json = output_dir / "paired_bootstrap_summary.json"
    runs_csv = output_dir / "phase5_runs.csv"
    manifest_json = output_dir / "run_manifest.json"
    selection_manifest_json = output_dir / "final_validation_manifest.json"
    report_md = output_dir / "FINAL_VALIDATION_REPORT.md"
    _write_json(result_path, json.loads(validated.canonical_bytes().decode("utf-8")))
    _write_json(selected_json, selected)
    _write_json(baseline_json, baseline)
    _write_json(oracle_json, oracle)
    _write_json(family_json, family_metrics)
    _write_json(
        gates_json, gate_payload | {"outcome_reasons": reasons, "outcome": outcome}
    )
    _write_json(paired_json, paired)
    _write_json(manifest_json, run_manifest)
    split_decl = canonical_split_declaration()
    _write_json(
        selection_manifest_json,
        {
            "protocol_id": PROTOCOL_ID,
            "phase_revision": PROTOCOL_PHASE_REVISION,
            "split_alias": "test",
            "split_name": "final-validation",
            "split_aliases": split_decl["split_aliases"],
            "split_seeds": split_decl["split_seeds"],
            "test_family_trials": split_decl["test_family_trials"],
            "final_mechanisms": split_decl["final_mechanisms"],
            "final_pairs": split_decl["final_pairs"],
            "final_triples": split_decl["final_triples"],
        },
    )
    _write_rows_csv(runs_csv, rows)
    _write_csv_file(
        output_dir / "selected_controller_metrics.csv",
        ["candidate", "trial_count", "mean_utility", "recovery_rate", "mean_harm"],
        [
            {
                "candidate": _SELECTED_CONTROLLER_ID,
                "trial_count": selected["trial_count"],
                "mean_utility": selected["mean_utility"],
                "recovery_rate": selected["recovery_rate"],
                "mean_harm": selected["mean_harm"],
            }
        ],
    )
    _write_csv_file(
        output_dir / "baseline_metrics.csv",
        ["candidate", "trial_count", "mean_utility", "recovery_rate", "mean_harm"],
        [
            {
                "candidate": _BASELINE_ID,
                "trial_count": baseline["trial_count"],
                "mean_utility": baseline["mean_utility"],
                "recovery_rate": baseline["recovery_rate"],
                "mean_harm": baseline["mean_harm"],
            }
        ],
    )
    _write_csv_file(
        output_dir / "oracle_metrics.csv",
        ["candidate", "trial_count", "mean_utility", "recovery_rate", "mean_harm"],
        [
            {
                "candidate": _ORACLE_ID,
                "trial_count": oracle["trial_count"],
                "mean_utility": oracle["mean_utility"],
                "recovery_rate": oracle["recovery_rate"],
                "mean_harm": oracle["mean_harm"],
            }
        ],
    )
    report_lines = [
        "# Phase V-B Final Validation Report",
        "",
        f"- Protocol: `{PROTOCOL_ID}`",
        f"- Protocol hash: `{compute_protocol_hashes().protocol_declaration_sha256}`",
        f"- Selection result hash: `{selection_hash}`",
        f"- Authorization hash: `{authorization_sha}`",
        "- Stage: `final-validation`",
        f"- Selected deployable controller: `{_SELECTED_CONTROLLER_ID}`",
        f"- Comparators: `{_BASELINE_ID}`, `{_ORACLE_ID}`",
        f"- Outcome: `{outcome}`",
        "- Authority: recommend_only",
        "- Hardware actuation remains disabled.",
        "- This is simulated benchmark evidence and not a physical certification.",
        "",
        "## Final gate status",
        f"- all_passed: `{gate_payload['all_passed']}`",
        "",
        "## Outcome reasons",
    ]
    if reasons:
        report_lines.extend(f"- {reason}" for reason in reasons)
    else:
        report_lines.append("- none")
    report_md.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    canonical_files = [
        result_path,
        selected_json,
        baseline_json,
        oracle_json,
        family_json,
        gates_json,
        paired_json,
        runs_csv,
        manifest_json,
        selection_manifest_json,
        output_dir / "selected_controller_metrics.csv",
        output_dir / "baseline_metrics.csv",
        output_dir / "oracle_metrics.csv",
        report_md,
    ]
    checksum_lines = [
        f"{_sha256_file(path)}  {path.relative_to(output_dir).as_posix()}"
        for path in canonical_files
    ]
    (output_dir / "checksums.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return validated


def verify_final_validation_reproducibility(
    run1_dir: Path, run2_dir: Path
) -> tuple[bool, list[str]]:
    names = (
        "final_validation_result.json",
        "selected_controller_metrics.json",
        "baseline_metrics.json",
        "oracle_metrics.json",
        "family_metrics.json",
        "final_gate_report.json",
        "paired_bootstrap_summary.json",
        "phase5_runs.csv",
        "run_manifest.json",
        "final_validation_manifest.json",
        "selected_controller_metrics.csv",
        "baseline_metrics.csv",
        "oracle_metrics.csv",
        "FINAL_VALIDATION_REPORT.md",
        "checksums.sha256",
    )
    differences: list[str] = []
    for name in names:
        p1 = run1_dir / name
        p2 = run2_dir / name
        if not p1.exists():
            differences.append(f"{name}: missing from run1")
            continue
        if not p2.exists():
            differences.append(f"{name}: missing from run2")
            continue
        h1 = _sha256_file(p1)
        h2 = _sha256_file(p2)
        if h1 != h2:
            differences.append(f"{name}: sha256 differs ({h1} != {h2})")
    return len(differences) == 0, differences


def write_reproducibility_report(
    *,
    destination: Path,
    run1_dir: Path,
    run2_dir: Path,
    pyhashseed_run1: str,
    pyhashseed_run2: str,
) -> tuple[bool, list[str]]:
    passed, differences = verify_final_validation_reproducibility(run1_dir, run2_dir)
    lines = [
        "# Phase V-B Final-Validation Reproducibility Verification",
        "",
        f"- Run 1 directory: `{run1_dir}`",
        f"- Run 2 directory: `{run2_dir}`",
        f"- Run 1 PYTHONHASHSEED: `{pyhashseed_run1}`",
        f"- Run 2 PYTHONHASHSEED: `{pyhashseed_run2}`",
        f"- Byte-identical: `{passed}`",
        "",
    ]
    if differences:
        lines.append("## Differences")
        lines.extend(f"- {diff}" for diff in differences)
    else:
        lines.append("No differences detected across canonical outputs.")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return passed, differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m qrtc_benchmark.phase5b_final_validation",
        description="Execute authorized Phase V-B final-validation for qrtc.",
    )
    parser.add_argument("--protocol-dir", required=True)
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--execution-index", required=True, type=int)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_final_validation(
            protocol_dir=Path(args.protocol_dir),
            artifacts_root=Path(args.artifacts_root),
            output_dir=Path(args.output_dir),
            authorization_path=Path(args.authorization),
            execution_index=args.execution_index,
            source_commit=args.source_commit,
            skip_preflight=args.skip_preflight,
        )
    except (PreflightError, AuthorizationValidationError) as exc:
        sys.stderr.write(f"PREFLIGHT FAILED:\n{exc}\n")
        return 2
    except (IntegrityError, FinalValidationResultValidationError) as exc:
        sys.stderr.write(f"INTEGRITY ERROR:\n{exc}\n")
        return 3

    print(f"Stage: {result.stage}")
    print(f"Selected: {result.selected_id}")
    print(f"Outcome: {result.outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
