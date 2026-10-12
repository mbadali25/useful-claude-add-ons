"""deploy tailnet-setup, the Tailscale install step and deploy test, against fakes only.

The Tailscale API is tests/fake_tailscale_api.py on a loopback port, the
installers and the tailscale CLI are tests/fake_deploy_bin.py, the credential
store is tests/fake_keyring, and `deploy test` talks to the real Bridge server
started on a loopback port in this process. No real Tailscale call is made.
"""
import asyncio
import hashlib
import json
import os
import threading
from pathlib import Path

import pytest
import yaml

from deploy_box import AUTH_KEY, NATIVE, PEER_TOKEN, PLUGIN, Box, FakeBridge, Phase, already, free_port, leaks
from fake_tailscale_api import (API_TOKEN, CLIENT_ID, CLIENT_SECRET, DEFAULT_POLICY, NODE_ID, OAUTH_ACCESS_TOKEN,
                                FakeTailscaleAPI)

TEMPLATE = (PLUGIN / "vpn" / "acl-template.hujson").read_text(encoding="utf-8")
WANTED = TEMPLATE.replace("admin@example.com", "autogroup:admin")
SECRETS = (API_TOKEN, CLIENT_SECRET, OAUTH_ACCESS_TOKEN)


# ---------------------------------------------------------------- tailnet-setup


@pytest.fixture
def api():
    server = FakeTailscaleAPI()
    yield server
    server.close()


def setup(box: Box, api: FakeTailscaleAPI, *args: str, **env: str) -> Phase:
    base = {"TS_API_BASE": api.base, "TS_API_TOKEN": API_TOKEN}
    confirm = ["--yes"] if "--apply" in args and "--bogus" not in args else []  # no terminal here to ask on
    return Phase(box, "tailnet-setup", *args, *confirm, extra_env={**base, **env})


def keyring_of(box: Box) -> dict:
    path = Path(box.env["FAKE_KEYRING_FILE"])
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def oauth_file(box: Box) -> Path:
    return Path(box.env["AI_CONNECT_OAUTH_FILE"])


def backups(box: Box) -> list[Path]:
    return sorted((box.home / ".config" / "ai-connect" / "acl-backups").glob("policy-*.hujson"))


def no_secret_in(text: str) -> bool:
    # The last segment is the secret part: a client secret starts with its (public) client ID
    return "tskey-api-k" not in text and not any(leaks(secret.rsplit("-", 1)[-1], text) for secret in SECRETS)


def test_preview_changes_nothing_and_shows_the_diff(box, api):
    run = setup(box, api)
    assert run.res.returncode == 0, run.text
    assert "preview" in run.out and run.out.count("would:") == 4, run.out  # policy, tag, key expiry, OAuth client
    assert api.writes() == [] and api.policy == DEFAULT_POLICY
    assert run.changed_nothing() and keyring_of(box) == {} and not oauth_file(box).exists()
    assert '+\t\t"tag:bridge":  ["autogroup:admin"],' in run.out  # the diff, with --admin filled in
    assert "REPLACES the whole tailnet policy" in run.out
    validate = api.made("POST", "/acl/validate")
    assert len(validate) == 1 and validate[0]["content_type"] == "application/hujson"
    assert validate[0]["body"] == WANTED and "admin@example.com" not in validate[0]["body"]
    assert no_secret_in(run.text)


def test_apply_backs_up_replaces_tags_and_stores_the_client(box, api):
    run = setup(box, api, "--apply")
    assert run.res.returncode == 0, run.text
    assert api.policy == WANTED
    saved = backups(box)
    assert len(saved) == 1 and saved[0].read_text(encoding="utf-8") == DEFAULT_POLICY
    written = [r["path"] for r in api.writes()]
    # The tag is refused until the policy defines it, so the policy goes first
    # Tagged after a login, the Bridge's node key would still expire: turned off with the tag
    assert written == ["/tailnet/-/acl", f"/device/{NODE_ID}/tags", f"/device/{NODE_ID}/key", "/tailnet/-/keys"]
    assert api.made("POST", "/tailnet/-/acl")[0]["if_match"] == '"v1"'
    assert api.devices[NODE_ID]["tags"] == ["tag:bridge"] and api.devices[NODE_ID]["keyExpiryDisabled"] is True
    assert json.loads(api.made("POST", "/keys")[0]["body"]) == {
        "keyType": "client", "scopes": ["auth_keys", "devices:core"], "tags": ["tag:ai-peer"],
        "description": "ai-connect mint-key and revoke"}
    assert keyring_of(box) == {"ai-connect-tailscale/oauth_client_id": CLIENT_ID,
                               "ai-connect-tailscale/oauth_client_secret": CLIENT_SECRET}
    assert not oauth_file(box).exists()
    assert f"OAuth client {CLIENT_ID} stored in the OS credential store" in run.out
    assert no_secret_in(run.text)
    assert all(r["authorization"] == f"Bearer {API_TOKEN}" for r in api.requests if r["path"] != "/oauth/token")


