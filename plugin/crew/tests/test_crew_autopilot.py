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
import json
import os
import subprocess
import sys
import textwrap

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
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
def test_next_budget_spent_without_a_receipt_stops(tmp_path, monkeypatch, refresh):
    """Round 2 CLEAN, then its receipt went stale: a /crew:review now would
    reserve a third round and write NEEDS_REPLAN, unattended."""
    root = _approved(tmp_path)
    _ledger(root, [_round(1, "FINDINGS"), _round(2, "CLEAN")], state="ACCEPTED",
            receipt=_receipt(2))
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


def test_next_post_implement_approval_stop_names_the_header_edit(tmp_path, monkeypatch):
    root = _approved(tmp_path)
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

    assert (got["phase"], got["stop"], "cannot tell" in got["reason"]) == (
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
                                  "- ~~which DB?~~ postgres", "None.", ""])
def test_next_answered_open_questions_do_not_stop(tmp_path, body):
    root = _approved(tmp_path)
    path = root / ".work" / "tickets" / T / "direction.md"
    _write(path, f"go\n## Open questions\n{body}\n")

    assert _next(root)["phase"] == "implement"


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

    assert (got["ticket"], got["stop"], "T-0012" in got["reason"]) == (None, True, True)


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


@pytest.mark.parametrize("value", ["Plan", "plan ", "PLAN", "on", True, "autonomous", None])
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
    assert crew_config.default_config()["autopilot"] == {"mode": "off", "maxPhases": 12}


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


def test_command_activates_the_ticket_only_without_a_pointer():
    text = _command_text()
    assert ("activate=1" in text, "crew_ticket.py activate --root . --ticket <ticket>" in text,
            "resume --root . --ticket $1" in text) == (True, True, True)


def test_command_says_every_implement_ends_in_an_approval_stop():
    assert "every implement ends in an approval stop" in " ".join(_command_text().split())


def test_code_enforced_stops_are_not_procedure_stops():
    code = {slug for slug, _text in crew_autopilot.FIXED_STOPS}
    assert ("failed-done-check" in code, "failed-done-check" in {
        slug for slug, _text in crew_autopilot.PROCEDURE_STOPS}) == (False, True)


def test_command_never_types_approve():
    text = _command_text()
    approving = [line for line in text.splitlines()
                 if "/crew:approve" in line and "human" not in line.lower()]
    assert ("crew_ticket.py approve" in text, "approval.json" in text, approving) == (
        False, False, [])


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
        assert test.startswith("tests/test_crew_autopilot.py::"), label


def test_autopilot_block_is_repo_only():
    import crew_config  # pylint: disable=import-outside-toplevel
    kept, ignored = crew_config.filter_global({"autopilot": {"mode": "plan"}})

    assert (kept, bool(ignored), crew_config.is_global_path("autopilot.mode")) == (
        {}, True, False)
