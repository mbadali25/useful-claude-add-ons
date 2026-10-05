"""T-0013: auto-resume TYPES the rendered resume command into its own session.

Must-fire and must-not-fire for each rule the typing path depends on:

  - the plan (`crew_autocycle.resume_plan`): T-0006's `decide` first, then
    the machine's onlyRepos/onlySessions narrowing, then the method -- tmux
    into the pane whose pid is an ancestor, `auto` never sendkeys on Windows,
    wtype refused, notify types nothing;
  - the sender (`auto-clear.sh --resume`, `auto-clear.ps1 -Resume`): the
    per-handoff marker claimed only after every refusal, the run recorded
    before anything is spawned, then delay -> ready probe -> inhibit -> keys;
  - the entry point: the context hook starts this flavour's sender on
    SessionStart clear|compact only, before its own claim, and a failing
    sender never costs the session its context.

No test sends a keystroke or enumerates a real window: every run sets
CREW_AUTOCLEAR_INHIBIT, points HOME at the fixture, puts a `tmux` stub that
records its argv first on PATH (the sender's keys would reach the stub even
without the inhibit), and gives the .ps1 a stubbed window list. The .ps1
cases are told they are on Windows (`OS=Windows_NT`) and skip without pwsh --
a skip there means the PowerShell flavour was NOT run.

Every case resumes a manual /compact: it is bound by session_id, the same on
every host, where a /clear is bound by the Claude Code process (T-0042) and
crew_resume_hook's `claude` stand-in covers that.
"""
import json
import os
import re
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import context_fixtures
import crew_autocycle
import crew_context
import crew_fixtures
import crew_resume
import crew_state
from poll_fixtures import poll_until

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_PLUGIN = context._ROOT  # pylint: disable=protected-access
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="bash not installed - the sh flavour was NOT run")
needs_pwsh = pytest.mark.skipif(_PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")
needs_posix = pytest.mark.skipif(os.name == "nt", reason="the tmux path is POSIX-only - NOT run here")

SESSION = "sess-t0013"
PROMPT = "/crew:done T-0001"
PANE = "%9"
RULE = "\x1b[38;5;244m" + "─" * 40 + "\x1b[39m"
READY = f"transcript line\n{RULE}\n\x1b[39m❯ \n{RULE}\n  ⏸ manual mode on\n"
PLACEHOLDER = f"{RULE}\n\x1b[39m❯ \x1b[2mTry \"how does <filepath> work?\"\x1b[0m\n{RULE}\n"
TYPED = f"{RULE}\n\x1b[39m❯ hello there\n{RULE}\n"
BUSY = (f"\x1b[38;5;246m✻ Running SessionStart hooks…\x1b[39m\n{RULE}\n"
        f"\x1b[38;5;246m❯ \x1b[39m\n{RULE}\n  esc to interrupt\n")

_TMUX_STUB = """#!/usr/bin/env bash
# Records its argv; never talks to a tmux server.
printf '%s\\n' "$*" >> "$CREW_TEST_TMUX_LOG"
case "$1" in
  display-message) echo "${CREW_TEST_PANE_PID:-$PPID}" ;;
  capture-pane) cat "$CREW_TEST_PANE" 2>/dev/null ;;
esac
exit 0
"""


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout.strip()


class Fixture:
    """A crew repo with T-0001, its own HOME and machine file, a handoff that
    names `resume: <line>`, a manual-/compact record and an author record
    binding the note to SESSION, and a tmux stub."""

    def __init__(self, tmp_path, resume_line=PROMPT, auto_clear=None, resume=None):
        self.tmp = tmp_path
        self.root = context_fixtures.make_repo(tmp_path)
        (self.root / ".work" / "tickets" / "T-0001").mkdir(parents=True)
        (self.root / ".work" / "tickets" / "T-0001" / "spec.md").write_text("spec\n", encoding="utf-8")
        self.home = tmp_path / "home"
        self.global_path = self.home / ".claude" / "crew" / "config.json"
        self.global_path.parent.mkdir(parents=True)
        self.machine(auto_clear=auto_clear, resume=resume)
        branch = _git(self.root, "rev-parse", "--abbrev-ref", "HEAD")
        head = _git(self.root, "rev-parse", "--short", "HEAD")
        self.handoff = self.root / ".work" / "HANDOFF.md"
        self.handoff.write_text(
            f"# Handoff\nwritten: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            f"ticket: T-0001\nbranch: {branch}\nhead: {head}\nresume: {resume_line}\n\n"
            "## Done\n- the spec\n\n## Next action\nClose T-0001 with /crew:done.\n", encoding="utf-8")
        crew_resume.write_precompact_record(str(self.root), {"session_id": SESSION, "trigger": "manual"})
        crew_resume.record_author(str(self.root), SESSION, str(self.handoff))
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        stub = self.bin / "tmux"
        stub.write_text(_TMUX_STUB, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
        self.tmux_log = tmp_path / "tmux-argv.log"
        self.pane = tmp_path / "pane.txt"
        self.pane.write_text(READY, encoding="utf-8")
        # T-0016: SESSION bound to its own Claude Code process, in its own
        # terminal; the stub tmux reports that terminal as the pane's pid.
        self.binding = crew_fixtures.bind_session(self.home, SESSION)

    def machine(self, auto=True, auto_clear=None, resume=None):
        block = {"auto": auto, "typeDelaySeconds": 0, "readyTimeoutSeconds": 2}
        block.update(resume or {})
        data = {"resume": block}
        if auto_clear is not None:
            data["context"] = {"autoClear": auto_clear}
        self.global_path.write_text(json.dumps(data), encoding="utf-8")

    @property
    def key(self):
        return crew_resume.hashlib.sha256(self.handoff.read_text(encoding="utf-8").encode("utf-8")).hexdigest()[:16]

    @property
    def marker(self):
        return os.path.join(crew_resume.state_dir(str(self.root)), f"resume-typed-{self.key}")

    def env(self, tmux=True, **extra):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), CREW_AUTOCLEAR_INHIBIT="1",
                   CLAUDE_PROJECT_DIR=str(self.root), PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                   CREW_TEST_TMUX_LOG=str(self.tmux_log), CREW_TEST_PANE=str(self.pane),
                   CREW_TEST_PANE_PID=str(crew_fixtures.TERMINAL_PID), **self.binding,
                   CREW_VAULT_OPS=str(self.tmp / "absent-vault-ops.py"),
                   CREW_OBSIDIAN_CONFIG=str(self.tmp / "absent-obsidian.json"))
        for name in ("TMUX", "TMUX_PANE", "DISPLAY", "WAYLAND_DISPLAY", "OS"):
            env.pop(name, None)
        if tmux:
            env.update(TMUX="/tmp/crew-test-tmux,1,0", TMUX_PANE=PANE)
        env.update(extra)
        return env

    def plan(self, monkeypatch, tmux=True, flavour="sh", **extra):
        """resume_plan in-process, with this fixture's environment."""
        env = self.env(tmux=tmux, **extra)
        monkeypatch.setenv("PATH", env["PATH"])
        for name in ("CREW_TEST_TMUX_LOG", "CREW_TEST_PANE", "CREW_TEST_PANE_PID",
                     crew_fixtures.PROC_STUB_ENV, "CREW_AUTOCLEAR_INHIBIT"):
            if name in env:
                monkeypatch.setenv(name, env[name])
        return crew_autocycle.resume_plan(str(self.root), SESSION, "compact", global_path=str(self.global_path),
                                          env=env, flavour=flavour, plugin_root=_PLUGIN)

    def sh(self, *args, tmux=True, wait=True, **extra):
        done = subprocess.run([_BASH, os.path.join(_SCRIPTS, "auto-clear.sh").replace("\\", "/"), "--resume",
                               "--session", SESSION, "--source", "compact", "--root", str(self.root), *args],
                              cwd=str(self.root), env=self.env(tmux=tmux, **extra), capture_output=True,
                              text=True, check=False, timeout=120)
        if wait and "autoresume: typing" in done.stdout:
            self.wait_for_sender()
        return done

    def ps1(self, *args, method="sendkeys", **extra):
        stub = self.tmp / "windows.json"
        stub.write_text(json.dumps([{"id": 4242, "pid": crew_fixtures.TERMINAL_PID, "title": "crew session"}]),
                        encoding="utf-8")
        env = self.env(tmux=False, OS="Windows_NT", CREW_AUTOCLEAR_WINDOW_STUB=str(stub), **extra)
        if method is not None:
            self.machine(auto_clear={"method": method})
        return subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-File",
                               os.path.join(_SCRIPTS, "auto-clear.ps1"), "-Resume", "-Session", SESSION,
                               "-Source", "compact", "-Root", str(self.root), "-Python", sys.executable, *args],
                              cwd=str(self.root), env=env, capture_output=True, text=True, check=False,
                              timeout=120)

    def log(self):
        path = self.root / ".crew" / ".autoclear.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def wait_for_sender(self, timeout=20):
        """The detached sender's last word: it typed, would have, or refused."""
        return poll_until(self.log, lambda text: re.search(
            r"auto-resume: (would have typed|typed|refusing - the input line)", text), timeout)

    def tmux_calls(self):
        return self.tmux_log.read_text(encoding="utf-8") if self.tmux_log.exists() else ""

    def recorded(self):
        return os.path.isfile(crew_resume.state_path(str(self.root)))


