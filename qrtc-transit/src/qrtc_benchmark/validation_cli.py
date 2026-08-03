# Phase V-B dry-run execution guard CLI.
#
# Provides future-facing validation API/CLI for the phase5b-selection-v1 protocol.
#
# For this PR (preregistered_not_executed) the CLI:
#   - validates protocol path/hash, implementation commit, stage, mandatory artifacts
#   - performs dry-run only — does NOT call real benchmark generation
#   - rejects final-validation unconditionally with a typed locked-stage error
#   - requires an explicit (unused) output directory
#
# Usage:
#   qrtc-selection validate \
#       --protocol-dir <path> \
#       --stage development|selection-validation \
#       --implementation-commit <40-hex> \
#       --output-dir <path>
#
#   qrtc-selection --help
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qrtc_benchmark.selection_protocol import (
    IMPLEMENTATION_COMMIT,
    MANDATORY_CANDIDATES,
    PROTOCOL_ID,
    compute_protocol_hashes,
)

# ── Typed errors ───────────────────────────────────────────────────────────────


class LockedStageError(RuntimeError):
    """Raised when final-validation execution is requested.  Always rejected."""


class ProtocolValidationError(ValueError):
    """Raised when the protocol directory or its artifacts fail validation."""


class IncompleteArtifactsError(ValueError):
    """Raised when mandatory candidate artifacts are missing."""


# ── Stage constants ────────────────────────────────────────────────────────────

_ALLOWED_STAGES: frozenset[str] = frozenset({"development", "selection-validation"})
_LOCKED_STAGE: str = "final-validation"


# ── Validation result ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationReport:
    protocol_id: str
    protocol_hash: str
    stage: str
    implementation_commit: str
    mandatory_artifacts_found: list[str]
    mandatory_artifacts_missing: list[str]
    dry_run_only: bool
    status: str  # "ok" | "error"
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "protocol_hash": self.protocol_hash,
            "stage": self.stage,
            "implementation_commit": self.implementation_commit,
            "mandatory_artifacts_found": list(self.mandatory_artifacts_found),
            "mandatory_artifacts_missing": list(self.mandatory_artifacts_missing),
            "dry_run_only": self.dry_run_only,
            "status": self.status,
            "errors": list(self.errors),
        }


# ── Protocol directory validator ───────────────────────────────────────────────


def _expected_artifact_name(controller_id: str) -> str:
    return f"{controller_id}.json"


