"""T-0020: `/crew:autopilot focus` -- a scope lock on one ticket.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_focus.py -q

Focus is this worktree's active-ticket pointer
(`crew_ticket.activate` / `deactivate` / `resolve_active`): `focus <id>` sets
it (and `activate` records `.crew/.scope-base`, whose line focus shows), `focus off` clears it, `focus` shows it. While it is set, the router
refuses another ticket, `assign` and `goal`; once the plan is approved, `next`
runs the completion audit read-only and stops as `drift` on any changed path
outside Touch. Every repository is built under tmp_path; nothing touches the
real one or ~/.claude.
"""
import ast
import json
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_ticket
from review_fixtures import git
from scope_fixtures import approve_as_user, make_repo
from test_crew_autopilot import (_COMMAND, _SCRIPT, _approved, _handoff, _index, _snapshot,
                                 _ticket, _write)

_ROOT = context._ROOT  # pylint: disable=protected-access
_HOOKS = os.path.join(_ROOT, "hooks", "hooks.json")
T = "T-1"
OTHER = "T-2"
RELEASE = "/crew:autopilot focus off"
REMINDER = ("Claude Code's built-in /focus only toggles the display (just your prompt, summary, "
            "and response); it does not scope work, and only you can type it")


# --- fixtures ----------------------------------------------------------------

def _two(tmp_path, mode="off"):
    """Two open tickets, T-1 and T-2, each with a folder; no pointer."""
    root = make_repo(tmp_path, mode=mode)
    for ticket in (T, OTHER):
        _ticket(root, ticket=ticket)
    _index(root, f"{T} | spec | high | r | one", f"{OTHER} | spec | high | r | two")
    return root


def _focused(tmp_path, mode="off"):
    root = _two(tmp_path, mode)
    ok, _line = crew_autopilot.focus_set(str(root), T)
    assert ok
    return root


def _pointer(root):
    path = os.path.join(crew_ticket.state_dir(str(root)), "active-ticket")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _crew_state(root):
    return {p: v for p, v in _snapshot(root).items()
            if os.sep + "crew" + os.sep in p and ".work" not in p}


def _break(root, ticket=OTHER):
    """Point this worktree at `ticket`, then remove its folder: a broken pointer."""
    crew_ticket.activate(str(root), ticket)
    folder = root / ".work" / "tickets" / ticket
    for name in os.listdir(folder):
        os.unlink(folder / name)
    folder.rmdir()


def _cli(root, capsys, *rest):
    capsys.readouterr()  # drop what the fixtures printed (approval_hook's context line)
    code = crew_autopilot.main(["focus", "--root", str(root)] + list(rest))
    return code, capsys.readouterr().out


# --- step 1: focus over the active-ticket pointer ------------------------------

def test_focus_set_writes_this_worktree_only(tmp_path):
    root = _two(tmp_path)
    other = tmp_path / "wt2"
    git(root, "worktree", "add", "-q", str(other), "-b", "second")
    _ticket(other, ticket=T)

    ok, line = crew_autopilot.focus_set(str(root), T)

    top = crew_ticket.toplevel(str(root))
    assert (ok, line.startswith(f"focus={T}"), _pointer(root),
            crew_autopilot.focus_state(str(root))["focus"],
            crew_autopilot.focus_state(str(other))["focus"]) == (
        True, True, {top: T}, T, None)


def test_focus_refuses_folderless_ticket(tmp_path):
    root = _two(tmp_path)
    before = _crew_state(root)

    ok, line = crew_autopilot.focus_set(str(root), "T-9")

    assert (ok, line.startswith("refused:"), "no .work/tickets/T-9/" in line,
            _crew_state(root) == before, _pointer(root)) == (False, True, True, True, None)


def test_focus_refuses_switch(tmp_path):
    root = _focused(tmp_path)
    before = _crew_state(root)

    ok, line = crew_autopilot.focus_set(str(root), OTHER)

    assert (ok, f"focus is on {T}" in line, RELEASE in line, _crew_state(root) == before) == (
        False, True, True, True)


