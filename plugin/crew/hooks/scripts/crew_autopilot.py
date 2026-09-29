"""`/crew:autopilot`'s reader: which ticket, which phase, and every stop.

    python3 crew_autopilot.py next --root . --ticket <id> [--phases-run N]
                                   [--last-command CMD] [--json]
    python3 crew_autopilot.py resume --root . [--ticket <id>] [--json]
    python3 crew_autopilot.py settings --root . [--json]
    python3 crew_autopilot.py stops [--json]
    python3 crew_autopilot.py deploy-allowed --root . --env <name> --class <class>
                                             [--json]
    python3 crew_autopilot.py route --root . --args "<the command's arguments>" [--json]
    python3 crew_autopilot.py route --root . --first <token> [--json]
    python3 crew_autopilot.py status --root . [--ticket <id>] [--json]
                                     (at most 12 lines; --json is one line)
    python3 crew_autopilot.py approve --root . --ticket <id>
    python3 crew_autopilot.py questions-check --root . --ticket <id> [--json]

T-0004. The lifecycle is prose commands (spec, plan, implement, review,
done); `/crew:autopilot` follows each one's procedure in-session. This module
is what names the NEXT one, from files on disk and nothing else, so a skipped
phase is visible and a phase that cannot be told stops. Read-only except
`approve`, and only when `approval_policy` allows under the configured policy;
it never accepts a review. That is the single exception (T-0010, below):
`next`, `resume`, `settings`, `stops`, `route`, `status`, `questions-check` and
T-0072's `deploy-allowed` write no file. `approve` writes exactly what
`crew_ticket.approve` writes for every approval route, `/crew:approve` included,
all under `<git-common-dir>/crew/`: `approval.json`; `scope-tickets.json`, the scope
ramp's list, on a ticket's first approval; and, when the review ledger is
NEEDS_REPLAN and the plan is a distinct successor, the ledger itself, moved
NEEDS_REPLAN -> IN_REVIEW (the successor continuation). Run as a script it writes no
bytecode either, however it is invoked (`-B` or not); a module that imports it
keeps its own bytecode setting.

## approve and questions-check -- the two policies (T-0010)

`autopilot.approval` and `autopilot.questions` are `human|self|risk`
(default `risk`); any other value reads as `human`, with a warning.

`approval_policy` allows only when `scope.allowCliApproval` is exactly
`true` in `.crew/config.json` -- at every setting -- and the review ledger is
readable (a NEEDS_REPLAN one included: a distinct successor plan is its only
way out, and the ledger refuses a plan approved before); then
`human` never allows, `self` allows any risk, `risk` only a spec header that
says `risk: low`. An absent or unparseable risk is `high`
(`crew_ticket.parse_risk`), never `low`. `approve` also needs autopilot
armed, writes the receipt with `approved_via: "autopilot"` and prints
`self-approved <id> under approval=<policy>, risk=<risk>`; a refusal exits 2
with `refused: <why>`. `crew_ticket.accepted` re-asks `approval_policy` on
every read, so an `autopilot` receipt stands only while the policy still says
yes. `question_policy` is the same decision for an open question -- `take`
the researched recommendation or `stop` -- with no `allowCliApproval` rule.

`questions-check` validates `.work/tickets/<id>/questions.md` (the shape is
QUESTIONS_SHAPE, printed when it fails) and prints `valid= action= policy=
risk=`, then one `taken:` line per question autopilot answered. A `taken:`
line is valid only for the recommended option, only naming a policy that
takes (`self` or `risk` -- the one in force when it was taken, so a later
policy change does not void an honest record), and only while the policy in
force says `take`. Exit 0 valid, 1 not.

## next -- the phase from disk, first match wins

  no direction.md                        brainstorm          stop
  INDEX status `direction`, or no row    direction-approval  stop (no row: cannot tell)
  INDEX status done/merged/closed/...    closed              stop
  INDEX status not in DIRECTION_APPROVED direction-approval  stop (cannot tell)
  spec header `status: done`             closed              stop
  `## Open questions` with an item       open-questions      stop
  no spec.md                             spec                /crew:spec <id>
  spec fails crew_ticket.validate        spec                stop
  no plan.md                             plan                /crew:plan <id>
  plan fails crew_ticket.validate        plan                stop
  approval not accepted                  approve             stop, unless the policy allows
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
closed is never re-driven because a later commit staled its receipt. The
header `status:` edits the lifecycle makes keep the approval (T-0026's
digest); one that still stales it -- a receipt from before T-0026, or a value
outside `crew_ticket.STATUS_VALUES` -- stops, with a reason saying only the
header changed.

Refresh runs after implement and before every review round, never after an
accepted receipt: a review bundle excludes only `.work/` and `graphify-out/`
(`review_patch.py`), so a codemap, diagram or rules refresh stales the receipt and
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

Exit 0 always, but for `approve` and `questions-check` (above); the answer is
in the output. An exception inside `next` or `resume` prints `stop=1` with its reason: a crash is "cannot tell", never
silence the command could read as permission.

## deploy-allowed -- may autopilot deploy here without asking (T-0072)

`deploy_allowed` answers `allow`, `ask` or `refuse` for one environment. It
resolves the checkout root ONCE, as text, refusing when it cannot, and judges
only that root (`root` in the result). Each probe answers present, absent or
could-not-tell; could-not-tell never reads as absent. First match wins: an
incident file present or could-not-tell refuses; an unusable name, a class not
`nonProd`/`prod`, or a config layer could-not-tell or not ok asks; autopilot
off or `deploy: none` asks; `nonProd` allows under `nonprod`/`all`; `prod`
only under `all` with `environments.prodUnattended` true in BOTH layers and
`guards.cloudGuard` a plain `block`. A crash asks. The CLI prints one line per
stream (`--json` too), and `verdict=ask` even for a crash it cannot describe.

The consumer (T-0045, not built here) calls it immediately before each
dispatch, passes the class from T-0005's classifier, proceeds only on the exact
verdict `allow`, and persists every non-empty `report`. `allow` is necessary,
not sufficient: T-0009's hook, promote-gate and every other gate still decide.
"""
import argparse
import importlib
import json
import os
import re
import sys

if __name__ == "__main__":
    # Before the sibling imports: the direct CLI writes no bytecode either.
    sys.dont_write_bytecode = True

import crew_config
import crew_state
import crew_ticket
import review_ledger
from crew_common import git_out, read_text

AUTOPILOT = "/crew:autopilot"
# `autopilot.deploy` (T-0072): where a deploy may run without asking.
DEPLOY_VALUES = ("none", "nonprod", "all")
UNAVAILABLE = "unavailable"
FRESH = "fresh"
STALE = "stale"
UNKNOWN = "unknown"
UNSETTLED = "unsettled"
# T-0008's reason for the one `unknown` a refresh settles: the anchor names no
# commit here (a squash merge dropped it), and re-anchoring is the refresh.
ORPHANED_ANCHOR = "names no commit"
FALLBACK_BASE = "[fallback base]"
# Header statuses tried when naming a header-only approval change: T-0026's
# STATUS_VALUES plus older words. Such a change stales only a pre-T-0026
# receipt or a value outside STATUS_VALUES; the stop then says so.
HEADER_STATUSES = crew_ticket.STATUS_VALUES + ("ready", "direction", "implement")
REFRESH_UNAVAILABLE = "refresh-artifacts unavailable (T-0008 not landed)"
# INDEX.md status cells that say direction.md was approved: `/crew:brainstorm`
# step 5 writes `ready`, and every later phase's own word. Any other cell --
# blank, a typo, `parked` -- cannot tell, so it stops (a closed list, not "not
# `direction`").
DIRECTION_APPROVED = ("ready", "open", "spec", "planned", "approved", "in-progress",
                      "implement", "review")
