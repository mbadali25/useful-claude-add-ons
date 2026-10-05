#!/usr/bin/env python3
"""Regenerate the generated blocks in the README files.

Two kinds of block, one script, one ``--check``.

**The root README's "What's new".** ``CHANGELOG.md`` is the history. The root
``README.md`` shows only its newest two entries, one line each, between
``<!-- BEGIN CHANGELOG.md -->`` markers, then a link to the full changelog. A
line is the entry's heading -- ``<subject> <version>: <title>``, with a trailing
ticket reference dropped -- and one sentence: the entry's ``**Summary.**``
bullet when it has one, else the first sentence of its first bullet, else
nothing. Generated so it cannot go stale: the root README used to carry the
three UPDATE.md mirrors below, about 500 lines that sat on crew 0.17.0 while
crew shipped 1.0.344 (L-1518).

**The component READMEs' "What's new".**

Each component directory -- ``plugin/``, ``skills/``, ``mcp-servers/`` -- owns an
``UPDATE.md`` listing what is newly possible there, newest first. That file is the
single source. Everything above its first ``## `` heading is preamble and stays
local to it; the sections below are mirrored into the directory's own
``README.md`` (not the root one, since L-1518), between markers named after the
source path:

    <!-- BEGIN plugin/UPDATE.md -->
    <!-- END plugin/UPDATE.md -->

which is the same convention the existing ``README.md`` mirror blocks use.

Two rules fall out of mirroring one text into a README that is not its
directory's own file, and they stay although each source now has one host:

* **Headings are demoted one level.** A mirrored section always sits underneath a
  heading its host README supplies, so a source ``##`` renders as ``###``.
* **The mirrored sections carry no relative links.** ``../CHANGELOG.md`` is
  correct in at most one host depth, and a second host can come back. Keep links in the preamble, which is
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
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]

# Component directory -> the READMEs its UPDATE.md is mirrored into. The root
# README.md is not one: it shows the changelog's newest entries instead (L-1518).
SOURCES = {
    "plugin": ("plugin/README.md",),
    "skills": ("skills/README.md",),
    "mcp-servers": ("mcp-servers/README.md",),
}

CHANGELOG = "CHANGELOG.md"
WHATS_NEW_HOST = "README.md"
WHATS_NEW_COUNT = 2
# One line per entry, so a fallback first sentence is cut to this many characters.
SENTENCE_LIMIT = 240

# Every "### " heading under a release is an entry; the Keep-a-Changelog kind
# word is optional, so a heading in any other shape still renders rather than
# being skipped in silence. "#### " headings are a batch entry's parts.
KIND = r"(?:(?:Added|Changed|Fixed|Removed|Deprecated|Security)\b\s*(?:[\u2014\u2013-]\s*)?)?"
ENTRY_HEADING = re.compile(r"^### " + KIND + r"(.*)$")
PART_HEADING = re.compile(r"^#### " + KIND + r"(.*)$")
# "crew 1.0.345 — batch 5: T-0052, T-0057" (any dash, or none): the subject is
# what precedes the dash or the colon, without a trailing "batch <n>".
BATCH_SUBJECT = re.compile(r"^(.*?)(?:\s+[\u2014\u2013-]\s+|:\s|$)")
BATCH_WORD = re.compile(r"\bbatch\b", re.IGNORECASE)
BATCH_NUMBER = re.compile(r"\s+batch\s+\d+\s*$", re.IGNORECASE)
# A trailing "(T-0037, PR A)" or "(L-1518)": a ticket reference means nothing to
# a reader deciding whether to update.
TICKET_SUFFIX = re.compile(r"\s*\([^()]*\b[A-Z]+-\d+\b[^()]*\)\s*$")
BULLET_LABEL = re.compile(r"^\*\*([^*]+?)\*\*\s*")


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
    """Replace the content between a BEGIN/END marker pair.

    A second pair for the same marker is a structural error, not a second
    mirror. ``find`` returns the FIRST of each, so a duplicate pair below the
    first is never rewritten, never compared, and never reported -- and because
    the first block does update correctly, the run prints "already current" and
    ``--check`` exits 0. That is how ``skills/README.md`` came to carry a second
    block still announcing 25 skills while its source said 34, through CI, for
    four days. Refuse instead: one source, one block per README.
    """
    begin = f"<!-- BEGIN {marker} -->"
    end = f"<!-- END {marker} -->"
    if text.count(begin) > 1 or text.count(end) > 1:
        fail(
            f"{where} has {text.count(begin)} {begin} and {text.count(end)} {end} "
            "markers -- only the first pair would be rewritten and the rest would "
            "silently keep stale content. Delete the duplicate block; the "
            "surviving one is regenerated from the source."
        )
    start = text.find(begin)
    stop = text.find(end)
    if start == -1 or stop == -1:
        fail(f"{where} is missing the {begin} / {end} marker pair -- add it first")
    if stop < start:
        fail(f"{where} has {end} before {begin}")
    return text[: start + len(begin)] + f"\n\n{body}\n\n" + text[stop:]


def changelog_entries(
    text: str, limit: int = WHATS_NEW_COUNT
) -> list[tuple[str, list[str], list[str]]]:
    """Return the newest ``limit`` entries as (heading text, bullet texts, part titles).

    An entry is any ``###`` heading below a ``## [`` release heading. Its bullets
    are the top-level ``- `` items up to the next heading, each with its
    continuation lines joined by spaces. Its parts are the titles of the ``####``
    headings under it (a batch PR's per-ticket entries). Fenced code is skipped
    so a ``###`` inside an example is not an entry.
    """
    entries: list[tuple[str, list[str], list[str]]] = []
    parts: list[str] | None = None
    in_release = False
    fenced = False
    current: list[str] | None = None
    joining = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            in_release = line.startswith("## [")
            current = parts = None
            continue
        if line.startswith("#"):
            current = None
            if line.startswith("#####"):
                # Deeper than a part: belongs to the part above, ends nothing.
                continue
            part = PART_HEADING.match(line) if in_release else None
            if part and parts is not None:
                title = part.group(1).strip() or line[5:].strip()
                if title:
                    parts.append(title)
                continue
            match = ENTRY_HEADING.match(line) if in_release else None
            parts = None
            if match:
                if len(entries) == limit:
                    break
                current, parts = [], []
                entries.append((match.group(1).strip() or line[4:].strip(), current, parts))
            continue
        if current is None:
            continue
        if line.startswith("- "):
            current.append(line[2:].strip())
            joining = True
        elif not line.strip() or line.lstrip().startswith(("- ", "* ")):
            # A blank line or a nested list ends the bullet's lead sentence.
            joining = False
        elif current and joining and line.startswith("  "):
            current[-1] += " " + line.strip()
    return entries


def first_sentence(text: str) -> str:
    """Return ``text`` up to its first full stop outside inline code."""
    in_code = False
    for index, char in enumerate(text):
        if char == "`":
            in_code = not in_code
        elif char in ".!?" and not in_code:
            after = text[index + 1 : index + 2]
            if after in ("", " ") and not text[: index + 1].endswith(("e.g.", "i.e.", "etc.")):
                return text[: index + 1]
    return text


def shorten(text: str, limit: int = SENTENCE_LIMIT) -> str:
    """Cut ``text`` to ``limit`` characters at a space outside inline code."""
    if len(text) <= limit:
        return text
    cut = -1
    in_code = False
    for index, char in enumerate(text[:limit]):
        if char == "`":
            in_code = not in_code
        elif char == " " and not in_code:
            cut = index
    return (text[:cut] if cut > 0 else text[:limit]).rstrip(" ,;:") + " ..."


def summary_bullet(bullets: list[str]) -> str:
    """The text of a ``**Summary.**`` bullet, or "" when there is none."""
    for bullet in bullets:
        label = BULLET_LABEL.match(bullet)
        if label and label.group(1).strip().rstrip(".").lower() == "summary":
            return bullet[label.end() :].strip()
    return ""


def summary(bullets: list[str]) -> str:
    """One plain sentence for a reader: a ``**Summary.**`` bullet, else the first bullet's."""
    own = summary_bullet(bullets)
    if own:
        return own
    if not bullets:
        return ""
    first = BULLET_LABEL.sub("", bullets[0], count=1).strip()
    return shorten(first_sentence(first))


def part_title(heading: str) -> str:
    """A batch part's title without its ticket reference or its ``subject:`` prefix."""
    subject, _, title = TICKET_SUFFIX.sub("", heading).partition(": ")
    return (title or subject).strip().rstrip(".")


def entry_line(heading: str, bullets: list[str], parts: list[str] | None = None) -> str:
    """``- **<subject> <version>**: <Title>. <sentence>`` -- one line per entry.

    A batch entry (``####`` parts, and either no bullets of its own or
    "batch" in its heading) shows its ``**Summary.**`` bullet if it has one,
    else its parts' titles: ``- **crew 1.0.345**: <part>; <part>.``
    """
    if parts and (not bullets or BATCH_WORD.search(heading)):
        subject = BATCH_SUBJECT.match(heading).group(1)
        subject = BATCH_NUMBER.sub("", subject).replace("`", "").strip()
        own = summary_bullet(bullets)
        listed = own or shorten("; ".join(part_title(part) for part in parts))
        listed = listed[:1].upper() + listed[1:]
        if not listed.endswith((".", "!", "?")):
            listed += "."
        return f"- **{subject}**: {listed}" if subject else f"- {listed}"
    subject, _, title = TICKET_SUFFIX.sub("", heading).partition(": ")
    if not title:
        subject, title = "", subject
    subject = subject.replace("`", "")
    title = title.strip().rstrip(".")
    title = title[:1].upper() + title[1:]
    line = f"- **{subject.strip()}**: {title}." if subject.strip() else f"- {title}."
    sentence = summary(bullets)
    return f"{line} {sentence}" if sentence else line


def render_whats_new(changelog: str) -> str:
    """The root README's "What's new" block body, from the newest changelog entries."""
    entries = changelog_entries(changelog)
    if not entries:
        fail(f"{CHANGELOG} has no '###' entry under a '## [' heading")
    lines = [entry_line(heading, bullets, parts) for heading, bullets, parts in entries]
    return "\n".join(lines) + f"\n\nFull history: [{CHANGELOG}]({CHANGELOG})."


def fail(message: str) -> NoReturn:
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

    changelog = ROOT / CHANGELOG
    if not changelog.is_file():
        fail(f"{CHANGELOG} does not exist")
    host = ROOT / WHATS_NEW_HOST
    if not host.is_file():
        fail(f"{WHATS_NEW_HOST} does not exist")
    current = updated.get(WHATS_NEW_HOST, read(host))
    updated[WHATS_NEW_HOST] = splice(current, CHANGELOG, render_whats_new(read(changelog)), WHATS_NEW_HOST)

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
