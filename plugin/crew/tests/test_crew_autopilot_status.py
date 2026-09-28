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
import re
import shlex
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_ticket
import review_ledger
from scope_fixtures import approve_as_user, make_repo
from test_crew_autopilot import (_COMMAND, _SCRIPT, _approved, _handoff, _index, _ledger, _round,
                                 _snapshot, _spec_text, _ticket, _two_tickets, _write)

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


@pytest.mark.parametrize("text,want", [
    ("", ("run", False, "")),
    ("run", ("run", False, "")),
    ("T-0018", ("run", False, "T-0018")),
    ("run T-0018", ("run", False, "T-0018")),
    ("status", ("status", False, "")),
    ("status T-0018", ("status", False, "T-0018")),
    ("  status   T-0018  ", ("status", False, "T-0018")),
])
def test_route_args_names_the_ticket(tmp_path, text, want):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route_args(str(root), text)

    assert (got["sub"], got["stop"], got["ticket"]) == want


def test_route_args_takes_an_existing_folder_as_the_ticket(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root, ticket="fix-login")

    got = crew_autopilot.route_args(str(root), "status fix-login")

    assert (got["sub"], got["stop"], got["ticket"]) == ("status", False, "fix-login")


@pytest.mark.parametrize("text", ["status stauts", "run rm", "run status", "status run",
                                  "status ../..", "status T-1 T-2", "T-1 T-2", "stauts T-1"])
def test_route_args_refuses_what_is_not_a_ticket(tmp_path, text):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route_args(str(root), text)

    assert (got["stop"], got["ticket"], bool(got["reason"])) == (True, "", True)


@pytest.mark.parametrize("text,line", [
    ("status", "sub=status stop=0 ticket= reason="),
    ("status T-0018", "sub=status stop=0 ticket=T-0018 reason="),
    ("stauts", "sub= stop=1 ticket= reason=unknown subcommand"),
])
def test_route_cli_prints_one_line(tmp_path, capsys, text, line):
    root = make_repo(tmp_path, mode="off")

    code = crew_autopilot.main(["route", "--root", str(root), "--args", text])

    out = capsys.readouterr().out
    assert (code, out.startswith(line), out.count("\n")) == (0, True, 1)


