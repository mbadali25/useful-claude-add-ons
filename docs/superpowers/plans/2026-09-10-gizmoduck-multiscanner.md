# Gizmoduck Multi-Scanner Routine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give gizmoduck a `routine` command that runs nine security scanners across a manifest of targets and merges everything into one report with an explicit coverage table.

**Architecture:** A new `scripts/scanners/` package holds one adapter per tool behind a four-method protocol (`is_available`/`run`/`parse` plus module constants), so each tool's quirks stay isolated and testable offline from captured fixtures. `normalize.py` owns the finding shape and every severity mapping. `routine.py` owns manifest parsing and orchestration. The existing single-scanner commands are not touched.

**Tech Stack:** Python 3 (stdlib subprocess/json/xml/csv/sqlite3), `pyyaml` for the manifest, pytest for tests, wkhtmltopdf (Qt WebKit 4.8) for PDF rendering.

**Spec:** `docs/superpowers/specs/2026-09-10-gizmoduck-multiscanner-design.md` (commit `fe52c6c0`). Read §13 first — it supersedes §§3–9 wherever they conflict.

## Global Constraints

Every task's requirements implicitly include this section.

- **Plugin root:** `plugin/gizmoduck/`. All paths below are relative to it.
- **Additive only.** `scan`, `summary`, `report`, `tickets`, `diff`, `doctor`, `update` must produce byte-for-byte identical output for plain Nuclei input. This is the acceptance bar for every task that touches an existing file.
- **Finding dict keys** (exact, from `gizmoduck.py:144-173`): `template_id, name, severity, severity_name, type, timestamp, host, matched_at, cve, cvss, description, remediation, reference, tags`. New keys added by this work: `tool`, `target`, `tools`, `merged_from`.
- **`severity` is an int**, `severity_name` is the display string. Canonical maps: `SEV_NUM`, `SEV_NAME`, `SEV_COLOR`, `ORDER=[4,3,2,1,0]` at `gizmoduck.py:38-41`.
- **Severity vocabulary:** `critical`(4) `high`(3) `medium`(2) `low`(1) `info`(0). No other values.
- **Never infer findings from an exit code.** Six of the nine tools mislead here (spec §13.12): Nikto exits **non-zero regardless of outcome**; testssl.sh reserves **50–200 for a severity-scored exit**; Trivy and sqlmap exit **0 with findings present**; ZAP's Automation Framework codes track job errors, not alert risk. **Nmap is the only tool whose exit code is a clean success signal.** Every adapter decides from parsed output.
- **`base.run_tool`'s timeout is the real guard** (spec §13.13). Nikto's `-timeout` is per-request; Nmap and testssl.sh have per-host/per-check caps but no total cap. Only Trivy and sqlmap cap total wall-clock. Never rely on a tool's own flag to stop a hung scan.
- **Detail floor exists twice** — `REPORT_DETAIL_FLOOR`/`detail_floor()` (`gizmoduck.py:50`, `204-210`) and `ACTION_THRESHOLD` (`report_template.py:34`). Any report change must satisfy both.
- **PDF is Qt WebKit 4.8.** No flexbox, no CSS grid, no custom properties. Tables and floats only. Verify in the PDF, not a browser.
- **No `__init__.py` exists in `scripts/` today.** Imports rely on the script's own directory heading `sys.path`, with a `spec_from_file_location` fallback at `gizmoduck.py:274-291`. Follow that pattern; do not assume a package import works.
- **Nine tools:** nuclei, zap, nikto, nmap, testssl, trivy (serves both `deps` and `iac`), depcheck, checkov, sqlmap. **No tfsec** — dropped as deprecated (§13.4).
- **Active tools** (`ACTIVE=True`, `DEFAULT_ENABLED=False`): sqlmap. sqlmap additionally requires an explicit confirm token at routine level.
- **Two adapters are active only in one of their two modes** — Nmap (safe vs `vuln` NSE) and ZAP (baseline vs active scan). A single module-level `ACTIVE` flag cannot express that: setting it `True` would wrongly gate the safe mode off by default, and `False` loses the record that the dangerous mode was available and declined. So those two carry **`ACTIVE_OPTS`** — a list of option keys whose presence makes the run active:

  ```python
  ACTIVE = False              # the default mode sends no attack traffic
  ACTIVE_OPTS = ["nmap_vuln"] # ...but this option does
  ```

  `routine` treats an adapter as active when `ACTIVE` is true **or** any key in `ACTIVE_OPTS` is set for that target, and the run manifest records the **mode actually used**, not just ran/skipped: `ran(safe)` vs `ran(safe+vuln)`, `ran(baseline)` vs `ran(baseline+active)`.

  This matters for the coverage table specifically. A cell reading a bare `ran` for Nmap would imply vulnerability coverage that a safe-only scan never attempted — which is the same false-assurance failure the coverage table exists to prevent, just one level finer. Adapters with a single mode set `ACTIVE_OPTS = []`.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/normalize.py` | **Create.** The finding shape, every severity mapping, synthetic `template_id` construction. Pure functions, no I/O. |
| `scripts/scanners/__init__.py` | **Create.** Registry: `KIND_DEFAULTS` (kind → adapter names) and `ADAPTERS` (name → module). Nothing else. |
| `scripts/scanners/base.py` | **Create.** Adapter protocol docstring, `run_tool()` subprocess+timeout helper, `which()` availability helper. |
| `scripts/scanners/<tool>.py` | **Create ×9.** One per tool. Each owns its command construction and its parser. No cross-imports between adapters. |
| `scripts/routine.py` | **Create.** Manifest parse + validation, target→adapter resolution, orchestration loop, run-manifest writing. |
| `scripts/gizmoduck.py` | **Modify.** Target-aware `dedupe()`; `routine` added to the `choices` list and the dispatch chain; combined-report grouping in the Markdown path. |
| `scripts/report_template.py` | **Modify.** Coverage table + target/category grouping for HTML/PDF. |
| `scripts/_test/conftest.py` | **Create.** `fixture_path()` helper and the plugin-root anchor, so tests stop hardcoding directory depth. |
| `scripts/_test/fixtures/<tool>.<ext>` | **Create ×9.** Captured native output per tool. Offline, no binaries needed. |
| `bootstrap.sh` / `bootstrap.ps1` | **Modify.** Restructure from fail-fast to per-tool independent installs. |
| `commands/routine.md`, `skills/gizmoduck/SKILL.md`, `.claude-plugin/plugin.json` | **Modify.** New command doc, skill description, version bump. |

---

## Task 1: Test harness foundation

Nothing else can be tested until there is a fixtures convention. Today there is no `conftest.py`, no `pytest.ini`, no `pyproject.toml`, and the one test file hardcodes `parent.parent` and `.parents[2]` for its paths.

**Files:**
- Create: `scripts/_test/conftest.py`
- Create: `scripts/_test/fixtures/.gitkeep`
- Create: `pytest.ini`

**Interfaces:**
- Consumes: nothing.
- Produces: `plugin_root() -> Path`, `scripts_dir() -> Path`, `fixture(name: str) -> Path` — pytest fixtures every later test uses instead of computing paths.

- [ ] **Step 1: Write the failing test**

```python
# scripts/_test/test_conftest.py
def test_fixture_helper_resolves_under_test_dir(fixture):
    p = fixture("sample.json")
    assert p.parent.name == "fixtures"
    assert p.parent.parent.name == "_test"

