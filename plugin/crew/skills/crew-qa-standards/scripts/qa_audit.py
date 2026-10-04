"""Audit a repository against crew's harness and QA-review standards.

REPORT-ONLY. Nothing is written. Each audited rule (the `[audited]` ones in
references/harness.md and references/review.md) gets exactly one of:

  PASS     the evidence the rule asks for is there
  GAP      it is not, and the evidence says what is missing
  N/A      the rule does not apply here (no pytest, no ruff config, ...)
  UNKNOWN  it could not be told -- never folded into PASS: a report that
           reads "could not look" as "looked and found nothing" is the
           defect this marketplace keeps paying for

HOW IT LOOKS. A text scan of CI files, not a YAML parse, and of Python test
files, not an import. So a pytest run through a wrapper (`make test`, `tox`,
a script) is invisible to it, and it says UNKNOWN rather than PASS or GAP.
Comment lines (`#`) are skipped. Python and GitHub/Bitbucket/GitLab/Azure CI
are what it reads today; other stacks' rules still need a reader.

ENVIRONMENT AND GATE ITEMS (L-0618). `qa_audit_env.CHECKS` adds the E* and
G* items of references/environments.md -- environment isolation, rollback,
deploy refs, fire-and-forget commands, the D10 `reach` check -- to the same
report, under the same four answers.

`--stamp` records the audited HEAD in `.crew/.qa-audit-at` (gitignored by the
`.crew/*` block) so the `qaAuditStale` session trigger can say when the paths
the audit reads have moved since. It is the only write, and only on request.

`--all-repos ROOT` prints one line per crew checkout found under ROOT (a
directory holding `.crew/`, at most two levels down): the setup phase reached,
the GAP and UNKNOWN counts, and whether D10 is live: an undeclared rule the
Stop gate's own classifier defers (CONFIG.md §19).

Usage: qa_audit.py [--root DIR] [--json] [--strict] [--stamp] [--all-repos ROOT]
Exit: 0 report printed; 1 with --strict and any GAP or UNKNOWN; 2 usage.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import qa_audit_env

PASS, GAP, NA, UNKNOWN = "PASS", "GAP", "N/A", "UNKNOWN"
CLAUDE_MD_LIMIT = 12000
# Below this many test functions a serial run is the right one: measured here, a
# 137-test suite took 0.57s serially and 0.9s under -n 4 (worker start-up).
SMALL_SUITE = 200
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "graphify-out"}
CI_SINGLE_FILES = ("bitbucket-pipelines.yml", ".gitlab-ci.yml", "azure-pipelines.yml")
GIT_PINS = ("commit.gpgsign", "maintenance.auto")

_INSTALL_RE = re.compile(r"\b(pip3?|uv|pipx|poetry|apt-get|brew)\b[^\n]*\b(install|add)\b")
_PARALLEL_RE = re.compile(r"(?:^|\s)(?:-n|--numprocesses)(?:\s|=)")
_ELAPSED_RE = re.compile(r"elapsed\w*\s*<|<\s*[\d.]+[^\n]*elapsed")
_NOT_MARKER_RE = re.compile(r"-m\s+[\"']?not\s+(\w+)")
_NAME_KEY_RE = re.compile(r"^\s*-?\s*name\s*:")
_POSITIVE_MARKER_RE = re.compile(r"-m\s+[\"']?(?!not\b)(\w+)")
_SELECT_RE = re.compile(r"^\s*(?:extend-)?select\s*=", re.M)
_PINNED_RE = re.compile(r"ruff\s*(?:\[[^\]]*\])?\s*(?:==|~=|>=|<=|<|>)")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _files(root):
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            yield os.path.join(base, name)


def ci_files(root):
    """(relative path, text) of every CI definition found."""
    found = []
    workflows = os.path.join(root, ".github", "workflows")
    if os.path.isdir(workflows):
        for name in sorted(os.listdir(workflows)):
            if name.endswith((".yml", ".yaml")):
                found.append(os.path.join(".github", "workflows", name))
    found += [n for n in CI_SINGLE_FILES if os.path.isfile(os.path.join(root, n))]
    return [(rel, _read(os.path.join(root, rel)) or "") for rel in found]


def ci_lines(ci, pattern):
    """(file:line, text) of every non-comment, non-install CI line matching."""
    out = []
    for rel, text in ci:
        for number, line in enumerate(text.split("\n"), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or _INSTALL_RE.search(line) \
                    or _NAME_KEY_RE.match(line):
                continue
            if re.search(pattern, line):
                out.append((f"{rel}:{number}", stripped))
    return out


def _install_lines(ci, word):
    out = []
    for rel, text in ci:
        for number, line in enumerate(text.split("\n"), 1):
            if not line.strip().startswith("#") and _INSTALL_RE.search(line) \
                    and re.search(rf"\b{word}\b", line):
                out.append((f"{rel}:{number}", line.strip()))
    return out


def _python_tests(root):
    return [p for p in _files(root) if p.endswith(".py") and (
        os.path.basename(p).startswith("test_") or p.endswith("_test.py")
        or os.path.basename(p) == "conftest.py" or "fixture" in os.path.basename(p))]


def _pytest_args(line):
    """What follows the `pytest` token: `python -m pytest` must not read as a
    `-m pytest` marker selection."""
    match = re.search(r"\bpytest\b", line)
    return line[match.end():] if match else ""


def _row(rule, title, status, evidence, fix):
    return {"rule": rule, "title": title, "status": status, "evidence": evidence, "fix": fix}


def _suite_size(root, args, tests):
    """Test functions under the paths an invocation names (all tests when it
    names none) -- the same `def test_` count a reader would make."""
    paths = [os.path.join(root, tok.rstrip("/")) for tok in args.split()
             if not tok.startswith("-") and os.path.exists(os.path.join(root, tok.rstrip("/")))]
    chosen = [t for t in tests if not paths or any(
        t == p or t.startswith(p + os.sep) for p in paths)]
    return sum(len(re.findall(r"^\s*(?:async\s+)?def test_", _read(t) or "", re.M))
               for t in chosen)


def check_parallel_tests(root, ci, tests):
    title, fix = "Parallel test runner", "references/harness.md, H2"
    if not tests:
        return _row("H2", title, NA, "no Python test files", fix)
    if not ci:
        return _row("H2", title, UNKNOWN, "tests exist but no CI configuration was found", fix)
    runs = ci_lines(ci, r"\bpytest\b")
    if not runs:
        return _row("H2", title, UNKNOWN, "tests exist but no CI line invokes pytest directly "
                    "(a make/tox/script wrapper is not followed)", fix)
    excluded = {m.group(1) for _, line in runs if _PARALLEL_RE.search(_pytest_args(line))
                for m in [_NOT_MARKER_RE.search(_pytest_args(line))] if m}
    # A serial run of a marker the parallel runs exclude is the H3 split, by design.
    serial, small = [], []
    for where, line in runs:
        args = _pytest_args(line)
        if _PARALLEL_RE.search(args) or any(
                re.search(rf"-m\s+[\"']?{x}\b", args) for x in excluded):
            continue
        size = _suite_size(root, args, tests)
        (small if size < SMALL_SUITE else serial).append(f"{where} ({size} tests)")
    note = (f"; serial and small enough that workers would cost more: {', '.join(small)}"
            if small else "")
    if serial:
        return _row("H2", title, GAP, "pytest without -n on a large suite: "
                    + ", ".join(serial) + note, fix)
    return _row("H2", title, PASS, f"{len(runs)} pytest invocation(s); every large one "
                "is parallel" + note, fix)


def check_wallclock_serial(root, ci, tests):
    title, fix = "Wall-clock tests run serially", "references/harness.md, H3"
    runs = ci_lines(ci, r"\bpytest\b")
    runs = [(w, _pytest_args(line)) for w, line in runs]
    parallel = [(w, line) for w, line in runs if _PARALLEL_RE.search(line)]
    if not parallel:
        return _row("H3", title, NA, "no parallel pytest invocation", fix)
    bounded = []
    for path in tests:
        for number, line in enumerate((_read(path) or "").split("\n"), 1):
            if "assert" in line and _ELAPSED_RE.search(line):
                bounded.append(f"{os.path.relpath(path, root)}:{number}")
    if not bounded:
        return _row("H3", title, NA, "no elapsed-time assertion found in the tests", fix)
    subsets = []
    for where, line in parallel:
        if _POSITIVE_MARKER_RE.search(line) and not _NOT_MARKER_RE.search(line):
            # `-m slow` selects a subset; whether it holds a bounded test cannot
            # be told from text, so it is named in the evidence, never passed.
            subsets.append(where)
            continue
        marker = _NOT_MARKER_RE.search(line)
        serial_run = marker and any(
            re.search(rf"-m\s+[\"']?{marker.group(1)}\b", other) and not _PARALLEL_RE.search(other)
            for _, other in runs)
        if not serial_run:
            return _row("H3", title, GAP, f"{where} runs in parallel with no serial marker split; "
                        f"elapsed-time assertions at {', '.join(bounded[:3])}", fix)
    note = f"; not judged (select a marker subset): {', '.join(subsets)}" if subsets else ""
    return _row("H3", title, PASS, "parallel runs exclude a marker that a serial run selects"
                + note, fix)


def check_fixture_git(root, ci, tests):
    title, fix = "Fixtures isolated from global git config", "references/harness.md, H4"
    commits = [p for p in tests if re.search(r"git[^\n]*[\"']?\bcommit\b", _read(p) or "")]
    if not commits:
        return _row("H4", title, NA, "no test commits to a git repository", fix)
    support = "".join(_read(p) or "" for p in tests if os.path.basename(p) == "conftest.py"
                      or "fixture" in os.path.basename(p))
    missing = [pin for pin in GIT_PINS if pin not in support]
    if missing:
        return _row("H4", title, GAP, f"{len(commits)} test file(s) commit; no conftest/fixture "
                    f"module pins {', '.join(missing)}", fix)
    return _row("H4", title, PASS, "conftest/fixture modules pin " + ", ".join(GIT_PINS), fix)


def check_pylint_jobs(root, ci, tests):
    title, fix = "Deep linter parallel, explicit job count", "references/harness.md, H5"
    runs = ci_lines(ci, r"\bpylint\s")
    runs = [(w, line) for w, line in runs if "--version" not in line]
    if not runs:
        return _row("H5", title, NA, "no CI line runs pylint", fix)
    bad = [w for w, line in runs if not re.search(r"(?:^|\s)(?:-j|--jobs)(?:\s|=)", line)
           or re.search(r"(?:-j|--jobs)[\s=]+[\"']?0\b", line)]
    if bad:
        return _row("H5", title, GAP, "pylint without an explicit -j (or with -j 0): "
                    + ", ".join(bad), fix)
    return _row("H5", title, PASS, f"{len(runs)} pylint invocation(s) with an explicit -j", fix)


def _ruff_config(root):
    for name in ("ruff.toml", ".ruff.toml"):
        text = _read(os.path.join(root, name))
        if text is not None:
            return name, text
    text = _read(os.path.join(root, "pyproject.toml"))
    if text and "[tool.ruff" in text:
        return "pyproject.toml", text[text.index("[tool.ruff"):]
    return None, None


def check_ruff_pinned(root, ci, tests):
    title, fix = "Fast linter: rule set named, version pinned", "references/harness.md, H6"
    name, text = _ruff_config(root)
    if name is None:
        return _row("H6", title, NA, "no ruff configuration", fix)
    problems = []
    if not _SELECT_RE.search(text):
        problems.append(f"{name} has no `select` - the rule set moves with ruff's defaults")
    unpinned = [w for w, line in _install_lines(ci, "ruff") if not _PINNED_RE.search(line)]
    if unpinned:
        problems.append("ruff installed unpinned at " + ", ".join(unpinned))
    if problems:
        return _row("H6", title, GAP, "; ".join(problems), fix)
    return _row("H6", title, PASS, f"{name} names its rule set; CI installs are pinned", fix)


def check_ruff_in_ci(root, ci, tests):
    title, fix = "CI runs the configured fast linter", "references/harness.md, H7"
    name, _ = _ruff_config(root)
    if name is None:
        return _row("H7", title, NA, "no ruff configuration", fix)
    if not ci:
        return _row("H7", title, UNKNOWN, f"{name} exists but no CI configuration was found", fix)
    runs = [w for w, line in ci_lines(ci, r"\bruff\b") if "--version" not in line]
    if not runs:
        return _row("H7", title, GAP, f"{name} configures ruff but no CI line runs it", fix)
    return _row("H7", title, PASS, "ruff runs at " + ", ".join(runs), fix)


def check_claude_md(root, ci, tests):
    title, fix = "Always-loaded instructions stay small", "references/review.md, R9"
    text = _read(os.path.join(root, "CLAUDE.md"))
    if text is None:
        return _row("R9", title, NA, "no CLAUDE.md", fix)
    size = len(text)
    status = GAP if size > CLAUDE_MD_LIMIT else PASS
    return _row("R9", title, status, f"CLAUDE.md is {size} chars (~{size // 4} tokens, loaded "
                f"every session; threshold {CLAUDE_MD_LIMIT})", fix)


def check_steward(root, ci, tests):
    title, fix = "Repo carries a steward skill", "references/review.md, R11"
    if not ci:
        return _row("R11", title, NA, "no CI configuration, so no PR loop to steer", fix)
    if os.path.isfile(os.path.join(root, ".claude", "skills", "steward", "SKILL.md")):
        return _row("R11", title, PASS, ".claude/skills/steward/SKILL.md present", fix)
    return _row("R11", title, GAP, "CI exists but .claude/skills/steward/SKILL.md does not; "
                "start from references/steward-template.md", fix)


CHECKS = (check_parallel_tests, check_wallclock_serial, check_fixture_git, check_pylint_jobs,
          check_ruff_pinned, check_ruff_in_ci, check_claude_md, check_steward) + qa_audit_env.CHECKS
STAMP = os.path.join(".crew", ".qa-audit-at")


def audit(root):
    root = os.path.abspath(root)
    ci, tests = ci_files(root), _python_tests(root)
    rows = []
    for check in CHECKS:
        try:
            rows.append(check(root, ci, tests))
        except Exception as exc:  # pylint: disable=broad-except
            rows.append(_row(check.__name__, check.__name__, UNKNOWN,
                             f"the check itself failed: {type(exc).__name__}: {exc}", ""))
    return rows


def render(rows):
    counts = {s: sum(r["status"] == s for r in rows) for s in (GAP, UNKNOWN, PASS, NA)}
    lines = [f"qa-audit: {counts[GAP]} GAP, {counts[UNKNOWN]} UNKNOWN, {counts[PASS]} PASS, "
             f"{counts[NA]} N/A", "", "| Rule | Status | Check | Evidence | Fix |",
             "|---|---|---|---|---|"]
    order = {GAP: 0, UNKNOWN: 1, PASS: 2, NA: 3}
    for r in sorted(rows, key=lambda r: order.get(r["status"], 9)):
        evidence = r["evidence"].replace("|", "\\|")
        lines.append(f"| {r['rule']} | {r['status']} | {r['title']} | {evidence} | {r['fix']} |")
    return "\n".join(lines) + "\n"


def stamp(root):
    """Record HEAD as the last audited commit. Returns the sha, or None when
    there is no `.crew/` or git cannot name HEAD -- never a guessed value."""
    if not os.path.isdir(os.path.join(root, ".crew")):
        return None
    try:
        sha = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=30, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not re.fullmatch(r"[0-9a-f]{7,64}", sha):
        return None
    text = sha + "\n"
    tmp = os.path.join(root, STAMP + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, os.path.join(root, STAMP))
    return sha


def _phase_reached(root):
    """The last `done` phase in `.crew/STATUS.md`, `none`, or `unknown`."""
    text = _read(os.path.join(root, ".crew", "STATUS.md"))
    if text is None:
        return "unknown"
    done = re.findall(r"^\|\s*(\d+)[^|\n]*\|[^\n]*\bdone\b", text, re.M | re.I)
    return f"phase {max(int(n) for n in done)}" if done else "none"


def crew_checkouts(base):
    """Directories at most two levels under base (base included) holding `.crew/`."""
    found, stack = [], [(base, 0)]
    while stack:
        here, level = stack.pop()
        if os.path.isdir(os.path.join(here, ".crew")):
            found.append(here)
        if level < 2:
            try:
                names = sorted(os.listdir(here), reverse=True)
            except OSError:
                continue
            stack += [(os.path.join(here, n), level + 1) for n in names
                      if n not in SKIP_DIRS and not n.startswith(".")
                      and os.path.isdir(os.path.join(here, n))]
    return sorted(found)


def fleet(base):
    lines = ["| Repo | Setup | GAP | UNKNOWN | D10 (rules skipped on Stop) |", "|---|---|---|---|---|"]
    for repo in crew_checkouts(base):
        rows = audit(repo)
        d10 = next((r for r in rows if r["rule"] == "G1"), None)
        d10_text = {GAP: "YES" if d10 and "SKIPPED" in d10["evidence"] else "no",
                    PASS: "no", NA: "no map"}.get(d10["status"] if d10 else UNKNOWN, "unknown")
        lines.append(f"| {os.path.relpath(repo, base)} | {_phase_reached(repo)} | "
                     f"{sum(r['status'] == GAP for r in rows)} | "
                     f"{sum(r['status'] == UNKNOWN for r in rows)} | {d10_text} |")
    if len(lines) == 2:
        lines.append("| (no crew checkout found) | | | | |")
    return "\n".join(lines) + "\n"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 when any rule is GAP or UNKNOWN")
    parser.add_argument("--stamp", action="store_true",
                        help="record HEAD in .crew/.qa-audit-at after reporting")
    parser.add_argument("--all-repos", metavar="ROOT",
                        help="one line per crew checkout under ROOT, instead of one report")
    args = parser.parse_args(argv)
    if args.all_repos:
        if not os.path.isdir(args.all_repos):
            parser.error(f"--all-repos {args.all_repos!r} is not a directory")
        sys.stdout.write(fleet(os.path.abspath(args.all_repos)))
        return 0
    if not os.path.isdir(args.root):
        parser.error(f"--root {args.root!r} is not a directory")
    rows = audit(args.root)
    sys.stdout.write(json.dumps(rows, indent=2) + "\n" if args.json else render(rows))
    if args.stamp:
        sha = stamp(os.path.abspath(args.root))
        sys.stderr.write(f"qa-audit: stamped {sha[:12]} in {STAMP}\n" if sha else
                         "qa-audit: NOT stamped (no .crew/ here, or git could not name HEAD)\n")
    if args.strict and any(r["status"] in (GAP, UNKNOWN) for r in rows):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
