# Gizmoduck multi-scanner routine — design spec

**Date:** 2026-09-10
**Status:** Approved 2026-09-10 — §12 open questions resolved, see §12
**Repo:** `useful-claude-add-ons` (plugin: `plugin/gizmoduck`)
**Branch:** `gizmoduck-multiscanner`

## 1. Problem

Gizmoduck today runs one scanner — Nuclei — against web/host targets and turns
its JSONL into triaged Markdown/HTML/PDF reports and ServiceDesk Plus tickets.
Nuclei is a signature scanner: it confirms *known* issues on the unauthenticated
network edge and structurally cannot see authenticated app logic, dependency
CVEs, IaC misconfiguration, TLS weaknesses, or SQL injection it has no template
for.

We want gizmoduck to orchestrate a fuller toolchain, pick the right tools per
target automatically, and merge everything into one report — without breaking
the existing Nuclei-only commands.

## 2. Goals / non-goals

**Goals**
- Integrate eight additional scanners alongside Nuclei — nine tools in total
  (see §4; tfsec was dropped as deprecated, §13.4).
- A `routine` command that reads a targets manifest, runs the tools that fit each
  target's kind, and produces **one combined report per run** with per-target
  sections and a coverage table.
- Normalize every tool's output into the existing finding shape so `report`,
  `summary`, `diff`, and `tickets` keep working unchanged.
- Extend `bootstrap` and `doctor` to install/verify the new tools.

**Non-goals**
- No change to the existing single-scanner commands' behavior or output.
- No new ticketing logic — the combined `findings.jsonl` feeds the existing
  `tickets` flow as-is.
- Not a crawler/DAST engine of our own — we orchestrate established tools.

## 3. Architecture

Rather than grow the 598-line `gizmoduck.py`, add a small package so each tool's
quirks stay isolated and independently testable.

```
scripts/
  gizmoduck.py            # CLI dispatch (unchanged commands + new `routine`)
  report_template.py      # HTML/PDF rendering (extended for grouping+coverage)
  normalize.py            # Finding shape + severity map + synthetic template-id
  routine.py              # manifest parse, target→tool mapping, orchestration
  scanners/
    __init__.py           # registry: kind -> [adapter], name -> adapter
    base.py               # adapter protocol + shared subprocess/timeout helpers
    nuclei.py             # refactor of existing cmd_scan into the adapter shape
    zap.py  nikto.py  nmap.py  testssl.py
    trivy.py  depcheck.py  checkov.py  sqlmap.py
                          # (no tfsec.py — deprecated, see §13.4)
```

**Adapter protocol** (`scanners/base.py`) — every tool module implements:
- `NAME`, `KINDS` (which target kinds it applies to), `ACTIVE` (bool: sends
  attack traffic), `DEFAULT_ENABLED` (bool).
- `is_available() -> bool` — binary/image present.
- `run(target, outdir, opts) -> (raw_path | None, ToolResult)` — invoke the tool,
  write native output under `outdir`, return its path and the execution result.
  **The `ToolResult` is not optional**: `routine` records `error:timeout` and
  `error:<message>` per cell (§6 step 5) and cannot derive either from a path.
  See §13.14.
- `parse(raw_path, target) -> list[Finding]` — normalize native output.

`gizmoduck.py` imports the package and adds one subcommand; nothing else in its
existing command set changes.

## 4. Tools, invocation, output → normalization

