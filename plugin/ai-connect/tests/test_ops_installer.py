"""Tests for installer.py: token generation, hashing, add/revoke peer,
placeholder rejection and the shape of the config it writes.

Plain pytest, no AI-Connect install required. Every test works in a tmp_path
config and never touches the real ~/.config/ai-connect or ~/.claude.
"""

import hashlib
import json
import os
import re
from pathlib import Path

import pytest
import yaml

import installer

HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def config_path(tmp_path):
    return tmp_path / "config.yaml"


@pytest.fixture(autouse=True)
def isolate_claude_settings(monkeypatch, tmp_path):
    """Never let a test touch the real ~/.claude/settings.json."""
    monkeypatch.setattr(installer, "CLAUDE_SETTINGS", tmp_path / "settings.json")


@pytest.fixture(autouse=True)
def isolate_token_paths(monkeypatch, tmp_path):
    """Never let a test touch the real ~/.config/ai-connect/*.token files."""
    monkeypatch.setitem(installer.TOKEN_PATHS, "observer", tmp_path / "observer.token")
    monkeypatch.setitem(installer.TOKEN_PATHS, "user", tmp_path / "user.token")


def write_yaml(path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def read_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def full_config(**overrides):
    """A config with every key the template has, so check_config's key check passes."""
    config = installer._example()
    config["client"]["token"] = "a-real-token-not-the-placeholder"
    for dotted, value in overrides.items():
        node = config
        *path, leaf = dotted.split(".")
        for part in path:
            node = node[part]
        node[leaf] = value
    return config


def answer_with(monkeypatch, *answers):
    """Make every input() call return the next canned answer in order."""
    queue = list(answers)

    def fake_input(_prompt=""):
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)


# ---------------------------------------------------------------------------
# Token generation and hashing
# ---------------------------------------------------------------------------


def test_token_sha256_matches_hashlib():
    assert installer._token_sha256("abc") == hashlib.sha256(b"abc").hexdigest()


def test_add_peer_token_is_256_bits_hex(config_path):
    write_yaml(config_path, full_config())
    token = installer._add_peer("laptop", config_path)
    assert HEX64.match(token), f"expected 64 hex chars (256 bits), got {token!r}"
    assert len(bytes.fromhex(token)) == 32


def test_add_peer_stores_only_the_hash(config_path):
    write_yaml(config_path, full_config())
    token = installer._add_peer("laptop", config_path)

    saved = read_yaml(config_path)
    assert saved["auth"]["peers"]["laptop"] == installer._token_sha256(token)

    # The raw token must never land on disk, only its hash
    raw_text = config_path.read_text(encoding="utf-8")
    assert token not in raw_text


def test_add_peer_duplicate_name_exits(config_path):
    write_yaml(config_path, full_config())
    installer._add_peer("laptop", config_path)
    with pytest.raises(SystemExit):
        installer._add_peer("laptop", config_path)


def test_add_peer_unicode_name_round_trips(config_path):
    write_yaml(config_path, full_config())
    installer._add_peer("café-portátil", config_path)
    saved = read_yaml(config_path)
    assert "café-portátil" in saved["auth"]["peers"]


def test_add_peer_cli_prints_token_once(config_path, capsys):
    write_yaml(config_path, full_config())
    installer.add_peer("laptop", config_path)
    out = capsys.readouterr().out
    saved = read_yaml(config_path)
    token_hash = saved["auth"]["peers"]["laptop"]
    # The printed raw token must hash to what was stored
    printed_token = [line.strip() for line in out.splitlines() if HEX64.match(line.strip())][0]
    assert installer._token_sha256(printed_token) == token_hash


# ---------------------------------------------------------------------------
# revoke-peer
# ---------------------------------------------------------------------------


def test_revoke_peer_removes_entry(config_path):
    write_yaml(config_path, full_config())
    installer._add_peer("laptop", config_path)
    installer.revoke_peer("laptop", config_path)
    saved = read_yaml(config_path)
    assert "laptop" not in saved["auth"]["peers"]


def test_revoke_peer_unknown_name_exits(config_path):
    write_yaml(config_path, full_config())
    with pytest.raises(SystemExit):
        installer.revoke_peer("nobody", config_path)


def test_revoke_then_readd_peer_gets_a_new_token(config_path):
    write_yaml(config_path, full_config())
    first = installer._add_peer("laptop", config_path)
    installer.revoke_peer("laptop", config_path)
    second = installer._add_peer("laptop", config_path)
    assert first != second


