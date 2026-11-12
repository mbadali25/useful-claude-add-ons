"""The Windows hot path starts no Git Bash (crew 1.3.55).

On Git Bash every process start is an MSYS fork, and a Bash tool call used to cost about thirty of them:
each `.sh` row started a Git Bash whose wrapper started a subshell, python and git. The wrappers are only
launchers for a Python file, so `crew_hook.dispatch` now runs that file directly on Windows (`DIRECT`) and
believes the run only when it exits with a code the wrapper would have passed through. These tests hold:

  * (a) a Windows dispatch of a Bash call, a prompt or a Read spawns ZERO `.sh`, and never resolves Git Bash;
        a bad exit, a failed launch or a missing file runs the original wrapper; a timeout is not rerun;
  * (b) the registration is one bash launcher per event, no PowerShell, and every hot-path row has a direct
        route, so the number of process starts per tool call cannot silently grow back;
  * the direct route and the wrapper give the same exit code, stdout and stderr for the recorded cases;
  * the bash launcher does not stand down on Windows and falls through the Store python3 stub (exit 49).
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_hook
import crew_hook_harness as h
import record_golden_hooks as rgh

SCRIPTS = h.SCRIPTS
HOOKS_JSON = os.path.join(context._ROOT, "hooks", "hooks.json")  # pylint: disable=protected-access
FAKE_BASH = "C:/fake/bash.exe"
BASH_TOOL = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                        "tool_input": {"command": "ls"}, "session_id": "s-1"}).encode()


def _prompt(text):
    return json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": text, "session_id": "s-1"}).encode()


def _result(code=0, out=b"", err=b"", timed_out=False, error=""):
    return {"exit": None if timed_out or error else code, "stdout": out, "stderr": err, "timed_out": timed_out,
            "error": error, "pid": 1}


def _project(tmp_path):
    project = tmp_path / "project"
    (project / ".crew").mkdir(parents=True)
    (project / ".crew" / "verify.json").write_text("{}", encoding="utf-8")
    return str(project)


class Spy:
    """crew_hook.run_child replaced: records every start, answers through `decide(argv)`."""

    def __init__(self, monkeypatch, decide=None):
        self.calls = []
        self.decide = decide or (lambda argv: _result())
        monkeypatch.setattr(crew_hook, "run_child", self)

    def __call__(self, argv, raw, timeout, env, cwd=None):
        self.calls.append({"argv": list(argv), "raw": raw, "env": env, "cwd": cwd})
        return self.decide(list(argv))

    def wrappers(self):
        return [c for c in self.calls if any(str(a).endswith(".sh") for a in c["argv"])]

    def direct(self):
        return [c for c in self.calls if c not in self.wrappers()]

    def modules(self):
        return sorted(os.path.basename(c["argv"][1]) for c in self.direct())


def _dispatch(tmp_path, payload, event="PreToolUse", armed=True, windows=True, bash=FAKE_BASH, env_extra=None,
              scripts=SCRIPTS, direct=None):
    project = _project(tmp_path)
    asked = []

    def resolver(strict=True):
        asked.append(strict)
        return (bash, "stub") if bash else (None, "Git Bash not found (strict)")

    env = {"CLAUDE_PROJECT_DIR": project, **(env_extra or {})}
    code, out, err = crew_hook.dispatch(event, "claude", payload, crew_hook.now_ms() + 30000, env, project,
                                        windows=windows, resolve_bash=resolver, resolve_pwsh=lambda: (None, ""),
                                        scripts=scripts, armed_fn=lambda _root: armed, direct=direct)
    return code, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"), asked, project


# --- (a) zero .sh on the happy path -------------------------------------------------------------

def test_a_bash_call_on_windows_spawns_no_sh_and_never_resolves_git_bash(monkeypatch, tmp_path):
    spy = Spy(monkeypatch)

    code, _, _, asked, _ = _dispatch(tmp_path, BASH_TOOL)

    assert code == 0
    assert spy.wrappers() == [] and asked == []
    assert spy.modules() == ["_promote_gate.py", "cloud_guard.py", "env_guard.py", "scope_guard.py"]
    assert all(c["argv"][0] == sys.executable for c in spy.calls)


def test_the_direct_children_get_the_environment_and_stdin_their_wrappers_gave(monkeypatch, tmp_path):
    spy = Spy(monkeypatch)

    _, _, _, _, project = _dispatch(tmp_path, BASH_TOOL)

    by = {os.path.basename(c["argv"][1]): c for c in spy.calls}
    assert by["cloud_guard.py"]["env"]["CREW_CLOUD_GUARD_FLAVOUR"] == "bash"
    assert by["env_guard.py"]["env"]["CREW_ENV_GUARD_FLAVOUR"] == "bash"
    for name in ("cloud_guard.py", "env_guard.py", "scope_guard.py"):
        assert by[name]["env"]["PYTHONUTF8"] == "1" and by[name]["env"]["PYTHONIOENCODING"] == "utf-8"
        assert by[name]["raw"] == BASH_TOOL and by[name]["cwd"] is None
    gate = by["_promote_gate.py"]
    assert gate["cwd"] == project and gate["raw"] == BASH_TOOL + b"\n"  # promote-gate.sh's here-string
    assert gate["env"]["CREW_GATE_START"].isdigit() and gate["env"]["CREW_HEAD_MAP"] == ""
    assert gate["env"]["CREW_MAP_DIRTY"] == "" and gate["env"]["PYTHONIOENCODING"] == "utf-8"
    assert all(c["env"]["CREW_HOOK_FLAVOUR"] == "bash" for c in spy.calls)


@pytest.mark.parametrize("tool,rows", [
    ("Write", ["role_write_guard.py", "scope_guard.py"]), ("Edit", ["role_write_guard.py", "scope_guard.py"]),
    ("MultiEdit", ["scope_guard.py"]), ("NotebookEdit", ["scope_guard.py"])])
def test_a_write_call_on_windows_spawns_no_sh(tool, rows, monkeypatch, tmp_path):
    spy = Spy(monkeypatch)
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"file_path": "a"}}).encode()

    code, _, _, asked, _ = _dispatch(tmp_path, payload)

    assert code == 0 and spy.wrappers() == [] and asked == []
    assert spy.modules() == sorted(rows)


@pytest.mark.parametrize("event,tool", [("PostToolUse", "Read"), ("PostToolUse", "mcp__obsidian__search"),
                                        ("SubagentStart", None)])
def test_the_context_events_on_windows_spawn_no_sh(event, tool, monkeypatch, tmp_path):
    spy = Spy(monkeypatch)
    payload = json.dumps({"hook_event_name": event, **({"tool_name": tool} if tool else {})}).encode()

    code, _, _, asked, _ = _dispatch(tmp_path, payload, event=event)

    assert code == 0 and spy.wrappers() == [] and asked == []
    assert spy.modules() == ["crew_context.py"]
    assert spy.direct()[0]["argv"][2:] == ["--flavour", "sh"]


def test_a_plain_prompt_on_windows_starts_only_the_context_hook(monkeypatch, tmp_path):
    spy = Spy(monkeypatch)

    code, _, _, asked, _ = _dispatch(tmp_path, _prompt("what is the plan"), event="UserPromptSubmit")

    assert code == 0 and spy.wrappers() == [] and asked == []
    assert spy.modules() == ["crew_context.py"]  # approval-hook.sh's own pre-filter: no `approve`, no python


@pytest.mark.parametrize("text", ["/crew:approve T-1", "please ApPrOvE it", "APPROVED", "/crew:confirm-config"])
def test_a_prompt_the_approval_hook_cares_about_runs_its_python_directly(text, monkeypatch, tmp_path):
    spy = Spy(monkeypatch)

    code, _, _, asked, _ = _dispatch(tmp_path, _prompt(text), event="UserPromptSubmit")

    assert code == 0 and spy.wrappers() == [] and asked == []
    assert spy.modules() == ["approval_hook.py", "crew_context.py"]
    assert [c["raw"] for c in spy.calls] == [_prompt(text)] * 2


def test_the_rows_with_no_direct_route_still_resolve_git_bash_up_front(monkeypatch, tmp_path):
    spy = Spy(monkeypatch)
    payload = json.dumps({"hook_event_name": "SessionStart", "source": "startup"}).encode()

    code, _, _, asked, _ = _dispatch(tmp_path, payload, event="SessionStart")

    assert code == 0 and asked == [True]
    assert len(spy.wrappers()) == 2 and all(c["argv"][0] == FAKE_BASH for c in spy.wrappers())  # handoff-read, platform-sync


def test_no_git_bash_still_refuses_an_event_that_has_a_row_with_no_direct_route(monkeypatch, tmp_path):
    spy = Spy(monkeypatch)
    payload = json.dumps({"hook_event_name": "Stop"}).encode()

    code, _, err, _, _ = _dispatch(tmp_path, payload, event="Stop", bash=None)

    assert code == 2 and "Git for Windows" in err and spy.calls == []


# --- a direct run that is not believed runs the wrapper -----------------------------------------

def _bad_direct(module, code, noise=b"STALE-DIRECT-OUTPUT"):
    def decide(argv):
        if argv[0] == FAKE_BASH:
            return _result(0)
        return _result(code, out=noise, err=noise) if os.path.basename(argv[1]) == module else _result(0)
    return decide


@pytest.mark.parametrize("module,wrapper,code", [
    ("scope_guard.py", "scope-guard.sh", 1), ("scope_guard.py", "scope-guard.sh", 3),
    ("scope_guard.py", "scope-guard.sh", 127), ("scope_guard.py", "scope-guard.sh", 137),
    ("cloud_guard.py", "cloud-guard.sh", 1), ("cloud_guard.py", "cloud-guard.sh", 2),
    ("env_guard.py", "env-guard.sh", 1), ("env_guard.py", "env-guard.sh", 2),
    ("_promote_gate.py", "promote-gate.sh", 1), ("_promote_gate.py", "promote-gate.sh", 11),
    ("_promote_gate.py", "promote-gate.sh", 22), ("_promote_gate.py", "promote-gate.sh", 127)])
def test_a_direct_exit_the_wrapper_would_not_pass_through_runs_the_wrapper(module, wrapper, code, monkeypatch, tmp_path):
    spy = Spy(monkeypatch, _bad_direct(module, code))

    got, out, err, asked, _ = _dispatch(tmp_path, BASH_TOOL)

    assert got == 0 and asked == [True]
    assert [os.path.basename(c["argv"][1]) for c in spy.wrappers()] == [wrapper]
    assert spy.wrappers()[0]["argv"][0] == FAKE_BASH
    assert "STALE-DIRECT-OUTPUT" not in out + err  # only the wrapper's answer is used


@pytest.mark.parametrize("module,code", [("scope_guard.py", 2), ("_promote_gate.py", 2)])
def test_exit_2_from_scope_and_promote_gate_is_a_decision_and_the_wrapper_is_not_run(module, code, monkeypatch, tmp_path):
    spy = Spy(monkeypatch, _bad_direct(module, code, noise=b"BLOCKED because reasons\n"))

    got, _, err, asked, _ = _dispatch(tmp_path, BASH_TOOL)

    assert got == 2 and "BLOCKED because reasons" in err
    assert spy.wrappers() == [] and asked == []


def test_a_failed_launch_runs_the_wrapper(monkeypatch, tmp_path):
    def decide(argv):
        if argv[0] == sys.executable and os.path.basename(argv[1]) == "cloud_guard.py":
            return _result(error="could not start python: [WinError 5]")
        return _result(0)

    spy = Spy(monkeypatch, decide)

    got, _, _, _, _ = _dispatch(tmp_path, BASH_TOOL)

    assert got == 0
    assert [os.path.basename(c["argv"][1]) for c in spy.wrappers()] == ["cloud-guard.sh"]


def test_a_direct_guard_that_times_out_is_not_rerun_through_the_wrapper(monkeypatch, tmp_path):
    def decide(argv):
        if argv[0] == sys.executable and os.path.basename(argv[1]) == "scope_guard.py":
            return _result(timed_out=True)
        return _result(0)

    spy = Spy(monkeypatch, decide)

    got, _, err, _, _ = _dispatch(tmp_path, BASH_TOOL)

    assert got == 2 and "scope-guard.sh timed out" in err and "UNKNOWN (guard timeout" in err
    assert spy.wrappers() == []


def test_a_missing_python_file_runs_the_wrapper(monkeypatch, tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("promote-gate.sh", "cloud-guard.sh", "env-guard.sh", "scope-guard.sh", "_promote_gate.py",
                 "env_guard.py", "scope_guard.py"):
        (scripts / name).write_text("", encoding="utf-8")  # no cloud_guard.py
    spy = Spy(monkeypatch)

    got, _, _, _, _ = _dispatch(tmp_path, BASH_TOOL, scripts=str(scripts))

    assert got == 0
    assert [os.path.basename(c["argv"][1]) for c in spy.wrappers()] == ["cloud-guard.sh"]
    assert "cloud_guard.py" not in spy.modules()


def test_with_git_bash_missing_a_direct_row_that_is_not_believed_fails_closed_naming_git(monkeypatch, tmp_path):
    spy = Spy(monkeypatch, _bad_direct("scope_guard.py", 1))

    got, _, err, _, _ = _dispatch(tmp_path, BASH_TOOL, bash=None)

    assert got == 2 and "Git for Windows" in err
    assert spy.wrappers() == []


def test_with_git_bash_missing_healthy_direct_rows_still_judge(monkeypatch, tmp_path):
    """The one deliberate change in who can be judged: the direct rows no longer need Git Bash."""
    spy = Spy(monkeypatch)

    got, _, _, asked, _ = _dispatch(tmp_path, BASH_TOOL, bash=None)

    assert got == 0 and asked == [] and len(spy.direct()) == 4


# --- the switch, and the other platforms --------------------------------------------------------

def test_crew_hook_direct_zero_takes_the_wrapper_route(monkeypatch, tmp_path):
    spy = Spy(monkeypatch)

    got, _, _, asked, _ = _dispatch(tmp_path, BASH_TOOL, env_extra={"CREW_HOOK_DIRECT": "0"})

    assert got == 0 and asked == [True]
    assert len(spy.wrappers()) == 4 and spy.direct() == []


def test_off_windows_the_rows_run_through_bash_unless_asked_otherwise(monkeypatch, tmp_path):
    spy = Spy(monkeypatch)

    _dispatch(tmp_path, BASH_TOOL, windows=False)

    assert len(spy.wrappers()) == 4 and spy.direct() == []


# --- direct_plan: promote-gate's own routing ------------------------------------------------------

def _git_repo(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True, capture_output=True)
    return str(path)


def _plan(argv, payload, env):
    return crew_hook.direct_plan(argv, crew_hook.parse_payload(payload), payload, env, SCRIPTS)


def test_promote_gate_goes_direct_only_for_a_bash_call(tmp_path):
    env = {"CLAUDE_PROJECT_DIR": _project(tmp_path)}
    power = json.dumps({"tool_name": "PowerShell", "tool_input": {"command": "x"}}).encode()

    assert _plan(["promote-gate.sh"], power, env) is None
    assert _plan(["promote-gate.sh"], b"{not json", env) is None
    assert _plan(["promote-gate.sh"], BASH_TOOL, env) is not None


def test_promote_gate_leaves_a_map_that_is_not_a_regular_file_to_the_wrapper(tmp_path):
    project = tmp_path / "p"
    (project / ".crew" / "verify.json").mkdir(parents=True)

    assert _plan(["promote-gate.sh"], BASH_TOOL, {"CLAUDE_PROJECT_DIR": str(project)}) is None


def test_promote_gate_with_no_map_anywhere_is_the_wrappers_own_exit_0(tmp_path):
    project = _git_repo(tmp_path / "g")

    assert _plan(["promote-gate.sh"], BASH_TOOL, {"CLAUDE_PROJECT_DIR": project}) == crew_hook._SKIP  # pylint: disable=protected-access


def test_promote_gate_with_a_map_committed_but_deleted_is_left_to_the_wrapper(tmp_path):
    project = _git_repo(tmp_path / "g")
    os.makedirs(os.path.join(project, ".crew"))
    with open(os.path.join(project, ".crew", "verify.json"), "w", encoding="utf-8") as handle:
        handle.write("{}")
    base = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "add", "-f", ".crew/verify.json"], cwd=project, check=True, capture_output=True)
    subprocess.run(base + ["commit", "-qm", "map"], cwd=project, check=True, capture_output=True)
    os.remove(os.path.join(project, ".crew", "verify.json"))

    assert _plan(["promote-gate.sh"], BASH_TOOL, {"CLAUDE_PROJECT_DIR": project}) is None


def test_promote_gate_with_an_unusable_project_dir_is_left_to_the_wrapper(tmp_path):
    assert _plan(["promote-gate.sh"], BASH_TOOL, {"CLAUDE_PROJECT_DIR": str(tmp_path / "gone")}) is None


def test_the_direct_table_names_only_python_files_that_exist_and_codes_the_wrappers_pass_through():
    for wrapper, spec in crew_hook.DIRECT.items():
        assert os.path.isfile(os.path.join(SCRIPTS, wrapper)), wrapper
        assert os.path.isfile(os.path.join(SCRIPTS, spec.module)), spec.module
        assert spec.accept in ((0,), (0, 2)), wrapper
    assert crew_hook.DIRECT["cloud-guard.sh"].accept == crew_hook.DIRECT["env-guard.sh"].accept == (0,)
    for name in ("scope-guard.sh", "role-write-guard.sh", "promote-gate.sh", "approval-hook.sh"):
        assert crew_hook.DIRECT[name].accept == (0, 2), name


def test_every_direct_row_names_the_python_file_its_wrapper_runs():
    for wrapper, spec in crew_hook.DIRECT.items():
        text = h.read_text(os.path.join(SCRIPTS, wrapper))
        assert spec.module in text, f"{wrapper} does not run {spec.module}"


# --- (b) the process-start budget -----------------------------------------------------------------

def _registrations():
    with open(HOOKS_JSON, encoding="utf-8") as handle:
        events = json.load(handle)["hooks"]
    return [(event, entry, hook) for event, entries in events.items() for entry in entries for hook in entry["hooks"]]


def test_hooks_json_registers_one_bash_launcher_per_event_and_no_powershell():
    regs = _registrations()

    assert sorted(e for e, _, _ in regs) == sorted(crew_hook.EVENTS)  # one each: no second flavour runs every guard again
    for event, _, hook in regs:
        assert hook.get("shell", "bash") == "bash", event
        assert hook["command"] == f'bash "${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/crew-hook.sh" {event}'
    assert not re.search(r'"shell"\s*:|\.ps1', h.read_text(HOOKS_JSON))  # no PowerShell shell, no launcher script


HOT = ("PreToolUse", "PostToolUse", "UserPromptSubmit", "SubagentStart")
TOOLS = ("Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "mcp__obsidian__search", None)


@pytest.mark.parametrize("event", HOT)
@pytest.mark.parametrize("tool", TOOLS)
def test_every_row_a_hot_event_selects_on_windows_has_a_direct_route(event, tool):
    payload = {"tool_name": tool} if tool else {}
    chosen = crew_hook.select(event, "claude", payload, windows=True)

    for _, argv in chosen:
        assert argv[0] in crew_hook.DIRECT, f"{event}/{tool}: {argv[0]} would start a Git Bash on every call"


def test_a_windows_bash_tool_call_costs_the_launcher_the_dispatcher_and_one_python_per_guard():
    """The budget: 1 bash launcher + 1 dispatcher python + 1 python per selected row. It was 1 pwsh + 1 bash +
    2 python + a Git Bash per row (each with a subshell, python and git): about thirty starts."""
    rows = crew_hook.select("PreToolUse", "claude", {"tool_name": "Bash"}, windows=True)

    assert len(rows) == 4
    assert 1 + 1 + len(rows) <= 6


# --- the bash launcher on Windows ------------------------------------------------------------------

SH_TEXT = h.read_text(os.path.join(SCRIPTS, "crew-hook.sh"))


def test_the_sh_launcher_has_no_windows_stand_down():
    code = "\n".join(line for line in SH_TEXT.splitlines() if not line.lstrip().startswith("#"))

    assert "BASH_VERSINFO" not in code and "uname" not in code and "MINGW" not in code
    assert "Windows_NT" not in code


def test_the_sh_launcher_treats_the_store_python_stub_exit_as_an_interpreter_failure():
    assert re.search(r"^\s*1\|126\|127\|49\) ;;$", SH_TEXT, re.MULTILINE)


def _git_bash():
    if os.name != "nt":
        return h.BASH
    import crew_shell  # pylint: disable=import-outside-toplevel
    path, _ = crew_shell.resolve_gitbash(strict=True)
    return path


GIT_BASH = _git_bash()
needs_launcher_bash = pytest.mark.skipif(GIT_BASH is None, reason="no bash - crew-hook.sh was NOT run")


def _run_sh(event, data, root, home, path=None, env_extra=None, harness="claude"):
    env = rgh.env_for(root, home, path=path)
    env.update(env_extra or {})
    argv = [GIT_BASH, SH_PATH.replace("\\", "/"), event] + (["--harness", "codex"] if harness == "codex" else [])
    done = subprocess.run(argv, input=data, capture_output=True, env=env, cwd=root, timeout=180, check=False)
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


SH_PATH = os.path.join(SCRIPTS, "crew-hook.sh")


@needs_launcher_bash
def test_the_sh_launcher_falls_through_a_python3_stub_that_exits_49(tmp_path):
    """The Windows Store alias answers 9009 (49 as a shell status) and can be the first python3 on PATH."""
    root, home = rgh.build_repo(str(tmp_path), True)
    stub = tmp_path / "stubbin"
    stub.mkdir()
    with open(stub / "python3", "w", encoding="utf-8", newline="\n") as handle:
        handle.write("#!/bin/sh\necho 'Python was not found' >&2\nexit 49\n")
    os.chmod(stub / "python3", 0o755)
    real = os.path.dirname(os.path.realpath(sys.executable))
    path = os.pathsep.join([str(stub), real, os.environ.get("PATH", "")])
    trace = tmp_path / "trace.crew-trace"

    code, _, err = _run_sh("PreToolUse", BASH_TOOL, root, home, path=path,
                           env_extra={"CREW_HOOK_TRACE_FILE": str(trace)})

    assert code == 0, err
    assert "exit 49" not in err
    assert sorted(line.split()[1] for line in h.read_text(str(trace)).splitlines()) == [
        "cloud-guard.sh", "env-guard.sh", "promote-gate.sh", "scope-guard.sh"]


@needs_launcher_bash
@pytest.mark.skipif(os.name != "nt", reason="this is the Windows registration: the sh launcher must run, not exit 0")
def test_on_windows_the_sh_launcher_runs_every_row_exactly_once_and_blocks_what_it_blocked(tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)
    trace = tmp_path / "trace.crew-trace"
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write", "session_id": "s-1",
                          "tool_input": {"file_path": os.path.join(root, "docs", "nope.md"), "content": "x"}}).encode()

    code, _, err = _run_sh("PreToolUse", payload, root, home, env_extra={"CREW_HOOK_TRACE_FILE": str(trace)})

    ran = [line.split()[1] for line in h.read_text(str(trace)).splitlines()]
    assert sorted(ran) == ["role-write-guard.sh", "scope-guard.sh"]
    assert code == 2 and err.strip()


# --- the direct route and the wrapper agree on the recorded cases ----------------------------------

KEEP = {"bash-approval-forgery", "bash-cloud-blocked", "bash-declared-deploy", "bash-env-dump",
        "bash-out-of-touch-redirect", "edit-out-of-touch", "write-restricted-role", "approve-unknown", "plain"}


def _equivalence_keys():
    keys = sorted((k for k in rgh.load_golden()
                   if not k[0] and k[4] and not k[3] and k[1] in ("PreToolUse", "UserPromptSubmit", "PostToolUse")
                   and rgh.load_golden()[k]["harness"] == "claude" and rgh.load_golden()[k]["rows"]), key=h.golden_ids)
    return [pytest.param(k, id=h.golden_ids(k), marks=() if k[2] in KEEP else (crew_fixtures.SLOW,)) for k in keys]


def _run_route(record, base, direct):
    root, home = rgh.build_repo(str(base), record["armed"], record.get("dirty") or None)
    env = rgh.env_for(root, home)
    code, out, err = crew_hook.dispatch(record["event"], record["harness"], h.payload_bytes(record, root),
                                        crew_hook.now_ms() + 120000, env, root, windows=h.WINDOWS, direct=direct)
    return code, rgh.normalise(out.decode("utf-8", "replace"), root, home), rgh.normalise(err.decode("utf-8", "replace"),
                                                                                          root, home)


@pytest.mark.skipif(shutil.which("git") is None or (h.WINDOWS and GIT_BASH is None) or (not h.WINDOWS and h.BASH is None),
                    reason="needs git and a bash: the wrapper route was NOT run")
@pytest.mark.parametrize("key", _equivalence_keys())
def test_the_direct_route_gives_the_wrappers_exit_stdout_and_stderr(key, tmp_path):
    record = rgh.load_golden()[key]

    wrapper = _run_route(record, tmp_path / "wrapper", False)
    direct = _run_route(record, tmp_path / "direct", True)

    assert direct == wrapper
