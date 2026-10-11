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
- the function's `$EUID` is replaced by a value each test states, so no test
  depends on who runs the suite;
- the "must not reach" tests at the end fail if any of the above is undone.

Skipped when bash is not on PATH (e.g. a CI image without Git Bash / WSL), and
when the real euid is 0 unless ALLOW_ROOT_ENV is set to 1: a root caller is the
one for whom a hermeticity bug edits the host firewall, and whether it is
sandboxed cannot be detected from here, so it has to say so.
"""

import os
import shlex
import shutil
import stat
import subprocess
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


_ROOT_SKIP = root_skip_reason(os.geteuid() if hasattr(os, "geteuid") else None, os.environ)

pytestmark = [
    pytest.mark.skipif(BASH is None, reason="bash not found on PATH"),
    pytest.mark.skipif(_ROOT_SKIP is not None, reason=_ROOT_SKIP or ""),
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
STATE="{state.as_posix()}"
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
STATE="{state.as_posix()}"
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


def run_in_child(bin_dir: Path, script: str):
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        env=child_env(bin_dir),
        timeout=30,
    )


def extract_configure_firewall() -> str:
    """configure_firewall() as install.sh has it, with its one `$EUID` read
    replaced by `$TEST_EUID`: bash's own EUID is read-only, and the real one
    is exactly what a test must not depend on."""
    lines = INSTALL_SH.read_text(encoding="utf-8").splitlines()
    start = lines.index("configure_firewall() {")
    end = lines.index("}", start)
    body = "\n".join(lines[start : end + 1]) + "\n"
    assert body.count("$EUID") == 1, "configure_firewall's EUID guard changed; update this harness"
    return body.replace("$EUID", "$TEST_EUID")


def run_configure_firewall(bin_dir: Path, vpn_subnet: str = "100.64.0.0/10", euid: int = NON_ROOT_EUID):
    """Calls the extracted configure_firewall() once, as the given euid, in a
    child that can resolve only the fakes in bin_dir and REAL_TOOLS."""
    script = f"""
set -e
{extract_configure_firewall()}
RED='' GREEN='' YELLOW='' BLUE='' NC=''
VPN_SUBNET="{vpn_subnet}"
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


def _make_canaries(canary_dir: Path, marker: Path) -> None:
    canary_dir.mkdir()
    for name in FIREWALL_TOOLS:
        _write_script(
            canary_dir / name,
            f'echo "{name} $*" >> {shlex.quote(marker.as_posix())}\nexit 0',
        )


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


def test_child_path_holds_only_test_made_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("BASH_ENV", str(tmp_path / "never_sourced.sh"))
    monkeypatch.setenv("AI_CONNECT_TEST_CALLER_SECRET", "not for the child")
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


def test_child_cannot_resolve_a_real_firewall_tool_or_sudo(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    result = run_in_child(
        bin_dir,
        "for tool in " + " ".join(FIREWALL_TOOLS) + '; do command -v "$tool"; done; exit 0',
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "", f"the child resolved a real tool: {result.stdout!r}"


@pytest.mark.parametrize(
    "euid, expected",
    [
        (0, "neither ufw nor firewalld"),
        (NON_ROOT_EUID, "not root and no passwordless sudo"),
    ],
)
def test_canary_tools_on_callers_path_are_never_run(tmp_path, monkeypatch, euid, expected):
    # Stand-ins for a host's real ufw, firewall-cmd and sudo, first on the
    # CALLER's PATH. With no fake in bin_dir, nothing may reach them.
    marker = tmp_path / "canary_ran"
    _make_canaries(tmp_path / "host_bin", marker)
    monkeypatch.setenv("PATH", str(tmp_path / "host_bin") + os.pathsep + os.environ.get("PATH", ""))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    result = run_configure_firewall(bin_dir, euid=euid)

    ran = marker.read_text(encoding="utf-8") if marker.exists() else ""
    assert ran == "", f"a tool outside the fake dir ran: {ran!r}"
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout


@pytest.mark.parametrize("command", ["ufw", "{host_bin}/ufw", "-n ufw", "true extra"])
def test_fake_sudo_refuses_a_command_that_is_not_a_fake(tmp_path, command):
    # The fake sudo is handed a PATH on which a "real" ufw resolves. It must
    # refuse, not exec it: a pass-through sudo is how the real ufw was reached.
    marker = tmp_path / "canary_ran"
    host_bin = tmp_path / "host_bin"
    _make_canaries(host_bin, marker)
    (host_bin / "sudo").unlink()
    (host_bin / "true").symlink_to(host_bin / "ufw")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _make_sudo(bin_dir)
    env = child_env(bin_dir)
    env["PATH"] = os.pathsep.join([str(bin_dir), str(host_bin), env["PATH"]])
    argv = command.format(host_bin=host_bin.as_posix())

    result = subprocess.run(
        [BASH, "-c", f"sudo {argv} allow from 100.64.0.0/10"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    ran = marker.read_text(encoding="utf-8") if marker.exists() else ""
    assert ran == "", f"the fake sudo ran a tool outside the fake dir: {ran!r}"
    assert result.returncode == FAKE_SUDO_REFUSED, (result.returncode, result.stderr)
    assert "fake sudo: refusing" in result.stderr
