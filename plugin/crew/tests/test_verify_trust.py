"""`verify_trust.py` (L-0888): does this machine trust a repo's verify map?

MUST-BLOCK (the verdict is not 0, so the gate runs nothing): no store entry;
one byte changed in verify.json or in the smoke script after approval; the
verify.json deleted so a smoke script would run; a corrupt or unreadable
store (UNKNOWN, never trusted); the `testTrustAll` test seam read from a store
that was not named through the environment variable; every lookalike host,
owner and URL form; an allowlisted remote beside a foreign one; a foreign
`pushurl`; a local `insteadOf`; a global rewrite that makes the raw and the
resolved URL disagree; a top level owned by another user; an owner entry
restricted to a directory the repo is not under; a remote changed after the
pin; a pin that cannot be written; an `approve` with no terminal and no --yes.

MUST-ALLOW: approved bytes; approve, revoke, approve again; an allowlisted
https, ssh://git@ and scp-style remote; case-folded host and owner; a linked
worktree of an approved repo with identical bytes; an allowlisted repo after a
legitimate verify.json edit (owner trust follows the remote, not the bytes); a
repo below its owner entry's --under directory; a repo with nothing to run.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import verify_trust

_VERIFY = json.dumps({"version": 1, "rules": [{"paths": ["a.py"], "run": ["true"]}]})
_OWNER = "github.com/mbadali25"
_OK_URL = "https://github.com/mbadali25/useful.git"


def _git(root, *args):
    subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True, timeout=60)


@pytest.fixture(name="store")
def _store(tmp_path, monkeypatch):
    path = tmp_path / "trust" / "verify-trust.json"
    monkeypatch.setenv(verify_trust.ENV_STORE, str(path))
    return path


def _repo(tmp_path, name="repo", remotes=(), verify=_VERIFY, smoke=None):
    root = tmp_path / name
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    for index, url in enumerate(remotes):
        _git(root, "remote", "add", "origin" if index == 0 else f"r{index}", url)
    if verify is not None:
        (root / ".crew" / "verify.json").write_text(verify, encoding="utf-8")
    if smoke is not None:
        (root / "_verify").mkdir()
        (root / "_verify" / "smoke.sh").write_text(smoke, encoding="utf-8")
    return root


def _approve(root):
    return verify_trust.main(["approve", "--root", str(root), "--yes"])


def _allow(owner=_OWNER, *under):
    args = ["allow-owner", owner, "--yes"]
    for directory in under:
        args += ["--under", str(directory)]
    return verify_trust.main(args)


def _code(root, **kwargs):
    return verify_trust.evaluate(str(root), **kwargs).code


# ------------------------------------------------------------ hash approval

def test_evaluate_no_entry_is_untrusted(tmp_path, store):
    root = _repo(tmp_path)

    assert _code(root) == verify_trust.EXIT_UNTRUSTED
    assert not store.exists()


def test_evaluate_approved_bytes_are_trusted(tmp_path, store):
    root = _repo(tmp_path)
    _approve(root)

    assert _code(root) == verify_trust.EXIT_TRUSTED


def test_evaluate_one_byte_changed_in_verify_json_is_changed(tmp_path, store):
    root = _repo(tmp_path)
    _approve(root)
    (root / ".crew" / "verify.json").write_text(_VERIFY.replace("true", "tru3"), encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_CHANGED


def test_evaluate_one_byte_changed_in_the_smoke_script_is_changed(tmp_path, store):
    root = _repo(tmp_path, verify=None, smoke="echo one\n")
    _approve(root)
    (root / "_verify" / "smoke.sh").write_text("echo two\n", encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_CHANGED


def test_evaluate_smoke_script_stands_in_when_verify_json_is_deleted(tmp_path, store):
    root = _repo(tmp_path, smoke="echo evil\n")
    _approve(root)
    os.remove(root / ".crew" / "verify.json")

    assert _code(root) == verify_trust.EXIT_CHANGED


def test_evaluate_same_bytes_in_a_smoke_script_are_not_the_verify_json(tmp_path, store):
    root = _repo(tmp_path)
    _approve(root)
    os.remove(root / ".crew" / "verify.json")
    (root / "_verify").mkdir()
    (root / "_verify" / "smoke.sh").write_text(_VERIFY, encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_CHANGED


def test_evaluate_revoke_then_reapprove(tmp_path, store):
    root = _repo(tmp_path)
    _approve(root)
    verify_trust.main(["revoke", "--root", str(root)])

    assert _code(root) == verify_trust.EXIT_UNTRUSTED

    _approve(root)

    assert _code(root) == verify_trust.EXIT_TRUSTED


def test_evaluate_linked_worktree_with_identical_bytes_shares_the_approval(tmp_path, store):
    root = _repo(tmp_path)
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-q", "-m", "x")
    _approve(root)
    linked = tmp_path / "linked"
    _git(root, "worktree", "add", "-q", "-b", "lane", str(linked))

    assert _code(linked) == verify_trust.EXIT_TRUSTED

    (linked / ".crew" / "verify.json").write_text(_VERIFY + "\n", encoding="utf-8")

    assert _code(linked) == verify_trust.EXIT_CHANGED


def test_evaluate_nothing_to_run_is_trusted(tmp_path, store):
    root = _repo(tmp_path, verify=None)

    assert _code(root) == verify_trust.EXIT_TRUSTED


def test_approve_without_a_terminal_and_without_yes_changes_nothing(tmp_path, store):
    root = _repo(tmp_path)

    code = verify_trust.main(["approve", "--root", str(root)])

    assert code == 1
    assert not store.exists()


def test_approve_writes_a_store_only_the_owner_can_read(tmp_path, store):
    root = _repo(tmp_path)
    _approve(root)

    assert json.loads(store.read_text(encoding="utf-8"))["version"] == 1
    if os.name == "posix":
        assert store.stat().st_mode & 0o077 == 0


# ----------------------------------------------------------------- the store

def test_evaluate_a_corrupt_store_is_unknown(tmp_path, store):
    root = _repo(tmp_path)
    store.parent.mkdir(parents=True)
    store.write_text("{not json", encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_evaluate_an_unreadable_store_is_unknown(tmp_path, store):
    root = _repo(tmp_path)
    store.mkdir(parents=True)

    assert _code(root) == verify_trust.EXIT_UNKNOWN


@pytest.mark.parametrize("body", [
    '{"version": 2, "repos": {}, "owners": {}}',
    '{"version": 1, "repos": [], "owners": {}}',
    '{"version": 1, "repos": {"x": {"hashes": "abc"}}, "owners": {}}',
    "[]",
])
def test_evaluate_a_malformed_store_is_unknown(tmp_path, store, body):
    root = _repo(tmp_path)
    store.parent.mkdir(parents=True)
    store.write_text(body, encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_evaluate_the_test_seam_is_ignored_for_a_store_not_named_by_the_environment(
        tmp_path, monkeypatch):
    root = _repo(tmp_path)
    config = tmp_path / "claude"
    (config / "crew").mkdir(parents=True)
    (config / "crew" / "verify-trust.json").write_text(
        '{"version": 1, "repos": {}, "owners": {}, "testTrustAll": true}', encoding="utf-8")
    monkeypatch.delenv(verify_trust.ENV_STORE, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_the_test_seam_trusts_a_store_named_by_the_environment(tmp_path, store):
    root = _repo(tmp_path)
    store.parent.mkdir(parents=True)
    store.write_text('{"version": 1, "repos": {}, "owners": {}, "testTrustAll": true}',
                     encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_TRUSTED


# ------------------------------------------------------------- the allowlist

@pytest.mark.parametrize("url", [
    _OK_URL,
    "https://github.com/mbadali25/useful",
    "ssh://git@github.com/mbadali25/useful.git",
    "git@github.com:mbadali25/useful.git",
    "https://GitHub.COM/MBadali25/Useful.git",
])
def test_evaluate_an_allowlisted_remote_is_trusted_and_pinned(tmp_path, store, url):
    root = _repo(tmp_path, remotes=[url])
    _allow()

    assert _code(root) == verify_trust.EXIT_TRUSTED

    entry = json.loads(store.read_text(encoding="utf-8"))["repos"]
    assert [e["pin"] for e in entry.values()] == [[url]]


@pytest.mark.parametrize("url", [
    "https://github.com.evil.io/mbadali25/x.git",
    "https://githuh.com/mbadali25/x",
    "https://evilgithub.com/mbadali25/x",
    "https://github.com/mbadali25x/x",
    "https://github.com/xmbadali25/x",
    "https://github.com/mbadali2/x",
    "https://github.com/evil/mbadali25",
    "https://mbadali25@github.com/mbadali25/x",
    "https://evil@github.com/mbadali25/x",
    "http://github.com/mbadali25/x",
    "https://github.com:8443/mbadali25/x",
    "ssh://git@github.com:22/mbadali25/x",
    "ssh://root@github.com/mbadali25/x",
    "git@github.com.evil.io:mbadali25/x",
    "git@github.com:mbadali25/x/extra",
    "git@github.com:mbadali25",
    "file:///srv/github.com/mbadali25/x",
    "ext::sh -c id",
    "/srv/github.com/mbadali25/x",
    "../github.com/mbadali25/x",
    "https://github.com/mbadali25/../evil/x",
    "https://github.com/mbadali25/..",
    "https://github.com/%6dbadali25/x",
    "https://github.com/mbadali25/x\\y",
    " https://github.com/mbadali25/x",
])
def test_evaluate_a_lookalike_remote_is_untrusted(tmp_path, store, url):
    root = _repo(tmp_path, remotes=[url])
    _allow()

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


@pytest.mark.parametrize("url", ["https://github.com/mbadali25x/x", "https://github.com/evil/x"])
def test_parse_remote_never_returns_the_allowlisted_owner_for_another(url):
    assert verify_trust.parse_remote(url) != _OWNER


def test_evaluate_an_allowlisted_remote_beside_a_foreign_one_is_untrusted(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL, "https://github.com/evil/x.git"])
    _allow()

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_a_foreign_pushurl_is_untrusted(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _git(root, "config", "remote.origin.pushurl", "https://github.com/evil/x.git")
    _allow()

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_a_local_rewrite_is_untrusted_even_when_it_changes_nothing(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _git(root, "config", "url.https://unrelated.example/.insteadOf", "https://elsewhere.example/")
    _allow()

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_a_rewrite_outside_the_local_config_is_untrusted(tmp_path, store, monkeypatch):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    monkeypatch.setenv(f"GIT_CONFIG_KEY_{count}", "url.https://github.com/evil/.insteadOf")
    monkeypatch.setenv(f"GIT_CONFIG_VALUE_{count}", "https://github.com/mbadali25/")
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(count + 1))

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_no_remote_is_untrusted(tmp_path, store):
    root = _repo(tmp_path)
    _allow()

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_a_top_level_owned_by_another_user_is_untrusted(tmp_path, store):
    if os.name != "posix":
        pytest.skip("the ownership check is POSIX only")
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    other = os.geteuid() + 1

    assert _code(root, euid=other) == verify_trust.EXIT_UNTRUSTED
    assert _code(root) == verify_trust.EXIT_TRUSTED


def test_evaluate_a_remote_changed_after_the_pin_is_remote_changed(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    _code(root)
    _git(root, "remote", "set-url", "origin", "https://github.com/mbadali25/other.git")

    assert _code(root) == verify_trust.EXIT_REMOTE_CHANGED


def test_approve_repins_a_changed_remote(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    _code(root)
    _git(root, "remote", "set-url", "origin", "https://github.com/mbadali25/other.git")
    _approve(root)

    assert _code(root) == verify_trust.EXIT_TRUSTED


def test_evaluate_a_pin_that_cannot_be_written_is_untrusted(tmp_path, store, monkeypatch):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()

    def refuse(*_args, **_kwargs):
        raise verify_trust.TrustError("disk full")
    monkeypatch.setattr(verify_trust, "update_store", refuse)

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_an_allowlisted_repo_stays_trusted_after_a_verify_json_edit(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    _code(root)
    (root / ".crew" / "verify.json").write_text(_VERIFY + " ", encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_TRUSTED


def test_evaluate_an_owner_entry_trusts_nothing_after_disallow(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    verify_trust.main(["disallow-owner", _OWNER, "--yes"])

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_an_owner_restricted_to_a_directory_trusts_only_below_it(tmp_path, store):
    inside = tmp_path / "work"
    inside.mkdir()
    below = _repo(inside, "below", remotes=[_OK_URL])
    outside = _repo(tmp_path, "outside", remotes=[_OK_URL])
    _allow(_OWNER, inside)

    assert _code(below) == verify_trust.EXIT_TRUSTED
    assert _code(outside) == verify_trust.EXIT_UNTRUSTED


def test_allow_owner_refuses_a_malformed_owner(tmp_path, store):
    assert verify_trust.main(["allow-owner", "github.com", "--yes"]) == 2
    assert verify_trust.main(["allow-owner", "https://github.com/x", "--yes"]) == 2
    assert not store.exists()


def test_allow_owner_without_a_terminal_and_without_yes_changes_nothing(store):
    assert verify_trust.main(["allow-owner", _OWNER]) == 1
    assert not store.exists()


def test_status_does_not_write_a_pin(tmp_path, store, capsys):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    before = store.read_text(encoding="utf-8")

    verify_trust.main(["status", "--root", str(root)])

    assert store.read_text(encoding="utf-8") == before
    assert _OWNER in capsys.readouterr().out