INDEX_DONE = ("done", "closed", "merged", "shipped", "complete", "completed")

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
    # T-0029: crew_wave.py plan/start refuse the whole wave on it.
    ("scope-not-enforcing", "`/crew:autopilot wave` runs lanes only while scope.mode is "
                            "block for every lane ticket (crew_wave.scope_enforcing)"),
)
# A person, unless the T-0010 policy named says otherwise; `human` always stops.
HUMAN_STOPS = (
    ("brainstorm", "/crew:brainstorm and direction approval are a human dialogue"),
    ("plan-approval", ("plan approval: the human types /crew:approve <id>, unless "
                       "autopilot.approval allows `crew_autopilot.py approve` "
                       "(needs scope.allowCliApproval: true)")),
    ("review-acceptance", "accepting review FINDINGS is the owner's, at every setting"),
    ("open-questions", "an open question in direction.md, spec.md or plan.md is answered "
                       "by a person, unless autopilot.questions takes the researched "
                       "recommendation"),
)

# T-0018: the command's subcommands. A later ticket adds its name to AVAILABLE
# and drops it from ARRIVES when it replaces the router's stop.
SUBCOMMANDS = ("status", "run", "assign", "goal", "focus", "wave")
AVAILABLE = frozenset({"status", "run", "wave"})
ARRIVES = {"assign": "T-0019", "goal": "T-0012", "focus": "T-0020"}
GOAL_FLAG = "--goal"
UNKNOWN_SUB = ("unknown subcommand; one of " + "|".join(SUBCOMMANDS)
               + ", or a ticket id")
# The INDEX.md id shape, whole-string; [0-9], not \d, which is any Unicode digit.
_INDEX_ID = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")
# T-0029: a wave set's slug (T-0012's grammar); crew_wave.py reads it from here.
WAVE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
WAVE = "wave"
WAVE_ARGS = ("wave takes nothing, `--set <slug>` ([a-z0-9][a-z0-9-]{0,63}), or one or more "
             "ticket ids, never both")


def _rel(top, path):
    """`path` relative to `top` for evidence lines, or `path` itself when there
    is no relative form: on Windows a path on another drive than `top` makes
    `os.path.relpath` raise ValueError (T-0077)."""
    try:
        return os.path.relpath(path, top).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


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
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# An answered item: `none` or `n/a` alone or followed by a separator and the
# answer (`none - postgres`), checked `[x]`, or struck `~~`. `None of the
# owners has decided` is an open question, not an answer.
_ANSWERED = re.compile(r"^(?:(?:none|n/a)(?:$|\s*[-:,(\u2013\u2014])|\[x\]|~~|-$)")


def _open_items(text):
    """Unanswered items under any `Open questions` heading, at any level, down
    to the next heading of the same or a higher level -- a sub-heading inside
    the section stays inside it. See `_ANSWERED` for what counts as answered."""
    items, depth = [], 0
    for line in (text or "").splitlines():
        heading = _HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            if depth and level > depth:
                continue
            if title.lower().startswith("open questions"):
                depth, line = level, title[len("open questions"):]
            else:
                depth = 0
        if not depth:
            continue
        item = line.strip()
        for mark in _BULLET:
            if item.startswith(mark):
                item = item[len(mark):].strip()
        item = re.sub(r"^\d+[.)]\s*", "", item)
        bare = item.strip("\"'`.: ").lower()
        if not bare or _ANSWERED.match(bare):
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


def _phase(root, ticket, policy=True):
    """`next`'s phase table (module docstring), with no session guard.
    `policy=False` is `status`'s read: the approve and open-questions reasons
    then name no policy, so status reads the same under every setting."""
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
    if status in INDEX_DONE:
        return answer("closed", True, f".work/INDEX.md marks {ticket} `{status}`: never "
                      "re-driven, whatever spec.md's header says")
    if status not in DIRECTION_APPROVED:
        return answer("direction-approval", True, f"cannot tell whether {ticket}'s "
                      f"direction is approved: its .work/INDEX.md status is `{status}`, not one "
                      f"of {', '.join(DIRECTION_APPROVED)}. The human sets it to `ready` once "
                      "direction.md is agreed")
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
                      + " - a person answers (write `none - <answer>` or check it `[x]`). "
                      + (_question_hint(top, ticket) if policy else POLICY_FREE_QUESTIONS))
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
            f"`status: {_header_status(crew_ticket._text(contract['spec.md']))}`), an edit "  # pylint: disable=protected-access
            "T-0026's approval digest keeps only for a receipt written since T-0026 and a "
            "value in crew_ticket.STATUS_VALUES; this one is older or the value is not")
        hint = (_approval_hint(top, ticket) if policy
                else POLICY_FREE_APPROVE.format(ticket=ticket))
        return answer("approve", True, f"{why}. {hint}", f"/crew:approve {ticket}")
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
                      "spent; a different plan continues it once approved (the approve "
                      "phase and autopilot.approval decide by whom)",
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


def next_phase(root, ticket, phases_run=0, last_command=None, max_phases=None,
               policy=True):
    """`{"ticket", "phase", "stop", "reason", "command", "evidence"}`. A
    `stop` phase's `command` is what the HUMAN types, never run by autopilot.
    `max_phases` and `last_command` are the session's count and the command it
    last ran: reaching the count, or being handed the same command again, stops.
    So does a phase that would run while `crew_ticket.resolve_active` -- what
    the scope guard reads -- names another ticket, none, or a broken pointer.
    `policy=False` is `status`'s: see `_phase`."""
    crew_ticket.check_ticket(ticket)
    result = _phase(root, ticket, policy)
    if result["stop"]:
        return result
    active, where, broken = crew_ticket.resolve_active(
        crew_ticket.toplevel(root) or os.path.abspath(root))
    if broken or active != ticket:
        return dict(result, stop=True, reason=(
            f"ticket mismatch: the scope guard and completion audit judge edits by "
            f"{active or 'no ticket'} ({where}), not {ticket}, so {result['command']} would "
            f"run under the wrong approval and Touch - run crew_autopilot.py resume, or the "
            f"human runs crew_ticket.py activate --ticket {ticket}"))
    if max_phases is not None and phases_run >= max_phases:
        return dict(result, stop=True, reason=(
            f"autopilot.maxPhases ({max_phases}) reached after {phases_run} phases; next "
            f"would be {result['phase']} - run /crew:autopilot {ticket} again"))
    if last_command and result["command"] == last_command:
        return dict(result, stop=True, reason=(
            f"no progress: {last_command} ran and the files on disk still name it "
            f"({result['reason']}) - a human looks at why"))
    return result


HANDOFF_ABSENT = "no .work/HANDOFF.md"
HANDOFF_UNREADABLE = "unknown - .work/HANDOFF.md exists but could not be read"


def _read_handoff(top):
    """(text, why_not): `.work/HANDOFF.md`'s text, or None with why. Only a
    file that is not there is absent; one that is there and cannot be read
    -- denied, a directory, a dangling or looping symlink, or a `.work` that
    is a dangling symlink -- is unknown, never absent (read_text says None
    for all of them)."""
    work = os.path.join(top, ".work")
    path = os.path.join(work, "HANDOFF.md")
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read(), ""
    except FileNotFoundError:
        # open() follows links: a dangling one raises this too, but its entry is there.
        if os.path.lexists(path) or (os.path.lexists(work) and not os.path.isdir(work)):
            return None, HANDOFF_UNREADABLE
        return None, HANDOFF_ABSENT
    except (OSError, ValueError):
        return None, HANDOFF_UNREADABLE


def _handoff_ticket(top):
    """(ticket, hint, stop_reason, why_not) from `.work/HANDOFF.md`."""
    text, why = _read_handoff(top)
    if text is None:
        return None, "", None, why
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


def resume_target(root, ticket=None, policy=True):
    """`{"ticket", "source", "stop", "hint", "disagreement", "reason",
    "fallthrough", "next", "activate"}` -- see the module docstring's order.
    `ticket` is the command's `$1`; it is still held to the active pointer.
    `policy=False` is `status`'s: see `_phase`."""
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
    disk = next_phase(top, ticket, policy=policy)
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


