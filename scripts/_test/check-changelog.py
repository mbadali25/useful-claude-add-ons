#!/usr/bin/env python3
"""Suite for scripts/check-changelog.py: must-fail and must-pass cases.

Every case builds a throwaway git repo in a temp directory (origin/main is a
local ref there) and runs the real checker against it with --root. Nothing
touches this repository's files. Two mutation cases at the end prove the suite
can go red: a checker that accepts every entry, and one that ignores the
intermediate versions, must each fail at least one case.

Run: python3 scripts/_test/check-changelog.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check-changelog.py")


def load():
    spec = importlib.util.spec_from_file_location("check_changelog", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sh(cwd, *args):
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"{args} -> {done.returncode}\n{done.stderr}")
    return done.stdout.strip()


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def market(root, crew, other="1.0.0"):
    write(root, ".claude-plugin/marketplace.json", json.dumps({"plugins": [
        {"name": "crew", "source": "./plugin/crew", "version": crew},
        {"name": "other", "source": "./plugin/other", "version": other}]}, indent=2))


HEAD = "# Changelog\n\n## [Unreleased]\n\n"
OLD = "### Fixed - crew 1.3.0: the first entry\n\n- **Summary.** old.\n"


def log(*, ledger="", entries=""):
    """A changelog: the pre-### block (ledger), then new entries, then history."""
    return HEAD + ledger + ("\n" if ledger else "") + entries + OLD


def commit(root, message):
    sh(root, "git", "add", "-A")
    sh(root, "git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
       "--no-gpg-sign", "-m", message)


def repo(tmp):
    """main at crew 1.3.0, origin/main pointing at it, a branch checked out."""
    sh(tmp, "git", "init", "-q", "-b", "main")
    market(tmp, "1.3.0")
    write(tmp, "CHANGELOG.md", log())
    commit(tmp, "base")
    sh(tmp, "git", "update-ref", "refs/remotes/origin/main", "HEAD")
    sh(tmp, "git", "checkout", "-q", "-b", "lane")
    return tmp


def run(module, root):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main(["--root", root])
    return code, err.getvalue()


def bump(tmp, version, changelog, message=None):
    market(tmp, version)
    write(tmp, "CHANGELOG.md", changelog)
    commit(tmp, message or f"crew {version}")


