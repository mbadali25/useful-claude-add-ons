# gizmoduck (Claude Code plugin)

**Gizmoduck** runs [Nuclei](https://github.com/projectdiscovery/nuclei) vulnerability
scans on websites and hosts on their own, or the full scanner routine from one manifest
(checkov, trivy, dependency-check, semgrep, ZAP, testssl, nmap, nikto, and sqlmap only
when confirmed by name), diffs them against previous scans, and turns findings into
triaged reports (Markdown + HTML + PDF) and ServiceDesk Plus tickets. Runs on
**WSL/Linux and Windows**.

Nuclei is MIT-licensed and self-hosted, so the CLI runs scans end-to-end — no export
step, no API restrictions. **Only scan assets you own or have written permission to test.**

## Commands
| Command | Does |
|---|---|
| `/gizmoduck:scan <target> [sev]` | Scan → report (md/html/pdf) → confirm batch → ticket Crit+High |
| `/gizmoduck:report <findings.jsonl> [sev]` | Rebuild a report from findings (no rescan) |
| `/gizmoduck:tickets <findings.jsonl> [sev]` | Confirm batch → open/sync SDP tickets from findings |
| `/gizmoduck:diff <old.jsonl> <new.jsonl> [sev]` | What's new since a previous scan |
| `/gizmoduck:update` | Update the Nuclei engine + templates |
| `/gizmoduck:doctor` | Check the toolchain (nuclei, templates, python, PDF) |

## Install Nuclei (once)
**WSL / Linux:** `./bootstrap.sh`
**Windows (PowerShell):** `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1`

Both fetch the latest prebuilt binary and community templates. PDF reports need
`wkhtmltopdf` (installed by bootstrap.sh; `winget install wkhtmltopdf` on Windows).
Where `api.github.com` is refused (a Claude Code cloud session, some corporate proxies) they
fall back to git tags and git for the version lookup and the templates. `bootstrap.sh` skips
any tool already on PATH, so it is safe to re-run; `GIZMODUCK_BOOTSTRAP_FORCE=1 ./bootstrap.sh`
reinstalls everything.

If your antivirus/EDR quarantines or deletes nikto, sqlmap, ZAP, or a Nuclei
template mid-install, see [`docs/antivirus-exclusions.md`](docs/antivirus-exclusions.md) - that's expected, not a broken install.

## Dependency-Check: NVD API key (optional)

dependency-check's first run downloads the entire NVD CVE corpus. Without an API
key, NIST rate-limits that sync to ~5 requests/30s — on a fresh machine, that
first run can take the better part of an hour with no progress output, which
looks like a hang but isn't. An API key raises the limit to ~50/30s, roughly 10x.

Get a free key at https://nvd.nist.gov/developers/request-an-api-key (just an
email + organization, no cost). NIST emails an **activation link**, not the key
itself — open that link; the key is shown on the page behind it.

Set it as an environment variable before scanning:
```bash
export NVD_API_KEY=<your key>          # Linux/WSL
$env:NVD_API_KEY = '<your key>'        # Windows PowerShell
```
It's optional — dependency-check runs fine without it, just slower on the first
sync. `bootstrap.sh`/`bootstrap.ps1` print this same reminder after installing
dependency-check; `/gizmoduck:doctor` reports whether the variable is set (never
the value itself), and an unset key is reported as a gap, not a failure.

## Layout
```
gizmoduck/
├── .claude-plugin/plugin.json
├── bootstrap.sh / bootstrap.ps1   # installers (Linux/WSL, Windows)
├── scripts/gizmoduck.py           # scan / routine / report / tickets / diff / doctor / update
├── scripts/routine.py             # the multi-tool routine: manifest, gates, orchestration
├── scripts/scanners/              # one adapter per tool (nuclei, zap, nikto, nmap, testssl,
│                                  # trivy, depcheck, checkov, sqlmap, semgrep)
├── scripts/report_template.py     # HTML+PDF rendering (read its docstring before
│                                  # editing the CSS - wkhtmltopdf is Qt WebKit 4.8)
├── skills/gizmoduck/SKILL.md
├── commands/                      # scan, report, tickets, diff, update, doctor
└── README.md
```

