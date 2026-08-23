#!/usr/bin/env python3
"""Draft Keep a Changelog entries from git history.

Groups commits into Added / Changed / Deprecated / Removed / Fixed / Security using
conventional-commit prefixes where present, falling back to keyword heuristics. Filters
merge commits and noise.

The output is a DRAFT. Rewrite entries in user-facing language before committing them:
"fix(parser): handle null in tokenize()" should become "Fixed a crash when parsing files
with empty lines."

Usage:
    python git_changelog.py /path/to/repo                    # since last tag
    python git_changelog.py . --since-tag v1.2.0
    python git_changelog.py . --since-ref abc1234
    python git_changelog.py . --all                          # entire history
    python git_changelog.py . --json
    python git_changelog.py . --list-tags

No third-party dependencies. Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

CATEGORIES = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]

TYPE_MAP = {
    "feat": "Added", "feature": "Added", "add": "Added",
    "fix": "Fixed", "bugfix": "Fixed", "hotfix": "Fixed", "patch": "Fixed",
    "perf": "Changed", "refactor": "Changed", "change": "Changed", "update": "Changed",
    "style": "Changed", "revert": "Changed", "build": "Changed", "deps": "Changed",
    "remove": "Removed", "delete": "Removed", "drop": "Removed",
    "deprecate": "Deprecated",
    "security": "Security", "sec": "Security",
}

KEYWORDS = [
    ("Security", re.compile(
        r"(?i)\b(security|vulnerab|CVE-\d{4}-\d+|xss|csrf|sql\s?injection|sanitiz|"
        r"escalat|auth bypass|exploit)\b")),
    ("Removed", re.compile(r"(?i)\b(remove[ds]?|delete[ds]?|drop(?:ped|s)?|purge[ds]?)\b")),
    ("Deprecated", re.compile(r"(?i)\bdeprecat")),
    ("Fixed", re.compile(r"(?i)\b(fix(?:e[sd])?|bug|regression|repair|correct(?:ed|s)?|resolve[ds]?)\b")),
    ("Added", re.compile(r"(?i)\b(add(?:ed|s)?|new|introduce[ds]?|implement(?:ed|s)?|"
                         r"support for|create[ds]?|enable[ds]?)\b")),
]

NOISE = re.compile(
    r"(?i)^(merge (branch|pull request|remote)|revert \"revert|wip\b|"
    r"bump version|version bump|release v?\d|"
    r"(chore|style|ci|test|docs)(\([^)]*\))?!?:\s*(lint|format|typo|whitespace|"
    r"prettier|eslint|black|isort|reformat|cleanup|update snapshot)|"
    r"\[skip ci\]|^fixup!|^squash!|^amend)"
)

CONVENTIONAL = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<subject>.+)$")

BREAKING_BODY = re.compile(r"(?im)^BREAKING[ -]CHANGE:")


def git(repo: Path, *args: str):
    out = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, text=True, check=False, timeout=30)
    return out.stdout.strip() if out.returncode == 0 else None


def collect(repo: Path, rev_range: str, limit: int):
    sep = "\x1e"
    fmt = f"%h{sep}%an{sep}%ad{sep}%s{sep}%b"
    raw = git(repo, "log", rev_range, "--no-merges", f"--pretty=format:{fmt}%x1f",
              "--date=short", f"-n{limit}")
    if not raw:
        return []
    commits = []
    for record in raw.split("\x1f"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split(sep)
        if len(parts) < 4:
            continue
        sha, author, date, subject = parts[0], parts[1], parts[2], parts[3]
        body = parts[4] if len(parts) > 4 else ""
        commits.append({"sha": sha, "author": author, "date": date,
                        "subject": subject.strip(), "body": body.strip()})
    return commits


def classify(commit) -> tuple:
    """Return (category, cleaned_subject, breaking, noise)."""
    subject = commit["subject"]
    if NOISE.search(subject):
        return None, subject, False, True

    breaking = BREAKING_BODY.search(commit["body"]) is not None
    m = CONVENTIONAL.match(subject)
    if m:
        ctype = m.group("type").lower()
        breaking = breaking or bool(m.group("bang"))
        cleaned = m.group("subject").strip()
        scope = m.group("scope")
        category = TYPE_MAP.get(ctype)
        if category:
            if scope:
                cleaned = f"{cleaned} ({scope})"
            return category, cleaned, breaking, False
        if ctype in {"chore", "docs", "test", "ci"}:
            return None, cleaned, breaking, True
        subject = cleaned

    for category, pattern in KEYWORDS:
        if pattern.search(subject):
            return category, subject, breaking, False
    return "Changed", subject, breaking, False


def build(repo: Path, rev_range: str, limit: int, keep_noise: bool):
    commits = collect(repo, rev_range, limit)
    grouped = OrderedDict((c, []) for c in CATEGORIES)
    skipped = []
    for c in commits:
        category, cleaned, breaking, noise = classify(c)
        entry = {"sha": c["sha"], "date": c["date"], "author": c["author"],
                 "text": cleaned, "breaking": breaking, "original": c["subject"]}
        if noise and not keep_noise:
            skipped.append(entry)
            continue
        grouped[category or "Changed"].append(entry)
    return grouped, skipped, len(commits)


def render(grouped, skipped, total, rev_range, show_sha) -> str:
    out = ["## [Unreleased]", ""]
    out.insert(0, f"<!-- draft from `git log {rev_range}` - {total} commits examined; "
                  f"rewrite in user-facing language before committing -->")
    any_entries = False
    for category in CATEGORIES:
        entries = grouped.get(category) or []
        if not entries:
            continue
        any_entries = True
        out.append(f"### {category}")
        for e in entries:
            prefix = "**BREAKING:** " if e["breaking"] else ""
            suffix = f"  <!-- {e['sha']} -->" if show_sha else ""
            text = e["text"][:1].upper() + e["text"][1:] if e["text"] else e["original"]
            out.append(f"- {prefix}{text}{suffix}")
        out.append("")
    if not any_entries:
        out.append("_No user-facing changes detected in this range._")
        out.append("")
    if skipped:
        out.append(f"<!-- {len(skipped)} commits filtered as noise:")
        for e in skipped[:25]:
            out.append(f"     {e['sha']} {e['original'][:90]}")
        if len(skipped) > 25:
            out.append(f"     ... {len(skipped)-25} more")
        out.append("-->")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--since-tag", default="auto",
                    help="tag to start from; 'auto' uses the most recent tag")
    ap.add_argument("--since-ref", help="explicit ref/sha to start from (overrides --since-tag)")
    ap.add_argument("--all", action="store_true", help="use entire history")
    ap.add_argument("--limit", type=int, default=500, help="max commits (default 500)")
    ap.add_argument("--keep-noise", action="store_true",
                    help="include chore/docs/format commits instead of filtering them")
    ap.add_argument("--show-sha", action="store_true", help="append commit sha as a comment")
    ap.add_argument("--list-tags", action="store_true", help="list tags newest first and exit")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser()
    if git(repo, "rev-parse", "--git-dir") is None:
        print(f"error: {repo} is not a git repository", file=sys.stderr)
        return 2

    if args.list_tags:
        tags = git(repo, "tag", "--sort=-creatordate") or ""
        print(tags or "(no tags)")
        return 0

    if args.all:
        rev_range = "HEAD"
    elif args.since_ref:
        rev_range = f"{args.since_ref}..HEAD"
    else:
        tag = None if args.since_tag == "auto" else args.since_tag
        if tag is None:
            tag = git(repo, "describe", "--tags", "--abbrev=0")
        rev_range = f"{tag}..HEAD" if tag else "HEAD"

    grouped, skipped, total = build(repo, rev_range, args.limit, args.keep_noise)

    if args.json:
        print(json.dumps({
            "range": rev_range, "commits_examined": total,
            "grouped": {k: v for k, v in grouped.items() if v},
            "filtered": skipped,
        }, indent=2))
    else:
        print(render(grouped, skipped, total, rev_range, args.show_sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