# ---------------------------------------------------------------------------
# Placeholder rejection
# ---------------------------------------------------------------------------


def test_placeholder_token_is_the_example_value():
    assert installer._placeholder_token() == installer._example()["client"]["token"]


def test_reject_placeholder_exits_on_match():
    with pytest.raises(SystemExit):
        installer._reject_placeholder(installer._placeholder_token(), "Peer token")


def test_reject_placeholder_allows_real_token():
    installer._reject_placeholder("a-real-token-value", "Peer token")  # must not raise


def test_check_config_rejects_placeholder_when_shared_token_allowed(config_path):
    config = full_config(**{
        "auth.allow_shared_token": True,
        "auth.token": installer._placeholder_token(),
    })
    write_yaml(config_path, config)
    with pytest.raises(SystemExit, match="placeholder"):
        installer.check_config(config_path)


def test_check_config_rejects_shared_token_allowed_but_unset(config_path):
    write_yaml(config_path, full_config(**{"auth.allow_shared_token": True}))
    with pytest.raises(SystemExit, match="unset"):
        installer.check_config(config_path)


def test_check_config_allows_placeholder_when_shared_token_disabled(config_path):
    # allow_shared_token defaults to false, so a leftover placeholder in
    # auth.token (an old config migrated to auth.peers) is harmless
    config = full_config(**{
        "auth.allow_shared_token": False,
        "auth.token": installer._placeholder_token(),
    })
    write_yaml(config_path, config)
    installer.check_config(config_path)  # must not raise


def test_write_config_client_rejects_pasted_placeholder(monkeypatch, config_path):
    answer_with(monkeypatch, "my-laptop", "bridge.example.com", installer._placeholder_token())
    with pytest.raises(SystemExit):
        installer.write_config(server=False, config_path=config_path)


# ---------------------------------------------------------------------------
# check_config: missing keys, and the "empty dict never required" rule
# ---------------------------------------------------------------------------


def test_check_config_reports_missing_key(config_path):
    config = full_config()
    del config["server"]["rate_per_second"]
    write_yaml(config_path, config)
    with pytest.raises(SystemExit, match="server.rate_per_second"):
        installer.check_config(config_path)


def test_check_config_passes_on_a_complete_config(config_path):
    write_yaml(config_path, full_config())
    installer.check_config(config_path)  # must not raise


def test_empty_peers_dict_requires_no_leaf_key():
    # auth.peers: {} in the template must not force every real config to
    # have a literal "auth.peers" leaf, nor a specific peer name under it
    assert installer._dotted_keys({"peers": {}}) == set()


def test_a_config_with_different_peers_than_the_template_still_passes(config_path):
    # The template ships auth.peers: {}; a real config naming actual peers
    # must not be flagged as "missing" anything under auth.peers
    config = full_config()
    config["auth"]["peers"] = {"laptop": "f" * 64, "desktop": "a" * 64}
    write_yaml(config_path, config)
    installer.check_config(config_path)  # must not raise


# ---------------------------------------------------------------------------
# write_config: output shape
# ---------------------------------------------------------------------------


def test_write_config_server_shape(monkeypatch, config_path):
    answer_with(monkeypatch, "bridge-host", "100.64.0.1")
    installer.write_config(server=True, config_path=config_path)

    saved = read_yaml(config_path)
    assert saved["client"]["name"] == "bridge-host"
    assert saved["server"]["host"] == "100.64.0.1"
    assert saved["client"]["bridge_url"] == "ws://100.64.0.1:9999"
    assert saved["auth"]["allow_shared_token"] is False
    assert "token" not in saved["auth"]  # the peer's token is client.token, not the Bridge's auth
    assert saved["auth"]["peers"].keys() == {"bridge-host"}
    assert HEX64.match(saved["client"]["token"])  # own peer token, filled in
    assert saved["auth"]["peers"]["bridge-host"] == installer._token_sha256(saved["client"]["token"])
    assert HEX64.match(saved["auth"]["observer_token_sha256"])
    assert HEX64.match(saved["auth"]["user_token_sha256"])
    assert saved["server"]["max_message_bytes"] == 65536
    assert saved["server"]["rate_per_second"] == 10
    assert saved["server"]["history_days"] == 14


def test_write_config_server_default_host_is_loopback_not_wildcard(monkeypatch, config_path):
    # Blank answer takes the _ask default; that default must never be 0.0.0.0
    answer_with(monkeypatch, "bridge-host", "")
    installer.write_config(server=True, config_path=config_path)
    saved = read_yaml(config_path)
    assert saved["server"]["host"] == "127.0.0.1"
    assert saved["server"]["host"] != "0.0.0.0"


