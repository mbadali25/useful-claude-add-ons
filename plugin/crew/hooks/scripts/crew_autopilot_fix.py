#!/usr/bin/env python3
"""T-0067: `autopilot.reviewPolicy` and the single-ticket `fix` phase.

`crew_autopilot._review_phase` asks `decide` where it would stop at
`accept-review` for a FINDINGS round no receipt stands on. Three answers:

- None: today's `accept-review` stop, its reason unchanged. The policy is
  `stop` (the default) or `clean-only` (a wave meaning only, T-0029).
- a string: the same stop, with this could-not-tell or refusal cause appended.
  The policy is `unknown` (the config could not be read), or it is
  `fix-and-rereview` and something it needs cannot be read or is not so.
- a dict: the phase `next` returns. `fix` (stop=0, command `fix-findings <id>
  round <n>`) until the fix is complete; then `toward(...)` -- the refresh,
  then `/crew:review <id>`, as a receipt that does not stand goes.

`fix-and-rereview` fixes only when ALL hold: `rounds_left` is an int (never a
bool) and at least 1; the round row carries `findings`, a list of one-line
strings with at least one `BLOCK|` or `FIX|` line, plus `base` and
`bundle_sha256`. The fix is complete when BOTH hold, read from disk:
`.work/tickets/<id>/fixes.md` has a `## Round <n>` section holding every
`BLOCK|` and `FIX|` line of the row verbatim as a whole line, as many times as
the row carries it (`review_ledger.check_follow_up`'s rule; NIT lines are not
owed), and the bundle rebuilt now from the row's `base` has a different
`bundle_sha256` (`.work/` is outside the bundle, so fixes.md alone never
does). A missing fixes.md is "not fixed yet"; one that is present but not
UTF-8, or a bundle that cannot be rebuilt, is could-not-tell and stops.

The loop bound is `next_phase`'s no-progress guard: `fix` named again right
after a `fix` phase ran stops. An unrefunded INCOMPLETE round, NEEDS_REPLAN and
a reserved round never reach here. Nothing here writes a file or accepts a
review. Imports nothing from crew_autopilot.
"""

from __future__ import annotations

import collections
import os
import re

import crew_ticket
import review_patch

STOP, CLEAN_ONLY, FIX = "stop", "clean-only", "fix-and-rereview"
POLICIES = (STOP, CLEAN_ONLY, FIX)
UNKNOWN = "unknown"
# Appended to crew_autopilot.PROCEDURE_STOPS.
PROCEDURE_STOPS = (
    ("fix-refused", "the fix phase could not or would not fix a finding (outside Touch, "
                    "disputes the spec or plan, or the implementer disagrees): the owner decides"),
)
OWED = ("BLOCK|", "FIX|")
_ROUND_HEADING = re.compile(r"^##[ \t]+Round[ \t]+(\d+)[ \t]*$")


def review_policy(block, warnings):
    """The policy from an `autopilot` block already known to be an object:
    anything but exactly one of POLICIES -- a case variant, a bool, an empty
    string -- reads `stop`, and a warning naming the value joins `warnings`."""
    value = block.get("reviewPolicy", STOP)
    if isinstance(value, str) and value in POLICIES:
        return value
    warnings.append(f"autopilot.reviewPolicy is {value!r}, not one of {'|'.join(POLICIES)}; it "
                    "reads as stop")
    return STOP


def command(ticket, number):
    return f"fix-findings {ticket} round {number}"


def fixes_path(folder):
    return os.path.join(folder, "fixes.md")


def _section_lines(text, number):
    """Every line under `## Round <number>` (to the next `## `), CRLF-safe;
    lines split on "\\n" only, never stripped (check_follow_up's rule)."""
    lines, inside = [], False
    for raw in text.split("\n"):
        line = raw[:-1] if raw.endswith("\r") else raw
        if line.startswith("## "):
            match = _ROUND_HEADING.match(line)
            inside = bool(match) and int(match.group(1)) == number
            continue
        if inside:
            lines.append(line)
    return lines


def _missing(folder, number, owed):
    """(missing lines, None), or (None, why) when fixes.md cannot be read. A
    missing fixes.md owes every line."""
    path = fixes_path(folder)
    if not os.path.lexists(path):
        return list(owed), None
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except UnicodeDecodeError as exc:
        return None, f"fixes.md is not UTF-8 ({exc.reason}): could not tell"
    except OSError as exc:
        return None, f"fixes.md could not be read ({exc.strerror or exc}): could not tell"
    have = collections.Counter(_section_lines(text, number))
    return list((collections.Counter(owed) - have).elements()), None


def decide(top, ticket, policy, ledger, latest, answer, toward):
    """None, a cause string, or the phase dict; see the module docstring."""
    folder = crew_ticket.ticket_dir(top, ticket)
    if policy in (STOP, CLEAN_ONLY):
        return None
    cause = " - autopilot.reviewPolicy fix-and-rereview does not fix it: "
    if policy != FIX:
        return (" - autopilot.reviewPolicy could not be told (the config could not be read), "
                "so autopilot does not fix it")
    left = ledger.get("rounds_left")
    if isinstance(left, bool) or not isinstance(left, int):
        return cause + f"rounds_left is {left!r}, not an integer: could not tell"
    if left < 1:
        return cause + "this is the final round; it is the owner's"
    number, findings = latest.get("round"), latest.get("findings")
    if not isinstance(findings, list) or not all(isinstance(f, str) for f in findings):
        return cause + f"round {number} carries no list of finding lines: could not tell"
    if any("\n" in f or "\r" in f for f in findings):
        return cause + f"round {number} lists a finding with a line break: could not tell"
    owed = [f for f in findings if f.strip().startswith(OWED)]
    if not owed:
        return cause + f"round {number} lists no BLOCK or FIX line"
    base, recorded = latest.get("base"), latest.get("bundle_sha256")
    if isinstance(number, bool) or not isinstance(number, int) or not base or not recorded:
        return cause + (f"round {number!r} has no round number, base or bundle_sha256: "
                        "could not tell")
    missing, why = _missing(folder, number, owed)
    if why:
        return cause + why
    try:
        current = review_patch.compute(top, base)[0]["bundle_sha256"]
    except (RuntimeError, OSError, KeyError, TypeError) as exc:
        return cause + f"the bundle could not be rebuilt from {base} ({exc}): could not tell"
    if missing or current == recorded:
        todo = []
        if missing:
            todo.append(f"fixes.md's `## Round {number}` lacks {len(missing)} of {len(owed)} "
                        f"BLOCK/FIX line(s) as a whole line, first: {missing[0]}")
        if current == recorded:
            todo.append("the bundle has not changed since the round")
        return answer("fix", False, f"round {number} is FINDINGS with {left} round(s) left and "
                      "autopilot.reviewPolicy fix-and-rereview: fix every BLOCK and FIX "
                      "test-first inside Touch, commit, record each in fixes.md - "
                      + "; ".join(todo), command(ticket, number))
    return toward(top, ticket, answer, False,
                  f"round {number}'s findings are fixed (fixes.md quotes every BLOCK and FIX "
                  "line and the bundle changed)")
