"""deploy list, approve and remove: the admin side of onboarding, against fakes only.

The Tailscale API is tests/fake_tailscale_api.py on a loopback port, reached with
the OAuth client tailnet-setup stores; the Bridge is FakeBridge; every system
tool is tests/fake_deploy_bin.py. No real Tailscale call is made.
"""
import base64
import hashlib
import json
from pathlib import Path

import pytest

from deploy_box import NATIVE, PEER_TOKEN, Box, FakeBridge, OwnBridge, Phase, already, leaks
from fake_tailscale_api import (AUTH_KEY_MINTED, CLIENT_ID, CLIENT_SECRET, NODE_ID, OAUTH_ACCESS_TOKEN,
                                FakeTailscaleAPI, device)

LAPTOP_ID, STRAY_ID = "nLAPTOP22CNTRL", "nSTRAY33CNTRL"
HASH = hashlib.sha256(PEER_TOKEN.encode()).hexdigest()
SECRETS = (CLIENT_SECRET, OAUTH_ACCESS_TOKEN)


@pytest.fixture
def api():
    server = FakeTailscaleAPI()
    yield server
    server.close()


def admin_env(box: Box, api: FakeTailscaleAPI) -> dict:
    """The admin machine after tailnet-setup: the OAuth client stored in its owner-only file."""
    api.clients[CLIENT_ID] = CLIENT_SECRET
    oauth = Path(box.env["AI_CONNECT_OAUTH_FILE"])
    oauth.parent.mkdir(parents=True, exist_ok=True)
    oauth.write_text(json.dumps({"oauth_client_id": CLIENT_ID, "oauth_client_secret": CLIENT_SECRET}),
                     encoding="utf-8")
    box.env["TS_API_BASE"] = api.base  # every later run on this machine, deploy bridge too
    return {"TS_API_BASE": api.base}


def restarted(phase: Phase) -> bool:
    want = (["schtasks", "/Run"], ["systemctl", "restart", "ai-connect"])
    return any(w in (c[:len(w)], c[1:1 + len(w)]) for c in phase.calls for w in want)  # or behind sudo


def no_secret_in(text: str) -> bool:
    return not any(leaks(secret.rsplit("-", 1)[-1], text) for secret in SECRETS)


# ---------------------------------------------------------------- list


def test_list_joins_the_tailnet_with_the_bridge_peers_and_flags_expiring_keys(box, api):
    env = admin_env(box, api)
    api.devices[NODE_ID]["tags"] = ["tag:bridge"]  # joined by a login, then tagged: its key still expires
    api.devices[LAPTOP_ID] = device(LAPTOP_ID, "laptop", "100.64.0.2", ["tag:ai-peer"], expiry_disabled=True)
    api.devices[STRAY_ID] = device(STRAY_ID, "stray", "100.64.0.3", ["tag:ai-peer"], expiry_disabled=True)
    with OwnBridge(box) as own:
        assert box.deploy(*own.args, "--peer", "laptop", "--peer", "desk").returncode == 0
        api.devices[NODE_ID]["keyExpiryDisabled"] = False  # as on a Bridge deployed before 0.1.6
        api.requests.clear()
        run = Phase(box, "list", extra_env=env)
    assert run.res.returncode == 0, run.text
    rows = {line.split()[0]: line for line in run.out.splitlines() if line.startswith("  ") and line.split()}
    assert "100.64.0.2" in rows["laptop"] and "tag:ai-peer" in rows["laptop"] and "peer" in rows["laptop"]
    assert "disabled" in rows["laptop"]
    assert "ENABLED" in rows["hub"] and "tag:bridge" in rows["hub"]
    assert "not a Bridge peer" in rows["stray"]
    assert "desk" in rows and "not on the tailnet" in rows["desk"]
    assert "1 node keeps a key that expires: hub" in run.out
    assert api.writes() == [] and run.changed_nothing() and no_secret_in(run.text)


def test_list_without_an_oauth_client_says_how_to_get_one(box, api):
    run = Phase(box, "list", extra_env={"TS_API_BASE": api.base})
    assert run.res.returncode == 1
    assert "tailnet-setup --apply" in run.res.stderr and api.requests == []


# ---------------------------------------------------------------- approve


