from __future__ import annotations

import argparse
from pathlib import Path

from qrtc_benchmark.controller_artifact import (
    DEFAULT_PROTOCOL_ID,
    freeze_controller_artifact,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qrtc-controller",
        description="Freeze and validate Phase V-B controller artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    freeze_parser = subparsers.add_parser(
        "freeze",
        help="Freeze a controller artifact using canonical rescueos-controller-v1 JSON.",
    )
    freeze_parser.add_argument("--controller", required=True)
    freeze_parser.add_argument("--implementation-commit", required=True)
    freeze_parser.add_argument("--protocol-id", default=DEFAULT_PROTOCOL_ID)
    freeze_parser.add_argument("--output", required=True)
    freeze_parser.add_argument("--overwrite", action="store_true")
    freeze_parser.add_argument(
        "--deployable-only",
        action="store_true",
        help="Reject non-deployable controllers such as oracle.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "freeze":
        freeze_controller_artifact(
            controller_id=args.controller,
            implementation_commit=args.implementation_commit,
            protocol_id=args.protocol_id,
            output_path=Path(args.output),
            overwrite=args.overwrite,
            deployable_only=args.deployable_only,
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