| Tool | Kind(s) | Native output | Severity source | Active? |
|---|---|---|---|---|
| Nuclei | web, host | JSONL (existing) | template `info.severity` | no |
| OWASP ZAP | web | JSON (`-J`) | alert `riskcode` (0–3) | baseline=no, active=yes (opt-in) |
| ↳ delivery | | local ZAP first, Docker image only as fallback (§12.2) | | |
| Nikto | web | CSV or XML — **not** JSON (§13.6) | none at all → heuristic (`medium`/`info`) | no |
| Nmap + NSE | web, host | XML (`-oX`) | ports=`info`; `vuln` NSE→map | safe=no, `vuln`=opt-in |
| testssl.sh | web, host | JSON (`--jsonfile`) | `severity` field | no |
| Trivy | deps | JSON (`--format json`) | `Severity` | no |
| Dependency-Check | deps | JSON (`--format JSON`) | CVSS→band | no |
| Checkov | iac | JSON (`-o json`) — object OR array | check `severity` (usually `null` → `medium`) | no |
| Trivy (misconfig) | iac | JSON (`--scanners misconfig`) | `Severity` | no |
| sqlmap | web (gated) | `--output-dir` session artifacts; no JSON exists (§13.9) | persisted injection Type+Payload = `high`/`critical` | **yes (opt-in + confirm)** |

**Severity map (`normalize.py`)** → gizmoduck's five levels
`critical/high/medium/low/info`:
- ZAP riskcode 3→high, 2→medium, 1→low, 0→info (ZAP has no "critical"; a
  High with confidence High stays high).
- CVSS band (Dependency-Check): ≥9.0 critical, ≥7.0 high, ≥4.0 medium, >0 low,
  else info.
- Text levels (testssl/Trivy/Checkov/Nmap-vuln): case-insensitive map;
  unknown → `info` and flagged `unknown` in the raw field. Trivy's `UNKNOWN`
  and Checkov's `null` both land here (§13.5, §13.7).
- Nikto: no severity model → default `medium` for its reported vulns, `info`
  for banner/version items, with a comment noting the assignment is heuristic.

**Finding shape** — identical keys to today's Nuclei finding dict, plus:
- `tool` — originating tool name.
- `template_id` — synthetic `"<tool>:<rule-or-plugin-id>"` so `dedupe()` works
  across tools without collision. **Not sufficient on its own:** `dedupe()` also
  collapses across *targets*, which §13.1 corrects.
- `target` — the manifest target it came from.
- `tools` — list of every tool that reported this finding. Length 1 until the
  report's cross-tool merge (§7) collapses `deps`/`iac` duplicates.
- `merged_from` — list of each contributing tool's native rule id, populated
  only on merged entries so provenance survives the collapse.

Because the shape is unchanged otherwise, `cmd_report`, `cmd_summary`,
`cmd_diff`, and `cmd_tickets` operate on the combined `findings.jsonl` with no
changes to their logic.

## 5. Targets manifest

A YAML file (routine input). Each entry declares a `kind` that drives tool
selection; `tools` may override the default set; per-target `options` toggle
active scans.

```yaml
authorized_by: "<name/ticket> — I confirm authorization to test these targets"
targets:
  - name: www.thdmarketplace.com
    kind: web
    url: https://www.thdmarketplace.com
    options: { zap_active: false, nmap_vuln: false, sqlmap: false }
  - name: thd-processors-terraform
    kind: iac
    path: ../TheHomeDepot/terraform/thd-processors
  - name: thd-processors-deps
    kind: deps
    path: ../TheHomeDepot/terraform/thd-processors
```

Kind → default tools:
- `web` → nuclei, zap(baseline), nikto, nmap(safe), testssl  (sqlmap only if `options.sqlmap`)
- `host` → nuclei, nmap(safe), testssl
- `iac` → checkov, trivy(misconfig)
- `deps` → trivy(vuln), depcheck

`routine` refuses to run unless `authorized_by` is present and non-empty.

## 6. Data flow (`routine`)

1. Parse manifest; validate `authorized_by`.
2. For each target, resolve the adapter list (kind default ± `tools`/`options`).
3. For each adapter: if `is_available()` is false → record `skipped(missing)`;
   if `ACTIVE` and not enabled → record `skipped(active-not-enabled)`; else
   `run()` → native file under `<out>/<target-name>/<tool>.<ext>`.
4. `parse()` each native file → normalized findings; append to
   `<out>/findings.jsonl` (one combined file) with `tool`+`target` set.
5. Write `<out>/run-manifest.json`: per-target/per-tool status
   (ran / skipped-missing / skipped-active / error+message), durations, counts.
