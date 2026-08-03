from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict as _asdict
from pathlib import Path
from statistics import mean
from typing import Any

from qrtc_benchmark.eligibility import CandidateMetrics, check_all_eligibility
from qrtc_benchmark.phase5 import (
    PHASE5_POLICIES,
    PHASE5_REVISION,
    SPLIT_SEEDS,
    Phase5Config,
    Phase5Family,
    Phase5TrialRow,
    _build_split_manifest,
    _matched_differences,
    _policy_rows,
    build_phase5_trials,
    cluster_bootstrap_interval,
)
from qrtc_benchmark.phase5b_development import (
    IntegrityError,
    PreflightError,
    _check_controller_artifacts,
    _get_source_commit,
    _is_ancestor,
    _sha256_file,
    _verify_checksums,
    _write_csv_file,
    _write_json,
)
from qrtc_benchmark.result_schema import (
    RESULT_SCHEMA,
    SelectionResultV1,
    load_development_result,
    load_selection_result,
)
from qrtc_benchmark.selection_protocol import (
    BETA_HARM,
    BOOTSTRAP_REPS,
    BOOTSTRAP_SEED,
    COST_REGIMES,
    DEPLOYABLE_MANDATORY_CANDIDATES,
    GAMMA_UNSAFE,
    IMPLEMENTATION_COMMIT,
    LAMBDA_COST,
    MANDATORY_CANDIDATES,
    MAX_ACTIONS,
    OPTIONAL_BASELINE_IDS,
    PROTOCOL_ID,
    PROTOCOL_PHASE_REVISION,
    PROTOCOL_STATE,
    RELIABILITY_LEVELS,
    SPLIT_ALIASES,
    SPLIT_SEEDS_FROZEN,
    VALIDATION_FAMILY_TRIALS,
    VALIDATION_MECHANISMS,
    VALIDATION_PAIRS,
    VALIDATION_TRIPLES,
    canonical_candidate_declaration,
    canonical_config_declaration,
    canonical_split_declaration,
    compute_protocol_hashes,
)
from qrtc_benchmark.selection_rule import SelectionOutcome, select_controller
from qrtc_benchmark.validation_cli import (
    LockedStageError,
    ProtocolValidationError,
    validate_protocol_directory,
)

_MERGED_DEVELOPMENT_SOURCE_COMMIT = "54ac41b57af075dc2fa22cce66b6fe3ce7f5cffe"
_DEVELOPMENT_RESULT_DIR = "development-run-1"
_FORBIDDEN_FINAL_NAMES = ("final-validation", "test")


