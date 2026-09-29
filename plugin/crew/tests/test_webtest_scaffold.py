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


def _stub_npx(monkeypatch, calls, cwds=None):
    """init-agents stand-in: records the command (and cwd) and writes the
    three agent files the real one would. The stub binds to `runner`, the
    last keyword of `run_agents`, through `__defaults__`."""
    def _fake_npx(cmd, cwd):
        calls.append(cmd)
        if cwds is not None:
            cwds.append(cwd)
        for role in ("planner", "generator", "healer"):
            path = os.path.join(cwd, ".claude", "agents", f"playwright-test-{role}.md")
            if not os.path.exists(path):
                _write(cwd, f".claude/agents/playwright-test-{role}.md", "generated")
        return 0
    monkeypatch.setattr(webtest_scaffold.run_agents, "__defaults__", (_fake_npx,))


@pytest.fixture(name="web_nocreds")
def _web_nocreds(tmp_path, monkeypatch):
    root = str(tmp_path / "web")
    os.makedirs(root)
    _write(root, "package.json", json.dumps({"devDependencies": {"@playwright/test": "1.63.0"}}))
    calls = []
    _stub_npx(monkeypatch, calls)
    return root, calls


@pytest.fixture(name="web")
def _web(tmp_path, monkeypatch):
    root = str(tmp_path / "web")
    os.makedirs(root)
    _write(root, "package.json", json.dumps({"devDependencies": {"@playwright/test": "1.63.0"}}))
    _write(root, ".crew/secrets.md", "# test credentials\n")
    calls = []

    def _fake_npx(cmd, cwd):
        calls.append(cmd)
        for role in ("planner", "generator", "healer"):
            path = os.path.join(cwd, ".claude", "agents", f"playwright-test-{role}.md")
            if not os.path.exists(path):
                _write(cwd, f".claude/agents/playwright-test-{role}.md", "generated")
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


def test_playwright_mcp_entry_is_isolated_headless_testing(web, monkeypatch):
    root, _calls = web
    # `--windows`'s own default is `os.name == "nt"` (deliberate: a real
    # Windows host should wrap MCP entries in `cmd /c` without being told).
    # This test is about the un-wrapped shape specifically -- covered
    # against a real Windows host's default by
    # test_windows_wraps_every_mcp_entry_in_cmd_c below -- so force the
    # default the same way the CLI can't (there is no `--no-windows`).
    monkeypatch.setattr(webtest_scaffold.os, "name", "posix")

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


def _agents(root, roles=("planner", "generator", "healer"), text="agent"):
    for role in roles:
        _write(root, f".claude/agents/playwright-test-{role}.md", text)


def test_second_apply_changes_nothing(web):
    root, _calls = web
    webtest_scaffold.main(["--root", root, "--apply"])
    _agents(root)
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


def test_agents_are_skipped_when_all_three_exist(web):
    root, calls = web
    _agents(root)

    webtest_scaffold.main(["--root", root, "--apply"])

    assert calls == []


def _module_args(root, module):
    """`--module` for the tests run both at the root and for a module: the
    web fixture's root is itself a web project, so a module needs its own
    marker."""
    if not module:
        return []
    _write(root, f"{module}/package.json", json.dumps({"devDependencies": {"playwright": "1"}}))
    return ["--module", module]


@pytest.mark.parametrize("module", [None, "mod-a"])
def test_init_agents_rewriting_mcp_json_is_undone_keeping_its_new_server(web, monkeypatch, module):
    root, _calls = web
    _write(root, ".mcp.json", json.dumps({"mcpServers": {"mine": {"command": "x"}}}))

    def _clobber(cmd, cwd):
        _write(cwd, ".mcp.json", json.dumps({"mcpServers": {"playwright-test": {"command": "npx"}}}))
        return 0
    monkeypatch.setattr(webtest_scaffold.run_agents, "__defaults__", (_clobber,))

    webtest_scaffold.main(["--root", root, "--apply"] + _module_args(root, module))

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


def _init_agents_writes_all(cmd, cwd):
    _agents(cwd, text=f"generated by {next(a for a in cmd if a.startswith('--loop='))}")
    return 0


def _gaps(out):
    """{gap line: [snippet lines]} from a run's stdout."""
    found, current = {}, None
    for line in out.splitlines():
        if line.startswith("  gap     "):
            current = line[len("  gap     "):]
            found[current] = []
        elif current is not None and line.startswith("          "):
            found[current].append(line.strip())
        else:
            current = None
    return found