def test_route_args_run_goal_arrives_with_its_ticket(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route_args(str(root), "run --goal ship")

    assert (got["sub"], got["stop"], got["ticket"], "arrives with T-0012" in got["reason"]) == (
        "run", True, "", True)


@pytest.mark.parametrize("argv,line", [
    (["--first", "status"], "sub=status stop=0 reason="),
    (["--first", "run"], "sub=run stop=0 reason="),
    (["--first", ""], "sub=run stop=0 reason="),
    (["--first", "T-0018"], "sub=run stop=0 reason="),
    (["--first", "--goal"], "sub=run stop=1 reason=run --goal <slug> arrives with T-0012"),
    (["--first", "stauts"], "sub= stop=1 reason=unknown subcommand; one of "
                            "status|run|assign|goal|focus"),
    (["--first", "assign"], "sub=assign stop=1 reason=/crew:autopilot assign arrives with "
                            "T-0019"),
    (["--args", "--goal"], "sub=run stop=1 ticket= reason=run --goal <slug> arrives with "
                           "T-0012"),
    (["--args", "-h"], "sub= stop=1 ticket= reason=unknown subcommand"),
], ids=["first-status", "first-run", "first-empty", "first-id", "first-goal", "first-typo",
        "first-assign", "args-goal", "args-dash"])
def test_route_cli_takes_a_token_that_starts_with_a_dash(tmp_path, capsys, argv, line):
    root = make_repo(tmp_path, mode="off")

    code = crew_autopilot.main(["route", "--root", str(root), *argv])

    out = capsys.readouterr().out
    assert (code, out.startswith(line), out.count("\n")) == (0, True, 1)


def test_route_cli_refuses_first_and_args_together(tmp_path, capsys):
    root = make_repo(tmp_path, mode="off")

    code = crew_autopilot.main(["route", "--root", str(root), "--first", "status",
                                "--args", "status"])

    assert (code, capsys.readouterr().out) == (2, "")


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

    assert (got["phase"], got["waiting"].split(" - ", maxsplit=1)[0]) == ("review", "reviewer")


def test_status_unknown_ledger_is_unknown(tmp_path):
    root = _approved(tmp_path)
    _corrupt_ledger(root)

    got = crew_autopilot.status(str(root), T)

    assert got["review"] == "unknown (ledger unreadable)"


def test_status_ledger_without_a_rounds_count_is_unknown(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    monkeypatch.setattr(review_ledger, "status", lambda *_a: {
        "ticket": T, "path": "p", "state": review_ledger.IN_REVIEW, "budget": 2})

    got = crew_autopilot.status(str(root), T)

    assert got["review"] == "unknown (ledger unreadable)"


def test_status_ledger_that_says_unknown_prints_no_rounds_count(tmp_path):
    root = _approved(tmp_path)
    _ledger(root, [], state="UNKNOWN")

    got = crew_autopilot.status(str(root), T)

    assert got["review"] == "unknown (ledger unreadable)"


@pytest.mark.parametrize("state", ["BOGUS", "reviewed", 7], ids=["word", "case", "number"])
def test_status_ledger_state_review_ledger_never_writes_is_unknown(tmp_path, state):
    root = _approved(tmp_path)
    _ledger(root, [], state=state)

    got = crew_autopilot.status(str(root), T)

    assert got["review"] == "unknown (ledger state is not one review_ledger writes)"


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


def _unreadable_handoff(root, monkeypatch, how):
    """A `.work/HANDOFF.md` that exists and cannot be read. The session may
    run as root, where chmod denies nothing, so the denial is injected into
    the reader itself; a directory is a real one."""
    if how == "directory":
        os.makedirs(str(root / ".work" / "HANDOFF.md"))
        return
    if how in ("dangling", "loop"):
        # An entry open() cannot follow: FileNotFoundError for a dangling link,
        # ELOOP for a loop. Either is there, so neither is absent.
        os.symlink("missing" if how == "dangling" else "HANDOFF.md",
                   str(root / ".work" / "HANDOFF.md"))
        return
    _handoff(root, f"resume: /crew:autopilot {T}")
    real = open

    def deny(path, *args, **kwargs):
        if str(path).endswith("HANDOFF.md"):
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, *args, **kwargs)
    monkeypatch.setattr(crew_autopilot, "open", deny, raising=False)


@pytest.mark.parametrize("how", ["denied", "directory", "dangling", "loop"])
def test_status_resume_line_unknown_when_the_handoff_cannot_be_read(tmp_path, monkeypatch,
                                                                    how):
    root = _approved(tmp_path)
    _unreadable_handoff(root, monkeypatch, how)

    got = crew_autopilot.status(str(root), T)

    assert got["resume_line"] == crew_autopilot.HANDOFF_UNREADABLE


@pytest.mark.parametrize("how", ["denied", "directory", "dangling", "loop"])
def test_resume_falls_through_saying_the_handoff_could_not_be_read(tmp_path, monkeypatch, how):
    root = _approved(tmp_path)
    crew_ticket.activate(str(root), T)
    _unreadable_handoff(root, monkeypatch, how)

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["fallthrough"][0]) == (T, crew_autopilot.HANDOFF_UNREADABLE)


def test_status_resume_line_usable_through_a_symlinked_handoff(tmp_path):
    root = _approved(tmp_path)
    _handoff(root, f"resume: /crew:autopilot {T}")
    os.replace(str(root / ".work" / "HANDOFF.md"), str(root / ".work" / "handoff-real.md"))
    os.symlink("handoff-real.md", str(root / ".work" / "HANDOFF.md"))

    got = crew_autopilot.status(str(root), T)

    assert got["resume_line"] == f"/crew:autopilot {T} (usable)"


