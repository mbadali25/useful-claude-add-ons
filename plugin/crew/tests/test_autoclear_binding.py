"""T-0016: auto-clear (and T-0013's resume typing) types only into a terminal
that is provably this session's own.

The session is bound to its OWN process -- the nearest ancestor of the hook
named by a Claude Code session record (`${CLAUDE_CONFIG_DIR:-~/.claude}/
sessions/<pid>.json`) with this session's id and that process's start time
-- and classified terminal / headless / unknown. Only `terminal` is typed
into; the target is then proven by walking up FROM that process.

Must-allow and must-block pairs, both flavours where the method exists:

  - must-allow: a bound terminal session in its own tmux pane, or under an
    X11 / console window owned by a strict ancestor, sends; notify's text is
    unchanged for a terminal or an unknown session;
  - must-block: a headless child (`claude -p`: entrypoint sdk-cli, or no
    controlling terminal) inside its parent's pane or window types nothing
    and gets one headless notice; a walk that passes through another
    session refuses; a window that also hosts another terminal refuses; a
    session that could not be identified is never "headless" and never
    "safe"; a truncated chain refuses; a pid-less or title-only window
    refuses while another session is live;
  - order: the binding runs before the sent-marker claim.

No case reads the real process table, the real `~/.claude/sessions`, or a real
window, and none sends a keystroke: every run sets CREW_AUTOCLEAR_INHIBIT, a
fixture HOME and CLAUDE_CONFIG_DIR, CREW_AUTOCLEAR_PROC_STUB (the whole process
table) and CREW_AUTOCLEAR_WINDOW_STUB. The .ps1 cases are told they are on
Windows and skip without pwsh -- a skip there means that flavour did NOT run.
"""
import json
import os
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autocycle
import crew_fixtures as cf

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_BASH = cf.resolve_bash()
_PWSH = cf.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash not installed - the sh flavour was NOT run")
needs_pwsh = pytest.mark.skipif(_PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")
FLAVORS = [pytest.param("sh", marks=needs_bash), pytest.param("ps1", marks=needs_pwsh)]

SESSION = "33333333-cccc-4ccc-8ccc-000000000003"
OTHER_SESSION = "44444444-dddd-4ddd-8ddd-000000000004"
RESUME = "/crew:done T-0001"
HANDOFF = ("# Handoff\nwritten: now\nticket: T-0001\nbranch: x\nhead: y\n"
           f"resume: {RESUME}\n\n## Done\n- a thing\n\n## Next action\nClose T-0001.\n")
H, O, T = cf.HOOK_PID, cf.OWNER_PID, cf.TERMINAL_PID
TTY, TTY_OTHER = cf.TERMINAL_TTY, cf.TERMINAL_TTY + 1
SHELL, PARENT, SCRIPT, SIBLING = 5_000_003, 5_000_050, 5_000_004, 5_000_060
PARENT_START = 4242
PLAIN_NOTIFY = ("crew: handoff written and verified for this session - it is safe to run /clear now "
                "(auto-clear will not type it for you).")
P = cf.proc_entry


# --- plumbing ------------------------------------------------------------------

class Box:
    """A crew repo whose session asked for a wrap-up and wrote its handoff,
    with its own HOME, machine file and config dir."""

    def __init__(self, tmp_path, **auto):
        self.tmp = tmp_path
        self.root = cf.make_repo(tmp_path, config={"context": {"handoffPath": ".work/HANDOFF.md"}}, git=False)
        self.home = tmp_path / "home"
        self.config = self.home / ".claude"
        self.machine(**auto)
        (self.root / ".crew" / (".handoff-requested-" + SESSION)).write_text(json.dumps({
            "session_id": SESSION, "requested_at": time.time() - 30, "trusted": True, "why": "measured"}),
            encoding="utf-8")
        handoff = self.root / ".work" / "HANDOFF.md"
        handoff.write_text(HANDOFF, encoding="utf-8")
        stamp = time.time() + 5
        os.utime(handoff, (stamp, stamp))
        self.env = {"CLAUDE_CONFIG_DIR": str(self.config)}

    def machine(self, **auto):
        crew = self.home / ".claude" / "crew"
        crew.mkdir(parents=True, exist_ok=True)
        block = {"enabled": True}
        block.update(auto)
        (crew / "config.json").write_text(json.dumps({"context": {"autoClear": block}}), encoding="utf-8")

    def record(self, pid=O, session=SESSION, config=None, **kw):
        return cf.write_session_record(config or self.config, session, pid, **kw)

    def procs(self, table, **kw):
        self.env.update(cf.proc_stub(self.tmp, table, **kw))

    def tmux(self, pane_pid=T):
        bindir = self.tmp / "fakebin"
        cf.write_shim(bindir, "tmux", f"#!/bin/sh\necho {pane_pid}\n", f"@echo off\r\necho {pane_pid}\r\n")
        self.env.update(cf.shim_env("sh", bindir, TMUX="/tmp/fake,1,0", TMUX_PANE="%7"))

    def windows(self, windows, xdotool=True):
        path = self.tmp / "windows.json"
        path.write_text(json.dumps(windows), encoding="utf-8")
        self.env["CREW_AUTOCLEAR_WINDOW_STUB"] = str(path)
        if xdotool:
            bindir = self.tmp / "fakebin"
            cf.write_shim(bindir, "xdotool")
            self.env.update(cf.shim_env("sh", bindir, DISPLAY=":0"))

    def run(self, flavor, *args, extra=None):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), CREW_AUTOCLEAR_INHIBIT="1",
                   CLAUDE_PROJECT_DIR=str(self.root))
        for name in ("TMUX", "TMUX_PANE", "DISPLAY", "OS"):
            env.pop(name, None)
        env.update(self.env)
        env.update(extra or {})
        if flavor == "ps1":
            env["OS"] = "Windows_NT"
            names = {"--dry-run": "-DryRun", "--force": "-Force"}
            cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", os.path.join(_SCRIPTS, "auto-clear.ps1"),
                   "-Session", SESSION, "-Root", str(self.root), *[names.get(a, a) for a in args]]
        else:
            cmd = [_BASH, os.path.join(_SCRIPTS, "auto-clear.sh").replace("\\", "/"),
                   "--session", SESSION, "--root", str(self.root), *args]
        return cf.subprocess.run(cmd, cwd=str(self.root), env=env, capture_output=True, text=True,
                                 stdin=cf.subprocess.DEVNULL, check=False, timeout=120)

    def log(self):
        path = self.root / ".crew" / ".autoclear.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def sent_marker(self):
        return self.root / ".crew" / (".autoclear-sent-" + SESSION)


