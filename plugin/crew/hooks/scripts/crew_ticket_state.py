#!/usr/bin/env python3
"""crew_ticket_state.py -- derived ticket statuses, read-only (L-0639).

One question per call, for one ticket, and nothing acts on the answer yet
(L-0550's autopilot stops and L-0551's owner list are the consumers):

    dependency_state(top, dep)   -> (state, reason); state is one of
                                    closed | open | unknown | cancelled |
                                    superseded. Every state but `closed`
                                    blocks the ticket that depends on it.
    parse_depends_on(spec_text)  -> (ids, problem): the optional
                                    `depends-on: T-1, T-2` line under the
                                    spec header; ([], None) when absent.
    view(top, ticket)            -> {"ticket", "gate", "gate_source",
                                    "depends_on", "dependencies", "blocked",
                                    "needs_replan", "derived", "problems"}

`blocked` and `needs-replan` are DERIVED, never typed: `blocked` from the
`depends-on:` line and each dependency's state, `needs-replan` from the review
ledger. A typed `blocked` or `needs-replan` INDEX cell is reported in
`problems`, never obeyed. The gating statuses (`GATING_STATUSES`) are read
from the ticket's INDEX status cell first, then its spec header.

An unknown never collapses into the safe value: a dependency whose state
cannot be read is `unknown` (and blocks), `blocked` is None when the
`depends-on:` line cannot be read (no spec, or an unreadable one), `gate` is
`unknown` when INDEX.md cannot be read, and `needs_replan` is None, with a
`problems` entry, when the ledger cannot be read -- never False.

`done` counts as closed (approved 2026-09-26), like `merged`. Order for one
dependency: its INDEX status cell; a closing word (`cancelled`,
`superseded`) is returned as itself before any closed-word test; then
`crew_ticket._index_closed` (None is `unknown` with its why); with no INDEX
row, the dependency's spec header (`done`/`merged` closed, a closing word
named, anything else or no spec `unknown`).

Writes no file and starts no process of its own; the ledger read goes
through `review_ledger.status`, which asks git for the common dir.
"""
from __future__ import annotations

import os
import re

import crew_common
import crew_state
import crew_ticket
import review_ledger

# crew_tracker.CLOSED_STATUSES (T-0037), pinned equal by test_ticket_state.py.
CLOSING_STATUSES = ("cancelled", "superseded")
DERIVED_STATUSES = ("blocked", "needs-replan")
GATING_STATUSES = ("hold", "landing", "needs-owner") + CLOSING_STATUSES
# A dependency's spec header that says it is finished, when it has no INDEX row.
HEADER_CLOSED = ("done", "merged")
CANNOT_TELL = "cannot tell"
# Ledger states that say "no replan": `EMPTY` is `review_ledger.summary`'s word
# for a ledger with no state yet. Any other word but NEEDS_REPLAN cannot tell.
LEDGER_NOT_REPLAN = ("EMPTY", review_ledger.IN_REVIEW, review_ledger.REVIEWED,
                     review_ledger.ACCEPTED)

# The header's field block: the `key: value` pairs that end line 1, set off
# from the title by the template's column gap (two or more spaces, or a tab).
_FIELD_BLOCK_RE = re.compile(r"(?:\s{2,}|\t)((?:[A-Za-z][\w-]*:[ \t]*\S+[ \t]*)+)$")
_STATUS_FIELD_RE = re.compile(r"(?:^|\s)status:\s*(\S+)", re.IGNORECASE)
_DEPENDS_RE = re.compile(r"^depends-on:\s*(.*?)\s*$", re.IGNORECASE)


def _rel_index():
    return os.path.join(".work", "INDEX.md")