def test_plugin_root_contains_scripts(plugin_root):
    assert (plugin_root / "scripts" / "gizmoduck.py").is_file()
```

- [ ] **Step 2: Run it and verify it fails**

Run: `python -m pytest scripts/_test/test_conftest.py -v`
Expected: FAIL — `fixture 'fixture' not found`.

- [ ] **Step 3: Write conftest.py**

```python
# scripts/_test/conftest.py
"""Shared path anchors for the test suite.

Tests previously hardcoded directory depth (parent.parent, .parents[2]),
which breaks the moment a test moves a level deeper - and the scanners
package does exactly that. Anchor on a marker file instead.
"""
from pathlib import Path
import pytest


def _find_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".claude-plugin" / "plugin.json").is_file():
            return p
    raise RuntimeError("plugin root not found above %s" % start)


@pytest.fixture(scope="session")
def plugin_root() -> Path:
    return _find_root(Path(__file__).resolve())


@pytest.fixture(scope="session")
def scripts_dir(plugin_root: Path) -> Path:
    return plugin_root / "scripts"


@pytest.fixture(scope="session")
def fixture():
    base = Path(__file__).resolve().parent / "fixtures"
    def _get(name: str) -> Path:
        return base / name
    return _get
```

- [ ] **Step 4: Add pytest.ini at the plugin root**

```ini
[pytest]
testpaths = scripts/_test
python_files = test_*.py
addopts = -q
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest scripts/_test -v`
Expected: PASS — 2 new tests, plus the 8 existing `test_tickets_gate.py` tests still passing.

- [ ] **Step 6: Commit**

```bash
git add scripts/_test/conftest.py scripts/_test/test_conftest.py scripts/_test/fixtures/.gitkeep pytest.ini
git commit -m "test: add conftest path anchors and a fixtures convention"
```

---

## Task 2: normalize.py — severity mapping

The severity map is the single highest-risk piece of shared logic: every adapter depends on it, and a silent mis-band turns a Critical into an Info. It gets built first and tested exhaustively.

**Files:**
- Create: `scripts/normalize.py`
- Test: `scripts/_test/test_normalize.py`

**Interfaces:**
- Consumes: `SEV_NUM`/`SEV_NAME` semantics from `gizmoduck.py:38-41` (re-declared here, not imported — `normalize.py` must stay importable without pulling in the CLI).
- Produces:
  - `sev_from_text(value: str | None, default: str = "info") -> tuple[int, bool]` — returns `(severity_int, was_recognized)`.
  - `sev_from_cvss(score: float | None) -> int`
  - `sev_from_riskcode(code: int | str | None) -> tuple[int, bool]`
  - `synthetic_id(tool: str, rule_id: str) -> str`
  - `make_finding(**kwargs) -> dict` — produces the full 14-key shape plus `tool`/`target`, defaulting every absent key.

- [ ] **Step 1: Write the failing tests**

```python
# scripts/_test/test_normalize.py
import pytest
import normalize as n


@pytest.mark.parametrize("text,expected", [
    ("CRITICAL", 4), ("critical", 4),
    ("HIGH", 3), ("High", 3), ("IMPORTANT", 3),
    ("MEDIUM", 2), ("MODERATE", 2),
    ("LOW", 1), ("INFO", 0), ("INFORMATIONAL", 0),
])
def test_known_text_levels(text, expected):
    sev, known = n.sev_from_text(text)
    assert (sev, known) == (expected, True)


@pytest.mark.parametrize("text", [None, "", "UNKNOWN", "banana", "OK"])
def test_unknown_text_falls_back_and_flags(text):
    sev, known = n.sev_from_text(text)
    assert sev == 0 and known is False