def _collect_input_hashes(protocol_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    target_files = [
        "preregistration.json",
        "commit.txt",
        "frozen_semantic_declarations.json",
        "checksums.sha256",
    ] + [f"manifests/{cid}.json" for cid in MANDATORY_CANDIDATES]
    for rel in target_files:
        path = protocol_dir / rel
        if path.exists():
            hashes[rel] = _sha256_file(path)
    return hashes


def _check_source_commit_ancestry(source_commit: str) -> list[str]:
    errors: list[str] = []
    if source_commit == "0" * 40:
        return ["could not determine source commit (git not available)"]
    if not _is_ancestor(_MERGED_DEVELOPMENT_SOURCE_COMMIT, source_commit):
        errors.append(
            f"source commit {source_commit!r} is not a descendant of required merge commit "
            f"{_MERGED_DEVELOPMENT_SOURCE_COMMIT!r}"
        )
    return errors


def _check_preregistration_and_semantics(protocol_dir: Path) -> list[str]:
    errors: list[str] = []
    prereg_path = protocol_dir / "preregistration.json"
    semantic_path = protocol_dir / "frozen_semantic_declarations.json"
    if not prereg_path.exists():
        return [f"preregistration.json missing from {protocol_dir}"]
    if not semantic_path.exists():
        return [f"frozen_semantic_declarations.json missing from {protocol_dir}"]

    try:
        prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
        semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"failed to parse frozen protocol artifacts: {exc}"]

    hashes = compute_protocol_hashes()
    if prereg.get("protocol_id") != PROTOCOL_ID:
        errors.append(
            f"protocol_id mismatch: got {prereg.get('protocol_id')!r}, expected {PROTOCOL_ID!r}"
        )
    if prereg.get("protocol_state") != PROTOCOL_STATE:
        errors.append(
            f"protocol_state mismatch: got {prereg.get('protocol_state')!r}, expected {PROTOCOL_STATE!r}"
        )
    if prereg.get("phase_revision") != PROTOCOL_PHASE_REVISION:
        errors.append(
            f"phase_revision mismatch: got {prereg.get('phase_revision')!r}, expected {PROTOCOL_PHASE_REVISION!r}"
        )
    if prereg.get("protocol_hash") != hashes.protocol_declaration_sha256:
        errors.append(
            "preregistration protocol_hash does not match canonical preregistration"
        )
    if prereg.get("implementation_commit") != IMPLEMENTATION_COMMIT:
        errors.append(
            f"preregistration implementation_commit mismatch: got {prereg.get('implementation_commit')!r}"
        )
    if prereg.get("authority") != "recommend_only":
        errors.append("preregistration authority must be recommend_only")
    if prereg.get("hardware_actuation_enabled") is not False:
        errors.append("preregistration hardware_actuation_enabled must be false")
    if prereg.get("final_validation_status") != "locked_not_executed":
        errors.append(
            "preregistration final_validation_status must be locked_not_executed"
        )

    if semantic.get("protocol_id") != PROTOCOL_ID:
        errors.append("frozen semantic declarations protocol_id mismatch")
    expected_hashes = {
        "split_declaration_sha256": hashes.split_declaration_sha256,
        "config_declaration_sha256": hashes.config_declaration_sha256,
        "candidate_declaration_sha256": hashes.candidate_declaration_sha256,
        "protocol_declaration_sha256": hashes.protocol_declaration_sha256,
    }
    if semantic.get("hashes") != expected_hashes:
        errors.append(
            "frozen semantic declaration hashes do not match canonical values"
        )
    if semantic.get("split_declaration") != canonical_split_declaration():
        errors.append("frozen split declaration does not match authoritative constants")
    if semantic.get("config_declaration") != canonical_config_declaration():
        errors.append(
            "frozen config declaration does not match authoritative constants"
        )
    if semantic.get("candidate_declaration") != canonical_candidate_declaration():
        errors.append(
            "frozen candidate declaration does not match authoritative constants"
        )
    return errors


def _check_development_result(artifacts_root: Path) -> list[str]:
    errors: list[str] = []
    dev_dir = artifacts_root / _DEVELOPMENT_RESULT_DIR
    result_path = dev_dir / "development_result.json"
    manifest_path = dev_dir / "run_manifest.json"
    if not result_path.exists():
        return [f"development result missing: {result_path}"]
    if not manifest_path.exists():
        return [f"development run manifest missing: {manifest_path}"]

    try:
        development_result = load_development_result(
            result_path.read_text(encoding="utf-8")
        )
        run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"failed to load development artifacts: {exc}"]

    if development_result.stage != "development":
        errors.append(
            f"development result stage must be 'development', got {development_result.stage!r}"
        )
    if development_result.outcome != "development_completed_no_selection":
        errors.append(
            f"development result outcome must be development_completed_no_selection, got {development_result.outcome!r}"
        )
    if development_result.selected_id is not None:
        errors.append("development result selected_id must be null")
    if development_result.selection_validation_status != "not_executed":
        errors.append(
            "development result selection_validation_status must be not_executed"
        )
    if development_result.final_validation_status != "locked_not_executed":
        errors.append(
            "development result final_validation_status must be locked_not_executed"
        )
    if development_result.integrity_all_passed is not True:
        errors.append("development result integrity_all_passed must be true")
    if run_manifest.get("stage") != "development":
        errors.append("development run manifest stage must be development")
    if (
        run_manifest.get("protocol_hash")
        != compute_protocol_hashes().protocol_declaration_sha256
    ):
        errors.append("development run manifest protocol_hash mismatch")
    return errors


