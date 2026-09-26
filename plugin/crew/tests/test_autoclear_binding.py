"""auto-clear types only into a pane or window proven to be THIS session's (T-0016).

The proof starts at Claude Code's own session record, `~/.claude/sessions/
<pid>.json`: the record naming the payload's `session_id` must belong to a
live process, with the recorded start time, that is an ancestor of the hook,
and that is an interactive session with a controlling terminal. Only then
does each method's own check run, anchored on that process rather than on
the hook: tmux needs its tty to be the pane's, xdotool and the ps1 window
walk start from it.

Measured on Claude Code 2.1.282 (the spike, `.work/tickets/T-0016/spike.md`):
a `claude -p` child started from a parent's Bash tool inherits `$TMUX_PANE`,
has the parent's pane shell among its ancestors, writes a record whose
`kind` is still `interactive` -- but whose `entrypoint` is `sdk-cli` -- and
has no controlling tty. Before this change its Stop planned `send` into the
PARENT's pane.

Must-fire and must-not-fire pairs for each link of that proof, the headless
outcome (notify plus the parent-restart recipe, never a keystroke), and the
ssh / WSL boundary. Every case sets CREW_AUTOCLEAR_INHIBIT, points HOME at
its fixture, and stubs the tty read, the window list and tmux: nothing here
reads the developer's real `~/.claude/sessions/`, enumerates a real window,
or sends a keystroke.
"""
import json
import os
import subprocess
import sys
import threading
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autocycle
import crew_fixtures

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_SH = os.path.join(_SCRIPTS, "auto-clear.sh").replace("\\", "/")
_PS1 = os.path.join(_SCRIPTS, "auto-clear.ps1")
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="needs bash")
needs_pwsh = pytest.mark.skipif(
    _PWSH is None, reason="needs pwsh: the ps1 binding cases did NOT run on this host")
needs_proc = pytest.mark.skipif(not os.path.isdir("/proc"), reason="procStart is read from /proc")

SESSION = "33333333-cccc-4ccc-8ccc-000000000003"
FAKE_TTY = crew_fixtures.FAKE_TTY
OTHER_TTY = "/dev/pts/78"
_NO_BOUNDARY = {"SSH_CONNECTION": "", "SSH_CLIENT": "", "SSH_TTY": "",
                "WSL_DISTRO_NAME": "", "WSL_INTEROP": ""}


# --- plumbing --------------------------------------------------------------

def _repo(tmp_path, **auto):
    root = crew_fixtures.make_repo(
        tmp_path, config={"context": {"handoffPath": ".work/HANDOFF.md"}}, git=False)
    crew = root.parent / "home" / ".claude" / "crew"
    crew.mkdir(parents=True, exist_ok=True)
    (crew / "config.json").write_text(
        json.dumps({"context": {"autoClear": dict(auto, enabled=True)}}), encoding="utf-8")
    return root


def _home(root):
    return root.parent / "home"


def _log(root):
    path = root / ".crew" / ".autoclear.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# The owner as a process of its own, between this test and the hook. Every
# other case binds THIS test process as the owner, which leaves no room for
# the shapes a real terminal has: the window belongs to a strict ancestor of
# the owner (the terminal owns the window, never claude), a sibling session
# shares that ancestor, or the walk from the owner climbs through another
# session's process. The wrapper writes its own record (and tty stub) with
# its own pid, optionally starts a live session UNDER itself, then runs the
# hook and relays its output.
_OWNER_WRAPPER = """
import json, os, subprocess, sys
spec = json.loads(sys.argv[1])
sys.path.insert(0, spec["tests"])
import crew_fixtures
crew_fixtures.bind_session(spec["home"], spec["session"], pid=os.getpid(), tty=spec["tty"])
child = None
if spec.get("child_session"):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             stdin=subprocess.DEVNULL)
    crew_fixtures.write_session_record(spec["home"], spec["child_session"], pid=child.pid,
                                       name="child-of-owner.json")
try:
    done = subprocess.run(spec["cmd"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False, timeout=110)
finally:
    if child is not None:
        child.kill()
        child.wait()
sys.stdout.write(done.stdout)
sys.stderr.write(done.stderr)
sys.exit(done.returncode)
"""


def _run(flavor, root, env_extra=None, dry_run=True, session=SESSION, owner=None):
    """`owner`: None binds nothing here (the case binds this test process
    itself); a dict runs the hook under `_OWNER_WRAPPER`, which binds
    `session` to the wrapper's own pid. `owner["child_session"]` also puts a
    live session record under the wrapper."""
    home = str(_home(root))
    env = dict(os.environ, HOME=home, USERPROFILE=home, CREW_AUTOCLEAR_INHIBIT="1",
               CLAUDE_PROJECT_DIR=str(root), TMUX="", TMUX_PANE="", DISPLAY="",
               **_NO_BOUNDARY)
    env.update(env_extra or {})
    if flavor == "ps1":
        env["OS"] = "Windows_NT"
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1, "-Session", session, "-Force"]
        if dry_run:
            cmd.append("-DryRun")
    else:
        env.pop("OS", None)
        cmd = [_BASH, _SH, "--session", session, "--force"]
        if dry_run:
            cmd.append("--dry-run")
    if owner is not None:
        env.update(crew_fixtures.tty_stub_env(home))
        spec = {"tests": os.path.dirname(os.path.abspath(__file__)), "home": home,
                "session": session, "tty": FAKE_TTY, "cmd": cmd,
                "child_session": owner.get("child_session")}
        cmd = [sys.executable, "-c", _OWNER_WRAPPER, json.dumps(spec)]
    return subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False, timeout=120)


