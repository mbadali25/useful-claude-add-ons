"""L-0666: every autopilot stop names an owner decision, never a mechanical step.

One case per stop site. `SITES` walks the source of the modules whose stops
reach `next` (`crew_autopilot.py` and the `crew_autopilot_*.py` modules
handed its `answer`) for `answer(<phase>, <not False>, ...)`, `dict(...,
stop=<not False>)`, `dict(..., phase=...)` and `stopped(...)`; each case
names its site by a fragment of that site's source and builds the state that
reaches it. A new stop site without a case fails `test_every_stop_site_has_a_case`.

Each `next` stop must carry a `decision` from `OWNER_DECISIONS`, a `command`
that is empty or that decision's own, and a reason with no `MECHANICAL` shape;
`resume` and `route` stops carry no decision and are held to MECHANICAL.
Every case builds a throwaway repo under pytest's tmp_path.
"""

import ast
import collections
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_autopilot_docs
import crew_autopilot_slices
import crew_autopilot_split
import crew_autopilot_stops
import crew_ship
import crew_ticket
import review_ledger
from scope_fixtures import approve_as_user, make_repo
from test_crew_autopilot import (_COMMAND, _SCRIPT, _approved, _index, _ledger, _receipt, _round,
                                 _spec_text, _ticket, _with_line2, _write)
import test_crew_autopilot_ship as ship_fixtures

T = "T-1"
SCRIPTS = os.path.dirname(crew_autopilot.__file__)
WALKED = ("crew_autopilot.py", "crew_autopilot_gates.py", "crew_autopilot_docs.py",
          "crew_autopilot_split.py")
DOCS_OK = {"state": crew_autopilot_docs.DOCS_OK, "missing": [], "reason": ""}


def _false(node):
    return isinstance(node, ast.Constant) and node.value is False


def _is_stop(call, node):
    """`answer(<phase>, <not False>, ...)`, `dict(..., stop=<not False>)`, `dict(...,
    phase=...)` with no `stop=` (it keeps its base's stop), or `stopped(...)`."""
    keys = {k.arg: k.value for k in node.keywords}
    if call == "answer":
        return len(node.args) >= 2 and not _false(node.args[1])
    if call == "dict":
        return ("stop" in keys and not _false(keys["stop"])) or ("phase" in keys and "stop" not in keys)
    return call == "stopped"


def stop_sites():
    """[(file, line, source)] for every stop site in WALKED."""
    found = []
    for name in WALKED:
        with open(os.path.join(SCRIPTS, name), encoding="utf-8") as handle:
            src = handle.read()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            call = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if _is_stop(call, node):
                found.append((name, node.lineno, " ".join(ast.get_source_segment(src, node).split())))
    return sorted(found)


# --- builders: each returns `next`'s (or resume's, route's) result ------------------

def _docs(monkeypatch, state=crew_autopilot_docs.DOCS_OK, reason=""):
    monkeypatch.setattr(crew_autopilot_docs, "_docs_state", lambda root, ticket: {
        "state": state, "missing": [], "reason": reason})


def _refresh(monkeypatch, **state):
    monkeypatch.setattr(crew_autopilot, "_refresh_state", lambda root, ticket: dict(
        {"command": "", "reason": ""}, **state))


def _receipt_says(monkeypatch, ok, message):
    monkeypatch.setattr(review_ledger, "check_receipt", lambda root, ticket: (ok, message))


def _next(root, **kwargs):
    return crew_autopilot.next_phase(str(root), T, **kwargs)


def _ctx(n=1, m=1, done=(), error=""):
    return {"slices": [], "state": {"done": list(done)}, "m": m, "error": error,
            "piece": {"n": n, "name": "first", "steps": [1]}}


def _sliced(monkeypatch, ctx):
    monkeypatch.setattr(crew_autopilot_slices, "context", lambda top, ticket, plan_text=None: ctx)


