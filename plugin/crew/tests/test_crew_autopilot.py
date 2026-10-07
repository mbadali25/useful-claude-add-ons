"""T-0004: `/crew:autopilot` resumes and drives one ticket.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q

`crew_autopilot.next_phase` names the phase from files on disk; every branch
that cannot tell stops. `resume_target` picks the ticket: the handoff's
`resume:` line (T-0006's `crew_resume.parse_resume`, stood in for here by a
fixture module on sys.path, since T-0006 may not be merged), then the active
ticket, then INDEX.md only when exactly one ticket is open. Every repository
is built under tmp_path; nothing touches the real one or ~/.claude.
`sabotage_autopilot.py` mutates the must-stop branches to prove these tests
can fail.
"""
import hashlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_autopilot_docs
import crew_state
import crew_ticket
import review_ledger
from review_fixtures import git
from scope_fixtures import PLAN, SPEC, approve_as_user, make_repo

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_autopilot.py")
_COMMAND = os.path.join(_ROOT, "commands", "autopilot.md")
T = "T-1"
HEADER = "status: spec   risk: high"


# --- fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def _documents_ok(monkeypatch):
    """T-0022's docs phase reads `crew_docs_check`; these tests are about the
    other phases, so the documents read ok unless a test says otherwise
    (test_crew_autopilot_docs.py owns the docs phase)."""
    monkeypatch.setattr(crew_autopilot_docs, "_docs_state", lambda root, ticket: {
        "state": crew_autopilot_docs.DOCS_OK, "missing": [], "reason": ""})


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _index(root, *rows):
    _write(root / ".work" / "INDEX.md", "".join(f"{row}\n" for row in rows))


def _spec_text(ticket=T, header=HEADER):
    body = SPEC.format(ticket=ticket, touch="- `src/**`")
    first, rest = body.split("\n", 1)
    return f"{first} title          {header}\n{rest}"


def _ticket(root, ticket=T, direction=True, spec=True, plan=True, header=HEADER,
            status="spec"):
    folder = root / ".work" / "tickets" / ticket
    folder.mkdir(parents=True, exist_ok=True)
    if direction:
        _write(folder / "direction.md", "go\n")
    if spec:
        _write(folder / "spec.md", _spec_text(ticket, header))
    if plan:
        _write(folder / "plan.md", PLAN.format(files="src/app.py"))
    _index(root, f"{ticket} | {status} | high | r | title")
    return folder


def _approved(tmp_path, **kwargs):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, **kwargs)
    approve_as_user(root, T)
    return root


def _ledger(root, rounds, state=None, receipt=None, successors=None):
    path = review_ledger.ledger_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"ticket": T, "budget": 2, "rounds": rounds, "refused": [],
            "state": state or ("IN_REVIEW" if rounds else None), "receipt": receipt}
    if successors is not None:
        data["successors"] = successors
    _write(path, json.dumps(data))
    return path


def _round(number=1, verdict="CLEAN", status="completed"):
    row = {"round": number, "status": status, "provider": "claude", "model": None}
    if status == "completed":
        row.update({"verdict": verdict, "bundle_sha256": "a" * 64, "base": "HEAD"})
    return row


def _receipt(number=1, kind="clean"):
    return {"kind": kind, "round": number, "bundle_sha256": "a" * 64, "base": "HEAD",
            "verdict": "CLEAN" if kind == "clean" else "FINDINGS"}


def _receipt_ok(monkeypatch, ok):
    monkeypatch.setattr(review_ledger, "check_receipt",
                        lambda root, ticket: (ok, "receipt current" if ok else "receipt is stale"))


def _refresh(monkeypatch, state, command="/crew:diagram refresh", reason="a diagram moved"):
    monkeypatch.setattr(crew_autopilot, "_refresh_state", lambda root, ticket: {
        "state": state, "command": command if state == "stale" else "", "reason": reason})


def _next(root, **kwargs):
    return crew_autopilot.next_phase(str(root), T, **kwargs)


def _snapshot(root):
    """Every file in the worktree plus crew's state under the git common dir
    (approval receipts, the review ledger, the active-ticket pointer); the
    rest of `.git` is git's own bookkeeping."""
    found = {}
    walks = [str(root), os.path.join(crew_ticket.common_dir(str(root)), "crew")]
    for base, dirs, files in (entry for top in walks for entry in os.walk(top)):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as handle:
                found[path] = handle.read()
    return found


# --- step 1: risk ------------------------------------------------------------

@pytest.mark.parametrize("value", ["low", "med", "high", "LOW", "High"])
def test_risk_low_med_high_parse(value):
    got = crew_ticket.parse_risk(_spec_text(header=f"status: spec   risk: {value}"))
    assert got == {"risk": value.lower(), "known": True}


def test_risk_absent_reads_high():
    assert crew_ticket.parse_risk(_spec_text(header="status: spec")) == {
        "risk": "high", "known": False}


@pytest.mark.parametrize("value", ["lo", "LOW!", "", "low-ish", "medium"])
def test_risk_typo_reads_high(value):
    got = crew_ticket.parse_risk(_spec_text(header=f"status: spec   risk: {value}"))
    assert got == {"risk": "high", "known": False}


def test_risk_only_from_first_line():
    text = _spec_text(header="status: spec") + "\nrisk: low\n# Another heading risk: low\n"
    assert crew_ticket.parse_risk(text) == {"risk": "high", "known": False}


# --- step 2: next, one test per transition -----------------------------------

def test_next_brainstorm(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, direction=False)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("brainstorm", True, "/crew:brainstorm")


def test_next_direction_approval(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, spec=False, plan=False, status="direction")

    assert (_next(root)["phase"], _next(root)["stop"]) == ("direction-approval", True)


def test_next_spec(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, spec=False, plan=False, status="ready")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("spec", False, f"/crew:spec {T}")


def test_next_spec_that_fails_validate_stops(tmp_path):
    root = make_repo(tmp_path, mode="off")
    folder = _ticket(root)
    _write(folder / "spec.md", f"# {T} title   {HEADER}\n## Intent\nx\n")

    got = _next(root)

    assert (got["phase"], got["stop"], "## Touch" in got["reason"]) == ("spec", True, True)


def test_next_plan(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, plan=False)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("plan", False, f"/crew:plan {T}")


def test_next_plan_that_fails_validate_stops(tmp_path):
    root = make_repo(tmp_path, mode="off")
    folder = _ticket(root)
    _write(folder / "plan.md", PLAN.format(files="elsewhere/x.py"))

    got = _next(root)

    assert (got["phase"], got["stop"], "outside spec ## Touch" in got["reason"]) == (
        "plan", True, True)


def test_next_approve(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("approve", True, f"/crew:approve {T}")


def _cli_approved(root):
    crew_ticket.approve(str(root), T, by="someone")


def _stale_approval(root):
    approve_as_user(root, T)
    _write(root / ".work" / "tickets" / T / "plan.md",
           PLAN.format(files="src/app.py") + "\nedited after approval\n")


@pytest.mark.parametrize("arrange", [lambda root: None, _cli_approved, _stale_approval],
                         ids=["none", "cli-unaccepted", "stale"])
def test_next_never_returns_approve_without_stop(tmp_path, arrange):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)
    arrange(root)

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("approve", True)


def test_next_unknown_ledger_stops(tmp_path):
    root = _approved(tmp_path)
    _write(review_ledger.ledger_path(str(root), T), "{not json")

    got = _next(root)

    assert (got["phase"], got["stop"], "UNKNOWN" in got["reason"]) == ("review", True, True)


def test_next_replan(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "FINDINGS"), _round(2, "FINDINGS")], state="NEEDS_REPLAN")

    got = _next(root)

    assert (got["phase"], got["stop"], "NEEDS_REPLAN" in got["reason"]) == ("replan", True, True)


def test_next_implement(tmp_path):
    root = _approved(tmp_path)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == (
        "implement", False, f"/crew:implement {T}")


def test_next_implements_again_after_a_successor_plan(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "FINDINGS"), _round(2, "FINDINGS")], state="IN_REVIEW",
            successors=[{"plan_sha256": "b" * 64, "after_round": 2}])

    assert _next(root)["phase"] == "implement"


def test_next_reserved_round_stops(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, status="reserved")])

    got = _next(root)

    assert (got["phase"], got["stop"], "reserved" in got["reason"]) == ("review", True, True)


def test_next_accept_review(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "FINDINGS")], state="REVIEWED")

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("accept-review", True)


def test_next_owner_accepted_findings_move_on(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "FINDINGS")], state="ACCEPTED",
            receipt=_receipt(1, "owner-accepted"))
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")

    assert _next(root)["phase"] == "done"


LINE = "FIX|src/app.py:1|the loop never stops|run it offline"


def _auto_row(number=2, block=0, provider="codex", family="gpt"):
    row = _round(number, "FINDINGS")
    row.update({"counts": {"BLOCK": block, "FIX": 1, "NIT": 0}, "findings": [LINE],
                "webtest_open": review_ledger.WEBTEST_NA, "refunded": False,
                "provider": provider, "model_family": family,
                # L-0576's count, as its `record` writes it (owner decision #6).
                "ignored_lines": 0})
    return row


def _auto_receipt(number=2):
    return dict(_receipt(number, review_ledger.AUTO_KIND), accepted_by=review_ledger.AUTO_BY,
                findings=[LINE], follow_up="L-9999", provider="codex", model_family="gpt")


