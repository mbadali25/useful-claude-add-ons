"""deploy/deploy.py and its deploy.sh / deploy.ps1 pair, against fakes only.

The fake machine (tests/deploy_box.py) and its fixtures (conftest.py) keep every
run inside tmp_path. Both OS flavours (systemd + ufw, scheduled task + netsh) run
on any host through AI_CONNECT_DEPLOY_OS.
"""
import hashlib
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy_box import (AUTH_KEY, BASH, DEPLOY_DIR, NATIVE, PEER_TOKEN, PLUGIN, PWSH, SUBNET, Box, FakeBridge, Phase,
                        already, leaks, output, steps)

# ---------------------------------------------------------------- bridge


@pytest.fixture(scope="module", params=["linux", "windows"])
def bridge(request, tmp_path_factory, venv):
    """A Bridge machine's whole life, run once per OS flavour: each test reads one phase of it.

    dry run on a clean machine -> deploy -> the same again -> status -> add a peer ->
    uninstall dry run -> uninstall -> uninstall again.
    """
    box = Box(tmp_path_factory.mktemp(f"bridge-{request.param}"), venv, request.param)

    def accepted():  # the real Bridge's rule: the hashes in its own auth.peers
        if not box.config_file.exists():
            return set()
        return set(((box.config().get("auth") or {}).get("peers") or {}).values())
    server = FakeBridge(accepted)
    args = ["bridge", "--name", "hub", "--peer", "laptop", "--port", str(server.port)]
    port = ["--port", str(server.port)]
    run = SimpleNamespace()
    run.box, run.port, run.target = box, server.port, request.param
    try:
        run.dry = Phase(box, *args, "--dry-run")
        run.dry_left_config = box.config_file.exists()
        run.first = Phase(box, *args)
        run.config = box.config()
        run.state = box.state()
        run.unit = box.systemd / "ai-connect.service"
        run.unit_text = run.unit.read_text(encoding="utf-8") if run.unit.exists() else ""
        config_dir = box.home / ".config" / "ai-connect"
        run.laptop_token = (config_dir / "peer-tokens" / "laptop.token").read_text(encoding="utf-8").strip()
        run.secrets = [run.laptop_token, run.config["client"]["token"],
                       (config_dir / "observer.token").read_text(encoding="utf-8").strip(),
                       (config_dir / "user.token").read_text(encoding="utf-8").strip()]
        run.second = Phase(box, *args)
        run.status = Phase(box, "status")
        run.add_peer = Phase(box, *args, "--peer", "desk")
        run.peers_after_add = set(box.config()["auth"]["peers"])
        run.uninstall_dry = Phase(box, "uninstall", "--purge", "--dry-run", *port)
        run.uninstall = Phase(box, "uninstall", "--yes", "--purge", *port)
        run.state_after_uninstall = box.state()
        run.config_after_uninstall = box.config_file.exists()
        run.unit_after_uninstall = run.unit.exists()
        run.uninstall_again = Phase(box, "uninstall", "--yes", "--purge", *port)
    finally:
        server.close()
    return run


def test_bridge_happy_path(bridge):
    first = bridge.first
    assert first.res.returncode == 0, first.text
    assert [s.split("]")[0] for s in steps(first.out)] == [f"[{n}/7" for n in range(1, 8)]
    config = bridge.config
    assert config["server"]["host"] == "127.0.0.1"
    assert config["server"]["port"] == bridge.port
    assert config["client"]["bridge_url"] == f"ws://127.0.0.1:{bridge.port}"
    assert set(config["auth"]["peers"]) == {"hub", "laptop"}
    assert hashlib.sha256(bridge.laptop_token.encode()).hexdigest() == config["auth"]["peers"]["laptop"]
    assert "accepted this machine's token" in first.out
    state = bridge.state
    if bridge.target == "linux":
        assert "-m server.main" in bridge.unit_text and f"WorkingDirectory={PLUGIN}" in bridge.unit_text
        assert state["units"]["ai-connect"] == {"active": True, "enabled": True}
        assert any(SUBNET in line and str(bridge.port) in line for line in state["ufw"])
    else:
        assert state["tasks"]["AI-Connect Bridge"] == "Running"
        assert state["rules"]["AI-Connect Bridge"] == SUBNET
        assert "pythonw.exe" in state["task_xml"] and "LeastPrivilege" in state["task_xml"]
        added = [c for c in first.calls if c[:5] == ["netsh", "advfirewall", "firewall", "add", "rule"]]
        assert len(added) == 1 and "profile=private" in added[0] and f"remoteip={SUBNET}" in added[0]


