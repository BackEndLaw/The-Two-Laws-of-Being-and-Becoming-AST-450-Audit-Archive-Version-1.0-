#!/usr/bin/env python3
"""
Create paradox database templates and seed files.

Outputs:
- paradox_template_blank.csv
- paradox_template_seed.csv
- paradox_template_seed.jsonl
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


COLUMNS = [
    "id",
    "name",
    "domain",
    "predicate",
    "j1_origin",
    "j2_extension",
    "p_remainder",
    "gate_operator",
    "gate_type",
    "admissibility_change",
    "output_class",
    "root_cause",
    "suggested_fix",
    "fix_type",
    "boat_candidate",
    "measurables",
    "evidence_refs",
    "confidence",
    "notes",
    "created_by",
    "created_at",
    "updated_at",
    "tags",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_blank_csv(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()


def write_seed_csv(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in records:
            writer.writerow(row)


def write_seed_jsonl(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in records:
            obj = dict(row)
            obj["domain"] = [d for d in row["domain"].split("|") if d]
            obj["evidence_refs"] = [r for r in row["evidence_refs"].split("|") if r]
            obj["tags"] = [t for t in row["tags"].split("|") if t]
            if row["confidence"]:
                obj["confidence"] = float(row["confidence"])
            f.write(json.dumps(obj, ensure_ascii=True) + "\n")


def main() -> None:
    here = Path(__file__).resolve().parent
    source_csv = here / "paradox_template.csv"
    blank_csv = here / "paradox_template_blank.csv"
    seed_csv = here / "paradox_template_seed.csv"
    seed_jsonl = here / "paradox_template_seed.jsonl"

    now = _now_iso()
    records: list[dict[str, str]] = []

    with source_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec = {k: (row.get(k, "") or "") for k in COLUMNS}
            rec["created_at"] = rec["created_at"] or now
            rec["updated_at"] = rec["updated_at"] or now
            records.append(rec)

    write_blank_csv(blank_csv)
    write_seed_csv(seed_csv, records)
    write_seed_jsonl(seed_jsonl, records)

    print(f"Wrote {blank_csv.name}, {seed_csv.name}, and {seed_jsonl.name}")


if __name__ == "__main__":
    main()
