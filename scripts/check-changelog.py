#!/usr/bin/env python3
"""Every version a branch sets owes a CHANGELOG.md line naming that exact version.

    python3 scripts/check-changelog.py [--root <repo>] [--base <ref>]

THE RULE (owner, 2026-11-09; CLAUDE.md "Scope discipline"). A branch that sets
a marketplace entry's `version` - a bump, a re-bump after main moved, a new
entry - leaves CHANGELOG.md naming `<name> <version>` in one of two forms:

  * an entry heading (`###` or `####`) that contains `<name> <version>`, as
    every entry does today: `### Fixed - crew 1.3.16: <title>`;
  * a re-number line, for a version that carries no change of its own, in the
    block directly under a `## [` heading and before its first `###` (the
    generator in `scripts/sync-updates.py` reads only `###` entries, so this
    block never reaches the README's "What's new"):

        - crew 1.3.14: re-bump only - <why: what it follows, or what carries the change>

A re-number line without a reason after `re-bump only` does not count.

WHICH VERSIONS. Only the ones the branch itself introduces, so history is
never asked to backfill. The versions are read from `.claude-plugin/marketplace.json`
(the file every plugin and skill registers in; `check-marketplace.py` already
holds each `plugin.json` equal to it) at every commit in `<base>..HEAD` that
changed that file, merges included (`git log -m`: a merge of main resolved to a
new number sets a version too), plus HEAD. A version equal to the one at the
merge base is not new. A version the branch set and then replaced is still
owed: it reached main's history through the merge, and the missing 1.3.2-1.3.5
were exactly that.

WHAT THIS DOES NOT CHECK. That the entry describes the change truthfully; that
the version was bumped at all (`check-marketplace.py`'s drift check owns that);
uncommitted edits (commit first, as CLAUDE.md says for the gate); a plugin
whose entry was removed.

<base> is `--base`, else `origin/$GITHUB_BASE_REF` (a pull_request run), else
`origin/main`.

Exit 0: nothing owed, or every version is covered. Exit 1: one line per version
with no entry. Exit 77: the check could not tell (the base is not a ref, git
failed, no CHANGELOG.md, an unparseable marketplace.json). 77 is never a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

MARKETPLACE = ".claude-plugin/marketplace.json"
CHANGELOG = "CHANGELOG.md"
EXIT_UNKNOWN = 77


class Unknown(Exception):
    """The check could not tell; never a pass."""


def _git(root: str, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", stdin=subprocess.DEVNULL, check=False)
    if done.returncode != 0:
        raise Unknown(f"git {' '.join(args)} -> {done.returncode}: {done.stderr.strip()}")
    return done.stdout


def versions_at(root: str, rev: str) -> dict[str, str]:
    """{entry name: version} in marketplace.json at `rev`; {} when it is absent there."""
    probe = subprocess.run(["git", "cat-file", "-e", f"{rev}:{MARKETPLACE}"], cwd=root,
                           capture_output=True, stdin=subprocess.DEVNULL, check=False)
    if probe.returncode != 0:
        return {}
    try:
        data = json.loads(_git(root, "show", f"{rev}:{MARKETPLACE}"))
        return {p["name"]: str(p["version"]) for p in data["plugins"] if "version" in p}
    except (ValueError, KeyError, TypeError) as exc:
        raise Unknown(f"{MARKETPLACE} at {rev[:12]} does not parse: {exc}") from exc


def resolve_base(root: str, explicit: str | None) -> str:
    if explicit:
        base = explicit
    elif os.environ.get("GITHUB_BASE_REF"):
        base = f"origin/{os.environ['GITHUB_BASE_REF']}"
    else:
        base = "origin/main"
    probe = subprocess.run(["git", "rev-parse", "--verify", "-q", f"{base}^{{commit}}"], cwd=root,
                           capture_output=True, stdin=subprocess.DEVNULL, check=False)
    if probe.returncode != 0:
        raise Unknown(f"{base} is not a ref here, so the check did not run")
    return base


def introduced(root: str, base: str) -> dict[tuple[str, str], str]:
    """{(name, version): short sha that set it} for the versions this branch sets."""
    merge_base = _git(root, "merge-base", base, "HEAD").strip()
    old = versions_at(root, merge_base) if merge_base else {}
    found: dict[tuple[str, str], str] = {}
    # -m: a merge commit is listed when its tree differs from ANY parent.
    log = _git(root, "log", "-m", "--format=%H", f"{base}..HEAD", "--", MARKETPLACE)
    revs = list(dict.fromkeys([*log.split(), _git(root, "rev-parse", "HEAD").strip()]))
    for rev in revs:
        for name, version in versions_at(root, rev).items():
            if old.get(name) != version:
                found.setdefault((name, version), rev[:7])
    return found


def _token(version: str) -> str:
    return rf"(?<![\d.]){re.escape(version)}(?![\d]|\.\d)"


def covered(text: str, name: str, version: str) -> bool:
    """True when CHANGELOG `text` has an entry heading or a re-number line for the pair."""
    heading = re.compile(rf"(?<![\w.-])`?{re.escape(name)}`?[\s:]*v?{_token(version)}")
    ledger = re.compile(
        rf"^[-*]\s+[*`]*{re.escape(name)}[*`]*\s+{_token(version)}[*`]*:\s+re-bump only"
        r"\s*[-–—:,;]\s*\S", re.IGNORECASE)
    fenced = False
    top_block = False  # between a `## [` heading and the first `###` under it
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            top_block = line.startswith("## [")
        elif line.startswith("### "):
            top_block = False
        if re.match(r"#{3,4}\s", line) and heading.search(line):
            return True
        if top_block and ledger.match(line):
            return True
    return False


def check(root: str, base: str) -> list[str]:
    path = os.path.join(root, CHANGELOG)
    if not os.path.isfile(path):
        raise Unknown(f"no {CHANGELOG} in {root}")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    problems = []
    for (name, version), sha in sorted(introduced(root, base).items()):
        if not covered(text, name, version):
            problems.append(
                f"MISSING: {name} {version} (set in {sha}) has no {CHANGELOG} entry. Add a `###` "
                f"heading naming `{name} {version}`, or, when it only re-numbers, under "
                f"`## [Unreleased]` before its first `###`: "
                f"`- {name} {version}: re-bump only - <why>`")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--base", default=None)
    args = parser.parse_args(argv)
    try:
        base = resolve_base(args.root, args.base)
        problems = check(args.root, base)
    except Unknown as exc:
        print(f"check-changelog: could not tell: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN
    for line in problems:
        print(f"check-changelog: {line}", file=sys.stderr)
    if problems:
        return 1
    print(f"check-changelog: every version set since {base} has a {CHANGELOG} entry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