def test_bridge_rerun_is_idempotent(bridge):
    second = bridge.second
    assert second.res.returncode == 0, second.text
    assert second.mutations == []
    assert not second.files_changed and not second.state_changed
    # deps, Tailscale installed, on the tailnet, config, peer, service, firewall; the health check always runs
    assert len(already(second.res)) == 7, second.out
    assert "would:" not in second.out and "  done: write" not in second.out


def test_bridge_dry_run_changes_nothing(bridge):
    dry = bridge.dry
    assert dry.res.returncode == 0, dry.text
    assert "(dry run)" in dry.out and dry.out.count("would:") >= 6, dry.out
    assert dry.changed_nothing(), dry.mutations
    assert not bridge.dry_left_config


def test_bridge_never_prints_a_token(bridge):
    text = "".join(p.text for p in (bridge.dry, bridge.first, bridge.second, bridge.status, bridge.add_peer,
                                    bridge.uninstall_dry, bridge.uninstall))
    for secret in bridge.secrets:
        assert len(secret) == 64
        assert not leaks(secret, text), "a token leaked"
    assert f"token ****{bridge.laptop_token[-4:]} written" in bridge.first.out  # shown masked, not hidden


def test_bridge_status(bridge):
    status = bridge.status
    assert status.res.returncode == 0, status.text
    assert "service: running" in status.out
    assert f"firewall: rule present for {SUBNET} on port {bridge.port}" in status.out
    assert "bridge: ok" in status.out
    assert status.changed_nothing()


def test_bridge_new_peer_on_rerun_restarts_service(bridge):
    add = bridge.add_peer
    assert add.res.returncode == 0, add.text
    assert bridge.peers_after_add == {"hub", "laptop", "desk"}
    restart = ["systemctl", "restart", "ai-connect"] if bridge.target == "linux" else ["schtasks", "/Run"]
    assert any(c[:len(restart)] == restart for c in add.calls), add.calls
    assert "already done: peer 'laptop'" in add.out


def test_uninstall_dry_run_changes_nothing(bridge):
    dry = bridge.uninstall_dry
    assert dry.res.returncode == 0, dry.text
    assert dry.out.count("would:") >= 3
    assert dry.changed_nothing(), dry.mutations


def test_uninstall_removes_everything_and_reruns_clean(bridge):
    assert bridge.uninstall.res.returncode == 0, bridge.uninstall.text
    state = bridge.state_after_uninstall
    assert not bridge.config_after_uninstall and not bridge.unit_after_uninstall
    if bridge.target == "linux":
        assert state["ufw"] == [] and not state["units"]["ai-connect"]["active"]
    else:
        assert state["tasks"] == {} and state["rules"] == {}
    again = bridge.uninstall_again
    assert again.res.returncode == 0, again.text
    assert again.changed_nothing(), again.mutations
    assert len(already(again.res)) == 5, again.out


def test_bridge_without_tailscale_ip_fails(box):
    box.set(ts_ip="")
    res = box.deploy("bridge", "--name", "hub")
    assert res.returncode == 1
    assert "no Tailscale IPv4 address" in res.stderr
    assert not box.config_file.exists() and box.mutations() == []


def test_bridge_without_tailscale_and_told_not_to_install(box):
    box.remove_tool("tailscale")
    res = box.deploy("bridge", "--name", "hub", "--no-install-tailscale")
    assert res.returncode == 3, output(res)
    assert "tailscale is not installed" in res.stderr and box.mutations() == []


