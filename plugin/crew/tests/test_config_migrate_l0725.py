"""L-0725 schema 8: the config migration, both layers.

The two owner files in `migrate_fixtures/l0725/` are sanitized copies of the
real repo layer and machine layer (`notify.chatId` and every private path
redacted). What is held here:

  * the repo layer becomes `guards: {profile: standard}` with no overrides, the
    machine layer `{profile: off, overrides: {terraformApply, forcePush,
    adminMerge, mergeGate: allow}}`, and every kept key is byte-for-byte the same;
  * every guard keeps the value it had in its layer, before and after, for the
    fixtures, a synthetic corpus and every layer pair (the ratchet's input);
  * a dropped key holding a non-default value refuses the run and writes
    nothing, unless `--accept-dropped` names it, and then the backup keeps it;
  * `--rollback` is byte-identical, for the repo file and for the machine file;
  * `--global --preview` writes nothing and `--apply` replaces the file
    atomically after backing it up.
"""
import copy
import itertools
import json
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config_files
import crew_dropped
import crew_guards
import crew_migrate
import crew_state
import crew_upgrade

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "migrate_fixtures", "l0725")
SCRIPT = os.path.join(os.path.dirname(HERE), "hooks", "scripts", "crew_migrate.py")
NAMES = crew_guards.ALL_GUARD_NAMES
OWNER_MACHINE_OVERRIDES = {"terraformApply": "allow", "forcePush": "allow",
                           "adminMerge": "allow", "mergeGate": "allow"}


# ---------------------------------------------------------------- helpers

def _fixture_bytes(name):
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        return fh.read()


def _fixture(name):
    return json.loads(_fixture_bytes(name).decode("utf-8"))


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not isinstance(data, bytes):
        data = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _repo(tmp_path, data, name="repo"):
    root = str(tmp_path / name)
    _write(os.path.join(root, ".crew", "config.json"), data)
    return root


def _config(root):
    return json.loads(_read(os.path.join(root, ".crew", "config.json")))


@pytest.fixture(name="machine")
def _machine(tmp_path, monkeypatch):
    """The machine file path, bound as `crew_state.GLOBAL_CONFIG_PATH` (the
    name `crew_migrate --global` reads); the file itself is not created."""
    path = str(tmp_path / "home" / ".claude" / "crew" / "config.json")
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", path)
    return path


def _snapshot(*roots):
    out = {}
    for root in roots:
        for base, _dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(base, name)
                out[path] = _read(path)
    return out


def _backups(root_or_dir, repo=True):
    folder = os.path.join(root_or_dir, ".crew" if repo else "", "backups")
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                  if n.startswith("migrate-"))


def _values(layer_cfg):
    """`{guard: tier}` with an unset guard as its default: what the ratchet
    reads (`resolve_ratcheted` ranks `normalise(None)`)."""
    return crew_upgrade.guard_layer_values(layer_cfg)


def _combined(repo_cfg, machine_cfg):
    return {name: crew_guards.effective_ratcheted(
        f"guards.{name}", _values(repo_cfg)[name], _values(machine_cfg)[name])
        for name in NAMES}


def _leaves(node, prefix=()):
    if isinstance(node, dict) and node:
        for key, value in node.items():
            yield from _leaves(value, prefix + (key,))
    else:
        yield ".".join(prefix), node


def _kept(cfg):
    """Every leaf the migration must not touch: all but the guards block, the
    schema stamp and the dropped keys. An empty table is not a leaf here: the
    repo upgrade has always stripped a stray `{}` (`_strip_empty_dicts`)."""
    return {key: value for key, value in _leaves(cfg)
            if not key.startswith("guards") and key != "schema" and value != {}
            and not any(key == d or key.startswith(d + ".") for d in crew_dropped.DROPPED)}


def _carried(before, after):
    """Every kept leaf of `before` is in `after` with the same value. `after`
    may hold more: the repo upgrade seeds the repo-only defaults of the blocks
    it migrates (`cloud.azureSubscriptions: []`), as it always has."""
    kept_after = _kept(after)
    missing = {k: v for k, v in _kept(before).items() if kept_after.get(k, object()) != v}
    return missing == {}, missing


def _put(cfg, dotted, value):
    node = cfg
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _has(cfg, dotted):
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def _non_default(default):
    """A value that is not `default` and is not equal to it in Python either."""
    if isinstance(default, bool):
        return not default
    if isinstance(default, (int, float)):
        return default + 7
    if isinstance(default, str):
        return default + "-changed"
    if isinstance(default, list):
        return default + ["changed"]
    return "changed"


# ---------------------------------------------------------------- the fixtures

def test_fixtures_hold_no_secret_and_no_private_path():
    for name in ("repo.config.json", "machine.config.json"):
        text = _fixture_bytes(name).decode("utf-8")
        assert '"chatId": "REDACTED"' in text, name
        assert "1335188592" not in text, name
        assert "mbadali" not in text, name
        for line in text.splitlines():
            assert "/root/" not in line and "/home/" not in line, (name, line)
            if "/repos/" in line:
                assert "/repos/example/" in line, (name, line)


# ---------------------------------------------------------------- the repo layer

def test_owner_repo_layer(tmp_path, capsys):
    original = _fixture_bytes("repo.config.json")
    before = _fixture("repo.config.json")
    root = _repo(tmp_path, original)

    code = crew_migrate.main(["--root", root, "--apply"])

    after = _config(root)
    out = capsys.readouterr().out
    assert code == 0
    assert after["guards"] == {"profile": "standard", "overrides": {}}
    assert after["schema"] == crew_state.SCHEMA_CURRENT == 8
    assert _carried(before, after) == (True, {})
    assert _values(after) == _values(before)
    assert after["notify"]["chatId"] == "REDACTED"
    assert after["install"] == {"policy": "ask"}
    for gone in ("tier", "roles", "docs", "bitbucket", "github", "sdp", "worktree"):
        assert gone not in after, gone
    assert "guards: `guards.profile` standard, no overrides" in out
    assert "unknown  platform.tools" in out
    assert "unknown  qa.tssPinsNote" in out


def test_owner_repo_layer_rollback_is_byte_identical(tmp_path):
    original = _fixture_bytes("repo.config.json")
    root = _repo(tmp_path, original)
    crew_migrate.main(["--root", root, "--apply"])
    (backup,) = _backups(root)

    code = crew_migrate.main(["--root", root, "--rollback", backup])

    assert code == 0
    assert _read(os.path.join(root, ".crew", "config.json")) == original
    assert not os.path.exists(os.path.join(root, ".crew", "crew.json"))


