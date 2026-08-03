from __future__ import annotations

# Phase V-B Stage 1: Development Comparison Runner
#
# Protocol ID: phase5b-selection-v1
# Stage:       development
# Outcome:     development_completed_no_selection
#
# This module implements the authoritative Phase V-B development comparison.
# It is the ONLY approved entry point for running Phase V-B development benchmarks.
#
# Scope:
#   - development split only
#   - all mandatory candidates (qrtc, qrtc_no_abstention, qrtc_untyped, greedy_gain, oracle)
#   - optional descriptive baselines included if the runner produces them
#   - no selection, no winner declaration, no validation/test splits
#
# Preflight (fail-closed):
#   1. Verify source commit is a descendant of implementation_commit.
#   2. Load and validate the canonical preregistration.
#   3. Verify protocol state is preregistered_not_executed.
#   4. Verify checksums for all frozen protocol files.
#   5. Load all mandatory rescueos-controller-v1 artifacts.
#   6. Verify candidate IDs, versions, roles, deployability, etc.
#   7. Verify development split declaration matches authoritative Phase V-B constants.
#   8. Verify selection-validation and final-validation remain inaccessible.
#   9. Run qrtc-selection validate for stage development (dry-run).
#
# Result schema: rescueos-development-result-v1
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict as _asdict
from pathlib import Path
from statistics import mean
from typing import Any

from qrtc_benchmark.controller_artifact import (
    ControllerArtifactValidationError,
    load_controller_artifact,
)
from qrtc_benchmark.phase5 import (
    PHASE5_REVISION,
    Phase5Config,
    Phase5Family,
    Phase5TrialRow,
    _build_split_manifest,
    _matched_differences,
    _policy_rows,
    _strongest_nonoracle_policy,
    build_phase5_trials,
    cluster_bootstrap_interval,
)
from qrtc_benchmark.result_schema import (
    _DEVELOPMENT_OUTCOME,
    DEVELOPMENT_RESULT_SCHEMA,
    DevelopmentResultV1,
    load_development_result,
)
from qrtc_benchmark.selection_protocol import (
    CONTROLLER_VERSIONS,
    DEPLOYABLE_MANDATORY_CANDIDATES,
    DEVELOPMENT_FAMILY_TRIALS,
    DEVELOPMENT_MECHANISMS,
    DEVELOPMENT_PAIRS,
    DEVELOPMENT_TRIPLES,
    IMPLEMENTATION_COMMIT,
    MANDATORY_CANDIDATES,
    PROTOCOL_ID,
    PROTOCOL_PHASE_REVISION,
    PROTOCOL_STATE,
    compute_protocol_hashes,
)
from qrtc_benchmark.validation_cli import validate_protocol_directory

# ── Typing aliases ─────────────────────────────────────────────────────────────

_ArtifactHashes = dict[str, str]

# ── Errors ─────────────────────────────────────────────────────────────────────


class PreflightError(RuntimeError):
    """Raised when a preflight check fails.  Run is aborted."""


class IntegrityError(RuntimeError):
    """Raised when an integrity check fails after the run."""


# ── Constants ──────────────────────────────────────────────────────────────────

#: Frozen Phase5Config for Phase V-B (sourced from preregistration).
FROZEN_CONFIG = Phase5Config()

#: Mandatory candidates that must appear in every development run.
_MANDATORY: tuple[str, ...] = MANDATORY_CANDIDATES

#: Merge commit of the canonical development comparison result on main (PR #25).
_DEVELOPMENT_RESULT_MERGE_COMMIT = "390481e62500fda6e98559508c46134382b77736"


# ── Git utilities ──────────────────────────────────────────────────────────────


def _get_source_commit(repo_root: Path | None = None) -> str:
    """Return the current HEAD commit hash (40 hex)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root or Path.cwd(),
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "0" * 40


def _is_ancestor(ancestor: str, descendant: str, repo_root: Path | None = None) -> bool:
    """Return True if *ancestor* is an ancestor of (or equal to) *descendant*."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True,
            check=False,
            cwd=repo_root or Path.cwd(),
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ── Checksum utilities ─────────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_checksums(protocol_dir: Path) -> list[str]:
    """Verify checksums.sha256 in *protocol_dir*.  Return list of mismatches."""
    checksums_path = protocol_dir / "checksums.sha256"
    if not checksums_path.exists():
        return [f"checksums.sha256 missing from {protocol_dir}"]

    mismatches: list[str] = []
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            mismatches.append(f"malformed checksum line: {line!r}")
            continue
        expected_digest, rel_path = parts
        file_path = protocol_dir / rel_path
        if not file_path.exists():
            mismatches.append(f"file missing: {rel_path}")
            continue
        actual_digest = _sha256_file(file_path)
        if actual_digest != expected_digest:
            mismatches.append(
                f"checksum mismatch for {rel_path}: "
                f"expected {expected_digest}, got {actual_digest}"
            )
    return mismatches


