from __future__ import annotations

from pathlib import Path

from qrtc.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_release_candidate_flow(tmp_path: Path) -> None:
    db_path = tmp_path / "rc.sqlite3"

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