def test_bridge_health_check_fails_when_bridge_refuses(box):
    server = FakeBridge(set)  # refuses every token
    try:
        res = box.deploy("bridge", "--name", "hub", "--port", str(server.port))
    finally:
        server.close()
    assert res.returncode == 1
    assert "refused this machine's token" in res.stderr


# ---------------------------------------------------------------- peer


def peer_args(port: int, token_file: Path) -> list[str]:
    return ["peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(port), "--token-file", str(token_file)]


@pytest.fixture(scope="module")
def peer(tmp_path_factory, venv):
    """A peer machine, off the tailnet at first: dry run -> deploy -> the same again -> status."""
    tmp = tmp_path_factory.mktemp("peer")
    box = Box(tmp, venv, NATIVE)
    box.set(ts_backend="Stopped", ts_ip="")
    token_file = tmp / "laptop.token"
    token_file.write_text(PEER_TOKEN + "\n", encoding="utf-8")
    server = FakeBridge(lambda: {hashlib.sha256(PEER_TOKEN.encode()).hexdigest()})
    args, key = peer_args(server.port, token_file), {"TS_AUTHKEY": AUTH_KEY}
    run = SimpleNamespace()
    run.box, run.port = box, server.port
    try:
        run.dry = Phase(box, *args, "--dry-run", extra_env=key)
        run.first = Phase(box, *args, extra_env=key)
        run.state = box.state()
        run.client = box.config()["client"]
        run.second = Phase(box, *args, extra_env=key)
        run.status = Phase(box, "status")
    finally:
        server.close()
    return run


def test_peer_happy_path(peer):
    first = peer.first
    assert first.res.returncode == 0, first.text
    assert [s.split("]")[0] for s in steps(first.out)] == [f"[{n}/5" for n in range(1, 6)]
    assert peer.state["plugins"] == ["ai-connect@useful-claude-add-ons"]
    assert str(PLUGIN / "client" / "server.py") in peer.state["mcp"]["ai-connect"]
    assert peer.state["ts_backend"] == "Running"
    up = [c for c in first.calls if c[:2] == ["tailscale", "up"]]
    assert len(up) == 1 and "--hostname=laptop" in up[0]
    assert (peer.client["name"], peer.client["token"], peer.client["bridge_url"]) == \
        ("laptop", PEER_TOKEN, f"ws://127.0.0.1:{peer.port}")
    assert "accepted this machine's token" in first.out


def test_peer_rerun_is_idempotent(peer):
    second = peer.second
    assert second.res.returncode == 0, second.text
    assert second.changed_nothing(), second.mutations
    assert len(already(second.res)) == 5, second.out  # deps, plugin, MCP server, VPN, config


def test_peer_dry_run_changes_nothing(peer):
    dry = peer.dry
    assert dry.res.returncode == 0, dry.text
    assert dry.out.count("would:") >= 5, dry.out
    assert dry.changed_nothing(), dry.mutations


def test_peer_never_prints_token_or_auth_key(peer):
    text = "".join(p.text for p in (peer.dry, peer.first, peer.second, peer.status))
    for secret in (PEER_TOKEN, AUTH_KEY):
        assert not leaks(secret, text), "a secret leaked"
    assert "token ****beef" in peer.dry.out and "token ****beef" in peer.first.out
    key_on_argv = [c for c in peer.first.calls if any(AUTH_KEY in a for a in c) and c[:2] != ["tailscale", "up"]]
    assert key_on_argv == []  # only `tailscale up --auth-key=` itself ever carries it


def test_peer_wrong_token_fails_verification(box, tmp_path):
    box.set(ts_backend="Running")
    wrong = tmp_path / "wrong.token"
    wrong.write_text("0123456789abcdef" * 4, encoding="utf-8")
    server = FakeBridge(lambda: {hashlib.sha256(PEER_TOKEN.encode()).hexdigest()})
    try:
        res = box.deploy(*peer_args(server.port, wrong))
    finally:
        server.close()
    assert res.returncode == 1
    assert "refused this machine's token" in res.stderr
    assert not leaks("0123456789abcdef" * 4, output(res))


def test_peer_without_auth_key_when_off_tailnet_fails(box, tmp_path):
    box.set(ts_backend="Stopped", ts_ip="")
    token_file = tmp_path / "laptop.token"
    token_file.write_text(PEER_TOKEN, encoding="utf-8")
    res = box.deploy(*peer_args(9, token_file))
    assert res.returncode == 1
    assert "no auth key" in res.stderr
    assert not box.config_file.exists() and box.mutations() == []


# ---------------------------------------------------------------- bad arguments


@pytest.fixture(scope="module")
def args_box(tmp_path_factory, venv):
    return Box(tmp_path_factory.mktemp("bad-args"), venv, NATIVE)


@pytest.mark.parametrize("args", [
    [], ["bogus"], ["peer", "--bridge", "127.0.0.1"], ["peer", "--name", "laptop"],
    ["peer", "--name", "bad name!", "--bridge", "127.0.0.1"], ["peer", "--name", "laptop", "--bridge", "a b"],
    ["peer", "--name", "laptop", "--bridge", "127.0.0.1"], ["bridge", "--port", "70000"],
    ["bridge", "--vpn-subnet", "nope"], ["bridge", "--peer", "-x-"], ["uninstall"], ["status", "--dry-run"],
], ids=lambda a: " ".join(a) or "no-args")
def test_bad_arguments_exit_2_and_change_nothing(args_box, args):
    phase = Phase(args_box, *args)
    assert phase.res.returncode == 2, phase.text
    assert phase.res.stderr.strip()
    assert phase.calls == [] and phase.changed_nothing()


# ---------------------------------------------------------------- the .sh / .ps1 pair


def test_shims_are_lf_and_paired():
    for name in ("deploy.sh", "deploy.ps1", "deploy.py", "config_tool.py", "deploy_core.py", "ts_install.py",
                 "tailnet_setup.py", "smoke_test.py"):
        assert b"\r" not in (DEPLOY_DIR / name).read_bytes(), name


def _sh(box, args):
    env = dict(box.env)
    if os.name == "nt":  # Git Bash needs its own coreutils (dirname) on PATH
        env["PATH"] = os.pathsep.join([r"C:\Program Files\Git\usr\bin", env["PATH"]])
    return subprocess.run([BASH, str(DEPLOY_DIR / "deploy.sh"), *args], capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL, env=env, timeout=180)


def _ps1(box, args, tmp_path):
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(DEPLOY_DIR / "deploy.ps1"), *args],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, timeout=180,
                          env=dict(box.env, XDG_CACHE_HOME=str(tmp_path / "xdg-cache")))