def _bound_auto_receipt(root, number=2):
    """An auto receipt bound to a review.json for its round, as auto_accept
    writes both (review round 6 BLOCK 1)."""
    raw = json.dumps({"round": number, "bundle_sha256": "a" * 64,
                      "ignored_lines": 0}).encode("utf-8")
    path = os.path.join(str(root), ".work", "tickets", T, "review.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)
    return dict(_auto_receipt(number), review_json_sha256=hashlib.sha256(raw).hexdigest(),
                ignored_lines=0)


def test_next_auto_accepted_findings_move_on(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_auto_row(1), _auto_row(2)], state="ACCEPTED",
            receipt=_bound_auto_receipt(root))
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")

    assert _next(root)["phase"] == "done"


def test_next_auto_receipt_with_an_edited_review_json_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    receipt = _bound_auto_receipt(root)
    _write(os.path.join(str(root), ".work", "tickets", T, "review.json"),
           json.dumps({"round": 2, "bundle_sha256": "a" * 64, "ignored_lines": 3}))
    _ledger(root, [_auto_row(1), _auto_row(2)], state="ACCEPTED", receipt=receipt)
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("accept-review", True)


def test_next_auto_receipt_on_a_block_row_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_auto_row(1), _auto_row(2, block=1)], state="ACCEPTED",
            receipt=_auto_receipt())
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("accept-review", True)


def test_next_eligible_round_without_receipt_names_auto_accept(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_auto_row(1), _auto_row(2)], state="REVIEWED")

    got = _next(root)

    assert (got["phase"], got["stop"], "review_ledger.py --auto-accept" in got["reason"]) == (
        "accept-review", True, True), got["reason"]


def test_next_ineligible_findings_quote_the_refusal(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_auto_row(1), _auto_row(2, block=1)], state="REVIEWED")

    got = _next(root)

    assert (got["phase"], got["stop"], "a BLOCK is never auto-accepted" in got["reason"],
            "--accept --by <owner>" in got["reason"]) == ("accept-review", True, True, True), \
        got["reason"]


def test_next_same_family_round_quotes_the_family_refusal(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_auto_row(1), _auto_row(2, provider="claude", family="claude")],
            state="REVIEWED")

    got = _next(root)

    assert (got["phase"], got["stop"], "same family" in got["reason"],
            "--auto-accept refuses it" in got["reason"]) == (
        "accept-review", True, True, True), got["reason"]


def test_next_refresh_before_rereview(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "stale", command="graphify update .")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("refresh", False, "graphify update .")


def test_next_review(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "fresh")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("review", False, f"/crew:review {T}")


def test_next_stale_after_review_stops_without_writing(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "stale")
    before = _snapshot(root)

    got = _next(root)

    assert ((got["phase"], got["stop"], got["command"]), _snapshot(root) == before) == (
        ("stale-after-review", True, ""), True)


def test_next_done(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("done", False, f"/crew:done {T}")


def test_next_closed(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _write(root / ".work" / "tickets" / T / "spec.md",
           _spec_text(header="status: done   risk: high"))
    _receipt_ok(monkeypatch, False)

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("closed", True)


@pytest.mark.parametrize("refresh", ["fresh", "stale"])
@pytest.mark.parametrize("second,state,receipt", [
    ("CLEAN", "ACCEPTED", _receipt(2)), ("INCOMPLETE", "REVIEWED", None)],
    ids=["round-2-clean-gone-stale", "round-2-incomplete"])
def test_next_budget_spent_without_a_receipt_stops(tmp_path, monkeypatch, refresh, second,
                                                   state, receipt):
    """Round 2 CLEAN whose receipt went stale, or round 2 INCOMPLETE (round
    1's repro): a /crew:review now would reserve a third round and write
    NEEDS_REPLAN, unattended."""
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "FINDINGS"), _round(2, second)], state=state, receipt=receipt)
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, refresh)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"], "no review round left" in got["reason"]) == (
        "review", True, "", True)


def test_next_incomplete_round_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "INCOMPLETE")], state="REVIEWED")
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "fresh")

    got = _next(root)

    assert (got["phase"], got["stop"], "INCOMPLETE" in got["reason"]) == (
        "accept-review", True, True)


def _header_only_edit(root):
    _write(root / ".work" / "tickets" / T / "spec.md",
           _spec_text(header="status: review   risk: high"))


def _touch_edit(root):
    folder = root / ".work" / "tickets" / T
    text = _spec_text(header="status: review   risk: high").replace("- `src/**`",
                                                                    "- `src/**`\n- `other/**`")
    _write(folder / "spec.md", text)


def _legacy_receipt(root):
    """Rewrite the approval receipt the way crew wrote it before T-0026: no
    `digest`, so it is compared on the raw sha256 of each file."""
    path = crew_ticket.approval_path(str(root), T)
    with open(path, encoding="utf-8") as handle:
        receipt = json.load(handle)
    for key in ("digest", "spec_digest", "plan_digest"):
        receipt.pop(key, None)
    _write(path, json.dumps(receipt))


def test_next_header_status_edit_keeps_the_approval(tmp_path, monkeypatch):
    """T-0026 (main): /crew:implement step 7's `status: review` no longer
    stales the approval, so autopilot does not stop at `approve` after it."""
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")
    _header_only_edit(root)

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("done", False)


def test_next_legacy_receipt_header_edit_names_the_header_edit(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _legacy_receipt(root)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _refresh(monkeypatch, "fresh")
    _header_only_edit(root)

    got = _next(root)

    assert (got["phase"], got["stop"], "only the header's status" in got["reason"],
            "T-0026" in got["reason"]) == ("approve", True, True, True)


def test_next_approval_stale_beyond_the_header_keeps_the_plain_reason(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _touch_edit(root)

    got = _next(root)

    assert (got["phase"], got["stop"], "T-0026" in got["reason"]) == ("approve", True, False)


@pytest.mark.parametrize("index", [None, "T-9 | spec | low | r | another ticket"],
                         ids=["no-index", "no-row"])
def test_next_direction_approval_unknown_stops(tmp_path, index):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, spec=False, plan=False)
    if index is None:
        (root / ".work" / "INDEX.md").unlink()
    else:
        _index(root, index)

    got = _next(root)

    assert (got["phase"], got["stop"], "has no table row" in got["reason"]) == (
        "direction-approval", True, True)


@pytest.mark.parametrize("name", ["direction.md", "spec.md", "plan.md"])
def test_next_open_questions_stop(tmp_path, name):
    root = _approved(tmp_path)
    path = root / ".work" / "tickets" / T / name
    _write(path, path.read_text(encoding="utf-8") + "\n## Open questions\n- which DB?\n")

    got = _next(root)

    assert (got["phase"], got["stop"], "which DB?" in got["reason"], name in got["reason"]) == (
        "open-questions", True, True, True)


@pytest.mark.parametrize("body", ["none", "- none - decided by the owner", "- [x] which DB? postgres",
                                  "- ~~which DB?~~ postgres", "None.", "", "N/A",
                                  "- none (the owner chose postgres)"])
def test_next_answered_open_questions_do_not_stop(tmp_path, body):
    root = _approved(tmp_path)
    path = root / ".work" / "tickets" / T / "direction.md"
    _write(path, f"go\n## Open questions\n{body}\n")

    assert _next(root)["phase"] == "implement"


@pytest.mark.parametrize("text", [
    "go\n## Open questions\n- None of the owners has picked a DB yet\n",
    "go\n## Open questions\n- nonetheless, which DB?\n",
    "go\n## Open questions\n### For the owner\n- which DB?\n",
    "go\n### Open questions\n- which DB?\n",
], ids=["starts-with-none", "starts-with-none-word", "under-a-subheading", "level-3-heading"])
def test_next_open_question_that_only_looks_answered_stops(tmp_path, text):
    root = _approved(tmp_path)
    _write(root / ".work" / "tickets" / T / "direction.md", text)

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("open-questions", True)


def test_next_open_questions_section_ends_at_the_next_peer_heading(tmp_path):
    root = _approved(tmp_path)
    _write(root / ".work" / "tickets" / T / "direction.md",
           "go\n## Open questions\n- none\n## Recommendation\n- use postgres\n")

    assert _next(root)["phase"] == "implement"


@pytest.mark.parametrize("status", ["", "brainstorm", "parked", "rejected", "**ready**"])
def test_next_index_status_that_does_not_say_approved_stops(tmp_path, status):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, spec=False, plan=False, status=status)

    got = _next(root)

    assert (got["phase"], got["stop"], "cannot tell" in got["reason"]) == (
        "direction-approval", True, True)


@pytest.mark.parametrize("status", ["ready", "open", "spec", "planned", "approved",
                                    "in-progress", "review", "Ready"])
def test_next_index_status_after_direction_approval_proceeds(tmp_path, status):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, spec=False, plan=False, status=status)

    assert (_next(root)["phase"], _next(root)["stop"]) == ("spec", False)


@pytest.mark.parametrize("status", ["done", "merged", "closed", "shipped", "complete"])
def test_next_index_status_done_stops_as_closed(tmp_path, status):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, spec=False, plan=False, status=status)

    got = _next(root)

    assert (got["phase"], got["stop"], "INDEX.md" in got["reason"]) == ("closed", True, True)


def test_next_stops_when_another_ticket_is_active(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, "T-1")

    got = crew_autopilot.next_phase(str(root), "T-1")

    assert (got["phase"], got["stop"], "T-2" in got["reason"]) == ("implement", True, True)


def test_next_stops_when_the_scope_guard_would_judge_another_ticket(tmp_path):
    """No pointer: the scope guard falls back to INDEX.md's first open
    ticket (crew_ticket.resolve_active), which is T-1, not T-2."""
    root = _two_tickets(tmp_path)
    approve_as_user(root, "T-2")

    got = crew_autopilot.next_phase(str(root), "T-2")

    assert (got["phase"], got["stop"], "T-1" in got["reason"]) == ("implement", True, True)