@pytest.mark.parametrize("work,want", [
    ("dangling", crew_autopilot.HANDOFF_UNREADABLE),
    ("absent", crew_autopilot.HANDOFF_ABSENT),
])
def test_read_handoff_unknown_when_work_is_a_dangling_symlink(tmp_path, work, want):
    root = make_repo(tmp_path, mode="off")
    if work == "dangling":
        os.symlink("missing", str(root / ".work"))

    got = crew_autopilot._read_handoff(str(root))  # pylint: disable=protected-access

    assert got == (None, want)


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


@pytest.mark.parametrize("line,reason", [
    ("resume: /crew:autopilot T-9", "its ticket has no .work/tickets/ folder"),
    ("resume: /crew:autopilot", "it names no ticket"),
    ("resume: /crew:status", "it names no ticket"),
], ids=["no-folder", "no-ticket", "other-command"])
def test_status_resume_line_not_usable_where_resume_falls_through(tmp_path, line, reason):
    root = _approved(tmp_path)
    crew_ticket.activate(str(root), T)
    _handoff(root, line)

    got = crew_autopilot.status(str(root))

    assert (got["resume_line"].startswith("not usable: "), got["resume_line"].endswith(reason),
            bool(got["fallthrough"])) == (True, True, True)


@pytest.mark.parametrize("line,head", [
    (f"resume: /crew:autopilot {T}", None),
    ("resume: /crew:autopilot T-9", None),
    ("resume: /crew:autopilot", None),
    ("resume: /crew:status", None),
    (f"resume: /crew:plan {T}", None),
    (f"resume: /crew:autopilot {T}", "0123456789"),
    ("resume: /crew:autopilot --goal ship-it", None),
    ("resume: none", None),
], ids=["usable", "no-folder", "no-ticket", "other-command", "plan", "head", "goal", "none"])
def test_status_resume_line_usable_only_where_resume_takes_it(tmp_path, line, head):
    root = _approved(tmp_path)
    _handoff(root, line, head=head)
    top = crew_ticket.toplevel(str(root))

    said_usable = crew_autopilot.status(str(root), T)["resume_line"].endswith("(usable)")

    assert said_usable == bool(crew_autopilot._handoff_ticket(top)[0])  # pylint: disable=protected-access


def test_status_ticket_mismatch_waits_on_repointing(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, T)

    got = crew_autopilot.status(str(root), T)

    assert (got["stop"], got["waiting"].startswith("owner - "),
            f"crew_ticket.py activate --ticket {T}" in got["waiting"],
            "/crew:autopilot T-2" in got["waiting"], "/crew:implement" in got["waiting"]) == (
        True, True, True, True, False)


def test_status_unset_pointer_waits_on_autopilot_activating(tmp_path):
    root = _two_tickets(tmp_path)
    approve_as_user(root, "T-2")

    got = crew_autopilot.status(str(root), "T-2")

    assert (got["stop"], got["waiting"]) == (
        True, "autopilot - run /crew:autopilot T-2 to continue; it activates T-2 first")


def test_status_broken_pointer_waits_on_the_owner_fixing_it(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, T)
    for name in ("direction.md", "spec.md", "plan.md"):
        (root / ".work" / "tickets" / "T-2" / name).unlink()
    (root / ".work" / "tickets" / "T-2").rmdir()

    got = crew_autopilot.status(str(root), T)

    assert (got["stop"], got["waiting"].startswith("owner - "), "broken" in got["waiting"],
            "/crew:implement" in got["waiting"]) == (True, True, True, False)


def test_status_waiting_is_unknown_when_the_phase_check_raises(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    monkeypatch.setattr(crew_autopilot, "next_phase", lambda *a, **k: {
        "ticket": T, "phase": "implement", "stop": True, "reason": "r",
        "command": f"/crew:implement {T}", "evidence": []})

    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "_phase", boom)

    got = crew_autopilot.status(str(root), T)

    assert got["waiting"].startswith("unknown")


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