def test_preview_writes_nothing_for_the_repo_layer(tmp_path, capsys):
    root = _repo(tmp_path, _fixture_bytes("repo.config.json"))
    before = _snapshot(root)

    code = crew_migrate.main(["--root", root])

    assert code == 0
    assert _snapshot(root) == before
    assert "upgrade  - guards: `guards.profile` standard" in capsys.readouterr().out


def test_repo_preview_reports_an_unknown_guard_override(tmp_path, capsys):
    """Round-1 security F1: the repo path carried an unknown override name and
    never said so (`upgradeUnknown` was read and never set)."""
    body = json.dumps({"schema": 7, "guards": {"profile": "off",
                                               "overrides": {"futureGuard": "allow"}}}).encode()
    root = _repo(tmp_path, body)

    crew_migrate.main(["--root", root])

    assert "unknown  guards.overrides.futureGuard" in capsys.readouterr().out


def test_an_unknown_key_with_a_control_character_is_escaped_in_the_preview(tmp_path, capsys):
    body = json.dumps({"schema": 7, "odd\x1b[31mkey": 1}).encode()
    root = _repo(tmp_path, body)

    crew_migrate.main(["--root", root])

    out = capsys.readouterr().out
    assert "\x1b" not in out


# ---------------------------------------------------------------- the machine layer

def test_owner_machine_layer(machine, capsys):
    original = _fixture_bytes("machine.config.json")
    before = _fixture("machine.config.json")
    _write(machine, original)

    code = crew_migrate.main(["--global", "--apply"])

    after = json.loads(_read(machine))
    out = capsys.readouterr().out
    assert code == 0
    assert after["guards"] == {"profile": "off", "overrides": OWNER_MACHINE_OVERRIDES}
    assert "command" not in after["context"]["autoClear"]
    auto_before = before["context"]["autoClear"]
    for kept in ("minHandoffLines", "wrapUp", "onlyRepos", "enabled", "method", "delaySeconds"):
        assert after["context"]["autoClear"][kept] == auto_before[kept], kept
    assert after["install"] == {"policy": "ask"}
    assert after["qa"]["pinsResetNote"] == before["qa"]["pinsResetNote"]
    assert after["dev"]["pinsResetNote"] == before["dev"]["pinsResetNote"]
    assert _values(after) == _values(before)
    assert "unknown  qa.pinsResetNote" in out
    assert "unknown  dev.pinsResetNote" in out
    assert "schema" not in after


def test_owner_machine_layer_rollback_is_byte_identical(machine):
    original = _fixture_bytes("machine.config.json")
    _write(machine, original)
    crew_migrate.main(["--global", "--apply"])
    (backup,) = _backups(os.path.dirname(machine), repo=False)

    code = crew_migrate.main(["--global", "--rollback", backup])

    assert code == 0
    assert _read(machine) == original


def test_global_preview_writes_nothing(machine, capsys):
    _write(machine, _fixture_bytes("machine.config.json"))
    before = _snapshot(os.path.dirname(machine))

    code = crew_migrate.main(["--global", "--preview"])

    assert code == 0
    assert _snapshot(os.path.dirname(machine)) == before
    assert not _backups(os.path.dirname(machine), repo=False)
    assert "upgrade  - guards: `guards.profile` off with 4 override(s)" in capsys.readouterr().out


def test_global_apply_backs_up_first_and_records_the_scope(machine):
    original = _fixture_bytes("machine.config.json")
    _write(machine, original)

    crew_migrate.main(["--global", "--apply"])

    (backup,) = _backups(os.path.dirname(machine), repo=False)
    manifest = json.loads(_read(os.path.join(backup, "manifest.json")))
    assert (manifest["scope"], manifest["state"], manifest["acceptedDropped"]) == (
        "global", "applied", [])
    assert _read(os.path.join(backup, "sources", "config.json")) == original
    assert manifest["targets"][0]["originalSha256"] == crew_migrate._sha(original)  # pylint: disable=protected-access
    assert [n for n in os.listdir(os.path.dirname(machine)) if n.endswith(".tmp")] == []


def test_global_apply_is_atomic_when_the_replace_fails(machine, monkeypatch):
    original = _fixture_bytes("machine.config.json")
    _write(machine, original)
    real_replace = os.replace

    def replace(src, dst, *args, **kwargs):
        if os.path.basename(dst) == "config.json":
            raise OSError("injected: the final rename failed")
        return real_replace(src, dst, *args, **kwargs)
    monkeypatch.setattr(crew_migrate.os, "replace", replace)

    with pytest.raises(OSError):
        crew_migrate.main(["--global", "--apply"])

    monkeypatch.setattr(crew_migrate.os, "replace", real_replace)
    assert _read(machine) == original
    assert [n for n in os.listdir(os.path.dirname(machine)) if n.endswith(".tmp")] == []


def test_global_second_apply_is_a_no_op(machine, capsys):
    _write(machine, _fixture_bytes("machine.config.json"))
    crew_migrate.main(["--global", "--apply"])
    capsys.readouterr()
    migrated = _read(machine)

    code = crew_migrate.main(["--global", "--apply"])

    out = capsys.readouterr().out
    assert code == 0
    assert _read(machine) == migrated
    assert "nothing to write" in out
    assert len(_backups(os.path.dirname(machine), repo=False)) == 1


def test_global_with_no_machine_file_is_a_clean_note(machine, capsys):
    code = crew_migrate.main(["--global", "--apply"])

    assert code == 0
    assert "absent - no machine config to migrate" in capsys.readouterr().out
    assert not os.path.exists(machine)


def test_global_cli_reads_the_machine_file_from_home(tmp_path):
    home = tmp_path / "h"
    path = home / ".claude" / "crew" / "config.json"
    original = _fixture_bytes("machine.config.json")
    _write(str(path), original)
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    env.pop("CREW_BACKUP_DIR", None)

    done = subprocess.run([sys.executable, SCRIPT, "--global", "--preview"], env=env,
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)

    assert done.returncode == 0, done.stderr
    assert str(path) in done.stdout
    assert _read(str(path)) == original


# ---------------------------------------------------------------- refusal and --accept-dropped

REFUSED = [("sdp.portal", "https://portal.example"), ("worktree.root", "/elsewhere"),
           ("obsidian.board", "Other.md"), ("emergency.ttlMinutes", 30),
           ("secondOpinion.sendsCode", True), ("context.autoClear.windowTitle", "Terminal")]


