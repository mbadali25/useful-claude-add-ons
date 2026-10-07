"""`/crew:autopilot`'s reader: which ticket, which phase, and every stop.

    python3 crew_autopilot.py next --root . --ticket <id> [--phases-run N]
                                   [--last-command CMD] [--runner R] [--json]
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
    python3 crew_autopilot.py sleep --root . [--by <text>]
    python3 crew_autopilot.py wake --root .
    python3 crew_autopilot.py auto-reject --root . --ticket <id>
    python3 crew_autopilot.py focus --root . [--ticket <id> | --off |
                                    --findings --ticket <id>]
    python3 crew_autopilot.py ship --root . --ticket <id> [--json]
    python3 crew_autopilot.py split --root . --ticket <id> [--check|--apply]
    python3 crew_autopilot.py slice|slice-done|next-slice --root . --ticket <id>

T-0004. The lifecycle is prose commands (spec, plan, implement, review,
done); `/crew:autopilot` follows each one's procedure in-session. This module
is what names the NEXT one, from files on disk and nothing else, so a skipped
phase is visible and a phase that cannot be told stops. Read-only except
`approve` and `auto-reject`, each only when its policy allows under the
configured setting; it never accepts a review. Those are the two policy
exceptions (T-0010 and T-0074, below), and L-0652's `sleep` and `wake` the
only other writers: each writes or removes only
`<git-common-dir>/crew/autopilot-sleep.json`, the manual sleep state
(`crew_sleep`'s docstring; `sleep` only where `scope.allowCliApproval` is
exactly true).
`next`, `resume`, `settings`, `stops`, `route`, `status`, `questions-check`,
T-0072's `deploy-allowed` and T-0011's `ship` write no file. T-0058's `split
--check` writes `crew_split.check`'s record and `split --apply` what
`crew_split.apply` writes, only under `crew_split.ticket_split_policy`
(crew_autopilot_split.py's docstring). T-0059's `ship` on a sliced plan,
`slice-done` and `next-slice` write `<git-common-dir>/crew/tickets/<id>/slices.json`
(crew_autopilot_slices.py's docstring), and `next-slice` the next slice's branch. `ship` is the one
action outside the checkout: it pushes the ticket's branch, opens its PR and
may run `gh pr merge <n> --merge --match-head-commit <HEAD>` (below). `approve` writes exactly what
`crew_ticket.approve` writes for every approval route, `/crew:approve` included,
all under `<git-common-dir>/crew/`: `approval.json`; `scope-tickets.json`, the scope
ramp's list, on a ticket's first approval; and, when the review ledger is
NEEDS_REPLAN and the plan is a distinct successor, the ledger itself, moved
NEEDS_REPLAN -> IN_REVIEW (the successor continuation). `auto-reject` writes only
the review ledger, through `review_ledger.reject`: REVIEWED -> NEEDS_REPLAN, with
`rejected.by` the constant AUTO_REJECT_BY. Run as a script it writes no
bytecode either, however it is invoked (`-B` or not); a module that imports it
keeps its own bytecode setting. T-0020's `focus` is a script subcommand that
writes too, and approves nothing: `focus --ticket` writes this worktree's entry
in `<git-common-dir>/crew/autopilot-focus.json` and, when the active-ticket
pointer names another ticket or none, re-points it (`crew_ticket.activate`,
which records `.crew/.scope-base`); `focus --off` drops only the marker entry
(below).

## focus -- a scope lock on one ticket (T-0020)

Focus is explicit (owner decision, 2026-10-05): it is on only once `focus <id>` writes this
worktree's entry in the focus marker (`focus_path`), and `focus off` is the only thing that drops
it. The active-ticket pointer alone is never a focus, so with no marker entry `route` answers
exactly as without T-0020. No new hook. `focus_state` reads the marker; one that does not parse,
cannot be read, is not a file, or holds an entry that is not a ticket is `unknown` --
could-not-tell, its own value, never "no focus" -- and `focus_guard` then refuses everything but
`status`, `sleep` and `wake`, `next` stops as `drift`, and `focus off` refuses rather than delete
it; each such message ends with the removal command for the marker's path (`_focus_remedy`).
`focus` and `focus off` hold `_focus_lock` around the marker's read-modify-write, so two worktrees
cannot drop each other's entry. While focused, `focus_guard` refuses `run` of any other ticket
(named, or from the handoff in `resume`), `assign`, `goal` and any other subcommand, and all but
`focus <id>` while the pointer disagrees with the focus; `sleep` and `wake` always run (L-0652).
Once the focused ticket's plan is approved, every `next` runs the completion audit's own
`audit(root, ticket)` (read-only): a changed path outside Touch, or an audit that could not run,
stops as `drift`. `findings_target` names where an out-of-scope finding goes: `TODO.md` when the
approved Touch covers it, else `.work/tickets/<id>/out-of-scope.md`. Every `focus` output ends with
FOCUS_REMINDER: Claude Code's built-in `/focus` only toggles the display.

## approve and questions-check -- the two policies (T-0010)

`autopilot.approval` and `autopilot.questions` are `human|self|risk`
(default `risk`); any other value reads as `human`, with a warning.

`approval_policy` allows only when `scope.allowCliApproval` is exactly `true` in
`.crew/config.json` -- at every setting -- and the review ledger is readable (a NEEDS_REPLAN one
included: a distinct successor plan is its only way out, and the ledger refuses a plan approved
before); then `human` never allows, `self` allows any risk, `risk` only a spec header that says
`risk: low`. An absent or unparseable risk is `high` (`crew_ticket.parse_risk`), never `low`.
`approve` also needs autopilot armed, writes the receipt with `approved_via: "autopilot"` and
prints `self-approved <id> under approval=<policy>, risk=<risk>`; a refusal exits 2 with `refused:
<why>`. `crew_ticket.accepted` re-asks `approval_policy` on every read, so an `autopilot` receipt
stands only while the policy still says yes. `question_policy` is the same decision for an open
question -- `take` the researched recommendation or `stop` -- with no `allowCliApproval` rule.

`questions-check` validates `.work/tickets/<id>/questions.md` (the shape is QUESTIONS_SHAPE,
printed when it fails) and prints `valid= action= policy= risk=`, then one `taken:` line per
question autopilot answered. A `taken:` line is valid only for the recommended option, only naming
a policy that takes (`self` or `risk` -- the one in force when it was taken, so a later policy
change does not void an honest record), and only while the policy in force says `take`. Exit 0
valid, 1 not.

## next -- the phase from disk, first match wins

  folder only in the main checkout       folder-elsewhere    stop, naming the copy
  no folder here, main checkout unknown  folder-elsewhere    stop (cannot tell)
  no direction.md                        brainstorm          stop
  INDEX rows here and in main differ     direction-approval  stop (index-disagreement)
  INDEX status `direction`, or no row    direction-approval  stop (no row: cannot tell)
  INDEX `done` and spec header `done`    (the ship rows below)
  INDEX status done/cancelled/superseded closed              stop (and merged/closed/...)
  INDEX cell, else header: hold, landing hold, landing,      stop (L-0550: next.md's reason,
    or needs-owner (crew_autopilot_gates) needs-owner          revisit, next: or questions)
  header cancelled/superseded (view)     closed              stop (names the successor)
  gate unknown (INDEX rows disagree)     direction-approval  stop (cannot tell)
  INDEX status not in DIRECTION_APPROVED direction-approval  stop (cannot tell)
  spec header cancelled/superseded       closed              stop (quotes split-into:)
  spec header `done`, slice n < m current slices              stop (later slices unbuilt)
  spec header `status: done`, unarmed    closed              stop
  ... armed, detached HEAD or gh failure ship                stop (cannot tell)
  ... PR merged at this HEAD (full SHA)  closed              stop
  ... PR merged, HEAD differs/unreadable ship                stop, new branch and PR
  ... PR open, `autopilot.ship: pr`      closed              stop, merge by hand
  ... PR closed unmerged, other state    ship                stop
  ... working tree differs from HEAD     ship                stop
  ... receipt no longer stands           ship                stop
  ... no PR, or open under `merge`       ship                crew_autopilot.py ship
  `## Open questions` with an item       open-questions      stop (fences: L-0642)
  no spec.md                             spec                /crew:spec <id>
  spec fails crew_ticket.validate        spec                stop
  size check after spec (T-0058)         split-*             crew_autopilot_split.py
  no plan.md                             plan                /crew:plan <id>
  plan fails crew_ticket.validate        plan                stop
  size check after plan (T-0058)         split-*             crew_autopilot_split.py
  plan's `## PR slices` refused          plan                stop (T-0059, PR slices: ...)
  approval not accepted                  approve             stop, unless the policy allows
  slices.json unreadable/out of shape    slices              stop (cannot tell the slice)
  non-final slice in `done`              (the ship rows above; merged, or open under
                                          `ship: pr`, names next-slice instead of closed)
  a depends-on: not closed or unreadable blocked             stop (L-0550; names each one)
  review ledger UNKNOWN                  review              stop
  review ledger NEEDS_REPLAN             replan              stop, unless auto-rejected
  no review round under this plan        implement           /crew:implement <id>
  latest round still reserved            review              stop
  latest round FINDINGS, not accepted    accept-review       stop, unless auto-replan or
    (T-0067) reviewPolicy fix-and-rereview, a round left: fix  fix-findings <id> round <n>
  no receipt and no round left           review              stop, never a third reserve
  accepted FINDINGS, receipt staled      (the receipt-not-current rows below; T-0043)
  accepted FINDINGS, receipt unchecked   accept-review       stop (not confirmed stale)
  latest round INCOMPLETE or no verdict  accept-review       stop
  artifacts fresh-uncommitted            commit-refresh      git add, git commit -- <paths>
                                                             (stop when it names no path)
  receipt not current, artifacts stale   refresh             the refresh command
  receipt not current, artifacts fresh   review              /crew:review <id>
  receipt current, artifacts stale       stale-after-review  stop, nothing written
  receipt current, artifacts fresh       done                /crew:done <id>

A sliced plan's other rows carry `slice` and prefix the reason with `slice n
of m (<name>): steps a-b only` (crew_autopilot_slices.py, T-0059).

T-0074, only with `autopilot.maxAutoReplans` 1 or more (default 0, off): an out-of-rounds
FINDINGS round with a BLOCK that `auto_replan_policy` allows is `auto-replan`, whose command is
`auto-reject`; refused only by the cap it is the `auto-replan-cap` stop and names every successor
plan. A NEEDS_REPLAN that autopilot's own reject of the current plan's latest round wrote, whose
round still passes the policy's round checks and is still allowed, is `replan` without a stop.
`status` reads neither route (`policy=False`). T-0067's `fix` is crew_autopilot_fix.py's docstring.

The INDEX row (T-0063) is this checkout's; with none, the main checkout's -- the first record of
`git worktree list --porcelain` -- and `index_source` (`--json` only) names the file that answered.
Rows in both whose cells differ stop as `index-disagreement`; a listing that fails is
could-not-tell, kept in the reason. The ticket folder is never read from the main checkout: one
only there stops, naming the `cp -r` to make, since the scope guard reads Touch from this
checkout's folder.

## ship (T-0011)

`ship_decision`, the merge rule, and the gh/git adapter are crew_ship.py's (its docstring).

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
not landed)" -- never skipped. `fresh-uncommitted`
(T-0063) is `commit-refresh`, before review and after an accepted one alike:
it commits exactly the paths the check lists, which leaves the working state
-- the review bundle -- byte for byte as it was.

## resume -- which ticket

0. `--ticket <id>` (the command's `$1`), when given.
1. `.work/HANDOFF.md`'s `resume:` line, parsed by T-0006's
   `crew_resume.parse_resume` (never re-parsed here), naming a ticket, with
   `branch:` and `head:` equal to this checkout. `--goal` stops until L-0541.
2. This worktree's active-ticket pointer (`crew_ticket.resolve_active`).
3. `.work/INDEX.md`, only when exactly one open ticket has a folder.

A handoff that cannot be used falls through with its reason recorded; the
`## Next action` prose is never guessed from. When the handoff's command
disagrees with the phase on disk, disk wins and the disagreement is reported.
A ticket that differs from this worktree's active-ticket pointer stops, naming
both: the scope guard and the completion audit judge edits by the pointer.
With no pointer, `activate` tells the command to set it to the ticket it drives.

Exit 0 always (`ship` included), but for `approve` and `questions-check` (above); the answer is
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
# pylint: disable=too-many-lines  # over 3400 in the 1.2.0 rush; new logic goes to crew_autopilot_*.py
import argparse
import datetime
import hashlib
import importlib
import json
import os
import re
import shlex
import sys
import threading
import time

if __name__ == "__main__":
    # Before the sibling imports: the direct CLI writes no bytecode either.
    sys.dont_write_bytecode = True

import completion_audit
import crew_common
import crew_autopilot_docs
import crew_autopilot_fences
import crew_autopilot_fix
import crew_autopilot_gates
import crew_autopilot_sleep
import crew_autopilot_slices
import crew_autopilot_split
import crew_autopilot_stops
import crew_config
import crew_ship
import crew_sleep
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
# T-0063: every artifact current, a refreshed file not yet committed.
FRESH_UNCOMMITTED = "fresh-uncommitted"
UNCOMMITTED = "uncommitted"
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
# `cancelled` and `superseded` are T-0037's closed words (crew_tracker.CLOSED_STATUSES).
INDEX_DONE = ("done", "closed", "merged", "shipped", "complete", "completed", "cancelled", "superseded")
# spec.md header words that close a ticket. `merged` is not one: a header
# `merged` keeps its old meaning here (T-0037 left it as it was).
HEADER_CLOSED = ("done", "cancelled", "superseded")
# T-0037's open status that waits on the owner (crew_tracker.OWNER_STATUSES):
# INDEX and tracker only, never a spec header word.
NEEDS_OWNER = "needs-owner"

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
    ("index-disagreement", "the worktree's and the main checkout's .work/INDEX.md rows for "
                           "the ticket disagree"),
    ("unsettled-artifact", "an artifact is unknown for a cause a refresh cannot settle"),
    ("ticket-mismatch", "the ticket to drive is not this worktree's active ticket"),
    ("in-flight", "with --runner: another runner holds the ticket here, or its marker is stale or unreadable"),
    ("handover-elsewhere", "with --runner: a fresh holder drives the ticket from another worktree"),
    ("drift", "explicitly focused and approved: a changed path is outside the ticket's Touch "
              "(completion_audit.audit), or the audit could not run"),
    ("max-phases", "autopilot.maxPhases phases have run in this invocation"),
    ("no-progress", "a phase ran and the files on disk still name the same command"),
    ("auto-replan-cap", "autopilot.maxAutoReplans successor plans are already on the "
                        "ticket's review ledger: the owner decides, with the history"),
) + crew_autopilot_docs.FIXED_STOPS  # T-0022: the docs phase and the tracker step
FIXED_STOPS += crew_autopilot_split.FIXED_STOPS  # T-0058: the size check
FIXED_STOPS += crew_autopilot_gates.FIXED_STOPS  # L-0550: hold, landing, needs-owner, blocked
# Enforced by the command's procedure, not by `next` (which sees them only as
# `no-progress` when the same command comes round again).
PROCEDURE_STOPS = (
    ("review-verdict", "a review phase ends at its verdict: never fix and rerun inside it"),
    ("failed-done-check", "a /crew:done check refused: it is not retried around"),
    ("failed-phase", "a phase's own procedure refused or stopped"),
    ("scope-not-enforcing", "`/crew:autopilot wave` runs lanes only while scope.mode is block (T-0029)"),
) + crew_autopilot_fix.PROCEDURE_STOPS  # T-0067: a finding the fix phase refused
# A person, unless the T-0010 policy named says otherwise; `human` always stops.
HUMAN_STOPS = (
    ("brainstorm", "/crew:brainstorm and direction approval are a human dialogue"),
    ("plan-approval", ("plan approval: the human types /crew:approve <id>, unless "
                       "autopilot.approval allows `crew_autopilot.py approve` "
                       "(needs scope.allowCliApproval: true)")),
    ("review-acceptance", ("accepting review FINDINGS with any BLOCK, or any round "
                           "review_ledger.py --auto-accept refuses, is the owner's; a BLOCK "
                           "is never accepted by autopilot, and with "
                           "autopilot.maxAutoReplans an out-of-rounds BLOCK round is "
                           "rejected and replanned instead (T-0074)")),
    ("open-questions", "an open question in direction.md, spec.md or plan.md is answered "
                       "by a person, unless autopilot.questions takes the researched "
                       "recommendation"),
)

# T-0018: the command's subcommands. A later ticket adds its name to AVAILABLE
# and drops it from ARRIVES when it replaces the router's stop.
SUBCOMMANDS = ("status", "run", "assign", "goal", "focus")
SUBCOMMANDS += ("sleep", "wake", "wave")  # L-0652: manual sleep mode; T-0029: crew_wave.py
SUBCOMMANDS += ("split",)  # T-0058
AVAILABLE = frozenset({"status", "run", "goal", "focus", "sleep", "wake", "wave", "split"})
# L-0652: the subcommands that take no ticket, not even a second word.
NO_TICKET = frozenset({"sleep", "wake"})
ARRIVES = {"assign": "T-0019"}
GOAL_FLAG = "--goal"
GOAL_SUB = "goal"
UNKNOWN_SUB = ("unknown subcommand; one of " + "|".join(SUBCOMMANDS)
               + ", or a ticket id")
# The INDEX.md id shape, whole-string; [0-9], not \d, which is any Unicode digit.
_INDEX_ID = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")
WAVE = "wave"

# --- ship (T-0011) -------------------------------------------------------------
# The pure merge rule and the gh/git adapter live in crew_ship.py (batch 7: this
# module passed pylint's 3400-line cap); what reads the review ledger stays here.
SHIP_POLICIES = ("pr", "merge")
POLL_SECONDS = 30
_sleep = time.sleep
_clock = time.monotonic


def _ledger_hash(top, ticket):
    """sha256 of the review ledger's bytes, or None when it cannot be read."""
    try:
        with open(review_ledger.ledger_path(top, ticket), "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except (OSError, ValueError):
        return None


def _families(top, ticket):
    """The `model_family` of every completed round under the current plan,
    or None when the ledger cannot be read."""
    ledger = _ledger_status(top, ticket)
    if ledger["state"] == review_ledger.UNKNOWN:
        return None
    return [r.get("model_family") for r in _current_rounds(ledger)
            if isinstance(r, dict) and r.get("status") == "completed"]


def _ship_gate(top, ticket):
    """What a merge rests on, read from disk again on every poll: the
    settings, the spec's risk, the completed rounds' review families and the
    hash of the ledger bytes those families came from. CI can run for an
    hour, and in that time the owner may disarm autopilot, change `ship` or
    `knownFailures`, or the ledger may move to a successor plan - so nothing
    read before the wait is trusted after it. `stop` is a reason, or None."""
    config = settings(top)
    spec = read_text(os.path.join(crew_ticket.ticket_dir(top, ticket), "spec.md")) or ""
    ledger = _ledger_hash(top, ticket)
    families = _families(top, ticket)
    gate = {"config": config, "risk": crew_ticket.parse_risk(spec)["risk"],
            "families": families, "ledger": ledger, "stop": None}
    if not config["armed"]:
        gate["stop"] = "autopilot.mode is not armed any more - a person ships it"
    if families is None or ledger is None or _ledger_hash(top, ticket) != ledger:
        gate["stop"] = ("the review ledger is unreadable, or changed while it was read, so "
                        "the review families cannot be told")
    gate["stop"] = gate["stop"] or crew_autopilot_gates.hold_reason(top, ticket, _index_row(top, ticket))
    return gate


def ship_command(ticket):
    return f"crew_autopilot.py ship --ticket {ticket}"


def _ship_phase(top, ticket, answer, why, ctx=None, deep=True):
    """`next` for a ticket `/crew:done` closed: `closed` once its PR merged
    this HEAD (or, under `ship: pr`, once one is open), `ship` while there is work
    left, and a stop for every state that cannot be read. Unarmed, it is
    `closed` without asking gh: shipping is autopilot's alone. `ctx` is a
    sliced ticket's (T-0059): a non-final slice whose PR merged (or opened,
    under `ship: pr`) names `next-slice` instead of `closed`."""
    config = settings(top)
    final = ctx is None or ctx["piece"]["n"] == ctx["m"]
    sl = crew_autopilot_slices

    def finished(reason):
        if final:
            return answer("closed", True, reason)
        return dict(answer("next-slice", False, f"{sl.label(ctx)} shipped: {reason}",
                           sl.slice_command(ticket)), slice=ctx["piece"]["n"])

    if not config["armed"] and not final:
        return answer("ship", True, f"{sl.label(ctx)} done. Shipping is "
                      "/crew:autopilot's and autopilot.mode is off: a person ships this "
                      "slice; armed, autopilot ships it and opens the next")
    if not config["armed"]:
        return answer("closed", True, f"{why}: closed by /crew:done. Shipping is "
                      "/crew:autopilot's and autopilot.mode is off, so a person pushes and "
                      "merges", decision="look")  # L-0666: a person still ships it
    if not deep:  # L-0551: the owner list never asks gh
        return answer(crew_autopilot_stops.UNREAD, True, crew_autopilot_stops.UNREAD_SHIP)
    branch = crew_ship._branch(top)
    if not branch:
        return answer("ship", True, "cannot tell which branch ships: HEAD is detached or "
                      "unreadable - a human checks out the ticket's branch")
    wrong = sl.branch_stop(ctx, branch) if ctx else ""
    if wrong:
        return answer("ship", True, wrong)
    pr = crew_ship.read_pr(top, branch)
    if pr is None:
        return answer("ship", True, f"could not read the PR state for {branch} (gh pr view "
                      "failed: gh missing, not authenticated, no remote, or an answer that "
                      "is not a PR) - a human looks")
    state = pr["state"]
    wrong = (sl.expected_base_stop(top, ctx, branch) if ctx and state == "OPEN" else
             sl.merged_base_stop(top, ctx, branch) if ctx and state == "MERGED" else "")
    if wrong:
        return answer("ship", True, wrong)
    if state == "MERGED":
        return crew_ship.merged_phase(top, branch, pr, answer, finished)
    if state == "OPEN" and config["ship"] != "merge":
        return finished(f"PR #{pr['number']} open, merge by hand "
                        f"({pr.get('url')}; autopilot.ship is {config['ship']})")
    if state not in ("NONE", "OPEN"):
        return answer("ship", True, f"PR #{pr.get('number')} for {branch} is {state}, not "
                      "open or merged - a person decides")
    tree = crew_ship._tree_stop(top)
    if tree:
        return answer("ship", True, f"{tree}: a push carries only commits, so what was "
                      "reviewed would not be what ships - a human decides")
    order = sl.order_stop(top, ctx, branch, config["ship"]) if ctx else ""
    if order:
        return answer("ship", True, order)
    ok, message = review_ledger.check_receipt(top, ticket)
    if not ok:
        return answer("ship", True, f"the review receipt no longer stands ({message}): "
                      "shipping would put unreviewed commits in the PR - a human decides")
    if ctx:
        why = f"{sl.label(ctx)}: {why}"
    return answer("ship", False, f"{why}; " + ("no PR yet" if state == "NONE" else
                                               f"PR #{pr['number']} open, merging when green"),
                  ship_command(ticket))


def _ship_result(ticket, action, stop, reason, pr=None, checks=None, families=None):
    return {"ticket": ticket, "action": action, "stop": stop, "reason": reason,
            "pr": (pr or {}).get("url") or (f"#{pr['number']}" if pr and pr.get("number")
                                           else ""),
            "checks": checks, "families": families}


def _head_stop(top, branch, head, where):
    """The reason the PR's head or this checkout's HEAD is no longer `head`,
    or "": the checks, the receipt and the merge must all be about one
    commit."""
    local = git_out(top, "rev-parse", "HEAD")
    if local != head:
        return (f"this checkout's HEAD moved {where} ({local or 'unreadable'} vs {head}): "
                "the checks read are not for what was reviewed - never merged")
    now = crew_ship.read_pr(top, branch)
    if now is None or now.get("state") != "OPEN" or now.get("headRefOid") != head:
        return (f"the PR's head is not the commit ship pushed {where} "
                f"({(now or {}).get('headRefOid') or (now or {}).get('state', 'unreadable')} "
                f"vs {head}): the checks read are not for what was reviewed - never merged")
    return ""


def _wait_for_ci(top, ticket, branch, pr, head):
    """Poll the required checks until `crew_ship.ship_decision` says merge, or return
    the stop. `(result, decision, checks, gate)`: `result` is a finished
    `_ship_result` when it stopped, else None."""
    gate = _ship_gate(top, ticket)
    if gate["stop"]:
        return _ship_result(ticket, "stop", True, gate["stop"], pr, None,
                            gate["families"]), None, None, gate
    minutes = gate["config"]["ciTimeoutMinutes"]
    deadline = _clock() + minutes * 60
    while True:
        moved = _head_stop(top, branch, head, "before a poll")
        checks = crew_ship.read_checks(top, pr["number"])
        moved = moved or _head_stop(top, branch, head, "while the checks were read")
        gate = _ship_gate(top, ticket)
        families = gate["families"]
        if moved:
            return _ship_result(ticket, "stop", True, moved, pr, checks,
                                families), None, checks, gate
        if gate["stop"]:
            return _ship_result(ticket, "stop", True, gate["stop"], pr, checks,
                                families), None, checks, gate
        decision = crew_ship.ship_decision(gate["config"]["ship"], gate["risk"], checks, families,
                                 gate["config"]["knownFailures"])
        # Read after the checks, not before: a green that arrives past the
        # deadline is a stop, the same as a pending one.
        late = _clock() >= deadline
        if decision["action"] == "merge" and not late:
            return None, decision, checks, gate
        if decision["action"] not in ("merge", "wait"):
            opened = decision["action"] == "open-pr"
            return _ship_result(ticket, "open-pr" if opened else "stop", not opened,
                                decision["reason"], pr, checks, families), None, checks, gate
        if late:
            return _ship_result(ticket, "stop", True, f"{decision['reason']} after "
                                f"{minutes} min (autopilot.ciTimeoutMinutes) - never merged",
                                pr, checks, families), None, checks, gate
        _sleep(min(POLL_SECONDS, deadline - _clock()))


def _pre_merge_stop(top, ticket, branch, pr, head, gate, base=None):
    """Every check between CI turning green and the merge call, or "". `base`
    is a slice's planned base (T-0059): a PR retargeted while CI ran is never
    merged."""
    # The receipt was checked before the push; commits made while CI ran
    # would ship unreviewed without this second look.
    stands, why = review_ledger.check_receipt(top, ticket)
    if not stands:
        return (f"the review receipt no longer stands ({why}) after waiting on CI - never "
                "merged")
    if _ledger_hash(top, ticket) != gate["ledger"]:
        return ("the review ledger changed after the review families were read: the "
                "receipt checked is not the one the families came from - never merged")
    moved = _head_stop(top, branch, head, "after CI")
    if moved:
        return moved
    tree = crew_ship._tree_stop(top)
    if tree:
        return f"{tree} - never merged"
    wrong = crew_autopilot_slices.pr_base_stop(top, branch, base) if base else ""
    if wrong:
        return f"{wrong} - never merged"
    queue = crew_ship.read_merge_queue(top, pr["number"])
    if queue is not False:
        return (("the base branch has a merge queue, or the PR is in one" if queue else
                 "could not tell whether the base branch has a merge queue") + ": a queue "
                "picks its own merge method and keeps merging after ship stops - a person "
                "merges")
    held = crew_autopilot_gates.hold_reason(top, ticket, _index_row(top, ticket))  # L-0550
    if held:
        return f"{held} - never merged"
    # Last, right before the call: the ledger and this checkout's HEAD again.
    if _ledger_hash(top, ticket) != gate["ledger"]:
        return "the review ledger changed just before the merge - never merged"
    local = git_out(top, "rev-parse", "HEAD")
    if local != head:
        return (f"this checkout's HEAD moved just before the merge ({local or 'unreadable'} "
                f"vs {head}) - never merged")
    return ""


def ship(root, ticket):
    """Push the branch, open its PR if none, then under `ship: merge` poll
    the required checks every POLL_SECONDS up to `ciTimeoutMinutes`, feeding
    `crew_ship.ship_decision` from a gate read afresh each poll, and on `merge` - once
    the receipt still stands on the same ledger the families came from, the
    PR's head and this checkout's HEAD are still the commit pushed, the tree
    is clean and no merge queue is involved - run exactly `crew_ship.merge_argv`. A
    merge that leaves the PR not MERGED in a queue is dequeued and stops.
    Runs only when `next` names `ship` -- which it never does unarmed. Every
    answer names the PR, the checks and the review families it rested on."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    # Unarmed, `next` names `closed` (see `_ship_phase`), so this refuses too.
    phase = next_phase(top, ticket)
    if phase["phase"] != "ship" or phase["stop"]:
        return _ship_result(ticket, "stop", True, f"next names {phase['phase']}"
                            f"{' (stop)' if phase['stop'] else ''}, not ship: {phase['reason']}")
    branch = crew_ship._branch(top)
    default = crew_ship._default_branch(top)
    if not branch or not default or branch == default:
        return _ship_result(ticket, "stop", True, f"will not push {branch or '(no branch)'}: "
                            f"the default branch is {default or 'unreadable'}, and ship "
                            "pushes only a ticket branch that is not it")
    ctx = crew_autopilot_slices.context(top, ticket)
    if ctx:
        # T-0059: one PR per slice, in order, based per the plan's Base: rule.
        return crew_autopilot_slices.ship_slice(
            top, ticket, ctx, branch, default,
            lambda create, base: _ship(top, ticket, branch, create, base))
    return _ship(top, ticket, branch, ["pr", "create", "--head", branch, "--fill"])


def _ship(top, ticket, branch, create, base=None):
    """`ship` from the clean-tree check on, with `create` the `gh pr create`
    argv when the branch has no PR."""
    tree = crew_ship._tree_stop(top)
    if tree:
        return _ship_result(ticket, "stop", True, f"{tree} - nothing pushed")
    pushed, detail = crew_ship._push(top, branch)
    if not pushed:
        return _ship_result(ticket, "stop", True, f"git push -u origin {branch} failed: "
                            f"{detail}")
    # The one commit everything after rests on, taken once, before any check
    # is read: a commit that lands later is a stop, never re-sampled.
    head = git_out(top, "rev-parse", "HEAD")
    if not head:
        return _ship_result(ticket, "stop", True, "could not read this checkout's HEAD "
                            "after pushing")
    pr = crew_ship.read_pr(top, branch)
    if pr is not None and pr["state"] == "NONE":
        created = crew_ship._run_gh(top, create)
        if created is None or created[0] != 0:
            return _ship_result(ticket, "stop", True, "gh pr create failed: "
                                + ((created[2] or created[1]).strip() if created else
                                   "gh could not run"))
        pr = crew_ship.read_pr(top, branch)
    if pr is None or pr["state"] != "OPEN":
        return _ship_result(ticket, "stop", True, "could not read an open PR for "
                            f"{branch} after pushing ({(pr or {}).get('state', 'unreadable')})",
                            pr)
    if pr.get("headRefOid") != head:
        return _ship_result(ticket, "stop", True, "the PR's head is not the commit ship "
                            f"pushed ({pr.get('headRefOid')} vs {head}) - never merged", pr)
    stopped, decision, checks, gate = _wait_for_ci(top, ticket, branch, pr, head)
    if stopped:
        return stopped
    families = gate["families"]
    why = _pre_merge_stop(top, ticket, branch, pr, head, gate, base)
    if why:
        return _ship_result(ticket, "stop", True, why, pr, checks, families)
    merged = crew_ship._run_gh(top, crew_ship.merge_argv(pr["number"], head))
    after = crew_ship.read_pr(top, branch)
    if merged is not None and merged[0] == 0 and after is not None \
            and after.get("state") == "MERGED":
        return _ship_result(ticket, "merged", False, decision["reason"], pr, checks, families)
    failed = ("gh pr merge --merge failed: " + ((merged[2] or merged[1]).strip() if merged
                                                 else "gh could not run")
              if merged is None or merged[0] != 0 else
              "gh pr merge exited 0 but the PR reads "
              f"{(after or {}).get('state', 'unreadable')}, not MERGED")
    queue = crew_ship.read_merge_queue(top, pr["number"])
    if queue is not False:
        outcome = crew_ship._dequeue(top, after if isinstance(after, dict) and after.get("id") else pr)
        return _ship_result(ticket, "stop", True, f"{failed}; " + (
            "the PR is in a merge queue, or its base branch has one" if queue else
            "could not tell whether gh handed the PR to a merge queue")
            + f" - a queue merges with its own method after ship stops, so ship dequeued "
            f"it: {outcome}. A person merges", pr, checks, families)
    return _ship_result(ticket, "stop", True, f"{failed} - a human looks", pr, checks,
                        families)


def _rel(top, path):
    """`path` relative to `top` for evidence lines, or `path` itself when there
    is no relative form: on Windows a path on another drive than `top` makes
    `os.path.relpath` raise ValueError (T-0077)."""
    try:
        return os.path.relpath(path, top).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def _rel_inside(top, path):
    """`path` relative to `top` when it lies inside it, `/`-separated as every
    evidence line is; else whole and exactly as given (T-0063: an INDEX.md read
    from the main checkout is named in full, the same string `index_source`
    carries -- never re-slashed, which on Windows made the evidence and the
    reason name a path `index_source` did not)."""
    rel = _rel(top, path)
    if rel == ".." or rel.startswith("../") or os.path.isabs(rel):
        return path
    return rel


def _index_rows(top, index_path=None):
    """[(ticket, line)] for every line naming a ticket in `index_path` (this
    checkout's `.work/INDEX.md` by default), in order."""
    rows = []
    path = index_path or os.path.join(top, ".work", "INDEX.md")
    for line in (read_text(path) or "").splitlines():
        found = crew_state._TICKET_RE.search(line)  # pylint: disable=protected-access
        if found:
            rows.append((found.group(1), line))
    return rows


def _index_status(top, ticket, index_path=None):
    """The status cell of `ticket`'s INDEX.md table row, lower-cased, or None."""
    for found, line in _index_rows(top, index_path):
        if found != ticket or line.count("|") < 2:
            continue
        cells = [c.strip() for c in line.split("|")]
        for index, cell in enumerate(cells):
            if cell == ticket and index + 1 < len(cells):
                return cells[index + 1].lower()
    return None


def _main_checkout(top):
    """`(path, why)` (T-0063): the main checkout of the linked worktree `top`,
    the first record of `git worktree list --porcelain`. `(None, "")` when
    `top` is the main checkout -- `.git` a directory needs no subprocess --
    so there is nothing else to read. `(None, why)` when the listing failed,
    its first record is bare, or that path cannot be read: could-not-tell,
    never "no row there"."""
    if os.path.isdir(os.path.join(top, ".git")):
        return None, ""
    out = git_out(top, "worktree", "list", "--porcelain")
    if out is None:
        return None, "git worktree list failed, so the main checkout cannot be named"
    record = out.replace("\r\n", "\n").split("\n\n", 1)[0].splitlines()
    if not record or not record[0].startswith("worktree "):
        return None, "git worktree list named no main checkout"
    path = record[0][len("worktree "):]
    if "bare" in record[1:]:
        return None, f"the first worktree, {path}, is a bare repository: no main checkout"
    if not os.path.isdir(path):
        return None, f"the main checkout {path} cannot be read"
    path = os.path.realpath(path)
    if os.path.normcase(path) == os.path.normcase(os.path.realpath(top)):
        return None, ""
    return path, ""


def _index_row(top, ticket):
    """`{"status", "source", "other", "why", "paths"}` (T-0063): this
    checkout's INDEX row for `ticket`, else the main checkout's. `source` is
    the INDEX.md that answered, None when none did. Rows in both whose cells
    differ are `status` None with `other` holding both `(path, cell)`. `why`
    is a could-not-tell about the main checkout; `paths` every file asked."""
    here = os.path.join(top, ".work", "INDEX.md")
    local = _index_status(top, ticket)
    main, why = _main_checkout(top)
    there = os.path.join(main, ".work", "INDEX.md") if main else None
    row = {"status": local, "source": here if local is not None else None, "other": None,
           "why": why, "paths": [here] + ([there] if there else [])}
    if not there:
        return row
    found = _index_status(top, ticket, there)
    if found is None and os.path.lexists(there) and read_text(there) is None:
        row["why"] = f"{there} exists but could not be read"
    elif local is not None and found is not None and found != local:
        row.update(status=None, source=None, other=((here, local), (there, found)))
    elif local is None and found is not None:
        row.update(status=found, source=there)
    return row


def _main_folder(top, ticket):
    """`(there, why)`: `there` is `<main>/.work/tickets/<id>/` when only the
    main checkout holds it -- named, never read: the scope guard reads Touch
    from this checkout. `why` is set when this checkout has no folder and
    the main checkout could not be named: could-not-tell, never "absent"."""
    if os.path.isdir(crew_ticket.ticket_dir(top, ticket)):
        return None, ""
    main, why = _main_checkout(top)
    there = crew_ticket.ticket_dir(main, ticket) if main else None
    return (there if there and os.path.isdir(there) else None), why


def _folder_elsewhere(top, ticket, there, why=""):
    if not there:
        return (f"{ticket} has no .work/tickets/ folder here, and autopilot could not tell "
                f"whether the ticket folder is in the main checkout: {why}")
    return (f"{ticket}'s folder is only in the main checkout ({there}); copy it here first: "
            f"cp -r {shlex.quote(there)} {shlex.quote(crew_ticket.ticket_dir(top, ticket))} "
            "- autopilot never reads a ticket's contract from another checkout")


def _is_open(ticket, line):
    table = crew_state._table_status(line, ticket)  # pylint: disable=protected-access
    if table is not None:
        return not table
    return not crew_state._DONE_RE.search(line)  # pylint: disable=protected-access


def _open_index_rows(top):
    """[(ticket, from_main)] for every open INDEX.md ticket whose
    `.work/tickets/<id>/` exists HERE, in order, once each: this checkout's
    rows, then the main checkout's for tickets with no row here (T-0063)."""
    main, _why = _main_checkout(top)
    rows = [(ticket, line, False) for ticket, line in _index_rows(top)]
    here = {ticket for ticket, _line, _main in rows}
    if main:
        rows += [(ticket, line, True) for ticket, line in
                 _index_rows(top, os.path.join(main, ".work", "INDEX.md")) if ticket not in here]
    seen = {}
    for ticket, line, from_main in rows:
        if ticket not in seen and _is_open(ticket, line) \
                and os.path.isdir(crew_ticket.ticket_dir(top, ticket)):
            seen[ticket] = from_main
    return list(seen.items())


def open_index_tickets(top):
    """Every open INDEX.md ticket whose `.work/tickets/<id>/` exists, in order,
    once each. Unlike `crew_state.read_work`, this does not stop at the first."""
    return [ticket for ticket, _from_main in _open_index_rows(top)]


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
    """L-0642: main's parser (the floor) plus a column-0 fence view; any other fence shape is
    could-not-tell and stops. Put fences at column 0 and close each (crew_autopilot_fences)."""
    return crew_autopilot_fences.open_items(text, _legacy_open_items, _HEADING)


UNCLEAR_FENCE, UNEXPLAINED_FENCE = (crew_autopilot_fences.UNCLEAR_FENCE,
                                    crew_autopilot_fences.UNEXPLAINED_FENCE)


def _legacy_open_items(text):
    """Main's parser, unchanged (L-0642's floor): unanswered items under any
    `Open questions` heading, at any level, down to the next heading of the same or a
    higher level -- a sub-heading inside the section stays inside it. See `_ANSWERED`."""
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
    if status == FRESH_UNCOMMITTED:
        return {"state": UNCOMMITTED, "command": "", "reason": result.get("reason", ""),
                "paths": [p for p in result.get("uncommitted") or [] if isinstance(p, str)]}
    pending = [a for a in result.get("artifacts") or [] if a.get("status") in (STALE, UNKNOWN)]
    reason, unsettled, named = (crew_autopilot_stops.refresh_reason(status, result, pending, _settles, stop)
                                for stop in (None, "unsettled", "named"))  # L-0666: stops name no command
    overall_unknown = status == UNKNOWN and not any(a.get("status") == UNKNOWN for a in pending)
    if status not in (STALE, UNKNOWN) or not pending or overall_unknown \
            or not all(_settles(a) for a in pending):
        return {"state": UNSETTLED, "command": "", "reason": unsettled}
    return {"state": STALE, "command": pending[0]["command"], "reason": reason, "stop_reason": named}


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


def _phase(root, ticket, policy=True, deep=True):
    """`next`'s phase table (module docstring), with no session guard.
    `policy=False` is `status`'s read: the approve and open-questions reasons
    then name no policy, so status reads the same under every setting. `deep=False` (L-0551's
    owner list) stops at `review-unread` where a bundle rebuild or a gh call would come."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    folder = crew_ticket.ticket_dir(top, ticket)
    evidence = []

    source = None

    def answer(phase, stop, reason, command="", decision=None):  # L-0666: a stop's decision
        return {"ticket": ticket, "phase": phase, "stop": stop, "reason": reason, "command": command,
                "evidence": list(evidence), "index_source": source,
                **crew_autopilot_stops.decided(phase, stop, decision)}

    there, why = _main_folder(top, ticket)
    if there or why:
        return answer("folder-elsewhere", True, _folder_elsewhere(top, ticket, there, why))
    direction = os.path.join(folder, "direction.md")
    evidence.append(_rel(top, direction))
    if not os.path.isfile(direction):
        return answer("brainstorm", True, f"no {_rel(top, direction)}: needs "
                      "/crew:brainstorm - a human dialogue", "/crew:brainstorm")
    row = _index_row(top, ticket)
    status, source = row["status"], row["source"]
    evidence.append(_rel_inside(top, source) if source else ".work/INDEX.md")
    if status is not None and row["why"]:
        # QA F2: this checkout's row answered, but the main checkout's could
        # not be read, so the two were never compared -- said, never agreement.
        evidence.append(f"main checkout's INDEX not compared: {row['why']}")
    if row["other"]:
        (here, mine), (main, theirs) = row["other"]  # pylint: disable=unpacking-non-sequence
        return answer("direction-approval", True, f"index-disagreement: {here} says "
                      f"`{mine}` and the main checkout's {main} says `{theirs}` for "
                      f"{ticket} - the human makes them agree", decision="look")
    if status == "direction":
        return answer("direction-approval", True, "INDEX.md status is `direction`: "
                      "direction.md waits for the owner's yes in /crew:brainstorm")
    if status is None:
        asked = " or ".join(_rel_inside(top, path) for path in row["paths"])
        return answer("direction-approval", True, f"cannot tell whether {ticket}'s "
                      f"direction is approved: {asked} has no table row for {ticket}"
                      + (f" ({row['why']})" if row["why"] else "")
                      + " (Jira and ServiceDesk Plus modes write none). The human adds "
                      f"`{ticket} | ready | <risk> | <repo> | <title>` once it is agreed", decision="look")
    if status in INDEX_DONE:
        spec_text = read_text(os.path.join(folder, "spec.md")) if status == "done" else None
        if spec_text is not None and _header_status(spec_text) == "done":
            evidence.append(_rel(top, os.path.join(folder, "spec.md")))
            return _done_phase(top, ticket, answer, f".work/INDEX.md marks {ticket} `done` "
                               "and spec.md's header is `status: done`", deep=deep)
        return answer("closed", True, *crew_autopilot_gates.closed(f".work/INDEX.md marks {ticket} `{status}`: "
                      "never re-driven, whatever spec.md's header says", folder, status))
    stop, view = crew_autopilot_gates.gate(top, ticket, status, folder, status in DIRECTION_APPROVED,
                                           lambda: _open_questions(folder), answer, evidence)
    if stop:
        return stop
    if status not in DIRECTION_APPROVED:
        return answer("direction-approval", True, f"cannot tell whether {ticket}'s "
                      f"direction is approved: its .work/INDEX.md status is `{status}`, not one "
                      f"of {', '.join(DIRECTION_APPROVED)}. The human sets it to `ready` once "
                      "direction.md is agreed", decision="look")  # L-0666: cannot tell
    contract = crew_ticket.read_contract(top, ticket)
    evidence.append(_rel(top, os.path.join(folder, "spec.md")))
    header = None if contract["spec.md"] is None else _header_status(
        crew_ticket._text(contract["spec.md"]))  # pylint: disable=protected-access
    if header == "done":
        return _done_phase(top, ticket, answer, "spec.md header is `status: done`", deep=deep,
                           plan_text=None if contract["plan.md"] is None
                           else crew_ticket._text(contract["plan.md"]))  # pylint: disable=protected-access
    if header in HEADER_CLOSED:
        return answer("closed", True, *crew_autopilot_gates.closed(f"spec.md header is `status: {header}`: "
                      "nothing left in this ticket", folder, header))
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
    gate = crew_autopilot_split.gate(top, ticket, "spec", answer, policy)
    if gate:
        return gate
    evidence.append(_rel(top, os.path.join(folder, "plan.md")))
    if contract["plan.md"] is None:
        return answer("plan", False, "no plan.md", f"/crew:plan {ticket}")
    problems = crew_ticket.validate(top, ticket, contract)
    if problems:
        return answer("plan", True, "plan.md fails crew_ticket.validate: "
                      + "; ".join(problems), f"/crew:plan {ticket}")
    gate = crew_autopilot_split.gate(top, ticket, "plan", answer, policy)
    if gate:
        return gate
    sl = crew_autopilot_slices
    ctx = sl.context(top, ticket, crew_ticket._text(contract["plan.md"]))  # pylint: disable=protected-access
    if ctx and ctx["error"].startswith("PR slices:"):
        return answer("plan", True, f"plan.md's {ctx['error']}", f"/crew:plan {ticket}")
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
    if ctx and ctx["error"]:
        return answer("slices", True, ctx["error"])
    if ctx and ctx["piece"]["n"] in ctx["state"]["done"] and ctx["piece"]["n"] < ctx["m"]:
        return sl.with_slice(ctx, crew_autopilot_gates.before_ship(top, ticket, answer, _ship_phase(
            top, ticket, answer, "done by /crew:done (crew_autopilot.py slice-done)", ctx, deep)))
    found = crew_autopilot_gates.blocked(view, answer) or _review_phase(top, ticket, evidence, answer, deep)
    found = _auto_replan_route(top, ticket, found, answer) if policy else found
    if ctx:
        found = dict(found, reason=f"{sl.label(ctx)}: steps "
                     f"{sl.steps_text(ctx['piece']['steps'])} only - {found['reason']}")
    return sl.with_slice(ctx, found)


def _done_phase(top, ticket, answer, why, plan_text=None, deep=True):
    """The header reads `done`: `_ship_phase`, except on a sliced plan whose
    current slice is not the last (closing now would leave the later slices
    unbuilt) or whose slice state cannot be read (T-0059)."""
    sl = crew_autopilot_slices
    ctx = sl.context(top, ticket, plan_text)
    if ctx and ctx["error"]:
        return answer("slices", True, ctx["error"])
    if ctx and ctx["piece"]["n"] != ctx["m"]:
        return answer("slices", True, f"spec.md header is `status: done` while "
                      f"{sl.label(ctx)} is current: closing now would leave the "
                      "later slices unbuilt. A non-final slice's /crew:done sets "
                      "`in-progress` and runs crew_autopilot.py slice-done - a human "
                      "puts the header back")
    return sl.with_slice(ctx, crew_autopilot_gates.before_ship(top, ticket, answer, _ship_phase(
        top, ticket, answer, why, ctx, deep)))


def _current_rounds(ledger):
    """Rounds reserved under the current plan and slice: after the later of
    the latest successor's and the latest slice's (T-0059) boundary."""
    rounds = ledger.get("rounds") or []
    marks = []
    for key in ("successors", "slices"):
        rows = ledger.get(key) or []
        marks.append(rows[-1].get("after_round", 0) if rows and isinstance(rows[-1], dict)
                     else 0)
    if not all(crew_autopilot_slices.is_int(m) for m in marks):
        return rounds
    return rounds[max(marks):]


def _ledger_status(top, ticket):
    """`review_ledger.status` plus the ledger's `slices` rows (T-0059), which
    its summary does not carry: `_current_rounds` counts from them."""
    ledger = review_ledger.status(top, ticket)
    if ledger["state"] != review_ledger.UNKNOWN and "slices" not in ledger:
        data, state = review_ledger._load(ledger["path"])  # pylint: disable=protected-access
        if state == "ok" and isinstance(data, dict):
            rows = data.get("slices", [])
            count = len(data.get("rounds") or [])
            # A slice boundary that is not a list of rows each with an
            # in-range integer `after_round` cannot say which rounds are this
            # slice's: UNKNOWN, never "every round counts".
            if not isinstance(rows, list) or not all(
                    isinstance(r, dict) and crew_autopilot_slices.is_int(r.get("after_round"))
                    and 0 <= r["after_round"] <= count for r in rows):
                return dict(ledger, state=review_ledger.UNKNOWN)
            ledger = dict(ledger, slices=rows)
    return ledger


# T-0074: the one name `auto-reject` writes as `rejected.by`. No flag sets it.
AUTO_REJECT_BY = "autopilot (policy: autopilot.maxAutoReplans)"
# Review round 1 N1: the highest cap a setting can ask for; more reads as this.
MAX_AUTO_REPLANS = 5
AUTO_REJECT = ("python3 -B ${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/crew_autopilot.py "
               "auto-reject --root . --ticket {ticket}")


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def auto_replan_policy(root, ticket):
    """`{"allow", "reason", "used", "cap", "round", "blocks", "fixes", "capped",
    "successors"}` -- whether autopilot may reject `ticket`'s final review round
    itself and replan (T-0074). Pure read. Allows only when autopilot is armed,
    `autopilot.maxAutoReplans` is 1 or more, `approval_policy` would approve the
    successor plan, the ledger is REVIEWED, its latest round under this plan is
    a completed FINDINGS round whose counts and finding lines agree on at least
    one BLOCK, no round is left, the reviewer is another family than the author
    (`review_ledger`'s own rule), and fewer than the cap successor plans -- by
    whoever approved them -- are on the ledger. Anything that raises, or any
    value of the wrong type, refuses with "could not tell"."""
    result = {"allow": False, "reason": "", "used": None, "cap": 0, "round": None,
              "blocks": [], "fixes": [], "capped": False, "successors": []}
    try:
        return dict(result, **_auto_replan_decision(root, ticket))
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return dict(result, reason=(f"could not tell whether autopilot may reject the review "
                                    f"({type(exc).__name__}: {exc})"))


def _auto_replan_decision(root, ticket):  # pylint: disable=too-many-return-statements
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    conf = settings(top)
    cap = conf.get("maxAutoReplans")
    if not conf["armed"]:
        return {"reason": "autopilot.mode is not plan, so autopilot rejects nothing"}
    if not _count(cap):
        return {"reason": f"autopilot.maxAutoReplans is {cap!r}: could not tell"}
    if cap < 1:
        return {"reason": "autopilot.maxAutoReplans is 0 (off): a BLOCK round stops for "
                          "the owner"}
    approval = approval_policy(top, ticket)
    if approval.get("allow") is not True:
        return {"cap": cap, "reason": (
            f"the successor plan could not be self-approved ({approval.get('reason')}), so "
            "a reject would only take the owner's accept option away")}
    path = review_ledger.ledger_path(top, ticket)
    data, state = review_ledger.load(path)
    if state != "ok":
        return {"cap": cap, "reason": f"the review ledger is {state}: could not tell"}
    if data.get("state") != review_ledger.REVIEWED:
        return {"cap": cap, "reason": (f"the review ledger is {data.get('state') or 'EMPTY'}, "
                                       f"not {review_ledger.REVIEWED}")}
    found = _block_round(data, state, ticket, path)
    if "reason" in found:
        return dict(found, cap=cap)
    number, blocks, fixes = found["round"], found["blocks"], found["fixes"]
    successors = data.get("successors") or []
    used = len(successors)
    if used >= cap:
        return {"cap": cap, "round": number, "used": used, "capped": True,
                "successors": successors, "reason": (
                    f"autopilot.maxAutoReplans ({cap}) reached: {used} successor plan(s) "
                    "on the ledger")}
    return {"allow": True, "cap": cap, "round": number, "used": used, "blocks": blocks,
            "fixes": fixes, "successors": successors, "reason": (
                f"round {number} is FINDINGS with {len(blocks)} BLOCK and no round "
                f"left; autopilot.maxAutoReplans is {cap} ({used} used) and "
                f"{approval.get('reason')}")}


def _block_round(data, state, ticket, path):  # pylint: disable=too-many-return-statements
    """Conditions 5-8 of `auto_replan_policy` on a loaded ledger: the latest
    round under the current plan is a completed FINDINGS round whose counts
    and single-line finding lines agree on at least one BLOCK, no round is
    left, and the reviewer is another family (`review_ledger`'s own rule).
    `{"round", "blocks", "fixes"}`, or a dict with the `reason` it fails. The
    non-stop `replan` asks it again of the round it rejected (review round 1
    F1: the reject name alone is a string anyone can type)."""
    rounds = _current_rounds(data)
    row = rounds[-1] if rounds else None
    if not isinstance(row, dict) or row.get("status") != "completed":
        return {"reason": "no completed review round under the current plan"}
    number = row.get("round")
    if row.get("verdict") != "FINDINGS":
        return {"round": number, "reason": (
            f"round {number} is {row.get('verdict')!r}, not FINDINGS")}
    counts, findings = row.get("counts"), row.get("findings")
    if not isinstance(counts, dict) or not all(_count(counts.get(s))
                                               for s in ("BLOCK", "FIX", "NIT")):
        return {"round": number, "reason": (
            f"round {number}'s counts are {counts!r}, not three non-negative integers: "
            "could not tell")}
    if counts["BLOCK"] < 1:
        return {"round": number, "reason": (
            f"round {number} has no BLOCK; the 0-BLOCK case is review_ledger.py "
            "--auto-accept's")}
    if not isinstance(findings, list) or not all(
            isinstance(f, str) and "\n" not in f and "\r" not in f for f in findings):
        return {"round": number, "reason": (
            f"round {number} carries no single-line finding lines: could not tell")}
    blocks = [f for f in findings if f.strip().startswith("BLOCK|")]
    fixes = [f for f in findings if f.strip().startswith("FIX|")]
    if len(blocks) != counts["BLOCK"]:
        return {"round": number, "reason": (
            f"round {number} lists {len(blocks)} BLOCK line(s) for a BLOCK count of "
            f"{counts['BLOCK']}: could not tell")}
    left = review_ledger.summary(data, state, ticket, path).get("rounds_left")
    if not _count(left):
        return {"round": number, "reason": (
            f"rounds left is {left!r}: could not tell")}
    if left:
        return {"round": number, "reason": (
            f"{left} review round(s) left: fix, then /crew:review")}
    family = review_ledger._family_problem(row)  # pylint: disable=protected-access
    if family:
        return {"round": number, "reason": family}
    return {"round": number, "blocks": blocks, "fixes": fixes}


def _successor_rows(successors):
    return "; ".join(f"{str(s.get('plan_sha256'))[:12]} after round {s.get('after_round')} "
                     f"approved by {s.get('approved_by')}" for s in successors)


def _auto_replan_route(top, ticket, found, answer):
    """`next`'s T-0074 routes, on top of `_review_phase`'s answer: an
    out-of-rounds BLOCK round the policy allows is `auto-replan`; one refused
    only by the cap stops naming the cap and every successor; a NEEDS_REPLAN
    from autopilot's own reject of the latest round, still allowed, names
    `/crew:plan` without stopping. Anything else is `found`, byte for byte."""
    if found["phase"] == "accept-review":
        got = auto_replan_policy(top, ticket)
        if got["allow"] is True:
            return answer("auto-replan", False, f"{got['reason']}: autopilot rejects it "
                          f"itself (replan {got['used'] + 1} of {got['cap']})",
                          AUTO_REJECT.format(ticket=ticket))
        if got["capped"]:
            return dict(found, phase="auto-replan-cap", decision="replan", reason=(
                f"{got['reason']} ({_successor_rows(got['successors'])}) - the owner "
                f"decides. {found['reason'].replace('; ' + crew_autopilot_stops.FIXED_INSTEAD, '')}"))
    if found["phase"] == "replan" and found["stop"]:
        why = _auto_rejected(top, ticket)
        if why:
            return dict(found, stop=False, reason=why)
    return found


def _auto_rejected(top, ticket):
    """The non-stop `replan` reason, or "" for today's stop: the ledger's
    `rejected.by` is AUTO_REJECT_BY for its latest round, that round is the
    current plan's (after the last successor's `after_round`) and still passes
    conditions 5-8 (`_block_round`), and autopilot is still armed, under the
    cap, and allowed to approve the successor plan. The name alone proves
    nothing: `review_ledger.py --reject --by` can type it (review round 1)."""
    try:
        path = review_ledger.ledger_path(top, ticket)
        data, state = review_ledger.load(path)
        rejected = data.get("rejected") if state == "ok" else None
        rounds = data.get("rounds") or []
        latest = rounds[-1].get("round") if rounds and isinstance(rounds[-1], dict) else None
        current = _current_rounds(data) if state == "ok" else []
        conf = settings(top)
        cap, used = conf.get("maxAutoReplans"), len(data.get("successors") or [])
        if not (isinstance(rejected, dict) and rejected.get("by") == AUTO_REJECT_BY
                and _count(latest) and rejected.get("round") == latest
                and type(rejected.get("round")) is int  # pylint: disable=unidiomatic-typecheck
                and current and current[-1].get("round") == latest
                and "reason" not in _block_round(data, state, ticket, path)
                and conf["armed"] and _count(cap) and used < cap
                and approval_policy(top, ticket).get("allow") is True):
            return ""
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return ""
    return (f"{ticket} is NEEDS_REPLAN after autopilot's own reject of round {latest} "
            f"(replan {used + 1} of {cap}): /crew:plan writes a successor plan whose steps "
            f"quote every BLOCK and FIX line of round {latest}; the approve phase then "
            "decides under autopilot.approval")


def auto_reject(root, ticket):
    """(exit code, text). This module's second writing path (T-0074): when
    `auto_replan_policy` allows, `review_ledger.reject` under AUTO_REJECT_BY,
    which moves the ledger REVIEWED -> NEEDS_REPLAN and writes nothing else.
    Exit 2 `refused: <why>` writes nothing, a LedgerError included."""
    crew_ticket.check_ticket(ticket)
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    got = auto_replan_policy(top, ticket)
    if got["allow"] is not True:
        return 2, f"refused: {got['reason']}"
    try:
        review_ledger.reject(top, ticket, AUTO_REJECT_BY)
    except review_ledger.LedgerError as exc:
        return 2, f"refused: {exc}"
    return 0, "\n".join([f"auto-rejected {ticket}: round {got['round']}, {len(got['blocks'])} "
                         f"BLOCK / {len(got['fixes'])} FIX, replan {got['used'] + 1} of "
                         f"{got['cap']}"] + got["blocks"] + got["fixes"])


RECEIPT_STALE = "receipt is stale"  # T-0043: check_receipt's one confirmed-stale answer


def _review_phase(top, ticket, evidence, answer, deep=True):
    ledger = _ledger_status(top, ticket)
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
                      "spends the next round - a human decides", decision="spend-round-or-replan")
    receipt = ledger.get("receipt") or {}
    # L-0510: the ledger's one predicate decides whether a FINDINGS receipt
    # stands (owner-accepted, or auto-accepted with its row still passing the
    # guard), so this and /crew:done's --check-receipt cannot disagree.
    if latest.get("verdict") == "FINDINGS" and not review_ledger.receipt_stands(receipt, latest, top, ticket):
        if isinstance(fix := crew_autopilot_fix.decide(top, ticket, settings(top)["reviewPolicy"], ledger,
                                                       latest, answer, _toward_review, deep), dict):  # T-0067
            return fix
        data, state = review_ledger.load(ledger["path"])
        refusal = (review_ledger.auto_accept_refusal(data, ticket) if state == "ok"
                   else f"ledger is {state}: could not tell")
        how = ("the --auto-accept guard passes but no receipt was written; " if refusal is None
               else f"review_ledger.py --auto-accept refuses it ({refusal}); ")  # L-0666: decisions only
        return answer("accept-review", True, f"round {latest.get('round')} is FINDINGS; {how}the owner "
                      "accepts it with review_ledger.py --accept --by <owner>, or rejects it; "
                      "autopilot.reviewPolicy fix-and-rereview makes autopilot fix and re-review a "
                      "round with one left itself" + (fix or "") + "; " + crew_autopilot_stops.FIXED_INSTEAD)
    if not deep:  # L-0551: the owner list never rebuilds a bundle
        return answer(crew_autopilot_stops.UNREAD, True, crew_autopilot_stops.UNREAD_REVIEW)
    ok, message = review_ledger.check_receipt(top, ticket)
    left = ledger.get("rounds_left", 0)
    if not ok and (not isinstance(left, int) or left < 1):
        return answer("review", True, f"no review round left and no receipt stands "
                      f"({message}): /crew:review would reserve a third round and put "
                      f"{ticket} in NEEDS_REPLAN, which only a new approved plan leaves. A "
                      "human reverts the edit that staled the receipt, or replans", decision="revert-or-replan")
    if latest.get("refunded") is True and not ok:
        # Marked so `next_phase` does not read this rerun as "no progress"
        # (its docstring says what bounds it). Only the review itself: a
        # refresh that left its artifact stale is still no progress.
        found = _toward_review(top, ticket, answer, ok, message,
                               f"round {latest.get('round')} was a tool failure and "
                               "was refunded; ")
        return dict(found, refunded_rerun=found["phase"] == "review")
    if latest.get("verdict") == "FINDINGS":  # T-0043: its receipt stood; an edit staled it
        if ok or message.startswith(RECEIPT_STALE):
            return _toward_review(top, ticket, answer, ok, message)
        return answer("accept-review", True, f"round {latest.get('round')} is FINDINGS and accepted, "
                      f"but its receipt is not confirmed stale ({message}) - a human looks", decision="look")
    if latest.get("verdict") != "CLEAN" and not ok:
        return answer("accept-review", True, f"round {latest.get('round')} is "
                      f"{latest.get('verdict') or 'without a verdict'}: the reviewer did not "
                      "finish reading, and it cannot be accepted - a human reruns "
                      "/crew:review (spending a round) or replans", decision="spend-round-or-replan")
    return _toward_review(top, ticket, answer, ok, message)


def _toward_review(top, ticket, answer, ok, message, note=""):
    """Refresh before the next review round, then review; or done once a
    receipt stands. `note` prefixes the review reason (a refunded round). The
    docs phase (T-0022) runs first, before the refresh and every round."""
    docs = None if ok else crew_autopilot_docs.before_review(top, ticket, answer)
    if docs is not None:
        return docs
    refresh = _refresh_state(top, ticket)
    if refresh["state"] == UNAVAILABLE:
        return answer("refresh", True, refresh["reason"])
    if refresh["state"] == UNCOMMITTED:
        return _commit_refresh(ticket, answer, refresh["paths"])
    if not ok and refresh["state"] != FRESH:
        command = refresh["command"] if refresh["state"] == STALE else ""
        return answer("refresh", not command,
                      f"before the next review round - {refresh['reason']}", command)
    if not ok:
        return answer("review", False, f"{note}{message}; artifacts fresh",
                      f"/crew:review {ticket}")
    if refresh["state"] != FRESH:
        return answer("stale-after-review", True, "an artifact is stale after an "
                      "accepted review; refreshing now would stale the receipt - human "
                      f"decides. {refresh.get('stop_reason', refresh['reason'])}")
    return crew_autopilot_docs.after_review(top, ticket, answer) or answer(
        "done", False, f"{message}; artifacts fresh", f"/crew:done {ticket}")


def _inflight(root, ticket, runner, result):  # T-0049: next_stop's stop or None; a raise is in-flight
    try:
        stop = importlib.import_module("crew_inflight").next_stop(root, ticket, runner)
    except Exception as exc:  # pylint: disable=broad-except
        stop = {"phase": "in-flight", "command": "", "reason": f"in-flight: unknown - {ticket}: {_failure(exc)}"}
    return dict(result, stop=True, **crew_autopilot_stops.inflight(stop)) if stop else None


def _commit_refresh(ticket, answer, paths):
    """T-0063: every artifact is current but its refresh is uncommitted. The
    commit names exactly those paths -- `git commit -- <paths>` commits only
    them, so anything else already staged stays staged and out of it (QA
    F1); it changes no byte of the working state, which is what the review
    bundle is, so a receipt stays current and the same phase applies before
    review and after an accepted one. A path that is not printable is never
    put in a command or a reason line (QA F3): it stops, shown escaped."""
    if not paths:
        return answer("commit-refresh", True, "the refresh check says fresh-uncommitted "
                      "and names no path to commit - a human looks")
    shown = ", ".join(completion_audit.shown(p) for p in paths[:4]) + (
        f" (+{len(paths) - 4} more)" if len(paths) > 4 else "")
    if any(not p.isprintable() for p in paths):
        return answer("commit-refresh", True, f"refreshed artifacts are uncommitted: {shown}; "
                      "a path holds a character that is not printable, so no command is "
                      "printed for it - a human commits them")
    quoted = " ".join(shlex.quote(p) for p in paths)
    command = (f"git add -- {quoted} && "
               f'git commit -m "{ticket}: commit refreshed artifacts" -- {quoted}')
    return answer("commit-refresh", False, f"refreshed artifacts are uncommitted: {shown}; "
                  "the review bundle is the working state, so this commit leaves any "
                  "receipt current", command)


def next_phase(root, ticket, phases_run=0, last_command=None, max_phases=None,
               policy=True, runner=None):
    """`{"ticket", "phase", "stop", "reason", "command", "evidence"}`. A
    `stop` phase's `command` is what the HUMAN types, never run by autopilot.
    `max_phases` and `last_command` are the session's count and the command it
    last ran: reaching the count, or being handed the same command again, stops
    -- except `/crew:review` after a refunded tool-failure round: each run that
    records a round moves the ledger, `review_ledger.REFUND_LIMIT` per plan
    bounds how many are refunded, and `max_phases` bounds one that records none.
    So does a phase that would run while `crew_ticket.resolve_active` -- what
    the scope guard reads -- names another ticket, none, or a broken pointer.
    A focused, approved ticket whose tree has drifted outside Touch stops as
    `drift` first (`_drift`). `policy=False` is `status`'s: see `_phase`; `runner`: `_inflight` (T-0049)."""
    crew_ticket.check_ticket(ticket)
    result = _phase(root, ticket, policy)
    rerun = result.pop("refunded_rerun", False)
    rerun = result.pop("docs_rerun", False) or rerun  # T-0022: a recorded /crew:docs rerun
    drift = _drift(root, ticket, result)
    if drift is not None:
        return drift
    if result["stop"] or (runner and (result := _inflight(root, ticket, runner, result) or result)["stop"]):
        return result
    active, where, broken = crew_ticket.resolve_active(
        crew_ticket.toplevel(root) or os.path.abspath(root))
    if broken or active != ticket:
        return dict(result, stop=True, decision="activate-ticket", command="", reason=(
            f"ticket mismatch: the scope guard and completion audit judge edits by "
            f"{active or 'no ticket'} ({where}), not {ticket}, so {result['command']} would "
            f"run under the wrong approval and Touch - the owner re-points this worktree: "
            f"crew_ticket.py activate --ticket {ticket}"))
    if max_phases is not None and phases_run >= max_phases:
        return dict(result, stop=True, decision="continue", command=_drive(ticket), reason=(
            f"autopilot.maxPhases ({max_phases}) reached after {phases_run} phases; next "
            f"would be {result['phase']} - run /crew:autopilot {ticket} again"))
    if last_command and result["command"] == last_command and not rerun:
        return dict(result, stop=True, decision="look", command="", reason=(
            f"no progress: {last_command} ran and the files on disk still name it "
            f"({result['reason']}) - a human looks at why"))
    return {key: value for key, value in result.items() if key != "decision"}  # L-0666: stops only


# `next`'s phases that stop yet are not a stop for the loop: the T-0010 policy
# may approve or answer and go round again, so drift is judged before them.
POLICY_PHASES = ("approve", "open-questions")


def _drift(root, ticket, result):
    """`next`'s drift stop (T-0020), or None. Judged only when this worktree is
    focused on `ticket` and its plan is approved (before approval the audit
    fails every path, and spec and plan write only `.work/`, which it skips),
    and only ahead of a phase the loop would run. `completion_audit.audit` is
    read-only; an audit that raised, or could not be imported, stops: it is
    never a pass."""
    if result["stop"] and result["phase"] not in POLICY_PHASES:
        return None
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    state = focus_state(top)
    if state["unknown"]:
        return dict(result, phase="drift", stop=True, command="", decision="look", reason=(
            f"drift: whether {ticket} is focused, and so whether its tree must stay inside "
            f"Touch, could not be told: {state['unknown']}"))
    if state["focus"] != ticket:
        return None
    try:
        if crew_ticket.accepted(top, ticket)["status"] != "approved":
            return None
        ok, lines = importlib.import_module("completion_audit").audit(top, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        return dict(result, phase="drift", stop=True, command="", decision="look", reason=(
            f"drift: the audit could not run ({_failure(exc)}), so whether {ticket}'s tree "
            "stays inside Touch cannot be told"))
    if ok:
        return None
    shown = " ".join(" ".join(str(line).split()) for line in list(lines)[:2]) or (
        "the completion audit failed and gave no reason")
    return dict(result, phase="drift", stop=True, command="", decision="look", reason=(
        f"drift: {shown} - revert them, or file the finding (crew_autopilot.py focus "
        f"--findings --ticket {ticket}) and amend Touch through /crew:plan"))


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
                         f"arrives with {GOAL_RESUME_ARRIVES}", ""
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
        there, missing_why = _main_folder(top, ticket)
        if there or missing_why:
            return stopped(source, _folder_elsewhere(top, ticket, there, missing_why))
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
            rows = _open_index_rows(top)
            candidates = [found for found, _from_main in rows]
            if len(candidates) > 1:
                return stopped(".work/INDEX.md", "several open tickets and no pointer: "
                               + ", ".join(candidates)
                               + " - name one: /crew:autopilot <ticket>")
            if not candidates:
                return stopped(".work/INDEX.md", "no open ticket with a .work/tickets/ "
                               "folder - start one with /crew:brainstorm")
            ticket = candidates[0]
            source = ".work/INDEX.md (main checkout)" if rows[0][1] else ".work/INDEX.md"
    active, where, broken = crew_ticket.resolve_active(top)
    if broken:
        return stopped("active-ticket", f"{where}; a broken pointer is not guessed past - "
                       "fix it with crew_ticket.py activate")
    if where == "active-ticket" and active != ticket:
        return stopped(source, f"{source} names {ticket}, but this worktree's active ticket "
                       f"is {active}, and the scope guard and completion audit judge edits "
                       f"by {active}'s approval and Touch. Run /crew:autopilot {active}, or "
                       f"the human re-points it: crew_ticket.py activate --ticket {ticket}."
                       + _also(focus_guard(top, "run", ticket)))
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
    file first so neither collapse is taken for a configured value. The file is
    `crew_common.repo_config_file`'s -- the one `resolve_config` reads, which in
    a lane worktree is the main checkout's (T-0088)."""
    data, state = crew_ticket._read_json(  # pylint: disable=protected-access
        crew_common.repo_config_file(top, "config.json"))
    if state == "corrupt":
        return ".crew/config.json exists but could not be read as JSON"
    if state == "ok" and not isinstance(data, dict):
        return (f".crew/config.json is {type(data).__name__}, not a JSON object, so it "
                "could not be read")
    block = data.get("autopilot") if state == "ok" else None
    if block is not None and not isinstance(block, dict):
        return f"autopilot in .crew/config.json is {block!r}, not an object"
    return _unreadable_machine_autopilot()


def _unreadable_machine_autopilot():
    """Why the machine-global file's `autopilot` block cannot be told, or "".
    Since T-0050 the personal autopilot keys (`crew_state.PERSONAL_KEYS`) can be
    set in the machine file -- a global `approval: human` the stricter-wins rule keeps. But
    `crew_config.read_global_config` collapses a corrupt machine file to `{}`,
    so without this check that `human` would silently read as the default
    `risk`: the unknown collapsing into the wider value. The path is read at
    call time (`crew_config.GLOBAL_CONFIG_PATH`), the one `resolve_config`
    reads. Absent is known: no machine default."""
    path = crew_config.GLOBAL_CONFIG_PATH
    data, state = crew_ticket._read_json(path)  # pylint: disable=protected-access
    if state == "corrupt":
        return f"the machine-global config {path} exists but could not be read as JSON"
    if state == "ok" and not isinstance(data, dict):
        return (f"the machine-global config {path} is {type(data).__name__}, not a JSON "
                "object, so it could not be read")
    block = data.get("autopilot") if state == "ok" else None
    if not isinstance(block, (dict, type(None))):
        return f"autopilot in the machine-global config {path} is {block!r}, not an object"
    return ""


def settings(root):
    """`{"mode", "armed", "maxPhases", "saw", "deploy", "deploySaw", "approval",
    "questions", "maxAutoReplans", "reviewPolicy" (T-0067: crew_autopilot_fix), "ship",
    "knownFailures", "ciTimeoutMinutes", "warnings", "policyWarnings"}` (T-0027: the
    approval/questions value warnings, also in `warnings`, which `status` leaves out). Read through
    `crew_config.resolve_config`, which reads both layers: the autopilot keys
    with a `crew_state.PERSONAL_KEYS` row are personal (T-0050), so where
    `.crew/config.json` and the machine-global file both set one the stricter
    value wins, and a silent layer imposes nothing (`crew_guards.
    effective_personal`); `maxAutoReplans`, `sleep` and T-0011's three ship keys
    are repo-only (`crew_state.REPO_ONLY_AUTOPILOT`). `scope.allowCliApproval`,
    which `crew_ticket.cli_approval_allowed` reads, is still the repo file's alone.
    `mode` arms only when it is
    exactly the string `plan`; `maxPhases` must be a positive int, else 12;
    `deploy` is exactly one of DEPLOY_VALUES, else `none`; `approval` and
    `questions` must be one of POLICIES, else `human`; `maxAutoReplans` (T-0074)
    must be a non-negative int, else 0 (off), and reads at most
    MAX_AUTO_REPLANS; `ship` is exactly one of SHIP_POLICIES, else `pr` (the
    non-merging direction); `knownFailures` a list of strings, else `[]`;
    `ciTimeoutMinutes` a positive int, else 60.

    A `.crew/config.json` or machine-global file that is present but
    unreadable, or an `autopilot` value in either that is not an object, is
    could-not-tell: both policies read
    UNKNOWN, `mode` reads `off`, `deploy` reads `none`, and a warning names
    the cause. That is never the default `risk`, which `resolve_config` would
    otherwise hand back for both. An absent file or an absent (or null) block
    is known and reads the defaults. `deploy_allowed` reads `_settings_at`,
    after its own per-layer checks, not this."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    cause = _unreadable_autopilot(top)
    if cause:
        return {"mode": "off", "armed": False, "maxPhases": crew_state.AUTOPILOT_DEFAULTS["maxPhases"],
                "saw": None, "deploy": "none", "deploySaw": None, "approval": UNKNOWN,
                "questions": UNKNOWN, "maxAutoReplans": 0, "reviewPolicy": UNKNOWN,  # T-0067
                "day": {"approval": UNKNOWN, "questions": UNKNOWN},
                "sleep": {"state": crew_sleep.UNKNOWN, "schedule": None, "applied": [],
                          "overrides": {key: None for key in crew_sleep.OVERRIDES}},
                "ship": "pr", "knownFailures": [],
                "ciTimeoutMinutes": crew_state.AUTOPILOT_DEFAULTS["ciTimeoutMinutes"],
                "warnings": [(f"{cause}, so autopilot.approval and autopilot.questions "
                              "could not be told (both read as unknown, which never "
                              "approves or takes an answer) and autopilot reads as off")],
                "policyWarnings": []}
    result = _settings_at(top)
    inert, policy = crew_config.autopilot_inert_split(top, _failure, ("approval", "questions"))
    result["warnings"] += inert  # T-0070
    result["policyWarnings"] += policy  # T-0027: an object policy value names its inert keys
    return result


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
    replans = block.get("maxAutoReplans", 0)
    if isinstance(replans, bool) or not isinstance(replans, int) or replans < 0:
        warnings.append(f"autopilot.maxAutoReplans is {replans!r}, not a non-negative "
                        "integer; using 0 (off: a BLOCK round stops for the owner)")
        replans = 0
    if replans > MAX_AUTO_REPLANS:
        warnings.append(f"autopilot.maxAutoReplans is {replans}, above the limit of "
                        f"{MAX_AUTO_REPLANS}; using {MAX_AUTO_REPLANS}")
        replans = MAX_AUTO_REPLANS
    deploy_saw = block.get("deploy", "none")
    deploy = deploy_saw if _exact(deploy_saw, DEPLOY_VALUES) else "none"
    if deploy != deploy_saw:
        warnings.append(f"autopilot.deploy is {deploy_saw!r}: only the exact strings "
                        "'nonprod' and 'all' arm it, so it reads as none")
    if deploy != "none":
        warnings.append(f"autopilot.deploy is {deploy!r}, but nothing in this crew version "
                        "dispatches a deploy: T-0045 consumes it; deploy-allowed answers "
                        "the policy only")
    crew_json = _read_json(crew_common.repo_config_file(top, "crew.json"))
    if isinstance(crew_json, dict) and "autopilot" in crew_json \
            and "autopilot" not in crew_state.load_config(top):
        warnings.append("autopilot is set in .crew/crew.json, which crew does not read "
                        "for this key; move it to .crew/config.json")
    ship = block.get("ship", crew_state.AUTOPILOT_DEFAULTS["ship"])
    if not _exact(ship, SHIP_POLICIES):
        warnings.append(f"autopilot.ship is {ship!r}, not 'pr' or 'merge'; reading it as "
                        "'pr' (open the PR, never merge)")
        ship = "pr"
    known = block.get("knownFailures", [])
    if not isinstance(known, list) or not all(isinstance(k, str) for k in known):
        warnings.append(f"autopilot.knownFailures is {known!r}, not a list of check names; "
                        "using [] (no failing check is excused)")
        known = []
    timeout = block.get("ciTimeoutMinutes")
    default_timeout = crew_state.AUTOPILOT_DEFAULTS["ciTimeoutMinutes"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        warnings.append(f"autopilot.ciTimeoutMinutes is {timeout!r}, not a positive "
                        f"integer; using {default_timeout}")
        timeout = default_timeout
    day, policy_warnings = {}, []  # T-0027: status leaves the policy-value warnings out
    for key in ("approval", "questions"):
        day[key], warning = _policy_setting(block, key)
        policy_warnings += [warning] if warning else []
    warnings += policy_warnings
    review = crew_autopilot_fix.review_policy(block, warnings)  # T-0067
    sleep = _sleep_at(top, block)
    warnings += sleep.pop("warnings")
    policies, sleep["applied"] = _overlay(day, sleep)
    return {"mode": "plan" if armed else "off", "armed": armed, "maxPhases": limit,
            "saw": mode, "deploy": deploy, "deploySaw": deploy_saw,
            "approval": policies["approval"], "questions": policies["questions"],
            "maxAutoReplans": replans, "reviewPolicy": review,
            "ship": ship, "knownFailures": list(known), "ciTimeoutMinutes": timeout,
            "day": day, "sleep": sleep, "warnings": warnings, "policyWarnings": policy_warnings}


# Strictest first: under a sleep state that cannot be told, a valid night
# override applies only when it comes earlier here than the day value.
STRICTNESS = ("human", "risk", "self")


def _overlay(day, sleep):
    """`(policies, applied)`: asleep, every non-null override replaces the
    day value; unknown, one replaces it only when stricter (human > risk >
    self), so could-not-tell never loosens a policy and never drops a
    tightening the owner set; off or awake, the day values. `tightenOnly`
    (L-0652: a manual sleep outside the window, or a manual wake inside it)
    is stricter-only whatever the state."""
    policies, applied = dict(day), []
    for key, value in sleep["overrides"].items():
        if value is None:
            continue
        stricter = STRICTNESS.index(value) < STRICTNESS.index(policies[key])
        if sleep.get("tightenOnly") or sleep["state"] == crew_sleep.UNKNOWN:
            take = stricter
        else:
            take = sleep["state"] == crew_sleep.ASLEEP
        if take:
            policies[key] = value
            applied.append(key)
    return policies, applied


def _sleep_block(top, block):
    """`autopilot.sleep` as the reader sees it. The resolved block cannot say
    whether the file held a non-object there (`merge_defaults` drops it for
    the default), so the raw repo file is asked first."""
    raw = crew_state.load_config(top).get("autopilot")
    saw = raw.get("sleep") if isinstance(raw, dict) else None
    sleep = saw if saw is not None and not isinstance(saw, dict) else block.get("sleep")
    return {} if sleep is None else sleep


def _sleep_at(top, block):
    """T-0053: `crew_sleep.resolve` of `autopilot.sleep`, read from the clock
    on every call and never cached. A raising read, clock or resolve is
    could-not-tell: state unknown, with the overrides still read where the
    block can be, so `_overlay` keeps a stricter one; and a warning."""
    sleep, found = None, {key: crew_sleep.STRICTEST for key in crew_sleep.OVERRIDES}
    try:
        sleep = _sleep_block(top, block)
        return crew_sleep.resolve(sleep, crew_sleep.now(), POLICIES, crew_autopilot_sleep._manual_found(top),
                                  crew_ticket.cli_approval_allowed(top))
    except Exception as exc:  # pylint: disable=broad-except
        try:
            found = crew_sleep.read_overrides(sleep, POLICIES)[0]
        except Exception:  # pylint: disable=broad-except
            pass
        return {"state": crew_sleep.UNKNOWN, "schedule": None, "overrides": found,
                "warnings": [f"autopilot.sleep could not be resolved ({type(exc).__name__}: "
                             f"{_safe_text(exc, str)[:120]}); per key the stricter of the day "
                             "value and the night value applies"]}


def _hhmm(iso):
    """`HH:MM`, in local time, of an ISO time `crew_sleep` produced (a
    UTC-aware one is shown in the machine's time zone)."""
    found = datetime.datetime.fromisoformat(iso)
    return (found.astimezone() if found.tzinfo else found).strftime("%H:%M")


def _sleep_span(sleep):
    """What an asleep note names: the window, or a manual sleep's end."""
    if sleep.get("source") == "manual":
        return f"by hand until {_hhmm(sleep['until'])}"
    return sleep["schedule"]


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
    layers = (("repo", crew_common.repo_config_file(top, "config.json")),
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
    """(policy, risk, warnings), or raises when the settings cannot be read.
    `risk` carries `sleep` (T-0053): `""`, or, only when a sleep override set
    `key`, ` (asleep <schedule>; day value <day>)` or the could-not-tell
    form, which `_noted` puts after the reason."""
    conf = settings(top)
    sleep, day = conf.get("sleep") or {}, (conf.get("day") or {}).get(key)
    note = ""
    if key in sleep.get("applied", ()) and sleep.get("state") == crew_sleep.ASLEEP:
        note = f" (asleep {_sleep_span(sleep)}; day value {day})"
    elif key in sleep.get("applied", ()) and sleep.get("tightenOnly"):
        note = f" (awake by hand; the stricter autopilot.sleep.{key} over day value {day})"
    elif key in sleep.get("applied", ()):
        note = (f" (sleep could not be told; the stricter autopilot.sleep.{key} over "
                f"day value {day})")
    return conf[key], dict(_ticket_risk(top, ticket), sleep=note), [
        w for w in conf["warnings"] if f"autopilot.{key} " in w]


def _noted(result):
    """`result` with its `sleep` note (T-0053) after its reason; a result
    that never read the settings carries an empty note."""
    note = result.get("sleep", "")
    return dict(result, reason=result["reason"] + note, sleep=note)


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
    before. An unreadable ledger refuses, like anything that cannot be told.
    While asleep (T-0053) the policy is the night value, and `reason` and
    `sleep` say so."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    pinned = _pinned().get((top, ticket))
    if pinned is not None:
        return dict(pinned)
    return _noted(_approval_policy(top, ticket))


# `approve`'s one decision, replayed to `crew_ticket.approve`'s re-check while
# that call runs (T-0053 review round 1): the receipt's `by=`, the printed line
# and the check that lets the write happen are the same read of the clock, so
# a window edge between two reads cannot make them disagree. Process-local,
# set and cleared inside `approve` only.
_PINNED = threading.local()


def _pinned():
    """This thread's pinned decisions, `{(top, ticket): decision}`."""
    return getattr(_PINNED, "decisions", {})


def _approval_policy(root, ticket):
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
              "known": risk["known"], "warnings": warnings, "sleep": risk["sleep"]}
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
    `risk: low`. No `allowCliApproval` rule; anything unreadable stops.
    While asleep (T-0053) the policy is the night value, and `reason` and
    `sleep` say so."""
    return _noted(_question_policy(root, ticket))


def _question_policy(root, ticket):
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    try:
        policy, risk, warnings = _decision(top, ticket, "questions")
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return {"action": STOP, "policy": UNKNOWN, "risk": "high", "known": False,
                "warnings": [], "reason": (f"could not tell the questions policy "
                                           f"({type(exc).__name__}: {exc})")}
    result = {"action": STOP, "policy": policy, "risk": risk["risk"],
              "known": risk["known"], "warnings": warnings, "sleep": risk["sleep"]}
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
        cause = _unreadable_autopilot(top)  # T-0027: name the cause, never "mode is not plan"
        return 2, (f"refused: {cause}, so autopilot could not tell whether it is armed and "
                   f"approves nothing; {human}" if cause else f"refused: autopilot.mode is not "
                   f"plan, so autopilot approves nothing; {human}")
    got = approval_policy(top, ticket)
    if not got["allow"]:
        return 2, f"refused: {got['reason']}; {human}"
    replan = importlib.import_module("crew_autopilot_replan").replan_check(top, ticket)  # L-0670
    if replan["applies"] and not replan["ok"]:
        return 2, f"refused: {replan['reason']}; {human}"
    _PINNED.decisions = {(top, ticket): got}
    try:
        _receipt, successor = crew_ticket.approve(
            top, ticket, by=f"autopilot:{got['policy']}", via=crew_ticket.AUTOPILOT)
    finally:
        _PINNED.decisions = {}
    text = (f"self-approved {ticket} under approval={got['policy']}, "
            f"risk={got['risk'] if got['known'] else 'unknown (high)'}{got.get('sleep', '')}")
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


GOAL_ROUTE_FIRST = "goal takes free text, never on a shell line: the command runs route --root . --first goal"
GOAL_RESUME_ARRIVES = "L-0541"  # `--goal` resume; the goal file itself: crew_autopilot_goal.py
# Script actions whose code (parsers, usage and `main`) lives in a sibling module.
EXTRA_ACTIONS = {"goal-propose": "crew_autopilot_goal", "goal-approve": "crew_autopilot_goal",
                 "tracker": "crew_autopilot_docs", "sleep": "crew_autopilot_sleep",
                 "wake": "crew_autopilot_sleep", "split": "crew_autopilot_split",
                 "slice": "crew_autopilot_slices", "slice-done": "crew_autopilot_slices",
                 "next-slice": "crew_autopilot_slices", "replan-check": "crew_autopilot_replan"}


def stops():
    """Every stop, from code: AUTONOMOUS_STOPS, the fixed ones, the human ones."""
    def rows(pairs):
        return [{"id": slug, "text": text} for slug, text in pairs]
    return {"autonomous": rows(crew_state.AUTONOMOUS_STOPS), "fixed": rows(FIXED_STOPS),
            "human": rows(HUMAN_STOPS), "procedure": rows(PROCEDURE_STOPS),
            "decisions": rows(row[:2] for row in crew_autopilot_stops.OWNER_DECISIONS)}  # L-0666


def _existing_ticket(top, token):
    """Whether `token` is a plain ticket id naming a `.work/tickets/` folder."""
    try:
        return os.path.isdir(crew_ticket.ticket_dir(top, token))
    except crew_ticket.TicketError:
        return False


def route(root, first, ticket=""):
    """`{"sub", "stop", "reason"}` for the command's first argument. First match, exact and case-
    sensitive: a SUBCOMMANDS name; nothing or `--goal` (run); an INDEX-shaped id or an existing
    `.work/tickets/<token>/` (run). Anything else stops: `crew_ticket` accepts `stauts` as an id,
    so a typo is refused here rather than driven as a ticket. Then T-0020's `focus_guard`, before
    the AVAILABLE check, so `assign` and `goal` are refused under an explicit focus whether or not
    they have landed. `ticket` is the word after the subcommand when `route_args` knows it
    (FOCUS_OFF for `focus off`); a bare id is its own ticket."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    token = first or ""
    if token in SUBCOMMANDS:
        sub = token
    elif token == "":
        sub = "run"
    elif token == GOAL_FLAG:
        refusal = focus_guard(top, "goal")
        return {"sub": "run", "stop": True,
                "reason": refusal or f"run {GOAL_FLAG} <slug> arrives with {GOAL_RESUME_ARRIVES}"}
    elif _INDEX_ID.fullmatch(token) or _existing_ticket(top, token):
        sub, ticket = "run", token
    else:
        return {"sub": "", "stop": True, "reason": UNKNOWN_SUB}
    refusal = focus_guard(top, sub, ticket)
    if refusal:
        return {"sub": sub, "stop": True, "reason": refusal}
    if sub not in AVAILABLE:
        return {"sub": sub, "stop": True,
                "reason": f"{AUTOPILOT} {sub} arrives with {ARRIVES.get(sub, 'a later ticket')}"}
    return {"sub": sub, "stop": False, "reason": ""}


NOT_A_TICKET = ("not a ticket id: at most one, INDEX-shaped (T-0018) or naming an "
                "existing .work/tickets/<id>/")


def route_args(root, text):
    """`route` for the command's whole argument string, plus `ticket`: the word after a subcommand, or
    a bare ticket id itself. The command passes `$ARGUMENTS` whole because Claude Code numbers
    positional arguments from `$0` and leaves an out-of-range `$N` literal. A second word that is
    not a ticket, or a third word, stops; it is never read as a ticket -- except `focus off`,
    exactly, which sets `off` (T-0020): the only route to `focus --off`, so focus is released only
    when the owner's own arguments say so. A ticket is held to `focus_guard` once it is known."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    words = (text or "").split()
    rest = words[1:] if words and words[0] in SUBCOMMANDS else words
    off = words[:1] == ["focus"] and rest == [FOCUS_OFF]
    got = dict(route(top, words[0] if words else "", FOCUS_OFF if off else ""), ticket="")
    if got["sub"] == "focus":
        got["off"] = off
    if got["stop"]:
        return got
    if words[:1] == [GOAL_SUB]:
        return dict(got, stop=True, reason=GOAL_ROUTE_FIRST)
    if words[:1] == [WAVE]:  # T-0029: also `set` and `tickets`; crew_wave.py imports this module
        import crew_wave  # pylint: disable=import-outside-toplevel,cyclic-import
        return crew_wave.wave_args(top, got, rest)
    if words[:1] and words[0] in NO_TICKET and rest:
        return dict(got, stop=True, reason=f"{AUTOPILOT} {words[0]} takes no other word")
    if words[:1] == ["run"] and rest[:1] == [GOAL_FLAG]:
        return dict(route(top, GOAL_FLAG), ticket="")
    if off:
        return got
    if len(rest) > 1 or (rest and not (_INDEX_ID.fullmatch(rest[0])
                                       or _existing_ticket(top, rest[0]))):
        return dict(got, stop=True, reason=NOT_A_TICKET)
    refusal = focus_guard(top, got["sub"], rest[0]) if rest else None
    if refusal:
        return dict(got, stop=True, reason=refusal)
    return dict(got, ticket=rest[0] if rest else "")


# --- focus (T-0020) -------------------------------------------------------------

FOCUS_OFF = "off"
FOCUS_RELEASE = f"{AUTOPILOT} focus off"
FOCUS_REMINDER = ("reminder: Claude Code's built-in /focus only toggles the display (just "
                  "your prompt, summary, and response); it does not scope work, and only "
                  "you can type it")
FOCUS_SCOPE_OFF = ("the scope guard is off: writes outside Touch are not refused as they "
                   "happen; autopilot's drift stop still applies")
FINDINGS_TODO = "TODO.md"
FINDINGS_FILE = "out-of-scope.md"
FINDINGS_WHY = "the scope guard exempts nothing outside Touch"


def _also(text):
    return f" {text}" if text else ""


FOCUS_FILE = "autopilot-focus.json"


def focus_path(root):
    """`<git-common-dir>/crew/autopilot-focus.json`, the explicit focus marker,
    or None outside git. A JSON object keyed by worktree top-level, as the
    active-ticket pointer is, so a focus is this worktree's only."""
    state = crew_ticket.state_dir(root)
    return os.path.join(state, FOCUS_FILE) if state else None


FOCUS_LOCK_WAIT = 5.0


# PowerShell reads U+2018..U+201B as single quotes too.
_PS_QUOTES = ("'", "\u2018", "\u2019", "\u201a", "\u201b")
# C0, DEL and C1 controls (a terminal acts on C1 too), the PowerShell quotes,
# and the bidi embedding/override/isolate controls U+202A..U+202E and
# U+2066..U+2069 (they reorder what a person reads): the JSON form instead.
_UNSAFE_PATH = re.compile(r"[\x00-\x1f\x7f-\x9f\u2018-\u201b\u202a-\u202e\u2066-\u2069]|\s{2,}")


def _posix_quoted(path):
    return "'" + path.replace("'", "'\\''") + "'"


def _ps_quoted(path):
    for mark in _PS_QUOTES:
        path = path.replace(mark, mark * 2)
    return "'" + path + "'"


def _paste_safe(path):
    """Whether `path` survives into a printed command unchanged: no control
    character (C0, DEL or C1), no bidi control, no run of whitespace (`_one_line` would collapse it), no
    quote PowerShell also reads, and the POSIX command parses back to exactly
    `rm -- <path>`."""
    if _UNSAFE_PATH.search(path):
        return False
    rm_part = f"rm -- {_posix_quoted(path)}"
    try:
        return shlex.split(rm_part) == ["rm", "--", path] and _one_line(rm_part) == rm_part
    except ValueError:
        return False


def _remove_by_hand(path, effect):
    """`effect`, then paste-ready removal commands for `path` (POSIX and
    PowerShell) when it is paste-safe, else the path as JSON and "remove
    this file by hand", with no command that could name another file."""
    if not _paste_safe(path):
        # JSON escapes control characters; a run of spaces is escaped too, so
        # `_one_line`'s collapse cannot change the path it names.
        shown = re.sub(r" {2,}", lambda run: "\\u0020" * len(run.group()), json.dumps(path))
        return f"{effect}: remove this file by hand: {shown}"
    return (f"{effect}: rm -- {_posix_quoted(path)} (POSIX shell) or "
            f"Remove-Item -LiteralPath {_ps_quoted(path)} (PowerShell)")


def _focus_remedy(path):
    """The way out of an unknown marker, naming its exact path: `focus off`
    refuses to touch a file it cannot read, so the human removes it."""
    return _remove_by_hand(path, "removing it drops EVERY worktree's focus, not only this one's")


def _focus_marker(top):
    """(path, mapping, unknown). `unknown` is "" or why the marker could not be
    read -- not a file, a file that does not parse (or cannot be read), one
    that is not an object, or this worktree's entry not a ticket (an
    INDEX-shaped id, or one with a `.work/tickets/` folder) -- ending with
    `_focus_remedy`. An unknown is never read as "no focus"."""
    path = focus_path(top)
    if not path:
        return None, {}, ""
    if os.path.lexists(path) and not os.path.isfile(path):
        return path, None, f"the focus marker {path} is not a file; {_focus_remedy(path)}"
    data, state = crew_ticket._read_json(path)  # pylint: disable=protected-access
    if state == "corrupt" or (state == "ok" and not isinstance(data, dict)):
        return path, None, f"the focus marker {path} does not parse; {_focus_remedy(path)}"
    mapping = data if state == "ok" else {}
    entry = mapping.get(top)
    if entry is not None and not (isinstance(entry, str) and (
            _INDEX_ID.fullmatch(entry) or _existing_ticket(top, entry))):
        return path, None, (f"the focus marker {path} names {entry!r}, not a ticket; "
                            f"{_focus_remedy(path)}")
    return path, mapping, ""


class _FocusLockError(Exception):
    """The marker's lock could not be taken; nothing was written."""


class _focus_lock:  # pylint: disable=invalid-name,too-few-public-methods
    """`<marker>.lock`, crew_config_files.Lock's exclusive create with a
    bounded wait, around every read-modify-write of the marker: two worktrees
    running `focus` at once would otherwise both read the old mapping and the
    later write would drop the other's entry while both report success. A
    lock that cannot be taken raises _FocusLockError; nothing writes
    unlocked."""

    def __init__(self, path):
        import crew_config_files  # pylint: disable=import-outside-toplevel
        self.path, self.files = path, crew_config_files
        self.lock = crew_config_files.Lock(path, FOCUS_LOCK_WAIT)

    def __enter__(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.lock.__enter__()
        except (self.files.Busy, OSError) as exc:
            raise _FocusLockError(
                f"refused: the focus marker's lock {self.path}.lock could not be taken "
                f"({exc}); nothing written. If no focus command is running, a process "
                "died holding it; " + _remove_by_hand(
                    self.path + ".lock", "removing the lock releases it")) from exc
        return self

    def __exit__(self, *exc):
        self.lock.__exit__(*exc)


def focus_state(root):
    """`{"focus", "unknown", "pointer", "broken", "why", "scope_mode"}` for this
    worktree. `focus` is the explicit focus marker's ticket, set only by
    `focus <id>` (owner decision, 2026-10-05): the active-ticket pointer alone
    is never a focus. `unknown` is "" or why the marker could not be read --
    could-not-tell, its own value, with `focus` None beside it. `pointer` is
    the active-ticket pointer's ticket (never the `.work/INDEX.md` fallback);
    `broken`/`why` are its state. `scope_mode` is
    `crew_ticket.configured_mode`'s value."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    active, where, broken = crew_ticket.resolve_active(top)
    mode, _why = crew_ticket.configured_mode(top)
    _path, mapping, unknown = _focus_marker(top)
    return {"focus": None if unknown else mapping.get(top), "unknown": unknown,
            "pointer": active if where == "active-ticket" and not broken else None,
            "broken": bool(broken), "why": where if broken else "", "scope_mode": mode}


def focus_guard(root, sub, ticket=""):
    """None when `sub` (with `ticket`, "" for none, FOCUS_OFF for `focus off`) may run under this
    worktree's focus, else the refusal, naming the focused ticket and `/crew:autopilot focus off`.
    `status`, `focus off` and the NO_TICKET subcommands (L-0652's `sleep` and `wake`, which neither
    start nor switch work) always run. No marker entry: no focus, everything runs. A marker that
    could not be read refuses everything else -- whether focus is on cannot be told, so nothing may
    start or switch work. Focused on T-A: a pointer naming anything but T-A refuses all but `focus
    T-A` (which re-points it); else `run` or `split` with no ticket or T-A, and `focus` alone or
    `focus T-A`, run; anything else -- another ticket, `assign`, `goal`, a subcommand this does not
    know -- is refused."""
    if sub == "status" or sub in NO_TICKET or (sub == "focus" and ticket == FOCUS_OFF):
        return None
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    state = focus_state(top)
    if state["unknown"]:
        return ("whether focus is on could not be told, so only status, sleep and wake run "
                f"until the human repairs or removes the marker: {state['unknown']}")
    focus = state["focus"]
    if focus is None:
        return None
    if sub == "focus" and ticket in ("", focus):
        return None
    if state["pointer"] != focus:
        names = (f"is broken ({state['why']})" if state["broken"]
                 else f"names {state['pointer'] or 'no ticket'}")
        return (f"focus is on {focus}, but this worktree's active-ticket pointer {names}: "
                f"type {AUTOPILOT} focus {focus} to re-point it, or {FOCUS_RELEASE}")
    # T-0058: `split` looks at the focused ticket's size; it starts no other work.
    if sub in ("run", "split") and ticket in ("", focus):
        return None
    what = (f"{AUTOPILOT} {sub} {ticket}" if ticket else f"{AUTOPILOT} {sub}").strip()
    return (f"focus is on {focus}: {what} would start or switch to other work, which focus "
            f"refuses. Type {FOCUS_RELEASE} first")


def _scope_line(mode):
    if mode == "off":
        return f"scope.mode=off: {FOCUS_SCOPE_OFF}"
    return (f"scope.mode={mode}: the scope guard and the completion audit judge every write "
            "against the active ticket's Touch")


def _write_marker(path, mapping):
    """Write `mapping`, or remove the file when it is empty, so a released
    focus leaves the common dir as it was."""
    if mapping:
        crew_ticket._write_json(path, mapping)  # pylint: disable=protected-access
    elif os.path.lexists(path):
        os.remove(path)


def _unknown_refusal(head, unknown):
    return f"{head}: {unknown}"


def focus_set(root, ticket):
    """(ok, line). Writes this worktree's entry in the focus marker, then, only
    when the active-ticket pointer names another ticket or none, points it at
    `ticket` through `crew_ticket.activate` -- marker first, so a failed
    activate leaves a focus the guard refuses on (pointer mismatch), never a
    switch without one. The marker's read-modify-write holds `_focus_lock`,
    and the focus-on-another-ticket check is made again inside it. `activate`
    checks the id's shape only, so the folder is checked here. Refuses,
    writing nothing, an unreadable marker, a lock it cannot take, a broken
    pointer and a focus on another ticket; the same ticket again, already
    pointed at, writes nothing. On a re-point `line` also carries activate's
    scope-base line, an unknown or a fallback included, never dropped."""
    crew_ticket.check_ticket(ticket)
    top = crew_ticket.toplevel(root)
    if not top:
        return False, f"refused: {root} is not a git repository"
    path = focus_path(top)
    if not path:
        return False, "refused: there is no git common dir to keep the focus marker in"
    state = focus_state(top)
    if state["unknown"]:
        return False, _unknown_refusal(
            "refused: whether focus is on could not be told, so nothing is written",
            state["unknown"])
    if state["broken"]:
        return False, (f"refused: the active-ticket pointer is broken ({state['why']}); "
                       "the human repairs it (crew_ticket.py activate --ticket <id>)")
    if not os.path.isdir(crew_ticket.ticket_dir(top, ticket)):
        return False, (f"refused: {ticket} has no .work/tickets/{ticket}/ folder, and a "
                       "focus on it would be a broken pointer")
    if state["focus"] not in (None, ticket):
        return False, (f"refused: focus is on {state['focus']}; type {FOCUS_RELEASE} "
                       "first")
    if state["focus"] == ticket and state["pointer"] == ticket:
        return True, f"focus={ticket} (already; nothing written)"
    try:
        with _focus_lock(path):
            _path, mapping, unknown = _focus_marker(top)
            if unknown:
                return False, _unknown_refusal(
                    "refused: whether focus is on could not be told, so nothing is written",
                    unknown)
            if mapping.get(top) not in (None, ticket):
                return False, (f"refused: focus is on {mapping[top]}; type "
                               f"{FOCUS_RELEASE} first")
            if mapping.get(top) != ticket:
                _write_marker(path, dict(mapping, **{top: ticket}))
    except _FocusLockError as exc:
        return False, str(exc)
    line = f"focus={ticket} (this worktree only: {top})"
    if state["pointer"] == ticket:
        return True, line
    # activate also records `.crew/.scope-base` (T-0061); its line -- a
    # could-not-tell or a fallback included -- is the caller's to see.
    message = crew_ticket.activate(top, ticket)[2]
    was = state["pointer"] or "no ticket"
    return True, f"{line}\nactive ticket: {was} -> {ticket}\n{message}".rstrip("\n")


def focus_off(root):
    """(ok, line). Drops this worktree's focus marker entry and no other,
    under `_focus_lock`, and leaves the active-ticket pointer as it is: the
    pointer was never the focus. A marker that could not be read is refused,
    never deleted and never read as released (fail-closed): its line ends
    with the removal command for the human."""
    top = crew_ticket.toplevel(root)
    if not top:
        return False, f"refused: {root} is not a git repository"
    path = focus_path(top)
    if not path:
        return True, "focus=none (nothing was set)"
    try:
        with _focus_lock(path):
            _path, mapping, unknown = _focus_marker(top)
            if unknown:
                return False, _unknown_refusal(
                    "focus=unknown - focus off does not clear a marker it cannot read",
                    unknown)
            was = mapping.get(top)
            if was is not None:
                _write_marker(path, {key: value for key, value in mapping.items()
                                     if key != top})
    except _FocusLockError as exc:
        return False, str(exc)
    after = focus_state(top)
    if after["unknown"]:
        return False, _unknown_refusal("focus=unknown - focus off could not clear it",
                                       after["unknown"])
    if after["focus"] is not None:
        return False, f"focus={after['focus']} - focus off could not clear it"
    return True, f"focus=none (released {was})" if was else "focus=none (nothing was set)"


def focus_show(root):
    """(True, line): `focus=<id>`, `focus=none` or `focus=unknown <why>`."""
    state = focus_state(root)
    if state["unknown"]:
        return True, f"focus=unknown {state['unknown']}"
    return True, f"focus={state['focus'] or 'none'}"


def findings_target(root, ticket):
    """`{"path", "reason"}`: where an out-of-scope finding is filed while
    focused. `TODO.md` only when `ticket`'s APPROVED Touch covers it; else the
    ticket's own `.work/tickets/<id>/out-of-scope.md`, which the scope guard
    always allows and the audit skips."""
    crew_ticket.check_ticket(ticket)
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    approval = crew_ticket.accepted(top, ticket)
    touch = (approval.get("touch") or []) if approval.get("status") == "approved" else []
    if crew_ticket.in_touch(FINDINGS_TODO, touch):
        return {"path": FINDINGS_TODO, "reason": f"{ticket}'s approved Touch covers TODO.md"}
    return {"path": f".work/tickets/{ticket}/{FINDINGS_FILE}",
            "reason": f"TODO.md is not in {ticket}'s approved Touch, and {FINDINGS_WHY}"}


def focus_text(root, ticket="", off=False, findings=False):
    """(code, text) for the `focus` CLI: the answer, the scope.mode line, and
    FOCUS_REMINDER last, whatever happened. Exit 1 on a refusal or a crash."""
    try:
        if findings:
            got = findings_target(root, ticket)
            ok, line = True, f"findings={got['path']} reason={got['reason']}"
        elif off:
            ok, line = focus_off(root)
        elif ticket:
            ok, line = focus_set(root, ticket)
        else:
            ok, line = focus_show(root)
        mode = focus_state(root)["scope_mode"]
        lines = line.splitlines() + [_scope_line(mode)]
    except Exception as exc:  # pylint: disable=broad-except
        ok, lines = False, [f"refused: {_failure(exc)}"]
    return (0 if ok else 1), "\n".join(_one_line(text) for text in lines + [FOCUS_REMINDER])


# Who acts when `next` stops at each phase it names. A phase not here -- a
# rename, `invalid` from a crash -- reads `unknown`, never `autopilot`.
WAITING = {phase: "owner" for phase in (
    "brainstorm", "direction-approval", "open-questions", "spec", "plan", "approve",
    "review", "replan", "implement", "accept-review", "refresh", "stale-after-review",
    "done", "auto-replan", "auto-replan-cap", NEEDS_OWNER) + crew_autopilot_docs.WAITING
    + crew_autopilot_split.WAITING + crew_autopilot_slices.WAITING}
WAITING["split-check"] = "autopilot"  # T-0058: autopilot looks, then goes on
WAITING["ship"] = "owner"
WAITING["closed"] = "nobody"
WAITING["drift"] = "owner"
WAITING.update(crew_autopilot_gates.WAITING, fix="owner")  # L-0550; T-0067: `fix` runs at stop=0
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
    if who in crew_autopilot_gates.ELSEWHERE:
        return crew_autopilot_gates.waiting(who, result)
    if phase == "drift":
        return ("owner - reverts the paths outside Touch, or amends Touch and approves "
                "again")
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
    or spec.md's closed header (HEADER_CLOSED). Read directly, because `_phase` checks
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
        crew_ticket._text(spec)) in HEADER_CLOSED  # pylint: disable=protected-access


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
        return f"not usable: {rendered} - goal resume arrives with {GOAL_RESUME_ARRIVES}"
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
    policy = conf.get("policyWarnings") or []  # T-0027: status reads no policy
    return {"mode": conf["mode"], "maxPhases": conf["maxPhases"],
            "warnings": [w for w in conf["warnings"] if w not in policy],
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


def _sleep_line(sleep):
    """`settings`' third line (T-0053): the window's state and overrides."""
    line = _line(sleep=sleep["state"], schedule=sleep["schedule"] or "none",
                 **{key: sleep["overrides"][key] or "-" for key in crew_sleep.OVERRIDES})
    line += " " + _line(source=sleep.get("source", "schedule"))
    if sleep.get("until"):
        line += " " + _line(until=_hhmm(sleep["until"]))
    if sleep["state"] == crew_sleep.UNKNOWN or sleep.get("tightenOnly"):
        # Which night values the stricter rule applied (`--json`'s `applied`).
        line += " " + _line(applied=",".join(sleep.get("applied") or []) or "-")
    return line


def _policy_main(args):
    """`approve` and `questions-check`: exit 0 only on a yes. A crash is a
    refusal (exit 1), never an approval or a valid file."""
    try:
        if args.action in ("approve", "auto-reject"):
            code, text = (approve if args.action == "approve" else auto_reject)(
                args.root, args.ticket)
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
    """deploy-allowed's `(text, json_text, report)`; never raises. Stage 1 builds all three from
    `deploy_allowed` inside one try. Stage 2, on any exception from stage 1 (a raise, a result
    missing a key, a value JSON cannot dump), builds them from the literal verdict `ask`; the
    exception only decorates the reason, and one that cannot be described gets a constant."""
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


def _runner_ok(runner):  # an import failure is True here, and next's in-flight stop
    try:
        return runner in importlib.import_module("crew_inflight").RUNNERS
    except Exception:  # pylint: disable=broad-except
        return True


def _ship_text(result):
    checks = result["checks"]
    families = result["families"]
    return "\n".join([
        _one_line(_line(action=result["action"], stop=int(result["stop"]),
                        pr=result["pr"] or "", reason=result["reason"])),
        _one_line("checks: " + (", ".join(f"{c.get('name')}={c.get('state')}" for c in checks)
                                if checks else "(none read)" if checks is None
                                else "(none reported)")),
        _one_line("families: " + (", ".join(crew_ship._family(f) or "unknown" for f in families)
                                  if families else "(not read)" if families is None
                                  else "(none)"))])


def main(argv):
    # `next` quotes the ledger's auto-accept refusal, which can quote reviewer
    # text: write UTF-8 whatever the console code page (review_ledger.utf8_stdio).
    review_ledger.utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("next", "resume", "settings", "stops", "route", "status", "approve",
                 "questions-check", "auto-reject"):
        action = sub.add_parser(name)
        action.add_argument("--json", action="store_true")
        if name != "stops":
            action.add_argument("--root", default=".")
    ship_action = sub.add_parser("ship")
    ship_action.add_argument("--json", action="store_true")
    ship_action.add_argument("--root", default=".")
    for name in ("next", "approve", "questions-check", "auto-reject", "ship"):
        sub.choices[name].add_argument("--ticket", required=True)
    focus = sub.add_parser("focus")
    focus.add_argument("--root", default=".")
    focus.add_argument("--ticket", default="")
    focus_how = focus.add_mutually_exclusive_group()
    focus_how.add_argument("--off", action="store_true")
    focus_how.add_argument("--findings", action="store_true")
    sub.choices["resume"].add_argument("--ticket", default="")
    sub.choices["status"].add_argument("--ticket", default="")
    given = sub.choices["route"].add_mutually_exclusive_group()
    given.add_argument("--args", default=None)
    given.add_argument("--first", default=None)
    sub.choices["next"].add_argument("--phases-run", type=int, default=0)
    sub.choices["next"].add_argument("--last-command", default="")
    sub.choices["next"].add_argument("--runner", default="")  # checked lazily: _runner_ok
    for module in sorted(set(EXTRA_ACTIONS.values())):
        importlib.import_module(module).add_parsers(sub)
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
    # Read-only but for approve's receipt, sleep/wake's state and ship's push: git must not
    # refresh the index's stat cache.
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    if args.action in ("approve", "questions-check", "auto-reject"):
        return _policy_main(args)
    if args.action == "next" and args.runner and not _runner_ok(args.runner):
        sys.stderr.write("crew_autopilot.py next: --runner is not one of crew_inflight.RUNNERS\n")
        return 2
    if args.action in EXTRA_ACTIONS:
        return importlib.import_module(EXTRA_ACTIONS[args.action]).main(args)
    if args.action == "focus":
        if (args.off and args.ticket) or (args.findings and not args.ticket):
            sys.stdout.write("refused: focus takes --ticket <id>, --off, or --findings "
                             f"--ticket <id>\n{FOCUS_REMINDER}\n")
            return 2
        code, text = focus_text(args.root, args.ticket, args.off, args.findings)
        sys.stdout.write(text + "\n")
        return code
    if args.action == "ship":
        try:
            result = ship(args.root, args.ticket)
        except Exception as exc:  # pylint: disable=broad-except
            # A crash cannot tell whether it is safe to merge: a stop, never silence.
            result = _ship_result(args.ticket, "stop", True, _failure(exc))
        text = _ship_text(result)
    elif args.action == "status":
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
        fields = {"sub": result["sub"], "stop": int(result["stop"]), "ticket": result["ticket"]}
        if "off" in result:
            fields["off"] = int(result["off"])
        if result["sub"] == WAVE:
            fields.update(set=result.get("set", ""), tickets=",".join(result.get("tickets", [])))
        text = _line(**fields, reason=result["reason"])
    elif args.action == "stops":
        result = stops()
        text = "\n".join(f"{kind} {row['id']}: {row['text']}"
                         for kind, rows in result.items() for row in rows)
    elif args.action == "settings":
        result = settings(args.root)
        text = "\n".join([_line(mode=result["mode"], maxPhases=result["maxPhases"],
                                deploy=result["deploy"],
                                maxAutoReplans=result["maxAutoReplans"])]
                         + [_line(approval=result["approval"], questions=result["questions"])]
                         + [_sleep_line(result["sleep"]), _line(reviewPolicy=result["reviewPolicy"])]
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
                                settings(args.root)["maxPhases"], runner=args.runner or None)
        except Exception as exc:  # pylint: disable=broad-except
            # A crash cannot tell the phase: it is a stop, never no answer.
            result = {"ticket": args.ticket, "phase": "invalid", "stop": True,
                      "command": "", "reason": _failure(exc), "evidence": [], "decision": "look"}
        text = _line(phase=result["phase"], stop=int(result["stop"]), command=result["command"],
                     **({"decision": result["decision"]} if result["stop"] else {}), reason=result["reason"])
    if args.json and args.action != "deploy-allowed":
        # status holds STATUS_MAX_LINES as JSON too: one line, nothing dropped.
        text = json.dumps(result, indent=None if args.action == "status" else 2)
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