# --- step 5: review round 2 --------------------------------------------------

def _raise(*_a, **_k):
    raise RuntimeError("disk on fire")


@pytest.mark.parametrize("pointer,named", [("T-2", "T-1"), ("T-1", "T-2")],
                         ids=["pointer-T2-handoff-T1", "pointer-T1-handoff-T2"])
@pytest.mark.parametrize("argument", [None, "pointer", "named"])
def test_status_resume_line_not_usable_on_a_pointer_mismatch(tmp_path, pointer, named,
                                                             argument):
    root = _two_tickets(tmp_path, activate=pointer)
    _handoff(root, f"resume: /crew:autopilot {named}")
    ticket = {None: None, "pointer": pointer, "named": named}[argument]

    line = crew_autopilot.status(str(root), ticket)["resume_line"]

    assert (line.startswith("not usable: "), line.endswith("(usable)"),
            f"active ticket is {pointer}" in line) == (True, False, True)


@pytest.mark.parametrize("ticket", [None, "T-1", "T-2"])
def test_status_resume_line_usable_when_pointer_and_handoff_agree(tmp_path, ticket):
    root = _two_tickets(tmp_path, activate="T-1")
    _handoff(root, "resume: /crew:autopilot T-1")

    got = crew_autopilot.status(str(root), ticket)

    assert got["resume_line"] == "/crew:autopilot T-1 (usable)"


def test_status_resume_line_unknown_when_resume_target_raises(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    _handoff(root, f"resume: /crew:autopilot {T}")
    monkeypatch.setattr(crew_autopilot, "resume_target", _raise)

    line = crew_autopilot.status(str(root), T)["resume_line"]

    assert (line.startswith("not usable"), line.endswith("(usable)"), "unknown" in line) == (
        False, False, True)


@pytest.mark.parametrize("change,reason", [
    ("branch", "its branch: does not match this checkout"),
    ("head", "its head: does not match this checkout"),
    ("folder", "its ticket has no .work/tickets/ folder"),
])
def test_status_resume_line_checks_the_handoff_it_read_not_the_one_resume_read(
        tmp_path, change, reason):
    """HANDOFF.md rewritten between `resume_target`'s read and `_resume_line`'s:
    the same ticket, but this read fails a check `resume_target` never saw."""
    root = _approved(tmp_path)
    _handoff(root, f"resume: /crew:autopilot {T}")
    top = crew_ticket.toplevel(str(root))
    bare = crew_autopilot.resume_target(top)
    if change == "folder":
        shutil.rmtree(str(root / ".work" / "tickets" / T))
    else:
        _handoff(root, f"resume: /crew:autopilot {T}",
                 **{change: "elsewhere" if change == "branch" else "0123456789"})

    line = crew_autopilot._resume_line(top, bare)  # pylint: disable=protected-access

    assert (bare["ticket"], line) == (T, f"not usable: /crew:autopilot {T} - {reason}")


def test_status_resume_line_not_usable_when_resume_took_the_ticket_from_elsewhere(tmp_path):
    """HANDOFF.md rewritten the other way: `resume_target`'s read fell through
    and took the same ticket from the active pointer; this read passes every
    check, but bare `/crew:autopilot` did not take the handoff."""
    root = _approved(tmp_path)
    crew_ticket.activate(str(root), T)
    _handoff(root, f"resume: /crew:autopilot {T}", head="0123456789")
    top = crew_ticket.toplevel(str(root))
    bare = crew_autopilot.resume_target(top)
    _handoff(root, f"resume: /crew:autopilot {T}")

    line = crew_autopilot._resume_line(top, bare)  # pylint: disable=protected-access

    assert (bare["ticket"], bare["source"] != "handoff", line) == (
        T, True, f"not usable: /crew:autopilot {T} - bare /crew:autopilot does not take it")


def test_status_resume_line_usable_when_the_handoff_is_rewritten_unchanged(tmp_path):
    root = _approved(tmp_path)
    _handoff(root, f"resume: /crew:autopilot {T}")
    top = crew_ticket.toplevel(str(root))
    bare = crew_autopilot.resume_target(top)
    _handoff(root, f"resume: /crew:autopilot {T}")

    line = crew_autopilot._resume_line(top, bare)  # pylint: disable=protected-access

    assert line == f"/crew:autopilot {T} (usable)"


def test_status_continue_names_this_ticket_when_bare_autopilot_would_not(tmp_path):
    root = _two_tickets(tmp_path, activate="T-1")
    approve_as_user(root, "T-1")
    _handoff(root, "resume: /crew:autopilot T-2")

    got = crew_autopilot.status(str(root), "T-1")

    assert (got["stop"], got["waiting"]) == (
        False, "autopilot - run /crew:autopilot T-1 to continue")


@pytest.mark.parametrize("line", ["resume: /crew:autopilot T-1", None],
                         ids=["handoff-agrees", "no-handoff"])
def test_status_continue_is_bare_when_bare_autopilot_takes_this_ticket(tmp_path, line):
    root = _two_tickets(tmp_path, activate="T-1")
    approve_as_user(root, "T-1")
    if line:
        _handoff(root, line)

    got = crew_autopilot.status(str(root), "T-1")

    assert (got["stop"], got["waiting"]) == (False, "autopilot - run /crew:autopilot to continue")


def test_status_continue_names_this_ticket_when_resume_target_raises(tmp_path, monkeypatch):
    root = _approved(tmp_path)
    crew_ticket.activate(str(root), T)
    monkeypatch.setattr(crew_autopilot, "resume_target", _raise)

    got = crew_autopilot.status(str(root), T)

    assert (got["stop"], got["waiting"]) == (
        False, f"autopilot - run /crew:autopilot {T} to continue")


def _close_t2(root):
    _index(root, "T-1 | spec | high | r | one", "T-2 | done | high | r | two")


def test_status_repoint_never_offers_a_closed_ticket(tmp_path):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, T)
    _close_t2(root)

    got = crew_autopilot.status(str(root), T)

    assert (got["waiting"].startswith("owner - "),
            f"crew_ticket.py activate --ticket {T}" in got["waiting"],
            "/crew:autopilot T-2" in got["waiting"]) == (True, True, False)