@pytest.mark.parametrize("key,value", REFUSED)
def test_refuses_non_default_dropped_key(tmp_path, capsys, key, value):
    cfg = _fixture("repo.config.json")
    _put(cfg, key, value)
    root = _repo(tmp_path, cfg)
    before = _snapshot(root)

    code = crew_migrate.main(["--root", root, "--apply"])

    said = capsys.readouterr()
    constant = crew_dropped.DROPPED[key][1]
    assert code == 1
    assert _snapshot(root) == before
    assert not _backups(root)
    assert f"{key} holds a non-default value" in said.out + said.err
    assert constant in said.out + said.err
    assert f"--accept-dropped {key}" in said.out + said.err
    assert str(value) not in said.out.replace(constant, "") + said.err


def test_refuses_every_non_default_dropped_key_at_once_and_names_each(tmp_path, capsys):
    cfg = _fixture("repo.config.json")
    for key, value in REFUSED:
        _put(cfg, key, value)
    root = _repo(tmp_path, cfg)

    code = crew_migrate.main(["--root", root])

    out = capsys.readouterr().out
    assert code == 1
    for key, _value in REFUSED:
        assert f"CONFLICT  .crew/config.json: {key} holds a non-default value" in out, key


def test_refuses_a_non_default_dropped_key_in_the_machine_file(machine, capsys):
    cfg = _fixture("machine.config.json")
    cfg["notify"]["questionTypes"] = ["question"]
    original = (json.dumps(cfg, indent=2) + "\n").encode("utf-8")
    _write(machine, original)

    code = crew_migrate.main(["--global", "--apply"])

    said = capsys.readouterr()
    assert code == 1
    assert _read(machine) == original
    assert not _backups(os.path.dirname(machine), repo=False)
    assert "notify.questionTypes holds a non-default value" in said.out + said.err
    assert "crew_state.NOTIFY_QUESTION_TYPES" in said.out + said.err


def test_the_machine_default_for_shell_route_mode_is_auto(machine, capsys):
    default = {"shellRoute": {"mode": "auto"}, "pm": {"authority": "report-only"}}
    _write(machine, default)
    assert crew_migrate.main(["--global", "--apply"]) == 0
    assert json.loads(_read(machine)) == {"pm": {"authority": "report-only"}}
    capsys.readouterr()

    _write(machine, {"shellRoute": {"mode": None}})
    assert crew_migrate.main(["--global", "--apply"]) == 1
    assert "shellRoute.mode holds a non-default value" in capsys.readouterr().out


def test_accept_dropped_records_backup(tmp_path, capsys):
    cfg = _fixture("repo.config.json")
    cfg["sdp"]["portal"] = "https://portal.example"
    cfg["worktree"]["root"] = "/elsewhere"
    original = (json.dumps(cfg, indent=2) + "\n").encode("utf-8")
    root = _repo(tmp_path, original)

    code = crew_migrate.main(["--root", root, "--apply", "--accept-dropped", "sdp.portal",
                              "--accept-dropped", "worktree.root"])

    out = capsys.readouterr().out
    after = _config(root)
    (backup,) = _backups(root)
    manifest = json.loads(_read(os.path.join(backup, "manifest.json")))
    assert code == 0
    assert "sdp" not in after and "worktree" not in after
    assert manifest["acceptedDropped"] == ["sdp.portal", "worktree.root"]
    assert _read(os.path.join(backup, "sources", ".crew", "config.json")) == original
    assert "removed at your request" in out
    assert "sdp.portal (now crew_state.SDP_PORTAL)" in out
    crew_migrate.main(["--root", root, "--rollback", backup])
    assert _read(os.path.join(root, ".crew", "config.json")) == original


def test_accept_dropped_covers_only_the_keys_it_names(tmp_path, capsys):
    cfg = _fixture("repo.config.json")
    cfg["sdp"]["portal"] = "https://portal.example"
    cfg["worktree"]["root"] = "/elsewhere"
    root = _repo(tmp_path, cfg)
    before = _snapshot(root)

    code = crew_migrate.main(["--root", root, "--apply", "--accept-dropped", "sdp.portal"])

    out = capsys.readouterr().out
    assert code == 1
    assert _snapshot(root) == before
    assert "worktree.root holds a non-default value" in out
    assert "sdp.portal holds a non-default value" not in out


def test_accept_dropped_records_backup_for_the_machine_file(machine, capsys):
    cfg = _fixture("machine.config.json")
    cfg["notify"]["questionTypes"] = ["question"]
    original = (json.dumps(cfg, indent=2) + "\n").encode("utf-8")
    _write(machine, original)

    code = crew_migrate.main(["--global", "--apply", "--accept-dropped", "notify.questionTypes"])

    (backup,) = _backups(os.path.dirname(machine), repo=False)
    manifest = json.loads(_read(os.path.join(backup, "manifest.json")))
    assert code == 0
    assert "questionTypes" not in json.loads(_read(machine))["notify"]
    assert manifest["acceptedDropped"] == ["notify.questionTypes"]
    assert _read(os.path.join(backup, "sources", "config.json")) == original
    assert "removed at your request" in capsys.readouterr().out
    assert crew_migrate.main(["--global", "--rollback", backup]) == 0
    assert _read(machine) == original


@pytest.mark.parametrize("name", ["tier", "roles", "not.a.key", "guards.profile"])
def test_accept_dropped_refuses_a_name_migrate_does_not_drop(tmp_path, capsys, name):
    root = _repo(tmp_path, _fixture("repo.config.json"))
    before = _snapshot(root)

    code = crew_migrate.main(["--root", root, "--apply", "--accept-dropped", name])

    assert code == 1
    assert _snapshot(root) == before
    assert "which is not a key migrate drops" in capsys.readouterr().err


def test_a_refused_run_through_crew_upgrade_writes_nothing(tmp_path, capsys):
    cfg = _fixture("repo.config.json")
    cfg["schema"] = 3
    cfg["sdp"]["portal"] = "https://portal.example"
    original = (json.dumps(cfg, indent=2) + "\n").encode("utf-8")
    root = _repo(tmp_path, original)
    before = _snapshot(root)

    result = crew_upgrade.run(root, {})

    assert result["status"] == "refused: dropped keys"
    assert "sdp.portal" in result["report"]
    assert _snapshot(root) == before
    assert crew_upgrade.main(["--root", root]) == 1
    assert "refused: dropped keys" in capsys.readouterr().out


