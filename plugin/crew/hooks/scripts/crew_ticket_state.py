#!/usr/bin/env python3
"""crew_ticket_state.py -- derived ticket statuses, read-only (L-0639, L-0640).

One question per call, for one ticket, and nothing acts on the answer yet
(L-0550's autopilot stops and L-0551's owner list are the consumers):

    dependency_state(top, dep)   -> (state, reason); state is one of
                                    closed | open | unknown | cancelled |
                                    superseded. Every state but `closed`
                                    blocks the ticket that depends on it.
    parse_depends_on(spec_text)  -> (ids, problem): the optional
                                    `depends-on: T-1, T-2` line under the
                                    spec header; ([], None) when absent.
    read_next(folder)            -> (fields, problems) from the ticket
                                    folder's optional next.md (L-0640).
    view(top, ticket, today=None) -> {"ticket", "gate", "gate_source",
                                    "depends_on", "dependencies", "blocked",
                                    "needs_replan", "derived", "next",
                                    "revisit_due", "problems"}

`blocked` and `needs-replan` are DERIVED, never typed: `blocked` from the
`depends-on:` line and each dependency's state, `needs-replan` from the review
ledger. A typed `blocked` or `needs-replan` INDEX cell is reported in
`problems`, never obeyed. The gating statuses (`GATING_STATUSES`) are read
from the ticket's INDEX status cell first, then its spec header.

An unknown never collapses into the safe value: a dependency whose state
cannot be read is `unknown` (and blocks), `blocked` is None when the
`depends-on:` line cannot be read (no spec, or an unreadable one), `gate` is
`unknown` when INDEX.md cannot be read or two of its rows for the ticket
disagree, and `needs_replan` is None, with a
`problems` entry, when the ledger cannot be read -- never False.

`done` counts as closed (approved 2026-09-26), like `merged`. Order for one
dependency: a row that a prose INDEX line contradicts is `unknown` (a closing
row must be marked with its own word, a done row `done`, an open row not at
all); then its INDEX status cell, a closing word (`cancelled`, `superseded`)
returned as itself before any closed-word test; then
`crew_ticket._index_closed` (None is `unknown` with its why); prose lines
that mark it two ways are `unknown`, one closing word is that word; with no
INDEX row, the dependency's spec header (`done`/`merged` closed, a closing word
named, anything else or no spec `unknown`).

next.md (L-0640) is local state nothing in crew writes: one `key: value` per
line, key case-insensitive, blank and `#` lines skipped, unknown keys ignored.
`waiting-on` is owner | agent | external | a ticket id, `revisit` is
YYYY-MM-DD, `superseded-by` a ticket id, `next` and `reason` free text clipped
to NEXT_TEXT_MAX. A bad, empty or repeated value is a problem and that field
is None; a next.md that cannot be read (or resolves outside the ticket folder)
is a problem and every field is None -- cannot tell, never "nothing asked".
`revisit_due` is True on or after the date, False before it, None without one.
It is not part of the contract: the approval digest never reads it.

Writes no file and starts no process of its own; the ledger read goes
through `review_ledger.status`, which asks git for the common dir.
"""
from __future__ import annotations

import datetime
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

# next.md (L-0640).
NEXT_KEYS = ("waiting-on", "next", "reason", "revisit", "superseded-by")
WAITING_ON_WORDS = ("owner", "agent", "external")
NEXT_TEXT_MAX = 200
NEEDS_OWNER_NO_NEXT = "needs-owner: cannot tell what is asked (no next: in next.md)"
SUPERSEDED_NO_SUCCESSOR = ("superseded: cannot tell what replaced it (no superseded-by: in "
                           "next.md, and no split-into: or superseded-by: line under the spec header)")

