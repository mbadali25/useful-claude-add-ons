#!/usr/bin/env python3
"""L-0551: what waits on the owner, from autopilot's own phase read.

`owner_items(root)` asks `crew_autopilot._phase(top, ticket, policy=False,
deep=False)` about every open ticket, so the list cannot disagree with what
`/crew:autopilot` would do: no approval or questions policy is read, and
`deep=False` stops at `review-unread` before a bundle rebuild or a gh call.
It writes nothing and runs nothing on the owner's behalf.

Tickets, in order: `crew_autopilot.open_index_tickets`, then every folder
under `.work/tickets/` whose name is a ticket id and that no INDEX line names
(listed; its phase is `direction-approval`). Per ticket:

- not a stop, or `closed`: skipped (autopilot drives it, or nobody does);
- `review-unread`: in `unread` (a finished round, or a ship, not read);
- `review` with a reserved round: skipped (the reviewer has it);
- any other stop: an item `(ticket, phase, action)`, the action from
  OWNER_ACTIONS, else FALLBACK;
- `_phase` raising: in `unknown` with the exception's type name, never dropped
  and never counted as "on you".

No `.work/INDEX.md`, or one that cannot be read, is `state: unknown` (Jira and
ServiceDesk Plus modes write no rows, so "nothing waiting" would be a guess).
`crew_status.py` renders it: the `waiting` line and `--owner`.
"""

from __future__ import annotations

import os

import crew_autopilot
import crew_autopilot_stops
import crew_ticket

# The command to type, or the question to answer, per stop phase.
OWNER_ACTIONS = {
    "brainstorm": "/crew:brainstorm {id}",
    "direction-approval": "/crew:brainstorm {id}",
    "approve": "/crew:approve {id}",
    "replan": "/crew:plan {id}, then /crew:approve {id}",
    "accept-review": ("review_ledger.py --accept --ticket {id} --by <owner>, or reject it "
                      "(autopilot.reviewPolicy fix-and-rereview fixes a round with one left)"),
}
FALLBACK = "see /crew:autopilot status {id}"
OWN_COMMAND = ("spec", "plan")  # the phase's own `command`


def action(ticket, result, questions):
    """What the owner types or answers for one stop."""
    phase = result["phase"]
    if phase == "open-questions" and questions:
        name, item = questions[0]
        return f"answer: {name}: {item}"
    if phase in OWN_COMMAND and result.get("command"):
        return result["command"]
    return OWNER_ACTIONS.get(phase, FALLBACK).format(id=ticket)


def _index_problem(top):
    path = os.path.join(top, ".work", "INDEX.md")
    if not os.path.lexists(path):
        return "no .work/INDEX.md"
    if crew_autopilot.read_text(path) is None:
        return "could not read .work/INDEX.md"
    return ""


def _tickets(top):
    """Open INDEX tickets, then folders no INDEX line names."""
    found = list(crew_autopilot.open_index_tickets(top))
    named = {ticket for ticket, _line in crew_autopilot._index_rows(top)}  # pylint: disable=protected-access
    folder = os.path.join(top, ".work", "tickets")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        names = []
    for name in names:
        try:
            crew_ticket.check_ticket(name)
        except crew_ticket.TicketError:
            continue
        if name not in named and name not in found and os.path.isdir(os.path.join(folder, name)):
            found.append(name)
    return found


def owner_items(root):
    """`{"state": "ok"|"unknown", "why", "items": [(ticket, phase, action)],
    "unread": [ticket], "unknown": [(ticket, why)]}`; see the module docstring."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    got = {"state": "ok", "why": "", "items": [], "unread": [], "unknown": []}
    why = _index_problem(top)
    if why:
        return dict(got, state="unknown", why=why)
    for ticket in _tickets(top):
        try:
            result = crew_autopilot._phase(top, ticket, policy=False, deep=False)  # pylint: disable=protected-access
            if not result["stop"] or result["phase"] == "closed":
                continue
            if result["phase"] == crew_autopilot_stops.UNREAD:
                got["unread"].append(ticket)
                continue
            if result["phase"] == "review" and crew_autopilot._reserved_round(top, ticket):  # pylint: disable=protected-access
                continue
            questions = (crew_autopilot._open_questions(crew_ticket.ticket_dir(top, ticket))  # pylint: disable=protected-access
                         if result["phase"] == "open-questions" else [])
            got["items"].append((ticket, result["phase"], action(ticket, result, questions)))
        except Exception as exc:  # pylint: disable=broad-except
            got["unknown"].append((ticket, type(exc).__name__))
    return got