def _gap(out, needle):
    rows = [(line, snippet) for line, snippet in _gaps(out).items() if needle in line]
    assert len(rows) == 1, (needle, out)
    return rows[0][0], "\n".join(rows[0][1])


MINIMAL = "export default { projects: [{ name: 'chromium' }] };\n"


def test_missing_projects_are_advisory_gap_lines_and_exit_0(web, capsys):
    root, _calls = web
    _write(root, "playwright.config.ts", MINIMAL)
    _agents(root)

    code = webtest_scaffold.main(["--root", root, "--apply"])

    out = capsys.readouterr().out
    _axe_line, axe = _gap(out, "lacks the 'axe' project")
    _visual_line, visual = _gap(out, "lacks the 'visual' project")
    assert (code, "  keep    playwright.config.ts: exists - kept" in out.splitlines(),
            [line.split(" - ")[0] for line in _gaps(out)],
            all(s in axe for s in ("name: 'axe'", "testMatch: /.*\\.axe\\.spec\\.ts/",
                                   "devices['Desktop Chrome']")),
            all(s in visual for s in (f"process.env.{webtest_guard.IMAGE_ENV} === "
                                      f"'{webtest_guard.PINNED_IMAGE}'", "name: 'visual'"))) == (
        0, True, ["playwright.config.ts lacks the 'setup' project",
                  "playwright.config.ts lacks the 'axe' project",
                  "playwright.config.ts lacks the 'visual' project"], True, True)


def test_setup_is_not_a_gap_without_credentials(web_nocreds, capsys):
    root, _calls = web_nocreds
    _write(root, "playwright.config.ts", MINIMAL)
    _agents(root)

    code = webtest_scaffold.main(["--root", root, "--apply"])

    out = capsys.readouterr().out
    assert (code, any("'setup'" in line for line in _gaps(out)),
            any(line.startswith("  skip    tests/auth.setup.ts: no credentials recorded")
                for line in out.splitlines())) == (0, False, True)


def test_a_visual_project_without_the_image_gate_is_one_gap_naming_the_gate(web, capsys):
    root, _calls = web
    _write(root, "playwright.config.ts", "export default { projects: [{ name: 'setup' }, "
           "{ name: 'chromium' }, { name: 'axe' }, { name: 'visual' }] };\n")
    _agents(root)

    webtest_scaffold.main(["--root", root, "--apply"])

    gaps = _gaps(capsys.readouterr().out)
    assert (list(gaps), any(f"process.env.{webtest_guard.IMAGE_ENV}" in s
                            for s in next(iter(gaps.values())))) == (
        [f"playwright.config.ts lacks the visual project's gate on {webtest_guard.PINNED_IMAGE}"
         " - wrap the existing 'visual' entry in:"], True)


@pytest.mark.parametrize("projects, depends", [
    ("{ name: 'setup' }, { name: 'chromium' }", True),
    ("{ name: 'chromium' }", False),
])
def test_axe_snippet_depends_on_setup_only_when_the_config_names_it(web, capsys, projects,
                                                                    depends):
    root, _calls = web
    _write(root, "playwright.config.ts", f"export default {{ projects: [{projects}] }};\n")
    _agents(root)

    webtest_scaffold.main(["--root", root, "--apply"])

    _line, axe = _gap(capsys.readouterr().out, "lacks the 'axe' project")
    assert ("dependencies: ['setup']" in axe) == depends


def test_an_existing_config_with_every_project_passes(web):
    root, _calls = web
    webtest_scaffold.main(["--root", root, "--apply"])
    _agents(root)

    assert webtest_scaffold.config_gaps(_read(root, "playwright.config.ts")) == []


def test_only_the_planner_present_still_runs_init_agents(web):
    root, calls = web
    _agents(root, roles=("planner",))

    webtest_scaffold.main(["--root", root, "--apply"])

    assert len(calls) == 2


def test_agents_init_agents_did_not_write_are_reported_and_fail(web, monkeypatch, capsys):
    root, _calls = web
    _agents(root, roles=("planner",))
    monkeypatch.setattr(webtest_scaffold.run_agents, "__defaults__", (lambda cmd, cwd: 0,))

    code = webtest_scaffold.main(["--root", root, "--apply"])

    out = capsys.readouterr().out
    assert (code, "playwright-test-generator.md" in out.split("left")[-1]) == (1, True)