@pytest.mark.skipif(not BASH or not PWSH, reason="needs both bash and pwsh at known paths")
def test_sh_and_ps1_print_the_same_steps(box, tmp_path):
    cases = [["bridge", "--name", "hub", "--peer", "laptop", "--dry-run"], ["uninstall", "--dry-run"],
             ["peer", "--name", "bad name!", "--bridge", "x"]]
    for args in cases:
        sh, ps1 = _sh(box, args), _ps1(box, args, tmp_path)
        assert (sh.returncode, sh.stdout, sh.stderr) == (ps1.returncode, ps1.stdout, ps1.stderr), args
        assert sh.stdout or sh.stderr
    assert len(steps(_sh(box, cases[0]).stdout)) == 7
    assert box.mutations() == []


@pytest.mark.skipif(not BASH, reason="bash not found")
def test_deploy_sh_syntax():
    res = subprocess.run([BASH, "-n", str(DEPLOY_DIR / "deploy.sh")], capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL)
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(not PWSH, reason="pwsh not found at an absolute path")
def test_deploy_ps1_passes_the_repo_powershell_static_check(tmp_path):
    checker = PLUGIN.parents[1] / "scripts" / "check-powershell.ps1"
    res = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(checker), "-Path",
                          str(DEPLOY_DIR / "deploy.ps1")], capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL, env=dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "xdg-cache")))
    assert res.returncode == 0, res.stdout + res.stderr