def _unreadable_autopilot(top):
    """Why the repo's `autopilot` block cannot be told, or "" when it can.
    `crew_config.resolve_config` collapses a malformed file, and
    `merge_defaults` a non-object block, to the defaults; this reads the raw
    file first so neither collapse is taken for a configured value."""
    data, state = crew_ticket._read_json(  # pylint: disable=protected-access
        os.path.join(top, ".crew", "config.json"))
    if state == "corrupt":
        return ".crew/config.json exists but could not be read as JSON"
    if state == "ok" and not isinstance(data, dict):
        return (f".crew/config.json is {type(data).__name__}, not a JSON object, so it "
                "could not be read")
    block = data.get("autopilot") if state == "ok" else None
    if block is not None and not isinstance(block, dict):
        return f"autopilot in .crew/config.json is {block!r}, not an object"
    return ""


def settings(root):
    """`{"mode", "armed", "maxPhases", "saw", "deploy", "deploySaw", "approval",
    "questions", "warnings"}`. Read through `crew_config.resolve_config` --
    `.crew/config.json` over the defaults, the file
    `crew_ticket.cli_approval_allowed` reads. `mode` arms only when it is
    exactly the string `plan`; `maxPhases` must be a positive int, else 12;
    `deploy` is exactly one of DEPLOY_VALUES, else `none`; `approval` and
    `questions` must be one of POLICIES, else `human`.

    A `.crew/config.json` that is present but unreadable, or an `autopilot`
    value that is not an object, is could-not-tell: both policies read
    UNKNOWN, `mode` reads `off`, `deploy` reads `none`, and a warning names
    the cause. That is never the default `risk`, which `resolve_config` would
    otherwise hand back for both. An absent file or an absent (or null) block
    is known and reads the defaults. `deploy_allowed` reads `_settings_at`,
    after its own per-layer checks, not this."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    cause = _unreadable_autopilot(top)
    if cause:
        return {"mode": "off", "armed": False,
                "maxPhases": crew_state.AUTOPILOT_DEFAULTS["maxPhases"],
                "saw": None, "deploy": "none", "deploySaw": None,
                "approval": UNKNOWN, "questions": UNKNOWN,
                "warnings": [(f"{cause}, so autopilot.approval and autopilot.questions "
                              "could not be told (both read as unknown, which never "
                              "approves or takes an answer) and autopilot reads as off")]}
    return _settings_at(top)


def _settings_at(top):
    """`settings` for a checkout root already resolved: no lookup of its own,
    so `deploy_allowed` reads the settings of the one root it judged."""
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
    deploy_saw = block.get("deploy", "none")
    deploy = deploy_saw if _exact(deploy_saw, DEPLOY_VALUES) else "none"
    if deploy != deploy_saw:
        warnings.append(f"autopilot.deploy is {deploy_saw!r}: only the exact strings "
                        "'nonprod' and 'all' arm it, so it reads as none")
    if deploy != "none":
        warnings.append(f"autopilot.deploy is {deploy!r}, but nothing in this crew version "
                        "dispatches a deploy: T-0045 consumes it; deploy-allowed answers "
                        "the policy only")
    crew_json = _read_json(os.path.join(top, ".crew", "crew.json"))
    if isinstance(crew_json, dict) and "autopilot" in crew_json \
            and "autopilot" not in crew_state.load_config(top):
        warnings.append("autopilot is set in .crew/crew.json, which crew does not read "
                        "for this key; move it to .crew/config.json")
    policies = {}
    for key in ("approval", "questions"):
        policies[key], warning = _policy_setting(block, key)
        warnings += [warning] if warning else []
    return {"mode": "plan" if armed else "off", "armed": armed, "maxPhases": limit,
            "saw": mode, "deploy": deploy, "deploySaw": deploy_saw,
            "approval": policies["approval"], "questions": policies["questions"],
            "warnings": warnings}


def _exact(value, allowed):
    """`value` is one of the strings in `allowed`, compared as a string: `True`
    and `1` compare equal to nothing here, and neither does `"All"`."""
    return isinstance(value, str) and value in allowed


def _probe(path):
    """`("present" | "absent" | "could-not-tell", detail)` for one path: the
    only place this module asks whether a path exists. The try holds the one
    `os.lstat`. Only a missing file (or a missing directory on the way) is
    absent; anything else raised -- PermissionError, ELOOP, a NUL, a crash --
    could not tell, and never reads as absent (`os.path.lexists` would)."""
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return "absent", ""
    except Exception as exc:  # pylint: disable=broad-except
        return "could-not-tell", type(exc).__name__
    return "present", ""


def _resolve_root(root):
    """`(top, "")`, or `(None, problem)`: the checkout root, looked up ONCE
    per `deploy_allowed` and passed to everything after it. The try holds the
    one lookup, so its failure is never mistaken for a missing file. A root
    that is not text (a bytes path) is a problem too: every path after this
    joins str parts onto it, and that join must not be able to raise."""
    try:
        top = crew_ticket.toplevel(root) or os.path.abspath(root)
    except Exception as exc:  # pylint: disable=broad-except
        return None, f"could not find the checkout ({type(exc).__name__})"
    if not isinstance(top, str):
        return None, f"could not find the checkout (a {type(top).__name__} path, not text)"
    return top, ""


def _layer_problem(label, path):
    """Why the `label` config layer at `path` cannot be relied on, or `""`
    when it is absent or ok. `layer_state` is asked only about a path the
    probe saw present, so its `absent` (a `lexists` that could not tell) is a
    contradiction and asks, never a layer nobody set."""
    state, detail = _probe(path)
    if state == "absent":
        return ""
    if state != "present":
        return f"could not tell whether the {label} config layer can be read ({detail})"
    if crew_config.layer_state(path, environments=True) != "ok":
        return f"could not read the {label} config layer"
    return ""


def _decide(top, env_name, env_class, machine_path):
    """`(verdict, reason, deploy)`, the Design table's rows 1-11 in order, for
    the root `top` that `deploy_allowed` resolved; never looks it up again.
    The incident probe runs first, ahead of the `cloud_guard` import: a
    failure after it asks, and asking would downgrade an emergency's refusal."""
    state, detail = _probe(os.path.join(top, ".crew", "incident.json"))
    if state == "present":
        return "refuse", "an emergency may be active (.crew/incident.json exists)", None
    if state != "absent":
        return "refuse", f"could not tell whether an emergency is active ({detail})", None
    import cloud_guard  # pylint: disable=import-outside-toplevel
    if not isinstance(env_name, str) or not env_name.strip() or not env_name.isprintable():
        return "ask", f"could not tell which environment: {_safe_text(env_name)}", None
    known = (cloud_guard.ENV_NONPROD, cloud_guard.ENV_PROD)
    cls = env_class if isinstance(env_class, str) else ""
    if cls not in known:
        return "ask", (f"crew could not classify {env_name} "
                       f"(class {_safe_text(env_class)})"), None
    layers = (("repo", os.path.join(top, ".crew", "config.json")),
              ("machine", machine_path))
    for label, path in layers:
        problem = _layer_problem(label, path)
        if problem:
            return "ask", problem, None
    current = _settings_at(top)
    deploy = current["deploy"]
    if not current["armed"]:
        return "ask", "autopilot.mode is not plan", deploy
    if deploy == "none":
        return "ask", "autopilot.deploy is none", deploy
    if cls == cloud_guard.ENV_NONPROD:
        return "allow", f"autopilot.deploy={deploy} allows nonProd", deploy
    if deploy != "all":
        return "ask", "autopilot.deploy is nonprod; production needs all", deploy
    ratchet = crew_config.resolve_ratcheted(top, "environments.prodUnattended",
                                            path=machine_path)
    if ratchet["effective"] is not True:
        short = [name for name, key in (("repo", "repo"), ("machine", "global"))
                 if ratchet[key] is not True]
        where = " and ".join(short) or f"held down by {ratchet['heldDownBy']}"
        return "ask", (f"environments.prodUnattended is not true in the {where} config "
                       "layer; production needs true in both"), deploy
    mode = cloud_guard.resolve_mode(top)
    if mode != ("block", ""):
        note = f": {mode[1]}" if mode[1] else ""
        return "ask", (f"guards.cloudGuard is {mode[0]}{note}, so T-0009's guard is not "
                       "armed to enforce the dispatch"), deploy
    return "allow", ("autopilot.deploy=all and environments.prodUnattended=true in both "
                     "config layers (repo and machine), guards.cloudGuard=block"), deploy