def _tmux_env(tmp_path, pane_pid=None, pane_tty=FAKE_TTY):
    """A fake tmux whose pane pid is this test process -- an ancestor of the
    script, exactly as today's check needs -- and whose pane tty is
    `pane_tty`. The binding decides the rest."""
    bindir = tmp_path / "fakebin"
    crew_fixtures.tmux_shim(bindir, os.getpid() if pane_pid is None else pane_pid, pane_tty)
    return crew_fixtures.shim_env("sh", bindir, TMUX="/tmp/fake,1,0", TMUX_PANE="%7")


def _xdotool_env(tmp_path, windows):
    bindir = tmp_path / "fakebin"
    crew_fixtures.write_shim(bindir, "xdotool")
    path = tmp_path / "windows.json"
    path.write_text(json.dumps(windows), encoding="utf-8")
    return crew_fixtures.shim_env("sh", bindir, DISPLAY=":0",
                                  CREW_AUTOCLEAR_WINDOW_STUB=str(path))


def _window_stub(tmp_path, windows):
    path = tmp_path / "windows.json"
    path.write_text(json.dumps(windows), encoding="utf-8")
    return {"CREW_AUTOCLEAR_WINDOW_STUB": str(path)}


def _bound(root, pid=None, tty=FAKE_TTY, **record):
    return crew_fixtures.bind_session(_home(root), SESSION, pid=pid, tty=tty, **record)


def _sleeper():
    """A live process that is NOT an ancestor of anything this test runs."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                            stdin=subprocess.DEVNULL)


def _dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _parent_pid():
    ppid = os.getppid()
    if ppid <= 1:
        pytest.skip("this test process's parent is pid 1, which the ancestor walk never lists")
    return ppid


def _sent(result):
    return "would send" in result.stdout


# --- must-fire: tmux, bound -----------------------------------------------

@needs_bash
@pytest.mark.parametrize("method", ["tmux", "auto"])
def test_owner_bound_tmux_pane_sends(method, tmp_path):
    root = _repo(tmp_path, method=method)
    env = dict(_tmux_env(tmp_path), **_bound(root))

    result = _run("sh", root, env)

    assert _sent(result), result.stdout + result.stderr + _log(root)
    assert "method: tmux" in result.stdout
    assert "target: %7" in result.stdout


@needs_bash
def test_bound_send_is_still_inhibited_before_the_keystroke(tmp_path):
    """The binding sits in front of the loop guards, never instead of them:
    a bound session with CREW_AUTOCLEAR_INHIBIT set still types nothing."""
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root))

    result = _run("sh", root, env, dry_run=False)

    assert "would have sent, but CREW_AUTOCLEAR_INHIBIT is set" in _log(root), (
        _log(root) + result.stderr)


# --- must-not-fire: each link of the proof, one test each ------------------

@needs_bash
def test_child_in_parent_pane_refuses_on_tty_mismatch(tmp_path):
    """The owner is a live interactive ancestor, the pane pid is an ancestor
    too -- today's check passes -- but the owner's terminal is not the pane's."""
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path, pane_tty=FAKE_TTY), **_bound(root, tty=OTHER_TTY))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert f"controlling terminal {OTHER_TTY} is not the pane's {FAKE_TTY}" in _log(root), _log(root)


@needs_bash
def test_owner_tty_unreadable_refuses(tmp_path):
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root, tty=None))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "could not read the controlling terminal" in _log(root), _log(root)


@needs_bash
def test_unknown_tty_refuses(tmp_path):
    """Neither side readable: "could not tell" twice is still not a match."""
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path, pane_tty=""), **_bound(root, tty=None))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout + _log(root)
    assert "could not read the controlling terminal" in _log(root), _log(root)


@needs_bash
def test_no_record_tmux_method_refuses(tmp_path):
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **crew_fixtures.tty_stub(tmp_path / "t", {os.getpid(): FAKE_TTY}))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    log = _log(root)
    assert "no Claude Code session record names this session" in log, log
    assert "crew_resume.py decide --source clear --json" in log, log


@needs_bash
def test_non_interactive_kind_refuses(tmp_path):
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root, kind="background"))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "kind 'background', not interactive" in _log(root), _log(root)


@needs_bash
def test_sdk_entrypoint_refuses(tmp_path):
    """The measured `claude -p` record: `kind: interactive` and still headless."""
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root, entrypoint="sdk-cli"))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "entrypoint 'sdk-cli'" in _log(root), _log(root)


@needs_bash
def test_missing_entrypoint_refuses(tmp_path):
    """A record with no entrypoint cannot say whether it is headless."""
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root, entrypoint=""))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "has no entrypoint" in _log(root), _log(root)


@needs_bash
def test_owner_with_no_controlling_tty_is_headless_and_refuses(tmp_path):
    """The measured Bash-tool child: tty `?`. Under an explicit tmux it refuses."""
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root, tty="?"))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "has no controlling terminal" in _log(root), _log(root)


@needs_bash
def test_dead_owner_refuses(tmp_path):
    root = _repo(tmp_path, method="tmux")
    dead = _dead_pid()
    env = dict(_tmux_env(tmp_path), **_bound(root, pid=dead, proc_start="1"))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert f"pid {dead} is not running" in _log(root), _log(root)


