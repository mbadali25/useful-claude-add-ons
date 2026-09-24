"""Pins the ORDER invariant both auto-clear senders must follow, in both
flavours:

    1. is this a crew repo at all? (`.crew/` the directory exists -- crew
       1.0 F4 reverses this back to the directory from the `.crew/config.json`
       file-only gate F3 shipped, see CONFIG.md sec 14)
    2. is auto-clear ARMED? (the machine's `enabled`, then its
       `onlyRepos`/`onlySessions` narrowing)
    3. only THEN may anything be written -- even a single log line.

A not-opted-in run must stay completely silent on a path that reaches BEYOND
the gate: `.crew/config.json` genuinely exists (so step 1 passes), but step 2
says no. If the enabled/narrowing check ever ran AFTER something that can
write (a refusal log, a "no session id" note), a disabled or narrowed-out repo
would stop being silent the moment some other refusal fired first -- which is
exactly the regression a real Windows run hit once (see the module docstring
in `test_auto_cycle.py` and CONFIG.md sec 14's own account of it).

Every case below omits `--session` (`session=None`): a session-less run is the
sharpest way to prove the order, because "no session id" is itself a
refusal reason `note()`/`Write-CrewAutoClearNote` WOULD log -- so any of
these tests going red proves the enabled/narrowing check stopped running
before that refusal, not that no refusal exists at all.
"""
import json
import os
import shutil
import subprocess
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = (_ROOT + "/hooks/scripts/auto-clear.sh").replace("\\", "/")
_PS1 = _ROOT + "/hooks/scripts/auto-clear.ps1"
_BASH = crew_fixtures.resolve_bash()
_PWSH_ANY = shutil.which("pwsh")

SESSION = "sess-order-1"
HANDOFF = (
    "# Handoff\nwritten: now\nticket: T-1\nbranch: x\nhead: y\n\n"
    "## Done\n- a thing\n\n## Next action\nDo the next thing.\n"
)


def _write_machine(root, block):
    """The whole `context.autoClear` block, written to the machine-global
    file `_run`/`_run_ps1` point HOME/USERPROFILE at -- never the real one."""
    crew = root.parent / "home" / ".claude" / "crew"
    crew.mkdir(parents=True, exist_ok=True)
    (crew / "config.json").write_text(
        json.dumps({"context": {"autoClear": block}}), encoding="utf-8")


def _repo(tmp_path, repo_auto=None):
    """`.crew/config.json` genuinely present (step 1 passes), optionally
    carrying its own `context.autoClear` sub-block (a repo-local opt-out)."""
    cfg = {"context": {"warnAt": 0.8, "handoffPath": ".work/HANDOFF.md"}}
    if repo_auto is not None:
        cfg["context"]["autoClear"] = repo_auto
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    (root / ".crew" / (".handoff-requested-" + SESSION)).write_text(json.dumps({
        "session_id": SESSION, "requested_at": time.time() - 30,
        "trusted": True, "why": "measured"}), encoding="utf-8")
    handoff_path = root / ".work" / "HANDOFF.md"
    handoff_path.write_text(HANDOFF, encoding="utf-8")
    stamp = time.time() + 5
    os.utime(handoff_path, (stamp, stamp))
    return root


def _run_sh(root):
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    return subprocess.run([_BASH, _SH, "--dry-run"], cwd=str(root), env=env,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)


def _run_ps1(root):
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT",
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    return subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-NonInteractive", "-File", _PS1,
         "-Root", str(root), "-DryRun"],
        cwd=str(root), env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, check=False)


def _assert_silent(result, root):
    assert result.returncode == 0
    assert result.stdout.strip() == "", result.stdout
    assert result.stderr.strip() == "", result.stderr
    assert not (root / ".crew" / ".autoclear.log").exists()


# --- config.json present, autoClear block absent entirely -----------------


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_config_present_autoclear_absent_writes_no_log_sh(tmp_path):
    root = _repo(tmp_path)  # no autoClear block at all in the repo config
    _write_machine(root, {})  # machine never opted in either
    assert (root / ".crew" / "config.json").exists()
    _assert_silent(_run_sh(root), root)


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_config_present_autoclear_absent_writes_no_log_ps1(tmp_path):
    root = _repo(tmp_path)
    _write_machine(root, {})
    assert (root / ".crew" / "config.json").exists()
    _assert_silent(_run_ps1(root), root)


# --- config.json present, repo-local enabled: false, machine says true ----


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_config_present_enabled_false_writes_no_log_sh(tmp_path):
    root = _repo(tmp_path, repo_auto={"enabled": False})
    _write_machine(root, {"enabled": True, "method": "tmux"})
    _assert_silent(_run_sh(root), root)


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_config_present_enabled_false_writes_no_log_ps1(tmp_path):
    root = _repo(tmp_path, repo_auto={"enabled": False})
    _write_machine(root, {"enabled": True, "method": "tmux"})
    _assert_silent(_run_ps1(root), root)


