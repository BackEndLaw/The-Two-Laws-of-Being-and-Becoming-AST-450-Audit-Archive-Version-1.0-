# Paradox Database Template

This folder contains a ready-to-use catalog template for paradox analysis in the Generative Remainder / Door-Gate workflow.

## Files

- paradox_template.csv: seed dataset with 26 example paradox entries.
- paradox_template_schema.json: JSON schema for validation of object-form records.
- create_paradox_template.py: script that generates blank/seed CSV and JSONL files.

## Controlled Vocabularies

- gate_type: Door, Gate
- output_class: preserved, transformed, split, null, extinct, proxy-substituted
- root_cause: extension_error, construction_error, mixed
- fix_type: hierarchy, retype, rebuild, enlarge_arena, construct_boat, paraconsistent, probabilistic, other

## Quick Start

1. Edit paradox_template.csv to add or revise rows.
2. Run create_paradox_template.py to emit machine-friendly outputs.
3. Validate JSON records against paradox_template_schema.json in your preferred validator.

## Notes on Normalization

- CSV stores multi-valued fields using pipe separators (for example, domain, tags, evidence_refs).
- The Python script converts these to arrays in JSONL output.
- Confidence is a numeric score in [0,1].