def test_write_config_client_shape(monkeypatch, config_path):
    real_token = "b" * 64
    answer_with(monkeypatch, "laptop", "100.64.0.1", real_token)
    installer.write_config(server=False, config_path=config_path)

    saved = read_yaml(config_path)
    assert saved["client"]["name"] == "laptop"
    assert saved["client"]["bridge_url"] == "ws://100.64.0.1:9999"
    assert saved["client"]["token"] == real_token
    assert "token" not in saved["auth"]
    assert saved["auth"]["peers"] == {}
    # A client never generates observer/user tokens
    assert saved["auth"]["observer_token_sha256"] == ""
    assert saved["auth"]["user_token_sha256"] == ""


def test_write_config_client_requires_a_host_answer(monkeypatch, config_path):
    # No default for the Bridge host; a blank answer must abort, not silently
    # write an empty/garbage host
    answer_with(monkeypatch, "laptop", "")
    with pytest.raises(SystemExit):
        installer.write_config(server=False, config_path=config_path)


def test_write_config_keeps_existing_config_unchanged(monkeypatch, config_path):
    existing = full_config()
    write_yaml(config_path, existing)
    # No input() should be consulted at all when a valid config already exists
    answer_with(monkeypatch)
    installer.write_config(server=True, config_path=config_path)
    assert read_yaml(config_path) == existing


# ---------------------------------------------------------------------------
# create_token
# ---------------------------------------------------------------------------


def test_create_token_writes_file_and_hash(config_path, tmp_path):
    write_yaml(config_path, full_config())
    installer.create_token("observer", config_path)

    token_file = installer.TOKEN_PATHS["observer"]
    token = token_file.read_text(encoding="utf-8").strip()
    assert HEX64.match(token)

    saved = read_yaml(config_path)
    assert saved["auth"]["observer_token_sha256"] == installer._token_sha256(token)


def test_create_token_deny_rules_skip_missing_settings_file(config_path, tmp_path):
    write_yaml(config_path, full_config())
    assert not installer.CLAUDE_SETTINGS.exists()
    installer.create_token("user", config_path)  # must not raise even though settings.json is absent


def test_create_token_adds_deny_rules_to_existing_settings(config_path, tmp_path):
    write_yaml(config_path, full_config())
    installer.CLAUDE_SETTINGS.write_text("{}", encoding="utf-8")
    installer.create_token("observer", config_path)

    settings = json.loads(installer.CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    assert any("observer.token" in rule or "observer_client" in rule for rule in deny)


# ---------------------------------------------------------------------------
# Secret files are private from the moment they hold a secret
# ---------------------------------------------------------------------------


@pytest.fixture
def replaced(monkeypatch):
    """Record every os.replace the installer makes: (target name, source mode, source text)."""
    calls = []
    real_replace = os.replace

    def spy(src, dst):
        calls.append((Path(dst).name, os.stat(src).st_mode, Path(src).read_text(encoding="utf-8")))
        real_replace(src, dst)

    monkeypatch.setattr(installer.os, "replace", spy)
    return calls


def test_secret_files_are_written_whole_then_moved_into_place(config_path, tmp_path, replaced):
    """config.yaml and the token file appear only by an atomic replace of a complete temp file."""
    write_yaml(config_path, full_config())
    installer.create_token("observer", config_path)
    token = installer.TOKEN_PATHS["observer"].read_text(encoding="utf-8")
    names = [name for name, _, _ in replaced]
    assert "observer.token" in names and "config.yaml" in names
    assert (dict((n, t) for n, _, t in replaced))["observer.token"] == token
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.yaml", "observer.token", "user.token"] or \
        not [p for p in tmp_path.iterdir() if p.name.startswith(".")]  # no temp file left


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")
def test_secret_files_are_never_group_or_world_readable(config_path, replaced, monkeypatch):
    """Under umask 022 a secret file must be 0600 before it holds the secret, and stay 0600."""
    old = os.umask(0o022)
    try:
        write_yaml(config_path, full_config())
        config_path.chmod(0o644)
        installer.create_token("user", config_path)
    finally:
        os.umask(old)
    assert replaced and all(mode & 0o077 == 0 for _, mode, _ in replaced)
    assert config_path.stat().st_mode & 0o077 == 0
    assert installer.TOKEN_PATHS["user"].stat().st_mode & 0o077 == 0
