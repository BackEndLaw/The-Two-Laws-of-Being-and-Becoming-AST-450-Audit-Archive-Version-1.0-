from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qrtc.config import load_input_document, load_policy_document
from qrtc.evidence_store import EvidenceStore
from qrtc.exceptions import (
    DeliveryError,
    EncodingError,
    EvidenceError,
    GuardError,
    IntegrityError,
    PolicyError,
    QRTCError,
    RealizationError,
    ResourceLimitError,
    StabilizationError,
)
from qrtc.kernel import Future, analyze_gate
from qrtc.pipeline import execute_configured_transit
from qrtc.policy import PolicyValidationError
from qrtc.registry import PolicyResolutionError, build_default_registry
from qrtc.replay import ReplayEngine, ReplayPolicy
from qrtc.transit import TransitFailureState

EXIT_CODES = {
    None: 0,
    TransitFailureState.REJECTED_BY_KEY: 3,
    TransitFailureState.REJECTED_BY_GUARD: 4,
    TransitFailureState.ENCODING_FAILED: 5,
    TransitFailureState.DELIVERY_FAILED: 6,
    TransitFailureState.DELIVERY_UNCERTAIN: 6,
    TransitFailureState.INTEGRITY_FAILED: 6,
    TransitFailureState.REALIZATION_FAILED: 7,
    TransitFailureState.STABILIZATION_FAILED: 8,
}
INTERNAL_ERROR_EXIT_CODE = 10


def _json_dump(value: object) -> None:
    print(json.dumps(value, indent=2, default=str))


def _field_accessor(field: str) -> Callable[[dict[str, Any]], Any]:
    return lambda state: state[field]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qrtc")
    parser.add_argument(
        "--dev-traceback",
        action="store_true",
        help="show traceback for unexpected internal errors",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    policy_parser = subparsers.add_parser("policy")
    policy_subparsers = policy_parser.add_subparsers(
        dest="policy_command", required=True
    )
    policy_validate = policy_subparsers.add_parser("validate")
    policy_validate.add_argument("policy")

    transit_parser = subparsers.add_parser("transit")
    transit_subparsers = transit_parser.add_subparsers(
        dest="transit_command", required=True
    )

    transit_run = transit_subparsers.add_parser("run")
    transit_run.add_argument("--policy", required=True)
    transit_run.add_argument("--input", required=True)
    transit_run.add_argument("--db", default="qrtc_evidence.sqlite3")

    transit_inspect = transit_subparsers.add_parser("inspect")
    transit_inspect.add_argument("transit_id")
    transit_inspect.add_argument("--db", default="qrtc_evidence.sqlite3")

    transit_replay = transit_subparsers.add_parser("replay")
    transit_replay.add_argument("transit_id")
    transit_replay.add_argument("--db", default="qrtc_evidence.sqlite3")

    adequacy_parser = subparsers.add_parser("adequacy")
    adequacy_subparsers = adequacy_parser.add_subparsers(
        dest="adequacy_command", required=True
    )
    adequacy_analyze = adequacy_subparsers.add_parser("analyze")
    adequacy_analyze.add_argument("--model", required=True)
    adequacy_analyze.add_argument("--gate", required=True)
    adequacy_analyze.add_argument("--future-family", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    registry = build_default_registry()

    try:
        if args.command == "policy" and args.policy_command == "validate":
            policy = load_policy_document(args.policy)
            _json_dump(policy.as_dict())
            return 0

        if args.command == "transit" and args.transit_command == "run":
            policy = load_policy_document(args.policy)
            input_record = load_input_document(args.input)
            configured, outcome = execute_configured_transit(
                policy, input_record, registry
            )
            store = EvidenceStore(args.db)
            store.record_transit(
                policy,
                input_record,
                configured.request,
                outcome,
                policy_hash=configured.policy_digest,
                registry_snapshot_id=configured.registry_snapshot_id,
                resolved_components=configured.resolved_component_ids,
            )
            _json_dump(outcome.as_dict())
            return EXIT_CODES.get(outcome.failure_state, 0)

        if args.command == "transit" and args.transit_command == "inspect":
            store = EvidenceStore(args.db)
            _json_dump(store.inspect(args.transit_id))
            return 0

        if args.command == "transit" and args.transit_command == "replay":
            store = EvidenceStore(args.db)
            replay_report = ReplayEngine(store, registry).replay(
                args.transit_id, policy=ReplayPolicy()
            )
            _json_dump(replay_report.as_dict())
            return 0

        if args.command == "adequacy" and args.adequacy_command == "analyze":
            with Path(args.model).open("r", encoding="utf-8") as file_handle:
                model = json.load(file_handle)

            states = model.get("states", [])
            gate_field = model.get("gate_field")
            future_fields = model.get("future_fields", [])
            typed_states = [dict(state) for state in states if isinstance(state, dict)]
            futures = tuple(
                Future(name=name, function=_field_accessor(field))
                for name, field in future_fields
            )
            adequacy_report = analyze_gate(
                typed_states,
                futures,
                gate=_field_accessor(gate_field),
            )
            _json_dump(
                {
                    "gate": args.gate,
                    "future_family": args.future_family,
                    **adequacy_report.as_dict(),
                }
            )
            return 0

    except (
        PolicyValidationError,
        PolicyResolutionError,
        PolicyError,
        ResourceLimitError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    except EncodingError as error:
        print(str(error), file=sys.stderr)
        return 5
    except (DeliveryError, IntegrityError) as error:
        print(str(error), file=sys.stderr)
        return 6
    except RealizationError as error:
        print(str(error), file=sys.stderr)
        return 7
    except StabilizationError as error:
        print(str(error), file=sys.stderr)
        return 8
    except (GuardError, EvidenceError, QRTCError) as error:
        print(str(error), file=sys.stderr)
        return 9
    except Exception as error:
        if args.dev_traceback:
            raise
        print(f"internal error: {error}", file=sys.stderr)
        return INTERNAL_ERROR_EXIT_CODE

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
