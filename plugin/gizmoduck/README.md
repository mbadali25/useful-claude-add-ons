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
**WSL / Linux:** `./bootstrap.sh` (root, or `sudo`), or `./bootstrap.sh --user` with no root at all
**Windows (PowerShell):** `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1`

`./bootstrap.sh --dry-run` (with or without `--user`) prints where each tool would go and changes
nothing. CI pipelines and containers: see "CI and containers" below.

Both fetch the latest prebuilt binary and community templates. PDF reports need
`wkhtmltopdf` (installed by bootstrap.sh; `winget install wkhtmltopdf` on Windows).
Where `api.github.com` is refused (a Claude Code cloud session, some corporate proxies) they
fall back to git tags and git for the version lookup and the templates. `bootstrap.sh` skips
any tool already on PATH that passes a run check, so it is safe to re-run;
`GIZMODUCK_BOOTSTRAP_FORCE=1 ./bootstrap.sh` reinstalls everything. The install locations are
fixed (`/usr/local/bin`, `/opt`): `GIZMODUCK_BIN_DIR`, `GIZMODUCK_OPT_DIR` and
`GIZMODUCK_APT_LISTS_DIR` are a test seam, honoured only with `GIZMODUCK_BOOTSTRAP_TEST=1` and
otherwise ignored with a notice.

If your antivirus/EDR quarantines or deletes nikto, sqlmap, ZAP, or a Nuclei
template mid-install, see [`docs/antivirus-exclusions.md`](docs/antivirus-exclusions.md) - that's expected, not a broken install.

## CI and containers

gizmoduck runs **inside** a container or a CI job; it never drives Docker itself (no image, no
`docker run`, and ZAP runs from its unzipped Automation Framework, not the `zaproxy` image).

- **As root in a container** (the usual image build step), `./bootstrap.sh` runs every step
  without `sudo`. Not root and no `sudo` on PATH: it exits 2 and points at `--user`. Through `sudo`
  without a terminal it uses `sudo -n`, so a password prompt fails instead of hanging the job.
  apt runs with `DEBIAN_FRONTEND=noninteractive`.
- **`--user`** installs, with no elevation anywhere, every tool that needs no package manager
  into the tool home (`GIZMODUCK_HOME`, else `$XDG_DATA_HOME/gizmoduck`, else
  `~/.local/share/gizmoduck`; see "Where gizmoduck looks for tools"): Nuclei, trivy, sqlmap,
  dependency-check, ZAP, and testssl.sh and nikto when `hexdump` and `perl` are present; checkov
  and semgrep go through `pip3 install --user` and are linked into the tool home's `bin`. It needs `curl`, `unzip`, `git` and `python3` first and exits 2 naming
  any that are missing. Tools only a package manager provides are reported as present (on
  PATH and `--version` runs), **skipped** (not on PATH), or failed (on PATH but `--version`
  fails, so the run exits 1), never installed. Add these to the image when you want them:

  | Package (Debian/Ubuntu) | For |
  |---|---|
  | `nmap` | nmap |
  | `openjdk-17-jre` | ZAP and dependency-check (Java 17+; without it both **fail** under `--user`) |
  | `perl`, `libxml-writer-perl` | nikto |
  | `wkhtmltopdf` | PDF reports (HTML reports work without it) |
  | `bsdextrautils` | `hexdump`, without which testssl.sh is skipped under `--user` |
  | `python3-pip` | `pip3`, which checkov and semgrep install through (without it both **fail**) |

- **Exit status**, so a pipeline can gate on it: `0` nothing failed; `1` a tool or the Nuclei
  template download failed (it used to exit 0 after a partial install); `2` a usage or
  precondition error. When tools were skipped and none failed it exits 0 and its **last line**
  is `GIZMODUCK_BOOTSTRAP_SKIPPED: <names>`, the same shape as `GIZMODUCK_ROUTINE_INCOMPLETE`.
- **`--dry-run`** prints the tool home, the privilege it would use and one `plan:` line per
  tool, then exits 0: no network call, no file written, no directory created.
- **Cache between runs**: the tool home, Nuclei's template directory (`~/nuclei-templates`,
  or what `~/.config/nuclei/.templates-config.json` names), and Python's user base
  (`python3 -m site --user-base`, usually `~/.local`), where `pip3 install --user` puts checkov
  and semgrep - the tool home holds only links to their scripts. A re-run skips every tool that
  is already installed and passes its probe.
