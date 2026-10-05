"""T-0020: `/crew:autopilot focus` -- a scope lock on one ticket.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_focus.py -q

Focus is explicit (owner decision, 2026-10-05): it is on only once `focus
<id>` writes this worktree's entry in `<git-common-dir>/crew/autopilot-focus.json`
(re-pointing the active ticket through `crew_ticket.activate` when it names
another, which records `.crew/.scope-base`, whose line focus shows); `focus
off` drops the entry and leaves the pointer; `focus` shows it. An active-ticket
pointer alone is never a focus. While focus is set, the router refuses another
ticket, `assign` and `goal`; `sleep` and `wake` always run; a marker that
cannot be read is could-not-tell and refuses as if focused. Once the plan is
approved, `next` runs the completion audit read-only and stops as `drift` on
any changed path outside Touch. Every repository is built under tmp_path; nothing touches the
real one or ~/.claude.
"""
import ast
import json
import os
import re
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_route
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


def _marker(root):
    path = crew_autopilot.focus_path(str(root))
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _corrupt_marker(root, text="{not json"):
    _write(crew_autopilot.focus_path(str(root)), text)


def _remedy_tail(root):
    """What every unknown-marker message ends with: the removal commands for
    the exact path, POSIX and PowerShell."""
    path = crew_autopilot.focus_path(str(root))
    return (f"removing it drops EVERY worktree's focus, not only this one's: rm -- '{path}' "
            f"(POSIX shell) or Remove-Item -LiteralPath '{path}' (PowerShell)")


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


# --- step 1: focus is its own marker, never the active-ticket pointer -----------

def test_focus_set_writes_this_worktree_only(tmp_path):
    root = _two(tmp_path)
    other = tmp_path / "wt2"
    git(root, "worktree", "add", "-q", str(other), "-b", "second")
    _ticket(other, ticket=T)

    ok, line = crew_autopilot.focus_set(str(root), T)

    top = crew_ticket.toplevel(str(root))
    assert (ok, line.startswith(f"focus={T}"), _pointer(root), _marker(root),
            crew_autopilot.focus_state(str(root))["focus"],
            crew_autopilot.focus_state(str(other))["focus"]) == (
        True, True, {top: T}, {top: T}, T, None)


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

    tops = crew_ticket.toplevel(str(root)), crew_ticket.toplevel(str(other))
    assert (ok, line, crew_autopilot.focus_state(str(root))["focus"],
            crew_autopilot.focus_state(str(other))["focus"],
            _marker(root), _pointer(root)) == (
        True, f"focus=none (released {T})", None, OTHER,
        {tops[1]: OTHER}, {tops[0]: T, tops[1]: OTHER})


def test_focus_off_with_nothing_set_says_so(tmp_path):
    root = _two(tmp_path)

    assert crew_autopilot.focus_off(str(root)) == (True, "focus=none (nothing was set)")


def test_focus_off_of_an_unparseable_marker_is_not_read_as_released(tmp_path):
    root = _focused(tmp_path)
    _corrupt_marker(root)

    ok, line = crew_autopilot.focus_off(str(root))

    assert (ok, line.startswith("focus=unknown"), "does not clear" in line,
            line.endswith(_remedy_tail(root)), os.path.isfile(crew_autopilot.focus_path(
                str(root)))) == (False, True, True, True, True)


def test_focus_off_removes_the_marker_and_keeps_the_pointer(tmp_path):
    root = _two(tmp_path)
    crew_ticket.activate(str(root), T)
    before = _crew_state(root)
    crew_autopilot.focus_set(str(root), T)

    ok, _line = crew_autopilot.focus_off(str(root))

    assert (ok, _crew_state(root) == before, os.path.exists(crew_autopilot.focus_path(
        str(root))), _pointer(root)) == (True, True, False, {crew_ticket.toplevel(str(root)): T})


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


def test_focus_show_pointer_alone_is_not_focus(tmp_path):
    root = _two(tmp_path)
    crew_ticket.activate(str(root), T)

    got = crew_autopilot.focus_state(str(root))

    assert (got["pointer"], got["focus"], got["unknown"], _marker(root),
            crew_autopilot.focus_show(str(root))) == (T, None, "", None, (True, "focus=none"))


