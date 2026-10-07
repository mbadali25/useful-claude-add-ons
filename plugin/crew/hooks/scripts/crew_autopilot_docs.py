"""T-0022: autopilot's docs phase and tracker step, split out of
`crew_autopilot.py` (pylint's module-length limit). `crew_autopilot` calls
`before_review` and `after_review` from `_toward_review`, appends
`FIXED_STOPS` to its own, and dispatches the `tracker` action here.

    python3 crew_autopilot.py tracker --root . --ticket <id> [--after CMD] [--json]

`next`'s table gains, after the review rows (crew_autopilot.py's docstring):

  receipt not current, docs unknown      docs-unknown        stop at once
  receipt not current, a doc MISSING     docs                /crew:docs <id>
    ... after two recorded runs          docs                stop
  receipt current, documents owed        docs-after-review   stop, nothing written

The docs phase runs before the refresh and every review round, so the review
receipt covers the documents. A MISSING line from `crew_docs_check.ticket_docs`
is owed, and `/crew:docs` can write it; its `unknown` (no trusted scope base,
an unreadable docs.json, git that could not read a base blob) and a check that
raised or will not import stop at once as `docs-unknown`, because another run
cannot settle them -- never read as ok, never rerun. After each
`/crew:docs <id>` the command runs `tracker --after "/crew:docs <id>"`, which
records the attempt; two attempts recorded since the latest review round stop
with the documents named, and only a recorded attempt exempts the rerun from
`no-progress`. A document owed after an accepted receipt stops as
`docs-after-review`: writing it would stale the receipt.

`tracker` derives the status from disk (`disk_status`: done or review from
spec.md's header, in-progress once something outside `.work/` changed since a
recorded (non-fallback) scope base,
planned once approved, spec, direction) and calls T-0021's
`crew_tracker.move`. updated, unchanged, not applicable: continue; delegated:
the command to run in-session (Jira, SDP); could not update: stop with the
reason and the `crew_tracker.py move` retry. No `crew_tracker` module stops as
"tracker interface unavailable (T-0021 not landed)". Safe after a receipt
only because every tracker write lands outside the bundle (`.work/INDEX.md`,
a vault outside the worktree or one git ignores; T-0021 refuses one it does
not), which `test_tracker_move_after_receipt_keeps_bundle_hash` measures.

`tracker` writes, never into a review bundle: what `crew_tracker.move`
writes, and, with `--after /crew:docs ...`, one attempt appended to
`.work/tickets/<id>/autopilot-docs.json`. Exit 0 always; a crash prints
`stop=1` with its reason, never silence. `crew_autopilot` is imported lazily
(`_ap`), so importing this module never imports it back.
"""
import importlib
import json
import os
import sys

import crew_ticket
import scope_base
from crew_common import git_out, read_text

DOCS_OK = "ok"
DOCS_MISSING = "missing"
DOCS_UNKNOWN = "unknown"
DOCS_ATTEMPTS = 2
DOCS_RECORD = "autopilot-docs.json"
DOCS_UNAVAILABLE = "docs check unavailable (crew_docs_check.py could not be imported)"
TRACKER_UNAVAILABLE = "tracker interface unavailable (T-0021 not landed)"
# Appended to crew_autopilot.FIXED_STOPS.
FIXED_STOPS = (
    ("docs-missing", "a document is still MISSING after two /crew:docs runs"),
    ("docs-unknown", "the docs check cannot tell (no trusted scope base, an unreadable "
                     "docs.json, git failed, the check raised): another /crew:docs run "
                     "cannot settle it"),
    ("docs-after-review", "a document is MISSING after an accepted review: writing it now "
                          "stales the receipt"),
    ("tracker-failed", "the tracker step could not update the tracker (could not update, "
                       "or the status on disk could not be told)"),
    ("tracker-unavailable", "the tracker interface (crew_tracker.py, T-0021) is absent"),
)
# Phases `status` reports as waiting on the owner (crew_autopilot.WAITING).
WAITING = ("docs", "docs-unknown", "docs-after-review")


