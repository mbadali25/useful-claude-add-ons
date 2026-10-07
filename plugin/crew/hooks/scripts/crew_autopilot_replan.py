#!/usr/bin/env python3
"""L-0670: after T-0074's automatic reject, autopilot approves a successor plan
only when it quotes every BLOCK and FIX line of the rejected round.

`replan_check(root, ticket)` -> `{"applies", "ok", "reason", "missing"}`:

- `applies` False (and `ok` True) when the review ledger is not NEEDS_REPLAN, or
  its `rejected.by` is a name other than `crew_autopilot.AUTO_REJECT_BY` (an
  owner's reject: the owner plans freely), or NEEDS_REPLAN carries no
  `rejected` record at all (the budget was spent; `review_ledger.reject` always
  writes one), or there is no ledger at all. A `rejected` record that is not
  an object naming who rejected is could-not-tell.
- Otherwise the required lines are the `findings` of the row whose `round` is
  `rejected.round` that start with `BLOCK|` or `FIX|` (NIT lines are not
  owed), compared without stripping. `plan.md` is read as UTF-8 with
  `newline=""`, split on "\\n" only, one trailing "\\r" dropped per line, and
  counted: `ok` only when every required line is a whole line at least as many
  times as the round carries it (`review_ledger.check_follow_up`'s rule).
- Could-not-tell is `ok` False with a reason: a ledger that cannot be read,
  no row for the rejected round, `findings` not a list of one-line strings,
  no BLOCK line (T-0074 rejects only for a BLOCK), `plan.md` missing,
  unreadable or not UTF-8.

`crew_autopilot.approve` asks it after `approval_policy` allows and before
`crew_ticket.approve`: applies and not ok is `refused:`, exit 2, nothing
written. `/crew:approve` and `crew_ticket.py approve --by` never ask it (the
owner may approve a plan that drops a finding on purpose). The script action
`replan-check` prints `applies= ok= missing=` and the reason, exit 0 when ok,
1 when not, and writes nothing.
"""

from __future__ import annotations

import collections
import os

import crew_autopilot_fix
import crew_ticket
import review_ledger

OWED = ("BLOCK|", "FIX|")
CANNOT_TELL = "could not tell"


def _result(applies, ok, reason, missing=0):
    return {"applies": applies, "ok": ok, "reason": reason, "missing": missing}


def _required(data):
    """`(lines, None)` owed by the rejected round, or `(None, why)`."""
    rejected = data.get("rejected") or {}
    rows = [r for r in data.get("rounds") or [] if isinstance(r, dict)
            and r.get("round") == rejected.get("round")]
    if len(rows) != 1:
        return None, f"no single round row for the rejected round {rejected.get('round')!r}"
    findings = rows[0].get("findings")
    if not isinstance(findings, list) or not all(isinstance(f, str) for f in findings) \
            or any("\n" in f or "\r" in f for f in findings):
        return None, "the rejected round's findings are not a list of one-line strings"
    # Classified as the automatic reject reads them (stripped); compared verbatim.
    disagree = crew_autopilot_fix._counts_disagree(rows[0].get("counts"), findings)  # pylint: disable=protected-access
    if disagree:
        return None, f"the rejected round's {disagree}"
    lines = [f for f in findings if f.strip().startswith(OWED)]
    if not any(f.strip().startswith("BLOCK|") for f in lines):
        return None, "the rejected round lists no BLOCK line, yet an automatic reject needs one"
    return lines, None


def _plan_lines(top, ticket):
    """`(Counter of plan.md's lines, None)` or `(None, why)`."""
    path = os.path.join(crew_ticket.ticket_dir(top, ticket), "plan.md")
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None, "plan.md is missing"
    except UnicodeDecodeError as exc:
        return None, f"plan.md is not UTF-8 ({exc.reason})"
    except OSError as exc:
        return None, f"plan.md could not be read ({exc.strerror or exc})"
    return collections.Counter(line[:-1] if line.endswith("\r") else line
                               for line in text.split("\n")), None


def replan_check(root, ticket):
    """See the module docstring. Reads only."""
    import crew_autopilot  # pylint: disable=import-outside-toplevel,cyclic-import
    crew_ticket.check_ticket(ticket)
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    data, state = review_ledger.load(review_ledger.ledger_path(top, ticket))
    if state == "absent":
        return _result(False, True, "no review ledger: not a successor after an automatic reject")
    if state != "ok":
        return _result(True, False, f"{CANNOT_TELL}: the review ledger is {state}")
    rejected = data.get("rejected")
    if data.get("state") != review_ledger.NEEDS_REPLAN:
        return _result(False, True, "not NEEDS_REPLAN")
    if "rejected" not in data:  # review_ledger.reject always writes it: a spent budget, no reject
        return _result(False, True, "NEEDS_REPLAN with no reject recorded (the budget was spent)")
    if not isinstance(rejected, dict) or not isinstance(rejected.get("by"), str) \
            or not rejected["by"].strip():
        # L-0670 review r2: who rejected cannot be told, so neither can whether the guard applies.
        return _result(True, False, f"{CANNOT_TELL}: the ledger is NEEDS_REPLAN and its rejected "
                                    f"record ({rejected!r}) does not say who rejected")
    if rejected.get("by") != crew_autopilot.AUTO_REJECT_BY:
        return _result(False, True, "NEEDS_REPLAN after the owner's reject")
    lines, why = _required(data)
    if why:
        return _result(True, False, f"{CANNOT_TELL}: {why}")
    have, why = _plan_lines(top, ticket)
    if why:
        return _result(True, False, f"{CANNOT_TELL}: {why}")
    missing = list((collections.Counter(lines) - have).elements())
    if missing:
        return _result(True, False, f"successor plan lacks {len(missing)} of {len(lines)} "
                                    f"finding line(s), first: {missing[0]}", len(missing))
    return _result(True, True, f"successor plan quotes all {len(lines)} BLOCK and FIX line(s)")


def add_parsers(sub):
    """`replan-check` on crew_autopilot.py's subparsers."""
    parser = sub.add_parser("replan-check")
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)


def main(args):
    got = replan_check(args.root, args.ticket)
    print(f"applies={int(got['applies'])} ok={int(got['ok'])} missing={got['missing']} "
          f"reason={' '.join(got['reason'].split())}")
    return 0 if got["ok"] else 1