def _safe_text(value, render=repr):
    """`render(value)`, or a placeholder naming its type when that raises: a
    value crew cannot print is still one it can name in a reason."""
    try:
        return render(value)
    except Exception:  # pylint: disable=broad-except
        return f"<unprintable {type(value).__name__}>"


def _crash_reason(exc):
    return (f"crew_autopilot raised {type(exc).__name__}: {_safe_text(exc, str)} - "
            "cannot tell, so ask")


def _env_label(env_name):
    usable = isinstance(env_name, str) and env_name.strip() and env_name.isprintable()
    return env_name if usable else _safe_text(env_name)


def _deploy_report(env_name, verdict, reason, env_class):
    """The line every production decision carries, `""` for any other class."""
    if env_class != "prod":
        return ""
    return f"unattended production: {_env_label(env_name)} {verdict} - {reason}"


def deploy_allowed(root, env_name, env_class):
    """`{"verdict", "reason", "report", "env", "envClass", "deploy", "root"}`
    for one environment: may autopilot deploy there without asking a person?
    Read-only and never raises; "could not tell" asks and an emergency
    refuses. The checkout root is resolved once, here, and `root` names it. See
    the module docstring's `deploy-allowed` section for the rows and the
    consumer contract."""
    top, problem = _resolve_root(root)
    machine_path = crew_config.GLOBAL_CONFIG_PATH
    deploy = None
    try:
        if problem:
            verdict, reason = "refuse", f"could not tell whether an emergency is active: {problem}"
        else:
            verdict, reason, deploy = _decide(top, env_name, env_class, machine_path)
    except Exception as exc:  # pylint: disable=broad-except
        # A crash cannot tell whether production is allowed: it asks.
        verdict, reason = "ask", _crash_reason(exc)
    try:
        report = _deploy_report(env_name, verdict, reason, env_class)
    except Exception as exc:  # pylint: disable=broad-except
        # Which environment, or whether it is production, cannot be told: the
        # decision asks (a refusal stays one, with its reason) and is reported.
        if verdict != "refuse":
            verdict, reason = "ask", _crash_reason(exc)
        report = f"unattended production: <unnamed environment> {verdict} - {reason}"
    return {"verdict": verdict, "reason": reason, "report": report,
            "env": env_name, "envClass": env_class, "deploy": deploy, "root": top}


# --- T-0010: the approval and questions policies ------------------------------

POLICIES = ("human", "self", "risk")
HUMAN, SELF, RISK = POLICIES
TAKE, STOP = "take", "stop"
ALLOW_CLI = "scope.allowCliApproval"


def _policy_setting(block, key):
    """(policy, warning). Anything but one of POLICIES -- a typo, a bool, a
    list -- is `human`, which always stops: an unreadable policy is never
    read as permission."""
    value = block.get(key, crew_state.AUTOPILOT_DEFAULTS[key])
    if isinstance(value, str) and value in POLICIES:
        return value, ""
    return HUMAN, (f"autopilot.{key} is {value!r}, not one of {'|'.join(POLICIES)}; it "
                   "reads as human, which always stops")


def _ticket_risk(top, ticket):
    """`crew_ticket.parse_risk` of the spec's header; a spec that is missing
    or unreadable is `high`, unknown -- never `low`. So is a header naming
    `risk:` more than once (`# T-9 cut risk: low paths  status: spec  risk:
    high`): parse_risk takes the first, and which one the owner meant cannot
    be told, so neither is trusted to grant anything."""
    try:
        spec = crew_ticket.read_contract(top, ticket)["spec.md"]
        text = crew_ticket._text(spec) if spec is not None else ""  # pylint: disable=protected-access
    except (crew_ticket.TicketError, OSError, ValueError):
        text = ""
    if len(re.findall(r"\brisk:", crew_ticket.header_line(text), re.IGNORECASE)) > 1:
        return {"risk": "high", "known": False}
    return crew_ticket.parse_risk(text)


def _decision(top, ticket, key):
    """(policy, risk, warnings), or raises when the settings cannot be read."""
    conf = settings(top)
    return conf[key], _ticket_risk(top, ticket), [
        w for w in conf["warnings"] if f"autopilot.{key} " in w]


def _risk_words(risk):
    return (f"risk: {risk['risk']}" if risk["known"]
            else "no risk: low|med|high in the spec header (reads as high)")


def approval_policy(root, ticket):
    """`{"allow", "policy", "risk", "known", "reason", "warnings"}` -- whether
    autopilot may approve `ticket`'s plan itself. Never allows unless
    `scope.allowCliApproval` is exactly true, at any setting; `human` never,
    `self` at any risk, `risk` only on a known `risk: low`. A NEEDS_REPLAN
    ledger is no refusal: approving a distinct successor plan is the only way
    out of it, and `crew_ticket.approve` hands that plan to
    `review_ledger.continue_with_successor_plan`, which refuses one approved
    before. An unreadable ledger refuses, like anything that cannot be told."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    try:
        policy, risk, warnings = _decision(top, ticket, "approval")
        allowed = crew_ticket.cli_approval_allowed(top)
        ledger = review_ledger.status(top, ticket).get("state")
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return {"allow": False, "policy": UNKNOWN, "risk": "high", "known": False,
                "warnings": [], "reason": (f"could not tell whether autopilot may approve "
                                           f"({type(exc).__name__}: {exc})")}
    result = {"allow": False, "policy": policy, "risk": risk["risk"],
              "known": risk["known"], "warnings": warnings}
    if policy == UNKNOWN:
        why = (f"could not tell autopilot.approval ({'; '.join(warnings) or 'unreadable'}); "
               "the human approves")
    elif not allowed:
        why = (f"{ALLOW_CLI} is not exactly true in .crew/config.json, so no approval but "
               "the human's counts")
    elif policy == HUMAN:
        why = "autopilot.approval is human: plan approval always waits for the owner"
    elif ledger == review_ledger.UNKNOWN:
        why = ("the review ledger is unreadable, so whether this plan may continue review "
               "cannot be told; the human approves")
    elif policy == SELF:
        return dict(result, allow=True, reason=f"autopilot.approval is self ({_risk_words(risk)})")
    elif risk["known"] and risk["risk"] == "low":
        return dict(result, allow=True, reason="autopilot.approval is risk and the spec "
                    "header says risk: low")
    else:
        why = f"autopilot.approval is risk and the spec has {_risk_words(risk)}"
    return dict(result, reason=why)


def question_policy(root, ticket):
    """`{"action": take|stop, "policy", "risk", "known", "reason", "warnings"}`
    for an open question whose researched options are in questions.md. `human`
    stops, `self` takes the recommendation, `risk` takes it only on a known
    `risk: low`. No `allowCliApproval` rule; anything unreadable stops."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    try:
        policy, risk, warnings = _decision(top, ticket, "questions")
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return {"action": STOP, "policy": UNKNOWN, "risk": "high", "known": False,
                "warnings": [], "reason": (f"could not tell the questions policy "
                                           f"({type(exc).__name__}: {exc})")}
    result = {"action": STOP, "policy": policy, "risk": risk["risk"],
              "known": risk["known"], "warnings": warnings}
    if policy == UNKNOWN:
        return dict(result, reason=(f"could not tell autopilot.questions "
                                    f"({'; '.join(warnings) or 'unreadable'}): a person answers"))
    if policy == SELF:
        return dict(result, action=TAKE, reason="autopilot.questions is self")
    if policy == RISK and risk["known"] and risk["risk"] == "low":
        return dict(result, action=TAKE, reason="autopilot.questions is risk and the "
                    "spec header says risk: low")
    if policy == HUMAN:
        return dict(result, reason="autopilot.questions is human: a person answers")
    return dict(result, reason=f"autopilot.questions is risk and the spec has "
                               f"{_risk_words(risk)}")


