"""`/crew:autopilot`'s reader: which ticket, which phase, and every stop.

    python3 crew_autopilot.py next --root . --ticket <id> [--phases-run N]
                                   [--last-command CMD] [--json]
    python3 crew_autopilot.py resume --root . [--ticket <id>] [--json]
    python3 crew_autopilot.py settings --root . [--json]
    python3 crew_autopilot.py stops [--json]

T-0004. The lifecycle is prose commands (spec, plan, implement, review,
done); `/crew:autopilot` follows each one's procedure in-session. This module
is what names the NEXT one, from files on disk and nothing else, so a skipped
phase is visible and a phase that cannot be told stops. Read-only: it never
writes a file, never approves, never accepts a review.

## next -- the phase from disk, first match wins

  no direction.md                        brainstorm          stop
  INDEX status `direction`, or no row    direction-approval  stop (no row: cannot tell)
  spec header `status: done`             closed              stop
  `## Open questions` with an item       open-questions      stop
  no spec.md                             spec                /crew:spec <id>
  spec fails crew_ticket.validate        spec                stop
  no plan.md                             plan                /crew:plan <id>
  plan fails crew_ticket.validate        plan                stop
  approval not accepted                  approve             stop, the human types it
  review ledger UNKNOWN                  review              stop
  review ledger NEEDS_REPLAN             replan              stop
  no review round under this plan        implement           /crew:implement <id>
  latest round still reserved            review              stop
  latest round FINDINGS, not accepted    accept-review       stop
  no receipt and no round left           review              stop, never a third reserve
  latest round INCOMPLETE                accept-review       stop
  receipt not current, artifacts stale   refresh             the refresh command
  receipt not current, artifacts fresh   review              /crew:review <id>
  receipt current, artifacts stale       stale-after-review  stop, nothing written
  receipt current, artifacts fresh       done                /crew:done <id>

`closed` sits right after the spec is read, not last: a ticket `/crew:done`
closed is never re-driven because a later commit staled its receipt. An
approval staled only by the spec header's `status:` (what `/crew:implement`
step 7 writes) still stops, with a reason saying so (T-0026).

Refresh runs after implement and before every review round, never after an
accepted receipt: a review bundle excludes only `.work/`
(`review_patch.py`), so a refresh written after review stales the receipt and
`/crew:done` refuses. T-0008's `crew_refresh_check.ticket_freshness` judges
the artifacts. A `stale` one is refreshed with the command it names. An
`unknown` one is refreshed only in T-0008's orphaned-anchor case (the anchor
names no commit, a refresh re-anchors it, and the line carries a command);
every other `unknown` -- a missing tool, no or a fallback scope base, a check
that raised -- stops, as `/crew:implement` step 6 does. When the module
cannot be imported the phase stops as "refresh-artifacts unavailable (T-0008
not landed)" -- never skipped.

## resume -- which ticket

0. `--ticket <id>` (the command's `$1`), when given.
1. `.work/HANDOFF.md`'s `resume:` line, parsed by T-0006's
   `crew_resume.parse_resume` (never re-parsed here), naming a ticket, with
   `branch:` and `head:` equal to this checkout. `--goal` stops until T-0012.
2. This worktree's active-ticket pointer (`crew_ticket.resolve_active`).
3. `.work/INDEX.md`, only when exactly one open ticket has a folder.

A handoff that cannot be used falls through with its reason recorded; the
`## Next action` prose is never guessed from. When the handoff's command
disagrees with the phase on disk, disk wins and the disagreement is reported.
A ticket that differs from this worktree's active-ticket pointer stops, naming
both: the scope guard and the completion audit judge edits by the pointer.
With no pointer, `activate` tells the command to set it to the ticket it drives.

Exit 0 always; the answer is in the output.
"""
import argparse
import importlib
import json
import os
import re
import sys

import crew_config
import crew_state
import crew_ticket
import review_ledger
from crew_common import git_out, read_text

AUTOPILOT = "/crew:autopilot"
UNAVAILABLE = "unavailable"
FRESH = "fresh"
STALE = "stale"
UNKNOWN = "unknown"
UNSETTLED = "unsettled"
# T-0008's reason for the one `unknown` a refresh settles: the anchor names no
# commit here (a squash merge dropped it), and re-anchoring is the refresh.
ORPHANED_ANCHOR = "names no commit"
FALLBACK_BASE = "[fallback base]"
# A status `/crew:implement` or `/crew:plan` may leave in the spec header; the
# approval stop says so when that is the ONLY change since approval.
HEADER_STATUSES = ("spec", "planned", "ready", "direction", "implement", "in-progress",
                   "review")