## What the report shows

Critical, High and Medium findings are itemised in full. Low and Info are counted in
the severity table and then dropped: a signature scanner's low/info output is inventory
(version banners, DNS records, "a form exists"), and listing it buries the findings
somebody is expected to fix. The report states how many it suppressed, so nothing is
silently missing, and the complete detail stays in the JSONL.

`--min-severity` raises that floor but never lowers it.

## Ticketing is gated

`tickets` files REAL ServiceDesk Plus tickets, so it is confirmed by default whenever there
is anything to confirm. Without `--yes`, `gizmoduck.py tickets` prints the candidate list
(severity + subject), a digest over that exact batch, and the rerun command carrying it, then
exits 3 without emitting the JSON records a ticketing step would act on. Pass `--yes
<digest>` only after the whole batch has been shown to the user and approved — one
confirmation for the batch, not one per ticket — and only the digest the preview just printed:
a stale or mismatched one (a different findings file, a different `--min-severity`, findings
that changed in between) is refused with `GIZMODUCK_APPROVAL_MISMATCH` rather than silently
creating whatever the current batch turns out to be. Zero qualifying findings has nothing to
confirm: it prints `[]` and exits 0 either way, `--yes` or not.

## Routine: every scanner from one manifest

`gizmoduck.py routine <manifest.yaml>` runs every scanner the manifest resolves for each
target, then writes the combined report with its coverage table. There is no slash command
for it yet; it is a CLI for scheduled and headless runs.

```yaml
authorized_by: "CHG-1234 - Jane Doe, approved 2026-09-29, authorized to test these targets"
targets:
  - name: portal                  # unique; keys the output directory and every finding
    kind: web                     # web | host | iac | deps | code
    url: https://portal.example.com
    options: {zap_active: false, nmap_vuln: false, sqlmap: false}
  - name: infra
    kind: iac
    path: ./terraform             # web -> url, host -> host, iac/deps/code -> path
    tools: [checkov]              # optional: replaces the kind's default tool list
```

Default tools per kind: `web` nuclei, zap, nikto, nmap, testssl; `host` nuclei, nmap,
testssl; `iac` checkov, trivy; `deps` trivy, dependency-check; `code` semgrep. A manifest
with no `authorized_by`, a duplicate `name`, an unknown `kind`, a target missing its
location, or a value of the wrong type is refused before anything runs, with exit 2. A
`name` becomes the directory `<out>/<name>/` and a row in `report.md`, so it must be
portable: letters, digits, `.`, `_` and `-` only, starting with a letter or digit, not
ending with `.`, at most 64 characters, not a Windows device name (`CON`, `nul.txt`, `COM1`
...), not the name of a file routine writes there (`report.md`, `scan-meta.json` and the
rest, in any case), and not the same as another target's name but for case. The options that
switch active scanning on (`zap_active`, `nmap_vuln`, `sqlmap`) must be YAML `true` or
`false`: a quoted `"false"` is refused, because it would read as true. The manifest is read
once; what was checked is what runs. `routine` needs PyYAML; without it the command exits 2
and names it.

Two output layouts, one of them per run:

```bash
python3 scripts/gizmoduck.py routine targets.yaml --out scans/today     # default: routine-out/
python3 scripts/gizmoduck.py routine targets.yaml --scan-root .         # ./docs/security-scans/YYYY-MM-DD/
python3 scripts/gizmoduck.py routine targets.yaml --scan-root . --date 2026-09-29
```

Either directory holds `findings.jsonl`, `run-manifest.json` (per target and tool: `ran`,
`ran(<mode>)`, `skipped-missing`, `skipped-active` or `error:<why>`), `report.md`,
`report.html`, `report.pdf` when wkhtmltopdf or WeasyPrint is installed, `scan-meta.json`,
and one subdirectory per target holding each tool's native output. `--date` only shapes the
`--scan-root` path and defaults to today's UTC date; `--scan-root` and `--out` together is a
usage error.