def _done(tmp, monkeypatch, branch="T-1-build", pr=None, **block):
    root = ship_fixtures._done_ticket(tmp, **block)  # pylint: disable=protected-access
    monkeypatch.setattr(crew_ship, "_branch", lambda top: branch)
    monkeypatch.setattr(crew_ship, "read_pr", lambda top, name: pr)
    monkeypatch.setattr(crew_ship, "_tree_stop", lambda top: "")
    for name in ("branch_stop", "expected_base_stop", "merged_base_stop", "order_stop"):
        monkeypatch.setattr(crew_autopilot_slices, name, lambda *a: "")
    _receipt_says(monkeypatch, True, "receipt current")
    return root


def _pr(state):
    return ship_fixtures._pr(state)  # pylint: disable=protected-access


def b_finished_closed(tmp, mp):
    return _next(_done(tmp, mp, pr=_pr("OPEN"), ship="pr"))


def b_unarmed_slice(tmp, mp):
    root = _approved(tmp)
    ship_fixtures._config(root, mode="off")  # pylint: disable=protected-access
    _sliced(mp, _ctx(1, 2, done=[1]))
    return _next(root)


def b_unarmed_closed(tmp, mp):
    return _next(_done(tmp, mp, mode="off"))


def b_no_branch(tmp, mp):
    return _next(_done(tmp, mp, branch=None))


def b_branch_stop(tmp, mp):
    root = _done(tmp, mp)
    _sliced(mp, _ctx(1, 1))
    mp.setattr(crew_autopilot_slices, "branch_stop", lambda ctx, branch: "slice 1 is recorded on X")
    return _next(root)


def b_no_pr(tmp, mp):
    return _next(_done(tmp, mp, pr=None))


def b_base_stop(tmp, mp):
    root = _done(tmp, mp, pr=_pr("OPEN"))
    _sliced(mp, _ctx(1, 1))
    mp.setattr(crew_autopilot_slices, "expected_base_stop", lambda *a: "its base is wrong")
    return _next(root)


def b_pr_closed(tmp, mp):
    return _next(_done(tmp, mp, pr=_pr("CLOSED")))


def b_tree(tmp, mp):
    root = _done(tmp, mp, pr=_pr("NONE"))
    mp.setattr(crew_ship, "_tree_stop", lambda top: "the working tree differs from HEAD")
    return _next(root)


def b_order(tmp, mp):
    root = _done(tmp, mp, pr=_pr("NONE"))
    _sliced(mp, _ctx(1, 1))
    mp.setattr(crew_autopilot_slices, "order_stop", lambda *a: "slice 0 has not shipped")
    return _next(root)


def b_ship_receipt(tmp, mp):
    root = _done(tmp, mp, pr=_pr("NONE"))
    _receipt_says(mp, False, "receipt is stale")
    return _next(root)


def b_ship_held(tmp, mp):
    root = _done(tmp, mp, pr=_pr("NONE"), index="done")
    _index(root, f"{T} | done | high | r | title", f"{T} | hold | high | r | title")
    return _next(root)


def b_folder_elsewhere(tmp, mp):
    root = _approved(tmp)
    mp.setattr(crew_autopilot, "_main_folder", lambda top, ticket: (None, "git worktree list failed"))
    return _next(root)


def b_brainstorm(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root, direction=False)
    return _next(root)


def b_index_disagreement(tmp, mp):
    root = _approved(tmp)
    mp.setattr(crew_autopilot, "_index_row", lambda top, ticket: {
        "status": "ready", "source": str(root / ".work" / "INDEX.md"), "why": None,
        "paths": [], "other": (("here", "ready"), ("main", "spec"))})
    return _next(root)


def b_direction(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root, status="direction")
    return _next(root)


def b_no_row(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root)
    _index(root, "T-9 | ready | high | r | other")
    return _next(root)


def b_index_closed(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root, status="cancelled")
    return _next(root)


def b_not_approved_direction(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root, status="parked")
    return _next(root)


def b_header_closed_loose(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root)
    spec = root / ".work" / "tickets" / T / "spec.md"
    rest = spec.read_text(encoding="utf-8").split("\n", 1)[1]
    _write(spec, f"# {T} title status: cancelled\n{rest}")
    return _next(root)


def b_open_questions(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root)
    _write(root / ".work" / "tickets" / T / "direction.md", "go\n## Open questions\n- which?\n")
    return _next(root)


