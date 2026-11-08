"""Faults fail closed in an armed repo, and only there (L-0727, A7, B8).

The launchers supervise `crew_hook.py` instead of handing the process over, so
a crash before `main` runs (an import or syntax error), an exception in `main`,
a hook script that is gone, a guard past its timeout, a stdin that never closes
and a python probe that eats the deadline are all caught. In an ARMED repo
(own config, a linked worktree inheriting the main checkout's, or only the
machine-global config) each is exit 2 with a named reason on PreToolUse; in an
unarmed repo each is exit 0, as the scripts behave today.

Every case drives the REAL launcher on a temp COPY of hooks/scripts, so a fault
can be planted without touching the real files. The PowerShell launcher runs
under pwsh with `OS=Windows_NT` on a POSIX host (the slow flavour).
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook
import crew_hook_harness as h
import record_golden_hooks as rgh

BASH_PAYLOAD = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                           "tool_input": {"command": "ls"}, "session_id": "s-1"}).encode()
CONFIGS = ("own", "inherited", "global")


def _copy_scripts(tmp_path):
    """A copy of the plugin (its scripts import siblings in skills/), without the suites."""
    plugin = os.path.dirname(os.path.dirname(h.SCRIPTS))
    dest = tmp_path / "crew"
    shutil.copytree(plugin, dest, ignore=shutil.ignore_patterns("tests", "_test", "evals", "docs", "__pycache__"))
    return str(dest / "hooks" / "scripts")


def _repo(tmp_path, config):
    """(root, home) for one of: own, inherited (a linked worktree of an armed repo),
    global (no repo config; the machine-global config file), none (nothing)."""
    base = str(tmp_path)
    if config == "own":
        return rgh.build_repo(base, True)
    if config == "inherited":
        main, home = rgh.build_repo(base, True)
        linked = os.path.join(base, "linked")
        subprocess.run(["git", "worktree", "add", "-q", "-b", "linked", linked], cwd=main, check=True,
                       capture_output=True)
        return linked, home
    root, home = rgh.build_repo(base, False)
    if config == "global":
        os.makedirs(os.path.join(home, ".claude", "crew"), exist_ok=True)
        with open(os.path.join(home, ".claude", "crew", "config.json"), "w", encoding="utf-8") as handle:
            handle.write("{}")
    return root, home


def _run(flavour, scripts, event, data, root, home, env_extra=None, path=None, timeout=60):
    env = rgh.env_for(root, home, path=path)
    env["CLAUDE_PLUGIN_ROOT"] = os.path.dirname(os.path.dirname(scripts))
    env.update(env_extra or {})
    if flavour == "ps1":
        argv = [h.PWSH or "pwsh", "-NoProfile", "-File", os.path.join(scripts, "crew-hook.ps1"), event]
        if not h.WINDOWS:
            env["OS"] = "Windows_NT"
    else:
        argv = [h.BASH or "bash", os.path.join(scripts, "crew-hook.sh"), event]
    done = subprocess.run(argv, input=data, capture_output=True, env=env, cwd=root, timeout=timeout, check=False)
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


PS1_STARTUP = 8.0  # seconds a loaded runner may need to start pwsh, python and the dispatcher


def _deadline(seconds, flavour="sh"):
    """The inherited deadline, `seconds` from now; the PowerShell launcher is given its start-up on top."""
    seconds += PS1_STARTUP if flavour == "ps1" else 0
    return {"CREW_HOOK_DEADLINE": str(int(time.time() * 1000) + int(seconds * 1000))}


def _edit(scripts, name, old, new):
    path = os.path.join(scripts, name)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    assert old in text, f"{old!r} not in {name}"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(old, new, 1))


def _plant_exception(scripts):
    _edit(scripts, "crew_hook.py", 'if __name__ == "__main__":',
          'def _boom(*args, **kwargs):\n    raise RuntimeError("boom")\n\n\ndispatch = _boom\n\n\n'
          'if __name__ == "__main__":')


def _plant_syntax_error(scripts):
    _edit(scripts, "crew_hook.py", "import json\n", "import json\ndef (:\n")


def _plant_hang_before_main(scripts):
    _edit(scripts, "crew_hook.py", "import json\n", "import json\nimport time as _t\n_t.sleep(120)\n")


def _plant_missing_script(scripts):
    os.remove(os.path.join(scripts, "scope-guard.sh"))


def _plant_slow_guard(scripts):
    with open(os.path.join(scripts, "scope-guard.sh"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("#!/usr/bin/env bash\nsleep 30\n")


# On a loaded runner the python probe can exhaust the whole deadline during startup,
# before the planted fault is reached; the hook still fails closed (exit 2) with this reason.
_WHOLE_DEADLINE = "the python probe used the whole deadline"

FAULTS = {
    "exception-in-main": (_plant_exception, "dispatcher error RuntimeError: boom", lambda flavour: {}),
    "syntax-error-before-main": (_plant_syntax_error, "crew_hook.py failed (exit 1)", lambda flavour: {}),
    "table-script-missing": (_plant_missing_script, "scope-guard.sh is missing", lambda flavour: {}),
    "guard-past-its-timeout": (_plant_slow_guard, ("scope-guard.sh timed out", "ran past the deadline", "failed (exit", _WHOLE_DEADLINE),
                               lambda flavour: _deadline(2.5, flavour)),
    "dispatcher-hangs-before-main": (_plant_hang_before_main, ("failed (exit 137)", "ran past the deadline", _WHOLE_DEADLINE),
                                     lambda flavour: _deadline(2.0, flavour)),
}

needs_runner = pytest.mark.skipif(h.BASH is None and not h.WINDOWS, reason="no bash - the launcher was NOT run")


def test_control_an_unplanted_copy_allows_a_plain_command(tmp_path):
    scripts = _copy_scripts(tmp_path)
    root, home = _repo(tmp_path, "own")

    code, out, err = _run(h.FLAVOURS[0], scripts, "PreToolUse", BASH_PAYLOAD, root, home)

    assert code == 0, err
    assert out == ""


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
@pytest.mark.parametrize("config", CONFIGS)
@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_a_fault_in_an_armed_repo_is_exit_2_naming_the_cause(fault, config, flavour, tmp_path):
    plant, reason, extra = FAULTS[fault]
    scripts = _copy_scripts(tmp_path)
    plant(scripts)
    root, home = _repo(tmp_path, config)

    code, _, err = _run(flavour, scripts, "PreToolUse", BASH_PAYLOAD, root, home, env_extra=extra(flavour))

    assert code == 2, err
    assert any(part in err for part in ((reason,) if isinstance(reason, str) else reason)), err


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_the_same_fault_in_an_unarmed_repo_is_exit_0(fault, flavour, tmp_path):
    plant, _, extra = FAULTS[fault]
    scripts = _copy_scripts(tmp_path)
    plant(scripts)
    root, home = _repo(tmp_path, "none")

    code, _, err = _run(flavour, scripts, "PreToolUse", BASH_PAYLOAD, root, home, env_extra=extra(flavour))

    assert code == 0, err


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
@pytest.mark.parametrize("config,armed", [("own", True), ("inherited", True), ("global", True), ("none", False)])
def test_a_stdin_that_never_closes_is_a_fault_not_a_hang(config, armed, flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    root, home = _repo(tmp_path, config)
    env = rgh.env_for(root, home)
    env.update(_deadline(2.5, flavour))
    env["CLAUDE_PLUGIN_ROOT"] = os.path.dirname(os.path.dirname(scripts))
    if flavour == "ps1":
        env["OS"] = "Windows_NT"
        argv = [h.PWSH or "pwsh", "-NoProfile", "-File", os.path.join(scripts, "crew-hook.ps1"), "PreToolUse"]
    else:
        argv = [h.BASH or "bash", os.path.join(scripts, "crew-hook.sh"), "PreToolUse"]
    started = time.monotonic()
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,  # pylint: disable=consider-using-with
                            env=env, cwd=root)
    try:
        proc.stdin.write(b'{"tool_name": "Bash"')
        proc.stdin.flush()
        code = proc.wait(timeout=30)
        err = proc.stderr.read().decode("utf-8", "replace")
    finally:
        proc.kill()
        proc.communicate()

    assert code == (2 if armed else 0), err
    assert time.monotonic() - started < 25
    assert "stdin did not close before the deadline" in err


def _slow_python_dir(tmp_path):
    """A PATH directory whose python3 takes longer than the whole deadline to answer."""
    stub = tmp_path / "slowbin"
    stub.mkdir()
    real = os.path.realpath(sys.executable)
    (stub / "python3").write_text(f'#!/bin/sh\nsleep 2.4\nexec "{real}" "$@"\n', encoding="utf-8")
    (stub / "python3").chmod(0o755)
    base = rgh.no_python_path(str(tmp_path))
    return f"{stub}{os.pathsep}{base}"


@needs_runner
@pytest.mark.skipif(h.WINDOWS, reason="a POSIX shell stub models the slow probe")
@pytest.mark.parametrize("config,armed", [("own", True), ("global", True), ("none", False)])
def test_a_python_probe_that_eats_the_deadline_is_a_fault_not_an_allow(config, armed, tmp_path):
    scripts = _copy_scripts(tmp_path)
    root, home = _repo(tmp_path, config)

    code, _, err = _run("sh", scripts, "PreToolUse", BASH_PAYLOAD, root, home, env_extra=_deadline(2.0),
                        path=_slow_python_dir(tmp_path), timeout=60)

    assert code == (2 if armed else 0), err


@needs_runner
@pytest.mark.skipif(h.WINDOWS, reason="the no-python POSIX path is not a Windows path (B10)")
@pytest.mark.parametrize("config,armed", [("own", True), ("inherited", True), ("none", False)])
def test_with_no_python_the_scripts_own_fallbacks_decide(config, armed, tmp_path):
    scripts = _copy_scripts(tmp_path)
    root, home = _repo(tmp_path, config)
    path = rgh.no_python_path(str(tmp_path))

    code, _, err = _run("sh", scripts, "PreToolUse", BASH_PAYLOAD, root, home, path=path)

    assert code == (2 if armed else 0), err


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
def test_a_child_printing_malformed_json_is_passed_on_as_plain_text(flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    with open(os.path.join(scripts, "notify.sh"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("#!/usr/bin/env bash\ncat >/dev/null\necho '{not json'\n")
    root, home = _repo(tmp_path, "own")
    data = json.dumps({"hook_event_name": "Notification", "message": "x"}).encode()

    code, out, err = _run(flavour, scripts, "Notification", data, root, home)

    assert code == 0, err
    assert out.strip() == "{not json"


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
@pytest.mark.parametrize("event", ["SessionStart", "PostToolUse", "Notification", "PreCompact", "SubagentStart"])
def test_a_fault_on_an_event_that_cannot_block_is_exit_0_even_when_armed(event, flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    _plant_exception(scripts)
    root, home = _repo(tmp_path, "own")
    data = json.dumps({"hook_event_name": event, "tool_name": "Read", "tool_input": {}}).encode()

    code, _, err = _run(flavour, scripts, event, data, root, home)

    assert code == 0, err


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
@pytest.mark.parametrize("event", ["UserPromptSubmit", "Stop"])
def test_user_prompt_submit_and_stop_fail_closed_when_armed(event, flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    _plant_exception(scripts)
    root, home = _repo(tmp_path, "own")
    data = json.dumps({"hook_event_name": event, "prompt": "hi", "session_id": "s-1"}).encode()

    code, _, err = _run(flavour, scripts, event, data, root, home)

    assert code == 2, err


def test_every_blocking_event_is_one_where_a_child_can_block():
    can_block = {row.event for row in crew_hook.TABLE if row.guard}

    assert can_block == set(crew_hook.BLOCKING_EVENTS)


# --- armed(): the dispatcher's answer, and the launchers' superset of it -------

def _scenarios(tmp_path):
    """name -> (root, home) for each way a repo can be governed or not."""
    out = {}
    for name in ("own", "inherited", "global", "none"):
        sub = tmp_path / name
        sub.mkdir()
        out[name] = _repo(sub, name)
    return out


def test_armed_is_true_for_own_inherited_and_global_config_and_false_for_none(tmp_path):
    scenarios = _scenarios(tmp_path)

    got = {name: crew_hook.armed(root, home=home) for name, (root, home) in scenarios.items()}

    assert got == {"own": True, "inherited": True, "global": True, "none": False}


def test_armed_is_true_when_the_resolution_fails_or_cannot_tell(tmp_path, monkeypatch):
    import crew_common  # pylint: disable=import-outside-toplevel
    root, home = _repo(tmp_path, "none")

    def boom(_root):
        raise OSError("cannot stat")

    monkeypatch.setattr(crew_common, "repo_config_dir", boom)
    failed = crew_hook.armed(root, home=home)
    monkeypatch.setattr(crew_common, "repo_config_dir",
                        lambda _root: (os.path.join(root, ".crew"), crew_common.SOURCE_UNKNOWN, "git failed"))

    assert failed is True
    assert crew_hook.armed(root, home=home) is True


def _launcher_armed(flavour, root, home, project_dir=None):
    """Run the launcher's own armed check, extracted from the file, in the same environment."""
    env = rgh.env_for(root, home)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = project_dir
    if flavour == "sh":
        text = h.read_text(h.SH)
        body = text[text.index("# Exists, or cannot be told"):text.index("_fail() {")]
        done = subprocess.run([h.BASH, "-c", f"EVENT=PreToolUse\n{body}\n_armed\necho $?\n"],
                              capture_output=True, text=True, env=env, cwd=root, check=True)
        return done.stdout.strip() == "0"
    text = h.read_text(h.PS1)
    body = text[text.index("# True when the path is there, or cannot be told"):text.index("function Exit-Fault")]
    env["OS"] = "Windows_NT"
    done = subprocess.run([h.PWSH, "-NoProfile", "-Command",
                           body + "\nif (Test-CrewArmed) { 'armed' } else { 'unarmed' }"],
                          capture_output=True, text=True, env=env, cwd=root, check=True)
    return done.stdout.strip() == "armed"


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
def test_the_launcher_check_calls_armed_every_case_armed_calls_armed(flavour, tmp_path):
    if flavour == "ps1" and h.PWSH is None:
        pytest.skip("pwsh not installed - the ps1 armed check was NOT run")
    scenarios = _scenarios(tmp_path)
    scenarios["linked-git-file"] = scenarios["inherited"]

    for name, (root, home) in scenarios.items():
        want = crew_hook.armed(root, home=home)
        got = _launcher_armed(flavour, root, home)
        assert got or not want, f"{name}: armed() says armed but the {flavour} launcher check says not"
        if name == "none":
            assert not got


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
def test_the_launcher_check_is_armed_for_a_missing_project_directory(flavour, tmp_path):
    if flavour == "ps1" and h.PWSH is None:
        pytest.skip("pwsh not installed - the ps1 armed check was NOT run")
    root, home = _repo(tmp_path, "none")

    got = _launcher_armed(flavour, root, home, project_dir=os.path.join(str(tmp_path), "gone"))

    assert got is True