def _target(box, flavor, method=None):
    """The configured method and a target each flavour could type into: a
    tmux pane on the terminal for sh (or the X11 window when method is
    xdotool), the console window on the terminal for ps1."""
    if flavor == "ps1":
        box.machine(method=method or "sendkeys")
        box.windows([{"id": 4242, "pid": T, "title": "Claude Code"}], xdotool=False)
        return
    box.machine(method=method or "tmux")
    if method == "xdotool":
        box.windows([{"id": 4242, "pid": T, "title": "Claude Code"}])
    else:
        box.tmux()


def _own_terminal(box, **record):
    box.record(**record)
    box.procs(cf.session_table())


def _child_of_parent(box, tty=0, entrypoint="sdk-cli"):
    """A child session started from the parent's Bash tool: hook -> child
    (owner) -> tool shell -> parent claude (a live record of its own) ->
    the parent's terminal, which owns the pane and the window."""
    box.record(entrypoint=entrypoint)
    box.record(pid=PARENT, session=OTHER_SESSION, proc_start=PARENT_START)
    box.procs({H: P(O, tty, 1), O: P(SHELL, tty, cf.OWNER_START, "claude"), SHELL: P(PARENT, tty, 1),
               PARENT: P(T, TTY, PARENT_START, "claude"), T: P(1, 0, 1, "terminal")})


# --- the fixture mirrors the measured record -----------------------------------

def test_fixture_record_has_the_measured_shape(tmp_path):
    path = cf.write_session_record(tmp_path, SESSION, O)
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    assert set(data) == set(cf.MEASURED_RECORD_KEYS)
    assert (data["sessionId"], data["procStart"], data["kind"], data["entrypoint"]) == \
        (SESSION, str(cf.OWNER_START), "interactive", "cli")


def test_fixture_pids_are_never_real_processes():
    for pid in (H, O, T, SHELL, PARENT, SCRIPT, SIBLING):
        assert pid > 4194304 and not os.path.exists(f"/proc/{pid}")


# --- owner and classify, in-process ---------------------------------------------

def _inproc(monkeypatch, box):
    monkeypatch.setenv("CREW_AUTOCLEAR_INHIBIT", "1")  # stubs are read only while it is set
    for name, value in box.env.items():
        monkeypatch.setenv(name, value)


def test_owner_found_by_record_and_session_id(tmp_path, monkeypatch):
    box = Box(tmp_path)
    _own_terminal(box)
    _inproc(monkeypatch, box)
    owner = crew_autocycle.session_owner(SESSION)
    assert (owner["pid"], owner["how"]) == (O, "session record + session id + start time")


def test_owner_honours_claude_config_dir(tmp_path, monkeypatch):
    box = Box(tmp_path)
    box.procs(cf.session_table())
    elsewhere = tmp_path / "other-config"
    box.record(config=elsewhere)
    _inproc(monkeypatch, box)
    assert "unknown" in crew_autocycle.session_owner(SESSION)  # ~/.claude has none
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(elsewhere))
    assert crew_autocycle.session_owner(SESSION)["pid"] == O


def test_owner_uses_home_claude_when_config_dir_is_unset(tmp_path, monkeypatch):
    box = Box(tmp_path)
    _own_terminal(box)
    _inproc(monkeypatch, box)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setenv("HOME", str(box.home))
    assert crew_autocycle.claude_config_dir() == os.path.join(str(box.home), ".claude")
    assert crew_autocycle.session_owner(SESSION)["pid"] == O


def test_owner_unknown_without_record(tmp_path, monkeypatch):
    box = Box(tmp_path)
    box.procs(cf.session_table())
    _inproc(monkeypatch, box)
    owner = crew_autocycle.session_owner(SESSION)
    assert "no session record under" in owner["unknown"]
    assert crew_autocycle.classify(owner)[0] == "unknown"


def test_owner_unknown_on_session_id_mismatch(tmp_path, monkeypatch):
    box = Box(tmp_path)
    _own_terminal(box, session=OTHER_SESSION)
    _inproc(monkeypatch, box)
    assert "names another session" in crew_autocycle.session_owner(SESSION)["unknown"]


def test_owner_unknown_on_proc_start_mismatch(tmp_path, monkeypatch):
    box = Box(tmp_path)
    _own_terminal(box, proc_start=1)
    _inproc(monkeypatch, box)
    assert "reused pid" in crew_autocycle.session_owner(SESSION)["unknown"]