REFRESH_UNAVAILABLE = "refresh-artifacts unavailable (T-0008 not landed)"

# Stops `next` enforces in code, beyond the ones the phase table names.
FIXED_STOPS = (
    ("needs-replan", "the review ledger is NEEDS_REPLAN: the budget is spent and only "
                     "an approved successor plan continues"),
    ("unknown-ledger", "the review ledger is UNKNOWN (unreadable): the rounds already "
                       "spent cannot be counted"),
    ("needs-replan-or-revert", "no review round left and no receipt stands: /crew:review "
                               "would write NEEDS_REPLAN, so a human reverts or replans"),
    ("failed-validate", "crew_ticket.validate reports a problem in spec.md or plan.md"),
    ("direction-unknown", "no .work/INDEX.md table row says whether direction.md is "
                          "approved"),
    ("unsettled-artifact", "an artifact is unknown for a cause a refresh cannot settle"),
    ("ticket-mismatch", "the ticket to drive is not this worktree's active ticket"),
    ("max-phases", "autopilot.maxPhases phases have run in this invocation"),
    ("no-progress", "a phase ran and the files on disk still name the same command"),
)
# Enforced by the command's procedure, not by `next` (which sees them only as
# `no-progress` when the same command comes round again).
PROCEDURE_STOPS = (
    ("review-verdict", "a review phase ends at its verdict: never fix and rerun inside it"),
    ("failed-done-check", "a /crew:done check refused: it is not retried around"),
    ("failed-phase", "a phase's own procedure refused or stopped"),
)
# In this version these always wait for a person (T-0010 may add policies).
HUMAN_STOPS = (
    ("brainstorm", "/crew:brainstorm and direction approval are a human dialogue"),
    ("plan-approval", "plan approval: the human types /crew:approve <id>"),
    ("review-acceptance", "accepting review FINDINGS is the owner's"),
    ("open-questions", "an open question in direction.md, spec.md or plan.md is answered "
                       "by a person"),
)


def _rel(top, path):
    return os.path.relpath(path, top).replace("\\", "/")


def _index_rows(top):
    """[(ticket, line)] for every INDEX.md line naming a ticket, in order."""
    rows = []
    for line in (read_text(os.path.join(top, ".work", "INDEX.md")) or "").splitlines():
        found = crew_state._TICKET_RE.search(line)  # pylint: disable=protected-access
        if found:
            rows.append((found.group(1), line))
    return rows


def _index_status(top, ticket):
    """The status cell of `ticket`'s INDEX.md table row, lower-cased, or None."""
    for found, line in _index_rows(top):
        if found != ticket or line.count("|") < 2:
            continue
        cells = [c.strip() for c in line.split("|")]
        for index, cell in enumerate(cells):
            if cell == ticket and index + 1 < len(cells):
                return cells[index + 1].lower()
    return None


def _is_open(ticket, line):
    table = crew_state._table_status(line, ticket)  # pylint: disable=protected-access
    if table is not None:
        return not table
    return not crew_state._DONE_RE.search(line)  # pylint: disable=protected-access


def open_index_tickets(top):
    """Every open INDEX.md ticket whose `.work/tickets/<id>/` exists, in order,
    once each. Unlike `crew_state.read_work`, this does not stop at the first."""
    seen = []
    for ticket, line in _index_rows(top):
        if ticket not in seen and _is_open(ticket, line) \
                and os.path.isdir(crew_ticket.ticket_dir(top, ticket)):
            seen.append(ticket)
    return seen


def _header_status(spec_text):
    header = crew_ticket.header_line(spec_text)
    marker = "status:"
    at = header.lower().find(marker)
    if at < 0:
        return None
    rest = header[at + len(marker):].split()
    return rest[0].lower() if rest else None


_BULLET = ("- ", "* ", "+ ")