# ---------------------------------------------------------------- rollback

@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_rollback_byte_identical(tmp_path, machine, layer):
    if layer == "repo":
        original = _fixture_bytes("repo.config.json")
        root = _repo(tmp_path, original)
        target, args = os.path.join(root, ".crew", "config.json"), ["--root", root]

        def backups():
            return _backups(root)
    else:
        original = _fixture_bytes("machine.config.json")
        _write(machine, original)
        target, args = machine, ["--global"]

        def backups():
            return _backups(os.path.dirname(machine), repo=False)
    crew_migrate.main(args + ["--apply"])
    assert _read(target) != original
    (backup,) = backups()

    assert crew_migrate.main(args + ["--rollback", backup]) == 0

    assert _read(target) == original
    assert crew_migrate.main(args + ["--rollback", backup]) == 0
    assert _read(target) == original


def test_rollback_refuses_a_file_edited_since_apply(machine, capsys):
    _write(machine, _fixture_bytes("machine.config.json"))
    crew_migrate.main(["--global", "--apply"])
    (backup,) = _backups(os.path.dirname(machine), repo=False)
    edited = _read(machine) + b" "
    _write(machine, edited)

    code = crew_migrate.main(["--global", "--rollback", backup])

    assert code == 1
    assert _read(machine) == edited
    assert "edited since apply" in capsys.readouterr().err


def test_rollback_holds_the_config_writer_lock_and_refuses_while_it_is_held(machine, capsys):
    original = _fixture_bytes("machine.config.json")
    _write(machine, original)
    crew_migrate.main(["--global", "--apply"])
    (backup,) = _backups(os.path.dirname(machine), repo=False)
    migrated = _read(machine)

    with crew_config_files.machine_lock(machine):
        code = crew_migrate.main(["--global", "--rollback", backup])

    assert code == 1
    assert _read(machine) == migrated
    assert "nothing written" in capsys.readouterr().err
    assert crew_migrate.main(["--global", "--rollback", backup]) == 0
    assert _read(machine) == original


def test_rollback_refuses_a_backup_from_the_other_scope(tmp_path, machine, capsys):
    _write(machine, _fixture_bytes("machine.config.json"))
    crew_migrate.main(["--global", "--apply"])
    (global_backup,) = _backups(os.path.dirname(machine), repo=False)
    root = _repo(tmp_path, _fixture_bytes("repo.config.json"))
    crew_migrate.main(["--root", root, "--apply"])
    (repo_backup,) = _backups(root)
    capsys.readouterr()
    # each backup copied into the other scope's folder, so only the manifest's
    # own `scope` can tell them apart
    stray_repo = os.path.join(os.path.dirname(machine), "backups", "migrate-stray-repo")
    stray_global = os.path.join(root, ".crew", "backups", "migrate-stray-global")
    shutil.copytree(repo_backup, stray_repo)
    shutil.copytree(global_backup, stray_global)
    machine_before = _read(machine)

    assert crew_migrate.main(["--global", "--rollback", stray_repo]) == 1
    assert "is a repo backup; roll it back without --global" in capsys.readouterr().err
    assert crew_migrate.main(["--root", root, "--rollback", stray_global]) == 1
    assert "is a global backup; pass --global to roll it back" in capsys.readouterr().err
    assert _read(machine) == machine_before
    assert crew_migrate.main(["--root", root, "--rollback", repo_backup]) == 0
    assert crew_migrate.main(["--global", "--rollback", global_backup]) == 0


def test_rollback_refuses_a_folder_outside_the_backups(tmp_path, machine, capsys):
    _write(machine, _fixture_bytes("machine.config.json"))
    crew_migrate.main(["--global", "--apply"])
    root = _repo(tmp_path, _fixture_bytes("repo.config.json"))
    crew_migrate.main(["--root", root, "--apply"])
    (repo_backup,) = _backups(root)
    capsys.readouterr()

    assert crew_migrate.main(["--global", "--rollback", repo_backup]) == 1
    assert "is not a backup under backups; refused" in capsys.readouterr().err


# ---------------------------------------------------------------- unknown keys

def test_unknown_keys_carried(machine, capsys):
    cfg = _fixture("machine.config.json")
    cfg["platform"] = {"os": "linux", "tools": {"git": True}}
    cfg["somethingNew"] = {"a": [1, 2]}
    _write(machine, cfg)

    code = crew_migrate.main(["--global", "--apply"])

    after = json.loads(_read(machine))
    out = capsys.readouterr().out
    assert code == 0
    assert after["platform"] == {"os": "linux", "tools": {"git": True}}
    assert after["somethingNew"] == {"a": [1, 2]}
    for key in ("qa.pinsResetNote", "dev.pinsResetNote", "platform.tools", "somethingNew"):
        assert f"unknown  {key} " in out, key
    assert "unknown  platform.tools.git" not in out


def test_unknown_keys_are_never_deleted_from_the_repo_layer(tmp_path):
    before = _fixture("repo.config.json")
    root = _repo(tmp_path, before)

    crew_migrate.main(["--root", root, "--apply"])

    after = _config(root)
    assert after["platform"]["tools"] == before["platform"]["tools"]
    assert after["qa"]["tssPinsNote"] == before["qa"]["tssPinsNote"]


# ---------------------------------------------------------------- profile selection

TABLE = [
    ({}, "off", {}),
    (crew_guards.PROFILE_MAP["standard"], "standard", {}),
    (crew_guards.PROFILE_MAP["strict"], "strict", {}),
    ({**crew_guards.PROFILE_MAP["standard"], "forcePush": "allow"}, "standard",
     {"forcePush": "allow"}),
    ({**crew_guards.PROFILE_MAP["strict"], "prodServer": "read"}, "strict", {"prodServer": "read"}),
    ({"cloudGuard": "block"}, "off", {"cloudGuard": "block"}),
    # ties: the first of off, standard, strict wins
    ({"adminMerge": "block", "roleWrites": "block", "cloudGuard": "report", "envGuard": "off"},
     "off", {"roleWrites": "block", "cloudGuard": "report"}),
    ({"adminMerge": "block", "roleWrites": "report", "cloudGuard": "block", "envGuard": "report"},
     "standard", {"adminMerge": "block", "envGuard": "report"}),
    ({"adminMerge": "block", "roleWrites": "report", "cloudGuard": "report", "envGuard": "off"},
     "off", {"roleWrites": "report", "cloudGuard": "report"}),
    ({"adminMerge": "block", "roleWrites": "report", "cloudGuard": "report", "envGuard": "report"},
     "off", {"roleWrites": "report", "cloudGuard": "report", "envGuard": "report"}),
]