@pytest.mark.parametrize("text", ["{not json", "[1, 2]"], ids=["unreadable", "non-object"])
def test_owner_unknown_on_unreadable_record(tmp_path, monkeypatch, text):
    box = Box(tmp_path)
    box.procs(cf.session_table())
    (box.config / "sessions").mkdir(parents=True, exist_ok=True)
    (box.config / "sessions" / f"{O}.json").write_text(text, encoding="utf-8")
    _inproc(monkeypatch, box)
    assert "unreadable or not a JSON object" in crew_autocycle.session_owner(SESSION)["unknown"]


def test_owner_unknown_on_a_truncated_chain(tmp_path, monkeypatch):
    box = Box(tmp_path)
    chain = {H + i: P(H + i + 1, TTY, 1) for i in range(0, 30)}
    box.procs(chain)
    _inproc(monkeypatch, box)
    assert "deeper than 16" in crew_autocycle.session_owner(SESSION)["unknown"]


def _owner(entrypoint="cli", kind="interactive", tty=TTY):
    return {"pid": O, "record": {"kind": kind, "entrypoint": entrypoint}, "info": {"tty": tty}}


def test_classify_terminal_requires_allowlist_and_tty():
    assert crew_autocycle.classify(_owner())[0] == "terminal"
    assert crew_autocycle.classify(_owner(tty=None))[0] == "unknown"
    assert crew_autocycle.classify(_owner(kind=None))[0] == "unknown"


def test_classify_headless_on_sdk_entrypoint():
    assert crew_autocycle.classify(_owner(entrypoint="sdk-cli")) == ("headless", "entrypoint sdk-cli")
    assert crew_autocycle.classify(_owner(entrypoint="sdk-ts", tty=TTY))[0] == "headless"


def test_classify_headless_on_no_tty():
    assert crew_autocycle.classify(_owner(tty=0)) == ("headless", "no controlling terminal: tty_nr 0")
    assert crew_autocycle.classify(_owner(kind="background"))[0] == "headless"


def test_classify_unknown_entrypoint_is_unknown_not_headless():
    cls, evidence = crew_autocycle.classify(_owner(entrypoint="remote_mobile"))
    assert cls == "unknown" and "remote_mobile" in evidence


def test_ps_line_parses_for_hosts_without_proc():
    assert crew_autocycle._parse_ps("  412 ttys003  /usr/local/bin/claude") == {  # pylint: disable=protected-access
        "ppid": 412, "tty": crew_autocycle._tty_token("ttys003"), "start": None, "comm": "claude"}  # pylint: disable=protected-access
    assert crew_autocycle._parse_ps("1 ?? launchd")["tty"] == 0  # pylint: disable=protected-access
    assert crew_autocycle._parse_ps("garbage") is None  # pylint: disable=protected-access


def test_unarmed_reads_no_record(tmp_path, monkeypatch):
    box = Box(tmp_path)
    box.machine(enabled=False, method="tmux")
    _own_terminal(box)
    _inproc(monkeypatch, box)

    def boom(*_args, **_kwargs):
        raise AssertionError("an unarmed machine read a session record")

    monkeypatch.setattr(crew_autocycle, "session_owner", boom)
    got = crew_autocycle.plan(str(box.root), SESSION, global_path=str(box.home / ".claude" / "crew" / "config.json"))
    assert got["status"] == "off"


