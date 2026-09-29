"""conftest's autouse fixture must keep the developer's commit signing out of
every fixture `git commit`.

The global file here is built to make signing FAIL (`gpg.format=ssh` with
`/bin/false` as the signer), so a fixture commit that still signs exits
non-zero instead of silently costing a signature. Delete the unsigned_git_env
loop from conftest.py and the two signing tests go red; the last two pin
the helper's append-not-overwrite rule directly.
"""
import os
import subprocess

import pytest

from crew_fixtures import unsigned_git_env

_POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="uses /bin/false as the signer")


def _hostile_global(tmp_path, monkeypatch):
    cfg = tmp_path / "hostile-gitconfig"
    cfg.write_text("[user]\n\tname = t\n\temail = t@example.invalid\n"
                   "\tsigningkey = /nonexistent.pub\n"
                   "[gpg]\n\tformat = ssh\n[gpg \"ssh\"]\n\tprogram = /bin/false\n"
                   "[commit]\n\tgpgsign = true\n[tag]\n\tgpgsign = true\n",
                   encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


@_POSIX_ONLY
def test_a_fixture_commit_does_not_sign_under_a_signing_global_config(tmp_path, monkeypatch):
    repo = _hostile_global(tmp_path, monkeypatch)
    run = subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"],
                         cwd=repo, capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr


@_POSIX_ONLY
def test_a_fixture_tag_does_not_sign_under_a_signing_global_config(tmp_path, monkeypatch):
    repo = _hostile_global(tmp_path, monkeypatch)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"],
                   cwd=repo, check=True, capture_output=True)
    run = subprocess.run(["git", "tag", "-a", "v1", "-m", "v1"],
                         cwd=repo, capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr


def test_the_pins_append_after_a_runners_own_entries():
    ambient = {"GIT_CONFIG_COUNT": "3",
               "GIT_CONFIG_KEY_0": "credential.interactive", "GIT_CONFIG_VALUE_0": "false",
               "GIT_CONFIG_KEY_1": "url.a.insteadOf", "GIT_CONFIG_VALUE_1": "b",
               "GIT_CONFIG_KEY_2": "url.c.insteadOf", "GIT_CONFIG_VALUE_2": "d"}
    env = unsigned_git_env(ambient)
    assert env == {"GIT_CONFIG_KEY_3": "commit.gpgsign", "GIT_CONFIG_VALUE_3": "false",
                   "GIT_CONFIG_KEY_4": "tag.gpgsign", "GIT_CONFIG_VALUE_4": "false",
                   "GIT_CONFIG_COUNT": "5"}


@pytest.mark.parametrize("count", [None, "", "abc", "-1"])
def test_no_usable_count_starts_the_pins_at_slot_0(count):
    env = unsigned_git_env({} if count is None else {"GIT_CONFIG_COUNT": count})
    assert env["GIT_CONFIG_KEY_0"] == "commit.gpgsign"
    assert env["GIT_CONFIG_COUNT"] == "2"