def _check_validation_split_declaration(protocol_dir: Path) -> list[str]:
    errors: list[str] = []
    prereg_path = protocol_dir / "preregistration.json"
    if not prereg_path.exists():
        return [f"preregistration.json missing from {protocol_dir}"]
    try:
        prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"failed to parse preregistration.json: {exc}"]
    splits = prereg.get("splits", {})
    if splits.get("validation_family_trials") != VALIDATION_FAMILY_TRIALS:
        errors.append(
            "validation_family_trials mismatch: "
            f"recorded {splits.get('validation_family_trials')}, authoritative {VALIDATION_FAMILY_TRIALS}"
        )
    if splits.get("split_aliases") != SPLIT_ALIASES:
        errors.append("split_aliases mismatch for validation declaration")
    if splits.get("split_seeds") != {
        name: list(values) for name, values in SPLIT_SEEDS_FROZEN.items()
    }:
        errors.append("split_seeds mismatch for validation declaration")
    for family in Phase5Family:
        recorded = splits.get("validation_mechanisms", {}).get(family.value, [])
        authoritative = list(VALIDATION_MECHANISMS[family.value])
        if recorded != authoritative:
            errors.append(
                f"validation_mechanisms[{family.value}] mismatch: recorded {recorded}, authoritative {authoritative}"
            )
    if splits.get("validation_pairs") != list(VALIDATION_PAIRS):
        errors.append("validation_pairs mismatch")
    if splits.get("validation_triples") != list(VALIDATION_TRIPLES):
        errors.append("validation_triples mismatch")
    return errors


def _check_final_validation_locked_and_absent(
    artifacts_root: Path, current_output_dir: Path
) -> list[str]:
    errors: list[str] = []
    try:
        validate_protocol_directory(
            protocol_dir=artifacts_root.parent / "protocols" / PROTOCOL_ID,
            stage="final-validation",
            implementation_commit=IMPLEMENTATION_COMMIT,
        )
    except LockedStageError:
        pass
    else:
        errors.append("final-validation guard did not reject locked stage")

    for name in _FORBIDDEN_FINAL_NAMES:
        if (current_output_dir / name).exists():
            errors.append(
                f"forbidden final-validation path exists in output dir: {current_output_dir / name}"
            )

    for runs_csv in artifacts_root.glob("*/phase5_runs.csv"):
        run_dir_name = runs_csv.parent.name
        if run_dir_name == "final-validation-run-1":
            # Authorized Stage 3 output may exist after PR #26; keep scanning strict for
            # all other unexpected final-validation outputs.
            continue
        if run_dir_name.startswith("final-validation-run-"):
            errors.append(
                f"unregistered final-validation output detected: {runs_csv.parent}"
            )
            continue
        try:
            with runs_csv.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for index, row in enumerate(reader, start=2):
                    if row.get("split") in {"test", "final-validation"}:
                        errors.append(
                            f"final-validation row detected in historical artifact {runs_csv}:{index}"
                        )
                        break
        except OSError as exc:
            errors.append(f"failed to scan {runs_csv}: {exc}")
    return errors


def run_selection_validation_preflight(
    protocol_dir: Path,
    artifacts_root: Path,
    output_dir: Path,
    *,
    source_commit: str | None = None,
    protocol_hash: str | None = None,
) -> dict[str, Any]:
    if source_commit is None:
        source_commit = _get_source_commit()
    expected_protocol_hash = (
        protocol_hash or compute_protocol_hashes().protocol_declaration_sha256
    )
    errors: list[str] = []
    errors.extend(_check_source_commit_ancestry(source_commit))
    errors.extend(_check_preregistration_and_semantics(protocol_dir))
    errors.extend(_verify_checksums(protocol_dir))
    errors.extend(_check_controller_artifacts(protocol_dir))
    errors.extend(_check_development_result(artifacts_root))
    errors.extend(_check_validation_split_declaration(protocol_dir))
    errors.extend(_check_final_validation_locked_and_absent(artifacts_root, output_dir))

    try:
        validation_report = validate_protocol_directory(
            protocol_dir=protocol_dir,
            stage="selection-validation",
            implementation_commit=IMPLEMENTATION_COMMIT,
            expected_protocol_hash=expected_protocol_hash,
            output_dir=output_dir,
        )
        if validation_report.status != "ok":
            errors.extend(f"validation_cli: {error}" for error in validation_report.errors)
    except ProtocolValidationError as exc:
        errors.append(f"validation_cli: {exc}")
        validation_report = None

    if errors:
        error_lines = "\n".join(f"  - {error}" for error in errors)
        raise PreflightError(
            f"Selection-validation preflight failed with {len(errors)} error(s):\n{error_lines}"
        )

    return {
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": expected_protocol_hash,
        "source_commit": source_commit,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "stage": "selection-validation",
        "validation_report": validation_report.as_dict() if validation_report else None,
        "status": "ok",
    }


