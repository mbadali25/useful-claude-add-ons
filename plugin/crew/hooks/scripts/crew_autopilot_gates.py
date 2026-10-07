#!/usr/bin/env python3
"""L-0550: autopilot stops on hold, landing, needs-owner, cancelled/superseded
and blocked.

`crew_autopilot._phase` asks `crew_ticket_state.view` once (L-0639, L-0640),
right after its INDEX `done` branch and before the direction-approval test
(`gate`), and checks the dependencies it returned immediately before the
review phase (`blocked`). Nothing here writes a file or a status: autopilot
never sets or lifts a gate.

- A gate of `hold`, `landing` or `needs-owner` stops as that phase, from the
  INDEX status cell autopilot already read (this checkout's or the main
  checkout's row), else from the spec header as `view` reads it. The INDEX cell
  wins, as `view` reads it.
- A header `cancelled` or `superseded` stops as `closed` and names the
  successor (`successor`): the line under the spec header, else next.md's
  `superseded-by:`, else "successor not named".
- A gate `view` cannot tell (`unknown`: INDEX.md unreadable, or two of its rows
  for the ticket disagree) stops as `direction-approval`, quoting why -- never
  "no gate".
- `blocked`: an approved ticket whose `depends-on:` names a ticket that is not
  closed (`open`, `unknown`, `cancelled`, `superseded`), or whose `depends-on:`
  line cannot be read, stops before implement, review and done, and before a
  `ship` or `next-slice` that would act (`before_ship`). A blocked
  ticket still gets its spec and plan. The review-ledger problems `view`
  reports are not read here: `_review_phase` reads the ledger itself.
- `revisit:` never lifts a hold. It is printed, with "(passed)" once due.

No `try` around `view`: a crash reaches `next`'s boundary and prints `stop=1`,
never "no gate". Standard library and crew modules only; imports nothing from
crew_autopilot.
"""

from __future__ import annotations

import os
import re

import crew_common
import crew_ticket_state

GATES = ("hold", "landing", "needs-owner")
CLOSING = crew_ticket_state.CLOSING_STATUSES
CANNOT_TELL = crew_ticket_state.CANNOT_TELL
NEEDS_OWNER = "needs-owner"
NO_SUCCESSOR = " (successor not named)"

# Appended to crew_autopilot.FIXED_STOPS.
FIXED_STOPS = (
    ("hold", "the INDEX status cell or spec header says `hold`: only the owner lifts it, "
             "whatever next.md's `revisit:` says"),
    ("landing", "the INDEX status cell or spec header says `landing`: the land step owns "
                "the ticket, even with a current receipt"),
    ("needs-owner", "the INDEX status cell or spec header says `needs-owner`: it waits on "
                    "the owner's answer to next.md's `next:` or its open questions"),
    ("blocked", "approved, and a `depends-on:` ticket is not closed or cannot be told, or "
                "the `depends-on:` line cannot be read"),
)
# Added to crew_autopilot.WAITING. Neither is ever `autopilot`.
WAITING = {"hold": "owner", NEEDS_OWNER: "owner", "landing": "the land step",
           "blocked": "another ticket"}
# Who `_waiting` names with no owner command: someone other than the owner.
ELSEWHERE = ("the land step", "another ticket")
# Marks a header gate read under an INDEX cell autopilot does not know (L-0666 review r4).
UNKNOWN_CELL = "is not one autopilot knows"


def waiting(who, result):
    """`/crew:autopilot status`'s `waiting on:` for a stop WAITING gives to someone
    else. A `blocked` stop whose dependencies cannot be told waits on the owner,
    who reads the depends-on: line: never "another ticket" (L-0550 review r6)."""
    reason = result.get("reason") or ""
    if result.get("phase") == "blocked" and (CANNOT_TELL in reason or "can be told" in reason):
        return "owner - cannot tell the dependencies: see the phase reason"
    return f"{who} - see the phase reason"

# The line under a closed spec's header naming what replaced it (T-0037,
# T-0052): `split-into: T-2, T-3` or `superseded-by: T-9`.
_SUCCESSOR = re.compile(r"^(?:split-into|superseded-by)\s*:\s*\S.*$", re.IGNORECASE)