@needs_runner
@pytest.mark.skipif(h.WINDOWS, reason="symlinks need privileges on Windows")
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
def test_a_dangling_symlink_config_counts_as_present_for_both_checks(flavour, tmp_path):
    if flavour == "ps1" and h.PWSH is None:
        pytest.skip("pwsh not installed - the ps1 armed check was NOT run")
    root, home = _repo(tmp_path, "none")
    os.makedirs(os.path.join(root, ".crew"), exist_ok=True)
    os.symlink(os.path.join(str(tmp_path), "elsewhere.json"), os.path.join(root, ".crew", "config.json"))

    assert crew_hook.armed(root, home=home) is True
    assert _launcher_armed(flavour, root, home) is True


def test_run_child_forwards_stdin_bytes_exactly():
    raw = b'\xef\xbb\xbf{"x": "caf\xc3\xa9"}\r\n\xff\xfe'
    echo = "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"

    result = crew_hook.run_child([sys.executable, "-c", echo], raw, 30, dict(os.environ))

    assert result["exit"] == 0 and result["stdout"] == raw


def test_a_stdin_larger_than_the_bound_is_a_problem_not_a_truncation():
    big = io.BytesIO(b"x" * (crew_hook.MAX_STDIN + 1))

    data, problem = crew_hook.read_stdin(big, crew_hook.now_ms() + 30000)

    assert "larger than" in problem and len(data) <= crew_hook.MAX_STDIN


