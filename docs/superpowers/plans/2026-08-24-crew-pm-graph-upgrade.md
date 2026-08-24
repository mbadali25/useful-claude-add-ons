# crew Project Manager, Graph-Backed Onboarding, and v1 Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the crew plugin an always-present Project Manager, replace guessed
codemap structure with a real code graph exported to Obsidian, fix the
`find-skills` trigger collision, and upgrade existing v1 crew setups without
losing hand-written judgment.

**Architecture:** The PM's "always on" property comes from a `SessionStart` hook
whose stdout is injected as context — not from a subagent, which cannot
auto-load. Hook logic lives in two stdlib-only Python modules (`crew_state.py`
reads and evaluates, `pm_brief.py` renders); the `.sh` and `.ps1` files are thin
wrappers, so both platforms produce identical output by construction rather than
by parallel maintenance. graphify supplies mechanical structure (entry points,
callers, communities); `crew:explorer` agents are spawned only for judgment
(landmines, what breaks). One reconciliation module serves both
`/crew:upgrade` and `/crew:onboard --refresh`.

**Tech Stack:** Python 3.11+ standard library only (pylint 4 CI runs
`pylint $(git ls-files '*.py')` on 3.11/3.12/3.13 with third-party deps
deliberately absent); pytest for tests; bash + PowerShell hook wrappers;
`graphifyy` PyPI package (CLI `graphify`) as an optional external tool.

**Spec:** `docs/superpowers/specs/2026-08-24-crew-pm-graph-upgrade-design.md`

## Global Constraints

- **Python is stdlib-only.** CI installs no third-party packages. No `requests`,
  no `pyyaml`. `json`, `os`, `re`, `subprocess`, `argparse` only.
- **Python floor is 3.11.** pylint 4 requires >= 3.10; CI matrix is 3.11, 3.12, 3.13.
- **Every hook read fails soft.** A missing, empty, or malformed file yields an
  absent value, never an exception. A `SessionStart` hook that raises breaks
  every session opened in that repository.
- **Every hook exits 0.** Including on total failure.
- **Hook output is project information, not instructions.** Text framed as
  out-of-band commands trips prompt-injection defences and gets surfaced to the
  user rather than treated as context — see `hooks/scripts/handoff-read.sh:18-20`.
- **Ship every hook script in both flavours** — a `.sh` and a `.ps1` registered
  with `shell: powershell` — **and wire both in `hooks.json`**. A `.ps1` on disk
  that nothing references is dead code; a bash-only gate is silently inert on
  Windows, which reads as "the gate passed" rather than "the gate never ran".
  (`CLAUDE.md`, "New plugin under `plugin/`")
- **A plugin that registers hooks defaults to OFF in the install menu.**
- **Never commit a `marketplace.json` inside a plugin directory.**
- **Install scripts are a matched pair.** `scripts/install-prerequisites.sh` and
  `.ps1` must have identical menu keys, order, and default flags, or
  `--select 3,7` means different things per platform.
- **No skill description gets broadened.** Trigger breadth is the bug being
  fixed in Task 12; reintroducing it anywhere else fails the plan.
- **`SCHEMA_CURRENT = 2`.** A `.crew/config.json` with no `schema` key is v1.
- **Health thresholds, verbatim from `crew-scaling/SKILL.md`:** BLOCK+FIX per
  ticket `< 0.3` = review broken; `0.3`–`2.0` = healthy; `> 2.0` = tickets too
  large. Window is the last 10 review rows.
- **Metrics row format, verbatim from `commands/review.md:40`:**
  `<date> | <ticket> | <reviewer> | <n BLOCK> | <n FIX>`
- **Anchor honesty.** Bump a codemap `anchor:` only on a section actually
  re-verified in that run. A false freshness claim is worse than an honest stale
  one, because the entire freshness rule depends on the anchor being true.
- **Report, never auto-apply, a contradiction.** The graph can be wrong too:
  generated call sites, reflection, dynamic dispatch.
- **Obsidian writes are gated twice**: `graph.obsidian.confirmed == true` in
  config AND a scratch-directory proof run completed. Default target is
  `<vault>/codegraphs/<repo>/`, vault `C:\repos\claude-memories`.
- **graphify default build is code-only and keyless.** Docs, PDFs, and images
  require an LLM call and are opt-in with the key requirement stated at the
  point of choice.
- **Codex reviews every task** before its commit is considered done, using the
  invocation pattern already established in `commands/review.md:17-22`.

---

## File Structure

**Create — hook logic (Python, pylint-covered):**

| File | Responsibility |
|---|---|
| `plugin/crew/hooks/scripts/crew_state.py` | Read crew state from a repo; evaluate PM triggers. No rendering. |
| `plugin/crew/hooks/scripts/pm_brief.py` | Render quiet or expanded brief from state. No file reads. |
| `plugin/crew/hooks/scripts/pm-brief.sh` | Wrapper: locate python3, exec `pm_brief.py`, fail soft. |
| `plugin/crew/hooks/scripts/pm-brief.ps1` | Same, PowerShell. |
| `plugin/crew/hooks/scripts/handoff-write.ps1` | Missing PowerShell twin of `handoff-write.sh`. |
| `plugin/crew/hooks/scripts/notify.ps1` | Missing PowerShell twin of `notify.sh`. |

The split between `crew_state.py` and `pm_brief.py` is deliberate: state is what
the `crew:pm` agent also needs, rendering is not. Keeping them separate is what
lets the agent reuse the reader without inheriting a 40-line cap.

**Create — graph and upgrade:**

| File | Responsibility |
|---|---|
| `plugin/crew/skills/crew-graph/SKILL.md` | Own graphify: detect, build, query, export, keep fresh. |
| `plugin/crew/skills/crew-graph/scripts/graph_reconcile.py` | Reconcile a codemap file against the graph. Pure; no I/O side effects beyond the report it returns. |
| `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py` | v1 -> v2: back up, upgrade config, drive reconciliation, write `UPGRADE.md`. |
| `plugin/crew/skills/crew-graph/reconcile.md` | The shared procedure both `/crew:upgrade` and `/crew:onboard --refresh` follow. Single source of truth. |

**Create — PM prose:**

| File | Responsibility |
|---|---|
| `plugin/crew/skills/crew-pm/SKILL.md` | Narrowly-triggered manager procedures. |
| `plugin/crew/skills/crew-pm/onboarding.md` | Onboard a repo or a role. |
| `plugin/crew/skills/crew-pm/offboarding.md` | Remove a role and name the lost coverage. |
| `plugin/crew/agents/pm.md` | `crew:pm` — heavy analysis in its own context. |
| `plugin/crew/commands/pm.md` | `/crew:pm`, `/crew:pm onboard`, `/crew:pm offboard`. |
| `plugin/crew/commands/upgrade.md` | `/crew:upgrade`. |

**Create — tests:**

| File | Responsibility |
|---|---|
| `plugin/crew/tests/context.py` | Put `hooks/scripts` and `skills/*/scripts` on `sys.path`. Mirrors `skills/cisco-meraki/tests/context.py`. |
| `plugin/crew/tests/helpers.py` | Build fixture repos on a tmp path. |
| `plugin/crew/tests/test_crew_state.py` | Reader and trigger evaluation. |
| `plugin/crew/tests/test_pm_brief.py` | Rendering, line caps, fail-soft. |
| `plugin/crew/tests/test_upgrade.py` | Reconciliation and config upgrade. |
| `.github/workflows/pytest-crew.yml` | Run those tests. Scoped to `plugin/crew/tests/` only. |

The workflow is scoped deliberately: an unscoped pytest job would also collect
`skills/cisco-meraki/tests/test_live_smoke.py`, which needs live credentials.

**Modify:**

| File | Change |
|---|---|
| `plugin/crew/hooks/hooks.json` | Add `pm-brief` (both shells); wire the three existing unreferenced `.ps1`; wire the two new ones. |
| `plugin/crew/skills/find-skills/SKILL.md` | Narrow `description:`. |
| `plugin/crew/skills/find-skills/BUNDLING-NOTE.md` | Record that the narrowing is applied. |
| `plugin/crew/skills/crew-setup/SKILL.md` | `schema: 2`, `pm` and `graph` blocks, global find-skills detection. |
| `plugin/crew/skills/crew-setup/phases.md` | Same, in the phase walkthrough. |
| `plugin/crew/commands/onboard.md` | Graph-first ordering. |
| `plugin/crew/commands/scale.md` | Cross-reference offboarding. |
| `plugin/crew/skills/crew-scaling/SKILL.md` | Same. |
| `plugin/crew/skills/crew-context/SKILL.md` | Note `pm-brief` also runs at `SessionStart`. |
| `scripts/install-prerequisites.sh` / `.ps1` | graphify item; find-skills detection. Matched pair. |
| `.claude-plugin/marketplace.json` | crew 0.2.0 -> 0.3.0. |
| `plugin/README.md`, `plugin/PLUGINS.md`, `README.md`, `INSTALLATION.md`, `CHANGELOG.md`, `plugin/crew/README.md` | Documentation tail. |

---

## Task 1: Test harness

**Files:**
- Create: `plugin/crew/tests/context.py`
- Create: `plugin/crew/tests/helpers.py`
- Create: `.github/workflows/pytest-crew.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: `helpers.make_repo(tmp_path, **kwargs) -> pathlib.Path` — writes a
  synthetic crew repo and returns its root. Keyword arguments:
  `config: dict | None` (written to `.crew/config.json`; `None` writes no file),
  `metrics: list[tuple[str, int, int]] | None` (rows of
  `(ticket, n_block, n_fix)`), `codemap: dict[str, str] | None` (subsystem name
  -> file body), `work_ticket: str | None`, `handoff: bool`, `graph: bool`,
  `git: bool` (default `True`; runs `git init` and one commit so
  `rev-parse HEAD` works), `graph_sha: str | None` (default `"head"` — stamps
  the graph's sidecar with the real HEAD; a literal sha stamps that instead;
  `None` writes no sidecar).
  Also `helpers.head_sha(root, length=7) -> str`.

- [ ] **Step 1: Write `context.py`**

```python
"""Puts crew's script directories on sys.path so tests can import them."""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

for _rel in ("hooks/scripts", "skills/crew-graph/scripts"):
    _path = os.path.join(_ROOT, *_rel.split("/"))
    if _path not in sys.path:
        sys.path.insert(0, _path)
```

- [ ] **Step 2: Write `helpers.py`**

```python
"""Builds synthetic crew repositories for tests.

A fixture is a real git repository with a real commit, because the code under
test asks git for HEAD and comparing against a mocked sha would test the mock.
"""
import json
import os
import subprocess


def _git(root, *args):
    subprocess.run(
        ("git",) + args, cwd=root, check=True,
        capture_output=True, text=True,
    )


def make_repo(tmp_path, config=None, metrics=None, codemap=None,
              work_ticket=None, handoff=False, graph=False, git=True,
              graph_sha="head"):
    """Write a synthetic crew repo under tmp_path and return its root."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".work").mkdir(parents=True)

    if git:
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "test@example.invalid")
        _git(root, "config", "user.name", "Test")
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        _git(root, "add", "README.md")
        _git(root, "commit", "-q", "-m", "fixture")

    if config is not None:
        (root / ".crew" / "config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

    if metrics is not None:
        lines = ["date | ticket | reviewer | BLOCK | FIX",
                 "--- | --- | --- | --- | ---"]
        for ticket, block, fix in metrics:
            lines.append(f"2026-08-01 | {ticket} | codex | {block} | {fix}")
        (root / ".crew" / "metrics.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    if codemap is not None:
        mapdir = root / ".crew" / "codemap"
        mapdir.mkdir()
        for name, body in codemap.items():
            (mapdir / f"{name}.md").write_text(body, encoding="utf-8")

    if work_ticket:
        (root / ".work" / "INDEX.md").write_text(
            f"# Work\n\n- {work_ticket} — in progress\n", encoding="utf-8"
        )

    if handoff:
        (root / ".work" / "HANDOFF.md").write_text(
            "# Handoff\n\n## Next action\nSomething.\n", encoding="utf-8"
        )

    if graph:
        out = root / "graphify-out"
        out.mkdir()
        (out / "graph.json").write_text('{"nodes": [], "edges": []}',
                                        encoding="utf-8")
        # graph_sha: "head" stamps the sidecar with the real HEAD (a fresh
        # graph), a literal sha stamps that (a stale one), None writes no
        # sidecar (a graph built outside crew).
        if graph_sha == "head" and git:
            (out / ".crew-graph-sha").write_text(head_sha(root) + "\n",
                                                 encoding="utf-8")
        elif graph_sha and graph_sha != "head":
            (out / ".crew-graph-sha").write_text(graph_sha + "\n",
                                                 encoding="utf-8")

    return root


def head_sha(root, length=7):
    """Short HEAD sha of a fixture repo."""
    done = subprocess.run(
        ("git", "rev-parse", f"--short={length}", "HEAD"),
        cwd=root, check=True, capture_output=True, text=True,
    )
    return done.stdout.strip()


def commit_with_date(root, path, iso_date):
    """Commit one file with both dates forced, simulating a pulled commit.

    A pull lands commits authored earlier than now, which is what breaks any
    freshness check based on timestamps rather than a recorded sha.
    """
    env = dict(os.environ,
               GIT_AUTHOR_DATE=iso_date, GIT_COMMITTER_DATE=iso_date)
    subprocess.run(("git", "add", path), cwd=root, check=True,
                   capture_output=True, text=True)
    subprocess.run(("git", "commit", "-q", "-m", f"backdated {path}"),
                   cwd=root, check=True, capture_output=True, text=True,
                   env=env)
```

- [ ] **Step 3: Write the workflow**

```yaml
name: Pytest (crew plugin)

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        # Matches the pylint job's floor: pylint 4 needs >=3.10, and these
        # scripts are stdlib-only so there is nothing else to pin against.
        python-version: ["3.11", "3.12", "3.13"]
    steps:
    - uses: actions/checkout@v4
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
    - name: Install pytest
      run: |
        python -m pip install --upgrade pip
        pip install 'pytest~=8.0'
    - name: Run crew plugin tests
      # Scoped to this directory on purpose. An unscoped run would also collect
      # skills/cisco-meraki/tests/test_live_smoke.py, which needs live
      # credentials and would fail every push.
      run: pytest plugin/crew/tests/ -v
```

- [ ] **Step 4: Verify the harness collects nothing and passes**

Run: `python -m pytest plugin/crew/tests/ -v`
Expected: exit 0, "no tests ran" (or 0 collected). Not an import error.

- [ ] **Step 5: Verify pylint accepts the new files**

Run: `pylint plugin/crew/tests/context.py plugin/crew/tests/helpers.py`
Expected: 10.00/10, or only messages disabled by `.pylintrc`.

- [ ] **Step 6: Codex review**

```bash
git diff > .work/review-diff.txt
codex exec --skip-git-repo-check "Review .work/review-diff.txt as a hostile QA engineer.
Output one line per defect: SEVERITY|file:line|what breaks|how to reproduce.
SEVERITY is BLOCK, FIX, or NIT. Output nothing but those lines.
If no defects, output exactly: CLEAN" > .work/review-out.txt 2>&1
```
Report every BLOCK and FIX verbatim. Fix all BLOCK before committing.

- [ ] **Step 7: Commit**

```bash
git add plugin/crew/tests/ .github/workflows/pytest-crew.yml
git commit -m "test(crew): add pytest harness and fixture builder for plugin scripts"
```

---

## Task 2: `crew_state.py` — config, metrics, work

**Files:**
- Create: `plugin/crew/hooks/scripts/crew_state.py`
- Test: `plugin/crew/tests/test_crew_state.py`

**Interfaces:**
- Consumes: `helpers.make_repo` (Task 1).
- Produces:
  - `SCHEMA_CURRENT: int = 2`
  - `load_config(root: str) -> dict` — `{}` when absent or malformed
  - `read_metrics(root: str, window: int = 10) -> dict` with keys
    `tickets: int`, `findings: int`, `rate: float | None`, `verdict: str`
  - `read_work(root: str) -> dict` with keys
    `ticket: str | None`, `handoffPending: bool`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the crew state reader."""