# `status`'s approve and open-questions sentences: fixed text, so the report
# reads the same under every autopilot.approval and autopilot.questions value
# (T-0018's status reads no policy; `next` names the policy's route instead).
POLICY_FREE_APPROVE = ("The human types /crew:approve {ticket}. status reads no approval "
                       "policy: crew_autopilot.py settings shows whether autopilot.approval "
                       "lets /crew:autopilot approve it instead")
POLICY_FREE_QUESTIONS = ("status reads no questions policy: crew_autopilot.py settings shows "
                         "whether autopilot.questions lets /crew:autopilot research and "
                         "answer them instead")


def _approval_hint(top, ticket):
    """The approve phase's second sentence: which route approves, and why."""
    got = approval_policy(top, ticket)
    if got["allow"]:
        return (f"{got['reason']}: autopilot runs crew_autopilot.py approve --root . "
                f"--ticket {ticket}, and reports it")
    return f"Only the human types /crew:approve {ticket} ({got['reason']})"


def _question_hint(top, ticket):
    got = question_policy(top, ticket)
    return (f"autopilot.questions: action={got['action']} ({got['reason']}); research, "
            f"write questions.md, then crew_autopilot.py questions-check --ticket {ticket}")


def approve(root, ticket):
    """(exit code, text). This module's one writing path, only when autopilot
    is armed and `approval_policy` allows: `crew_ticket.approve` with
    `via=autopilot`, which asks `approval_policy` again and then writes
    `approval.json`, `scope-tickets.json` on a ticket's first approval, and,
    for a distinct successor plan under a NEEDS_REPLAN ledger, the ledger
    moved NEEDS_REPLAN -> IN_REVIEW. Exit 3 when that continuation refused."""
    crew_ticket.check_ticket(ticket)
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    human = f"the human types /crew:approve {ticket}"
    if not settings(top)["armed"]:
        return 2, (f"refused: autopilot.mode is not plan, so autopilot approves nothing; "
                   f"{human}")
    got = approval_policy(top, ticket)
    if not got["allow"]:
        return 2, f"refused: {got['reason']}; {human}"
    _receipt, successor = crew_ticket.approve(
        top, ticket, by=f"autopilot:{got['policy']}", via=crew_ticket.AUTOPILOT)
    text = (f"self-approved {ticket} under approval={got['policy']}, "
            f"risk={got['risk'] if got['known'] else 'unknown (high)'}")
    if successor is not None and not successor[0]:
        return 3, f"{text}\nreview is still NEEDS_REPLAN -- {successor[1]}"
    return 0, text


QUESTIONS_SHAPE = (
    "## Q1: <the question, one line>",
    "Research: <what crew:explorer (repo) and crew:researcher (outside) found, sourced>",
    "### Option A (recommended): <title>   <- the recommendation is always first",
    "Cost: <what choosing it costs>",
    "### Option B: <title>   <- 2 to 4 options, each with its Cost: line",
    "Cost: <what choosing it costs>",
    "taken: Option A by autopilot (<policy>)   <- only once autopilot took it",
)
RECOMMENDED = "(recommended)"
_Q_RE = re.compile(r"^##[ \t]+Q([0-9]+)\b[ \t]*:?[ \t]*(.*)$")
_OPTION_RE = re.compile(r"^###[ \t]+Option[ \t]+([A-Za-z0-9]+)\b(.*)$")
_COST_RE = re.compile(r"^(?:[-*][ \t]+)?Cost:[ \t]*\S")
_RESEARCH_RE = re.compile(r"^(?:[-*][ \t]+)?Research:[ \t]*\S")
_TAKEN_RE = re.compile(r"^taken:[ \t]*(.*?)[ \t]*$")
_TAKEN_FORM = re.compile(r"^Option[ \t]+([A-Za-z0-9]+)[ \t]+by autopilot[ \t]+\(([^()]*)\)$")


def _question_blocks(text):
    """[(number, title, preamble, options, taken)] -- each `## Q<n>` section;
    `options` is [(id, rest, lines)], `taken` every `taken:` value in it. A
    `#`/`##` heading that is not a question ends the section."""
    blocks, current, option = [], None, None
    for line in (text or "").splitlines():
        found = _Q_RE.match(line)
        if found:
            current = (found.group(1), found.group(2).strip(), [], [], [])
            blocks.append(current)
            option = None
            continue
        if re.match(r"^#{1,2}[ \t]", line):
            current = option = None
            continue
        if current is None:
            continue
        taken = _TAKEN_RE.match(line)
        if taken:
            current[4].append(taken.group(1))
            continue
        heading = _OPTION_RE.match(line)
        if heading:
            option = (heading.group(1), heading.group(2), [])
            current[3].append(option)
            continue
        (option[2] if option is not None else current[2]).append(line)
    return blocks


def _question_problems(block, decision):
    """(problems, taken) for one `## Q<n>` section, judged against the
    questions policy in force (`decision`, from `question_policy`). A `taken:`
    line's `(<policy>)` records the policy that took it, which may differ from
    today's: it must name one that takes (`self` or `risk`), and today's must
    say `take`."""
    number, title, preamble, options, taken = block
    name, problems = f"Q{number}", []
    if not title:
        problems.append(f"{name}: the heading states no question")
    if not any(_RESEARCH_RE.match(line) for line in preamble):
        problems.append(f"{name}: no Research: line before the options - research it first")
    if not 2 <= len(options) <= 4:
        problems.append(f"{name}: {len(options)} options; it needs 2-4")
    marked = [oid for oid, rest, _lines in options if RECOMMENDED in rest]
    if not options or RECOMMENDED not in options[0][1] or len(marked) != 1:
        problems.append(f"{name}: the first option, and only it, must be marked "
                        f"{RECOMMENDED}")
    problems += [f"{name}: Option {oid} has no Cost: line" for oid, _rest, lines in options
                 if not any(_COST_RE.match(line) for line in lines)]
    reported = []
    if len(taken) > 1:
        problems.append(f"{name}: {len(taken)} taken: lines; at most one")
    for value in taken[:1]:
        form = _TAKEN_FORM.match(value)
        if not form:
            problems.append(f"{name}: taken: {value!r} is not "
                            "`Option <id> by autopilot (<policy>)`")
            continue
        oid, policy = form.groups()
        if not options or oid != options[0][0]:
            problems.append(f"{name}: taken Option {oid}, not the recommended option")
        # The name is history: the policy that took it then. It must be one
        # that can take at all; whether taking is allowed NOW is the next check.
        if policy not in (SELF, RISK):
            problems.append(f"{name}: taken under {policy!r}, a policy that never takes "
                            f"(only {SELF} or {RISK} does)")
        if decision["action"] != TAKE:
            problems.append(f"{name}: taken, but the questions policy says stop: "
                            f"{decision['reason']}")
        reported.append(f"{name}: {value}")
    return problems, reported


def questions_check(root, ticket):
    """`{"valid", "action", "policy", "risk", "known", "reason", "warnings",
    "questions", "taken", "problems"}` for `.work/tickets/<id>/questions.md`.
    Valid only when every question has the QUESTIONS_SHAPE and every
    `taken:` line names a policy that takes, while the policy in force says
    `take` (`_question_problems`)."""
    crew_ticket.check_ticket(ticket)
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    decision = question_policy(top, ticket)
    path = os.path.join(crew_ticket.ticket_dir(top, ticket), "questions.md")
    blocks = _question_blocks(read_text(path))
    problems, taken = [], []
    if not blocks:
        problems.append(f"{_rel(top, path)} has no `## Q<n>` question")
    numbers = [block[0] for block in blocks]
    problems += [f"Q{n}: numbered twice" for n in sorted(set(numbers)) if numbers.count(n) > 1]
    for block in blocks:
        found, reported = _question_problems(block, decision)
        problems += found
        taken += reported
    return dict(decision, valid=not problems, questions=len(blocks), taken=taken,
                problems=problems)


