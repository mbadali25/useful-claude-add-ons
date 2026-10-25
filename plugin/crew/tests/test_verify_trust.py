"""`verify_trust.py` (L-0888): does this machine trust a repo's verify map?

MUST-BLOCK (the verdict is not 0, so the gate runs nothing): no store entry;
one byte changed in verify.json or in the smoke script after approval; the
verify.json deleted so a smoke script would run; a corrupt or unreadable
store (UNKNOWN, never trusted); a `testTrustAll` flag in a store (honoured by
nothing); a store location a repo can author (relative, or inside the repo, set
through CREW_VERIFY_TRUST_FILE, CLAUDE_CONFIG_DIR or HOME); every lookalike host,
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
import shutil
import subprocess
import threading

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
    monkeypatch.delenv("CREW_TEST_TRUST_ALL", raising=False)
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


def _allow(owner=_OWNER, under=()):
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


_TRUST_ALL_STORE = '{"version": 1, "repos": {}, "owners": {}, "testTrustAll": true}'


def test_evaluate_a_test_trust_all_flag_in_the_store_trusts_nothing(tmp_path, store):
    root = _repo(tmp_path)
    store.parent.mkdir(parents=True)
    store.write_text(_TRUST_ALL_STORE, encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_a_test_trust_all_flag_in_a_config_dir_store_trusts_nothing(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    config = tmp_path / "claude"
    (config / "crew").mkdir(parents=True)
    (config / "crew" / "verify-trust.json").write_text(_TRUST_ALL_STORE, encoding="utf-8")
    monkeypatch.delenv(verify_trust.ENV_STORE, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    assert _code(root) == verify_trust.EXIT_UNTRUSTED


# ------------------------------------- a repo-authored store location (settings env)

def test_evaluate_a_relative_store_override_is_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(verify_trust.ENV_STORE, "store/t.json")

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_evaluate_a_store_override_inside_the_repo_is_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    inside = root / ".claude" / "t.json"
    inside.parent.mkdir()
    inside.write_text(_TRUST_ALL_STORE, encoding="utf-8")
    monkeypatch.setenv(verify_trust.ENV_STORE, str(inside))

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_evaluate_a_store_override_through_a_symlink_into_the_repo_is_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    (root / "real").mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(root / "real", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")
    monkeypatch.setenv(verify_trust.ENV_STORE, str(link / "t.json"))

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_evaluate_a_store_override_inside_a_linked_worktrees_main_checkout_is_unknown(
        tmp_path, monkeypatch):
    main = _repo(tmp_path, name="main")
    _git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-q", "-m", "x")
    work = tmp_path / "work"
    _git(main, "worktree", "add", "-q", str(work))
    (work / ".crew").mkdir(exist_ok=True)
    (work / ".crew" / "verify.json").write_text(_VERIFY, encoding="utf-8")
    monkeypatch.setenv(verify_trust.ENV_STORE, str(main / "t.json"))

    assert _code(work) == verify_trust.EXIT_UNKNOWN


def test_evaluate_a_relative_claude_config_dir_is_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.delenv(verify_trust.ENV_STORE, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "claude")

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_evaluate_a_claude_config_dir_inside_the_repo_is_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    (root / "cfg" / "crew").mkdir(parents=True)
    (root / "cfg" / "crew" / "verify-trust.json").write_text(_TRUST_ALL_STORE, encoding="utf-8")
    monkeypatch.delenv(verify_trust.ENV_STORE, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root / "cfg"))

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_evaluate_a_home_inside_the_repo_is_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.delenv(verify_trust.ENV_STORE, raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("USERPROFILE", str(root / "home"))

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_approve_with_a_store_inside_the_repo_writes_nothing(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    inside = root / "t.json"
    monkeypatch.setenv(verify_trust.ENV_STORE, str(inside))

    code = _approve(root)

    assert code == 1
    assert not inside.exists()


def test_evaluate_an_absolute_store_outside_the_repo_is_honoured(tmp_path, store):
    root = _repo(tmp_path)
    _approve(root)

    assert _code(root) == verify_trust.EXIT_TRUSTED


def test_evaluate_the_default_home_store_outside_the_repo_is_honoured(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.delenv(verify_trust.ENV_STORE, raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    _approve(root)

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
    _allow(_OWNER, [inside])

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


def test_approve_prints_a_hostile_remote_escaped(tmp_path, store, capsys):
    root = _repo(tmp_path, remotes=["https://example.com/a\x1b[2Jb"])

    _approve(root)

    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "\\u001b" in out


def test_update_store_two_writers_at_once_both_land(tmp_path, store):
    roots = [_repo(tmp_path, f"repo{i}") for i in range(6)]
    threads = [threading.Thread(target=_approve, args=(root,)) for root in roots]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(json.loads(store.read_text(encoding="utf-8"))["repos"]) == 6


def test_evaluate_a_subdirectory_of_an_allowlisted_repo_is_untrusted(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    sub = root / "sub"
    (sub / ".crew").mkdir(parents=True)
    (sub / ".crew" / "verify.json").write_text(_VERIFY, encoding="utf-8")
    _allow()

    assert _code(root) == verify_trust.EXIT_TRUSTED
    assert _code(sub) == verify_trust.EXIT_UNTRUSTED


def test_evaluate_a_git_file_pointing_at_a_trusted_repo_does_not_borrow_its_place(
        tmp_path, store):
    inside = tmp_path / "work"
    inside.mkdir()
    trusted = _repo(inside, "good", remotes=[_OK_URL])
    evil = tmp_path / "elsewhere" / "evil"
    (evil / ".crew").mkdir(parents=True)
    (evil / ".git").write_text(f"gitdir: {trusted / '.git'}\n", encoding="utf-8")
    (evil / ".crew" / "verify.json").write_text(_VERIFY, encoding="utf-8")
    _allow(_OWNER, [inside])

    assert _code(trusted) == verify_trust.EXIT_TRUSTED
    assert _code(evil) == verify_trust.EXIT_UNTRUSTED


def test_disallow_owner_without_a_terminal_or_yes_changes_nothing(tmp_path, store, monkeypatch):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    monkeypatch.setattr(verify_trust.sys.stdin, "isatty", lambda: False)

    code = verify_trust.main(["disallow-owner", _OWNER])

    assert code == 1
    assert _code(root) == verify_trust.EXIT_TRUSTED


def test_lock_a_stale_lock_is_broken_once_and_a_fresh_one_is_kept(tmp_path):
    path = str(tmp_path / "s.json")
    lock_dir = path + ".lock"
    os.mkdir(lock_dir)
    old = os.stat(lock_dir).st_mtime - verify_trust.LOCK_STALE - 5
    os.utime(lock_dir, (old, old))

    with verify_trust._Lock(path):
        assert os.path.isdir(lock_dir)
    assert not os.path.exists(lock_dir)

    os.mkdir(lock_dir)
    verify_trust._Lock(path)._break()
    assert os.path.isdir(lock_dir)


def test_lock_release_leaves_a_lock_another_holder_took(tmp_path):
    path = str(tmp_path / "s.json")
    mine = verify_trust._Lock(path)
    other = path + ".lock"

    with mine:
        with open(os.path.join(other, "token"), "w", encoding="utf-8") as handle:
            handle.write("someone-else")

    assert os.path.isdir(other)


def test_lock_release_does_not_remove_a_holder_that_replaced_it_mid_release(tmp_path, monkeypatch):
    path = str(tmp_path / "s.json")
    mine = verify_trust._Lock(path)
    real = shutil.rmtree

    def replaced_first(target, *args, **kwargs):
        real(target, ignore_errors=True)
        os.mkdir(mine.path)
        with open(os.path.join(mine.path, "token"), "w", encoding="utf-8") as handle:
            handle.write("the-replacement-holder")
        real(target, *args, **kwargs)

    monkeypatch.setattr(verify_trust.shutil, "rmtree", replaced_first)

    with mine:
        pass

    assert os.path.isdir(mine.path)


def test_lock_release_puts_back_a_foreign_directory_it_claimed(tmp_path):
    path = str(tmp_path / "s.json")
    mine = verify_trust._Lock(path)

    with mine:
        shutil.rmtree(mine.path)
        os.mkdir(mine.path)
        with open(os.path.join(mine.path, "token"), "w", encoding="utf-8") as handle:
            handle.write("someone-else")

    with open(os.path.join(mine.path, "token"), encoding="utf-8") as handle:
        assert handle.read() == "someone-else"
    assert sorted(os.listdir(tmp_path)) == ["s.json.lock"]


def test_replace_retries_a_permission_error_then_succeeds(tmp_path, monkeypatch):
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("x", encoding="utf-8")
    real, calls = os.replace, []

    def flaky(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError
        real(a, b)

    monkeypatch.setattr(verify_trust.os, "replace", flaky)

    verify_trust._replace(str(src), str(dst))

    assert dst.read_text(encoding="utf-8") == "x" and len(calls) == 3


def test_git_output_with_invalid_bytes_stays_distinct(tmp_path):
    first = b"https://github.com/\xff/x".decode("utf-8", "backslashreplace")
    second = b"https://github.com/\xfe/x".decode("utf-8", "backslashreplace")

    assert first != second and verify_trust.parse_remote(first) is None


def test_check_expect_verify_sha_for_other_bytes_is_changed_though_trusted(tmp_path, store, capsys):
    root = _repo(tmp_path)
    _approve(root)

    code = verify_trust.main(["check", "--root", str(root), "--expect-verify-sha", "0" * 64])

    assert code == verify_trust.EXIT_CHANGED
    assert "CHANGED, not run" in capsys.readouterr().out


def test_check_expect_verify_sha_for_the_same_bytes_is_trusted(tmp_path, store):
    import hashlib
    root = _repo(tmp_path)
    _approve(root)
    sha = hashlib.sha256((root / ".crew" / "verify.json").read_bytes()).hexdigest()

    code = verify_trust.main(["check", "--root", str(root), "--expect-verify-sha", sha])

    assert code == verify_trust.EXIT_TRUSTED


def test_check_a_named_verify_file_is_not_trusted_by_the_remote_owner(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    _allow()
    other = tmp_path / "other.json"
    other.write_text(_VERIFY + " ", encoding="utf-8")

    own = verify_trust.evaluate(str(root)).code
    named = verify_trust.evaluate(str(root), verify_file=str(other)).code

    assert (own, named) == (verify_trust.EXIT_TRUSTED, verify_trust.EXIT_UNTRUSTED)


def test_check_a_named_verify_file_with_approved_bytes_is_trusted(tmp_path, store):
    root = _repo(tmp_path)
    _approve(root)
    copy = tmp_path / "copy.json"
    copy.write_text(_VERIFY, encoding="utf-8")

    assert verify_trust.evaluate(str(root), verify_file=str(copy)).code == verify_trust.EXIT_TRUSTED


def test_evaluate_a_malformed_owner_restriction_is_unknown(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    store.parent.mkdir(parents=True)
    store.write_text(json.dumps({"version": verify_trust.STORE_VERSION, "repos": {},
                                 "owners": {_OWNER: {"under": [1]}}}), encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_UNKNOWN


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
def test_evaluate_a_fifo_as_the_store_is_unknown_and_does_not_hang(tmp_path, store):
    root = _repo(tmp_path)
    store.parent.mkdir(parents=True)
    os.mkfifo(store)

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_approve_inside_a_claude_code_session_changes_nothing_even_with_yes(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.delenv(verify_trust.ENV_STORE, raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")

    code = verify_trust.main(["approve", "--root", str(root), "--yes"])

    assert code == 1


@pytest.mark.parametrize("url", ["https://github.com/mbadali25/evil..repo",
                                 "https://github.com/mbadali25..x/repo"])
def test_parse_remote_a_double_dot_inside_a_segment_is_refused(url):
    assert verify_trust.parse_remote(url) is None


def test_evaluate_a_lone_surrogate_in_an_owner_restriction_is_unknown(tmp_path, store):
    root = _repo(tmp_path, remotes=[_OK_URL])
    store.parent.mkdir(parents=True)
    store.write_text('{"version": %d, "repos": {}, "owners": {"%s": {"under": ["\\ud800"]}}}'
                     % (verify_trust.STORE_VERSION, _OWNER), encoding="utf-8")

    assert _code(root) == verify_trust.EXIT_UNKNOWN


def test_lock_one_that_stays_stale_is_given_up_on_at_the_deadline(tmp_path, monkeypatch):
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(verify_trust, "LOCK_WAIT", 0.3)
    lock = verify_trust._Lock(path)
    monkeypatch.setattr(lock, "_stale", lambda: True)
    monkeypatch.setattr(lock, "_break", lambda: None)
    os.mkdir(lock.path)

    with pytest.raises(verify_trust.TrustError), lock:
        pass


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
def test_check_a_named_verify_file_that_is_a_fifo_is_unknown_and_does_not_hang(tmp_path, store):
    root = _repo(tmp_path)
    fifo = tmp_path / "map.json"
    os.mkfifo(fifo)

    assert verify_trust.evaluate(str(root), verify_file=str(fifo)).code == verify_trust.EXIT_UNKNOWN