import context  # noqa: F401  pylint: disable=unused-import
import crew_state
import helpers


def test_missing_config_is_empty_dict(tmp_path):
    root = helpers.make_repo(tmp_path)
    assert crew_state.load_config(str(root)) == {}


def test_malformed_config_is_empty_dict_not_an_exception(tmp_path):
    root = helpers.make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text("{not json", encoding="utf-8")
    assert crew_state.load_config(str(root)) == {}


def test_config_list_at_top_level_is_rejected(tmp_path):
    root = helpers.make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text("[1, 2]", encoding="utf-8")
    assert crew_state.load_config(str(root)) == {}


def test_metrics_rate_is_findings_over_tickets(tmp_path):
    root = helpers.make_repo(
        tmp_path, metrics=[("T-1", 1, 0), ("T-2", 0, 1), ("T-3", 1, 1)]
    )
    got = crew_state.read_metrics(str(root))
    assert got["tickets"] == 3
    assert got["findings"] == 4
    assert got["rate"] == 1.33
    assert got["verdict"] == "healthy"


def test_metrics_header_and_separator_rows_are_skipped(tmp_path):
    # make_repo always writes both; a rate of 0.0 would mean they were counted.
    root = helpers.make_repo(tmp_path, metrics=[("T-1", 2, 0)])
    assert crew_state.read_metrics(str(root))["tickets"] == 1


def test_metrics_window_keeps_only_the_last_n(tmp_path):
    rows = [(f"T-{i}", 5, 5) for i in range(12)] + [("T-last", 0, 0)]
    root = helpers.make_repo(tmp_path, metrics=rows)
    got = crew_state.read_metrics(str(root), window=2)
    assert got["tickets"] == 2
    assert got["findings"] == 10  # one 5+5 row and one 0+0 row


def test_low_rate_reports_review_not_catching(tmp_path):
    rows = [(f"T-{i}", 0, 0) for i in range(10)]
    root = helpers.make_repo(tmp_path, metrics=rows)
    assert crew_state.read_metrics(str(root))["verdict"] == (
        "review not catching defects"
    )


def test_high_rate_reports_tickets_too_large(tmp_path):
    rows = [(f"T-{i}", 3, 2) for i in range(10)]
    root = helpers.make_repo(tmp_path, metrics=rows)
    assert crew_state.read_metrics(str(root))["verdict"] == "tickets too large"


def test_absent_metrics_is_no_data_not_zero(tmp_path):
    # A repo that has run no reviews must not read as a broken review.
    root = helpers.make_repo(tmp_path)
    got = crew_state.read_metrics(str(root))
    assert got["rate"] is None
    assert got["verdict"] == "no data"


def test_work_reads_ticket_and_handoff(tmp_path):
    root = helpers.make_repo(tmp_path, work_ticket="T-0042", handoff=True)
    got = crew_state.read_work(str(root))
    assert got["ticket"] == "T-0042"
    assert got["handoffPending"] is True


def test_work_absent_is_none_and_false(tmp_path):
    root = helpers.make_repo(tmp_path)
    got = crew_state.read_work(str(root))
    assert got["ticket"] is None
    assert got["handoffPending"] is False


def test_work_skips_finished_tickets_above_the_open_one(tmp_path):
    """A real INDEX.md accumulates. Taking the first match names a closed
    ticket, in the brief, as fact, on every session.
    """
    root = helpers.make_repo(tmp_path)
    (root / ".work" / "INDEX.md").write_text(
        "# Work\n\n"
        "- [x] T-0001 — done\n"
        "- ~~T-0002~~ merged\n"
        "- T-0003 — in progress\n"
        "- T-0004 — queued\n",
        encoding="utf-8",
    )
    assert crew_state.read_work(str(root))["ticket"] == "T-0003"