6. Render one combined report (md, html, pdf) via the extended report path.

Native per-tool outputs are retained for provenance; the combined `findings.jsonl`
is the single source the report and tickets consume.

## 7. Combined report

Extend `cmd_report` / `report_template.py`:
- New optional grouping: **by target, then by category**, when the input
  carries `target`/`tool` fields (the existing flat mode stays for plain Nuclei
  JSONL). One section per category, not per tool — so `deps` and `iac` each
  render once even though two tools feed them (§12.3).
- **Cross-tool merge within a category.** Where two tools report the same
  issue, the entries collapse to one carrying a `tools` list naming every
  reporter, and the *highest* severity any of them assigned. Merge keys are
  deliberately narrow, and nothing merges across categories:
  - `deps` — merge on `(CVE id, package name, installed version)`. A finding
    with no CVE id never merges; it renders on its own.
  - `iac` — merge on `(file path, start line, resource identifier)`. Rule ids
    differ between Checkov and tfsec and are **not** part of the key.
  - Every merged entry keeps each contributing tool's native rule id in a
    `merged_from` list, so provenance survives the merge and an over-merge is
    visible in the report rather than silent.
  - Guard: if a merge would combine entries whose normalized titles share no
    token, keep them separate and record the near-miss in the run manifest —
    a wrong merge hides a real finding, which costs more than a duplicate.
- A **coverage table** at the top: rows = targets, columns = tools, cells =
  ran ✓ / skipped(missing) / skipped(active-off) / error. This makes gaps
  explicit so an absent finding is never mistaken for a clean result — directly
  addressing the registration.thdmarketplace.com "0 vs 21" lesson from the
  initial scans.
- Detail floor unchanged: itemize Critical/High/Medium, count Low/Info, state
  how many suppressed.
- **CSS caution:** `report_template.py` renders PDF through wkhtmltopdf's Qt
  WebKit 4.8 (no flexbox/grid/custom-properties). Any new report markup must be
  verified in the PDF, not just a browser — per the module docstring.

## 8. Safety / gating

- **Active tools** (`ACTIVE=True`): sqlmap, ZAP active scan, Nmap `vuln` NSE —
  all `DEFAULT_ENABLED=False`. They run only when the target's `options` opt in.
- **sqlmap** additionally is confirm-gated at the routine level, mirroring the
  `tickets` digest gate: routine prints the exact sqlmap target/args it would
  run and requires an explicit approval token before it fires. sqlmap targets an
  injection point (ideally one ZAP flagged), never a blind sweep.
- **Authorization:** manifest `authorized_by` is mandatory; routine aborts
  without it. The report header restates it.
- Per-tool timeouts (shared helper in `base.py`) so one hung scanner can't stall
  the run; a timeout is recorded as `error(timeout)` in the run manifest.

## 9. Install / doctor

- `bootstrap.sh` / `bootstrap.ps1`: best-effort install of nmap, nikto,
  testssl.sh, trivy, checkov, tfsec, dependency-check, sqlmap, and ZAP
  (**local ZAP install, including its JRE prerequisite**; the
  `zaproxy/zap-stable` Docker image is only used if a local install is
  impossible and Docker happens to be present — §12.2). Each install is
  independent — one failure doesn't abort the rest.
- `doctor`: report present/missing for every tool, with a one-line install hint
  per missing tool. For ZAP, report *which* delivery was found
  (`local` / `docker` / missing) rather than a bare present/absent, so an
  operator can tell a working local ZAP from a Docker path that will never
  resolve on this machine. Exit non-zero only if *core* (nuclei) is missing;
  the rest are reported as gaps, not failures.

## 10. Testing

- **Per-adapter `parse()` unit tests** using captured sample native outputs as
  fixtures in `scripts/_test/fixtures/<tool>.<ext>` — fully offline, no network,
  no tool binary required. This is the bulk of the value and the coverage.
- **Severity-map unit tests** for every band/edge in `normalize.py`.
- **Routine orchestration test** with fake adapters (monkeypatched registry):
  verifies kind→tool mapping, skip/active/error paths, combined-jsonl assembly,
  and run-manifest contents — no real scanners invoked.