# --- config.json present, machine on, onlyRepos excludes this repo --------


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_config_present_only_repos_excludes_writes_no_log_sh(tmp_path):
    root = _repo(tmp_path)
    _write_machine(root, {"enabled": True,
                           "onlyRepos": [str(tmp_path / "some-other-repo")]})
    _assert_silent(_run_sh(root), root)


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_config_present_only_repos_excludes_writes_no_log_ps1(tmp_path):
    root = _repo(tmp_path)
    _write_machine(root, {"enabled": True,
                           "onlyRepos": [str(tmp_path / "some-other-repo")]})
    _assert_silent(_run_ps1(root), root)


# --- config.json present, machine on, onlySessions excludes this session --
#
# The onlyRepos case above already exists elsewhere in the suite (scenario
# (c) in test_auto_clear.py); this is its onlySessions twin, which was not
# covered anywhere with an explicit no-log assertion before this file.


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_config_present_only_sessions_excludes_writes_no_log_sh(tmp_path):
    root = _repo(tmp_path)
    _write_machine(root, {"enabled": True, "onlySessions": ["some-other-session"]})
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root),
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    result = subprocess.run([_BASH, _SH, "--session", SESSION, "--dry-run"],
                           cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, check=False)
    _assert_silent(result, root)


@pytest.mark.skipif(_PWSH_ANY is None, reason="needs pwsh")
def test_config_present_only_sessions_excludes_writes_no_log_ps1(tmp_path):
    root = _repo(tmp_path)
    _write_machine(root, {"enabled": True, "onlySessions": ["some-other-session"]})
    home = str(root.parent / "home")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT",
               CREW_AUTOCLEAR_INHIBIT="1", HOME=home, USERPROFILE=home)
    result = subprocess.run(
        [_PWSH_ANY, "-NoProfile", "-NonInteractive", "-File", _PS1,
         "-Root", str(root), "-Session", SESSION, "-DryRun"],
        cwd=str(root), env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, check=False)
    _assert_silent(result, root)


# --- structural: the gate and the "off" exit are textually BEFORE anything
#     that can write, in both flavours ----------------------------------


def _lineno(lines, needle):
    for i, line in enumerate(lines):
        if needle in line:
            return i
    return None


def test_sh_gate_and_off_exit_precede_the_logger():
    with open(_ROOT + "/hooks/scripts/auto-clear.sh", encoding="utf-8") as handle:
        lines = handle.readlines()
    gate = _lineno(lines, "[ -d .crew ] || exit 0")
    log_var = _lineno(lines, 'LOG=".crew/.autoclear.log"')
    note_def = _lineno(lines, "note() {")
    off_exit = _lineno(lines, '[ "$STATUS" = "off" ] && exit 0')
    # The general refusal log -- reached for every non-"off", non-"send"
    # status (a disabled/narrowed-out repo would land here if the "off"
    # exit above it did not run first). Deliberately NOT "the first note()
    # call of any kind": `note "refusing - could not read the plan..."`
    # (line ~109) is an earlier, unrelated failure mode -- crew_autocycle.py
    # itself could not be read at all -- and logging THAT is correct
    # regardless of enabled/narrowing, so it must not count as a violation.
    refusal_note = _lineno(lines, 'note "refusing - $REASON"')
    assert None not in (gate, log_var, note_def, off_exit, refusal_note), (
        "one of the anchors this test relies on has moved or been renamed")
    assert gate < log_var < note_def, "the crew-repo gate must precede the logger being armed"
    assert off_exit < refusal_note, (
        "the silent `off` exit must precede the general refusal that logs")


def test_ps1_gate_and_enabled_check_precede_the_logger():
    with open(_ROOT + "/hooks/scripts/auto-clear.ps1", encoding="utf-8") as handle:
        lines = handle.readlines()
    gate = _lineno(lines, 'Test-Path ".crew" -PathType Container')
    log_var = _lineno(lines, '$log = ".crew/.autoclear.log"')
    note_def = _lineno(lines, "function Write-CrewAutoClearNote")
    enabled_exit = _lineno(lines, "if (-not $enabled) { exit 0 }")
    first_stop_call = None
    for i, line in enumerate(lines):
        if i <= note_def:
            continue
        if "Stop-CrewAutoClear" in line and "function Stop-CrewAutoClear" not in line:
            first_stop_call = i
            break
    assert None not in (gate, log_var, note_def, enabled_exit, first_stop_call), (
        "one of the anchors this test relies on has moved or been renamed")
    assert gate < log_var < note_def, "the crew-repo gate must precede the logger being armed"
    assert enabled_exit < first_stop_call, (
        "the silent enabled exit must precede the first refusal that logs")