_NEXT_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$")
_REVISIT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# The successor line under a spec header (T-0037, T-0052; crew_autopilot._SUCCESSOR).
_SPEC_SUCCESSOR_RE = re.compile(r"^(?:split-into|superseded-by)\s*:\s*(.*?)\s*$", re.IGNORECASE)
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
    ('' when the row has none); `why` set when INDEX.md cannot be read, or when
    two rows name it with different status cells (cannot tell which holds;
    `crew_ticket._index_closed` would read a later done row as closed). The id
    matching is `crew_ticket._index_closed`'s."""
    path = os.path.join(top, ".work", "INDEX.md")
    text = crew_common.read_text(path)
    if text is None:
        if os.path.lexists(path):
            return False, None, f"could not read {_rel_index()}"
        return False, None, None
    key, seen = ticket.casefold(), []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.count("|") < 2 and not (line.count("|") == 1 and crew_ticket._cell_id(cells[0])):  # pylint: disable=protected-access
            continue
        ids = [(i, crew_ticket._cell_id(c)) for i, c in enumerate(cells)  # pylint: disable=protected-access
               if crew_ticket._cell_id(c)]  # pylint: disable=protected-access
        if ids and ids[0][1] == key:
            at = ids[0][0] + 1
            cell = cells[at].lower() if at < len(cells) else ""
            if cell not in seen:
                seen.append(cell)
    if len(seen) > 1:
        return True, None, (f"{_rel_index()} has rows for {ticket} that disagree: "
                            + ", ".join(f"`{c}`" for c in seen))
    return (True, seen[0], None) if seen else (False, None, None)


# A closing word after a `[x]` or `~~` marker: `crew_state._DONE_RE` matches
# only the marker there, so `- [x] Cancelled: T-1` must still read `cancelled`.
_CLOSING_PROSE_RE = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])?\s*(?:(?:\[x\]|~~)\s*)*(cancelled|superseded)\s*:", re.IGNORECASE)


def _prose_marks(top, ticket):
    """The set of marks the prose INDEX.md lines closing `ticket` by
    `crew_state._DONE_RE` give it -- the lines `crew_ticket._index_closed`
    reads as closed: the closing word (`cancelled`/`superseded`) a line names,
    after any `[x]`/`~~` marker, else `done`. Empty when no prose line closes
    it. A dependency closed by a closing word never closed as done, so it must
    not read `closed`."""
    text = crew_common.read_text(os.path.join(top, ".work", "INDEX.md")) or ""
    key, marks = ticket.casefold(), set()
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.count("|") >= 2 or (line.count("|") == 1 and crew_ticket._cell_id(cells[0])):  # pylint: disable=protected-access
            continue
        if crew_state._DONE_RE.search(line) and crew_ticket._prose_names(line, key):  # pylint: disable=protected-access
            closing = _CLOSING_PROSE_RE.match(line)
            marks.add(closing.group(1).lower() if closing else "done")
    return marks


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
    marks = _prose_marks(top, dep)
    if found and marks:
        agree = {cell} if cell in CLOSING_STATUSES else (
            {"done"} if cell in crew_state._TABLE_DONE_WORDS else set())  # pylint: disable=protected-access
        if marks != agree:
            return "unknown", (f"{CANNOT_TELL} whether {dep} is closed: its {_rel_index()} row "
                               f"says `{cell}` and a prose line there marks it "
                               f"{' and '.join(sorted(marks - agree))}")
    if found and cell in CLOSING_STATUSES:
        return cell, f"{dep} is {cell} in {_rel_index()}: it will never close as done"
    closed, why = crew_ticket._index_closed(top, dep)  # pylint: disable=protected-access
    if closed is None:
        return "unknown", f"{CANNOT_TELL} whether {dep} is closed: {why}"
    if len(marks) > 1:
        return "unknown", (f"{CANNOT_TELL} whether {dep} is closed: prose lines in "
                           f"{_rel_index()} mark it {' and '.join(sorted(marks))}")
    word = next((w for w in CLOSING_STATUSES if w in marks), None)
    if word:
        return word, f"a prose line in {_rel_index()} marks {dep} {word}: it will never close as done"
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


def _is_ticket_id(value):
    """A plain ticket id (`crew_ticket.check_ticket`) with a letter and a digit,
    the INDEX id shape (`crew_ticket._cell_id`): check_ticket alone accepts any
    word, so `waiting-on: someone` would read as a ticket id."""
    try:
        crew_ticket.check_ticket(value)
    except crew_ticket.TicketError:
        return False
    return bool(re.search(r"[A-Za-z]", value) and re.search(r"\d", value))


