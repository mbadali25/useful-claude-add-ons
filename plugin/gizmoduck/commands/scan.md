---
description: Run a Nuclei scan on a target, then report and offer to open SDP tickets
argument-hint: <url-host-or-targets-file> [min-severity]
---
Scan `$1` with the `gizmoduck` skill: run the scan (default `--severity critical,high,medium`),
show the summary, then produce a report at severity `$2` (default: high) as inline Markdown plus
HTML and PDF.

Then run `gizmoduck.py tickets <findings> --min-severity high` **without** `--create` and show the
resulting list - the findings that would become tickets. Ask whether to open them. This command
does not file anything on its own; a scan the user asked for is not consent to write to a
ticketing system on their behalf.

The ticket floor is `high` and does not follow `$2`. `$2` sets the *report* severity, and a user
who widens the report to `medium` to read about Mediums has not asked to open a ticket for each
one. Passing `${2:-high}` here would tie the two together and let a report-widening flag quietly
widen the write.

On an explicit yes, follow `/gizmoduck:tickets` from its `--create` step: re-run with `--create`,
skip any finding that already has an open `[Nuclei <template-id>]` request (add a note instead),
and print a created-vs-updated summary.
