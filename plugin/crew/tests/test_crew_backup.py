"""T-0050: a timestamped backup before every crew write of a config file.

Must-block, per writer: with the backup root unwritable (a FILE where the
directory should be), the write is refused and the target stays
byte-identical. Must-allow, per writer: the pre-write bytes -- corrupt ones
included -- are the newest backup once the write lands.
"""
import datetime
import json
import os
import stat

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autoclear_setup
import crew_backup
import crew_config
import crew_fixtures
import crew_platform
import crew_state
import crew_upgrade

NOW = datetime.datetime(2026, 10, 4, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _root():
    return os.environ["CREW_BACKUP_DIR"]


def _break_backup_root(tmp_path, monkeypatch):
    """A file where the backup directory should be: every backup fails."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CREW_BACKUP_DIR", str(blocker / "backups"))


def _newest(path):
    stamps = crew_backup.list_backups(str(path))
    assert stamps, f"no backup of {path}"
    return crew_backup.read_backup(str(path), stamps[0])


def _global(tmp_path, monkeypatch, contents):
    path = tmp_path / "home" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contents), encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    return path


# --- The unit ----------------------------------------------------------------


def test_backup_copies_raw_bytes_including_corrupt(tmp_path):
    target = tmp_path / "r" / ".crew" / "config.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xef\xbb\xbf{ not json\r\n")
    stamp = crew_backup.backup(str(target), now=NOW)
    assert stamp == "20261004T120000Z"
    assert crew_backup.read_backup(str(target), stamp) == b"\xef\xbb\xbf{ not json\r\n"
    source = os.path.join(crew_backup.target_dir(str(target)), "source")
    with open(source, encoding="utf-8") as handle:
        assert handle.read().strip() == os.path.realpath(str(target))


def test_backup_absent_file_returns_none(tmp_path):
    assert crew_backup.backup(str(tmp_path / "nope.json")) is None
    assert not os.path.exists(_root())


def test_backup_rotation_keeps_newest_20(tmp_path):
    target = tmp_path / "g.json"
    for index in range(25):
        target.write_text(str(index), encoding="utf-8")
        crew_backup.backup(str(target), now=NOW + datetime.timedelta(seconds=index))
    stamps = crew_backup.list_backups(str(target))
    assert len(stamps) == crew_backup.KEEP == 20
    assert stamps[0] == "20261004T120024Z"
    assert stamps[-1] == "20261004T120005Z"
    assert crew_backup.read_backup(str(target), stamps[0]) == b"24"


def test_backup_same_second_collision_suffix(tmp_path):
    target = tmp_path / "g.json"
    got = []
    for index in range(3):
        target.write_text(str(index), encoding="utf-8")
        got.append(crew_backup.backup(str(target), now=NOW))
    assert got == ["20261004T120000Z", "20261004T120000Z-2", "20261004T120000Z-3"]
    assert crew_backup.list_backups(str(target))[0] == "20261004T120000Z-3"
    assert crew_backup.read_backup(str(target), "20261004T120000Z-2") == b"1"


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes; Windows ACLs are not 0700/0600")
def test_backup_dirs_private(tmp_path):
    target = tmp_path / "g.json"
    target.write_text("{}", encoding="utf-8")
    stamp = crew_backup.backup(str(target))
    directory = crew_backup.target_dir(str(target))
    for path in (_root(), os.path.dirname(directory), directory):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o700, path
    mode = os.stat(os.path.join(directory, f"{stamp}.json")).st_mode
    assert stat.S_IMODE(mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes; Windows ACLs are not 0700/0600")
def test_backup_leaves_an_existing_backup_root_mode_alone(tmp_path, monkeypatch):
    """Review of e6c5fa6a: a `CREW_BACKUP_DIR` the owner already made (0755)
    was chmod'ed to 0700. Only a directory this call created is made private."""
    mine = tmp_path / "owners-dir"
    mine.mkdir()
    os.chmod(mine, 0o755)
    monkeypatch.setenv("CREW_BACKUP_DIR", str(mine))
    target = tmp_path / "g.json"
    target.write_text("{}", encoding="utf-8")
    crew_backup.backup(str(target), now=NOW)
    assert stat.S_IMODE(os.stat(mine).st_mode) == 0o755
    directory = crew_backup.target_dir(str(target))
    for path in (os.path.dirname(directory), directory):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o700, path


def test_backup_reads_back_and_refuses_a_mismatch(tmp_path, monkeypatch):
    """Must-block: a backup whose bytes on disk are not the bytes read is
    refused (the caller then refuses its write), and the bad copy is not left
    behind as a stamp `--restore` would offer."""
    target = tmp_path / "g.json"
    target.write_bytes(b'{"a": 1}')
    real = crew_backup._write_private

    def torn(where, data):
        real(where, data[:-1] if where.endswith(".json") else data)

    monkeypatch.setattr(crew_backup, "_write_private", torn)
    with pytest.raises(crew_backup.BackupError, match="read back"):
        crew_backup.backup(str(target), now=NOW)
    assert crew_backup.list_backups(str(target)) == []
    monkeypatch.setattr(crew_backup, "_write_private", real)
    stamp = crew_backup.backup(str(target), now=NOW)
    assert crew_backup.read_backup(str(target), stamp) == b'{"a": 1}'


@pytest.mark.parametrize("stamp", ["../x", "latest", "", "20261004T120000Z/../../x",
                                   "20261004T120000"])
def test_read_backup_refuses_bad_stamp(tmp_path, stamp):
    with pytest.raises(crew_backup.BackupError):
        crew_backup.read_backup(str(tmp_path / "g.json"), stamp)


def test_target_dir_global_vs_repo(tmp_path, monkeypatch):
    gpath = _global(tmp_path, monkeypatch, {})
    assert crew_backup.target_dir(str(gpath)) == os.path.join(_root(), "global")
    repo_file = tmp_path / "myrepo" / ".crew" / "config.json"
    got = crew_backup.target_dir(str(repo_file))
    assert os.path.dirname(got) == os.path.join(_root(), "repo")
    assert os.path.basename(got).startswith("myrepo-")
    other = crew_backup.target_dir(str(tmp_path / "other" / ".crew" / "config.json"))
    assert other != got


# --- Per writer: backs up first, refuses without a backup --------------------


def test_write_global_config_backs_up_first(tmp_path, monkeypatch):
    gpath = _global(tmp_path, monkeypatch, {"pm": {"authority": "act"}})
    before = gpath.read_bytes()
    crew_config.write_global_config({"notify.chatId": "1"}, str(gpath))
    assert _newest(gpath) == before
    assert json.loads(gpath.read_text(encoding="utf-8"))["notify"]["chatId"] == "1"


def test_write_global_config_refuses_without_backup(tmp_path, monkeypatch):
    gpath = _global(tmp_path, monkeypatch, {"pm": {"authority": "act"}})
    before = gpath.read_bytes()
    _break_backup_root(tmp_path, monkeypatch)
    with pytest.raises(crew_config.WriteBackupRefused):
        crew_config.write_global_config({"notify.chatId": "1"}, str(gpath))
    assert gpath.read_bytes() == before


def test_write_global_config_first_write_needs_no_backup(tmp_path, monkeypatch):
    """No file, nothing to lose: the first write of the machine file lands
    even with the backup root unwritable."""
    gpath = tmp_path / "fresh" / "config.json"
    _break_backup_root(tmp_path, monkeypatch)
    crew_config.write_global_config({"notify.chatId": "1"}, str(gpath))
    assert gpath.is_file()


def _repo(tmp_path, cfg=None):
    return crew_fixtures.make_repo(tmp_path, config=cfg or crew_config.template_config(),
                                   git=False)


def test_write_repo_config_backs_up_first(tmp_path):
    root = _repo(tmp_path)
    path = root / ".crew" / "config.json"
    before = path.read_bytes()
    crew_config.write_repo_config(str(root), {"tracker": "jira"})
    assert _newest(path) == before


def test_write_repo_config_refuses_without_backup(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    path = root / ".crew" / "config.json"
    before = path.read_bytes()
    _break_backup_root(tmp_path, monkeypatch)
    with pytest.raises(crew_config.WriteBackupRefused):
        crew_config.write_repo_config(str(root), {"tracker": "jira"})
    assert path.read_bytes() == before


def _broken_repo(tmp_path):
    root = tmp_path / "r"
    (root / ".crew").mkdir(parents=True)
    path = root / ".crew" / "config.json"
    path.write_bytes(b"{ corrupt")
    return root, path


def test_heal_config_backs_up_first(tmp_path):
    root, path = _broken_repo(tmp_path)
    healed, _message = crew_platform.heal_config(str(root))
    assert healed is not None
    assert _newest(path) == b"{ corrupt"


def test_heal_config_refuses_without_backup(tmp_path, monkeypatch):
    root, path = _broken_repo(tmp_path)
    _break_backup_root(tmp_path, monkeypatch)
    healed, message = crew_platform.heal_config(str(root))
    assert healed is None
    assert "could NOT be backed up" in message
    assert path.read_bytes() == b"{ corrupt"


def _platform_repo(tmp_path):
    cfg = crew_config.template_config()
    cfg["platform"]["os"] = "plan9"
    root = _repo(tmp_path, cfg)
    loaded, raw = crew_platform.load(str(root))
    return root, loaded, raw


def test_apply_changes_backs_up_first(tmp_path):
    root, cfg, raw = _platform_repo(tmp_path)
    path = root / ".crew" / "config.json"
    before = path.read_bytes()
    assert crew_platform.apply_changes(str(root), cfg, raw, {"os": ("plan9", "linux")})
    assert _newest(path) == before


def test_apply_changes_refuses_without_backup(tmp_path, monkeypatch):
    root, cfg, raw = _platform_repo(tmp_path)
    path = root / ".crew" / "config.json"
    before = path.read_bytes()
    _break_backup_root(tmp_path, monkeypatch)
    assert crew_platform.apply_changes(str(root), cfg, raw,
                                       {"os": ("plan9", "linux")}) is False
    assert path.read_bytes() == before
    assert not [n for n in os.listdir(path.parent) if n.endswith(".tmp")]


def _autoclear_repo(tmp_path):
    cfg = crew_config.template_config()
    cfg["context"]["autoClear"]["method"] = "windows"
    return _repo(tmp_path, cfg)


def test_autoclear_repo_write_backs_up_first(tmp_path):
    root = _autoclear_repo(tmp_path)
    path = root / ".crew" / "config.json"
    before = path.read_bytes()
    crew_autoclear_setup.apply_migrate_to_repo(str(root), global_path=str(tmp_path / "g.json"))
    assert path.read_bytes() != before
    assert _newest(path) == before


def test_autoclear_repo_write_refuses_without_backup(tmp_path, monkeypatch):
    root = _autoclear_repo(tmp_path)
    path = root / ".crew" / "config.json"
    before = path.read_bytes()
    _break_backup_root(tmp_path, monkeypatch)
    with pytest.raises(crew_backup.BackupError):
        crew_autoclear_setup.apply_migrate_to_repo(str(root),
                                                   global_path=str(tmp_path / "g.json"))
    assert path.read_bytes() == before
    assert not [n for n in os.listdir(path.parent) if n.endswith(".tmp")]


def test_autoclear_atomic_write_backs_up_and_refuses(tmp_path, monkeypatch):
    path = tmp_path / ".crew" / "config.json"
    path.parent.mkdir()
    path.write_text('{"a": 1}', encoding="utf-8")
    crew_autoclear_setup._atomic_write_json(str(path), {"a": 2})
    assert _newest(path) == b'{"a": 1}'
    _break_backup_root(tmp_path, monkeypatch)
    with pytest.raises(crew_backup.BackupError):
        crew_autoclear_setup._atomic_write_json(str(path), {"a": 3})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 2}


def test_upgrade_backs_up_first(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0}, git=False)
    path = root / ".crew" / "config.json"
    before = path.read_bytes()
    assert crew_upgrade.run(str(root), {})["status"] == "upgraded"
    assert _newest(path) == before


def test_upgrade_refuses_without_backup(tmp_path, monkeypatch):
    root = crew_fixtures.make_repo(tmp_path, config={"tier": 0}, git=False)
    path = root / ".crew" / "config.json"
    before = path.read_bytes()
    _break_backup_root(tmp_path, monkeypatch)
    assert crew_upgrade.run(str(root), {})["status"] == "config backup failed"
    assert path.read_bytes() == before
    assert not [n for n in os.listdir(path.parent) if n.endswith(".tmp")]


def test_menu_restore_backs_up_the_current_file(tmp_path, monkeypatch):
    import crew_config_menu  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path)
    path = root / ".crew" / "config.json"
    saved = root / ".crew" / "config.json.bak-20261001T000000Z"
    saved.write_text(json.dumps({"tracker": "jira"}), encoding="utf-8")
    before = path.read_bytes()
    _break_backup_root(tmp_path, monkeypatch)
    assert crew_config_menu.restore_repo_config(str(root), str(saved), True) == 2
    assert path.read_bytes() == before
    monkeypatch.setenv("CREW_BACKUP_DIR", str(tmp_path / "ok-backups"))
    assert crew_config_menu.restore_repo_config(str(root), str(saved), True) == 0
    assert _newest(path) == before