def _index_cell(top, ticket):
    """`(found, cell, why)` for `ticket`'s INDEX.md table row: `found` False
    when no row names it as its id cell; `cell` the lower-cased status cell
    ('' when the row has none); `why` set when INDEX.md cannot be read. The id
    matching is `crew_ticket._index_closed`'s, so the two read one row."""
    path = os.path.join(top, ".work", "INDEX.md")
    text = crew_common.read_text(path)
    if text is None:
        if os.path.lexists(path):
            return False, None, f"could not read {_rel_index()}"
        return False, None, None
    key = ticket.casefold()
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.count("|") < 2 and not (line.count("|") == 1 and crew_ticket._cell_id(cells[0])):  # pylint: disable=protected-access
            continue
        ids = [(i, crew_ticket._cell_id(c)) for i, c in enumerate(cells)  # pylint: disable=protected-access
               if crew_ticket._cell_id(c)]  # pylint: disable=protected-access
        if ids and ids[0][1] == key:
            at = ids[0][0] + 1
            return True, (cells[at].lower() if at < len(cells) else ""), None
    return False, None, None


def _prose_closing(top, ticket):
    """The closing word (`cancelled`/`superseded`) of a prose INDEX.md line
    that closes `ticket` by `crew_state._DONE_RE` -- the lines
    `crew_ticket._index_closed` reads as closed -- or None. A dependency closed
    that way never closed as done, so it must not read `closed`."""
    text = crew_common.read_text(os.path.join(top, ".work", "INDEX.md")) or ""
    key = ticket.casefold()
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.count("|") >= 2 or (line.count("|") == 1 and crew_ticket._cell_id(cells[0])):  # pylint: disable=protected-access
            continue
        marker = crew_state._DONE_RE.search(line)  # pylint: disable=protected-access
        if marker and crew_ticket._prose_names(line, key):  # pylint: disable=protected-access
            for word in CLOSING_STATUSES:
                if word in marker.group(0).lower():
                    return word
    return None


def _header_status(spec_text):
    """The `status:` field of the spec's header line, lower-cased, or None.
    Only the field block that ends the line counts (`<title>   status: spec
    risk: low`), so a `status:` in the title is never read as the field; no
    field block, or more than one `status:` in it, is None (cannot tell)."""
    block = _FIELD_BLOCK_RE.search(crew_ticket.header_line(spec_text).rstrip())
    words = [m.lower() for m in _STATUS_FIELD_RE.findall(block.group(1))] if block else []
    return words[0] if len(words) == 1 else None


def _spec(top, ticket):
    """`(text, why)`: the ticket's spec.md text, or None with why (None, None
    when there is no spec)."""
    path = os.path.join(crew_ticket.ticket_dir(top, ticket), "spec.md")
    data = crew_ticket.read_contract(top, ticket)["spec.md"]
    if data is None:
        return None, (f"could not read {ticket}'s spec.md" if os.path.lexists(path) else None)
    return crew_ticket._text(data), None  # pylint: disable=protected-access


def parse_depends_on(spec_text):
    """`(ids, problem)` from the optional `depends-on:` line, which sits under
    the header and before the first `## ` section. `[T-1, T-2]` and `T-1, T-2`
    both read; `none` or an empty value is no dependency. A second line, or an
    entry that is not a plain ticket id, is a problem and `ids` is None."""
    found = None
    for line in (spec_text or "").splitlines():
        if line.startswith("## "):
            break
        match = _DEPENDS_RE.match(line.strip())
        if match is None:
            continue
        if found is not None:
            return None, "spec.md has more than one depends-on: line"
        found = match.group(1)
    if found is None:
        return [], None
    value = found.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if value.strip().lower() in ("", "none"):
        return [], None
    ids = []
    for part in value.split(","):
        item = part.strip().strip("`")
        try:
            crew_ticket.check_ticket(item)
        except crew_ticket.TicketError:
            return None, f"depends-on: entry {part.strip()!r} is not a ticket id"
        if item not in ids:
            ids.append(item)
    return ids, None


