#!/usr/bin/env python3
"""L-0642: autopilot's open-questions stop sees through code fences, and stops
when it cannot tell.

`crew_autopilot._open_items` is the union of three answers:

1. main's parser (`crew_autopilot._legacy_open_items`, unchanged) -- the
   floor, so the stop never loses an item main's parser finds;
2. a strict fence view: the same parser run over the text with every TRACKED
   fence blanked. Only a fence opened at column 0 (backticks with no backtick
   in the info string, or tildes) and closed at column 0 by a run of the same
   marker, at least as long, with nothing after it, is tracked. Its lines are
   neither headings nor items, so a `# how to check` line inside it no longer
   ends the Open-questions section and hides the items after it. A tracked
   fence that opens inside the section before any item line is itself an item
   (`UNEXPLAINED_FENCE`): nothing says what it asks;
3. could not tell: any other fence-shaped line (indented, a backtick in a
   backtick info string, a shorter run, or a run with anything after it -- a
   trailing space included -- inside a fence) or a
   fence still open at the end of the text adds one `UNCLEAR_FENCE` item
   naming the first such line -- but only when the file names an
   Open-questions section somewhere (indented or fenced included). A file with
   no such section is never stopped by its fences.

No CommonMark emulation: no indentation, list or container rules. Put fences
at column 0 and close each one. The caller passes main's parser and heading
pattern, so this module imports nothing from crew_autopilot. Standard library
only.
"""

from __future__ import annotations

import re

UNCLEAR_FENCE = "could not tell where a code fence starts or ends"
UNEXPLAINED_FENCE = ("a code fence opens the Open questions section before any item: say what it "
                     "asks in an item, or move it under one")
_FENCE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_OPEN_QUESTIONS = "open questions"


def _shape(line):
    """(run, rest) when the line, indentation stripped, is fence-shaped, else None."""
    match = _FENCE.match(line.lstrip())
    return match.groups() if match else None


def fence_view(text, legacy, heading):
    """(items, unclear_line): `legacy` (main's parser) over the text with every
    tracked fence blanked, plus UNEXPLAINED_FENCE; `unclear_line` is the
    1-based line of the first fence shape this view does not track, or None."""
    lines = (text or "").splitlines()
    masked, unclear, fence = list(lines), None, None
    depth, seen, unexplained = 0, False, False
    for number, line in enumerate(lines, 1):
        shape = _shape(line)
        if fence is not None:
            masked[number - 1] = ""
            run, rest = shape or ("", "")
            if shape and line == line.lstrip() and run[0] == fence[0] \
                    and len(run) >= fence[1] and not rest:
                fence = None
            elif shape and unclear is None:
                unclear = number
            continue
        if shape:
            run, rest = shape
            if line == line.lstrip() and not (run[0] == "`" and "`" in rest):
                fence = (run[0], len(run), number)
                masked[number - 1] = ""
                unexplained = unexplained or bool(depth and not seen)
                continue
            unclear = unclear or number
        found = heading.match(line)
        if found:
            level, title = len(found.group(1)), found.group(2).strip()
            if depth and level > depth:
                continue
            if title.lower().startswith(_OPEN_QUESTIONS):
                depth = level
                seen = bool(title[len(_OPEN_QUESTIONS):].strip("\"'`.: "))
            else:
                depth = 0
        elif depth and line.strip():
            seen = True
    if fence is not None:
        unclear = unclear or fence[2]
    items = list(legacy("\n".join(masked)))
    return items + ([UNEXPLAINED_FENCE] if unexplained else []), unclear


def names_open_questions(text, heading):
    """Whether any line, indentation stripped, is an Open-questions heading."""
    for line in (text or "").splitlines():
        found = heading.match(line.lstrip())
        if found and found.group(2).strip().lower().startswith(_OPEN_QUESTIONS):
            return True
    return False


def open_items(text, legacy, heading):
    """main's items, then the fence view's not already present, then one
    UNCLEAR_FENCE item when a fence shape could not be read and the file names
    an Open-questions section."""
    items = list(legacy(text))
    view, unclear = fence_view(text, legacy, heading)
    items += [item for item in view if item not in items]
    if unclear is not None and names_open_questions(text, heading):
        items.append(f"{UNCLEAR_FENCE} (line {unclear}): put each fence at column 0 and close "
                     "it with the same marker")
    return items