# ── Preflight checks ───────────────────────────────────────────────────────────


def _check_commit_ancestry(source_commit: str) -> list[str]:
    """Check that source commit is implementation_commit or a descendant."""
    errors: list[str] = []
    if source_commit == "0" * 40:
        errors.append("could not determine source commit (git not available)")
        return errors
    if source_commit == IMPLEMENTATION_COMMIT:
        return []
    if _is_ancestor(IMPLEMENTATION_COMMIT, source_commit):
        return []
    if not _is_ancestor(_DEVELOPMENT_RESULT_MERGE_COMMIT, source_commit):
        errors.append(
            f"source commit {source_commit!r} is not a descendant of "
            f"implementation commit {IMPLEMENTATION_COMMIT!r} or merged development "
            f"commit {_DEVELOPMENT_RESULT_MERGE_COMMIT!r}"
        )
    return errors


def _check_preregistration(protocol_dir: Path) -> list[str]:
    """Validate preregistration.json contents.  Return list of errors."""
    errors: list[str] = []
    prereg_path = protocol_dir / "preregistration.json"
    if not prereg_path.exists():
        return [f"preregistration.json missing from {protocol_dir}"]

    try:
        prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"failed to parse preregistration.json: {exc}"]

    if prereg.get("protocol_id") != PROTOCOL_ID:
        errors.append(
            f"protocol_id mismatch: got {prereg.get('protocol_id')!r}, "
            f"expected {PROTOCOL_ID!r}"
        )

    if prereg.get("protocol_state") != PROTOCOL_STATE:
        errors.append(
            f"protocol_state must be {PROTOCOL_STATE!r}, "
            f"got {prereg.get('protocol_state')!r}"
        )

    recorded_hash = prereg.get("protocol_hash", "")
    expected_hash = compute_protocol_hashes().protocol_declaration_sha256
    if recorded_hash != expected_hash:
        errors.append(
            f"protocol_hash mismatch: recorded {recorded_hash!r}, "
            f"computed {expected_hash!r}"
        )

    if prereg.get("phase_revision") != PROTOCOL_PHASE_REVISION:
        errors.append(f"phase_revision mismatch: got {prereg.get('phase_revision')!r}")

    if prereg.get("no_experiment_executed") is not True:
        errors.append("preregistration must have no_experiment_executed=true")

    if prereg.get("no_winner_selected") is not True:
        errors.append("preregistration must have no_winner_selected=true")

    return errors


def _check_controller_artifacts(protocol_dir: Path) -> list[str]:
    """Load all mandatory controller artifacts fail-closed.  Return errors."""
    errors: list[str] = []
    manifests_dir = protocol_dir / "manifests"
    for cid in _MANDATORY:
        artifact_path = manifests_dir / f"{cid}.json"
        if not artifact_path.exists():
            errors.append(f"mandatory artifact missing: manifests/{cid}.json")
            continue
        try:
            artifact, _ = load_controller_artifact(
                json.loads(artifact_path.read_text(encoding="utf-8")),
                allow_oracle=True,
                deployable_only=False,
            )
        except ControllerArtifactValidationError as exc:
            errors.append(f"artifact {cid}.json failed validation: {exc}")
            continue

        # Verify fields against preregistration.
        if artifact.controller_id != cid:
            errors.append(
                f"artifact {cid}.json: controller_id {artifact.controller_id!r} "
                f"does not match expected {cid!r}"
            )
        expected_version = CONTROLLER_VERSIONS.get(cid)
        if expected_version and artifact.controller_version != expected_version:
            errors.append(
                f"artifact {cid}.json: version {artifact.controller_version!r} "
                f"does not match preregistration {expected_version!r}"
            )
        if artifact.implementation_commit != IMPLEMENTATION_COMMIT:
            errors.append(
                f"artifact {cid}.json: implementation_commit "
                f"{artifact.implementation_commit!r} != {IMPLEMENTATION_COMMIT!r}"
            )
        if artifact.protocol_id != PROTOCOL_ID:
            errors.append(
                f"artifact {cid}.json: protocol_id {artifact.protocol_id!r} "
                f"!= {PROTOCOL_ID!r}"
            )
        if artifact.authority != "recommend_only":
            errors.append(
                f"artifact {cid}.json: authority {artifact.authority!r} != recommend_only"
            )
        if artifact.hardware_actuation_enabled is not False:
            errors.append(
                f"artifact {cid}.json: hardware_actuation_enabled must be false"
            )
    return errors


