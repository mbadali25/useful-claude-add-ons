#!/usr/bin/env python3
"""Tooling PRs land alone: a change to crew's review/gate harness carries no
feature work.

    python3 scripts/check-tooling-pr.py [--root <repo>]

THE RULE (owner, 2026-09-28, T-0087: tooling PRs "carry no feature work"). The
review and gate harness decides whether every other change is accepted. When a
harness change rides in a PR with a feature, a harness bug is found only after
it has already judged that feature, and a review round lost to the tool is
also a round lost to the feature. So when a branch changes any `HARNESS` path,
every other path it changes must be in `ALONGSIDE`: the harness's tests, docs
(`BUDGETS.md`'s line count moves with every crew doc edit), version files, code
map, graph and ticket records.

WHAT COUNTS AS CHANGED. The lane's own changes: `git diff --name-only
origin/main...HEAD` (from the merge base, so the files a merge of main brought
in are main's, not the lane's, while an edit made inside a merge's conflict
resolution IS seen), both sides of a rename, plus every path `git status`
reports (staged, unstaged, untracked), so an uncommitted feature file counts.

Exit 0: no harness path changed, or only tooling changed. Exit 1: a harness
change carries feature work, with one line per path to land separately. Exit
77: `origin/main` is not a ref here, so the check did not run. That is a
missing ref, never a pass: the verify gate records 77 as SKIP (NOT VERIFIED).

Matching is `crew_ticket.path_matches`, the same segment-aware globs as a
spec's Touch list. `.crew/verify.json`'s harness rule lists exactly `HARNESS`
as its paths, and `test_verify_rule_paths_are_the_checkers_harness_globs`
keeps the two lists equal.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugin", "crew", "hooks", "scripts"))
import crew_ticket  # noqa: E402  pylint: disable=wrong-import-position

EXIT_MISSING = 77

HARNESS = (
    "plugin/crew/hooks/scripts/review_*.py",
    "plugin/crew/hooks/scripts/verify-gate.sh",
    "plugin/crew/hooks/scripts/verify-gate.ps1",
    "plugin/crew/hooks/scripts/verify_record.py",
    "plugin/crew/hooks/scripts/verify_fingerprint.py",
    "plugin/crew/hooks/scripts/verify_price.py",
    "plugin/crew/hooks/scripts/crew_ticket.py",
    "plugin/crew/hooks/scripts/approval_hook.py",
    "plugin/crew/hooks/scripts/approval-hook.sh",
    "plugin/crew/hooks/scripts/approval-hook.ps1",
    "plugin/crew/hooks/scripts/scope_guard.py",
    "plugin/crew/hooks/scripts/scope-guard.sh",
    "plugin/crew/hooks/scripts/scope-guard.ps1",
    "plugin/crew/hooks/scripts/scope_base.py",
    "plugin/crew/hooks/scripts/completion_audit.py",
    "plugin/crew/hooks/scripts/completion-audit.sh",
    "plugin/crew/hooks/scripts/completion-audit.ps1",
    "plugin/crew/tests/sabotage*.py",
    "plugin/crew/tests/review_fixtures.py",
    "plugin/crew/tests/golden_build.py",
    "plugin/crew/tests/golden/**",
    "scripts/check-tooling-pr.py",
)

ALONGSIDE = (
    "plugin/crew/tests/**",
    "plugin/crew/README.md",
    "plugin/crew/CONFIG.md",
    "plugin/crew/BUDGETS.md",
    "plugin/crew/commands/**",
    "plugin/crew/agents/**",
    "plugin/crew/docs/**",
    "plugin/crew/evals/**",
    "plugin/crew/hooks/scripts/crew_status.py",
    "plugin/crew/hooks/scripts/crew_autopilot.py",
    "plugin/crew/hooks/scripts/crew_resume.py",
    "plugin/crew/.claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".claude/rules/**",
    "plugin/PLUGINS.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "TODO.md",
    "docs/**",
    ".crew/codemap/**",
    ".crew/verify.json",
    "graphify-out/**",
    "scripts/_test/tooling-pr.py",
    ".work/**",
)


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def changed_paths(root: str) -> list[str]:
    """The lane's own changed paths: merge base to HEAD, plus the working tree."""
    paths: set[str] = set()
    diff = _git(root, "diff", "--name-status", "-z", "origin/main...HEAD")
    if diff.returncode != 0:
        raise RuntimeError(f"git diff origin/main...HEAD failed: {diff.stderr.strip()}")
    fields = [f for f in diff.stdout.split("\0") if f]
    i = 0
    while i < len(fields):
        status = fields[i]
        width = 2 if status[:1] in ("R", "C") else 1
        paths.update(fields[i + 1:i + 1 + width])
        i += 1 + width
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status.returncode != 0:
        raise RuntimeError(f"git status failed: {status.stderr.strip()}")
    entries = status.stdout.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.add(entry[3:])
        if entry[0] in ("R", "C"):
            paths.add(entries[i])
            i += 1
    return sorted(paths)


def _matches(path: str, globs: tuple[str, ...]) -> bool:
    return any(crew_ticket.path_matches(path, glob) for glob in globs)


def check(root: str) -> tuple[int, list[str]]:
    """(exit code, output lines) for the branch checked out at `root`."""
    if _git(root, "rev-parse", "--verify", "-q", "origin/main").returncode != 0:
        return EXIT_MISSING, ["TOOL MISSING: origin/main is not a ref here, so the "
                              "tooling-alone check DID NOT RUN. This is a missing ref, "
                              "not a pass."]
    try:
        paths = changed_paths(root)
    except RuntimeError as exc:
        return EXIT_MISSING, [f"TOOL MISSING: {exc}; the tooling-alone check DID NOT RUN."]
    harness = [p for p in paths if _matches(p, HARNESS)]
    if not harness:
        return 0, ["tooling-pr: no harness path changed"]
    outside = [p for p in paths if not _matches(p, HARNESS + ALONGSIDE)]
    if outside:
        return 1, (["tooling-pr: FAIL - a tooling change carries feature work; "
                    "land these separately:"] + [f"  {p}" for p in outside])
    return 0, [f"tooling-pr: OK - {len(harness)} harness path(s), nothing outside tooling"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    code, lines = check(os.path.abspath(args.root))
    stream = sys.stderr if code == EXIT_MISSING else sys.stdout
    for line in lines:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
