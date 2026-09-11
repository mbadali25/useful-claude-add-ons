# Gizmoduck multi-scanner routine — design spec

**Date:** 2026-09-10
**Status:** Draft for review
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
- Integrate nine additional scanners alongside Nuclei (see §4).
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
    trivy.py  depcheck.py  checkov.py  tfsec.py  sqlmap.py
```

**Adapter protocol** (`scanners/base.py`) — every tool module implements:
- `NAME`, `KINDS` (which target kinds it applies to), `ACTIVE` (bool: sends
  attack traffic), `DEFAULT_ENABLED` (bool).
- `is_available() -> bool` — binary/image present.
- `run(target, outdir, opts) -> raw_path | None` — invoke the tool, write native
  output under `outdir`, return its path (or None on skip).
- `parse(raw_path, target) -> list[Finding]` — normalize native output.

`gizmoduck.py` imports the package and adds one subcommand; nothing else in its
existing command set changes.

## 4. Tools, invocation, output → normalization

| Tool | Kind(s) | Native output | Severity source | Active? |
|---|---|---|---|---|
| Nuclei | web, host | JSONL (existing) | template `info.severity` | no |
| OWASP ZAP | web | JSON (`-J`) | alert `riskcode` (0–3) | baseline=no, active=yes (opt-in) |
| Nikto | web | JSON (`-Format json`) | none → heuristic (`medium`/`info`) | no |
| Nmap + NSE | web, host | XML (`-oX`) | ports=`info`; `vuln` NSE→map | safe=no, `vuln`=opt-in |
| testssl.sh | web, host | JSON (`--jsonfile`) | `severity` field | no |
| Trivy | deps | JSON (`--format json`) | `Severity` | no |
| Dependency-Check | deps | JSON (`--format JSON`) | CVSS→band | no |
| Checkov | iac | JSON (`-o json`) | check `severity` (else `medium`) | no |
| tfsec | iac | JSON (`--format json`) | `severity` | no |
| sqlmap | web (gated) | session/log + `--results-file` CSV | confirmed injection=`high`/`critical` | **yes (opt-in + confirm)** |

**Severity map (`normalize.py`)** → gizmoduck's five levels
`critical/high/medium/low/info`:
- ZAP riskcode 3→high, 2→medium, 1→low, 0→info (ZAP has no "critical"; a
  High with confidence High stays high).
- CVSS band (Dependency-Check): ≥9.0 critical, ≥7.0 high, ≥4.0 medium, >0 low,
  else info.
- Text levels (testssl/Trivy/tfsec/Checkov/Nmap-vuln): case-insensitive map;
  unknown → `info` and flagged `unknown` in the raw field.
- Nikto: no severity model → default `medium` for its reported vulns, `info`
  for banner/version items, with a comment noting the assignment is heuristic.

**Finding shape** — identical keys to today's Nuclei finding dict, plus:
- `tool` — originating tool name.
- `template-id` — synthetic `"<tool>:<rule-or-plugin-id>"` so `dedupe()` (which
  keys on `template-id`) works across tools without collision.
- `target` — the manifest target it came from.

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
- `iac` → checkov, tfsec
- `deps` → trivy, depcheck

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
- New optional grouping: **by target, then by category/tool**, when the input
  carries `target`/`tool` fields (the existing flat mode stays for plain Nuclei
  JSONL).
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
  testssl.sh, trivy, checkov, tfsec, dependency-check, sqlmap, and ZAP (prefer
  the `zaproxy/zap-stable` Docker image; fall back to a local ZAP if Docker is
  absent). Each install is independent — one failure doesn't abort the rest.
- `doctor`: report present/missing for every tool (and Docker for ZAP), with a
  one-line install hint per missing tool. Exit non-zero only if *core* (nuclei)
  is missing; the rest are reported as gaps, not failures.

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

## 12. Open questions for review

1. Manifest format: YAML (this spec) vs. reuse the existing plain-text targets
   file with a sidecar for kinds. YAML chosen for the per-target options; confirm.
2. ZAP delivery: Docker image (portable, needs Docker) vs. local ZAP install.
   Spec prefers Docker with local fallback; confirm the environment has Docker.
3. Both-tools-per-category is in scope (Trivy+Dependency-Check, Checkov+tfsec) —
   confirm we want the overlap deduped into one section per category rather than
   shown per tool.
