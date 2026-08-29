---
description: Run a Nuclei scan on a target, then report + auto-open SDP tickets
argument-hint: <url-host-or-targets-file> [min-severity]
---
Scan `$1` with the `gizmoduck` skill: run the scan (default `--severity critical,high,medium`),
show the summary, produce a report at severity `$2` (default: high) as inline Markdown plus HTML
and PDF, then auto-create one ServiceDesk Plus ticket per Critical/High finding (skipping any with
an open `[Nuclei <template-id>]` ticket) and print a created-vs-updated summary.
