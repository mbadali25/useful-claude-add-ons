"""tsadmin.py: mint-key, revoke, vpn-up, vpn-down against a fake API and a fake tailscale CLI."""
import hashlib
import os
import re
import socket
import sys
from pathlib import Path

import pytest

from conftest import ACCESS_TOKEN, AUTH_KEY, CLIENT_SECRET

SECRETS = (AUTH_KEY, CLIENT_SECRET, ACCESS_TOKEN)


def assert_no_secret(text, allow=()):
    for secret in SECRETS:
        if secret not in allow:
            assert secret not in text, f"secret leaked: {secret[:12]}..."


# ------------------------------------------------------------------ mint-key


def test_mint_key_request_body_is_single_use_ephemeral_preauthorized_tagged(ts, api, capsys):
    assert ts.main(["mint-key", "--name", "alice-laptop"]) == 0
    token_call = api.find("POST", "/oauth/token")[0]
    assert token_call["form"] == {"client_id": "kOAUTHCLIENTID", "client_secret": CLIENT_SECRET,
                                  "grant_type": "client_credentials"}
    key_call = api.find("POST", "/tailnet/-/keys")[0]
    assert key_call["token"] == ACCESS_TOKEN
    assert key_call["body"]["capabilities"] == {"devices": {"create": {
        "reusable": False, "ephemeral": True, "preauthorized": True, "tags": ["tag:ai-peer"]}}}
    assert key_call["body"]["expirySeconds"] == 86400
    assert key_call["body"]["description"] == "ai-connect peer alice-laptop"
    assert len(api.find("POST", "/tailnet/-/keys")) == 1


@pytest.mark.parametrize("flag,seconds", [("12h", 43200), ("30m", 1800), ("3600", 3600), ("2d", 172800)])
def test_mint_key_expiry_flag(ts, api, flag, seconds):
    assert ts.main(["mint-key", "--name", "p1", "--expiry", flag]) == 0
    assert api.find("POST", "/tailnet/-/keys")[0]["body"]["expirySeconds"] == seconds


@pytest.mark.parametrize("flag", ["0", "10s", "91d", "1w", ""])
def test_mint_key_rejects_bad_expiry_without_calling_api(ts, api, flag, capsys):
    assert ts.main(["mint-key", "--name", "p1", "--expiry", flag]) == 1
    assert api.calls == []


@pytest.mark.parametrize("name", ["bad name", "-lead", "x" * 64, "a.b", "ünï"])
def test_mint_key_rejects_bad_peer_name(ts, api, name):
    assert ts.main(["mint-key", f"--name={name}"]) == 1
    assert api.calls == []


def test_mint_key_prints_key_once_and_never_the_oauth_secrets(ts, api, capsys):
    assert ts.main(["mint-key", "--name", "alice"]) == 0
    out, err = capsys.readouterr()
    assert out.count(AUTH_KEY) == 1
    assert "alice" in out
    assert_no_secret(out + err, allow=(AUTH_KEY,))
    assert AUTH_KEY not in err


def test_mint_key_to_file_writes_key_and_prints_no_secret(ts, api, tmp_path, capsys):
    out_file = tmp_path / "keys" / "alice.key"
    assert ts.main(["mint-key", "--name", "alice", "--out", str(out_file)]) == 0
    assert out_file.read_text(encoding="utf-8") == AUTH_KEY + "\n"
    out, err = capsys.readouterr()
    assert_no_secret(out + err)
    assert str(out_file.resolve()) in out
    assert [p.name for p in out_file.parent.iterdir()] == ["alice.key"]  # no temp file left


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_mint_key_file_is_owner_only_posix(ts, api, tmp_path):
    out_file = tmp_path / "alice.key"
    ts.main(["mint-key", "--name", "alice", "--out", str(out_file)])
    assert out_file.stat().st_mode & 0o077 == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL")