def _check_development_split(protocol_dir: Path) -> list[str]:
    """Verify development split declaration matches Phase V-B constants."""
    errors: list[str] = []
    prereg_path = protocol_dir / "preregistration.json"
    if not prereg_path.exists():
        return ["preregistration.json missing"]

    try:
        prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"failed to parse preregistration.json: {exc}"]

    splits = prereg.get("splits", {})

    if splits.get("development_family_trials") != DEVELOPMENT_FAMILY_TRIALS:
        errors.append(
            f"development_family_trials mismatch: "
            f"recorded {splits.get('development_family_trials')}, "
            f"authoritative {DEVELOPMENT_FAMILY_TRIALS}"
        )

    # Verify mechanism sets
    for family in Phase5Family:
        recorded = splits.get("development_mechanisms", {}).get(family.value, [])
        authoritative = list(DEVELOPMENT_MECHANISMS[family.value])
        if recorded != authoritative:
            errors.append(
                f"development_mechanisms[{family.value}] mismatch: "
                f"recorded {recorded}, authoritative {authoritative}"
            )

    # Verify pairs
    recorded_pairs = splits.get("development_pairs", [])
    if recorded_pairs != list(DEVELOPMENT_PAIRS):
        errors.append(
            f"development_pairs mismatch: recorded {recorded_pairs}, "
            f"authoritative {list(DEVELOPMENT_PAIRS)}"
        )

    # Verify triples
    recorded_triples = splits.get("development_triples", [])
    if recorded_triples != list(DEVELOPMENT_TRIPLES):
        errors.append(
            f"development_triples mismatch: recorded {recorded_triples}, "
            f"authoritative {list(DEVELOPMENT_TRIPLES)}"
        )

    return errors


def _check_validation_inaccessible(output_dir: Path) -> list[str]:
    """Verify that output_dir contains no selection-validation or final-validation rows."""
    errors: list[str] = []
    for sub in ("selection-validation", "final-validation", "validation", "test"):
        sub_path = output_dir / sub
        if sub_path.exists():
            errors.append(
                f"forbidden directory exists in output: {sub_path} "
                "(selection-validation and final-validation must not be accessible)"
            )
    return errors


def run_preflight(
    protocol_dir: Path,
    output_dir: Path,
    source_commit: str | None = None,
) -> None:
    """Run all preflight checks.  Raise PreflightError on any failure.

    Parameters
    ----------
    protocol_dir:
        Path to the frozen protocol directory (e.g. artifacts/protocols/phase5b-selection-v1).
    output_dir:
        Proposed output directory (must not contain forbidden splits).
    source_commit:
        40-hex source commit.  If None, determined from git HEAD.
    """
    if source_commit is None:
        source_commit = _get_source_commit()

    errors: list[str] = []

    # 1. Commit ancestry
    errors.extend(_check_commit_ancestry(source_commit))

    # 2. Preregistration
    errors.extend(_check_preregistration(protocol_dir))

    # 3. Checksums
    errors.extend(_verify_checksums(protocol_dir))

    # 4. Controller artifacts
    errors.extend(_check_controller_artifacts(protocol_dir))

    # 5. Development split declaration
    errors.extend(_check_development_split(protocol_dir))

    # 6. Validation inaccessibility (output must not have forbidden dirs)
    errors.extend(_check_validation_inaccessible(output_dir))

    # 7. Dry-run validation CLI
    try:
        report = validate_protocol_directory(
            protocol_dir=protocol_dir,
            stage="development",
            implementation_commit=IMPLEMENTATION_COMMIT,
        )
        if report.status != "ok":
            for error in report.errors:
                errors.append(f"validation_cli: {error}")
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append(f"validation_cli raised: {exc}")

    if errors:
        error_lines = "\n".join(f"  - {e}" for e in errors)
        raise PreflightError(
            f"Preflight failed with {len(errors)} error(s):\n{error_lines}"
        )