def test_next_proceeds_when_its_ticket_is_the_active_one(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, "T-2")

    got = crew_autopilot.next_phase(str(root), "T-2")

    assert (got["phase"], got["stop"]) == ("implement", False)


@pytest.mark.parametrize("action", ["next", "resume"])
def test_cli_that_raises_prints_a_stop(tmp_path, monkeypatch, capsys, action):
    """A crash is `could not tell`: it prints `stop=1`, never nothing."""
    root = make_repo(tmp_path, mode="off")
    _ticket(root)

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(crew_autopilot, "_phase", boom)
    code = crew_autopilot.main([action, "--root", str(root), "--ticket", T])

    out = capsys.readouterr().out
    assert (code, "stop=1" in out, "disk on fire" in out) == (0, True, True)


class _UnprintableError(RuntimeError):
    """An exception whose `__str__` raises (T-0072 review round 4's neighbour)."""

    def __str__(self):
        raise ValueError("no str")


def _raise_unprintable(*_args, **_kwargs):
    raise _UnprintableError()


def test_next_crash_that_cannot_be_described_still_stops(tmp_path, monkeypatch, capsys):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)
    monkeypatch.setattr(crew_autopilot, "next_phase", _raise_unprintable)

    code = crew_autopilot.main(["next", "--root", str(root), "--ticket", T])

    assert (code, "stop=1" in capsys.readouterr().out) == (0, True)


def test_resume_crash_that_cannot_be_described_still_stops(tmp_path, monkeypatch, capsys):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)
    monkeypatch.setattr(crew_autopilot, "resume_target", _raise_unprintable)

    code = crew_autopilot.main(["resume", "--root", str(root), "--ticket", T])

    assert (code, "stop=1" in capsys.readouterr().out) == (0, True)


def test_status_crash_that_cannot_be_described_still_prints_unknown(tmp_path, monkeypatch,
                                                                    capsys):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)
    monkeypatch.setattr(crew_autopilot, "status", _raise_unprintable)

    code = crew_autopilot.main(["status", "--root", str(root), "--ticket", T])

    assert (code, capsys.readouterr().out.startswith("status: unknown")) == (0, True)


def test_next_ticket_error_that_cannot_be_described_still_stops(tmp_path, monkeypatch,
                                                                capsys):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)

    class _UnprintableTicketError(crew_autopilot.crew_ticket.TicketError):
        def __str__(self):
            raise ValueError("no str")

    def boom(*_args, **_kwargs):
        raise _UnprintableTicketError()

    monkeypatch.setattr(crew_autopilot, "next_phase", boom)

    code = crew_autopilot.main(["next", "--root", str(root), "--ticket", T])

    assert (code, "stop=1" in capsys.readouterr().out) == (0, True)


def test_cli_next_prints_one_line_and_exits_zero(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)

    done = subprocess.run([sys.executable, _SCRIPT, "next", "--root", str(root), "--ticket", T],
                          capture_output=True, text=True, check=False, timeout=60,
                          stdin=subprocess.DEVNULL)

    assert (done.returncode, done.stdout.startswith("phase=approve stop=1 command=/crew:approve "),
            done.stdout.count("\n")) == (0, True, 1)


# --- step 3: refresh ---------------------------------------------------------

def test_refresh_unavailable_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, False)
    monkeypatch.setitem(sys.modules, "crew_refresh_check", None)

    got = _next(root)

    assert (got["phase"], got["stop"], got["reason"]) == (
        "refresh", True, crew_autopilot.REFRESH_UNAVAILABLE)


_ORPHAN = ("anchor 0123abcd names no commit in this repository (a squash-merged or "
           "rebased branch?); a refresh re-anchors it")


def _freshness(monkeypatch, status, *artifacts, reason="scope base abc (recorded)"):
    import crew_refresh_check  # pylint: disable=import-outside-toplevel
    rows = [dict(zip(("kind", "name", "status", "reason", "command", "refreshable"), a))
            for a in artifacts]
    for row in rows:
        if row["refreshable"] is None:
            del row["refreshable"]
    monkeypatch.setattr(crew_refresh_check, "ticket_freshness", lambda root, ticket: {
        "status": status, "reason": reason, "artifacts": rows})


def _state():
    return crew_autopilot._refresh_state("/nowhere", T)  # pylint: disable=protected-access


def test_refresh_unknown_orphaned_anchor_refreshes(monkeypatch):
    _freshness(monkeypatch, "unknown",
               ("codemap", "crew", "unknown", _ORPHAN, "/crew:onboard --refresh crew", True))

    assert (_state()["state"], _state()["command"]) == ("stale", "/crew:onboard --refresh crew")


@pytest.mark.parametrize("artifact", [
    ("graph", "graphify-out", "unknown", "graphify missing on this machine", "graphify update .",
     False),
    ("codemap", "crew", "unknown", "no `anchor:` line, so nothing about it can be checked",
     "/crew:onboard --refresh crew", True),
    ("codemap", "crew", "unknown", _ORPHAN, "/crew:onboard --refresh crew", None),
    ("codemap", "crew", "unknown", _ORPHAN + " [fallback base]", "/crew:onboard --refresh crew",
     True),
    ("codemap", "crew", "unknown", _ORPHAN, "", True),
], ids=["tool-missing", "refreshable-but-not-orphaned", "no-refreshable-key", "fallback-base",
        "no-command"])
def test_refresh_unknown_other_cause_stops(tmp_path, monkeypatch, artifact):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, False)
    _freshness(monkeypatch, "unknown", artifact)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("refresh", True, "")


def test_refresh_unknown_with_no_artifact_stops(monkeypatch):
    _freshness(monkeypatch, "unknown", reason="no scope base for T-1 (none recorded)")

    assert _state()["state"] == "unsettled"


def test_refresh_one_unsettled_artifact_stops_the_rest(monkeypatch):
    _freshness(monkeypatch, "unknown",
               ("diagram", "flow", "stale", "src/a.py changed", "/crew:diagram refresh", True),
               ("graph", "graphify-out", "unknown", "graphify missing", "graphify update .",
                False))

    assert _state()["state"] == "unsettled"


def test_refresh_overall_unknown_over_stale_artifacts_stops(monkeypatch):
    """T-0008 says `unknown` for the whole answer (a fallback scope base) while
    every artifact line reads merely stale: the unknown is the answer's, and no
    artifact's command settles it."""
    _freshness(monkeypatch, "unknown",
               ("diagram", "flow", "stale", "src/a.py changed", "/crew:diagram refresh", True),
               reason="scope base abc is not T-1's recorded start (merge-base)")

    assert _state()["state"] == "unsettled"


def test_refresh_check_that_raises_stops(tmp_path, monkeypatch):
    import crew_refresh_check  # pylint: disable=import-outside-toplevel

    def boom(root, ticket):
        raise RuntimeError("git exploded")
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    monkeypatch.setattr(crew_refresh_check, "ticket_freshness", boom)

    got = _next(root)

    assert (got["phase"], got["stop"], "git exploded" in got["reason"]) == (
        "stale-after-review", True, True)


def test_refresh_fresh_goes_to_review(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "fresh")

    assert _next(root)["phase"] == "review"


def test_refresh_stale_with_no_command_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, False)
    monkeypatch.setattr(crew_autopilot, "_refresh_state", lambda root, ticket: {
        "state": "stale", "command": "", "reason": "no scope base"})

    got = _next(root)

    assert (got["phase"], got["stop"]) == ("refresh", True)


def test_refresh_state_reads_the_real_t0008_check(tmp_path):
    root = _approved(tmp_path)
    subprocess.run([sys.executable, os.path.join(_ROOT, "hooks", "scripts", "scope_base.py"),
                    "--root", str(root), "--record", T], check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)

    got = crew_autopilot._refresh_state(str(root), T)  # pylint: disable=protected-access

    assert got["state"] == "fresh"


# --- step 4: resume ----------------------------------------------------------

_STUB_RESUME = r'''
"""Stand-in for T-0006's crew_resume: parse_resume and render with the
signatures and return shapes of its module at df17b667 (not yet merged)."""
import re

RESUME_COMMANDS = (("/crew:spec", "ticket"), ("/crew:plan", "ticket"),
                   ("/crew:implement", "ticket"), ("/crew:review", "ticket"),
                   ("/crew:done", "ticket"), ("/crew:autopilot", "ticket|goal|none"),
                   ("/crew:status", "none"))
EXCLUDED = ("/crew:approve", "/crew:brainstorm", "/crew:fix", "/crew:emergency",
            "/crew:gate", "/crew:promote", "/crew:migrate", "/crew:change")
_TICKET = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _refuse(reason):
    return {"ok": False, "command": "", "arg": "", "kind": "", "reason": reason}


def _ok(command, arg, kind):
    return {"ok": True, "command": command, "arg": arg, "kind": kind, "reason": ""}


def parse_resume(text):
    lines = re.findall(r"^resume:[ \t]*(.*?)[ \t]*$", text or "", re.MULTILINE)
    if len(lines) != 1:
        return _refuse("no resume line" if not lines else f"{len(lines)} resume lines")
    tokens = lines[0].split()
    if not tokens or tokens == ["none"]:
        return _refuse("resume: none" if tokens else "empty resume line")
    command, rest = tokens[0], tokens[1:]
    if command in EXCLUDED:
        return _refuse(f"{command} is excluded from auto-resume")
    kinds = dict(RESUME_COMMANDS).get(command, "").split("|")
    if kinds == [""]:
        return _refuse("not an allowlisted /crew: command")
    if not rest:
        return _ok(command, "", "none") if "none" in kinds else _refuse("needs a ticket id")
    if rest[0] == "--goal":
        if "goal" in kinds and len(rest) == 2 and _SLUG.match(rest[1]):
            return _ok(command, rest[1], "goal")
        return _refuse("bad --goal")
    if "ticket" in kinds and len(rest) == 1 and _TICKET.match(rest[0]):
        return _ok(command, rest[0], "ticket")
    return _refuse("extra text after the command")


def render(parsed):
    if not parsed.get("ok"):
        return ""
    if parsed["kind"] == "goal":
        return f"{parsed['command']} --goal {parsed['arg']}"
    if parsed["kind"] == "ticket":
        return f"{parsed['command']} {parsed['arg']}"
    return parsed["command"]
'''