@pytest.mark.parametrize("text", ["{not json", "[]", json.dumps({"x": 1}).replace("x", "{top}")])
def test_focus_show_unknown_marker(tmp_path, text):
    root = _two(tmp_path)
    top = crew_ticket.toplevel(str(root))
    _corrupt_marker(root, text.replace("{top}", top.replace("\\", "\\\\")))

    ok, line = crew_autopilot.focus_show(str(root))
    got = crew_autopilot.focus_state(str(root))

    assert (ok, line.startswith("focus=unknown "), got["focus"], bool(got["unknown"])) == (
        True, True, None, True)


def test_focus_show_broken_pointer_is_not_focus(tmp_path):
    root = _two(tmp_path)
    _break(root)

    got = crew_autopilot.focus_state(str(root))

    assert (got["broken"], got["focus"], crew_autopilot.focus_show(str(root))) == (
        True, None, (True, "focus=none"))


def test_focus_refuses_to_set_over_a_broken_pointer(tmp_path):
    root = _two(tmp_path)
    _break(root)
    before = _crew_state(root)

    ok, line = crew_autopilot.focus_set(str(root), T)

    assert (ok, "broken" in line, _crew_state(root) == before, _marker(root)) == (
        False, True, True, None)


def test_focus_refuses_to_set_over_an_unknown_marker(tmp_path):
    root = _two(tmp_path)
    _corrupt_marker(root)
    before = _crew_state(root)

    ok, line = crew_autopilot.focus_set(str(root), T)

    assert (ok, "could not be told" in line, _crew_state(root) == before) == (False, True, True)


def test_focus_set_over_a_pointer_on_the_same_ticket_writes_only_the_marker(tmp_path):
    root = _two(tmp_path)
    crew_ticket.activate(str(root), T)
    before = _crew_state(root)
    base = (root / ".crew" / ".scope-base").read_bytes()

    ok, line = crew_autopilot.focus_set(str(root), T)

    after = _crew_state(root)
    assert (ok, sorted(set(after) - set(before)), {p: after[p] for p in before} == before,
            (root / ".crew" / ".scope-base").read_bytes() == base, "->" in line) == (
        True, [crew_autopilot.focus_path(str(root))], True, True, False)


def test_focus_set_re_points_a_pointer_on_another_ticket_and_says_so(tmp_path):
    root = _two(tmp_path)
    crew_ticket.activate(str(root), OTHER)

    ok, line = crew_autopilot.focus_set(str(root), T)

    top = crew_ticket.toplevel(str(root))
    assert (ok, f"active ticket: {OTHER} -> {T}" in line, _pointer(root), _marker(root)) == (
        True, True, {top: T}, {top: T})


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


@pytest.mark.parametrize("sub,ticket", [("run", ""), ("run", T), ("assign", ""), ("goal", ""),
                                        ("focus", "")])
def test_guard_broken_pointer_without_focus_is_no_focus(tmp_path, sub, ticket):
    """A broken pointer is not a focus: the guard says nothing, and `next`'s
    own ticket-mismatch stop is what refuses to drive."""
    root = _two(tmp_path)
    _break(root)

    assert crew_autopilot.focus_guard(str(root), sub, ticket) is None


@pytest.mark.parametrize("text", ["", "run", f"run {T}", T, "assign", "goal", "--goal"])
def test_guard_focus_with_a_pointer_elsewhere_refuses(tmp_path, text):
    """Focused on T-1, then the human re-points the active ticket at T-2:
    nothing may run on either until focus T-1 re-points it or focus off."""
    root = _focused(tmp_path)
    crew_ticket.activate(str(root), OTHER)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["stop"], f"focus is on {T}" in got["reason"], f"names {OTHER}" in got["reason"],
            RELEASE in got["reason"]) == (True, True, True, True)


@pytest.mark.parametrize("text", ["status", "focus off", "focus", f"focus {T}", "sleep", "wake"])
def test_guard_focus_with_a_pointer_elsewhere_allows_release_and_re_point(tmp_path, text):
    root = _focused(tmp_path)
    crew_ticket.activate(str(root), OTHER)

    assert crew_autopilot.route_args(str(root), text)["stop"] is False