@pytest.mark.parametrize("module", [None, "mod-a"])
def test_a_customised_agent_survives_init_agents(web, monkeypatch, module):
    root, _calls = web
    _write(root, ".claude/agents/playwright-test-generator.md", "mine, customised\n")
    monkeypatch.setattr(webtest_scaffold.run_agents, "__defaults__", (_init_agents_writes_all,))

    code = webtest_scaffold.main(["--root", root, "--apply"] + _module_args(root, module))

    assert (code, _read(root, ".claude/agents/playwright-test-generator.md"),
            _read(root, ".claude/agents/playwright-test-healer.md")) == (
        0, "mine, customised\n", "generated by --loop=codex")


def test_init_agents_is_pinned_to_the_verified_playwright(web, capsys, monkeypatch):
    root, calls = web
    # See test_playwright_mcp_entry_is_isolated_headless_testing above: this
    # is asserting the un-wrapped `npx` invocation shape, which is not what
    # `--windows`'s own `os.name == "nt"` default produces on a real Windows
    # host.
    monkeypatch.setattr(webtest_scaffold.os, "name", "posix")

    webtest_scaffold.main(["--root", root])
    dry = capsys.readouterr().out
    webtest_scaffold.main(["--root", root, "--apply"])

    pin = f"--package=@playwright/test@{webtest_guard.PINNED_PLAYWRIGHT}"
    assert ([c[:4] for c in calls], pin in dry) == ([["npx", "-y", pin, "playwright"]] * 2, True)


# ---- T-0104: multi-module repositories (aws-ops report items 1-5)

MODULE_NA = ("no playwright.config.*, angular.json, or Playwright in package.json")


def _modules_tree(root):
    _write(root, "mod-a/playwright.config.ts", "export default { projects: [{ name: 'chromium' }] };\n")
    _write(root, "mod-a/e2e/package.json", json.dumps({"devDependencies": {"playwright": "1"}}))
    _write(root, "apps/mod-b/angular.json", "{}")
    _write(root, "pkgs/scope/mod-c/package.json",
           json.dumps({"devDependencies": {"@playwright/test": "1.63.0"}}))
    _write(root, "node_modules/x/playwright.config.ts", "")
    _write(root, ".hidden/playwright.config.ts", "")


@pytest.fixture(name="modules")
def _modules(tmp_path, monkeypatch):
    root = str(tmp_path / "repo")
    os.makedirs(root)
    _modules_tree(root)
    calls = []

    def _fake_npx(cmd, cwd):
        calls.append((cmd, cwd))
        for role in ("planner", "generator", "healer"):
            if not os.path.exists(os.path.join(cwd, ".claude", "agents", f"playwright-test-{role}.md")):
                _write(cwd, f".claude/agents/playwright-test-{role}.md", "generated")
        return 0
    monkeypatch.setattr(webtest_scaffold.run_agents, "__defaults__", (_fake_npx,))
    return root, calls


def test_a_root_without_a_web_project_lists_its_modules_with_the_command_to_scaffold_each(
        modules, capsys):
    root, _calls = modules

    code = webtest_scaffold.main(["--root", root])

    lines = capsys.readouterr().out.splitlines()
    assert (code, lines) == (0, [
        f"webtest scaffold: n/a at {root} - {MODULE_NA}",
        "  module  apps/mod-b (angular.json) -> --module apps/mod-b",
        "  module  mod-a (playwright.config.ts) -> --module mod-a",
        "  module  pkgs/scope/mod-c (package.json (@playwright/test)) -> --module pkgs/scope/mod-c",
        "  searched 3 directory levels below --root, skipping node_modules and dot-directories"])


def test_a_root_with_no_module_says_none_found_and_the_depth(tmp_path, capsys):
    _write(str(tmp_path), "a/b/c/d/playwright.config.ts", "")

    code = webtest_scaffold.main(["--root", str(tmp_path)])

    assert (code, capsys.readouterr().out.splitlines()[1:]) == (
        0, ["  no module found within 3 levels (skipping node_modules and dot-directories)"])


def test_module_search_does_not_descend_into_a_detected_module(modules):
    root, _calls = modules

    assert [rel for rel, _reason in webtest_scaffold.find_modules(root)] == [
        "apps/mod-b", "mod-a", "pkgs/scope/mod-c"]