def _ap():
    """crew_autopilot, imported when first needed (it imports this module)."""
    return importlib.import_module("crew_autopilot")


def _docs_state(root, ticket):
    """`{"state": ok|missing|unknown, "missing": [...], "reason"}` from
    T-0022's `crew_docs_check.ticket_docs`. `missing` only for the check's
    own `missing`, which a `/crew:docs` run can fix; anything else -- its
    `unknown`, a status it does not name, a check that raised or will not
    import -- is `unknown`, never `ok` and never another docs run."""
    try:
        check = importlib.import_module("crew_docs_check")
    except ImportError:
        return {"state": DOCS_UNKNOWN, "missing": [], "reason": DOCS_UNAVAILABLE}
    try:
        result = check.ticket_docs(root, ticket)
    except Exception as exc:  # pylint: disable=broad-except
        return {"state": DOCS_UNKNOWN, "missing": [],
                "reason": f"the docs check could not run ({exc})"}
    status = result.get("status")
    if status == DOCS_OK:
        return {"state": DOCS_OK, "missing": [], "reason": ""}
    missing = check.missing_documents(result)
    if status == DOCS_MISSING and missing:
        return {"state": DOCS_MISSING, "missing": missing,
                "reason": "docs check says missing: MISSING: " + "; ".join(missing)}
    return {"state": DOCS_UNKNOWN, "missing": missing,
            "reason": f"docs check says {status}: {result.get('reason')}"}


def before_review(top, ticket, answer):
    """The docs phase ahead of the refresh and the next review round: None
    when the documents read ok, else `next`'s answer (`docs-unknown` stops at
    once; `docs` runs `/crew:docs`, or stops after DOCS_ATTEMPTS recorded
    runs). `docs_rerun` marks a recorded rerun, exempt from `no-progress`."""
    docs = _docs_state(top, ticket)
    if docs["state"] == DOCS_UNKNOWN:
        return answer("docs-unknown", True, f"{docs['reason']} - another /crew:docs run "
                      "cannot settle this; a human looks")
    if docs["state"] == DOCS_OK:
        return None
    tried = _docs_attempts(top, ticket)
    if tried >= DOCS_ATTEMPTS:
        return answer("docs", True, f"documents still MISSING after {tried} "
                      f"/crew:docs runs: {docs['reason']} - a human looks",
                      f"/crew:docs {ticket}")
    found = answer("docs", False, f"before the refresh and the next review round - "
                   f"{docs['reason']}", f"/crew:docs {ticket}")
    return dict(found, docs_rerun=tried > 0)


def after_review(top, ticket, answer):
    """None when the documents read ok after an accepted receipt, else the
    `docs-after-review` stop: writing a document now stales the receipt."""
    docs = _docs_state(top, ticket)
    if docs["state"] == DOCS_OK:
        return None
    return answer("docs-after-review", True, "a document is MISSING (or the docs check "
                  "cannot tell) after an accepted review; writing it now stales the "
                  f"receipt - human decides. {docs['reason']}")


def _docs_record_path(top, ticket):
    return os.path.join(crew_ticket.ticket_dir(top, ticket), DOCS_RECORD)


