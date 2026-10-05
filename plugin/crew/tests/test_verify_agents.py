"""`verify_agents.py`: which agents `.crew/verify.json` names that are not
installed on this machine (T-0065, item 3).

A false "installed" is the defect: it reproduces the silent under-review that
`/crew:review` warns about. So every source a name could come from must be
read cleanly before the name is called `missing`, and a source that will not
parse makes the names it could have supplied `unknown` (exit 2), never `ok`.

Every test points `HOME` and `CLAUDE_CONFIG_DIR` at its own `tmp_path`, so no
test reads the real `~/.claude`.
"""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import verify_agents


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _agent(directory, stem, name=None):
    name = stem if name is None else name
    _write(os.path.join(str(directory), f"{stem}.md"),
           f"---\nname: {name}\ndescription: test agent\n---\n\nbody\n")


@pytest.fixture(name="home")
def _home_fixture(tmp_path, monkeypatch):
    home = tmp_path / "home"
    config = home / ".claude"
    config.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    return config


def _home(config, user_agents=(), plugins=None, enabled=None):
    """`plugins` maps `<plugin>@<mkt>` to the agent stems its installPath holds;
    `enabled` is the user-scope `enabledPlugins`."""
    for name in user_agents:
        _agent(config / "agents", name)
    registry = {"version": 2, "plugins": {}}
    for key, agents in (plugins or {}).items():
        install = config / "plugins" / "cache" / key.replace("@", "-")
        for name in agents:
            _agent(install / "agents", name)
        registry["plugins"][key] = [{"installPath": str(install), "version": "1.0.0"}]
    _write(config / "plugins" / "installed_plugins.json", json.dumps(registry))
    if enabled is not None:
        _write(config / "settings.json", json.dumps({"enabledPlugins": enabled}))


def _repo(tmp_path, agents, paths=("**/*.php",)):
    root = tmp_path / "repo"
    rules = [{"paths": list(paths), "run": ["true"], "agents": list(agents)}]
    _write(root / ".crew" / "verify.json", json.dumps({"version": 1, "rules": rules}))
    return root


def _main(root, capsys, *extra):
    code = verify_agents.main(["--root", str(root), "--check", *extra])
    return code, capsys.readouterr().out


def test_missing_agent_is_named(tmp_path, home, capsys):
    _home(home)
    root = _repo(tmp_path, ["php-developer"])

    code, out = _main(root, capsys)

    assert code == 1
    assert "php-developer" in out and "**/*.php" in out


@pytest.mark.parametrize("name", ["security", "crew:reviewer", "sql-pro", "dba",
                                  "voltagent:security-auditor", "security-auditor"])
def test_installed_agents_resolve(tmp_path, home, capsys, name):
    _home(home, user_agents=["sql-pro"], plugins={"voltagent@mkt": ["security-auditor"]},
          enabled={"voltagent@mkt": True})
    root = _repo(tmp_path, [name])
    _agent(root / ".claude" / "agents", "dba")

    code, out = _main(root, capsys)

    assert code == 0, out


def test_frontmatter_name_wins_over_file_stem(tmp_path, home, capsys):
    _home(home)
    _agent(home / "agents", "x", name="y")

    assert _main(_repo(tmp_path, ["y"]), capsys)[0] == 0
    assert _main(_repo(tmp_path, ["x"]), capsys)[0] == 1


@pytest.mark.parametrize("case", ["disabled-at-a-narrower-scope", "not-in-the-registry"])
def test_disabled_or_unregistered_plugin_agent_is_missing(tmp_path, home, capsys, case):
    _home(home, plugins={"voltagent@mkt": ["security-auditor"]}, enabled={"voltagent@mkt": True})
    if case == "disabled-at-a-narrower-scope":
        name = "voltagent:security-auditor"
        root = _repo(tmp_path, [name])
        _write(root / ".claude" / "settings.local.json",
               json.dumps({"enabledPlugins": {"voltagent@mkt": False}}))
    else:
        name = "other:thing"
        root = _repo(tmp_path, [name])

    code, out = _main(root, capsys)

    assert code == 1, out
    assert name in out


@pytest.mark.parametrize("source", ["registry", "user-settings", "verify-json"])
def test_unknowns_never_read_as_installed(tmp_path, home, capsys, source):
    _home(home, plugins={"voltagent@mkt": ["security-auditor"]}, enabled={"voltagent@mkt": True})
    root = _repo(tmp_path, ["voltagent:security-auditor"])
    if source == "registry":
        _write(home / "plugins" / "installed_plugins.json", "{not json")
    elif source == "user-settings":
        _write(home / "settings.json", "{not json")
    else:
        _write(root / ".crew" / "verify.json", "{not json")

    code, out = _main(root, capsys)

    assert code == 2, out
    assert "unknown" in out.lower()


