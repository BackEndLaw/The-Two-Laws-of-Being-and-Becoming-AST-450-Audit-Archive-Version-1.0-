from __future__ import annotations

import json
from pathlib import Path

import pytest

from qrtc.config import load_input_document
from qrtc.exceptions import ResourceLimitError
from qrtc.policy import load_policy_document


def test_malformed_policy_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "malicious.json"
    path.write_text("import os\nos.system('echo unsafe')\n", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_policy_document(path)


def test_oversized_input_fails_with_resource_limit(tmp_path: Path) -> None:
    big_string = "x" * 300_000
    path = tmp_path / "big-input.json"
    path.write_text(
        json.dumps(
            {
                "transit_id": "t-oversize",
                "principal": "authorized-operator",
                "destination": "alarm-record",
                "expiration": "2099-01-01T00:00:00+00:00",
                "interface_projection": {"payload": big_string},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ResourceLimitError):
        load_input_document(path)