def questions_text(result):
    risk = result["risk"] if result.get("known") else "high(unknown)"
    lines = [_line(valid=int(result["valid"]), action=result["action"],
                   policy=result["policy"], risk=risk, questions=result["questions"],
                   taken=len(result["taken"]), reason=result["reason"])]
    lines += [f"problem: {p}" for p in result["problems"]]
    lines += [f"taken: {t}" for t in result["taken"]]
    lines += [f"warning: {w}" for w in result["warnings"]]
    if not result["valid"]:
        lines += ["shape:"] + [f"  {row}" for row in QUESTIONS_SHAPE]
    return "\n".join(lines)


def stops():
    """Every stop, from code: AUTONOMOUS_STOPS, the fixed ones, the human ones."""
    def rows(pairs):
        return [{"id": slug, "text": text} for slug, text in pairs]
    return {"autonomous": rows(crew_state.AUTONOMOUS_STOPS), "fixed": rows(FIXED_STOPS),
            "human": rows(HUMAN_STOPS), "procedure": rows(PROCEDURE_STOPS)}


def _existing_ticket(top, token):
    """Whether `token` is a plain ticket id naming a `.work/tickets/` folder."""
    try:
        return os.path.isdir(crew_ticket.ticket_dir(top, token))
    except crew_ticket.TicketError:
        return False