@needs_bash
@needs_proc
def test_proc_start_mismatch_refuses(tmp_path):
    """A record left by a dead session whose pid was reused by a live one."""
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root, proc_start="1"))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "procStart" in _log(root), _log(root)


@needs_bash
def test_owner_not_ancestor_refuses(tmp_path):
    root = _repo(tmp_path, method="tmux")
    proc = _sleeper()
    try:
        env = dict(_tmux_env(tmp_path), **_bound(root, pid=proc.pid))
        result = _run("sh", root, env)
    finally:
        proc.kill()
        proc.wait()

    assert not _sent(result), result.stdout
    assert f"pid {proc.pid}) is not an ancestor of this hook" in _log(root), _log(root)


@needs_bash
def test_two_matching_records_refuse(tmp_path):
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root))
    crew_fixtures.write_session_record(_home(root), SESSION, name="999999.json", pid=999999)

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "2 Claude Code session records name this session" in _log(root), _log(root)


@needs_bash
def test_unreadable_record_refuses(tmp_path):
    root = _repo(tmp_path, method="tmux")
    env = dict(_tmux_env(tmp_path), **_bound(root))
    (_home(root) / ".claude" / "sessions" / "424242.json").write_text("{not json", encoding="utf-8")

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "424242.json is unreadable" in _log(root), _log(root)


# --- xdotool walks from the owner, never from the hook ----------------------

@needs_bash
def test_xdotool_walks_from_owner(tmp_path):
    """must-not-fire: the owner is this test's PARENT, and the only window
    belongs to this test process -- an ancestor of the hook, but BELOW the
    owner. Walking from the hook would take it; walking from the owner does
    not."""
    root = _repo(tmp_path, method="xdotool")
    owner = _parent_pid()
    env = dict(_xdotool_env(tmp_path, [{"id": 11, "pid": os.getpid(), "title": "term"}]),
               **_bound(root, pid=owner))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "no window belongs to any ancestor of the session's own process (itself included)" in _log(root), _log(root)


@needs_bash
def test_xdotool_window_of_the_owner_itself_sends(tmp_path):
    """must-fire twin: the window belongs to the owner itself. The window of
    a strict ancestor of the owner -- the shape a real terminal has -- is
    `test_xdotool_window_of_a_strict_ancestor_of_the_owner_sends`."""
    root = _repo(tmp_path, method="xdotool")
    owner = _parent_pid()
    env = dict(_xdotool_env(tmp_path, [{"id": 12, "pid": owner, "title": "term"}]),
               **_bound(root, pid=owner))

    result = _run("sh", root, env)

    assert _sent(result), result.stdout + result.stderr + _log(root)
    assert "method: xdotool" in result.stdout
    assert "window 12" in result.stdout


@needs_bash
def test_xdotool_owner_tty_unreadable_refuses(tmp_path):
    root = _repo(tmp_path, method="xdotool")
    env = dict(_xdotool_env(tmp_path, [{"id": 13, "pid": os.getpid(), "title": "term"}]),
               **_bound(root, tty=None))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "could not read the controlling terminal" in _log(root), _log(root)


# --- the window the walk finds must be THIS session's alone -----------------
#
# The owner is `_OWNER_WRAPPER`'s process, so this test process is its
# parent and this test's own parent its grandparent: room for the window to
# belong to a strict ancestor of the owner, the only shape a real terminal
# has, and for another session to sit between them or beside them.

OTHER = "44444444-dddd-4ddd-8ddd-000000000004"
_SHARED = "also hosts another live Claude Code session"


def _xdotool_run(tmp_path, window_pid, owner=None, extra=None):
    root = _repo(tmp_path, method="xdotool")
    env = dict(_xdotool_env(tmp_path, [{"id": 51, "pid": window_pid, "title": "term"}]),
               **(extra or {}))
    return root, _run("sh", root, env, owner=owner or {})


def _ps1_run(tmp_path, window_pid, owner=None, extra=None):
    root = _repo(tmp_path, method="sendkeys")
    env = dict(_window_stub(tmp_path, [{"id": 52, "pid": window_pid, "title": "Claude"}]),
               **(extra or {}))
    return root, _run("ps1", root, env, owner=owner or {})


@needs_bash
@pytest.mark.parametrize("above", ["parent", "grandparent"])
def test_xdotool_window_of_a_strict_ancestor_of_the_owner_sends(above, tmp_path):
    """must-fire: the terminal above the owner owns the window, as it always
    does outside a test. A walk that looked only at the owner itself would
    never type anywhere."""
    window_pid = os.getpid() if above == "parent" else _parent_pid()

    root, result = _xdotool_run(tmp_path, window_pid)

    assert _sent(result), result.stdout + result.stderr + _log(root)
    assert "window 51" in result.stdout, result.stdout


@needs_bash
def test_xdotool_walk_through_another_sessions_process_refuses(tmp_path):
    """A child `claude` with its own pty (`script -qc claude` from a parent's
    Bash tool) passes the binding; the walk from it climbs through the
    PARENT session's process to the parent's terminal window."""
    root = _repo(tmp_path, method="xdotool")
    crew_fixtures.write_session_record(_home(root), OTHER, pid=os.getpid(), name="parent.json")
    env = _xdotool_env(tmp_path, [{"id": 53, "pid": _parent_pid(), "title": "term"}])

    result = _run("sh", root, env, owner={})

    assert not _sent(result), result.stdout
    assert _SHARED in _log(root), _log(root)
    assert f"pid {os.getpid()}" in _log(root), _log(root)