@pytest.fixture
def fx(tmp_path):
    return Fixture(tmp_path)


# --- step 2: the plan --------------------------------------------------------

@needs_posix
def test_resume_plan_send_on_tmux_ancestor_pane(fx, monkeypatch):
    got = fx.plan(monkeypatch)

    assert (got["status"], got["method"], got["target"], got["command"], got["delay"], got["timeout"],
            got["key"], got["marker"].endswith(f"resume-typed-{fx.key}"), json.loads(got["decision"])["action"]) == \
        ("send", "tmux", PANE, PROMPT, "0", "2", fx.key, True, "run")


def test_resume_plan_off_when_decide_off(fx, monkeypatch):
    fx.machine(auto=None)

    got = fx.plan(monkeypatch)

    assert (got["status"], got["reason"], got["command"]) == ("off", "", "")


def test_resume_plan_refuses_on_decide_wait(tmp_path, monkeypatch):
    fx = Fixture(tmp_path, resume_line="/crew:done T-0002")

    got = fx.plan(monkeypatch)

    assert (got["status"], got["command"], got["marker"]) == ("refuse", "", "")
    assert got["reason"] == "auto-resume is waiting: .work/tickets/T-0002/ does not exist"


def test_resume_plan_refuses_without_tmux(fx, monkeypatch):
    fx.machine(auto_clear={"method": "tmux"})

    got = fx.plan(monkeypatch, tmux=False)

    assert (got["status"], got["reason"]) == \
        ("refuse", "method tmux but $TMUX is unset, so this session is not in a tmux pane")


