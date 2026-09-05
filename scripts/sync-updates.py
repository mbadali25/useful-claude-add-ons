#!/usr/bin/env python3
"""Regenerate the UPDATE.md blocks mirrored into README files.

Each component directory -- ``plugin/``, ``skills/``, ``mcp-servers/`` -- owns an
``UPDATE.md`` listing what is newly possible there, newest first. That file is the
single source. Everything above its first ``## `` heading is preamble and stays
local to it; the sections below are mirrored into the directory's own
``README.md`` and into the repository ``README.md``, between markers named after
the source path:

    <!-- BEGIN plugin/UPDATE.md -->
    <!-- END plugin/UPDATE.md -->

which is the same convention the existing ``README.md`` mirror blocks use.

Two rules fall out of mirroring one text into two directory depths:

* **Headings are demoted one level.** A mirrored section always sits underneath a
  heading its host README supplies, so a source ``##`` renders as ``###``.
* **The mirrored sections carry no relative links.** ``../CHANGELOG.md`` is
  correct in at most one of the two hosts. Keep links in the preamble, which is
  never mirrored, and write paths in the sections as inline code.

Run with no arguments to rewrite every block. Run with ``--check`` to verify the
blocks are current -- it writes nothing, prints what is stale, and exits 1.

Exit codes: 0 everything current (or written), 1 a block is stale under
``--check``, 2 a structural problem the script will not paper over.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Component directory -> the READMEs its UPDATE.md is mirrored into.
SOURCES = {
    "plugin": ("plugin/README.md", "README.md"),
    "skills": ("skills/README.md", "README.md"),
    "mcp-servers": ("mcp-servers/README.md", "README.md"),
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    # newline="\n" so a run on Windows does not rewrite the whole file to CRLF.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def sections(source: Path) -> str:
    """Return the mirrored part of an UPDATE.md: its first ``## `` heading onward."""
    lines = read(source).splitlines()
    for index, line in enumerate(lines):
        if line.startswith("## "):
            return "\n".join(lines[index:]).strip()
    fail(f"{source.relative_to(ROOT)} has no '## ' heading, so there is nothing to mirror")


def check_links(text: str, source: str) -> None:
    """Reject relative Markdown links in the mirrored body.

    A mirrored section is spliced into two READMEs at different directory
    depths, so any relative target is wrong in at least one of them:
    ``../CHANGELOG.md`` resolves from ``plugin/README.md`` and 404s from the
    root, and ``skills/foo`` does the reverse. The module docstring has always
    stated this rule; nothing enforced it, and the first UPDATE.md written
    against it shipped a ``../.claude-plugin/marketplace.json`` link that had to
    be caught by eye. A rule the generator states and does not check is worse
    than no rule, because it reads as guaranteed.

    Absolute URLs and pure ``#anchor`` targets are fine -- they mean the same
    thing from any depth. Keep relative links in the preamble above the first
    ``## `` heading, which is never mirrored.
    """
    offenders = []
    for label, target in re.findall(r"\[([^\]]*)\]\(([^)]+)\)", text):
        href = target.split()[0].strip("<>")
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        offenders.append(f"[{label}]({href})")
    if offenders:
        fail(
            f"{source} has relative link(s) in a mirrored section: "
            + ", ".join(offenders)
            + " -- a relative target cannot resolve from both the component "
            "README and the root README. Move the link above the first '## ' "
            "heading, or write the path as inline code."
        )


def demote(text: str) -> str:
    """Drop every heading one level, leaving fenced code untouched."""
    out = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("#"):
            line = "#" + line
        out.append(line)
    return "\n".join(out)


def splice(text: str, marker: str, body: str, where: str) -> str:
    """Replace the content between a BEGIN/END marker pair."""
    begin = f"<!-- BEGIN {marker} -->"
    end = f"<!-- END {marker} -->"
    start = text.find(begin)
    stop = text.find(end)
    if start == -1 or stop == -1:
        fail(f"{where} is missing the {begin} / {end} marker pair -- add it first")
    if stop < start:
        fail(f"{where} has {end} before {begin}")
    return text[: start + len(begin)] + f"\n\n{body}\n\n" + text[stop:]


def fail(message: str) -> None:
    print(f"sync-updates: {message}", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the blocks are current; write nothing and exit 1 if any is stale",
    )
    args = parser.parse_args()

    # One target README can host several blocks, so build each target's text once
    # and splice every source into it before comparing or writing.
    updated: dict[str, str] = {}
    for name, targets in SOURCES.items():
        source = ROOT / name / "UPDATE.md"
        if not source.is_file():
            fail(f"{name}/UPDATE.md does not exist")
        raw = sections(source)
        check_links(raw, f"{name}/UPDATE.md")
        body = demote(raw)
        for target in targets:
            path = ROOT / target
            if not path.is_file():
                fail(f"{target} does not exist")
            current = updated.get(target, read(path))
            updated[target] = splice(current, f"{name}/UPDATE.md", body, target)

    stale = sorted(target for target, text in updated.items() if text != read(ROOT / target))

    if args.check:
        if stale:
            for target in stale:
                print(f"sync-updates: {target} is stale -- run scripts/sync-updates.py")
            return 1
        print(f"sync-updates: {len(updated)} README files current")
        return 0

    for target in stale:
        write(ROOT / target, updated[target])
        print(f"sync-updates: wrote {target}")
    if not stale:
        print(f"sync-updates: {len(updated)} README files already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
