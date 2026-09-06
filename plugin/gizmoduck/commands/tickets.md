---
description: Preview SDP tickets from an existing findings file, and open them once confirmed
argument-hint: <findings.jsonl> [min-severity]
---
Using the `gizmoduck` skill, run `gizmoduck.py tickets $1 --min-severity ${2:-high}`.

That is the **preview** run and it is the one you always do first. Its output carries
no ticket bodies, so nothing in it can be filed - show the subjects and severities to
the user and ask, in one question, whether to open them.

Only after an explicit yes, re-run the same command with `--create` and then, for each
record, search ServiceDesk Plus for an open request whose subject contains the same
`[Nuclei <template-id>]` tag: add a note if one exists, create the request if none
does. Print a created-vs-updated summary.

A "no" ends the command. Do not open a subset, and do not offer to open the Criticals
"just in case" - the user was asked and answered.