@pytest.fixture
def stub_resume(tmp_path, monkeypatch):
    where = tmp_path / "stub"
    _write(where / "crew_resume.py", textwrap.dedent(_STUB_RESUME))
    monkeypatch.syspath_prepend(str(where))
    monkeypatch.delitem(sys.modules, "crew_resume", raising=False)
    return where


def _handoff(root, line, branch=None, head=None):
    branch = branch or git(root, "rev-parse", "--abbrev-ref", "HEAD")
    head = head or git(root, "rev-parse", "--short=10", "HEAD")
    _write(root / ".work" / "HANDOFF.md",
           f"# Handoff\nwritten: 2026-09-25T00:00:00Z\nbranch: {branch}\nhead: {head}\n"
           f"{line}\n\n## Next action\nwork on T-2 next\n")


def _two_tickets(tmp_path, activate=None):
    root = make_repo(tmp_path, mode="off")
    for ticket in ("T-1", "T-2"):
        _ticket(root, ticket=ticket)
    _index(root, "T-1 | spec | high | r | one", "T-2 | spec | high | r | two",
           "T-3 | done | low | r | closed")
    if activate:
        crew_ticket.activate(str(root), activate)
    return root


@pytest.mark.parametrize("pointer,activate", [(None, True), ("T-1", False)],
                         ids=["no-pointer", "pointer-agrees"])
def test_resume_from_handoff_line(tmp_path, stub_resume, pointer, activate):  # pylint: disable=unused-argument
    root = _two_tickets(tmp_path, activate=pointer)
    _handoff(root, "resume: /crew:autopilot T-1")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], got["stop"], got["disagreement"], got["activate"]) == (
        "T-1", "handoff", False, "", activate)


def test_resume_handoff_disagreeing_with_the_active_pointer_stops(tmp_path, stub_resume):  # pylint: disable=unused-argument
    root = _two_tickets(tmp_path, activate="T-2")
    _handoff(root, "resume: /crew:autopilot T-1")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["stop"], "T-1" in got["reason"], "T-2" in got["reason"]) == (
        None, True, True, True)


def test_resume_argument_disagreeing_with_the_active_pointer_stops(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")

    got = crew_autopilot.resume_target(str(root), ticket="T-1")

    assert (got["ticket"], got["stop"], got["source"]) == (None, True, "argument")


def test_resume_argument_with_no_pointer_is_activated(tmp_path):
    root = _two_tickets(tmp_path)

    got = crew_autopilot.resume_target(str(root), ticket="T-1")

    assert (got["ticket"], got["stop"], got["activate"]) == ("T-1", False, True)


def test_resume_handoff_ticket_without_a_folder_falls_through(tmp_path, stub_resume):  # pylint: disable=unused-argument
    root = _two_tickets(tmp_path, activate="T-2")
    _handoff(root, "resume: /crew:autopilot T-9")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], "T-9" in got["fallthrough"][0]) == (
        "T-2", "active-ticket", True)


def test_resume_handoff_head_mismatch_falls_through(tmp_path, stub_resume):  # pylint: disable=unused-argument
    root = _two_tickets(tmp_path, activate="T-2")
    _handoff(root, "resume: /crew:autopilot T-1", head="0123456789")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], "head:" in got["fallthrough"][0]) == (
        "T-2", "active-ticket", True)


def test_resume_handoff_branch_mismatch_falls_through(tmp_path, stub_resume):  # pylint: disable=unused-argument
    root = _two_tickets(tmp_path, activate="T-2")
    _handoff(root, "resume: /crew:autopilot T-1", branch="some-other-branch")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], "branch:" in got["fallthrough"][0]) == ("T-2", True)


@pytest.mark.parametrize("line", ["resume: none", "", "resume: /crew:implement T-1; rm -rf x",
                                  "resume: /crew:status", "resume: /crew:approve T-1"])
def test_resume_handoff_none_falls_through(tmp_path, stub_resume, line):  # pylint: disable=unused-argument
    root = _two_tickets(tmp_path, activate="T-2")
    _handoff(root, line)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"]) == ("T-2", "active-ticket")


def test_resume_goal_line_stops_until_t0012(tmp_path, stub_resume):  # pylint: disable=unused-argument
    root = _two_tickets(tmp_path, activate="T-2")
    _handoff(root, "resume: /crew:autopilot --goal ship-it")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["stop"], "L-0541" in got["reason"]) == (None, True, True)


def test_resume_active_ticket(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"], got["activate"]) == ("T-2", "active-ticket", False)


def test_resume_broken_pointer_stops(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")
    (root / ".work" / "tickets" / "T-2" / "direction.md").unlink()
    for name in ("spec.md", "plan.md"):
        (root / ".work" / "tickets" / "T-2" / name).unlink()
    (root / ".work" / "tickets" / "T-2").rmdir()

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["stop"]) == (None, True)


def test_resume_single_open_index_ticket(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, ticket="T-1")
    _index(root, "T-1 | spec | high | r | one", "T-3 | done | low | r | closed",
           "T-4 | spec | low | r | no folder")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["source"]) == ("T-1", ".work/INDEX.md")


def test_resume_several_open_tickets_stops(tmp_path):
    root = _two_tickets(tmp_path)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["stop"], "T-1, T-2" in got["reason"]) == (None, True, True)


def test_resume_no_open_ticket_stops(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _index(root, "T-3 | done | low | r | closed")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["stop"]) == (None, True)


def test_resume_disk_beats_handoff_hint(tmp_path, stub_resume):  # pylint: disable=unused-argument
    root = _two_tickets(tmp_path)
    _handoff(root, "resume: /crew:implement T-1")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["next"]["phase"], got["disagreement"]) == (
        "T-1", "approve", "the handoff says /crew:implement T-1, the disk says "
        "/crew:approve T-1; disk wins")


def test_resume_without_crew_resume_module_falls_through(tmp_path, monkeypatch):
    root = _two_tickets(tmp_path, activate="T-2")
    _handoff(root, "resume: /crew:autopilot T-1")
    monkeypatch.setitem(sys.modules, "crew_resume", None)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], "T-0006" in got["fallthrough"][0]) == ("T-2", True)


def test_real_crew_resume_reads_the_line_autopilot_writes():
    """Holds the stand-in above to T-0006's real module once it lands."""
    try:
        import crew_resume  # pylint: disable=import-outside-toplevel
    except ImportError:
        pytest.skip("crew_resume (T-0006) is not in this tree - the real parser was NOT run")
    got = crew_resume.parse_resume("resume: /crew:autopilot T-0004\n")
    assert (got["ok"], got["command"], got["arg"], got["kind"], crew_resume.render(got),
            "/crew:autopilot" in dict(crew_resume.RESUME_COMMANDS)) == (
        True, "/crew:autopilot", "T-0004", "ticket", "/crew:autopilot T-0004", True)


# --- step 5: config and stops ------------------------------------------------

def _config(root, block):
    path = root / ".crew" / "config.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["autopilot"] = block
    _write(path, json.dumps(data))