def test_focus_same_ticket_is_noop(tmp_path):
    root = _focused(tmp_path)
    before = _crew_state(root)

    ok, line = crew_autopilot.focus_set(str(root), T)

    assert (ok, "nothing written" in line, _crew_state(root) == before) == (True, True, True)


def test_focus_off_clears_this_worktree_only(tmp_path):
    root = _two(tmp_path)
    other = tmp_path / "wt2"
    git(root, "worktree", "add", "-q", str(other), "-b", "second")
    _ticket(other, ticket=OTHER)
    crew_autopilot.focus_set(str(root), T)
    crew_autopilot.focus_set(str(other), OTHER)

    ok, line = crew_autopilot.focus_off(str(root))

    assert (ok, line, crew_autopilot.focus_state(str(root))["focus"],
            crew_autopilot.focus_state(str(other))["focus"],
            _pointer(root)) == (
        True, f"focus=none (released {T})", None, OTHER,
        {crew_ticket.toplevel(str(other)): OTHER})


def test_focus_off_with_nothing_set_says_so(tmp_path):
    root = _two(tmp_path)

    assert crew_autopilot.focus_off(str(root)) == (True, "focus=none (nothing was set)")


def test_focus_off_of_an_unparseable_pointer_is_not_read_as_released(tmp_path):
    root = _focused(tmp_path)
    path = os.path.join(crew_ticket.state_dir(str(root)), "active-ticket")
    _write(path, "{not json")

    ok, line = crew_autopilot.focus_off(str(root))

    assert (ok, line.startswith("focus=broken"), "could not clear" in line) == (
        False, True, True)


def test_focus_show_index_fallback_is_not_focus(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)
    active, where, broken = crew_ticket.resolve_active(str(root))

    got = crew_autopilot.focus_state(str(root))

    assert ((active, where, broken), got["focus"], got["broken"],
            crew_autopilot.focus_show(str(root))) == (
        (T, ".work/INDEX.md", False), None, False, (True, "focus=none"))


def test_focus_show_set(tmp_path):
    root = _focused(tmp_path)

    assert crew_autopilot.focus_show(str(root)) == (True, f"focus={T}")


def test_focus_show_broken(tmp_path):
    root = _two(tmp_path)
    _break(root)

    ok, line = crew_autopilot.focus_show(str(root))

    assert (ok, line.startswith("focus=broken "), OTHER in line,
            crew_autopilot.focus_state(str(root))["broken"]) == (True, True, True, True)


def test_focus_refuses_to_set_over_a_broken_pointer(tmp_path):
    root = _two(tmp_path)
    _break(root)
    before = _crew_state(root)

    ok, line = crew_autopilot.focus_set(str(root), T)

    assert (ok, "broken" in line, RELEASE in line, _crew_state(root) == before) == (
        False, True, True, True)


@pytest.mark.parametrize("rest", [[], ["--ticket", T], ["--ticket", OTHER], ["--off"],
                                  ["--findings", "--ticket", T], ["--ticket", "T-9"],
                                  ["--off", "--ticket", T], ["--findings"]],
                         ids=["show", "set", "switch", "off", "findings", "folderless",
                              "off-and-ticket", "findings-no-ticket"])
def test_focus_output_carries_reminder(tmp_path, capsys, rest):
    root = _focused(tmp_path)

    _code, out = _cli(root, capsys, *rest)

    assert out.splitlines()[-1] == f"reminder: {REMINDER}"


def test_focus_output_carries_reminder_after_a_crash(tmp_path, capsys, monkeypatch):
    root = _focused(tmp_path)

    def boom(_root):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "focus_show", boom)

    code, out = _cli(root, capsys)

    assert (code, out.splitlines()[0].startswith("refused: crew_autopilot raised RuntimeError"),
            out.splitlines()[-1]) == (1, True, f"reminder: {REMINDER}")


def test_focus_scope_off_says_so(tmp_path, capsys):
    root = _focused(tmp_path, mode="off")

    _code, out = _cli(root, capsys)

    assert out.splitlines()[1] == (
        "scope.mode=off: the scope guard is off: writes outside Touch are not refused as they "
        "happen; autopilot's drift stop still applies")


