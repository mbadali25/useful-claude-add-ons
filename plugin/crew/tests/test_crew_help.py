"""T-0025: `/crew:help` -- where you are and the one command next, or what a
command is for (`crew_help.py`).

    python3 -m pytest plugin/crew/tests/test_crew_help.py -q

`where` reads state only through T-0004/T-0018's `crew_autopilot.status`;
`about` resolves questions only through T-0023's `crew_route.match`. Every
repository is built under tmp_path; nothing touches the real one or
~/.claude.
"""
import ast
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_help
import crew_route
import crew_ticket
from scope_fixtures import make_repo, make_ticket
from test_crew_autopilot import _index, _snapshot, _ticket, _two_tickets

_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts", "crew_help.py")  # pylint: disable=protected-access
_COMMANDS = os.path.join(context._ROOT, "commands")  # pylint: disable=protected-access
T = "T-1"
# Every phase `next` names: the keys of T-0018's waiting-on mapping
# (`crew_autopilot.WAITING`), the one place that lists them.
PHASES = sorted(crew_autopilot.WAITING)
LONG = "a reason " * 60


def _files():
    return sorted(f[:-3] for f in os.listdir(_COMMANDS) if f.endswith(".md"))


# The spec's number, written out: `crew_help.MAX_LINES` is what is under test.
MAX = 8
KINDS = ("where: ", "waiting on: ", "open: ", "next: ", "also: ")


def _shape(lines):
    """The `where` contract every state is held to: at most 8 lines, each one
    of the five kinds, so a line nobody asked for is caught even under the cap."""
    nexts = [line for line in lines if line.startswith("next: ")]
    also = [line for line in lines if line.startswith("also: ")]
    return (len(lines) <= MAX and all(line.startswith(KINDS) for line in lines),
            lines[0].startswith("where: "),
            lines[1].startswith("waiting on: "), len(nexts), 2 <= len(also) <= 3,
            all("\n" not in line and len(line) <= crew_help.LINE_CHARS for line in lines))


_GOOD = (True, True, True, 1, True, True)


def _stub(monkeypatch, phase, stop, command):
    waiting = (f"owner - types {command}" if stop and command
               else "owner - see the phase reason" if stop
               else f"autopilot - run /crew:autopilot {T} to continue")
    result = {"ticket": T, "source": "active-ticket", "phase": phase, "stop": stop,
              "command": command, "phase_reason": LONG, "waiting": waiting, "reason": ""}
    monkeypatch.setattr(crew_autopilot, "status", lambda root, ticket=None: dict(result))


# --- step 1: where -------------------------------------------------------------

def test_the_cap_is_8():
    assert crew_help.MAX_LINES == MAX


def test_every_phase_has_related_commands():
    assert (sorted(crew_help.RELATED), [n for n, pairs in crew_help.RELATED.items()
                                        if not 2 <= len(pairs) <= 3]) == (PHASES, [])


@pytest.mark.parametrize("stop", [True, False], ids=["stop", "go"])
@pytest.mark.parametrize("command", ["", f"/crew:spec {T}"], ids=["no-command", "command"])
@pytest.mark.parametrize("phase", PHASES)
def test_where_has_at_most_8_lines(tmp_path, monkeypatch, phase, stop, command):
    _stub(monkeypatch, phase, stop, command)

    lines = crew_help.where(str(tmp_path))

    assert (_shape(lines), lines[0]) == (_GOOD, f"where: {T} (from active-ticket) - phase {phase}")


def _real_states(tmp_path):
    """(name, root) for the states built on disk, one per kind of answer."""
    none = make_repo(tmp_path, mode="off", name="none")
    several = _two_tickets(tmp_path / "several")
    broken = make_repo(tmp_path, mode="off", name="broken")
    make_ticket(broken, "T-1")
    make_ticket(broken, "T-2", activate=False)
    _index(broken, "T-2 | ready | low | r | two")
    shutil.rmtree(broken / ".work" / "tickets" / "T-1")
    spec = make_repo(tmp_path, mode="off", name="spec")
    _ticket(spec, spec=False, plan=False, status="ready")
    crew_ticket.activate(str(spec), T)
    approve = make_repo(tmp_path, mode="off", name="approve")
    _ticket(approve, status="ready")
    crew_ticket.activate(str(approve), T)
    return {"no-ticket": none, "several": several, "broken": broken, "spec": spec,
            "approve": approve}


