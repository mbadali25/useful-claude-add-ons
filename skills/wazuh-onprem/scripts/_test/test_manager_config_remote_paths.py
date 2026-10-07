"""Regression suite for wazuh-onprem audit entry #16.

`manager_config.py` shells out to the local `ssh`/`scp` binaries and never
touches a real host directly - `run_remote`/`scp_up`/`scp_down` all go
through `subprocess.run`, so every test here stubs that call instead of
opening a socket. No network, no credentials, no real manager.

The bug: `_scratch_path()` (the function these tests replaced) built its
scratch path from `tempfile.gettempdir()` and used the SAME path both
locally (fine) and as the REMOTE upload/xmllint/install target (not fine).
`tempfile.gettempdir()` reports the LOCAL machine's temp dir - on Windows
that's something like `C:/Users/<you>/AppData/Local/Temp/...` - and the
Wazuh manager this script edits (`sudo cp`, `systemctl`, `/var/ossec/...`
throughout) is always Linux. scp'ing and xmllint'ing a Windows-shaped path
on a Linux remote fails, and it fails AFTER `cmd_apply`'s step 1/6 has
already taken a `sudo cp` backup of the live config on the manager - so an
operator who ran this from Windows got a bare scp/ssh error with no
statement that nothing was installed and no pointer to the backup that was
already sitting on the manager.

Fixed by splitting `_scratch_path` into `_local_scratch_path` (unchanged,
local-only) and `_remote_scratch_path` (built with `posixpath`, hardcoded
under `/tmp` - never touches `tempfile.gettempdir()`), and by wrapping the
backup-to-install window in `cmd_apply` in a try/except that states plainly
that nothing was installed and where the backup is.

Extended after an independent review of that first pass came back FIX:

  - the pre-install try/except now also catches OSError (a local write
    failure after the backup, e.g. a vanished directory) and KeyboardInterrupt
    (prints the same statement, then re-raises rather than swallowing it),
    and --block is read and validated BEFORE the backup is taken at all, so a
    mistyped path can never leave a dangling, unexplained backup;
  - that try/except is scoped to steps 2/6-4/6 ONLY, deliberately not
    widened to cover the live install at step 5/6 onward - a failure AFTER
    the live `sudo cp` must not claim "nothing was installed" (it may not be
    true), and takes the existing wazuh-analysisd/rollback path instead;
  - the remote candidate scratch file (a full ossec.conf, including any
    integration API keys) is chmod 600'd right after upload and rm -f'd on
    every exit path, success or failure; the local scratch files are
    unlinked the same way.

Extended AGAIN after a second independent review came back FIX - the
shipped control-flow logic was correct, the gaps were in guards and secrets
handling:

  - every LOCAL scratch file (tmp_current, tmp_candidate, and cmd_diff's own
    copy) is now created 0600 via `_create_local_scratch_file()` BEFORE
    anything writes to it - `open(path, "w")` alone is masked by the process
    umask (typically 0644), so a full ossec.conf with integration API keys
    sat world-readable in the shared local /tmp for the life of the run;
  - the remote cleanup `rm -f` now: prints a named WARNING (with the remote
    path) on failure instead of swallowing it silently; is bounded by both
    `ssh -o ConnectTimeout=10` and a subprocess-level timeout, so a hung ssh
    can't delay the abort message; and has its OWN KeyboardInterrupt/
    RuntimeError/OSError handling, so a SECOND Ctrl-C or a missing local
    `ssh` binary during cleanup doesn't replace/mask whatever message
    already printed;
  - `cmd_diff`'s tmp_current now gets the same 0600-and-unlink treatment
    `cmd_apply` already had - it too is a full copy of the live config.

Extended a THIRD time after a round-3 review came back FIX (no BLOCK; 15
sabotages held from before) - the remaining gap was step 5 itself:

  - the install `sudo cp {remote_candidate} {conf_path}` is exactly where a
    "nothing was installed" claim would be FALSE if it failed - a failed cp
    can truncate its DESTINATION (it opens conf_path for writing before it
    is done reading the source), so the live config may already be
    different, not merely untouched. It now gets its own handling: on
    failure, print what happened and attempt a rollback from the backup;
    report the backup path either way, and say plainly if the live config
    is left in an UNKNOWN state (install failed AND the rollback attempt
    also failed) rather than claim anything was or wasn't touched;
  - local scratch files (tmp_current, tmp_candidate) are now created BEFORE
    the remote backup, not during steps 2/3 - so a purely local O_EXCL
    collision (astronomically unlikely given the per-run uuid, but not
    impossible under PID reuse) fails with nothing remote yet touched and
    no backup yet to explain, instead of after the backup already ran.
    Cleanup now tracks `created_locals` - only the paths THIS run actually
    created - so it can never delete a file that collided with (and
    therefore belongs to) something else;
  - the 10s cleanup timeout now raises a dedicated `SSHTimeout` (a
    RuntimeError subclass) and cleanup reports "removal not confirmed
    (timed out)" for it, distinct from "could not remove" - a timeout means
    the remote outcome is genuinely UNKNOWN, not a confirmed failure.

Several of these are locked in by sabotage below, not just by a passing
suite - narrowing the post-backup except tuple back to (RuntimeError,)
alone, widening the try block to cover the post-install steps (as far as
the restart, as far as the config-test-and-rollback, AND as far as the
install cp itself), narrowing `main()`'s new `except OSError`, and
narrowing cleanup's own except tuple - see the tests named for each below.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _SKILL_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import manager_config as mc  # noqa: E402  pylint: disable=wrong-import-position

# A Windows local temp dir, forward/back-slash mixed the way
# tempfile.gettempdir() actually returns it on Windows.
WINDOWS_TEMPDIR = "C:\\Users\\opuser\\AppData\\Local\\Temp"


def _windows_shaped(path: str) -> bool:
    return "C:" in path or "\\" in path


def _local_mode(path: str) -> int:
    return os.stat(path).st_mode & 0o777


@pytest.fixture
def apply_args(tmp_path):
    block = tmp_path / "block.xml"
    block.write_text("<integration><name>office365</name></integration>\n", encoding="utf-8")
    return type("Args", (), {"block": str(block), "anchor": None, "restart": False})()


@pytest.fixture
def wazuh_env(monkeypatch):
    monkeypatch.setenv("WAZUH_SSH_HOST", "manager.example.internal")
    monkeypatch.setenv("WAZUH_SSH_USER", "opuser")
    monkeypatch.delenv("WAZUH_SSH_KEY_PATH", raising=False)
    monkeypatch.delenv("WAZUH_CONF_PATH", raising=False)


class _RecordingSSH:
    """Stubs subprocess.run for the ssh/scp shapes manager_config.py builds.
    Records every invocation. A remote-side path (the ssh remote command
    string, or the `user@host:` half of an scp argument) that is
    Windows-shaped fails, exactly as a real Linux manager would reject it -
    everything else succeeds. A successful scp download also materialises
    the local destination file (which `_create_local_scratch_file()` will
    already have created 0600, empty), since real scp would.
    """

    FAKE_OSSEC_CONF = "<ossec_config>\n  <global/>\n</ossec_config>\n"

    def __init__(self):
        self.calls = []

    def _remote_side_is_windows_shaped(self, full_cmd):
        if full_cmd[0] == "ssh":
            return _windows_shaped(full_cmd[-1])
        if full_cmd[0] == "scp":
            for arg in full_cmd:
                if "@" in arg and ":" in arg:
                    if _windows_shaped(arg.split(":", 1)[1]):
                        return True
        return False

    def __call__(self, full_cmd, capture_output=True, text=True, check=False, timeout=None):
        self.calls.append(list(full_cmd))
        if self._remote_side_is_windows_shaped(full_cmd):
            return subprocess.CompletedProcess(
                full_cmd, 1, "", "No such file or directory (simulated Linux manager)")
        if full_cmd[0] == "scp":
            src, dst = full_cmd[-2], full_cmd[-1]
            if "@" in src and ":" in src:
                # download direction: materialise the local file. The
                # destination already exists (0600, empty) via
                # _create_local_scratch_file() - "w" truncates content,
                # not mode, same as real scp overwriting an existing file.
                local_dir = os.path.dirname(dst)
                if local_dir:
                    os.makedirs(local_dir, exist_ok=True)
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write(self.FAKE_OSSEC_CONF)
        return subprocess.CompletedProcess(full_cmd, 0, "", "")


@pytest.fixture
def windows_local_machine(monkeypatch, tmp_path):
    """Simulates running this script from a Windows workstation: a
    Windows-shaped tempfile.gettempdir(), backed by a real directory this
    process can actually write to (this suite may run on any OS).

    The returned string ("C:\\...") is not POSIX-absolute - `posixpath`
    treats it as a RELATIVE path, same as CLAUDE.md's doc-builder landmine
    ("a broken mapping can yield a RELATIVE path ... under the CWD").
    Anchoring the CWD to tmp_path keeps any such write inside the fixture's
    own throwaway directory instead of leaking a literal `C:/` directory
    into the repo checkout - that happened here once already, while this
    suite was being written, and was cleaned up with `rm -rf`.

    `cmd_apply` now pre-creates every local scratch file itself (0600)
    BEFORE scp/open ever touches it, so the directory `_local_scratch_path`
    resolves to has to genuinely exist under the chdir'd CWD - on a real
    Windows machine "C:\\...\\Temp" already does; here it does not, so this
    fixture creates it too.
    """
    monkeypatch.chdir(tmp_path)
    fake_tempdir = tmp_path / "winhome" / "AppData" / "Local" / "Temp"
    fake_tempdir.mkdir(parents=True)
    win_tempdir = "C:\\" + str(fake_tempdir).lstrip("/")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: win_tempdir)
    os.makedirs(win_tempdir.replace("\\", "/"), exist_ok=True)
    return fake_tempdir


# ---------------------------------------------------------------------------
# unit-level: the scratch-path helpers themselves
# ---------------------------------------------------------------------------
def test_local_scratch_path_may_be_windows_shaped(windows_local_machine):
    # This is fine - it is genuinely this operator's own machine.
    path = mc._local_scratch_path("candidate")
    assert "AppData" in path or "Temp" in path


def test_remote_scratch_path_is_always_posix_even_on_a_windows_local_machine(windows_local_machine):
    path = mc._remote_scratch_path("candidate")

    assert path.startswith("/tmp/"), path
    assert "C:" not in path
    assert "\\" not in path


def test_remote_scratch_path_ignores_gettempdir_entirely(monkeypatch):
    """However tempfile.gettempdir() is patched, the remote path must not
    move - it should never even be called."""
    def _boom():
        raise AssertionError("_remote_scratch_path must not consult tempfile.gettempdir()")
    monkeypatch.setattr(tempfile, "gettempdir", _boom)

    path = mc._remote_scratch_path("current")
    assert path.startswith("/tmp/")


def test_old_shared_scratch_path_function_is_gone():
    """Guards against a future edit reintroducing one function shared
    between local and remote callers - that sharing is the entire bug."""
    assert not hasattr(mc, "_scratch_path")


def test_create_local_scratch_file_is_0600_and_excl(tmp_path):
    target = str(tmp_path / "probe_ossec.conf")

    mc._create_local_scratch_file(target)

    assert _local_mode(target) == 0o600
    with pytest.raises(FileExistsError):
        mc._create_local_scratch_file(target)  # O_EXCL - never silently reuses a path


# ---------------------------------------------------------------------------
# integration-level: cmd_apply end to end, no real host
# ---------------------------------------------------------------------------
def test_apply_never_sends_a_windows_shaped_path_to_the_remote_side(
        wazuh_env, windows_local_machine, apply_args, monkeypatch):
    ssh = _RecordingSSH()
    monkeypatch.setattr(subprocess, "run", ssh)

    mc.cmd_apply(apply_args)  # must not raise / sys.exit

    remote_side_args = []
    for call in ssh.calls:
        if call[0] == "ssh":
            remote_side_args.append(call[-1])
        elif call[0] == "scp":
            for arg in call:
                if "@" in arg and ":" in arg:
                    remote_side_args.append(arg.split(":", 1)[1])

    assert remote_side_args, "no remote-side commands were recorded"
    offenders = [a for a in remote_side_args if _windows_shaped(a)]
    assert offenders == [], f"Windows-shaped path(s) sent to the remote side: {offenders}"


def test_apply_backs_up_before_touching_anything_else(
        wazuh_env, windows_local_machine, apply_args, monkeypatch):
    ssh = _RecordingSSH()
    monkeypatch.setattr(subprocess, "run", ssh)

    mc.cmd_apply(apply_args)

    backup_calls = [c for c in ssh.calls if "cp" in " ".join(c) and ".bak." in " ".join(c)]
    assert backup_calls, "no backup cp was issued"
    assert ssh.calls.index(backup_calls[0]) == 0, "backup must be the first remote command"


def test_apply_states_plainly_when_a_post_backup_step_fails(
        wazuh_env, apply_args, monkeypatch):
    """A failure between the backup (step 1/6) and install (step 5/6) -
    here, an unrelated transient scp failure fetching the current config at
    step 2/6 - must say plainly that nothing was installed and where the
    backup is. Before the fix this reached main()'s generic
    `except RuntimeError as e: sys.exit(f"ERROR: {e}")`, which named neither.
    """
    calls = {"n": 0}

    def flaky_run(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        calls["n"] += 1
        if full_cmd[0] == "scp":
            return subprocess.CompletedProcess(
                full_cmd, 255, "", "ssh: connection reset by peer")
        return subprocess.CompletedProcess(full_cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", flaky_run)

    with pytest.raises(SystemExit) as exc:
        mc.cmd_apply(apply_args)

    message = str(exc.value)
    assert "backup" in message.lower()
    assert "not" in message.lower()  # "was NOT touched" / "nothing was installed"
    assert ".bak." in message


def test_apply_reports_backup_path_on_xml_validation_failure(
        wazuh_env, windows_local_machine, apply_args, monkeypatch):
    """The other pre-install failure branch (malformed XML) must also
    name the backup, not just say 'nothing was touched'."""
    def failing_xmllint_run(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh" and "xmllint" in full_cmd[-1]:
            return subprocess.CompletedProcess(full_cmd, 1, "", "parser error")
        if full_cmd[0] == "scp":
            src, dst = full_cmd[-2], full_cmd[-1]
            if "@" in src and ":" in src:
                # download direction - materialise the local destination,
                # same as _RecordingSSH does, so the caller's local
                # open()/read() has somewhere real to land in this sandbox
                local_dir = os.path.dirname(dst)
                if local_dir:
                    os.makedirs(local_dir, exist_ok=True)
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write("<ossec_config></ossec_config>\n")
        return subprocess.CompletedProcess(full_cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", failing_xmllint_run)

    with pytest.raises(SystemExit) as exc:
        mc.cmd_apply(apply_args)

    message = str(exc.value)
    assert ".bak." in message
    assert "nothing was installed" in message.lower() or "not touched" in message.lower()


# ---------------------------------------------------------------------------
# FIX 1 - validate local input before the backup; catch OSError and
# KeyboardInterrupt in the post-backup span, with the same statement
# ---------------------------------------------------------------------------
def test_apply_validates_the_block_file_before_taking_any_backup(
        wazuh_env, monkeypatch, tmp_path):
    """A mistyped --block path must fail before step 1/6's backup, not
    after it - so there is never a backup to explain in the first place."""
    calls = []

    def spy_run(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        calls.append(list(full_cmd))
        return subprocess.CompletedProcess(full_cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", spy_run)

    args = type("Args", (), {
        "block": str(tmp_path / "does-not-exist.xml"),
        "anchor": None, "restart": False,
    })()

    with pytest.raises(FileNotFoundError):
        mc.cmd_apply(args)

    assert calls == [], f"a remote command ran before --block was even read: {calls}"


def test_apply_catches_a_local_os_error_after_the_backup(
        wazuh_env, apply_args, monkeypatch):
    """An OSError raised locally AFTER the backup - here, the local `scp`
    binary itself vanishing mid-run, which subprocess.run raises directly
    (FileNotFoundError, not something scp_down converts to RuntimeError) -
    must get the same 'nothing was installed' treatment as a
    RuntimeError/ValueError, not a raw traceback with no mention of the
    backup. (Local scratch-file creation itself now happens BEFORE the
    backup - see test_apply_creates_local_scratch_files_before_the_backup_
    and_cleanup_tracks_only_what_it_created below for that collision case.)
    """
    ssh = _RecordingSSH()

    def flaky_scp(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "scp":
            raise FileNotFoundError("[Errno 2] No such file or directory: 'scp'")
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", flaky_scp)

    with pytest.raises(SystemExit) as exc:
        mc.cmd_apply(apply_args)

    message = str(exc.value)
    assert "backup" in message.lower()
    assert ".bak." in message


def test_apply_creates_local_scratch_files_before_the_backup_and_cleanup_tracks_only_what_it_created(
        wazuh_env, apply_args, monkeypatch, tmp_path):
    """An O_EXCL collision on the SECOND local scratch file (simulating a
    pre-existing file this run did NOT create - e.g. a PID-reuse race) must
    fail BEFORE any remote command runs (no backup taken, nothing to
    explain), and cleanup must remove only the FIRST file (which this run
    DID create) - the pre-existing collision target must be left
    completely untouched, not deleted or overwritten."""
    calls = []

    def spy_run(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        calls.append(list(full_cmd))
        return subprocess.CompletedProcess(full_cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", spy_run)

    real_create = mc._create_local_scratch_file
    created_by_run = []
    colliding_path = {}

    def sometimes_colliding(path):
        if "_candidate_" in path:
            # Simulate: this path already existed, NOT created by this run.
            colliding_path["path"] = path
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("PRE-EXISTING CONTENT - NOT OURS\n")
            raise FileExistsError(f"[Errno 17] File exists: '{path}'")
        real_create(path)
        created_by_run.append(path)

    monkeypatch.setattr(mc, "_create_local_scratch_file", sometimes_colliding)

    with pytest.raises(FileExistsError):
        mc.cmd_apply(apply_args)

    assert calls == [], f"a remote command ran despite a purely local collision: {calls}"
    assert created_by_run, "setup error: the current-config scratch file should have been created first"
    for p in created_by_run:
        assert not os.path.exists(p), f"cleanup failed to remove a file THIS RUN created: {p}"

    assert colliding_path.get("path"), "setup error: candidate collision never triggered"
    with open(colliding_path["path"], encoding="utf-8") as fh:
        assert fh.read() == "PRE-EXISTING CONTENT - NOT OURS\n", (
            "cleanup deleted or altered a file this run did NOT create")


def test_apply_prints_the_same_statement_on_keyboard_interrupt_and_reraises(
        wazuh_env, apply_args, monkeypatch, capsys):
    """A Ctrl-C mid-fetch/build/upload must not vanish silently or leave the
    operator guessing - same statement as any other pre-install abort,
    and the interrupt itself must still propagate (not be swallowed)."""
    def interrupting_run(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "scp":
            raise KeyboardInterrupt()
        return subprocess.CompletedProcess(full_cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", interrupting_run)

    with pytest.raises(KeyboardInterrupt):
        mc.cmd_apply(apply_args)

    printed = capsys.readouterr().err
    assert "backup" in printed.lower()
    assert ".bak." in printed


def test_main_turns_an_os_error_from_any_subcommand_into_a_clean_exit(monkeypatch):
    """main()'s new `except OSError` (for a bad local path on ANY
    subcommand, not just cmd_apply's own post-backup span) must actually be
    reachable - not just present as dead code. Swapping it for a different
    exception type must fail this test. `cmd_fetch` is monkeypatched
    directly, since main()'s dispatch dict looks the function up by its
    module-global name at call time."""
    def raising_cmd(args):
        raise FileNotFoundError("nope")

    monkeypatch.setattr(mc, "cmd_fetch", raising_cmd)
    monkeypatch.setattr(sys, "argv", ["manager_config.py", "fetch", "--out", "/x"])

    with pytest.raises(SystemExit) as exc:
        mc.main()

    assert "nope" in str(exc.value)


# ---------------------------------------------------------------------------
# FIX 2(a) - the caught-exception tuple must include ValueError, not just
# RuntimeError. Narrowing it to (RuntimeError,) passes every test above but
# must fail this one.
# ---------------------------------------------------------------------------
def test_apply_states_plainly_when_a_post_backup_step_raises_value_error(
        wazuh_env, apply_args, monkeypatch):
    """insert_block() raises ValueError when --anchor names a tag that is
    not in the fetched config. That must get the same 'nothing was
    installed' treatment as a RuntimeError."""
    args = type("Args", (), {
        "block": apply_args.block, "anchor": "nonexistent_tag", "restart": False,
    })()

    ssh = _RecordingSSH()
    monkeypatch.setattr(subprocess, "run", ssh)

    with pytest.raises(SystemExit) as exc:
        mc.cmd_apply(args)

    message = str(exc.value)
    assert "anchor" in message.lower()
    assert "backup" in message.lower()
    assert ".bak." in message