- **Report grouping test**: a combined `findings.jsonl` fixture renders the
  target grouping and coverage table (assert on Markdown; PDF checked manually
  per the Qt caveat).
- Existing tests continue to pass unchanged (regression guard on the untouched
  commands).

## 11. Rollout / compatibility

- Additive only: new `routine` subcommand + new modules; existing commands and
  their output are byte-for-byte unchanged.
- New Python deps kept minimal: a YAML parser for the manifest (`pyyaml`);
  everything else is subprocess + stdlib JSON/XML. Document the `pyyaml` add.
- `plugin.json` version bump; README + a `/gizmoduck:routine` command doc;
  SKILL.md updated to describe the routine and the gating.

## 12. Resolved questions (2026-09-10 review)

1. **Manifest format — YAML.** Confirmed as specified in §5. Accepts the
   `pyyaml` dependency in exchange for per-target `kind`, `options` and
   `authorized_by` in a single file. The existing plain-text targets file stays
   as-is for the single-scanner `scan` command; `routine` uses YAML only.
2. **ZAP delivery — local install preferred, Docker optional.** Reversed from
   the draft. Docker is **not installed** on the operator machine
   (`docker: command not found`, verified 2026-09-10), so a Docker-first
   preference would make ZAP permanently unavailable there. `zap.py` therefore
   probes for a local ZAP first and falls back to the `zaproxy/zap-stable`
   image only when Docker is present. `doctor` must distinguish "no ZAP" from
   "ZAP present via <local|docker>", and `bootstrap` installs local ZAP
   (including its JRE prerequisite) rather than pulling an image.
3. **Category overlap — deduped into one section per category.** `deps`
   (Trivy vuln + Dependency-Check) renders as a single section, and `iac`
   (Checkov + Trivy misconfig) as a single section. Findings the two tools agree on are
   merged into one entry carrying a `tools` list of every tool that reported
   it, rather than appearing twice. See §7 for the merge keys and the
   over-merge guard.

---

## 13. Research-verified corrections (2026-09-10)

Findings from source-verification of the existing code and of each tool's
documentation. **Where these conflict with sections 3-9 above, these win** — the
earlier sections were written from design intent, these from the actual
artifacts.

### 13.1 `dedupe()` collapses across targets — the spec's compatibility claim is wrong

`dedupe()` (`scripts/gizmoduck.py:176-190`) keys **strictly on `template_id`**,
with no host or target component. Section 4's claim that a synthetic
`"<tool>:<rule-id>"` id lets `dedupe()` work unchanged is true for *tools* but
false for *targets*: run `routine` over five sites into one combined
`findings.jsonl` and one template firing on all five collapses into a single
group. Section 7 then asks to group by target, which cannot work on
target-blind data.

**Resolution:** key on `(target, template_id)` when a `target` field is present,
falling back to `template_id` alone when it is absent. Plain Nuclei findings
carry no `target`, so section 11's "existing commands byte-for-byte unchanged"
guarantee holds.

### 13.2 Finding-shape field names in section 4 are wrong

The normalized dict key is **`template_id`** (underscore), not `template-id` —
the hyphenated form is the raw Nuclei JSON key read at `gizmoduck.py:155`.
`severity` in the dict is an **int** (`SEV_NUM`, `gizmoduck.py:38-41`);
`severity_name` carries the display string. `normalize.py` must emit both.

The full existing key set, which every adapter must produce:
`template_id, name, severity, severity_name, type, timestamp, host,
matched_at, cve, cvss, description, remediation, reference, tags`.

### 13.3 ZAP: `zap-baseline.py` requires Docker even "standalone"

`zap-baseline.py` and `zap-full-scan.py` shell out to
`docker run ghcr.io/zaproxy/zaproxy:weekly` internally, so they are unusable on
the Docker-less operator machine despite being plain Python. The local path is
ZAP's **Automation Framework**: `zap.bat -cmd -autorun plan.yaml` with a
`report` job of `template: traditional-json`.