@pytest.mark.parametrize("flavor", FLAVORS)
def test_unarmed_is_silent(flavor, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    box.machine(enabled=False, method="tmux" if flavor == "sh" else "sendkeys")
    _own_terminal(box)
    result = box.run(flavor, "--dry-run")
    assert (result.stdout, box.log()) == ("", "")


# --- 2. must-allow ---------------------------------------------------------------

@needs_bash
def test_tmux_own_pane_sends(tmp_path):
    box = Box(tmp_path)
    _target(box, "sh")
    _own_terminal(box)
    result = box.run("sh", "--dry-run")
    assert "would send\n  method: tmux" in result.stdout, result.stderr


@needs_bash
def test_tmux_pane_running_claude_directly_sends(tmp_path):
    """`tmux new claude`: the pane's own process IS the session (measured)."""
    box = Box(tmp_path)
    _target(box, "sh")
    box.tmux(pane_pid=O)
    _own_terminal(box)
    assert "would send" in box.run("sh", "--dry-run").stdout


@pytest.mark.parametrize("flavor", FLAVORS)
def test_xdotool_window_on_strict_ancestor_sends(flavor, tmp_path):
    """The window belongs to the terminal ABOVE the session, never to the
    session's own process (r1 FIX test_autoclear_binding.py:357)."""
    box = Box(tmp_path)
    _target(box, flavor, "xdotool" if flavor == "sh" else None)
    _own_terminal(box)
    result = box.run(flavor, "--dry-run")
    assert "would send" in result.stdout, result.stdout + result.stderr
    assert f"pid {T}, owner pid]" in result.stdout


@pytest.mark.parametrize("flavor", FLAVORS)
def test_window_owned_by_the_session_process_itself_is_not_its_terminal(flavor, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor, "xdotool" if flavor == "sh" else None)
    box.windows([{"id": 4242, "pid": O, "title": "Claude Code"}], xdotool=flavor == "sh")
    _own_terminal(box)
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout
    assert "no window belongs to any ancestor of this session's process" in result.stderr, result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("bound", [True, False], ids=["terminal", "unknown"])
def test_notify_text_is_unchanged_for_terminal_and_unknown(flavor, bound, tmp_path):
    box = Box(tmp_path)
    box.machine(method="notify")
    if bound:
        _own_terminal(box)
    else:
        box.procs(cf.session_table())
    result = box.run(flavor)
    assert json.loads(result.stdout) == {"systemMessage": PLAIN_NOTIFY}, result.stdout + result.stderr


# --- 3. must-block: a headless child ---------------------------------------------

_HEADLESS_METHODS = [("sh", "auto"), ("sh", "tmux"), ("sh", "xdotool"), ("sh", "notify"),
                     ("ps1", "auto"), ("ps1", "sendkeys"), ("ps1", "notify")]


@pytest.mark.parametrize("flavor,method", [
    pytest.param(f, m, marks=needs_bash if f == "sh" else needs_pwsh) for f, m in _HEADLESS_METHODS])
def test_headless_child_in_parent_pane_types_nothing(flavor, method, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor, method if method in ("xdotool", "sendkeys") else None)
    box.machine(method=method)
    box.windows([{"id": 4242, "pid": T, "title": "Claude Code"}], xdotool=flavor == "sh")
    if flavor == "sh":
        box.tmux()
    _child_of_parent(box)
    result = box.run(flavor, "--dry-run")
    assert "method: notify-headless" in result.stdout, result.stdout + result.stderr
    assert "entrypoint sdk-cli" in result.stdout


@needs_bash
def test_headless_child_with_no_tty_types_nothing(tmp_path):
    """tty_nr 0 alone is headless, whatever the entrypoint says (sh only:
    native Windows has no controlling terminal to read)."""
    box = Box(tmp_path)
    _target(box, "sh")
    _child_of_parent(box, tty=0, entrypoint="cli")
    result = box.run("sh", "--dry-run")
    assert "method: notify-headless" in result.stdout, result.stderr
    assert "no controlling terminal: tty_nr 0" in result.stdout


@pytest.mark.parametrize("flavor", FLAVORS)
def test_headless_notify_names_handoff_resume_and_restart(flavor, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    _child_of_parent(box)
    result = box.run(flavor)
    message = json.loads(result.stdout)["systemMessage"]
    assert message == (
        "crew: this session has no terminal of its own (entrypoint sdk-cli), so nothing was cleared or "
        "typed. Its handoff is written and verified at .work/HANDOFF.md; resume: /crew:done T-0001. "
        "The process that started this session must start a new one to continue.")
    assert "sent - method notify-headless: " + message in box.log()
    assert "would have sent" not in box.log()
    assert box.sent_marker().exists()


@pytest.mark.parametrize("flavor", FLAVORS)
def test_headless_notify_fires_once(flavor, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    _child_of_parent(box)
    first, second = box.run(flavor), box.run(flavor)
    assert "systemMessage" in first.stdout
    assert (second.stdout, second.returncode) == ("", 0)
    assert box.log().count("notify-headless") == 1


@needs_bash
@needs_pwsh
def test_headless_notify_parity(tmp_path):
    texts = []
    for flavor in ("sh", "ps1"):
        box = Box(tmp_path / flavor)
        _target(box, flavor)
        _child_of_parent(box)
        texts.append(json.loads(box.run(flavor).stdout)["systemMessage"])
    assert texts[0] == texts[1]


# --- 4. must-block: the walk crosses another session -------------------------------

@pytest.mark.parametrize("flavor", FLAVORS)
def test_walk_through_another_session_refuses(flavor, tmp_path):
    """An INTERACTIVE child under its own pty (`script -qc claude`) is a
    terminal, but its parent's pane and window are not its own (r1 BLOCK
    crew_autocycle.py:786, r1 FIX auto-clear.ps1:733)."""
    box = Box(tmp_path)
    _target(box, flavor)
    box.record()
    box.record(pid=PARENT, session=OTHER_SESSION, proc_start=PARENT_START)
    box.procs({H: P(O, TTY_OTHER, 1), O: P(SCRIPT, TTY_OTHER, cf.OWNER_START, "claude"),
               SCRIPT: P(SHELL, TTY, 1, "script"), SHELL: P(PARENT, TTY, 1),
               PARENT: P(T, TTY, PARENT_START, "claude"), T: P(1, 0, 1, "terminal")})
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout
    assert f"passes through another Claude Code session (pid {PARENT})" in result.stderr, result.stderr


@needs_bash
@pytest.mark.parametrize("method", ["tmux", "xdotool"])
def test_walk_through_an_unrecorded_claude_refuses(method, tmp_path):
    """A Claude Code process with no record (another config dir) still ends
    the walk: its comm is claude. Same tty as the child, so the shared-window
    scan alone would not catch it -- only the walk does."""
    box = Box(tmp_path)
    _target(box, "sh", method)
    box.record()
    box.procs({H: P(O, TTY, 1), O: P(PARENT, TTY, cf.OWNER_START, "claude"),
               PARENT: P(T, TTY, PARENT_START, "claude"), T: P(1, 0, 1, "terminal")})
    result = box.run("sh", "--dry-run")
    assert f"passes through another Claude Code session (pid {PARENT})" in result.stderr, result.stderr


@needs_bash
@pytest.mark.parametrize("parent_comm", ["2.1.289", "node"])
@pytest.mark.parametrize("method", ["tmux", "xdotool"])
def test_parent_pane_on_another_tty_refuses(method, parent_comm, tmp_path):
    """Review round 1 BLOCK (crew_autocycle.py:696-760): an interactive child
    on its own pty (`script`), whose parent session's record is under a
    DIFFERENT config dir and whose comm is not `claude` (a versioned native
    binary, or node). No record and no comm gives the parent away, so the
    tty is the proof: every process from the session up to the pane must be
    on the session's own tty (or none)."""
    box = Box(tmp_path)
    box.record()
    cf.write_session_record(tmp_path / "otherconfig", OTHER_SESSION, PARENT, proc_start=PARENT_START)
    box.procs({H: P(O, TTY_OTHER, 1), O: P(SCRIPT, TTY_OTHER, cf.OWNER_START, "claude"),
               SCRIPT: P(SHELL, TTY_OTHER, 1, "script"), SHELL: P(PARENT, 0, 1, "bash"),
               PARENT: P(T, TTY, PARENT_START, parent_comm), T: P(1, 0, 1, "terminal")})
    _target(box, "sh", method)
    result = box.run("sh", "--dry-run")
    assert "would send" not in result.stdout, result.stdout
    if method == "tmux" and parent_comm == "node":  # a versioned comm ends the walk first
        assert f"pid {PARENT} is on tty_nr {TTY}" in result.stderr, result.stderr


@needs_bash
def test_tmux_chain_with_an_unreadable_tty_refuses(tmp_path):
    box = Box(tmp_path)
    _target(box, "sh")
    box.record()
    box.procs({H: P(O, TTY, 1), O: P(SHELL, TTY, cf.OWNER_START, "claude"),
               SHELL: {"ppid": T, "tty": None, "start": 1, "comm": "bash"}, T: P(1, TTY, 1, "terminal")})
    result = box.run("sh", "--dry-run")
    assert "would send" not in result.stdout
    assert f"the controlling terminal of pid {SHELL}, between this session" in result.stderr, result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_walk_through_a_versioned_claude_binary_refuses(flavor, tmp_path):
    """A native install runs as `~/.local/share/claude/versions/<x.y.z>`, so
    its comm is the version: it ends the walk like `claude` does (NIT 1)."""
    box = Box(tmp_path)
    _target(box, flavor, "xdotool" if flavor == "sh" else None)
    box.record()
    box.procs({H: P(O, TTY, 1), O: P(PARENT, TTY, cf.OWNER_START, "claude"),
               PARENT: P(T, TTY, PARENT_START, "2.1.289"), T: P(1, 0, 1, "terminal")})
    result = box.run(flavor, "--dry-run")
    assert f"passes through another Claude Code session (pid {PARENT})" in result.stderr, result.stderr


# --- review round 1 FIX 1: a stub is honoured only when nothing can be typed -------

@pytest.mark.parametrize("flavor", FLAVORS)
def test_proc_stub_is_ignored_without_inhibit(flavor, tmp_path):
    """CREW_AUTOCLEAR_PROC_STUB (and the window stub) can reach a hook from a
    repo's settings env, so they are read only while CREW_AUTOCLEAR_INHIBIT
    is set -- when no keystroke can be sent anyway."""
    box = Box(tmp_path)
    _target(box, flavor)
    _own_terminal(box)
    with_stub = box.run(flavor, "--dry-run")
    without = box.run(flavor, "--dry-run", extra={"CREW_AUTOCLEAR_INHIBIT": ""})
    assert "would send" in with_stub.stdout, with_stub.stderr
    assert "would send" not in without.stdout, without.stdout
    # sh: the hook's own (real) walk refuses the stubbed pane first; either way the stub was not read.
    assert ("could not identify this session's process" in without.stderr
            or "could not be confirmed" in without.stderr), without.stderr


def test_window_stub_is_ignored_without_inhibit(tmp_path, monkeypatch):
    path = tmp_path / "windows.json"
    path.write_text(json.dumps([{"id": 1, "pid": T, "title": "x"}]), encoding="utf-8")
    monkeypatch.setenv("CREW_AUTOCLEAR_WINDOW_STUB", str(path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setenv("CREW_AUTOCLEAR_INHIBIT", "1")
    assert crew_autocycle.list_windows()[0] == [{"id": 1, "pid": T, "title": "x"}]
    monkeypatch.delenv("CREW_AUTOCLEAR_INHIBIT")
    assert crew_autocycle.list_windows() == (None, "xdotool is not on PATH")


@needs_bash
@pytest.mark.skipif(os.name == "nt", reason="the tmux sender is POSIX-only - NOT run here")
def test_spawn_inhibit_spawns_the_sender_but_types_nothing(tmp_path):
    """CREW_AUTOCLEAR_INHIBIT=spawn (for the suite's spawn tests) still honours
    the stubs, so the sender it spawns must stop before any keystroke."""
    box = Box(tmp_path)
    box.machine(method="tmux", delaySeconds=0)
    _own_terminal(box)
    calls = tmp_path / "tmux-calls.log"
    bindir = tmp_path / "fakebin"
    cf.write_shim(bindir, "tmux", f'#!/bin/sh\necho "$*" >> "{calls}"\necho {T}\n')
    box.env.update(cf.shim_env("sh", bindir, TMUX="/tmp/fake,1,0", TMUX_PANE="%7"))
    box.run("sh", extra={"CREW_AUTOCLEAR_INHIBIT": "spawn"})
    assert "sent - method tmux" in box.log(), box.log()
    time.sleep(2)  # delaySeconds 0: an unguarded sender has typed long before this
    assert "send-keys" not in calls.read_text(encoding="utf-8"), calls.read_text(encoding="utf-8")


# --- review round 1 FIX 3: a live session whose record cannot be read --------------

@pytest.mark.parametrize("flavor", FLAVORS)
def test_unreadable_live_sibling_record_refuses_the_title_fallback(flavor, tmp_path):
    box = Box(tmp_path)
    _title_only(box, flavor, 999999 if flavor == "sh" else T)
    box.record()
    (box.config / "sessions" / f"{SIBLING}.json").write_text("{not json", encoding="utf-8")
    box.procs({**cf.session_table(), SIBLING: P(1, TTY_OTHER, 77, "claude")})
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout, result.stdout
    assert "another session cannot be ruled out" in result.stderr, result.stderr


def test_other_sessions_cannot_rule_out_a_live_unreadable_record(tmp_path, monkeypatch):
    box = Box(tmp_path)
    box.record()
    (box.config / "sessions" / f"{SIBLING}.json").write_text("[]", encoding="utf-8")
    (box.config / "sessions" / f"{SIBLING + 1}.json").write_text("{not json", encoding="utf-8")
    box.procs({**cf.session_table(), SIBLING: P(1, TTY_OTHER, 77, "claude")})
    _inproc(monkeypatch, box)
    assert crew_autocycle.other_sessions(O) is None  # SIBLING is live; SIBLING + 1 is gone and ignored
    (box.config / "sessions" / f"{SIBLING}.json").unlink()
    assert crew_autocycle.other_sessions(O) == set()


# --- review round 1 FIX 2: an exited parent is the top; an unreadable one is not ---

@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("parent", ["gone", "unreadable"])
def test_exited_parent_ends_the_chain_but_unreadable_does_not(flavor, parent, tmp_path):
    box = Box(tmp_path)
    _title_only(box, flavor, 999999 if flavor == "sh" else T)
    box.record()
    table = {H: P(O, TTY, 1), O: P(SHELL, TTY, cf.OWNER_START, "claude"), SHELL: P(SHELL + 1, TTY, 1),
             SHELL + 1: {"gone": True} if parent == "gone" else None}
    if flavor == "ps1":
        table[T] = P(1, 0, 1, "terminal")  # the console window's owner, read for its name
    box.procs(table)
    result = box.run(flavor, "--dry-run")
    if parent == "gone":
        assert "would send" in result.stdout, result.stdout + result.stderr
    else:
        assert "would send" not in result.stdout
        assert f"the parent of pid {SHELL + 1} could not be read" in result.stderr, result.stderr


@needs_pwsh
def test_ps1_live_lookup_tells_an_exited_parent_from_an_unreadable_one():
    """Review round 1 FIX 2, the real (unstubbed) Windows path, run from the
    live functions: no such process is an exit; a parent id that could not be
    read (Get-CrewParentId's 0) is unreadable, never the top of the chain."""
    with open(os.path.join(_SCRIPTS, "auto-clear.ps1"), encoding="utf-8") as handle:
        source = handle.read()

    def _extract_ps1_function(text, name):
        start = text.index(f"function {name}")
        depth, i = 0, text.index("{", start)
        while True:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                return text[start:i + 1]
            i += 1

    funcs = "\n".join(_extract_ps1_function(source, name) for name in (
        "Test-CrewTrue", "Get-CrewChild", "Get-CrewProcStub", "Get-CrewProcLookup"))
    script = (funcs + "\n$script:crewProcStubRead = $false\n"
              "function Get-CrewParentId([int]$Id) { return 0 }\n"
              "$a = Get-CrewProcLookup 999999; $b = Get-CrewProcLookup $PID\n"
              "function Get-Process { throw [System.UnauthorizedAccessException]::new('denied') }\n"
              "$c = Get-CrewProcLookup 4242\n"
              "Write-Output \"$($null -eq $a.Info)|$($a.Gone)|$($null -eq $b.Info)|$($b.Gone)|$($c.Gone)\"\n")
    env = {k: v for k, v in os.environ.items() if k not in ("CREW_AUTOCLEAR_PROC_STUB", "CREW_AUTOCLEAR_INHIBIT")}
    done = cf.subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                             text=True, check=False, timeout=60, env=env, stdin=cf.subprocess.DEVNULL)
    assert done.stdout.strip() == "True|True|True|False|False", done.stdout + done.stderr


# --- 5. must-block: a shared window ------------------------------------------------

_SHARED = {
    "sibling-record": {SIBLING: P(T, TTY_OTHER, 77, "claude")},
    "reparented-tmux-client": {SIBLING: P(T, TTY_OTHER, 1, "tmux: client")},
    "plain-shell": {SIBLING: P(T, TTY_OTHER, 1, "bash")},
}


@needs_bash
@pytest.mark.parametrize("case", [*_SHARED, "failed-scan"])
def test_shared_window_other_tty_refuses(case, tmp_path):
    """One terminal server, one X window, many tabs: proving the owner is an
    ancestor does not prove the window (r1 FIX :786, r2 FIX :619)."""
    box = Box(tmp_path)
    _target(box, "sh", "xdotool")
    box.record()
    if case == "sibling-record":
        box.record(pid=SIBLING, session=OTHER_SESSION, proc_start=77)
    table = {**cf.session_table(), **_SHARED.get(case, {})}
    box.procs(table, scan_fails=case == "failed-scan")
    result = box.run("sh", "--dry-run")
    assert "would send" not in result.stdout
    expect = "could not be listed" if case == "failed-scan" else "also hosts another"
    assert expect in result.stderr, result.stderr


@needs_bash
def test_shared_window_control_same_tty_sends(tmp_path):
    """The control: a second process under the terminal on the SAME tty (the
    session's own shell) is not another terminal."""
    box = Box(tmp_path)
    _target(box, "sh", "xdotool")
    box.record()
    box.procs({**cf.session_table(), SIBLING: P(T, TTY, 1, "bash")})
    assert "would send" in box.run("sh", "--dry-run").stdout


@needs_pwsh
def test_ps1_window_owner_above_another_session_refuses(tmp_path):
    box = Box(tmp_path)
    _target(box, "ps1")
    box.record()
    box.record(pid=SIBLING, session=OTHER_SESSION, proc_start=77)
    box.procs({**cf.session_table(), SIBLING: P(T, 0, 77, "claude")})
    result = box.run("ps1", "--dry-run")
    assert "would send" not in result.stdout
    assert f"also hosts another Claude Code session (pid {SIBLING})" in result.stderr, result.stderr


# --- 6. could-not-tell is never "headless" or "safe" -------------------------------

@pytest.mark.parametrize("flavor", FLAVORS)
def test_unknown_owner_explicit_method_refuses(flavor, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    box.procs(cf.session_table())
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout
    assert "could not identify this session's process" in result.stderr, result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_unknown_owner_never_says_headless(flavor, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    box.procs(cf.session_table())
    result = box.run(flavor)
    text = result.stdout + result.stderr + box.log()
    assert "no terminal" not in text and "headless" not in text, text


@needs_bash
def test_unknown_owner_auto_is_plain_notify(tmp_path):
    box = Box(tmp_path)
    _target(box, "sh")
    box.machine(method="auto")
    box.procs(cf.session_table())
    result = box.run("sh")
    assert json.loads(result.stdout) == {"systemMessage": PLAIN_NOTIFY}
    assert "auto falls back to notify" in box.log()


@pytest.mark.parametrize("flavor", FLAVORS)
def test_unlisted_entrypoint_is_unknown_and_logged(flavor, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    _own_terminal(box, entrypoint="remote_mobile")
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout
    assert "'remote_mobile' is not one measured to have a terminal" in result.stderr + box.log(), result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("where", ["config-dir", "home-only"])
def test_claude_config_dir_is_where_the_record_is_looked_for(flavor, where, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    box.procs(cf.session_table())
    custom = tmp_path / "custom-config"
    box.record(config=custom if where == "config-dir" else box.config)
    box.env["CLAUDE_CONFIG_DIR"] = str(custom)
    result = box.run(flavor, "--dry-run")
    assert ("would send" in result.stdout) is (where == "config-dir"), result.stdout + result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("case", ["session-id", "proc-start"])
def test_mismatched_record_refuses(flavor, case, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    _own_terminal(box, **({"session": OTHER_SESSION} if case == "session-id" else {"proc_start": 9}))
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout
    assert ("names another session" if case == "session-id" else "reused pid") in result.stderr, result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("case", ["deep", "unreadable-parent"])
def test_truncated_chain_refuses(flavor, case, tmp_path):
    """r2 NIT :651: a chain that could not be read to the end proves nothing
    about what is above the break."""
    box = Box(tmp_path)
    _target(box, flavor)
    box.record()
    table = {H: P(O, TTY, 1), O: P(SHELL, TTY, cf.OWNER_START, "claude")}
    if case == "deep":
        table.update({SHELL + i: P(SHELL + i + 1, TTY, 1) for i in range(0, 30)})
    else:
        table[SHELL] = None
    box.procs(table)
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout
    if flavor == "ps1":  # sh: the hook's own walk is cut at the same place and refuses first
        expect = "deeper than 16" if case == "deep" else f"the parent of pid {SHELL} could not be read"
        assert expect in result.stderr, result.stderr


@pytest.mark.parametrize("method", ["tmux", "xdotool"])
@pytest.mark.parametrize("case", ["deep", "unreadable-parent"])
def test_truncated_chain_refuses_from_the_owner(method, case, tmp_path, monkeypatch):
    box = Box(tmp_path)
    box.windows([{"id": 4242, "pid": T, "title": "Claude Code"}], xdotool=False)
    box.record()
    table = {H: P(O, TTY, 1), O: P(SHELL, TTY, cf.OWNER_START, "claude")}
    if case == "deep":
        table.update({SHELL + i: P(SHELL + i + 1, TTY, 1) for i in range(0, 30)})
    else:
        table[SHELL] = None
    box.procs(table)
    _inproc(monkeypatch, box)
    owner = crew_autocycle.session_owner(SESSION)
    got = {"method": method, "target": "%7", "label": "%7", "pane_pid": T}
    proof = crew_autocycle.prove_target(owner, got, {"windowTitle": ""})
    expect = "deeper than 16" if case == "deep" else f"the parent of pid {SHELL} could not be read"
    assert not proof["ok"] and expect in proof["reason"], proof


def _title_only(box, flavor, pid):
    if flavor == "sh":
        box.machine(method="xdotool", windowTitle="Claude")
    else:
        box.machine(method="sendkeys", windowTitle="Claude")
    box.windows([{"id": 4242, "pid": pid, "title": "Claude - mine"}], xdotool=flavor == "sh")


@pytest.mark.parametrize("flavor", FLAVORS)
def test_window_without_pid_refuses_with_sibling(flavor, tmp_path):
    box = Box(tmp_path)
    _title_only(box, flavor, 0)
    box.record()
    box.record(pid=SIBLING, session=OTHER_SESSION, proc_start=77)
    box.procs({**cf.session_table(), SIBLING: P(1, TTY_OTHER, 77, "claude")})
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout
    assert "has no owning process" in result.stderr, result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_window_without_pid_unchanged_without_sibling(flavor, tmp_path):
    """r2 BLOCK :658's failing control: the same window with no other session
    live still sends, exactly as before T-0016."""
    box = Box(tmp_path)
    _title_only(box, flavor, 0)
    _own_terminal(box)
    result = box.run(flavor, "--dry-run")
    assert "has no owning process" not in result.stderr and "title alone" not in result.stderr, result.stderr
    if flavor == "sh":  # ps1's own owner-name check then decides pid 0 by the host's Get-Process
        assert "would send" in result.stdout and "title fallback]" in result.stdout, result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_title_fallback_refuses_with_sibling(flavor, tmp_path):
    box = Box(tmp_path)
    _title_only(box, flavor, 999999)
    box.record()
    box.record(pid=SIBLING, session=OTHER_SESSION, proc_start=77)
    box.procs({**cf.session_table(), SIBLING: P(1, TTY_OTHER, 77, "claude")})
    result = box.run(flavor, "--dry-run")
    assert "would send" not in result.stdout
    assert "found by its title alone" in result.stderr, result.stderr


@pytest.mark.parametrize("flavor", FLAVORS)
def test_a_stale_sibling_record_is_not_a_live_session(flavor, tmp_path):
    """Claude Code leaves a record behind when a session is killed
    (measured): a record whose process is gone, or whose start time names a
    reused pid, is not another live session."""
    box = Box(tmp_path)
    _title_only(box, flavor, 999999 if flavor == "sh" else T)
    box.record()
    box.record(pid=SIBLING, session=OTHER_SESSION, proc_start=77)
    box.record(pid=SIBLING + 1, session=OTHER_SESSION, proc_start=78)
    box.procs({**cf.session_table(), SIBLING + 1: P(1, TTY_OTHER, 5, "bash")})
    result = box.run(flavor, "--dry-run")
    assert "would send" in result.stdout, result.stdout + result.stderr


# --- 7. resume typing -----------------------------------------------------------

@needs_bash
@pytest.mark.skipif(os.name == "nt", reason="the tmux resume path is POSIX-only - NOT run here")
@pytest.mark.parametrize("who", ["headless-child", "own-terminal"])
def test_resume_headless_child_types_nothing(who, tmp_path):
    from test_resume_typing import SESSION as RSESSION, Fixture  # pylint: disable=import-outside-toplevel
    fx = Fixture(tmp_path)
    if who == "headless-child":
        cf.write_session_record(fx.home / ".claude", RSESSION, O, entrypoint="sdk-cli")
        cf.write_session_record(fx.home / ".claude", OTHER_SESSION, PARENT, proc_start=PARENT_START)
        fx.binding.update(cf.proc_stub(fx.home, {
            H: P(O, 0, 1), O: P(SHELL, 0, cf.OWNER_START, "claude"), SHELL: P(PARENT, 0, 1),
            PARENT: P(T, TTY, PARENT_START, "claude"), T: P(1, 0, 1, "terminal")}))
    done = fx.sh("--dry-run")
    if who == "headless-child":
        assert "refused - auto-resume types only into this session's own terminal: this session has no " \
               "terminal of its own (entrypoint sdk-cli)" in done.stdout, done.stdout + done.stderr
        assert not fx.tmux_calls().count("send-keys")
    else:
        assert "autoresume: would send\n  method: tmux" in done.stdout, done.stdout + done.stderr


@needs_pwsh
@pytest.mark.parametrize("who", ["headless-child", "unknown"])
def test_ps1_resume_refuses_without_a_terminal(who, tmp_path):
    from test_resume_typing import SESSION as RSESSION, Fixture  # pylint: disable=import-outside-toplevel
    fx = Fixture(tmp_path)
    (fx.home / ".claude" / "sessions" / f"{O}.json").unlink()
    if who == "headless-child":
        cf.write_session_record(fx.home / ".claude", RSESSION, O, entrypoint="sdk-cli")
    done = fx.ps1("-DryRun")
    expect = "this session has no terminal of its own" if who == "headless-child" else \
        "could not identify this session's process"
    assert "autoresume: refused - auto-resume types only into this session's own terminal: " in done.stdout
    assert expect in done.stdout, done.stdout + done.stderr


# --- 8. order: the binding runs before the claim -----------------------------------

@pytest.mark.parametrize("flavor", FLAVORS)
def test_binding_refusal_leaves_sent_marker_unclaimed(flavor, tmp_path):
    box = Box(tmp_path)
    _target(box, flavor)
    box.procs(cf.session_table())  # no record: unknown, explicit method refuses
    result = box.run(flavor)
    assert "could not identify this session's process" in result.stderr, result.stderr
    assert not box.sent_marker().exists()
    _own_terminal(box)  # corrected mid-session: the next Stop still gets its one attempt
    box.run(flavor)
    assert box.sent_marker().exists()
    assert "would have sent, but CREW_AUTOCLEAR_INHIBIT is set" in box.log()


@pytest.mark.parametrize("flavor", FLAVORS)
def test_binding_runs_after_the_handoff_checks(flavor, tmp_path):
    """A headless child still has its handoff verified first: without one it
    is refused for the handoff, and gets no notice."""
    box = Box(tmp_path)
    _target(box, flavor)
    _child_of_parent(box)
    (box.root / ".work" / "HANDOFF.md").unlink()
    result = box.run(flavor)
    assert "has not been written" in result.stderr, result.stderr
    assert "systemMessage" not in result.stdout and not box.sent_marker().exists()