@pytest.mark.parametrize("changes,profile,overrides", TABLE)
def test_profile_selection_takes_the_fewest_overrides_and_breaks_ties_off_standard_strict(
        changes, profile, overrides):
    values = {**crew_guards.GUARD_DEFAULTS, **changes}

    got = crew_upgrade.choose_profile(values)

    assert got == (profile, overrides)
    table = crew_guards.PROFILE_MAP[got[0]]
    assert {**table, **got[1]} == values


def test_profile_selection_is_minimal_over_every_combination_of_the_profile_diffs():
    free = ("adminMerge", "roleWrites", "cloudGuard", "envGuard")
    for combo in itertools.product(*[crew_guards.guard_tiers(n)[0] for n in free]):
        values = {**crew_guards.GUARD_DEFAULTS, **dict(zip(free, combo))}
        profile, overrides = crew_upgrade.choose_profile(values)
        distances = [sum(1 for n in NAMES if values[n] != crew_guards.PROFILE_MAP[p][n])
                     for p in ("off", "standard", "strict")]
        assert len(overrides) == min(distances), combo
        assert ("off", "standard", "strict")[distances.index(min(distances))] == profile, combo


# ---------------------------------------------------------------- orientation and equivalence

def _layer(**guards):
    return {"guards": dict(guards)}


def _migrated(layer_cfg):
    out, _notes = crew_upgrade.upgrade_config(copy.deepcopy(layer_cfg))
    return out


def test_legacy_and_override_in_one_layer_migrate_to_the_narrower():
    for legacy, override, expected in (("block", "allow", "block"), ("allow", "block", "block"),
                                       ("ask", "allow", "ask"), ("allow", "ask", "ask")):
        layer = {"guards": {"forcePush": legacy, "overrides": {"forcePush": override}}}
        before = crew_guards.layer_guard_value(layer, "forcePush")

        after = crew_guards.layer_guard_value(_migrated(layer), "forcePush")

        assert before == after == expected, (legacy, override)
        assert "forcePush" not in _migrated(layer)["guards"]


def test_legacy_and_a_profile_value_in_one_layer_migrate_to_the_narrower():
    layer = {"guards": {"profile": "standard", "adminMerge": "allow"}}

    out = _migrated(layer)

    assert crew_guards.layer_guard_value(layer, "adminMerge") == "ask"
    assert crew_guards.layer_guard_value(out, "adminMerge") == "ask"
    assert out["guards"] == {"profile": "standard", "overrides": {}}


MALFORMED = ["bogus", 5, ["block"], {"x": 1}, True, "", "BLOCK ", "Allow"]


@pytest.mark.parametrize("bad", MALFORMED)
def test_a_malformed_legacy_value_keeps_the_value_the_resolver_gave_it(bad):
    for name in NAMES:
        layer = {"guards": {name: bad}}
        before = crew_guards.layer_guard_value(layer, name)

        out = _migrated(layer)

        assert crew_guards.layer_guard_value(out, name) == before, name
        assert _values(out) == _values(layer), name
        assert name not in out["guards"]


@pytest.mark.parametrize("bad_profile", ["bogus", 3, ["standard"], {"a": 1}])
def test_a_malformed_profile_is_left_as_written_and_keeps_the_floor(bad_profile):
    layer = {"guards": {"profile": bad_profile, "overrides": {"cloudGuard": "off"}}}

    out, notes = crew_upgrade.upgrade_config(copy.deepcopy(layer))

    assert out["guards"] == layer["guards"]
    assert "guards.profile" in notes["unmigrated"]
    assert notes["schemaStamped"] is False
    assert _values(out) == _values(layer)
    assert all(_values(out)[n] == crew_guards.guard_tiers(n)[0][0] for n in NAMES)


def test_a_malformed_overrides_table_is_left_as_written_and_keeps_the_floor():
    layer = {"guards": {"profile": "off", "overrides": "oops"}}

    out, notes = crew_upgrade.upgrade_config(copy.deepcopy(layer))

    assert out["guards"] == layer["guards"]
    assert "guards.overrides" in notes["unmigrated"]
    assert _values(out) == _values(layer)


@pytest.mark.parametrize("bad", ["oops", ["block"], 5, True, None])
def test_a_guards_value_that_is_not_an_object_is_left_alone_and_blocks_the_stamp(bad):
    layer = {"guards": bad}

    out, notes = crew_upgrade.upgrade_config(copy.deepcopy(layer))

    assert out["guards"] == bad
    assert "guards" in notes["unmigrated"]
    assert notes["schemaStamped"] is False
    assert "schema" not in out


def test_a_non_object_guards_value_is_a_conflict_in_both_layers(tmp_path, machine, capsys):
    root = _repo(tmp_path, {"schema": 7, "guards": "oops"})
    _write(machine, {"guards": ["block"]})
    before = _snapshot(root, os.path.dirname(machine))

    assert crew_migrate.main(["--root", root, "--apply"]) == 1
    assert crew_migrate.main(["--global", "--apply"]) == 1

    assert _snapshot(root, os.path.dirname(machine)) == before
    assert "guards" in capsys.readouterr().out


def test_unknown_keys_inside_guards_are_carried():
    layer = {"guards": {"forcePush": "ask", "note": "keep me"}}

    out = _migrated(layer)

    assert out["guards"] == {"profile": "off", "overrides": {"forcePush": "ask"}, "note": "keep me"}


def test_a_guards_block_with_none_of_the_keys_is_left_as_written():
    out, notes = crew_upgrade.upgrade_config({"guards": {"note": "x"}})

    assert out["guards"] == {"note": "x"}
    assert notes["guardProfile"] is None


def test_no_guards_block_stays_absent():
    out, notes = crew_upgrade.upgrade_config({"qa": {"provider": "codex"}})

    assert "guards" not in out
    assert notes["guardProfile"] is None


