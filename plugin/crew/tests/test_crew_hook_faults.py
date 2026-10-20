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


def _deadline(seconds):
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


FAULTS = {
    "exception-in-main": (_plant_exception, "dispatcher error RuntimeError: boom", dict),
    "syntax-error-before-main": (_plant_syntax_error, "crew_hook.py failed (exit 1)", dict),
    "table-script-missing": (_plant_missing_script, "scope-guard.sh is missing", dict),
    "guard-past-its-timeout": (_plant_slow_guard, "scope-guard.sh timed out", lambda: _deadline(2.5)),
    "dispatcher-hangs-before-main": (_plant_hang_before_main, ("failed (exit 137)", "ran past the deadline"),
                                     lambda: _deadline(2.0)),
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

    code, _, err = _run(flavour, scripts, "PreToolUse", BASH_PAYLOAD, root, home, env_extra=extra())

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

    code, _, err = _run(flavour, scripts, "PreToolUse", BASH_PAYLOAD, root, home, env_extra=extra())

    assert code == 0, err


@needs_runner
@pytest.mark.parametrize("flavour", h.POSIX_FLAVOURS)
@pytest.mark.parametrize("config,armed", [("own", True), ("inherited", True), ("global", True), ("none", False)])
def test_a_stdin_that_never_closes_is_a_fault_not_a_hang(config, armed, flavour, tmp_path):
    scripts = _copy_scripts(tmp_path)
    root, home = _repo(tmp_path, config)
    env = rgh.env_for(root, home)
    env.update(_deadline(2.5))
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


def test_a_child_that_backgrounds_work_holding_its_pipes_does_not_hold_the_dispatcher_up():
    script = "sleep 20 & echo started"

    started = time.monotonic()
    result = crew_hook.run_child(["bash", "-c", script], b"", 30, dict(os.environ))

    assert result["exit"] == 0 and result["stdout"].strip() == b"started"
    assert time.monotonic() - started < 10
