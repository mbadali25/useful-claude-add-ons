"""T-0050: `/crew:config` repo writes, the owner's profile, rebuild and restore.

Every write is a dry run until `--apply`. Must-block cases assert that a dry
run, an unreadable profile, an absent one without `--no-profile`, an unknown
stamp and a failed backup each write NOTHING: the file's bytes and mtime, the
backup directory and the profile are all unchanged.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autoclear_setup
import crew_backup
import crew_config
import crew_fixtures
import crew_platform
import crew_state
import crew_upgrade


@pytest.fixture(name="home")
def _home(tmp_path, monkeypatch):
    """A scratch machine: global config path, profile beside it."""
    path = tmp_path / "home" / ".claude" / "crew" / "config.json"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    return path


def _repo(tmp_path, cfg=None, git=False):
    return str(crew_fixtures.make_repo(
        tmp_path, config=crew_config.template_config() if cfg is None else cfg, git=git))


def _bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _cli(capsys, *argv):
    code = crew_config.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def _snapshot(*paths):
    """Bytes and mtime of each path, plus the whole backup tree."""
    state = {}
    for path in paths:
        path = str(path)
        state[path] = ((_bytes(path), os.stat(path).st_mtime_ns)
                       if os.path.exists(path) else None)
    tree = []
    for dirpath, _dirs, files in os.walk(os.environ["CREW_BACKUP_DIR"]):
        tree.extend(os.path.join(dirpath, name) for name in files)
    state["backups"] = sorted(tree)
    return state


def _profile(home):
    return home.parent / "profile.json"


def _config(root):
    return os.path.join(root, ".crew", "config.json")


def _write_profile(home, repos=None, global_values=None, saved_at="2026-10-01T00:00:00Z"):
    body = {"schema": 1, "saved_at": saved_at,
            "global": {"saved_at": saved_at, "values": global_values or {}},
            "repos": repos or {}}
    _profile(home).write_text(json.dumps(body), encoding="utf-8")
    return body


# --- --set / --unset with --repo (Step 4) ------------------------------------


def test_set_repo_dry_run_writes_nothing(tmp_path, home, capsys):
    root = _repo(tmp_path)
    before = _snapshot(_config(root), _profile(home))
    code, out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--set", 'tracker="jira"', "--repo")
    assert code == 0 and "would write (dry run)" in out
    assert _snapshot(_config(root), _profile(home)) == before


def test_set_repo_apply_merges_and_backs_up(tmp_path, home, capsys):
    root = _repo(tmp_path)
    before = _bytes(_config(root))
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--set", 'tracker="jira"', "--repo", "--apply")
    assert code == 0, err
    after = _json(_config(root))
    assert after["tracker"] == "jira" and after["qa"] == crew_config.template_config()["qa"]
    stamps = crew_backup.list_backups(_config(root))
    assert crew_backup.read_backup(_config(root), stamps[0]) == before


@pytest.mark.parametrize("assignment", ['schema=8', 'nope.key=1', 'scope.mode="off"'])
def test_set_repo_refuses_schema_and_unknown_and_scope(tmp_path, home, capsys, assignment):
    root = _repo(tmp_path)
    before = _snapshot(_config(root))
    code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                            "--set", assignment, "--repo", "--apply")
    assert code == 2
    assert _snapshot(_config(root)) == before


def test_unset_repo_removes_one_leaf_and_keeps_siblings(tmp_path, home, capsys):
    cfg = crew_config.template_config()
    cfg["autopilot"] = {"mode": "off", "approval": "human"}
    root = _repo(tmp_path, cfg)
    home.write_text(json.dumps({"autopilot": {"mode": "plan"}}), encoding="utf-8")
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--unset", "autopilot.mode", "--repo")
    assert code == 0, err
    assert "autopilot.mode: \"off\" -> (removed)" in out
    assert "! autopilot.mode widens to `plan`" in out
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--unset", "autopilot.mode", "--repo", "--apply")
    assert code == 0, err
    after = _json(_config(root))
    assert after["autopilot"] == {"approval": "human"}
    assert crew_config.resolve_config(root)["autopilot"]["mode"] == "plan"


def test_unset_repo_refuses_scope_and_blocks(tmp_path, home, capsys):
    root = _repo(tmp_path)
    for path in ("scope.allowCliApproval", "qa", "schema"):
        code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                                "--unset", path, "--repo", "--apply")
        assert code == 2, path


def test_unset_global_personal_key(tmp_path, home, capsys):
    root = _repo(tmp_path)
    home.write_text(json.dumps({"autopilot": {"approval": "self", "mode": "plan"}}),
                    encoding="utf-8")
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--unset", "autopilot.approval", "--apply")
    assert code == 0, err
    assert _json(home) == {"autopilot": {"mode": "plan"}}


def test_profile_refreshed_after_set_apply(tmp_path, home, capsys):
    root = _repo(tmp_path)
    _write_profile(home, repos={"elsewhere": {"saved_at": "x", "values": {"tier": 2}}},
                   global_values={"pm.authority": "act"})
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--set", 'tracker="jira"', "--repo", "--apply")
    assert code == 0, err
    profile = _json(_profile(home))
    assert profile["global"]["values"] == {"pm.authority": "act"}
    assert profile["repos"]["elsewhere"]["values"] == {"tier": 2}
    key = crew_config.profile_key(root)
    assert profile["repos"][key]["values"] == {"tracker": "jira"}


def test_profile_values_exclude_schema_and_platform(tmp_path):
    cfg = crew_config.template_config()
    cfg["schema"] = 99
    cfg["platform"]["os"] = "linux"
    cfg["tier"] = 3
    assert crew_config.profile_section(cfg, crew_config.template_config()) == {"tier": 3}


def test_profile_keeps_unknown_keys():
    cfg = crew_config.template_config()
    cfg["mystery"] = {"x": [1]}
    assert crew_config.profile_section(cfg, crew_config.template_config()) == {
        "mystery.x": [1]}


@pytest.mark.parametrize("url", ["git@github.com:O/R.git",
                                 "https://user:tok@GitHub.com/O/R/",
                                 "ssh://git@github.com/O/R"])
def test_profile_key_normalises_origin(url):
    assert crew_config.normalise_origin(url) == "github.com/O/R"


def test_profile_key_without_origin_is_the_path(tmp_path):
    root = _repo(tmp_path, git=True)
    assert crew_config.profile_key(root) == "path:" + os.path.realpath(root)
    subprocess.run(["git", "-C", root, "remote", "add", "origin",
                    "git@github.com:O/R.git"], check=True)
    assert crew_config.profile_key(root) == "github.com/O/R"


def test_save_profile_dry_run_then_apply(tmp_path, home, capsys):
    cfg = crew_config.template_config()
    cfg["tracker"] = "jira"
    root = _repo(tmp_path, cfg)
    home.write_text(json.dumps({"autopilot": {"approval": "self"}}), encoding="utf-8")
    code, out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--save-profile")
    assert code == 0 and "dry run" in out
    assert not _profile(home).exists()
    code, out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--save-profile", "--apply")
    assert code == 0
    profile = _json(_profile(home))
    assert profile["global"]["values"] == {"autopilot.approval": "self"}
    assert profile["repos"][crew_config.profile_key(root)]["values"] == {"tracker": "jira"}


def test_save_profile_refuses_an_unreadable_profile(tmp_path, home, capsys):
    root = _repo(tmp_path)
    _profile(home).write_text("{ nope", encoding="utf-8")
    code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                            "--save-profile", "--apply")
    assert code == 3
    assert _profile(home).read_text(encoding="utf-8") == "{ nope"


def _vault(tmp_path, home):
    vault = tmp_path / "vault"
    vault.mkdir()
    home.write_text(json.dumps({"memory": {"vaultPath": str(vault)}}), encoding="utf-8")
    return vault / "crew" / "profile.json"


def test_vault_copy_written_when_vault_path_set(tmp_path, home, capsys):
    root = _repo(tmp_path)
    vault_copy = _vault(tmp_path, home)
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--save-profile", "--apply")
    assert code == 0, err
    assert vault_copy.read_bytes() == _profile(home).read_bytes()


def test_no_vault_copy_when_vault_path_missing_dir(tmp_path, home, capsys):
    root = _repo(tmp_path)
    home.write_text(json.dumps({"memory": {"vaultPath": str(tmp_path / "gone")}}),
                    encoding="utf-8")
    code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                            "--save-profile", "--apply")
    assert code == 0
    assert not (tmp_path / "gone").exists()


def test_defaults_writers_never_touch_profile(tmp_path, home):
    _write_profile(home, global_values={"pm.authority": "act"})
    before = _profile(home).read_bytes()
    broken = tmp_path / "a"
    (broken / ".crew").mkdir(parents=True)
    (broken / ".crew" / "config.json").write_text("{ x", encoding="utf-8")
    crew_platform.heal_config(str(broken))
    cfg = crew_config.template_config()
    cfg["platform"]["os"] = "plan9"
    root = crew_fixtures.make_repo(tmp_path / "b", config=cfg, git=False)
    loaded, raw = crew_platform.load(str(root))
    assert crew_platform.apply_changes(str(root), loaded, raw, {"os": ("plan9", "linux")})
    old = crew_fixtures.make_repo(tmp_path / "c", config={"tier": 0}, git=False)
    crew_upgrade.run(str(old), {})
    clear = crew_config.template_config()
    clear["context"]["autoClear"]["method"] = "windows"
    clear_root = crew_fixtures.make_repo(tmp_path / "d", config=clear, git=False)
    crew_autoclear_setup.apply_migrate_to_repo(str(clear_root), global_path=str(home))
    assert _profile(home).read_bytes() == before


# --- --rebuild, --restore, --backups (Step 5) ---------------------------------


def _corrupt_repo(tmp_path):
    root = _repo(tmp_path)
    with open(_config(root), "w", encoding="utf-8") as handle:
        handle.write("{ corrupt")
    return root


def _saved_repo_profile(home, root, values):
    return _write_profile(home, repos={crew_config.profile_key(root): {
        "saved_at": "2026-10-01T00:00:00Z", "path": root, "values": values}})


def test_rebuild_never_writes_without_apply(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    _saved_repo_profile(home, root, {"tracker": "jira"})
    before = _snapshot(_config(root), _profile(home))
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--rebuild", "--repo")
    assert code == 0, err
    assert "would rebuild" in out and "tracker" in out
    assert _snapshot(_config(root), _profile(home)) == before


def test_rebuild_profile_unreadable_exit_3(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    _profile(home).write_text("{ nope", encoding="utf-8")
    before = _snapshot(_config(root), _profile(home))
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--rebuild", "--repo", "--apply")
    assert code == 3, err
    assert _snapshot(_config(root), _profile(home)) == before


def test_rebuild_profile_unreadable_vault_absent_exit_3(tmp_path, home, capsys):
    """A present-but-unreadable copy with no other copy is could-not-tell,
    never "no profile": --no-profile is not implied."""
    root = _corrupt_repo(tmp_path)
    vault_copy = _vault(tmp_path, home)
    _profile(home).write_text("[]", encoding="utf-8")
    assert not vault_copy.exists()
    code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                            "--rebuild", "--repo", "--apply")
    assert code == 3


def test_rebuild_profile_absent_refused_without_no_profile(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    before = _snapshot(_config(root), _profile(home))
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--rebuild", "--repo", "--apply")
    assert code == 2 and "--no-profile" in err
    assert _snapshot(_config(root), _profile(home)) == before


def test_rebuild_needs_a_layer(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    before = _snapshot(_config(root))
    code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                            "--rebuild", "--apply")
    assert code == 2
    code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                            "--rebuild", "--repo", "--global", "--apply")
    assert code == 2
    assert _snapshot(_config(root)) == before


def test_rebuild_refuses_when_backup_fails_exit_4(tmp_path, home, capsys, monkeypatch):
    root = _corrupt_repo(tmp_path)
    _saved_repo_profile(home, root, {"tracker": "jira"})
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CREW_BACKUP_DIR", str(blocker / "b"))
    before = _bytes(_config(root))
    code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                            "--rebuild", "--repo", "--apply")
    assert code == 4
    assert _bytes(_config(root)) == before


def test_corrupt_repo_rebuilt_from_profile(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    _saved_repo_profile(home, root, {"tracker": "jira", "autopilot.mode": "plan"})
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--rebuild", "--repo")
    assert code == 0, err
    assert "corrupt (9 bytes)" in out
    assert "! autopilot.mode widens to `plan`" in out
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--rebuild", "--repo", "--apply")
    assert code == 0, err
    expected = crew_config.template_config()
    expected["tracker"] = "jira"
    # The template keeps the repo-only autopilot keys (`maxAutoReplans`,
    # `sleep`); the profile's personal `mode` joins them.
    expected.setdefault("autopilot", {})["mode"] = "plan"
    assert _json(_config(root)) == expected
    newest = crew_backup.list_backups(_config(root))[0]
    assert crew_backup.read_backup(_config(root), newest) == b"{ corrupt"


def test_missing_repo_config_rebuilt_from_profile(tmp_path, home, capsys):
    root = _repo(tmp_path)
    os.remove(_config(root))
    _saved_repo_profile(home, root, {"tier": 2})
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--rebuild", "--repo", "--apply")
    assert code == 0, err
    assert "absent" in out
    assert _json(_config(root))["tier"] == 2


def test_rebuild_keeps_a_readable_files_platform_block(tmp_path, home, capsys):
    cfg = crew_config.template_config()
    cfg["platform"]["os"] = "linux"
    root = _repo(tmp_path, cfg)
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--rebuild", "--repo", "--no-profile", "--apply")
    assert code == 0, err
    assert _json(_config(root))["platform"]["os"] == "linux"


def test_rebuild_global_from_profile(tmp_path, home, capsys):
    root = _repo(tmp_path)
    home.write_text("{ broken", encoding="utf-8")
    _write_profile(home, global_values={"pm.authority": "act",
                                        "autopilot.approval": "self"})
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--rebuild", "--global", "--apply")
    assert code == 0, err
    got = _json(home)
    assert got["pm"]["authority"] == "act"
    assert got["autopilot"] == {"approval": "self"}
    assert "! autopilot.approval widens to `self`" in out
    newest = crew_backup.list_backups(str(home))[0]
    assert crew_backup.read_backup(str(home), newest) == b"{ broken"


def test_rebuild_no_profile_writes_template(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--rebuild", "--repo", "--no-profile", "--apply")
    assert code == 0, err
    assert _json(_config(root)) == crew_config.template_config()
    assert not _profile(home).exists()


def test_rebuild_does_not_refresh_the_profile(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    _saved_repo_profile(home, root, {"tracker": "jira"})
    before = _profile(home).read_bytes()
    _cli(capsys, "--root", root, "--global-path", str(home), "--rebuild", "--repo",
         "--no-profile", "--apply")
    assert _profile(home).read_bytes() == before


def test_vault_copy_newer_wins_and_is_named(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    vault_copy = _vault(tmp_path, home)
    _saved_repo_profile(home, root, {"tracker": "files"})
    newer = {"schema": 1, "saved_at": "2026-10-03T00:00:00Z", "global": None,
             "repos": {crew_config.profile_key(root): {
                 "saved_at": "2026-10-03T00:00:00Z", "values": {"tracker": "jira"}}}}
    vault_copy.parent.mkdir(parents=True)
    vault_copy.write_text(json.dumps(newer), encoding="utf-8")
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--rebuild", "--repo", "--apply")
    assert code == 0, err
    assert "differ" in out and str(vault_copy) in out and str(_profile(home)) in out
    assert _json(_config(root))["tracker"] == "jira"


def test_vault_copy_unreadable_uses_home_copy_and_says_so(tmp_path, home, capsys):
    root = _corrupt_repo(tmp_path)
    vault_copy = _vault(tmp_path, home)
    _saved_repo_profile(home, root, {"tracker": "jira"})
    vault_copy.parent.mkdir(parents=True)
    vault_copy.write_text("{ torn", encoding="utf-8")
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--rebuild", "--repo", "--apply")
    assert code == 0, err
    assert f"{vault_copy} is unreadable" in out
    assert _json(_config(root))["tracker"] == "jira"


def test_restore_unknown_stamp_exit_2(tmp_path, home, capsys):
    root = _repo(tmp_path)
    before = _snapshot(_config(root))
    for stamp in ("20200101T000000Z", "../x"):
        code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                                "--restore", stamp, "--repo", "--apply")
        assert code == 2
    assert _snapshot(_config(root)) == before


def _two_versions(tmp_path, home, capsys):
    root = _repo(tmp_path)
    original = _bytes(_config(root))
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--set", 'tracker="jira"', "--repo", "--apply")
    assert code == 0, err
    return root, original, crew_backup.list_backups(_config(root))[0]


def test_restore_dry_run_writes_nothing(tmp_path, home, capsys):
    root, _original, stamp = _two_versions(tmp_path, home, capsys)
    before = _snapshot(_config(root), _profile(home))
    code, out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--restore", stamp, "--repo")
    assert code == 0 and "would restore" in out and "tracker" in out
    assert _snapshot(_config(root), _profile(home)) == before


def test_restore_roundtrip(tmp_path, home, capsys):
    root, original, stamp = _two_versions(tmp_path, home, capsys)
    current = _bytes(_config(root))
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--restore", stamp, "--repo", "--apply")
    assert code == 0, err
    assert _bytes(_config(root)) == original
    newest = crew_backup.list_backups(_config(root))[0]
    assert crew_backup.read_backup(_config(root), newest) == current


def test_restore_refuses_when_backup_fails_exit_4(tmp_path, home, capsys, monkeypatch):
    root, _original, stamp = _two_versions(tmp_path, home, capsys)
    data = crew_backup.read_backup(_config(root), stamp)
    current = _bytes(_config(root))
    monkeypatch.setattr(crew_backup, "backup", _fail)
    code, _out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                            "--restore", stamp, "--repo", "--apply")
    assert code == 4
    assert _bytes(_config(root)) == current != data


def _corrupt_stamp_over_healthy(tmp_path, home, capsys):
    """A healthy repo file whose newest backup holds corrupt bytes: the
    corrupt file is backed up by a rebuild, which then writes a healthy one."""
    root = _corrupt_repo(tmp_path)
    code, _out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--rebuild", "--repo", "--no-profile", "--apply")
    assert code == 0, err
    stamp = crew_backup.list_backups(_config(root))[0]
    assert crew_backup.read_backup(_config(root), stamp) == b"{ corrupt"
    return root, stamp


def test_restore_of_a_corrupt_stamp_refuses_exit_2(tmp_path, home, capsys):
    """Must-block (review of e6c5fa6a): `--restore` of a corrupt backup over a
    healthy file said "nothing to change", then wrote the corrupt bytes."""
    root, stamp = _corrupt_stamp_over_healthy(tmp_path, home, capsys)
    healthy = _bytes(_config(root))
    for extra in ((), ("--apply",)):
        code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                              "--restore", stamp, "--repo", *extra)
        assert code == 2, (extra, out)
        assert "stamped file is not valid JSON" in err and "--force-invalid" in err
        assert "nothing to change" not in out
    assert _bytes(_config(root)) == healthy


def test_restore_of_a_corrupt_stamp_with_force_invalid(tmp_path, home, capsys):
    """The explicit flag path: the dry run says what it would write, and
    `--apply` writes the stamped bytes as they are."""
    root, stamp = _corrupt_stamp_over_healthy(tmp_path, home, capsys)
    healthy = _bytes(_config(root))
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--restore", stamp, "--repo", "--force-invalid")
    assert code == 0, err
    assert "stamped file is not valid JSON" in out and "nothing to change" not in out
    assert _bytes(_config(root)) == healthy
    code, out, err = _cli(capsys, "--root", root, "--global-path", str(home),
                          "--restore", stamp, "--repo", "--force-invalid", "--apply")
    assert code == 0, err
    assert _bytes(_config(root)) == b"{ corrupt"


def _fail(*_args, **_kwargs):
    raise crew_backup.BackupError("the backup root is unwritable")


def test_backups_lists_newest_first(tmp_path, home, capsys):
    root = _repo(tmp_path)
    for value in ("jira", "files", "sdp"):
        _cli(capsys, "--root", root, "--global-path", str(home),
             "--set", f'tracker="{value}"', "--repo", "--apply")
    code, out, _err = _cli(capsys, "--root", root, "--global-path", str(home),
                           "--backups", "--repo")
    assert code == 0
    listed = [line.strip() for line in out.splitlines()[1:]]
    assert listed == crew_backup.list_backups(_config(root))
    assert len(listed) == 3
    assert listed == sorted(listed, key=crew_backup._stamp_key, reverse=True)


def test_profile_drift_finding(tmp_path, home, capsys):
    cfg = crew_config.template_config()
    cfg["tracker"] = "jira"
    root = _repo(tmp_path, cfg)
    _saved_repo_profile(home, root, {"tracker": "sdp"})
    findings = crew_config.explain_findings(root, str(home))
    drift = [f for f in findings if f["kind"] == "profile drift"]
    assert drift and drift[0]["path"] == "tracker"
    assert 'file="jira" profile="sdp"' in drift[0]["detail"]