# ── Metrics computation ────────────────────────────────────────────────────────


def _compute_candidate_metrics(
    rows: list[Phase5TrialRow],
    candidate: str,
    oracle_rows: list[Phase5TrialRow],
) -> dict[str, Any]:
    """Compute all required descriptive metrics for a single candidate."""
    subset = _policy_rows(rows, candidate)
    if not subset:
        return {"candidate": candidate, "trial_count": 0}

    oracle_by_key = {row.trial_key: row for row in oracle_rows}
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

    evidence_rows = subset
    abstention_rate = mean(
        1.0 if row.evidence_requested else 0.0 for row in evidence_rows
    )

    # V1–V4 family metrics
    family_metrics: dict[str, Any] = {}
    for family in Phase5Family:
        family_subset = [row for row in subset if row.family == family.value]
        if family_subset:
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
                "evidence_request_rate": mean(
                    1.0 if row.evidence_requested else 0.0 for row in family_subset
                ),
            }
        else:
            family_metrics[family.value] = None

    return {
        "candidate": candidate,
        "trial_count": len(subset),
        "mean_utility": mean(row.utility for row in subset),
        "recovery_rate": mean(1.0 if row.recovered else 0.0 for row in subset),
        "mean_intervention_cost": mean(row.intervention_cost for row in subset),
        "mean_harm": mean(row.harm for row in subset),
        "unsafe_commitment_rate": mean(float(row.unsafe_commitment) for row in subset),
        "evidence_request_rate": abstention_rate,
        "oracle_regret": oracle_regret,
        "family_metrics": family_metrics,
    }


def _compute_all_metrics(rows: list[Phase5TrialRow]) -> dict[str, Any]:
    """Compute metrics for every mandatory candidate."""
    oracle_rows = _policy_rows(rows, "oracle")
    result: dict[str, Any] = {}
    for candidate in _MANDATORY:
        result[candidate] = _compute_candidate_metrics(rows, candidate, oracle_rows)
    return result


def _compute_bootstrap_comparisons(
    rows: list[Phase5TrialRow], config: Phase5Config
) -> dict[str, Any]:
    """Compute all required paired bootstrap comparisons."""
    comparisons: dict[str, Any] = {}

    # Strongest deployable (excludes oracle; used for the primary comparison)
    strongest = _strongest_nonoracle_policy(rows)
    comparisons["_strongest_deployable_nonoracle"] = strongest

    # Paired delta vs greedy_gain for every mandatory deployable candidate
    for candidate in DEPLOYABLE_MANDATORY_CANDIDATES:
        if candidate == "greedy_gain":
            continue
        diffs = _matched_differences(rows, candidate, "greedy_gain")
        if not diffs:
            comparisons[f"{candidate}_vs_greedy_gain"] = {
                "note": "no matched rows",
                "label": "non-selective development diagnostic",
            }
            continue
        interval = cluster_bootstrap_interval(
            differences=diffs,
            bootstrap_reps=config.bootstrap_reps,
            bootstrap_seed=config.bootstrap_seed,
        )
        interval["left_policy"] = candidate
        interval["right_policy"] = "greedy_gain"
        interval["label"] = "non-selective development diagnostic"
        interval["method"] = "paired_cluster_bootstrap"
        comparisons[f"{candidate}_vs_greedy_gain"] = interval

    # Paired delta vs strongest_deployable for every mandatory deployable candidate
    for candidate in DEPLOYABLE_MANDATORY_CANDIDATES:
        if candidate == strongest:
            continue
        diffs = _matched_differences(rows, candidate, strongest)
        if not diffs:
            comparisons[f"{candidate}_vs_strongest_deployable"] = {
                "note": "no matched rows",
                "label": "non-selective development diagnostic",
            }
            continue
        interval = cluster_bootstrap_interval(
            differences=diffs,
            bootstrap_reps=config.bootstrap_reps,
            bootstrap_seed=config.bootstrap_seed,
        )
        interval["left_policy"] = candidate
        interval["right_policy"] = strongest
        interval["label"] = "non-selective development diagnostic"
        interval["method"] = "paired_cluster_bootstrap"
        comparisons[f"{candidate}_vs_strongest_deployable"] = interval

    return comparisons