@pytest.mark.parametrize("closing", ["index", "header"])
def test_status_repoint_never_offers_a_closed_ticket_without_a_direction(tmp_path, closing):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, T)
    if closing == "index":
        _close_t2(root)
    else:
        _write(root / ".work" / "tickets" / "T-2" / "spec.md",
               _spec_text("T-2", "status: done   risk: high"))
    os.remove(str(root / ".work" / "tickets" / "T-2" / "direction.md"))

    got = crew_autopilot.status(str(root), T)

    assert (f"crew_ticket.py activate --ticket {T}" in got["waiting"],
            "/crew:autopilot T-2" in got["waiting"],
            "T-2 is closed" in got["waiting"]) == (True, False, True)


def test_status_repoint_says_unknown_when_the_active_phase_raises(tmp_path, monkeypatch):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, T)
    real = crew_ticket.read_contract

    def contract(top, ticket):
        if ticket == "T-2":
            raise RuntimeError("disk on fire")
        return real(top, ticket)
    monkeypatch.setattr(crew_ticket, "read_contract", contract)

    got = crew_autopilot.status(str(root), T)

    assert (f"crew_ticket.py activate --ticket {T}" in got["waiting"],
            "/crew:autopilot T-2" in got["waiting"],
            "could not tell whether T-2" in got["waiting"]) == (True, False, True)


def _deny_spec(monkeypatch, ticket):
    """`ticket`'s spec.md exists and cannot be read. chmod denies nothing to
    root, which these sessions run as, so the denial is injected into the
    reader `crew_ticket.read_contract` uses."""
    real = open
    target = os.path.join(".work", "tickets", ticket, "spec.md")

    def deny(path, *args, **kwargs):
        if os.path.normpath(str(path)).endswith(target):
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, *args, **kwargs)
    monkeypatch.setattr(crew_ticket, "open", deny, raising=False)