def test_mode_off_by_default(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.settings(str(root))

    assert (got["mode"], got["armed"], got["maxPhases"], got["warnings"]) == ("off", False, 12, [])


def test_mode_plan_arms(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _config(root, {"mode": "plan", "maxPhases": 5})

    got = crew_autopilot.settings(str(root))

    assert (got["mode"], got["armed"], got["maxPhases"]) == ("plan", True, 5)


def test_mode_null_is_silent_and_reads_the_default(tmp_path):
    """T-0050: `null` is a silent layer for a personal key (the global value,
    else the default), so a repo `mode: null` is `off` with nothing to warn
    about -- it is not a typo, it is "not set here"."""
    root = make_repo(tmp_path, mode="off")
    _config(root, {"mode": None})

    got = crew_autopilot.settings(str(root))

    assert (got["armed"], got["mode"], got["warnings"]) == (False, "off", [])


@pytest.mark.parametrize("value", ["Plan", "plan ", "PLAN", "on", True, "autonomous"])
def test_mode_typo_is_off(tmp_path, value):
    root = make_repo(tmp_path, mode="off")
    _config(root, {"mode": value})

    got = crew_autopilot.settings(str(root))

    assert (got["armed"], got["mode"], repr(value) in got["warnings"][0]) == (False, "off", True)


@pytest.mark.parametrize("value", [0, -3, "12", True, 2.5])
def test_max_phases_not_a_positive_int_reads_default(tmp_path, value):
    root = make_repo(tmp_path, mode="off")
    _config(root, {"mode": "plan", "maxPhases": value})

    got = crew_autopilot.settings(str(root))

    assert (got["maxPhases"], len(got["warnings"])) == (12, 1)


def test_autopilot_only_in_crew_json_is_reported(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _write(root / ".crew" / "crew.json", json.dumps({"autopilot": {"mode": "plan"}}))

    got = crew_autopilot.settings(str(root))

    assert (got["armed"], any(".crew/crew.json" in w for w in got["warnings"])) == (False, True)


def test_max_phases_stop(tmp_path):
    root = _approved(tmp_path)

    got = _next(root, phases_run=3, max_phases=3)

    assert (got["phase"], got["stop"], "maxPhases (3)" in got["reason"]) == (
        "implement", True, True)


def test_same_command_twice_stops_for_no_progress(tmp_path):
    root = _approved(tmp_path)

    got = _next(root, phases_run=1, last_command=f"/crew:implement {T}", max_phases=12)

    assert (got["stop"], got["reason"].startswith("no progress")) == (True, True)


def test_stops_lists_every_autonomous_stop():
    got = crew_autopilot.stops()

    assert [row["id"] for row in got["autonomous"]] == [
        slug for slug, _text in crew_state.AUTONOMOUS_STOPS]


def test_autopilot_defaults_are_the_config_block():
    import crew_config  # pylint: disable=import-outside-toplevel
    assert crew_config.default_config()["autopilot"] == {
        "mode": "off", "maxPhases": 12, "deploy": "none", "approval": "risk",
        "questions": "risk", "maxAutoReplans": 0,
        "sleep": {"schedule": None, "approval": None, "questions": None},
        "ship": "merge", "knownFailures": [], "ciTimeoutMinutes": 60}


# --- step 6: the command -----------------------------------------------------

def _command_text():
    with open(_COMMAND, encoding="utf-8") as handle:
        return handle.read()


def test_command_names_every_autonomous_stop():
    text = _command_text()
    missing = [slug for slug, _text in crew_state.AUTONOMOUS_STOPS if f"`{slug}`" not in text]
    assert missing == []


def test_command_names_every_fixed_and_human_stop():
    text = _command_text()
    slugs = [slug for slug, _text in (crew_autopilot.FIXED_STOPS + crew_autopilot.HUMAN_STOPS
                                      + crew_autopilot.PROCEDURE_STOPS)]
    assert [slug for slug in slugs if f"`{slug}`" not in text] == []


REVIEW_VERDICT_RULE = ("A review phase ends at its verdict: stop following `review.md` once the "
                       "round is recorded")


def test_command_ends_the_review_phase_at_the_verdict():
    text = " ".join(_command_text().split())
    assert (REVIEW_VERDICT_RULE in text, "never fix and rerun" in text,
            "back through `next`" in text) == (True, True, True)


def test_command_runs_auto_accept_only_when_eligible():
    text = " ".join(_command_text().split())
    assert ("`review: auto-accept: eligible`" in text, "--auto-accept" in text,
            REVIEW_VERDICT_RULE in text, "never fix and rerun" in text,
            "back through `next`" in text) == (True, True, True, True, True)


def test_command_exempts_the_auto_accept_follow_up_from_the_new_ticket_stop():
    """Review round 4 BLOCK: section 4's no-new-ticket stop must name section 3's
    step 3.3 follow-up as its one exception, or the two sections contradict."""
    text = " ".join(_command_text().split())
    assert "new ticket (T-0012) except section 3's step 3.3 follow-up" in text


def test_command_activates_the_ticket_only_without_a_pointer():
    text = _command_text()
    assert ("activate=1" in text, "crew_ticket.py activate --root . --ticket <ticket>" in text,
            "resume --root . --ticket <ticket>" in text) == (True, True, True)


def test_command_says_the_status_edit_keeps_the_approval():
    text = " ".join(_command_text().split())
    assert ("every implement ends in an approval stop" in text,
            "keeps the approval" in text) == (False, True)


def test_command_leaves_accept_and_pr_review_to_the_human():
    text = " ".join(_command_text().split())
    assert ("`review_ledger.py --accept`" in text, "`gh pr review`" in text,
            "are the human's" in text) == (True, True, True)


def test_command_reads_no_answer_as_a_stop():
    text = " ".join(_command_text().split())
    assert "No output, a traceback or a non-zero exit is a stop" in text


def test_code_enforced_stops_are_not_procedure_stops():
    code = {slug for slug, _text in crew_autopilot.FIXED_STOPS}
    assert ("failed-done-check" in code, "failed-done-check" in {
        slug for slug, _text in crew_autopilot.PROCEDURE_STOPS}) == (False, True)


def test_command_never_types_approve():
    text = _command_text()
    approving = [line for line in text.splitlines()
                 if "/crew:approve" in line and "human" not in line.lower()]
    # T-0010 review round 3: the one `approval.json` is the exception sentence
    # naming what section 3's `approve` script writes -- never a file to write.
    rest = text.replace("it writes `approval.json`, `scope-tickets.json`", "", 1)
    assert ("crew_ticket.py approve" in text, "approval.json" in rest, approving,
            text.count("approval.json")) == (False, False, [], 1)


def test_autopilot_report_calls_run_stop():
    """T-0060: which stop pings is decided by `crew_notify.py run-stop`, tested
    code, not by prose. The report section names it once, for every stop,
    with `next`'s phase. Group review (G2) BLOCK: never the reason, which can
    quote ticket text, interpolated into a shell command."""
    text = _command_text()
    report = text[text.index("## 5."):]
    lines = [line for line in text.splitlines() if "crew_notify.py run-stop" in line]

    assert (len(lines), "crew_notify.py run-stop --root . --ticket <ticket> --phase <p>`"
            in report, "--reason" in lines[0], "at every stop" in report) == (1, True, False, True)
    # T-0060 port review BLOCK: a claim refused for a stale or unknown marker
    # stops before `next` names a phase; it stops as `in-flight`, so the ping runs.
    claim = text[text.index("## 2."):text.index("## 3.")]
    assert "stops, as phase `in-flight` for section 5's ping" in claim


def test_command_drives_through_the_cli_and_writes_the_resume_line():
    text = _command_text()
    for needle in ("crew_autopilot.py settings", "crew_autopilot.py resume",
                   "crew_autopilot.py next", "resume: /crew:autopilot <ticket>"):
        assert needle in text, needle


# --- step 7: sabotage anchors ------------------------------------------------

def test_every_autopilot_sabotage_anchor_is_present_exactly_once():
    from sabotage_autopilot import AUTOPILOT_MUTATIONS  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, test in AUTOPILOT_MUTATIONS:
        with open(target, encoding="utf-8") as handle:
            assert handle.read().count(find) == 1, label
        assert test.startswith(("tests/test_crew_autopilot.py::",
                                "tests/test_crew_autopilot_deploy.py::",
                                "tests/test_crew_autopilot_status.py::",
                                "tests/test_crew_ticket_mint.py::",
                                "tests/test_crew_autopilot_assign.py::")), label
    # T-0010's POLICY_MUTATIONS, the approve exception's six included: they
    # share these targets, so an anchor either list moves must stay unique.
    from sabotage_autopilot import POLICY_MUTATIONS  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, test in POLICY_MUTATIONS:
        with open(target, encoding="utf-8") as handle:
            assert handle.read().count(find) == 1, label
        assert test.startswith(("tests/test_crew_autopilot_policy.py::",
                                "tests/test_crew_autopilot.py::",
                                "tests/test_crew_autopilot_status.py::",
                                "tests/test_crew_route.py::", "tests/test_crew_ticket.py::",
                                "tests/test_scope_guard.py::")), label


def test_status_sabotage_is_registered_with_sabotage_py():
    import sabotage  # pylint: disable=import-outside-toplevel
    from sabotage_autopilot import STATUS_MUTATIONS  # pylint: disable=import-outside-toplevel

    missing = [m[0] for m in STATUS_MUTATIONS if m not in sabotage.MUTATIONS]

    assert (len(STATUS_MUTATIONS), missing) == (45, [])


def test_autopilot_block_is_personal_since_t0050():
    """T-0050 reversed the repo-only rule: the block's keys are personal, kept
    by `filter_global` and combined per key by `resolve_config`."""
    import crew_config  # pylint: disable=import-outside-toplevel
    kept, ignored = crew_config.filter_global({"autopilot": {"mode": "plan"}})

    assert (kept, ignored, crew_config.is_global_path("autopilot.mode")) == (
        {"autopilot": {"mode": "plan"}}, [], True)


# --- T-0087: a refunded tool-failure round goes back to review -----------------------

def test_next_refunded_incomplete_goes_to_review(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [dict(_round(1, "INCOMPLETE"), refunded=True, failure_class="tool")],
            state="REVIEWED")
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "fresh")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"], "refunded" in got["reason"]) == (
        "review", False, f"/crew:review {T}", True)


def test_next_refunded_incomplete_refreshes_first(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [dict(_round(1, "INCOMPLETE"), refunded=True, failure_class="tool")],
            state="REVIEWED")
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "stale")

    got = _next(root)

    assert got["phase"] == "refresh"


def test_next_refunded_rerun_after_review_is_not_no_progress(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [dict(_round(1, "INCOMPLETE"), refunded=True, failure_class="tool")],
            state="REVIEWED")
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "fresh")

    got = _next(root, phases_run=1, last_command=f"/crew:review {T}", max_phases=12)

    assert (got["phase"], got["stop"], got["command"], sorted(got)) == (
        "review", False, f"/crew:review {T}",
        ["command", "evidence", "index_source", "phase", "reason", "stop", "ticket"])