# ── Artifact writing ───────────────────────────────────────────────────────────


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_csv_file(
    path: Path, fieldnames: list[str], rows: list[dict[str, Any]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_run_manifest(
    source_commit: str,
    protocol_hash: str,
    input_hashes: _ArtifactHashes,
    trial_count: int,
    config: Phase5Config,
) -> dict[str, Any]:
    """Build reproducibility manifest (no secrets/usernames/timestamps/abs paths)."""
    return {
        "schema": "qrtc-development-run-manifest-v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_hash": protocol_hash,
        "phase_revision": PHASE5_REVISION,
        "stage": "development",
        "source_commit": source_commit,
        "implementation_commit": IMPLEMENTATION_COMMIT,
        "split": "development",
        "split_seeds": [701, 702, 703],
        "development_family_trials": config.development_family_trials,
        "reliability_levels": list(config.reliability_levels),
        "cost_regimes": list(config.cost_regimes),
        "bootstrap_reps": config.bootstrap_reps,
        "bootstrap_seed": config.bootstrap_seed,
        "lambda_cost": config.lambda_cost,
        "beta_harm": config.beta_harm,
        "gamma_unsafe": config.gamma_unsafe,
        "max_actions": config.max_actions,
        "mandatory_candidates": list(_MANDATORY),
        "trial_count": trial_count,
        "input_hashes": input_hashes,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "command": (
            "qrtc-benchmark-phase5b-dev "
            "--protocol-dir <protocol_dir> "
            "--output-dir <output_dir>"
        ),
        "determinism_note": (
            "Phase V-B uses _stable_hash (SHA-256-based) instead of Python built-in "
            "hash() for all experiment-affecting random selections.  Results are "
            "byte-identical regardless of PYTHONHASHSEED."
        ),
    }


def _build_development_markdown_report(
    source_commit: str,
    protocol_hash: str,
    trial_count: int,
    metrics: dict[str, Any],
    comparisons: dict[str, Any],
    integrity_passed: bool,
    integrity_notes: list[str],
) -> str:
    """Build the concise Markdown development report."""
    lines: list[str] = [
        "# Phase V-B Development Comparison Report",
        "",
        "**Stage:** development  ",
        "**Outcome:** development_completed_no_selection  ",
        "**Selected controller:** none (null)  ",
        "**Selection-validation:** NOT EXECUTED  ",
        "**Final-validation:** LOCKED AND NOT EXECUTED  ",
        "",
        "---",
        "",
        "## Protocol",
        "",
        f"- Protocol ID: `{PROTOCOL_ID}`",
        f"- Protocol hash: `{protocol_hash}`",
        f"- Phase revision: `{PHASE5_REVISION}`",
        f"- Implementation commit: `{IMPLEMENTATION_COMMIT}`",
        f"- Source commit: `{source_commit}`",
        f"- Development trials per family: {DEVELOPMENT_FAMILY_TRIALS}",
        f"- Total trial rows: {trial_count}",
        "",
        "---",
        "",
        "## Integrity and Safety Diagnostics",
        "",
        f"All integrity checks passed: **{'YES' if integrity_passed else 'NO'}**",
        "",
    ]

    if integrity_notes:
        lines.append("### Notes")
        lines.append("")
        for note in integrity_notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Candidate Metrics (descriptive — no selection applied)",
            "",
            "| Candidate | Mean Utility | Recovery Rate | Mean Cost | Mean Harm | Unsafe% | Evidence% | Oracle Regret |",
            "|-----------|-------------|---------------|-----------|-----------|---------|-----------|---------------|",
        ]
    )

    for cid, m in metrics.items():
        if not m.get("trial_count"):
            continue
        lines.append(
            f"| {cid} "
            f"| {m['mean_utility']:.4f} "
            f"| {m['recovery_rate']:.4f} "
            f"| {m['mean_intervention_cost']:.4f} "
            f"| {m['mean_harm']:.4f} "
            f"| {m['unsafe_commitment_rate']:.4f} "
            f"| {m['evidence_request_rate']:.4f} "
            f"| {m['oracle_regret']:.4f} |"
        )

    strongest = comparisons.get("_strongest_deployable_nonoracle", "unknown")
    lines.extend(
        [
            "",
            "---",
            "",
            "## Paired Bootstrap Comparisons (non-selective development diagnostics)",
            "",
            f"Strongest deployable non-oracle comparator: **{strongest}**",
            "",
            "All superiority intervals below are **non-selective development diagnostics**.  ",
            "They do NOT constitute a selection decision.  No controller has been selected.",
            "",
            "| Comparison | Mean Δ | CI low | CI high |",
            "|------------|--------|--------|---------|",
        ]
    )

    for key, comp in comparisons.items():
        if key.startswith("_"):
            continue
        if isinstance(comp, dict) and "mean_difference" in comp:
            left = comp.get("left_policy", "?")
            right = comp.get("right_policy", "?")
            lines.append(
                f"| {left} vs {right} "
                f"| {comp['mean_difference']:.4f} "
                f"| {comp['ci_low']:.4f} "
                f"| {comp['ci_high']:.4f} |"
            )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Authoritative Statements",
            "",
            "1. This is a **development comparison only**.  No controller has been selected.",
            "2. **Selection-validation has not been executed.**",
            "3. **Final-validation is locked and has not been executed.**",
            "4. No provisional winner has been declared.",
            "5. The next stage (selection-validation) requires separate user authorization.",
            "",
        ]
    )

    return "\n".join(lines)


