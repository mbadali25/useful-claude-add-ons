# pylint: disable=subprocess-run-check  # upstream AI-Connect style, kept to minimise the fork's diff
"""Tests for install.sh's configure_firewall() function.

Runs only the extracted function body under bash. Each test asserts the exact
commands configure_firewall ran and that a second run detects its own rule
instead of adding it again ("already present").

Hermetic by construction (L-0790: this file once ran the host's real
`sudo ufw allow`):

- the child's PATH is two directories the test itself creates under tmp_path,
  the fakes and one-line wrappers for the tools in REAL_TOOLS. The caller's
  PATH is never passed on, so `command -v ufw` can only find a fake;
- the fake sudo answers `true` itself and otherwise runs only a file inside
  the fake-tool dir. Anything else is refused with FAKE_SUDO_REFUSED;
- the function's `$EUID` is replaced by a value the harness sets (a normal
  user unless the test says otherwise), so no test depends on who runs it;
- every child first checks, inside itself, that sudo, ufw and firewall-cmd
  resolve to a fake or to nothing, and exits HARNESS_NOT_HERMETIC before the
  code under test if not. So a leak fails closed instead of being noticed by a
  later test;
- the "must not reach" tests at the end fail if one of these is undone.

Skipped when bash is not on PATH (e.g. a CI image without Git Bash / WSL);
when the real euid is 0 unless ALLOW_ROOT_ENV is set to 1 (a root caller is the
one for whom a hermeticity bug edits the host firewall, and whether it is
sandboxed cannot be detected from here, so it has to say so); and when bash is
Windows' WSL launcher, which starts a shell in another system that takes
neither this PATH nor these fakes.

NOT run on Windows by the change that made it hermetic (L-0790).
"""

import ntpath
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"

BASH = shutil.which("bash")

# The only host tools the child may run, each through a wrapper that execs
# the absolute path found here: configure_firewall pipes into grep, and the
# fakes below use grep and cat.
REAL_TOOLS = ("grep", "cat")
FIREWALL_TOOLS = ("ufw", "firewall-cmd", "sudo")
ALLOW_ROOT_ENV = "AI_CONNECT_TEST_ALLOW_ROOT"
FAKE_SUDO_REFUSED = 97
HARNESS_NOT_HERMETIC = 98
NON_ROOT_EUID = 1000
# The child's environment is built, not inherited: PATH, a home under
# tmp_path, and only these from the caller, which Windows needs to start a
# process at all. Nothing else reaches the child, so no startup file
# (BASH_ENV), exported function or credential of the caller's does.
PASSED_ENV = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")


def root_skip_reason(euid, environ):
    """Why this module must not run for this caller, or None."""
    if euid != 0 or environ.get(ALLOW_ROOT_ENV) == "1":
        return None
    return (
        f"real euid is 0 and {ALLOW_ROOT_ENV}=1 is not set: refusing to run "
        "firewall tests as root outside a declared sandbox (L-0790)"
    )


def launcher_skip_reason(bash, os_name, environ):
    """Why this bash cannot run the harness, or None.

    On Windows, System32's bash.exe and the WindowsApps alias are the WSL
    launcher: the shell they start is in another system, with its own PATH
    (and often root as its user), so `env=` does not confine it.
    """
    if bash is None or os_name != "nt":
        return None
    where = ntpath.normcase(ntpath.dirname(ntpath.abspath(bash)))
    system_root = ntpath.normcase(environ.get("SYSTEMROOT") or r"C:\Windows")
    launchers = [ntpath.join(system_root, name) for name in ("system32", "sysnative", "syswow64")]
    if where in launchers or ntpath.basename(where) == "windowsapps":
        return f"bash is the WSL launcher ({bash}); it does not take the test's PATH (L-0790)"
    return None


_ROOT_SKIP = root_skip_reason(os.geteuid() if hasattr(os, "geteuid") else None, os.environ)
_LAUNCHER_SKIP = launcher_skip_reason(BASH, os.name, os.environ)

pytestmark = [
    pytest.mark.skipif(BASH is None, reason="bash not found on PATH"),
    pytest.mark.skipif(_ROOT_SKIP is not None, reason=_ROOT_SKIP or ""),
    pytest.mark.skipif(_LAUNCHER_SKIP is not None, reason=_LAUNCHER_SKIP or ""),
]