@needs_posix
def test_resume_plan_refuses_non_ancestor_pane(fx, monkeypatch):
    got = fx.plan(monkeypatch, CREW_TEST_PANE_PID="999999")

    assert (got["status"], "is not an ancestor of this hook" in got["reason"]) == ("refuse", True), got


@pytest.mark.parametrize("narrowing", [{"onlyRepos": ["/nowhere/at/all"]}, {"onlySessions": ["another"]}])
def test_resume_plan_off_outside_only_repos(fx, monkeypatch, narrowing):
    fx.machine(auto_clear=narrowing)

    got = fx.plan(monkeypatch)

    assert (got["status"], got["reason"]) == ("off", "")


def test_resume_plan_refuses_wtype(fx, monkeypatch):
    fx.machine(auto_clear={"method": "wtype", "unsafeFocus": True})

    got = fx.plan(monkeypatch)

    assert (got["status"], "wtype types into whatever has focus" in got["reason"]) == ("refuse", True)


def test_resume_plan_auto_on_windows_is_notify(fx, monkeypatch):
    got = fx.plan(monkeypatch, tmux=False, OS="Windows_NT")

    assert (got["status"], got["method"], got["target"], got["delay"]) == ("send", "notify", "", "0")


@needs_posix
def test_resume_plan_command_is_rendered_prompt(tmp_path, monkeypatch):
    """The typed text is `render`'s, rebuilt from tokens, never the line."""
    fx = Fixture(tmp_path, resume_line="  /crew:done\t   T-0001   ")

    got = fx.plan(monkeypatch)

    assert (got["status"], got["command"]) == ("send", PROMPT)


def test_resume_plan_refuses_xdotool(fx, monkeypatch):
    """No probe can see an X11 input line, so resume never types through it."""
    monkeypatch.setattr(crew_autocycle, "resolve_method",
                        lambda cfg, env=None: {"ok": True, "method": "xdotool", "target": "1", "label": "w"})

    got = fx.plan(monkeypatch)

    assert (got["status"], "xdotool cannot see" in got["reason"]) == ("refuse", True)


def test_resume_plan_ps1_flavour_leaves_the_method_to_the_ps1(fx, monkeypatch):
    fx.machine(auto_clear={"method": "sendkeys"})

    got = fx.plan(monkeypatch, tmux=False, OS="Windows_NT", flavour="ps1")

    assert (got["status"], got["method"], got["command"]) == ("send", "sendkeys", PROMPT)