def _collect_input_hashes(protocol_dir: Path) -> _ArtifactHashes:
    """Collect SHA-256 hashes of frozen input artifact files."""
    hashes: _ArtifactHashes = {}
    target_files = [
        "preregistration.json",
        "commit.txt",
        "frozen_semantic_declarations.json",
        "checksums.sha256",
    ] + [f"manifests/{cid}.json" for cid in _MANDATORY]

    for rel in target_files:
        path = protocol_dir / rel
        if path.exists():
            hashes[rel] = _sha256_file(path)
    return hashes


# ── Main runner ────────────────────────────────────────────────────────────────


def run_development_comparison(
    protocol_dir: Path,
    output_dir: Path,
    config: Phase5Config | None = None,
    source_commit: str | None = None,
    skip_preflight: bool = False,
) -> DevelopmentResultV1:
    """Run the Phase V-B development comparison and write canonical artifacts.

    Parameters
    ----------
    protocol_dir:
        Path to the frozen protocol directory.
    output_dir:
        Output directory for artifacts (will be created; must not be inside
        historical artifact directories).
    config:
        Phase5Config to use.  If None, uses FROZEN_CONFIG (recommended).
    source_commit:
        40-hex source commit.  If None, determined from git HEAD.
    skip_preflight:
        For testing only.  If True, skips the preflight checks.

    Returns
    -------
    DevelopmentResultV1
        Validated canonical development result.

    Raises
    ------
    PreflightError
        If any preflight check fails.
    IntegrityError
        If post-run integrity checks fail.
    """
    resolved_config = config if config is not None else FROZEN_CONFIG
    if source_commit is None:
        source_commit = _get_source_commit()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Preflight
    if not skip_preflight:
        run_preflight(
            protocol_dir=protocol_dir,
            output_dir=output_dir,
            source_commit=source_commit,
        )

    # Run benchmark
    rows = build_phase5_trials(split_name="development", config=resolved_config)

    # Verify no forbidden splits were generated
    forbidden_splits = {
        "validation",
        "test",
        "selection-validation",
        "final-validation",
    }
    generated_splits = {row.split for row in rows}
    if forbidden_splits.intersection(generated_splits):
        raise IntegrityError(
            f"forbidden split(s) found in generated trials: "
            f"{forbidden_splits.intersection(generated_splits)}"
        )

    # Post-run: verify all mandatory candidates present
    generated_policies = {row.policy for row in rows}
    missing_mandatory = [c for c in _MANDATORY if c not in generated_policies]
    integrity_notes: list[str] = []
    integrity_passed = True

    if missing_mandatory:
        integrity_passed = False
        integrity_notes.append(
            f"missing mandatory candidates in output: {missing_mandatory}"
        )

    # Verify trial counts
    # Each (case, reliability, cost_regime) combination is a unique trial_key.
    trial_keys = {row.trial_key for row in rows if row.policy == "qrtc"}
    expected_trial_keys = (
        resolved_config.development_family_trials
        * len(list(Phase5Family))
        * len(resolved_config.reliability_levels)
        * len(resolved_config.cost_regimes)
    )
    if len(trial_keys) != expected_trial_keys:
        integrity_notes.append(
            f"trial key count {len(trial_keys)} != expected {expected_trial_keys}"
        )

    # Compute metrics
    metrics = _compute_all_metrics(rows)
    comparisons = _compute_bootstrap_comparisons(rows, resolved_config)

    # Collect input hashes
    input_hashes = _collect_input_hashes(protocol_dir)
    protocol_hash = compute_protocol_hashes().protocol_declaration_sha256

    # Build trial manifest
    manifest = _build_split_manifest("development")

    # Write artifacts
    output_dir.mkdir(parents=True, exist_ok=True)

    # Trials CSV
    trials_csv = output_dir / "phase5_runs.csv"
    with trials_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(Phase5TrialRow.__annotations__.keys())
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(_asdict(row))

    # Manifest
    manifest_path = output_dir / "development_manifest.json"
    _write_json(manifest_path, manifest)

    # Candidate metrics JSON
    metrics_json_path = output_dir / "candidate_metrics.json"
    _write_json(metrics_json_path, metrics)

    # Candidate metrics CSV
    metrics_csv_rows: list[dict[str, Any]] = []
    csv_fields = [
        "candidate",
        "trial_count",
        "mean_utility",
        "recovery_rate",
        "mean_intervention_cost",
        "mean_harm",
        "unsafe_commitment_rate",
        "evidence_request_rate",
        "oracle_regret",
    ]
    for cid, m in metrics.items():
        if not m.get("trial_count"):
            continue
        metrics_csv_rows.append({f: m.get(f, "") for f in csv_fields})
    metrics_csv_path = output_dir / "candidate_metrics.csv"
    _write_csv_file(metrics_csv_path, csv_fields, metrics_csv_rows)

    # Family metrics JSON
    family_metrics_payload: dict[str, Any] = {}
    for cid, m in metrics.items():
        if m.get("family_metrics"):
            family_metrics_payload[cid] = m["family_metrics"]
    family_metrics_path = output_dir / "family_metrics.json"
    _write_json(family_metrics_path, family_metrics_payload)

    # Paired comparisons JSON
    comparisons_path = output_dir / "paired_comparisons.json"
    _write_json(comparisons_path, comparisons)

    # Run manifest
    run_manifest = _build_run_manifest(
        source_commit=source_commit,
        protocol_hash=protocol_hash,
        input_hashes=input_hashes,
        trial_count=len(rows),
        config=resolved_config,
    )
    run_manifest_path = output_dir / "run_manifest.json"
    _write_json(run_manifest_path, run_manifest)

    # Build development result
    dev_result = DevelopmentResultV1(
        result_schema=DEVELOPMENT_RESULT_SCHEMA,
        protocol_id=PROTOCOL_ID,
        protocol_hash=protocol_hash,
        phase_revision=PHASE5_REVISION,
        stage="development",
        outcome=_DEVELOPMENT_OUTCOME,
        selected_id=None,
        authority="recommend_only",
        hardware_actuation_enabled=False,
        selection_validation_status="not_executed",
        final_validation_status="locked_not_executed",
        implementation_commit=IMPLEMENTATION_COMMIT,
        source_commit=source_commit,
        input_hashes=input_hashes,
        run_trial_count=len(rows),
        metrics_summary={
            cid: {k: v for k, v in m.items() if k != "family_metrics"}
            for cid, m in metrics.items()
        },
        bootstrap_comparisons=comparisons,
        integrity_all_passed=integrity_passed,
        integrity_notes=integrity_notes,
    )

    # Write development result JSON
    dev_result_path = output_dir / "development_result.json"
    dev_result_payload = json.loads(dev_result.canonical_bytes().decode("utf-8"))
    _write_json(dev_result_path, dev_result_payload)

    # Validate by round-trip
    validated = load_development_result(dev_result_payload)
    assert validated.outcome == _DEVELOPMENT_OUTCOME
    assert validated.selected_id is None
    assert validated.selection_validation_status == "not_executed"
    assert validated.final_validation_status == "locked_not_executed"

    # Markdown report
    report_md = _build_development_markdown_report(
        source_commit=source_commit,
        protocol_hash=protocol_hash,
        trial_count=len(rows),
        metrics=metrics,
        comparisons=comparisons,
        integrity_passed=integrity_passed,
        integrity_notes=integrity_notes,
    )
    report_path = output_dir / "DEVELOPMENT_REPORT.md"
    report_path.write_text(report_md, encoding="utf-8")

    # Checksums (canonical files only — relative paths)
    canonical_files: list[Path] = [
        dev_result_path,
        metrics_json_path,
        metrics_csv_path,
        family_metrics_path,
        comparisons_path,
        trials_csv,
        manifest_path,
        run_manifest_path,
    ]
    checksums_lines: list[str] = []
    for f in canonical_files:
        digest = _sha256_file(f)
        rel = f.relative_to(output_dir)
        checksums_lines.append(f"{digest}  {rel.as_posix()}")
    checksums_path = output_dir / "checksums.sha256"
    checksums_path.write_text("\n".join(checksums_lines) + "\n", encoding="utf-8")

    return dev_result