def _build_policy_metrics(rows: list[Phase5TrialRow], candidate: str) -> dict[str, Any]:
    subset = _policy_rows(rows, candidate)
    if not subset:
        return {"candidate": candidate, "trial_count": 0}
    oracle_rows = _policy_rows(rows, "oracle")
    oracle_by_key = {row.trial_key: row for row in oracle_rows}
    family_metrics: dict[str, Any] = {}
    for family in Phase5Family:
        family_subset = [row for row in subset if row.family == family.value]
        family_metrics[family.value] = {
            "trial_count": len(family_subset),
            "mean_utility": mean(row.utility for row in family_subset),
            "recovery_rate": mean(
                1.0 if row.recovered else 0.0 for row in family_subset
            ),
            "mean_intervention_cost": mean(
                row.intervention_cost for row in family_subset
            ),
            "mean_harm": mean(row.harm for row in family_subset),
            "unsafe_commitment_rate": mean(
                float(row.unsafe_commitment) for row in family_subset
            ),
            "unsafe_commitment_count": sum(
                int(row.unsafe_commitment) for row in family_subset
            ),
            "evidence_request_rate": mean(
                1.0 if row.evidence_requested else 0.0 for row in family_subset
            ),
        }
    matched_keys = [row.trial_key for row in subset if row.trial_key in oracle_by_key]
    oracle_regret = (
        mean(
            oracle_by_key[key].utility
            - next(row.utility for row in subset if row.trial_key == key)
            for key in matched_keys
        )
        if matched_keys
        else 0.0
    )
    return {
        "candidate": candidate,
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
        "oracle_regret": oracle_regret,
        "family_metrics": family_metrics,
    }


def _build_candidate_metrics(
    rows: list[Phase5TrialRow],
    global_integrity_ok: bool,
) -> tuple[list[CandidateMetrics], dict[str, Any], dict[str, Any]]:
    metrics_payload: dict[str, Any] = {}
    family_payload: dict[str, Any] = {}

    for candidate in PHASE5_POLICIES:
        policy_metrics = _build_policy_metrics(rows, candidate)
        metrics_payload[candidate] = {
            key: value
            for key, value in policy_metrics.items()
            if key != "family_metrics"
        }
        family_payload[candidate] = policy_metrics.get("family_metrics", {})

    mandatory_metrics: list[CandidateMetrics] = []
    mandatory_trial_keys: dict[str, set[str]] = {
        cid: {row.trial_key for row in _policy_rows(rows, cid)}
        for cid in MANDATORY_CANDIDATES
    }
    expected_keys = mandatory_trial_keys["greedy_gain"]

    for candidate in MANDATORY_CANDIDATES:
        strongest_other = max(
            (other for other in DEPLOYABLE_MANDATORY_CANDIDATES if other != candidate),
            key=lambda cid: metrics_payload[cid]["mean_utility"],
        )
        subset = _policy_rows(rows, candidate)
        trial_keys = mandatory_trial_keys[candidate]
        matched_rows_ok = (
            len(subset) == len(trial_keys)
            and trial_keys == expected_keys
            and len(subset) == len(expected_keys)
        )
        if candidate not in MANDATORY_CANDIDATES:
            continue
        if candidate == "greedy_gain":
            bootstrap_vs_greedy = {
                "left_policy": "greedy_gain",
                "right_policy": "greedy_gain",
                "mean_difference": 0.0,
                "ci_low": 0.0,
                "ci_high": 0.0,
                "bootstrap_reps": BOOTSTRAP_REPS,
                "bootstrap_seed": BOOTSTRAP_SEED,
                "matched_trial_count": len(expected_keys),
                "cluster_count": len(expected_keys),
                "method": "paired_cluster_bootstrap",
            }
        else:
            diffs = _matched_differences(rows, candidate, "greedy_gain")
            bootstrap_vs_greedy = cluster_bootstrap_interval(
                diffs, bootstrap_reps=BOOTSTRAP_REPS, bootstrap_seed=BOOTSTRAP_SEED
            )
            bootstrap_vs_greedy["left_policy"] = candidate
            bootstrap_vs_greedy["right_policy"] = "greedy_gain"
            bootstrap_vs_greedy["method"] = "paired_cluster_bootstrap"

        diffs_other = _matched_differences(rows, candidate, strongest_other)
        bootstrap_vs_strongest = cluster_bootstrap_interval(
            diffs_other, bootstrap_reps=BOOTSTRAP_REPS, bootstrap_seed=BOOTSTRAP_SEED
        )
        bootstrap_vs_strongest["left_policy"] = candidate
        bootstrap_vs_strongest["right_policy"] = strongest_other
        bootstrap_vs_strongest["method"] = "paired_cluster_bootstrap"

        mandatory_metrics.append(
            CandidateMetrics(
                controller_id=candidate,
                mean_utility=metrics_payload[candidate]["mean_utility"],
                recovery_rate=metrics_payload[candidate]["recovery_rate"],
                mean_intervention_cost=metrics_payload[candidate][
                    "mean_intervention_cost"
                ],
                mean_harm=metrics_payload[candidate]["mean_harm"],
                unsafe_commitment_rate=metrics_payload[candidate][
                    "unsafe_commitment_rate"
                ],
                evidence_request_rate=metrics_payload[candidate][
                    "evidence_request_rate"
                ],
                per_family_recovery_rate={
                    family: family_payload[candidate][family]["recovery_rate"]
                    for family in family_payload[candidate]
                },
                per_family_mean_harm={
                    family: family_payload[candidate][family]["mean_harm"]
                    for family in family_payload[candidate]
                },
                per_family_unsafe_count={
                    family: family_payload[candidate][family]["unsafe_commitment_count"]
                    for family in family_payload[candidate]
                },
                bootstrap_vs_greedy=bootstrap_vs_greedy,
                bootstrap_vs_strongest=bootstrap_vs_strongest,
                oracle_regret=metrics_payload[candidate]["oracle_regret"],
                matched_rows_ok=matched_rows_ok,
                artifact_hash_ok=True,
                protocol_match_ok=True,
                operational_integrity_ok=global_integrity_ok,
            )
        )
    return mandatory_metrics, metrics_payload, family_payload