def _rel(top, path):
    """`path` relative to `top` with '/' separators, or `path` itself when
    there is no relative form (another drive on Windows)."""
    try:
        return os.path.relpath(path, top).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def _names_ids(line, ticket):
    """Whether a `split-into:`/`superseded-by:` line names only ticket ids, none
    of them `ticket` itself (`crew_ticket_state`'s rule: `TBD` names none)."""
    value = crew_ticket_state._unbracket(line.split(":", 1)[1].strip())  # pylint: disable=protected-access
    ids = [part.strip().strip("`") for part in value.split(",")]
    return all(crew_ticket_state._is_ticket_id(item)  # pylint: disable=protected-access
               and item.casefold() != ticket.casefold() for item in ids)


def successor(folder, word=None, fields=None, problems=None):
    """` (split-into: ...)` from spec.md's lines above its first `##`; else,
    for `superseded`, next.md's ` (superseded-by: T-9, from next.md)`, a
    could-not-tell naming next.md's problem, or NO_SUCCESSOR; else ''. `fields`
    and `problems` are next.md as `view` read it (read here when None)."""
    spec = os.path.join(folder, "spec.md")
    text = crew_common.read_text(spec)
    if text is None and os.path.lexists(spec):  # L-0550 review r5: unreadable is not "none named"
        return " (successor: cannot tell - spec.md could not be read)"
    for line in (text or "").splitlines()[1:]:
        if line.startswith("##"):
            break
        if _SUCCESSOR.match(line.strip()) and _names_ids(line, os.path.basename(folder)):
            return f" ({line.strip()})"
    if word != "superseded":
        return ""
    if fields is None:
        fields, problems = crew_ticket_state.read_next(folder)
    if fields.get("superseded-by"):
        return f" (superseded-by: {fields['superseded-by']}, from next.md)"
    unread = [p for p in problems or [] if p.startswith("next.md")]
    if unread:
        return f" (successor: cannot tell - {'; '.join(unread)})"
    return NO_SUCCESSOR


def _next_problems(view):
    return [p for p in view["problems"] if p.startswith("next.md")]


def _hold_reason(view):
    fields, due = view["next"], view["revisit_due"]
    reason = f"reason: {fields['reason']}" if fields["reason"] else "no reason given"
    revisit = (f"revisit: {fields['revisit']}" + (" (passed)" if due else "")
               if fields["revisit"] else "no revisit date")
    return (f"on hold - {reason}; {revisit}. Only the owner lifts a hold, by editing the "
            "status; a revisit date never does")


def _needs_owner_reason(view, questions):
    asked = [f"next: {view['next']['next']}"] if view["next"]["next"] else []
    asked += [f"{name}: {item}" for name, item in questions[:4]]
    if not asked:
        return ("it waits on an owner decision - cannot tell what is asked (no next: in "
                "next.md) and no open question recorded - the owner says what is needed")
    return "it waits on an owner decision - " + "; ".join(asked)


def gate(top, ticket, index_status, folder, known, questions, answer, evidence):
    """`(stop, view)`: the gate stop `answer` builds, or None, and the view
    `blocked` reads later. `index_status` is the INDEX cell `_phase` read;
    `known` whether it is one autopilot knows (a header gate under an unknown
    cell stops as the header says, with decision `look`: the cell is not read
    as approval); `questions` a callable giving `_open_questions(folder)`."""
    view = crew_ticket_state.view(top, ticket)
    nxt = os.path.join(folder, "next.md")
    if os.path.lexists(nxt):
        evidence.append(_rel(top, nxt))
    if view["gate"] == "unknown":  # before the INDEX cell: the first of two disagreeing rows is no gate
        why = [p for p in view["problems"] if p.startswith("gate:")]
        return answer("direction-approval", True, f"cannot tell whether a gate ({', '.join(GATES)}, "
                      f"{', '.join(CLOSING)}) holds {ticket}: " + ("; ".join(why) or "unknown")
                      + " - the human makes .work/INDEX.md say one status for it", decision="look"), view
    if index_status in GATES:
        word, where = index_status, f".work/INDEX.md marks {ticket} `{index_status}`"
    elif view["gate"] and view["gate_source"] == "header":
        word, where = view["gate"], f"spec.md header is `status: {view['gate']}`"
        if not known:  # L-0666 review r4: an unknown INDEX cell keeps the stop could-not-tell
            where += f" (and its .work/INDEX.md status `{index_status}` {UNKNOWN_CELL})"
    else:
        return None, view
    unknown_cell = None if known or word == index_status else "look"
    if word in CLOSING:
        named = successor(folder, word, view["next"], view["problems"])
        return answer("closed", True, f"{where}: nothing left in this ticket" + named,
                      decision=unknown_cell or ("look" if "cannot tell" in named else None)), view
    decision = unknown_cell
    if word == "hold":
        why = _hold_reason(view)
    elif word == "landing":
        why = "accepted; the land step owns it from here, even with a current receipt"
    else:
        asked = questions()
        why = _needs_owner_reason(view, asked)
        unread = bool(_next_problems(view)) and not view["next"]["next"]  # L-0666 r6: next.md unread
        decision = unknown_cell or (None if (asked or view["next"]["next"]) and not unread else "look")
    problems = _next_problems(view)
    if problems:
        why += " (next.md: cannot tell - " + "; ".join(problems) + ")"
    return answer(word, True, f"{where}: {why}", decision=decision), view


