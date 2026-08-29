---
description: Regenerate a report from an existing findings file (no rescan)
argument-hint: <findings.jsonl> [min-severity]
---
Using the `gizmoduck` skill, regenerate the report from `$1` at severity `$2` (default: high) —
inline Markdown plus HTML and PDF files. Do not rescan; do not open tickets unless asked.