def _build_bootstrap_payload(
    mandatory_metrics: list[CandidateMetrics],
) -> dict[str, Any]:
    metrics_by_id = {metric.controller_id: metric for metric in mandatory_metrics}
    payload: dict[str, Any] = {}
    for candidate in DEPLOYABLE_MANDATORY_CANDIDATES:
        payload[f"{candidate}_vs_greedy_gain"] = metrics_by_id[
            candidate
        ].bootstrap_vs_greedy
        payload[f"{candidate}_vs_strongest_other"] = metrics_by_id[
            candidate
        ].bootstrap_vs_strongest
    return payload


def _build_run_manifest(
    source_commit: str,
    protocol_hash: str,
    input_hashes: dict[str, str],
    trial_count: int,
) -> dict[str, Any]:
    return {
        "schema": "qrtc-selection-validation-run-manifest-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": protocol_hash,
        "phase_revision": PHASE5_REVISION,
        "stage": "selection-validation",
        "split": "validation",
        "source_commit": source_commit,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "base_commit": _MERGED_DEVELOPMENT_SOURCE_COMMIT,
        "split_seeds": list(SPLIT_SEEDS["validation"]),
        "validation_family_trials": VALIDATION_FAMILY_TRIALS,
        "reliability_levels": list(RELIABILITY_LEVELS),
        "cost_regimes": list(COST_REGIMES),
        "bootstrap_reps": BOOTSTRAP_REPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "lambda_cost": LAMBDA_COST,
        "beta_harm": BETA_HARM,
        "gamma_unsafe": GAMMA_UNSAFE,
        "max_actions": MAX_ACTIONS,
        "mandatory_candidates": list(MANDATORY_CANDIDATES),
        "optional_baselines": list(OPTIONAL_BASELINE_IDS),
        "trial_count": trial_count,
        "input_hashes": input_hashes,
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "preflight_validate_command": (
            "qrtc-selection validate --protocol-dir <protocol_dir> "
            "--stage selection-validation --implementation-commit <implementation_commit> "
            "--protocol-hash <protocol_hash> --output-dir <unused_output_dir>"
        ),
        "execution_command": (
            "python -m qrtc_benchmark.phase5b_selection_validation "
            "--protocol-dir <protocol_dir> --artifacts-root <artifacts_root> "
            "--output-dir <output_dir> --source-commit <source_commit> "
            "--protocol-hash <protocol_hash>"
        ),
    }