def test_approve_enrols_restarts_and_turns_key_expiry_off(box, api):
    env = admin_env(box, api)
    api.devices[LAPTOP_ID] = device(LAPTOP_ID, "laptop", "100.64.0.2", ["tag:ai-peer"])
    with OwnBridge(box) as own:
        assert box.deploy(*own.args).returncode == 0
        first = Phase(box, "approve", "--name", "laptop", "--token-sha256", HASH, extra_env=env)
        again = Phase(box, "approve", "--name", "laptop", "--token-sha256", HASH, extra_env=env)
    assert first.res.returncode == 0, first.text
    assert box.config()["auth"]["peers"]["laptop"] == HASH and restarted(first)
    key = api.made("POST", f"/device/{LAPTOP_ID}/key")
    assert len(key) == 1 and json.loads(key[0]["body"]) == {"keyExpiryDisabled": True}
    assert again.res.returncode == 0 and again.mutations == [] and not restarted(again), again.text
    assert len(api.made("POST", f"/device/{LAPTOP_ID}/key")) == 1
    assert "key expiry is off" in again.out and no_secret_in(first.text + again.text)


def test_approve_of_a_machine_not_on_the_tailnet_yet_still_enrols(box, api):
    env = admin_env(box, api)
    with OwnBridge(box) as own:
        assert box.deploy(*own.args).returncode == 0
        run = Phase(box, "approve", "--name", "laptop", "--token-sha256", HASH, extra_env=env)
    assert run.res.returncode == 0, run.text
    assert box.config()["auth"]["peers"]["laptop"] == HASH
    assert "no node 'laptop' tagged tag:ai-peer on the tailnet yet" in run.out


def test_approve_dry_run_runs_nothing_and_asks_nothing(box, api):
    env = admin_env(box, api)
    with OwnBridge(box) as own:
        assert box.deploy(*own.args).returncode == 0
        api.requests.clear()
        dry = Phase(box, "approve", "--name", "laptop", "--token-sha256", HASH, "--dry-run", extra_env=env)
    assert dry.res.returncode == 0, dry.text
    assert dry.calls == [] and dry.changed_nothing() and api.requests == []
    assert "would: enrol peer 'laptop'" in dry.out and "would: turn key expiry off" in dry.out


def test_approve_without_a_hash_needs_the_peer_enrolled(box, api):
    env = admin_env(box, api)
    with OwnBridge(box) as own:
        assert box.deploy(*own.args).returncode == 0
        run = Phase(box, "approve", "--name", "laptop", extra_env=env)
    assert run.res.returncode == 2 and "--token-sha256" in run.res.stderr


# ---------------------------------------------------------------- the Bridge's own node key


def test_bridge_turns_its_own_key_expiry_off_with_the_oauth_client(box, api):
    """Joined by a login and then tagged, the Bridge's node key still expires: deploy bridge turns that off."""
    env = admin_env(box, api)
    api.devices[NODE_ID]["tags"] = ["tag:bridge"]
    with OwnBridge(box) as own:
        dry = Phase(box, *own.args, "--dry-run", extra_env=env)
        first = Phase(box, *own.args, extra_env=env)
        again = Phase(box, *own.args, extra_env=env)
    assert dry.res.returncode == 0 and dry.calls == [] and "would: turn this machine's node key expiry off" in dry.out
    assert first.res.returncode == 0, first.text
    key = api.made("POST", f"/device/{NODE_ID}/key")
    assert len(key) == 1 and json.loads(key[0]["body"]) == {"keyExpiryDisabled": True}
    assert again.res.returncode == 0 and "already done: this machine's node key expiry is off" in again.out
    assert len(api.made("POST", f"/device/{NODE_ID}/key")) == 1 and no_secret_in(first.text + again.text)


def test_bridge_without_an_oauth_client_warns_about_an_expiring_key(box, api):
    box.set(ts_key_expiry="2027-04-09T23:00:00Z")
    with OwnBridge(box) as own:
        run = Phase(box, *own.args, extra_env={"TS_API_BASE": api.base})
    assert run.res.returncode == 0, run.text
    assert "WARNING: this machine's node key expires 2027-04-09T23:00:00Z" in run.out
    assert "tailnet-setup --apply" in run.out and api.requests == []


