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


def successor(folder, word=None, fields=None):
    """` (split-into: ...)` from spec.md's lines above its first `##`; else,
    for `superseded`, next.md's ` (superseded-by: T-9, from next.md)` or
    NO_SUCCESSOR; else ''. `fields` is next.md as `view` read it (read here
    when None and needed)."""
    for line in (crew_common.read_text(os.path.join(folder, "spec.md")) or "").splitlines()[1:]:
        if line.startswith("##"):
            break
        if _SUCCESSOR.match(line.strip()):
            return f" ({line.strip()})"
    if word != "superseded":
        return ""
    if fields is None:
        fields = crew_ticket_state.read_next(folder)[0]
    if fields.get("superseded-by"):
        return f" (superseded-by: {fields['superseded-by']}, from next.md)"
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


def gate(top, ticket, index_status, folder, questions, answer, evidence):
    """`(stop, view)`: the gate stop `answer` builds, or None, and the view
    `blocked` reads later. `index_status` is the INDEX cell `_phase` read;
    `questions` a callable giving `_open_questions(folder)`."""
    view = crew_ticket_state.view(top, ticket)
    nxt = os.path.join(folder, "next.md")
    if os.path.lexists(nxt):
        evidence.append(_rel(top, nxt))
    if view["gate"] == "unknown":  # before the INDEX cell: the first of two disagreeing rows is no gate
        why = [p for p in view["problems"] if p.startswith("gate:")]
        return answer("direction-approval", True, f"cannot tell whether a gate ({', '.join(GATES)}, "
                      f"{', '.join(CLOSING)}) holds {ticket}: " + ("; ".join(why) or "unknown")
                      + " - the human makes .work/INDEX.md say one status for it"), view
    if index_status in GATES:
        word, where = index_status, f".work/INDEX.md marks {ticket} `{index_status}`"
    elif view["gate"] and view["gate_source"] == "header":
        word, where = view["gate"], f"spec.md header is `status: {view['gate']}`"
    else:
        return None, view
    if word in CLOSING:
        return answer("closed", True, f"{where}: nothing left in this ticket"
                      + successor(folder, word, view["next"])), view
    if word == "hold":
        why = _hold_reason(view)
    elif word == "landing":
        why = "accepted; the land step owns it from here, even with a current receipt"
    else:
        why = _needs_owner_reason(view, questions())
    problems = _next_problems(view)
    if problems:
        why += " (next.md: cannot tell - " + "; ".join(problems) + ")"
    return answer(word, True, f"{where}: {why}"), view


def before_ship(top, ticket, answer, found):
    """`found` from `_ship_phase`, unless it would act (stop=0: `ship` or
    `next-slice`) while a dependency is not closed or cannot be told: then the
    `blocked` stop. A stop (`closed` included) is returned as it is."""
    if found["stop"]:
        return found
    return blocked(crew_ticket_state.view(top, ticket), answer) or found


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
