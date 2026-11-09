"""crew 1.3.18: the scope guard's allow path starts as few processes as it can.

scope-guard.sh runs before every Write, Edit and Bash call of every lane at
once. On Git Bash each process start is an MSYS fork (~0.15s measured on the
Windows host), and srl-ai saw `scope-guard.sh timed out ... failing closed`
with a single lane. Measured on the allow path (a Write inside Touch of an
approved ticket) before this change: `dirname` and `cat` in the wrapper, and
EIGHT `git rev-parse` processes from scope_guard.py / crew_ticket.py (the same
two answers, the worktree top and the git-common-dir, asked again at every
step); ~1.27s median. After: no helper in bash, one `git rev-parse`.

Decisions are not under test here (test_scope_guard.py holds every must-block
and must-allow case); this holds the COST of reaching an allow, and the memo's
own contract: per process, keyed by the directory asked, never freezing a
"git could not tell".
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
import crew_ticket
from scope_fixtures import make_repo, ready

_SCRIPTS = pathlib.Path(context._ROOT) / "hooks" / "scripts"  # pylint: disable=protected-access
_BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash not installed - the sh flavour was NOT run")

# Never on the allow path any more.
_HELPERS = {"tr", "dirname", "uname", "cut", "cygpath", "date", "jq", "sed", "awk", "git",
            "basename", "head", "wc", "grep", "cat"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")

_SITE = '''import json, os, subprocess
_orig = subprocess.Popen.__init__
def _init(self, args, *a, **k):
    with open(os.environ["SPAWN_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(args if isinstance(args, list) else [str(args)]) + "\\n")
    return _orig(self, args, *a, **k)
subprocess.Popen.__init__ = _init
'''

_WRITE = "write-in-touch"
_BASH_CMD = "bash-echo"


def _payload(root, case):
    if case == _WRITE:
        return {"tool_name": "Write", "tool_input": {"file_path": str(root / "src" / "app.py")}}
    return {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}


def _armed_repo(tmp_path):
    root = make_repo(tmp_path, mode="block")
    ready(root)
    return root


def _env(root, tmp_path):
    env = crew_fixtures.isolated_home_env(tmp_path / "home")
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env["CREW_PYTHON"] = sys.executable
    return env


def _programs(trace):
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


def _spawned(tmp_path, root, case, argv, extra_env=None):
    """Run a guard with every subprocess the python start is logged; returns
    (completed process, the logged argvs)."""
    site = tmp_path / "site"
    site.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(_SITE, encoding="utf-8")
    log = tmp_path / f"spawn-{case}.log"
    env = _env(root, tmp_path)
    env["SPAWN_LOG"] = str(log)
    env["PYTHONPATH"] = str(site)
    env.update(extra_env or {})
    payload = dict(_payload(root, case), hook_event_name="PreToolUse", cwd=str(root),
                   session_id="s")
    proc = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, cwd=str(root),
                          check=False, timeout=170)
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return proc, [json.loads(line) for line in lines]


def _git_spawns(spawned):
    return [a for a in spawned if os.path.basename(a[0]).lower().startswith("git")]


@pytest.mark.parametrize("case", [_WRITE, _BASH_CMD])
def test_the_allow_path_asks_git_once(tmp_path, case):
    root = _armed_repo(tmp_path)
    proc, spawned = _spawned(tmp_path, root, case,
                             [sys.executable, str(_SCRIPTS / "scope_guard.py")])

    assert proc.returncode == 0, proc.stderr
    git = _git_spawns(spawned)
    assert len(git) == 1, git
    # ONE rev-parse carries both answers the guard needs.
    assert git[0][-3:] == ["rev-parse", "--show-toplevel", "--git-common-dir"], git


@needs_bash
@pytest.mark.parametrize("case", [_WRITE, _BASH_CMD])
def test_the_bash_wrapper_starts_no_helper_programs(tmp_path, case):
    root = _armed_repo(tmp_path)
    path = str(_SCRIPTS / "scope-guard.sh").replace("\\", "/")  # as crew_hook._argv_for does
    proc, spawned = _spawned(tmp_path, root, case, [_BASH, "-x", path], {"PS4": "+ "})
    programs = _programs(proc.stderr)

    assert proc.returncode == 0, proc.stderr[-4000:]
    helpers = sorted(set(programs) & _HELPERS)
    assert helpers == [], f"scope-guard.sh started {helpers} on the allow path:\n{proc.stderr[-4000:]}"
    assert len(_python_runs(programs)) == 1, programs
    assert len(_git_spawns(spawned)) == 1, spawned


@needs_bash
def test_the_bash_wrapper_still_hands_python_the_payload(tmp_path):
    """The control for dropping `INPUT=$(cat)`: python reads the payload from
    the wrapper's own stdin, so a write outside Touch is still refused (exit 2
    with the reason), not judged on an empty payload."""
    root = _armed_repo(tmp_path)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(root),
               "tool_input": {"file_path": str(root / "other" / "keep.py")}}
    env = _env(root, tmp_path)
    proc = subprocess.run([_BASH, str(_SCRIPTS / "scope-guard.sh").replace("\\", "/")],
                          input=json.dumps(payload), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, cwd=str(root),
                          check=False, timeout=170)

    assert proc.returncode == 2, proc.stderr
    assert "other/keep.py" in proc.stderr


# --- the memo's contract ---------------------------------------------------------

@pytest.fixture(name="counted")
def _counted(monkeypatch):
    """Count the `git` processes crew_ticket starts; leave the memo as found."""
    calls = []
    real = crew_ticket._git  # pylint: disable=protected-access

    def counting(root, *args):
        calls.append((root, args))
        return real(root, *args)

    monkeypatch.setattr(crew_ticket, "_git", counting)
    monkeypatch.setattr(crew_ticket, "_GIT_MEMO", None)
    return calls


def test_without_the_memo_every_ask_reaches_git(tmp_path, counted):
    """Off unless asked: a long-lived caller must never see a stale answer."""
    root = make_repo(tmp_path)
    for _ in range(2):
        assert crew_ticket.toplevel(str(root))
        assert crew_ticket.common_dir(str(root))

    assert len(counted) == 4, counted


def test_with_the_memo_both_answers_cost_one_git(tmp_path, counted):
    root = make_repo(tmp_path)
    crew_ticket.memoize_git()
    first = (crew_ticket.toplevel(str(root)), crew_ticket.common_dir(str(root)))
    again = (crew_ticket.toplevel(str(root)), crew_ticket.common_dir(str(root)))

    assert first == again and all(first)
    assert len(counted) == 1, counted


def test_the_memo_is_keyed_by_the_directory_asked(tmp_path, counted):
    one = make_repo(tmp_path, name="one")
    two = make_repo(tmp_path, name="two")
    crew_ticket.memoize_git()

    assert crew_ticket.toplevel(str(one)) != crew_ticket.toplevel(str(two))
    assert crew_ticket.common_dir(str(one)) != crew_ticket.common_dir(str(two))
    assert len(counted) == 2, counted


def test_a_git_that_could_not_tell_is_asked_again(tmp_path, counted):
    """The unknown must not freeze: outside git the answer is None, and after a
    `git init` the same directory answers."""
    plain = tmp_path / "plain"
    plain.mkdir()
    crew_ticket.memoize_git()
    assert crew_ticket.toplevel(str(plain)) is None
    assert crew_ticket.common_dir(str(plain)) is None

    subprocess.run(["git", "init", "-q", str(plain)], check=True, capture_output=True)

    assert crew_ticket.toplevel(str(plain)) == os.path.realpath(str(plain))
    assert crew_ticket.common_dir(str(plain)) == os.path.realpath(str(plain / ".git"))


def test_a_bare_repo_keeps_its_half_answer(tmp_path, counted):
    """`--show-toplevel` fails in a bare repo while `--git-common-dir` answers;
    the combined ask fails whole, so each is asked on its own as before."""
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    crew_ticket.memoize_git()

    assert crew_ticket.toplevel(str(bare)) is None
    assert crew_ticket.common_dir(str(bare)) == os.path.realpath(str(bare))
