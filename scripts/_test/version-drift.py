#!/usr/bin/env python3
"""Sabotage suite for check-marketplace.py's version-drift check.

Every case builds a throwaway git repo in a temp directory and points the
checker's ROOT at it, then runs the real ``check_versions``. Nothing touches
this repository's own files.

The check answers one question - "when was this version set?" - and the answer
is a commit, which is then diffed against HEAD. Get the commit wrong in the
*newer* direction and the diff window shrinks; shrink it to HEAD itself and the
commit diffs against its own tree, reports nothing, and the check passes while
a plugin ships changed under an unbumped version. That is not a wrong answer,
it is a missing one wearing the label of a check that ran - which is this
repo's recurring bug, and it shipped as crew 0.19.29.

Two orderings of the manifest's history are walked because each is blind to a
shape the other catches. The two mutation cases below are what prove that: a
suite that only broke one arm would pass with the other arm deleted.

Run: python3 scripts/_test/version-drift.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check-marketplace.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_marketplace", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


# ------------------------------------------------------------------ fixtures

# Commit dates are pinned, never left to the clock. `git log` orders by commit
# date, and a fixture whose commits all land in the same second is ordered by
# git's tie-breaking instead - which made the merge case below report the drift
# on roughly one run in five and miss it on the other four. A regression case
# that goes red by coincidence is the same defect as the bug it is meant to
# catch, so every commit here is given an explicit second.
EPOCH = 1700000000
STEP = 100


def sh(cwd: str, *args: str, when: int | None = None) -> str:
    env = None
    if when is not None:
        env = dict(os.environ)
        stamp = f"@{when} +0000"
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          check=False, env=env)
    if done.returncode != 0:
        raise RuntimeError(f"{args} -> {done.returncode}\n{done.stderr}")
    return done.stdout.strip()


def manifest(tmp: str, crew_version: str, other_version: str = "1.0.0") -> None:
    path = os.path.join(tmp, ".claude-plugin", "marketplace.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "plugins": [
            {"name": "crew", "source": "./plugin/crew", "version": crew_version,
             "description": "d"},
            {"name": "other", "source": "./plugin/other", "version": other_version,
             "description": "d"},
        ]
    }
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2)


def plugin_file(tmp: str, name: str, body: str) -> None:
    path = os.path.join(tmp, "plugin", name, "thing.py")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


def commit(tmp: str, message: str, at: int) -> str:
    """Commit at an explicit second since the epoch. `at` is not optional."""
    sh(tmp, "git", "add", "-A")
    sh(tmp, "git", "-c", "user.email=t@t", "-c", "user.name=t",
       "commit", "-q", "--no-gpg-sign", "-m", message, when=EPOCH + at)
    return sh(tmp, "git", "rev-parse", "HEAD")


def merge(tmp: str, branch: str, message: str, at: int, *extra: str) -> None:
    sh(tmp, "git", "-c", "user.email=t@t", "-c", "user.name=t",
       "merge", "-q", "--no-ff", "--no-gpg-sign", *extra, "-m", message, branch,
       when=EPOCH + at)


def init(tmp: str) -> None:
    sh(tmp, "git", "init", "-q", "-b", "main")
    manifest(tmp, "1.0.0")
    plugin_file(tmp, "crew", "v0\n")
    plugin_file(tmp, "other", "v0\n")
    commit(tmp, "initial", 0)


def run_check(tmp: str) -> list[str]:
    """Run the real check_versions with the checker's ROOT pointed at a fixture."""
    old_root, old_manifest = CHECKER.ROOT, CHECKER.MARKETPLACE
    CHECKER.ROOT = tmp
    CHECKER.MARKETPLACE = os.path.join(tmp, ".claude-plugin", "marketplace.json")
    problems: list[str] = []
    try:
        CHECKER.check_versions(CHECKER.load_entries(), problems.append)
    finally:
        CHECKER.ROOT, CHECKER.MARKETPLACE = old_root, old_manifest
    return problems


# ----------------------------------------------------------------- scenarios

def s_linear_stale(tmp: str) -> None:
    """Bump, THEN change the plugin. The whole reason the check exists."""
    init(tmp)
    manifest(tmp, "1.0.1")
    commit(tmp, "bump crew to 1.0.1", 100)
    plugin_file(tmp, "crew", "v1 changed after the bump\n")
    commit(tmp, "change crew after the bump", 200)


def s_linear_clean(tmp: str) -> None:
    """Change the plugin, THEN bump. The correct order, and it must stay quiet."""
    init(tmp)
    plugin_file(tmp, "crew", "v1\n")
    commit(tmp, "change crew", 100)
    manifest(tmp, "1.0.1")
    commit(tmp, "bump crew to 1.0.1 last", 200)