@pytest.mark.parametrize("value, reason", [
    ("../x", "is not relative to --root"),
    ("/abs", "is absolute"),
    ("C:\\abs", "is absolute"),
    ("missing", "does not exist"),
    ("not-web", "is not a web project (" + MODULE_NA + ")"),
])
def test_module_must_be_a_relative_web_project_under_root(modules, capsys, value, reason):
    root, calls = modules
    os.makedirs(os.path.join(root, "not-web"))
    before = _snapshot(root)

    code = webtest_scaffold.main(["--root", root, "--module", value, "--apply"])

    assert (code, f"refused: --module {value} {reason}" in capsys.readouterr().out,
            _snapshot(root), calls) == (1, True, before, [])


def test_module_apply_reports_the_module_and_the_root(modules, capsys):
    root, _calls = modules

    webtest_scaffold.main(["--root", root, "--module", "mod-a", "--apply"])

    assert capsys.readouterr().out.splitlines()[0] == (
        "webtest scaffold (apply): web project detected by playwright.config.ts in mod-a; "
        f"session files at {root}")


def _repo(tmp_path, monkeypatch, secrets=False):
    """A repository root that is not a web project itself; its modules are
    written by each test. Returns (root, calls, cwds)."""
    root = str(tmp_path / "repo")
    os.makedirs(root)
    if secrets:
        _write(root, ".crew/secrets.md", "# test credentials\n")
    calls, cwds = [], []
    _stub_npx(monkeypatch, calls, cwds)
    return root, calls, cwds


def _ts_files(root):
    return sorted(rel.replace(os.sep, "/") for rel in _snapshot(root) if rel.endswith(".ts"))


E2E_CONFIG = "export default { testDir: './e2e', projects: [{ name: 'chromium' }] };\n"


def test_test_files_follow_the_existing_configs_testdir(tmp_path, monkeypatch):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch, secrets=True)
    _write(root, "mod-c/playwright.config.ts", E2E_CONFIG)
    _write(root, "mod-c/tests/cognito-guards/main.tf", "module \"guards\" {}\n")

    webtest_scaffold.main(["--root", root, "--module", "mod-c", "--apply"])

    assert (_ts_files(root), sorted(os.listdir(os.path.join(root, "mod-c", "tests"))),
            _read(root, "mod-c/tests/cognito-guards/main.tf")) == (
        ["mod-c/e2e/auth.setup.ts", "mod-c/e2e/fixtures/axe.ts", "mod-c/e2e/home.axe.spec.ts",
         "mod-c/playwright.config.ts"], ["cognito-guards"], "module \"guards\" {}\n")


def test_no_testdir_literal_keeps_tests_because_the_default_scans_the_config_dir(tmp_path,
                                                                                 monkeypatch):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch, secrets=True)
    _write(root, "mod-a/playwright.config.ts", MINIMAL)

    webtest_scaffold.main(["--root", root, "--module", "mod-a", "--apply"])

    assert _ts_files(root) == ["mod-a/playwright.config.ts", "mod-a/tests/auth.setup.ts",
                               "mod-a/tests/fixtures/axe.ts", "mod-a/tests/home.axe.spec.ts"]


@pytest.mark.parametrize("prelude, expr", [
    ("", "process.env.TD ?? './e2e'"),
    ("const TD = 'a';\nconst TD = 'b';\n", "TD"),
    ("", "'../outside'"),
    ("", "'/abs'"),
    ("", "`${base}/e2e`"),
])
def test_a_non_literal_testdir_is_could_not_tell_and_writes_no_test_file(tmp_path, monkeypatch,
                                                                         capsys, prelude, expr):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch, secrets=True)
    _write(root, "mod-a/playwright.config.ts",
           f"{prelude}export default {{ testDir: {expr}, projects: [{{ name: 'chromium' }}] }};\n")

    code = webtest_scaffold.main(["--root", root, "--module", "mod-a", "--apply"])

    out = capsys.readouterr().out
    skips = [line for line in out.splitlines() if line.startswith("  skip    ")]
    assert (code, _ts_files(root), len(skips), "could not tell where tests are collected" in out,
            [rel in out for rel in ("mod-a/.gitignore", ".mcp.json", ".codex/config.toml")]) == (
        1, ["mod-a/playwright.config.ts"], 1, True, [True, True, True])