def test_real_states_hold_the_shape(tmp_path):
    got = {name: _shape(crew_help.where(str(root)))
           for name, root in _real_states(tmp_path).items()}

    assert got == dict.fromkeys(got, _GOOD)


def test_approve_phase_says_you_type_it(tmp_path):
    root = _real_states(tmp_path)["approve"]

    lines = crew_help.where(str(root))

    assert (lines[0], [line for line in lines if line.startswith("next: ")][0].split(" - ")[0]) \
        == (f"where: {T} (from active-ticket) - phase approve", f"next: you type /crew:approve {T}")


def test_spec_phase_names_the_spec_command(tmp_path):
    root = _real_states(tmp_path)["spec"]

    lines = crew_help.where(str(root))

    assert [line for line in lines if line.startswith("next: ")][0].startswith(
        f"next: /crew:spec {T} - ")


def test_several_open_tickets_are_listed_not_picked(tmp_path):
    root = _two_tickets(tmp_path)

    lines = crew_help.where(str(root))

    assert (lines[0].startswith("where: no single ticket"), "open: T-1, T-2" in lines,
            [line for line in lines if line.startswith("next: ")],
            [line for line in lines if "phase" in line and line.startswith("where: T-")]) == \
        (True, True, ["next: /crew:help <ticket-id> - name one of them to see its phase"], [])


def test_no_ticket_suggests_brainstorm(tmp_path):
    root = make_repo(tmp_path, mode="off")

    lines = crew_help.where(str(root))

    assert "next: /crew:brainstorm <idea> - start a ticket" in lines


def test_broken_pointer_is_named_not_guessed_past(tmp_path):
    root = _real_states(tmp_path)["broken"]

    lines = crew_help.where(str(root))

    assert (lines[0].startswith("where: no single ticket"), lines[1],
            any(line.startswith("where: T-2") for line in lines)) == \
        (True, "waiting on: you - the active-ticket pointer is broken", False)


def test_a_raising_reader_is_cannot_tell(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "status", boom)

    lines = crew_help.where(str(tmp_path))

    assert (lines[0], len(lines) <= crew_help.MAX_LINES) == (
        "where: cannot tell - crew_autopilot raised RuntimeError: disk on fire", True)


def test_where_writes_nothing(tmp_path):
    states = _real_states(tmp_path)
    before = {name: _snapshot(root) for name, root in states.items()}

    for root in states.values():
        crew_help.where(str(root))
        crew_help.about("what now", str(root))
        crew_help.about("T-2", str(root))
        crew_help.about("implement", str(root))
        subprocess.run([sys.executable, _SCRIPT, "where", "--root", str(root)],
                       capture_output=True, check=True, stdin=subprocess.DEVNULL)

    assert {name: _snapshot(root) for name, root in states.items()} == before


def test_where_leaves_every_mtime_alone(tmp_path):
    root = _two_tickets(tmp_path)
    stamps = {os.path.join(base, f): os.stat(os.path.join(base, f)).st_mtime_ns
              for base, _dirs, files in os.walk(root) for f in files}

    subprocess.run([sys.executable, _SCRIPT, "where", "--root", str(root)],
                   capture_output=True, check=True, stdin=subprocess.DEVNULL)

    assert {p: os.stat(p).st_mtime_ns for p in stamps if os.path.exists(p)} == stamps


@pytest.mark.parametrize("argv", [["where"], ["about", "implement"], ["about", "what", "now"],
                                  ["about", "--root", ".", "--", "/crew:done"], ["bogus"], []])