@pytest.mark.parametrize("mode", ["report", "block", "auto"])
def test_focus_scope_on_names_the_mode(tmp_path, capsys, mode):
    root = _focused(tmp_path, mode=mode)

    _code, out = _cli(root, capsys)

    assert (out.splitlines()[1].startswith(f"scope.mode={mode}: "), "is off" in out) == (
        True, False)


def test_focus_cli_set_off_and_exit_codes(tmp_path, capsys):
    root = _two(tmp_path)

    set_code, set_out = _cli(root, capsys, "--ticket", T)
    switch_code, switch_out = _cli(root, capsys, "--ticket", OTHER)
    off_code, off_out = _cli(root, capsys, "--off")

    assert ((set_code, set_out.splitlines()[0].startswith(f"focus={T} ")),
            (switch_code, switch_out.splitlines()[0].startswith("refused: focus is on T-1")),
            (off_code, off_out.splitlines()[0])) == (
        (0, True), (1, True), (0, f"focus=none (released {T})"))


def test_focus_set_records_the_scope_base_and_says_so(tmp_path, capsys):
    """`crew_ticket.activate` records `.crew/.scope-base` too (T-0061), so
    focus writes two files, and the scope-base line reaches the caller."""
    root = _two(tmp_path)

    code, out = _cli(root, capsys, "--ticket", T)

    with open(root / ".crew" / ".scope-base", encoding="utf-8") as handle:
        record = json.load(handle)
    head = git(root, "rev-parse", "HEAD")
    assert (code, record.get(T, {}).get("base"), out.splitlines()[0].startswith(f"focus={T} "),
            f"scope-base: recorded {head[:12]} as the start of {T}" in out) == (
        0, head, True, True)


def test_focus_set_shows_a_scope_base_could_not_tell(tmp_path, capsys):
    """An unknown base is said, never dropped: focus still succeeds (the
    pointer is set), and the could-not-tell line is in its output."""
    root = _two(tmp_path)
    (root / ".crew" / "config.json").write_text(json.dumps(
        {"scope": {"mode": "off"}, "tickets": {"baseBranch": "no-such-branch"}}),
        encoding="utf-8")

    code, out = _cli(root, capsys, "--ticket", T)

    assert (code, crew_autopilot.focus_state(str(root))["focus"],
            f"scope-base: could not tell {T}'s scope base" in out,
            "nothing recorded" in out, out.splitlines()[-1]) == (
        0, T, True, True, f"reminder: {REMINDER}")


def test_focus_cli_refuses_off_with_a_ticket(tmp_path, capsys):
    root = _focused(tmp_path)
    before = _crew_state(root)

    code, out = _cli(root, capsys, "--off", "--ticket", OTHER)

    assert (code, out.startswith("refused:"), _crew_state(root) == before) == (2, True, True)


# --- step 2: focus_guard in the router -----------------------------------------

@pytest.mark.parametrize("text", ["", "run", f"run {T}", T, "focus", f"focus {T}"])
def test_guard_allows_focused_ticket(tmp_path, text):
    root = _focused(tmp_path)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["stop"], got["reason"]) == (False, "")


@pytest.mark.parametrize("text", [f"run {OTHER}", OTHER, f"focus {OTHER}", f"status {OTHER}"])
def test_guard_refuses_other_ticket(tmp_path, text):
    root = _focused(tmp_path)

    got = crew_autopilot.route_args(str(root), text)

    if text.startswith("status"):
        # status is read-only and always runs; it starts no work on OTHER.
        assert (got["stop"], got["ticket"]) == (False, OTHER)
    else:
        assert (got["stop"], f"focus is on {T}" in got["reason"], OTHER in got["reason"],
                RELEASE in got["reason"]) == (True, True, True, True)


def test_guard_refuses_other_ticket_directly(tmp_path):
    root = _focused(tmp_path)

    got = crew_autopilot.focus_guard(str(root), "run", OTHER)

    assert (got is not None, T in (got or ""), RELEASE in (got or "")) == (True, True, True)