@pytest.mark.parametrize("value,expected", [(5, (5, 2)), (-1, (2, 2)), ("x", (2, 2)), (True, (2, 2))])
def test_resume_typing_reads_the_machine_file_and_rejects_unusable_values(fx, value, expected):
    fx.machine(resume={"typeDelaySeconds": value})

    assert crew_autocycle.resume_typing(str(fx.global_path)) == expected


def test_resume_typing_defaults_are_crew_states(tmp_path):
    assert crew_autocycle.resume_typing(str(tmp_path / "absent.json")) == \
        (crew_state.RESUME_DEFAULTS["typeDelaySeconds"], crew_state.RESUME_DEFAULTS["readyTimeoutSeconds"])


@pytest.mark.parametrize("capture,state", [
    (READY, "ready"),
    (PLACEHOLDER, "ready"),
    (TYPED, "nonempty"),
    (BUSY, "busy"),
    ("no prompt at all\n", "noprompt"),
    (f"❯ \n{RULE}\n", "noprompt"),
])
def test_probe_input_line(capture, state):
    assert crew_autocycle.probe_input_line(capture) == state


def test_cli_resume_plan_prints_every_field_and_a_terminator(fx):
    done = subprocess.run([sys.executable, os.path.join(_SCRIPTS, "crew_autocycle.py"), "resume-plan",
                           "--root", str(fx.root), "--session", SESSION, "--source", "startup"],
                          env=fx.env(), capture_output=True, text=True, check=False, timeout=60)

    assert (done.returncode, done.stdout.splitlines()) == (0, ["off"] + [""] * 10 + ["."])


# --- step 3: the sender --------------------------------------------------------

@needs_bash
@needs_posix
def test_types_rendered_prompt_via_tmux_stub(fx):
    dry = fx.sh("--dry-run")
    done = fx.sh()
    log = fx.wait_for_sender()

    assert dry.stdout.splitlines()[:5] == ["autoresume: would send", "  method: tmux",
                                           f"  target: {PANE} [pane pid " + dry.stdout.split("[pane pid ")[1]
                                           .split("]")[0] + "]", f"  command: {PROMPT}", "  delay: 0s"]
    assert done.stdout.strip() == f"autoresume: typing {PROMPT} in 0s (method tmux)"
    assert f"would have typed '{PROMPT}' into {PANE}, but CREW_AUTOCLEAR_INHIBIT is set" in log, log
    assert (os.path.isfile(fx.marker), fx.recorded()) == (True, True)
    assert f"capture-pane -p -e -t {PANE}" in fx.tmux_calls()
    assert "send-keys" not in fx.tmux_calls()


@needs_bash
@needs_posix
def test_second_run_same_handoff_types_nothing(fx):
    """The marker alone stops it: claimed by an earlier sender whose record
    never landed, the handoff is still unused to `decide`."""
    os.makedirs(os.path.dirname(fx.marker), exist_ok=True)
    with open(fx.marker, "w", encoding="utf-8"):
        pass

    done = fx.sh()

    assert done.stdout.strip() == ("autoresume: refused - this handoff was already typed once "
                                   f"(marker resume-typed-{fx.key} exists)")
    assert (fx.recorded(), "would have typed" in fx.log(), fx.tmux_calls().count("capture-pane")) == \
        (False, False, 0)


def _race(fx, *runs):
    """Start every (argv, env) at once; each one's stdout, in order."""
    # pylint: disable-next=consider-using-with
    procs = [subprocess.Popen(argv, cwd=str(fx.root), env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) for argv, env in runs]
    return [p.communicate(timeout=120)[0] for p in procs]


@needs_bash
@needs_posix
def test_both_flavours_type_at_most_once(fx):
    """Two senders on one SessionStart: exactly one gets as far as the keys."""
    sh = [_BASH, os.path.join(_SCRIPTS, "auto-clear.sh"), "--resume", "--session", SESSION,
          "--source", "compact", "--root", str(fx.root)]
    outs = _race(fx, (sh, fx.env()), (sh, fx.env()))
    fx.wait_for_sender()
    time.sleep(1)

    assert sum("autoresume: typing" in o for o in outs) == 1, outs
    assert fx.log().count("would have typed") == 1, fx.log()