def test_mint_key_file_acl_has_no_inherited_entries_windows(ts, api, tmp_path):
    import subprocess
    out_file = tmp_path / "alice.key"
    ts.main(["mint-key", "--name", "alice", "--out", str(out_file)])
    acl = subprocess.run(["icacls", str(out_file)], capture_output=True, text=True).stdout
    assert "(I)" not in acl  # inheritance stripped
    assert os.environ["USERNAME"].lower() in acl.lower()


def test_mint_key_api_error_names_status_and_leaks_nothing(ts, api, capsys):
    api.routes[("POST", "/tailnet/-/keys")] = (403, {"message": f"denied for {CLIENT_SECRET}"})
    assert ts.main(["mint-key", "--name", "alice"]) == 1
    out, err = capsys.readouterr()
    assert "HTTP 403" in err
    assert_no_secret(out + err)


def test_mint_key_token_exchange_failure(ts, api, capsys):
    api.routes[("POST", "/oauth/token")] = (401, {"message": "invalid client"})
    assert ts.main(["mint-key", "--name", "alice"]) == 1
    _, err = capsys.readouterr()
    assert "OAuth token exchange failed: HTTP 401" in err
    assert api.find("POST", "/tailnet/-/keys") == []
    assert_no_secret(err)


def test_mint_key_without_credentials_explains(ts, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(ts, "http", lambda *a, **k: calls.append(a) or (200, {}))
    assert ts.main(["mint-key", "--name", "alice"]) == 1
    assert "TS_OAUTH_CLIENT_ID" in capsys.readouterr().err
    assert calls == []


def test_unexpected_exception_does_not_leak_secret(ts, api, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError(f"exploded holding {AUTH_KEY} and {CLIENT_SECRET}")
    monkeypatch.setattr(ts, "key_request_body", boom)
    assert ts.main(["mint-key", "--name", "alice"]) == 1
    out, err = capsys.readouterr()
    assert "RuntimeError" in err
    assert_no_secret(out + err)


def test_peer_token_skipped_gracefully_when_installer_absent(ts, api, monkeypatch, capsys):
    monkeypatch.setattr(ts, "find_installer", lambda explicit: None)
    assert ts.main(["mint-key", "--name", "alice", "--peer-token"]) == 0
    assert "peer token: skipped" in capsys.readouterr().out


def test_peer_token_runs_installer_add_peer(ts, api, tmp_path, capsys):
    installer = tmp_path / "installer.py"
    marker = tmp_path / "ran.txt"
    installer.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text(' '.join(sys.argv[1:]))\n", encoding="utf-8")
    assert ts.main(["mint-key", "--name", "alice", "--peer-token", "--installer", str(installer)]) == 0
    assert marker.read_text() == "add-peer alice"


REAL_INSTALLER = Path(__file__).resolve().parents[2] / "installer.py"


@pytest.fixture
def bridge_home(tmp_path, monkeypatch):
    """A Bridge machine's config under a throwaway home, for the real installer.py."""
    pytest.importorskip("yaml")
    home = tmp_path / "home"
    config = home / ".config" / "ai-connect" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("auth:\n  peers: {}\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return config


def test_peer_token_drives_the_real_installer_add_peer(ts, api, bridge_home, capfd):
    import yaml
    assert ts.main(["mint-key", "--name", "alice", "--peer-token",
                    "--installer", str(REAL_INSTALLER)]) == 0
    out = capfd.readouterr().out
    assert "Peer 'alice' added" in out
    token = re.search(r"^\s+([0-9a-f]{64})\s*$", out, re.MULTILINE).group(1)
    peers = yaml.safe_load(bridge_home.read_text(encoding="utf-8"))["auth"]["peers"]
    assert peers == {"alice": hashlib.sha256(token.encode()).hexdigest()}


def test_peer_token_existing_peer_warns_but_mint_still_succeeds(ts, api, bridge_home, capfd):
    bridge_home.write_text("auth:\n  peers:\n    alice: " + "0" * 64 + "\n", encoding="utf-8")
    assert ts.main(["mint-key", "--name", "alice", "--peer-token",
                    "--installer", str(REAL_INSTALLER)]) == 0
    captured = capfd.readouterr()
    assert "already exists" in captured.err
    assert "installer exited 1; the auth key above is still valid" in captured.err


@pytest.mark.parametrize("parts", [("venv", "Scripts", "python.exe"), ("venv", "bin", "python")])
def test_installer_runs_under_the_venv_beside_it(ts, tmp_path, parts):
    installer = tmp_path / "installer.py"
    installer.write_text("", encoding="utf-8")
    venv_python = tmp_path.joinpath(*parts)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    assert ts.installer_python(installer) == str(venv_python)


def test_installer_without_a_venv_falls_back_to_this_interpreter(ts, tmp_path):
    assert ts.installer_python(tmp_path / "installer.py") == sys.executable


# ------------------------------------------------------------------ revoke


def devices(*items):
    return 200, {"devices": list(items)}


def test_revoke_deletes_matching_tagged_node(ts, api, capsys):
    api.routes[("GET", "/tailnet/-/devices")] = devices(
        {"nodeId": "nA", "name": "alice.tail1.ts.net", "hostname": "alice", "tags": ["tag:ai-peer"]},
        {"nodeId": "nB", "name": "bob.tail1.ts.net", "hostname": "bob", "tags": ["tag:ai-peer"]})
    assert ts.main(["revoke", "--name", "alice"]) == 0
    deletes = [c for c in api.calls if c["method"] == "DELETE"]
    assert [c["url"].rsplit("/", 1)[1] for c in deletes] == ["nA"]
    assert_no_secret("".join(capsys.readouterr()))


def test_revoke_ignores_untagged_node_unless_any_tag(ts, api):
    api.routes[("GET", "/tailnet/-/devices")] = devices(
        {"nodeId": "nA", "name": "alice.tail1.ts.net", "hostname": "alice", "tags": []})
    assert ts.main(["revoke", "--name", "alice"]) == 1
    assert not [c for c in api.calls if c["method"] == "DELETE"]
    assert ts.main(["revoke", "--name", "alice", "--any-tag"]) == 0


def test_revoke_refuses_ambiguous_name_without_all(ts, api):
    two = [{"nodeId": f"n{i}", "name": f"alice-{i}.ts.net", "hostname": "alice", "tags": ["tag:ai-peer"]}
           for i in (1, 2)]
    api.routes[("GET", "/tailnet/-/devices")] = devices(*two)
    assert ts.main(["revoke", "--name", "alice"]) == 1
    assert not [c for c in api.calls if c["method"] == "DELETE"]
    assert ts.main(["revoke", "--name", "alice", "--all"]) == 0
    assert len([c for c in api.calls if c["method"] == "DELETE"]) == 2


def test_revoke_delete_failure_is_reported(ts, api, capsys):
    api.routes[("GET", "/tailnet/-/devices")] = devices(
        {"nodeId": "nA", "name": "alice.ts.net", "hostname": "alice", "tags": ["tag:ai-peer"]})
    api.routes[("DELETE", "/device/nA")] = (403, {"message": "missing devices:core scope"})
    assert ts.main(["revoke", "--name", "alice"]) == 1
    assert "devices:core" in capsys.readouterr().err


# ------------------------------------------------------------------ vpn-up


@pytest.fixture
def probe(ts, monkeypatch):
    seen = []

    def set_result(result):
        def fake(host, port, timeout=5.0, socks_port=None):
            seen.append((host, port, socks_port))
            return result
        monkeypatch.setattr(ts, "probe_tcp", fake)
    set_result("ok")
    set_result.seen = seen
    return set_result


def test_vpn_up_already_connected_is_idempotent(ts, fake_ts, probe, monkeypatch, capsys):
    fake_ts.set(backend="Running")
    monkeypatch.setenv("TS_AUTHKEY", AUTH_KEY)
    assert ts.main(["vpn-up", "--bridge", "bridge-host"]) == 0
    out, err = capsys.readouterr()
    assert "already connected" in out
    assert fake_ts.up_calls() == []  # the single-use key is not spent
    assert probe.seen == [("bridge-host", 9999, None)]
    assert_no_secret(out + err)


def test_vpn_up_running_but_probe_timeout_is_could_not_tell(ts, fake_ts, probe, capsys):
    fake_ts.set(backend="Running")
    probe("unknown")
    assert ts.main(["vpn-up", "--bridge", "bridge-host"]) == 2
    assert "already connected" not in capsys.readouterr().out
    assert fake_ts.up_calls() == []


def test_vpn_up_running_but_bridge_refuses_is_failed(ts, fake_ts, probe):
    fake_ts.set(backend="Running")
    probe("refused")
    assert ts.main(["vpn-up", "--bridge", "bridge-host"]) == 1


def test_vpn_up_running_without_bridge_host_is_could_not_tell(ts, fake_ts, probe):
    fake_ts.set(backend="Running")
    assert ts.main(["vpn-up"]) == 2
    assert probe.seen == []


def test_vpn_up_bridge_host_from_env(ts, fake_ts, probe, monkeypatch):
    fake_ts.set(backend="Running")
    monkeypatch.setenv("AI_CONNECT_BRIDGE_HOST", "env-bridge")
    assert ts.main(["vpn-up"]) == 0
    assert probe.seen[0][0] == "env-bridge"


def test_vpn_up_joins_with_env_key_and_tags(ts, fake_ts, probe, monkeypatch, capsys):
    monkeypatch.setattr(ts, "IS_WINDOWS", False)
    monkeypatch.setenv("TS_AUTHKEY", AUTH_KEY)
    assert ts.main(["vpn-up", "--bridge", "b", "--hostname", "alice"]) == 0
    (call,) = fake_ts.up_calls()
    assert f"--auth-key={AUTH_KEY}" in call
    assert "--advertise-tags=tag:ai-peer" in call
    assert "--hostname=alice" in call
    assert "--unattended" not in call
    out, err = capsys.readouterr()
    assert "connected" in out
    assert_no_secret(out + err)


def test_vpn_up_adds_unattended_on_windows(ts, fake_ts, probe, monkeypatch):
    monkeypatch.setattr(ts, "IS_WINDOWS", True)
    monkeypatch.setenv("TS_AUTHKEY", AUTH_KEY)
    assert ts.main(["vpn-up", "--bridge", "b"]) == 0
    assert "--unattended" in fake_ts.up_calls()[0]


def test_vpn_up_deletes_key_file_after_success(ts, fake_ts, probe, tmp_path):
    key_file = tmp_path / "alice.key"
    key_file.write_text("\n" + AUTH_KEY + "\n", encoding="utf-8")
    assert ts.main(["vpn-up", "--auth-key-file", str(key_file), "--bridge", "b"]) == 0
    assert not key_file.exists()
    assert f"--auth-key={AUTH_KEY}" in fake_ts.up_calls()[0]


def test_vpn_up_key_file_from_env(ts, fake_ts, probe, tmp_path, monkeypatch):
    key_file = tmp_path / "k"
    key_file.write_text(AUTH_KEY, encoding="utf-8")
    monkeypatch.setenv("TS_AUTHKEY_FILE", str(key_file))
    assert ts.main(["vpn-up", "--bridge", "b"]) == 0
    assert not key_file.exists()


def test_vpn_up_keeps_key_file_and_redacts_when_up_fails(ts, fake_ts, probe, tmp_path, capsys):
    fake_ts.set(backend="Stopped", up_rc=1, up_stderr=f"backend error: invalid key: {AUTH_KEY}")
    key_file = tmp_path / "alice.key"
    key_file.write_text(AUTH_KEY, encoding="utf-8")
    assert ts.main(["vpn-up", "--auth-key-file", str(key_file), "--bridge", "b"]) == 1
    assert key_file.exists()
    out, err = capsys.readouterr()
    assert "tailscale up failed" in err
    assert_no_secret(out + err)


def test_vpn_up_not_connected_without_key_fails(ts, fake_ts, probe, capsys):
    assert ts.main(["vpn-up", "--bridge", "b"]) == 1
    assert "TS_AUTHKEY" in capsys.readouterr().err
    assert fake_ts.up_calls() == []


def test_vpn_up_empty_key_file_fails(ts, fake_ts, probe, tmp_path):
    key_file = tmp_path / "empty.key"
    key_file.write_text("\n\n", encoding="utf-8")
    assert ts.main(["vpn-up", "--auth-key-file", str(key_file)]) == 1
    assert fake_ts.up_calls() == []


def test_vpn_up_succeeds_but_backend_not_running_is_could_not_tell(ts, fake_ts, probe, monkeypatch):
    fake_ts.set(backend="Stopped", after_up="Starting")
    monkeypatch.setenv("TS_AUTHKEY", AUTH_KEY)
    assert ts.main(["vpn-up", "--bridge", "b"]) == 2


def test_vpn_up_falls_back_to_userspace_when_no_tun(ts, fake_ts, probe, monkeypatch, tmp_path, capsys):
    fake_ts.set(backend="Stopped", up_rc=1, up_stderr="failed to connect to local tailscaled; it doesn't appear to be running")
    monkeypatch.setenv("TS_AUTHKEY", AUTH_KEY)
    started = []
    monkeypatch.setattr(ts, "start_userspace_tailscaled", lambda: started.append(True))
    assert ts.main(["vpn-up", "--bridge", "b"]) == 0
    assert started == [True]
    ups = fake_ts.up_calls()
    assert len(ups) == 2 and any(a.startswith("--socket=") for a in ups[1])
    assert "--unattended" not in ups[1]
    assert probe.seen[-1] == ("b", 9999, 1055)
    out, err = capsys.readouterr()
    assert "socks5h://localhost:1055" in out
    assert_no_secret(out + err)


def test_vpn_up_userspace_needs_tailscaled(ts, fake_ts, probe, monkeypatch, capsys):
    monkeypatch.setenv("TS_AUTHKEY", AUTH_KEY)
    real_which = ts.shutil.which
    monkeypatch.setattr(ts.shutil, "which", lambda name: real_which(name) if name == "tailscale" else None)
    assert ts.main(["vpn-up", "--userspace", "--bridge", "b"]) == 1
    assert "tailscaled" in capsys.readouterr().err


def test_vpn_up_missing_tailscale_exit_3_with_install_hint(ts, tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setenv("TS_AUTHKEY", AUTH_KEY)
    assert ts.main(["vpn-up", "--bridge", "b"]) == 3
    err = capsys.readouterr().err
    assert "not installed" in err and ("winget" in err or "brew" in err or "install.sh" in err)


# ------------------------------------------------------------------ vpn-down


def test_vpn_down(ts, fake_ts, capsys):
    fake_ts.set(backend="Running")
    assert ts.main(["vpn-down"]) == 0
    assert fake_ts.calls()[-1] == ["down"]


def test_vpn_down_logout(ts, fake_ts):
    assert ts.main(["vpn-down", "--logout"]) == 0
    assert fake_ts.calls()[-1] == ["logout"]


def test_vpn_down_failure(ts, fake_ts):
    fake_ts.set(backend="Running", down_rc=1)
    assert ts.main(["vpn-down"]) == 1


def test_vpn_down_missing_tailscale(ts, tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert ts.main(["vpn-down"]) == 3


# ------------------------------------------------------------------ probe (loopback only)


def test_probe_tcp_ok_and_refused_on_loopback(ts):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert ts.probe_tcp("127.0.0.1", port, timeout=2) == "ok"
    finally:
        srv.close()
    # Windows retries a refused SYN for about 2s before reporting it, so allow longer.
    assert ts.probe_tcp("127.0.0.1", port, timeout=5) == "refused"


def test_probe_tcp_unresolvable_is_unknown(ts):
    assert ts.probe_tcp("no-such-host.invalid", 9999, timeout=2) == "unknown"