def test_guard_refuses_handoff_other_ticket(tmp_path):
    """The real crew_resume (T-0006) parses the handoff's resume: line."""
    root = _focused(tmp_path)
    _handoff(root, f"resume: /crew:autopilot {OTHER}")

    got = crew_autopilot.resume_target(str(root))

    assert (got["ticket"], got["stop"], got["source"], T in got["reason"],
            OTHER in got["reason"], RELEASE in got["reason"]) == (
        None, True, "handoff", True, True, True)


@pytest.mark.parametrize("text", ["assign", f"assign {T}"])
def test_guard_refuses_assign(tmp_path, text):
    root = _focused(tmp_path)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["sub"], got["stop"], f"focus is on {T}" in got["reason"],
            RELEASE in got["reason"]) == ("assign", True, True, True)


@pytest.mark.parametrize("text", ["goal", "--goal", "run --goal ship"])
def test_guard_refuses_goal(tmp_path, text):
    root = _focused(tmp_path)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["stop"], f"focus is on {T}" in got["reason"], RELEASE in got["reason"]) == (
        True, True, True)


def test_guard_refuses_goal_through_first(tmp_path):
    root = _focused(tmp_path)

    got = [crew_autopilot.route(str(root), token) for token in ("goal", "--goal", "assign")]

    assert [(g["stop"], RELEASE in g["reason"]) for g in got] == [(True, True)] * 3


@pytest.mark.parametrize("text,want", [("status", ("status", False)),
                                       (f"status {T}", ("status", False)),
                                       ("focus off", ("focus", False))])
def test_guard_allows_status_and_focus_off(tmp_path, text, want):
    root = _focused(tmp_path)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["sub"], got["stop"]) == want


@pytest.mark.parametrize("text", ["", "run", f"run {T}", T, "assign", "goal", "--goal",
                                  "focus", f"focus {T}"])
def test_guard_broken_pointer_refuses(tmp_path, text):
    root = _two(tmp_path)
    _break(root)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["stop"], "broken" in got["reason"], RELEASE in got["reason"]) == (
        True, True, True)


@pytest.mark.parametrize("text", ["status", "focus off"])
def test_guard_broken_pointer_allows_status_and_focus_off(tmp_path, text):
    root = _two(tmp_path)
    _break(root)

    assert crew_autopilot.route_args(str(root), text)["stop"] is False


def test_guard_index_fallback_is_no_focus(tmp_path):
    """No pointer: INDEX.md's first open ticket (T-1) is what the scope guard
    falls back to, but it is never a focus, so T-2 may be run."""
    root = _two(tmp_path)

    got = crew_autopilot.route_args(str(root), f"run {OTHER}")

    assert (crew_ticket.resolve_active(str(root))[:2], crew_autopilot.focus_state(
        str(root))["focus"], crew_autopilot.focus_guard(str(root), "run", OTHER),
            got["stop"], got["ticket"]) == ((T, ".work/INDEX.md"), None, None, False, OTHER)


def test_guard_unknown_subcommand_is_refused_under_focus(tmp_path):
    root = _focused(tmp_path)

    assert crew_autopilot.focus_guard(str(root), "deploy") is not None


def test_route_focus_off_sets_off_and_no_ticket(tmp_path):
    root = _focused(tmp_path)

    got = crew_autopilot.route_args(str(root), "focus off")
    show = crew_autopilot.route_args(str(root), "focus")

    assert ((got["sub"], got["stop"], got["ticket"], got["off"]),
            (show["sub"], show["stop"], show["ticket"], show["off"])) == (
        ("focus", False, "", True), ("focus", False, "", False))


@pytest.mark.parametrize("text", ["focus Off", "focus off now", "focus --off", "run off"])
def test_route_only_exact_focus_off_releases(tmp_path, text):
    root = _focused(tmp_path)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["stop"], got.get("off", False)) == (True, False)


def test_route_cli_prints_off_only_for_focus(tmp_path, capsys):
    root = _focused(tmp_path)

    lines = []
    for text in ("focus off", "focus", "status"):
        crew_autopilot.main(["route", "--root", str(root), "--args", text])
        lines.append(capsys.readouterr().out.strip())

    assert lines == ["sub=focus stop=0 ticket= off=1 reason=",
                     "sub=focus stop=0 ticket= off=0 reason=",
                     "sub=status stop=0 ticket= reason="]


