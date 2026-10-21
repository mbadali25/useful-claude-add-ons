"""On Windows the PowerShell launcher is the single path (L-0727, A9).

crew-hook.sh exits 0 there; crew-hook.ps1 runs the dispatcher, which runs `.sh`
children through a strictly resolved Git Bash and sends a `PowerShell` tool call
to a row's PowerShell twin when the file exists (promote-gate; cloud-guard and
env-guard are judged by their `.sh` for a `PowerShell` call). With no strict Git Bash
an armed repo is refused on PreToolUse, UserPromptSubmit and Stop, SessionStart gets one `systemMessage`, and every other
event exits 0.

What runs on any host here is what can be modelled honestly: the launcher's
"not on Windows" exit with a stubbed `uname` and with `OS=Windows_NT`; the Windows
routing of `select`; the no-Git-Bash policy of `dispatch` with a stub resolver; and
a `PowerShell` cloud call judged by `cloud-guard.sh` end to end under pwsh with
`OS=Windows_NT`. The cases that need a
real Windows host (both registrations on one payload with an exactly-once trace,
the side effects counted once, native PowerShell must-block payloads, the resume
status line under Git Bash, Git Bash hidden for the approval hook) skip off Windows
WITH the reason printed, and spec A10 makes the win-repo-2 run of this file
mandatory: a skipped run there is a failed acceptance, not a pass.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_hook
import crew_hook_harness as h
import record_golden_hooks as rgh

ON_WINDOWS = h.WINDOWS
native = pytest.mark.skipif(not ON_WINDOWS, reason="needs a real Windows host: the win-repo-2 run is spec A10's "
                            "evidence, and a skip there is a failed acceptance")
needs_pwsh = h.needs_pwsh


def _payload(tool, **tool_input):
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                       "session_id": "s-1"}).encode()


# --- crew-hook.sh stands down on Windows ----------------------------------------

def _stub_uname(tmp_path, text):
    folder = tmp_path / "unamebin"
    folder.mkdir()
    (folder / "uname").write_text(f'#!/bin/sh\necho "{text}"\n', encoding="utf-8")
    (folder / "uname").chmod(0o755)
    return str(folder)


@h.needs_bash
@pytest.mark.skipif(ON_WINDOWS, reason="a POSIX shell stub models uname here")
@pytest.mark.parametrize("uname", ["MINGW64_NT-10.0-26100", "MSYS_NT-10.0", "CYGWIN_NT-10.0"])
def test_crew_hook_sh_exits_0_without_dispatching_when_uname_says_windows(uname, tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)
    trace = tmp_path / "trace.crew-trace"
    path = _stub_uname(tmp_path, uname) + os.pathsep + os.environ["PATH"]

    code, out, err = h.run_launcher("sh", "PreToolUse", _payload("Bash", command="ls"), root, home, path=path,
                                    env_extra={"CREW_HOOK_TRACE_FILE": str(trace)})

    assert (code, out) == (0, "")
    assert not trace.exists(), err


@h.needs_bash
@pytest.mark.skipif(ON_WINDOWS, reason="a POSIX shell models the OS variable here")
def test_an_os_variable_cannot_stand_the_guards_down_on_a_posix_host(tmp_path):
    """Security pass (L-0850): `OS=Windows_NT` in the hook environment, set by anything, must not make
    a Linux or macOS host skip every guard. uname says Linux, so the variable says nothing."""
    root, home = rgh.build_repo(str(tmp_path), True)
    trace = tmp_path / "trace.crew-trace"

    code, _, err = h.run_launcher("sh", "PreToolUse", _payload("Bash", command="ls"), root, home,
                                  env_extra={"OS": "Windows_NT", "CREW_HOOK_TRACE_FILE": str(trace)})

    assert code == 0, err
    assert trace.exists() and "cloud-guard.sh" in h.read_text(str(trace))


@h.needs_bash
@pytest.mark.skipif(ON_WINDOWS, reason="a POSIX shell stub models uname here")
@pytest.mark.parametrize("uname", ["Interix", ""])
def test_crew_hook_sh_honours_os_windows_nt_only_when_uname_is_not_a_posix_kernel(uname, tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)
    trace = tmp_path / "trace.crew-trace"
    path = _stub_uname(tmp_path, uname) + os.pathsep + os.environ["PATH"]

    code, out, _ = h.run_launcher("sh", "PreToolUse", _payload("Bash", command="ls"), root, home, path=path,
                                  env_extra={"OS": "Windows_NT", "CREW_HOOK_TRACE_FILE": str(trace)})

    assert (code, out) == (0, "") and not trace.exists()


@h.needs_bash
@pytest.mark.skipif(ON_WINDOWS, reason="a POSIX shell stub models uname here")
def test_crew_hook_sh_dispatches_when_uname_cannot_be_read_and_os_is_unset(tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)
    trace = tmp_path / "trace.crew-trace"
    folder = tmp_path / "brokenuname"
    folder.mkdir()
    (folder / "uname").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (folder / "uname").chmod(0o755)

    code, _, err = h.run_launcher("sh", "PreToolUse", _payload("Bash", command="ls"), root, home,
                                  path=str(folder) + os.pathsep + os.environ["PATH"],
                                  env_extra={"CREW_HOOK_TRACE_FILE": str(trace)})

    assert code == 0, err
    assert trace.exists() and "cloud-guard.sh" in trace.read_text(encoding="utf-8")


# --- the Windows routing of select ----------------------------------------------

def _argvs(tool, windows, exists=os.path.isfile):
    return [argv for _, argv in crew_hook.select("PreToolUse", "claude", {"tool_name": tool}, windows=windows,
                                                 exists=exists)]


def test_a_power_shell_call_on_windows_goes_to_the_promote_gate_twin_and_the_sh_rows():
    got = _argvs("PowerShell", True)

    assert got == [["promote-gate.ps1"], ["cloud-guard.sh"], ["env-guard.sh"], ["scope-guard.sh"]]


def test_a_power_shell_call_on_windows_uses_the_sh_when_no_twin_file_exists():
    got = _argvs("PowerShell", True, exists=lambda _path: False)

    assert got == [["cloud-guard.sh"], ["env-guard.sh"], ["scope-guard.sh"]]


def test_a_power_shell_call_off_windows_never_selects_a_twin():
    assert _argvs("PowerShell", False) == [["cloud-guard.sh"], ["env-guard.sh"], ["scope-guard.sh"]]


@pytest.mark.parametrize("windows", [True, False])
def test_a_bash_call_selects_the_same_sh_rows_on_either_os(windows):
    assert _argvs("Bash", windows) == [["promote-gate.sh"], ["cloud-guard.sh"], ["env-guard.sh"],
                                       ["scope-guard.sh"]]


# --- no strict Git Bash ---------------------------------------------------------

def _no_bash(event, armed):
    payload = json.dumps({"hook_event_name": event, "tool_name": "Bash", "tool_input": {"command": "ls"}}).encode()
    return crew_hook.dispatch(event, "claude", payload, crew_hook.now_ms() + 20000, dict(os.environ), "/nowhere",
                              windows=True, resolve_bash=lambda strict=True: (None, "Git Bash not found (strict)"),
                              armed_fn=lambda _root: armed)


@pytest.mark.parametrize("event", ["PreToolUse", "UserPromptSubmit", "Stop"])
def test_armed_with_no_git_bash_the_blocking_events_exit_2_naming_git_for_windows(event):
    code, out, err = _no_bash(event, True)

    assert code == 2 and out == b""
    assert b"Git for Windows" in err


@pytest.mark.parametrize("event", ["PreToolUse", "UserPromptSubmit", "Stop"])
def test_unarmed_with_no_git_bash_the_blocking_events_exit_0(event):
    code, _, err = _no_bash(event, False)

    assert code == 0 and b"Git for Windows" in err


def test_session_start_with_no_git_bash_prints_one_system_message():
    code, out, _ = _no_bash("SessionStart", True)

    message = json.loads(out)["systemMessage"]
    assert code == 0 and "Git for Windows" in message and out.count(b"systemMessage") == 1


@pytest.mark.parametrize("event", ["PostToolUse", "SubagentStart", "PreCompact", "Notification"])
def test_the_other_events_with_no_git_bash_exit_0(event):
    code, out, _ = _no_bash(event, True)

    assert code == 0 and out == b""


# --- a PowerShell call judged by the .sh end to end (pwsh with OS=Windows_NT on a POSIX host) ---

@needs_pwsh
@h.needs_bash
@pytest.mark.skipif(ON_WINDOWS, reason="this models the routing; the native run is the other test")
def test_a_power_shell_cloud_call_is_judged_by_cloud_guard_sh_and_denied(tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)
    trace = tmp_path / "trace.crew-trace"
    env = rgh.env_for(root, home)
    env.update(OS="Windows_NT", CREW_HOOK_TRACE_FILE=str(trace))
    payload = _payload("PowerShell", command=rgh.CLOUD)
    code, out, err = crew_hook.dispatch("PreToolUse", "claude", payload, crew_hook.now_ms() + 60000, env, root,
                                        windows=True, resolve_bash=lambda strict=True: (h.BASH, "stub"),
                                        resolve_pwsh=lambda: (h.PWSH, "stub"))

    ran = trace.read_text(encoding="utf-8")
    assert code == 0, err
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "cloud-guard.sh" in ran and "cloud-guard.ps1" not in ran


# --- native Windows ---------------------------------------------------------------

def _run_both_registrations(event, payload, root, home, trace):
    """Both launchers on one payload, as the two registrations run them."""
    results = []
    for flavour in ("sh", "ps1"):
        argv = h.launcher_argv(flavour, event)
        if flavour == "sh" and h.BASH is None:
            continue
        env = rgh.env_for(root, home)
        env["CREW_HOOK_TRACE_FILE"] = trace
        done = subprocess.run(argv, input=payload, capture_output=True, env=env, cwd=root, timeout=180, check=False)
        results.append((flavour, done.returncode, done.stdout.decode("utf-8", "replace"),
                        done.stderr.decode("utf-8", "replace")))
    return results


@native
def test_both_registrations_on_one_payload_run_every_applicable_row_exactly_once(tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)
    trace = str(tmp_path / "trace.crew-trace")

    results = _run_both_registrations("PreToolUse", _payload("Bash", command="ls"), root, home, trace)

    ran = [line.split()[1] for line in h.read_text(trace).splitlines()]
    assert sorted(ran) == sorted(["promote-gate.sh", "cloud-guard.sh", "env-guard.sh", "scope-guard.sh"]), results
    assert all(code == 0 for _, code, _, _ in results), results


# The golden is recorded from the per-script `.sh` run, which never sees a PowerShell tool call; on
# Windows the promote-gate twin DOES run for one, and blocks a declared deploy in this fixture (no
# rollback runbook). That divergence is the point of the twin, and
# test_a_power_shell_declared_deploy_is_blocked_natively_by_promote_gate_ps1 pins it.
TWIN_BLOCKS_NATIVELY = frozenset({"powershell-declared-deploy"})


@native
@pytest.mark.parametrize("case", sorted(k for k in rgh.load_golden()
                                        if not k[0] and k[4] and not k[3] and k[2] not in TWIN_BLOCKS_NATIVELY),
                         ids=h.golden_ids)
def test_both_registrations_together_equal_the_golden_single_result(case, tmp_path):
    record = rgh.load_golden()[case]
    root, home = rgh.build_repo(str(tmp_path), True, record.get("dirty") or None)
    trace = str(tmp_path / "trace.crew-trace")

    results = _run_both_registrations(record["event"], h.payload_bytes(record, root), root, home, trace)

    want = h.expected(record)
    combined_code = 2 if any(code == 2 for _, code, _, _ in results) else 0
    assert combined_code == want["exit"], results
    ps = next(r for r in results if r[0] == "ps1")
    h.assert_same(want, (ps[1], ps[2], ps[3]), root, home, strict=False)


@native
def test_notify_and_handoff_write_side_effects_are_counted_once(tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)
    trace = str(tmp_path / "trace.crew-trace")
    for event, name, extra in (("Notification", "notify.sh", {"notification_type": "idle_prompt", "message": "x"}),
                               ("PreCompact", "handoff-write.sh", {"trigger": "manual"})):
        payload = json.dumps({"hook_event_name": event, "session_id": "s-1", **extra}).encode()

        _run_both_registrations(event, payload, root, home, trace)

        ran = [line.split()[1] for line in h.read_text(trace).splitlines()]
        assert ran.count(name) == 1, (event, ran)


@native
def test_a_power_shell_cloud_call_is_denied_natively(tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)

    code, out, err = h.run_launcher("ps1", "PreToolUse", _payload("PowerShell", command=rgh.CLOUD), root, home)

    assert code == 0, err
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


@native
def test_a_power_shell_declared_deploy_is_blocked_natively_by_promote_gate_ps1(tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)

    code, _, err = h.run_launcher("ps1", "PreToolUse", _payload("PowerShell", command="deploy-prod"), root, home)

    assert code == 2, err


@native
@pytest.mark.parametrize("source", ["clear", "compact"])
def test_session_start_clear_and_compact_yield_the_auto_resume_status_line(source, tmp_path):
    root, home = rgh.build_repo(str(tmp_path), True)
    os.makedirs(os.path.join(home, ".claude", "crew"), exist_ok=True)
    with open(os.path.join(home, ".claude", "crew", "config.json"), "w", encoding="utf-8") as handle:
        json.dump({"resume": {"auto": True}, "context": {"autoClear": {"enabled": True, "method": "auto"}}}, handle)
    payload = json.dumps({"hook_event_name": "SessionStart", "source": source, "session_id": "s-1",
                          "cwd": root}).encode()

    code, out, err = h.run_launcher("ps1", "SessionStart", payload, root, home)

    assert code == 0, err
    assert "Auto-resume" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


@native
def test_the_approval_hook_is_refused_with_git_bash_hidden(tmp_path):
    """UserPromptSubmit exits 2 naming Git for Windows. Git Bash is hidden by replacing the
    resolver inside the real dispatcher process; everything else is the native path."""
    root, home = rgh.build_repo(str(tmp_path), True)
    driver = ("import sys, crew_shell, crew_hook\n"
              "crew_shell.resolve_gitbash = lambda strict=False: (None, 'Git Bash hidden for this test')\n"
              "sys.exit(crew_hook.main(['UserPromptSubmit']))\n")
    env = rgh.env_for(root, home)
    env["PYTHONPATH"] = h.SCRIPTS
    payload = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "/crew:approve T-2",
                          "session_id": "s-1"}).encode()

    done = subprocess.run([sys.executable, "-c", driver], input=payload, capture_output=True, env=env, cwd=root,
                          timeout=120, check=False)

    assert done.returncode == 2, done.stderr
    assert b"Git for Windows" in done.stderr