def _review_position(top, ticket):
    """`(plan, rounds)`: `plan` counts the successor plans the review ledger
    records, `rounds` the rounds under the current plan. `(-1, -1)` when the
    ledger cannot say. A successor plan restarts `rounds` at zero, so the plan
    number keeps an earlier plan's attempts from counting against it."""
    try:
        ap = _ap()
        ledger = ap.review_ledger.status(top, ticket)
        return (len(ledger.get("successors") or []),
                len(ap._current_rounds(ledger)))  # pylint: disable=protected-access
    except Exception:  # pylint: disable=broad-except
        return -1, -1


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _docs_attempts(top, ticket):
    """`/crew:docs` runs autopilot recorded since the latest review round of the
    current plan. An unreadable record counts as spent: it can only stop, never
    loop. An attempt recorded before plans were numbered reads as plan 0."""
    path = _docs_record_path(top, ticket)
    if not os.path.lexists(path):
        return 0
    data = _ap()._read_json(path)  # pylint: disable=protected-access
    attempts = data.get("attempts") if isinstance(data, dict) else None
    if not isinstance(attempts, list):
        return DOCS_ATTEMPTS
    # A malformed attempt is a record that cannot be read: spent, never skipped.
    if not all(isinstance(a, dict) and _is_int(a.get("round")) and _is_int(a.get("plan", 0))
               for a in attempts):
        return DOCS_ATTEMPTS
    plan, rounds = _review_position(top, ticket)
    return sum(1 for a in attempts if a["round"] == rounds and a.get("plan", 0) == plan)


def record_docs_attempt(root, ticket):
    """Append one `/crew:docs` run to `.work/tickets/<id>/autopilot-docs.json`
    (under `.work/`, so outside every review bundle), computed in full and
    written once through a temp file. Returns the attempts since the latest
    review round, this one included."""
    crew_ticket.check_ticket(ticket)
    ap = _ap()
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    path = _docs_record_path(top, ticket)
    data = ap._read_json(path) if os.path.lexists(path) else {  # pylint: disable=protected-access
        "attempts": []}
    attempts = data.get("attempts") if isinstance(data, dict) else None
    if not isinstance(attempts, list):
        # Never reset a record that cannot be read: it reads as spent.
        raise RuntimeError(f"{ap._rel(top, path)} is unreadable; "  # pylint: disable=protected-access
                           "not overwritten")
    docs = _docs_state(top, ticket)
    plan, rounds = _review_position(top, ticket)
    attempts.append({"plan": plan, "round": rounds, "missing": docs["missing"],
                     "state": docs["state"]})
    text = json.dumps({"ticket": ticket, "attempts": attempts}, indent=2) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temp, path)
    return _docs_attempts(top, ticket)