def _build_markdown_report(
    *,
    source_commit: str,
    protocol_hash: str,
    selection_result: SelectionResultV1,
    metrics_payload: dict[str, Any],
    eligibility_payload: dict[str, Any],
    bootstrap_payload: dict[str, Any],
) -> str:
    outcome_reason = (
        f"provisional selection: `{selection_result.selected_id}`"
        if selection_result.outcome == SelectionOutcome.PROVISIONAL_SELECTION.value
        else "no controller selected"
    )
    lines = [
        "# Phase V-B Selection-Validation Report",
        "",
        "**Stage:** selection-validation  ",
        f"**Protocol:** `{PROTOCOL_ID}`  ",
        f"**Protocol hash:** `{protocol_hash}`  ",
        f"**Source commit:** `{source_commit}`  ",
        f"**Implementation commit:** `{IMPLEMENTATION_COMMIT}`  ",
        f"**Outcome:** `{selection_result.outcome}`  ",
        f"**Selected controller:** `{selection_result.selected_id}`  "
        if selection_result.selected_id is not None
        else "**Selected controller:** `null`  ",
        "",
        "Selection-validation was executed under the frozen preregistered protocol.",
        f"Exact decision: **{outcome_reason}**.",
        "",
        "## Required safety statements",
        "",
        "- Any selected controller is **provisional only**.",
        "- `oracle` is **not deployable** and was never eligible.",
        "- Final-validation remains **locked and not executed**.",
        "- No hardware authority is granted.",
        "",
        "## Eligibility",
        "",
        "| Candidate | Deployable | Eligible | Superior vs greedy_gain | Reasons |",
        "|---|---:|---:|---:|---|",
    ]
    for candidate in MANDATORY_CANDIDATES:
        eligibility = eligibility_payload[candidate]
        superior = eligibility.get("superior_vs_greedy", False)
        reasons = "; ".join(eligibility.get("disqualification_reasons", [])) or "—"
        deployable = "yes" if candidate != "oracle" else "no"
        lines.append(
            f"| {candidate} | {deployable} | {'yes' if eligibility['eligible'] else 'no'} "
            f"| {'yes' if superior else 'no'} | {reasons} |"
        )
    lines.extend(
        [
            "",
            "## Candidate summary",
            "",
            "| Candidate | Mean utility | Recovery rate | Mean cost | Mean harm | Unsafe rate |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for candidate in MANDATORY_CANDIDATES:
        metric = metrics_payload[candidate]
        lines.append(
            f"| {candidate} | {metric['mean_utility']:.6f} | {metric['recovery_rate']:.6f} "
            f"| {metric['mean_intervention_cost']:.6f} | {metric['mean_harm']:.6f} "
            f"| {metric['unsafe_commitment_rate']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Paired bootstrap comparisons",
            "",
            "| Comparison | Mean Δ | CI low | CI high |",
            "|---|---:|---:|---:|",
        ]
    )
    for key, comparison in sorted(bootstrap_payload.items()):
        left = comparison.get("left_policy", "?")
        right = comparison.get("right_policy", "?")
        lines.append(
            f"| {left} vs {right} | {comparison['mean_difference']:.6f} "
            f"| {comparison['ci_low']:.6f} | {comparison['ci_high']:.6f} |"
        )
    return "\n".join(lines) + "\n"


def run_selection_validation(
    protocol_dir: Path,
    artifacts_root: Path,
    output_dir: Path,
    *,
    source_commit: str | None = None,
    protocol_hash: str | None = None,
    skip_preflight: bool = False,
) -> SelectionResultV1:
    if source_commit is None:
        source_commit = _get_source_commit()
    expected_protocol_hash = (
        protocol_hash or compute_protocol_hashes().protocol_declaration_sha256
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    if not skip_preflight:
        run_selection_validation_preflight(
            protocol_dir=protocol_dir,
            artifacts_root=artifacts_root,
            output_dir=output_dir,
            source_commit=source_commit,
            protocol_hash=expected_protocol_hash,
        )

    rows = build_phase5_trials(split_name="validation", config=Phase5Config())
    generated_splits = {row.split for row in rows}
    if generated_splits != {"validation"}:
        raise IntegrityError(
            f"selection-validation run generated unexpected splits: {sorted(generated_splits)}"
        )

    qrtc_trial_keys = {row.trial_key for row in rows if row.policy == "qrtc"}
    expected_trial_keys = (
        VALIDATION_FAMILY_TRIALS
        * len(list(Phase5Family))
        * len(RELIABILITY_LEVELS)
        * len(COST_REGIMES)
    )
    integrity_notes: list[str] = []
    global_integrity_ok = len(qrtc_trial_keys) == expected_trial_keys
    if not global_integrity_ok:
        integrity_notes.append(
            f"validation trial key count {len(qrtc_trial_keys)} != expected {expected_trial_keys}"
        )

    mandatory_metrics, metrics_payload, family_payload = _build_candidate_metrics(
        rows, global_integrity_ok
    )
    eligibility = check_all_eligibility(mandatory_metrics)
    decision = select_controller(mandatory_metrics, eligibility)
    bootstrap_payload = _build_bootstrap_payload(mandatory_metrics)

    eligibility_payload: dict[str, Any] = {}
    for metric in mandatory_metrics:
        result = eligibility[metric.controller_id]
        eligibility_payload[metric.controller_id] = {
            **result.as_dict(),
            "deployable": metric.controller_id != "oracle",
            "superior_vs_greedy": metric.bootstrap_vs_greedy.get("ci_low", 0.0) > 0.0,
        }

    input_hashes = _collect_input_hashes(protocol_dir)
    split_manifest = _build_split_manifest("validation")
    run_manifest = _build_run_manifest(
        source_commit=source_commit,
        protocol_hash=expected_protocol_hash,
        input_hashes=input_hashes,
        trial_count=len(rows),
    )

    trials_csv = output_dir / "phase5_runs.csv"
    with trials_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(Phase5TrialRow.__annotations__.keys())
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(_asdict(row))

    split_manifest_path = output_dir / "selection_validation_manifest.json"
    _write_json(split_manifest_path, split_manifest)
    metrics_json_path = output_dir / "candidate_metrics.json"
    _write_json(metrics_json_path, metrics_payload)
    metrics_csv_rows: list[dict[str, Any]] = []
    csv_fields = [
        "candidate",
        "trial_count",
        "mean_utility",
        "recovery_rate",
        "mean_intervention_cost",
        "mean_harm",
        "unsafe_commitment_rate",
        "unsafe_commitment_count",
        "evidence_request_rate",
        "oracle_regret",
        "mandatory",
        "deployable",
        "eligible",
        "superior_vs_greedy",
    ]
    for candidate in PHASE5_POLICIES:
        metric = metrics_payload[candidate]
        eligibility_result = eligibility_payload.get(candidate)
        metrics_csv_rows.append(
            {
                **{
                    field: metric.get(field, "")
                    for field in csv_fields
                    if field in metric
                },
                "candidate": candidate,
                "mandatory": candidate in MANDATORY_CANDIDATES,
                "deployable": candidate in DEPLOYABLE_MANDATORY_CANDIDATES,
                "eligible": eligibility_result["eligible"]
                if eligibility_result
                else "",
                "superior_vs_greedy": eligibility_result["superior_vs_greedy"]
                if eligibility_result
                else "",
            }
        )
    metrics_csv_path = output_dir / "candidate_metrics.csv"
    _write_csv_file(metrics_csv_path, csv_fields, metrics_csv_rows)
    family_metrics_path = output_dir / "family_metrics.json"
    _write_json(family_metrics_path, family_payload)
    eligibility_path = output_dir / "eligibility_report.json"
    _write_json(eligibility_path, eligibility_payload)
    comparisons_path = output_dir / "paired_comparisons.json"
    _write_json(comparisons_path, bootstrap_payload)
    run_manifest_path = output_dir / "run_manifest.json"
    _write_json(run_manifest_path, run_manifest)

    selection_result = SelectionResultV1(
        result_schema=RESULT_SCHEMA,
        protocol_id=PROTOCOL_ID,
        protocol_hash=expected_protocol_hash,
        phase_revision=PHASE5_REVISION,
        stage="selection-validation",
        input_hashes=input_hashes,
        implementation_commit=IMPLEMENTATION_COMMIT,
        source_commit=source_commit,
        metrics_summary={
            candidate: {
                key: value for key, value in metric.items() if key != "family_metrics"
            }
            for candidate, metric in metrics_payload.items()
        },
        eligibility_reasons=eligibility_payload,
        bootstrap_comparisons=bootstrap_payload,
        selected_id=decision.selected_id,
        oracle_ceiling={
            **metrics_payload["oracle"],
            "deployable": False,
            "eligible": False,
        },
        authority="recommend_only",
        hardware_actuation_enabled=False,
        final_validation_status="locked_not_executed",
        outcome=decision.outcome.value,
    )
    selection_result_path = output_dir / "selection_result.json"
    _write_json(
        selection_result_path,
        json.loads(selection_result.canonical_bytes().decode("utf-8")),
    )
    validated = load_selection_result(selection_result_path.read_text(encoding="utf-8"))
    if validated.outcome != selection_result.outcome:
        raise IntegrityError("selection result round-trip validation mismatch")

    report_path = output_dir / "SELECTION_VALIDATION_REPORT.md"
    report_path.write_text(
        _build_markdown_report(
            source_commit=source_commit,
            protocol_hash=expected_protocol_hash,
            selection_result=selection_result,
            metrics_payload=metrics_payload,
            eligibility_payload=eligibility_payload,
            bootstrap_payload=bootstrap_payload,
        ),
        encoding="utf-8",
    )

    canonical_files = [
        selection_result_path,
        metrics_json_path,
        metrics_csv_path,
        family_metrics_path,
        eligibility_path,
        comparisons_path,
        trials_csv,
        split_manifest_path,
        run_manifest_path,
        report_path,
    ]
    checksums_lines = []
    for file_path in canonical_files:
        checksums_lines.append(
            f"{_sha256_file(file_path)}  {file_path.relative_to(output_dir).as_posix()}"
        )
    checksums_path = output_dir / "checksums.sha256"
    checksums_path.write_text("\n".join(checksums_lines) + "\n", encoding="utf-8")
    return validated


def verify_selection_validation_reproducibility(
    run1_dir: Path, run2_dir: Path
) -> tuple[bool, list[str]]:
    names = (
        "selection_result.json",
        "candidate_metrics.json",
        "candidate_metrics.csv",
        "family_metrics.json",
        "eligibility_report.json",
        "paired_comparisons.json",
        "phase5_runs.csv",
        "selection_validation_manifest.json",
        "run_manifest.json",
        "SELECTION_VALIDATION_REPORT.md",
        "checksums.sha256",
    )
    differences: list[str] = []
    for name in names:
        p1 = run1_dir / name
        p2 = run2_dir / name
        if not p1.exists():
            differences.append(f"{name}: missing from run 1")
            continue
        if not p2.exists():
            differences.append(f"{name}: missing from run 2")
            continue
        h1 = _sha256_file(p1)
        h2 = _sha256_file(p2)
        if h1 != h2:
            differences.append(f"{name}: sha256 differs (run1={h1}, run2={h2})")
    return len(differences) == 0, differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m qrtc_benchmark.phase5b_selection_validation",
        description="Execute Phase V-B Stage 2 selection-validation under the frozen protocol.",
    )
    parser.add_argument("--protocol-dir", required=True)
    parser.add_argument("--artifacts-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--protocol-hash", default=None)
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = run_selection_validation(
            protocol_dir=Path(args.protocol_dir),
            artifacts_root=Path(args.artifacts_root),
            output_dir=Path(args.output_dir),
            source_commit=args.source_commit,
            protocol_hash=args.protocol_hash,
            skip_preflight=args.skip_preflight,
        )
    except PreflightError as exc:
        sys.stderr.write(f"PREFLIGHT FAILED:\n{exc}\n")
        return 2
    except IntegrityError as exc:
        sys.stderr.write(f"INTEGRITY ERROR:\n{exc}\n")
        return 3

    print(f"Stage: {result.stage}")
    print(f"Outcome: {result.outcome}")
    print(f"Selected: {result.selected_id!r}")
    print("Final-validation: locked_not_executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