def test_apply_again_is_idempotent(box, api):
    assert setup(box, api, "--apply").res.returncode == 0
    api.requests.clear()
    again = setup(box, api, "--apply")
    assert again.res.returncode == 0, again.text
    assert api.writes() == []
    assert again.changed_nothing() and len(backups(box)) == 1
    # installed, on the tailnet, policy, tag, key expiry, OAuth client
    assert len(already(again.res)) == 7 and "would:" not in again.out, again.out  # + Tailscale settings pinned
    preview = setup(box, api)
    assert preview.res.returncode == 0 and "would:" not in preview.out and api.writes() == []
    assert no_secret_in(again.text + preview.text)


def test_a_policy_tailscale_refuses_is_never_applied(box, api):
    api.validate_message = "test(s) failed"
    run = setup(box, api, "--apply")
    assert run.res.returncode == 1
    assert "Tailscale refuses the policy file: test(s) failed" in run.res.stderr
    assert api.writes() == [] and api.policy == DEFAULT_POLICY and backups(box) == []


def test_without_an_api_token_nothing_is_called(box, api):
    run = Phase(box, "tailnet-setup", "--apply", "--yes", extra_env={"TS_API_BASE": api.base})
    assert run.res.returncode == 2
    assert "TS_API_TOKEN" in run.res.stderr
    assert api.requests == [] and run.changed_nothing()


def test_apply_without_a_terminal_needs_yes(box, api):
    run = Phase(box, "tailnet-setup", "--apply", extra_env={"TS_API_BASE": api.base, "TS_API_TOKEN": API_TOKEN})
    assert run.res.returncode == 2 and "pass --yes" in run.res.stderr
    assert api.requests == [] and run.changed_nothing()
    assert Phase(box, "tailnet-setup", "--yes", extra_env={"TS_API_TOKEN": API_TOKEN}).res.returncode == 2


def test_the_api_token_can_come_from_the_credential_store(box, api):
    Path(box.env["FAKE_KEYRING_FILE"]).write_text(json.dumps({"ai-connect-tailscale/api_token": API_TOKEN}),
                                                  encoding="utf-8")
    run = Phase(box, "tailnet-setup", "--apply", "--yes", extra_env={"TS_API_BASE": api.base})
    assert run.res.returncode == 0, run.text
    assert api.policy == WANTED and no_secret_in(run.text)


def test_json_output_is_one_object_with_no_secret(box, api):
    preview = setup(box, api, "--json")
    applied = setup(box, api, "--apply", "--json")
    for run in (preview, applied):
        assert run.res.returncode == 0, run.text
        assert no_secret_in(run.text) and "[1/5]" in run.res.stderr and "[1/5]" not in run.out
    doc = json.loads(preview.out)
    assert doc["ok"] is True and doc["applied"] is False and doc["oauth_client_id"] is None
    assert [s["step"] for s in doc["steps"]][1:3] == ["Policy file", "Tailnet policy"]
    assert [res["status"] for s in doc["steps"] for res in s["results"]].count("would") == 4  # + key expiry
    doc = json.loads(applied.out)
    assert doc["applied"] is True and doc["oauth_client_id"] == CLIENT_ID
    assert doc["oauth_client_stored_in"] == "credential store"
    statuses = [res["status"] for s in doc["steps"] for res in s["results"]]
    assert statuses.count("done") == 4 and "backup" in statuses and "would" not in statuses  # + key expiry
    api.validate_message = "test(s) failed"
    failed = setup(box, api, "--apply", "--json", "--acl", str(PLUGIN / "vpn" / "acl-template.hujson"))
    doc = json.loads(failed.out)
    assert failed.res.returncode == 1 and doc["ok"] is False and "refuses the policy file" in doc["error"]


def test_a_refused_api_token_stops_before_any_change(box, api):
    wrong = "tskey-api-kWRONG-ThisTokenIsNotTheAdminsToken000000"
    run = setup(box, api, "--apply", TS_API_TOKEN=wrong)
    assert run.res.returncode == 1
    assert "HTTP 401" in run.res.stderr and "API access token" in run.res.stderr
    assert api.writes() == [] and not leaks(wrong, run.text)


def test_policy_changed_meanwhile_is_not_overwritten(box, api):
    api.race = True
    run = setup(box, api, "--apply")
    assert run.res.returncode == 1
    assert "HTTP 412" in run.res.stderr and "nothing was applied" in run.res.stderr
    assert api.policy == DEFAULT_POLICY and api.devices[NODE_ID]["tags"] == []
    assert len(backups(box)) == 1  # the backup is taken before the write is tried