def disk_status(root, ticket):
    """The lifecycle status files on disk say, or None when none can be told:
    done/review from spec.md's header, in-progress once a path outside `.work/`
    changed since a recorded (non-fallback) scope base -- `activate` records the
    base before implement, so the base alone is not work begun; git that cannot
    tell is None -- planned once the approval is accepted, spec once spec.md
    exists, direction once direction.md does."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    folder = crew_ticket.ticket_dir(top, ticket)
    spec = read_text(os.path.join(folder, "spec.md"))
    header = _ap()._header_status(spec) if spec is not None else None  # pylint: disable=protected-access
    if header in ("done", "review"):
        return header
    base, source, _why = scope_base.resolve(top, ticket)
    if source == scope_base.RECORDED:
        # `crew_ticket.activate` records the base before implement starts, so a
        # recorded base alone is not work begun: a change outside `.work/` is.
        started = _changed_since(top, base)
        if started is None:
            return None
        if started:
            return "in-progress"
    if spec is not None and crew_ticket.accepted(top, ticket).get("status") == "approved":
        return "planned"
    if spec is not None:
        return "spec"
    if os.path.isfile(os.path.join(folder, "direction.md")):
        return "direction"
    return None


def _changed_since(top, base):
    """Whether anything outside `.work/` changed since `base` (committed, staged,
    unstaged or untracked), or None when git could not tell."""
    diff = git_out(top, "diff", "--name-only", base, "--")
    untracked = git_out(top, "ls-files", "--others", "--exclude-standard")
    if diff is None or untracked is None:
        return None
    paths = (diff + "\n" + untracked).replace("\\", "/").splitlines()
    return any(p.strip() and not p.startswith(".work/") for p in paths)


def _retry(ticket, status):
    return (f"python3 ${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/crew_tracker.py move --root . "
            f"--ticket {ticket} --to {status}")


def tracker_step(root, ticket):
    """T-0022's tracker step: move the tracker to `disk_status` through
    T-0021's `crew_tracker.move`. `{"state", "stop", "status", "command",
    "reason", "lines"}`; `state` is updated, unchanged, not applicable,
    delegated (run `command` in-session) or stop. Writes only what
    `crew_tracker.move` writes: `.work/INDEX.md`, a vault outside the
    worktree or one git ignores, or nothing (Jira, SDP)."""
    crew_ticket.check_ticket(ticket)
    try:
        tracker = importlib.import_module("crew_tracker")
    except ImportError:
        return {"state": "stop", "stop": True, "status": None, "command": "",
                "reason": TRACKER_UNAVAILABLE, "lines": []}
    status = disk_status(root, ticket)
    if not status:
        return {"state": "stop", "stop": True, "status": None, "command": "",
                "reason": f"could not tell {ticket}'s status from disk (no direction.md)",
                "lines": []}
    report = tracker.move(root, ticket, status)
    results = report.get("results") or []
    lines = [tracker._line(r) for r in results]  # pylint: disable=protected-access
    failed = [r for r in results if r.get("state") not in (
        tracker.UPDATED, tracker.UNCHANGED, tracker.NOT_APPLICABLE, tracker.DELEGATED)]
    if failed or not results:
        why = "; ".join(f"{r.get('backend')}: {r.get('reason')}" for r in failed) \
            or "the tracker returned no result"
        return {"state": "stop", "stop": True, "status": status, "command": _retry(ticket, status),
                "reason": f"tracker could not update to {status}: {why}", "lines": lines}
    delegated = [r for r in results if r.get("state") == tracker.DELEGATED]
    if delegated:
        return {"state": tracker.DELEGATED, "stop": False, "status": status,
                "command": delegated[0].get("command") or "",
                "reason": delegated[0].get("reason") or "", "lines": lines}
    state = (tracker.UPDATED if any(r.get("state") == tracker.UPDATED for r in results)
             else tracker.UNCHANGED if any(r.get("state") == tracker.UNCHANGED for r in results)
             else tracker.NOT_APPLICABLE)
    return {"state": state, "stop": False, "status": status, "command": "",
            "reason": "; ".join(lines), "lines": lines}


def add_parsers(sub):
    """`tracker` on crew_autopilot.py's subparsers."""
    action = sub.add_parser("tracker")
    action.add_argument("--json", action="store_true")
    action.add_argument("--root", default=".")
    action.add_argument("--ticket", required=True)
    action.add_argument("--after", default="")


def main(args):
    """`tracker` (T-0022): with `--after "/crew:docs ..."`, record that docs
    run first; then the tracker step. Exit 0 with the answer in the line, as
    `next` does: a crash, or a docs run that could not be recorded, is
    `stop=1`, never silence."""
    ap = _ap()
    try:
        if args.after.split()[:2] == ["/crew:docs", args.ticket]:
            record_docs_attempt(args.root, args.ticket)
        result = tracker_step(args.root, args.ticket)
    except Exception as exc:  # pylint: disable=broad-except
        result = {"state": "stop", "stop": True, "status": None, "command": "",
                  "reason": ap._failure(exc), "lines": []}  # pylint: disable=protected-access
    text = ap._line(tracker=result["state"].replace(" ", "-"),  # pylint: disable=protected-access
                    stop=int(result["stop"]), status=result["status"] or "",
                    command=result["command"],
                    reason=ap._one_line(result["reason"]))  # pylint: disable=protected-access
    text += "".join(f"\n{ap._one_line(row)}" for row in result["lines"])  # pylint: disable=protected-access
    sys.stdout.write((json.dumps(result, indent=2) if args.json else text) + "\n")
    return 0