def test_status_repoint_unreadable_active_spec_is_could_not_tell(tmp_path, monkeypatch):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, T)
    _deny_spec(monkeypatch, "T-2")

    got = crew_autopilot.status(str(root), T)

    assert (f"crew_ticket.py activate --ticket {T}" in got["waiting"],
            "or runs /crew:autopilot T-2" in got["waiting"],
            "could not tell whether T-2 is still open" in got["waiting"]) == (True, False, True)


@pytest.mark.parametrize("spec", ["readable", "absent"])
def test_status_repoint_offers_an_open_active_ticket_whose_spec_reads_or_is_absent(
        tmp_path, spec):
    root = _two_tickets(tmp_path, activate="T-2")
    approve_as_user(root, T)
    if spec == "absent":
        os.remove(str(root / ".work" / "tickets" / "T-2" / "spec.md"))

    got = crew_autopilot.status(str(root), T)

    assert (got["waiting"].endswith("or runs /crew:autopilot T-2"),
            "could not tell" in got["waiting"]) == (True, False)


def _index_reads(monkeypatch, ticket):
    """INDEX.md rows parse INDEX-shaped ids only (`crew_state._TICKET_RE`), so
    a ticket named like a subcommand never gets past direction-approval on
    disk. Its status cell is read as `spec` here so the drive suggestions
    after that phase can be reached at all."""
    real = crew_autopilot._index_status  # pylint: disable=protected-access

    def status_cell(top, name):
        return "spec" if name == ticket else real(top, name)
    monkeypatch.setattr(crew_autopilot, "_index_status", status_cell)


def _subcommand_ticket(tmp_path, monkeypatch, name, activate=True):
    root = make_repo(tmp_path, mode="off")
    for ticket in (name, "T-2"):
        _ticket(root, ticket=ticket)
    _index(root, "T-2 | spec | high | r | two")
    _index_reads(monkeypatch, name)
    approve_as_user(root, name)
    if activate:
        crew_ticket.activate(str(root), name)
    return root


@pytest.mark.parametrize("name", list(crew_autopilot.SUBCOMMANDS) + [T])
def test_status_suggests_run_for_a_ticket_named_like_a_subcommand(tmp_path, monkeypatch, name):
    root = _subcommand_ticket(tmp_path, monkeypatch, name)
    _handoff(root, "resume: /crew:autopilot T-2")
    word = "run " if name in crew_autopilot.SUBCOMMANDS else ""

    got = crew_autopilot.status(str(root), name)
    routed = crew_autopilot.route_args(str(root), f"{word}{name}")

    assert (got["stop"], got["waiting"], routed["sub"], routed["ticket"], routed["stop"]) == (
        False, f"autopilot - run /crew:autopilot {word}{name} to continue", "run", name, False)


@pytest.mark.parametrize("name", ["status", "focus", T])
def test_status_activating_suggestion_runs_a_ticket_named_like_a_subcommand(
        tmp_path, monkeypatch, name):
    root = _subcommand_ticket(tmp_path, monkeypatch, name, activate=False)
    word = "run " if name in crew_autopilot.SUBCOMMANDS else ""

    got = crew_autopilot.status(str(root), name)

    assert (got["stop"], got["waiting"]) == (
        True, f"autopilot - run /crew:autopilot {word}{name} to continue; it activates "
              f"{name} first")


@pytest.mark.parametrize("name", ["status", "assign", "T-3"])
def test_status_repoint_offers_run_for_an_active_ticket_named_like_a_subcommand(
        tmp_path, monkeypatch, name):
    root = _two_tickets(tmp_path)
    _ticket(root, ticket=name)
    _index(root, "T-1 | spec | high | r | one", "T-2 | spec | high | r | two")
    crew_ticket.activate(str(root), name)
    approve_as_user(root, T)
    word = "run " if name in crew_autopilot.SUBCOMMANDS else ""

    got = crew_autopilot.status(str(root), T)
    routed = crew_autopilot.route_args(str(root), f"{word}{name}")

    assert (got["waiting"].endswith(f", or runs /crew:autopilot {word}{name}"),
            routed["sub"], routed["ticket"], routed["stop"]) == (True, "run", name, False)


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