def test_api_refusing_the_client_prints_the_console_steps(box, api):
    api.keys_status = 403
    run = setup(box, api, "--apply")
    assert run.res.returncode == 1
    assert "https://login.tailscale.com/admin/settings/oauth" in run.out
    assert "Auth Keys (write)" in run.out and "Devices > Core (write)" in run.out
    assert "TS_OAUTH_CLIENT_ID" in run.res.stderr
    assert api.policy == WANTED and api.devices[NODE_ID]["tags"] == ["tag:bridge"]  # the earlier steps stand
    assert keyring_of(box) == {} and not oauth_file(box).exists()
    # The admin made the client in the console and hands it over through the environment
    api.clients["kMANUAL11CNTRL"] = CLIENT_SECRET
    again = setup(box, api, "--apply", TS_OAUTH_CLIENT_ID="kMANUAL11CNTRL", TS_OAUTH_CLIENT_SECRET=CLIENT_SECRET)
    assert again.res.returncode == 0, again.text
    assert keyring_of(box)["ai-connect-tailscale/oauth_client_id"] == "kMANUAL11CNTRL"
    assert keyring_of(box)["ai-connect-tailscale/oauth_client_secret"] == CLIENT_SECRET
    assert no_secret_in(run.text + again.text)


def test_a_client_tailscale_refuses_is_not_stored(box, api):
    api.keys_status = 403
    run = setup(box, api, "--apply", TS_OAUTH_CLIENT_ID="kNOPE", TS_OAUTH_CLIENT_SECRET=CLIENT_SECRET)
    assert run.res.returncode == 1
    assert "refused OAuth client kNOPE" in run.res.stderr and "nothing was stored" in run.res.stderr
    assert keyring_of(box) == {} and not oauth_file(box).exists()


@pytest.mark.parametrize("mode", ["absent", "broken"])
def test_without_a_credential_store_the_client_goes_to_an_owner_only_file(box, api, mode):
    run = setup(box, api, "--apply", FAKE_KEYRING_MODE=mode)
    assert run.res.returncode == 0, run.text
    saved = json.loads(oauth_file(box).read_text(encoding="utf-8"))
    assert saved == {"oauth_client_id": CLIENT_ID, "oauth_client_secret": CLIENT_SECRET}
    assert "owner-only file" in run.out and "pip install keyring" in run.out
    if os.name != "nt":
        assert oauth_file(box).stat().st_mode & 0o077 == 0
    assert keyring_of(box) == {} and no_secret_in(run.text)
    # Still no store: the file is what mint-key reads, and a rerun leaves it alone
    same = setup(box, api, "--apply", FAKE_KEYRING_MODE=mode)
    assert same.res.returncode == 0 and len(api.made("POST", "/keys")) == 1
    assert f"already done: OAuth client {CLIENT_ID}" in same.out
    # keyring installed since: the rerun moves the client out of the file
    moved = setup(box, api, "--apply")
    assert moved.res.returncode == 0, moved.text
    assert keyring_of(box)["ai-connect-tailscale/oauth_client_secret"] == CLIENT_SECRET
    assert not oauth_file(box).exists() and len(api.made("POST", "/keys")) == 1
    assert no_secret_in(same.text + moved.text)


def test_a_stored_client_tailscale_no_longer_accepts_is_reported(box, api):
    Path(box.env["FAKE_KEYRING_FILE"]).write_text(json.dumps({
        "ai-connect-tailscale/oauth_client_id": "kOLD", "ai-connect-tailscale/oauth_client_secret": CLIENT_SECRET}),
        encoding="utf-8")
    run = setup(box, api, "--apply")
    assert run.res.returncode == 1
    assert "stored OAuth client kOLD" in run.res.stderr and "was refused" in run.res.stderr
    assert api.made("POST", "/keys") == [] and no_secret_in(run.text)


def test_device_names_a_bridge_that_is_another_machine(box, api):
    box.remove_tool("tailscale")
    run = setup(box, api, "--apply", "--device", "hub")
    assert run.res.returncode == 0, run.text
    assert api.devices[NODE_ID]["tags"] == ["tag:bridge"]
    assert not any(c[0] in ("curl", "sh", "winget", "msiexec", "brew", "tailscale") for c in run.calls)
    assert setup(box, api, "--apply", "--device", "nobody").res.returncode == 1


def test_a_custom_policy_file_and_admin(box, api, tmp_path):
    acl = tmp_path / "policy.hujson"
    acl.write_text(TEMPLATE, encoding="utf-8")
    run = setup(box, api, "--apply", "--acl", str(acl), "--admin", "matthew@example.org")
    assert run.res.returncode == 0, run.text
    assert '"tag:bridge":  ["matthew@example.org"]' in api.policy and "admin@example.com" not in api.policy


def test_preview_with_a_stored_client_issues_no_token(box, api):
    assert setup(box, api, "--apply").res.returncode == 0
    api.requests.clear()
    preview = setup(box, api)
    assert preview.res.returncode == 0, preview.text
    assert api.made("POST", "/oauth/token") == [] and api.writes() == []
    assert f"OAuth client {CLIENT_ID} is stored" in preview.out and "does not check it" in preview.out


