#!/usr/bin/env python3
"""Sabotage suite for scripts/check-tooling-pr.py -- tooling PRs land alone.

Every case builds a throwaway git repository in a temp directory, with a fake
`refs/remotes/origin/main`, and runs the checker's `check(root)` against it.
Nothing touches this repository's own files or refs.

The must-block cases are what the rule exists for: a change to crew's
review/gate harness that also carries feature work. The must-allow cases keep
it honest: the harness with its own tests and docs, a branch that touches no
harness path, and a lane that merged main (whose feature files are main's,
not the lane's). A missing `origin/main` must say TOOL MISSING and exit 77 --
"nothing to compare against" is not "nothing changed" (T-0087).

Run: python3 scripts/_test/tooling-pr.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check-tooling-pr.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_tooling_pr", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: str, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL).stdout.strip()


def write(root: str, rel: str, text: str = "x\n") -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def commit(root: str, paths: list[str], message: str) -> None:
    for rel in paths:
        write(root, rel, f"{message}\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def repo(tmp: str, origin: bool = True) -> str:
    """A repo on `main` with one seed commit, origin/main at it, and a lane
    branch checked out."""
    root = os.path.join(tmp, "repo")
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    commit(root, ["README.md"], "seed")
    if origin:
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-qb", "lane")
    return root


HARNESS_FILE = "plugin/crew/hooks/scripts/review_ledger.py"


def case_harness_feature(tmp: str) -> str:
    root = repo(tmp)
    commit(root, [HARNESS_FILE, "plugin/obsidian-vault/x.py"], "harness plus feature")
    return root


def case_harness_crew_feature(tmp: str) -> str:
    root = repo(tmp)
    commit(root, ["plugin/crew/hooks/scripts/review_run.py",
                  "plugin/crew/hooks/scripts/crew_tracker.py"], "harness plus crew feature")
    return root


def case_harness_uncommitted_feature(tmp: str) -> str:
    root = repo(tmp)
    commit(root, [HARNESS_FILE], "harness")
    write(root, "skills/x/SKILL.md")
    return root


def case_harness_tests_docs(tmp: str) -> str:
    root = repo(tmp)
    commit(root, ["plugin/crew/hooks/scripts/review_verdict.py", "plugin/crew/tests/test_x.py",
                  "plugin/crew/README.md", "CHANGELOG.md", "plugin/PLUGINS.md",
                  ".crew/codemap/crew.md"], "harness with tests and docs")
    return root


def case_harness_budgets(tmp: str) -> str:
    """BUDGETS.md's line-count claim moves with every crew .md edit (owner,
    2026-09-28), so a harness change that edits a command file carries it."""
    root = repo(tmp)
    commit(root, ["plugin/crew/hooks/scripts/review_verdict.py", "plugin/crew/commands/review.md",
                  "plugin/crew/BUDGETS.md"], "harness with its budget re-measure")
    return root


def case_feature_only(tmp: str) -> str:
    root = repo(tmp)
    commit(root, ["plugin/crew/hooks/scripts/crew_tracker.py"], "feature only")
    return root


def case_merged_main(tmp: str) -> str:
    """The lane changes the harness and merges main, which had gained a
    feature file; main then moves again. Neither feature file is the lane's."""
    root = repo(tmp)
    commit(root, ["plugin/crew/hooks/scripts/review_run.py"], "lane harness change")
    git(root, "checkout", "-q", "main")
    commit(root, ["plugin/gizmoduck/y.py"], "main feature")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "lane")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "refs/remotes/origin/main")
    git(root, "checkout", "-q", "main")
    commit(root, ["plugin/gizmoduck/z.py"], "main moves again")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "lane")
    return root


def _harness_with(tmp: str, other: str, message: str = "harness plus other") -> str:
    root = repo(tmp)
    commit(root, ["plugin/crew/hooks/scripts/review_verdict.py", other], message)
    return root


def case_harness_autopilot_feature(tmp: str) -> str:
    """A new subcommand in a seam consumer, undeclared: file level cannot tell
    it from a seam edit, so it blocks."""
    return _harness_with(tmp, "plugin/crew/hooks/scripts/crew_autopilot.py")


def case_harness_status_undeclared(tmp: str) -> str:
    return _harness_with(tmp, "plugin/crew/hooks/scripts/crew_status.py")


def case_harness_implement_prompt(tmp: str) -> str:
    return _harness_with(tmp, "plugin/crew/commands/implement.md")


def case_harness_agent_prompt(tmp: str) -> str:
    return _harness_with(tmp, "plugin/crew/agents/developer.md")