@pytest.mark.parametrize("text", ["status", "focus off"])
def test_guard_broken_pointer_allows_status_and_focus_off(tmp_path, text):
    root = _focused(tmp_path)
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


# --- explicit focus (owner decision, 2026-10-05) -------------------------------
# A pointer alone is not focus, so plain text that main's router (T-0057,
# L-0662) sends to assign, goal, wave or split still goes there.

_LATER = ("wave", "split")
_PLAIN = [("take care of the login audit", "/crew:autopilot assign the login audit"),
          ("work toward zero flaky tests", "/crew:autopilot goal zero flaky tests"),
          ("run T-1 and T-2 in parallel", "/crew:autopilot wave T-1 T-2"),
          ("split it", "/crew:autopilot split T-1"),
          ("T-1 is too big", "/crew:autopilot split T-1")]


def _live(monkeypatch):
    """Every subcommand available, wave and split known: as each lands."""
    subs = tuple(crew_autopilot.SUBCOMMANDS) + _LATER
    monkeypatch.setattr(crew_autopilot, "SUBCOMMANDS", subs)
    monkeypatch.setattr(crew_autopilot, "AVAILABLE", frozenset(subs))


def _pointed(tmp_path):
    """T-1 and T-2, the active-ticket pointer on T-1, and no focus."""
    root = _two(tmp_path)
    crew_ticket.activate(str(root), T)
    return root


@pytest.mark.parametrize("prompt,command", _PLAIN)
def test_plain_text_routes_with_a_pointer_and_no_focus(tmp_path, monkeypatch, prompt, command):
    root = _pointed(tmp_path)
    _live(monkeypatch)

    got = crew_route.decide(str(root), prompt)

    assert (crew_autopilot.focus_state(str(root))["pointer"], got["outcome"],
            got["command"], got["unavailable"]) == (T, "route", command, False)


@pytest.mark.parametrize("sub", ["assign", "goal", "wave", "split", "deploy"])
def test_route_with_a_pointer_and_no_focus_is_mains_answer(tmp_path, sub):
    """Today's AVAILABLE: assign and goal stop as arriving, an unknown name as
    unknown -- never as focus."""
    root = _pointed(tmp_path)

    got = crew_autopilot.route(str(root), sub)

    assert (crew_autopilot.focus_guard(str(root), sub), "focus is on" in got["reason"],
            "arrives with" in got["reason"] or got["reason"] == crew_autopilot.UNKNOWN_SUB) == (
        None, False, True)


@pytest.mark.parametrize("prompt,command", _PLAIN)
def test_plain_text_under_focus_asks_with_the_focus_refusal(tmp_path, monkeypatch, prompt,
                                                           command):
    root = _focused(tmp_path)
    _live(monkeypatch)

    got = crew_route.decide(str(root), prompt)

    assert (got["outcome"], got["command"], f"focus is on {T}" in got["reason"],
            command.split(" ", 2)[1] in got["reason"], RELEASE in got["reason"]) == (
        "ask", None, True, True, True)


def test_plain_text_focus_on_routes_now_that_focus_is_available(tmp_path):
    root = _pointed(tmp_path)

    got = crew_route.decide(str(root), "focus on T-2")

    assert (got["outcome"], got["command"], got["ticket"]) == (
        "route", "/crew:autopilot focus T-2", OTHER)


@pytest.mark.parametrize("text", [f"run {OTHER}", OTHER, "assign", "goal", f"focus {OTHER}"])
def test_focus_then_off_restores_the_unfocused_answer(tmp_path, text):
    root = _pointed(tmp_path)
    unfocused = crew_autopilot.route_args(str(root), text)
    crew_autopilot.focus_set(str(root), T)
    focused = crew_autopilot.route_args(str(root), text)
    crew_autopilot.focus_off(str(root))

    assert (focused["stop"], f"focus is on {T}" in focused["reason"],
            crew_autopilot.route_args(str(root), text)) == (True, True, unfocused)