@pytest.mark.parametrize("config, expected", [
    ("export default { testDir: './e2e' };", ("e2e", None)),
    ("export default { testDir: \"e2e\" };", ("e2e", None)),
    ("export default { testDir: `e2e` };", ("e2e", None)),
    ("export default { testDir: './e2e/' };", ("e2e", None)),
    ("export default { testDir: 'e2e\\\\ui' };", ("e2e/ui", None)),
    ("const dir = './e2e';\nexport default { testDir: dir };", ("e2e", None)),
    ("const testDir = 'e2e';\nexport default defineConfig({ testDir, projects: [] });", ("e2e", None)),
    ("export default { projects: [{ name: 'a', testDir: 'x' }] };", (None, None)),
    ("export default { projects: [] };", (None, None)),
])
def test_testdir_reader_matches_playwright_shapes(config, expected):
    assert webtest_scaffold.test_dir(config) == expected


def _baseline(root, rel):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG")


def test_visual_snippet_keeps_existing_baseline_names(tmp_path, monkeypatch, capsys):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch)
    _write(root, "mod-c/playwright.config.ts", E2E_CONFIG)
    _baseline(root, "mod-c/e2e/login.visual.spec.ts-snapshots/login-chromium-linux.png")
    _baseline(root, "mod-c/e2e/sign-in.visual.spec.ts-snapshots/sign-in-gate-narrow-chromium-linux.png")

    webtest_scaffold.main(["--root", root, "--module", "mod-c"])

    line, visual = _gap(capsys.readouterr().out, "lacks the 'visual' project")
    assert ("snapshotPathTemplate: '{snapshotDir}/{testFileDir}/{testFileName}-snapshots/"
            "{arg}-chromium-{platform}{ext}'" in visual,
            "2 baseline(s) under e2e are named for project 'chromium' (e.g. "
            "e2e/login.visual.spec.ts-snapshots/login-chromium-linux.png)" in line) == (True, True)


def test_baselines_named_for_no_declared_project_are_could_not_tell(tmp_path, monkeypatch, capsys):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch)
    _write(root, "mod-c/playwright.config.ts", E2E_CONFIG)
    _baseline(root, "mod-c/e2e/x.visual.spec.ts-snapshots/x-firefox-linux.png")

    webtest_scaffold.main(["--root", root, "--module", "mod-c"])

    line, visual = _gap(capsys.readouterr().out, "lacks the 'visual' project")
    assert ("snapshotPathTemplate" in visual,
            "none is named for a project this config declares (e.g. "
            "e2e/x.visual.spec.ts-snapshots/x-firefox-linux.png)" in line) == (False, True)


def test_no_baselines_means_the_plain_visual_snippet(tmp_path, monkeypatch, capsys):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch)
    _write(root, "mod-c/playwright.config.ts", E2E_CONFIG)

    webtest_scaffold.main(["--root", root, "--module", "mod-c"])

    line, visual = _gap(capsys.readouterr().out, "lacks the 'visual' project")
    assert ("snapshotPathTemplate" in visual, "baseline" in line) == (False, False)


# CONFIG_TS rendered at origin/main 2693d0fa (crew 1.0.59) for a non-Angular
# repository: a credentialed repository must still get exactly this.
CONFIG_TS_2693D0FA = "import { defineConfig, devices } from '@playwright/test';\n\nconst CI = !!process.env.CI;\nconst PINNED_IMAGE = 'mcr.microsoft.com/playwright:v1.63.0-noble';\nconst inPinnedImage = process.env.CREW_PLAYWRIGHT_IMAGE === PINNED_IMAGE;\nconst authFile = 'playwright/.auth/user.json';\nconst browser = { ...devices['Desktop Chrome'], storageState: authFile };\n\nexport default defineConfig({\n  testDir: './tests',\n  fullyParallel: true,\n  forbidOnly: CI,\n  retries: CI ? 2 : 0,\n  reporter: CI ? 'blob' : 'html',\n  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{platform}/{testFilePath}/{arg}{ext}',\n  expect: { toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.01 } },\n  use: {\n    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',\n    trace: 'on-first-retry',\n    testIdAttribute: 'data-testid',\n  },\n  projects: [\n    { name: 'setup', testMatch: /.*\\.setup\\.ts/ },\n    {\n      name: 'chromium',\n      use: browser,\n      dependencies: ['setup'],\n      testIgnore: [/.*\\.axe\\.spec\\.ts/, /.*\\.visual\\.spec\\.ts/],\n    },\n    { name: 'axe', testMatch: /.*\\.axe\\.spec\\.ts/, use: browser, dependencies: ['setup'] },\n    ...(inPinnedImage\n      ? [{ name: 'visual', testMatch: /.*\\.visual\\.spec\\.ts/, use: browser, dependencies: ['setup'] }]\n      : []),\n  ],\n});\n"


