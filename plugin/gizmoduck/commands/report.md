---
description: Regenerate a report from an existing findings file (no rescan)
argument-hint: <findings.jsonl> [min-severity]
---
Using the `gizmoduck` skill, regenerate the report from `$1` — inline Markdown plus HTML
and PDF files. Do not rescan; do not open tickets unless asked.

Reports itemise Critical, High and Medium and report Low/Info as counts only. `$2`, if
given, can raise that floor (`high` reports High and Critical) but cannot lower it.