ZAP 2.16+ requires **Java 17 minimum** on Windows; `bootstrap` must check for
and install a JRE, not just ZAP.

The documented exit codes (0 pass / 1 FAIL / 2 WARN / 3 error) belong to the
*Docker wrapper scripts*. The Automation Framework's exit-code contract is
separate and must be verified against a real run before it is relied on.

The `riskcode` 0-3 to Info/Low/Medium/High mapping is a high-confidence
inference from example output, not a directly quoted source; the adapter should
treat an unexpected riskcode as `info` and flag it rather than assume.

### 13.4 tfsec is deprecated — dropped from the tool list

tfsec's engine was consolidated into Trivy (announced Feb 2023, per tfsec's own
README); last tag v1.28.14, May 2025, no new rules since. Its JSON schema could
not be source-verified — only corroborated by secondary sources.

**Dropped.** IaC coverage is Checkov + `trivy --scanners misconfig`. This is one
fewer parser, reuses the Trivy adapter already being built, and avoids the exact
failure the coverage table exists to prevent: IaC findings that stop reflecting
new rules while still *looking* like live coverage. Tool count is **nine total
(eight alongside Nuclei), not ten** — §2 and the §4 table are corrected to match.

### 13.5 Checkov: `severity` is normally `null`, and output may be an array

`BaseCheck.__init__` sets `self.severity = None`; severity is populated **only**
when checks sync from Bridgecrew/Prisma Cloud via `--bc-api-key`. In a
free/open-source run the large majority of built-in checks emit
`"severity": null`. Section 4's `medium` fallback is therefore the **normal
path**, not an edge case, and the report must not imply a real severity
assessment was made.

When more than one framework is scanned in one run, Checkov emits a **JSON array
of report objects**, not a single object. The parser must accept both shapes.