@needs_bash
def test_xdotool_window_shared_with_a_sibling_session_refuses(tmp_path):
    """Two tabs of one gnome-terminal / konsole / VS Code window: one X
    window, owned by one process, above both sessions. xdotool types into
    whichever tab is showing."""
    root = _repo(tmp_path, method="xdotool")
    sibling = _sleeper()
    try:
        crew_fixtures.write_session_record(_home(root), OTHER, pid=sibling.pid, name="sibling.json")
        env = _xdotool_env(tmp_path, [{"id": 54, "pid": os.getpid(), "title": "term"}])
        result = _run("sh", root, env, owner={})
    finally:
        sibling.kill()
        sibling.wait()

    assert not _sent(result), result.stdout
    assert _SHARED in _log(root), _log(root)
    assert f"pid {sibling.pid}" in _log(root), _log(root)


@needs_bash
def test_xdotool_sibling_record_without_proc_start_still_refuses(tmp_path):
    """A live pid whose record carries no procStart cannot be proven stale:
    "could not tell" counts it as the session it says it is."""
    root = _repo(tmp_path, method="xdotool")
    sibling = _sleeper()
    try:
        crew_fixtures.write_session_record(_home(root), OTHER, pid=sibling.pid, name="sibling.json",
                                           proc_start=None)
        env = _xdotool_env(tmp_path, [{"id": 55, "pid": os.getpid(), "title": "term"}])
        result = _run("sh", root, env, owner={})
    finally:
        sibling.kill()
        sibling.wait()

    assert not _sent(result), result.stdout
    assert _SHARED in _log(root), _log(root)


@needs_bash
def test_xdotool_sibling_record_with_no_usable_pid_refuses(tmp_path):
    root = _repo(tmp_path, method="xdotool")
    crew_fixtures.write_session_record(_home(root), OTHER, pid="1234", name="odd.json",
                                       proc_start=None)
    env = _xdotool_env(tmp_path, [{"id": 56, "pid": os.getpid(), "title": "term"}])

    result = _run("sh", root, env, owner={})

    assert not _sent(result), result.stdout
    assert "odd.json has no usable pid" in _log(root), _log(root)


@needs_bash
def test_xdotool_dead_sibling_record_does_not_block(tmp_path):
    """must-fire twin: a record left by a session that has exited shares
    nothing."""
    root = _repo(tmp_path, method="xdotool")
    crew_fixtures.write_session_record(_home(root), OTHER, pid=_dead_pid(), name="gone.json",
                                       proc_start="1")
    env = _xdotool_env(tmp_path, [{"id": 57, "pid": os.getpid(), "title": "term"}])

    result = _run("sh", root, env, owner={})

    assert _sent(result), result.stdout + result.stderr + _log(root)


@needs_bash
@needs_proc
def test_xdotool_stale_sibling_record_on_a_reused_pid_does_not_block(tmp_path):
    """must-fire twin: a live pid whose start time is not the recorded one
    is some other process, not the session the record names."""
    root = _repo(tmp_path, method="xdotool")
    sibling = _sleeper()
    try:
        crew_fixtures.write_session_record(_home(root), OTHER, pid=sibling.pid, name="stale.json",
                                           proc_start="1")
        env = _xdotool_env(tmp_path, [{"id": 58, "pid": os.getpid(), "title": "term"}])
        result = _run("sh", root, env, owner={})
    finally:
        sibling.kill()
        sibling.wait()

    assert _sent(result), result.stdout + result.stderr + _log(root)


@needs_bash
def test_xdotool_session_under_the_owner_does_not_block(tmp_path):
    """must-fire twin: a `claude -p` this session started from its own Bash
    tool sits under the owner, and reaches the window only through it."""
    root = _repo(tmp_path, method="xdotool")
    env = _xdotool_env(tmp_path, [{"id": 59, "pid": os.getpid(), "title": "term"}])

    result = _run("sh", root, env, owner={"child_session": OTHER})

    assert _sent(result), result.stdout + result.stderr + _log(root)


@needs_pwsh
@pytest.mark.parametrize("above", ["parent", "grandparent"])
def test_ps1_window_of_a_strict_ancestor_of_the_owner_sends(above, tmp_path):
    window_pid = os.getpid() if above == "parent" else _parent_pid()

    root, result = _ps1_run(tmp_path, window_pid)

    assert _sent(result), result.stdout + result.stderr + _log(root)
    assert "window 52" in result.stdout, result.stdout


@needs_pwsh
def test_ps1_walk_through_another_sessions_process_declines(tmp_path):
    """The ps1 twin of the child walking up through its parent session --
    and on Windows the only thing that stops it, whatever entrypoint a -p
    child writes there (unmeasured)."""
    root = _repo(tmp_path, method="sendkeys")
    crew_fixtures.write_session_record(_home(root), OTHER, pid=os.getpid(), name="parent.json")
    env = _window_stub(tmp_path, [{"id": 60, "pid": _parent_pid(), "title": "Claude"}])

    result = _run("ps1", root, env, owner={})

    assert not _sent(result), result.stdout
    assert "would decline sendkeys" in result.stdout, result.stdout + result.stderr
    assert _SHARED in result.stdout, result.stdout