def test_work_with_every_ticket_done_reports_none(tmp_path):
    # "no ticket open" is true; naming a closed ticket is not.
    root = helpers.make_repo(tmp_path)
    (root / ".work" / "INDEX.md").write_text(
        "# Work\n\n- [x] T-0001 — done\n- [x] T-0002 — closed\n",
        encoding="utf-8",
    )
    assert crew_state.read_work(str(root))["ticket"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest plugin/crew/tests/test_crew_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'crew_state'`

- [ ] **Step 3: Write the implementation**

```python
"""Reads crew state from a repository and evaluates the PM's attention triggers.

Standard library only, and every read fails soft. This module runs from a
SessionStart hook, so an exception here would break every session opened in the
repository -- an absent or malformed file must yield an absent value, never a
traceback.
"""

import json
import os
import re

SCHEMA_CURRENT = 2

# Verbatim from crew-scaling/SKILL.md. Below the floor the review is broken
# rather than thorough; above the ceiling the tickets are too large.
HEALTHY_LOW = 0.3
HEALTHY_HIGH = 2.0
METRICS_WINDOW = 10

_TICKET_RE = re.compile(r"([A-Z][A-Z0-9]*-\d+)")

# Markers that mean a ticket line is finished. `[x]` is the markdown checkbox
# form; the words cover how these files actually get written by hand.
_DONE_RE = re.compile(
    r"(\[x\]|~~|\bdone\b|\bclosed\b|\bmerged\b|\bshipped\b|\bcomplete)",
    re.IGNORECASE,
)


def read_text(path):
    """Return the file's text, or None if it cannot be read for any reason."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def load_config(root):
    """Parse .crew/config.json. Returns {} when absent, malformed, or not a dict."""
    text = read_text(os.path.join(root, ".crew", "config.json"))
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _leading_int(cell):
    """First integer in a table cell, or None. 'BLOCK' and '---' yield None."""
    found = re.search(r"-?\d+", cell)
    return int(found.group()) if found else None


def _verdict(rate):
    if rate < HEALTHY_LOW:
        return "review not catching defects"
    if rate > HEALTHY_HIGH:
        return "tickets too large"
    return "healthy"


def read_metrics(root, window=METRICS_WINDOW):
    """BLOCK+FIX per ticket over the last `window` review rows.

    Rows are appended by /crew:review as
    `<date> | <ticket> | <reviewer> | <n BLOCK> | <n FIX>`. Leading and
    trailing pipes are tolerated, and any row whose BLOCK/FIX cells are not
    numeric is skipped -- which is how the header and separator rows are
    filtered without hard-coding their text.
    """
    empty = {"tickets": 0, "findings": 0, "rate": None, "verdict": "no data"}
    text = read_text(os.path.join(root, ".crew", "metrics.md"))
    if not text:
        return empty

    totals = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        block, fix = _leading_int(cells[3]), _leading_int(cells[4])
        if block is None or fix is None:
            continue
        totals.append(block + fix)

    recent = totals[-window:]
    if not recent:
        return empty
    findings = sum(recent)
    rate = findings / len(recent)
    return {
        "tickets": len(recent),
        "findings": findings,
        "rate": round(rate, 2),
        "verdict": _verdict(rate),
    }


def read_work(root):
    """The OPEN ticket and whether a handoff is waiting.

    Not simply the first ticket in the file. A real .work/INDEX.md accumulates
    finished tickets above the current one, so taking the first match names a
    ticket that closed weeks ago -- on every session, in the brief, as fact.

    A line is skipped when it carries a done marker; the first line that does
    not wins. A file with no in-progress line yields None rather than a guess,
    because "no ticket open" is a true statement and a stale ticket number is
    not.
    """
    ticket = None
    text = read_text(os.path.join(root, ".work", "INDEX.md"))
    for line in (text or "").splitlines():
        found = _TICKET_RE.search(line)
        if not found:
            continue
        if _DONE_RE.search(line):
            continue
        ticket = found.group(1)
        break
    return {
        "ticket": ticket,
        "handoffPending": os.path.exists(
            os.path.join(root, ".work", "HANDOFF.md")
        ),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest plugin/crew/tests/test_crew_state.py -v`
Expected: all pass, none skipped, none errored

- [ ] **Step 5: Lint**

Run: `pylint plugin/crew/hooks/scripts/crew_state.py`
Expected: clean under `.pylintrc`

- [ ] **Step 6: Codex review** — same invocation as Task 1 Step 6.

- [ ] **Step 7: Commit**

```bash
git add plugin/crew/hooks/scripts/crew_state.py plugin/crew/tests/test_crew_state.py
git commit -m "feat(crew): read crew config, review metrics, and work state"
```

---

## Task 3: `crew_state.py` — knowledge freshness and graph

**Files:**
- Modify: `plugin/crew/hooks/scripts/crew_state.py`
- Modify: `plugin/crew/tests/test_crew_state.py`

**Interfaces:**
- Consumes: `read_text`, `load_config` (Task 2).
- Produces:
  - `git_out(root: str, *args: str) -> str | None`
  - `GRAPH_SHA_FILE: str = ".crew-graph-sha"`
  - `read_knowledge(root: str, cfg: dict) -> dict` with keys
    `subsystems: int`, `behind: list[str]`, `graph: dict`
  - `graph` sub-dict keys: `present: bool`, `current: bool`,
    `builtAt: str | None`, `path: str`

**Design note — why "behind HEAD" and not "stale".** `commands/onboard.md`
defines staleness per-path: `git diff --name-only <anchor-sha>..HEAD -- <paths>`.
The brief cannot afford that walk on every session start, and the paths would
have to be parsed out of prose. So the hook reports the cheap, honest fact — the
anchor is not HEAD — and leaves the per-path verdict to `crew-pm`. Reporting
"behind" where we have not proven "wrong" is the whole point.

- [ ] **Step 1: Write the failing tests**

```python
CODEMAP_BODY = """# auth
anchor: repo@{sha}
verified: 2026-08-01

## Does
Authenticates.

## Landmines
- Do not touch the session cache.
"""


def test_anchor_matching_head_is_not_behind(tmp_path):
    root = helpers.make_repo(tmp_path, codemap={"auth": "placeholder"})
    sha = helpers.head_sha(root)
    (root / ".crew" / "codemap" / "auth.md").write_text(
        CODEMAP_BODY.format(sha=sha), encoding="utf-8"
    )
    got = crew_state.read_knowledge(str(root), {})
    assert got["subsystems"] == 1
    assert got["behind"] == []


def test_anchor_behind_head_is_reported(tmp_path):
    root = helpers.make_repo(
        tmp_path, codemap={"auth": CODEMAP_BODY.format(sha="0000000")}
    )
    assert crew_state.read_knowledge(str(root), {})["behind"] == ["auth"]


def test_missing_anchor_counts_as_behind(tmp_path):
    root = helpers.make_repo(tmp_path, codemap={"auth": "# auth\nno anchor\n"})
    assert crew_state.read_knowledge(str(root), {})["behind"] == ["auth"]


def test_index_and_upgrade_reports_are_not_subsystems(tmp_path):
    root = helpers.make_repo(
        tmp_path,
        codemap={"INDEX": "# index\n", "UPGRADE": "# report\n",
                 "auth": CODEMAP_BODY.format(sha="0000000")},
    )
    assert crew_state.read_knowledge(str(root), {})["subsystems"] == 1


def test_absent_graph_is_not_present(tmp_path):
    root = helpers.make_repo(tmp_path)
    got = crew_state.read_knowledge(str(root), {})["graph"]
    assert got["present"] is False
    assert got["current"] is False


def test_graph_built_at_head_is_current(tmp_path):
    root = helpers.make_repo(tmp_path, graph=True, graph_sha="head")
    assert crew_state.read_knowledge(str(root), {})["graph"]["current"] is True


def test_graph_built_at_another_sha_is_not_current(tmp_path):
    root = helpers.make_repo(tmp_path, graph=True, graph_sha="0000000")
    assert crew_state.read_knowledge(str(root), {})["graph"]["current"] is False


def test_graph_with_no_sidecar_is_not_current(tmp_path):
    # Built outside crew, so its provenance is unknown. Unknown resolves to
    # stale: claiming freshness we cannot prove is the failure mode.
    root = helpers.make_repo(tmp_path, graph=True, graph_sha=None)
    got = crew_state.read_knowledge(str(root), {})["graph"]
    assert got["present"] is True
    assert got["current"] is False
    assert got["builtAt"] is None


def test_a_pull_of_older_commits_makes_the_graph_stale(tmp_path):
    """The regression a timestamp comparison gets wrong.

    `git pull` brings in commits authored before the graph was built, so any
    mtime-vs-commit-time check reports the graph current while it knows
    nothing about the pulled code.
    """
    root = helpers.make_repo(tmp_path, graph=True, graph_sha="head")
    assert crew_state.read_knowledge(str(root), {})["graph"]["current"] is True

    # A new commit backdated well before the graph was written.
    (root / "pulled.py").write_text("# from upstream\n", encoding="utf-8")
    helpers.commit_with_date(root, "pulled.py", "2020-01-01T00:00:00")

    got = crew_state.read_knowledge(str(root), {})["graph"]
    assert got["current"] is False, "backdated commit must invalidate the graph"


def test_graph_out_dir_comes_from_config(tmp_path):
    root = helpers.make_repo(tmp_path)
    (root / "custom-out").mkdir()
    (root / "custom-out" / "graph.json").write_text("{}", encoding="utf-8")
    cfg = {"graph": {"out": "custom-out"}}
    assert crew_state.read_knowledge(str(root), cfg)["graph"]["present"] is True


def test_knowledge_survives_a_non_git_directory(tmp_path):
    root = helpers.make_repo(
        tmp_path, codemap={"auth": CODEMAP_BODY.format(sha="0000000")},
        git=False,
    )
    got = crew_state.read_knowledge(str(root), {})
    assert got["subsystems"] == 1  # no crash, and no false freshness claim
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest plugin/crew/tests/test_crew_state.py -v -k "anchor or graph or knowledge or subsystem"`
Expected: FAIL — `AttributeError: module 'crew_state' has no attribute 'read_knowledge'`

- [ ] **Step 3: Write the implementation**

Add to `crew_state.py`. `subprocess` joins the imports.

```python
_ANCHOR_RE = re.compile(
    r"^anchor:\s*(?:\S*@)?([0-9a-f]{7,40})\s*$", re.MULTILINE | re.IGNORECASE
)

# Files under .crew/codemap/ that describe the map rather than a subsystem.
_NOT_SUBSYSTEMS = frozenset({"INDEX.md", "UPGRADE.md", "MIGRATION.md"})

# Written by crew-graph at build time, holding the short HEAD sha the graph was
# built from. A sha, not a timestamp -- see _read_graph.
GRAPH_SHA_FILE = ".crew-graph-sha"

_GIT_TIMEOUT = 10


def git_out(root, *args):
    """Stripped stdout of a git command, or None on any failure.

    Failure includes git being absent and root not being a repository. Both
    are ordinary: the hook runs wherever the user opens a session.
    """
    try:
        done = subprocess.run(
            ("git",) + args, cwd=root, capture_output=True,
            text=True, timeout=_GIT_TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def _read_graph(root, cfg):
    """Graph presence, and whether it was built at the current HEAD.

    Freshness is a recorded sha, never a timestamp. Comparing graph.json's
    mtime against HEAD's commit time looks reasonable and is wrong: `git pull`
    brings in commits authored earlier than the graph was built, so a graph
    that knows nothing about the pulled code reports itself current. That is
    the false-freshness failure this module exists to avoid.

    The sha comes from a sidecar that crew-graph writes at build time. No
    sidecar means the graph was built outside crew, so its provenance is
    unknown -- and unknown resolves to stale, which is the honest direction.
    """
    out = (cfg.get("graph") or {}).get("out") or "graphify-out"
    path = os.path.join(root, out, "graph.json")
    if not os.path.exists(path):
        return {"present": False, "current": False, "builtAt": None,
                "path": path}

    built = (read_text(os.path.join(root, out, GRAPH_SHA_FILE)) or "").strip()
    head = git_out(root, "rev-parse", "--short=7", "HEAD")
    current = bool(built) and bool(head) and built[:7] == head[:7]
    return {"present": True, "current": current,
            "builtAt": built or None, "path": path}


def read_knowledge(root, cfg):
    """Codemap inventory plus graph freshness.

    `behind` names maps whose anchor is not HEAD. That is not the same as
    wrong -- see the design note in the plan. Without git there is no HEAD to
    compare against, so nothing is claimed either way.
    """
    head = git_out(root, "rev-parse", "--short=7", "HEAD")
    mapdir = os.path.join(root, ".crew", "codemap")
    try:
        names = sorted(os.listdir(mapdir))
    except OSError:
        names = []

    subsystems, behind = 0, []
    for name in names:
        if not name.endswith(".md") or name in _NOT_SUBSYSTEMS:
            continue
        subsystems += 1
        if not head:
            continue
        found = _ANCHOR_RE.search(read_text(os.path.join(mapdir, name)) or "")
        if not found or found.group(1)[:7] != head[:7]:
            behind.append(name[: -len(".md")])

    return {
        "subsystems": subsystems,
        "behind": behind,
        "graph": _read_graph(root, cfg),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest plugin/crew/tests/test_crew_state.py -v`
Expected: all pass, none skipped, none errored

- [ ] **Step 5: Lint** — `pylint plugin/crew/hooks/scripts/crew_state.py`

- [ ] **Step 6: Codex review**

- [ ] **Step 7: Commit**

```bash
git add plugin/crew/hooks/scripts/crew_state.py plugin/crew/tests/test_crew_state.py
git commit -m "feat(crew): report codemap anchor drift and graph freshness"
```

---

## Task 4: `crew_state.py` — trigger evaluation and `collect`

**Files:**
- Modify: `plugin/crew/hooks/scripts/crew_state.py`
- Modify: `plugin/crew/tests/test_crew_state.py`

**Interfaces:**
- Consumes: everything from Tasks 2 and 3.
- Produces:
  - `TRIGGERS: tuple[str, ...]` in priority order —
    `("upgradeNeeded", "handoffPending", "graphStale", "knowledgeBehind", "reviewNotWorking", "ticketsTooLarge")`
  - `evaluate_triggers(state: dict) -> list[str]`
  - `collect(root: str) -> dict` — the whole state object, keys:
    `isCrew, schema, tier, roles, tracker, pm, health, work, knowledge, triggers`
  - `main() -> int` — prints `collect()` as JSON, returns 0

**Priority order is load-bearing.** `pm_brief.py` truncates from the bottom when
it hits the line cap, so the most actionable finding has to sort first.
`upgradeNeeded` leads because every other finding may be an artifact of a
pre-upgrade layout.

- [ ] **Step 1: Write the failing tests**

```python
def _state(**over):
    base = {
        "schema": 2,
        "health": {"rate": 1.0, "verdict": "healthy"},
        "work": {"ticket": None, "handoffPending": False},
        "knowledge": {"subsystems": 0, "behind": [],
                      "graph": {"present": True, "current": True}},
    }
    base.update(over)
    return base


def test_healthy_state_fires_no_triggers():
    assert crew_state.evaluate_triggers(_state()) == []


def test_v1_schema_fires_upgrade_needed():
    assert "upgradeNeeded" in crew_state.evaluate_triggers(_state(schema=1))


def test_absent_graph_fires_graph_stale():
    got = crew_state.evaluate_triggers(
        _state(knowledge={"subsystems": 0, "behind": [],
                          "graph": {"present": False, "current": False}})
    )
    assert "graphStale" in got


def test_behind_anchors_fire_knowledge_behind():
    got = crew_state.evaluate_triggers(
        _state(knowledge={"subsystems": 2, "behind": ["auth"],
                          "graph": {"present": True, "current": True}})
    )
    assert "knowledgeBehind" in got


def test_low_rate_fires_review_not_working():
    got = crew_state.evaluate_triggers(
        _state(health={"rate": 0.1, "verdict": "review not catching defects"})
    )
    assert "reviewNotWorking" in got


def test_no_data_does_not_fire_review_not_working():
    # A fresh repo has run no reviews. That is not a broken review.
    got = crew_state.evaluate_triggers(
        _state(health={"rate": None, "verdict": "no data"})
    )
    assert "reviewNotWorking" not in got


def test_high_rate_fires_tickets_too_large():
    got = crew_state.evaluate_triggers(
        _state(health={"rate": 3.0, "verdict": "tickets too large"})
    )
    assert "ticketsTooLarge" in got


def test_pending_handoff_fires():
    got = crew_state.evaluate_triggers(
        _state(work={"ticket": "T-1", "handoffPending": True})
    )
    assert "handoffPending" in got


def test_triggers_come_back_in_priority_order():
    got = crew_state.evaluate_triggers(
        _state(schema=1, work={"ticket": None, "handoffPending": True},
               health={"rate": 0.0, "verdict": "review not catching defects"})
    )
    assert got == ["upgradeNeeded", "handoffPending", "reviewNotWorking"]


def test_collect_on_a_non_crew_directory_is_not_crew(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    assert crew_state.collect(str(root))["isCrew"] is False


def test_collect_defaults_schema_to_one_when_absent(tmp_path):
    root = helpers.make_repo(tmp_path, config={"tier": 0, "roles": []})
    assert crew_state.collect(str(root))["schema"] == 1


def test_collect_reads_pm_block_defaults(tmp_path):
    root = helpers.make_repo(tmp_path, config={"schema": 2})
    pm = crew_state.collect(str(root))["pm"]
    assert pm["enabled"] is True
    assert pm["mode"] == "adaptive"
    assert pm["quietLines"] == 8
    assert pm["maxLines"] == 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest plugin/crew/tests/test_crew_state.py -v -k "trigger or collect or fires or order"`
Expected: FAIL — no attribute `evaluate_triggers`

- [ ] **Step 3: Write the implementation**

```python
# Priority order. pm_brief truncates from the bottom when it hits the line cap,
# so the most actionable finding has to sort first. upgradeNeeded leads because
# every other finding may be an artifact of a pre-upgrade layout.
TRIGGERS = (
    "upgradeNeeded",
    "handoffPending",
    "graphStale",
    "knowledgeBehind",
    "reviewNotWorking",
    "ticketsTooLarge",
)

PM_DEFAULTS = {
    "enabled": True,
    "mode": "adaptive",
    "quietLines": 8,
    "maxLines": 40,
    "authority": "report-only",
}


def evaluate_triggers(state):
    """Reasons the PM should speak up, in TRIGGERS order."""
    knowledge = state.get("knowledge") or {}
    graph = knowledge.get("graph") or {}
    health = state.get("health") or {}
    work = state.get("work") or {}

    fired = {
        "upgradeNeeded": state.get("schema", 1) < SCHEMA_CURRENT,
        "handoffPending": bool(work.get("handoffPending")),
        # An absent graph is stale by definition -- there is nothing to trust.
        "graphStale": not graph.get("present") or not graph.get("current"),
        "knowledgeBehind": bool(knowledge.get("behind")),
        # `rate is None` means no reviews have run. A repo that has reviewed
        # nothing has not got a broken review, and saying so would be noise
        # on every fresh setup.
        "reviewNotWorking": health.get("rate") is not None
        and health["rate"] < HEALTHY_LOW,
        "ticketsTooLarge": health.get("rate") is not None
        and health["rate"] > HEALTHY_HIGH,
    }
    return [name for name in TRIGGERS if fired[name]]


def collect(root):
    """Full crew state for a repository. Never raises."""
    cfg = load_config(root)
    pm = dict(PM_DEFAULTS)
    supplied = cfg.get("pm")
    if isinstance(supplied, dict):
        pm.update(supplied)

    state = {
        "isCrew": bool(cfg),
        # No `schema` key means a config written before schema tracking: v1.
        "schema": cfg.get("schema", 1) if cfg else SCHEMA_CURRENT,
        "tier": cfg.get("tier"),
        "roles": cfg.get("roles") or [],
        "tracker": cfg.get("tracker"),
        "pm": pm,
        "health": read_metrics(root),
        "work": read_work(root),
        "knowledge": read_knowledge(root, cfg),
    }
    state["triggers"] = evaluate_triggers(state)
    return state


def main():
    """Print the state as JSON. Exit code is always 0."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    print(json.dumps(collect(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note the `schema` default: a non-crew directory reports `SCHEMA_CURRENT` so it
never fires `upgradeNeeded` on a repo that has no crew at all.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest plugin/crew/tests/test_crew_state.py -v`
Expected: all pass, none skipped, none errored

- [ ] **Step 5: Verify it runs standalone against this repo**

Run: `python plugin/crew/hooks/scripts/crew_state.py`
Expected: JSON on stdout with `"isCrew": false` (this repo has no `.crew/`), exit 0.

- [ ] **Step 6: Lint, then Codex review**

- [ ] **Step 7: Commit**

```bash
git add plugin/crew/hooks/scripts/crew_state.py plugin/crew/tests/test_crew_state.py
git commit -m "feat(crew): evaluate PM attention triggers and expose full state"
```

---

## Task 5: `pm_brief.py` — quiet mode

**Files:**
- Create: `plugin/crew/hooks/scripts/pm_brief.py`
- Test: `plugin/crew/tests/test_pm_brief.py`

**Interfaces:**
- Consumes: `crew_state.collect` (Task 4).
- Produces:
  - `render(state: dict) -> list[str]` — the brief's lines, no trailing newline
  - `main(argv: list[str] | None = None) -> int` — reads the hook's JSON payload
    from stdin, prints, returns 0

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for the PM brief renderer."""
import io
import json

import context  # noqa: F401  pylint: disable=unused-import
import helpers
import pm_brief

HEALTHY = {
    "isCrew": True, "schema": 2, "tier": 1,
    "roles": ["explorer", "qa-reviewer"], "tracker": "files",
    "pm": {"enabled": True, "mode": "adaptive", "quietLines": 8,
           "maxLines": 40, "authority": "report-only"},
    "health": {"tickets": 10, "findings": 8, "rate": 0.8,
               "verdict": "healthy"},
    "work": {"ticket": "T-0042", "handoffPending": False},
    "knowledge": {"subsystems": 6, "behind": [],
                  "graph": {"present": True, "current": True}},
    "triggers": [],
}


def test_non_crew_repo_renders_nothing():
    assert pm_brief.render({"isCrew": False, "triggers": []}) == []


def test_disabled_pm_renders_nothing():
    state = dict(HEALTHY, pm=dict(HEALTHY["pm"], enabled=False))
    assert pm_brief.render(state) == []


def test_quiet_brief_respects_quiet_lines():
    out = pm_brief.render(HEALTHY)
    assert 0 < len(out) <= HEALTHY["pm"]["quietLines"]


def test_quiet_brief_states_tier_roles_and_tracker():
    joined = "\n".join(pm_brief.render(HEALTHY))
    assert "tier 1" in joined
    assert "2 roles" in joined
    assert "files" in joined


def test_quiet_brief_states_the_health_number():
    joined = "\n".join(pm_brief.render(HEALTHY))
    assert "0.8" in joined
    assert "healthy" in joined


def test_quiet_brief_names_the_open_ticket():
    assert "T-0042" in "\n".join(pm_brief.render(HEALTHY))


def test_quiet_brief_contains_no_imperative_framing():
    # Hook stdout is injected as context. Framing it as instructions trips
    # prompt-injection defences and gets it surfaced to the user instead.
    joined = "\n".join(pm_brief.render(HEALTHY)).lower()
    for banned in ("you must", "system:", "instruction", "ignore previous"):
        assert banned not in joined


def test_main_exits_zero_on_garbage_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    assert pm_brief.main([]) == 0
    assert capsys.readouterr().out == ""


def test_main_exits_zero_on_empty_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert pm_brief.main([]) == 0


def test_main_uses_cwd_from_the_payload(tmp_path, monkeypatch, capsys):
    root = helpers.make_repo(
        tmp_path, config={"schema": 2, "tier": 0, "roles": [],
                          "tracker": "files"}, graph=True
    )
    payload = json.dumps({"source": "startup", "cwd": str(root)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert pm_brief.main([]) == 0
    assert "crew" in capsys.readouterr().out


def test_main_on_a_plain_directory_prints_nothing(tmp_path, monkeypatch, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    payload = json.dumps({"source": "startup", "cwd": str(plain)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert pm_brief.main([]) == 0
    assert capsys.readouterr().out == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest plugin/crew/tests/test_pm_brief.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pm_brief'`

- [ ] **Step 3: Write the implementation**

```python
"""Renders the crew Project Manager's session-start brief.

Reads nothing from disk itself -- crew_state does that -- so the renderer can
be tested against a literal state dict. Output is plain project information,
never instructions: text framed as out-of-band commands trips prompt-injection
defences and gets surfaced to the user instead of treated as context. See
hooks/scripts/handoff-read.sh for the same reasoning.
"""

import json
import sys

import crew_state


def _crew_line(state):
    roles = state.get("roles") or []
    tier = state.get("tier")
    parts = ["## crew"]
    parts.append(f"tier {tier}" if tier is not None else "tier unset")
    parts.append(f"{len(roles)} role{'' if len(roles) == 1 else 's'}")
    tracker = state.get("tracker")
    if tracker:
        parts.append(f"tracker {tracker}")
    return f"{parts[0]} — " + ", ".join(parts[1:])


def _health_line(state):
    health = state.get("health") or {}
    if health.get("rate") is None:
        return "health: no reviews recorded yet"
    return (
        f"health: {health['rate']} BLOCK+FIX per ticket "
        f"over {health['tickets']} — {health['verdict']}"
    )


def _work_line(state):
    work = state.get("work") or {}
    ticket = work.get("ticket")
    open_part = f"{ticket} open" if ticket else "no ticket open"
    handoff = "handoff pending" if work.get("handoffPending") else "no handoff"
    return f"work: {open_part}, {handoff}"


def _knowledge_line(state):
    knowledge = state.get("knowledge") or {}
    graph = knowledge.get("graph") or {}
    total = knowledge.get("subsystems", 0)
    behind = knowledge.get("behind") or []
    if total:
        maps = f"{total} subsystem{'' if total == 1 else 's'} mapped"
        maps += ", anchors current" if not behind else (
            f", {len(behind)} anchored behind HEAD"
        )
    else:
        maps = "no codemap"
    if not graph.get("present"):
        graph_part = "no graph"
    else:
        graph_part = "graph current" if graph.get("current") else "graph behind HEAD"
    return f"knowledge: {maps}; {graph_part}"


def render(state):
    """The brief's lines. Empty list means print nothing at all."""
    if not state.get("isCrew"):
        return []
    pm = state.get("pm") or {}
    if not pm.get("enabled", True):
        return []
    return [
        _crew_line(state),
        _health_line(state),
        _work_line(state),
        _knowledge_line(state),
    ]


def main(argv=None):
    """Hook entry point. Reads the SessionStart payload from stdin. Always 0."""
    del argv
    try:
        raw = sys.stdin.read()
    except OSError:
        return 0
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    root = payload.get("cwd") or crew_state.os.environ.get(
        "CLAUDE_PROJECT_DIR"
    ) or crew_state.os.getcwd()

    try:
        lines = render(crew_state.collect(root))
    except Exception:  # pylint: disable=broad-except
        # A SessionStart hook that raises breaks every session opened in this
        # repository. Silence is the only acceptable failure mode.
        return 0
    if lines:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest plugin/crew/tests/test_pm_brief.py -v`
Expected: all pass, none skipped, none errored

- [ ] **Step 5: Lint, then Codex review**

- [ ] **Step 6: Commit**

```bash
git add plugin/crew/hooks/scripts/pm_brief.py plugin/crew/tests/test_pm_brief.py
git commit -m "feat(crew): render the PM's quiet session-start brief"
```

---

## Task 6: `pm_brief.py` — expanded mode and the line cap

**Files:**
- Modify: `plugin/crew/hooks/scripts/pm_brief.py`
- Modify: `plugin/crew/tests/test_pm_brief.py`

**Interfaces:**
- Consumes: `render` (Task 5), `crew_state.TRIGGERS` (Task 4).
- Produces: `FINDINGS: dict[str, tuple[str, str]]` — trigger name mapped to
  `(finding text, recommended next action)`. `render` gains expansion.

- [ ] **Step 1: Write the failing tests**

```python
def _with(trigger, **over):
    state = dict(HEALTHY, triggers=[trigger])
    state.update(over)
    return state


def test_expanded_brief_names_the_finding_and_one_action():
    out = "\n".join(pm_brief.render(_with("upgradeNeeded", schema=1)))
    assert "/crew:upgrade" in out


def test_each_trigger_has_a_finding_and_an_action():
    # A trigger with no entry would fire silently, which is worse than not
    # firing: the state says something is wrong and the brief says nothing.
    for name in pm_brief.crew_state.TRIGGERS:
        assert name in pm_brief.FINDINGS
        finding, action = pm_brief.FINDINGS[name]
        assert finding and action


def test_expanded_brief_states_report_only_authority():
    out = "\n".join(pm_brief.render(_with("upgradeNeeded", schema=1))).lower()
    assert "recommend" in out or "report" in out


def test_healthy_state_stays_quiet():
    out = pm_brief.render(HEALTHY)
    assert len(out) <= HEALTHY["pm"]["quietLines"]
    assert "/crew:upgrade" not in "\n".join(out)


def test_every_trigger_at_once_respects_max_lines():
    state = dict(HEALTHY, schema=1,
                 triggers=list(pm_brief.crew_state.TRIGGERS))
    out = pm_brief.render(state)
    assert len(out) <= HEALTHY["pm"]["maxLines"]


def test_truncation_points_at_the_pm_command():
    state = dict(HEALTHY, schema=1,
                 triggers=list(pm_brief.crew_state.TRIGGERS),
                 pm=dict(HEALTHY["pm"], maxLines=7))
    out = pm_brief.render(state)
    assert len(out) <= 7
    assert "/crew:pm" in out[-1]


def test_truncation_keeps_the_highest_priority_finding():
    state = dict(HEALTHY, schema=1,
                 triggers=["upgradeNeeded", "ticketsTooLarge"],
                 pm=dict(HEALTHY["pm"], maxLines=7))
    out = "\n".join(pm_brief.render(state))
    assert "/crew:upgrade" in out


def test_quiet_mode_config_never_expands():
    state = dict(HEALTHY, schema=1, triggers=["upgradeNeeded"],
                 pm=dict(HEALTHY["pm"], mode="quiet"))
    assert "/crew:upgrade" not in "\n".join(pm_brief.render(state))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest plugin/crew/tests/test_pm_brief.py -v -k "expanded or trigger or truncation or quiet_mode"`
Expected: FAIL — no attribute `FINDINGS`

- [ ] **Step 3: Write the implementation**

Add to `pm_brief.py`, and replace `render`:

```python
# One finding and exactly one next action per trigger. One action because a
# brief that lists three is a brief nobody acts on.
FINDINGS = {
    "upgradeNeeded": (
        "this setup predates the PM and the code graph (config has no schema)",
        "run /crew:upgrade — it backs up the codemap first and reports "
        "conflicts rather than overwriting them",
    ),
    "handoffPending": (
        "a handoff note from a previous session is still in place",
        "finish or delete it — a stale handoff is injected into every "
        "session as though it were current",
    ),
    "graphStale": (
        "the code graph is missing or older than HEAD",
        "run /crew:onboard, or graphify . --no-viz to refresh it",
    ),
    "knowledgeBehind": (
        "some codemap anchors are behind HEAD, so those notes may describe "
        "code that has since changed",
        "run /crew:onboard --refresh <subsystem> before relying on them",
    ),
    "reviewNotWorking": (
        "review is finding almost nothing, which usually means it is broken "
        "rather than that the code is clean",
        "check that Codex is really running, the diff is not empty, and the "
        "base branch is right — before adding any role",
    ),
    "ticketsTooLarge": (
        "findings per ticket are high enough that the tickets are probably "
        "too large",
        "cut ticket scope rather than adding roles",
    ),
}

_AUTHORITY_NOTE = (
    "The manager reports and recommends; it does not change roles, tier, or "
    "delete anything without being asked."
)

_TRUNCATED = "More findings than fit here — run /crew:pm for the full report."


def render(state):
    """The brief's lines. Empty list means print nothing at all."""
    if not state.get("isCrew"):
        return []
    pm = state.get("pm") or {}
    if not pm.get("enabled", True):
        return []

    quiet = [
        _crew_line(state),
        _health_line(state),
        _work_line(state),
        _knowledge_line(state),
    ]

    triggers = state.get("triggers") or []
    if pm.get("mode") != "adaptive" or not triggers:
        return quiet[: max(1, int(pm.get("quietLines", 8)))]

    lines = list(quiet) + [""]
    for name in triggers:
        entry = FINDINGS.get(name)
        if not entry:
            continue
        finding, action = entry
        lines.append(f"- {finding}")
        lines.append(f"  -> {action}")
    lines.append("")
    lines.append(_AUTHORITY_NOTE)

    cap = max(2, int(pm.get("maxLines", 40)))
    if len(lines) <= cap:
        return lines
    # Truncate from the bottom: crew_state returns triggers in priority order,
    # so what survives is the most actionable finding.
    return lines[: cap - 1] + [_TRUNCATED]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest plugin/crew/tests/ -v`
Expected: all pass, none skipped, none errored

- [ ] **Step 5: Lint, then Codex review**

- [ ] **Step 6: Commit**

```bash
git add plugin/crew/hooks/scripts/pm_brief.py plugin/crew/tests/test_pm_brief.py
git commit -m "feat(crew): expand the PM brief on a finding, capped and prioritised"
```

---

## Task 7: Hook wrappers and `hooks.json` — including section E

**Files:**
- Create: `plugin/crew/hooks/scripts/pm-brief.sh`
- Create: `plugin/crew/hooks/scripts/pm-brief.ps1`
- Create: `plugin/crew/hooks/scripts/handoff-write.ps1`
- Create: `plugin/crew/hooks/scripts/notify.ps1`
- Modify: `plugin/crew/hooks/hooks.json`

**Interfaces:**
- Consumes: `pm_brief.py` (Tasks 5–6).
- Produces: registered hooks. Nothing imports these.

**Why wrappers rather than two implementations.** The repo requires both
flavours wired. Two hand-written implementations of the same logic drift, and
the drift is invisible because each platform only ever runs one of them. A
wrapper per platform over one Python module makes identical output structural.

**Why the three existing `.ps1` files were never wired — read this first.**
Only `PreToolUse` has a `matcher`, and it keys on the **tool name** (`Bash` vs
`PowerShell`), which is why `guard` legitimately has two entries.
`SessionStart`, `Stop`, `PreCompact`, and `Notification` have **no matcher at
all**. Registering both flavours there does not pick one per platform — it runs
both, on any machine that has both interpreters. On a Windows box with Git Bash
and PowerShell that means the handoff prints twice, the brief prints twice,
`context-watch` writes its marker and returns exit 2 twice, and `verify-gate` —
a 600-second gate — runs twice per Stop.

So the three unwired `.ps1` files are not an oversight; they are the unresolved
half of this problem. Wiring them naively is a regression, not a fix.

**The fix is a guard inside each `.ps1`, not a change to `hooks.json`.** Every
matcher-less PowerShell hook exits early when a POSIX bash is reachable, so bash
wins where both exist and the `.ps1` still covers the case it exists for —
Windows with no POSIX layer, where the `.sh` is silently inert. `guard.ps1` is
**excluded**: `PreToolUse` discriminates by tool name, so both entries there are
correct and adding the guard would disable PowerShell command inspection.

- [ ] **Step 1: Write `pm-brief.sh`**

```bash
#!/usr/bin/env bash
# SessionStart hook. Prints the crew PM's brief; stdout is injected as context.
#
# Unlike handoff-read.sh this does NOT filter on source -- it must fire on
# `startup` too, which is the whole point: before this hook existed, crew said
# nothing at all when you opened a fresh session.
#
# Thin wrapper on purpose. The logic lives in pm_brief.py so that the bash and
# PowerShell paths cannot drift.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
exec "$PY" "$DIR/pm_brief.py"
```

- [ ] **Step 2: Write `pm-brief.ps1`**

```powershell
# SessionStart hook. Prints the crew PM's brief; stdout is injected as context.
# PowerShell twin of pm-brief.sh -- both delegate to pm_brief.py so neither can
# drift from the other.
$ErrorActionPreference = 'SilentlyContinue'

# SessionStart has no matcher, so BOTH this and pm-brief.sh are registered and
# both fire wherever both interpreters exist -- printing the brief twice. bash
# wins when it is reachable; this script covers the case it exists for, which is
# Windows with no POSIX layer, where the .sh is silently inert.
if (Get-Command bash -ErrorAction SilentlyContinue) { exit 0 }

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'pm_brief.py')
exit 0
```

- [ ] **Step 3: Add the same guard to the three existing `.ps1` hooks**

`handoff-read.ps1`, `verify-gate.ps1`, and `context-watch.ps1` each get the
identical four-line guard, with the identical comment. They are about to be
wired for the first time, and without it wiring them is a regression:
double-printed handoffs, a doubled `context-watch` marker, and a 600-second
verify gate running twice per Stop.

**Do not add it to `guard.ps1`.** `PreToolUse` discriminates by tool name, so
its two entries are both correct — the guard would disable PowerShell command
inspection entirely.

- [ ] **Step 4: Write `handoff-write.ps1` and `notify.ps1`**

Port `handoff-write.sh` and `notify.sh` line for line, each opening with the
same guard. Read each `.sh` first and mirror its behaviour exactly — same paths,
same config keys, same exit codes. Do not improve them in this task; a port that
also changes behaviour cannot be reviewed against its original.

- [ ] **Step 5: Rewrite `hooks.json`**

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/handoff-read.sh", "timeout": 15 }] },
      { "hooks": [{ "type": "command", "shell": "powershell", "command": "& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/handoff-read.ps1'", "timeout": 15 }] },
      { "hooks": [{ "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/pm-brief.sh", "timeout": 20 }] },
      { "hooks": [{ "type": "command", "shell": "powershell", "command": "& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/pm-brief.ps1'", "timeout": 20 }] }
    ],
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard.sh", "timeout": 10 }] },
      { "matcher": "PowerShell",
        "hooks": [{ "type": "command", "shell": "powershell", "command": "& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard.ps1'", "timeout": 10 }] }
    ],
    "PreCompact": [
      { "hooks": [{ "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/handoff-write.sh", "timeout": 30 }] },
      { "hooks": [{ "type": "command", "shell": "powershell", "command": "& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/handoff-write.ps1'", "timeout": 30 }] }
    ],
    "Notification": [
      { "hooks": [{ "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh waiting 'Claude is waiting on you'", "timeout": 15 }] },
      { "hooks": [{ "type": "command", "shell": "powershell", "command": "& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.ps1' waiting 'Claude is waiting on you'", "timeout": 15 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/verify-gate.sh", "timeout": 600 }] },
      { "hooks": [{ "type": "command", "shell": "powershell", "command": "& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/verify-gate.ps1'", "timeout": 600 }] },
      { "hooks": [{ "type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/context-watch.sh", "timeout": 20 }] },
      { "hooks": [{ "type": "command", "shell": "powershell", "command": "& '${CLAUDE_PLUGIN_ROOT}/hooks/scripts/context-watch.ps1'", "timeout": 20 }] }
    ]
  }
}
```

- [ ] **Step 6: Verify — every referenced script exists, every script is referenced**

```bash
python - <<'PY'
import json, os, re
root = "plugin/crew"
wired = set(re.findall(r"hooks/scripts/([A-Za-z0-9_.-]+)",
            open(f"{root}/hooks/hooks.json", encoding="utf-8").read()))
disk = {f for f in os.listdir(f"{root}/hooks/scripts")
        if f.endswith((".sh", ".ps1"))}
print("wired but absent:", sorted(wired - disk))
print("on disk but dead:", sorted(disk - wired))
PY
```
Expected: both lists empty. A non-empty second list is the dead-code condition
`CLAUDE.md` prohibits.

- [ ] **Step 7: Verify `hooks.json` is valid JSON, and that every matcher-less PowerShell hook carries the guard**

```bash
python - <<'PY'
import json, os, re
root = "plugin/crew/hooks"
spec = json.load(open(f"{root}/hooks.json", encoding="utf-8"))["hooks"]
print("json ok")

# Any .ps1 registered on an event with no matcher fires alongside its .sh twin
# and MUST guard against it. guard.ps1 is exempt: PreToolUse matches on tool
# name, so its two entries are both correct.
needs = set()
for event, entries in spec.items():
    for entry in entries:
        if entry.get("matcher"):
            continue
        for hook in entry.get("hooks", []):
            for name in re.findall(r"hooks/scripts/([A-Za-z0-9_.-]+\.ps1)",
                                   hook.get("command", "")):
                needs.add(name)

missing = []
for name in sorted(needs):
    body = open(f"{root}/scripts/{name}", encoding="utf-8").read()
    if "Get-Command bash" not in body:
        missing.append(name)
print("matcher-less .ps1 hooks:", sorted(needs))
print("MISSING the double-fire guard:", missing)
assert not missing, missing
PY
```
Expected: `MISSING the double-fire guard: []`

- [ ] **Step 8: Verify the composed hook set fires each hook exactly once**

This is the check that the per-script tests cannot make. Running `pm-brief.sh`
and `pm-brief.ps1` separately and diffing them proves they agree; it says
nothing about how many times the *registered set* runs.

```bash
# A crew fixture, so the brief actually has something to print.
FIX="$(mktemp -d)/fire"; mkdir -p "$FIX/.crew"; cd "$FIX"
git init -q && git config user.email t@e.invalid && git config user.name T
echo x > f.txt && git add . && git commit -qm init
printf '{"schema":2,"tier":0,"roles":[],"tracker":"files"}' > .crew/config.json

# Simulate what Claude Code does: run every registered SessionStart entry.
printf '{"source":"startup","cwd":"%s"}' "$FIX" | bash <plugin>/hooks/scripts/pm-brief.sh  >  out.txt
printf '{"source":"startup","cwd":"%s"}' "$FIX" | pwsh -NoProfile -File <plugin>/hooks/scripts/pm-brief.ps1 >> out.txt
grep -c '^## crew' out.txt
```
Expected: **`1`**. A `2` means the guard is not working and the brief will print
twice on every session — which is the defect this step exists to catch.

Repeat for `verify-gate` (both entries, one Stop payload) and `context-watch`,
confirming a single `.crew/.handoff-requested` write rather than two.

- [ ] **Step 9: Codex review**

- [ ] **Step 10: Commit**

```bash
git add plugin/crew/hooks/
git commit -m "feat(crew): wire the PM brief at SessionStart and fix PowerShell hook parity"
```

---

## Task 8: `crew-pm` skill

**Files:**
- Create: `plugin/crew/skills/crew-pm/SKILL.md`
- Create: `plugin/crew/skills/crew-pm/onboarding.md`
- Create: `plugin/crew/skills/crew-pm/offboarding.md`

**Interfaces:**
- Consumes: `crew_state.py` (invoked as a script), `crew-scaling`, `crew-context`,
  `crew-setup`.
- Produces: the `crew-pm` skill name, referenced by `commands/pm.md` (Task 9)
  and `agents/pm.md` (Task 9).

**Frontmatter — verbatim. The description's narrowness is the deliverable, not
a detail.**

```markdown
---
name: crew-pm
description: Manage the crew itself - report crew status, decide which roles the crew should have, onboard a repo or a role, offboard a role, and keep session context and the code map from going stale. Use when the user asks about crew status, who is on the crew, whether the crew is the right size, onboarding or offboarding a role or repo, or says the map is out of date. Not for general "how do I" questions.
---
```

Required sections in `SKILL.md`:

- **Reading state** — run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py`
  and interpret the JSON. Never re-derive by hand; the hook and the skill must
  agree or the brief becomes untrustworthy.
- **Authority: report and recommend only.** Role, tier, and deletion changes need
  the user's yes. Matches `commands/scale.md`'s existing "Add nothing without
  asking".
- **The anchor caveat** — `behind` means the anchor is not HEAD, which is not the
  same as wrong. The per-path check
  (`git diff --name-only <anchor-sha>..HEAD -- <paths>`) is this skill's job,
  because the hook cannot afford it.
- **Routing** — scaling arithmetic to `crew-scaling`; handoffs to `crew-context`;
  first-time repo setup to `crew-setup`; graph work to `crew-graph`. State the
  routing rather than duplicating the content.
- Pointers to `onboarding.md` and `offboarding.md`, loaded on demand.

`onboarding.md`: onboarding a repo (delegate to `crew-setup`, then `/crew:onboard`,
then confirm `verify.json` / `secrets.md` / `e2e/` exist) and onboarding a role
(state its cost — a full context load plus the whole `CLAUDE.md` hierarchy on
every invocation — name the defect class it covers, and check `metrics.md`
supports it first).

`offboarding.md`: remove from `config.json.roles`; recompute `tier` from the
tier table; append a dated line to `.crew/metrics.md` recording the removal and
its reason; delete role-specific artifacts; and **name the failure mode now
uncovered**. A role removed without naming what it was catching is a silent
coverage regression, which is the one outcome offboarding must not produce.

- [ ] **Step 1: Write the three files** per the above.

- [ ] **Step 2: Verify the description does not overlap a sibling**

```bash
python - <<'PY'
import glob, re
for path in sorted(glob.glob("plugin/crew/skills/*/SKILL.md")):
    body = open(path, encoding="utf-8").read()
    found = re.search(r"^description:\s*(.+)$", body, re.M)
    print(f"{path.split('/')[-2]:20} {len(found.group(1)) if found else 0:4}  "
          f"{(found.group(1)[:70] if found else 'MISSING')}")
PY
```
Expected: `crew-pm`'s description names crew-management vocabulary only. If it
reads as though it could answer a general question, it is too broad — that is
the `find-skills` failure this plan exists partly to fix.

- [ ] **Step 3: Codex review** — ask specifically whether the description could
  plausibly fire on a general "how do I" question.

- [ ] **Step 4: Commit**

```bash
git add plugin/crew/skills/crew-pm/
git commit -m "feat(crew): add the crew-pm skill with onboarding and offboarding"
```

---

## Task 9: `crew:pm` agent and `/crew:pm` command

**Files:**
- Create: `plugin/crew/agents/pm.md`
- Create: `plugin/crew/commands/pm.md`
- Modify: `plugin/crew/commands/scale.md`
- Modify: `plugin/crew/skills/crew-scaling/SKILL.md`

**Interfaces:**
- Consumes: `crew-pm` skill (Task 8), `crew_state.py` (Task 4).
- Produces: agent name `crew:pm`; command `/crew:pm` with subcommands
  `onboard <role>` and `offboard <role>`.

**Agent frontmatter — verbatim:**

```markdown
---
name: pm
description: Heavy crew-management analysis in its own context - correlate defect classes across the whole metrics history, audit every codemap anchor per path, or build the evidence for a tier change. Use when the analysis would cost more context than the answer is worth in the main session.
tools: Read, Bash, Grep, Glob
model: inherit
memory: project
---
```

Agent body must state: writes only under `.crew/`; returns a report under 200
words plus a recommendation; **never applies a change** — the authority decision
is report-only, and an agent that quietly edits `config.json` breaks it.

**Command frontmatter — verbatim:**

```markdown
---
description: Talk to the crew's manager - status, onboarding, offboarding
allowed-tools: Read, Write, Edit, Bash, Agent
---
```

Command body: `$ARGUMENTS` routing for the bare form, `onboard <role>`, and
`offboard <role>`; run `crew_state.py` first in every path; delegate to
`crew:pm` when the analysis is large; never change roles or tier without an
explicit yes.

`scale.md` and `crew-scaling/SKILL.md` gain one line each pointing at
`/crew:pm offboard <role>` for removals — the tier table already implies
shrinking is possible but nothing implemented it.

- [ ] **Step 1: Write `agents/pm.md` and `commands/pm.md`.**

- [ ] **Step 2: Add the offboarding cross-references.**

- [ ] **Step 3: Verify frontmatter parses and names are unique**

```bash
python - <<'PY'
import glob, re
names = {}
for path in glob.glob("plugin/crew/agents/*.md") + glob.glob("plugin/crew/commands/*.md"):
    head = open(path, encoding="utf-8").read().split("---")[1]
    assert "description:" in head, f"{path}: no description"
    for line in head.splitlines():
        if line.startswith("name:"):
            n = line.split(":", 1)[1].strip()
            assert n not in names, f"duplicate agent name {n}: {path} and {names[n]}"
            names[n] = path
print("ok:", len(names), "named")
PY
```

- [ ] **Step 4: Codex review**

- [ ] **Step 5: Commit**

```bash
git add plugin/crew/agents/pm.md plugin/crew/commands/pm.md plugin/crew/commands/scale.md plugin/crew/skills/crew-scaling/SKILL.md
git commit -m "feat(crew): add the crew:pm agent and /crew:pm with offboarding"
```

---

## Task 10: `graph_reconcile.py` — codemap against graph

**Files:**
- Create: `plugin/crew/skills/crew-graph/scripts/graph_reconcile.py`
- Test: `plugin/crew/tests/test_upgrade.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — deliberately standalone and pure.
- Produces:
  - `KEEP: frozenset[str]` = `{"Does", "Landmines", "Unverified"}`
  - `DERIVE: frozenset[str]` = `{"Entry points", "Owns data", "Calls out to"}`
  - `split_sections(text: str) -> dict[str, list[str]]` — `## ` heading to its
    body lines, preserving order and original text
  - `reconcile(text: str, derived: dict[str, list[str]]) -> dict` with keys
    `body: str` (the new file text), `conflicts: list[str]`,
    `added: list[str]`, `touched: list[str]`

**Comparison granularity is by file path, not by `path:line`.** A refactor
shifts line numbers constantly; comparing on `path:line` would report every
hand-written entry as a contradiction, and an `UPGRADE.md` that is mostly
line-drift noise is a report nobody reads. A moved line is an update. A file the
graph has never heard of is a conflict.

**The rule this module enforces:** `KEEP` sections pass through byte-identical.
`DERIVE` sections get graph facts added. A `DERIVE` line the graph contradicts
is **retained and reported**, never replaced — the graph misses generated call
sites, reflection, and dynamic dispatch.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for codemap/graph reconciliation and the v1 -> v2 upgrade."""
import json

import context  # noqa: F401  pylint: disable=unused-import
import crew_upgrade
import graph_reconcile
import helpers

V1_MAP = """# auth
anchor: repo@0000000
verified: 2026-01-01

## Does
Authenticates requests.

## Entry points
- `src/auth.py:10` — called by the router

## Calls out to
- billing at `src/auth.py:99`

## Landmines
- The session cache is not invalidated on password change.

## Unverified
- Whether the legacy path is still reachable.
"""


def test_split_sections_finds_every_heading():
    got = graph_reconcile.split_sections(V1_MAP)
    assert set(got) >= {"Does", "Entry points", "Calls out to",
                        "Landmines", "Unverified"}


def test_landmines_survive_byte_identical():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": ["- `x.py:1` — new"]})
    assert "The session cache is not invalidated on password change." in out["body"]


def test_does_section_survives():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": []})
    assert "Authenticates requests." in out["body"]


def test_derived_facts_are_added():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/cli.py:7` — called by the CLI"]}
    )
    assert "src/cli.py:7" in out["body"]
    assert "Entry points" in out["touched"]


def test_a_line_number_shift_is_not_a_conflict():
    """The noise case. The map says src/auth.py:10, the graph says :44 --
    same file, moved line. Reporting that as a contradiction would make
    UPGRADE.md mostly line-drift noise on any repo that has been refactored,
    and a report nobody reads protects nothing.
    """
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/auth.py:44` — called by the cron"]}
    )
    assert out["conflicts"] == []
    assert "src/auth.py:10" in out["body"]   # the human's note is still there
    assert out["added"] == []                # and the graph added nothing new


def test_a_file_the_graph_does_not_know_is_a_conflict():
    # billing.py is claimed by the map and absent from the graph entirely.
    out = graph_reconcile.reconcile(
        V1_MAP, {"Calls out to": ["- payments at `src/pay.py:3`"]}
    )
    assert "src/billing.py" not in V1_MAP  # guard: the fixture says `src/auth.py:99`
    assert any("auth.py" in c for c in out["conflicts"])
    assert "src/auth.py:99" in out["body"]  # kept regardless


def test_a_new_file_from_the_graph_is_added():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Entry points": ["- `src/cron.py:1` — called by the scheduler"]}
    )
    assert "src/cron.py:1" in out["body"]
    assert out["added"]
    assert "Entry points" in out["touched"]


def test_a_keep_section_is_never_touched_even_if_derived_is_supplied():
    out = graph_reconcile.reconcile(
        V1_MAP, {"Landmines": ["- graph says something"]}
    )
    assert "graph says something" not in out["body"]
    assert "Landmines" not in out["touched"]


def test_untouched_sections_are_not_in_touched():
    out = graph_reconcile.reconcile(V1_MAP, {"Entry points": []})
    assert "Calls out to" not in out["touched"]


def test_reconcile_is_idempotent():
    derived = {"Entry points": ["- `src/cli.py:7` — called by the CLI"]}
    once = graph_reconcile.reconcile(V1_MAP, derived)
    assert once["added"], "first pass must actually add something"
    twice = graph_reconcile.reconcile(once["body"], derived)
    assert twice["body"] == once["body"]
    assert twice["added"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest plugin/crew/tests/test_upgrade.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'graph_reconcile'`

- [ ] **Step 3: Write the implementation**

```python
"""Reconciles a hand-written codemap note against facts derived from the graph.

Pure text in, text out. No file or graph access, so the policy this module
encodes -- which sections a machine may rewrite and which it may not -- is
testable without building a graph first.

The split is the whole design:

  KEEP    human judgment an AST parser cannot produce. Passed through
          byte-identical, always.
  DERIVE  mechanical structure the graph knows better. Graph facts are ADDED;
          an existing line the graph does not corroborate is retained and
          reported, because the graph misses generated call sites, reflection,
          and dynamic dispatch.
"""

import re

KEEP = frozenset({"Does", "Landmines", "Unverified"})
DERIVE = frozenset({"Entry points", "Owns data", "Calls out to"})

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_ANCHOR_TOKEN_RE = re.compile(r"`([^`]+)`")
_LINE_SUFFIX_RE = re.compile(r":\d+$")


def split_sections(text):
    """Map each `## ` heading to its body lines. Preamble is keyed ''."""
    sections, current = {}, ""
    sections[current] = []
    for line in text.splitlines():
        found = _HEADING_RE.match(line)
        if found:
            current = found.group(1)
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return sections


def _path_of(token):
    """The file path from a `path:line` anchor, dropping the line number.

    Comparison is by path, never by path:line. A refactor that shifts line
    numbers would otherwise turn every hand-written entry into a
    "contradiction", and an UPGRADE.md that is mostly line-drift noise is a
    report nobody reads -- which protects nothing.
    """
    return token.rsplit(":", 1)[0] if _LINE_SUFFIX_RE.search(token) else token


def _paths(lines):
    """Anchored file paths in a set of lines -- what two claims are compared on."""
    return {
        _path_of(token)
        for line in lines
        for token in _ANCHOR_TOKEN_RE.findall(line)
    }


def reconcile(text, derived):
    """Merge graph-derived facts into a codemap note.

    Returns {body, conflicts, added, touched}. `conflicts` names existing
    claims the graph did not corroborate; they stay in `body`.
    """
    sections = split_sections(text)
    conflicts, added, touched = [], [], []

    for heading, new_lines in derived.items():
        if heading in KEEP or heading not in sections:
            continue
        if heading not in DERIVE:
            continue

        existing = sections[heading]
        have = _paths(existing)
        want = _paths(new_lines)

        # A graph line whose path is already claimed is an update to an
        # existing entry (typically a shifted line number), not a new fact.
        fresh = []
        for line in new_lines:
            found = _ANCHOR_TOKEN_RE.findall(line)
            if found and _path_of(found[0]) in have:
                continue
            fresh.append(line)

        if fresh:
            body = [ln for ln in existing if ln.strip()]
            sections[heading] = [""] + body + fresh + [""]
            added.extend(fresh)
            touched.append(heading)

        # A conflict is a whole FILE the map claims and the graph does not
        # know about -- not a line that moved.
        for path in sorted(have - want):
            conflicts.append(
                f"{heading}: `{path}` is in the map but not in the graph "
                f"— kept, verify by hand"
            )

    out = []
    for heading, lines in sections.items():
        if heading:
            out.append(f"## {heading}")
        out.extend(lines)
    body = "\n".join(out).rstrip() + "\n"
    return {"body": body, "conflicts": conflicts,
            "added": added, "touched": touched}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest plugin/crew/tests/test_upgrade.py -v`
Expected: all pass, none skipped, none errored

- [ ] **Step 5: Lint, then Codex review** — ask Codex specifically whether
  `reconcile` can ever drop a `KEEP` line, and whether the idempotency test
  actually proves idempotency.

- [ ] **Step 6: Commit**

```bash
git add plugin/crew/skills/crew-graph/scripts/graph_reconcile.py plugin/crew/tests/test_upgrade.py
git commit -m "feat(crew): reconcile codemap notes against the graph without overwriting judgment"
```

---

## Task 11: `crew_upgrade.py` — v1 to v2

**Files:**
- Create: `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py`
- Modify: `plugin/crew/tests/test_upgrade.py`

**Interfaces:**
- Consumes: `graph_reconcile.reconcile` (Task 10), `crew_state.SCHEMA_CURRENT`
  (Task 2).
- Produces:
  - `PM_BLOCK: dict`, `GRAPH_BLOCK: dict` — the v2 config defaults
  - `upgrade_config(cfg: dict) -> dict` — pure; adds blocks, sets `schema`,
    preserves every existing key
  - `backup_codemap(root: str) -> str | None` — returns the backup path
  - `run(root: str, derived: dict[str, dict], force: bool = False) -> dict` —
    with keys `status: str`, `report: str`, `conflicts: list[str]`
  - `main(argv=None) -> int`

- [ ] **Step 1: Write the failing tests**

```python
def test_upgrade_config_sets_schema_two():
    assert crew_upgrade.upgrade_config({})["schema"] == 2


def test_upgrade_config_adds_pm_and_graph_blocks():
    got = crew_upgrade.upgrade_config({"tier": 0})
    assert got["pm"]["mode"] == "adaptive"
    assert got["pm"]["authority"] == "report-only"
    assert got["graph"]["mode"] == "code-only"
    assert got["graph"]["obsidian"]["confirmed"] is False


def test_upgrade_config_preserves_unknown_keys():
    # A config written by a newer crew than the one running must survive.
    got = crew_upgrade.upgrade_config({"somethingNew": {"a": 1}, "tier": 2})
    assert got["somethingNew"] == {"a": 1}
    assert got["tier"] == 2


def test_upgrade_config_does_not_clobber_an_existing_pm_block():
    got = crew_upgrade.upgrade_config({"pm": {"quietLines": 3}})
    assert got["pm"]["quietLines"] == 3
    assert got["pm"]["mode"] == "adaptive"  # defaults still filled in


def test_obsidian_confirmed_defaults_false_even_if_dir_is_set():
    got = crew_upgrade.upgrade_config(
        {"graph": {"obsidian": {"dir": "/somewhere"}}}
    )
    assert got["graph"]["obsidian"]["dir"] == "/somewhere"
    assert got["graph"]["obsidian"]["confirmed"] is False


def test_backup_is_taken_before_any_write(tmp_path):
    root = helpers.make_repo(tmp_path, config={"tier": 0},
                             codemap={"auth": V1_MAP})
    crew_upgrade.run(str(root), {})
    backup = root / ".crew" / "codemap.v1.bak" / "auth.md"
    assert backup.read_text(encoding="utf-8") == V1_MAP


def test_run_writes_schema_two_to_disk(tmp_path):
    root = helpers.make_repo(tmp_path, config={"tier": 0})
    crew_upgrade.run(str(root), {})
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    assert cfg["schema"] == 2


def test_second_run_reports_already_current(tmp_path):
    root = helpers.make_repo(tmp_path, config={"tier": 0})
    crew_upgrade.run(str(root), {})
    assert crew_upgrade.run(str(root), {})["status"] == "already current"


def test_force_reruns_a_current_setup(tmp_path):
    root = helpers.make_repo(tmp_path, config={"schema": 2})
    assert crew_upgrade.run(str(root), {}, force=True)["status"] == "upgraded"


def test_conflicts_land_in_the_report_not_in_the_map(tmp_path):
    root = helpers.make_repo(tmp_path, config={"tier": 0},
                             codemap={"auth": V1_MAP})
    # The graph knows src/cron.py and does NOT know src/auth.py at all, so the
    # map's src/auth.py claim is a genuine contradiction rather than line drift.
    derived = {"auth": {"Entry points": ["- `src/cron.py:1` — scheduler"]}}
    out = crew_upgrade.run(str(root), derived)
    report = (root / ".crew" / "codemap" / "UPGRADE.md").read_text(encoding="utf-8")
    assert "auth.py" in report
    body = (root / ".crew" / "codemap" / "auth.md").read_text(encoding="utf-8")
    assert "src/auth.py:10" in body   # the contradicted claim is KEPT
    assert "src/cron.py:1" in body    # the graph's fact is ADDED
    assert out["conflicts"]


def test_anchor_is_bumped_only_on_a_touched_file(tmp_path):
    root = helpers.make_repo(
        tmp_path, config={"tier": 0},
        codemap={"auth": V1_MAP, "billing": V1_MAP.replace("# auth", "# billing")},
    )
    derived = {"auth": {"Entry points": ["- `src/cron.py:1` — scheduler"]}}
    crew_upgrade.run(str(root), derived)
    head = helpers.head_sha(root)
    auth = (root / ".crew" / "codemap" / "auth.md").read_text(encoding="utf-8")
    billing = (root / ".crew" / "codemap" / "billing.md").read_text(encoding="utf-8")
    assert head in auth
    # billing was not re-verified, so claiming freshness for it would be a lie.
    assert head not in billing
    assert "0000000" in billing


def test_run_on_a_repo_with_no_codemap_still_upgrades_config(tmp_path):
    root = helpers.make_repo(tmp_path, config={"tier": 0})
    assert crew_upgrade.run(str(root), {})["status"] == "upgraded"


def test_run_on_a_non_crew_directory_reports_not_crew(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert crew_upgrade.run(str(plain), {})["status"] == "not a crew repo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest plugin/crew/tests/test_upgrade.py -v -k "upgrade_config or backup or run or force or conflict or anchor"`
Expected: FAIL — `ModuleNotFoundError: No module named 'crew_upgrade'`

- [ ] **Step 3: Write the implementation**

Full module. Note `SCHEMA_CURRENT` is imported from `crew_state` rather than
redefined — two copies of a schema constant is how a migration ships that
disagrees with the thing it migrates to.

```python
"""Upgrades a v1 crew setup (no `schema` key) to v2.

Order matters and is not negotiable: back up, then upgrade config, then
reconcile, then report. The backup exists so that every later step can be
non-destructive in practice as well as in intent.

Two rules this module exists to enforce:

  * A codemap `anchor:` is bumped only on a file this run actually re-verified.
    A false freshness claim is worse than an honest stale one, because the
    entire freshness rule depends on the anchor being true.
  * A conflict between the map and the graph is written to the report, never
    applied to the map.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import graph_reconcile

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, os.pardir, "hooks", "scripts",
))
import crew_state  # pylint: disable=wrong-import-position