def validate_protocol_directory(
    protocol_dir: Path,
    stage: str,
    implementation_commit: str,
    *,
    expected_protocol_id: str = PROTOCOL_ID,
    expected_protocol_hash: str | None = None,
    output_dir: Path | None = None,
) -> ValidationReport:
    """Validate a protocol directory for the given stage.

    Checks:
    1. ``preregistration.json`` exists and contains matching protocol_id and hash.
    2. All mandatory candidate artifacts exist under ``manifests/<controller_id>.json``.
    3. ``commit.txt`` matches implementation_commit.
    4. Stage is not final-validation (locked).
    5. Protocol hash matches canonical computed hash.

    Raises
    ------
    LockedStageError
        If stage is "final-validation" (unconditional rejection).
    ProtocolValidationError
        If preregistration.json is missing or invalid.
    """
    if stage == _LOCKED_STAGE:
        raise LockedStageError(
            f"stage {_LOCKED_STAGE!r} is permanently locked and cannot be executed in this PR. "
            "Final-validation definitions are declared and hashed but no rows may be generated."
        )

    errors: list[str] = []

    # Check protocol preregistration file.
    prereg_path = protocol_dir / "preregistration.json"
    if not prereg_path.exists():
        raise ProtocolValidationError(
            f"preregistration.json not found in {protocol_dir}"
        )

    try:
        prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProtocolValidationError(
            f"failed to parse preregistration.json: {exc}"
        ) from exc

    if prereg.get("protocol_id") != expected_protocol_id:
        errors.append(
            f"protocol_id mismatch: got {prereg.get('protocol_id')!r}, "
            f"expected {expected_protocol_id!r}"
        )

    # Verify protocol hash.
    expected_hash = compute_protocol_hashes().protocol_declaration_sha256
    if expected_protocol_hash is not None and expected_protocol_hash != expected_hash:
        errors.append(
            f"requested protocol_hash mismatch: got {expected_protocol_hash!r}, "
            f"computed {expected_hash!r}"
        )
    recorded_hash = prereg.get("protocol_hash", "")
    if recorded_hash != expected_hash:
        errors.append(
            f"protocol_hash mismatch: recorded {recorded_hash!r}, "
            f"computed {expected_hash!r}"
        )

    # Check implementation commit in commit.txt if present.
    commit_path = protocol_dir / "commit.txt"
    if commit_path.exists():
        recorded_commit = commit_path.read_text(encoding="utf-8").strip()
        if recorded_commit != implementation_commit:
            errors.append(
                f"commit.txt mismatch: recorded {recorded_commit!r}, "
                f"expected {implementation_commit!r}"
            )

    # Check mandatory candidate artifacts.
    manifests_dir = protocol_dir / "manifests"
    found: list[str] = []
    missing: list[str] = []
    for cid in MANDATORY_CANDIDATES:
        artifact_path = manifests_dir / _expected_artifact_name(cid)
        if artifact_path.exists():
            found.append(cid)
        else:
            missing.append(cid)
            errors.append(f"mandatory artifact missing: manifests/{cid}.json")

    if output_dir is not None:
        if output_dir.exists() and not output_dir.is_dir():
            errors.append(f"output_dir is not a directory: {output_dir}")
        elif output_dir.exists() and any(output_dir.iterdir()):
            errors.append(f"output_dir must be unused and empty: {output_dir}")

    status = "ok" if not errors else "error"
    return ValidationReport(
        protocol_id=expected_protocol_id,
        protocol_hash=expected_hash,
        stage=stage,
        implementation_commit=implementation_commit,
        mandatory_artifacts_found=found,
        mandatory_artifacts_missing=missing,
        dry_run_only=True,
        status=status,
        errors=errors,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qrtc-selection",
        description=(
            "Phase V-B Selection Protocol v1 — dry-run validation guard.\n\n"
            "For preregistered_not_executed PRs this command validates only.\n"
            "It never calls benchmark generation and rejects final-validation unconditionally."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate",
        help=(
            "Validate protocol directory, hashes, mandatory artifacts, and stage. "
            "Dry-run only — does not generate any experiment data."
        ),
    )
    validate_parser.add_argument(
        "--protocol-dir",
        required=True,
        help="Path to the protocol directory (must contain preregistration.json).",
    )
    validate_parser.add_argument(
        "--stage",
        required=True,
        choices=sorted(_ALLOWED_STAGES),
        help="Stage to validate (development or selection-validation).",
    )
    validate_parser.add_argument(
        "--implementation-commit",
        default=IMPLEMENTATION_COMMIT,
        help="40-hex implementation commit to verify against commit.txt.",
    )
    validate_parser.add_argument(
        "--protocol-hash",
        default=None,
        help="Exact protocol hash expected for the frozen preregistration.",
    )
    validate_parser.add_argument(
        "--output-dir",
        required=True,
        help="Unused output directory path to validate fail-closed preflight behavior.",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Print validation report as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            report = validate_protocol_directory(
                protocol_dir=Path(args.protocol_dir),
                stage=args.stage,
                implementation_commit=args.implementation_commit,
                expected_protocol_hash=args.protocol_hash,
                output_dir=Path(args.output_dir),
            )
        except LockedStageError as exc:
            sys.stderr.write(f"LOCKED STAGE ERROR: {exc}\n")
            return 3
        except ProtocolValidationError as exc:
            sys.stderr.write(f"PROTOCOL ERROR: {exc}\n")
            return 2

        if args.output_json:
            print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        else:
            print(f"protocol_id: {report.protocol_id}")
            print(f"protocol_hash: {report.protocol_hash}")
            print(f"stage: {report.stage}")
            print(f"implementation_commit: {report.implementation_commit}")
            print(f"dry_run_only: {report.dry_run_only}")
            if report.mandatory_artifacts_found:
                print(f"artifacts_found: {', '.join(report.mandatory_artifacts_found)}")
            if report.mandatory_artifacts_missing:
                print(
                    f"artifacts_missing: {', '.join(report.mandatory_artifacts_missing)}"
                )
            if report.errors:
                for error in report.errors:
                    sys.stderr.write(f"  ERROR: {error}\n")

        if report.status == "ok":
            if not args.output_json:
                print("status: ok (dry-run validation passed)")
            return 0
        else:
            sys.stderr.write(f"status: error ({len(report.errors)} issue(s) found)\n")
            return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