def route(root, first):
    """`{"sub", "stop", "reason"}` for the command's first argument. First
    match, exact and case-sensitive: a SUBCOMMANDS name; nothing or `--goal`
    (run); an INDEX-shaped id or an existing `.work/tickets/<token>/` (run).
    Anything else stops: `crew_ticket` accepts `stauts` as an id, so a typo
    is refused here rather than driven as a ticket."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    token = first or ""
    if token in SUBCOMMANDS:
        sub = token
    elif token == "":
        sub = "run"
    elif token == GOAL_FLAG:
        return {"sub": "run", "stop": True,
                "reason": f"run {GOAL_FLAG} <slug> arrives with {ARRIVES['goal']}"}
    elif _INDEX_ID.fullmatch(token) or _existing_ticket(top, token):
        sub = "run"
    else:
        return {"sub": "", "stop": True, "reason": UNKNOWN_SUB}
    if sub not in AVAILABLE:
        return {"sub": sub, "stop": True,
                "reason": f"{AUTOPILOT} {sub} arrives with {ARRIVES.get(sub, 'a later ticket')}"}
    return {"sub": sub, "stop": False, "reason": ""}


NOT_A_TICKET = ("not a ticket id: at most one, INDEX-shaped (T-0018) or naming an "
                "existing .work/tickets/<id>/")


def route_args(root, text):
    """`route` for the command's whole argument string, plus `ticket`: the
    word after a subcommand, or a bare ticket id itself. The command passes
    `$ARGUMENTS` whole because Claude Code numbers positional arguments from
    `$0` and leaves an out-of-range `$N` literal. A second word that is not a
    ticket, or a third word, stops; it is never read as a ticket. `wave`
    (T-0029) also gets `set` and `tickets`: `wave --set <slug>` or
    `wave <id> <id>...`, parsed by `_wave_args`."""
    return dict({"set": "", "tickets": []}, **_route_args(root, text))


def _wave_args(top, got, rest):
    """`wave`'s arguments: nothing, `--set <slug>`, or ticket ids -- each an
    INDEX-shaped id or an existing ticket folder, once. Anything else stops."""
    base = dict(got, ticket="", set="", tickets=[])
    if not rest:
        return base
    if rest[0] == "--set":
        if len(rest) == 2 and WAVE_SLUG.fullmatch(rest[1]):
            return dict(base, set=rest[1])
        return dict(base, stop=True, reason=WAVE_ARGS)
    if len(set(rest)) == len(rest) and all(_INDEX_ID.fullmatch(w) or _existing_ticket(top, w)
                                           for w in rest):
        return dict(base, tickets=list(rest))
    return dict(base, stop=True, reason=WAVE_ARGS)


def _route_args(root, text):
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    words = (text or "").split()
    got = dict(route(top, words[0] if words else ""), ticket="")
    if got["stop"]:
        return got
    rest = words[1:] if words and words[0] in SUBCOMMANDS else words
    if words[:1] == [WAVE]:
        return _wave_args(top, got, rest)
    if words[:1] == ["run"] and rest[:1] == [GOAL_FLAG]:
        return dict(route(top, GOAL_FLAG), ticket="")
    if len(rest) > 1 or (rest and not (_INDEX_ID.fullmatch(rest[0])
                                       or _existing_ticket(top, rest[0]))):
        return dict(got, stop=True, reason=NOT_A_TICKET)
    return dict(got, ticket=rest[0] if rest else "")


# Who acts when `next` stops at each phase it names. A phase not here -- a
# rename, `invalid` from a crash -- reads `unknown`, never `autopilot`.
WAITING = {phase: "owner" for phase in (
    "brainstorm", "direction-approval", "open-questions", "spec", "plan", "approve",
    "review", "replan", "implement", "accept-review", "refresh", "stale-after-review",
    "done")}
WAITING["closed"] = "nobody"
STATUS_MAX_LINES = 12
# The states `review_ledger.status` reports for a ledger it could read. Its
# UNKNOWN is also a string a file can hold, with a count computed beside it.
LEDGER_STATES = ("EMPTY", review_ledger.IN_REVIEW, review_ledger.REVIEWED,
                 review_ledger.ACCEPTED, review_ledger.NEEDS_REPLAN)
T0006_UNAVAILABLE = "unavailable (T-0006 not landed)"


def _reserved_round(top, ticket):
    """Whether the latest round under the current plan is reserved, unfinished."""
    try:
        rounds = _current_rounds(review_ledger.status(top, ticket))
    except Exception:  # pylint: disable=broad-except
        return False
    return bool(rounds) and rounds[-1].get("status") != "completed"


def _bare(top):
    """What bare `/crew:autopilot` would take: `resume_target(top)`, or None
    when it raised -- could not tell, which is never read as agreeing. Read
    with no policy, as everything status composes is."""
    try:
        return resume_target(top, policy=False)
    except Exception:  # pylint: disable=broad-except
        return None


def _takes(bare, ticket, source=None):
    """Whether bare `/crew:autopilot` drives `ticket` (from `source`, if named)."""
    return (bare is not None and not bare.get("stop") and bare.get("ticket") == ticket
            and source in (None, bare.get("source")))


def _waiting(top, result, bare):
    phase, command = result.get("phase"), result.get("command")
    who = WAITING.get(phase, UNKNOWN)
    if who == UNKNOWN:
        return f"unknown (phase {phase!r} is not one status maps)"
    if who == "nobody":
        return "nobody - the ticket is closed"
    if phase == "review" and result.get("stop") and _reserved_round(top, result["ticket"]):
        return "reviewer - a round is reserved with no result"
    if not result.get("stop"):
        # Bare `/crew:autopilot` reads the handoff before any argument, so it
        # is named only when it would drive this same ticket.
        if _takes(bare, result["ticket"]):
            return f"autopilot - run {AUTOPILOT} to continue"
        return f"autopilot - run {_drive(result['ticket'])} to continue"
    try:
        guard = not _phase(top, result["ticket"], policy=False)["stop"]
    except Exception:  # pylint: disable=broad-except
        return "unknown (could not tell which check stopped the phase)"
    if guard:
        return _repoint(top, result["ticket"])
    return f"owner - types {command}" if command else "owner - see the phase reason"


def _repoint(top, ticket):
    """Who clears a stop `next_phase` made on the active pointer, not the phase:
    its `command` is what autopilot would run, never what the owner types."""
    active, where, broken = crew_ticket.resolve_active(top)
    if broken:
        return ("owner - fixes the broken active-ticket pointer: "
                f"crew_ticket.py activate --ticket {ticket}")
    if where != "active-ticket":
        return f"autopilot - run {_drive(ticket)} to continue; it activates {ticket} first"
    repoint = f"owner - re-points this worktree: crew_ticket.py activate --ticket {ticket}"
    try:
        closed = _closed(top, active)
    except Exception:  # pylint: disable=broad-except
        closed = None
    if closed is None:
        return f"{repoint} (could not tell whether {active} is still open)"
    if closed:
        return f"{repoint} ({active} is closed)"
    return f"{repoint}, or runs {_drive(active)}"


def _drive(ticket):
    """The command that drives `ticket`. `route` reads a SUBCOMMANDS name as
    the subcommand, so a ticket named like one is driven as `run <id>`; every
    other id keeps the bare `/crew:autopilot <id>` form."""
    if ticket in SUBCOMMANDS:
        return f"{AUTOPILOT} run {ticket}"
    return f"{AUTOPILOT} {ticket}"


def _closed(top, ticket):
    """Whether either fact `next` closes a ticket on says so: INDEX.md's status
    or spec.md's `status: done` header. Read directly, because `_phase` checks
    direction.md first and a closed ticket without one reads `brainstorm`."""
    if _index_status(top, ticket) in INDEX_DONE:
        return True
    spec = crew_ticket.read_contract(top, ticket)["spec.md"]
    # read_contract returns None for a spec it could not read as well as for an
    # absent one; only absence says "not closed".
    if spec is None and os.path.lexists(os.path.join(crew_ticket.ticket_dir(top, ticket),
                                                     "spec.md")):
        return None
    return spec is not None and _header_status(
        crew_ticket._text(spec)) == "done"  # pylint: disable=protected-access


def _review(top, ticket):
    """The ledger's rounds, or `unknown`: a corrupt ledger has no `rounds_left`,
    and a missing count is never read as the budget. A ledger whose state is
    UNKNOWN, or one review_ledger never writes, still gets a count computed
    from its rounds; that count is never printed."""
    try:
        ledger = review_ledger.status(top, ticket)
    except Exception:  # pylint: disable=broad-except
        return "unknown (ledger unreadable)"
    state = ledger.get("state")
    if state == review_ledger.UNKNOWN:
        return "unknown (ledger unreadable)"
    if state not in LEDGER_STATES:
        return "unknown (ledger state is not one review_ledger writes)"
    left = ledger.get("rounds_left")
    if isinstance(left, bool) or not isinstance(left, int):
        return "unknown (ledger unreadable)"
    return f"{state}, {left} of {ledger.get('budget')} rounds left"


def _resume_line(top, bare):
    """The handoff's `resume:` line and whether bare `/crew:autopilot` --
    `bare`, `resume_target`'s answer -- takes it. Only `crew_resume`'s own
    fixed reasons, its re-rendered tokens and `resume_target`'s stop reason
    are shown; nothing is echoed from the file."""
    text, why = _read_handoff(top)
    if text is None:
        return why
    try:
        resume = importlib.import_module("crew_resume")
    except ImportError:
        return T0006_UNAVAILABLE
    try:
        parsed = resume.parse_resume(text)
        rendered = resume.render(parsed) if parsed.get("ok") else ""
    except Exception as exc:  # pylint: disable=broad-except
        return f"not usable: crew_resume raised {type(exc).__name__}"
    if not rendered:
        return f"not usable: {parsed.get('reason') or 'no reason given'}"
    if bare is None:
        return f"{rendered} (unknown: resume_target raised, so whether it is usable " \
               "could not be told)"
    if parsed.get("command") == AUTOPILOT and parsed.get("kind") == "goal":
        return f"not usable: {rendered} - goal resume arrives with {ARRIVES['goal']}"
    # `_handoff_ticket`'s checks in its order, in fixed text, on THIS read's
    # text: `bare` came from an earlier read the file may have been rewritten
    # since, so it vouches for the ticket only after these pass.
    if parsed.get("kind") != "ticket" or not parsed.get("arg"):
        return f"not usable: {rendered} - it names no ticket"
    branch = crew_state._HANDOFF_BRANCH_RE.search(text)  # pylint: disable=protected-access
    head = crew_state._HANDOFF_HEAD_RE.search(text)  # pylint: disable=protected-access
    here_head = (git_out(top, "rev-parse", "HEAD") or "").lower()
    if not branch or branch.group(1) != git_out(top, "rev-parse", "--abbrev-ref", "HEAD"):
        return f"not usable: {rendered} - its branch: does not match this checkout"
    if not head or not here_head or not here_head.startswith(head.group(1).lower()):
        return f"not usable: {rendered} - its head: does not match this checkout"
    if not _existing_ticket(top, parsed["arg"]):
        return f"not usable: {rendered} - its ticket has no .work/tickets/ folder"
    if _takes(bare, parsed.get("arg"), "handoff"):
        return f"{rendered} (usable)"
    if bare.get("stop"):
        return f"not usable: {rendered} - {bare.get('reason') or 'resume_target stopped'}"
    return f"not usable: {rendered} - bare {AUTOPILOT} does not take it"


def status(root, ticket=None):
    """`{"mode", "maxPhases", "warnings", "ticket", "source", "reason", "phase",
    "command", "stop", "phase_reason", "waiting", "review", "resume_line",
    "fallthrough", "disagreement"}`. Read-only: composes `settings`,
    `resume_target` (or `next_phase` for an argument), `review_ledger.status`
    and `crew_resume`. Whatever it cannot tell reads `unknown`. It reads no
    approval or questions policy (`policy=False`): its lines are the same
    under every setting, and `next` is what names the policy's route."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    conf = settings(top)
    if ticket:
        crew_ticket.check_ticket(ticket)
        if os.path.isdir(crew_ticket.ticket_dir(top, ticket)):
            pick = {"ticket": ticket, "source": "argument", "reason": "", "fallthrough": [],
                    "disagreement": "", "next": next_phase(top, ticket, policy=False)}
        else:
            pick = {"ticket": None, "source": "argument", "fallthrough": [],
                    "disagreement": "", "next": None,
                    "reason": f"{ticket} has no .work/tickets/ folder"}
        bare = _bare(top)
    else:
        pick = bare = resume_target(top, policy=False)
    disk = pick.get("next") or {}
    found = pick.get("ticket")
    return {"mode": conf["mode"], "maxPhases": conf["maxPhases"], "warnings": conf["warnings"],
            "ticket": found, "source": pick.get("source"), "reason": pick.get("reason", ""),
            "phase": disk.get("phase") or UNKNOWN, "command": disk.get("command") or "",
            "stop": bool(disk.get("stop", True)), "phase_reason": disk.get("reason", ""),
            "waiting": _waiting(top, disk, bare) if found else "owner - see the ticket line",
            "review": _review(top, found) if found else "unknown (no ticket)",
            "resume_line": _resume_line(top, bare),
            "fallthrough": list(pick.get("fallthrough") or []),
            "disagreement": pick.get("disagreement") or ""}


def _one_line(value):
    return " ".join(str(value).split())


def status_text(result):
    """At most STATUS_MAX_LINES lines; every field folded onto one line."""
    lines = [f"mode: plan, maxPhases {result.get('maxPhases')}"
             if result.get("mode") == "plan" else
             "mode: off - `autopilot.mode: plan` in .crew/config.json arms it"]
    if result.get("ticket"):
        lines.append(f"ticket: {result['ticket']} (from {result.get('source')})")
    else:
        lines.append(f"ticket: none - {result.get('reason') or 'cannot tell'}")
    if result.get("stop"):
        lines.append(f"phase: {result.get('phase')}, stopped - "
                     f"{result.get('phase_reason') or 'cannot tell'}")
    else:
        lines.append(f"phase: {result.get('phase')} - next: {result.get('command')}")
    lines += [f"waiting on: {result.get('waiting')}", f"review: {result.get('review')}",
              f"resume: {result.get('resume_line')}"]
    lines += [f"fell through: {why}" for why in result.get("fallthrough") or [] if why]
    if result.get("disagreement"):
        lines.append(f"disagreement: {result['disagreement']}")
    lines += [f"warning: {w}" for w in result.get("warnings") or []]
    lines = [_one_line(line) for line in lines]
    if len(lines) > STATUS_MAX_LINES:
        extra = len(lines) - STATUS_MAX_LINES + 1
        lines = lines[:STATUS_MAX_LINES - 1] + [
            f"(+{extra} more: crew_autopilot.py resume / settings print them)"]
    return "\n".join(lines)