@needs_pwsh
@needs_bash
def test_both_flavours_type_at_most_once_sh_and_ps1(fx):
    """Both flavours on one SessionStart (method sendkeys): the sh one refuses
    without claiming, the .ps1 one claims, records and reaches the keys."""
    fx.machine(auto_clear={"method": "sendkeys"})
    stub = fx.tmp / "windows.json"
    stub.write_text(json.dumps([{"id": 4242, "pid": crew_fixtures.TERMINAL_PID, "title": "crew session"}]),
                    encoding="utf-8")
    sh_env = fx.env(tmux=False, OS="Windows_NT")
    ps_env = fx.env(tmux=False, OS="Windows_NT", CREW_AUTOCLEAR_WINDOW_STUB=str(stub))
    outs = _race(fx, ([_BASH, os.path.join(_SCRIPTS, "auto-clear.sh"), "--resume", "--session", SESSION,
                       "--source", "compact", "--root", str(fx.root)], sh_env),
                 ([_PWSH, "-NoProfile", "-NonInteractive", "-File", os.path.join(_SCRIPTS, "auto-clear.ps1"),
                   "-Resume", "-Session", SESSION, "-Source", "compact", "-Root", str(fx.root),
                   "-Python", sys.executable], ps_env))

    assert "auto-clear.ps1's job" in outs[0], outs
    assert fx.log().count("would have sent, but CREW_AUTOCLEAR_INHIBIT is set") == 1, fx.log()
    assert (os.path.isfile(fx.marker), fx.recorded()) == (True, True)


@needs_bash
@pytest.mark.parametrize("auto_clear,expect", [
    ({"method": "wtype", "unsafeFocus": True}, "wtype types into whatever has focus"),
    ({"method": "sendkeys"}, "auto-clear.ps1's job"),
])
def test_refusing_flavour_leaves_marker_unclaimed(fx, auto_clear, expect):
    fx.machine(auto_clear=auto_clear)

    done = fx.sh()

    assert (expect in done.stdout, os.path.exists(fx.marker), fx.recorded()) == (True, False, False), done.stdout
    assert f"refusing - auto-resume: {done.stdout.strip()[len('autoresume: refused - '):]}" in fx.log()


@needs_bash
@needs_posix
def test_record_failure_types_nothing(fx):
    """A held resume-state lock: decide (read-only) says run, record cannot
    land. The marker stays claimed (refusing direction), nothing is typed."""
    lock = crew_resume.state_path(str(fx.root)) + ".lock"
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    with open(lock, "w", encoding="utf-8"):
        pass

    done = fx.sh()

    assert done.stdout.strip() == ("autoresume: refused - could not record the run (could not take the "
                                   "resume-state lock) - nothing typed")
    assert (fx.recorded(), "would have typed" in fx.log(), "capture-pane" in fx.tmux_calls()) == \
        (False, False, False)


@needs_bash
@needs_posix
def test_nonempty_input_line_refuses(fx):
    fx.pane.write_text(TYPED, encoding="utf-8")

    fx.sh()
    log = fx.wait_for_sender()

    assert f"the input line of {PANE} is not empty, so nothing was typed - run {PROMPT} yourself" in log, log
    assert ("would have typed" in log, "send-keys" in fx.tmux_calls()) == (False, False)


@needs_bash
@needs_posix
def test_probe_timeout_refuses(fx):
    fx.pane.write_text(BUSY, encoding="utf-8")
    fx.machine(resume={"readyTimeoutSeconds": 1})

    fx.sh()
    log = fx.wait_for_sender()

    assert f"the input line of {PANE} did not become ready within 1s (last probe: busy)" in log, log
    assert ("would have typed" in log, "send-keys" in fx.tmux_calls()) == (False, False)


@needs_bash
@needs_posix
def test_a_busy_pane_that_turns_ready_is_typed(fx):
    """The probe waits rather than refusing while the /compact frame is busy."""
    fx.pane.write_text(BUSY, encoding="utf-8")
    fx.machine(resume={"readyTimeoutSeconds": 10})

    fx.sh(wait=False)
    time.sleep(1)
    fx.pane.write_text(READY, encoding="utf-8")
    log = fx.wait_for_sender()

    assert f"would have typed '{PROMPT}' into {PANE}" in log, log


@needs_bash
def test_off_is_silent_no_log(fx):
    fx.machine(auto=None)

    done = fx.sh()

    assert (done.stdout, fx.log(), fx.tmux_calls(), os.path.exists(fx.marker)) == ("", "", "", False)


@needs_bash
@needs_posix
def test_decide_wait_is_logged_and_types_nothing(tmp_path):
    fx = Fixture(tmp_path, resume_line="/crew:done T-0002")

    done = fx.sh()

    assert done.stdout.strip() == ("autoresume: refused - auto-resume is waiting: .work/tickets/T-0002/ "
                                   "does not exist")
    assert ("refusing - auto-resume: auto-resume is waiting" in fx.log(), os.path.exists(fx.marker)) == (True, False)


