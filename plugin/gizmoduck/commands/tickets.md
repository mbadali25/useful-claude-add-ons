---
description: Confirm batch, then open/sync SDP tickets from an existing findings file (no rescan)
argument-hint: <findings.jsonl> [min-severity]
---
Using the `gizmoduck` skill, run `gizmoduck.py tickets $1 --min-severity ${2:-high}` (no
`--yes`) to get the candidate list. Without `--yes`, this prints the candidate list, a digest
over that exact batch, and the rerun command carrying it. Search ServiceDesk Plus for each
`[Nuclei <template-id>]` tag to split it into create-vs-add-a-note, and show the user the full
batch (severity + subject per line, plus that split) **and the exact rerun command the preview
printed**, so there is nothing to retype. Get one explicit go-ahead for the whole batch before
creating anything — do not prompt per ticket. Only then run that exact printed command —
`gizmoduck.py tickets $1 --min-severity ${2:-high} --yes <digest-from-the-preview>` — and act on
the records (create, or add a note to an existing open ticket instead). The digest binds the
rerun to the exact batch shown: a `--yes` value that does not match what `tickets` recomputes
right now — a different `$1`, a different `--min-severity`, findings that changed in between —
is refused (`GIZMODUCK_APPROVAL_MISMATCH`), never silently widened. Never edit `$1` or
`--min-severity` on the rerun; if the batch needs to change, get a fresh preview and a fresh
digest, and confirm again. Print a created-vs-updated summary.