def test_unknown_respects_explicit_default():
    # Checkov's null severity must land on medium, not info (spec 13.5).
    sev, known = n.sev_from_text(None, default="medium")
    assert sev == 2 and known is False


@pytest.mark.parametrize("score,expected", [
    (10.0, 4), (9.0, 4), (8.9, 3), (7.0, 3), (6.9, 2),
    (4.0, 2), (3.9, 1), (0.1, 1), (0.0, 0), (None, 0),
])
def test_cvss_bands_including_boundaries(score, expected):
    assert n.sev_from_cvss(score) == expected


@pytest.mark.parametrize("code,expected,known", [
    (3, 3, True), (2, 2, True), (1, 1, True), (0, 0, True),
    ("3", 3, True), (9, 0, False), (None, 0, False),
])
def test_riskcode_map_and_unexpected(code, expected, known):
    assert n.sev_from_riskcode(code) == (expected, known)


def test_synthetic_id_namespaces_by_tool():
    assert n.synthetic_id("zap", "10038") == "zap:10038"


def test_make_finding_has_every_required_key():
    f = n.make_finding(tool="trivy", target="repo", rule_id="CVE-1", name="x", severity=3)
    for key in ("template_id", "name", "severity", "severity_name", "type",
                "timestamp", "host", "matched_at", "cve", "cvss", "description",
                "remediation", "reference", "tags", "tool", "target"):
        assert key in f, key
    assert f["template_id"] == "trivy:CVE-1"
    assert f["severity_name"] == "high"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest scripts/_test/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'normalize'`.

Note: add `scripts/` to the test path by setting `pythonpath = scripts` under `[pytest]` in `pytest.ini`, matching how `gizmoduck.py` gets its own directory on `sys.path` at runtime.

- [ ] **Step 3: Implement normalize.py**

```python
"""Finding shape and severity normalization shared by every scanner adapter.

Deliberately imports nothing from gizmoduck.py: adapters and their tests must
be loadable without the CLI. The severity ints are re-declared here and are
required to match SEV_NUM at gizmoduck.py:38-41 - test_normalize asserts the
values directly so a drift shows up as a test failure rather than as findings
quietly landing in the wrong band.
"""

SEV_NUM = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
SEV_NAME = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}

_TEXT_ALIASES = {
    "informational": "info",
    "moderate": "medium",   # Bridgecrew legacy
    "important": "high",    # Bridgecrew legacy
}

# ZAP riskcode. Treated as high-confidence inference, not documented fact
# (spec 13.3) - anything outside 0-3 is reported unknown rather than guessed.
_RISKCODE = {0: 0, 1: 1, 2: 2, 3: 3}


def sev_from_text(value, default="info"):
    """Map a tool's text severity to (int, was_recognized).

    was_recognized=False means the caller should mark the finding so a report
    reader can tell an assigned default from a real assessment.
    """
    if value is None:
        return SEV_NUM[default], False
    key = str(value).strip().lower()
    if not key:
        return SEV_NUM[default], False
    key = _TEXT_ALIASES.get(key, key)
    if key in SEV_NUM:
        return SEV_NUM[key], True
    return SEV_NUM[default], False


def sev_from_cvss(score):
    if score is None or score == "":
        return 0
    try:
        s = float(score)
    except (TypeError, ValueError):
        return 0
    if s >= 9.0:
        return 4
    if s >= 7.0:
        return 3
    if s >= 4.0:
        return 2
    if s > 0:
        return 1
    return 0


def sev_from_riskcode(code):
    try:
        c = int(code)
    except (TypeError, ValueError):
        return 0, False
    if c in _RISKCODE:
        return _RISKCODE[c], True
    return 0, False


def synthetic_id(tool, rule_id):
    return "%s:%s" % (tool, rule_id or "unknown")


def make_finding(tool, target, rule_id, name, severity,
                 severity_known=True, **extra):
    f = {
        "template_id": synthetic_id(tool, rule_id),
        "name": name or rule_id or "",
        "severity": severity,
        "severity_name": SEV_NAME[severity],
        "type": extra.get("type", ""),
        "timestamp": extra.get("timestamp", ""),
        "host": extra.get("host", ""),
        "matched_at": extra.get("matched_at", ""),
        "cve": extra.get("cve") or [],
        "cvss": extra.get("cvss", ""),
        "description": extra.get("description", "") or "",
        "remediation": extra.get("remediation", "") or "",
        "reference": extra.get("reference") or [],
        "tags": extra.get("tags") or [],
        "tool": tool,
        "target": target,
    }
    if not severity_known:
        f["tags"] = list(f["tags"]) + ["severity-assigned"]
    return f
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest scripts/_test/test_normalize.py -v`
Expected: PASS — all parametrized cases.

- [ ] **Step 5: Assert the map matches gizmoduck.py**

Add to `test_normalize.py`:

```python
def test_severity_ints_match_gizmoduck(scripts_dir):
    import importlib.util
    spec = importlib.util.spec_from_file_location("gz", scripts_dir / "gizmoduck.py")
    gz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gz)
    assert gz.SEV_NUM == n.SEV_NUM
    assert gz.SEV_NAME == n.SEV_NAME