def test_cli_exits_zero(tmp_path, argv):
    root = make_repo(tmp_path, mode="off")

    done = subprocess.run([sys.executable, _SCRIPT] + argv, cwd=str(root), capture_output=True,
                          text=True, check=False, stdin=subprocess.DEVNULL)

    assert done.returncode == 0, done.stderr


# --- step 2: about -------------------------------------------------------------

@pytest.mark.parametrize("form", ["{n}", "/crew:{n}", "crew:{n}", " /CREW:{n} "])
def test_every_command_file_resolves(form):
    got = {name: crew_help.about(form.format(n=name)) for name in _files()}

    assert {name: [line.split(":", 1)[0] for line in lines[1:]] + [lines[0].startswith(
        f"/crew:{name}: ")] for name, lines in got.items()} == \
        dict.fromkeys(got, ["when", "arguments", "next", True])


def test_every_command_is_in_exactly_one_group():
    members = [name for _group, names in crew_help.GROUPS for name in names]

    assert (sorted(members), len(members)) == (_files(), len(set(members)))


def test_a_new_command_without_a_group_is_caught(tmp_path, monkeypatch):
    """The grouping check is not vacuous: a command file nobody grouped
    shows up as `ungrouped`, and the membership check above goes red."""
    stage = tmp_path / "commands"
    shutil.copytree(_COMMANDS, stage)
    (stage / "newthing.md").write_text("---\ndescription: new\n---\n", encoding="utf-8")
    monkeypatch.setattr(crew_help, "COMMANDS_DIR", str(stage))

    assert crew_help.groups_text()[-1] == "ungrouped: newthing"


def test_removal_stubs_are_in_removed():
    assert dict(crew_help.GROUPS)["removed"] == ("ticket", "work")


def test_about_commands_lists_every_group_core_first():
    lines = crew_help.about("commands")

    assert [line.split(":", maxsplit=1)[0] for line in lines] == [g for g, _ in crew_help.GROUPS]


def test_help_questions_use_the_route_table(monkeypatch):
    seen = []

    def spy(prompt):
        seen.append(prompt)
        return {"intent": "review", "command": "/crew:review", "rule": "ticket",
                "ticket_arg": None, "topic": None}
    monkeypatch.setattr(crew_route, "match", spy)

    lines = crew_help.about("look over my work please")

    assert (seen[:1], lines[0], lines[1].startswith("/crew:review: ")) == (
        ["look over my work please"], "you asked: look over my work please", True)


@pytest.mark.parametrize("question,command", [("how do i write the spec", "spec"),
                                              ("write the spec", "spec"),
                                              ("how do i use autopilot", "autopilot"),
                                              ("how do i approve", "approve"),
                                              ("continue", "autopilot"),
                                              ("review it", "review")])
def test_a_question_answers_as_its_command(question, command):
    lines = crew_help.about(question)

    assert (lines[0], lines[1].split(":", 2)[1]) == (f"you asked: {question}", command)


def test_what_now_is_where(tmp_path):
    root = make_repo(tmp_path, mode="off")

    assert crew_help.about("what now", str(root)) == crew_help.where(str(root))


def test_a_ticket_id_is_where_for_that_ticket(tmp_path):
    root = _two_tickets(tmp_path)

    lines = crew_help.about("T-2", str(root))

    assert lines[0] == "where: T-2 (from argument) - phase approve"


def test_help_has_no_phrase_table_of_its_own():
    """One phrase table (T-0023's `crew_route.PHRASES`): crew_help.py imports
    no pattern module and compiles nothing."""
    with open(_SCRIPT, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in (node.names if isinstance(node, ast.Import)
                              else [ast.alias(name=node.module or "")])}
    compiles = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("compile", "fullmatch", "search", "findall", "sub")]

    assert (imported & {"re", "regex", "fnmatch", "glob"}, compiles) == (set(), [])


def test_about_unknown_lists_core():
    lines = crew_help.about("xyzzy plugh")

    assert lines == ["no command matched `xyzzy plugh`",
                     "core: " + ", ".join(dict(crew_help.GROUPS)["core"]),
                     "more: /crew:help commands"]