PM_BLOCK = {
    "enabled": True,
    "mode": "adaptive",
    "quietLines": 8,
    "maxLines": 40,
    "authority": "report-only",
}

GRAPH_BLOCK = {
    "enabled": True,
    "tool": "graphify",
    "out": "graphify-out",
    "mode": "code-only",
    "commitHook": False,
    "obsidian": {"enabled": False, "dir": None, "confirmed": False},
}

_ANCHOR_LINE_RE = re.compile(r"^(anchor:\s*\S*@?)([0-9a-f]{7,40})",
                             re.MULTILINE | re.IGNORECASE)


def _merged(defaults, supplied):
    """defaults, overlaid with anything already present. Recurses one level."""
    out = dict(defaults)
    if not isinstance(supplied, dict):
        return out
    for key, value in supplied.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merged(out[key], value)
        else:
            out[key] = value
    return out


def upgrade_config(cfg):
    """v1 config -> v2. Pure. Preserves every key it does not know about."""
    out = dict(cfg)
    out["pm"] = _merged(PM_BLOCK, cfg.get("pm"))
    out["graph"] = _merged(GRAPH_BLOCK, cfg.get("graph"))
    # obsidian.confirmed is a consent flag, not a setting. An upgrade must
    # never grant it -- only the user, in session, can.
    out["graph"]["obsidian"]["confirmed"] = bool(
        (cfg.get("graph") or {}).get("obsidian", {}).get("confirmed") is True
    )
    out["schema"] = crew_state.SCHEMA_CURRENT
    return out