def _guard_corpus():
    """Layers that exercise every tier of every guard, mixed and malformed."""
    layers = [{}, {"guards": {}}, _fixture("repo.config.json"), _fixture("machine.config.json")]
    for name in NAMES:
        for tier in crew_guards.guard_tiers(name)[0]:
            layers.append({"guards": {name: tier}})
            layers.append({"guards": {"overrides": {name: tier}}})
            layers.append({"guards": {"profile": "standard", "overrides": {name: tier}}})
            layers.append({"guards": {"profile": "strict", name: tier}})
        layers.append({"guards": {name: "bogus"}})
    for profile in crew_guards.GUARD_PROFILES:
        layers.append({"guards": {"profile": profile}})
    layers.append({"guards": {n: crew_guards.guard_tiers(n)[0][-1] for n in NAMES}})
    layers.append({"guards": {n: crew_guards.guard_tiers(n)[0][0] for n in NAMES}})
    layers.append({"guards": {"profile": "nonsense", "forcePush": "allow"}})
    return layers


def test_equivalence_on_fixture_corpus():
    corpus = _guard_corpus()
    migrated = []
    for layer in corpus:
        out, notes = crew_upgrade.upgrade_config(copy.deepcopy(layer))
        # an owner fixture carries a dropped key at a non-default value only
        # if the test says so; none of the corpus does
        assert notes["droppedNonDefault"] == []
        assert _values(out) == _values(layer), layer.get("guards")
        assert _carried(layer, out) == (True, {})
        assert notes["unmigrated"] or not any(name in out.get("guards", {}) for name in NAMES)
        migrated.append(out)
        glob, _ = crew_upgrade.upgrade_global(copy.deepcopy(layer))
        assert _values(glob) == _values(layer)
        assert _kept(glob) == _kept(layer)
    for (repo_before, repo_after), (mach_before, mach_after) in itertools.product(
            list(zip(corpus, migrated))[:40], list(zip(corpus, migrated))[:40]):
        assert _combined(repo_after, mach_after) == _combined(repo_before, mach_before)


def test_equivalence_through_the_real_resolver(tmp_path):
    """The same claim through `crew_config.resolve_guard`, the function the
    guards call, for the owner's two layers and a mixed pair."""
    import crew_config  # pylint: disable=import-outside-toplevel

    def resolve(repo_cfg, machine_cfg, name):
        root = _repo(tmp_path, repo_cfg, "r-" + name)
        gpath = str(tmp_path / ("g-" + name + ".json"))
        _write(gpath, machine_cfg)
        return crew_config.resolve_guard(root, name, gpath)

    pairs = [(_fixture("repo.config.json"), _fixture("machine.config.json")),
             (_fixture("repo.config.json"), {}), ({}, _fixture("machine.config.json")),
             ({"guards": {"forcePush": "ask", "overrides": {"forcePush": "allow"}}},
              {"guards": {"forcePush": "allow", "cloudGuard": "report"}})]
    for repo_cfg, machine_cfg in pairs:
        repo_after, _ = crew_upgrade.upgrade_config(copy.deepcopy(repo_cfg))
        machine_after, _ = crew_upgrade.upgrade_global(copy.deepcopy(machine_cfg))
        for name in NAMES:
            got = resolve(repo_after, machine_after, name)
            was = resolve(repo_cfg, machine_cfg, name)
            # `unmigrated` and `conflicts` are the legacy-key warnings: they
            # are exactly what the migration clears
            for key in ("unmigrated", "conflicts"):
                assert got[key] == [], (name, key)
                was.pop(key)
                got.pop(key)
            assert got == was, name


def test_migration_is_idempotent_for_both_layers():
    for layer in _guard_corpus():
        once, _ = crew_upgrade.upgrade_config(copy.deepcopy(layer))
        twice, notes = crew_upgrade.upgrade_config(copy.deepcopy(once))
        assert twice == once
        assert notes["removedDefault"] == notes["retiredRemoved"] == []
        glob_once, _ = crew_upgrade.upgrade_global(copy.deepcopy(layer))
        glob_twice, _ = crew_upgrade.upgrade_global(copy.deepcopy(glob_once))
        assert glob_twice == glob_once


def test_the_upgrade_does_not_edit_its_input():
    original = _fixture("repo.config.json")
    frozen = copy.deepcopy(original)

    crew_upgrade.upgrade_config(original)
    crew_upgrade.upgrade_global(original)

    assert original == frozen


# ---------------------------------------------------------------- the dropped keys, all 60

def test_every_dropped_key_at_its_default_is_removed_without_a_conflict():
    for dotted, (default, _constant) in crew_dropped.DROPPED.items():
        cfg = {"keep": {"me": 1}}
        _put(cfg, dotted, copy.deepcopy(default))

        out, notes = crew_upgrade.upgrade_config(cfg)

        assert dotted in notes["removedDefault"] + notes["retiredRemoved"], dotted
        assert notes["droppedNonDefault"] == [], dotted
        assert not _has(out, dotted), dotted
        assert out["keep"] == {"me": 1}
        assert notes["schemaStamped"] is True, dotted


def test_every_dropped_key_at_a_non_default_value_is_a_conflict_naming_it():
    for dotted, (default, constant) in crew_dropped.DROPPED.items():
        if constant.startswith("retired:"):
            continue
        cfg = {}
        _put(cfg, dotted, _non_default(default))

        out, notes = crew_upgrade.upgrade_config(copy.deepcopy(cfg))

        assert notes["droppedNonDefault"] == [dotted], dotted
        assert crew_upgrade.refused_drops(notes) == [(dotted, constant)], dotted
        assert notes["schemaStamped"] is False, dotted
        assert "schema" not in out
        assert _has(out, dotted), dotted

        kept, accepted = crew_upgrade.upgrade_config(copy.deepcopy(cfg), [dotted])

        assert accepted["acceptedDropped"] == [dotted]
        assert crew_upgrade.refused_drops(accepted) == []
        assert accepted["schemaStamped"] is True
        assert not _has(kept, dotted), dotted


def test_tier_and_roles_are_removed_whatever_they_hold():
    cfg = {"tier": 3, "roles": ["explorer", "wharrgarbl"], "tracker": "files"}

    out, notes = crew_upgrade.upgrade_config(cfg)

    assert out["tracker"] == "files"
    assert out["schema"] == crew_state.SCHEMA_CURRENT
    assert "tier" not in out and "roles" not in out
    assert notes["retiredRemoved"] == ["tier", "roles"]
    assert notes["droppedNonDefault"] == []
    assert crew_upgrade.upgrade_global({"tier": 1})[0] == {}