```

Run: `python -m pytest scripts/_test/test_normalize.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/normalize.py scripts/_test/test_normalize.py pytest.ini
git commit -m "feat: add normalize.py with the shared severity map and finding shape"
```

---

## Task 3: Target-aware dedupe

This fixes the defect in §13.1. It must go in before any adapter produces multi-target data, because until it lands a combined run silently merges findings across sites.

**Files:**
- Modify: `scripts/gizmoduck.py:176-190` (`dedupe`)
- Test: `scripts/_test/test_dedupe.py`

**Interfaces:**
- Produces: `dedupe(findings) -> list[dict]` — unchanged signature, changed key.

- [ ] **Step 1: Write the failing test**

```python
# scripts/_test/test_dedupe.py
import importlib.util
import pytest


@pytest.fixture(scope="module")
def gz(scripts_dir):
    spec = importlib.util.spec_from_file_location("gz", scripts_dir / "gizmoduck.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _f(tid, matched, target=None):
    d = {"template_id": tid, "matched_at": matched, "host": matched,
         "severity": 0, "severity_name": "info", "name": tid}
    if target is not None:
        d["target"] = target
    return d


def test_same_template_different_targets_stay_separate(gz):
    out = gz.dedupe([_f("nuclei:tls-version", "a.example", "site-a"),
                     _f("nuclei:tls-version", "b.example", "site-b")])
    assert len(out) == 2
    assert {g["target"] for g in out} == {"site-a", "site-b"}


def test_same_template_same_target_still_merges(gz):
    out = gz.dedupe([_f("nuclei:tls-version", "a.example/1", "site-a"),
                     _f("nuclei:tls-version", "a.example/2", "site-a")])
    assert len(out) == 1
    assert out[0]["instances"] == 2


def test_no_target_field_preserves_legacy_behaviour(gz):
    """Plain Nuclei findings carry no target - must merge exactly as before."""
    out = gz.dedupe([_f("nuclei:x", "a.example"), _f("nuclei:x", "b.example")])
    assert len(out) == 1
    assert out[0]["raw_count"] == 2
    assert out[0]["affected"] == ["a.example", "b.example"]
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest scripts/_test/test_dedupe.py -v`
Expected: `test_same_template_different_targets_stay_separate` FAILS with `assert 1 == 2`. The other two PASS — which is the point: they are the regression guard.

- [ ] **Step 3: Change the dedupe key**

Replace the `groups.setdefault` line at `gizmoduck.py:179`:

```python
def dedupe(findings):
    groups = {}
    for f in findings:
        # Key on (target, template_id), not template_id alone. A combined
        # routine run holds many targets in one findings list, and keying on
        # the template alone collapsed the same template across every site -
        # which also made the per-target report grouping impossible. Plain
        # Nuclei findings carry no `target`, so they key on (None, id) and
        # group exactly as they always have.
        key = (f.get("target"), f["template_id"])
        g = groups.setdefault(key, {**f, "affected": [], "raw_count": 0})
        g["affected"].append(f["matched_at"] or f["host"])
        g["raw_count"] += 1
    for g in groups.values():
        g["affected"] = sorted(set(a for a in g["affected"] if a))
        g["instances"] = len(g["affected"])
    return list(groups.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest scripts/_test -v`
Expected: PASS — all 3 new tests plus the 8 existing gate tests.

- [ ] **Step 5: Prove byte-for-byte compatibility on real input**

Run against a real Nuclei JSONL and diff:

```bash
python scripts/gizmoduck.py report <existing-findings.jsonl> --format md --out /tmp/after.md
git stash && python scripts/gizmoduck.py report <existing-findings.jsonl> --format md --out /tmp/before.md && git stash pop
diff /tmp/before.md /tmp/after.md
```

Expected: no output from `diff`. If it differs, the change is wrong — stop and fix before continuing.

- [ ] **Step 6: Commit**

```bash
git add scripts/gizmoduck.py scripts/_test/test_dedupe.py
git commit -m "fix: key dedupe on (target, template_id) so a multi-target run stops collapsing across sites"
```

---

## Task 4: The adapter protocol (`scanners/base.py` + registry)

**Files:**
- Create: `scripts/scanners/__init__.py`, `scripts/scanners/base.py`
- Test: `scripts/_test/test_base.py`

**Interfaces:**
- Produces:
  - `base.which(binary: str) -> str | None`
  - `base.run_tool(argv: list[str], timeout: int, cwd=None) -> ToolResult` where `ToolResult` is a dataclass with `returncode: int`, `stdout: str`, `stderr: str`, `timed_out: bool`. **Never raises on non-zero exit** — callers decide.
  - `scanners.KIND_DEFAULTS: dict[str, list[str]]`
  - `scanners.ADAPTERS: dict[str, module]`
  - `scanners.get(name) -> module`

- [ ] **Step 1: Write the failing tests**

```python
# scripts/_test/test_base.py
import sys
from scanners import base


def test_run_tool_returns_nonzero_without_raising():
    r = base.run_tool([sys.executable, "-c", "import sys; sys.exit(3)"], timeout=10)
    assert r.returncode == 3 and r.timed_out is False


def test_run_tool_marks_timeout_instead_of_hanging():
    r = base.run_tool([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
    assert r.timed_out is True


def test_which_returns_none_for_missing_binary():
    assert base.which("definitely-not-a-real-binary-xyz") is None


def test_registry_lists_nine_tools_and_no_tfsec():
    import scanners
    assert len(scanners.ADAPTERS) == 9
    assert "tfsec" not in scanners.ADAPTERS
    assert set(scanners.KIND_DEFAULTS) == {"web", "host", "iac", "deps"}


def test_every_registered_adapter_satisfies_the_protocol():
    import scanners
    for name, mod in scanners.ADAPTERS.items():
        for attr in ("NAME", "KINDS", "ACTIVE", "DEFAULT_ENABLED",
                     "is_available", "run", "parse"):
            assert hasattr(mod, attr), "%s missing %s" % (name, attr)
        assert mod.NAME == name
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest scripts/_test/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scanners'`.

- [ ] **Step 3: Implement base.py**

```python
"""Shared plumbing for scanner adapters.

run_tool never raises on a non-zero exit and never infers success from one:
Trivy exits 0 with findings present unless --exit-code is passed, sqlmap
exits 0 whether or not it found an injection, and ZAP's documented 0/1/2/3
contract belongs to its Docker wrapper rather than the Automation Framework
we actually invoke. Every adapter decides from parsed output, not status.
"""
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def which(binary):
    return shutil.which(binary)


def run_tool(argv, timeout, cwd=None):
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd, check=False)
        return ToolResult(p.returncode, p.stdout or "", p.stderr or "", False)
    except subprocess.TimeoutExpired as e:
        return ToolResult(-1, e.stdout or "", e.stderr or "", True)
    except FileNotFoundError as e:
        return ToolResult(-1, "", str(e), False)
```

- [ ] **Step 4: Implement the registry**

```python
# scripts/scanners/__init__.py
"""Adapter registry. Kind -> default adapter names, and name -> module.

No tfsec: its engine was folded into Trivy in 2023 and its rules stopped
moving in 2025, so IaC coverage runs through trivy's misconfig scanner
instead (spec 13.4).
"""
from . import (nuclei, zap, nikto, nmap, testssl,
               trivy, depcheck, checkov, sqlmap)

ADAPTERS = {m.NAME: m for m in
            (nuclei, zap, nikto, nmap, testssl, trivy, depcheck, checkov, sqlmap)}

KIND_DEFAULTS = {
    "web":  ["nuclei", "zap", "nikto", "nmap", "testssl"],
    "host": ["nuclei", "nmap", "testssl"],
    "iac":  ["checkov", "trivy"],
    "deps": ["trivy", "depcheck"],
}


def get(name):
    if name not in ADAPTERS:
        raise KeyError("unknown scanner %r; known: %s"
                       % (name, ", ".join(sorted(ADAPTERS))))
    return ADAPTERS[name]
```

Note: this imports all nine adapter modules, so it cannot pass until Tasks 5–13 exist. Create the nine files as minimal stubs in this task carrying only their constants and `NotImplementedError` bodies, so the protocol test passes and each later task fills one in.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest scripts/_test/test_base.py -v`
Expected: PASS — including the protocol conformance test across all nine stubs.

- [ ] **Step 6: Commit**

```bash
git add scripts/scanners/
git commit -m "feat: add the scanner adapter protocol, registry, and nine stubs"
```

---

## Tasks 5–13: One adapter per tool

**These nine tasks are mutually independent** — each touches exactly one file plus its own test and fixture, and none imports another. Run them in parallel.

Every adapter task follows the identical five-step shape below. The per-tool table that follows gives the only things that differ.

**Files (per task):**
- Modify: `scripts/scanners/<tool>.py` (from stub to implementation)
- Create: `scripts/_test/fixtures/<tool>.<ext>`
- Test: `scripts/_test/test_scanner_<tool>.py`

**Interfaces (per task):**
- Consumes: `normalize.make_finding`, `normalize.sev_from_*`, `base.run_tool`, `base.which`.
- Produces: `NAME`, `KINDS`, `ACTIVE`, `DEFAULT_ENABLED`, `is_available()`, `run(target, outdir, opts)`, `parse(raw_path, target)`.

**The five steps, for every adapter:**

- [ ] **Step 1:** Capture a real native output sample into `scripts/_test/fixtures/<tool>.<ext>`. If the tool is not installed, hand-build the fixture from the schema cited in spec §13 — it must contain at minimum one finding at each of two different severities, and one malformed/absent-severity entry.
- [ ] **Step 2:** Write `test_scanner_<tool>.py` asserting: the finding count, the severity of each parsed finding, that `template_id` is `"<tool>:<rule-id>"`, that `target` is set from the argument, and the tool-specific edge case named in the table.
- [ ] **Step 3:** Run it; verify it fails with `NotImplementedError`.
- [ ] **Step 4:** Implement `run()` and `parse()`. `run()` builds argv and calls `base.run_tool`; `parse()` is pure — it reads the file and returns findings, with no subprocess and no network, so the test needs neither the binary nor connectivity.
- [ ] **Step 5:** Run the test, verify PASS, and commit as `feat(scanners): add the <tool> adapter`.

### Per-tool specifics

| # | Tool | KINDS | ACTIVE | Native file | Command core | Severity source | **Edge case the test MUST cover** |
|---|---|---|---|---|---|---|---|
| 5 | `nuclei` | web, host | False | `nuclei.jsonl` | reuse `cmd_scan`'s existing argv (`gizmoduck.py:63`) | `info.severity` via `sev_from_text` | Byte-identical findings to today's `load()` for the same input — assert against `gizmoduck.load()` directly |
| 6 | `zap` | web | active only | `zap.json` | `zap.bat -cmd -autorun <plan>.yaml`, plan has a `report` job `template: traditional-json` | `riskcode` via `sev_from_riskcode` | `site[].alerts[].instances[]` fan-out — one alert with 3 instances must yield 3 `matched_at` values, and a `riskcode` of 9 must land `info` + `severity-assigned`. **Before writing the parser, run both the AF `report` job and a standalone `-J` once and diff the JSON structurally** — spec §13.11 could not confirm they match, and one parser serving both paths depends on it |
| 7 | `nikto` | web | False | `nikto.csv` | `nikto -h <url> -Format csv -output <file>` | none — heuristic | **No severity field exists.** Every finding is `medium` unless the message matches a banner/version pattern → `info`, and all carry `severity-assigned`. **Nikto exits non-zero even on success** (issue #837) — decide success by whether the output file has parseable content, never by status |
| 8 | `nmap` | web, host | `vuln` NSE only | `nmap.xml` | `nmap -oX <file> -sV <host>`; `--script vuln` only when `opts.nmap_vuln` | open ports → `info`; vulns.lua `state` via `sev_from_text` | An open port with no script yields `info`. A `<script>` with a nested `<table>`/`<elem key=...>` yields its own finding. States: `VULNERABLE`, `VULNERABLE (DoS)`, `VULNERABLE (Exploitable)`, `LIKELY VULNERABLE` — `NOT VULNERABLE` is not a finding. **Lock the elem key paths against one real `--script vuln -oX` run first**; §13.11's key names are secondhand |
| 9 | `testssl` | web, host | False | `testssl.json` | `testssl.sh --jsonfile <file> <host>` — **not `--jsonfile-pretty`**, which can emit invalid JSON (issue #1699) | `severity` field via `sev_from_text` | Enum is eight values: `OK, INFO, LOW, MEDIUM, HIGH, CRITICAL, WARN, FATAL`. **`WARN` and `FATAL` are scan errors, not target findings** — they must be recorded as a tool error in the run manifest and MUST NOT become findings, or a broken scan reports as a vulnerability. `OK`/`INFO` map to `info` |
| 10 | `trivy` | deps, iac | False | `trivy.json` | `trivy fs --format json --scanners vuln` (deps) or `--scanners misconfig` (iac), always `--timeout` | `Severity` via `sev_from_text` | **One adapter, two kinds**: `Results[]` may carry `Vulnerabilities[]` and `Misconfigurations[]` in one file — parse only the array matching the kind. `UNKNOWN` → `info` + `severity-assigned`. Exit code 0 with findings must still yield findings |
| 11 | `depcheck` | deps | False | `depcheck.json` | `dependency-check --format JSON --out <dir> --scan <path>` | fallback chain | **CVSS v3 absent**: a vulnerability with `severity: "HIGH"` and no `cvssv3` block must still resolve to 3. Order: text `severity` → `cvssv2.score` → `cvssv3.baseScore` |
| 12 | `checkov` | iac | False | `checkov.json` | `checkov -d <path> -o json` | `severity` with `default="medium"` | **Two shapes**: the fixture must be a JSON *array* of framework reports; a single-object fixture is a second test case. Every `failed_checks` entry has `severity: null` → `medium` + `severity-assigned`. `passed_checks` are ignored |
| 13 | `sqlmap` | web (gated) | **True** | `sqlmap-session/` | `sqlmap -u <url> --batch --time-limit=<n> --output-dir=<dir>` | confirmed injection → `high`; stacked/UNION with DB access → `critical` | **No JSON exists.** Parse `session.sqlite` / the target `log` for a persisted injection `Type` + `Payload`. A run with no persisted injection yields **zero findings**, not a low-severity one — and exit code 0 proves nothing |

---

## Task 14: routine.py — manifest parsing and the authorization gate

**Files:**
- Create: `scripts/routine.py`
- Test: `scripts/_test/test_routine_manifest.py`
- Create: `scripts/_test/fixtures/manifest-valid.yaml`, `manifest-no-auth.yaml`

**Interfaces:**
- Produces: `load_manifest(path) -> Manifest`, `resolve_adapters(target, registry) -> list[str]`, `AuthorizationError`.

- [ ] **Step 1: Write the failing tests**

```python
# scripts/_test/test_routine_manifest.py
import pytest
import routine


def test_missing_authorized_by_is_refused(fixture):
    with pytest.raises(routine.AuthorizationError):
        routine.load_manifest(fixture("manifest-no-auth.yaml"))


def test_empty_authorized_by_is_refused(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text('authorized_by: ""\ntargets: [{name: a, kind: web, url: "http://a"}]\n')
    with pytest.raises(routine.AuthorizationError):
        routine.load_manifest(p)


def test_kind_drives_the_default_adapter_list(fixture):
    m = routine.load_manifest(fixture("manifest-valid.yaml"))
    web = [t for t in m.targets if t.kind == "web"][0]
    assert routine.resolve_adapters(web) == ["nuclei", "zap", "nikto", "nmap", "testssl"]


def test_sqlmap_is_absent_unless_opted_in(fixture):
    m = routine.load_manifest(fixture("manifest-valid.yaml"))
    web = [t for t in m.targets if t.kind == "web"][0]
    assert "sqlmap" not in routine.resolve_adapters(web)
    web.options["sqlmap"] = True
    assert "sqlmap" in routine.resolve_adapters(web)


def test_unknown_kind_is_an_error_not_an_empty_list(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text('authorized_by: "me"\ntargets: [{name: a, kind: spaceship}]\n')
    with pytest.raises(ValueError, match="spaceship"):
        routine.load_manifest(p)
```

- [ ] **Step 2:** Run; verify failure (`No module named 'routine'`).
- [ ] **Step 3:** Implement `load_manifest` (yaml.safe_load, validate `authorized_by` non-empty, validate every `kind` against `KIND_DEFAULTS`, build `Target` dataclasses) and `resolve_adapters` (kind default, then `tools` override, then `options` gates for active tools).
- [ ] **Step 4:** Run tests; verify PASS.
- [ ] **Step 5:** Commit as `feat: add routine manifest parsing with a mandatory authorization gate`.

An unknown `kind` raising rather than returning an empty adapter list is deliberate: an empty list would run zero tools and report a clean target, which is the same false-assurance failure the coverage table exists to prevent.

---

## Task 15: routine.py — orchestration

**Files:**
- Modify: `scripts/routine.py`
- Test: `scripts/_test/test_routine_orchestration.py`

**Interfaces:**
- Produces: `run_routine(manifest, outdir, registry=None, confirm=None) -> RunManifest`. The `registry` parameter exists so tests inject fake adapters — no real scanner is ever invoked by a test.

- [ ] **Step 1: Write the failing tests**

```python
def test_missing_tool_is_recorded_as_skipped_not_silently_dropped(fake_registry):
    ...
    assert rm.status("site-a", "nikto") == "skipped-missing"


def test_active_tool_not_opted_in_is_skipped_with_its_own_status(fake_registry):
    assert rm.status("site-a", "sqlmap") == "skipped-active"


def test_a_tool_that_raises_records_an_error_and_the_run_continues(fake_registry):
    assert rm.status("site-a", "zap").startswith("error")
    assert rm.status("site-a", "nuclei") == "ran"


def test_a_tool_that_times_out_records_error_timeout(fake_registry):
    assert rm.status("site-a", "testssl") == "error:timeout"


def test_findings_are_combined_with_tool_and_target_set(fake_registry, tmp_path):
    lines = (tmp_path / "findings.jsonl").read_text().splitlines()
    recs = [json.loads(l) for l in lines]
    assert {r["target"] for r in recs} == {"site-a", "site-b"}
    assert all(r["tool"] for r in recs)


def test_sqlmap_does_not_run_without_the_confirm_token(fake_registry):
    assert rm.status("site-a", "sqlmap") != "ran"
```

- [ ] **Step 2:** Run; verify failure.
- [ ] **Step 3:** Implement the orchestration loop per spec §6, writing `<out>/<target>/<tool>.<ext>` natives, one combined `<out>/findings.jsonl`, and `<out>/run-manifest.json` with per-cell status, duration and count.
- [ ] **Step 4:** Run tests; verify PASS.
- [ ] **Step 5:** Commit as `feat: add routine orchestration with a per-cell run manifest`.

**The four statuses are not interchangeable** and each needs its own test: `ran`, `skipped-missing`, `skipped-active`, `error:<reason>`. Collapsing "we didn't run it" into "we found nothing" is the exact failure that made a previous scan of `registration.thdmarketplace.com` report zero findings when it had actually been blocked by a WAF.

---

## Task 16: Coverage table and target grouping — Markdown path

**Files:**
- Modify: `scripts/gizmoduck.py` (`cmd_report`, `detail_floor` region `204-240`)
- Test: `scripts/_test/test_report_grouping.py`
- Create: `scripts/_test/fixtures/combined-findings.jsonl`, `run-manifest.json`

- [ ] **Step 1:** Write tests asserting: a combined input renders one section per target; each target's tools appear as one section per category; the coverage table has one row per target and one column per tool; a `skipped-missing` cell renders visibly differently from a `ran` cell with zero findings; and a plain Nuclei JSONL with no `target` field renders the **existing flat format unchanged**.
- [ ] **Step 2:** Run; verify the grouping tests fail and the flat-format regression test passes.
- [ ] **Step 3:** Implement grouping keyed on the presence of `target`/`tool` fields, plus the coverage table read from `run-manifest.json`.
- [ ] **Step 4:** Run tests; verify PASS. Re-run the Task 3 Step 5 byte-for-byte diff.
- [ ] **Step 5:** Commit.

---

## Task 17: Coverage table — HTML/PDF path

**Files:**
- Modify: `scripts/report_template.py` (`render_report`, `316-363`)
- Test: `scripts/_test/test_report_html.py`

- [ ] **Step 1:** Write tests asserting the coverage table appears in the HTML and that `ACTION_THRESHOLD` still floors detail at Medium for combined input.
- [ ] **Step 2:** Run; verify failure.
- [ ] **Step 3:** Implement using **`<table>` markup only** — no flexbox, no grid, no CSS custom properties. Qt WebKit 4.8 silently ignores all three, so a browser-correct layout can render as a broken one in the PDF.
- [ ] **Step 4:** Run tests; verify PASS. **Then render an actual PDF and open it** — the automated test only checks the Markdown/HTML string.
- [ ] **Step 5:** Commit.

---

## Task 18: Cross-tool merge for deps and iac

**Files:**
- Modify: `scripts/normalize.py` (add `merge_category`)
- Test: `scripts/_test/test_merge.py`

- [ ] **Step 1:** Write tests: two `deps` findings sharing `(CVE, package, version)` merge into one with `tools == ["depcheck", "trivy"]` and the **higher** severity; two `iac` findings sharing `(path, line, resource)` merge despite different `check_id`s; a finding with no CVE never merges; and two findings whose normalized titles share no token stay separate with a near-miss recorded.
- [ ] **Step 2:** Run; verify failure.
- [ ] **Step 3:** Implement `merge_category`, populating `tools` and `merged_from`.
- [ ] **Step 4:** Run; verify PASS.
- [ ] **Step 5:** Commit.

The token-overlap guard is asymmetric on purpose: a duplicate finding costs a reader half a minute, a wrong merge hides a real vulnerability.

---

## Task 19: CLI wiring

**Files:**
- Modify: `scripts/gizmoduck.py:449-450` (choices list), `511-594` (dispatch chain)
- Create: `scripts/gizmoduck.py` `cmd_routine()`
- Test: `scripts/_test/test_cli_routine.py`

- [ ] **Step 1:** Write a test invoking `python gizmoduck.py routine --help` as a subprocess (matching the existing harness style at `test_tickets_gate.py:55`) and asserting exit 0; plus a test that `routine` without a manifest exits non-zero with an authorization message.
- [ ] **Step 2:** Run; verify failure — `argparse` rejects `routine` as an invalid choice.
- [ ] **Step 3:** Add `"routine"` to the `choices` list and an `elif a.command == "routine":` branch. Import `routine.py` using the same `spec_from_file_location` fallback as `report_template` (`gizmoduck.py:274-291`) — a plain import will not resolve when the script is invoked by absolute path.
- [ ] **Step 4:** Run the full suite; verify PASS.
- [ ] **Step 5:** Commit.

---

## Task 20: bootstrap — restructure to independent installs

**Files:**
- Modify: `bootstrap.sh` (lines 10-38), `bootstrap.ps1` (lines 9-39)

Both are currently single fail-fast scripts (`set -euo pipefail`). Spec §9 requires one failed install not to abort the rest — that is a restructure, not an addition.

- [ ] **Step 1:** Extract each tool's install into its own function, wrapped so a failure logs and continues.
- [ ] **Step 2:** Keep the **one existing exception**: a failed Nuclei template download still aborts, because a template-less Nuclei reports zero findings silently. Add a comment saying so, or the next reader will "fix" it.
- [ ] **Step 3:** Add installs for nmap, nikto, testssl.sh, trivy, checkov, dependency-check, sqlmap, and ZAP. **ZAP needs Java 17+** — check for it and install a JRE first, or the ZAP install succeeds and ZAP itself never starts.
- [ ] **Step 4:** Run each script on a clean-ish machine and confirm one deliberately broken install does not stop the others.
- [ ] **Step 5:** Commit.

---

## Task 21: doctor — report every tool

**Files:**
- Modify: `scripts/gizmoduck.py:390-423` (`cmd_doctor`)
- Test: `scripts/_test/test_doctor.py`

- [ ] **Step 1:** Write a test asserting `doctor` exits **0** when only Nuclei and its templates are present, and that its output names every missing optional tool.
- [ ] **Step 2:** Run; verify failure.
- [ ] **Step 3:** Add a per-adapter `is_available()` loop. Preserve the existing exit logic exactly — only Nuclei and templates flip `ok` to false. For ZAP, report **which** delivery was found (`local`, `docker`, or missing), per spec §12.2: a bare "missing" hides that a Docker-only path can never resolve on this machine.
- [ ] **Step 4:** Run; verify PASS.
- [ ] **Step 5:** Commit.

---

## Task 22: Documentation and release

**Files:**
- Create: `commands/routine.md`
- Modify: `skills/gizmoduck/SKILL.md`, `.claude-plugin/plugin.json`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1:** Write `commands/routine.md` — commands are auto-discovered by directory convention, so the file's existence registers it; `plugin.json` needs no `commands` key.
- [ ] **Step 2:** Update `SKILL.md`'s description so the routine and its gating are discoverable. The description is what decides whether the skill ever fires.
- [ ] **Step 3:** Bump `plugin.json` version from `0.2.5` to `0.3.0` — new command, new dependency.
- [ ] **Step 4:** Document the **`pyyaml` dependency** and the authorization requirement in the README.
- [ ] **Step 5:** Add the CHANGELOG entry. Run the full suite one final time. Commit.

---

## Open items — all three answered (spec §13.11)

Schemas and exit-code contracts are now documented. What remains is **one lab
confirmation per tool**, folded into its own adapter task rather than blocking
anything:

| Confirmation | In task | Why it still matters |
|---|---|---|
| Lock the Nmap `<table>`/`<elem key=...>` paths against one real `--script vuln -oX` run | 8 | The vulns.lua field names are secondhand; a wrong path yields zero findings silently |
| Diff the ZAP AF `traditional-json` report against a standalone `-J` report | 6 | One parser serving both delivery paths depends on them matching, and no primary source asserts it |
| Confirm the testssl.sh severities a real run emits | 9 | The eight-value enum is confirmed, but `WARN`/`FATAL` handling is the correctness risk — they must not become findings |

Each is a five-minute check inside the task that needs it. None blocks another task.

---

## Self-review notes

- **Spec coverage:** §§3–11 each map to a task (§3→4–13, §4→2+5–13, §5→14, §6→15, §7→16–18, §8→14+15+20, §9→20–21, §10→every task's tests, §11→3+19+22). §13's ten corrections are each attached to the task that acts on them.
- **The one deliberate deviation from the spec:** §4's severity map for Nikto assigns `medium` to vulns and `info` to banners. Task 7 keeps that but adds a `severity-assigned` tag to every Nikto finding, because a heuristic severity presented identically to a real one is indistinguishable in the report.
- **Parallelism:** Tasks 1→2→3→4 are serial (each is the next one's contract). Tasks 5–13 are fully parallel. Tasks 14→15 are serial. 16, 17, 18 are parallel with each other. 19–22 are serial and last.