def case_harness_other_eval(tmp: str) -> str:
    return _harness_with(tmp, "plugin/crew/evals/pm-does-not-write-code/prompt.md")


def case_declared_non_seam(tmp: str) -> str:
    """A trailer cannot admit a file outside SEAM."""
    return _harness_with(tmp, "plugin/crew/hooks/scripts/crew_tracker.py",
                         "harness\n\nTooling-seam: plugin/crew/hooks/scripts/crew_tracker.py")


def case_harness_declared_seam(tmp: str) -> str:
    root = repo(tmp)
    commit(root, [HARNESS_FILE, "plugin/crew/hooks/scripts/crew_status.py",
                  "plugin/crew/commands/status.md"],
           "harness with its status consumer\n\n"
           "Tooling-seam: plugin/crew/hooks/scripts/crew_status.py\n"
           "Tooling-seam: plugin/crew/commands/status.md")
    write(root, "plugin/crew/hooks/scripts/crew_status.py", "edited after the declaration\n")
    return root


def case_harness_review_prompts(tmp: str) -> str:
    root = repo(tmp)
    commit(root, ["plugin/crew/commands/review.md", "plugin/crew/agents/reviewer.md",
                  "plugin/crew/evals/qa-reviewer-stays-read-only/prompt.md"],
           "the reviewer's prompts are harness")
    return root


def case_worktree_rename(tmp: str) -> str:
    """` R` from `git add -N`: the old path follows as its own field."""
    root = os.path.join(tmp, "repo")
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    commit(root, ["README.md", "a/feature.py"], "seed with a feature file long enough")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-qb", "lane")
    commit(root, [HARNESS_FILE], "harness")
    os.makedirs(os.path.join(root, "b"))
    os.replace(os.path.join(root, "a", "feature.py"), os.path.join(root, "b", "feature.py"))
    git(root, "add", "-N", "b/feature.py")
    return root


def case_no_origin(tmp: str) -> str:
    root = repo(tmp, origin=False)
    commit(root, [HARNESS_FILE], "harness")
    return root


# (label, builder, expected exit, text the output must contain)
CASES = [
    ("must-block harness+feature", case_harness_feature, 1, "plugin/obsidian-vault/x.py"),
    ("must-block harness+crew-feature", case_harness_crew_feature, 1,
     "plugin/crew/hooks/scripts/crew_tracker.py"),
    ("must-block harness+uncommitted-feature", case_harness_uncommitted_feature, 1,
     "skills/x/SKILL.md"),
    ("must-allow harness+tests+docs", case_harness_tests_docs, 0, "OK"),
    ("must-allow harness+budgets", case_harness_budgets, 0, "OK"),
    ("must-allow feature-only", case_feature_only, 0, "no harness path changed"),
    ("must-allow merged-main", case_merged_main, 0, "OK"),
    ("must-report no-origin", case_no_origin, 77, "TOOL MISSING"),
    ("must-block harness+autopilot-feature", case_harness_autopilot_feature, 1,
     "  plugin/crew/hooks/scripts/crew_autopilot.py"),
    ("must-block harness+status-undeclared", case_harness_status_undeclared, 1,
     "  plugin/crew/hooks/scripts/crew_status.py"),
    ("must-block harness+implement-prompt", case_harness_implement_prompt, 1,
     "  plugin/crew/commands/implement.md"),
    ("must-block harness+agent-prompt", case_harness_agent_prompt, 1,
     "  plugin/crew/agents/developer.md"),
    ("must-block harness+other-eval", case_harness_other_eval, 1,
     "  plugin/crew/evals/pm-does-not-write-code/prompt.md"),
    ("must-block declared-non-seam", case_declared_non_seam, 1,
     "  plugin/crew/hooks/scripts/crew_tracker.py"),
    ("must-block worktree-rename", case_worktree_rename, 1, "\n  a/feature.py"),
    ("must-allow harness+declared-seam", case_harness_declared_seam, 0, "OK"),
    ("must-allow harness+review-prompts", case_harness_review_prompts, 0, "OK"),
]


def main() -> int:
    checker = load_checker()
    passed = failed = 0
    for label, builder, want_code, want_text in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = builder(tmp)
            code, lines = checker.check(root)
        text = "\n".join(lines)
        if code == want_code and want_text in text:
            passed += 1
            print(f"  ok   {label}")
        else:
            failed += 1
            print(f"  FAIL {label}")
            print(f"       expected exit {want_code} with {want_text!r}, got {code}:")
            for line in lines:
                print(f"       | {line}")
    print(f"\ntooling-pr: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
