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


# A backticked token is only a PATH claim when it looks like one. Everything
# else in backticks on a codemap line is prose furniture -- a symbol
# (`abspath`, `blake2b`), a literal (`None`), a method (`Front::dispatch()`),
# a CLI flag (`--worktree-path`). Comparing those against a set of file paths
# reports every one as an uncorroborated claim.
#
# Measured before this fix: 186 conflicts on this repo, nearly all symbols; a
# peer session measured 239 of 456 on a prose-heavy map. The cost is not the
# noise itself but what it hides -- a list that is mostly false is a list
# nobody reads, so a REAL contradiction in it is invisible.
#
# The limit, stated because it is a real one: a BARE single-segment name with
# no slash and no extension -- `_verify`, `scripts` -- reads as prose here and
# is therefore never compared. That is a false negative, and a false negative
# silently drops a real contradiction, which is the worse direction of the two.
# It is accepted anyway because nothing in a backticked token distinguishes a
# bare directory from a bare symbol, and guessing would reintroduce the noise
# this exists to remove. Cite a directory with a trailing slash or one child
# path if you want it compared.
_PATHISH_RE = re.compile(r"^[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)+$")
_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def is_path_token(token):
    """Whether `token` is a file-path claim rather than prose in backticks."""
    if not token or token.endswith("()") or "::" in token or "->" in token:
        return False
    if token.startswith("-"):          # a CLI flag, not a path
        return False
    return bool(_PATHISH_RE.match(token) or _EXT_RE.search(token))


def _paths(lines):
    """Anchored file paths in a set of lines -- what two claims are compared on.

    Non-path tokens are dropped rather than compared; see `is_path_token`.
    """
    return {
        path
        for line in lines
        for token in _ANCHOR_TOKEN_RE.findall(line)
        for path in (_path_of(token),)
        if is_path_token(path)
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
            found = [_path_of(x) for x in _ANCHOR_TOKEN_RE.findall(line)]
            found = [x for x in found if is_path_token(x)]
            if found and found[0] in have:
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
    # `touched` can only ever hold DERIVE headings -- KEEP is skipped at the
    # top of the loop above, so `Does`, `Landmines` and `Unverified` are never
    # read by this procedure at all. The caller must not treat it as "this
    # note was re-verified"; see crew_upgrade's anchor handling.
    return {"body": body, "conflicts": conflicts,
            "added": added, "touched": touched,
            "derivedOnly": True}