def s_merge_interleaved(tmp: str) -> None:
    """A branch bumps and changes crew; main's own manifest commit is dated between.

    Walking by date, the walk meets main's still-1.0.0 manifest before it
    reaches the branch's bump, stops there, and the window collapses.
    """
    init(tmp)
    sh(tmp, "git", "checkout", "-q", "-b", "feature")
    manifest(tmp, "1.0.1")
    plugin_file(tmp, "crew", "v1 from the branch\n")
    commit(tmp, "crew 1.0.1 on the branch", 100)

    sh(tmp, "git", "checkout", "-q", "main")
    manifest(tmp, "1.0.0", other_version="1.0.9")
    commit(tmp, "bump OTHER on main - crew still 1.0.0 here", 200)

    merge(tmp, "feature", "merge feature", 300, "-X", "theirs")

    plugin_file(tmp, "crew", "v2 AFTER the merge, no manifest touch\n")
    commit(tmp, "change crew after the merge", 400)


def s_merge_at_head(tmp: str) -> None:
    """The merge commit is HEAD and is where 1.0.1 first reaches main. MUST PASS.

    This one reads like a hole and is not. A branch bumped to 1.0.1 while main
    changed plugin/crew; the merge unites them. 1.0.1 has never existed on main
    before this commit, so nobody can be holding a *different* 1.0.1 - there is
    no stale install to warn about, and the next release of 1.0.1 is this tree.
    Asserted here precisely so nobody "fixes" it into a failure.
    """
    init(tmp)
    sh(tmp, "git", "checkout", "-q", "-b", "feature")
    manifest(tmp, "1.0.1")
    commit(tmp, "crew 1.0.1 on the branch, manifest only", 100)

    sh(tmp, "git", "checkout", "-q", "main")
    plugin_file(tmp, "crew", "v1 on main after the branch bumped\n")
    manifest(tmp, "1.0.0", other_version="1.0.9")
    commit(tmp, "change crew on main + bump OTHER", 200)

    merge(tmp, "feature", "merge feature", 300, "-X", "theirs")


def s_published_then_changed_then_merge(tmp: str) -> None:
    """The shape that is unambiguous user harm - and the one 0.19.29 hit.

    1.0.1 lands on main, so it is installable and somebody has it. Then
    plugin/crew changes with no bump: every installed copy is now stale. Then an
    unrelated branch - forked BEFORE the bump, so its manifest still says
    1.0.0 - is merged for its own reasons, and the merge touches the manifest.
    Walking by date, that merge resets the answer to HEAD and the staleness
    disappears.

    The branch's commit is dated AFTER the bump (t=400 against t=100) even
    though it forked before it, which is what a side branch worked on over a
    couple of days looks like. That date is the whole shape: it is what puts a
    still-1.0.0 manifest above the bump in the date-ordered log, so the walk
    stops at the merge. Left to the clock the ordering is a coin flip.
    """
    init(tmp)
    sh(tmp, "git", "checkout", "-q", "-b", "unrelated")
    plugin_file(tmp, "other", "other work\n")
    manifest(tmp, "1.0.0", other_version="1.0.9")
    commit(tmp, "unrelated branch bumps OTHER; crew still 1.0.0 here", 400)

    sh(tmp, "git", "checkout", "-q", "main")
    manifest(tmp, "1.0.1")
    commit(tmp, "crew 1.0.1 - PUBLISHED, installable from here", 100)

    plugin_file(tmp, "crew", "v1 changed AFTER 1.0.1 was installable\n")
    commit(tmp, "change crew with no bump - every installed 1.0.1 is now stale", 200)

    merge(tmp, "unrelated", "merge unrelated branch", 500, "-X", "ours")


def s_pr_merge_ref(tmp: str) -> None:
    """What CI actually judges on a `pull_request` event.

    actions/checkout@v4 checks out refs/pull/N/merge, whose FIRST parent is the
    base branch and whose second is the PR head. The PR bumps to 1.0.1 and then
    changes plugin/crew - the ordinary mistake. A first-parent walk follows main
    straight past the PR's own bump and goes blind here, which is why
    --first-parent is not the fix on its own.
    """
    init(tmp)
    sh(tmp, "git", "checkout", "-q", "-b", "pr")
    manifest(tmp, "1.0.1")
    commit(tmp, "bump crew to 1.0.1 on the PR", 100)
    plugin_file(tmp, "crew", "v1 changed after the bump, on the PR\n")
    commit(tmp, "change crew after the bump - THE MISTAKE", 200)

    sh(tmp, "git", "checkout", "-q", "main")
    merge(tmp, "pr", "Merge pr into main", 300)


CASES = [
    ("linear: bump then change", s_linear_stale, 1),
    ("linear: change then bump", s_linear_clean, 0),
    ("merge: main's manifest commit is dated between bump and merge",
     s_merge_interleaved, 1),
    ("merge: the merge is HEAD and is where the version first lands",
     s_merge_at_head, 0),
    ("merge: published, changed with no bump, then an unrelated merge",
     s_published_then_changed_then_merge, 1),
    ("CI pull_request merge ref: the PR bumps then changes", s_pr_merge_ref, 1),
]


def main() -> int:
    passed = failed = 0
    for name, build, expected in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            build(tmp)
            problems = run_check(tmp)
        ok = len(problems) == expected
        if ok and expected:
            ok = any("plugin/crew" in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {expected} problem(s), got {len(problems)}")
            for problem in problems:
                print(f"       says: {problem}")
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