@needs_bash
def test_tmux_unset_is_logged(fx):
    fx.machine(auto_clear={"method": "tmux"})

    done = fx.sh(tmux=False)

    assert "$TMUX is unset" in done.stdout and "$TMUX is unset" in fx.log(), (done.stdout, fx.log())


@needs_bash
def test_notify_types_nothing_and_claims_nothing(fx):
    done = fx.sh(tmux=False, OS="Windows_NT")

    assert done.stdout.strip() == f"autoresume: notify - run {PROMPT} yourself"
    assert (os.path.exists(fx.marker), fx.recorded()) == (False, False)


@needs_bash
def test_stop_path_never_types_a_resume(fx):
    """Without --resume the script is the /clear path: no autoClear opt-in
    here, so it is silent, whatever resume.auto says."""
    done = subprocess.run([_BASH, os.path.join(_SCRIPTS, "auto-clear.sh"), "--session", SESSION, "--root",
                           str(fx.root)], cwd=str(fx.root), env=fx.env(), capture_output=True, text=True,
                          check=False, timeout=60)

    assert (done.stdout, fx.log(), os.path.exists(fx.marker)) == ("", "", False)


@needs_pwsh
def test_ps1_sendkeys_must_fire_dry_run_and_inhibited_send(fx):
    dry = fx.ps1("-DryRun")
    done = fx.ps1()

    assert dry.stdout.splitlines()[:2] == ["autoclear: would send", "  method: sendkeys"], dry.stdout + dry.stderr
    assert f"  command: {PROMPT}" in dry.stdout and "  delay: 0s" in dry.stdout, dry.stdout
    assert "would have sent, but CREW_AUTOCLEAR_INHIBIT is set" in fx.log(), fx.log() + done.stderr
    assert (os.path.isfile(fx.marker), fx.recorded()) == (True, True)


@needs_pwsh
def test_ps1_auto_is_notify_and_claims_nothing(fx):
    done = fx.ps1(method="auto")

    assert done.stdout.strip() == f"autoresume: notify - run {PROMPT} yourself", done.stdout + done.stderr
    assert (os.path.exists(fx.marker), fx.recorded()) == (False, False)


@needs_pwsh
def test_ps1_second_run_same_handoff_types_nothing(fx):
    os.makedirs(os.path.dirname(fx.marker), exist_ok=True)
    with open(fx.marker, "w", encoding="utf-8"):
        pass

    done = fx.ps1()

    assert done.stdout.strip() == ("autoresume: refused - this handoff was already typed once "
                                   f"(marker resume-typed-{fx.key} exists)"), done.stdout + done.stderr
    assert (fx.recorded(), "would have sent" in fx.log()) == (False, False)


@needs_pwsh
def test_ps1_record_failure_types_nothing(fx):
    lock = crew_resume.state_path(str(fx.root)) + ".lock"
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    with open(lock, "w", encoding="utf-8"):
        pass

    done = fx.ps1()

    assert "could not record the run (could not take the resume-state lock)" in done.stdout, \
        done.stdout + done.stderr
    assert (fx.recorded(), "would have sent" in fx.log()) == (False, False)


@needs_pwsh
def test_ps1_off_is_silent(fx):
    fx.machine(auto=None, auto_clear={"method": "sendkeys"})

    done = fx.ps1(method=None)

    assert (done.stdout, fx.log()) == ("", ""), done.stderr


@needs_pwsh
def test_ps1_tmux_method_refuses_without_claiming(fx):
    done = fx.ps1(method="tmux")

    assert ("auto-clear.sh's job" in done.stdout, os.path.exists(fx.marker)) == (True, False), done.stdout


def _child_source():
    with open(os.path.join(_SCRIPTS, "auto-clear.ps1"), encoding="utf-8") as handle:
        source = handle.read()
    start = source.index("$child = @'\n") + len("$child = @'\n")
    return source[start:source.index("\n'@", start)]