def backup_codemap(root):
    """Copy .crew/codemap/ aside. Returns the path, or None if there is none."""
    src = os.path.join(root, ".crew", "codemap")
    if not os.path.isdir(src):
        return None
    dst = os.path.join(root, ".crew", "codemap.v1.bak")
    if os.path.exists(dst):
        return dst          # a previous run already took one; do not overwrite
    shutil.copytree(src, dst)
    return dst


def _head(root):
    try:
        done = subprocess.run(
            ("git", "rev-parse", "--short=7", "HEAD"), cwd=root,
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _bump_anchor(text, head):
    if not head:
        return text
    return _ANCHOR_LINE_RE.sub(lambda m: m.group(1) + head, text, count=1)


def _report(status, head, results):
    lines = [
        "# Upgrade report",
        f"from schema: 1 -> {crew_state.SCHEMA_CURRENT}",
        f"graph anchor: {head or 'unknown'}",
        "",
        "Nothing below was applied automatically. Conflicts are the map and",
        "the graph disagreeing, and either can be wrong: the graph misses",
        "generated call sites, reflection, and dynamic dispatch.",
        "",
    ]
    conflicts = [c for r in results.values() for c in r["conflicts"]]
    lines.append("## Contradictions — kept in the map, verify by hand")
    lines.extend(f"- {c}" for c in conflicts or ["- none"])
    lines.append("")
    lines.append("## Added by the graph")
    added = [f"- {name}: {len(r['added'])} new line(s)"
             for name, r in sorted(results.items()) if r["added"]]
    lines.extend(added or ["- none"])
    lines.append("")
    lines.append("## Anchors left stale on purpose")
    stale = [f"- {name} — not re-verified this run"
             for name, r in sorted(results.items()) if not r["touched"]]
    lines.extend(stale or ["- none"])
    lines.append("")
    return "\n".join(lines) + "\n"


def run(root, derived, force=False):
    """Upgrade the repo at `root`. `derived` maps subsystem -> graph sections."""
    cfg_path = os.path.join(root, ".crew", "config.json")
    if not os.path.exists(cfg_path):
        return {"status": "not a crew repo", "report": "", "conflicts": []}

    cfg = crew_state.load_config(root)
    if cfg.get("schema", 1) >= crew_state.SCHEMA_CURRENT and not force:
        return {"status": "already current", "report": "", "conflicts": []}

    backup_codemap(root)

    with open(cfg_path, "w", encoding="utf-8") as handle:
        json.dump(upgrade_config(cfg), handle, indent=2, sort_keys=True)
        handle.write("\n")

    head = _head(root)
    mapdir = os.path.join(root, ".crew", "codemap")
    results = {}
    for name, sections in (derived or {}).items():
        path = os.path.join(mapdir, f"{name}.md")
        text = crew_state.read_text(path)
        if text is None:
            continue
        out = graph_reconcile.reconcile(text, sections)
        body = _bump_anchor(out["body"], head) if out["touched"] else out["body"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        results[name] = out

    report = _report("upgraded", head, results)
    if os.path.isdir(mapdir):
        with open(os.path.join(mapdir, "UPGRADE.md"), "w",
                  encoding="utf-8") as handle:
            handle.write(report)

    return {
        "status": "upgraded",
        "report": report,
        "conflicts": [c for r in results.values() for c in r["conflicts"]],
    }


def main(argv=None):
    """CLI entry point. `derived` arrives as a JSON file written by the skill."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--derived", help="path to a JSON file of graph facts")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    derived = {}
    if args.derived:
        text = crew_state.read_text(args.derived)
        if text:
            try:
                derived = json.loads(text)
            except ValueError:
                derived = {}

    out = run(args.root, derived, force=args.force)
    print(out["status"])
    if out["conflicts"]:
        print(f"{len(out['conflicts'])} conflict(s) — see .crew/codemap/UPGRADE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest plugin/crew/tests/ -v`
Expected: all pass, none skipped, none errored

- [ ] **Step 5: Lint, then Codex review** — ask Codex specifically whether
  `run` can lose data on a second invocation, and whether `upgrade_config` can
  ever set `obsidian.confirmed` to true.

- [ ] **Step 6: Commit**

```bash
git add plugin/crew/skills/crew-graph/scripts/crew_upgrade.py plugin/crew/tests/test_upgrade.py
git commit -m "feat(crew): upgrade v1 setups to schema 2 without losing judgment"
```

---

## Task 12: find-skills narrowing

**Files:**
- Modify: `plugin/crew/skills/find-skills/SKILL.md` (the `description:` line)
- Modify: `plugin/crew/skills/find-skills/BUNDLING-NOTE.md`

**Interfaces:** none — prose only.

- [ ] **Step 1: Replace the `description:` line**

Use the replacement already written at `BUNDLING-NOTE.md:30`, verbatim:

```
description: Discover and install agent skills from the open skills ecosystem via the skills CLI. Use only when the user explicitly asks to find, search for, browse, or install a skill or plugin - not for general "how do I" questions, which should be answered directly.
```

Change nothing else in the file. The body is vendored third-party content; the
narrowing is a deliberate local delta and keeping it to one line is what makes
the delta legible next time upstream is pulled in.

- [ ] **Step 2: Update `BUNDLING-NOTE.md`**

Rewrite "The trigger-breadth problem" to record that the narrowing **is
applied**, note that the body remains upstream's, and keep the original
description quoted so a future reader can see what changed and why.

- [ ] **Step 3: Verify the narrowed description is actually in place**

```bash
python - <<'PY'
import re
p = "plugin/crew/skills/find-skills/SKILL.md"
d = re.search(r"^description:\s*(.+)$", open(p, encoding="utf-8").read(), re.M).group(1)
assert "how do I" in d and "not for general" in d.lower(), d
assert "asks how do I do X" not in d, "still the broad upstream description"
print("narrowed:", d[:80], "...")
PY
```

- [ ] **Step 4: Codex review**

- [ ] **Step 5: Commit**

```bash
git add plugin/crew/skills/find-skills/
git commit -m "fix(crew): narrow the vendored find-skills trigger so crew skills fire"
```

---

## Task 13: `crew-graph` skill

**Files:**
- Create: `plugin/crew/skills/crew-graph/SKILL.md`
- Create: `plugin/crew/skills/crew-graph/reconcile.md`

**Interfaces:**
- Consumes: `graph_reconcile.py`, `crew_upgrade.py` (Tasks 10–11).
- Produces: the `crew-graph` skill name, referenced by `commands/onboard.md`
  (Task 14), `commands/upgrade.md` (Task 15), and `crew-pm` (Task 8).

**Frontmatter — verbatim:**

```markdown
---
name: crew-graph
description: Build and query a code graph of this repository with graphify, export it to an Obsidian vault, and keep it fresh on commit. Use when the user asks to build or refresh the code graph, asks what calls what or what connects to what, wants the codebase in Obsidian, or asks how a subsystem is wired.
---
```

Required content:

- **Detect, never auto-install.** `command -v graphify`. If absent, report and
  offer `uv tool install graphifyy` — the PyPI package is `graphifyy`
  (double-y) while the CLI is `graphify`, and other `graphify*` packages on
  PyPI are unaffiliated. Say that, because installing the wrong one is silent.
- **Build.** `graphify . --no-viz` is the default: code-only, **no API key
  needed**. `--no-viz` because the HTML is unopenable past ~5000 nodes and is
  not what an agent reads anyway. Docs, PDFs, and images require an LLM call —
  opt-in, and state the key requirement at the point of choice.
- **Query.** `graphify query`, `graphify path`, `graphify explain`. Prefer these
  over loading `graph.json`; the file is large and the CLI already summarises.
- **Freshness.** `graphify hook install` rebuilds on commit and installs a union
  merge driver for `graph.json`. That merge driver is why `graph.json` is
  committed rather than ignored. `.gitignore` gets the HTML, the wiki, and any
  vault export.
- **Stamp every build.** Immediately after a successful build, write the short
  HEAD sha to `<out>/.crew-graph-sha`:

  ```bash
  git rev-parse --short=7 HEAD > graphify-out/.crew-graph-sha
  ```

  `crew_state._read_graph` reads this and nothing else. Freshness must be a
  recorded sha rather than a file timestamp: `git pull` lands commits authored
  before the graph was built, so a timestamp comparison reports a graph current
  while it knows nothing about the pulled code. A build that skips this step
  leaves the graph permanently reported as stale — which is the safe direction,
  but means the PM nags forever.
- **Obsidian — the gate, stated as a refusal.** Two conditions, both required:
  `graph.obsidian.confirmed == true` in `.crew/config.json`, and a completed
  scratch-directory proof run. Absent either, **refuse and ask**. Default target
  `<vault>/codegraphs/<repo>/`. Upstream says `--obsidian-dir` never overwrites
  your notes or `.obsidian` config; that is verified once against a scratch
  directory rather than trusted against a vault the user cares about.
- **MCP server** — `python -m graphify.serve` documented as optional and off by
  default. It is another always-on surface and should be chosen deliberately.
- **The community-key caveat** — the exact key naming communities in
  `graph.json` is unverified. Read the file before depending on a field name.

`reconcile.md` holds the shared procedure both `/crew:upgrade` and
`/crew:onboard --refresh` follow, so the rules live in one place: which
sections are `KEEP` versus `DERIVE`, that conflicts are reported not applied,
and that anchors are bumped only on re-verified sections.

- [ ] **Step 1: Write both files.**

- [ ] **Step 2: Prove graphify works on this repository, code-only and keyless**

```bash
uv tool install graphifyy
graphify --version
cd "$(mktemp -d)" && git clone --depth 1 <this repo> probe && cd probe
graphify . --no-viz
ls -la graphify-out/
graphify query "what connects the install scripts to the skills catalog?"
```
Expected: `graphify-out/graph.json` exists and the query answers with no API key
set. If it demands a key for a code-only corpus, stop and report — the skill's
central claim is wrong and the plan needs revisiting.

- [ ] **Step 3: Confirm or correct the community key**

```bash
python - <<'PY'
import json
g = json.load(open("graphify-out/graph.json", encoding="utf-8"))
print("top-level keys:", sorted(g)[:20])
node = (g.get("nodes") or [{}])[0]
print("node keys:", sorted(node))
PY
```
Write what you find into `SKILL.md`, replacing the caveat with the real key.

- [ ] **Step 4: Codex review**

- [ ] **Step 5: Commit**

```bash
git add plugin/crew/skills/crew-graph/
git commit -m "feat(crew): add the crew-graph skill for graphify and Obsidian export"
```

---

## Task 14: Obsidian export, gated

**Files:**
- Modify: `plugin/crew/skills/crew-graph/SKILL.md` (the Obsidian section)

**Interfaces:**
- Consumes: `GRAPH_BLOCK["obsidian"]` (Task 11).
- Produces: nothing importable.

- [ ] **Step 1: Prove it on a scratch vault**

```bash
SCRATCH="$(mktemp -d)/vault"
mkdir -p "$SCRATCH/.obsidian" "$SCRATCH/my-notes"
echo '{"probe":true}' > "$SCRATCH/.obsidian/app.json"
echo 'a note I care about' > "$SCRATCH/my-notes/keep.md"
cp -r "$SCRATCH" "$SCRATCH.before"

graphify . --obsidian --obsidian-dir "$SCRATCH"

diff -r "$SCRATCH.before/.obsidian" "$SCRATCH/.obsidian" && echo "config untouched"
diff -r "$SCRATCH.before/my-notes"  "$SCRATCH/my-notes"  && echo "notes untouched"
```
Expected: both diffs clean. **If either is dirty, stop.** Report it and do not
proceed to step 2 — the whole gate exists for this outcome.

- [ ] **Step 2: Write the finding into `SKILL.md`**

Record what the proof run showed — including that `.obsidian` and existing notes
were untouched, and the graphify version it was verified against. A verified
claim with no version attached rots into an unverified one.

- [ ] **Step 3: Ask before touching the real vault**

Present the finding, then ask whether to set
`graph.obsidian.confirmed = true` and target
`C:\repos\claude-memories\codegraphs\<repo>\`. Do not set it unasked. The user
asked to be consulted on this specific decision, so the consultation is the
deliverable, not a formality.

- [ ] **Step 4: Codex review, then commit**

```bash
git add plugin/crew/skills/crew-graph/SKILL.md
git commit -m "docs(crew): record the verified Obsidian export behaviour and its gate"
```

---

## Task 15: `/crew:upgrade` and the `/crew:onboard` rewrite

**Files:**
- Create: `plugin/crew/commands/upgrade.md`
- Modify: `plugin/crew/commands/onboard.md`

**Interfaces:**
- Consumes: `crew_upgrade.py` (Task 11), `crew-graph` and its `reconcile.md`
  (Task 13).
- Produces: `/crew:upgrade`, `/crew:onboard`, `/crew:onboard --refresh <subsystem>`.

**`upgrade.md` frontmatter — verbatim:**

```markdown
---
description: Bring a crew setup created before the PM and the code graph up to date
allowed-tools: Read, Write, Edit, Bash, Agent
---
```

Body must, in order: detect the schema and exit early if current; state that the
codemap is backed up first; build the graph via `crew-graph`; derive the graph
facts per subsystem and hand them to `crew_upgrade.py --derived`; then **report**
conflicts and stale-on-purpose anchors rather than resolving them. It must also
say what it did not do, because a migration that silently declines work reads as
a migration that succeeded.

**`onboard.md` changes** — reorder, keep every existing rule:

1. Build or refresh the graph first (`crew-graph`).
2. Derive the subsystem list from graph communities instead of guessing. Keep
   the existing cap of 6 per run and the existing "say which areas are still
   unmapped".
3. Fill `## Entry points`, `## Owns data`, `## Calls out to` from the graph.
4. Spawn `crew:explorer` **only** for `## Does`, `## Landmines`,
   `## Unverified`. This is where the saving is: explorers stop re-deriving what
   the parser already knows.
5. Keep the anchor freshness rule, the `INDEX.md` rule, and the closing
   "report which of the three are missing" verbatim.
6. `--refresh <subsystem>` follows `crew-graph/reconcile.md` — the same path
   `/crew:upgrade` uses, not a second implementation.

- [ ] **Step 1: Write `upgrade.md`.**
- [ ] **Step 2: Rewrite `onboard.md`.**

- [ ] **Step 3: End-to-end on a fixture, not on a repo you care about**

```bash
FIX="$(mktemp -d)/v1repo"
mkdir -p "$FIX/.crew/codemap" && cd "$FIX" && git init -q
git config user.email t@e.invalid && git config user.name T
echo x > f.py && git add . && git commit -qm init
printf '{"tier":0,"roles":["explorer"],"tracker":"files"}' > .crew/config.json
printf '# core\nanchor: repo@0000000\n\n## Does\nDoes things.\n\n## Entry points\n- `gone.py:1` — stale\n\n## Landmines\n- Keep me.\n' > .crew/codemap/core.md

python <plugin>/skills/crew-graph/scripts/crew_upgrade.py --root "$FIX"
```
Expected: `upgraded`; `.crew/codemap.v1.bak/core.md` byte-identical to the
original; `schema: 2` in config; `Keep me.` still present; `UPGRADE.md` written;
a second run printing `already current`.

- [ ] **Step 4: Codex review** — ask whether `upgrade.md` can leave a repo in a
  half-upgraded state if it is interrupted between the config write and the
  reconciliation.

- [ ] **Step 5: Commit**

```bash
git add plugin/crew/commands/upgrade.md plugin/crew/commands/onboard.md
git commit -m "feat(crew): add /crew:upgrade and make /crew:onboard graph-first"
```

---

## Task 16: `crew-setup` — schema, blocks, and find-skills detection

**Files:**
- Modify: `plugin/crew/skills/crew-setup/SKILL.md`
- Modify: `plugin/crew/skills/crew-setup/phases.md`
- Modify: `plugin/crew/skills/crew-setup/scripts/detect.sh`
- Modify: `plugin/crew/skills/crew-context/SKILL.md`

**Interfaces:**
- Consumes: `PM_BLOCK`, `GRAPH_BLOCK` (Task 11).
- Produces: new setups that are born at `schema: 2` and therefore never fire
  `upgradeNeeded`.

- [ ] **Step 1: Update the `config.json` template in `SKILL.md`**

The block at `SKILL.md:80-88` gains `"schema": 2` plus the `pm` and `graph`
blocks, matching `crew_upgrade.PM_BLOCK` and `GRAPH_BLOCK` exactly. If the
template and the upgrade defaults disagree, a fresh setup and an upgraded one
behave differently — which is the bug class this whole task exists to avoid.

- [ ] **Step 2: Add global find-skills detection to `detect.sh`**

Append, following the file's existing `say` convention:

```bash
say "find-skills:" "$([ -d "$HOME/.claude/skills/find-skills" ] && echo 'installed globally - see crew-setup, its trigger competes with crew skills' || echo 'not global')"
```

- [ ] **Step 3: Add the report-and-offer step to `SKILL.md` and `phases.md`**

Text must: name what was found, explain that its broad trigger competes with
`crew-setup` and `crew-verification` for ordinary requests, and **offer**
removal. Never delete. It is the user's own global configuration, and a setup
skill that quietly removes from `~/.claude` is worse than the collision it fixes.

- [ ] **Step 4: Note the new SessionStart hook in `crew-context/SKILL.md`**

Its table of lifecycle moments currently implies `SessionStart` prints only the
handoff. Add `pm-brief`, and note it fires on `startup` as well — otherwise the
skill contradicts the shipped behaviour.

- [ ] **Step 5: Verify template and upgrade defaults agree**

```bash
python - <<'PY'
import json, re, sys
sys.path.insert(0, "plugin/crew/skills/crew-graph/scripts")
sys.path.insert(0, "plugin/crew/hooks/scripts")
import crew_upgrade
text = open("plugin/crew/skills/crew-setup/SKILL.md", encoding="utf-8").read()
blob = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S).group(1)
tpl = json.loads(blob)
assert tpl["schema"] == crew_upgrade.crew_state.SCHEMA_CURRENT
assert tpl["pm"] == crew_upgrade.PM_BLOCK, "pm block drifted from the upgrade"
assert tpl["graph"] == crew_upgrade.GRAPH_BLOCK, "graph block drifted"
print("template matches upgrade defaults")
PY
```

- [ ] **Step 6: Codex review, then commit**

```bash
git add plugin/crew/skills/crew-setup/ plugin/crew/skills/crew-context/SKILL.md
git commit -m "feat(crew): new setups start at schema 2 and flag a global find-skills"
```

---

## Task 17: Install scripts — matched pair

**Files:**
- Modify: `scripts/install-prerequisites.sh`
- Modify: `scripts/install-prerequisites.ps1`

**Interfaces:**
- Consumes: nothing.
- Produces: a new menu item (graphify) and a find-skills detection step, with
  identical keys and order in both scripts.

**Read both scripts fully before editing.** They are a matched pair: menu keys,
their order, and their default flags must be identical, or `--select 3,7` means
different things on Windows and Linux.

- [ ] **Step 1: Add the graphify item to the `.sh`**

Follow the existing `PLUGIN_KEYS` / `SKILL_KEYS` convention. Requirements:
detect first (`command -v graphify`) and report "already installed" rather than
reinstalling; install with `uv tool install graphifyy`; register per-repo with
`graphify install --project`, **not** the global install — a global graphify
skill is the same broad-global-skill problem Task 12 fixes. Default **off**:
it installs an external tool and touches the repo.

- [ ] **Step 2: Add the find-skills detection step to the `.sh`**

Detect `~/.claude/skills/find-skills`, report, and offer removal. Never remove
without a yes.

- [ ] **Step 3: Mirror both into the `.ps1`**

Same keys, same order, same default flags, same wording. Use
`$script:PluginCatalog` / `$script:SkillCatalog` as the existing items do.

- [ ] **Step 4: Verify the menus still match**

```bash
python - <<'PY'
import re
sh = open("scripts/install-prerequisites.sh", encoding="utf-8").read()
ps = open("scripts/install-prerequisites.ps1", encoding="utf-8").read()
for name, pat in (("skills", r"SKILL_KEYS=\(([^)]*)\)"),
                  ("plugins", r"PLUGIN_KEYS=\(([^)]*)\)")):
    found = re.search(pat, sh)
    if not found:
        print(f"{name}: no *_KEYS array in the .sh — check by hand"); continue
    keys = found.group(1).split()
    missing = [k for k in keys if k.strip('"\'') not in ps]
    print(f"{name}: {len(keys)} keys, missing from .ps1: {missing}")
PY
```
Expected: `missing: []` for both. Anything else means the pair has diverged.

- [ ] **Step 5: Verify both scripts still parse**

```bash
bash -n scripts/install-prerequisites.sh && echo "sh ok"
pwsh -NoProfile -Command "[void][System.Management.Automation.Language.Parser]::ParseFile('scripts/install-prerequisites.ps1',[ref]\$null,[ref]\$null); 'ps ok'"
```

- [ ] **Step 6: Verify no menu line can wrap**

Every new label goes through `pick_fit` (bash) or `Format-PickerLine`
(PowerShell). Nothing may bypass them: a wrapped line throws off the cursor-up
redraw count and smears the menu over whatever was above it. Clipping is
survivable degradation; wrapping is not.

- [ ] **Step 7: Codex review, then commit**

```bash
git add scripts/install-prerequisites.sh scripts/install-prerequisites.ps1
git commit -m "feat(install): add graphify and detect a globally installed find-skills"
```

---

## Task 18: Documentation tail

**Files:**
- Modify: `.claude-plugin/marketplace.json`
- Modify: `plugin/README.md`
- Modify: `plugin/PLUGINS.md`
- Modify: `README.md`
- Modify: `INSTALLATION.md`
- Modify: `CHANGELOG.md`
- Modify: `plugin/crew/README.md`

**Interfaces:** none. This task is mandated by `CLAUDE.md` and is part of the
work, not a follow-up.

- [ ] **Step 1: Bump crew to 0.3.0 in `marketplace.json`.** Update its
  `description` if the component list no longer matches. Confirm no
  `marketplace.json` has appeared inside `plugin/crew/`.

- [ ] **Step 2: `plugin/PLUGINS.md`** — the full component breakdown: the new
  commands `/crew:pm` and `/crew:upgrade`, the `crew:pm` agent, the `crew-pm`
  and `crew-graph` skills, the `pm-brief` hook, and **what starts running the
  moment the plugin is enabled** — which now includes a `SessionStart` hook that
  fires on `startup`. That last point is the one a reader most needs and is
  easiest to omit.

- [ ] **Step 3: `plugin/README.md`** row (all five columns), then the same row
  inside `README.md`'s `<!-- BEGIN plugin/README.md -->` block, plus any count
  that appears as a number.

- [ ] **Step 4: `README.md`** — menu table (item number, label, default),
  "What each item actually installs", and the switch table if a flag changed.
  Check every piece of prose that names an item **by number**: the numbers shift
  whenever an item is added.

- [ ] **Step 5: `INSTALLATION.md`** — the same menu, in detail.

- [ ] **Step 6: `CHANGELOG.md`** — one entry covering the PM, the graph, the
  upgrade path, the find-skills narrowing, and the PowerShell hook parity fix.

- [ ] **Step 7: `plugin/crew/README.md`** — the plugin's own docs: the
  configuration reference (§11) gains `schema`, `pm`, `graph`; the command and
  agent reference (§23) gains the new entries; the growing-the-crew section
  (§22) gains offboarding; and the find-skills note (§~1126) records the
  narrowing.

- [ ] **Step 8: Verify the four/five registration places agree**

```bash
python - <<'PY'
import json, re
mk = json.load(open(".claude-plugin/marketplace.json", encoding="utf-8"))
entries = mk.get("plugins", mk)
names = [p["name"] for p in entries] if isinstance(entries, list) else []
print("marketplace plugins:", names)
for doc in ("plugin/README.md", "plugin/PLUGINS.md", "README.md"):
    body = open(doc, encoding="utf-8").read()
    print(f"{doc}: crew present={'crew' in body}")
for cmd in ("pm", "upgrade"):
    body = open("plugin/PLUGINS.md", encoding="utf-8").read()
    print(f"PLUGINS.md mentions /crew:{cmd}:", f"crew:{cmd}" in body)
PY
```

- [ ] **Step 9: Codex review of the docs diff** — ask whether any documented
  behaviour is not implemented, which is the failure mode a docs task
  actually has.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "docs: register crew 0.3.0's PM, graph, and upgrade path across all five places"
```

---

## Task 19: Full-branch QA

**Files:** none created. Output goes to `.work/`, which is gitignored.

- [ ] **Step 1: Full test and lint sweep**

```bash
python -m pytest plugin/crew/tests/ -v
pylint $(git ls-files '*.py')
bash -n scripts/install-prerequisites.sh
python -c "import json;json.load(open('plugin/crew/hooks/hooks.json',encoding='utf-8'));json.load(open('.claude-plugin/marketplace.json',encoding='utf-8'));print('json ok')"
```
Expected: all green. A failure here is fixed, not noted.

- [ ] **Step 2: Codex review of this plan's changes**

```bash
git diff origin/feat/crew-plugin...HEAD > .work/review-diff.txt
codex exec --skip-git-repo-check "Review .work/review-diff.txt as a hostile QA engineer.
Output one line per defect: SEVERITY|file:line|what breaks|how to reproduce.
SEVERITY is BLOCK, FIX, or NIT. Check: unintended behavior changes, unhandled
error paths, boundary and empty-collection cases, concurrency, and anything the
change makes reachable that was not before. Output nothing but those lines.
If no defects, output exactly: CLEAN" > .work/review-out.txt 2>&1
```

- [ ] **Step 3: Codex review of the pre-existing branch content**

The merge ships 28 commits, most of them predating this plan. QA covers the
branch, not only the new work.

```bash
git diff main...HEAD -- plugin/ claude-obsidian-setup/ vault-automation/ > .work/branch-diff.txt
codex exec --skip-git-repo-check "Review .work/branch-diff.txt as a hostile QA engineer.
This is a plugin and two bootstrap script sets about to merge to main for the
first time. Prioritise: hooks that run without consent, destructive filesystem
operations, secrets written to disk, and shell quoting bugs on paths with
spaces. Output one line per defect: SEVERITY|file:line|what breaks|how to
reproduce. SEVERITY is BLOCK, FIX, or NIT. If no defects, output exactly:
CLEAN" > .work/branch-out.txt 2>&1
```

- [ ] **Step 4: Report every BLOCK and FIX verbatim before arguing about any**

Fix all BLOCK. For anything in pre-existing branch content, **raise it rather
than merging past it** — that was the condition attached to merging.

- [ ] **Step 5: Hook smoke test on both shells, from a real repo**

Run `pm-brief.sh` and `pm-brief.ps1` against: a v1 fixture, a v2 fixture, and a
plain non-crew directory. Confirm identical output between shells in each case,
exit 0 in all six, and silence for the non-crew directory.

- [ ] **Step 6: Commit any fixes**

```bash
git add -A && git commit -m "fix(crew): address Codex QA findings"
```

---

## Task 20: PR and merge

- [ ] **Step 1: Push**

```bash
git push -u origin feat/crew-plugin
```

- [ ] **Step 2: Open the PR**

Body must state plainly what merging includes — the whole crew plugin,
`claude-obsidian-setup/`, and `vault-automation/`, not just this plan's work —
and summarise the QA results from Task 19 including anything raised and not
fixed.

- [ ] **Step 3: Wait for CI** — pylint and the new pytest job, all three Python
  versions.

- [ ] **Step 4: Confirm before merging**

Merging is outward-facing and hard to reverse. Present the QA outcome and get a
final yes, especially if Task 19 Step 3 raised anything in pre-existing content.

- [ ] **Step 5: Merge, then re-pin the install URLs**

```bash
gh pr merge --squash    # or --merge, per the user's preference
git checkout main && git pull
git rev-parse HEAD
```
Then update **both** one-liner install URLs in `README.md` to that SHA — the
install scripts changed in Tasks 17, so the pinned URLs now point at a stale
version. Commit and push.

---

## Self-Review

**Spec coverage.**

| Spec section | Task |
|---|---|
| A1 `pm-brief` hook, adaptive | 5, 6, 7 |
| A2 `crew-pm` skill, narrow | 8 |
| A3 `crew:pm` agent | 9 |
| A4 `/crew:pm`, offboarding | 9 |
| A5 config `pm` block | 11, 16 |
| B1 narrow vendored description | 12 |
| B2 detect-and-offer | 16, 17 |
| B3 remove on this machine | **not a task — see below** |
| C1 `crew-graph` skill | 13 |
| C2 `/crew:onboard` rewrite | 15 |
| C3 `graph` config block | 11, 16 |
| D1–D7 `/crew:upgrade` | 10, 11, 15 |
| E PowerShell parity | 7 |
| Testing 1–8 | 1–7, 13, 14, 19 |
| Documentation | 18, 20 |
| Delivery | 19, 20 |

**Gap, deliberate:** spec B3 (delete `~/.claude/skills/find-skills` on this
machine) is not a task. It is a one-off action on the user's own global config,
not a repository change — it belongs in the session, after showing the contents,
not in a plan an agent executes unattended. Do it in conversation with the
user's confirmation.

**Placeholder scan.** No TBD or TODO. Two items are explicitly labelled
"verify, do not assume" rather than left vague: the `graph.json` community key
(Task 13 Step 3 resolves it) and the graphify Obsidian behaviour (Task 14
Step 1 proves it). The `handoff-write.ps1` / `notify.ps1` port (Task 7 Step 3)
gives no code because the source of truth is the `.sh` file next to it, and
transcribing it here would create a second version to drift from.

**Type consistency.** Checked across tasks: `crew_state.collect` returns the
keys `pm_brief.render` reads (`isCrew`, `pm`, `health`, `work`, `knowledge`,
`triggers`, `schema`, `tier`, `roles`, `tracker`). `crew_state.TRIGGERS` names
match `pm_brief.FINDINGS` keys, and Task 6 has a test asserting exactly that.
`graph_reconcile.reconcile` returns `body`/`conflicts`/`added`/`touched` and
`crew_upgrade.run` consumes all four. `SCHEMA_CURRENT` is defined once in
`crew_state` and imported by `crew_upgrade`. `PM_BLOCK`/`GRAPH_BLOCK` are
defined once in `crew_upgrade` and asserted equal to the `crew-setup` template
by Task 16 Step 5.