def test_focus_is_available_and_no_longer_arriving():
    assert ("focus" in crew_autopilot.AVAILABLE, "focus" in crew_autopilot.ARRIVES) == (
        True, False)


# --- step 3: the drift stop, and where findings go -------------------------------

def _approved_focused(tmp_path):
    root = _approved(tmp_path)
    ok, _line = crew_autopilot.focus_set(str(root), T)
    assert ok
    return root


def test_drift_stops_on_path_outside_touch(tmp_path):
    root = _approved_focused(tmp_path)
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")
    before = _snapshot(root)

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"], got["command"], "other/keep.py" in got["reason"],
            _snapshot(root) == before) == ("drift", True, "", True, True)


def test_drift_lists_an_untracked_path_outside_touch(tmp_path):
    root = _approved_focused(tmp_path)
    (root / "notes.txt").write_text("hi\n", encoding="utf-8")

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], "notes.txt" in got["reason"]) == ("drift", True)


def test_drift_passes_inside_touch(tmp_path):
    root = _approved_focused(tmp_path)
    (root / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"]) == ("implement", False)


def test_drift_not_judged_before_approval(tmp_path):
    root = make_repo(tmp_path, mode="off")
    _ticket(root)
    crew_autopilot.focus_set(str(root), T)
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")

    got = crew_autopilot.next_phase(str(root), T)

    assert got["phase"] == "approve"


def test_drift_judged_ahead_of_a_policy_phase(tmp_path):
    """open-questions is a stop the T-0010 policy may answer and go round
    again from, so drift is judged before it."""
    root = _approved_focused(tmp_path)
    _write(root / ".work" / "tickets" / T / "direction.md", "go\n\n## Open questions\n- which db?\n")
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")

    assert crew_autopilot.next_phase(str(root), T)["phase"] == "drift"


def test_drift_audit_exception_stops(tmp_path, monkeypatch):
    import completion_audit  # pylint: disable=import-outside-toplevel
    root = _approved_focused(tmp_path)

    def boom(_root, _ticket):
        raise RuntimeError("git vanished")
    monkeypatch.setattr(completion_audit, "audit", boom)

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"], got["command"], "the audit could not run" in got["reason"],
            "git vanished" in got["reason"]) == ("drift", True, "", True, True)


def test_drift_audit_failure_with_no_lines_still_stops(tmp_path, monkeypatch):
    import completion_audit  # pylint: disable=import-outside-toplevel
    root = _approved_focused(tmp_path)
    monkeypatch.setattr(completion_audit, "audit", lambda _root, _ticket: (False, []))

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"]) == ("drift", True)


def test_drift_cli_prints_a_stop(tmp_path, capsys):
    root = _approved_focused(tmp_path)
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")
    capsys.readouterr()

    crew_autopilot.main(["next", "--root", str(root), "--ticket", T])
    out = capsys.readouterr().out

    assert out.startswith("phase=drift stop=1 command= reason=drift: ")


def test_unfocused_next_unchanged(tmp_path, monkeypatch):
    """No focus (the INDEX fallback names T-1): a path outside Touch is not
    judged, and `next` answers exactly what it answers with no drift check."""
    root = _approved(tmp_path)
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")

    got = crew_autopilot.next_phase(str(root), T)
    monkeypatch.setattr(crew_autopilot, "_drift", lambda *_args: None)
    without = crew_autopilot.next_phase(str(root), T)

    assert (crew_autopilot.focus_state(str(root))["focus"], got["phase"], got["stop"],
            got == without) == (None, "implement", False, True)