def _run_child_slice(tmp_path, body, env_overrides):
    """A slice of the child heredoc that ends before any SendWait, under pwsh
    with the log replaced by stdout. Refuses a slice that could type."""
    code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    assert "SendWait" not in code and "Windows.Forms" not in code, code
    script = tmp_path / "slice.ps1"
    script.write_text(
        "function Write-CrewChildNote { param($m) Write-Output \"NOTE: $m\" }\n"
        "[long]$Hwnd = [long]$env:CREW_TEST_HWND\n$Delay = 0\n"
        f"$Text = '{PROMPT}'\n$WindowTitle = ''\n$IsWindowsTerminalBool = $true\n"
        + body + "\nWrite-Output 'PROCEEDED'\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "CREW_AUTOCLEAR_INHIBIT"}
    env.update(env_overrides)
    done = subprocess.run([_PWSH, "-NoProfile", "-NonInteractive", "-File", str(script)], env=env,
                          capture_output=True, text=True, check=False, timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stdout


@needs_pwsh
def test_sendkeys_focus_lost_refuses(tmp_path):
    """The child resume mode spawns is the /clear path's own: after the delay,
    another window in front declines, naming the resume command."""
    child = _child_source()
    body = child[child.index("$fg = "):child.index("$recheck = Get-CrewChildTabRecheck")]
    body = body.replace("[CrewAC.Win]::GetForegroundWindow().ToInt64()", "[long]$env:CREW_TEST_FG")

    out = _run_child_slice(tmp_path, body, {"CREW_TEST_FG": "7", "CREW_TEST_HWND": "42"})

    assert ("lost focus" in out, f"run {PROMPT} yourself" in out, "PROCEEDED" in out) == (True, True, False), out


@needs_pwsh
def test_sendkeys_tab_mismatch_refuses(tmp_path):
    """The tab recheck after the delay, for a Windows Terminal owner: with no
    provable single tab (here: no UI Automation at all) it declines."""
    child = _child_source()
    functions = child[child.index("function Get-CrewWindowsTerminalTabState"):child.index("Start-Sleep -Seconds")]
    body = functions + child[child.index("$recheck = Get-CrewChildTabRecheck"):
                             child.index("if ($env:CREW_AUTOCLEAR_INHIBIT)")]

    out = _run_child_slice(tmp_path, body, {"CREW_TEST_HWND": "42"})

    assert ("cannot verify the active tab" in out, f"run {PROMPT} yourself" in out, "PROCEEDED" in out) == \
        (True, True, False), out


# --- step 4: the entry point ---------------------------------------------------

def _start(fx, source="compact"):
    return {"hook_event_name": "SessionStart", "source": source, "session_id": SESSION, "cwd": str(fx.root),
            "transcript_path": str(fx.root / "fresh.jsonl")}


def _hook(fx, payload, flavour="sh", **extra):
    done = subprocess.run([sys.executable, os.path.join(_SCRIPTS, "crew_context.py"), "--flavour", flavour],
                          cwd=str(fx.root), env=fx.env(**extra), input=json.dumps(payload), capture_output=True,
                          text=True, check=False, timeout=120)
    text = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"] if done.stdout.strip() else ""
    return done, text


def _typing_log(fx):
    path = crew_context.log_path(str(fx.root))
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [r for r in map(json.loads, handle) if "resumeTyping" in r]


@needs_bash
def test_context_hook_starts_resume_mode_on_clear(fx):
    """A /clear reaches the sender. Here it waits -- the note is bound to a
    Claude Code process that is not this one's (T-0042), whether or not the
    suite itself runs under a `claude` -- and the refusal is logged by the
    sender and by the hook."""
    path = crew_resume.author_path(str(fx.root))
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    for entry in data["worktrees"].values():
        entry["process"] = {"pid": 1, "start": 0}
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data))

    _done, _text = _hook(fx, _start(fx, "clear"))

    records = _typing_log(fx)
    assert [(r["resumeTyping"], r["flavour"]) for r in records] == [("refused", "sh")], records
    assert "refusing - auto-resume: auto-resume is waiting" in fx.log(), fx.log()


@needs_bash
@needs_posix
def test_context_hook_names_the_typing_on_compact(fx):
    _done, text = _hook(fx, _start(fx))
    log = fx.wait_for_sender()

    assert f"Auto-resume: typing {PROMPT} into this session in 0s (method tmux); if it does not arrive, " \
        "type it yourself." in text, text
    assert "Auto-resume did not start" not in text and f"would have typed '{PROMPT}'" in log, (text, log)


@needs_bash
@pytest.mark.parametrize("source", ["startup", "resume"])
def test_context_hook_never_starts_resume_mode_on_startup(fx, source):
    _hook(fx, _start(fx, source))

    assert (_typing_log(fx), fx.log(), fx.tmux_calls(), os.path.exists(fx.marker)) == ([], "", "", False)


@needs_bash
def test_context_hook_starts_nothing_without_a_flavour_or_when_unarmed(fx):
    fx.machine(auto=None)
    _hook(fx, _start(fx))
    fx.machine()
    subprocess.run([sys.executable, os.path.join(_SCRIPTS, "crew_context.py")], cwd=str(fx.root), env=fx.env(),
                   input=json.dumps(_start(fx)), capture_output=True, text=True, check=False, timeout=120)

    assert (_typing_log(fx), fx.log()) == ([], "")