def cases(module):
    """(label, expected exit code, expected text or None, builder) rows."""
    rows = []

    def case(label, code, text=None):
        def deco(fn):
            rows.append((label, code, text, fn))
            return fn
        return deco

    @case("PASS no version set by the branch", 0)
    def _(tmp):
        write(tmp, "x.txt", "x")
        commit(tmp, "unrelated")

    @case("PASS bump with an entry heading", 0)
    def _(tmp):
        bump(tmp, "1.3.1", log(entries="### Fixed - crew 1.3.1: a fix\n\n- **Summary.** s.\n\n"))

    @case("PASS bump with a backticked heading", 0)
    def _(tmp):
        bump(tmp, "1.3.1", log(entries="### Fixed - `crew` 1.3.1: a fix\n\n- **Summary.** s.\n\n"))

    @case("PASS re-bump only line with a reason", 0)
    def _(tmp):
        bump(tmp, "1.3.1", log(ledger="- crew 1.3.1: re-bump only - no change from 1.3.0's content\n"))

    @case("PASS history is never asked to backfill (1.3.0 stays, 9.9.9 never mentioned)", 0)
    def _(tmp):
        write(tmp, "CHANGELOG.md", log())  # unchanged; old versions have no extra entries
        write(tmp, "y.txt", "y")
        commit(tmp, "unrelated")

    @case("PASS every intermediate version covered", 0)
    def _(tmp):
        bump(tmp, "1.3.1", log(ledger="- crew 1.3.1: re-bump only - first\n"))
        bump(tmp, "1.3.2", log(ledger="- crew 1.3.1: re-bump only - first\n"
                                      "- crew 1.3.2: re-bump only - second\n"))

    @case("PASS a version set only by a merge commit, covered", 0)
    def _(tmp):
        sh(tmp, "git", "checkout", "-q", "-b", "side")
        write(tmp, "side.txt", "s")
        commit(tmp, "side work")
        sh(tmp, "git", "checkout", "-q", "lane")
        write(tmp, "lane.txt", "l")
        commit(tmp, "lane work")
        sh(tmp, "git", "-c", "user.email=t@t", "-c", "user.name=t", "merge", "-q", "--no-ff",
           "--no-commit", "--no-gpg-sign", "side")
        market(tmp, "1.3.4")
        write(tmp, "CHANGELOG.md", log(ledger="- crew 1.3.4: re-bump only - follows the merge\n"))
        commit(tmp, "Merge side; crew 1.3.4")

    @case("PASS a new entry in the marketplace with its heading", 0)
    def _(tmp):
        with open(os.path.join(tmp, ".claude-plugin/marketplace.json"), encoding="utf-8") as fh:
            data = json.loads(fh.read())
        data["plugins"].append({"name": "fresh", "source": "./plugin/fresh", "version": "0.1.0"})
        write(tmp, ".claude-plugin/marketplace.json", json.dumps(data))
        write(tmp, "CHANGELOG.md", log(entries="### Added - fresh 0.1.0: a new plugin\n\n- s\n\n"))
        commit(tmp, "add fresh")

    @case("FAIL bump with no CHANGELOG entry", 1, "crew 1.3.1")
    def _(tmp):
        bump(tmp, "1.3.1", log())

    @case("FAIL a replaced intermediate version has no entry", 1, "crew 1.3.1")
    def _(tmp):
        bump(tmp, "1.3.1", log())
        bump(tmp, "1.3.2", log(ledger="- crew 1.3.2: re-bump only - second\n"))

    @case("FAIL 1.3.1 does not cover 1.3.10 (prefix of a longer number)", 1, "crew 1.3.10")
    def _(tmp):
        bump(tmp, "1.3.10", log(entries="### Fixed - crew 1.3.1: older\n\n- s\n\n"))

    @case("FAIL a re-bump line with no reason", 1, "crew 1.3.1")
    def _(tmp):
        bump(tmp, "1.3.1", log(ledger="- crew 1.3.1: re-bump only\n"))

    @case("FAIL a re-bump line below an entry heading is not in the block", 1, "crew 1.3.1")
    def _(tmp):
        bump(tmp, "1.3.1", log().replace(
            OLD, OLD + "\n- crew 1.3.1: re-bump only - buried in an old entry\n"))

    @case("FAIL a mention in a bullet is not an entry", 1, "crew 1.3.1")
    def _(tmp):
        bump(tmp, "1.3.1", log(entries="### Fixed - crew 1.3.2: other\n\n- follows crew 1.3.1 here\n\n"))

    @case("FAIL the entry names another plugin", 1, "crew 1.3.1")
    def _(tmp):
        bump(tmp, "1.3.1", log(entries="### Fixed - other 1.3.1: not crew\n\n- s\n\n"))

    @case("FAIL a line inside a fenced block is not an entry", 1, "crew 1.3.1")
    def _(tmp):
        bump(tmp, "1.3.1", log(entries="```\n### Fixed - crew 1.3.1: example\n```\n\n"))

    @case("FAIL a new marketplace entry with no CHANGELOG line", 1, "fresh 0.1.0")
    def _(tmp):
        data = {"plugins": [{"name": "fresh", "source": "./plugin/fresh", "version": "0.1.0"}]}
        write(tmp, ".claude-plugin/marketplace.json", json.dumps(data))
        commit(tmp, "add fresh")

    @case("UNKNOWN origin/main is not a ref (exit 77, never a pass)", 77, "not a ref")
    def _(tmp):
        sh(tmp, "git", "update-ref", "-d", "refs/remotes/origin/main")

    return rows


def run_all(module):
    failures = []
    for label, code, text, build in cases(module):
        with tempfile.TemporaryDirectory() as tmp:
            repo(tmp)
            build(tmp)
            got, err = run(module, tmp)
        ok = got == code and (text is None or text in err)
        print(("ok   " if ok else "FAIL ") + label + ("" if ok else f"  (exit {got}, wanted {code}; {err.strip()})"))
        if not ok:
            failures.append(label)
    return failures


def main():
    module = load()
    failures = run_all(module)
    if failures:
        print(f"{len(failures)} case(s) failed")
        return 1
    # Sabotage: each mutated checker must turn the suite red.
    original = module.covered
    module.covered = lambda *_a, **_k: True
    with contextlib.redirect_stdout(io.StringIO()):
        accept_all = run_all(module)
    module.covered = original
    original_introduced = module.introduced

    def final_only(root, base):
        found = original_introduced(root, base)
        top = {}
        for (name, version), sha in found.items():
            top[name] = max(top.get(name, (version, sha)), (version, sha),
                            key=lambda p: [int(x) for x in p[0].split(".")])
        return {(n, v): s for n, (v, s) in top.items()}

    module.introduced = final_only
    with contextlib.redirect_stdout(io.StringIO()):
        final_only_failures = run_all(module)
    module.introduced = original_introduced
    for label, red in (("accept-everything", accept_all), ("ignore-intermediates", final_only_failures)):
        if not red:
            print(f"SABOTAGE NOT DETECTED: the {label} mutation left the suite green")
            return 1
        print(f"ok   sabotage {label}: {len(red)} case(s) went red")
    print("all cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