def test_fresh_config_template_is_unchanged_when_no_baselines(web):
    root, _calls = web

    webtest_scaffold.main(["--root", root, "--apply"])

    assert _read(root, "playwright.config.ts") == CONFIG_TS_2693D0FA


def test_no_credentials_means_no_auth_setup_and_no_setup_project(web_nocreds, capsys):
    root, _calls = web_nocreds

    code = webtest_scaffold.main(["--root", root, "--apply"])

    config = _read(root, "playwright.config.ts")
    assert (code, [s in config for s in ("name: 'setup'", "storageState", "dependencies: ['setup']")],
            os.path.exists(os.path.join(root, "tests", "auth.setup.ts")),
            f"  skip    tests/auth.setup.ts: no credentials recorded (.crew/secrets.md absent at "
            f"{root}; no storageState in the config)" in capsys.readouterr().out,
            [os.path.exists(os.path.join(root, "tests", *r.split("/")))
             for r in ("fixtures/axe.ts", "home.axe.spec.ts")]) == (
        0, [False, False, False], False, True, [True, True])


def test_secrets_md_at_root_records_credentials(tmp_path, monkeypatch):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch, secrets=True)
    _write(root, "mod-a/package.json", json.dumps({"devDependencies": {"@playwright/test": "1"}}))

    webtest_scaffold.main(["--root", root, "--module", "mod-a", "--apply"])

    assert ("mod-a/tests/auth.setup.ts" in _ts_files(root),
            "name: 'setup'" in _read(root, "mod-a/playwright.config.ts")) == (True, True)


def test_a_declared_storagestate_counts_as_credentials(web_nocreds, capsys):
    root, _calls = web_nocreds
    _write(root, "playwright.config.ts", "export default { use: { storageState: "
           "'playwright/.auth/user.json' }, projects: [{ name: 'chromium' }] };\n")
    _agents(root)

    webtest_scaffold.main(["--root", root, "--apply"])

    assert (os.path.exists(os.path.join(root, "tests", "auth.setup.ts")),
            any("'setup'" in line for line in _gaps(capsys.readouterr().out))) == (True, True)


def test_session_files_land_at_root_and_test_files_in_the_module(tmp_path, monkeypatch):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch, secrets=True)
    _write(root, ".gitignore", "node_modules\n")
    _write(root, "mod-a/playwright.config.ts", MINIMAL)

    webtest_scaffold.main(["--root", root, "--module", "mod-a", "--apply"])

    exists = [os.path.exists(os.path.join(root, *rel.split("/"))) for rel in (
        ".mcp.json", ".codex/config.toml", ".claude/agents/playwright-test-planner.md",
        ".claude/agents/playwright-test-generator.md", ".claude/agents/playwright-test-healer.md",
        "mod-a/.mcp.json", "mod-a/.codex", "mod-a/.claude")]
    assert (exists, all(line in _read(root, "mod-a/.gitignore").splitlines()
                        for line in webtest_scaffold.IGNORE_LINES),
            _read(root, ".gitignore")) == ([True] * 5 + [False] * 3, True, "node_modules\n")


def test_init_agents_gets_the_modules_config(tmp_path, monkeypatch):
    root, calls, cwds = _repo(tmp_path, monkeypatch)
    _write(root, "mod-a/playwright.config.ts", MINIMAL)

    webtest_scaffold.main(["--root", root, "--module", "mod-a", "--apply"])

    assert ([c[-2:] for c in calls], cwds) == (
        [["--loop=claude", "--config=mod-a/playwright.config.ts"],
         ["--loop=codex", "--config=mod-a/playwright.config.ts"]], [root, root])


def test_init_agents_without_a_module_gets_no_config_argument(web):
    root, calls = web

    webtest_scaffold.main(["--root", root, "--apply"])

    assert [a for c in calls for a in c if a.startswith("--config")] == []