def b_spec_invalid(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root)
    _write(root / ".work" / "tickets" / T / "spec.md", f"# {T} title          status: spec\n")
    return _next(root)


def b_plan_invalid(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root)
    _write(root / ".work" / "tickets" / T / "plan.md", "nothing\n")
    return _next(root)


def b_plan_slices(tmp, mp):
    root = _approved(tmp)
    _sliced(mp, _ctx(error="PR slices: slice 2 has no steps"))
    return _next(root)


def b_approve(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root)
    return _next(root)


def b_slices_error(tmp, mp):
    root = _approved(tmp)
    _sliced(mp, _ctx(error="slices.json could not be read"))
    return _next(root)


def b_done_slices_error(tmp, mp):
    root = _done(tmp, mp)
    _sliced(mp, _ctx(error="slices.json could not be read"))
    return _next(root)


def b_done_early_slice(tmp, mp):
    root = _done(tmp, mp)
    _sliced(mp, _ctx(1, 2))
    return _next(root)


def b_auto_replan_cap(tmp, mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "FINDINGS")], state="REVIEWED")
    mp.setattr(crew_autopilot, "auto_replan_policy", lambda top, ticket: {
        "allow": False, "capped": True, "reason": "1 successor plan already", "successors": []})
    return _next(root)


def b_ledger_unknown(tmp, _mp):
    root = _approved(tmp)
    _write(review_ledger.ledger_path(str(root), T), "{not json")
    return _next(root)


def b_needs_replan(tmp, _mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "FINDINGS"), _round(2, "FINDINGS")], state="NEEDS_REPLAN")
    return _next(root)


def b_reserved(tmp, _mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, status="reserved")])
    return _next(root)


def b_findings(tmp, _mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "FINDINGS")], state="REVIEWED")
    return _next(root)


def b_no_round_left(tmp, mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "FINDINGS"), _round(2, "CLEAN")], state="REVIEWED")
    _receipt_says(mp, False, "no accepted review receipt")
    return _next(root)


def b_accepted_unconfirmed(tmp, mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "FINDINGS")], state="ACCEPTED", receipt=_receipt(1, "owner-accepted"))
    _receipt_says(mp, False, "receipt could not be checked: git failed")
    return _next(root)


def b_incomplete(tmp, _mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "INCOMPLETE")], state="REVIEWED")
    return _next(root)


def _toward(tmp, mp, ok=False, **refresh):
    root = _approved(tmp)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_says(mp, ok, "receipt current" if ok else "receipt is stale: edited")
    _refresh(mp, **refresh)
    return _next(root)


def b_refresh_unavailable(tmp, mp):
    return _toward(tmp, mp, state=crew_autopilot.UNAVAILABLE, reason=crew_autopilot.REFRESH_UNAVAILABLE)


def b_refresh_unsettled(tmp, mp):
    return _toward(tmp, mp, state=crew_autopilot.UNSETTLED, reason="refresh check says unknown: x")


def b_stale_after_review(tmp, mp):
    return _toward(tmp, mp, ok=True, state=crew_autopilot.STALE, command="/crew:diagram refresh",
                   reason="refresh check says stale: d (refresh: /crew:diagram refresh)",
                   stop_reason="refresh check says stale: diagram d: stale - moved")


def b_inflight(tmp, mp):
    root = _approved(tmp)
    mp.setattr(__import__("crew_inflight"), "next_stop", lambda root, ticket, runner: {
        "phase": "in-flight", "command": "", "reason": "in-flight: held by another runner"})
    return _next(root, runner="autopilot")


def b_commit_nothing(tmp, mp):
    return _toward(tmp, mp, state=crew_autopilot.UNCOMMITTED, paths=[])


def b_commit_unprintable(tmp, mp):
    return _toward(tmp, mp, state=crew_autopilot.UNCOMMITTED, paths=["a\x07b"])


def b_mismatch(tmp, _mp):
    root = _approved(tmp)
    _ticket(root, ticket="T-2")
    _index(root, f"{T} | spec | high | r | title", "T-2 | spec | high | r | other")
    crew_ticket.activate(str(root), "T-2")
    return _next(root)


