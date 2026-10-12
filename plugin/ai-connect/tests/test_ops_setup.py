"""deploy/peer_setup.py and its setup.sh / setup.ps1 pair, against fakes only.

The fake machine is tests/deploy_box.py's: HOME, the systemd directory and every tool
(ufw, firewall-cmd, netsh, powershell, tailscale, sudo, claude) live in tmp_path, and a
loopback WebSocket server stands in for the Bridge. Nothing here reads or changes this
host's ai-connect config, firewall, Tailscale or Claude Code registration.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

from deploy_box import (BASH, DEPLOY_DIR, NATIVE, PLUGIN, PWSH, SUBNET, Box, OwnBridge, Phase, free_port, leaks,
                        output, owner_only)

SETUP = DEPLOY_DIR / "peer_setup.py"
OAUTH_SECRET = "tskey-client-kSETUP123-OAuthSecretThatMustNotLeak0123"
sys.path.insert(0, str(DEPLOY_DIR))
import firewall_state  # noqa: E402  pylint: disable=wrong-import-position,import-error


class SetupBox(Box):
    """A fake machine whose `deploy` is setup: Phase(box, ...) then runs peer_setup.py."""

    def deploy(self, *args, extra_env=None):
        return subprocess.run([sys.executable, str(SETUP), *args], capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, env=dict(self.env, **(extra_env or {})), timeout=180)

    def plain_deploy(self, *args, extra_env=None):
        return Box.deploy(self, *args, extra_env=extra_env)

    @property
    def config_dir(self):
        return self.home / ".config" / "ai-connect"


@pytest.fixture
def hub(tmp_path, venv):
    (tmp_path / "hub").mkdir()
    return SetupBox(tmp_path / "hub", venv, NATIVE)


@pytest.fixture
def laptop(tmp_path, venv):
    (tmp_path / "laptop").mkdir()
    return SetupBox(tmp_path / "laptop", venv, NATIVE)


def linux_box(tmp_path, venv, name="linux"):
    (tmp_path / name).mkdir()
    return SetupBox(tmp_path / name, venv, "linux")


def bridge_args(own: OwnBridge, *more: str) -> list[str]:
    return ["bridge", "--name", "hub", "--port", str(own.server.port), *more]


def tools_called(phase: Phase, name: str) -> list[list[str]]:
    """Calls to one tool, whether it ran directly or behind the fake sudo."""
    return [c for c in phase.calls if c[0] == name]


def summary(text: str, key: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip().startswith(f"{key}:")), "")


# ---------------------------------------------------------------- firewall_state, as functions


@pytest.mark.parametrize("status, conf, want", [
    ("Status: active\n\nTo  Action  From\n", None, firewall_state.ACTIVE),
    ("Status: inactive\n", "ENABLED=yes\n", firewall_state.INACTIVE),          # what runs now beats the file
    ("Status: active (verbose)\n", "ENABLED=no\n", firewall_state.ACTIVE),
    ("Status: Inaktiv\n", "# ufw\nENABLED=no\n", firewall_state.INACTIVE),     # translated: the file decides
    ("Status: Aktiv\n", "ENABLED=yes\nLOGLEVEL=low\n", firewall_state.ACTIVE),
    ("Status: Inaktiv\n", None, firewall_state.UNKNOWN),                       # unknown is not inactive
    ("", "LOGLEVEL=low\n", firewall_state.UNKNOWN),
    (None, "ENABLED=maybe\n", firewall_state.UNKNOWN),
])
def test_ufw_state_has_three_answers(status, conf, want):
    assert firewall_state.ufw_state(status, conf) == want


def test_ufw_added_reads_ufw_own_rule_lines():
    text = ("Added user rules (see 'ufw status' for running firewall):\n"
            "ufw allow 22/tcp\n"
            "ufw allow from 100.64.0.0/10 to any port 9999 proto tcp comment 'AI-Connect Bridge'\n"
            "ufw allow from 10.0.0.0/8 to any port 9999 proto tcp comment 'someone else'\n"
            "ufw allow from 100.64.0.0/10 to any port 8888 proto tcp\n")
    assert firewall_state.ufw_added(text, "AI-Connect Bridge") == [("9999", "100.64.0.0/10")]
    assert firewall_state.ufw_added("Added user rules:\n(None)\n", "AI-Connect Bridge") == []


@pytest.mark.parametrize("text, want", [
    ("profile:Domain=1\nprofile:Private=1\nprofile:Public=1\n", firewall_state.ACTIVE),
    ("profile:Domain=1\nprofile:Private=0\nprofile:Public=1\n", firewall_state.INACTIVE),
    ("profile:Domain=1\nprofile:Public=1\n", firewall_state.UNKNOWN),
    ("profile:Private=2\n", firewall_state.UNKNOWN),      # NotConfigured: neither on nor off
    ("", firewall_state.UNKNOWN),
])
def test_windows_state_is_the_private_profile(text, want):
    assert firewall_state.windows_state(text) == want


def test_no_note_only_when_the_firewall_is_on():
    for kind in ("ufw", "firewall-cmd", "netsh"):
        assert firewall_state.note(kind, firewall_state.ACTIVE, SUBNET, 9999) is None
        assert "NOT ENFORCED" in firewall_state.note(kind, firewall_state.INACTIVE, SUBNET, 9999)
        assert "NOT VERIFIED" in firewall_state.note(kind, firewall_state.UNKNOWN, SUBNET, 9999)


# ---------------------------------------------------------------- the firewall step


def test_active_ufw_reports_an_enforced_rule(tmp_path, venv):
    box = linux_box(tmp_path, venv)
    with OwnBridge(box) as own:
        first = Phase(box, *bridge_args(own, "--apply"))
    assert first.res.returncode == 0, first.text
    assert "NOT ENFORCED" not in first.text and "NOT VERIFIED" not in first.text
    assert summary(first.out, "firewall") == f"firewall: ufw is on and allows port {own.server.port} from {SUBNET} only"
    assert not any(c[:3] == ["ufw", "show", "added"] for c in first.calls)


def test_inactive_ufw_is_said_plainly_and_the_rule_is_stored_once(tmp_path, venv):
    box = linux_box(tmp_path, venv)
    box.set(ufw_active=False)
    with OwnBridge(box) as own:
        first = Phase(box, *bridge_args(own, "--apply"))
        second = Phase(box, *bridge_args(own, "--apply"))
    port = own.server.port
    for phase in (first, second):
        assert phase.res.returncode == 0, phase.text
        assert f"NOT ENFORCED: ufw is off, so the rule for port {port} from {SUBNET} filters nothing" in phase.out
        assert summary(phase.out, "firewall").startswith("firewall: NOT ENFORCED: ufw is off")
        # Nothing here turns a firewall on
        assert not [c for c in tools_called(phase, "ufw") if c[1] in ("enable", "--force", "reload", "default")]
    assert [c[1] for c in tools_called(first, "ufw") if c[1] == "allow"] == ["allow"]
    assert len(box.state()["ufw"]) == 1
    # The second run finds the stored rule (ufw status lists none while inactive) and adds nothing
    assert not [c for c in tools_called(second, "ufw") if c[1] == "allow"], second.calls
    assert f"already done: ufw rule for {SUBNET} on port {port} is stored" in second.out
    assert second.mutations == []


def test_inactive_ufw_keeps_one_rule_when_the_subnet_changes(tmp_path, venv):
    box = linux_box(tmp_path, venv)
    box.set(ufw_active=False)
    with OwnBridge(box) as own:
        assert Phase(box, *bridge_args(own, "--apply")).res.returncode == 0
        narrowed = Phase(box, *bridge_args(own, "--vpn-subnet", "100.100.0.0/16", "--apply"))
    assert narrowed.res.returncode == 0, narrowed.text
    assert [line.split()[2] for line in box.state()["ufw"]] == ["100.100.0.0/16"]


def test_translated_ufw_status_falls_back_to_ufw_conf(tmp_path, venv):
    box = linux_box(tmp_path, venv)
    box.set(ufw_status_text="Status: Inaktiv")
    with OwnBridge(box) as own:
        unknown = Phase(box, *bridge_args(own, "--apply"))
        (box.tmp / "ufw.conf").write_text("# /etc/ufw/ufw.conf\nENABLED=no\n", encoding="utf-8")
        inactive = Phase(box, *bridge_args(own, "--apply"))
    assert unknown.res.returncode == 0, unknown.text
    assert "NOT VERIFIED: could not tell whether ufw is on" in unknown.out and "NOT ENFORCED" not in unknown.out
    assert summary(unknown.out, "firewall").startswith("firewall: NOT VERIFIED")
    assert "NOT ENFORCED: ufw is off" in inactive.out


def test_plan_reads_ufw_conf_and_runs_no_tool(tmp_path, venv):
    box = linux_box(tmp_path, venv)
    (box.tmp / "ufw.conf").write_text("ENABLED=no\n", encoding="utf-8")
    plan = Phase(box, "bridge", "--name", "hub", "--peer", "laptop")
    assert plan.res.returncode == 0, plan.text
    assert "NOT ENFORCED: ufw is off" in plan.out
    assert plan.calls == [] and plan.changed_nothing()


def test_firewalld_that_is_not_running_gets_no_rule_and_says_so(tmp_path, venv):
    box = linux_box(tmp_path, venv)
    box.remove_tool("ufw")
    box.set(firewalld_state="stopped")
    with OwnBridge(box) as own:
        phase = Phase(box, *bridge_args(own, "--apply"))
    assert phase.res.returncode == 0, phase.text
    assert "NOT ENFORCED: firewalld is off" in phase.out
    assert not [c for c in tools_called(phase, "firewall-cmd") if c[1:] != ["--state"]], phase.calls
    assert "Health check" in phase.out and "accepted this machine's token" in phase.out


@pytest.mark.parametrize("state, marker", [({"fw_profiles": {"Domain": 1, "Private": 0, "Public": 1}}, "NOT ENFORCED"),
                                           ({"fw_profile_rc": 1}, "NOT VERIFIED"), ({}, None)])
def test_windows_firewall_profile_state_is_reported(tmp_path, venv, state, marker):
    (tmp_path / "win").mkdir()
    box = SetupBox(tmp_path / "win", venv, "windows")
    box.set(**state)
    with OwnBridge(box) as own:
        phase = Phase(box, *bridge_args(own, "--apply"))
    assert phase.res.returncode == 0, phase.text
    assert any(c[:4] == ["netsh", "advfirewall", "firewall", "add"] for c in phase.calls)
    if marker:
        assert f"{marker}:" in phase.out and summary(phase.out, "firewall").startswith(f"firewall: {marker}")
    else:
        assert "NOT ENFORCED" not in phase.out and "NOT VERIFIED" not in phase.out
        assert summary(phase.out, "firewall").startswith("firewall: Windows Firewall is on and allows port")


def test_status_and_uninstall_see_the_rule_of_an_inactive_ufw(tmp_path, venv):
    box = linux_box(tmp_path, venv)
    box.set(ufw_active=False)
    root = {"AI_CONNECT_DEPLOY_ROOT": "1"}  # status reads ufw only as root, and runs nothing through sudo
    with OwnBridge(box) as own:
        port = ["--port", str(own.server.port)]
        assert box.deploy(*bridge_args(own, "--apply"), extra_env=root).returncode == 0
        status = box.plain_deploy("status", extra_env=root)
        assert box.plain_deploy("uninstall", "--yes", *port, extra_env=root).returncode == 0
    assert f"rule present for {SUBNET} on port {own.server.port} - NOT ENFORCED: the firewall is off" in status.stdout
    assert box.state()["ufw"] == []


# ---------------------------------------------------------------- the plan


def test_plan_is_the_default_and_changes_nothing(hub, laptop, tmp_path):
    token_file = tmp_path / "laptop.token"
    plans = [Phase(hub, "bridge", "--name", "hub", "--peer", "laptop", "--enrol", "desk=" + "a" * 64,
                   "--register-mcp"),
             Phase(laptop, "peer", "--name", "laptop", "--bridge", "127.0.0.1", "--token-file", str(token_file),
                   "--register-mcp"),
             Phase(laptop, "peer", "--name", "laptop", "--bridge", "127.0.0.1")]
    for plan in plans:
        assert plan.res.returncode == 0, plan.text
        assert plan.calls == [], plan.calls          # no tool at all: no sudo, ufw, tailscale, claude
        assert plan.changed_nothing()
        assert "(plan: nothing is changed; --apply does it)" in plan.out and "would:" in plan.out
        assert "This was the plan: nothing was changed." in plan.out
        assert "tailnet policy: not checked (plan)" in plan.out
    assert not hub.config_file.exists() and not laptop.config_file.exists()
    assert "would: enrol peer 'desk' by its token hash ****aaaa" in plans[0].out   # no Bridge config to read yet
    assert "would: register MCP server 'ai-connect' (scope user" in plans[0].out


def test_bad_arguments_change_nothing(hub):
    cases = [(["bridge", "--peer", "bad name!", "--apply"], 2), (["bridge", "--enrol", "desk", "--apply"], 2),
             (["bridge", "--enrol", "desk=nothex", "--apply"], 2), (["peer", "--name", "laptop", "--apply"], 2),
             (["peer", "--name", "l", "--bridge", "127.0.0.1", "--token-file", "a", "--invite-file", "b"], 2),
             (["session", "--name", "bad name!", "--apply"], 2), (["bogus"], 2), ([], 2)]
    for args, code in cases:
        phase = Phase(hub, *args)
        assert phase.res.returncode == code, (args, phase.text)
        assert phase.changed_nothing() and phase.calls == [], args


# ---------------------------------------------------------------- bridge, then a peer with its token file


def test_bridge_then_peer_with_the_token_file(hub, laptop):
    with OwnBridge(hub) as own:
        port = str(own.server.port)
        first = Phase(hub, *bridge_args(own, "--peer", "laptop", "--apply"))
        second = Phase(hub, *bridge_args(own, "--peer", "laptop", "--apply"))
        token_file = hub.config_dir / "peer-tokens" / "laptop.token"
        token = token_file.read_text(encoding="utf-8").strip()
        peer = ["peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", port]
        joined = Phase(laptop, *peer, "--token-file", str(token_file), "--apply")
        again = Phase(laptop, *peer, "--apply")
    assert first.res.returncode == 0, first.text
    assert owner_only(token_file) and len(token) == 64
    assert hub.config()["auth"]["peers"]["laptop"] == hashlib.sha256(token.encode()).hexdigest()
    for phase in (first, second, joined, again):
        assert not leaks(token, phase.text)
        assert not tools_called(phase, "claude")      # no MCP server unless asked
    # What to run on the peer, for both operating systems, with the Bridge's address
    assert "deploy/setup.sh peer --name laptop --bridge 127.0.0.1 --token-file <file> --apply" in first.out
    assert "deploy\\setup.ps1 peer --name laptop --bridge 127.0.0.1 --token-file <file> --apply" in first.out
    assert second.res.returncode == 0 and second.mutations == [] and not second.files_changed, second.text

    assert joined.res.returncode == 0, joined.text
    assert laptop.config()["client"]["token"] == token and laptop.config()["client"]["name"] == "laptop"
    assert "accepts TCP connections: the tailnet policy lets this machine reach the Bridge" in joined.out
    assert not [c for c in joined.calls if c[0] in ("ufw", "firewall-cmd", "netsh")]   # a peer's firewall is untouched
    # Run again without the file: already set up, checked against the Bridge, nothing rewritten
    assert again.res.returncode == 0, again.text
    assert "Peer already set up with a token from the Bridge" in again.out
    assert again.mutations == [] and not again.files_changed
    assert laptop.config()["client"]["token"] == token


def test_register_mcp_is_off_by_default_and_user_scope_when_asked(hub, laptop):
    with OwnBridge(hub) as own:
        port = str(own.server.port)
        assert Phase(hub, *bridge_args(own, "--peer", "laptop", "--apply")).res.returncode == 0
        asked = Phase(hub, *bridge_args(own, "--register-mcp", "--apply"))
        rerun = Phase(hub, *bridge_args(own, "--register-mcp", "--apply"))
        token_file = hub.config_dir / "peer-tokens" / "laptop.token"
        peer = Phase(laptop, "peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", port, "--token-file",
                     str(token_file), "--register-mcp", "--scope", "project", "--apply")
    for phase, scope, box in ((asked, "user", hub), (peer, "project", laptop)):
        assert phase.res.returncode == 0, phase.text
        add = next(c for c in phase.calls if c[:3] == ["claude", "mcp", "add"])
        assert add[3:6] == ["-s", scope, "ai-connect"]
        assert add[-1] == str(box.app / "client" / "server.py")
        assert not any(c[:3] == ["claude", "plugin", "install"] for c in phase.calls)   # never the hooks
    assert rerun.res.returncode == 0 and not any(c[:3] == ["claude", "mcp", "add"] for c in rerun.calls)


# ---------------------------------------------------------------- a peer with its own token


def test_peer_with_its_own_token_and_enrol_on_the_bridge(hub, laptop):
    with OwnBridge(hub) as own:
        port = str(own.server.port)
        assert Phase(hub, *bridge_args(own, "--apply")).res.returncode == 0
        peer = ["peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", port, "--apply"]
        pending = Phase(laptop, *peer)
        enrolment = json.loads(next(line for line in pending.out.splitlines() if line.startswith("{")))
        enrol = Phase(hub, *bridge_args(own, "--enrol", f"laptop={enrolment['token_sha256']}", "--apply"))
        approved = Phase(laptop, *peer)
    token = (laptop.config_dir / "own-peer.token").read_text(encoding="utf-8").strip()
    assert pending.res.returncode == 0, pending.text
    assert enrolment == {"name": "laptop", "token_sha256": hashlib.sha256(token.encode()).hexdigest()}
    assert "PENDING" in pending.out and "bridge --enrol NAME=SHA256 --apply" in pending.out
    assert enrol.res.returncode == 0, enrol.text
    assert hub.config()["auth"]["peers"]["laptop"] == enrolment["token_sha256"]
    assert approved.res.returncode == 0 and "PASS" in approved.out and "PENDING" not in approved.out, approved.text
    for phase in (pending, enrol, approved):
        assert not leaks(token, phase.text)


# ---------------------------------------------------------------- the tailnet policy is never set here


def oauth_file(box) -> None:
    box.config_dir.mkdir(parents=True, exist_ok=True)
    (box.config_dir / "tailscale-oauth.json").write_text(
        json.dumps({"oauth_client_id": "kSETUPCLIENT", "oauth_client_secret": OAUTH_SECRET}), encoding="utf-8")


def test_tailnet_setup_outstanding_is_detected_and_never_run(hub):
    with OwnBridge(hub) as own:
        untagged = Phase(hub, *bridge_args(own, "--apply"))
        hub.set(ts_tags=["tag:bridge"])
        no_client = Phase(hub, *bridge_args(own, "--apply"))
        oauth_file(hub)
        done = Phase(hub, *bridge_args(own, "--apply"))
        hub.set(ts_tags=["tag:other"])
        tag_gone = Phase(hub, *bridge_args(own, "--apply"))
    for phase in (untagged, no_client, tag_gone):
        assert phase.res.returncode == 0, phase.text
        assert "OUTSTANDING: `deploy tailnet-setup --apply` does not look done" in phase.out
        assert "setup never runs it" in phase.out and "REPLACES the whole tailnet policy" in phase.out
        assert summary(phase.out, "tailnet policy") == "tailnet policy: outstanding"
    assert "this machine is not tagged tag:bridge" in untagged.out and "no OAuth client is stored" in untagged.out
    assert "not tagged" not in no_client.out and "no OAuth client is stored" in no_client.out
    assert "this machine is not tagged tag:bridge" in tag_gone.out and "no OAuth client" not in tag_gone.out
    assert "tailnet-setup has run here" in done.out and summary(done.out, "tailnet policy") == "tailnet policy: done"
    for phase in (untagged, no_client, done, tag_gone):
        assert not leaks(OAUTH_SECRET, phase.text)
        # Read-only: the only tailscale calls ask, none of them changes the node or the policy
        assert all(c[1] in ("status", "ip", "debug") for c in tools_called(phase, "tailscale")), phase.calls


def test_setup_has_no_way_to_run_tailnet_setup(hub):
    assert "tailnet_setup.main" not in SETUP.read_text(encoding="utf-8")
    for args in (["tailnet-setup"], ["tailnet-setup", "--apply"]):
        phase = Phase(hub, *args)
        assert phase.res.returncode == 2 and phase.changed_nothing() and phase.calls == []


def test_a_port_that_does_not_answer_points_at_the_policy(hub):
    probe = ("import sys; sys.path.insert(0, sys.argv[1]); import peer_setup; "
             "peer_setup.tsadmin.probe_tcp = lambda *a, **k: sys.argv[2]; "
             "print(peer_setup.acl_peer(peer_setup.Run(False, 1), '100.64.0.9', 9999))")
    answers = {}
    for result in ("ok", "refused", "timeout"):
        res = subprocess.run([sys.executable, "-c", probe, str(DEPLOY_DIR), result], capture_output=True, text=True,
                             check=False, stdin=subprocess.DEVNULL, env=hub.env, timeout=60)
        assert res.returncode == 0, output(res)
        answers[result] = res.stdout
    assert answers["ok"].splitlines()[-1] == "done" and "OUTSTANDING" not in answers["ok"]
    assert "nothing listens" in answers["refused"] and "OUTSTANDING" not in answers["refused"]
    assert answers["timeout"].splitlines()[-1] == "outstanding"
    assert "does not let tag:ai-peer reach tag:bridge:9999" in answers["timeout"]
    assert "setup never runs it" in answers["timeout"]


def test_peer_that_cannot_reach_the_bridge_fails_and_says_why(laptop, tmp_path):
    token_file = tmp_path / "laptop.token"
    token_file.write_text("ab" * 32 + "\n", encoding="utf-8")
    closed = str(free_port())
    phase = Phase(laptop, "peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", closed, "--token-file",
                  str(token_file), "--apply")
    assert phase.res.returncode == 1, phase.text
    assert "setup peer: Bridge check:" in phase.res.stderr
    assert "refused the connection" in phase.out and not leaks("ab" * 32, phase.text)


# ---------------------------------------------------------------- a second session on one machine


def token_the_client_sends(box, peer_name: str | None) -> str:
    """SHA-256 of the token config_loader.client_settings picks on that machine, in a process of its own."""
    code = ("import hashlib, sys; sys.path.insert(0, sys.argv[1]); "
            "from config_loader import client_settings, load_config; "
            "print(hashlib.sha256(client_settings(load_config()).token.encode()).hexdigest())")
    env = dict(box.env)
    env.pop("AI_CONNECT_PEER_NAME", None)
    if peer_name is not None:
        env["AI_CONNECT_PEER_NAME"] = peer_name
    res = subprocess.run([sys.executable, "-c", code, str(PLUGIN)], capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL, env=env, timeout=60)
    assert res.returncode == 0, output(res)
    return res.stdout.strip()


def test_second_session_on_the_bridge_machine(hub):
    restart = ["schtasks", "/Run"] if NATIVE == "windows" else ["systemctl", "restart", "ai-connect"]
    with OwnBridge(hub) as own:
        assert Phase(hub, *bridge_args(own, "--apply")).res.returncode == 0
        own_hash = hub.config()["auth"]["peers"]["hub"]
        plan = Phase(hub, "session", "--name", "second")
        first = Phase(hub, "session", "--name", "second", "--apply")
        second = Phase(hub, "session", "--name", "second", "--apply")
        same_name = Phase(hub, "session", "--name", "hub", "--apply")
    target = hub.config_dir / "session-tokens" / "second.token"
    assert plan.res.returncode == 0 and plan.changed_nothing() and plan.calls == [], plan.text
    assert "would: make a token for 'second'" in plan.out and "would: enrol peer 'second'" in plan.out
    assert first.res.returncode == 0, first.text
    token = target.read_text(encoding="utf-8").strip()
    digest = hashlib.sha256(token.encode()).hexdigest()
    assert len(token) == 64 and owner_only(target) and owner_only(target.parent)
    assert hub.config()["auth"]["peers"] == {"hub": own_hash, "second": digest}
    assert hub.config()["client"]["name"] == "hub"            # this machine's own peer is untouched
    assert any(restart in (c[-len(restart):], c[:len(restart)]) for c in first.calls), first.calls
    assert "AI_CONNECT_PEER_NAME=second claude" in first.out
    assert "$env:AI_CONNECT_PEER_NAME = 'second'; claude" in first.out
    for phase in (plan, first, second, same_name):
        assert not leaks(token, phase.text)
    assert second.res.returncode == 0 and second.mutations == [] and not second.files_changed, second.text
    assert same_name.res.returncode == 2 and "client.name" in same_name.res.stderr
    # What it is for: the client sends the second name's token under that name, and its own otherwise
    assert token_the_client_sends(hub, "second") == digest
    assert token_the_client_sends(hub, None) == own_hash
    assert token_the_client_sends(hub, "third") == own_hash   # a name with no token of its own
    assert token_the_client_sends(hub, "hub") == own_hash


def test_second_session_on_a_client_prints_only_the_hash(hub, laptop):
    with OwnBridge(hub) as own:
        port = str(own.server.port)
        assert Phase(hub, *bridge_args(own, "--peer", "laptop", "--apply")).res.returncode == 0
        token_file = hub.config_dir / "peer-tokens" / "laptop.token"
        assert Phase(laptop, "peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", port, "--token-file",
                     str(token_file), "--apply").res.returncode == 0
        session = Phase(laptop, "session", "--name", "laptop-2", "--apply")
        enrolment = json.loads(next(line for line in session.out.splitlines() if line.startswith("{")))
        enrol = Phase(hub, *bridge_args(own, "--enrol", f"laptop-2={enrolment['token_sha256']}", "--apply"))
    assert session.res.returncode == 0, session.text
    token = (laptop.config_dir / "session-tokens" / "laptop-2.token").read_text(encoding="utf-8").strip()
    assert enrolment == {"name": "laptop-2", "token_sha256": hashlib.sha256(token.encode()).hexdigest()}
    assert not leaks(token, session.text) and session.mutations == []   # no service, no firewall, no claude
    assert f"bridge --enrol laptop-2={enrolment['token_sha256']} --apply" in session.out
    assert enrol.res.returncode == 0 and hub.config()["auth"]["peers"]["laptop-2"] == enrolment["token_sha256"]
    assert token_the_client_sends(laptop, "laptop-2") == enrolment["token_sha256"]


def test_session_needs_a_machine_that_is_set_up(laptop):
    phase = Phase(laptop, "session", "--name", "second", "--apply")
    assert phase.res.returncode == 1 and "set this machine up first" in phase.res.stderr
    assert phase.changed_nothing()


def test_session_token_lookup_takes_only_a_plain_second_name(tmp_path):
    from config_loader import SESSION_TOKEN_DIR, session_token  # pylint: disable=import-outside-toplevel
    (tmp_path / "second.token").write_text("s" * 64 + "\n", encoding="utf-8")
    (tmp_path / "empty.token").write_text("\n", encoding="utf-8")
    (tmp_path.parent / "outside.token").write_text("o" * 64, encoding="utf-8")
    assert session_token("second", "hub", tmp_path) == "s" * 64
    assert session_token("second", "second", tmp_path) is None      # client.name keeps client.token
    assert session_token("empty", "hub", tmp_path) is None
    assert session_token("missing", "hub", tmp_path) is None
    for name in ("../outside", "..", "", None, "a/b", "second.token", "x" * 64):
        assert session_token(name, "hub", tmp_path) is None, name
    # setup writes where the client reads
    assert SESSION_TOKEN_DIR.parts[-3:] == (".config", "ai-connect", "session-tokens")
    assert 'SESSION_TOKEN_DIR = CONFIG_DIR / "session-tokens"' in SETUP.read_text(encoding="utf-8")


# ---------------------------------------------------------------- the setup.sh / setup.ps1 pair


def usage_lines(name: str) -> list[str]:
    """The leading comment's usage lines, with the script's own way of naming itself taken out."""
    lines = []
    for line in (DEPLOY_DIR / name).read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            if lines:
                break
            continue
        text = line.lstrip("#").strip()
        if re.match(r"(\./)?setup\.(sh|ps1) ", text):
            lines.append(re.sub(r"^(\./)?setup\.(sh|ps1) ", "setup ", text))
    return lines


def test_the_pair_documents_the_same_commands_in_the_same_order():
    sh, ps1 = usage_lines("setup.sh"), usage_lines("setup.ps1")
    assert sh == ps1 and [line.split()[1] for line in sh] == ["bridge", "peer", "session"]
    for name in ("setup.sh", "setup.ps1"):
        text = (DEPLOY_DIR / name).read_text(encoding="utf-8")
        assert "peer_setup.py" in text and "never runs `deploy tailnet-setup`" in text
        assert "| sh" not in text and "| bash" not in text and "iex" not in text.lower()
    for name in ("setup.sh", "peer_setup.py", "firewall_state.py"):
        assert b"\r" not in (DEPLOY_DIR / name).read_bytes(), name


def _sh(box, args):
    env = dict(box.env)
    if os.name == "nt":  # Git Bash needs its own coreutils (dirname) on PATH
        env["PATH"] = os.pathsep.join([r"C:\Program Files\Git\usr\bin", env["PATH"]])
    return subprocess.run([BASH, str(DEPLOY_DIR / "setup.sh"), *args], capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL, env=env, timeout=180)


def _ps1(box, args, tmp_path):
    return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(DEPLOY_DIR / "setup.ps1"), *args],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, timeout=180,
                          env=dict(box.env, XDG_CACHE_HOME=str(tmp_path / "xdg-cache")))


@pytest.mark.skipif(not BASH, reason="bash not found")
def test_setup_sh_runs_the_core(hub):
    res = subprocess.run([BASH, "-n", str(DEPLOY_DIR / "setup.sh")], capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL)
    assert res.returncode == 0, res.stderr
    direct, through = hub.deploy("bridge", "--name", "hub", "--peer", "laptop"), _sh(hub, ["bridge", "--name", "hub",
                                                                                           "--peer", "laptop"])
    assert (through.returncode, through.stdout, through.stderr) == (direct.returncode, direct.stdout, direct.stderr)
    assert hub.calls() == [] and "would:" in through.stdout


@pytest.mark.skipif(not BASH or not PWSH, reason="needs both bash and pwsh at known paths")
def test_sh_and_ps1_take_the_same_options_and_print_the_same_text(hub, tmp_path):
    cases = [["bridge", "--name", "hub", "--peer", "laptop", "--enrol", "desk=" + "b" * 64, "--register-mcp"],
             ["peer", "--name", "laptop", "--bridge", "127.0.0.1", "--register-mcp", "--scope", "user"],
             ["peer", "--name", "bad name!", "--bridge", "x", "--apply"], ["session", "--name", "second"],
             ["bridge", "--help"], ["peer", "--help"], ["session", "--help"], ["--help"]]
    for args in cases:
        sh, ps1 = _sh(hub, args), _ps1(hub, args, tmp_path)
        # A plan for a peer with no token yet masks a token it would make: four characters differ per run
        sh_out, ps1_out = (re.sub(r"token \*{4}[0-9a-f]{4}", "token ****", r.stdout) for r in (sh, ps1))
        assert sh_out.splitlines() == ps1_out.splitlines(), args
        assert (sh.returncode, sh.stderr) == (ps1.returncode, ps1.stderr), args
        assert sh.stdout or sh.stderr
    assert hub.mutations() == [] and not hub.config_file.exists()


@pytest.mark.skipif(not PWSH, reason="pwsh not found at an absolute path")
def test_setup_ps1_passes_the_repo_powershell_static_check(hub, tmp_path):
    # The fake machine's environment, like every other spawn here: with the caller's HOME, PowerShell
    # writes its startup directories into the real ~/.local/share/powershell
    checker = PLUGIN.parents[1] / "scripts" / "check-powershell.ps1"
    res = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(checker), "-Path",
                          str(DEPLOY_DIR / "setup.ps1")], capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL, env=dict(hub.env, XDG_CACHE_HOME=str(tmp_path / "xdg-cache")))
    assert res.returncode == 0, res.stdout + res.stderr
    assert (hub.home / ".local" / "share" / "powershell").is_dir() or os.name == "nt"   # it went to the fake HOME


def test_no_spawn_in_this_suite_inherits_the_callers_environment():
    """No process this suite starts is handed this process's environment, and with it the caller's HOME: each gets a fake
    machine's env. (`bash -n` passes none: it reads one file and runs nothing.)"""
    source = (PLUGIN / "tests" / "test_ops_setup.py").read_text(encoding="utf-8")
    assert "os." + "environ" not in source