def test_a_value_that_only_equals_the_default_in_python_is_not_the_default():
    for key, value in (("graph.enabled", 1), ("sdp.closeOnDone", 0), ("context.keepTranscripts", 5.0),
                       ("context.autoWrapUp", 1), ("pm.mode", "Adaptive")):
        cfg = {}
        _put(cfg, key, value)

        _out, notes = crew_upgrade.upgrade_config(cfg)

        assert notes["droppedNonDefault"] == [key], key


def test_a_block_the_removals_empty_goes_and_a_block_with_other_keys_stays():
    cfg = {"docs": {"theme": None, "reportTheme": None}, "obsidian": {
        "board": "Board.md", "columns": {"backlog": "Backlog"}, "vaultPath": "/v"},
        "graph": {"enabled": True, "out": "graphify-out"}, "worktree": {}}

    out, _notes = crew_upgrade.upgrade_config(cfg)

    assert "docs" not in out
    assert out["obsidian"] == {"vaultPath": "/v"}
    assert out["graph"] == {"out": "graphify-out"}
    assert out["worktree"] == {}


def test_the_machine_pass_does_not_seed_blocks_or_stamp_a_schema():
    out, notes = crew_upgrade.upgrade_global({"notify": {"provider": "telegram"}})

    assert out == {"notify": {"provider": "telegram"}}
    assert notes["guardProfile"] is None


def test_the_report_leaves_out_the_removed_ladder_and_theme_lines():
    _, notes = crew_upgrade.upgrade_config({"tier": 2, "roles": ["explorer"],
                                            "docs": {"theme": "neutral"}})
    said = "\n".join(crew_upgrade._config_lines(notes))  # pylint: disable=protected-access

    assert "roles added" not in said
    assert "tier:" not in said
    assert "docs.theme was" not in said
    assert "REFUSED" in said and "docs.theme (now crew_state.DOCS_THEME)" in said


# ---------------------------------------------------------------- the files themselves

@pytest.mark.parametrize("raw,why", [(b"", "not valid JSON"), (b"   \n", "not valid JSON"),
                                     (b"[1, 2]", "not a JSON object"),
                                     (b"{not json", "not valid JSON"), (b'"text"', "not a JSON object")])
def test_an_unusable_repo_file_is_refused_and_nothing_is_written(tmp_path, capsys, raw, why):
    root = _repo(tmp_path, raw)
    before = _snapshot(root)

    code = crew_migrate.main(["--root", root, "--apply"])

    assert code == 1
    assert _snapshot(root) == before
    assert why in capsys.readouterr().err


@pytest.mark.parametrize("raw,why", [(b"", "not valid JSON"), (b"[1, 2]", "not a JSON object"),
                                     (b"{not json", "not valid JSON"), (b"null", "not a JSON object")])
def test_an_unusable_machine_file_is_refused_and_nothing_is_written(machine, capsys, raw, why):
    _write(machine, raw)

    code = crew_migrate.main(["--global", "--apply"])

    assert code == 1
    assert _read(machine) == raw
    assert not _backups(os.path.dirname(machine), repo=False)
    assert why in capsys.readouterr().err


def test_a_machine_file_that_is_a_symlink_is_refused(tmp_path, machine, capsys):
    target = tmp_path / "elsewhere.json"
    target.write_bytes(_fixture_bytes("machine.config.json"))
    os.makedirs(os.path.dirname(machine))
    try:
        os.symlink(str(target), machine)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")

    code = crew_migrate.main(["--global", "--apply"])

    assert code == 1
    assert target.read_bytes() == _fixture_bytes("machine.config.json")
    assert "symlink" in capsys.readouterr().err


def test_an_interrupted_global_apply_blocks_the_next_run(machine, capsys):
    _write(machine, _fixture_bytes("machine.config.json"))
    stuck = os.path.join(os.path.dirname(machine), "backups", "migrate-20260101T000000Z")
    _write(os.path.join(stuck, "manifest.json"), {"state": "committing", "scope": "global"})
    before = _read(machine)

    code = crew_migrate.main(["--global", "--apply"])

    assert code == 1
    assert _read(machine) == before
    assert "interrupted apply at" in capsys.readouterr().out


# ---------------------------------------------------------------- guards.overrides is never silently reshaped

def test_unknown_guard_names_in_overrides_are_carried_and_reported():
    before = {"guards": {"profile": "off", "overrides": {"futureGuard": "allow"}}}

    out, notes = crew_upgrade.upgrade_global(before)

    assert out["guards"]["overrides"]["futureGuard"] == "allow"
    assert notes["unknown"] == ["guards.overrides.futureGuard"]
    assert notes["unmigrated"] == []


def test_unknown_guard_names_survive_a_rewrite_of_legacy_keys():
    before = {"guards": {"forcePush": "allow", "overrides": {"futureGuard": "allow"}}}

    out, notes = crew_upgrade.upgrade_global(before)

    assert out["guards"]["overrides"] == {"forcePush": "allow", "futureGuard": "allow"}
    assert notes["unknown"] == ["guards.overrides.futureGuard"]


@pytest.mark.parametrize("guards", [
    {"profile": "off", "overrides": ["terraformApply"]},
    {"profile": "off", "overrides": "allow"},
    {"overrides": 3, "forcePush": "allow"},
    {"profile": "bogus", "forcePush": "allow"},
    {"profile": 7, "overrides": {"forcePush": "allow"}},
    "strict",
    ["off"],
])
def test_a_malformed_guards_block_is_left_as_written_and_blocks_the_stamp(guards):
    before = {"guards": guards}

    out, notes = crew_upgrade.upgrade_global(before)

    assert out["guards"] == guards
    assert notes["unmigrated"]
    assert notes["guardProfile"] is None


def test_a_malformed_overrides_table_blocks_the_repo_stamp():
    before = {"schema": 7, "guards": {"profile": "off", "overrides": ["x"]}}

    out, notes = crew_upgrade.upgrade_config(before)

    assert out["guards"] == before["guards"]
    assert "guards.overrides" in notes["unmigrated"]
    assert notes["schemaStamped"] is False


def test_a_malformed_overrides_table_in_the_machine_file_is_a_conflict(machine, capsys):
    original = {"guards": {"profile": "off", "overrides": ["x"]}, "tier": "full"}
    _write(machine, original)
    before = _read(machine)

    code = crew_migrate.main(["--global", "--apply"])

    assert code == 1
    assert _read(machine) == before
    assert "guards.overrides" in capsys.readouterr().out