def test_status_flags_a_node_key_that_expires(box):
    plain = Phase(box, "status")
    box.set(ts_key_expiry="2027-04-09T23:00:00Z")
    flagged = Phase(box, "status")
    assert "node key: does not expire" in plain.out, plain.text
    assert "node key: EXPIRES 2027-04-09T23:00:00Z" in flagged.out and "deploy approve" in flagged.out


# ---------------------------------------------------------------- invite and join


def invite_code(name: str, bridge: str, port: int, key: str = AUTH_KEY_MINTED) -> str:
    """The documented format: aic1. and the base64url (no padding) of one JSON object."""
    raw = json.dumps({"v": 1, "name": name, "bridge": bridge, "port": port, "key": key}).encode()
    return "aic1." + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(code: str) -> dict:
    body = code.strip().removeprefix("aic1.")
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def test_invite_mints_a_single_use_non_ephemeral_key_into_an_owner_only_file(box, api):
    env = admin_env(box, api)
    out_file = box.tmp / "laptop.invite"
    with OwnBridge(box) as own:
        assert box.deploy(*own.args).returncode == 0
        api.requests.clear()
        dry = Phase(box, "invite", "--name", "laptop", "--out", str(out_file), "--dry-run", extra_env=env)
        assert dry.res.returncode == 0 and dry.calls == [] and api.requests == [] and not out_file.exists()
        run = Phase(box, "invite", "--name", "laptop", "--out", str(out_file), extra_env=env)
    assert run.res.returncode == 0, run.text
    assert api.auth_keys == [{"reusable": False, "ephemeral": False, "preauthorized": True, "tags": ["tag:ai-peer"]}]
    code = out_file.read_text(encoding="utf-8").strip()
    assert decode(code) == {"v": 1, "name": "laptop", "bridge": "127.0.0.1", "port": own.server.port,
                            "key": AUTH_KEY_MINTED}
    assert not leaks(AUTH_KEY_MINTED.rsplit("-", 1)[-1], run.text) and code not in run.text
    assert "deploy join --invite-file" in run.out and no_secret_in(run.text)
    if NATIVE == "linux":
        assert out_file.stat().st_mode & 0o077 == 0


def test_invite_without_out_shows_the_code_once(box, api):
    env = admin_env(box, api)
    run = Phase(box, "invite", "--name", "laptop", "--bridge", "100.64.0.1", "--ephemeral", extra_env=env)
    assert run.res.returncode == 0, run.text
    codes = [line.strip() for line in run.out.splitlines() if line.strip().startswith("aic1.")]
    assert len(codes) == 1 and decode(codes[0])["bridge"] == "100.64.0.1"
    assert api.auth_keys[0]["ephemeral"] is True and "shown once" in run.out


def joiner(box: Box) -> None:
    """A fresh machine: Tailscale installed but logged out."""
    box.set(ts_backend="NeedsLogin", ts_ip="")


def own_token(box: Box) -> Path:
    return box.home / ".config" / "ai-connect" / "own-peer.token"


def accepted_own(box: Box):
    def accepted():
        token = own_token(box)
        return {hashlib.sha256(token.read_text(encoding="utf-8").strip().encode()).hexdigest()} \
            if token.exists() else set()
    return accepted


