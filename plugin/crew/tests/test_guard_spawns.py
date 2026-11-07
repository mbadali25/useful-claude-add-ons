"""crew 1.2.115: the guards' allow path starts no helper processes in bash.

On Git Bash every process start is an MSYS fork (~0.15s measured on the
Windows host, against 9-21ms for a native process), and the PreToolUse guards
run on every Bash call of every lane at once. Peers measured guard timeouts
coming back with three or more lanes in parallel, each guard 0.4-1.0s alone:
contention. So the allow path of cloud-guard.sh, env-guard.sh and
promote-gate.sh was cut to the python that judges (and, for promote-gate.sh,
the one `cat` that reads the payload for its PowerShell hand-off):
`crew_strip_cr` and the CREW_PYTHON check became parameter expansions,
`crew_native_path` reads `$OSTYPE` and passes a mixed `D:/...` path through,
`$DIR` comes from `${BASH_SOURCE[0]%/*}`, the clock from printf's `%(%s)T`,
and promote-gate.sh proves "no deploy" in one python (_promote_fast.py).

This runs each guard with `bash -x` on a command that deploys nothing, in a
repo whose guards are armed and whose deploy map is committed, and fails if a
helper program comes back on that path. It reads bash's own trace, so it sees
what bash starts, not what python starts.
"""
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_SCRIPTS = pathlib.Path(context._ROOT) / "hooks" / "scripts"  # pylint: disable=protected-access
_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash not installed - the sh flavour was NOT run")

# Never on the allow path any more. `cygpath` and `git` stay legal elsewhere
# (a Cygwin CREW_PYTHON, the full promote gate); on this path they are a regression.
_HELPERS = {"tr", "dirname", "uname", "cut", "cygpath", "date", "jq", "sed", "awk", "git",
            "basename", "head", "wc", "grep"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")


def _repo(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"guards": {"cloudGuard": "block", "envGuard": "block"}}), encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps({"environments": {"prod": {
        "deploy": "deploy-prod", "rollback": "none", "rollbackReason": "fixture"}}}),
        encoding="utf-8")
    for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                 ["config", "user.name", "T"], ["config", "core.autocrlf", "false"],
                 ["add", "-A", "-f"], ["commit", "-q", "-m", "fixture"]):
        subprocess.run(["git"] + args, cwd=root, check=True, capture_output=True)
    return root


def _traced(script, root, tmp_path, command="echo hi"):
    env = crew_fixtures.isolated_home_env(tmp_path / "home")
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["PS4"] = "+ "
    # What crew-hook.sh / crew-hook.ps1 export: the interpreter they already ran.
    env["CREW_PYTHON"] = sys.executable
    # The dispatcher starts every .sh by a forward-slash path (crew_hook._argv_for).
    path = str(_SCRIPTS / script).replace("\\", "/")
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": command}, "cwd": str(root), "session_id": "s"}
    proc = subprocess.run([_BASH, "-x", path], input=json.dumps(payload), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, cwd=str(root),
                          check=False, timeout=170)
    return proc


def _programs(trace):
    """Every command word in a bash -x trace that names a program, by basename."""
    found = []
    for line in trace.splitlines():
        match = re.match(r"^\++ (.*)$", line)
        if not match:
            continue
        try:
            words = shlex.split(match.group(1))
        except ValueError:
            words = match.group(1).split()
        while words and _ASSIGN.match(words[0]):
            words.pop(0)
        if words:
            found.append(words[0].replace("\\", "/").rsplit("/", 1)[-1])
    return found


def _python_runs(programs):
    return [p for p in programs if re.match(r"^(python[0-9.]*|py)(\.exe)?$", p, re.I)]


@needs_bash
@pytest.mark.parametrize("script", ["cloud-guard.sh", "env-guard.sh", "promote-gate.sh"])
def test_the_allow_path_starts_no_helper_programs(tmp_path, script):
    root = _repo(tmp_path)
    proc = _traced(script, root, tmp_path)
    programs = _programs(proc.stderr)

    assert proc.returncode == 0, proc.stderr[-4000:]
    assert '"deny"' not in proc.stdout, proc.stdout
    helpers = sorted(set(programs) & _HELPERS)
    assert helpers == [], f"{script} started {helpers} on the allow path:\n{proc.stderr[-4000:]}"
    assert len(_python_runs(programs)) == 1, programs
    # promote-gate.sh keeps the one `cat` that reads the payload for its
    # PowerShell hand-off; the thin wrappers let python read stdin itself.
    assert programs.count("cat") == (1 if script == "promote-gate.sh" else 0), programs


@needs_bash
def test_a_declared_deploy_still_takes_the_full_gate(tmp_path):
    """The control: the fast path refuses a deploy, and the full gate (git,
    the second python) runs and blocks it, here for the missing PASS row."""
    root = _repo(tmp_path)
    proc = _traced("promote-gate.sh", root, tmp_path, command="deploy-prod --now")
    programs = _programs(proc.stderr)

    assert proc.returncode == 2, proc.stderr[-4000:]
    assert "git" in programs, programs
    assert len(_python_runs(programs)) > 1, programs