def test_status_waits_on_the_owner_at_drift(tmp_path):
    root = _approved_focused(tmp_path)
    (root / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")

    got = crew_autopilot.status(str(root))

    assert (got["phase"], got["waiting"].startswith("owner - reverts")) == ("drift", True)


def test_findings_todo_when_in_touch(tmp_path, capsys):
    root = make_repo(tmp_path, mode="off")
    folder = _ticket(root)
    spec = (folder / "spec.md").read_text(encoding="utf-8")
    _write(folder / "spec.md", spec.replace("- `src/**`", "- `src/**`\n- `TODO.md`"))
    approve_as_user(root, T)

    got = crew_autopilot.findings_target(str(root), T)
    code, out = _cli(root, capsys, "--findings", "--ticket", T)

    assert (got["path"], code, out.splitlines()[0].startswith("findings=TODO.md ")) == (
        "TODO.md", 0, True)


def test_findings_ticket_file_when_not_in_touch(tmp_path, capsys):
    root = _approved(tmp_path)

    got = crew_autopilot.findings_target(str(root), T)
    _code, out = _cli(root, capsys, "--findings", "--ticket", T)

    assert (got["path"], "the scope guard exempts nothing outside Touch" in got["reason"],
            out.splitlines()[0].startswith(f"findings=.work/tickets/{T}/out-of-scope.md ")) == (
        f".work/tickets/{T}/out-of-scope.md", True, True)


def test_findings_ticket_file_when_touch_is_not_approved(tmp_path):
    root = make_repo(tmp_path, mode="off")
    folder = _ticket(root)
    spec = (folder / "spec.md").read_text(encoding="utf-8")
    _write(folder / "spec.md", spec.replace("- `src/**`", "- `src/**`\n- `TODO.md`"))

    assert crew_autopilot.findings_target(str(root), T)["path"] == (
        f".work/tickets/{T}/out-of-scope.md")


# --- step 4: the command, one release site, no new hook -------------------------

def _command():
    with open(_COMMAND, encoding="utf-8") as handle:
        return handle.read()


def _focus_section(text):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(r"^## \d+\. focus\b", line))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
               len(lines))
    return lines[start:end]


def test_focus_section_at_most_6_lines():
    body = _focus_section(_command())[1:]
    while body and not body[-1].strip():
        body.pop()

    assert len(body) <= 6, body


def test_command_still_at_most_120_lines():
    assert len(_command().splitlines()) <= 120


def test_focus_off_named_only_in_focus_section():
    text = _command()
    section = "\n".join(_focus_section(text))
    outside = text.replace(section, "")

    assert ("focus off" in " ".join(section.split()), "focus off" in " ".join(outside.split()),
            "--off" in outside) == (True, False, False)


def test_command_routes_focus_to_its_section_and_the_cli():
    text = " ".join(_command().split())

    assert ("`sub=focus`: section 6 only" in text,
            "crew_autopilot.py focus --root ." in text,
            "`focus --findings --ticket <ticket>`" in text,
            "never fix an out-of-scope finding in the diff" in text.lower(),
            "`drift`" in text) == (True, True, True, True, True)


def _calls_to(tree, attr):
    """[(enclosing function, call)] for every `crew_ticket.<attr>(...)`."""
    found = []
    for func in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == attr and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id == "crew_ticket":
                found.append(func.name)
    return found


def test_deactivate_has_one_call_site():
    with open(_SCRIPT, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source)
    module_level = [n for n in tree.body[1:]
                    if not isinstance(n, (ast.FunctionDef, ast.ClassDef))
                    and "deactivate" in ast.dump(n)]

    assert (_calls_to(tree, "deactivate"), module_level,
            source.count("deactivate(")) == (["focus_off"], [], 1)


def test_focus_off_is_reached_only_from_the_off_flag():
    with open(_SCRIPT, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    callers = sorted({func.name for func in ast.walk(tree) if isinstance(func, ast.FunctionDef)
                      for node in ast.walk(func) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name) and node.func.id == "focus_off"})

    assert callers == ["focus_text"]


def test_hooks_json_registers_no_focus_hook():
    """No new hook (spec Exclusions). Durable form: no hook runs autopilot or
    names focus. The lane-time byte comparison with origin/main is in the PR."""
    with open(_HOOKS, "rb") as handle:
        data = handle.read()

    assert (b"crew_autopilot" in data, b"focus" in data.lower()) == (False, False)