def test_join_with_an_invite_joins_makes_its_token_and_prints_only_the_hash(box):
    joiner(box)
    approved = [False]
    accepted = accepted_own(box)
    server = FakeBridge(lambda: accepted() if approved[0] else set())
    invite = box.tmp / "laptop.invite"
    invite.write_text(invite_code("laptop", "127.0.0.1", server.port) + "\n", encoding="utf-8")
    try:
        dry = Phase(box, "join", "--invite-file", str(invite), "--dry-run")
        first = Phase(box, "join", "--invite-file", str(invite))
        approved[0] = True
        again = Phase(box, "join", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(server.port))
    finally:
        server.close()
    assert dry.res.returncode == 0 and dry.calls == [] and dry.changed_nothing(), dry.text
    assert first.res.returncode == 0, first.text
    up = [c for c in first.calls if c[:2] == ["tailscale", "up"]]
    assert len(up) == 1 and "--advertise-tags=tag:ai-peer" in up[0] and "--hostname=laptop" in up[0]
    assert "--accept-routes=false" in up[0] and "--exit-node=" in up[0] and "--accept-dns=false" in up[0]
    assert any(a.startswith("--auth-key=file:") for a in up[0])
    assert box.state()["up_key_sha256"] == hashlib.sha256(AUTH_KEY_MINTED.encode()).hexdigest()
    assert not invite.exists()  # single use: gone once it worked
    token = own_token(box).read_text(encoding="utf-8").strip()
    digest = hashlib.sha256(token.encode()).hexdigest()
    assert json.loads(next(line for line in first.out.splitlines() if line.startswith("{"))) == {
        "name": "laptop", "token_sha256": digest}
    assert f"deploy approve --name laptop --token-sha256 {digest}" in first.out
    assert box.config()["client"]["name"] == "laptop" and box.config()["client"]["token"] == token
    assert "PENDING" in first.out and "not approved yet" in first.out
    for secret in (token, AUTH_KEY_MINTED):
        assert not leaks(secret.rsplit("-", 1)[-1], first.text + again.text)
    if NATIVE == "linux":
        assert own_token(box).parent.stat().st_mode & 0o077 == 0 and box.config_file.stat().st_mode & 0o077 == 0
    assert again.res.returncode == 0 and again.mutations == [], again.text
    assert "Bridge accepts this token" in again.out and "PASS" in again.out and "PENDING" not in again.out
    assert "deploy test --bridge 127.0.0.1 --name laptop" in again.out


@pytest.mark.skipif(NATIVE != "linux", reason="sudo is the Linux path; Windows joins through vpn-up")
@pytest.mark.parametrize("root", [False, True], ids=["user", "root"])
def test_join_with_an_invite_on_linux_runs_tailscale_up_as_root(box, root):
    """tailscale up needs root (no operator is set on a fresh machine): through sudo for a user, the config and
    token stay the user's. The key reaches tailscale as a file, never on a command line."""
    joiner(box)
    env = {"AI_CONNECT_DEPLOY_ROOT": "1"} if root else {}
    server = FakeBridge(set)
    invite = box.tmp / "laptop.invite"
    invite.write_text(invite_code("laptop", "127.0.0.1", server.port), encoding="utf-8")
    try:
        run = Phase(box, "join", "--invite-file", str(invite), extra_env=env)
    finally:
        server.close()
    assert run.res.returncode == 0, run.text
    sudo_up = [c for c in run.calls if c[0] == "sudo" and "up" in c]
    assert (sudo_up == []) if root else (len(sudo_up) == 1 and any(a.startswith("--auth-key=file:") for a in
                                                                    sudo_up[0])), run.calls
    assert not any(AUTH_KEY_MINTED in a for c in run.calls for a in c)
    assert box.state()["up_key_sha256"] == hashlib.sha256(AUTH_KEY_MINTED.encode()).hexdigest()
    assert not list(own_token(box).parent.glob("*.join-key*"))  # the key's file is gone again


@pytest.mark.parametrize("how", [["--invite"], ["--invite-file", "missing.invite"]], ids=["prompt", "missing-file"])
def test_join_dry_run_reads_no_invite(box, how):
    """A first look asks for no secret and needs no file: the plan, with the invite's fields unknown."""
    run = Phase(box, "join", *how, "--dry-run")
    assert run.res.returncode == 0, run.text
    assert run.calls == [] and run.changed_nothing() and "would: join the tailnet" in run.out


def test_join_by_login_advertises_the_peer_tag(box):
    joiner(box)
    server = FakeBridge(set)
    try:
        run = Phase(box, "join", "--name", "legion", "--bridge", "127.0.0.1", "--port", str(server.port))
    finally:
        server.close()
    assert run.res.returncode == 0, run.text
    up = [c for c in run.calls if c[:2] == ["tailscale", "up"]]
    assert len(up) == 1 and "--advertise-tags=tag:ai-peer" in up[0] and "--hostname=legion" in up[0]
    assert not any(a.startswith("--auth-key") for a in up[0])
    assert "browser" in run.out and "approve" in run.out and "key expiry" in run.out