- **Secrets** come from the pipeline's secret store as environment variables, never from a
  manifest or a committed file: `GITHUB_TOKEN` (optional; release lookups use it for a higher
  API rate limit, and it is passed to curl as a header file, never printed or put on a command
  line) and `NVD_API_KEY` (optional; dependency-check's first NVD sync).
- **Scans** then run headless through `routine` (exit 4 and a
  `GIZMODUCK_ROUTINE_INCOMPLETE:` last line when a tool could not run). Nuclei's safe defaults
  apply there as everywhere.

```bash
# image build, as root
./bootstrap.sh
# job without root, with the tool home cached between runs
GIZMODUCK_HOME="$CI_CACHE_DIR/gizmoduck" ./bootstrap.sh --user
GIZMODUCK_HOME="$CI_CACHE_DIR/gizmoduck" python3 scripts/gizmoduck.py routine targets.yaml --out out/
```

## Where gizmoduck looks for tools

Every scanner is found by one rule, in this order:

1. **The tool's own override variable**, when it is set (table below).
2. **The tool home**: `GIZMODUCK_HOME`, or by default `$XDG_DATA_HOME/gizmoduck`, else
   `~/.local/share/gizmoduck`, on Linux and macOS. Executables in its `bin/` are found ahead of
   PATH for every scanner and for Nuclei. Windows has no default tool home; set `GIZMODUCK_HOME`
   to use one.
3. **PATH**.
4. **The Windows install location** `%LOCALAPPDATA%\Programs\<tool>`, where `bootstrap.ps1`
   extracts ZAP, nikto and testssl.sh.

**A set override that does not resolve disables that tool.** It does not fall back to a copy on
PATH, so a scan never runs a different install from the one you named; `/gizmoduck:doctor`
names the variable, its value and the tool it disables. Variables are read when a tool is looked
up, not when gizmoduck starts.

| Variable | Names | In the tool home |
|---|---|---|
| `GIZMODUCK_HOME` | the tool home itself | `bin/<tool>` for every scanner and Nuclei |
| `GIZMODUCK_ZAP_HOME` | a ZAP install directory: `zap.sh`/`zap.bat` in it or one level down, else a `zap-*.jar` under it (run with `java`) | `zap/` |
| `GIZMODUCK_NIKTO_PL` | the `nikto.pl` file (run with `perl`) | `nikto/program/nikto.pl` |
| `GIZMODUCK_TESTSSL_SH` | the `testssl.sh` script (run with `bash`) | `testssl.sh/testssl.sh` |
| `GIZMODUCK_MSYS2_BIN` | a directory holding `hexdump`, for testssl.sh under Git Bash; a helper, not a scanner, so it is not part of the order above | - |

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
    options: {zap_active: false, nmap_vuln: false, sqlmap: false,
              nuclei_intrusive: false, nuclei_rate_limit: 50}
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
switch active scanning on (`zap_active`, `nmap_vuln`, `nuclei_intrusive`, `sqlmap`) must be
YAML `true` or `false`: a quoted `"false"` is refused, because it would read as true.
`nuclei_rate_limit` must be an integer of 1 or more. Nuclei's `extra` option must be a string
and may not carry a tag, rate, attack or config-file flag (`-etags`, `-itags`, `-rl`, `-rlm`,
`-rld`, `-it`, `-dast`, `-fuzz`, `-config`, `-tp`, `-profile` and their long forms; the full
list is `NUCLEI_STRICT_FLAGS` in `gizmoduck.py`): the manifest is refused with exit 2, because
the recorded mode would otherwise lie - use `nuclei_intrusive` and `nuclei_rate_limit`.
Before Nuclei runs, the routine also reads the Nuclei config file Nuclei itself would merge
(`<user config dir>/nuclei/config.yaml` - `~/.config/nuclei/config.yaml` or
`$XDG_CONFIG_HOME/nuclei/config.yaml` on Linux, `%APPDATA%\nuclei\config.yaml` on Windows -
and `$NUCLEI_CONFIG_DIR/config.yaml`). If it sets `include-tags`, `include-templates`, any
rate key, `per-host-rate-limit`, `dast`, `fuzz` or `profile`, the Nuclei cell is refused
(`error:returncode=-1`, naming the file and keys) and nothing is sent; a file that exists but
cannot be read or parsed is refused the same way. A missing or comment-only file is fine. The manifest is read
once; what was checked is what runs. `routine` needs PyYAML; without it the command exits 2
and names it.

Two output layouts, one of them per run:

```bash
python3 scripts/gizmoduck.py routine targets.yaml --out scans/today     # default: routine-out/
python3 scripts/gizmoduck.py routine targets.yaml --scan-root .         # ./docs/security-scans/YYYY-MM-DD/
python3 scripts/gizmoduck.py routine targets.yaml --scan-root . --date 2026-09-29
```

Either directory holds `findings.jsonl`, `run-manifest.json` (per target and tool: `ran`,
`ran(<mode>)` - nmap `ran(safe)`/`ran(safe+vuln)`, ZAP `ran(baseline)`/`ran(baseline+active)`,
Nuclei `ran(safe)`/`ran(safe+intrusive)` - `skipped-missing`, `skipped-active` or
`error:<why>`), `report.md`,
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

**Nuclei is safe by default** (since T-0108): every scan, from `scan` or `routine`, adds
`-etags dos,intrusive,fuzz` and `-rl 50 -rld 1s` (at most 50 requests per second; Nuclei's own
default is 150). The exclusion is tag-based and best-effort: it skips templates whose `tags`
name those words, and a template that marks itself intrusive only elsewhere (a few upstream
templates put it under `info.metadata`) is not excluded. `scan --intrusive` drops the tag exclusion - pass it only after the target's owner has
authorised intrusive testing - and `scan --rate-limit N` replaces the 50. A rate flag typed in
`scan --extra` stands in place of the default; together with `--rate-limit` it is a usage error.
`scan --extra` is otherwise a raw passthrough, and on that path **you own its safety**: a
`-itags`, `-config`, `-tp` or `-rld` you type there, or your own Nuclei config file, can undo
both defaults. Only `routine` refuses them. In a manifest the same two switches are
`nuclei_intrusive` and `nuclei_rate_limit`.

```bash
python3 scripts/gizmoduck.py scan targets.txt --severity critical,high,medium --out findings.jsonl
python3 scripts/gizmoduck.py scan https://site --intrusive --rate-limit 20   # owner-authorised only
python3 scripts/gizmoduck.py diff baseline.jsonl findings.jsonl --min-severity high
python3 scripts/gizmoduck.py report findings.jsonl --format pdf --out report.pdf
python3 scripts/gizmoduck.py routine targets.yaml --scan-root .
python3 scripts/gizmoduck.py report routine-out/findings.jsonl --run-manifest routine-out/run-manifest.json
python3 scripts/gizmoduck.py doctor
```
