"""Reconciles a hand-written codemap note against facts derived from the graph.

Pure text in, text out. No file or graph access, so the policy this module
encodes -- which sections a machine may rewrite and which it may not -- is
testable without building a graph first.

The split is the whole design:

  KEEP    human judgment an AST parser cannot produce. Passed through
          byte-identical, always.
  DERIVE  mechanical structure the graph knows better. Graph facts are ADDED;
          an existing line the graph does not corroborate is retained and
          reported, because the graph misses generated call sites, reflection,
          and dynamic dispatch.
"""

import re

KEEP = frozenset({"Does", "Landmines", "Unverified"})
DERIVE = frozenset({"Entry points", "Owns data", "Calls out to"})

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_ANCHOR_TOKEN_RE = re.compile(r"`([^`]+)`")
_LINE_SUFFIX_RE = re.compile(r":\d+$")


def split_sections(text):
    """Map each `## ` heading to its body lines. Preamble is keyed ''."""
    sections, current = {}, ""
    sections[current] = []
    for line in text.splitlines():
        found = _HEADING_RE.match(line)
        if found:
            current = found.group(1)
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return sections


def _path_of(token):
    """The file path from a `path:line` anchor, dropping the line number.

    Comparison is by path, never by path:line. A refactor that shifts line
    numbers would otherwise turn every hand-written entry into a
    "contradiction", and an UPGRADE.md that is mostly line-drift noise is a
    report nobody reads -- which protects nothing.
    """
    return token.rsplit(":", 1)[0] if _LINE_SUFFIX_RE.search(token) else token


def _paths(lines):
    """Anchored file paths in a set of lines -- what two claims are compared on."""
    return {
        _path_of(token)
        for line in lines
        for token in _ANCHOR_TOKEN_RE.findall(line)
    }


def reconcile(text, derived):
    """Merge graph-derived facts into a codemap note.

    Returns {body, conflicts, added, touched}. `conflicts` names existing
    claims the graph did not corroborate; they stay in `body`.
    """
    sections = split_sections(text)
    conflicts, added, touched = [], [], []

    for heading, new_lines in derived.items():
        if heading in KEEP or heading not in DERIVE:
            continue

        if heading not in sections:
            # The map never had this heading. Without this branch the graph's
            # facts for it are dropped in silence -- not wrong, absent, which is
            # the worse failure for an upgrade tool. A v1 note written before
            # anyone thought to record owned tables is precisely the note most
            # likely to lack the heading and most in need of the content.
            if not new_lines:
                continue
            sections[heading] = [""] + list(new_lines) + [""]
            added.extend(new_lines)
            touched.append(heading)
            continue

        existing = sections[heading]
        have = _paths(existing)
        want = _paths(new_lines)

        # A graph line whose path is already claimed is an update to an
        # existing entry (typically a shifted line number), not a new fact.
        fresh = []
        for line in new_lines:
            found = _ANCHOR_TOKEN_RE.findall(line)
            if found and _path_of(found[0]) in have:
                continue
            fresh.append(line)

        if fresh:
            body = [ln for ln in existing if ln.strip()]
            sections[heading] = [""] + body + fresh + [""]
            added.extend(fresh)
            touched.append(heading)

        # A conflict is a whole FILE the map claims and the graph does not
        # know about -- not a line that moved.
        for path in sorted(have - want):
            # ASCII on purpose: /crew:upgrade reports conflicts, and a console
            # on a Windows OEM codepage cannot encode an em-dash -- the same
            # crash already fixed once in pm_brief.
            conflicts.append(
                f"{heading}: `{path}` is in the map but not in the graph "
                f"- kept, verify by hand"
            )

    out = []
    for heading, lines in sections.items():
        if heading:
            out.append(f"## {heading}")
        out.extend(lines)
    body = "\n".join(out).rstrip() + "\n"
    return {"body": body, "conflicts": conflicts,
            "added": added, "touched": touched}
