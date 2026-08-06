from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rescueos import RESULT_NAME


def render_gate_report(payload: dict[str, Any]) -> str:
    config = payload.get("config", {})
    result_name = config.get("result_name", RESULT_NAME)
    acceptance = payload.get("acceptance", {})
    rows = acceptance.get("by_k", [])
    targets = config.get("acceptance_targets", {})

    lines = [
        f"# {result_name} - Phase VI Gate Decision Report",
        "",
        "## Locked configuration",
        "",
        f"- Fault bank: `{config.get('fault_bank_path') or 'synthetic scenarios'}`",
        f"- Maximum faults: `{config.get('max_faults', 'unknown')}`",
        f"- Runs per k: `{config.get('runs_per_k', 'unknown')}`",
        f"- Maximum actions: `{config.get('max_actions', 'unknown')}`",
        f"- Seed: `{config.get('seed', 'unknown')}`",
        f"- Minimum utility delta: `{_format_number(targets.get('min_delta_vs_nonoracle'))}`",
        f"- Maximum harm rate: `{_format_number(targets.get('max_harm_rate'))}`",
        f"- Maximum unsafe rate: `{_format_number(targets.get('max_unsafe_rate'))}`",
        f"- Maximum unknown-fault unsafe rate: `{_format_number(targets.get('max_unsafe_unknown_rate'))}`",
        f"- Strict unknown-fault superiority: `{bool(targets.get('require_strict_unknown_superiority', False))}`",
        f"- Acceptance comparator: `{targets.get('baseline_policy') or 'strongest non-oracle by utility'}`",
        "",
        "## Gate decisions",
        "",
        "| k | Acceptance comparator | Delta U | QRTC harm | QRTC unsafe | QRTC unsafe unknown | Baseline unsafe unknown | Utility | Harm | Unsafe | Unknown threshold | Unknown superiority | Composite |",
        "|---:|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for row in rows:
        lines.append(
            "| {k} | {baseline} | {delta} | {harm} | {unsafe} | {unknown} | "
            "{baseline_unknown} | {pass_delta} | {pass_harm} | {pass_unsafe} | "
            "{pass_unknown} | {pass_superiority} | {pass_all} |".format(
                k=row.get("k_faults", ""),
                baseline=row.get("strongest_nonoracle", ""),
                delta=_format_number(row.get("delta_u_vs_nonoracle")),
                harm=_format_number(row.get("qrtc_harm_rate")),
                unsafe=_format_number(row.get("qrtc_unsafe_rate")),
                unknown=_format_number(row.get("qrtc_unsafe_unknown_rate")),
                baseline_unknown=_format_number(
                    row.get("strongest_nonoracle_unsafe_unknown_rate")
                ),
                pass_delta=_decision(row.get("pass_delta")),
                pass_harm=_decision(row.get("pass_harm")),
                pass_unsafe=_decision(row.get("pass_unsafe")),
                pass_unknown=_decision(row.get("pass_unsafe_unknown_threshold")),
                pass_superiority=_decision(row.get("pass_unsafe_unknown_superiority")),
                pass_all=_decision(row.get("pass_all")),
            )
        )

    overall_pass = bool(acceptance.get("all_k_pass", False))
    lines.extend(
        [
            "",
            "## Formal decision",
            "",
            f"**Overall composite gate: {_decision(overall_pass)}.**",
            "",
            _decision_statement(overall_pass, rows),
            "",
            "This report is descriptive of the supplied locked benchmark output. It does not replace the preregistered protocol or establish physical-system performance.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_report(input_path: str | Path, output_path: str | Path) -> Path:
    input_file = Path(input_path)
    output_file = Path(output_path)
    with input_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(render_gate_report(payload), encoding="utf-8")
    return output_file


def _format_number(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6f}"


def _decision(value: Any) -> str:
    return "PASS" if bool(value) else "FAIL"


def _decision_statement(overall_pass: bool, rows: list[dict[str, Any]]) -> str:
    if overall_pass:
        return "All evaluated k-specific utility and safety conditions passed literally."

    failed_k = [str(row.get("k_faults")) for row in rows if not row.get("pass_all")]
    if failed_k:
        return "The composite gate did not pass literally; failing k values: " + ", ".join(failed_k) + "."
    return "The composite gate did not pass literally."


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Render a {RESULT_NAME} Phase VI gate report from benchmark summary JSON"
    )
    parser.add_argument(
        "--input",
        default="artifacts/benchmark_runs/summary.json",
        help="Benchmark summary JSON path",
    )
    parser.add_argument(
        "--output",
        default="artifacts/benchmark_runs/PHASE_VI_GATE_REPORT.md",
        help="Markdown report output path",
    )
    args = parser.parse_args()

    output = generate_report(args.input, args.output)
    print(output)


if __name__ == "__main__":
    main()