@needs_bash
@needs_posix
def test_resume_mode_runs_in_each_flavour_despite_claim(fx):
    """The same raw payload twice: the second invocation loses the per-event
    context claim and emits nothing, but its sender still ran (and refused,
    because the first one already typed this handoff)."""
    first, first_text = _hook(fx, _start(fx))
    second, second_text = _hook(fx, _start(fx))
    fx.wait_for_sender()

    assert (bool(first_text), second_text, first.returncode, second.returncode) == (True, "", 0, 0)
    assert [r["resumeTyping"] for r in _typing_log(fx)] == ["typing", "refused"], _typing_log(fx)


def test_resume_mode_failure_keeps_context_output(fx, monkeypatch):
    """A sender that cannot even start costs the session nothing but the
    typing: the handoff and T-0006's line arrive, plus why it was not typed."""
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(fx.global_path))
    monkeypatch.setattr(crew_context, "_resume_typing_cmd",
                        lambda *a: [str(fx.tmp / "no-such-interpreter")])
    payload = _start(fx)

    text = crew_context.run(payload, json.dumps(payload).encode("utf-8"), "claude", "sh")

    assert "## Handoff from the previous session" in text, text
    assert f"Auto-resume: ready to run {PROMPT}." in text, text
    assert "Auto-resume was not typed: the sender did not run (FileNotFoundError)." in text, text
    assert [r["resumeTyping"] for r in _typing_log(fx)] == ["failed"]


def _ps1_tmux_refusal():
    """auto-clear.ps1's own refusal text for method tmux, read from the script."""
    with open(os.path.join(_SCRIPTS, "auto-clear.ps1"), encoding="utf-8") as handle:
        got = re.search(r'"tmux"\s*\{\s*Stop-CrewAutoClear "([^"]+)"', handle.read())
    assert got, "auto-clear.ps1 no longer refuses method tmux by name"
    return got.group(1)


@pytest.mark.parametrize("reason,expected", [
    (crew_autocycle.resolve_method({"method": "sendkeys"}, {})["reason"],
     "Auto-resume was left to the PowerShell hook (auto-clear.ps1): this flavour does not type method sendkeys."),
    (_ps1_tmux_refusal(),
     "Auto-resume was left to the bash hook (auto-clear.sh): this flavour does not type method tmux."),
    (f"the input line of {PANE} is not empty, so nothing was typed - run {PROMPT} yourself",
     f"Auto-resume was not typed: the input line of {PANE} is not empty, so nothing was typed - run {PROMPT} "
     "yourself."),
    (f"the input line of {PANE} did not become ready within 1s (last probe: busy)",
     f"Auto-resume was not typed: the input line of {PANE} did not become ready within 1s (last probe: busy)."),
])
def test_not_typed_line_tells_the_other_flavours_job_from_a_real_refusal(reason, expected):
    """On Windows both flavours run: a refusal that only says "the other
    flavour types this method" must never read as "not typed", because the
    other flavour may be typing it. Every other refusal still says so. The
    two other-flavour texts are each sender's own, so a reworded one fails."""
    assert crew_context.not_typed_line({"status": "refused", "text": f"refused - {reason}"}) == expected


@needs_bash
def test_sh_hook_with_sendkeys_leaves_the_resume_to_the_ps1(fx):
    """Windows with method sendkeys: the sh hook can win the context claim
    before the ps1 sender records its run, so decide still reads `run`. Its
    context must not say the resume was not typed."""
    fx.machine(auto_clear={"method": "sendkeys"})

    _done, text = _hook(fx, _start(fx), tmux=False)

    assert f"Auto-resume: ready to run {PROMPT}." in text, text
    assert "was not typed" not in text, text
    assert "Auto-resume was left to the PowerShell hook (auto-clear.ps1): this flavour does not type method " \
        "sendkeys." in text, text
    assert ([r["resumeTyping"] for r in _typing_log(fx)], os.path.exists(fx.marker)) == (["refused"], False)


@needs_bash
def test_sh_hook_with_a_real_refusal_still_says_not_typed(fx):
    fx.machine(auto_clear={"method": "tmux"})

    _done, text = _hook(fx, _start(fx), tmux=False)

    assert "Auto-resume was not typed: " in text and "$TMUX is unset" in text, text
    assert "was left to the" not in text, text


def test_codex_harness_never_types(fx, monkeypatch):
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(fx.global_path))

    assert crew_context.start_resume_typing(str(fx.root), _start(fx), "sh", "codex") is None