@pytest.mark.skipif(h.BASH is None, reason="no working bash - the child was NOT run")
def test_a_child_that_backgrounds_work_holding_its_pipes_does_not_hold_the_dispatcher_up():
    script = "sleep 20 & echo started"

    started = time.monotonic()
    result = crew_hook.run_child([h.BASH, "-c", script], b"", 30, dict(os.environ))

    assert result["exit"] == 0 and result["stdout"].strip() == b"started"
    assert time.monotonic() - started < 10


# --- security pass (L-0850): an undecided guard, the no-python deadline, the trace file -----------

def _plant_guard_exits(code):
    def plant(scripts):
        with open(os.path.join(scripts, "scope-guard.sh"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"#!/usr/bin/env bash\ncat >/dev/null\nexit {code}\n")
    return plant


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
@pytest.mark.parametrize("config", CONFIGS)
@pytest.mark.parametrize("code", [1, 127])
def test_a_guard_that_exits_without_a_decision_is_a_fault_when_armed(code, config, flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    _plant_guard_exits(code)(scripts)
    root, home = _repo(tmp_path, config)

    got, out, err = _run(flavour, scripts, "PreToolUse", BASH_PAYLOAD, root, home)

    assert got == 2, err
    assert f"scope-guard.sh exited {code} without a decision" in err and out == ""


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
def test_a_guard_that_exits_without_a_decision_is_a_note_when_unarmed(flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    _plant_guard_exits(1)(scripts)
    root, home = _repo(tmp_path, "none")

    got, _, err = _run(flavour, scripts, "PreToolUse", BASH_PAYLOAD, root, home)

    assert got == 0, err


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
def test_a_crashed_guard_is_not_retried_with_an_empty_payload(flavour, tmp_path):
    """The security pass's BLOCK 2: a child's exit 1 used to come back from the dispatcher as exit 1,
    which the launcher took for 'the interpreter failed' and retried with the stdin it had already
    consumed, so every row ran on an empty payload and the guard fault became an allow."""
    scripts = _copy_scripts(tmp_path)
    _plant_guard_exits(1)(scripts)
    trace = tmp_path / "ran.crew-trace"
    root, home = _repo(tmp_path, "own")

    got, _, err = _run(flavour, scripts, "PreToolUse", BASH_PAYLOAD, root, home,
                       env_extra={"CREW_HOOK_TRACE_FILE": str(trace)})

    lines = h.read_text(str(trace)).splitlines()
    assert got == 2, err
    assert sum(1 for line in lines if "scope-guard.sh" in line) == 1, lines


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
def test_a_non_guard_row_that_crashes_does_not_block_even_when_armed(flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    with open(os.path.join(scripts, "crew-context.sh"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("#!/usr/bin/env bash\ncat >/dev/null\necho context-crashed >&2\nexit 1\n")
    root, home = _repo(tmp_path, "own")
    data = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "hi", "session_id": "s-1"}).encode()

    got, _, err = _run(flavour, scripts, "UserPromptSubmit", data, root, home)

    assert got == 0, err
    assert "context-crashed" in err


def test_settle_gives_exit_2_or_0_whatever_the_children_exited():
    row_guard = crew_hook.TABLE[crew_hook.TABLE.index(next(r for r in crew_hook.TABLE if r.script == "scope-guard.sh"))]
    row_soft = next(r for r in crew_hook.TABLE if r.script == "crew-context.sh" and r.event == "UserPromptSubmit")

    def settle(row, code, armed):
        result = {"exit": code, "stdout": b"", "stderr": b"x\n", "timed_out": False, "error": "", "pid": 1}
        return crew_hook._settle(row.event, [(row, [row.script])], [result], "/r", lambda _root: armed)[0]  # pylint: disable=protected-access

    seen = {(code, armed): settle(row_guard, code, armed) for code in (1, 3, 127, 137, -9) for armed in (True, False)}
    soft = {settle(row_soft, code, True) for code in (1, 3, 127, 137, -9)}

    assert {k: v for k, v in seen.items() if k[1]} == {(c, True): 2 for c in (1, 3, 127, 137, -9)}
    assert {v for k, v in seen.items() if not k[1]} == {0} and soft == {0}


@needs_runner
@pytest.mark.skipif(h.WINDOWS, reason="the no-python POSIX path is not a Windows path (B10)")
@pytest.mark.parametrize("config,armed", [("own", True), ("none", False)])
def test_with_no_python_a_wedged_guard_is_a_fault_at_the_deadline(config, armed, tmp_path):
    scripts = _copy_scripts(tmp_path)
    _plant_slow_guard(scripts)
    root, home = _repo(tmp_path, config)
    started = time.monotonic()

    code, _, err = _run("sh", scripts, "PreToolUse", BASH_PAYLOAD, root, home, env_extra=_deadline(2.0),
                        path=rgh.no_python_path(str(tmp_path)), timeout=60)

    assert code == (2 if armed else 0), err
    assert time.monotonic() - started < 20
    # armed, the other guards (no python) block first and say so; unarmed the wedged one is the fault
    assert armed or "scope-guard.sh exited 137 without a decision" in err


@needs_runner
@pytest.mark.skipif(h.WINDOWS, reason="the no-python POSIX path is not a Windows path (B10)")
@pytest.mark.parametrize("config,armed", [("own", True), ("none", False)])
def test_with_no_python_a_crashed_guard_is_a_fault(config, armed, tmp_path):
    scripts = _copy_scripts(tmp_path)
    _plant_guard_exits(1)(scripts)
    root, home = _repo(tmp_path, config)

    code, _, err = _run("sh", scripts, "PreToolUse", BASH_PAYLOAD, root, home, path=rgh.no_python_path(str(tmp_path)))

    assert code == (2 if armed else 0), err


@needs_runner
@pytest.mark.skipif(h.WINDOWS, reason="the no-python POSIX path is not a Windows path (B10)")
@pytest.mark.parametrize("config,armed", [("own", True), ("none", False)])
def test_with_no_python_a_stdin_that_never_closes_is_a_fault(config, armed, tmp_path):
    scripts = _copy_scripts(tmp_path)
    root, home = _repo(tmp_path, config)
    env = rgh.env_for(root, home, path=rgh.no_python_path(str(tmp_path)))
    env.update(_deadline(2.0))
    env["CLAUDE_PLUGIN_ROOT"] = os.path.dirname(os.path.dirname(scripts))
    proc = subprocess.Popen([h.BASH or "bash", os.path.join(scripts, "crew-hook.sh"), "PreToolUse"],  # pylint: disable=consider-using-with
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=root)
    try:
        proc.stdin.write(b'{"tool_name": "Bash"')
        proc.stdin.flush()
        code = proc.wait(timeout=30)
        err = proc.stderr.read().decode("utf-8", "replace")
    finally:
        proc.kill()
        proc.communicate()

    assert code == (2 if armed else 0), err
    assert "stdin did not close before the deadline" in err


@pytest.mark.parametrize("name", ["trace.txt", "ran.log"])
def test_a_trace_path_without_the_suffix_is_never_written(name, tmp_path):
    target = tmp_path / name

    crew_hook._trace(str(target), "PreToolUse", ["x.sh"], 1)  # pylint: disable=protected-access

    assert not target.exists()


@pytest.mark.skipif(h.WINDOWS, reason="symlinks need privileges on Windows")
def test_a_trace_path_that_is_a_symlink_is_not_followed(tmp_path):
    victim = tmp_path / "bashrc"
    victim.write_text("original\n", encoding="utf-8")
    link = tmp_path / "t.crew-trace"
    link.symlink_to(victim)

    crew_hook._trace(str(link), "PreToolUse", ["x.sh"], 1)  # pylint: disable=protected-access

    assert victim.read_text(encoding="utf-8") == "original\n"


@needs_runner
@pytest.mark.skipif(h.WINDOWS, reason="the sh launcher is not a Windows path")
def test_the_sh_launcher_check_is_armed_when_home_is_unset(tmp_path):
    root, home = _repo(tmp_path, "none")
    text = h.read_text(h.SH)
    body = text[text.index("# Exists, or cannot be told"):text.index("_fail() {")]
    env = {key: value for key, value in rgh.env_for(root, home).items() if key != "HOME"}

    done = subprocess.run([h.BASH, "-c", f"EVENT=PreToolUse\n{body}\n_armed\necho $?\n"], capture_output=True,
                          text=True, env=env, cwd=root, check=True)

    assert done.stdout.strip() == "0"


@needs_runner
@pytest.mark.skipif(h.WINDOWS, reason="the no-python POSIX path is not a Windows path (B10)")
@pytest.mark.parametrize("config,armed", [("own", True), ("none", False)])
def test_with_no_python_the_approval_hook_crashing_is_a_fault_on_user_prompt_submit(config, armed, tmp_path):
    """On this event no other script blocks without python, so the crashed guard is the only reason."""
    scripts = _copy_scripts(tmp_path)
    with open(os.path.join(scripts, "approval-hook.sh"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("#!/usr/bin/env bash\ncat >/dev/null\nexit 1\n")
    root, home = _repo(tmp_path, config)
    data = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "hi", "session_id": "s-1"}).encode()

    code, _, err = _run("sh", scripts, "UserPromptSubmit", data, root, home, path=rgh.no_python_path(str(tmp_path)))

    assert code == (2 if armed else 0), err
    assert "approval-hook.sh exited 1 without a decision" in err

# --- PR A: a guard timeout is one bounded retry, then UNKNOWN (never a policy deny, never an allow) ----
# Driven in process against fake guards (crew_hook_harness.fake_guards), so each case is a few seconds.

def _counting(tmp_path, body):
    """Fake-guard source that appends a line to a run log, then runs `body`. Returns (source, log path)."""
    log = tmp_path / "runs.log"
    head = (f"import os, sys, time\nsys.stdin.buffer.read()\n"
            f"open({str(log)!r}, 'a').write('run\\n')\n")
    return head + body, log


def _runs(log):
    return len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0


def _hang_once(tmp_path):
    marker = tmp_path / "seen"
    return _counting(tmp_path, f"m = {str(marker)!r}\nif not os.path.exists(m):\n"
                               "    open(m, 'w').close()\n    time.sleep(60)\n")


def test_a_guard_that_times_out_once_is_retried_and_its_second_answer_is_used(tmp_path, monkeypatch):
    source, log = _hang_once(tmp_path)
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, out, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 0, err
    assert _runs(log) == 2 and "UNKNOWN" not in err and out == ""


def test_a_retried_guard_that_then_denies_still_blocks_as_a_deny(tmp_path, monkeypatch):
    marker = tmp_path / "seen"
    source, log = _counting(tmp_path, f"m = {str(marker)!r}\nif not os.path.exists(m):\n"
                                      "    open(m, 'w').close()\n    time.sleep(60)\n"
                                      "sys.stderr.write('env-guard: blocked a real policy deny\\n')\nsys.exit(2)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and _runs(log) == 2
    assert "env-guard: blocked a real policy deny" in err and "UNKNOWN" not in err


def test_a_guard_that_times_out_twice_fails_closed_labelled_unknown_with_the_armed_suffix(tmp_path, monkeypatch):
    source, log = _counting(tmp_path, "time.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, out, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and out == ""
    assert _runs(log) == 2, "exactly one retry, never a third run"
    unknown = "crew-hook: UNKNOWN (guard timeout, not a policy deny)"
    assert unknown in err
    assert err.index(unknown) < err.index("env-guard.sh timed out")
    assert "failing closed (armed repo)" in err


def test_a_timeout_in_an_unarmed_repo_is_a_labelled_note_and_exit_0(tmp_path, monkeypatch):
    source, _ = _counting(tmp_path, "time.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts, armed=False)

    assert code == 0
    assert "UNKNOWN (guard timeout" in err and "the repo is not armed, so this is not a block" in err


def test_no_retry_when_the_dispatch_deadline_has_no_room_for_one(tmp_path, monkeypatch):
    source, log = _counting(tmp_path, "time.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts, window_s=6.5, row_timeout=5)

    assert code == 2, err
    assert _runs(log) == 1 and "UNKNOWN (guard timeout" in err


def _with_reserve_of(monkeypatch, windows):
    """Make dispatch compute the retry reserve of the given platform, whatever OS runs the test."""
    real = crew_hook._retry_reserve  # pylint: disable=protected-access
    monkeypatch.setattr(crew_hook, "_retry_reserve", lambda _windows: real(windows))
    return real(windows)


@pytest.mark.parametrize("windows", [False, True], ids=["reserve-posix", "reserve-windows"])
def test_the_retry_gate_sits_exactly_at_the_floor_whichever_reserve_applies(tmp_path, monkeypatch, windows):
    """The window is derived from the platform's own reserve, so the guard bites on every OS: just
    under reserve + RETRY_FLOOR left after the first attempt there is no retry (a gate that ignores
    the deadline would start one with ~1 s), with ample room beyond the floor there is one."""
    reserve = _with_reserve_of(monkeypatch, windows)
    first = 3
    source, log = _counting(tmp_path, "time.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts, window_s=first + reserve + crew_hook.RETRY_FLOOR - 1.0,
                                   row_timeout=first)

    assert code == 2, err
    assert _runs(log) == 1 and "no retry: no room before the dispatch deadline" in err, err

    roomy_dir = tmp_path / "roomy"
    roomy_dir.mkdir()
    source, log = _counting(roomy_dir, "time.sleep(60)\n")
    scripts = h.fake_guards(roomy_dir, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts, window_s=first + reserve + crew_hook.RETRY_FLOOR + 2.0,
                                   row_timeout=first)

    assert code == 2, err
    assert _runs(log) == 2 and "attempts=2" in err, err


def test_a_timeout_is_never_exit_0_when_armed_whichever_guard_it_is(tmp_path, monkeypatch):
    for name in h.BASH_GUARDS:
        sub = tmp_path / name.replace(".", "_")
        sub.mkdir()
        source, _ = _counting(sub, "time.sleep(60)\n")
        scripts = h.fake_guards(sub, {name: source})

        code, _, err = h.dispatch_fake(monkeypatch, scripts, window_s=5.0, row_timeout=2)

        assert code == 2, f"{name}: {err}"
        assert "UNKNOWN (guard timeout" in err, name


def test_a_real_policy_deny_is_never_labelled_unknown_even_if_its_words_look_like_a_fault(tmp_path, monkeypatch):
    text = "env-guard: blocked - the command mentions MemoryError, and Resource temporarily unavailable\\n"
    source, _ = _counting(tmp_path, f"sys.stderr.write('{text}')\nsys.exit(2)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, out, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and out == ""
    assert "env-guard: blocked - the command mentions MemoryError" in err
    assert "UNKNOWN" not in err


def test_a_json_deny_from_a_guard_is_a_deny_not_unknown(tmp_path, monkeypatch):
    deny = ('{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", '
            '"permissionDecisionReason": "no"}}')
    source, _ = _counting(tmp_path, f"sys.stdout.write({deny!r})\n")
    scripts = h.fake_guards(tmp_path, {"cloud-guard.sh": source})

    code, out, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 0 and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "UNKNOWN" not in err


RESOURCE_TEXTS = ["bash: fork: retry: Resource temporarily unavailable", "OSError: [Errno 11] x",
                  "BlockingIOError: EAGAIN", "MemoryError", "env-guard: fork failed", "can't fork"]


@pytest.mark.parametrize("said", RESOURCE_TEXTS,
                         ids=["unavailable", "errno11", "eagain", "memoryerror", "forkfailed", "cantfork"])
def test_a_guard_that_exits_undecided_on_a_resource_failure_is_unknown_resource_and_fails_closed(said, tmp_path,
                                                                                                monkeypatch):
    source, _ = _counting(tmp_path, f"sys.stderr.write({said!r} + '\\n')\nsys.exit(1)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2, err
    assert "crew-hook: UNKNOWN (resource exhaustion, not a policy deny)" in err
    assert "UNKNOWN (guard timeout" not in err and "failing closed (armed repo)" in err


def test_a_guard_that_hangs_after_a_resource_failure_is_labelled_resource_not_timeout(tmp_path, monkeypatch):
    source, _ = _counting(tmp_path, "sys.stderr.write('fork: Resource temporarily unavailable\\n')\n"
                                    "sys.stderr.flush()\ntime.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts, window_s=6.0, row_timeout=2)

    assert code == 2 and "UNKNOWN (resource exhaustion" in err and "UNKNOWN (guard timeout" not in err


QUOTED_TEXTS = [
    'Traceback (most recent call last):\n'
    '  File "C:\\work\\MemoryError-tests\\guard.py", line 3, in <module>\nValueError: bad',
    "+ grep EAGAIN /var/log/app.log\nboom",
    "env-guard: refused - the command quotes errno 11 mid-sentence and says fork failed",
    "C:\\work\\MemoryError-tests\\guard.py",
]


@pytest.mark.parametrize("said", QUOTED_TEXTS, ids=["path", "quoted-eagain", "quoted-errno", "bare-path"])
def test_stderr_that_only_quotes_resource_words_is_not_labelled_resource_exhaustion(said, tmp_path, monkeypatch):
    source, _ = _counting(tmp_path, f"sys.stderr.write({said!r} + '\\n')\nsys.exit(1)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and "exited 1 without a decision" in err, err
    assert "resource exhaustion" not in err


def test_the_cygwin_dofork_line_is_resource_exhaustion(tmp_path, monkeypatch):
    said = ("      0 [main] bash 1234 dofork: child -1 - forked process 5678 died unexpectedly, "
            "retry 0, exit code 0xC0000142, errno 11")
    source, _ = _counting(tmp_path, f"sys.stderr.write({said!r} + '\\n')\nsys.exit(1)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and "UNKNOWN (resource exhaustion, not a policy deny)" in err, err


def test_a_start_failure_naming_eagain_is_resource_exhaustion(monkeypatch):
    row = next(r for r in crew_hook.TABLE if r.script == "scope-guard.sh")
    result = {"exit": None, "stdout": b"", "stderr": b"", "timed_out": False, "pid": 0,
              "error": "could not start bash: [Errno 11] Resource temporarily unavailable"}

    code, _, err = crew_hook._settle(row.event, [(row, [row.script])], [result], "/r", lambda _r: True)  # pylint: disable=protected-access

    assert code == 2 and b"UNKNOWN (resource exhaustion, not a policy deny)" in err


def test_an_undecided_exit_with_an_unrelated_message_fails_closed_without_a_resource_label(tmp_path, monkeypatch):
    source, _ = _counting(tmp_path, "sys.stderr.write('traceback: boom\\n')\nsys.exit(1)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and "env-guard.sh exited 1 without a decision" in err
    assert "UNKNOWN" not in err


def test_a_guard_that_has_no_usable_python_is_unknown_and_still_blocks(tmp_path, monkeypatch):
    source, _ = _counting(tmp_path, "sys.stderr.write('env-guard: no usable python, and guards.envGuard is armed\\n')\n"
                                    "sys.exit(2)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2
    assert "crew-hook: UNKNOWN (no usable python, not a policy deny)" in err
    assert "env-guard: no usable python" in err


def test_a_real_scope_deny_that_quotes_the_words_in_a_path_stays_a_deny(tmp_path, monkeypatch):
    """scope_guard.py prints `SCOPE GUARD: refused {tool} on {path}.`; a path may say anything."""
    source, _ = _counting(tmp_path, "sys.stderr.write('SCOPE GUARD: refused Write on notes/no usable python.md.\\n')\n"
                                    "sys.exit(2)\n")
    scripts = h.fake_guards(tmp_path, {"scope-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2
    assert "refused Write on notes/no usable python.md" in err
    assert "UNKNOWN" not in err


def test_a_deny_whose_later_line_starts_with_a_refusal_text_is_still_a_deny(tmp_path, monkeypatch):
    """A path with a newline in it can start a line with the guard's words; a refusal is ONE line."""
    source, _ = _counting(tmp_path, "sys.stderr.write('SCOPE GUARD: refused Write on a\\n"
                                    "SCOPE GUARD: no usable python - cannot judge this call.md.\\n')\nsys.exit(2)\n")
    scripts = h.fake_guards(tmp_path, {"scope-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and "UNKNOWN" not in err


def test_every_no_python_refusal_text_is_the_literal_start_of_a_line_a_guard_prints():
    scripts = {name: open(os.path.join(h.SCRIPTS, name), encoding="utf-8").read()  # pylint: disable=consider-using-with
               for name in os.listdir(h.SCRIPTS) if name.endswith(".sh")}
    for text in crew_hook.NO_PYTHON_REFUSALS:
        rest = text.split(": ", 1)[-1]  # role-write-guard and completion-audit print "<prefix>: $why/$1"
        assert any(f'echo "{text}' in body or f'"{rest}' in body for body in scripts.values()), \
            f"no guard prints {text!r}"


def test_a_guard_that_exits_1_with_the_words_is_not_relabelled_no_python(tmp_path, monkeypatch):
    source, _ = _counting(tmp_path, "sys.stderr.write('env-guard: no usable python, and guards.envGuard is armed\\n')\n"
                                    "sys.exit(1)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and "UNKNOWN (no usable python" not in err


# --- review of #700: what is retried, and how much room a retry needs --------------------------

def test_a_stateful_row_is_never_retried(tmp_path, monkeypatch):
    source, log = _counting(tmp_path, "time.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"promote-gate.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts)

    assert code == 2 and _runs(log) == 1, "promote-gate.sh must get exactly one attempt"
    assert "attempts=1" in err and "no retry: this row is not retry-safe" in err


def test_the_retry_allow_list_is_exactly_the_stateless_pretooluse_judges():
    assert crew_hook.RETRY_SAFE == {"role-write-guard.sh", "cloud-guard.sh", "env-guard.sh", "scope-guard.sh"}
    for row in crew_hook.TABLE:
        if row.script in ("approval-hook.sh", "completion-audit.sh", "verify-gate.sh", "promote-gate.sh"):
            assert row.script not in crew_hook.RETRY_SAFE


def test_the_reserve_covers_the_worst_cleanup_of_a_second_timeout():
    for windows in (False, True):
        worst = 2 * crew_hook.POST_KILL + (crew_hook.TASKKILL_BOUND if windows else 0)
        assert crew_hook._retry_reserve(windows) > worst  # pylint: disable=protected-access
    assert crew_hook._retry_reserve(True) > crew_hook._retry_reserve(False)  # pylint: disable=protected-access


def test_a_retry_is_refused_when_the_cleanup_reserve_would_not_fit(tmp_path, monkeypatch):
    """~7.4 s are left after the first 2 s attempt: more than the old 3.5 s reserve plus the floor,
    less than the real worst-case cleanup plus the floor."""
    source, log = _counting(tmp_path, "time.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})

    code, _, err = h.dispatch_fake(monkeypatch, scripts, window_s=9.5, row_timeout=2)

    assert code == 2, err
    assert _runs(log) == 1 and "attempts=1" in err and "no retry: no room before the dispatch deadline" in err


def _default_retry_set(windows):
    """Guard rows of the DEFAULT table that can be retried when every row of the event runs to its
    limit, from the window the launcher hands over (the event's registration timeout less its margin)."""
    found = set()
    for row in crew_hook.TABLE:
        if not row.guard or row.script not in crew_hook.RETRY_SAFE:
            continue
        window = crew_hook.event_timeout(row.event) - crew_hook.DEADLINE_MARGIN
        room = window - row.timeout - crew_hook._retry_reserve(windows)  # pylint: disable=protected-access
        if min(float(row.timeout), room) >= crew_hook.RETRY_FLOOR:
            found.add(row.script)
    return found


def test_at_the_default_table_only_these_rows_can_ever_be_retried():
    """Pins what the troubleshooting docs say. promote-gate, approval-hook, verify-gate and
    completion-audit never retry; on Windows only the 10 s role-write-guard has the room."""
    assert _default_retry_set(False) == {"role-write-guard.sh", "cloud-guard.sh", "env-guard.sh", "scope-guard.sh"}
    assert _default_retry_set(True) == {"role-write-guard.sh"}


def test_a_retry_that_replaces_the_first_attempt_keeps_what_the_first_one_said(tmp_path, monkeypatch):
    marker = tmp_path / "seen"
    source, _ = _counting(tmp_path, f"m = {str(marker)!r}\nif not os.path.exists(m):\n"
                                    "    open(m, 'w').close()\n    sys.stderr.write('first attempt: slow disk\\n')\n"
                                    "    sys.stderr.flush()\n    time.sleep(60)\n"
                                    "time.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})
    timing = tmp_path / "t.crew-trace"

    code, _, err = h.dispatch_fake(monkeypatch, scripts, env=dict(os.environ, CREW_HOOK_TIMING_FILE=str(timing)))

    line = next(l for l in timing.read_text(encoding="utf-8").splitlines() if "env-guard.sh" in l)
    assert code == 2 and "attempts=2" in err
    assert "attempt 1 said: 'first attempt: slow disk'" in err
    assert 'first_said="first attempt: slow disk"' in line and line.endswith("timeout")


# --- PR A: opt-in per-child timing --------------------------------------------------------------

def test_the_timing_file_records_start_end_and_duration_per_child(tmp_path, monkeypatch):
    scripts = h.fake_guards(tmp_path, {})
    timing = tmp_path / "t.crew-trace"

    code, _, err = h.dispatch_fake(monkeypatch, scripts, env=dict(os.environ, CREW_HOOK_TIMING_FILE=str(timing)))

    lines = timing.read_text(encoding="utf-8").splitlines()
    assert code == 0, err
    assert len(lines) == 4
    for line in lines:
        fields = dict(part.split("=", 1) for part in line.split() if "=" in part)
        assert int(fields["end_ms"]) >= int(fields["start_ms"])
        assert int(fields["ms"]) == int(fields["end_ms"]) - int(fields["start_ms"])
        assert fields["attempts"] == "1" and "exit=0" in line


def test_the_timing_file_records_the_retry_and_the_timeout(tmp_path, monkeypatch):
    source, _ = _counting(tmp_path, "time.sleep(60)\n")
    scripts = h.fake_guards(tmp_path, {"env-guard.sh": source})
    timing = tmp_path / "t.crew-trace"

    h.dispatch_fake(monkeypatch, scripts, env=dict(os.environ, CREW_HOOK_TIMING_FILE=str(timing)))

    line = next(l for l in timing.read_text(encoding="utf-8").splitlines() if "env-guard.sh" in l)
    assert "attempts=2" in line and line.endswith("timeout")


@pytest.mark.parametrize("name", ["timing.txt", "ran.log"])
def test_a_timing_path_without_the_suffix_is_never_written(name, tmp_path, monkeypatch):
    scripts = h.fake_guards(tmp_path, {})
    target = tmp_path / name

    h.dispatch_fake(monkeypatch, scripts, env=dict(os.environ, CREW_HOOK_TIMING_FILE=str(target)))

    assert not target.exists()


@pytest.mark.skipif(h.WINDOWS, reason="symlinks need privileges on Windows")
def test_a_timing_path_that_is_a_symlink_is_not_followed(tmp_path, monkeypatch):
    victim = tmp_path / "bashrc"
    victim.write_text("original\n", encoding="utf-8")
    link = tmp_path / "t.crew-trace"
    link.symlink_to(victim)
    scripts = h.fake_guards(tmp_path, {})

    h.dispatch_fake(monkeypatch, scripts, env=dict(os.environ, CREW_HOOK_TIMING_FILE=str(link)))

    assert victim.read_text(encoding="utf-8") == "original\n"

@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
def test_the_launcher_hands_the_python_it_resolved_to_the_guards_as_crew_python(flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    seen = tmp_path / "python.txt"
    with open(os.path.join(scripts, "scope-guard.sh"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"#!/usr/bin/env bash\ncat >/dev/null\n"
                     f"printf '%s' \"$CREW_PYTHON\" >'{seen.as_posix()}'\nexit 0\n")
    root, home = _repo(tmp_path, "own")

    code, _, err = _run(flavour, scripts, "PreToolUse", BASH_PAYLOAD, root, home,
                        env_extra={"CREW_PYTHON": "/inherited/not-this-one"})

    value = seen.read_text(encoding="utf-8")
    assert code == 0, err
    assert value and value != "/inherited/not-this-one", "the launcher's own python must replace an inherited value"
    assert os.path.isfile(value) or os.path.isfile(value + ".exe") or os.path.basename(value).startswith("python")