def test_a_policy_served_without_an_etag_is_not_replaced(box, api):
    api.send_etag = False
    run = setup(box, api, "--apply")
    assert run.res.returncode == 1
    assert "no ETag" in run.res.stderr and "nothing was applied" in run.res.stderr
    assert api.writes() == [] and api.policy == DEFAULT_POLICY


@pytest.mark.parametrize("body", ["<html>gateway error</html>", '{"unexpected": true}', "[]"])
def test_a_validation_answer_that_is_neither_pass_nor_refusal_stops(box, api, body):
    api.validate_raw = body
    run = setup(box, api, "--apply")
    assert run.res.returncode == 1
    assert "neither a pass nor a refusal" in run.res.stderr
    assert api.writes() == [] and api.policy == DEFAULT_POLICY


def test_a_locked_credential_store_never_leads_to_a_second_client(box, api):
    run = setup(box, api, "--apply", FAKE_KEYRING_MODE="locked")
    assert run.res.returncode == 1
    assert "could not be read (KeyringLocked)" in run.res.stderr
    assert api.made("POST", "/keys") == [] and not oauth_file(box).exists()


@pytest.mark.parametrize("content", ["{not json", '{"oauth_client_id": "kHALF"}', "[]"])
def test_an_unreadable_oauth_file_never_leads_to_a_second_client(box, api, content):
    oauth_file(box).parent.mkdir(parents=True)
    oauth_file(box).write_text(content, encoding="utf-8")
    run = setup(box, api, "--apply", FAKE_KEYRING_MODE="absent")
    assert run.res.returncode == 1
    assert "holds no OAuth client that can be read" in run.res.stderr
    assert api.made("POST", "/keys") == [] and oauth_file(box).read_text(encoding="utf-8") == content