def _write_script(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _make_sudo(bin_dir: Path) -> None:
    # Lets `sudo -n true` and `sudo <fake> ...` succeed. It never resolves a
    # command on PATH: `true` is answered here, and anything else must be a
    # regular file inside bin_dir (a fake), or it is refused.
    _write_script(
        bin_dir / "sudo",
        f"""
BIN={shlex.quote(bin_dir.as_posix())}
[[ "$1" == "-n" ]] && shift
[[ $# -eq 1 && "$1" == "true" ]] && exit 0
case "$1" in
    ""|*/*)
        echo "fake sudo: refusing '$1': not a bare fake-tool name" >&2
        exit {FAKE_SUDO_REFUSED}
        ;;
esac
if [[ -L "$BIN/$1" || ! -f "$BIN/$1" || ! -x "$BIN/$1" ]]; then
    echo "fake sudo: refusing '$1': not a fake in $BIN" >&2
    exit {FAKE_SUDO_REFUSED}
fi
CMD="$BIN/$1"
shift
exec "$CMD" "$@"
""",
    )


def _make_ufw(bin_dir: Path, state: Path) -> None:
    # `status` mimics real ufw's "<port>/tcp  ALLOW  <subnet>" column order
    # (port before subnet), which is what configure_firewall's grep expects.
    _write_script(
        bin_dir / "ufw",
        f"""
STATE={shlex.quote(state.as_posix())}
case "$1" in
    status)
        echo "Status: active"
        echo ""
        echo "To                         Action      From"
        echo "--                         ------      ----"
        [[ -f "$STATE" ]] && cat "$STATE"
        ;;
    allow)
        shift
        SUBNET="" PORT=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                from) SUBNET="$2"; shift 2 ;;
                port) PORT="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        echo "$PORT/tcp                   ALLOW       $SUBNET" >> "$STATE"
        ;;
    *)
        echo "unexpected ufw invocation: $*" >&2
        exit 1
        ;;
esac
""",
    )


def _make_firewall_cmd(bin_dir: Path, state: Path) -> None:
    _write_script(
        bin_dir / "firewall-cmd",
        f"""
STATE={shlex.quote(state.as_posix())}
for arg in "$@"; do
    case "$arg" in
        --query-rich-rule=*)
            RULE="${{arg#--query-rich-rule=}}"
            [[ -f "$STATE" ]] && grep -qF -- "$RULE" "$STATE" && exit 0
            exit 1
            ;;
        --add-rich-rule=*)
            RULE="${{arg#--add-rich-rule=}}"
            echo "$RULE" >> "$STATE"
            ;;
        --reload|--permanent)
            : # no-op
            ;;
    esac
done
exit 0
""",
    )


def _make_tool_dir(tool_dir: Path) -> Path:
    """One wrapper per REAL_TOOLS entry, each exec'ing an absolute path.

    The absolute path is resolved here, in the test process, so the child
    needs no host directory on its PATH.
    """
    tool_dir.mkdir(exist_ok=True)
    for name in REAL_TOOLS:
        real = shutil.which(name)
        if real is None:
            pytest.skip(f"{name} not found on PATH")
        _write_script(tool_dir / name, f'exec {shlex.quote(Path(real).as_posix())} "$@"')
    return tool_dir


def child_env(bin_dir: Path) -> dict:
    """The child's whole environment. PATH is the fake-tool dir and the
    wrapper dir, both made by the test, and nothing from the caller's PATH."""
    tool_dir = _make_tool_dir(bin_dir.parent / "_tools")
    home = bin_dir.parent / "_home"
    home.mkdir(exist_ok=True)
    env = {key: os.environ[key] for key in PASSED_ENV if key in os.environ}
    env["HOME"] = env["USERPROFILE"] = str(home)
    env["PATH"] = os.pathsep.join([str(bin_dir), str(tool_dir)])
    return env


def hermetic_preamble(bin_dir: Path) -> str:
    """Bash that runs first in every child and stops it, before any code
    under test, unless each firewall tool resolves to the fake in bin_dir or
    to nothing. `-ef` compares the files, not the spellings of their paths; a
    function or alias of that name is not a file and is refused too."""
    return f"""
BIN={shlex.quote(bin_dir.as_posix())}
for tool in {" ".join(FIREWALL_TOOLS)}; do
    found=$(command -v "$tool") || continue
    if [[ ! "$found" -ef "$BIN/$tool" ]]; then
        echo "HARNESS_NOT_HERMETIC: $tool resolves to $found, not a fake in $BIN" >&2
        exit {HARNESS_NOT_HERMETIC}
    fi
done
unset BIN tool found
"""


def run_bash(env: dict, script: str):
    return subprocess.run(
        [BASH, "-c", script],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def run_in_child(bin_dir: Path, script: str):
    """Runs script in the hermetic child. A child that could resolve a real
    firewall tool never reaches script, and the test fails here."""
    result = run_bash(child_env(bin_dir), hermetic_preamble(bin_dir) + script)
    if result.returncode == HARNESS_NOT_HERMETIC and "HARNESS_NOT_HERMETIC" in result.stderr:
        pytest.fail(f"the child was stopped before the code under test: {result.stderr.strip()}")
    return result


def extract_configure_firewall() -> str:
    """configure_firewall() as install.sh has it, with its one `$EUID` read
    replaced by `$TEST_EUID`: bash's own EUID is read-only, and the real one
    is exactly what a test must not depend on."""
    lines = INSTALL_SH.read_text(encoding="utf-8").splitlines()
    start = lines.index("configure_firewall() {")
    end = lines.index("}", start)
    body = "\n".join(lines[start : end + 1]) + "\n"
    changed = "configure_firewall reads the caller's identity differently now; update this harness"
    assert body.count("$EUID") == 1, changed
    body = body.replace("$EUID", "$TEST_EUID")
    # No second spelling of "who am I" may sit beside the one replaced above.
    assert body.count("UID") == 1, changed
    assert not [word for word in ("id -u", "whoami", "$USER", "${USER") if word in body], changed
    return body


def run_configure_firewall(bin_dir: Path, vpn_subnet: str = "100.64.0.0/10", euid: int = NON_ROOT_EUID):
    """Calls the extracted configure_firewall() once, as the given euid, in a
    child that can resolve only the fakes in bin_dir and REAL_TOOLS."""
    script = f"""
set -e
{extract_configure_firewall()}
RED='' GREEN='' YELLOW='' BLUE='' NC=''
VPN_SUBNET={shlex.quote(vpn_subnet)}
TEST_EUID={int(euid)}
configure_firewall
"""
    return run_in_child(bin_dir, script)


def test_extraction_finds_the_function():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "configure_firewall() {" in text


def test_skips_without_root_or_sudo(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # No sudo, no ufw, no firewall-cmd in the child's PATH, and the function
    # is told it is a normal user: it must refuse to touch anything.
    result = run_configure_firewall(bin_dir, euid=NON_ROOT_EUID)
    assert result.returncode == 0, result.stderr
    assert "not root" in result.stdout
    assert "skipping" in result.stdout.lower()


def test_ufw_adds_rule_and_is_idempotent(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "ufw_state"
    _make_sudo(bin_dir)
    _make_ufw(bin_dir, state)

    first = run_configure_firewall(bin_dir)
    assert first.returncode == 0, first.stderr
    assert "added" in first.stdout
    assert state.exists()
    logged = state.read_text(encoding="utf-8")
    assert "100.64.0.0/10" in logged
    assert "9999" in logged
    assert "tcp" in logged

    second = run_configure_firewall(bin_dir)
    assert second.returncode == 0, second.stderr
    assert "already present" in second.stdout
    # Still exactly one allow line: the second run did not add it again.
    assert len(state.read_text(encoding="utf-8").splitlines()) == 1


def test_firewalld_adds_rule_and_is_idempotent(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "firewalld_state"
    _make_sudo(bin_dir)
    _make_firewall_cmd(bin_dir, state)

    first = run_configure_firewall(bin_dir)
    assert first.returncode == 0, first.stderr
    assert "added" in first.stdout
    logged = state.read_text(encoding="utf-8")
    assert "100.64.0.0/10" in logged
    assert '"9999"' in logged
    assert '"tcp"' in logged

    second = run_configure_firewall(bin_dir)
    assert second.returncode == 0, second.stderr
    assert "already present" in second.stdout
    assert len(state.read_text(encoding="utf-8").splitlines()) == 1


def test_ufw_preferred_over_firewalld(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ufw_state = tmp_path / "ufw_state"
    fwd_state = tmp_path / "firewalld_state"
    _make_sudo(bin_dir)
    _make_ufw(bin_dir, ufw_state)
    _make_firewall_cmd(bin_dir, fwd_state)

    result = run_configure_firewall(bin_dir)
    assert result.returncode == 0, result.stderr
    assert ufw_state.exists()
    assert not fwd_state.exists()


def test_no_firewall_tool_prints_advice(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_sudo(bin_dir)

    result = run_configure_firewall(bin_dir)
    assert result.returncode == 0, result.stderr
    assert "neither ufw nor firewalld" in result.stdout
    assert "sudo ufw allow from 100.64.0.0/10 to any port 9999 proto tcp" in result.stdout


def test_custom_vpn_subnet_is_used(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "ufw_state"
    _make_sudo(bin_dir)
    _make_ufw(bin_dir, state)

    result = run_configure_firewall(bin_dir, vpn_subnet="10.0.0.0/24")
    assert result.returncode == 0, result.stderr
    logged = state.read_text(encoding="utf-8")
    assert "10.0.0.0/24" in logged
    assert "100.64.0.0/10" not in logged


# --- must not reach a real tool (L-0790) ---------------------------------
# Each of these fails if the harness above stops being hermetic. The canary
# tests plant their own "real" tools, so they do not depend on what the host
# has installed.


def _make_canaries(canary_dir: Path, marker: Path, names=FIREWALL_TOOLS) -> None:
    canary_dir.mkdir(exist_ok=True)
    for name in names:
        _write_script(
            canary_dir / name,
            f'echo "{name} $*" >> {shlex.quote(marker.as_posix())}\nexit 0',
        )


def _canaries_on_callers_path(tmp_path: Path, monkeypatch) -> Path:
    """Stand-ins for a host's real ufw, firewall-cmd and sudo, first on the
    CALLER's PATH. Returns the file each one appends to when it runs."""
    marker = tmp_path / "canary_ran"
    _make_canaries(tmp_path / "host_bin", marker)
    monkeypatch.setenv("PATH", str(tmp_path / "host_bin") + os.pathsep + os.environ.get("PATH", ""))
    return marker


def _ran(marker: Path) -> str:
    return marker.read_text(encoding="utf-8") if marker.exists() else ""


@pytest.mark.parametrize(
    "euid, environ, refused",
    [
        (0, {}, True),
        (0, {ALLOW_ROOT_ENV: "0"}, True),
        (0, {ALLOW_ROOT_ENV: "1"}, False),
        (NON_ROOT_EUID, {}, False),
        (None, {}, False),
    ],
)
def test_root_is_refused_unless_it_declares_a_sandbox(euid, environ, refused):
    reason = root_skip_reason(euid, environ)

    assert (reason is not None) is refused
    if refused:
        assert ALLOW_ROOT_ENV in reason


@pytest.mark.parametrize(
    "bash, os_name, environ, refused",
    [
        (r"C:\Windows\System32\bash.exe", "nt", {"SYSTEMROOT": r"C:\Windows"}, True),
        (r"c:\windows\system32\BASH.EXE", "nt", {"SYSTEMROOT": r"C:\WINDOWS"}, True),
        (r"C:\Windows\System32\bash.exe", "nt", {}, True),
        (r"D:\WinNT\Sysnative\bash.exe", "nt", {"SYSTEMROOT": r"D:\WinNT"}, True),
        (r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\bash.exe", "nt", {}, True),
        (r"C:\Program Files\Git\usr\bin\bash.exe", "nt", {"SYSTEMROOT": r"C:\Windows"}, False),
        (r"C:\Program Files\Git\bin\bash.exe", "nt", {}, False),
        ("/usr/bin/bash", "posix", {}, False),
        (None, "nt", {}, False),
    ],
)
def test_wsl_launcher_bash_is_refused(bash, os_name, environ, refused):
    reason = launcher_skip_reason(bash, os_name, environ)

    assert (reason is not None) is refused


def test_child_path_holds_only_test_made_dirs(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_sudo(bin_dir)
    _make_ufw(bin_dir, tmp_path / "ufw_state")
    _make_firewall_cmd(bin_dir, tmp_path / "firewalld_state")

    env = child_env(bin_dir)

    entries = [Path(entry).resolve() for entry in env["PATH"].split(os.pathsep)]
    root = os.path.realpath(tmp_path)
    assert entries
    assert all(os.path.commonpath([root, os.path.realpath(entry)]) == root for entry in entries), entries
    names = sorted(child.name for entry in entries for child in entry.iterdir())
    assert names == sorted(FIREWALL_TOOLS + REAL_TOOLS)
    assert set(env) <= {"PATH", "HOME", "USERPROFILE", *PASSED_ENV}, sorted(env)
    assert os.path.commonpath([root, os.path.realpath(env["HOME"])]) == root
    assert env["USERPROFILE"] == env["HOME"]


def test_child_sees_the_built_environment_not_the_callers(tmp_path, monkeypatch):
    # What the child process itself reports, not what child_env() returned.
    sourced = tmp_path / "bash_env_was_sourced"
    startup = tmp_path / "startup.sh"
    startup.write_text(f"echo yes > {shlex.quote(sourced.as_posix())}\n", encoding="utf-8", newline="\n")
    monkeypatch.setenv("BASH_ENV", str(startup))
    monkeypatch.setenv("ENV", str(startup))
    monkeypatch.setenv("AI_CONNECT_TEST_CALLER_SECRET", "not for the child")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    result = run_in_child(
        bin_dir,
        'echo "secret=${AI_CONNECT_TEST_CALLER_SECRET-unset}"\n'
        'echo "bash_env=${BASH_ENV-unset}"\n'
        'echo "home=$HOME"\n'
        'echo "path=$PATH"\n',
    )

    assert result.returncode == 0, result.stderr
    seen = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert seen["secret"] == "unset"
    assert seen["bash_env"] == "unset"
    assert not sourced.exists()
    expected = child_env(bin_dir)
    assert os.path.realpath(seen["home"]) == os.path.realpath(expected["HOME"])
    if os.name == "posix":
        # Git Bash respells a Windows PATH, so the exact text is checked
        # where the child takes it as given.
        assert seen["path"] == expected["PATH"]


def test_child_cannot_resolve_a_real_firewall_tool_or_sudo(tmp_path, monkeypatch):
    marker = _canaries_on_callers_path(tmp_path, monkeypatch)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    result = run_in_child(
        bin_dir,
        "for tool in " + " ".join(FIREWALL_TOOLS) + '; do command -v "$tool"; done; exit 0',
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "", f"the child resolved a real tool: {result.stdout!r}"
    assert _ran(marker) == ""


@pytest.mark.parametrize("tool", FIREWALL_TOOLS)
def test_child_stops_before_the_code_under_test_when_a_real_tool_resolves(tmp_path, tool):
    # The check inside the child, exercised directly: a PATH that does reach a
    # "real" tool (a canary) must stop the child before its script runs. This
    # is what contains a leak that the tests above would only report.
    marker = tmp_path / "canary_ran"
    host_bin = tmp_path / "host_bin"
    _make_canaries(host_bin, marker, names=(tool,))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    reached = tmp_path / "script_ran"
    env = child_env(bin_dir)
    env["PATH"] = os.pathsep.join([env["PATH"], str(host_bin)])

    result = run_bash(
        env,
        hermetic_preamble(bin_dir) + f"echo yes > {shlex.quote(reached.as_posix())}\n{tool} status\n",
    )

    assert result.returncode == HARNESS_NOT_HERMETIC, (result.returncode, result.stderr)
    assert f"HARNESS_NOT_HERMETIC: {tool} resolves to" in result.stderr
    assert not reached.exists()
    assert _ran(marker) == ""


def test_run_in_child_fails_closed_when_its_path_leaks(tmp_path, monkeypatch):
    # The call site, not only the check: if child_env ever hands out a PATH
    # that reaches a "real" tool, run_in_child fails the test and the script
    # (here, configure_firewall as root) never starts.
    marker = tmp_path / "canary_ran"
    host_bin = tmp_path / "host_bin"
    _make_canaries(host_bin, marker)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sound_env = child_env

    def leaking_env(fake_dir):
        env = sound_env(fake_dir)
        env["PATH"] = os.pathsep.join([env["PATH"], str(host_bin)])
        return env

    monkeypatch.setattr(sys.modules[__name__], "child_env", leaking_env)

    with pytest.raises(pytest.fail.Exception, match="HARNESS_NOT_HERMETIC"):
        run_configure_firewall(bin_dir, euid=0)

    assert _ran(marker) == ""


def test_child_runs_when_every_firewall_tool_is_a_fake(tmp_path):
    # The allow side of the check above: fakes in bin_dir are not refused.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_sudo(bin_dir)
    _make_ufw(bin_dir, tmp_path / "ufw_state")
    _make_firewall_cmd(bin_dir, tmp_path / "firewalld_state")

    result = run_in_child(bin_dir, "echo reached")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "reached\n"


@pytest.mark.parametrize(
    "euid, expected",
    [
        (0, "neither ufw nor firewalld"),
        (NON_ROOT_EUID, "not root and no passwordless sudo"),
    ],
)
def test_canary_tools_on_callers_path_are_never_run(tmp_path, monkeypatch, euid, expected):
    # With no fake in bin_dir, nothing may reach the caller's tools. The
    # canary sudo answers `-n true` with success, so euid 1000 here is the
    # caller with passwordless sudo.
    marker = _canaries_on_callers_path(tmp_path, monkeypatch)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    result = run_configure_firewall(bin_dir, euid=euid)

    assert _ran(marker) == "", f"a tool outside the fake dir ran: {_ran(marker)!r}"
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout


def _fake_sudo_with_a_real_ufw_in_reach(tmp_path: Path):
    """A fake sudo, and a PATH on which a "real" ufw and true (canaries)
    resolve. Returns (bin_dir, host_bin, marker, env)."""
    marker = tmp_path / "canary_ran"
    host_bin = tmp_path / "host_bin"
    _make_canaries(host_bin, marker, names=("ufw", "true"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_sudo(bin_dir)
    env = child_env(bin_dir)
    env["PATH"] = os.pathsep.join([str(bin_dir), str(host_bin), env["PATH"]])
    return bin_dir, host_bin, marker, env


@pytest.mark.parametrize("command", ["ufw", "{host_bin}/ufw", "-n ufw", "true extra", "-u root ufw"])
def test_fake_sudo_refuses_a_command_that_is_not_a_fake(tmp_path, command):
    # The fake sudo must refuse, not exec, what PATH resolves: a pass-through
    # sudo is how the real ufw was reached.
    _, host_bin, marker, env = _fake_sudo_with_a_real_ufw_in_reach(tmp_path)
    argv = command.format(host_bin=host_bin.as_posix())

    result = run_bash(env, f"sudo {argv} allow from 100.64.0.0/10")

    assert _ran(marker) == "", f"the fake sudo ran a tool outside the fake dir: {_ran(marker)!r}"
    assert result.returncode == FAKE_SUDO_REFUSED, (result.returncode, result.stderr)
    assert "fake sudo: refusing" in result.stderr


def test_fake_sudo_refuses_a_symlink_in_the_fake_dir(tmp_path):
    bin_dir, host_bin, marker, env = _fake_sudo_with_a_real_ufw_in_reach(tmp_path)
    try:
        (bin_dir / "ufw").symlink_to(host_bin / "ufw")
    except OSError as error:
        pytest.skip(f"cannot create a symlink here: {error}")

    result = run_bash(env, "sudo ufw allow from 100.64.0.0/10")

    assert _ran(marker) == "", f"the fake sudo followed a symlink out of the fake dir: {_ran(marker)!r}"
    assert result.returncode == FAKE_SUDO_REFUSED, (result.returncode, result.stderr)


@pytest.mark.skipif(os.name != "posix", reason="the executable bit is a POSIX permission")
def test_fake_sudo_refuses_a_file_that_is_not_executable(tmp_path):
    bin_dir, _, marker, env = _fake_sudo_with_a_real_ufw_in_reach(tmp_path)
    (bin_dir / "ufw").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8", newline="\n")

    result = run_bash(env, "sudo ufw allow from 100.64.0.0/10")

    assert _ran(marker) == ""
    assert result.returncode == FAKE_SUDO_REFUSED, (result.returncode, result.stderr)