`scan-meta.json` (gizmoduck's own format, `"schema": 1`):

| Field | Meaning |
|---|---|
| `schema` | `1` |
| `gizmoduck_version` | from `.claude-plugin/plugin.json` beside `scripts/`; `null` when that file is not there (a copy of `scripts/` alone) |
| `date`, `started_at`, `completed_at` | the run date and UTC timestamps |
| `authorized_by`, `manifest` | the manifest's authorization statement and the path it was read from |
| `confirm_active` | whether `--confirm-active` was named |
| `targets` | each target's `name`, `kind` and `location` |
| `coverage` | `cells`, `by_status` (counts per `ran` / `skipped-missing` / `skipped-active` / `error`), `complete` (true only when every cell ran; a run with no cells is not complete), `ran_with_scan_errors` (cells that ran but whose tool reported scan errors, e.g. testssl WARN lines) |
| `findings` | `total` and `by_severity` |
| `files` | the file names above; `report_pdf` is `null` when no PDF renderer was found |

Fields gizmoduck cannot know, such as whether a site was reachable, are not invented.

**Exit status.** `0`: every cell ran. `4`: every output was written but at least one cell did
not run, so **4 is not a clean result**; the last stdout line starts
`GIZMODUCK_ROUTINE_INCOMPLETE:` and the Coverage table in `report.md` says which cells.
`2`: a usage or manifest error, and nothing was written. Findings never change the status.

**A same-day rerun is refused.** A directory that already holds a `scan-meta.json` is an
earlier run's evidence, so `routine` exits 2 without touching it unless `--replace` is
named. `--replace` removes the earlier run's files and only the per-target directories its
`scan-meta.json` names; anything else in the directory (a `.git`, your own files) is left
alone. It removes that `scan-meta.json` first, so a replace interrupted part-way leaves no
`scan-meta.json` at all, exactly like an interrupted first run, never the old one describing
files that are gone. When it cannot tell which directories the earlier run owns (an
unreadable or older `scan-meta.json`, a target name that is not a plain directory name, or a
named directory that is a symlink or, on Windows, a junction) it exits 2 and removes
nothing. A target directory that already exists (or is a symlink) and that no earlier run in
the directory owns is refused the same way, on a first run as on `--replace`: writing into
it would make it the run's own, and the next `--replace` would remove a directory routine
never created. In a directory with no `scan-meta.json`, a file named like one routine writes
(`report.md`, `findings.jsonl` and the rest) is refused the same way rather than
overwritten. After an interrupted run, move its partial files and target directories aside
before rerunning. `scan-meta.json` and `report.*`, `report.pdf` included, are written to a
temp beside them and renamed into place, never truncated in place; wkhtmltopdf gets 300
seconds. A run holds `.gizmoduck-routine.lock` in the output directory for its whole length,
so a second run on the same directory exits 2; a run killed outright leaves the lock behind,
and the refusal names it to delete once no run is active.

**sqlmap has two gates, and both stay.** `options.sqlmap: true` makes a target a candidate;
it fires only when `--confirm-active` is named in full (no abbreviation is accepted). A
candidate without the flag records `skipped-active`. Name the flag only after the owner of
the target has authorised active testing.

`report --run-manifest <dir>/run-manifest.json` re-renders a routine run's report with its
coverage table; without it a routine report hides which tools did not run.

The dated layout is separate from crew's endpoint ledger path,
`docs/security-scans/<ep-id>.md`, and does not satisfy it; bridging the two is a follow-up.
The routine's own test suite never runs a real scanner: every tool is a fake injected through
`run_routine`'s registry, or provably absent in a sanitised environment.

## Manual CLI (Linux: `python3`, Windows: `python`)
```bash
python3 scripts/gizmoduck.py scan targets.txt --severity critical,high,medium --out findings.jsonl
python3 scripts/gizmoduck.py diff baseline.jsonl findings.jsonl --min-severity high
python3 scripts/gizmoduck.py report findings.jsonl --format pdf --out report.pdf
python3 scripts/gizmoduck.py routine targets.yaml --scan-root .
python3 scripts/gizmoduck.py report routine-out/findings.jsonl --run-manifest routine-out/run-manifest.json
python3 scripts/gizmoduck.py doctor
```