@pytest.mark.parametrize("state", ["none", "pointer", "focused", "unknown"])
@pytest.mark.parametrize("text", ["sleep", "wake"])
def test_sleep_and_wake_always_route(tmp_path, state, text):
    root = _two(tmp_path)
    if state == "pointer":
        crew_ticket.activate(str(root), T)
    elif state == "focused":
        crew_autopilot.focus_set(str(root), T)
    elif state == "unknown":
        _corrupt_marker(root)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["sub"], got["stop"], crew_autopilot.focus_guard(str(root), text)) == (
        text, False, None)


@pytest.mark.parametrize("text", ["", "run", f"run {T}", T, f"run {OTHER}", "assign", "goal",
                                  "--goal", "focus", f"focus {T}"])
def test_unknown_marker_refuses_start_and_switch(tmp_path, text):
    """Could-not-tell is its own value: the marker cannot be read, so whether
    focus is on cannot be told, and nothing may start or switch work."""
    root = _pointed(tmp_path)
    _corrupt_marker(root)

    got = crew_autopilot.route_args(str(root), text)

    assert (got["stop"], "could not be told" in got["reason"], RELEASE in got["reason"],
            got["reason"].endswith(_remedy_tail(root))) == (True, True, False, True)


@pytest.mark.parametrize("text", ["status", "focus off", "sleep", "wake"])
def test_unknown_marker_allows_status_release_sleep_and_wake(tmp_path, text):
    root = _pointed(tmp_path)
    _corrupt_marker(root)

    assert crew_autopilot.route_args(str(root), text)["stop"] is False


def test_unknown_marker_entry_that_is_not_an_id_refuses(tmp_path):
    root = _pointed(tmp_path)
    _write(crew_autopilot.focus_path(str(root)),
           json.dumps({crew_ticket.toplevel(str(root)): "../etc"}))

    got = crew_autopilot.focus_guard(str(root), "run", OTHER)

    assert "could not be told" in (got or "")


def test_unknown_marker_entry_bogus_is_unknown_not_a_focus(tmp_path):
    """N1: `bogus` passes crew_ticket's id shape but is neither INDEX-shaped
    nor a ticket folder, so it is unknown, never focus=bogus."""
    root = _pointed(tmp_path)
    _write(crew_autopilot.focus_path(str(root)),
           json.dumps({crew_ticket.toplevel(str(root)): "bogus"}))

    got = crew_autopilot.focus_state(str(root))

    assert (got["focus"], "'bogus', not a ticket" in got["unknown"],
            crew_autopilot.focus_show(str(root))[1].startswith("focus=unknown ")) == (
        None, True, True)


def test_marker_entry_naming_a_ticket_folder_is_a_focus(tmp_path):
    """A non-INDEX-shaped id with a `.work/tickets/` folder is a ticket, as
    `route` reads one."""
    root = _two(tmp_path)
    _ticket(root, ticket="hotfix")

    ok, _line = crew_autopilot.focus_set(str(root), "hotfix")

    assert (ok, crew_autopilot.focus_state(str(root))["focus"]) == (True, "hotfix")


def test_a_directory_marker_is_not_a_file(tmp_path):
    root = _pointed(tmp_path)
    os.makedirs(crew_autopilot.focus_path(str(root)))

    got = crew_autopilot.focus_state(str(root))
    off_ok, off_line = crew_autopilot.focus_off(str(root))

    assert ("is not a file" in got["unknown"], "does not parse" in got["unknown"],
            got["unknown"].endswith(_remedy_tail(root)), off_ok,
            off_line.endswith(_remedy_tail(root)),
            os.path.isdir(crew_autopilot.focus_path(str(root)))) == (
        True, False, True, False, True, True)


@pytest.mark.parametrize("call", ["show", "set", "off", "guard", "drift"])
def test_every_unknown_message_ends_with_the_removal_commands(tmp_path, call):
    root = _approved(tmp_path) if call == "drift" else _pointed(tmp_path)
    _corrupt_marker(root)

    line = {"show": lambda: crew_autopilot.focus_show(str(root))[1],
            "set": lambda: crew_autopilot.focus_set(str(root), OTHER)[1],
            "off": lambda: crew_autopilot.focus_off(str(root))[1],
            "guard": lambda: crew_autopilot.focus_guard(str(root), "run", OTHER),
            "drift": lambda: crew_autopilot.next_phase(str(root), T)["reason"]}[call]()

    assert (line.endswith(_remedy_tail(root)), RELEASE in line) == (True, False)