def test_next_refunded_round_with_a_refresh_still_stale_is_no_progress(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [dict(_round(1, "INCOMPLETE"), refunded=True, failure_class="tool")],
            state="REVIEWED")
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "stale", command="graphify update .")

    got = _next(root, phases_run=1, last_command="graphify update .", max_phases=12)

    assert (got["phase"], got["stop"], got["reason"].startswith("no progress")) == (
        "refresh", True, True)


def test_next_unrefunded_rerun_after_review_is_still_no_progress(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="REVIEWED")
    _receipt_ok(monkeypatch, False)
    _refresh(monkeypatch, "fresh")

    got = _next(root, phases_run=1, last_command=f"/crew:review {T}", max_phases=12)

    assert (got["stop"], got["reason"].startswith("no progress")) == (True, True)


def test_module_defines_each_function_once():
    import ast  # pylint: disable=import-outside-toplevel
    with open(_SCRIPT, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = [node.name for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]

    assert sorted({n for n in names if names.count(n) > 1}) == []


# --- T-0049: next --runner reads the in-flight marker ---------------------------------

def _holds(monkeypatch, state, **extra):
    import crew_inflight  # pylint: disable=import-outside-toplevel
    answer = {"state": state, "ticket": T, "runner": "lane", "since": "2026-10-04T10:00:00+00:00",
              "heartbeat_at": "2026-10-04T10:05:00+00:00", "worktree": "/w/other",
              "why": "because", "clear": crew_inflight.clear_command(T)
              if state in ("stale", "unknown") else ""}
    answer.update(extra)
    seen = []
    monkeypatch.setattr(crew_inflight, "holds",
                        lambda root, ticket, runner=None: seen.append(runner) or answer)
    return seen


@pytest.mark.parametrize("state", ["live", "stale", "unknown"])
def test_next_runner_live_stops_in_flight(tmp_path, monkeypatch, state):
    root = _approved(tmp_path)
    seen = _holds(monkeypatch, state)

    got = _next(root, runner="autopilot")

    assert (got["phase"], got["stop"], seen) == ("in-flight", True, ["autopilot"])
    for part in ("lane", T, "2026-10-04T10:00:00+00:00", state):
        assert part in got["reason"], (part, got["reason"])


@pytest.mark.parametrize("state", ["stale", "unknown"])
def test_next_runner_stale_names_clear(tmp_path, monkeypatch, state):
    import crew_inflight  # pylint: disable=import-outside-toplevel
    root = _approved(tmp_path)
    _holds(monkeypatch, state)

    got = _next(root, runner="autopilot")

    assert (got["command"], crew_inflight.clear_command(T) in got["reason"]) == (
        crew_inflight.clear_command(T), True)


def test_next_runner_live_has_no_clear(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _holds(monkeypatch, "live")

    got = _next(root, runner="autopilot")

    assert (got["command"], "clear" in got["reason"]) == ("", False)


def test_next_runner_unknown_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _holds(monkeypatch, "something-new")

    got = _next(root, runner="autopilot")

    assert (got["phase"], got["stop"]) == ("in-flight", True)


def test_next_runner_elsewhere_stops_handover(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _holds(monkeypatch, "elsewhere")

    got = _next(root, runner="autopilot")

    assert (got["phase"], got["stop"], "drive it from /w/other" in got["reason"]) == (
        "handover-elsewhere", True, True)


def test_next_runner_import_error_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    monkeypatch.setitem(sys.modules, "crew_inflight", None)

    got = _next(root, runner="autopilot")

    assert (got["phase"], got["stop"], "crew_inflight" in got["reason"]) == (
        "in-flight", True, True)


def test_next_runner_holds_raising_stops(tmp_path, monkeypatch):
    import crew_inflight  # pylint: disable=import-outside-toplevel
    root = _approved(tmp_path)

    def boom(*_args, **_kwargs):
        raise RuntimeError("marker exploded")
    monkeypatch.setattr(crew_inflight, "holds", boom)

    got = _next(root, runner="autopilot")

    assert (got["phase"], got["stop"], "marker exploded" in got["reason"]) == (
        "in-flight", True, True)


@pytest.mark.parametrize("state", ["free", "mine"])
def test_next_runner_free_and_mine_match_plain_next(tmp_path, monkeypatch, state):
    root = _approved(tmp_path)
    plain = _next(root)
    _holds(monkeypatch, state)

    assert _next(root, runner="autopilot") == plain


def test_next_runner_real_marker_free_mine_then_stale(tmp_path, monkeypatch):
    import crew_inflight  # pylint: disable=import-outside-toplevel
    root = _approved(tmp_path)
    plain = _next(root)
    monkeypatch.setattr(crew_inflight, "_holder_pid", os.getpid)
    assert _next(root, runner="autopilot") == plain
    crew_inflight.claim(str(root), T, "autopilot", session="s", spawn=lambda *a: None)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s")
    assert _next(root, runner="autopilot") == plain
    path = os.path.join(crew_inflight.inflight_dir(str(root)), f"{T}.json")
    with open(path, encoding="utf-8") as handle:
        marker = json.load(handle)
    marker["heartbeat_at"] = "2020-01-01T00:00:00+00:00"
    _write(path, json.dumps(marker))

    got = _next(root, runner="autopilot")

    assert (got["phase"], got["stop"], got["command"]) == (
        "in-flight", True, crew_inflight.clear_command(T))


def test_next_without_runner_is_unchanged(tmp_path, monkeypatch):
    """Without --runner nothing imports or reads crew_inflight."""
    root = _approved(tmp_path)
    plain = _next(root)
    monkeypatch.setitem(sys.modules, "crew_inflight", None)

    assert _next(root) == plain


def test_next_runner_stop_phase_is_returned_first(tmp_path, monkeypatch):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)
    seen = _holds(monkeypatch, "live")

    got = _next(root, runner="autopilot")

    assert (got["phase"], seen) == ("approve", [])


def test_next_runner_writes_nothing(tmp_path):
    import crew_inflight  # pylint: disable=import-outside-toplevel
    root = _approved(tmp_path)
    folder = crew_inflight.inflight_dir(str(root))
    os.makedirs(folder)
    _write(os.path.join(folder, f"{T}.json"), "{bad")
    before = _snapshot(root)

    got = _next(root, runner="autopilot")

    assert (got["phase"], _snapshot(root) == before) == ("in-flight", True)


def test_cli_next_runner(tmp_path):
    root = _approved(tmp_path)
    args = [sys.executable, "-B", _SCRIPT, "next", "--root", str(root), "--ticket", T]

    def run(*extra):
        return subprocess.run(args + list(extra), capture_output=True, text=True, check=False,
                              timeout=60, stdin=subprocess.DEVNULL)

    plain, free, bad = run(), run("--runner", "autopilot"), run("--runner", "robot")

    assert (free.returncode, free.stdout) == (0, plain.stdout)
    assert (bad.returncode, bad.stdout) == (2, "")


def test_fixed_stops_name_the_inflight_phases():
    slugs = [slug for slug, _text in crew_autopilot.FIXED_STOPS]
    assert {"in-flight", "handover-elsewhere"} <= set(slugs)
    assert ("clear-inflight", "clearing another runner's in-flight marker") in \
        crew_state.AUTONOMOUS_STOPS


def test_command_claims_passes_runner_and_releases():
    text = " ".join(_command_text().split())
    claim = text.index("crew_inflight.py claim --root . --ticket <ticket> --runner autopilot")
    assert (text.index("resume --root . --ticket <ticket>") < claim
            < text.index("crew_ticket.py activate") < text.index("Then `claim`")
            < text.index("## 3. The loop"),
            '--last-command "LAST" --runner autopilot' in text,
            "`refused:`" in text,
            "crew_inflight.py release --root . --ticket <ticket>" in text) == (
        True, True, True, True)




# --- T-0070: settings names the autopilot keys this crew does not act on ----

def _inert(got):
    return [w for w in got["warnings"] if w.startswith("inert: ")]


def test_settings_warns_on_inert_autopilot_keys(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _config(root, {"mode": "plan", "reviewPolicy": "fix-and-rereview", "maxLanes": 3})

    got = crew_autopilot.settings(str(root))

    assert [w.split(" - ")[0] for w in _inert(got)] == [
        "inert: autopilot.maxLanes=3 (T-0029)",
        "inert: autopilot.reviewPolicy=fix-and-rereview (T-0029)"]
    done = subprocess.run([sys.executable, _SCRIPT, "settings", "--root", str(root)],
                          capture_output=True, text=True, check=False)
    lines = done.stdout.splitlines()
    assert lines[0].startswith("mode=plan")
    assert "warning: inert: autopilot.reviewPolicy=fix-and-rereview (T-0029) - would choose " \
           "what autopilot does with review findings" in lines


def test_settings_warns_when_naming_an_inert_key_fails(tmp_path, monkeypatch):
    # `settings` warns only, never refuses: when the escaping import that
    # `inert_items` reaches fails, the run still gets its settings and the
    # warning says the inert keys could not be told.
    root = make_repo(tmp_path, mode="off")
    _config(root, {"mode": "plan", "maxLanes": 3})
    monkeypatch.setitem(sys.modules, "completion_audit", None)

    got = crew_autopilot.settings(str(root))

    assert got["armed"] is True
    assert [w.split(" (")[0] for w in _inert(got)] == [
        "inert: could not tell which settings are inert"], got["warnings"]


def test_settings_names_the_global_layer(tmp_path, monkeypatch):
    import crew_config  # pylint: disable=import-outside-toplevel
    path = tmp_path / "global.json"
    path.write_text(json.dumps({"autopilot": {"deploy": "nonprod"}}), encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.settings(str(root))

    # Owner, 2026-10-04: a global `autopilot.deploy` MAY be set (T-0050). Before
    # T-0050 the filter drops it and the line says it is `not read`; after, the
    # deploy warning names T-0045. Neither may call it repo-only or forbidden.
    told = " ".join(got["warnings"])
    for wrong in ("repo-only", "may not set"):
        assert wrong not in told, got["warnings"]
    inert = [w.split(" - ")[0] for w in _inert(got)]
    assert inert in ([], ["inert: autopilot.deploy=nonprod (global, not read)"]), inert
    assert inert or "T-0045" in told, got["warnings"]
    assert got["deploy"] == ("none" if inert else "nonprod")


def test_settings_is_quiet_for_implemented_keys(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _config(root, {"mode": "plan", "maxPhases": 5, "approval": "self", "questions": "risk"})

    assert crew_autopilot.settings(str(root))["warnings"] == []


def test_settings_does_not_repeat_the_deploy_warning(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _config(root, {"deploy": "nonprod"})

    got = crew_autopilot.settings(str(root))

    assert (len(got["warnings"]), _inert(got)) == (1, [])
    assert "T-0045" in got["warnings"][0]


def test_settings_backlog_mode_names_its_ticket(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _config(root, {"mode": "backlog"})

    got = crew_autopilot.settings(str(root))

    assert "'backlog'" in got["warnings"][0]
    assert [w.split(" - ")[0] for w in _inert(got)] == ["inert: autopilot.mode=backlog (L-0541)"]
# --- T-0037: cancelled and superseded close; needs-owner waits on the owner ------

def _with_line2(root, line, ticket=T, header=HEADER):
    """spec.md with `line` under the header, where `depends-on:` sits."""
    first, rest = _spec_text(ticket, header).split("\n", 1)
    _write(root / ".work" / "tickets" / ticket / "spec.md", f"{first}\n{line}\n{rest}")


@pytest.mark.parametrize("where", ["index", "header"])
def test_superseded_parent_is_closed(tmp_path, where):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, status="superseded" if where == "index" else "spec")
    _with_line2(root, "split-into: T-2, T-3",
                header="status: superseded   risk: high" if where == "header" else HEADER)

    got = _next(root)
    shown = crew_autopilot.status(str(root), T)

    assert (got["phase"], got["stop"], "split-into: T-2, T-3" in got["reason"],
            ("INDEX.md" if where == "index" else "spec.md header") in got["reason"],
            shown["waiting"]) == ("closed", True, True, True, "nobody - the ticket is closed")


@pytest.mark.parametrize("where", ["index", "header"])
def test_cancelled_header_is_closed(tmp_path, where):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, status="cancelled" if where == "index" else "spec",
            header="status: cancelled   risk: high" if where == "header" else HEADER)

    got = _next(root)

    assert (got["phase"], got["stop"], "cancelled`" in got["reason"],
            crew_autopilot.status(str(root), T)["waiting"]) == (
        "closed", True, True, "nobody - the ticket is closed")


def test_superseded_by_line_is_quoted(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)
    _with_line2(root, "superseded-by: T-9", header="status: Superseded   risk: high")

    got = _next(root)

    assert (got["phase"], got["reason"].endswith("(superseded-by: T-9)")) == ("closed", True)


def test_merged_header_does_not_close(tmp_path):
    """Unchanged on purpose: a header `merged` is not a closed header word here."""
    root = make_repo(tmp_path, mode="off")
    _ticket(root, header="status: merged   risk: high")

    assert _next(root)["phase"] != "closed"


def test_closed_reads_the_new_header_words(tmp_path):
    """`_closed` (the active-pointer repoint) agrees with `_phase`."""
    root = make_repo(tmp_path, mode="off")
    _ticket(root, header="status: cancelled   risk: high")
    _ticket(root, ticket="T-2", header="status: merged   risk: high")
    _index(root, "T-1 | spec | high | r | t", "T-2 | spec | high | r | t")

    assert (crew_autopilot._closed(str(root), "T-1"),  # pylint: disable=protected-access
            crew_autopilot._closed(str(root), "T-2")) == (True, False)  # pylint: disable=protected-access


def test_needs_owner_stops_for_owner(tmp_path):
    root = _approved(tmp_path)
    _index(root, f"{T} | needs-owner | high | r | title")
    _write(root / ".work" / "tickets" / T / "direction.md",
           "go\n## Open questions\n- which tracker closes a cancelled Jira item?\n- none - settled\n")

    got = _next(root)
    shown = crew_autopilot.status(str(root), T)

    assert (got["phase"], got["stop"], "which tracker closes a cancelled Jira item?" in got["reason"],
            "settled" in got["reason"], "cannot tell" in got["reason"], shown["waiting"].split(" - ")[0]) == (
        "needs-owner", True, True, False, False, "owner")


def test_needs_owner_without_questions_says_none(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, spec=False, plan=False, status="Needs-Owner")

    got = _next(root)

    assert (got["phase"], got["stop"], "no open question recorded" in got["reason"],
            "direction is approved" in got["reason"]) == ("needs-owner", True, True, False)


def test_open_index_tickets_drops_closed_words(tmp_path):
    root = make_repo(tmp_path, mode="off")
    for ticket in ("T-1", "T-2", "T-3", "T-4"):
        _ticket(root, ticket=ticket, spec=False, plan=False)
    _index(root, "T-1 | cancelled | high | r | t", "| T-2 | Superseded | high | r | t |",
           "T-3 | needs-owner | high | r | t", "- cancelled: T-4")

    assert crew_autopilot.open_index_tickets(str(root)) == ["T-3"]


# --- T-0063: the main checkout's INDEX ---------------------------------------

def _lane(tmp_path):
    """(main, lane): a repository and a linked worktree of it. `.work/` is
    ignored, as it is here, so the lane starts with no INDEX and no folder."""
    main = make_repo(tmp_path / "main", mode="off")
    lane = tmp_path / "lane"
    git(main, "worktree", "add", "-q", str(lane), "-b", "lane")
    return main, lane


def _folder_only(root, ticket=T):
    """The ticket folder without the INDEX row `_ticket` writes."""
    folder = _ticket(root, ticket=ticket)
    (root / ".work" / "INDEX.md").unlink()
    return folder


def _main_index(main):
    return os.path.join(os.path.realpath(str(main)), ".work", "INDEX.md")


def test_next_reads_the_index_row_from_the_main_checkout(tmp_path):
    main, lane = _lane(tmp_path)
    _index(main, f"{T} | ready | high | r | title")
    _folder_only(lane)

    got = crew_autopilot.next_phase(str(lane), T)

    assert (got["phase"] != "direction-approval", got["index_source"],
            _main_index(main) in got["evidence"]) == (True, _main_index(main), True), got


def test_next_no_row_in_either_checkout_stops(tmp_path):
    main, lane = _lane(tmp_path)
    _index(main, "T-9 | ready | high | r | another")
    _folder_only(lane)

    got = crew_autopilot.next_phase(str(lane), T)

    assert (got["phase"], got["stop"], _main_index(main) in got["reason"],
            ".work/INDEX.md" in got["reason"]) == (
        "direction-approval", True, True, True), got


def test_next_disagreeing_rows_stop(tmp_path):
    main, lane = _lane(tmp_path)
    _index(main, f"{T} | done | high | r | title")
    _ticket(lane, status="ready")

    got = crew_autopilot.next_phase(str(lane), T)

    assert (got["phase"], got["stop"], got["reason"].startswith("index-disagreement:"),
            _main_index(main) in got["reason"], "`ready`" in got["reason"],
            "`done`" in got["reason"]) == ("direction-approval", True, True, True, True, True), got


def test_next_agreeing_rows_proceed(tmp_path):
    main, lane = _lane(tmp_path)
    _index(main, f"{T} | ready | high | r | title")
    _ticket(lane, status="ready")

    got = crew_autopilot.next_phase(str(lane), T)

    assert ("index-disagreement" in got["reason"], got["phase"] != "direction-approval") == (
        False, True), got


def test_next_local_row_answers_without_a_main_row(tmp_path):
    main, lane = _lane(tmp_path)
    _index(main, "T-9 | ready | high | r | another")
    _ticket(lane, status="ready")

    got = crew_autopilot.next_phase(str(lane), T)

    assert (got["phase"] != "direction-approval", os.path.realpath(got["index_source"])) == (
        True, os.path.join(os.path.realpath(str(lane)), ".work", "INDEX.md")), got


def test_next_folder_only_in_the_main_checkout_stops_naming_it(tmp_path):
    main, lane = _lane(tmp_path)
    _ticket(main, status="ready")
    there = os.path.join(os.path.realpath(str(main)), ".work", "tickets", T)

    got = crew_autopilot.next_phase(str(lane), T)

    assert (got["stop"], there in got["reason"], "cp -r" in got["reason"],
            any(e.endswith("spec.md") and str(main) in e for e in got["evidence"])) == (
        True, True, True, False), got


def test_resume_folder_only_in_the_main_checkout_stops_naming_it(tmp_path):
    main, lane = _lane(tmp_path)
    _ticket(main, status="ready")
    there = os.path.join(os.path.realpath(str(main)), ".work", "tickets", T)

    got = crew_autopilot.resume_target(str(lane), T)

    assert (got["stop"], there in got["reason"], "cp -r" in got["reason"]) == (
        True, True, True), got


def test_an_unreadable_main_checkout_is_cannot_tell(tmp_path, monkeypatch):
    _main, lane = _lane(tmp_path)
    _folder_only(lane)
    monkeypatch.setattr(crew_autopilot, "_main_checkout",
                        lambda top: (None, "git worktree list failed: boom"))

    got = crew_autopilot.next_phase(str(lane), T)

    assert (got["stop"], "boom" in got["reason"],
            "main checkout's .work/INDEX.md has no table row" in got["reason"]) == (
        True, True, False), got


def _listing_fails(monkeypatch):
    """`git worktree list` fails; every other git call is real."""
    real = crew_autopilot.git_out
    monkeypatch.setattr(crew_autopilot, "git_out", lambda top, *args: (
        None if args[:2] == ("worktree", "list") else real(top, *args)))


@pytest.mark.parametrize("call", [crew_autopilot.next_phase, crew_autopilot.resume_target])
def test_no_local_folder_and_a_failed_listing_is_cannot_tell(tmp_path, monkeypatch, call):
    """Review FIX 1: the main checkout holds the folder, but the listing that
    would name it failed -- the stop names that, not brainstorm or "absent"."""
    main, lane = _lane(tmp_path)
    _ticket(main, status="ready")
    _listing_fails(monkeypatch)

    got = call(str(lane), T)

    assert (got["stop"], "could not tell whether the ticket folder is in the main checkout"
            in got["reason"], "git worktree list failed" in got["reason"],
            "brainstorm" in got["reason"]) == (True, True, True, False), got


def test_folder_elsewhere_quotes_a_path_with_a_space(tmp_path):
    """Review FIX 2: the printed `cp -r` survives a space in either path."""
    lane = tmp_path / "my lane"
    there = str(tmp_path / "main checkout" / ".work" / "tickets" / T)

    reason = crew_autopilot._folder_elsewhere(str(lane), T, there)  # pylint: disable=protected-access

    dest = crew_ticket.ticket_dir(str(lane), T)
    assert f"cp -r '{there}' '{dest}' " in reason, reason


def test_resume_finds_the_open_ticket_through_the_main_checkout_index(tmp_path):
    main, lane = _lane(tmp_path)
    _index(main, f"{T} | ready | high | r | title")
    _folder_only(lane)

    got = crew_autopilot.resume_target(str(lane))

    assert (got["ticket"], got["source"]) == (T, ".work/INDEX.md (main checkout)"), got


# --- T-0063: a fresh refresh is committed before review and done ---------------

_PATHS = [".crew/codemap/app.md", "docs/diagrams/a b.mmd"]
_COMMIT = ("git add -- .crew/codemap/app.md 'docs/diagrams/a b.mmd' && "
           f'git commit -m "{T}: commit refreshed artifacts" -- '
           ".crew/codemap/app.md 'docs/diagrams/a b.mmd'")


def _uncommitted(monkeypatch, paths):
    import crew_refresh_check  # pylint: disable=import-outside-toplevel
    monkeypatch.setattr(crew_refresh_check, "ticket_freshness", lambda root, ticket: {
        "status": "fresh-uncommitted", "reason": "scope base abc (recorded)",
        "stop": None, "artifacts": [], "uncommitted": list(paths)})


def test_next_commit_refresh_before_review(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="REVIEWED")
    _receipt_ok(monkeypatch, False)
    _uncommitted(monkeypatch, _PATHS)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("commit-refresh", False, _COMMIT), got


def test_next_commit_refresh_after_an_accepted_review(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _uncommitted(monkeypatch, _PATHS)

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("commit-refresh", False, _COMMIT), got


def test_next_done_only_when_committed(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _freshness(monkeypatch, "fresh")

    got = _next(root)

    assert (got["phase"], got["stop"], got["command"]) == ("done", False, f"/crew:done {T}"), got


def test_next_commit_refresh_with_no_paths_stops(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "CLEAN")], state="ACCEPTED", receipt=_receipt(1))
    _receipt_ok(monkeypatch, True)
    _uncommitted(monkeypatch, [])

    got = _next(root)

    assert (got["stop"], got["phase"] != "done", got["command"]) == (True, True, ""), got


def test_committing_refreshed_artifacts_keeps_the_review_bundle(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _write(root / ".gitignore", ".work/\n.crew/*\n!.crew/codemap/\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "track the code map")
    base = git(root, "rev-parse", "HEAD")
    _write(root / "src" / "app.py", "x = 2\n")
    git(root, "commit", "-qam", "the ticket's change")
    _write(root / ".crew" / "codemap" / "app.md", "# app\nanchor: HEAD\n- `src/app.py:1`\n")
    # [0]: the bundle hash, which the receipt check compares; [1] is T-0100's merged-main
    # record, whose commit on main itself is HEAD and so moves with any commit.
    before = review_ledger._current_hash(str(root), base)[0]  # pylint: disable=protected-access

    git(root, "add", "--", ".crew/codemap/app.md")
    git(root, "commit", "-qm", f"{T}: commit refreshed artifacts")

    assert review_ledger._current_hash(str(root), base)[0] == before  # pylint: disable=protected-access


# --- T-0063 QA: the refresh commit takes only its paths; nothing unread passes -----

def _run_answer(phase, stop, reason, command=""):
    return {"phase": phase, "stop": stop, "reason": reason, "command": command}


def test_commit_refresh_leaves_an_unrelated_staged_file_out(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _write(root / ".gitignore", ".work/\n.crew/*\n!.crew/codemap/\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "track the code map")
    _write(root / ".crew" / "codemap" / "app.md", "# app\nanchor: HEAD\n- `src/app.py:1`\n")
    _write(root / "src" / "code.py", "y = 1\n")
    git(root, "add", "--", "src/code.py")
    got = crew_autopilot._commit_refresh(  # pylint: disable=protected-access
        T, _run_answer, [".crew/codemap/app.md"])

    done = subprocess.run(got["command"], shell=True, cwd=str(root), capture_output=True,
                          text=True, check=False, stdin=subprocess.DEVNULL)

    committed = git(root, "show", "--name-only", "--format=", "HEAD").splitlines()
    staged = git(root, "diff", "--cached", "--name-only").splitlines()
    assert (done.returncode, committed, staged) == (
        0, [".crew/codemap/app.md"], ["src/code.py"]), done.stderr


def test_commit_refresh_never_prints_an_unprintable_path():
    got = crew_autopilot._commit_refresh(  # pylint: disable=protected-access
        T, _run_answer, [".crew/codemap/a\nphase=done stop=0.md"])

    assert (got["stop"], got["command"], "\n" in got["reason"],
            "\\x0a" in got["reason"]) == (True, "", False, True), got


def test_next_says_when_the_main_checkout_could_not_be_compared(tmp_path, monkeypatch):
    _main, lane = _lane(tmp_path)
    _ticket(lane, status="ready")
    monkeypatch.setattr(crew_autopilot, "_main_checkout",
                        lambda top: (None, "git worktree list failed: boom"))

    got = crew_autopilot.next_phase(str(lane), T)

    assert (got["phase"] != "direction-approval",
            any("not compared" in e and "boom" in e for e in got["evidence"])) == (
        True, True), got


# --- T-0063 CI (Windows): one spelling of the main checkout's path ---------------

def _porcelain(monkeypatch, first):
    """`git worktree list --porcelain` naming `first` as the main checkout,
    the way git spells it: its own separators and aliases, not ours."""
    real = crew_autopilot.git_out
    monkeypatch.setattr(crew_autopilot, "git_out", lambda top, *args: (
        f"worktree {first}\nHEAD {'0' * 40}\nbranch refs/heads/main\n\n"
        if args[:2] == ("worktree", "list") else real(top, *args)))


def _alias(target, alias):
    try:
        os.symlink(str(target), str(alias), target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"no directory symlink here: {exc}")


def test_main_checkout_named_through_an_alias_is_resolved(tmp_path, monkeypatch):
    main, lane = _lane(tmp_path)
    alias = tmp_path / "alias"
    _alias(main, alias)
    _porcelain(monkeypatch, str(alias) + os.sep + "." + os.sep)

    assert crew_autopilot._main_checkout(str(lane)) == (  # pylint: disable=protected-access
        os.path.realpath(str(main)), "")


def test_lane_named_through_an_alias_is_not_a_second_checkout(tmp_path, monkeypatch):
    _main, lane = _lane(tmp_path)
    alias = tmp_path / "lane-alias"
    _alias(lane, alias)
    _porcelain(monkeypatch, str(alias))

    assert crew_autopilot._main_checkout(str(lane)) == (None, "")  # pylint: disable=protected-access


def test_a_path_outside_the_checkout_is_named_exactly_as_given(tmp_path):
    """Never re-slashed: on Windows the evidence and the reason must carry
    the same string `index_source` does. A backslash inside a POSIX name
    stands in for Windows' separator, which a POSIX run cannot produce."""
    _main, lane = _lane(tmp_path)
    outside = str(tmp_path / "x\\y" / ".work" / "INDEX.md")

    assert (crew_autopilot._rel_inside(str(lane), outside),  # pylint: disable=protected-access
            crew_autopilot._rel_inside(str(lane), str(lane / ".work" / "INDEX.md"))) == (  # pylint: disable=protected-access
        outside, ".work/INDEX.md")


# --- L-0639: INDEX_DONE and crew_state's closed words are one set ------------

def test_index_done_matches_crew_state():
    assert set(crew_autopilot.INDEX_DONE) == crew_state._TABLE_DONE_WORDS  # pylint: disable=protected-access


@pytest.mark.parametrize("word", ["cancelled", "superseded"])
def test_next_cancelled_index_row_is_closed(tmp_path, word):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, status=word)
    got = _next(root)
    assert (got["phase"], got["stop"]) == ("closed", True)