def test_join_with_hooks_installs_the_plugin_and_says_what_that_means(box):
    box.set(ts_backend="Running")
    server = FakeBridge(set)
    try:
        run = Phase(box, "join", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(server.port),
                    "--with-hooks")
    finally:
        server.close()
    assert run.res.returncode == 0, run.text
    assert box.state()["plugins"] == ["ai-connect@useful-claude-add-ons"] and "WARNING: --install-hooks" in run.out


@pytest.mark.parametrize("content", ["aic1.bm90LWpzb24tc2VjcmV0aXNo", "tskey-auth-kNOTANINVITE-secretish", ""])
def test_join_refuses_a_bad_invite_without_echoing_it(box, content):
    invite = box.tmp / "bad.invite"
    invite.write_text(content, encoding="utf-8")
    run = Phase(box, "join", "--invite-file", str(invite))
    assert run.res.returncode == 2, run.text
    assert "not an ai-connect invite" in run.res.stderr and (not content or content not in run.text)
    assert run.calls == [] and run.changed_nothing()


def test_join_without_an_invite_needs_name_and_bridge(box):
    run = Phase(box, "join", "--name", "laptop")
    assert run.res.returncode == 2 and "--bridge" in run.res.stderr and run.calls == []


def test_join_asks_for_an_invite_only_with_a_terminal(box):
    run = Phase(box, "join", "--invite")
    assert run.res.returncode == 2 and "AI_CONNECT_INVITE" in run.res.stderr and run.calls == []


# ---------------------------------------------------------------- remove


def test_remove_deletes_the_node_revokes_the_peer_and_restarts(box, api):
    env = admin_env(box, api)
    api.devices[LAPTOP_ID] = device(LAPTOP_ID, "laptop", "100.64.0.2", ["tag:ai-peer"], expiry_disabled=True)
    token_file = box.home / ".config" / "ai-connect" / "peer-tokens" / "laptop.token"
    with OwnBridge(box) as own:
        assert box.deploy(*own.args, "--peer", "laptop").returncode == 0
        assert token_file.is_file()
        dry = Phase(box, "remove", "--name", "laptop", "--dry-run", extra_env=env)
        first = Phase(box, "remove", "--name", "laptop", "--yes", extra_env=env)
        again = Phase(box, "remove", "--name", "laptop", "--yes", extra_env=env)
    assert dry.res.returncode == 0 and dry.calls == [] and dry.changed_nothing(), dry.text
    assert first.res.returncode == 0, first.text
    assert LAPTOP_ID not in api.devices and len(api.made("DELETE", f"/device/{LAPTOP_ID}")) == 1
    assert "laptop" not in box.config()["auth"]["peers"] and not token_file.exists() and restarted(first)
    # no node, no peer, the installed copy current, the Bridge running as it is
    assert again.res.returncode == 0 and again.mutations == [] and len(already(again.res)) == 4, again.text
    assert NODE_ID in api.devices  # the Bridge's own node is never touched


def test_remove_needs_yes_and_never_removes_the_bridge_itself(box, api):
    env = admin_env(box, api)
    with OwnBridge(box) as own:
        assert box.deploy(*own.args).returncode == 0
        api.requests.clear()
        unconfirmed = Phase(box, "remove", "--name", "laptop", extra_env=env)
        itself = Phase(box, "remove", "--name", "hub", "--yes", extra_env=env)
    assert unconfirmed.res.returncode == 2 and "--yes" in unconfirmed.res.stderr
    assert itself.res.returncode == 2 and "this Bridge's own peer" in itself.res.stderr
    assert api.writes() == [] and NODE_ID in api.devices


def test_remove_by_another_os_flavour(tmp_path, venv, api):
    """The Windows Bridge restarts its scheduled task; the Linux one its unit."""
    other = "windows" if NATIVE == "linux" else "linux"
    box = Box(tmp_path, venv, other)
    env = admin_env(box, api)
    with OwnBridge(box) as own:
        assert box.deploy(*own.args, "--peer", "laptop").returncode == 0
        run = Phase(box, "remove", "--name", "laptop", "--yes", extra_env=env)
    assert run.res.returncode == 0, run.text
    assert "laptop" not in box.config()["auth"]["peers"] and restarted(run)
    assert "no node 'laptop' tagged tag:ai-peer on the tailnet" in run.out