_PASTE_TABLE = ["/r/a b/autopilot-focus.json", "/r/it's/autopilot-focus.json",
                "/r/-dash/autopilot-focus.json", "/r/$(echo pwn)`id`/autopilot-focus.json",
                "/r/\u00fcn\u00ef\u2019c\u00f8d\u00e9/autopilot-focus.json",
                "/r/two  spaces/autopilot-focus.json", "/r/tab\there/autopilot-focus.json",
                "/r/new\nline/autopilot-focus.json", "/r/\u2018q\u201b/autopilot-focus.json"]


@pytest.mark.parametrize("path", _PASTE_TABLE)
def test_printed_removal_names_exactly_the_path_or_no_command(path):
    """F1-b: what `focus` prints (one line, through `_one_line`) either holds
    an rm that parses back to exactly the path, or no command and the path as
    JSON that loads back to it."""
    import shlex  # pylint: disable=import-outside-toplevel
    printed = crew_autopilot._one_line(crew_autopilot._focus_remedy(path))  # pylint: disable=protected-access

    if "rm -- " in printed:
        rm_part = printed[printed.index("rm -- "):printed.index(" (POSIX shell)")]
        ps_part = printed[printed.index("Remove-Item -LiteralPath "):printed.index(" (PowerShell)")]
        assert (shlex.split(rm_part), ps_part) == (
            ["rm", "--", path], "Remove-Item -LiteralPath '" + path.replace("'", "''") + "'")
    else:
        shown = printed[printed.index("remove this file by hand: ") + 26:]
        assert ("Remove-Item" in printed, json.loads(shown)) == (False, path)


@pytest.mark.parametrize("path,commands", [("/r/a b/autopilot-focus.json", True),
                                           ("/r/two  spaces/autopilot-focus.json", False),
                                           ("/r/new\nline/autopilot-focus.json", False),
                                           ("/r/\u00fcn\u00ef\u2019c/autopilot-focus.json", False),
                                           ("/r/c1\x9bctl/autopilot-focus.json", False),
                                           ("/r/bidi\u202eevil/autopilot-focus.json", False)])
def test_commands_are_printed_only_for_a_paste_safe_path(path, commands):
    assert ("rm -- " in crew_autopilot._focus_remedy(path)) is commands  # pylint: disable=protected-access


def test_powershell_quoting_doubles_the_curly_single_quotes_too():
    assert crew_autopilot._ps_quoted("a\u2018b\u2019c'd") == "'a\u2018\u2018b\u2019\u2019c''d'"  # pylint: disable=protected-access


def test_a_stale_lock_names_a_paste_ready_removal(tmp_path, monkeypatch):
    """A crash mid-write leaves the lock; the refusal says how to remove it."""
    root = _two(tmp_path)
    monkeypatch.setattr(crew_autopilot, "FOCUS_LOCK_WAIT", 0.2)
    path = crew_autopilot.focus_path(str(root))
    _write(path + ".lock", "99999")

    _ok, line = crew_autopilot.focus_off(str(root))

    assert ("99999" in line, f"rm -- '{path}.lock' (POSIX shell)" in line,
            f"Remove-Item -LiteralPath '{path}.lock' (PowerShell)" in line) == (True, True, True)


def test_removal_commands_quote_an_apostrophe_in_the_path():
    remedy = crew_autopilot._focus_remedy("/tmp/it's/autopilot-focus.json")  # pylint: disable=protected-access

    assert ("rm -- '/tmp/it'\\''s/autopilot-focus.json'" in remedy,
            "Remove-Item -LiteralPath '/tmp/it''s/autopilot-focus.json'" in remedy) == (True, True)


_RACER = """
import sys, time
sys.path.insert(0, sys.argv[1])
import crew_autopilot
delay = float(sys.argv[4])
if delay:
    real = crew_autopilot._write_marker
    def slow(path, mapping):
        open(sys.argv[5], "w").close()  # read done, write not yet: the window is open
        time.sleep(delay)
        real(path, mapping)
    crew_autopilot._write_marker = slow
if sys.argv[3] == "off":
    ok, line = crew_autopilot.focus_off(sys.argv[2])
else:
    ok, line = crew_autopilot.focus_set(sys.argv[2], sys.argv[3])
print(line.splitlines()[0])
sys.exit(0 if ok else 1)
"""