def _next_value(key, value):
    """`(value, problem)` for one known next.md key; value None on a problem."""
    if value == "":
        return None, f"next.md: {key}: is empty"
    if key == "waiting-on":
        if value.lower() in WAITING_ON_WORDS:
            return value.lower(), None
        if _is_ticket_id(value):
            return value, None
        return None, (f"next.md: waiting-on: {value!r} is not one of "
                      f"{', '.join(WAITING_ON_WORDS)} or a ticket id")
    if key == "revisit":
        try:
            if not _REVISIT_RE.match(value):
                raise ValueError(value)
            datetime.date.fromisoformat(value)
        except ValueError:
            return None, f"next.md: revisit: {value!r} is not a YYYY-MM-DD date"
        return value, None
    if key == "superseded-by":
        if _is_ticket_id(value):
            return value, None
        return None, f"next.md: superseded-by: {value!r} is not a ticket id"
    return value[:NEXT_TEXT_MAX], None


def read_next(folder):
    """`(fields, problems)` from `folder`/next.md; see the module docstring.
    `fields` has every key of NEXT_KEYS, None when unset. Reads only."""
    fields = dict.fromkeys(NEXT_KEYS)
    path = os.path.join(folder, "next.md")
    if not os.path.lexists(path):
        return fields, []
    home, real = os.path.realpath(folder), os.path.realpath(path)
    try:
        inside = os.path.commonpath([home, real]) == home
    except ValueError:
        inside = False
    if not inside:
        return fields, [f"next.md: {CANNOT_TELL}, it resolves outside the ticket folder "
                        "and is not read"]
    try:
        with open(path, "rb") as handle:
            text = handle.read().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return fields, [f"next.md: {CANNOT_TELL}, it could not be read ({exc})"]
    problems, seen, repeated = [], {}, []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _NEXT_LINE_RE.match(line)
        if match is None:
            problems.append(f"next.md line {number}: not a `key: value` line")
            continue
        key = match.group(1).lower()
        if key not in NEXT_KEYS:
            continue
        if key in seen:
            if key not in repeated:
                repeated.append(key)
            continue
        seen[key] = match.group(2)
    for key in repeated:
        problems.append(f"next.md: {key}: given more than once, so it is unset")
    for key, raw in seen.items():
        if key in repeated:
            continue
        fields[key], problem = _next_value(key, raw)
        if problem:
            problems.append(problem)
    return fields, problems


def _spec_names_successor(spec_text):
    """True when a `split-into:`/`superseded-by:` line above the first `##`
    names only ticket ids (`[T-2, T-3]` or `T-2, T-3`); `TBD` names none."""
    for line in (spec_text or "").splitlines()[1:]:
        if line.startswith("##"):
            break
        match = _SPEC_SUCCESSOR_RE.match(line.strip())
        if match:
            value = match.group(1).strip().strip("[]")
            ids = [part.strip().strip("`") for part in value.split(",")]
            if ids and all(_is_ticket_id(item) for item in ids):
                return True
    return False


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


def view(top, ticket, today=None):
    """The derived statuses of one ticket. Read-only; see the module docstring.
    `today` (a datetime.date, default the local date) decides `revisit_due`."""
    crew_ticket.check_ticket(ticket)
    today = today or datetime.date.today()
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
    fields, next_problems = read_next(crew_ticket.ticket_dir(top, ticket))
    problems.extend(next_problems)
    revisit_due = (None if fields["revisit"] is None
                   else datetime.date.fromisoformat(fields["revisit"]) <= today)
    if gate == "needs-owner" and fields["next"] is None:
        problems.append(NEEDS_OWNER_NO_NEXT)
    if gate == "superseded" and fields["superseded-by"] is None \
            and not _spec_names_successor(text):
        problems.append(SUPERSEDED_NO_SUCCESSOR)
    derived = [name for name, on in (("blocked", blocked), ("needs-replan", needs_replan)) if on]
    return {"ticket": ticket, "gate": gate, "gate_source": source, "depends_on": ids,
            "dependencies": dependencies, "blocked": blocked, "needs_replan": needs_replan,
            "derived": derived, "next": fields, "revisit_due": revisit_due,
            "problems": problems}
