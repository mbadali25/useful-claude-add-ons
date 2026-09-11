---
description: Run the scanner suite on a target, then report + confirm-then-open SDP tickets
argument-hint: <url-host-or-targets-file> [min-severity]
---
**Pass `--source <dir>` whenever the target's source tree is available.** `scan` runs
five tools — nuclei and sslyze against the endpoint, and trivy (dependency CVEs,
committed secrets, IaC) plus semgrep (source analysis) against `--source`. Without it
those three report as `skipped` and the scan covers the edge only. Nuclei alone on an
authenticated app behind a WAF returns almost nothing but Info-severity fingerprinting,
so a quiet report from an endpoint-only scan is close to the expected result rather than
a clean bill of health. `--with-zap` adds crawler-driven DAST; `--with-checkov` adds IaC
breadth whose findings land at Low because Checkov OSS emits no severity. All tools merge
into the same `findings.jsonl` and the same report. If any tool reports `missing` or
`failed`, say so when presenting results — the scan is incomplete, not clean.

Scan `$1` with the `gizmoduck` skill: run the scan (default `--severity critical,high,medium`,
writing `findings.jsonl`), show the summary, produce a report at severity `$2` (default: high) as
inline Markdown plus HTML and PDF, then run `gizmoduck.py tickets findings.jsonl --min-severity
${2:-high}` (no `--yes`) to get the candidate list. Without `--yes`, the command prints the
candidate list, a digest over that exact batch, and the rerun command carrying it — search
ServiceDesk Plus for each `[Nuclei <template-id>]` tag to split it into create-vs-add-a-note, and
show the user the full batch (severity + subject per line, plus that split) **and the exact
rerun command the preview printed**, so there is nothing to retype. Get one explicit go-ahead
for the whole batch before creating anything — do not prompt per ticket. Only then run that
exact printed command — `gizmoduck.py tickets findings.jsonl --min-severity ${2:-high} --yes
<digest-from-the-preview>` — and act on the records (create, or add a note to an existing open
ticket). The digest binds the rerun to the exact batch shown: a `--yes` value that does not
match what `tickets` recomputes right now — a different findings file, a different
`--min-severity`, findings that changed in between — is refused (`GIZMODUCK_APPROVAL_MISMATCH`),
never silently widened. Never edit the findings file or `--min-severity` on the rerun; if the
batch needs to change, get a fresh preview and a fresh digest, and confirm again. Print a
created-vs-updated summary.

Producing the report: this scan may be discharging a crew endpoint-ledger obligation.
Follow the `--out` convention documented in `commands/report.md` — check
`.crew/endpoints.json` (when crew is installed) for a declared record whose `endpoint`
matches `$1`, and if one matches, land the report at that record's computed path and
freeze it there afterward (`--record-scan-artifact`), instead of an arbitrary default
location. Do not skip the freeze — `commands/report.md` explains why it is silent if you
do, and how it is now detectable (`endpoints.unfrozen`) rather than only discoverable
after the fact. The report's own `**Total finding instances:**` line is the marker
`crew_state.py` requires as proof this file is a real scan, not a placeholder or a note
that merely mentions the target — see `commands/report.md`'s scan-artifact contract.
