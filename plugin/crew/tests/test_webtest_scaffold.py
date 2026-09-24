"""`webtest_scaffold.py`: dry run by default, creates only what is missing,
never overwrites, and never runs npx inside the suite (the agents runner is
injected)."""
import json
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import webtest_guard
import webtest_scaffold


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _read(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


def _snapshot(root):
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, root)] = fh.read()
    return out


@pytest.fixture(name="web")
def _web(tmp_path, monkeypatch):
    root = str(tmp_path / "web")
    os.makedirs(root)
    _write(root, "package.json", json.dumps({"devDependencies": {"@playwright/test": "1.63.0"}}))
    calls = []

    def _fake_npx(cmd, cwd):
        calls.append(cmd)
        return 0
    monkeypatch.setattr(webtest_scaffold.run_agents, "__defaults__", (_fake_npx,))
    return root, calls


@pytest.mark.parametrize("files, expected", [
    ({"playwright.config.js": ""}, "playwright.config.js"),
    ({"angular.json": "{}"}, "angular.json"),
    ({"package.json": json.dumps({"dependencies": {"playwright": "1"}})}, "package.json (playwright)"),
    ({"package.json": json.dumps({"dependencies": {"react": "1"}})}, None),
    ({"package.json": "not json"}, None),
    ({}, None),
])
def test_detect_names_why_this_is_a_web_project(tmp_path, files, expected):
    for rel, text in files.items():
        _write(str(tmp_path), rel, text)

    assert webtest_scaffold.detect(str(tmp_path)) == expected


def test_not_a_web_project_is_na_and_writes_nothing(tmp_path, capsys):
    code = webtest_scaffold.main(["--root", str(tmp_path), "--apply"])

    assert (code, os.listdir(tmp_path), "n/a" in capsys.readouterr().out) == (0, [], True)


def test_dry_run_is_the_default_and_writes_nothing(web):
    root, calls = web
    before = _snapshot(root)

    code = webtest_scaffold.main(["--root", root])

    assert (code, _snapshot(root), calls) == (0, before, [])


def test_apply_creates_config_auth_axe_ignore_mcp_and_codex(web):
    root, calls = web

    code = webtest_scaffold.main(["--root", root, "--apply"])

    config = _read(root, "playwright.config.ts")
    assert (code,
            all(s in config for s in ("trace: 'on-first-retry'", "reporter: CI ? 'blob' : 'html'",
                                      "{platform}", webtest_guard.PINNED_IMAGE,
                                      webtest_guard.IMAGE_ENV, "testIdAttribute")),
            "/playwright/.auth/" in _read(root, ".gitignore").splitlines(),
            sorted(json.loads(_read(root, ".mcp.json"))["mcpServers"]),
            "[mcp_servers.chrome-devtools]" in _read(root, ".codex/config.toml"),
            "AxeBuilder" in _read(root, "tests/fixtures/axe.ts"),
            "storageState({ path: authFile })" in _read(root, "tests/auth.setup.ts"),
            [c[-1] for c in calls]) == (
        0, True, True, ["chrome-devtools", "playwright"], True, True, True,
        ["--loop=claude", "--loop=codex"])


def test_playwright_mcp_entry_is_isolated_headless_testing(web):
    root, _calls = web

    webtest_scaffold.main(["--root", root, "--apply"])

    server = json.loads(_read(root, ".mcp.json"))["mcpServers"]["playwright"]
    assert server == {"command": "npx", "args": [webtest_scaffold.PLAYWRIGHT_MCP, "--isolated",
                                                 "--headless", "--caps", "testing"]}


def test_windows_wraps_every_mcp_entry_in_cmd_c(web):
    root, calls = web

    webtest_scaffold.main(["--root", root, "--apply", "--windows"])

    servers = json.loads(_read(root, ".mcp.json"))["mcpServers"]
    assert ({s["command"] for s in servers.values()}, {tuple(s["args"][:2]) for s in servers.values()},
            calls[0][:2]) == ({"cmd"}, {("/c", "npx")}, ["cmd", "/c"])


def test_second_apply_changes_nothing(web):
    root, _calls = web
    webtest_scaffold.main(["--root", root, "--apply"])
    _write(root, ".claude/agents/playwright-test-planner.md", "agent")
    before = _snapshot(root)

    code = webtest_scaffold.main(["--root", root, "--apply"])

    assert (code, _snapshot(root)) == (0, before)


def test_existing_files_and_servers_are_never_overwritten(web):
    root, _calls = web
    mine = {"mcpServers": {"playwright": {"command": "mine"}}, "other": 1}
    _write(root, "playwright.config.mjs", "// mine\n")
    _write(root, "tests/auth.setup.ts", "// mine\n")
    _write(root, ".gitignore", "node_modules\n/test-results/")
    _write(root, ".mcp.json", json.dumps(mine))
    _write(root, ".codex/config.toml", "[mcp_servers.playwright]\ncommand = \"mine\"\n")

    webtest_scaffold.main(["--root", root, "--apply"])

    mcp = json.loads(_read(root, ".mcp.json"))
    assert (os.path.exists(os.path.join(root, "playwright.config.ts")),
            _read(root, "tests/auth.setup.ts"),
            _read(root, ".gitignore").splitlines()[:2],
            _read(root, ".gitignore").count("/test-results/"),
            mcp["mcpServers"]["playwright"], mcp["other"], sorted(mcp["mcpServers"]),
            _read(root, ".codex/config.toml").count("[mcp_servers.playwright]")) == (
        False, "// mine\n", ["node_modules", "/test-results/"], 1,
        {"command": "mine"}, 1, ["chrome-devtools", "playwright"], 1)


def test_unparseable_mcp_json_is_left_alone_and_reported(web, capsys):
    root, _calls = web
    _write(root, ".mcp.json", "{ nope")

    code = webtest_scaffold.main(["--root", root, "--apply"])

    assert (code, _read(root, ".mcp.json"), "does not parse" in capsys.readouterr().out) == (
        1, "{ nope", True)


def test_agents_are_skipped_when_the_planner_exists(web):
    root, calls = web
    _write(root, ".claude/agents/playwright-test-planner.md", "agent")

    webtest_scaffold.main(["--root", root, "--apply"])

    assert calls == []


def test_init_agents_rewriting_mcp_json_is_undone_keeping_its_new_server(web, monkeypatch):
    root, _calls = web
    _write(root, ".mcp.json", json.dumps({"mcpServers": {"mine": {"command": "x"}}}))

    def _clobber(cmd, cwd):
        _write(cwd, ".mcp.json", json.dumps({"mcpServers": {"playwright-test": {"command": "npx"}}}))
        return 0
    monkeypatch.setattr(webtest_scaffold.run_agents, "__defaults__", (_clobber,))

    webtest_scaffold.main(["--root", root, "--apply"])

    assert sorted(json.loads(_read(root, ".mcp.json"))["mcpServers"]) == [
        "chrome-devtools", "mine", "playwright", "playwright-test"]


def test_a_failed_init_agents_run_exits_1(web, monkeypatch):
    root, _calls = web
    monkeypatch.setattr(webtest_scaffold.run_agents, "__defaults__", (lambda cmd, cwd: 1,))

    assert webtest_scaffold.main(["--root", root, "--apply"]) == 1


def test_angular_defaults_the_base_url_to_4200(web):
    root, _calls = web
    _write(root, "angular.json", "{}")

    webtest_scaffold.main(["--root", root, "--apply"])

    assert "http://localhost:4200" in _read(root, "playwright.config.ts")