@pytest.mark.parametrize("data", ['{"rules": {"r": {"agents": ["php-developer"]}}}',
                                  '["php-developer"]', '{"rules": "php-developer"}',
                                  '{"rules": [{"agents": "php-developer"}]}',
                                  '{"rules": [{"agents": ["php-developer", 7]}]}',
                                  '{"rules": ["php-developer"]}',
                                  '{"rules": [{"agents": ["php-developer"], "paths": 7}]}',
                                  '{"rules": [{"agents": ["php-developer"], "paths": "src"}]}',
                                  'null'])
def test_a_verify_map_whose_shape_cannot_be_read_is_unknown(tmp_path, home, capsys, data):
    _home(home)
    root = _repo(tmp_path, ["php-developer"])
    _write(root / ".crew" / "verify.json", data)

    code, out = _main(root, capsys)

    assert code == 2, out
    assert "unknown" in out.lower() and "no agents named" not in out


def test_a_registry_entry_that_is_not_a_list_is_unknown_not_missing(tmp_path, home, capsys):
    _home(home, enabled={"voltagent@mkt": True})
    _write(home / "plugins" / "installed_plugins.json",
           json.dumps({"version": 2, "plugins": {"voltagent@mkt": {"installPath": "/x"}}}))

    code, out = _main(_repo(tmp_path, ["voltagent:security-auditor"]), capsys)

    assert code == 2, out
    assert "not a list of installs" in out


@pytest.mark.parametrize("install", ['"/x"', '{"version": "1.0.0"}', '{"installPath": 7}'])
def test_an_install_record_without_a_path_is_unknown_not_missing(tmp_path, home, capsys,
                                                                 install):
    _home(home, enabled={"voltagent@mkt": True})
    _write(home / "plugins" / "installed_plugins.json",
           '{"version": 2, "plugins": {"voltagent@mkt": [' + install + ']}}')

    code, out = _main(_repo(tmp_path, ["voltagent:security-auditor"]), capsys)

    assert (code, "no installPath" in out) == (2, True), out


@pytest.mark.parametrize("where", ["registry", "user-settings"])
def test_a_json_null_source_is_unknown_not_absent(tmp_path, home, capsys, where):
    _home(home, plugins={"voltagent@mkt": ["security-auditor"]}, enabled={"voltagent@mkt": True})
    target = (home / "plugins" / "installed_plugins.json" if where == "registry"
              else home / "settings.json")
    _write(target, "null")

    code, out = _main(_repo(tmp_path, ["voltagent:security-auditor"]), capsys)

    assert (code, "MISSING" in out) == (2, False), out


def test_an_install_path_os_cannot_take_is_unknown_not_a_crash(tmp_path, home, capsys):
    _home(home, enabled={"voltagent@mkt": True})
    _write(home / "plugins" / "installed_plugins.json",
           '{"version": 2, "plugins": {"voltagent@mkt": [{"installPath": "bad\\u0000path"}]}}')

    code, out = _main(_repo(tmp_path, ["voltagent:security-auditor"]), capsys)

    assert (code, "ValueError" in out) == (2, True), out


def test_crew_roles_resolve_even_when_registry_unreadable(tmp_path, home, capsys):
    _home(home)
    _write(home / "plugins" / "installed_plugins.json", "{not json")

    assert _main(_repo(tmp_path, ["security", "crew:explorer"]), capsys)[0] == 0


def test_no_agents_named_is_ok(tmp_path, home, capsys):
    _home(home)
    root = tmp_path / "repo"
    _write(root / ".crew" / "verify.json", json.dumps({"rules": [{"paths": ["**"], "run": ["true"]}]}))

    code, out = _main(root, capsys)

    assert code == 0
    assert "no agents named" in out


def test_json_output_lists_missing_with_paths(tmp_path, home, capsys):
    _home(home)
    root = _repo(tmp_path, ["php-developer"])

    code, out = _main(root, capsys, "--json")

    data = json.loads(out)
    assert code == 1
    assert data["status"] == "missing"
    assert data["missing"] == {"php-developer": ["**/*.php"]}
    assert "--agents" in " ".join(data["notChecked"])


def _stat_tree(*roots):
    out = {}
    for top in roots:
        for base, dirs, files in os.walk(str(top)):
            for name in dirs + files:
                path = os.path.join(base, name)
                stat = os.lstat(path)
                out[path] = (stat.st_mtime_ns, stat.st_size)
    return out


def test_check_is_read_only(tmp_path, home, capsys):
    _home(home, user_agents=["sql-pro"], plugins={"voltagent@mkt": ["security-auditor"]},
          enabled={"voltagent@mkt": True})
    root = _repo(tmp_path, ["php-developer", "sql-pro", "voltagent:security-auditor"])
    before = _stat_tree(root, home)

    _main(root, capsys)

    assert _stat_tree(root, home) == before