def _open_items(text):
    """Unanswered items under any `## Open questions` heading. An item is
    answered when it is `none...`, checked (`[x]`) or struck (`~~`)."""
    items, inside = [], False
    for line in (text or "").splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            inside = line.startswith("## ") and title.lower().startswith("open questions")
            line = title[len("open questions"):] if inside else ""
        if not inside:
            continue
        item = line.strip()
        for mark in _BULLET:
            if item.startswith(mark):
                item = item[len(mark):].strip()
        item = re.sub(r"^\d+[.)]\s*", "", item)
        bare = item.strip("\"'`. ").lower()
        if not bare or bare.startswith(("none", "[x]", "~~", "n/a")) or bare == "-":
            continue
        items.append(item)
    return items


def _open_questions(folder):
    """[(file, item)] for every unanswered open question in the ticket."""
    found = []
    for name in ("direction.md", "spec.md", "plan.md"):
        found += [(name, item) for item in _open_items(read_text(os.path.join(folder, name)))]
    return found


def _settles(artifact):
    """Whether running this artifact's command settles it: a `stale` one with a
    command, or T-0008's orphaned-anchor `unknown` it marks refreshable."""
    reason, command = str(artifact.get("reason") or ""), artifact.get("command")
    if not command or FALLBACK_BASE in reason:
        return False
    if artifact.get("status") == STALE:
        return artifact.get("refreshable", True) is not False
    return (artifact.get("status") == UNKNOWN and artifact.get("refreshable") is True
            and ORPHANED_ANCHOR in reason)