def _plugin_copy(tmp_path):
    """A writable plugin installation with no bytecode cache: every script
    the command runs, and `crew_upgrade`, which crew_config imports from
    skills/crew-graph/scripts."""
    crew = os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT)))
    plugin = tmp_path / "plugin"
    shutil.copytree(crew, str(plugin), ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", "tests", "evals", "docs", "_test"))
    return plugin


def _documented(heading, plugin, arguments):
    """The command's fenced crew_autopilot.py line under `heading`, as argv,
    with Claude Code's substitutions made and `python3` as this interpreter."""
    section = _section(_command_text(), heading)
    line = next(line.strip() for block in section.split("```")[1::2]
                for line in block.splitlines()[1:] if "crew_autopilot.py" in line)
    root = str(plugin).replace("\\", "/")
    line = line.split("  #")[0].replace("${CLAUDE_PLUGIN_ROOT}", root)
    argv = shlex.split(line.replace("$ARGUMENTS", arguments))
    assert argv[0] == "python3", line
    return [sys.executable] + argv[1:]


def test_status_as_the_command_runs_it_writes_no_bytecode(tmp_path):
    root = _approved(tmp_path / "repo")
    plugin = _plugin_copy(tmp_path)
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")}
    outs = [subprocess.run(_documented(heading, plugin, "status"), cwd=str(root), env=env,
                           capture_output=True, text=True, check=False,
                           stdin=subprocess.DEVNULL).stdout
            for heading in ("## 0. Route", "## 1. status")]

    written = [os.path.join(base, name) for base, dirs, files in os.walk(str(plugin))
               for name in dirs + files if name == "__pycache__" or name.endswith(".pyc")]
    assert (outs[0].startswith("sub=status stop=0"), "ticket: " in outs[1], written) == (
        True, True, [])


def _bytecode_env():
    return {k: v for k, v in os.environ.items()
            if k not in ("PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")}


def _bytecode(plugin):
    return [os.path.join(base, name) for base, dirs, files in os.walk(str(plugin))
            for name in dirs + files if name == "__pycache__" or name.endswith(".pyc")]


def test_status_direct_cli_writes_no_bytecode(tmp_path):
    root = _approved(tmp_path / "repo")
    plugin = _plugin_copy(tmp_path)
    script = os.path.join(str(plugin), "hooks", "scripts", "crew_autopilot.py")

    out = subprocess.run([sys.executable, script, "status", "--root", str(root)],
                         cwd=str(root), env=_bytecode_env(), capture_output=True, text=True,
                         check=False, stdin=subprocess.DEVNULL).stdout

    assert ("ticket: " in out, _bytecode(plugin)) == (True, [])


def test_importing_crew_autopilot_leaves_bytecode_setting_alone(tmp_path):
    plugin = _plugin_copy(tmp_path)
    scripts = os.path.join(str(plugin), "hooks", "scripts")
    probe = ("import sys; sys.path.insert(0, sys.argv[1]); import crew_autopilot; "
             "print(sys.dont_write_bytecode)")

    out = subprocess.run([sys.executable, "-c", probe, scripts], cwd=str(tmp_path),
                         env=_bytecode_env(), capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL)

    assert (out.returncode, out.stdout.strip()) == (0, "False")


def test_every_autopilot_invocation_in_command_skips_bytecode():
    lines = [line.strip() for line in _command_text().splitlines()
             if "crew_autopilot.py " in line and "${CLAUDE_PLUGIN_ROOT}" in line]

    assert (len(lines) >= 6, [line for line in lines
                              if not line.lstrip("`").startswith("python3 -B ")]) == (True, [])


def test_status_at_most_12_lines(tmp_path, monkeypatch, capsys):
    root = _two_tickets(tmp_path)
    _handoff(root, "resume: /crew:autopilot T-1", head="0123456789")
    monkeypatch.setattr(crew_autopilot, "settings", lambda _root: {
        "mode": "off", "armed": False, "maxPhases": 12, "saw": None,
        "warnings": [f"w{n}" for n in range(10)]})

    code = crew_autopilot.main(["status", "--root", str(root)])

    lines = capsys.readouterr().out.splitlines()
    assert (code, len(lines), lines[-1].startswith("(+")) == (
        0, crew_autopilot.STATUS_MAX_LINES, True)


@pytest.mark.parametrize("how", ["ordinary", "raises"])
def test_status_json_at_most_12_lines(tmp_path, monkeypatch, capsys, how):
    root = _two_tickets(tmp_path)
    _handoff(root, "resume: /crew:autopilot T-1", head="0123456789")
    monkeypatch.setattr(crew_autopilot, "settings", lambda _root: {
        "mode": "off", "armed": False, "maxPhases": 12, "saw": None,
        "warnings": [f"w{n}" for n in range(10)]})
    if how == "raises":
        monkeypatch.setattr(crew_autopilot, "status", _raise)

    code = crew_autopilot.main(["status", "--root", str(root), "--json"])

    out = capsys.readouterr().out
    kept = len(json.loads(out).get("warnings", []))
    assert (code, len(out.splitlines()) <= crew_autopilot.STATUS_MAX_LINES, kept) == (
        0, True, 10 if how == "ordinary" else 0)


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


def test_command_passes_its_arguments_whole():
    # Claude Code substitutes `$0` with the FIRST argument and leaves an
    # out-of-range `$N` literal (measured on 2.1.283), so a positional `$1`
    # would hand route the ticket and `$2` would never arrive.
    text = _command_text()

    assert (re.findall(r"\$[0-9]", text), "route --root . --args '$ARGUMENTS'" in text) == (
        [], True)


def test_command_stops_on_a_router_stop():
    flat = " ".join(_section(_command_text(), "## 0. Route").split())

    assert "`stop=1`: print the reason and stop" in flat


def test_command_stops_when_route_prints_no_answer():
    flat = " ".join(_section(_command_text(), "## 0. Route").split())

    assert "Anything but a `sub=` line - no output, a traceback, a non-zero exit - is a stop" \
        in flat


def test_command_takes_the_ticket_resume_printed():
    flat = " ".join(_command_text().split())

    assert "from `resume` on, `<ticket>` is the `ticket=` resume printed" in flat


def test_command_never_hands_the_shell_an_expandable_argument():
    flat = " ".join(_section(_command_text(), "## 0. Route").split())

    assert ("--args '$ARGUMENTS'" in flat, '"$ARGUMENTS"' in flat,
            "hold a quote, `$`, a backtick or a backslash, stop" in flat) == (True, False, True)


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


# --- T-0010: route and status are untouched by the approval policy -------------

ROUTE_ARGS = ("", "status", "run T-1", "T-1", "status T-1")


@pytest.mark.parametrize("policy", ["human", "self", "risk"])
def test_route_and_status_unaffected_by_approval_policy(tmp_path, policy):
    from test_crew_autopilot_policy import _repo  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, approval=policy, risk="low")
    config = root / ".crew" / "config.json"
    with_policy = config.read_text(encoding="utf-8")
    before = _git_state(root)
    code, lines = _lines(root)
    after = _git_state(root)
    routed = [crew_autopilot.route_args(str(root), text) for text in ROUTE_ARGS]
    _write(config, json.dumps({"scope": json.loads(with_policy)["scope"]}))

    plain = [crew_autopilot.route_args(str(root), text) for text in ROUTE_ARGS]

    assert (code, _field(lines, "waiting on"), after == before, routed == plain) == (
        0, f"waiting on: owner - types /crew:approve {T}", True, True)