# ---------------------------------------------------------------------------
# FIX 2(b) - the try/except that produces "nothing was installed" must NOT
# be widened to cover the post-install steps, in EITHER direction: as far as
# the final restart, or only as far as the install-and-test-and-rollback.
# A sabotage that widens it either way must make the false message appear.
# ---------------------------------------------------------------------------
def test_apply_does_not_claim_nothing_installed_for_a_failure_after_the_live_install(
        wazuh_env, apply_args, monkeypatch):
    """A failure AFTER `sudo cp {remote_candidate} {conf_path}` (here:
    restarting the service loses the SSH connection) must propagate as a
    plain RuntimeError, never as the pre-install 'nothing was installed' /
    'was NOT touched' message - the live config has already changed by
    then."""
    args = type("Args", (), {
        "block": apply_args.block, "anchor": None, "restart": True,
    })()

    ssh = _RecordingSSH()

    def flaky_after_install(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh" and "systemctl restart wazuh-manager" in full_cmd[-1]:
            return subprocess.CompletedProcess(
                full_cmd, 1, "", "ssh: connection reset by peer")
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", flaky_after_install)

    with pytest.raises(RuntimeError) as exc:
        mc.cmd_apply(args)

    message = str(exc.value)
    assert "nothing was installed" not in message.lower()
    assert "was not touched" not in message.lower()
    # and the live install itself DID happen - the whole point of this test
    install_calls = [c for c in ssh.calls if c[0] == "ssh"
                      and c[-1].startswith("sudo cp ") and ".bak." not in c[-1]]
    assert install_calls, "the live install cp never ran - test setup is wrong"


def test_apply_does_not_claim_not_touched_when_config_test_and_rollback_both_fail(
        wazuh_env, apply_args, monkeypatch):
    """analysisd -t fails (config test failed) AND the follow-up rollback
    cp ALSO fails - the config is now in an UNKNOWN state, neither
    confirmed-new nor confirmed-reverted. This must never be reported as
    'nothing was installed' / 'was NOT touched': both are false, and the
    second is actively dangerous advice. A sabotage that widens the
    pre-install try/except to cover step 5 (the install cp) onward - even
    if it stops short of the final restart - makes this print exactly that
    false message; this is the narrower widening `test
    _apply_does_not_claim_nothing_installed_for_a_failure_after_the_live_install`
    above does not catch on its own."""
    ssh = _RecordingSSH()

    def failing_test_and_rollback(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh":
            remote_cmd = full_cmd[-1]
            if "wazuh-analysisd -t" in remote_cmd:
                return subprocess.CompletedProcess(full_cmd, 1, "", "config test failed")
            parts = remote_cmd.split()
            if parts[:2] == ["sudo", "cp"] and ".bak." in parts[2]:
                # the ROLLBACK cp specifically: `sudo cp {backup_path}
                # {conf_path}` - backup_path (SOURCE) carries .bak., unlike
                # the initial backup cp where it is the DEST that does.
                return subprocess.CompletedProcess(full_cmd, 255, "", "ssh: broken pipe")
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", failing_test_and_rollback)

    with pytest.raises(RuntimeError) as exc:
        mc.cmd_apply(apply_args)

    message = str(exc.value)
    assert "not touched" not in message.lower()
    assert "nothing was installed" not in message.lower()


# ---------------------------------------------------------------------------
# FIX (round 3) - the install cp itself (step 5/6) is exactly where
# "nothing was installed" would be FALSE if it failed: cp opens its
# DESTINATION for writing before it has finished reading the source, so a
# failure there can truncate conf_path, not merely leave it unchanged. A
# sabotage that wraps just that one line back into the pre-install handler
# passed all 28 of the previous round's tests - none of them fail the
# install cp specifically.
# ---------------------------------------------------------------------------
def test_apply_install_cp_failure_never_claims_nothing_was_installed(
        wazuh_env, apply_args, monkeypatch):
    """The install cp (`sudo cp {remote_candidate} {conf_path}`) failing
    must never say 'nothing was installed' / 'was NOT touched', must
    attempt a rollback from the backup, and must name the backup path."""
    ssh = _RecordingSSH()

    def flaky_install(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh":
            parts = full_cmd[-1].split()
            if (parts[:2] == ["sudo", "cp"]
                    and parts[2].startswith("/tmp/_wazuh_candidate_")):
                # the INSTALL cp specifically
                return subprocess.CompletedProcess(full_cmd, 1, "", "No space left on device")
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", flaky_install)

    with pytest.raises(SystemExit) as exc:
        mc.cmd_apply(apply_args)

    message = str(exc.value)
    assert "not touched" not in message.lower()
    assert "nothing was installed" not in message.lower()
    assert ".bak." in message
    assert "rolled back" in message.lower()

    rollback_calls = [c for c in ssh.calls if c[0] == "ssh"
                       and c[-1].split()[:2] == ["sudo", "cp"]
                       and ".bak." in c[-1].split()[2]]
    assert rollback_calls, "no rollback cp was attempted after the install cp failed"


def test_apply_install_and_rollback_both_failing_reports_unknown_state(
        wazuh_env, apply_args, monkeypatch):
    """If the install cp fails AND the rollback attempt ALSO fails, the
    live config is genuinely in an unknown state - neither 'not touched'
    nor a confirmed rollback. Must say so plainly and still name the
    backup path so the operator can restore it by hand."""
    ssh = _RecordingSSH()

    def double_failure(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh":
            parts = full_cmd[-1].split()
            if parts[:2] == ["sudo", "cp"]:
                if parts[2].startswith("/tmp/_wazuh_candidate_"):
                    return subprocess.CompletedProcess(full_cmd, 1, "", "disk full")
                if ".bak." in parts[2]:
                    return subprocess.CompletedProcess(full_cmd, 1, "", "ssh: broken pipe")
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", double_failure)

    with pytest.raises(SystemExit) as exc:
        mc.cmd_apply(apply_args)

    message = str(exc.value)
    assert "not touched" not in message.lower()
    assert "nothing was installed" not in message.lower()
    assert "unknown state" in message.lower()
    assert ".bak." in message


# ---------------------------------------------------------------------------
# NIT 1 (round 2) - the remote candidate (a full ossec.conf, secrets and
# all) must be locked down and cleaned up; local scratch files too.
# ---------------------------------------------------------------------------
def test_apply_locks_down_and_cleans_up_the_remote_candidate_on_success(
        wazuh_env, windows_local_machine, apply_args, monkeypatch):
    ssh = _RecordingSSH()
    monkeypatch.setattr(subprocess, "run", ssh)

    mc.cmd_apply(apply_args)

    remote_cmds = [c[-1] for c in ssh.calls if c[0] == "ssh"]
    chmod_cmds = [c for c in remote_cmds if c.startswith("chmod 600 ")]
    assert chmod_cmds, f"no chmod 600 issued: {remote_cmds}"
    rm_cmds = [c for c in remote_cmds if c.startswith("rm -f ")]
    assert rm_cmds, f"no remote cleanup rm -f issued: {remote_cmds}"

    chmod_path = chmod_cmds[0].split(" ", 2)[2]
    rm_path = rm_cmds[0].split(" ", 2)[2]
    assert chmod_path == rm_path, "chmod and cleanup must target the same file"
    assert chmod_path.startswith("/tmp/_wazuh_candidate_")

    xmllint_idx = next(i for i, c in enumerate(remote_cmds) if c.startswith("xmllint "))
    chmod_idx = remote_cmds.index(chmod_cmds[0])
    assert chmod_idx < xmllint_idx, "chmod 600 must run BEFORE xmllint validates the upload"


def test_apply_cleans_up_local_scratch_files_on_success(
        wazuh_env, windows_local_machine, apply_args, monkeypatch):
    written_locals = []
    ssh = _RecordingSSH()

    def spying_call(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        result = ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)
        if full_cmd[0] == "scp":
            src, dst = full_cmd[-2], full_cmd[-1]
            if "@" in src and ":" in src:
                written_locals.append(dst)   # download destination (local)
            elif "@" in dst and ":" in dst:
                written_locals.append(src)   # upload source (local)
        return result

    monkeypatch.setattr(subprocess, "run", spying_call)

    mc.cmd_apply(apply_args)

    assert written_locals, "no local scratch files were observed"
    for p in written_locals:
        assert not os.path.exists(p), f"local scratch file not cleaned up: {p}"


def test_apply_cleans_up_remote_candidate_even_on_a_pre_install_abort(
        wazuh_env, apply_args, monkeypatch):
    """xmllint rejects the candidate (step 4/6) - the file that was already
    uploaded must still be rm -f'd, not abandoned on the manager."""
    ssh_calls = []

    def failing_xmllint_run(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        ssh_calls.append(list(full_cmd))
        if full_cmd[0] == "ssh" and "xmllint" in full_cmd[-1]:
            return subprocess.CompletedProcess(full_cmd, 1, "", "parser error")
        if full_cmd[0] == "scp":
            src, dst = full_cmd[-2], full_cmd[-1]
            if "@" in src and ":" in src:
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write("<ossec_config></ossec_config>\n")
        return subprocess.CompletedProcess(full_cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", failing_xmllint_run)

    with pytest.raises(SystemExit):
        mc.cmd_apply(apply_args)

    rm_cmds = [c[-1] for c in ssh_calls if c[0] == "ssh" and c[-1].startswith("rm -f ")]
    assert rm_cmds, "remote candidate scratch file was left behind on a pre-install abort"


# ---------------------------------------------------------------------------
# FIX (round 2) - local scratch files must be 0600 BEFORE they are sent
# anywhere, and the remote chmod 600 must precede xmllint (pinned above by
# test_apply_locks_down_and_cleans_up_the_remote_candidate_on_success).
# ---------------------------------------------------------------------------
def test_apply_creates_the_local_candidate_0600_before_scp_up(
        wazuh_env, windows_local_machine, apply_args, monkeypatch):
    observed_modes = []
    ssh = _RecordingSSH()

    def spying_call(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "scp":
            src = full_cmd[-2]
            if "@" not in src:  # local source = the upload direction
                observed_modes.append(_local_mode(src))
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", spying_call)

    mc.cmd_apply(apply_args)

    assert observed_modes, "no local upload source was observed"
    assert all(m == 0o600 for m in observed_modes), observed_modes


def test_apply_creates_the_local_current_copy_0600_too(
        wazuh_env, windows_local_machine, apply_args, monkeypatch):
    observed_modes = []
    ssh = _RecordingSSH()

    def spying_call(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        result = ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)
        if full_cmd[0] == "scp":
            dst = full_cmd[-1]
            if "@" not in dst and os.path.exists(dst):  # local dest = download direction
                observed_modes.append(_local_mode(dst))
        return result

    monkeypatch.setattr(subprocess, "run", spying_call)

    mc.cmd_apply(apply_args)

    assert observed_modes, "no local download destination was observed"
    assert all(m == 0o600 for m in observed_modes), observed_modes


# ---------------------------------------------------------------------------
# FIX (round 2) - a failed remote cleanup must warn by name, be bounded by a
# timeout, and handle its own KeyboardInterrupt/RuntimeError/OSError without
# masking whatever message already printed.
# ---------------------------------------------------------------------------
def test_cleanup_prints_a_named_warning_when_remote_rm_returns_nonzero(
        wazuh_env, apply_args, monkeypatch, capsys):
    ssh = _RecordingSSH()

    def flaky_rm(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh" and full_cmd[-1].startswith("rm -f "):
            return subprocess.CompletedProcess(full_cmd, 1, "", "Permission denied")
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", flaky_rm)

    mc.cmd_apply(apply_args)  # a failed cleanup is a warning, not an abort - must not raise

    printed = capsys.readouterr().err
    assert "WARNING" in printed
    assert "/tmp/_wazuh_candidate_" in printed


def test_cleanup_prints_a_named_warning_when_remote_rm_itself_raises_os_error(
        wazuh_env, apply_args, monkeypatch, capsys):
    """The local `ssh` binary vanishing mid-cleanup raises a raw OSError
    (e.g. FileNotFoundError) straight out of subprocess.run - not the
    RuntimeError run_remote raises for a nonzero exit or a timeout.
    Cleanup's own except must catch OSError too, or this crashes uncaught -
    narrowing that except tuple must fail this test."""
    ssh = _RecordingSSH()

    def flaky_rm(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh" and full_cmd[-1].startswith("rm -f "):
            raise FileNotFoundError("[Errno 2] No such file or directory: 'ssh'")
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", flaky_rm)

    mc.cmd_apply(apply_args)  # must NOT raise

    printed = capsys.readouterr().err
    assert "WARNING" in printed
    assert "/tmp/_wazuh_candidate_" in printed


def test_cleanup_bounds_the_remote_rm_with_a_timeout_and_reports_it_as_unconfirmed(
        wazuh_env, apply_args, monkeypatch, capsys):
    """A hung ssh during cleanup must not hang the whole abort. Asserts the
    subprocess-level timeout is actually passed (not just ConnectTimeout on
    the command line, which does not bound an ssh that connects fine but
    then never answers), and that a resulting timeout is reported as
    'removal not confirmed (timed out)' - NOT as 'could not remove', which
    would claim a certainty a timeout does not have: the remote `rm -f` may
    have completed right after the deadline."""
    ssh = _RecordingSSH()

    def hanging_rm(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh" and full_cmd[-1].startswith("rm -f "):
            assert timeout is not None, "cleanup's rm -f must pass a subprocess timeout"
            raise subprocess.TimeoutExpired(cmd=full_cmd, timeout=timeout)
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", hanging_rm)

    mc.cmd_apply(apply_args)  # must NOT raise / hang

    printed = capsys.readouterr().err
    assert "WARNING" in printed
    assert "not confirmed" in printed.lower()
    assert "timed out" in printed.lower()
    assert "could not remove" not in printed.lower()


def test_cleanup_passes_connect_timeout_on_the_rm_ssh_command(
        wazuh_env, apply_args, monkeypatch):
    ssh = _RecordingSSH()
    monkeypatch.setattr(subprocess, "run", ssh)

    mc.cmd_apply(apply_args)

    rm_calls = [c for c in ssh.calls if c[0] == "ssh" and c[-1].startswith("rm -f ")]
    assert rm_calls, "no cleanup rm -f was issued"
    assert "ConnectTimeout=" in " ".join(rm_calls[0]), rm_calls[0]


def test_cleanup_handles_a_second_interrupt_without_masking_the_first(
        wazuh_env, apply_args, monkeypatch, capsys):
    """A second Ctrl-C landing during cleanup's own remote `rm -f` must be
    handled THERE, not left to replace the original interrupt that started
    the abort. Python chains a `finally`-raised exception onto the one it
    replaces via `__context__`, so an unhandled second interrupt is visible
    here as `exc.value.__context__` being the first KeyboardInterrupt
    instead of None - narrowing/removing cleanup's own KeyboardInterrupt
    handling must fail this test."""
    ssh = _RecordingSSH()

    def double_interrupt(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        if full_cmd[0] == "ssh" and "xmllint" in full_cmd[-1]:
            raise KeyboardInterrupt("first: during validation")
        if full_cmd[0] == "ssh" and full_cmd[-1].startswith("rm -f "):
            raise KeyboardInterrupt("second: during cleanup")
        return ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", double_interrupt)

    with pytest.raises(KeyboardInterrupt) as exc:
        mc.cmd_apply(apply_args)

    assert exc.value.__context__ is None, (
        "the SECOND interrupt (from cleanup's own rm -f) replaced the "
        "original one - cleanup must catch KeyboardInterrupt itself")

    printed = capsys.readouterr().err
    assert "INTERRUPTED" in printed
    assert "backup" in printed.lower()


# ---------------------------------------------------------------------------
# NIT (round 2) - cmd_diff must not leave its own copy of the live config
# (secrets and all) behind either.
# ---------------------------------------------------------------------------
def test_diff_cleans_up_its_local_copy_of_the_current_config(
        wazuh_env, windows_local_machine, apply_args, monkeypatch, capsys):
    written_locals = []
    ssh = _RecordingSSH()

    def spying_call(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        result = ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)
        if full_cmd[0] == "scp":
            dst = full_cmd[-1]
            if "@" not in dst:
                written_locals.append(dst)
        return result

    monkeypatch.setattr(subprocess, "run", spying_call)

    args = type("Args", (), {"block": apply_args.block, "anchor": None})()
    mc.cmd_diff(args)

    assert written_locals, "no local copy of the current config was observed"
    for p in written_locals:
        assert not os.path.exists(p), f"cmd_diff left its local copy behind: {p}"


def test_diff_creates_its_local_copy_0600(
        wazuh_env, windows_local_machine, apply_args, monkeypatch):
    observed_modes = []
    ssh = _RecordingSSH()

    def spying_call(full_cmd, capture_output=True, text=True, check=False, timeout=None):
        result = ssh(full_cmd, capture_output=capture_output, text=text, check=check, timeout=timeout)
        if full_cmd[0] == "scp":
            dst = full_cmd[-1]
            if "@" not in dst and os.path.exists(dst):
                observed_modes.append(_local_mode(dst))
        return result

    monkeypatch.setattr(subprocess, "run", spying_call)

    args = type("Args", (), {"block": apply_args.block, "anchor": None})()
    mc.cmd_diff(args)

    assert observed_modes, "no local copy of the current config was observed"
    assert all(m == 0o600 for m in observed_modes), observed_modes