def dependency_state(top, dep):
    """`(state, reason)` for one dependency; see the module docstring."""
    try:
        crew_ticket.check_ticket(dep)
    except crew_ticket.TicketError as exc:
        return "unknown", f"{CANNOT_TELL}: {exc}"
    found, cell, why = _index_cell(top, dep)
    if why:
        return "unknown", f"{CANNOT_TELL} whether {dep} is closed: {why}"
    if found and cell in CLOSING_STATUSES:
        return cell, f"{dep} is {cell} in {_rel_index()}: it will never close as done"
    closed, why = crew_ticket._index_closed(top, dep)  # pylint: disable=protected-access
    if closed is None:
        return "unknown", f"{CANNOT_TELL} whether {dep} is closed: {why}"
    word = _prose_closing(top, dep) if closed else None
    if word:
        return word, f"a prose line in {_rel_index()} marks {dep} {word}: it will never close as done"
    if closed and found and cell not in crew_state._TABLE_DONE_WORDS:  # pylint: disable=protected-access
        return "unknown", (f"{CANNOT_TELL} whether {dep} is closed: its {_rel_index()} row says "
                           f"`{cell}` and a prose line there marks it closed")
    if closed:
        return "closed", f"{dep} is {cell or 'closed'} in {_rel_index()}"
    if found:
        return "open", f"{dep} is `{cell}` in {_rel_index()}"
    text, why = _spec(top, dep)
    if text is None:
        return "unknown", (f"{CANNOT_TELL} whether {dep} is closed: "
                           + (why or f"no {_rel_index()} row and no spec.md"))
    header = _header_status(text)
    if header in HEADER_CLOSED:
        return "closed", f"{dep}'s spec header is `status: {header}` (no {_rel_index()} row)"
    if header in CLOSING_STATUSES:
        return header, f"{dep}'s spec header is `status: {header}`: it will never close as done"
    return "unknown", (f"{CANNOT_TELL} whether {dep} is closed: no {_rel_index()} row, and its "
                       f"spec header says `{header or 'nothing'}`")


def _needs_replan(top, ticket, problems):
    try:
        status = review_ledger.status(top, ticket)
    except (review_ledger.LedgerError, OSError, ValueError) as exc:
        problems.append(f"needs-replan: {CANNOT_TELL}, the review ledger could not be read ({exc})")
        return None
    state = status["state"]
    if state == "EMPTY" and status.get("rounds_used"):
        # No state, yet a round was spent: a malformed ledger, never "no replan".
        problems.append(f"needs-replan: {CANNOT_TELL}, the review ledger has no state but "
                        "records review rounds")
        return None
    if state == review_ledger.NEEDS_REPLAN:
        return True
    if state in LEDGER_NOT_REPLAN:
        return False
    problems.append(f"needs-replan: {CANNOT_TELL}, the review ledger "
                    + ("could not be read" if state == review_ledger.UNKNOWN
                       else f"has a state crew does not know ({state!r})"))
    return None


def view(top, ticket):
    """The derived statuses of one ticket. Read-only; see the module docstring."""
    crew_ticket.check_ticket(ticket)
    problems = []
    found, cell, why = _index_cell(top, ticket)
    if why:
        problems.append(f"gate: {CANNOT_TELL}, {why}")
    if found and cell in DERIVED_STATUSES:
        problems.append(f"{_rel_index()} types `{cell}` for {ticket}: a derived status is "
                        "computed, never typed, so the cell is not obeyed")
    text, spec_why = _spec(top, ticket)
    if spec_why:
        problems.append(spec_why)
    gate, source = None, None
    if why:
        # INDEX outranks the header, so an unreadable INDEX leaves the gate unknown.
        gate = "unknown"
    elif found and cell in GATING_STATUSES:
        gate, source = cell, "index"
    elif text is not None and _header_status(text) in GATING_STATUSES:
        gate, source = _header_status(text), "header"
    if text is None:
        ids, problem = None, f"depends-on: {CANNOT_TELL}, " + (spec_why or f"{ticket} has no spec.md")
    else:
        ids, problem = parse_depends_on(text)
    if problem:
        problems.append(problem)
    dependencies = [{"id": dep, "state": state, "reason": reason}
                    for dep in (ids or []) for state, reason in [dependency_state(top, dep)]]
    blocked = None if ids is None else any(d["state"] != "closed" for d in dependencies)
    needs_replan = _needs_replan(top, ticket, problems)
    derived = [name for name, on in (("blocked", blocked), ("needs-replan", needs_replan)) if on]
    return {"ticket": ticket, "gate": gate, "gate_source": source, "depends_on": ids,
            "dependencies": dependencies, "blocked": blocked, "needs_replan": needs_replan,
            "derived": derived, "problems": problems}