def _refresh_state(root, ticket):
    """`{"state": fresh|stale|unsettled|unavailable, "command", "reason"}` from
    T-0008's check. `stale` has a command that settles every pending artifact;
    `unsettled` (a stop) is any other not-fresh answer, a check that raised
    included. Never `fresh` unless T-0008 said so."""
    try:
        check = importlib.import_module("crew_refresh_check")
    except ImportError:
        return {"state": UNAVAILABLE, "command": "", "reason": REFRESH_UNAVAILABLE}
    try:
        result = check.ticket_freshness(root, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        return {"state": UNSETTLED, "command": "",
                "reason": f"the refresh check could not run ({exc}) - a human looks"}
    status = result.get("status")
    if status == FRESH:
        return {"state": FRESH, "command": "", "reason": result.get("reason", "")}
    pending = [a for a in result.get("artifacts") or [] if a.get("status") in (STALE, UNKNOWN)]
    named = [f"{a.get('kind')} {a.get('name')}: {a.get('status')} - {a.get('reason')}"
             + (f" (refresh: {a.get('command')})" if _settles(a) else " (a refresh cannot "
                "settle this)") for a in pending]
    reason = (f"refresh check says {status}: {result.get('reason', '')}"
              + ("; " + "; ".join(named) if named else ""))
    overall_unknown = status == UNKNOWN and not any(a.get("status") == UNKNOWN for a in pending)
    if status not in (STALE, UNKNOWN) or not pending or overall_unknown \
            or not all(_settles(a) for a in pending):
        return {"state": UNSETTLED, "command": "", "reason": reason}
    return {"state": STALE, "command": pending[0]["command"], "reason": reason}


def _header_only_change(contract, receipt):
    """The spec header status the approval was taken at, when changing only
    that `status:` word back makes spec.md hash to the approved bytes and
    plan.md is unchanged -- else None. Measured, not guessed."""
    spec, plan = contract.get("spec.md"), contract.get("plan.md")
    if not spec or not plan or not isinstance(receipt, dict) \
            or crew_ticket._sha(plan) != receipt.get("plan_sha256"):  # pylint: disable=protected-access
        return None
    text = spec.decode("utf-8", errors="surrogateescape")
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if not line.lstrip("\ufeff").startswith("# "):
            continue
        found = re.search(r"(status:\s*)(\S+)", line)
        if not found:
            return None
        for was in HEADER_STATUSES:
            lines[index] = line[:found.start(2)] + was + line[found.end(2):]
            body = "\n".join(lines).encode("utf-8", errors="surrogateescape")
            if crew_ticket._sha(body) == receipt.get("spec_sha256"):  # pylint: disable=protected-access
                return was
        return None
    return None


def _phase(root, ticket):
    """`next`'s phase table (module docstring), with no session guard."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    folder = crew_ticket.ticket_dir(top, ticket)
    evidence = []

    def answer(phase, stop, reason, command=""):
        return {"ticket": ticket, "phase": phase, "stop": stop, "reason": reason,
                "command": command, "evidence": list(evidence)}

    direction = os.path.join(folder, "direction.md")
    evidence.append(_rel(top, direction))
    if not os.path.isfile(direction):
        return answer("brainstorm", True, f"no {_rel(top, direction)}: needs "
                      "/crew:brainstorm - a human dialogue", "/crew:brainstorm")
    evidence.append(".work/INDEX.md")
    status = _index_status(top, ticket)
    if status == "direction":
        return answer("direction-approval", True, "INDEX.md status is `direction`: "
                      "direction.md waits for the owner's yes in /crew:brainstorm")
    if status is None:
        return answer("direction-approval", True, f"cannot tell whether {ticket}'s "
                      f"direction is approved: .work/INDEX.md has no table row for {ticket} "
                      "(Jira and ServiceDesk Plus modes write none). The human adds "
                      f"`{ticket} | ready | <risk> | <repo> | <title>` once it is agreed")
    contract = crew_ticket.read_contract(top, ticket)
    evidence.append(_rel(top, os.path.join(folder, "spec.md")))
    if contract["spec.md"] is not None and _header_status(
            crew_ticket._text(contract["spec.md"])) == "done":  # pylint: disable=protected-access
        return answer("closed", True, "spec.md header is `status: done`: nothing left "
                      "in this ticket (ship is T-0011)")
    questions = _open_questions(folder)
    if questions:
        return answer("open-questions", True, "unanswered under ## Open questions: "
                      + "; ".join(f"{name}: {item}" for name, item in questions[:4])
                      + " - a person answers (write `none - <answer>` or check it `[x]`)")
    if contract["spec.md"] is None:
        return answer("spec", False, "no spec.md", f"/crew:spec {ticket}")
    spec_only = crew_ticket.validate(top, ticket, {"spec.md": contract["spec.md"],
                                                   "plan.md": None})[:-1]
    if spec_only:
        return answer("spec", True, "spec.md fails crew_ticket.validate: "
                      + "; ".join(spec_only), f"/crew:spec {ticket}")
    evidence.append(_rel(top, os.path.join(folder, "plan.md")))
    if contract["plan.md"] is None:
        return answer("plan", False, "no plan.md", f"/crew:plan {ticket}")
    problems = crew_ticket.validate(top, ticket, contract)
    if problems:
        return answer("plan", True, "plan.md fails crew_ticket.validate: "
                      + "; ".join(problems), f"/crew:plan {ticket}")
    approval = crew_ticket.accepted(top, ticket)
    evidence.append(_rel(top, crew_ticket.approval_path(top, ticket)))
    if approval["status"] != "approved":
        was = (_header_only_change(contract, approval.get("receipt"))
               if approval["status"] == "stale" else None)
        why = approval["why"] if not was else (
            f"only the header's status changed since approval (`status: {was}` -> "
            f"`status: {_header_status(crew_ticket._text(contract['spec.md']))}`): every "  # pylint: disable=protected-access
            "implement ends in an approval stop, because /crew:implement step 7 writes the "
            "header and the approval hashes all of spec.md (T-0026)")
        return answer("approve", True, f"{why}. Only the human types "
                      f"/crew:approve {ticket}; autopilot never approves",
                      f"/crew:approve {ticket}")
    return _review_phase(top, ticket, evidence, answer)


def _current_rounds(ledger):
    """Rounds reserved under the current plan: after the latest successor."""
    rounds = ledger.get("rounds") or []
    successors = ledger.get("successors") or []
    after = successors[-1].get("after_round", 0) if successors else 0
    return rounds[after:] if isinstance(after, int) else rounds


def _review_phase(top, ticket, evidence, answer):
    ledger = review_ledger.status(top, ticket)
    evidence.append(_rel(top, ledger["path"]))
    if ledger["state"] == review_ledger.UNKNOWN:
        return answer("review", True, f"review ledger {_rel(top, ledger['path'])} is "
                      "UNKNOWN (unreadable): the rounds spent cannot be counted")
    if ledger["state"] == review_ledger.NEEDS_REPLAN:
        return answer("replan", True, f"{ticket} is NEEDS_REPLAN: the review budget is "
                      "spent; a successor plan needs the human's /crew:approve",
                      f"/crew:plan {ticket}")
    rounds = _current_rounds(ledger)
    if not rounds:
        return answer("implement", False, "approved, no review round under this plan",
                      f"/crew:implement {ticket}")
    latest = rounds[-1]
    if latest.get("status") != "completed":
        return answer("review", True, f"round {latest.get('round')} is reserved with no "
                      "result: a reviewer is running or died, and another /crew:review "
                      "spends the next round - a human decides")
    receipt = ledger.get("receipt") or {}
    if latest.get("verdict") == "FINDINGS" and not (
            receipt.get("kind") == "owner-accepted"
            and receipt.get("round") == latest.get("round")):
        return answer("accept-review", True, f"round {latest.get('round')} is FINDINGS: "
                      "the owner accepts with review_ledger.py --accept --by <owner>, "
                      "or fixes then /crew:review")
    ok, message = review_ledger.check_receipt(top, ticket)
    left = ledger.get("rounds_left", 0)
    if not ok and (not isinstance(left, int) or left < 1):
        return answer("review", True, f"no review round left and no receipt stands "
                      f"({message}): /crew:review would reserve a third round and put "
                      f"{ticket} in NEEDS_REPLAN, which only a new approved plan leaves. A "
                      "human reverts the edit that staled the receipt, or replans")
    if latest.get("verdict") != "CLEAN" and not ok:
        return answer("accept-review", True, f"round {latest.get('round')} is "
                      f"{latest.get('verdict') or 'without a verdict'}: the reviewer did not "
                      "finish reading, and it cannot be accepted - a human reruns "
                      "/crew:review (spending a round) or replans")
    refresh = _refresh_state(top, ticket)
    if refresh["state"] == UNAVAILABLE:
        return answer("refresh", True, refresh["reason"])
    if not ok and refresh["state"] != FRESH:
        command = refresh["command"] if refresh["state"] == STALE else ""
        return answer("refresh", not command,
                      f"before the next review round - {refresh['reason']}", command)
    if not ok:
        return answer("review", False, f"{message}; artifacts fresh",
                      f"/crew:review {ticket}")
    if refresh["state"] != FRESH:
        return answer("stale-after-review", True, "an artifact is stale after an "
                      "accepted review; refreshing now would stale the receipt - human "
                      f"decides. {refresh['reason']}")
    return answer("done", False, f"{message}; artifacts fresh", f"/crew:done {ticket}")


def next_phase(root, ticket, phases_run=0, last_command=None, max_phases=None):
    """`{"ticket", "phase", "stop", "reason", "command", "evidence"}`. A
    `stop` phase's `command` is what the HUMAN types, never run by autopilot.
    `max_phases` and `last_command` are the session's count and the command it
    last ran: reaching the count, or being handed the same command again, stops."""
    crew_ticket.check_ticket(ticket)
    result = _phase(root, ticket)
    if result["stop"]:
        return result
    if max_phases is not None and phases_run >= max_phases:
        return dict(result, stop=True, reason=(
            f"autopilot.maxPhases ({max_phases}) reached after {phases_run} phases; next "
            f"would be {result['phase']} - run /crew:autopilot {ticket} again"))
    if last_command and result["command"] == last_command:
        return dict(result, stop=True, reason=(
            f"no progress: {last_command} ran and the files on disk still name it "
            f"({result['reason']}) - a human looks at why"))
    return result


def _handoff_ticket(top):
    """(ticket, hint, stop_reason, why_not) from `.work/HANDOFF.md`."""
    path = os.path.join(top, ".work", "HANDOFF.md")
    text = read_text(path)
    if text is None:
        return None, "", None, "no .work/HANDOFF.md"
    try:
        resume = importlib.import_module("crew_resume")
        parsed = resume.parse_resume(text)
    except ImportError:
        return None, "", None, ("crew_resume is not importable (T-0006 not landed), so "
                                "the handoff's resume: line was not read")
    except Exception as exc:  # pylint: disable=broad-except
        return None, "", None, f"crew_resume.parse_resume raised {exc!r}"
    if not isinstance(parsed, dict) or not parsed.get("ok"):
        reason = parsed.get("reason") if isinstance(parsed, dict) else "no answer"
        return None, "", None, f"the handoff's resume: line is not usable ({reason})"
    command, arg, kind = parsed.get("command"), parsed.get("arg"), parsed.get("kind")
    if command == AUTOPILOT and kind == "goal":
        return None, "", f"the handoff resumes {AUTOPILOT} --goal {arg}: goal resume " \
                         "arrives with T-0012", ""
    if kind != "ticket" or not arg:
        return None, "", None, f"the handoff's resume: {command} names no ticket"
    branch = crew_state._HANDOFF_BRANCH_RE.search(text)  # pylint: disable=protected-access
    head = crew_state._HANDOFF_HEAD_RE.search(text)  # pylint: disable=protected-access
    here_branch = git_out(top, "rev-parse", "--abbrev-ref", "HEAD")
    here_head = (git_out(top, "rev-parse", "HEAD") or "").lower()
    if not branch or branch.group(1) != here_branch:
        return None, "", None, (f"the handoff's branch: "
                                f"{branch.group(1) if branch else '(missing)'} is not "
                                f"this checkout's {here_branch}")
    if not head or not here_head or not here_head.startswith(head.group(1).lower()):
        return None, "", None, (f"the handoff's head: "
                                f"{head.group(1) if head else '(missing)'} is not this "
                                f"checkout's {here_head[:12] or '(unknown)'}")
    if not os.path.isdir(crew_ticket.ticket_dir(top, arg)):
        return None, "", None, f"the handoff names {arg}, which has no .work/tickets/ folder"
    render = getattr(resume, "render", None)
    return arg, (render(parsed) if callable(render) else f"{command} {arg}"), None, ""


def resume_target(root, ticket=None):
    """`{"ticket", "source", "stop", "hint", "disagreement", "reason",
    "fallthrough", "next", "activate"}` -- see the module docstring's order.
    `ticket` is the command's `$1`; it is still held to the active pointer."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    fallthrough = []

    def stopped(source, reason):
        return {"ticket": None, "source": source, "stop": True, "hint": "",
                "disagreement": "", "reason": reason, "fallthrough": fallthrough,
                "next": None, "activate": False}

    hint, source, why = "", "argument", ""
    if ticket:
        crew_ticket.check_ticket(ticket)
        if not os.path.isdir(crew_ticket.ticket_dir(top, ticket)):
            return stopped(source, f"{ticket} has no .work/tickets/ folder")
    else:
        ticket, hint, stop_reason, why = _handoff_ticket(top)
        source = "handoff"
        if stop_reason:
            return stopped(source, stop_reason)
    if not ticket:
        fallthrough.append(why)
        active, where, broken = crew_ticket.resolve_active(top)
        if broken:
            return stopped("active-ticket", f"{where}; a broken pointer is not guessed "
                           "past - fix it with crew_ticket.py activate")
        if where == "active-ticket":
            ticket, source = active, "active-ticket"
        else:
            fallthrough.append("no active-ticket entry for this worktree")
            candidates = open_index_tickets(top)
            if len(candidates) > 1:
                return stopped(".work/INDEX.md", "several open tickets and no pointer: "
                               + ", ".join(candidates)
                               + " - name one: /crew:autopilot <ticket>")
            if not candidates:
                return stopped(".work/INDEX.md", "no open ticket with a .work/tickets/ "
                               "folder - start one with /crew:brainstorm")
            ticket, source = candidates[0], ".work/INDEX.md"
    active, where, broken = crew_ticket.resolve_active(top)
    if broken:
        return stopped("active-ticket", f"{where}; a broken pointer is not guessed past - "
                       "fix it with crew_ticket.py activate")
    if where == "active-ticket" and active != ticket:
        return stopped(source, f"{source} names {ticket}, but this worktree's active ticket "
                       f"is {active}, and the scope guard and completion audit judge edits "
                       f"by {active}'s approval and Touch. Run /crew:autopilot {active}, or "
                       f"the human re-points it: crew_ticket.py activate --ticket {ticket}")
    disk = next_phase(top, ticket)
    disagreement = ""
    if hint and not hint.startswith(AUTOPILOT + " ") and hint != disk["command"]:
        disagreement = (f"the handoff says {hint}, the disk says "
                        f"{disk['command'] or disk['phase']}; disk wins")
    return {"ticket": ticket, "source": source, "stop": False, "hint": hint,
            "disagreement": disagreement, "reason": f"{ticket} from {source}",
            "fallthrough": fallthrough, "next": disk, "activate": where != "active-ticket"}


def _read_json(path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def settings(root):
    """`{"mode", "armed", "maxPhases", "saw", "warnings"}`. Read through
    `crew_config.resolve_config` -- `.crew/config.json` over the defaults, the
    file `crew_ticket.cli_approval_allowed` reads. `mode` arms only when it is
    exactly the string `plan`; `maxPhases` must be a positive int, else 12."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    block = crew_config.resolve_config(top).get("autopilot")
    block = block if isinstance(block, dict) else {}
    warnings = []
    mode = block.get("mode")
    armed = mode == "plan"
    if not armed and mode != "off":
        warnings.append(f"autopilot.mode is {mode!r}: only the exact string 'plan' arms "
                        "autopilot, so it reads as off")
    limit = block.get("maxPhases")
    default = crew_state.AUTOPILOT_DEFAULTS["maxPhases"]
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        warnings.append(f"autopilot.maxPhases is {limit!r}, not a positive integer; "
                        f"using {default}")
        limit = default
    crew_json = _read_json(os.path.join(top, ".crew", "crew.json"))
    if isinstance(crew_json, dict) and "autopilot" in crew_json \
            and "autopilot" not in crew_state.load_config(top):
        warnings.append("autopilot is set in .crew/crew.json, which crew does not read "
                        "for this key; move it to .crew/config.json")
    return {"mode": "plan" if armed else "off", "armed": armed, "maxPhases": limit,
            "saw": mode, "warnings": warnings}


def stops():
    """Every stop, from code: AUTONOMOUS_STOPS, the fixed ones, the human ones."""
    def rows(pairs):
        return [{"id": slug, "text": text} for slug, text in pairs]
    return {"autonomous": rows(crew_state.AUTONOMOUS_STOPS), "fixed": rows(FIXED_STOPS),
            "human": rows(HUMAN_STOPS), "procedure": rows(PROCEDURE_STOPS)}


def _line(**fields):
    return " ".join(f"{k}={v}" for k, v in fields.items())


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("next", "resume", "settings", "stops"):
        action = sub.add_parser(name)
        action.add_argument("--json", action="store_true")
        if name != "stops":
            action.add_argument("--root", default=".")
    sub.choices["next"].add_argument("--ticket", required=True)
    sub.choices["resume"].add_argument("--ticket", default="")
    sub.choices["next"].add_argument("--phases-run", type=int, default=0)
    sub.choices["next"].add_argument("--last-command", default="")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    # Read-only: git must not even refresh the index's stat cache.
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    if args.action == "stops":
        result = stops()
        text = "\n".join(f"{kind} {row['id']}: {row['text']}"
                         for kind, rows in result.items() for row in rows)
    elif args.action == "settings":
        result = settings(args.root)
        text = "\n".join([_line(mode=result["mode"], maxPhases=result["maxPhases"])]
                         + [f"warning: {w}" for w in result["warnings"]])
    elif args.action == "resume":
        try:
            result = resume_target(args.root, args.ticket or None)
        except crew_ticket.TicketError as exc:
            result = {"ticket": None, "source": "argument", "stop": True, "hint": "",
                      "disagreement": "", "reason": str(exc), "fallthrough": [],
                      "next": None, "activate": False}
        text = _line(ticket=result["ticket"] or "", source=result["source"],
                     stop=int(result["stop"]), activate=int(result["activate"]),
                     hint=result["hint"], reason=result["reason"])
        text += "".join(f"\nfell through: {w}" for w in result["fallthrough"])
        text += f"\ndisagreement: {result['disagreement']}" if result["disagreement"] else ""
    else:
        try:
            result = next_phase(args.root, args.ticket, args.phases_run,
                                args.last_command or None,
                                settings(args.root)["maxPhases"])
        except crew_ticket.TicketError as exc:
            result = {"ticket": args.ticket, "phase": "invalid", "stop": True,
                      "command": "", "reason": str(exc), "evidence": []}
        text = _line(phase=result["phase"], stop=int(result["stop"]),
                     command=result["command"], reason=result["reason"])
    sys.stdout.write((json.dumps(result, indent=2) if args.json else text) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