def b_max_phases(tmp, _mp):
    return _next(_approved(tmp), phases_run=3, max_phases=3)


def b_no_progress(tmp, _mp):
    return _next(_approved(tmp), last_command=f"/crew:implement {T}")


def _focused(tmp):
    root = _approved(tmp)
    ok, _line = crew_autopilot.focus_set(str(root), T)
    assert ok
    return root


def b_drift_unknown(tmp, _mp):
    root = _focused(tmp)
    _write(crew_autopilot.focus_path(str(root)), "{not json")
    return _next(root)


def b_drift_audit(tmp, mp):
    root = _focused(tmp)

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit on fire")

    mp.setattr(crew_autopilot.completion_audit, "audit", boom)
    return _next(root)


def b_drift_paths(tmp, _mp):
    root = _focused(tmp)
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")
    return _next(root)


def r_folder_elsewhere(tmp, mp):
    root = _approved(tmp)
    mp.setattr(crew_autopilot, "_main_folder", lambda top, ticket: (None, "git worktree list failed"))
    return crew_autopilot.resume_target(str(root), T)


def r_no_folder(tmp, _mp):
    return crew_autopilot.resume_target(str(make_repo(tmp, mode="off")), T)


def r_handoff(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _write(root / ".work" / "HANDOFF.md", "resume: /crew:autopilot --goal faster\n")
    return crew_autopilot.resume_target(str(root))


def _broken_pointer(root, mp):
    real = crew_ticket.resolve_active
    mp.setattr(crew_ticket, "resolve_active", lambda top: (None, "the active-ticket entry is "
                                                                 "unreadable", True))
    return real


def r_broken_first(tmp, mp):
    root = make_repo(tmp, mode="off")
    _broken_pointer(root, mp)
    return crew_autopilot.resume_target(str(root))


def r_several(tmp, _mp):
    root = make_repo(tmp, mode="off")
    _ticket(root)
    _ticket(root, ticket="T-2")
    _index(root, f"{T} | ready | high | r | a", "T-2 | ready | high | r | b")
    return crew_autopilot.resume_target(str(root))


def r_none_open(tmp, _mp):
    return crew_autopilot.resume_target(str(make_repo(tmp, mode="off")))


def r_broken_second(tmp, mp):
    root = _approved(tmp)
    _broken_pointer(root, mp)
    return crew_autopilot.resume_target(str(root), T)


def r_other_active(tmp, _mp):
    root = _approved(tmp)
    _ticket(root, ticket="T-2")
    _index(root, f"{T} | spec | high | r | a", "T-2 | spec | high | r | b")
    crew_ticket.activate(str(root), "T-2")
    return crew_autopilot.resume_target(str(root), T)


def route_goal(tmp, _mp):
    return crew_autopilot.route_args(str(make_repo(tmp, mode="off")), "goal make it faster")


def route_no_word(tmp, _mp):
    return crew_autopilot.route_args(str(make_repo(tmp, mode="off")), "sleep now")


def route_not_ticket(tmp, _mp):
    return crew_autopilot.route_args(str(make_repo(tmp, mode="off")), "run two words")


def route_focus_refusal(tmp, _mp):
    root = _focused(tmp)
    _ticket(root, ticket="T-2")
    _index(root, f"{T} | spec | high | r | a", "T-2 | spec | high | r | b")
    return crew_autopilot.route_args(str(root), "run T-2")


def g_unknown(tmp, _mp):
    root = _approved(tmp)
    _index(root, f"{T} | hold | high | r | a", f"{T} | ready | high | r | a")
    return _next(root)


def g_header_closed(tmp, _mp):
    root = _approved(tmp)
    _write(root / ".work" / "tickets" / T / "spec.md", _spec_text(T, "status: cancelled   risk: high"))
    return _next(root)


def g_hold(tmp, _mp):
    return _next(_approved(tmp, status="hold"))


def _depends(tmp, line, *rows):
    root = make_repo(tmp, mode="off")
    _ticket(root)
    _with_line2(root, line)
    _index(root, f"{T} | ready | high | r | title", *rows)
    approve_as_user(root, T)
    return root


def g_blocked_unreadable(tmp, _mp):
    return _next(_depends(tmp, "depends-on: T-2, not an id"))


def g_blocked_open(tmp, _mp):
    return _next(_depends(tmp, "depends-on: T-2", "T-2 | spec | high | r | other"))


def d_unknown(tmp, mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_says(mp, False, "receipt is stale: edited")
    _docs(mp, crew_autopilot_docs.DOCS_UNKNOWN, "the docs check could not run")
    return _next(root)


def d_missing(tmp, mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_says(mp, False, "receipt is stale: edited")
    _docs(mp, crew_autopilot_docs.DOCS_MISSING, "README.md is MISSING")
    mp.setattr(crew_autopilot_docs, "_docs_attempts", lambda top, ticket: crew_autopilot_docs.DOCS_ATTEMPTS)
    return _next(root)


def d_after_review(tmp, mp):
    root = _approved(tmp)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_says(mp, True, "receipt current")
    _refresh(mp, state=crew_autopilot.FRESH)
    _docs(mp, crew_autopilot_docs.DOCS_MISSING, "README.md is MISSING")
    return _next(root)


def _size(mp, stage, **size):
    real = crew_autopilot_split._size_check  # pylint: disable=protected-access
    got = dict({"fired": [], "unknown": [], "unmeasured": {}, "measures": {}}, **size)
    mp.setattr(crew_autopilot_split, "_size_check",
               lambda top, ticket, at: got if at == stage else real(top, ticket, at))


def s_raises(tmp, mp):
    root = _approved(tmp)

    def boom(*_args):
        raise ValueError("measure on fire")

    mp.setattr(crew_autopilot_split, "_size_check", boom)
    return _next(root)


def s_unknown(tmp, mp):
    root = _approved(tmp)
    _size(mp, "spec", unknown=["lines"])
    return _next(root)


def s_approval(tmp, mp):
    root = _approved(tmp)
    _size(mp, "spec", fired=["lines"])
    mp.setattr(crew_autopilot_split, "_decision_state", lambda top, ticket, fired: ("split", ""))
    return _next(root)


def s_slices_unknown(tmp, mp):
    root = _approved(tmp)
    _size(mp, "plan", fired=["lines"])
    mp.setattr(crew_autopilot_split, "_decision_state", lambda top, ticket, fired: ("slices", ""))
    mp.setattr(crew_autopilot_split, "_slice_problems", lambda top, ticket: None)
    return _next(root)


def s_slices_fail(tmp, mp):
    root = _approved(tmp)
    _size(mp, "plan", fired=["lines"])
    mp.setattr(crew_autopilot_split, "_decision_state", lambda top, ticket, fired: ("slices", ""))
    mp.setattr(crew_autopilot_split, "_slice_problems", lambda top, ticket: ["slice 2 has no steps"])
    return _next(root)


# (site fragment, builder, phase, decision); decision None: a resume or route stop.
CASES = [
    ('answer("closed", True, reason)', b_finished_closed, "closed", "closed"),
    ("a person ships this", b_unarmed_slice, "ship", "look"),
    ("closed by /crew:done. Shipping is", b_unarmed_closed, "closed", "closed"),
    ("cannot tell which branch ships", b_no_branch, "ship", "look"),
    ('answer("ship", True, wrong)', b_branch_stop, "ship", "look"),
    ('answer("ship", True, wrong)', b_base_stop, "ship", "look"),
    ("could not read the PR state for", b_no_pr, "ship", "look"),
    ("open or merged - a person decides", b_pr_closed, "ship", "look"),
    ("a push carries only commits", b_tree, "ship", "look"),
    ('answer("ship", True, order)', b_order, "ship", "look"),
    ("the review receipt no longer stands", b_ship_receipt, "ship", "look"),
    ("answer(held[0], True, held[1])", b_ship_held, "direction-approval", "direction"),
    ('answer("folder-elsewhere"', b_folder_elsewhere, "folder-elsewhere", "look"),
    ('answer("brainstorm", True', b_brainstorm, "brainstorm", "direction"),
    ("index-disagreement: {here} says", b_index_disagreement, "direction-approval", "direction"),
    ("INDEX.md status is `direction`", b_direction, "direction-approval", "direction"),
    ("has no table row for {ticket}", b_no_row, "direction-approval", "direction"),
    ("re-driven, whatever spec.md's header says", b_index_closed, "closed", "closed"),
    ("direction is approved: its .work/INDEX.md status is", b_not_approved_direction,
     "direction-approval", "direction"),
    ("`: nothing left \" \"in this ticket", b_header_closed_loose, "closed", "closed"),
    ("unanswered under ## Open questions", b_open_questions, "open-questions", "answer-question"),
    ("spec.md fails crew_ticket.validate", b_spec_invalid, "spec", "fix-contract"),
    ("plan.md fails crew_ticket.validate", b_plan_invalid, "plan", "fix-contract"),
    ("plan.md's {ctx['error']}", b_plan_slices, "plan", "fix-contract"),
    ('answer("approve", True', b_approve, "approve", "approve-plan"),
    ('answer("slices", True, ctx["error"])', b_slices_error, "slices", "look"),
    ('answer("slices", True, ctx["error"])', b_done_slices_error, "slices", "look"),
    ("is current: closing now would leave", b_done_early_slice, "slices", "look"),
    ('phase="auto-replan-cap"', b_auto_replan_cap, "auto-replan-cap", "replan"),
    ("UNKNOWN (unreadable): the rounds spent", b_ledger_unknown, "review", "look"),
    ("is NEEDS_REPLAN: the review budget", b_needs_replan, "replan", "replan"),
    ("is reserved with no", b_reserved, "review", "spend-round-or-replan"),
    ("is FINDINGS; {how}the owner", b_findings, "accept-review", "accept-review"),
    ("no review round left and no receipt stands", b_no_round_left, "review", "revert-or-replan"),
    ("is FINDINGS and accepted", b_accepted_unconfirmed, "accept-review", "look"),
    ("the reviewer did not", b_incomplete, "accept-review", "spend-round-or-replan"),
    ('answer("refresh", True, refresh["reason"])', b_refresh_unavailable, "refresh", "look"),
    ("before the next review round - {refresh", b_refresh_unsettled, "refresh", "look"),
    ("an artifact is stale after an", b_stale_after_review, "stale-after-review",
     "stale-after-review"),
    ('dict(result, stop=True, decision="look", **stop)', b_inflight, "in-flight", "look"),
    ("names no path to commit", b_commit_nothing, "commit-refresh", "look"),
    ("a path holds a character that is not printable", b_commit_unprintable, "commit-refresh",
     "look"),
    ("ticket mismatch: the scope guard", b_mismatch, "implement", "activate-ticket"),
    ("autopilot.maxPhases ({max_phases}) reached", b_max_phases, "implement", "continue"),
    ("no progress: {last_command}", b_no_progress, "implement", "look"),
    ("whether {ticket} is focused", b_drift_unknown, "drift", "look"),
    ("drift: the audit could not run", b_drift_audit, "drift", "look"),
    ("drift: {shown} - revert them", b_drift_paths, "drift", "look"),
    ("stopped(source, _folder_elsewhere", r_folder_elsewhere, None, None),
    ("has no .work/tickets/ folder", r_no_folder, None, None),
    ("stopped(source, stop_reason)", r_handoff, None, None),
    ("a broken pointer is not guessed \" \"past", r_broken_first, None, None),
    ("several open tickets and no pointer", r_several, None, None),
    ("no open ticket with a .work/tickets/", r_none_open, None, None),
    ("a broken pointer is not guessed past - \"", r_broken_second, None, None),
    ("but this worktree's active ticket", r_other_active, None, None),
    ("reason=GOAL_ROUTE_FIRST", route_goal, None, None),
    ("takes no other word", route_no_word, None, None),
    ("reason=NOT_A_TICKET", route_not_ticket, None, None),
    ("reason=refusal", route_focus_refusal, None, None),
    ("cannot tell whether a gate", g_unknown, "direction-approval", "direction"),
    ("{where}: nothing left in this ticket", g_header_closed, "closed", "closed"),
    ("answer(word, True", g_hold, "hold", "look"),
    ("'s dependencies: ", g_blocked_unreadable, "blocked", "look"),
    ("depends on \" + \"; \".join", g_blocked_open, "blocked", "look"),
    ('answer("docs-unknown"', d_unknown, "docs-unknown", "look"),
    ("documents still MISSING after", d_missing, "docs", "look"),
    ('answer("docs-after-review"', d_after_review, "docs-after-review", "look"),
    ("the size check after {stage} could not", s_raises, "split-check-unknown", "look"),
    ("_unknown_words(stage, size[\"unknown\"])", s_unknown, "split-check-unknown", "look"),
    ('answer("split-approval"', s_approval, "split-approval", "approve-split"),
    ("which arrives with {SLICES_ARRIVE}", s_slices_unknown, "split-check-unknown", "look"),
    ("the plan's ## PR slices fail", s_slices_fail, "plan", "fix-contract"),
]
IDS = [f"{i:02d}-{case[1].__name__}" for i, case in enumerate(CASES)]


def _traced(build, tmp, mp):
    """`build`'s result and the (file, line) pairs it ran in WALKED."""
    ran = set()

    def tracer(frame, event, _arg):
        name = os.path.basename(frame.f_code.co_filename)
        if name not in WALKED:
            return None
        if event == "line":
            ran.add((name, frame.f_lineno))
        return tracer

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        got = build(tmp, mp)
    finally:
        sys.settrace(previous)
    return got, ran


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Every case's result and the lines it ran, built once: {id: (result, ran)}."""
    found = {}
    for case_id, (_key, build, _phase, _decision) in zip(IDS, CASES):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(crew_autopilot_docs, "_docs_state", lambda root, ticket: dict(DOCS_OK))
            found[case_id] = _traced(build, tmp_path_factory.mktemp(case_id), mp)
    return found


@pytest.fixture(scope="module")
def results(built):
    return {case_id: got for case_id, (got, _ran) in built.items()}


def _site_count(key, sites):
    return sum(1 for _name, _line, src in sites if key in src)


@pytest.mark.parametrize("case_id, case", list(zip(IDS, CASES)), ids=IDS)
def test_every_stop_names_an_owner_decision(results, case_id, case):
    got = results[case_id]
    _key, _build, phase, decision = case
    if decision is None:
        assert (got["stop"], "decision" in got) == (True, False), got
        return
    assert (got["stop"], got["phase"], got.get("decision")) == (True, phase, decision), got
    assert decision in crew_autopilot_stops.DECISIONS


@pytest.mark.parametrize("case_id, case", list(zip(IDS, CASES)), ids=IDS)
def test_a_stop_command_is_the_decisions_own_command(results, case_id, case):
    got = results[case_id]
    if case[3] is None:
        return
    assert got["command"] in crew_autopilot_stops.commands(got["decision"], T), got


@pytest.mark.parametrize("case_id", IDS)
def test_no_stop_hands_the_owner_a_mechanical_step(results, case_id):
    got = results[case_id]
    assert crew_autopilot_stops.mechanical(got["reason"]) == [], got["reason"]


def test_every_stop_site_has_a_case():
    sites = stop_sites()
    keys = collections.Counter(key for key, *_rest in CASES)
    uncovered = [f"{name}:{line} {src[:90]}" for name, line, src in sites
                 if not any(key in src for key in keys)]
    wrong = {key: (_site_count(key, sites), count) for key, count in keys.items()
             if _site_count(key, sites) != count}
    assert (len(sites), uncovered, wrong) == (len(CASES), [], {})


def test_each_case_reaches_its_own_site(built):
    """A case counts for a site only when the site's line ran: cases sharing a
    fragment (two identical sites) must reach different ones."""
    sites = stop_sites()
    claimed, missed = collections.Counter(), []
    for case_id, (key, *_rest) in zip(IDS, CASES):
        ran = built[case_id][1]
        hits = [(name, line) for name, line, src in sites if key in src and (name, line) in ran]
        claimed.update(hits[:1])
        if not hits:
            missed.append(case_id)
    assert (missed, [site for site, count in claimed.items() if count > 1]) == ([], [])


def test_the_contract_rejects(tmp_path, monkeypatch):
    """Must-block: the checks can fail. A stop reason handed `run graphify
    update .` is mechanical; a decision outside the list is no decision."""
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "FINDINGS")], state="REVIEWED")
    real = crew_autopilot._review_phase  # pylint: disable=protected-access
    monkeypatch.setattr(crew_autopilot, "_review_phase", lambda *a: dict(
        real(*a), reason="run graphify update . first", decision="refresh-graph"))

    got = _next(root)

    assert (crew_autopilot_stops.mechanical(got["reason"]), got["decision"] in
            crew_autopilot_stops.DECISIONS) == (["graphify update"], False)


