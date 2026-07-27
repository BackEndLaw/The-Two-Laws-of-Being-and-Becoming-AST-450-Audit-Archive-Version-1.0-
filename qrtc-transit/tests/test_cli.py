from __future__ import annotations

import json
from pathlib import Path

from qrtc.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_cli_policy_validate_and_transit_run_and_inspect(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite3"

    assert main(["policy", "validate", str(EXAMPLES / "telemetry-policy.json")]) == 0
    assert (
        main(
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
        == 0
    )

    assert main(["transit", "inspect", "telemetry-001", "--db", str(db_path)]) == 0
    assert main(["transit", "replay", "telemetry-001", "--db", str(db_path)]) == 0


def test_cli_exit_codes_identify_key_and_guard_rejections(tmp_path: Path) -> None:
    db_path = tmp_path / "evidence.sqlite3"

    bad_key_input = tmp_path / "bad-key-input.json"
    bad_key_input.write_text(
        json.dumps(
            {
                "transit_id": "telemetry-002",
                "principal": "unauthorized-operator",
                "destination": "alarm-record",
                "expiration": "2099-01-01T00:00:00+00:00",
                "interface_projection": {
                    "temperature": 72,
                    "pressure": 110,
                },
            }
        ),
        encoding="utf-8",
    )

    guard_input = tmp_path / "guard-input.json"
    guard_input.write_text(
        json.dumps(
            {
                "transit_id": "telemetry-003",
                "principal": "authorized-operator",
                "destination": "alarm-record",
                "expiration": "2099-01-01T00:00:00+00:00",
                "interface_projection": {
                    "temperature": 72,
                },
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "transit",
                "run",
                "--policy",
                str(EXAMPLES / "telemetry-policy.json"),
                "--input",
                str(bad_key_input),
                "--db",
                str(db_path),
            ]
        )
        == 3
    )

    assert (
        main(
            [
                "transit",
                "run",
                "--policy",
                str(EXAMPLES / "telemetry-policy.json"),
                "--input",
                str(guard_input),
                "--db",
                str(db_path),
            ]
        )
        == 4
    )


def test_cli_invalid_policy_returns_invocation_error(tmp_path: Path) -> None:
    malformed_policy = tmp_path / "malformed-policy.json"
    malformed_policy.write_text(
        "import os\nos.system('echo unsafe')\n", encoding="utf-8"
    )

    assert main(["policy", "validate", str(malformed_policy)]) == 2
