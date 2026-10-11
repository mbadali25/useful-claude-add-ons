# pylint: disable=subprocess-run-check  # upstream AI-Connect style, kept to minimise the fork's diff
"""Tests for install.sh's configure_firewall() function.

Runs only the extracted function body under bash, with fake ufw / firewall-cmd
/ sudo scripts on PATH, so no real firewall is ever touched. Each test asserts
the exact commands configure_firewall ran and that a second run detects its
own rule instead of adding it again ("already present").

Skipped when bash is not on PATH (e.g. a CI image without Git Bash / WSL).
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"

BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not found on PATH")


def _write_script(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _make_sudo(bin_dir: Path) -> None:
    # Passes straight through: lets `sudo -n true` and `sudo <cmd> ...`
    # succeed without ever touching a real privileged command.
    _write_script(
        bin_dir / "sudo",
        '[[ "$1" == "-n" ]] && shift\nexec "$@"\n',
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


def run_configure_firewall(bin_dir: Path, vpn_subnet: str = "100.64.0.0/10", as_root: bool = False):
    """Extracts configure_firewall() from install.sh and calls it once,
    under env isolated to the given fake-tool bin_dir."""
    extracted = bin_dir.parent / "_configure_firewall.sh"
    extractor = (
        r"sed -n '/^configure_firewall() {/,/^}/p' "
        + f"'{INSTALL_SH.as_posix()}' > '{extracted.as_posix()}'"
    )
    script = f"""
set -e
{extractor}
source '{extracted.as_posix()}'
RED='' GREEN='' YELLOW='' BLUE='' NC=''
VPN_SUBNET="{vpn_subnet}"
configure_firewall
"""
    env = dict(os.environ)
    # Keep PATH minimal: only the fake-tool dir plus what bash itself needs.
    real_path = env.get("PATH", "")
    env["PATH"] = str(bin_dir) + os.pathsep + real_path
    if as_root:
        script = "EUID=0\n" + script
    result = subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return result


def test_extraction_finds_the_function():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "configure_firewall() {" in text


def test_skips_without_root_or_sudo(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # No sudo, no ufw, no firewall-cmd on PATH, and bash's own EUID is a
    # normal user: configure_firewall must refuse to touch anything.
    result = run_configure_firewall(bin_dir)
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
