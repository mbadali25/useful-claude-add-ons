"""The dispatcher words a strict-Git-Bash failure by what was established: a Git Bash that exists
but did not answer is `could not tell` and never says "Install Git for Windows"; only `absent`
does. An armed call is blocked in all three cases (fail-closed is unchanged)."""

import json

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook
import crew_shell


# --- the dispatcher names what it established ------------------------------------------

def _dispatch(problem):
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_input": {"command": "ls"}}).encode()
    return crew_hook.dispatch("PreToolUse", "claude", payload, crew_hook.now_ms() + 20000, {}, "/nowhere",
                              windows=True, resolve_bash=lambda strict=True: (None, problem),
                              armed_fn=lambda _root: True, direct=False)


def test_unknown_blocks_armed_calls_but_never_says_install_git():
    code, _, err = _dispatch(crew_shell.Problem("Git Bash exists but did not answer: x", "unknown"))

    assert code == 2
    assert b"Install Git for Windows" not in err and b"could not tell" in err and b"retry" in err


def test_absent_still_blocks_and_still_says_install_git():
    code, _, err = _dispatch(crew_shell.Problem("Git Bash not found (strict; tried x)", "absent"))

    assert code == 2 and b"Install Git for Windows" in err


def test_broken_blocks_and_names_the_self_test_failure():
    code, _, err = _dispatch(crew_shell.Problem("Git Bash exists but failed its self-test: x", "broken"))

    assert code == 2 and b"self-test" in err and b"Install Git for Windows" not in err