def test_findings_stop_names_the_accept_and_the_policy(tmp_path):
    for verdict in ("eligible", "refused"):
        root = _approved(tmp_path / verdict)
        _ledger(root, [_round(1, "FINDINGS")], state="REVIEWED")
        reason = _next(root)["reason"]
        assert ("--accept --by <owner>" in reason, "autopilot.reviewPolicy" in reason,
                "--auto-accept --follow-up" in reason) == (True, True, False), reason


def test_mismatch_stop_names_only_activate(tmp_path, monkeypatch):
    got = b_mismatch(tmp_path, monkeypatch)

    assert (f"crew_ticket.py activate --ticket {T}" in got["reason"],
            "crew_autopilot.py resume" in got["reason"], got["command"]) == (True, False, "")


def test_unsettled_stop_names_no_refresh_command(tmp_path, monkeypatch):
    """The stop lists only what a refresh cannot settle; the non-stop `refresh`
    phase keeps each artifact's command."""
    stale = {"kind": "diagram", "name": "d", "status": "stale", "reason": "moved",
             "command": "/crew:diagram refresh"}
    blind = {"kind": "map", "name": "m", "status": "unknown", "reason": "no anchor", "command": ""}
    monkeypatch.setattr(crew_autopilot, "_settles", lambda a: bool(a.get("command")))

    def check(*artifacts, status="stale"):
        module = type(sys)("crew_refresh_check")
        module.ticket_freshness = lambda root, ticket: {"status": status, "reason": "r",
                                                         "artifacts": list(artifacts)}
        monkeypatch.setitem(sys.modules, "crew_refresh_check", module)
        return crew_autopilot._refresh_state(str(tmp_path), T)  # pylint: disable=protected-access

    unsettled, runs = check(stale, blind, status="unknown"), check(stale)

    assert (unsettled["state"], "(refresh:" in unsettled["reason"], "map m" in unsettled["reason"],
            "diagram d" in unsettled["reason"], runs["state"], "(refresh: /crew:diagram refresh)" in
            runs["reason"]) == ("unsettled", False, True, False, "stale", True)


