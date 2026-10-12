"""deploy list, approve and remove: the admin side of onboarding, against fakes only.

The Tailscale API is tests/fake_tailscale_api.py on a loopback port, reached with
the OAuth client tailnet-setup stores; the Bridge is FakeBridge; every system
tool is tests/fake_deploy_bin.py. No real Tailscale call is made.
"""
import hashlib
import json
from pathlib import Path

import pytest

from deploy_box import NATIVE, PEER_TOKEN, Box, OwnBridge, Phase, already, leaks
from fake_tailscale_api import CLIENT_ID, CLIENT_SECRET, NODE_ID, OAUTH_ACCESS_TOKEN, FakeTailscaleAPI, device

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
