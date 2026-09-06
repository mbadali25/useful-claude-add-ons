---
description: Regenerate a report from an existing findings file (no rescan)
argument-hint: <findings.jsonl> [min-severity]
---
Using the `gizmoduck` skill, regenerate the report from `$1` — inline Markdown plus HTML
and PDF files. Do not rescan; do not open tickets unless asked.

Reports itemise Critical, High and Medium and report Low/Info as counts only. `$2`, if
given, can raise that floor (`high` reports High and Critical) but cannot lower it.

**Scan-artifact contract:** every report this command produces opens with the two lines
`cmd_report` always writes — `**Hosts with findings:**` and `**Total finding instances:**
<N>` — before it branches on severity, so both are present whether or not anything was
found. `crew_state.py`'s `_artifact_confirms_scan` requires the exact
`**Total finding instances:** <N>` line as proof this file came from a real scan run, not
a hand-typed note that merely mentions the target (`echo "TODO: scan <url> later" > ...`
does not contain it). Do not change this line's wording without updating
`_SCAN_MARKER_RE` in `crew_state.py` in the same change — the two are one contract, not two
independent formats that happen to agree.

If this repo has crew installed and `.crew/endpoints.json` exists: check whether any
DECLARED record's `endpoint` (a host or URL — not a free-text description; the endpoint
must be something this report's own text can literally contain) matches a target this
findings file actually scanned. If one does, this report is the scan discharging that
endpoint's obligation — land it at the ledger's own computed path instead of wherever
`--format`/`--out` would otherwise put it:

```bash
path=$(python3 <path-to-crew>/hooks/scripts/crew_state.py --root . --scan-artifact-path <id>)
```

Pass that as `--out "$path"` to the report generation (creating its parent directory
first), then, once the write succeeds, freeze it onto the record so a later repo-shape
change can never relocate or orphan this scan:

```bash
python3 <path-to-crew>/hooks/scripts/crew_state.py --root . --record-scan-artifact <id>
```

**Do not skip the freeze step.** It is silent if you do: the endpoint still reads as
scanned right afterward, because the report happens to sit at the same path
`crew_state.py` would compute fresh — until a repo-shape change recomputes a *different*
default and orphans it with no record of why. This is now detectable rather than only
discoverable after the fact: `crew_state.py`'s state JSON carries an `endpoints.unfrozen`
list naming exactly this — a declared record that reads as scanned today but has no frozen
`artifactPath` — so check it (or ask the PM) before assuming a scan without this step is
safe to leave that way.

Skip all of this — write the report exactly where asked — when no crew ledger exists, or
none of its records match this scan's target.