def _race(root, delay, sentinel, what=T):
    return subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, "-B", "-c", _RACER, os.path.dirname(crew_autopilot.__file__),
         str(root), what, str(delay), str(sentinel)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


@pytest.mark.parametrize("slow_does", [T, "off"])
def test_two_worktrees_writing_the_marker_at_once_lose_nothing(tmp_path, slow_does):
    """F2: worktree A reads the marker and stalls before writing (a `focus T-1`,
    or a `focus off` of its earlier focus); B runs `focus T-1` meanwhile.
    Without the lock A's write drops B's entry while B reports success. With
    it, B waits, then writes on top of A's result."""
    root = _two(tmp_path)
    other = tmp_path / "wt2"
    git(root, "worktree", "add", "-q", str(other), "-b", "second")
    _ticket(other, ticket=T)
    tops = crew_ticket.toplevel(str(root)), crew_ticket.toplevel(str(other))
    if slow_does == "off":
        assert crew_autopilot.focus_set(str(root), T)[0]

    sentinel = tmp_path / "a-has-read"
    slow = _race(root, 1.5, sentinel, slow_does)
    deadline = time.monotonic() + 60
    while not sentinel.exists() and slow.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert sentinel.exists(), slow.communicate()
    fast = _race(other, 0, sentinel)
    results = [(proc.wait(timeout=60), proc.communicate()) for proc in (slow, fast)]

    for code, (out, err) in results:
        assert (code, err) == (0, ""), out
    assert _marker(root) == ({tops[1]: T} if slow_does == "off" else {tops[0]: T, tops[1]: T})


def test_focus_refuses_when_the_marker_lock_is_held(tmp_path, monkeypatch):
    root = _two(tmp_path)
    monkeypatch.setattr(crew_autopilot, "FOCUS_LOCK_WAIT", 0.2)
    path = crew_autopilot.focus_path(str(root))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _write(path + ".lock", "99999")
    before = _crew_state(root)

    set_ok, set_line = crew_autopilot.focus_set(str(root), T)
    off_ok, off_line = crew_autopilot.focus_off(str(root))

    assert (set_ok, set_line.startswith("refused: the focus marker's lock"),
            "nothing written" in set_line, off_ok, "could not be taken" in off_line,
            _crew_state(root) == before, _marker(root)) == (
        False, True, True, False, True, True, None)


def test_unknown_marker_stops_next_as_drift(tmp_path):
    root = _approved(tmp_path)
    _corrupt_marker(root)

    got = crew_autopilot.next_phase(str(root), T)

    assert (got["phase"], got["stop"], "could not be told" in got["reason"]) == (
        "drift", True, True)


def test_unknown_marker_in_another_worktree_does_not_unlock_this_one(tmp_path):
    """The marker is one file for every worktree: unreadable, it is unknown
    for all of them, never an absent entry."""
    root = _focused(tmp_path)
    other = tmp_path / "wt2"
    git(root, "worktree", "add", "-q", str(other), "-b", "second")
    _corrupt_marker(other)

    assert (crew_autopilot.focus_state(str(root))["focus"],
            bool(crew_autopilot.focus_state(str(root))["unknown"])) == (None, True)


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
            "Focus is on only once `focus <ticket>` sets it, never from the active ticket "
            "alone" in text,
            "crew_autopilot.py focus --root ." in text,
            "`focus --findings --ticket <ticket>`" in text,
            "never fix an out-of-scope finding in the diff" in text.lower(),
            "`drift`" in text) == (True, True, True, True, True, True)


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


def test_focus_never_deactivates_and_activates_only_from_focus_set():
    """Explicit focus: `focus off` drops the marker, never the pointer, so the
    module calls `crew_ticket.deactivate` nowhere; `activate` only from
    `focus_set`, the re-point."""
    with open(_SCRIPT, encoding="utf-8") as handle:
        source = handle.read()
    tree = ast.parse(source)

    assert (_calls_to(tree, "deactivate"), source.count("deactivate("),
            _calls_to(tree, "activate")) == ([], 0, ["focus_set"])


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
