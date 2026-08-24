"""Reads crew state from a repository and evaluates the PM's attention triggers.

Standard library only, and every read fails soft. This module runs from a
SessionStart hook, so an exception here would break every session opened in the
repository -- an absent or malformed file must yield an absent value, never a
traceback.
"""

import json
import os
import re

SCHEMA_CURRENT = 2

# Verbatim from crew-scaling/SKILL.md. Below the floor the review is broken
# rather than thorough; above the ceiling the tickets are too large.
HEALTHY_LOW = 0.3
HEALTHY_HIGH = 2.0
METRICS_WINDOW = 10

_TICKET_RE = re.compile(r"([A-Z][A-Z0-9]*-\d+)")

# Markers that mean a ticket line is finished, matched only at the START of the
# line (after any list bullet). Scanning the whole line for words like "done"
# or "merged" reads a description as a status: `- T-3 — clean up after the
# merged branch` is open work, and skipping it would report "no ticket open"
# while one is -- the same class of bug as taking the first match.
_DONE_RE = re.compile(
    r"^[-*\s]*(\[x\]|~~|(done|closed|merged|shipped|complete\w*)\b[:\s-])",
    re.IGNORECASE,
)


def read_text(path):
    """Return the file's text, or None if it cannot be read for any reason."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def load_config(root):
    """Parse .crew/config.json. Returns {} when absent, malformed, or not a dict."""
    text = read_text(os.path.join(root, ".crew", "config.json"))
    if text is None:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _leading_int(cell):
    """First integer in a table cell, or None. 'BLOCK' and '---' yield None."""
    found = re.search(r"-?\d+", cell)
    return int(found.group()) if found else None


def _verdict(rate):
    if rate < HEALTHY_LOW:
        return "review not catching defects"
    if rate > HEALTHY_HIGH:
        return "tickets too large"
    return "healthy"


def read_metrics(root, window=METRICS_WINDOW):
    """BLOCK+FIX per ticket over the last `window` review rows.

    Rows are appended by /crew:review as
    `<date> | <ticket> | <reviewer> | <n BLOCK> | <n FIX>`. Leading and
    trailing pipes are tolerated, and any row whose BLOCK/FIX cells are not
    numeric is skipped -- which is how the header and separator rows are
    filtered without hard-coding their text.
    """
    empty = {"tickets": 0, "findings": 0, "rate": None, "verdict": "no data"}
    text = read_text(os.path.join(root, ".crew", "metrics.md"))
    if not text:
        return empty

    totals = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        block, fix = _leading_int(cells[3]), _leading_int(cells[4])
        if block is None or fix is None:
            continue
        totals.append(block + fix)

    recent = totals[-window:]
    if not recent:
        return empty
    findings = sum(recent)
    rate = findings / len(recent)
    return {
        "tickets": len(recent),
        "findings": findings,
        "rate": round(rate, 2),
        "verdict": _verdict(rate),
    }


def read_work(root):
    """The OPEN ticket and whether a handoff is waiting.

    Not simply the first ticket in the file. A real .work/INDEX.md accumulates
    finished tickets above the current one, so taking the first match names a
    ticket that closed weeks ago -- on every session, in the brief, as fact.

    A line is skipped when it carries a done marker; the first line that does
    not wins. A file with no in-progress line yields None rather than a guess,
    because "no ticket open" is a true statement and a stale ticket number is
    not.
    """
    ticket = None
    text = read_text(os.path.join(root, ".work", "INDEX.md"))
    for line in (text or "").splitlines():
        found = _TICKET_RE.search(line)
        if not found:
            continue
        if _DONE_RE.search(line):
            continue
        ticket = found.group(1)
        break
    return {
        "ticket": ticket,
        "handoffPending": os.path.exists(
            os.path.join(root, ".work", "HANDOFF.md")
        ),
    }
