---
description: Open/sync SDP tickets from an existing findings file (no rescan)
argument-hint: <findings.jsonl> [min-severity]
---
Using the `gizmoduck` skill, run `gizmoduck.py tickets $1 --min-severity ${2:-high}` and
auto-create one ServiceDesk Plus ticket per finding, skipping any with an open
`[Nuclei <template-id>]` ticket (add a note instead). Print a created-vs-updated summary.