# ── Reproducibility verification ───────────────────────────────────────────────


def verify_reproducibility(
    run1_dir: Path,
    run2_dir: Path,
) -> tuple[bool, list[str]]:
    """Verify that two development runs produced byte-identical canonical artifacts.

    Returns
    -------
    (passed, differences)
        passed: True if all canonical files are byte-identical.
        differences: list of difference descriptions (empty if passed).
    """
    canonical_names = [
        "development_result.json",
        "candidate_metrics.json",
        "candidate_metrics.csv",
        "family_metrics.json",
        "paired_comparisons.json",
        "phase5_runs.csv",
        "development_manifest.json",
        "run_manifest.json",
    ]

    differences: list[str] = []

    for name in canonical_names:
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


# ── CLI ────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qrtc-benchmark-phase5b-dev",
        description=(
            "Phase V-B Stage 1: Development Comparison Runner\n\n"
            "Runs the authoritative Phase V-B development split benchmark.\n"
            "Does NOT run selection-validation or final-validation.\n"
            "Does NOT select a controller or declare a winner."
        ),
    )
    parser.add_argument(
        "--protocol-dir",
        required=True,
        help="Path to the frozen protocol directory (must contain preregistration.json).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for development artifacts.",
    )
    parser.add_argument(
        "--source-commit",
        default=None,
        help="40-hex source commit (default: HEAD).",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight checks (for testing only; not for formal runs).",
    )
    args = parser.parse_args(argv)

    protocol_dir = Path(args.protocol_dir)
    output_dir = Path(args.output_dir)

    print("Phase V-B Development Comparison")
    print(f"  Protocol: {PROTOCOL_ID}")
    print(f"  Protocol dir: {protocol_dir}")
    print(f"  Output dir: {output_dir}")
    print("  Split: development only")
    print()

    try:
        dev_result = run_development_comparison(
            protocol_dir=protocol_dir,
            output_dir=output_dir,
            source_commit=args.source_commit,
            skip_preflight=args.skip_preflight,
        )
    except PreflightError as exc:
        sys.stderr.write(f"PREFLIGHT FAILED:\n{exc}\n")
        return 2
    except IntegrityError as exc:
        sys.stderr.write(f"INTEGRITY ERROR:\n{exc}\n")
        return 3
    except Exception as exc:
        sys.stderr.write(f"UNEXPECTED ERROR: {exc}\n")
        raise

    print(f"Stage:    {dev_result.stage}")
    print(f"Outcome:  {dev_result.outcome}")
    print(f"Selected: {dev_result.selected_id!r} (null — no controller selected)")
    print(f"Trials:   {dev_result.run_trial_count}")
    print(f"Integrity all passed: {dev_result.integrity_all_passed}")
    if dev_result.integrity_notes:
        for note in dev_result.integrity_notes:
            print(f"  NOTE: {note}")
    print()
    print("Artifacts written to:", output_dir)
    print()
    print("AUTHORITATIVE STATEMENTS:")
    print("  - Development comparison only.  No controller selected.")
    print("  - Selection-validation: NOT EXECUTED")
    print("  - Final-validation: LOCKED AND NOT EXECUTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