def test_cli_prints_the_decision(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "FINDINGS")], state="REVIEWED")
    run = [sys.executable, _SCRIPT]
    nxt = subprocess.run(run + ["next", "--root", str(root), "--ticket", T], capture_output=True,
                         text=True, check=False, stdin=subprocess.DEVNULL)
    stops = subprocess.run(run + ["stops", "--json"], capture_output=True, text=True, check=False,
                           stdin=subprocess.DEVNULL)

    assert (nxt.stdout.startswith("phase=accept-review stop=1 command= decision=accept-review "
                                  "reason="),
            [r["id"] for r in json.loads(stops.stdout)["decisions"]]) == (
        True, list(crew_autopilot_stops.DECISIONS)), nxt.stdout


def test_a_running_phase_carries_no_decision(tmp_path):
    got = _next(_approved(tmp_path))

    assert (got["phase"], got["stop"], "decision" in got) == ("implement", False, False)


def test_command_reports_the_decision():
    with open(_COMMAND, encoding="utf-8") as handle:
        text = " ".join(handle.read().split())

    assert ("decision=<d>" in text, "print the phase, the decision, the reason" in text,
            "the decision the owner makes next" in text,
            [shape for shape in crew_autopilot_stops.MECHANICAL
             if f"stop {shape}" in text]) == (True, True, True, [])
