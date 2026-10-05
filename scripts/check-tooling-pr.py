#!/usr/bin/env python3
"""Tooling PRs land alone: a change to crew's review/gate harness carries no
feature work.

    python3 scripts/check-tooling-pr.py [--root <repo>]

THE RULE (owner, 2026-09-28, T-0087: tooling PRs "carry no feature work"). The
review and gate harness decides whether every other change is accepted. When a
harness change rides in a PR with a feature, a harness bug is found only after
it has already judged that feature, and a review round lost to the tool is
also a round lost to the feature. So when a branch changes any `HARNESS` path,
every other path it changes must be in `ALONGSIDE`: tests, docs (`BUDGETS.md`'s
line count moves with every crew doc edit), version files, code map, graph and
ticket records. No production code and no prompt is in `ALONGSIDE`.

SEAM CONSUMERS. `SEAM` names the few production files that read a harness
format (`crew_status.py` renders the ledger, `crew_autopilot.py` routes on it,
`crew_resume.py` fingerprints it, and the two commands that describe them). A
harness change may have to move them, but a file-level check cannot tell that
edit from feature work in the same file. So a `SEAM` path rides along only
when a lane commit declares it with a `Tooling-seam: <path>` trailer, which
puts the claim in the PR for the reviewer to hold it to. An undeclared one
blocks like any feature file, and a trailer naming a path outside `SEAM`
admits nothing.

WHAT COUNTS AS CHANGED. The lane's own changes: `git diff --name-only
origin/main...HEAD` (from the merge base, so the files a merge of main brought
in are main's, not the lane's, while an edit made inside a merge's conflict
resolution IS seen), both sides of a rename, plus every path `git status`
reports (staged, unstaged, untracked; both sides of a rename in either
column), so an uncommitted feature file counts. Declarations are read from
the trailers of `origin/main..HEAD`'s commits.

Exit 0: no harness path changed, or only tooling changed. Exit 1: a harness
change carries feature work, with one line per path to land separately. Exit
77: `origin/main` is not a ref here, so the check did not run. That is a
missing ref, never a pass: the verify gate records 77 as SKIP (NOT VERIFIED).

Matching is `crew_ticket.path_matches`, the same segment-aware globs as a
spec's Touch list. `.crew/verify.json`'s harness rule lists `HARNESS`, `SEAM`
and the suites it runs as its paths, and
`test_verify_rule_paths_cover_the_harness_its_seams_and_suites` keeps them so.
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
    # T-0100: the merged-main drop rule the review bundle and the completion
    # audit share; a change here moves both, so it is harness like them.
    "plugin/crew/hooks/scripts/merged_main.py",
    "plugin/crew/tests/sabotage*.py",
    "plugin/crew/tests/review_fixtures.py",
    "plugin/crew/tests/golden_build.py",
    "plugin/crew/tests/golden/**",
    "plugin/crew/commands/review.md",
    "plugin/crew/agents/reviewer.md",
    "plugin/crew/evals/qa-reviewer-stays-read-only/**",
    "scripts/check-tooling-pr.py",
)

SEAM = (
    "plugin/crew/hooks/scripts/crew_status.py",
    "plugin/crew/hooks/scripts/crew_autopilot.py",
    "plugin/crew/hooks/scripts/crew_resume.py",
    "plugin/crew/commands/status.md",
    "plugin/crew/commands/autopilot.md",
)

TRAILER = "Tooling-seam"

ALONGSIDE = (
    "plugin/crew/tests/**",
    "plugin/crew/README.md",
    "plugin/crew/CONFIG.md",
    "plugin/crew/BUDGETS.md",
    "plugin/crew/docs/**",
    "plugin/crew/.claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".claude/rules/**",
    "plugin/PLUGINS.md",
    "CHANGELOG.md",
    # L-1518: root README.md's "What's new" block is generated from CHANGELOG.md.
    "README.md",
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
        # A rename or copy in EITHER column (` R` is a worktree rename, from
        # `git add -N`) is followed by its source path as a field of its own.
        if set(entry[:2]) & {"R", "C"} and i < len(entries):
            paths.add(entries[i])
            i += 1
    return sorted(paths)


def declared_seams(root: str) -> set[str]:
    """Paths the lane's own commits declare with a `Tooling-seam:` trailer."""
    log = _git(root, "log", f"--format=%(trailers:key={TRAILER},valueonly)",
               "origin/main..HEAD")
    if log.returncode != 0:
        raise RuntimeError(f"git log origin/main..HEAD failed: {log.stderr.strip()}")
    return {line.strip() for line in log.stdout.splitlines() if line.strip()}


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
        declared = declared_seams(root)
    except RuntimeError as exc:
        return EXIT_MISSING, [f"TOOL MISSING: {exc}; the tooling-alone check DID NOT RUN."]
    return judge(paths, declared)


def judge(paths: list[str], declared: set[str]) -> tuple[int, list[str]]:
    """(exit code, output lines) for a lane's changed paths and its declared seams."""
    harness = [p for p in paths if _matches(p, HARNESS)]
    if not harness:
        return 0, ["tooling-pr: no harness path changed"]
    seams = [p for p in paths if p in declared and _matches(p, SEAM)]
    outside = [p for p in paths if not _matches(p, HARNESS + ALONGSIDE) and p not in seams]
    if outside:
        undeclared = [p for p in outside if _matches(p, SEAM)]
        hint = ([f"  (a seam consumer rides along only when a lane commit declares it: "
                 f"`{TRAILER}: <path>`; undeclared: {', '.join(undeclared)})"]
                if undeclared else [])
        return 1, (["tooling-pr: FAIL - a tooling change carries feature work; "
                    "land these separately:"] + [f"  {p}" for p in outside] + hint)
    tail = f", {len(seams)} declared seam consumer(s)" if seams else ""
    return 0, [f"tooling-pr: OK - {len(harness)} harness path(s){tail}, "
               "nothing outside tooling"]


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