def ship_hold(top, ticket):
    """`(phase, reason)` when nothing may ship now, or None: a gate is set or
    cannot be told, or a dependency is not closed or cannot be told. Read
    again by `before_ship` and on every poll of `ship`'s CI wait
    (`crew_autopilot._ship_gate`), so a hold set during the wait stops it."""
    view = crew_ticket_state.view(top, ticket)
    if view["gate"] == "unknown":
        why = [p for p in view["problems"] if p.startswith("gate:")]
        return "direction-approval", (f"cannot tell whether a gate holds {ticket}: "
                                      + ("; ".join(why) or "unknown") + " - nothing ships")
    if view["gate"]:
        where = ".work/INDEX.md" if view["gate_source"] == "index" else "spec.md's header"
        return (view["gate"] if view["gate"] in GATES else "closed",
                f"{where} says `{view['gate']}` for {ticket} - nothing ships until the owner "
                "changes it")
    return blocked(view, lambda phase, _stop, reason: (phase, reason))


def hold_reason(top, ticket, row):
    """Why nothing may merge now, or None: `ship`'s CI wait (every poll) and the
    last look before `gh pr merge` ask it. `row` is `crew_autopilot._index_row`:
    this checkout's INDEX row and the main checkout's, so a hold set in either
    stops the merge; rows that disagree, or a main checkout that could not be
    read, are could-not-tell. Then `ship_hold`."""
    if row.get("other"):
        (here, mine), (main, theirs) = row["other"]
        return (f"{here} says `{mine}` and {main} says `{theirs}` for {ticket}: cannot tell "
                "whether a gate holds it - nothing ships")
    if row.get("status") in GATES + CLOSING:
        return (f"{row.get('source') or '.work/INDEX.md'} says `{row['status']}` for {ticket} - "
                "nothing ships until the owner changes it")
    if row.get("why"):
        return f"cannot tell whether the main checkout holds {ticket}: {row['why']} - nothing ships"
    held = ship_hold(top, ticket)
    return held[1] if held else None


def before_ship(top, ticket, answer, found):
    """`found` from `_ship_phase`, unless it would act (stop=0: `ship` or
    `next-slice`) while `ship_hold` says nothing ships. A stop (`closed`
    included) is returned as it is."""
    if found["stop"]:
        return found
    held = ship_hold(top, ticket)
    if not held:
        return found
    return answer(held[0], True, held[1], decision="look" if held[0] == "direction-approval" else None)


def blocked(view, answer):
    """The `blocked` stop, or None: a `depends-on:` ticket not closed, or a
    `depends-on:` line that cannot be read (`view["blocked"]` None)."""
    if view["blocked"] is None:
        why = [p for p in view["problems"] if p.startswith("depends-on:")]
        return answer("blocked", True, f"{view['ticket']}'s dependencies: "
                      + ("; ".join(why) or "cannot tell") + " - it waits until they can be told")
    open_deps = [d for d in view["dependencies"] if d["state"] != "closed"]
    if not open_deps:
        return None
    return answer("blocked", True, f"{view['ticket']} depends on "
                  + "; ".join(f"{d['id']} ({d['state']}: {d['reason']})" for d in open_deps)
                  + " - it continues once each is closed")