def test_a_client_that_cannot_be_stored_is_deleted_again(box, api, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a directory", encoding="utf-8")
    run = setup(box, api, "--apply", FAKE_KEYRING_MODE="absent", AI_CONNECT_OAUTH_FILE=str(blocker / "oauth.json"))
    assert run.res.returncode == 1
    assert f"OAuth client {CLIENT_ID} was created but could not be stored" in run.res.stderr
    assert "it was deleted again" in run.res.stderr
    assert api.clients == {} and len(api.made("DELETE", f"/keys/{CLIENT_ID}")) == 1
    assert no_secret_in(run.text)

def test_half_a_stored_client_never_leads_to_a_second_one(box, api):
    Path(box.env["FAKE_KEYRING_FILE"]).write_text(json.dumps({"ai-connect-tailscale/oauth_client_id": "kHALF"}),
                                                  encoding="utf-8")
    run = setup(box, api, "--apply")
    assert run.res.returncode == 1 and "holds only half of an OAuth client" in run.res.stderr
    assert api.made("POST", "/keys") == []


def test_a_half_written_store_is_emptied_and_the_file_holds_the_client(box, api):
    run = setup(box, api, "--apply", FAKE_KEYRING_MODE="half")
    assert run.res.returncode == 0, run.text
    assert keyring_of(box) == {}  # not {new ID, no secret}: that would be read before the file
    assert json.loads(oauth_file(box).read_text(encoding="utf-8"))["oauth_client_secret"] == CLIENT_SECRET
    again = setup(box, api, "--apply", FAKE_KEYRING_MODE="half")
    assert again.res.returncode == 0 and len(api.made("POST", "/keys")) == 1, again.text


def test_json_stays_one_object_when_an_installer_writes_to_stdout(box, api):
    env = missing(box, "windows", NATIVE)
    run = setup(box, api, "--apply", "--json", **env)
    assert run.res.returncode == 0, run.text
    assert json.loads(run.out)["applied"] is True
    assert "fake installer: unpacking" in run.res.stderr and "fake installer" not in run.out

@pytest.mark.parametrize("args", [["--admin", "not an admin"], ["--admin", 'x@y.z", "*'], ["--tailnet", "a/b"],
                                  ["--acl", "no-such-file.hujson"], ["--apply", "--bogus"]])
def test_tailnet_setup_bad_arguments(box, api, args):
    run = setup(box, api, *args)
    assert run.res.returncode == 2, run.text
    assert api.requests == [] and run.changed_nothing()


def test_out_redacts_a_secret_that_reaches_it(monkeypatch, capsys):
    """The backstop under every step: whatever text is printed, a known secret in it is not."""
    monkeypatch.syspath_prepend(str(PLUGIN / "deploy"))
    import deploy_core  # pylint: disable=import-outside-toplevel,import-error
    deploy_core.tsadmin.remember_secret("peer-token-that-must-not-show")
    deploy_core.out("stderr of a tool said: peer-token-that-must-not-show and tskey-auth-kABC-DEFsecret")
    shown = capsys.readouterr().out
    assert "peer-token-that-must-not-show" not in shown and "DEFsecret" not in shown
    assert "<redacted>" in shown and "tskey-<redacted>" in shown

# ---------------------------------------------------------------- installing Tailscale


def missing(box: Box, platform: str, target: str, **state) -> dict:
    """A machine without Tailscale; returns the environment that selects its installer."""
    box.remove_tool("tailscale")
    box.set(ts_backend="NoState", ts_ip="", **state)
    return {"AI_CONNECT_DEPLOY_PLATFORM": platform, "AI_CONNECT_DEPLOY_OS": target}


def installer_calls(phase: Phase) -> list[list[str]]:
    return [c for c in phase.calls if c[0] in ("curl", "sh", "install", "apt-get", "winget", "msiexec", "brew")]


@pytest.mark.parametrize("platform", ["linux", "windows"])
def test_bridge_installs_tailscale_and_logs_in(box, platform):
    env = missing(box, platform, platform)
    def accepted():
        return set(box.config()["auth"]["peers"].values()) if box.config_file.exists() else set()
    server = FakeBridge(accepted)
    args = ["bridge", "--name", "hub", "--port", str(server.port)]
    try:
        dry = Phase(box, *args, "--dry-run", extra_env=env)
        first = Phase(box, *args, extra_env=env)
        second = Phase(box, *args, extra_env=env)
    finally:
        server.close()
    assert dry.res.returncode == 0, dry.text
    assert "would: install Tailscale" in dry.out and dry.changed_nothing() and installer_calls(dry) == []
    assert first.res.returncode == 0, first.text
    calls = installer_calls(first)
    if platform == "linux":
        assert calls[0][:3] == ["curl", "-fsSL", "https://tailscale.com/install.sh"] and calls[1][0] == "sh"
        assert "sudo may ask for your password" in first.out
    else:
        assert calls == [["winget", "install", "--id", "Tailscale.Tailscale", "-e", "--accept-source-agreements",
                          "--accept-package-agreements"]]
        assert "UAC" in first.out
    assert "browser" in first.out  # the login is announced before the terminal is handed over
    assert [c for c in first.calls if c[-2:] == ["tailscale", "up"] or c[:2] == ["tailscale", "up"]]
    assert box.config()["server"]["host"] == "127.0.0.1"
    assert second.res.returncode == 0 and installer_calls(second) == [], second.text
    assert "already done: Tailscale installed" in second.out
    assert "already done: this machine is on the tailnet" in second.out


def test_windows_without_winget_uses_the_msi(box):
    env = missing(box, "windows", "windows")
    box.remove_tool("winget")
    run = Phase(box, "tailnet-setup", extra_env={**env, "TS_API_TOKEN": API_TOKEN, "TS_API_BASE": "http://127.0.0.1:9"})
    assert "would: install Tailscale" in run.out  # the preview gets as far as the unreachable API
    server = FakeBridge(set)
    try:
        first = Phase(box, "bridge", "--name", "hub", "--port", str(server.port), extra_env=env)
    finally:
        server.close()
    calls = installer_calls(first)
    assert calls[0][0] == "curl" and "https://pkgs.tailscale.com/stable/tailscale-setup-latest-" in calls[0][2]
    assert calls[1][:2] == ["msiexec", "/i"] and "the Tailscale MSI" in first.out


@pytest.mark.parametrize("cask", ["tailscale-app", "tailscale"])
def test_peer_on_macos_installs_with_homebrew(box, tmp_path, cask):
    env = missing(box, "darwin", NATIVE, brew_cask=cask)
    token_file = tmp_path / "laptop.token"
    token_file.write_text(PEER_TOKEN, encoding="utf-8")
    server = FakeBridge(lambda: {hashlib.sha256(PEER_TOKEN.encode()).hexdigest()})
    try:
        run = Phase(box, "peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(server.port),
                    "--token-file", str(token_file), extra_env={**env, "TS_AUTHKEY": AUTH_KEY})
    finally:
        server.close()
    assert run.res.returncode == 0, run.text
    assert installer_calls(run)[-1] == ["brew", "install", "--cask", cask]
    assert box.state()["ts_backend"] == "Running" and not leaks(AUTH_KEY, run.text)


def ubuntu(box: Box, codename: str = "noble") -> None:
    Path(box.env["AI_CONNECT_OS_RELEASE"]).write_text(
        f'NAME="Ubuntu"\nID=ubuntu\nVERSION_CODENAME={codename}\n', encoding="utf-8")


def test_ubuntu_as_root_installs_from_the_signed_apt_repository_without_sudo(box):
    env = {**missing(box, "linux", "linux"), "AI_CONNECT_DEPLOY_ROOT": "1"}
    ubuntu(box)
    server = FakeBridge(set)
    args = ["bridge", "--name", "hub", "--port", str(server.port)]
    try:
        dry = Phase(box, *args, "--dry-run", extra_env=env)
        first = Phase(box, *args, extra_env=env)
    finally:
        server.close()
    planned = [line.strip() for line in dry.out.splitlines() if line.strip().startswith("$ ")]
    assert dry.changed_nothing() and installer_calls(dry) == []
    # The dry run names every command, the keyring the repository is pinned to, and the login
    assert planned[0].startswith("$ curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg -o ")
    assert planned[1].startswith("$ curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list")
    assert planned[2].startswith("$ install ")
    assert planned[2].endswith(" /usr/share/keyrings/tailscale-archive-keyring.gpg")
    assert planned[3].endswith(" /etc/apt/sources.list.d/tailscale.list")
    assert planned[4].startswith("$ apt-get update -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/tailscale.list")
    assert planned[5] == "$ apt-get install -y tailscale"
    assert "$ tailscale up --accept-routes=false --exit-node= --accept-dns=false" in planned and "signed-by" in dry.out
    assert not any("sudo" in line for line in planned)
    ran = installer_calls(first)
    assert [c[0] for c in ran] == ["curl", "curl", "install", "install", "apt-get", "apt-get"], ran
    assert ran[5] == ["apt-get", "install", "-y", "tailscale"]
    assert not any(c[0] == "sudo" for c in first.calls), "root must not need sudo"
    assert ["tailscale", "up", "--accept-routes=false", "--exit-node=", "--accept-dns=false"] in first.calls


def test_a_release_the_apt_repository_lacks_falls_back_to_the_install_script(box):
    env = missing(box, "linux", "linux", curl_404="/resolute.")
    ubuntu(box, "resolute")
    server = FakeBridge(set)
    try:
        first = Phase(box, "bridge", "--name", "hub", "--port", str(server.port), extra_env=env)
    finally:
        server.close()
    ran = installer_calls(first)
    assert ran[0][2] == "https://pkgs.tailscale.com/stable/ubuntu/resolute.noarmor.gpg"
    assert [c[0] for c in ran[1:]] == ["curl", "sh"] and ran[1][2] == "https://tailscale.com/install.sh"
    assert "if the apt repository does not carry this release, with Tailscale's install script" in first.out
    assert "Tailscale's apt repository does not carry ubuntu resolute" in first.out
    assert box.state()["ts_backend"] == "Running"


@pytest.mark.parametrize("state", [{"apt_rc": 100}, {"curl_rc": 6}], ids=["dpkg-lock", "no-network"])
def test_an_apt_failure_that_is_not_a_missing_release_stops_without_the_install_script(box, state):
    """A held dpkg lock or no network is not fixed by piping a script from the internet into a root shell."""
    env = missing(box, "linux", "linux", **state)
    ubuntu(box)
    run = Phase(box, "bridge", "--name", "hub", "--port", "9", extra_env=env)
    assert run.res.returncode == 1, run.text
    ran = installer_calls(run)
    assert not any(c[0] == "sh" or "https://tailscale.com/install.sh" in c for c in ran), ran
    assert "does not fall back to Tailscale's install script" in run.text
    assert box.state()["ts_backend"] == "NoState"


def test_accept_dns_is_off_unless_asked_for(box, tmp_path):
    box.set(ts_backend="Stopped", ts_ip="")
    token_file = tmp_path / "laptop.token"
    token_file.write_text(PEER_TOKEN, encoding="utf-8")
    server = FakeBridge(lambda: {hashlib.sha256(PEER_TOKEN.encode()).hexdigest()})
    args = ["peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(server.port), "--token-file",
            str(token_file)]
    try:
        dry = Phase(box, *args, "--dry-run", extra_env={"TS_AUTHKEY": AUTH_KEY})
        default = Phase(box, *args, extra_env={"TS_AUTHKEY": AUTH_KEY})
        box.set(ts_backend="Stopped", ts_ip="")
        asked = Phase(box, *args, "--accept-dns", extra_env={"TS_AUTHKEY": AUTH_KEY})
    finally:
        server.close()
    assert "--accept-dns=false" in dry.out and not leaks(AUTH_KEY, dry.text)
    up = [c for c in default.calls if c[:2] == ["tailscale", "up"]]
    assert len(up) == 1 and "--accept-dns=false" in up[0]
    up = [c for c in asked.calls if c[:2] == ["tailscale", "up"]]
    assert len(up) == 1 and "--accept-dns=true" in up[0]


def test_no_install_tailscale_keeps_exit_3(box):
    env = missing(box, "linux", "linux")
    run = Phase(box, "bridge", "--name", "hub", "--no-install-tailscale", extra_env=env)
    assert run.res.returncode == 3, run.text
    assert "tailscale is not installed" in run.res.stderr and "install.sh" in run.res.stderr
    # Exit 3 means nothing was done: the installed copy is made in the service step, after Tailscale
    assert run.changed_nothing() and installer_calls(run) == []


def test_a_missing_installer_tool_is_exit_3_with_the_hint(box, tmp_path):
    env = missing(box, "darwin", NATIVE)
    box.remove_tool("brew")
    token_file = tmp_path / "laptop.token"
    token_file.write_text(PEER_TOKEN, encoding="utf-8")
    run = Phase(box, "peer", "--name", "laptop", "--bridge", "127.0.0.1", "--token-file", str(token_file),
                extra_env={**env, "TS_AUTHKEY": AUTH_KEY})
    assert run.res.returncode == 3, run.text
    assert "brew not found on PATH" in run.res.stderr and "brew install --cask tailscale" in run.res.stderr
    assert installer_calls(run) == [] and not box.config_file.exists()


def test_a_failed_install_stops_the_deploy(box):
    env = missing(box, "linux", "linux", install_rc=7)
    run = Phase(box, "bridge", "--name", "hub", extra_env=env)
    assert run.res.returncode == 1
    assert "install script failed at `sh " in run.res.stderr and "(exit 7)" in run.res.stderr
    assert not box.config_file.exists()


def test_a_join_that_did_not_join_is_not_reported_as_done(box, tmp_path):
    box.set(ts_backend="Stopped", ts_ip="", after_up="NeedsLogin")
    token_file = tmp_path / "laptop.token"
    token_file.write_text(PEER_TOKEN, encoding="utf-8")
    server = FakeBridge(lambda: {hashlib.sha256(PEER_TOKEN.encode()).hexdigest()})
    try:
        run = Phase(box, "peer", "--name", "laptop", "--bridge", "127.0.0.1", "--port", str(server.port),
                    "--token-file", str(token_file), extra_env={"TS_AUTHKEY": AUTH_KEY})
    finally:
        server.close()
    # The Bridge is reachable on loopback all the same: only Tailscale itself can say whether it joined
    assert run.res.returncode == 1 and "not on the tailnet (state: NeedsLogin)" in run.res.stderr
    assert not box.config_file.exists()

# ---------------------------------------------------------------- deploy test


class RealBridge:
    """The plugin's own Bridge server on a loopback port, knowing the given peers."""

    def __init__(self, tmp_path: Path, peers: dict):
        from config_loader import server_settings  # pylint: disable=import-outside-toplevel,import-error
        from server.main import build_server  # pylint: disable=import-outside-toplevel
        config = yaml.safe_load((PLUGIN / "config.yaml.example").read_text(encoding="utf-8"))
        config["server"]["port"] = 0
        config["auth"]["peers"] = {name: hashlib.sha256(token.encode()).hexdigest() for name, token in peers.items()}
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.port = 0

        async def main():
            self.stop = asyncio.Event()  # pylint: disable=attribute-defined-outside-init
            server = build_server(server_settings(config), db_path=str(tmp_path / "messages.db"))
            await server.start()
            self.port = server.bound_port
            self.ready.set()
            await self.stop.wait()
            await server.stop()

        self.thread = threading.Thread(target=lambda: self.loop.run_until_complete(main()), daemon=True)
        self.thread.start()
        assert self.ready.wait(15), "the Bridge did not start"

    def close(self):
        self.loop.call_soon_threadsafe(self.stop.set)
        self.thread.join(15)


@pytest.fixture
def real_bridge(tmp_path):
    server = RealBridge(tmp_path, {"laptop": PEER_TOKEN, "desk": "d" * 64})
    yield server
    server.close()


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "laptop.token"
    path.write_text(PEER_TOKEN + "\n", encoding="utf-8")
    return path


def smoke(box: Box, port: int, *args: str, name: str = "laptop", **env: str) -> Phase:
    return Phase(box, "test", "--bridge", "127.0.0.1", "--name", name, "--port", str(port), *args,
                 extra_env={"AI_CONNECT_DEPLOY_SMOKE_WAIT": "3", **env})


def rows(phase: Phase) -> dict:
    """{check title: (PASS/FAIL, detail)} out of the table."""
    table = {}
    for line in phase.out.splitlines():
        for verdict in ("PASS", "FAIL"):
            title, sep, detail = line.partition(f"  {verdict}    ")
            if sep:
                table[title.strip()] = (verdict, detail)
    return table


VERDICTS = ("VPN up", "Bridge port reachable", "Bridge accepts this token", "Message round trip, untrusted frame",
            "Wrong token refused")


def verdicts(phase: Phase) -> list[str]:
    table = rows(phase)
    return [table[title][0] for title in VERDICTS]


def test_smoke_passes_end_to_end_against_the_real_bridge(box, real_bridge, token_file):
    run = smoke(box, real_bridge.port, "--token-file", str(token_file))
    assert run.res.returncode == 0, run.text
    assert verdicts(run) == ["PASS"] * 5, run.out
    assert "5 of 5 checks passed" in run.out
    assert "came back inside the untrusted frame" in rows(run)["Message round trip, untrusted frame"][1]
    assert run.changed_nothing() and not leaks(PEER_TOKEN, run.text)


def test_smoke_reads_the_token_from_the_environment(box, real_bridge):
    run = smoke(box, real_bridge.port, AI_CONNECT_PEER_TOKEN=PEER_TOKEN)
    assert run.res.returncode == 0 and verdicts(run) == ["PASS"] * 5, run.text
    assert not leaks(PEER_TOKEN, run.text)


def test_smoke_fails_when_the_bridge_refuses_this_token(box, real_bridge, tmp_path):
    wrong = tmp_path / "wrong.token"
    wrong.write_text("0123456789abcdef" * 4, encoding="utf-8")
    run = smoke(box, real_bridge.port, "--token-file", str(wrong))
    assert run.res.returncode == 1
    assert verdicts(run) == ["PASS", "PASS", "FAIL", "FAIL", "PASS"], run.out
    assert "refused this machine's token" in run.out and "1 of 5" not in run.out and "2 FAILED" in run.out


def test_smoke_fails_when_the_token_belongs_to_another_name(box, real_bridge, token_file):
    run = smoke(box, real_bridge.port, "--token-file", str(token_file), name="desk")
    assert run.res.returncode == 1
    assert verdicts(run) == ["PASS", "PASS", "PASS", "FAIL", "PASS"], run.out
    assert "name_not_bound_to_token" in run.out


def test_smoke_fails_when_nothing_listens(box, token_file):
    run = smoke(box, free_port(), "--token-file", str(token_file))
    assert run.res.returncode == 1
    assert verdicts(run) == ["PASS", "FAIL", "FAIL", "FAIL", "FAIL"], run.out
    assert "could not tell" in rows(run)["Wrong token refused"][1]  # unreachable is not "refused"


def test_smoke_fails_when_the_vpn_is_down(box, real_bridge, token_file):
    box.set(ts_backend="Stopped", ts_ip="")
    run = smoke(box, real_bridge.port, "--token-file", str(token_file))
    assert run.res.returncode == 1
    assert verdicts(run) == ["FAIL", "PASS", "PASS", "PASS", "PASS"], run.out


def test_smoke_fails_a_bridge_that_takes_any_token_and_never_answers(box, token_file):
    class Anything(set):
        def __contains__(self, item):
            return True
    server = FakeBridge(Anything)
    try:
        run = smoke(box, server.port, "--token-file", str(token_file), AI_CONNECT_DEPLOY_SMOKE_WAIT="1")
    finally:
        server.close()
    assert run.res.returncode == 1
    assert verdicts(run) == ["PASS", "PASS", "PASS", "FAIL", "FAIL"], run.out
    assert "ACCEPTED a random token" in run.out and "no answer in time" in run.out


def test_round_trip_check_only_passes_a_message_inside_one_untrusted_block(monkeypatch):
    monkeypatch.syspath_prepend(str(PLUGIN / "deploy"))
    import config_tool  # pylint: disable=import-outside-toplevel,import-error
    check = config_tool._framed_as_untrusted  # pylint: disable=protected-access
    frame = {"from": "laptop", "content": "nonce-123"}
    real = config_tool.untrusted.frame_message
    assert check(frame, "laptop", "nonce-123") is None
    assert "does not name the sender" in check({**frame, "from": "mallory"}, "laptop", "nonce-123")
    monkeypatch.setattr(config_tool.untrusted, "frame_message", lambda sender, content: f"{sender}: {content}")
    assert "not rendered as exactly one untrusted block" in check(frame, "laptop", "nonce-123")
    monkeypatch.setattr(config_tool.untrusted, "frame_message",
                        lambda sender, content: content + "\n" + real(sender, "x"))
    assert "not inside the untrusted block" in check(frame, "laptop", "nonce-123")

def test_the_helper_redacts_a_token_a_bridge_echoes_back(monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(PLUGIN / "deploy"))
    import config_tool  # pylint: disable=import-outside-toplevel,import-error
    config_tool.tsadmin.remember_secret(PEER_TOKEN)
    config_tool.emit({"checks": [{"check": "round_trip", "ok": False, "detail": f"refused: bad token {PEER_TOKEN}"}]})
    shown = capsys.readouterr().out
    assert not leaks(PEER_TOKEN, shown) and json.loads(shown)["checks"][0]["detail"] == "refused: bad token <redacted>"

@pytest.mark.parametrize("args", [["test"], ["test", "--bridge", "127.0.0.1"], ["test", "--name", "laptop"],
                                  ["test", "--name", "bad name!", "--bridge", "127.0.0.1"],
                                  ["test", "--name", "laptop", "--bridge", "a b"],
                                  ["test", "--name", "laptop", "--bridge", "127.0.0.1", "--token-file", "nope.token"]],
                         ids=" ".join)
def test_smoke_bad_arguments(box, args):
    run = Phase(box, *args)
    assert run.res.returncode == 2, run.text
    assert run.calls == [] and run.changed_nothing()