Populated values: `INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, plus legacy
aliases `MODERATE` to MEDIUM and `IMPORTANT` to HIGH.

### 13.6 Nikto: JSON output is unreliable — parse CSV or XML

`-Format json` is documented but emits invalid JSON on 2.1.6 when a target has
no webserver (duplicate closing brace, issue #721), and the fix is unconfirmed
on current releases. **CSV or XML is the primary parse path**, not a fallback.
CSV columns: `id, scanid, testid, ip, hostname, port, tls, refs, httpmethod,
uri, message, request, response`. Nikto has **no severity field at all**, which
is what forces section 4's heuristic assignment — the report must label it as
such.

### 13.7 Trivy: exit code is 0 by default; one binary covers two kinds

`trivy` exits **0 regardless of findings** unless `--exit-code <n>` is passed, so
the adapter must never infer findings from the exit code. `Results[]` can carry
`Vulnerabilities[]`, `Misconfigurations[]` and `Secrets[]` in the same file,
gated by `--scanners`; this is what lets one Trivy adapter serve both the `deps`
and `iac` kinds. Severity set: `UNKNOWN, LOW, MEDIUM, HIGH, CRITICAL` — no
`INFO`; map `UNKNOWN` to `info` and flag it. Timeout: `--timeout` (default
`5m0s`, extend for large repos).

### 13.8 Dependency-Check: CVSS v3 can be absent

`cvssv3.baseScore` may be null or absent for a dependency whose only NVD entry is
CVSSv2 or which is unscored, while the plain-text `severity` field is still
populated. Section 4's "CVSS to band" is therefore insufficient on its own.
Fallback order: plain-text `severity`, then `cvssv2.score`, then
`cvssv3.baseScore`.

### 13.9 sqlmap: no JSON report; confirmation comes from session artifacts

There is **no `--report-json` flag** — it is absent from `lib/core/optiondict.py`
and earlier community claims of it are wrong. Confirmed options: `--results-file`
(CSV, auto-used in `-m` multi-target mode), `--output-dir` (per-target session
tree with `log` and `session.sqlite`), `--batch` (non-interactive), and
`--time-limit=<seconds>` (total wall-clock cap — distinct from `--timeout`, which
is per-HTTP-request).

A **confirmed** injection is one sqlmap persisted with a recorded injection
`Type` and `Payload`; probed-and-negative parameters are not persisted. The
adapter must read session artifacts, never scrape stdout, and must not infer
findings from the exit code (sqlmap exits 0 on normal completion whether or not
anything was found).

**Correction (2026-09-10, found while implementing):** read the **`log` file**,
not `session.sqlite`. An earlier draft of this section named both. `session.sqlite`
is sqlmap's internal HashDB cache (`lib/utils/hashdb.py`) — a single `storage`
table of zlib-compressed pickle blobs keyed by an internal hash, not queryable
injection rows. Parsing it would mean depending on an undocumented,
version-fragile internal format *and* unpickling blobs this process did not
create, for no gain: the `log` file sits beside it in the same output directory
and carries the same facts as stable, documented plain text
(`Parameter: X (PLACE)` / `Type:` / `Title:` / `Payload:` blocks, one per
confirmed technique).

Severity: UNION-query and stacked-queries techniques reach real database content
→ `critical`. Any other confirmed technique (boolean-, time-, or error-based
blind) → `high`.

### 13.10 Existing-code realities that change task shape

- **No package structure exists.** `scripts/` has no `__init__.py`;
  `import report_template` works only because the script's own directory heads
  `sys.path` when invoked as `python gizmoduck.py`, with a
  `spec_from_file_location` fallback at `gizmoduck.py:274-291`. A `scanners/`
  subpackage needs the same by-path pattern or an explicit `sys.path` insert.
- **`bootstrap` is fail-fast, not independent.** Both `bootstrap.sh`
  (`set -euo pipefail`, lines 10-38) and `bootstrap.ps1` (lines 9-39) are single
  linear scripts that abort on first failure. Section 9's "each install is
  independent" is a **restructure of existing code**, not an addition.
- **The detail floor is duplicated.** `REPORT_DETAIL_FLOOR` / `detail_floor()`
  (`gizmoduck.py:50`, `204-210`) for the Markdown path and `ACTION_THRESHOLD`
  (`report_template.py:34`, re-applied in `render_report()` at `316-363`) for
  HTML/PDF are two independent copies of "never below Medium" with no shared
  constant. New report markup must satisfy both.
- **The CLI has no auto-registration.** A single `argparse.ArgumentParser` with a
  hardcoded `choices` list (`gizmoduck.py:449-450`) and an `if/elif` dispatch
  chain (`511-594`). Adding `routine` means editing both by hand.
- **Test coverage is 8 tests on the `tickets` gate only**
  (`scripts/_test/test_tickets_gate.py`), run as real subprocesses. There is no
  `conftest.py`, `pytest.ini`, `pyproject.toml`, or fixtures convention to build
  on — the plan must create them. The harness hardcodes directory depth
  (`parent.parent`, `.parents[2]`), so tests nested deeper need matching path
  math.

### 13.11 Resolved — the three gaps, answered

**Nmap `vuln` NSE.** Results live in `<script id=... output=...>` inside `<port>`,
with nested `<table>` elements holding `<elem key="...">value</elem>` children.
The structure comes from NSE's shared `vulns.lua` library, whose fields are
`title, state, IDS, risk_factor, scores, description, dates, check_results,
exploit_results, extra_info, references`. Machine-readable state values:
`NOT VULNERABLE`, `LIKELY VULNERABLE`, `VULNERABLE`, `VULNERABLE (DoS)`,
`VULNERABLE (Exploitable)`. Only the last four are reported by default —
`NOT VULNERABLE` appears only when a script sets `vulns.showall`.
*The exact `<table>`/`<elem>` key names are secondhand.* Lock the parser against
one real `nmap --script vuln -oX` run before trusting the paths.

**testssl.sh.** Use `--jsonfile`, which is flat — one self-contained object per
check. `--jsonfile-pretty` nests under a header block and **can emit invalid
JSON** (issue #1699). Per-finding fields: `id, ip, port, severity, finding`, plus
`cve`/`cwe` where the check maps to one.

The `severity` enum is eight values, all real: `OK, INFO, LOW, MEDIUM, HIGH,
CRITICAL, WARN, FATAL`. **`WARN` and `FATAL` are not security ratings** — they
mean the scan itself hit a client-side error. They must be recorded as a tool
error in the run manifest, never emitted as a finding about the target, or a
broken scan reports as a vulnerability.

**ZAP Automation Framework.** Default contract for `zap.bat -cmd -autorun`:
`0` = completed clean, `1` = at least one job error, `2` = warnings but no
errors. These are keyed to **job-level** errors and warnings, not to alert risk —
unlike `zap-baseline.py`, whose codes track FAIL/WARN alert counts. To make the
exit code reflect alert risk you must add an explicit `exitStatus` job to the
plan; it is not the default. Two open bugs touch this path (#7833 alertFilter
broken under AF, #8875 exitStatus ignoring False Positive confidence), so it is
less battle-tested than the older script.

Whether an AF `report` job with `template: traditional-json` emits a schema
identical to the standalone add-on's `-J` output **could not be confirmed from
primary documentation**. Both are documented as the same template name in the
same Report Generation add-on, which strongly implies one generator — but
Task 6 must run both once and diff the structure before committing a single
parser to serve both paths. That is a five-minute check that removes the guess.

### 13.12 Two more exit-code traps — six of nine tools now

The "never infer findings from an exit code" constraint is broader than §13.7
and §13.9 implied:

| Tool | Exit-code behaviour |
|---|---|
| Nuclei | 0 normally |
| **Nikto** | **Non-zero regardless of outcome** (issue #837) — check output file content, never status |
| **testssl.sh** | 0 ok, 1 error, **50–200 reserved for a severity-scored exit**, 242–255 internal errors. Non-zero ≠ failure |
| ZAP (AF) | 0/1/2 on job errors and warnings, not alert risk (§13.11) |
| Trivy | 0 regardless of findings unless `--exit-code` passed (§13.7) |
| sqlmap | 0 whether or not an injection was found (§13.9) |
| **Nmap** | **0 on a completed scan regardless of findings** — the one tool where the exit code is a clean success signal |
| Dependency-Check, Checkov | conventional |

Every adapter decides from parsed output. The only tool whose exit code may gate
success is Nmap.

### 13.13 Timeouts: most tools have no whole-scan cap

Nikto's `-timeout` is **per-request**. Nmap has `--host-timeout` and
`--script-timeout` but no total cap. testssl.sh has `--connect-timeout` and
`--openssl-timeout` but no total cap. Only Trivy (`--timeout`) and sqlmap
(`--time-limit`) cap total wall-clock.

So §8's "per-tool timeouts so one hung scanner can't stall the run" **cannot be
delegated to the tools**. `base.run_tool`'s own `subprocess` timeout is the real
enforcement for Nikto, Nmap and testssl; their native flags are a refinement, not
the guard.

### 13.14 `run()` returns a tuple, not a path

Section 3's `run(target, outdir, opts) -> raw_path | None` was underspecified,
and nine adapters written in parallel against it would each have invented their
own convention — which `routine` would then have had to normalize across. The
contract is:

```python
run(target, outdir, opts) -> tuple[str | None, base.ToolResult]
```

`(raw_path, result)` on a successful invocation, `(None, result)` when the tool
did not run or wrote no output. The `ToolResult` is always returned, including
on failure, because it carries `timed_out`, `returncode` and `stderr` — the only
source for the `error:timeout` / `error:<message>` cells the run manifest needs.

Three adapters vary in what the path denotes, and each states it in its module
docstring: `depcheck` writes into an `--out` directory and returns the resolved
`dependency-check-report.json`; `sqlmap` returns a session **directory** rather
than a file; `trivy` must indicate which kind a given call served, since the
coverage table holds one cell per `(target, tool)`.

A declined active scan is `skipped-active`, never `error`. Conflating the two
would make a deliberately-declined sqlmap indistinguishable from a broken one.
