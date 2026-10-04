"""T-0082: a rule passes only on a completion record; killed or unrecorded is
FAILED (could not tell).

A Windows machine running `verify-gate.sh --all` for T-0077 saw a rule hang,
the runner killed at 2108s, and the gate record NO `VERIFY FAILED` for that
rule. Both gates decided pass from one number: the wrapper's exit status. A
kill that reported 0, or a PowerShell `& $bashExe` that never started (the
stale `$rc` of the previous rule), read as a pass.

Now the rule's wrapper writes the rule's exit status to a record file after
the rule ends, and one decision table, the same in both flavours, judges it:
no bash / no temp file -> unknown; wrapper never started -> unknown; wrapper
status not 0 -> unknown; record missing, empty, not 1-3 digits or above 255
-> unknown; record above 128 -> unknown; 77 skip; 0 pass; else fail. Unknown
prints `VERIFY FAILED: <cmd>` and `verify-gate: COULD NOT TELL (<reason>):
<cmd>`, fails the run, logs status `unknown` and never advances the marker.

Every `[ps1]` case runs wherever pwsh exists (OS=Windows_NT past the flavour
guard, as test_verify_gate_subset_cover.py does). A rule that kills its
wrapper never signals `$$` or `$PPID` under `[sh]`: those are the gate and
this test. The native-Windows run the spec asks for is not done here.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(_PWSH is None or _BASH is None,
                                                 reason="needs pwsh and bash")),
]
_NOT_POSIX_PROC = not os.path.isdir("/proc/self")

_TELL = "verify-gate: COULD NOT TELL ("


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S).stdout


def _repo(tmp_path, run):
    """A committed fixture repo with one rule per command in `run`."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text(".crew/.verify*\n", encoding="utf-8")
    rules = [{"paths": ["a.py"], "seconds": 1, "reach": "local", "run": [c]} for c in run]
    (root / ".crew" / "verify.json").write_text(
        json.dumps({"version": 1, "rules": rules, "default": [], "unmapped": "ignore"}),
        encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _cmd(flavour):
    if flavour == "sh":
        return [_BASH, _SH, "--all"]
    return [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1, "-All"]


def _env(flavour, root, extra=None):
    full = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    full.pop("PYTEST_ADDOPTS", None)
    if flavour == "ps1" and not sys.platform.startswith("win"):
        full["OS"] = "Windows_NT"
    full.update(extra or {})
    return full


def _run(flavour, root, env=None):
    return crew_fixtures.run_gate(_cmd(flavour), input="{}", cwd=str(root),
                                  env=_env(flavour, root, env), capture_output=True,
                                  text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _marker(root):
    p = root / ".crew" / ".verify-verified-at"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


def _wrapper_pid(flavour):
    """Shell text that sets $w to the pid of the rule's wrapper: the parent of
    the subshell the rule is evaluated in. Under [sh] that must never be the
    gate ($$) or this test ($PPID); the rule refuses with exit 5 if it is."""
    text = "read -r _ _ _ w _ < /proc/$BASHPID/stat; "
    if flavour == "sh":
        text += ('if [ "$w" = "$$" ] || [ "$w" = "$PPID" ]; then '
                 "echo 'refusing''-to-signal-the-gate'; exit 5; fi; ")
    return text


# --- must allow --------------------------------------------------------------

@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_that_exits_0_passes(flavour, tmp_path):
    root = _repo(tmp_path, ["echo all-good"])

    res = _run(flavour, root)

    assert res.returncode == 0, res.stderr
    assert _marker(root) == _git(root, "rev-parse", "HEAD").strip()
    assert "COULD NOT TELL" not in res.stderr
    assert "COULD NOT BE JUDGED" not in res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_plain_failure_and_skip_are_unchanged(flavour, tmp_path):
    root = _repo(tmp_path, ["exit 1", "exit 77"])

    res = _run(flavour, root)

    assert res.returncode == 2, res.stderr
    assert "VERIFY FAILED: exit 1" in res.stderr
    assert "verify-gate: SKIP (rc 77, environment absent): exit 77" in res.stderr
    assert "VERIFY FAILED: exit 77" not in res.stderr
    assert "COULD NOT TELL" not in res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_with_its_own_exit_or_trap_passes(flavour, tmp_path):
    """The record is written by the wrapper OUTSIDE the rule's own subshell, so
    a rule's `exit 0` or its own EXIT trap cannot skip the write."""
    root = _repo(tmp_path, ["exit 0", "trap 'echo bye' EXIT; echo hi"])

    res = _run(flavour, root)

    assert res.returncode == 0, res.stderr
    assert "COULD NOT TELL" not in res.stderr
    assert _marker(root) is not None


# --- must block --------------------------------------------------------------

@pytest.mark.skipif(_NOT_POSIX_PROC, reason="needs /proc")
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_killed_mid_run_could_not_tell(flavour, tmp_path):
    cmd = "echo started; kill -KILL $BASHPID; echo never"
    root = _repo(tmp_path, [cmd])

    res = _run(flavour, root)

    assert res.returncode == 2, res.stderr
    assert f"VERIFY FAILED: {cmd}" in res.stderr
    assert (f"{_TELL}exit status 137: ended by signal 9, or the rule's own status): "
            f"{cmd}") in res.stderr
    assert _marker(root) is None


@pytest.mark.skipif(_NOT_POSIX_PROC, reason="needs /proc")
@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("how", [
    "wrapper-killed",
    pytest.param("record-vanished", marks=pytest.mark.skipif(
        sys.platform.startswith("win"), reason="MSYS `ln -s` copies instead of linking")),
])
def test_no_completion_record_could_not_tell(flavour, how, tmp_path):
    """`wrapper-killed`: the rule ends its wrapper before the record exists.
    `record-vanished`: the wrapper ends 0 but its record lands nowhere (the
    rule points the record path at /dev/null) - the shape a native kill that
    reports exit 0 would leave, which only the record can catch."""
    if how == "wrapper-killed":
        cmd = _wrapper_pid(flavour) + 'kill -KILL "$w"; sleep 1'
        reason = "the rule's runner ended with status 137 before it recorded a result"
    else:
        cmd = 'ln -sf /dev/null "$RULE_DONE_FILE"; echo pointed-away'
        reason = "no completion record"
    root = _repo(tmp_path, [cmd])

    res = _run(flavour, root)

    assert res.returncode == 2, res.stderr
    assert "refusing-to-signal-the-gate" not in res.stderr
    assert f"VERIFY FAILED: {cmd}" in res.stderr
    assert f"{_TELL}{reason}): {cmd}" in res.stderr
    assert _marker(root) is None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("value", ["", "abc\\n", "256\\n"], ids=["empty", "text", "256"])
def test_unreadable_record_could_not_tell(flavour, value, tmp_path):
    """The record path is a shell variable the rule can see. The rule points
    it at a FIFO and leaves a background job that outlives it: the job drains
    the wrapper's own write, then hands the gate's read the bad value. A FIFO
    orders the three without a race: each open blocks until its peer opens."""
    fifo = (tmp_path / "rec").as_posix()
    cmd = (f'mkfifo {fifo}; ln -sf {fifo} "$RULE_DONE_FILE"; '
           f"( cat {fifo} >/dev/null; printf '{value}' > {fifo} ) &")
    root = _repo(tmp_path, [cmd])

    res = _run(flavour, root)

    assert res.returncode == 2, res.stderr
    assert f"{_TELL}no completion record): {cmd}" in res.stderr


@pytest.mark.skipif(_PWSH is None or _BASH is None, reason="needs pwsh and bash")
def test_ps1_launch_failure_does_not_inherit_the_previous_status(tmp_path):
    """The first rule passes and removes the bash the gate resolved; the second
    rule's `& $bashExe` cannot start. Before T-0082 `$rc` still held the first
    rule's 0 and the second rule passed without running."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    os.symlink(shutil.which("bash") or _BASH, bindir / "bash")
    first = f"rm -f {(bindir / 'bash').as_posix()}"
    second = "echo second-rule-ran"
    root = _repo(tmp_path, [first, second])

    res = _run("ps1", root, env={"PATH": str(bindir) + os.pathsep + os.environ["PATH"]})

    assert res.returncode == 2, res.stderr
    assert f"VERIFY FAILED: {first}" not in res.stderr
    assert f"{_TELL}the rule's shell could not be started): {second}" in res.stderr
    assert _marker(root) is None


@pytest.mark.skipif(_NOT_POSIX_PROC or shutil.which("timeout") is None,
                    reason="needs /proc and timeout(1)")
@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("where", ["rule-child", "wrapper"])
def test_a_rule_timed_out_from_outside_is_failed(flavour, where, tmp_path):
    if where == "rule-child":
        cmd = "timeout -s KILL 1 sleep 10"
        reason = "exit status 137: ended by signal 9, or the rule's own status"
    else:
        cmd = _wrapper_pid(flavour) + '( sleep 1; kill -KILL "$w" ) & sleep 4'
        reason = "the rule's runner ended with status 137 before it recorded a result"
    root = _repo(tmp_path, [cmd])

    res = _run(flavour, root)

    assert res.returncode == 2, res.stderr
    assert f"VERIFY FAILED: {cmd}" in res.stderr
    assert f"{_TELL}{reason}): {cmd}" in res.stderr


@pytest.mark.skipif(_NOT_POSIX_PROC, reason="needs /proc")
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_unknown_never_advances_the_marker(flavour, tmp_path):
    log = (tmp_path / "later.log").as_posix()
    root = _repo(tmp_path, ["kill -KILL $BASHPID", f"echo later >> {log}"])

    res = _run(flavour, root)

    assert res.returncode == 2, res.stderr
    assert _marker(root) is None
    assert not (root / ".crew" / ".verify-gate.fingerprint").exists()
    assert (tmp_path / "later.log").read_text(encoding="utf-8").split() == ["later"]
    assert ("verify-gate: 1 rule command(s) COULD NOT BE JUDGED - counted as FAILED"
            in res.stderr)


@pytest.mark.skipif(_NOT_POSIX_PROC, reason="needs /proc")
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_unknown_status_is_never_recorded_clean(flavour, tmp_path):
    """Same command text both runs, so the same record key: first it SKIPs (a
    record entry), then it is killed. The kill must leave that entry as it
    was and must not reach the tree-pass cache."""
    mode = tmp_path / "mode"
    mode.write_text("skip", encoding="utf-8")
    cmd = f"case $(cat {mode.as_posix()}) in skip) exit 77;; kill) kill -KILL $BASHPID;; esac"
    root = _repo(tmp_path, [cmd])
    record = root / ".crew" / ".verify-gate.record.json"

    first = _run(flavour, root)
    assert first.returncode == 0, first.stderr
    before = json.loads(record.read_text(encoding="utf-8"))
    assert before, "the SKIP must have left a record entry"

    mode.write_text("kill", encoding="utf-8")
    second = _run(flavour, root)

    assert second.returncode == 2, second.stderr
    assert _TELL in second.stderr
    assert json.loads(record.read_text(encoding="utf-8")) == before
    passes = root / ".crew" / ".verify-gate.passes.json"
    assert cmd not in (passes.read_text(encoding="utf-8") if passes.exists() else "")


def _tr_shim(tmp_path, armed, flag):
    """A `tr` on PATH that, once `armed` exists, announces itself and holds 3s.
    The gate's first `tr` after a rule is the command-log line, which runs
    after the rule's wait has returned: TERM then lands with no rule in flight
    (bash defers the trap until that foreground pipeline ends)."""
    bindir = tmp_path / "trbin"
    bindir.mkdir()
    shim = bindir / "tr"
    shim.write_text(
        "#!/bin/sh\n"
        f"if [ -f {armed.as_posix()} ]; then : > {flag.as_posix()}; sleep 3; fi\n"
        f'exec {shutil.which("tr")} "$@"\n', encoding="utf-8", newline="\n")
    shim.chmod(0o755)
    return bindir


def _signal_gate_when(root, flag, env):
    payload = root.parent / "payload.json"
    payload.write_text("{}", encoding="utf-8")
    with open(payload, encoding="utf-8") as stdin:
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            _cmd("sh"), stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(root), env=_env("sh", root, env), text=True)
    deadline = time.monotonic() + 60
    while not flag.exists() and time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.05)
    assert flag.exists(), "the gate never reached the point under test"
    proc.send_signal(signal.SIGTERM)
    out, err = proc.communicate(timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    return proc.returncode, out, err


@pytest.mark.skipif(_BASH is None or os.name != "posix", reason="needs bash and POSIX signals")
def test_a_signalled_gate_names_the_command_in_flight(tmp_path):
    flag = tmp_path / "started"
    cmd = f": > {flag.as_posix()}; sleep 8"
    root = _repo(tmp_path, [cmd])

    code, _, err = _signal_gate_when(root, flag, None)

    assert code == 143, err
    assert f"VERIFY FAILED: {cmd}" in err
    assert (f"{_TELL}the gate received TERM while this command was running): {cmd}"
            in err)


@pytest.mark.skipif(_BASH is None or os.name != "posix" or shutil.which("tr") is None,
                    reason="needs bash, tr and POSIX signals")
def test_a_signalled_gate_with_no_rule_in_flight_names_nothing(tmp_path):
    """Must-allow twin: TERM lands after the only rule has finished, so there
    is no command to name."""
    flag = tmp_path / "after-the-rule"
    armed = tmp_path / "armed"
    root = _repo(tmp_path, [f": > {armed.as_posix()}"])
    bindir = _tr_shim(tmp_path, armed, flag)

    code, _, err = _signal_gate_when(
        root, flag, {"PATH": str(bindir) + os.pathsep + os.environ["PATH"]})

    assert code == 143, err
    assert "COULD NOT TELL" not in err
    assert "VERIFY FAILED" not in err


def _leftovers(root, tmpdir):
    crew = [n for n in os.listdir(root / ".crew") if n.startswith(".verify-rule-")]
    temp = [n for n in os.listdir(tmpdir) if os.path.isfile(os.path.join(tmpdir, n))
            and n.startswith("tmp")] if os.path.isdir(tmpdir) else []
    return crew + temp


@pytest.mark.skipif(_NOT_POSIX_PROC, reason="needs /proc")
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_no_record_file_is_left_behind(flavour, tmp_path):
    """Pass, fail and unknown: neither temp file is left in the temp dir or in
    `.crew/`. (The `.crew/` fallback is not driven here: with TMPDIR missing
    the sh gate refuses earlier, before any rule, for its own temp files.)"""
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    env = {"TMPDIR": str(tmpdir), "TMP": str(tmpdir), "TEMP": str(tmpdir)}
    root = _repo(tmp_path, ["echo ok", "exit 1", "kill -KILL $BASHPID"])

    res = _run(flavour, root, env=env)

    assert res.returncode == 2, res.stderr
    assert "VERIFY FAILED: exit 1" in res.stderr
    assert f"{_TELL}exit status 137" in res.stderr
    assert _leftovers(root, tmpdir) == []


@pytest.mark.skipif(_BASH is None or os.name != "posix", reason="needs bash and POSIX signals")
def test_a_signalled_gate_leaves_no_record_file(tmp_path):
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    flag = tmp_path / "started"
    root = _repo(tmp_path, [f": > {flag.as_posix()}; sleep 8"])

    code, _, err = _signal_gate_when(root, flag, {"TMPDIR": str(tmpdir)})

    assert code == 143, err
    assert _leftovers(root, tmpdir) == []
