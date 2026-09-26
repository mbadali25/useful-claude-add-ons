"""T-0018: `/crew:autopilot`'s subcommand router and its read-only `status`.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_status.py -q

`crew_autopilot.route` decides the subcommand from the command's first
argument and refuses a word it does not know rather than reading it as a
ticket id. `crew_autopilot.status` reports where a ticket stands in at most
12 lines, writes nothing, and says `unknown` wherever it cannot tell. Every
repository is built under tmp_path; nothing touches the real one or
~/.claude. `sabotage_autopilot.STATUS_MUTATIONS` mutates the must-refuse and
must-say-unknown branches to prove these tests can fail.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_ticket
import review_ledger
from scope_fixtures import make_repo
from test_crew_autopilot import (_COMMAND, _SCRIPT, _approved, _config, _handoff, _ledger, _round,
                                 _snapshot, _ticket, _two_tickets, _write)

T = "T-1"


# --- step 1: route -----------------------------------------------------------

@pytest.mark.parametrize("name", ["status", "run"])
def test_route_each_subcommand(tmp_path, name):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), name)

    assert (got["sub"], got["stop"]) == (name, False)


def test_route_empty_is_run(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), "")

    assert (got["sub"], got["stop"]) == ("run", False)


def test_route_goal_flag_is_run(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), "--goal")

    assert (got["sub"], got["stop"], "T-0012" in got["reason"]) == ("run", True, True)


@pytest.mark.parametrize("token", ["T-1", "T-0018", "ABC-42"])
def test_route_ticket_id_is_run(tmp_path, token):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), token)

    assert (got["sub"], got["stop"]) == ("run", False)


def test_route_existing_folder_is_run(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, ticket="fix-login")

    got = crew_autopilot.route(str(root), "fix-login")

    assert (got["sub"], got["stop"]) == ("run", False)


@pytest.mark.parametrize("token", ["stauts", "Status", "rm", "../..", "T-1 x", "t-1", "T-1\n"])
def test_route_unknown_word_refuses(tmp_path, token):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), token)

    assert (got["sub"], got["stop"], "status|run|assign|goal|focus" in got["reason"]) == (
        "", True, True)


@pytest.mark.parametrize("name,ticket", [("assign", "T-0019"), ("goal", "T-0012"),
                                         ("focus", "T-0020")])
def test_route_unavailable_names_its_ticket(tmp_path, name, ticket):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), name)

    assert (got["sub"], got["stop"], f"arrives with {ticket}" in got["reason"]) == (
        name, True, True)


def test_route_every_subcommand_is_available_or_names_its_ticket():
    unaccounted = [name for name in crew_autopilot.SUBCOMMANDS
                   if name not in crew_autopilot.AVAILABLE
                   and name not in crew_autopilot.ARRIVES]

    assert unaccounted == []


@pytest.mark.parametrize("token,line", [
    ("status", "sub=status stop=0 reason="),
    ("stauts", "sub= stop=1 reason=unknown subcommand"),
])
def test_route_cli_prints_one_line(tmp_path, capsys, token, line):
    root = make_repo(tmp_path, mode="off")

    code = crew_autopilot.main(["route", "--root", str(root), "--first", token])

    out = capsys.readouterr().out
    assert (code, out.startswith(line), out.count("\n")) == (0, True, 1)


# --- step 2: status ----------------------------------------------------------

def _corrupt_ledger(root):
    path = review_ledger.ledger_path(str(root), T)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path, "{not json")


def _lines(root, *args):
    done = subprocess.run([sys.executable, _SCRIPT, "status", "--root", str(root), *args],
                          capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)
    return done.returncode, done.stdout.splitlines()


def _field(lines, name):
    found = [line for line in lines if line.startswith(name + ":")]
    assert len(found) == 1, (name, lines)
    return found[0]


def test_status_lines_on_an_implement_phase(tmp_path):
    root = _approved(tmp_path)
    crew_ticket.activate(str(root), T)

    code, lines = _lines(root)

    assert (code, _field(lines, "ticket"), _field(lines, "phase"), _field(lines, "waiting on"),
            _field(lines, "review")) == (
        0, "ticket: T-1 (from active-ticket)", "phase: implement - next: /crew:implement T-1",
        "waiting on: autopilot - run /crew:autopilot to continue",
        "review: EMPTY, 2 of 2 rounds left")


def test_status_mode_line_reads_off_by_default(tmp_path):
    root = _approved(tmp_path)

    _code, lines = _lines(root, "--ticket", T)

    assert _field(lines, "mode").startswith("mode: off")


def test_status_waiting_on_owner_at_approve(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)

    got = crew_autopilot.status(str(root), T)

    assert (got["phase"], got["stop"], got["waiting"]) == (
        "approve", True, f"owner - types /crew:approve {T}")


def test_status_reserved_round_waits_on_reviewer(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [_round(1, status="reserved")])

    got = crew_autopilot.status(str(root), T)

    assert (got["phase"], got["waiting"].split(" - ")[0]) == ("review", "reviewer")


def test_status_unknown_ledger_is_unknown(tmp_path):
    root = _approved(tmp_path)
    _corrupt_ledger(root)

    got = crew_autopilot.status(str(root), T)

    assert got["review"] == "unknown (ledger unreadable)"


def test_status_unmapped_phase_is_unknown(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    monkeypatch.setattr(crew_autopilot, "next_phase", lambda *a, **k: {
        "ticket": T, "phase": "mystery", "stop": False, "reason": "r", "command": "/x",
        "evidence": []})

    got = crew_autopilot.status(str(root), T)

    assert (got["waiting"].startswith("unknown"), "mystery" in got["waiting"]) == (True, True)


def test_status_without_a_ticket_says_unknown(tmp_path):
    root = _two_tickets(tmp_path)

    got = crew_autopilot.status(str(root))

    assert (got["ticket"], got["phase"], got["review"]) == (
        None, "unknown", "unknown (no ticket)")


def test_status_resume_line_absent_handoff(tmp_path):
    root = _approved(tmp_path)

    got = crew_autopilot.status(str(root), T)

    assert got["resume_line"] == "no .work/HANDOFF.md"


def test_status_resume_line_unavailable_without_crew_resume(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _handoff(root, f"resume: /crew:autopilot {T}")
    monkeypatch.setitem(sys.modules, "crew_resume", None)

    got = crew_autopilot.status(str(root), T)

    assert got["resume_line"] == "unavailable (T-0006 not landed)"


def test_status_resume_line_usable(tmp_path):
    root = _approved(tmp_path)
    _handoff(root, f"resume: /crew:autopilot {T}")

    got = crew_autopilot.status(str(root), T)

    assert got["resume_line"] == f"/crew:autopilot {T} (usable)"


@pytest.mark.parametrize("line,head,reason", [
    (f"resume: /crew:autopilot {T}", "0123456789", "head: does not match this checkout"),
    (f"resume: /crew:approve {T}", None, "/crew:approve is excluded from auto-resume"),
    ("resume: rm -rf ~ EVIL", None, "not an allowlisted /crew: command"),
    ("resume: /crew:autopilot --goal ship-it", None, "goal resume arrives with T-0012"),
], ids=["head", "excluded", "not-allowlisted", "goal"])
def test_status_resume_line_mismatch_reason(tmp_path, line, head, reason):
    root = _approved(tmp_path)
    _handoff(root, line, head=head)

    got = crew_autopilot.status(str(root), T)

    assert (got["resume_line"].startswith("not usable: "), reason in got["resume_line"],
            "EVIL" in got["resume_line"]) == (True, True, False)


def test_status_several_open_tickets_names_them(tmp_path):
    root = _two_tickets(tmp_path)

    _code, lines = _lines(root)

    assert ("T-1" in _field(lines, "ticket"), "T-2" in _field(lines, "ticket")) == (True, True)


def test_status_prints_fell_through_lines(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")

    _code, lines = _lines(root)

    assert [line for line in lines if line.startswith("fell through: ")] == [
        "fell through: no .work/HANDOFF.md"]


def test_status_prints_the_disagreement_line(tmp_path):
    root = _approved(tmp_path)
    crew_ticket.activate(str(root), T)
    _handoff(root, f"resume: /crew:plan {T}")

    _code, lines = _lines(root)

    assert _field(lines, "disagreement").endswith("disk wins")


def test_status_argument_without_a_folder_says_so(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.status(str(root), "T-9")

    assert (got["ticket"], got["phase"], "no .work/tickets/" in got["reason"]) == (
        None, "unknown", True)


def _git_state(root):
    index = os.path.join(str(root), ".git", "index")
    return _snapshot(root), os.stat(index).st_mtime_ns


@pytest.mark.parametrize("args", [(), ("--ticket", T)], ids=["resume", "argument"])
def test_status_writes_nothing(tmp_path, args):
    root = _approved(tmp_path)
    _handoff(root, f"resume: /crew:autopilot {T}")
    _write(root / "src" / "app.py", "x = 2\n")
    before = _git_state(root)

    code, lines = _lines(root, *args)

    assert (code, bool(lines), _git_state(root) == before) == (0, True, True)


def test_status_at_most_12_lines(tmp_path):
    root = _two_tickets(tmp_path)
    _config(root, {"mode": "Plan", "maxPhases": 0})
    _write(root / ".crew" / "crew.json", json.dumps({"autopilot": {"mode": "plan"}}))
    _handoff(root, "resume: /crew:autopilot T-1", head="0123456789")

    code, lines = _lines(root)

    assert (code, len(lines) <= crew_autopilot.STATUS_MAX_LINES,
            crew_autopilot.STATUS_MAX_LINES) == (0, True, 12)


def test_status_folds_a_multiline_reason_into_one_line(tmp_path):
    got = crew_autopilot.status_text({
        "mode": "off", "warnings": ["a\nb\nc"], "ticket": None, "source": "x",
        "reason": "one\ntwo", "phase": "unknown", "command": "", "stop": True,
        "waiting": "unknown", "review": "unknown (no ticket)", "resume_line": "r",
        "fallthrough": ["f\ng"], "disagreement": ""})

    assert len(got.splitlines()) == 8


def test_status_cli_that_raises_exits_zero_and_says_unknown(tmp_path, monkeypatch, capsys):
    root = make_repo(tmp_path, mode="off")

    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "status", boom)

    code = crew_autopilot.main(["status", "--root", str(root)])

    out = capsys.readouterr().out
    assert (code, out.startswith("status: unknown"), "disk on fire" in out) == (0, True, True)


# --- step 3: the command -----------------------------------------------------

def _command_text():
    with open(_COMMAND, encoding="utf-8") as handle:
        return handle.read()


def _section(text, heading):
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:end if end >= 0 else len(text)]


def test_every_subcommand_named_in_command():
    text = _command_text()

    assert [name for name in crew_autopilot.SUBCOMMANDS if f"`{name}`" not in text] == []


def test_every_arriving_subcommand_names_its_ticket_in_command():
    flat = " ".join(_command_text().split())

    assert [ticket for ticket in crew_autopilot.ARRIVES.values() if ticket not in flat] == []


def test_status_section_runs_nothing_else():
    section = _section(_command_text(), "## 1. status")
    fenced = [line.strip() for block in section.split("```")[1::2]
              for line in block.splitlines()[1:] if line.strip()]

    assert (len(fenced), "crew_autopilot.py status --root ." in fenced[0]) == (1, True)


def test_command_routes_before_it_refuses_unarmed():
    text = _command_text()

    assert (text.index("crew_autopilot.py route --root .")
            < text.index("## 1. status")
            < text.index("crew_autopilot.py settings --root .")), \
        "status is read-only and must not need autopilot armed"


def test_command_stops_on_a_router_stop():
    flat = " ".join(_section(_command_text(), "## 0. Route").split())

    assert "`stop=1`: print the reason and stop" in flat


def test_status_text_caps_at_12_lines():
    got = crew_autopilot.status_text({
        "mode": "off", "warnings": [f"w{n}" for n in range(20)], "ticket": T,
        "source": "argument", "phase": "implement", "command": "/crew:implement T-1",
        "stop": False, "waiting": "autopilot", "review": "EMPTY", "resume_line": "r",
        "fallthrough": [], "disagreement": ""}).splitlines()

    assert (len(got), got[-1].startswith("(+15 more")) == (12, True)


# --- step 4: sabotage anchors ------------------------------------------------

def test_every_status_sabotage_anchor_is_present_exactly_once():
    from sabotage_autopilot import STATUS_MUTATIONS  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, test in STATUS_MUTATIONS:
        with open(target, encoding="utf-8") as handle:
            assert handle.read().count(find) == 1, label
        prefix, name = test.split("::")
        assert (prefix, callable(globals().get(name))) == (
            "tests/test_crew_autopilot_status.py", True), label