def test_unknown_guard_names_are_listed_by_the_global_preview(machine, capsys):
    _write(machine, {"guards": {"profile": "off", "overrides": {"futureGuard": "allow"}}})

    crew_migrate.main(["--global", "--apply"])

    assert "unknown  guards.overrides.futureGuard " in capsys.readouterr().out
    assert json.loads(_read(machine))["guards"]["overrides"] == {"futureGuard": "allow"}


GUARD_LAYERS = [
    {"guards": {"forcePush": "allow", "adminMerge": "block", "cloudGuard": "report"}},
    {"guards": {"profile": "strict", "forcePush": "allow"}},
    {"guards": {"profile": "standard", "overrides": {"prodServer": "read", "futureGuard": "x"},
                "cloudGuard": "block"}},
    {"guards": {"overrides": {"terraformApply": "bogus"}}},
    {"guards": {"terraformApply": "bogus", "envGuard": "off"}},
    {"guards": {"profile": "off", "overrides": {"futureGuard": "allow"}, "extra": 1}},
]


@pytest.mark.parametrize("layer", GUARD_LAYERS)
def test_every_guard_keeps_its_value_through_the_rewrite(layer):
    def read(cfg):
        return {name: crew_guards.GUARD_DEFAULTS[name] if value is None else value
                for name in NAMES
                for value in [crew_guards.layer_guard_value(cfg, name)]}
    before = read(layer)

    out, _notes = crew_upgrade.upgrade_global(layer)

    after = read(out)
    assert after == before
    assert not [name for name in NAMES if name in out["guards"]]


# ---------------------------------------------------------------- the apply takes the config writer's lock

def _edit(path, key, value, wait=None):

    def mutate(parsed):
        parsed[key] = value
        return parsed
    crew_config_files.update_json(path, mutate, wait=wait)


def _between_check_and_replace(monkeypatch, action):
    """Run `action()` once, right after the real pre-state check passed and
    before the file is replaced: the window a concurrent writer needs."""
    real = crew_migrate._check_pre_state  # pylint: disable=protected-access
    calls = []

    def check(root, item):
        real(root, item)
        if not calls:
            calls.append(item["path"])
            action()
    monkeypatch.setattr(crew_migrate, "_check_pre_state", check)
    return calls


def test_global_apply_holds_the_machine_lock_across_check_and_replace(machine, monkeypatch):
    _write(machine, _fixture_bytes("machine.config.json"))
    seen = {}

    def action():
        try:
            _edit(machine, "concurrent", "edit", wait=0.05)
            seen["outcome"] = "wrote"
        except crew_config_files.Busy:
            seen["outcome"] = "busy"
    _between_check_and_replace(monkeypatch, action)

    code = crew_migrate.main(["--global", "--apply"])

    assert code == 0
    assert seen["outcome"] == "busy"
    assert "concurrent" not in json.loads(_read(machine))
    assert not os.path.exists(machine + ".lock")


def test_global_apply_does_not_lose_a_writer_that_arrives_mid_apply(machine, monkeypatch):
    import threading  # pylint: disable=import-outside-toplevel
    _write(machine, _fixture_bytes("machine.config.json"))
    writer = threading.Thread(target=_edit, args=(machine, "concurrent", "edit", 20))

    def action():
        writer.start()
        writer.join(0.5)
    _between_check_and_replace(monkeypatch, action)

    code = crew_migrate.main(["--global", "--apply"])
    writer.join(20)

    after = json.loads(_read(machine))
    assert code == 0
    assert after["concurrent"] == "edit"
    assert "tier" not in after
    assert after["guards"]["profile"]


def test_repo_apply_does_not_lose_a_writer_that_arrives_mid_apply(tmp_path, monkeypatch):
    import threading  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, _fixture("repo.config.json"))
    path = os.path.join(root, ".crew", "config.json")
    writer = threading.Thread(target=_edit, args=(path, "concurrent", "edit", 20))

    def action():
        writer.start()
        writer.join(0.5)
    _between_check_and_replace(monkeypatch, action)

    code = crew_migrate.main(["--root", root, "--apply"])
    writer.join(20)

    assert code == 0
    assert _config(root)["concurrent"] == "edit"
    assert not os.path.exists(path + ".lock")


def test_global_apply_refuses_a_file_edited_after_the_preview(machine, capsys):
    _write(machine, _fixture_bytes("machine.config.json"))
    plan = crew_migrate.build_global_plan(machine)
    _edit(machine, "concurrent", "edit")
    edited = _read(machine)

    with pytest.raises(crew_migrate.MigrateError) as caught:
        crew_migrate.apply_plan(plan)

    assert "config.json changed since the plan was built" in str(caught.value)
    assert _read(machine) == edited
    assert not os.path.exists(machine + ".lock")
    assert [n for n in os.listdir(os.path.dirname(machine)) if n.endswith(".tmp")] == []


def test_the_lock_is_released_when_the_replace_fails(machine, monkeypatch):
    _write(machine, _fixture_bytes("machine.config.json"))
    real_replace = os.replace

    def replace(src, dst, *args, **kwargs):
        if os.path.basename(dst) == "config.json":
            raise OSError("injected")
        return real_replace(src, dst, *args, **kwargs)
    monkeypatch.setattr(crew_migrate.os, "replace", replace)

    with pytest.raises(OSError):
        crew_migrate.main(["--global", "--apply"])

    assert not os.path.exists(machine + ".lock")


def test_a_held_machine_lock_is_a_refusal_with_nothing_written(machine, capsys, monkeypatch):
    _write(machine, _fixture_bytes("machine.config.json"))
    before = _read(machine)
    monkeypatch.setattr(crew_config_files, "LOCK_WAIT_SECONDS", 0.1)

    with crew_config_files.machine_lock(machine):
        code = crew_migrate.main(["--global", "--apply"])

    assert code == 1
    assert _read(machine) == before
    assert "config.json.lock" in capsys.readouterr().err


def test_a_schema_8_repo_still_carrying_a_legacy_guard_key_is_rewritten(tmp_path):
    root = _repo(tmp_path, json.dumps({"schema": 8, "guards": {"forcePush": "block"}}).encode())

    code = crew_migrate.main(["--root", root, "--apply"])

    assert code == 0
    assert "forcePush" not in _config(root).get("guards", {})


def test_an_unreadable_machine_config_is_a_conflict_not_a_traceback(machine, capsys):
    os.makedirs(machine)

    code = crew_migrate.main(["--global", "--preview"])

    assert code == 1
    assert "cannot read" in capsys.readouterr().err