@needs_pwsh
def test_ps1_window_shared_with_a_sibling_session_declines(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    sibling = _sleeper()
    try:
        crew_fixtures.write_session_record(_home(root), OTHER, pid=sibling.pid, name="sibling.json")
        env = _window_stub(tmp_path, [{"id": 61, "pid": os.getpid(), "title": "Claude"}])
        result = _run("ps1", root, env, owner={})
    finally:
        sibling.kill()
        sibling.wait()

    assert not _sent(result), result.stdout
    assert _SHARED in result.stdout, result.stdout + result.stderr


@needs_pwsh
def test_ps1_session_under_the_owner_does_not_block(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    env = _window_stub(tmp_path, [{"id": 62, "pid": os.getpid(), "title": "Claude"}])

    result = _run("ps1", root, env, owner={"child_session": OTHER})

    assert _sent(result), result.stdout + result.stderr + _log(root)


# --- a relocated CLAUDE_CONFIG_DIR -----------------------------------------

def _relocated(tmp_path):
    folder = tmp_path / "relocated-claude"
    folder.mkdir(exist_ok=True)
    return folder


@needs_bash
def test_record_under_claude_config_dir_is_found(tmp_path):
    root = _repo(tmp_path, method="tmux")
    config_dir = _relocated(tmp_path)
    env = dict(_tmux_env(tmp_path), CLAUDE_CONFIG_DIR=str(config_dir),
               **_bound(root, sessions_dir=config_dir / "sessions"))

    result = _run("sh", root, env)

    assert _sent(result), result.stdout + result.stderr + _log(root)
    assert "method: tmux" in result.stdout


@needs_bash
def test_no_record_with_claude_config_dir_set_is_could_not_tell(tmp_path):
    """Where Claude Code keeps its records under a relocated config dir is
    unmeasured, so finding none there is "could not tell" -- never the fact
    "headless", which `auto` would turn into a notify telling a user at
    their own pane that a parent must restart it."""
    root = _repo(tmp_path)
    env = dict(_tmux_env(tmp_path), CLAUDE_CONFIG_DIR=str(_relocated(tmp_path)),
               **crew_fixtures.tty_stub(tmp_path / "t", {os.getpid(): FAKE_TTY}))

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "method: notify" not in result.stdout
    assert "CLAUDE_CONFIG_DIR" in _log(root), _log(root)
    assert "no terminal of its own" not in _log(root), _log(root)


@needs_pwsh
def test_ps1_record_under_claude_config_dir_is_found(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    config_dir = _relocated(tmp_path)
    env = dict(_window_stub(tmp_path, [{"id": 63, "pid": os.getpid(), "title": "Claude"}]),
               CLAUDE_CONFIG_DIR=str(config_dir),
               **_bound(root, sessions_dir=config_dir / "sessions"))

    result = _run("ps1", root, env)

    assert _sent(result), result.stdout + result.stderr + _log(root)


@needs_pwsh
def test_ps1_no_record_with_claude_config_dir_set_refuses(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    env = dict(_window_stub(tmp_path, [{"id": 64, "pid": os.getpid(), "title": "Claude"}]),
               CLAUDE_CONFIG_DIR=str(_relocated(tmp_path)))

    result = _run("ps1", root, env)

    assert not _sent(result), result.stdout
    assert "would decline sendkeys" not in result.stdout, result.stdout
    assert "CLAUDE_CONFIG_DIR" in _log(root), _log(root)


# --- headless: notify with the parent-restart recipe, never a keystroke -----

@needs_bash
@pytest.mark.parametrize("record", [
    None, {"kind": "background"}, {"entrypoint": "sdk-cli"}, {"tty": ""}],
    ids=["no-record", "kind", "sdk-entrypoint", "no-tty"])
def test_no_record_auto_is_notify_with_restart_recipe(record, tmp_path):
    root = _repo(tmp_path)  # method auto; $TMUX set, so auto picks tmux first
    env = _tmux_env(tmp_path)
    if record is None:
        env.update(crew_fixtures.tty_stub(tmp_path / "t", {os.getpid(): FAKE_TTY}))
    else:
        env.update(_bound(root, **record))

    result = _run("sh", root, env)

    assert "would send" in result.stdout, result.stdout + result.stderr
    assert "method: notify" in result.stdout, result.stdout
    assert "method: tmux" not in result.stdout
    assert "crew_resume.py decide --source clear --json" in result.stdout, result.stdout


@needs_bash
def test_notify_message_carries_the_headless_reason(tmp_path):
    root = _repo(tmp_path)
    env = dict(_tmux_env(tmp_path), **_bound(root, entrypoint="sdk-cli", tty=""))

    result = _run("sh", root, env, dry_run=False)

    message = json.loads(result.stdout.strip().splitlines()[-1])["systemMessage"]
    assert "it is safe to run /clear now" in message, message
    assert "crew_resume.py decide --source clear --json" in message, message
    assert "then record" in message, message
    assert "claude -p" in message, message
    assert "sent - method notify" in _log(root), _log(root)
    assert "no terminal of its own" in _log(root), _log(root)


@needs_bash
def test_headless_notify_never_says_cleared_or_compacted(tmp_path):
    root = _repo(tmp_path)
    env = dict(_tmux_env(tmp_path), **_bound(root, entrypoint="sdk-cli", tty=""))

    result = _run("sh", root, env, dry_run=False)

    lowered = result.stdout.lower()
    assert "cleared" not in lowered and "compacted" not in lowered, result.stdout


@needs_bash
def test_headless_with_no_terminal_method_at_all_is_notify(tmp_path):
    """No $TMUX, no $DISPLAY, not Windows: `auto` has no keystroke method, and
    a session that provably has no terminal still gets the restart recipe."""
    root = _repo(tmp_path)
    env = _bound(root, entrypoint="sdk-cli", tty="")

    result = _run("sh", root, env)

    assert "method: notify" in result.stdout, result.stdout + result.stderr + _log(root)
    assert "crew_resume.py decide --source clear --json" in result.stdout, result.stdout


@needs_bash
def test_bound_session_with_no_terminal_method_is_still_refused(tmp_path):
    """must-block twin: a session WITH a terminal of its own, but no method
    that could type into it, is the old "no usable method" refusal -- never
    a notify that hides the missing setup."""
    root = _repo(tmp_path)
    env = _bound(root)

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "no usable method" in _log(root), _log(root)


def test_the_plan_is_still_eight_lines_with_a_notify_reason(tmp_path, monkeypatch, capsys):
    """auto-clear.sh reads exactly eight lines; a reason on a `send` must not
    add or split one."""
    root = _repo(tmp_path)
    monkeypatch.setenv("HOME", str(_home(root)))
    monkeypatch.setenv("USERPROFILE", str(_home(root)))
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 1 10.0.0.2 22")
    for name in ("TMUX", "TMUX_PANE"):
        monkeypatch.delenv(name, raising=False)

    crew_autocycle.main(["plan", "--root", str(root), "--session", SESSION, "--force"])
    lines = capsys.readouterr().out.split("\n")

    assert len(lines) == 9 and lines[-1] == "", lines
    assert lines[0] == "send" and lines[2] == "notify", lines
    assert "ssh" in lines[1], lines


def test_restart_recipe_names_the_t0006_cli():
    recipe = crew_autocycle.restart_recipe()

    assert "crew_resume.py decide --source clear --json" in recipe
    assert "then record" in recipe
    assert 'claude -p "<prompt>"' in recipe


# --- ssh and WSL: never across the boundary --------------------------------

_SSH = {"SSH_CONNECTION": "10.0.0.1 50000 10.0.0.2 22"}
_WSL = {"WSL_DISTRO_NAME": "Ubuntu"}


@needs_bash
@pytest.mark.parametrize("marker", [_SSH, {"SSH_CLIENT": "10.0.0.1 50000 22"}, {"SSH_TTY": "/dev/pts/3"}],
                         ids=["SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"])
def test_ssh_auto_is_notify_not_xdotool(marker, tmp_path):
    root = _repo(tmp_path)
    env = dict(_xdotool_env(tmp_path, [{"id": 21, "pid": os.getpid(), "title": "term"}]),
               **_bound(root), **marker)

    result = _run("sh", root, env)

    assert "method: notify" in result.stdout, result.stdout + result.stderr
    assert "xdotool" not in result.stdout
    assert "ssh" in result.stdout, result.stdout


@needs_bash
def test_ssh_explicit_xdotool_refuses(tmp_path):
    root = _repo(tmp_path, method="xdotool")
    env = dict(_xdotool_env(tmp_path, [{"id": 22, "pid": os.getpid(), "title": "term"}]),
               **_bound(root), **_SSH)

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "the X display is not on the host this session runs on" in _log(root), _log(root)


@needs_bash
@pytest.mark.parametrize("marker", ["env-distro", "env-interop", "interop-file"])
def test_wsl_auto_is_notify(marker, tmp_path):
    root = _repo(tmp_path)
    env = dict(_xdotool_env(tmp_path, [{"id": 23, "pid": os.getpid(), "title": "term"}]),
               **_bound(root))
    if marker == "env-distro":
        env.update(_WSL)
    elif marker == "env-interop":
        env["WSL_INTEROP"] = "/run/WSL/1_interop"
    else:
        probe = tmp_path / "WSLInterop"
        probe.write_text("enabled\n", encoding="utf-8")
        env["CREW_AUTOCLEAR_WSL_INTEROP_PATH"] = str(probe)

    result = _run("sh", root, env)

    assert "method: notify" in result.stdout, result.stdout + result.stderr
    assert "WSL" in result.stdout, result.stdout


@needs_bash
def test_wsl_explicit_xdotool_refuses(tmp_path):
    root = _repo(tmp_path, method="xdotool")
    env = dict(_xdotool_env(tmp_path, [{"id": 24, "pid": os.getpid(), "title": "term"}]),
               **_bound(root), **_WSL)

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout
    assert "the X display is not on the host this session runs on" in _log(root), _log(root)


@needs_bash
@pytest.mark.parametrize("marker", [_SSH, _WSL], ids=["ssh", "wsl"])
def test_tmux_inside_ssh_still_sends(marker, tmp_path):
    """tmux running where Claude runs is the supported route across both."""
    root = _repo(tmp_path)
    env = dict(_tmux_env(tmp_path), **_bound(root), **marker)

    result = _run("sh", root, env)

    assert _sent(result), result.stdout + result.stderr + _log(root)
    assert "method: tmux" in result.stdout


@needs_bash
def test_tmux_inside_ssh_with_a_foreign_tty_still_refuses(tmp_path):
    root = _repo(tmp_path)
    env = dict(_tmux_env(tmp_path), **_bound(root, tty=OTHER_TTY), **_SSH)

    result = _run("sh", root, env)

    assert not _sent(result), result.stdout


# --- the record lookup, in process ----------------------------------------

def _in_process_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_record_lag_polls_then_refuses(tmp_path, monkeypatch):
    """No record at all: the lookup waits its fixed ~2 s (the spike measured
    0 ms after /clear and 74 ms at a `-p` startup), then reads as headless."""
    _in_process_home(tmp_path, monkeypatch)

    started = time.monotonic()
    owner = crew_autocycle.session_owner(SESSION)
    elapsed = time.monotonic() - started

    assert owner["ok"] is False and owner["headless"] is True, owner
    assert 1.8 <= elapsed < 6, elapsed


def test_record_that_lands_during_the_poll_is_found(tmp_path, monkeypatch):
    home = _in_process_home(tmp_path, monkeypatch)
    monkeypatch.setenv(crew_autocycle.TTY_STUB_ENV,
                       crew_fixtures.tty_stub(tmp_path, {os.getpid(): FAKE_TTY})["CREW_AUTOCLEAR_TTY_STUB"])
    timer = threading.Timer(0.4, crew_fixtures.write_session_record, args=(home, SESSION))
    timer.start()
    try:
        owner = crew_autocycle.session_owner(SESSION)
    finally:
        timer.join()

    assert owner["ok"] is True, owner
    assert owner["pid"] == os.getpid()
    assert owner["tty"] == FAKE_TTY


def test_no_session_id_is_a_refusal_not_headless(tmp_path, monkeypatch):
    _in_process_home(tmp_path, monkeypatch)

    owner = crew_autocycle.session_owner("")

    assert owner["ok"] is False and owner["headless"] is False, owner


def test_resolve_method_without_a_session_id_types_nothing(tmp_path, monkeypatch):
    """Any caller that does not say which session it is asking for gets no
    keystroke method -- never a binding skipped."""
    _in_process_home(tmp_path, monkeypatch)
    bindir = tmp_path / "fakebin"
    crew_fixtures.tmux_shim(bindir, os.getpid())
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    cfg = dict(crew_autocycle._DEFAULTS, method="tmux")  # pylint: disable=protected-access
    env = {"TMUX": "/tmp/fake,1,0", "TMUX_PANE": "%7"}

    got = crew_autocycle.resolve_method(cfg, env)

    assert got["ok"] is False, got


@pytest.mark.parametrize("tty_nr, expect", [
    (0, ""), (34822, "/dev/pts/6"), (34816, "/dev/pts/0"), (34816 + 255, "/dev/pts/255"),
    ((137 << 8) | 4, "/dev/pts/260"), ((136 << 8) | (1 << 20), "/dev/pts/256")])
def test_tty_nr_decodes_to_the_pane_tty_form(tty_nr, expect):
    assert crew_autocycle._tty_from_nr(tty_nr) == expect  # pylint: disable=protected-access


def test_a_non_pts_tty_nr_is_left_to_ps():
    assert crew_autocycle._tty_from_nr((4 << 8) | 1) is None  # pylint: disable=protected-access


# --- the ps1 twin (pwsh with OS=Windows_NT; native Windows NOT run here) -----

@needs_pwsh
def test_ps1_owner_bound_sendkeys_sends(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    env = dict(_window_stub(tmp_path, [{"id": 31, "pid": os.getpid(), "title": "Claude"}]),
               **_bound(root))

    result = _run("ps1", root, env)

    assert _sent(result), result.stdout + result.stderr + _log(root)
    assert "method: sendkeys" in result.stdout


@needs_pwsh
@pytest.mark.parametrize("record", [None, {"kind": "background"}, {"entrypoint": "sdk-cli"}],
                         ids=["no-record", "kind", "sdk-entrypoint"])
def test_ps1_no_record_declines_to_notify(record, tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    env = _window_stub(tmp_path, [{"id": 32, "pid": os.getpid(), "title": "Claude"}])
    if record is not None:
        env.update(_bound(root, **record))

    result = _run("ps1", root, env)

    assert "would decline sendkeys" in result.stdout, result.stdout + result.stderr
    assert "falling back to notify" in result.stdout
    assert "crew_resume.py decide --source clear --json" in result.stdout, result.stdout
    assert "would send" not in result.stdout


@needs_pwsh
def test_ps1_headless_notify_message_carries_the_recipe(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    env = dict(_window_stub(tmp_path, [{"id": 33, "pid": os.getpid(), "title": "Claude"}]),
               **_bound(root, entrypoint="sdk-cli"))

    result = _run("ps1", root, env, dry_run=False)

    message = json.loads(result.stdout.strip().splitlines()[-1])["systemMessage"]
    assert "crew_resume.py decide --source clear --json" in message, message
    assert "claude -p" in message, message
    assert "declined sendkeys" in _log(root), _log(root)
    lowered = message.lower()
    assert "cleared" not in lowered and "compacted" not in lowered


@needs_pwsh
def test_ps1_non_interactive_kind_declines(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    env = dict(_window_stub(tmp_path, [{"id": 34, "pid": os.getpid(), "title": "Claude"}]),
               **_bound(root, kind="background"))

    result = _run("ps1", root, env, dry_run=False)

    assert "kind 'background', not interactive" in _log(root), _log(root)
    assert "declined sendkeys" in _log(root)


@needs_pwsh
def test_ps1_owner_not_ancestor_declines(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    proc = _sleeper()
    try:
        env = dict(_window_stub(tmp_path, [{"id": 35, "pid": os.getpid(), "title": "Claude"}]),
                   **_bound(root, pid=proc.pid))
        result = _run("ps1", root, env)
    finally:
        proc.kill()
        proc.wait()

    assert not _sent(result), result.stdout
    assert f"pid {proc.pid}) is not an ancestor of this hook" in _log(root), _log(root)


@needs_pwsh
def test_ps1_dead_owner_refuses(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    dead = _dead_pid()
    env = dict(_window_stub(tmp_path, [{"id": 36, "pid": os.getpid(), "title": "Claude"}]),
               **_bound(root, pid=dead))

    result = _run("ps1", root, env)

    assert not _sent(result), result.stdout
    assert f"pid {dead} is not running" in _log(root), _log(root)


@needs_pwsh
def test_ps1_two_matching_records_refuse(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    env = dict(_window_stub(tmp_path, [{"id": 37, "pid": os.getpid(), "title": "Claude"}]),
               **_bound(root))
    crew_fixtures.write_session_record(_home(root), SESSION, name="999999.json", pid=999999)

    result = _run("ps1", root, env)

    assert not _sent(result), result.stdout
    assert "2 Claude Code session records name this session" in _log(root), _log(root)


@needs_pwsh
def test_ps1_walk_starts_at_owner(tmp_path):
    """must-not-fire: the owner is this test's parent and the only window
    belongs to this test process, between the hook and the owner."""
    root = _repo(tmp_path, method="sendkeys")
    owner = _parent_pid()
    env = dict(_window_stub(tmp_path, [{"id": 38, "pid": os.getpid(), "title": "Claude"}]),
               **_bound(root, pid=owner))

    result = _run("ps1", root, env)

    assert not _sent(result), result.stdout
    assert "no window belongs to any ancestor of the session's own process (itself included)" in _log(root), _log(root)


@needs_pwsh
def test_ps1_window_of_the_owner_sends(tmp_path):
    root = _repo(tmp_path, method="sendkeys")
    owner = _parent_pid()
    env = dict(_window_stub(tmp_path, [{"id": 39, "pid": owner, "title": "Claude"}]),
               **_bound(root, pid=owner))

    result = _run("ps1", root, env)

    assert _sent(result), result.stdout + result.stderr + _log(root)
    assert "window 39" in result.stdout


@needs_pwsh
def test_ps1_auto_is_still_notify_with_no_lookup(tmp_path):
    """`auto` on native Windows is notify, which types nothing, so it needs
    no binding and must not wait on one."""
    root = _repo(tmp_path)
    started = time.monotonic()

    result = _run("ps1", root, {})

    assert "method: notify" in result.stdout, result.stdout + result.stderr
    assert time.monotonic() - started < 30


# --- parity: the two flavours agree on typed-or-not -------------------------

_PARITY = [
    ("bound", {}, True),
    ("no-record", None, False),
    ("kind", {"kind": "background"}, False),
    ("sdk-entrypoint", {"entrypoint": "sdk-cli"}, False),
    ("no-entrypoint", {"entrypoint": ""}, False),
]


@pytest.mark.parametrize("flavor", [
    pytest.param("sh", marks=needs_bash), pytest.param("ps1", marks=needs_pwsh)])
@pytest.mark.parametrize("case, record, typed", _PARITY, ids=[c[0] for c in _PARITY])
def test_both_flavours_agree_on_whether_anything_is_typed(flavor, case, record, typed, tmp_path):
    del case
    if flavor == "sh":
        root = _repo(tmp_path, method="tmux")
        env = _tmux_env(tmp_path)
    else:
        root = _repo(tmp_path, method="sendkeys")
        env = _window_stub(tmp_path, [{"id": 40, "pid": os.getpid(), "title": "Claude"}])
    if record is None:
        env.update(crew_fixtures.tty_stub(tmp_path / "t", {os.getpid(): FAKE_TTY}))
    else:
        env.update(_bound(root, **record))

    result = _run(flavor, root, env)

    assert _sent(result) is typed, result.stdout + result.stderr + _log(root)
    if typed:
        assert ("method: tmux" if flavor == "sh" else "method: sendkeys") in result.stdout


@pytest.mark.parametrize("flavor", [
    pytest.param("sh", marks=needs_bash), pytest.param("ps1", marks=needs_pwsh)])
def test_both_flavours_refuse_a_pid_that_is_not_an_integer(flavor, tmp_path):
    """`"pid": 1234.0` names this test process only after a rounding cast.
    Python refuses anything but an int; the twin must not cast its way to a
    match, or the flavours disagree on a record neither has measured."""
    if flavor == "sh":
        root = _repo(tmp_path, method="tmux")
        env = _tmux_env(tmp_path)
    else:
        root = _repo(tmp_path, method="sendkeys")
        env = _window_stub(tmp_path, [{"id": 41, "pid": os.getpid(), "title": "Claude"}])
    env.update(_bound(root, pid=float(os.getpid()), proc_start=None))

    result = _run(flavor, root, env)

    assert not _sent(result), result.stdout + result.stderr
    assert "the session record has no usable pid" in _log(root), _log(root)


def test_every_binding_sabotage_anchor_is_present_exactly_once():
    import sabotage_autoclear_binding  # pylint: disable=import-outside-toplevel

    lost = []
    for label, target, find, _replace, _test in sabotage_autoclear_binding.BINDING_MUTATIONS:
        with open(target, encoding="utf-8", newline="") as handle:
            if handle.read().count(find) != 1:
                lost.append(label)

    assert not lost, lost