def _failure(exc):
    """A `next`/`resume`/`status` crash as text, even when `str(exc)` raises."""
    if isinstance(exc, crew_ticket.TicketError):
        return _safe_text(exc, str)
    return (f"crew_autopilot raised {type(exc).__name__}: {_safe_text(exc, str)} - "
            "cannot tell, so stop")


def _line(**fields):
    return " ".join(f"{k}={v}" for k, v in fields.items())


def _policy_main(args):
    """`approve` and `questions-check`: exit 0 only on a yes. A crash is a
    refusal (exit 1), never an approval or a valid file."""
    try:
        if args.action == "approve":
            code, text = approve(args.root, args.ticket)
            result = {"code": code, "text": text}
        else:
            result = questions_check(args.root, args.ticket)
            code, text = (0 if result["valid"] else 1), questions_text(result)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        code, text = 1, _one_line(f"refused: {_failure(exc)}")
        result = {"code": code, "text": text}
    sys.stdout.write((json.dumps(result, indent=2) if args.json else text) + "\n")
    return code


def _cli_value(value, token=False):
    """`value` as one field of deploy-allowed's one line: itself when it is a
    printable string (for a `token`, non-empty with no whitespace either),
    else its repr, which escapes every line break. So nothing the CLI was
    handed, and no exception text, can print a second line to read as a
    verdict (review round 3)."""
    text = value if isinstance(value, str) else _safe_text(value)
    plain = text.isprintable() and not (token and (not text or any(
        char.isspace() for char in text)))
    return text if plain else _safe_text(text)


def _cli_deploy(args):
    """deploy-allowed's `(text, json_text, report)`; never raises. Stage 1
    builds all three from `deploy_allowed` inside one try. Stage 2, on any
    exception from stage 1 (a raise, a result missing a key, a value JSON
    cannot dump), builds them from the literal verdict `ask`; the exception
    only decorates the reason, and one that cannot be described gets a
    constant."""
    try:
        result = deploy_allowed(args.root, args.env, args.env_class)
        text = _line(**{"verdict": result["verdict"],
                        "env": _cli_value(result["env"], token=True),
                        "class": _cli_value(result["envClass"], token=True),
                        "reason": _cli_value(result["reason"])})
        report = _cli_value(result["report"]) if result["report"] else ""
        return text, json.dumps(result), report
    except Exception as exc:  # pylint: disable=broad-except
        # deploy_allowed never raises; if stage 1 does, that cannot tell: ask.
        try:
            reason = _crash_reason(exc)
        except Exception:  # pylint: disable=broad-except
            reason = ("crew_autopilot raised an exception it could not describe - "
                      "cannot tell, so ask")
    env, cls = _cli_value(args.env, token=True), _cli_value(args.env_class, token=True)
    text = _line(**{"verdict": "ask", "env": env, "class": cls, "reason": _cli_value(reason)})
    report = (f"unattended production: {env} ask - {_cli_value(reason)}"
              if args.env_class == "prod" else "")
    return text, json.dumps({"verdict": "ask", "reason": reason, "report": report,
                             "env": args.env, "envClass": args.env_class, "deploy": None,
                             "root": None}), report


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("next", "resume", "settings", "stops", "route", "status", "approve",
                 "questions-check"):
        action = sub.add_parser(name)
        action.add_argument("--json", action="store_true")
        if name != "stops":
            action.add_argument("--root", default=".")
    for name in ("next", "approve", "questions-check"):
        sub.choices[name].add_argument("--ticket", required=True)
    sub.choices["resume"].add_argument("--ticket", default="")
    sub.choices["status"].add_argument("--ticket", default="")
    given = sub.choices["route"].add_mutually_exclusive_group()
    given.add_argument("--args", default=None)
    given.add_argument("--first", default=None)
    sub.choices["next"].add_argument("--phases-run", type=int, default=0)
    sub.choices["next"].add_argument("--last-command", default="")
    deploy = sub.add_parser("deploy-allowed")
    deploy.add_argument("--json", action="store_true")
    deploy.add_argument("--root", default=".")
    deploy.add_argument("--env", required=True)
    # No `choices`: a class crew does not know reaches deploy_allowed and asks.
    deploy.add_argument("--class", dest="env_class", required=True)
    argv = list(argv)
    if argv[:1] == ["route"]:
        # `--goal` or `-h` is a value here, never an option: `--args=<v>`.
        for flag in ("--args", "--first"):
            at = argv.index(flag) if flag in argv else -1
            if 0 <= at < len(argv) - 1:
                argv[at:at + 2] = [f"{flag}={argv[at + 1]}"]
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    # Read-only but for approve's receipt: git must not even refresh the index's
    # stat cache.
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    if args.action in ("approve", "questions-check"):
        return _policy_main(args)
    if args.action == "status":
        try:
            result = status(args.root, args.ticket or None)
            text = status_text(result)
        except Exception as exc:  # pylint: disable=broad-except
            # A crash cannot tell where the ticket stands: say so, never nothing.
            result = {"status": UNKNOWN, "reason": _failure(exc)}
            text = _one_line(f"status: unknown - {_failure(exc)}")
    elif args.action == "route" and args.first is not None:
        result = route(args.root, args.first)
        text = _line(sub=result["sub"], stop=int(result["stop"]), reason=result["reason"])
    elif args.action == "route":
        result = route_args(args.root, args.args or "")
        extra = ({"set": result["set"], "tickets": ",".join(result["tickets"])}
                 if result["sub"] == WAVE else {})
        text = _line(sub=result["sub"], stop=int(result["stop"]), ticket=result["ticket"],
                     **extra, reason=result["reason"])
    elif args.action == "stops":
        result = stops()
        text = "\n".join(f"{kind} {row['id']}: {row['text']}"
                         for kind, rows in result.items() for row in rows)
    elif args.action == "settings":
        result = settings(args.root)
        text = "\n".join([_line(mode=result["mode"], maxPhases=result["maxPhases"],
                                deploy=result["deploy"])]
                         + [_line(approval=result["approval"], questions=result["questions"])]
                         + [f"warning: {w}" for w in result["warnings"]])
    elif args.action == "deploy-allowed":
        text, json_text, report = _cli_deploy(args)
        if report:
            sys.stderr.write(report + "\n")
        if args.json:
            text = json_text
    elif args.action == "resume":
        try:
            result = resume_target(args.root, args.ticket or None)
        except Exception as exc:  # pylint: disable=broad-except
            # A crash cannot tell which ticket: it is a stop, never no answer.
            result = {"ticket": None, "source": "argument", "stop": True, "hint": "",
                      "disagreement": "", "reason": _failure(exc), "fallthrough": [],
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
        except Exception as exc:  # pylint: disable=broad-except
            # A crash cannot tell the phase: it is a stop, never no answer.
            result = {"ticket": args.ticket, "phase": "invalid", "stop": True,
                      "command": "", "reason": _failure(exc), "evidence": []}
        text = _line(phase=result["phase"], stop=int(result["stop"]),
                     command=result["command"], reason=result["reason"])
    if args.json and args.action != "deploy-allowed":
        # status holds STATUS_MAX_LINES as JSON too: one line, nothing dropped.
        text = json.dumps(result, indent=None if args.action == "status" else 2)
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