def test_windows_init_agents_carries_the_config_argument_too(tmp_path, monkeypatch):
    root, calls, _cwds = _repo(tmp_path, monkeypatch)
    _write(root, "mod-a/playwright.config.ts", MINIMAL)

    webtest_scaffold.main(["--root", root, "--module", "mod-a", "--apply", "--windows"])

    assert [(c[:3], c[-1]) for c in calls] == [
        (["cmd", "/c", "npx"], "--config=mod-a/playwright.config.ts")] * 2


def test_dry_run_lists_the_config_argument_in_its_run_lines(tmp_path, monkeypatch, capsys):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch)
    _write(root, "mod-a/playwright.config.ts", MINIMAL)

    webtest_scaffold.main(["--root", root, "--module", "mod-a"])

    runs = [line for line in capsys.readouterr().out.splitlines() if line.startswith("  run     ")]
    assert [r.split(" ")[-2:] for r in runs] == [
        ["--loop=claude", "--config=mod-a/playwright.config.ts"],
        ["--loop=codex", "--config=mod-a/playwright.config.ts"]]


NEXT = (f"next: npm i -D @playwright/test@{webtest_guard.PINNED_PLAYWRIGHT} "
        "@axe-core/playwright@4.13.0 && npx playwright install --with-deps chromium")


@pytest.mark.parametrize("module, expected", [
    (None, NEXT),
    ("mod-a", f"next: (cd mod-a && {NEXT[len('next: '):]})"),
])
def test_next_line_runs_npm_in_the_module(tmp_path, monkeypatch, capsys, module, expected):
    root, _calls, _cwds = _repo(tmp_path, monkeypatch)
    _write(root, "mod-a/playwright.config.ts", MINIMAL)
    _write(root, "playwright.config.ts", MINIMAL)

    webtest_scaffold.main(["--root", root] + (["--module", module] if module else []))

    assert capsys.readouterr().out.splitlines()[-1] == expected


def test_the_aws_ops_report_shape_end_to_end(tmp_path, monkeypatch, capsys):
    root, calls, cwds = _repo(tmp_path, monkeypatch)
    _write(root, ".mcp.json", json.dumps({"mcpServers": {"theirs": {"command": "x"}}}))
    for mod in ("mod-a", "mod-b", "mod-c"):
        _write(root, f"{mod}/playwright.config.ts",
               "import { defineConfig, devices } from '@playwright/test';\n"
               "export default defineConfig({ testDir: './e2e', projects: [\n"
               "  { name: 'chromium', use: { ...devices['Desktop Chrome'] } }] });\n")
    _baseline(root, "mod-c/e2e/sign-in-gate.visual.spec.ts-snapshots/sign-in-gate-chromium-linux.png")
    _write(root, "mod-c/tests/cognito-guards/main.tf", "module \"guards\" {}\n")
    tests_before = _snapshot(os.path.join(root, "mod-c", "tests"))
    listed = (webtest_scaffold.main(["--root", root]), capsys.readouterr().out)

    code = webtest_scaffold.main(["--root", root, "--module", "mod-c", "--apply"])
    out = capsys.readouterr().out
    after_first = _snapshot(root)
    second = webtest_scaffold.main(["--root", root, "--module", "mod-c", "--apply"])

    _line, visual = _gap(out, "lacks the 'visual' project")
    assert (listed[0], [m in listed[1] for m in ("--module mod-a", "--module mod-b", "--module mod-c")],
            code, [f for f in _ts_files(root) if f.startswith("mod-c/e2e/")],
            any(line.startswith("  skip    mod-c/e2e/auth.setup.ts: no credentials recorded")
                for line in out.splitlines()),
            _snapshot(os.path.join(root, "mod-c", "tests")) == tests_before,
            sorted(line.split(" - ")[0] for line in _gaps(out)),
            "{arg}-chromium-{platform}{ext}" in visual,
            sorted(json.loads(_read(root, ".mcp.json"))["mcpServers"]),
            "[mcp_servers.playwright]" in _read(root, ".codex/config.toml"),
            [(c[-1], cwd) for c, cwd in zip(calls, cwds)],
            second, _snapshot(root) == after_first) == (
        0, [True, True, True],
        0, ["mod-c/e2e/fixtures/axe.ts", "mod-c/e2e/home.axe.spec.ts"], True, True,
        ["mod-c/playwright.config.ts lacks the 'axe' project",
         "mod-c/playwright.config.ts lacks the 'visual' project"], True,
        ["chrome-devtools", "playwright", "theirs"], True,
        [("--config=mod-c/playwright.config.ts", root)] * 2, 0, True)
