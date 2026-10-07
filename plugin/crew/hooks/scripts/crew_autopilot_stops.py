#!/usr/bin/env python3
"""L-0666: every autopilot stop names the owner decision it asks for, and never
hands the owner a mechanical step.

- OWNER_DECISIONS: the closed list `(id, what the owner decides, commands)`.
  Every stop `next` returns carries `decision`, one of these ids: `_phase`'s
  `answer` sets it from the phase (`BY_PHASE`, else `look`) unless the site
  names one, and `next_phase`'s guard stops name theirs. A stop's `command` is
  empty or one of its decision's commands (`commands`).
- MECHANICAL: command shapes no stop reason may hand the owner -- a refresh, a
  graph build, a review round within budget, a crew helper. Autopilot runs
  those itself; a stop that cannot is `look`, and says what could not be told.
- `refresh_reason`: the refresh check's answer as a reason. Only the non-stop
  `refresh` phase carries each artifact's `(refresh: <command>)`; a stop lists
  only what a refresh cannot settle, and names no command.

`resume` and `route` stops carry no decision (they pick a ticket, they do not
drive one); their reasons are held to MECHANICAL too. Imports nothing from
crew_autopilot.
"""

from __future__ import annotations

ID = "<id>"
OWNER_DECISIONS = (
    ("direction", "brainstorm the direction, or say it is approved", ("/crew:brainstorm",)),
    ("answer-question", "answer an open question", ()),
    ("fix-contract", "make spec.md or plan.md pass validation", (f"/crew:spec {ID}", f"/crew:plan {ID}")),
    ("approve-plan", "approve the plan, or not", (f"/crew:approve {ID}",)),
    ("approve-split", "approve the proposed split, or not", (f"/crew:split {ID}",)),
    ("replan", "write or approve a different plan", (f"/crew:plan {ID}",)),
    ("accept-review", "accept or reject the review's FINDINGS (review_ledger.py --accept --by "
                      "<owner>)", ()),
    ("spend-round-or-replan", "spend another review round on an unfinished one, or replan", ()),
    ("revert-or-replan", "revert the edit that staled the receipt, or replan", ()),
    ("look", "look at what autopilot could not tell or settle, and decide", ()),
    ("stale-after-review", "decide about an artifact stale after an accepted review", ()),
    ("activate-ticket", "re-point this worktree at the ticket (crew_ticket.py activate "
                        "--ticket <id>), which changes the approval that governs edits", ()),
    ("continue", "run autopilot again", (f"/crew:autopilot {ID}", f"/crew:autopilot run {ID}")),
    ("closed", "nothing: the ticket is closed", ()),
)
DECISIONS = tuple(row[0] for row in OWNER_DECISIONS)
MECHANICAL = ("graphify update", "graphify . --", "/crew:onboard --refresh",
              "/crew:diagram refresh", "/crew:graph --refresh", "--auto-accept --follow-up",
              "crew_autopilot.py resume", "crew_refresh_check.py", "then /crew:review")
# L-0551: `_phase(deep=False)`'s stop where `next` would rebuild a bundle or ask gh.
UNREAD = "review-unread"
UNREAD_REVIEW = ("a finished review round: whether its receipt is current needs a bundle rebuild, "
                 "which the owner list never runs - see /crew:autopilot status")
UNREAD_SHIP = ("closed by /crew:done and armed to ship: the PR state needs gh, which the owner list "
               "never asks - see /crew:autopilot status")
# The decision a stop at each phase asks for, unless its site names another.
BY_PHASE = {"brainstorm": "direction", "direction-approval": "direction",
            "open-questions": "answer-question", "needs-owner": "answer-question",
            "spec": "fix-contract", "plan": "fix-contract", "approve": "approve-plan",
            "split-approval": "approve-split", "replan": "replan", "auto-replan-cap": "replan",
            "accept-review": "accept-review", "stale-after-review": "stale-after-review",
            "closed": "closed"}


def decided(phase, stop, decision=None):
    """`{"decision": id}` for a stop, `{}` for a phase that runs."""
    return {"decision": decision or BY_PHASE.get(phase, "look")} if stop else {}


def commands(decision, ticket):
    """The commands a stop with `decision` may carry for `ticket`, "" first."""
    found = dict((row[0], row[2]) for row in OWNER_DECISIONS)[decision]
    return ("",) + tuple(c.replace(ID, ticket) for c in found)


def mechanical(text):
    """The MECHANICAL shapes `text` holds."""
    return [shape for shape in MECHANICAL if shape in (text or "")]


def refresh_reason(status, result, pending, settles, stop=None):
    """`refresh check says <status>: <reason>; <artifact>; ...`. `stop` None
    (the non-stop `refresh` phase): every pending artifact, with `(refresh:
    <command>)` where a refresh settles it. "unsettled" (that stop): only the
    artifacts a refresh cannot settle. "named" (`stale-after-review`): every
    one, no command."""
    named = [f"{a.get('kind')} {a.get('name')}: {a.get('status')} - {a.get('reason')}"
             + ("" if settles(a) and stop else f" (refresh: {a.get('command')})" if settles(a)
                else " (a refresh cannot settle this)")
             for a in pending if not (stop == "unsettled" and settles(a))]
    return (f"refresh check says {status}: {result.get('reason', '')}"
            + ("; " + "; ".join(named) if named else ""))
