---
description: Show what's new since a previous scan (regression / deploy check)
argument-hint: <baseline.jsonl> <current.jsonl> [min-severity]
---
Using the `gizmoduck` skill, run `gizmoduck.py diff $1 $2 --min-severity ${3:-low}` and present the
new-vs-resolved findings. Offer to open tickets for any NEW Critical/High findings.
