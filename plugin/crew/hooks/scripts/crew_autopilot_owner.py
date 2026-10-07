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
- a phase `WAITING` gives to someone else: `landing` (the land step) is
  skipped; `blocked` (another ticket) goes to `blocked`, counted, never listed --
  unless a dependency's state, or the `depends-on:` line, cannot be told: then
  `unknown`, with why;
- a `done` INDEX row is read too: with a `done` spec header it still ships;
- `hold` (L-0687): a hold whose `revisit:` date is still ahead goes to `held`,
  counted, never listed; one that is due, or whose date is missing or does not
  parse (`revisit_due` None: cannot tell is never "not yet"), is listed as
  `revisit` with next.md's `reason:`;
- `needs-owner`: listed with next.md's `next:` line, else the first open
  question, else "cannot tell what is asked (no next: in next.md)";
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
import crew_autopilot_gates
import crew_autopilot_stops
import crew_ticket
import crew_ticket_state

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
    """What the owner types or answers for one stop. A stop that could not tell
    (decision `look`: no INDEX row, rows that disagree) names the status read,
    whose reason says what to fix, never a command that would hide it."""
    phase = result["phase"]
    if result.get("decision") == "look":
        return FALLBACK.format(id=ticket)
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
    """`(tickets, why)`: open INDEX tickets, then folders no INDEX line names
    (compared case-folded: one folder on a case-insensitive filesystem is one
    ticket); `why` when `.work/tickets/` exists and cannot be listed."""
    found = list(crew_autopilot.open_index_tickets(top))
    # A `done` row whose spec header is `done` too still ships (`_phase`'s ship rows).
    found += [ticket for ticket, _line in crew_autopilot._index_rows(top)  # pylint: disable=protected-access
              if ticket not in found and crew_autopilot._index_status(top, ticket) == "done"  # pylint: disable=protected-access
              and os.path.isdir(crew_ticket.ticket_dir(top, ticket))]
    seen = {ticket.casefold() for ticket in found} | {
        ticket.casefold() for ticket, _line in crew_autopilot._index_rows(top)}  # pylint: disable=protected-access
    folder = os.path.join(top, ".work", "tickets")
    try:
        names = sorted(os.listdir(folder)) if os.path.lexists(folder) else []
    except OSError as exc:
        return found, f"could not list .work/tickets/ ({exc.strerror or exc})"
    for name in names:
        try:
            crew_ticket.check_ticket(name)
        except crew_ticket.TicketError:
            continue
        if name.casefold() not in seen and os.path.isdir(os.path.join(folder, name)):
            seen.add(name.casefold())
            found.append(name)
    return found, ""


def _unread_next(view):
    """next.md's read or parse problems, joined, or '' (an absent field is known
    only when the file read cleanly)."""
    return "; ".join(p for p in view["problems"] if p.startswith("next.md"))


def _hold(view):
    """`("held", "")` for a hold whose date is still ahead, else `("revisit", action)`."""
    if view["revisit_due"] is False:
        return "held", ""
    fields, unread = view["next"], _unread_next(view)
    date = (f"revisit {fields['revisit']} (due)" if view["revisit_due"]
            else "revisit date: cannot tell")
    reason = fields["reason"] or (f"cannot tell ({unread})" if unread else "no reason given")
    return "revisit", f"{date}; reason: {reason} - lift or keep the hold"


def _needs_owner(view, questions):
    if view["next"]["next"]:
        return f"next: {view['next']['next']}"
    if questions:
        return f"answer: {questions[0][0]}: {questions[0][1]}"
    unread = _unread_next(view)
    return (f"cannot tell what is asked ({unread})" if unread
            else "cannot tell what is asked (no next: in next.md)")


def _blocked(view):
    """'' when every dependency's state was read, else why it cannot be told."""
    if view["blocked"] is None:
        return "; ".join(p for p in view["problems"] if p.startswith("depends-on:")) or \
            "the depends-on: line cannot be read"
    unknown = [d["id"] for d in view["dependencies"] if d["state"] == "unknown"]
    return f"cannot tell whether {', '.join(unknown)} is closed" if unknown else ""


def owner_items(root, today=None):
    """`{"state": "ok"|"unknown", "why", "items": [(ticket, phase, action)],
    "unread": [ticket], "held": [ticket], "blocked": [ticket], "unknown": [(ticket,
    why)]}`; see the module docstring. `today` decides a hold's `revisit_due`."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    got = {"state": "ok", "why": "", "items": [], "unread": [], "held": [], "blocked": [],
           "unknown": []}
    why = _index_problem(top)
    tickets, listing = _tickets(top) if not why else ([], "")
    if why or listing:
        return dict(got, state="unknown", why=why or listing)
    for ticket in tickets:
        try:
            result = crew_autopilot._phase(top, ticket, policy=False, deep=False)  # pylint: disable=protected-access
            if not result["stop"] or result["phase"] == "closed":
                continue
            if result["phase"] == crew_autopilot_stops.UNREAD:
                got["unread"].append(ticket)
                continue
            if result["phase"] == "review" and crew_autopilot._reserved_round(top, ticket):  # pylint: disable=protected-access
                continue
            if result["phase"] == "blocked":
                why = _blocked(crew_ticket_state.view(top, ticket, today))
                got["unknown" if why else "blocked"].append((ticket, why) if why else ticket)
                continue
            if crew_autopilot.WAITING.get(result["phase"]) in crew_autopilot_gates.ELSEWHERE:
                continue  # landing: the land step, not the owner
            questions = (crew_autopilot._open_questions(crew_ticket.ticket_dir(top, ticket))  # pylint: disable=protected-access
                         if result["phase"] in ("open-questions", "needs-owner") else [])
            if result["phase"] in ("hold", "needs-owner"):
                view = crew_ticket_state.view(top, ticket, today)
                phase, said = (_hold(view) if result["phase"] == "hold"
                               else ("needs-owner", _needs_owner(view, questions)))
                if phase == "held":
                    got["held"].append(ticket)
                else:
                    got["items"].append((ticket, phase, said))
                continue
            got["items"].append((ticket, result["phase"], action(ticket, result, questions)))
        except Exception as exc:  # pylint: disable=broad-except
            got["unknown"].append((ticket, type(exc).__name__))
    return got
