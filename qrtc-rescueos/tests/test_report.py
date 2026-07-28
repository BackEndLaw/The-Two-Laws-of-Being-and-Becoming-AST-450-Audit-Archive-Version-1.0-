from __future__ import annotations

import json

from rescueos import RESULT_NAME
from rescueos.experiments.report import generate_report, render_gate_report


def _payload(*, passed: bool) -> dict:
    return {
        "config": {
            "fault_bank_path": "configs/fault_bank_locked.yaml",
            "max_faults": 1,
            "runs_per_k": 2,
            "max_actions": 4,
            "seed": 11,
            "acceptance_targets": {
                "min_delta_vs_nonoracle": 0.0,
                "max_harm_rate": 0.05,
                "max_unsafe_rate": 0.05,
                "max_unsafe_unknown_rate": 0.05,
                "require_strict_unknown_superiority": True,
            },
        },
        "acceptance": {
            "all_k_pass": passed,
            "by_k": [
                {
                    "k_faults": 1,
                    "strongest_nonoracle": "qrtc_untyped",
                    "delta_u_vs_nonoracle": 0.1 if passed else -0.1,
                    "qrtc_harm_rate": 0.0,
                    "qrtc_unsafe_rate": 0.0,
                    "qrtc_unsafe_unknown_rate": 0.0,
                    "strongest_nonoracle_unsafe_unknown_rate": 0.1,
                    "pass_delta": passed,
                    "pass_harm": True,
                    "pass_unsafe": True,
                    "pass_unsafe_unknown_threshold": True,
                    "pass_unsafe_unknown_superiority": True,
                    "pass_all": passed,
                }
            ],
        },
    }


def test_render_gate_report_preserves_literal_failure() -> None:
    report = render_gate_report(_payload(passed=False))

    assert report.startswith(f"# {RESULT_NAME} - Phase VI Gate Decision Report")
    assert "**Overall composite gate: FAIL.**" in report
    assert "failing k values: 1" in report
    assert "| 1 | qrtc_untyped | -0.100000" in report


def test_generate_report_writes_markdown(tmp_path) -> None:
    input_path = tmp_path / "summary.json"
    output_path = tmp_path / "PHASE_VI_GATE_REPORT.md"
    input_path.write_text(json.dumps(_payload(passed=True)), encoding="utf-8")

    generated = generate_report(input_path, output_path)

    assert generated == output_path
    assert "**Overall composite gate: PASS.**" in output_path.read_text(encoding="utf-8")
