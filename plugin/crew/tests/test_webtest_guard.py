"""`webtest_guard.py`: the healer-skip, auth-leak and visual-placement checks.

Must-block and must-allow cases for each, against real git repositories under
`tmp_path` -- the questions are what git answers (what was added since a base,
what is tracked). The bash and PowerShell drivers run the same CLI the way the
verify gate does (`bash -c` from both flavours): see `_test/run-tests.sh`'s
webtest section and `_test/webtest-guard.ps1`, driven by
`test_webtest_guard_pwsh.py`.
"""
import fnmatch
import json
import os
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger
import review_patch
import review_prompt
import review_run
import webtest_guard
import webtest_rules

_GUARD = os.path.join(context._ROOT, "hooks", "scripts", "webtest_guard.py")  # pylint: disable=protected-access
TICKET = "T-0007"
SPEC = "tests/login.spec.ts"
CLEAN_TEST = "import { test } from '@playwright/test';\ntest('logs in', async () => {});\n"


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL).stdout.strip()


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _write(root, ".gitignore", ".work/\n.crew/\n")
    _write(root, SPEC, CLEAN_TEST)
    _write(root, "tests/old.spec.ts", "test.skip('already skipped before the ticket', () => {});\n")
    _write(root, ".work/tickets/" + TICKET + "/spec.md", "# spec\n\n## Exclusions\n- none\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _base(root):
    return _git(root, "rev-parse", "HEAD")


def _spec_exclusions(root, body):
    _write(root, f".work/tickets/{TICKET}/spec.md", f"# spec\n\n## Exclusions\n{body}\n## Evidence\nx\n")


@pytest.mark.parametrize("line", [
    "test.skip('flaky', async () => {});",
    "test.fixme('broken', async () => {});",
    "  test.skip();",
    "test.describe.skip('group', () => {});",
    "it.skip('x', () => {});",
    "test.fail();",
    "test.describe.fail('group', () => {});",
    "test('x', { annotation: { type: 'skip' } }, async () => {});",
    "test('x', { annotation: { type: \"fixme\" } }, async () => {});",
])
def test_skips_blocks_a_skip_added_since_the_base(repo, line):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + line + "\n")

    code, lines = webtest_guard.check_skips(repo, TICKET, base)

    assert (code, any(ln.startswith(f"FINDING|FIX|healer-skip|{SPEC}:3|") for ln in lines)) == (1, True)


def test_skips_blocks_a_skip_in_a_new_untracked_spec_file(repo):
    base = _base(repo)
    _write(repo, "e2e/cart.spec.ts", "test.fixme('cart', async () => {});\n")

    code, lines = webtest_guard.check_skips(repo, TICKET, base)

    assert (code, "FINDING|FIX|healer-skip|e2e/cart.spec.ts:1|test.fixme('cart', async () => {});"
            in lines) == (1, True)


def test_skips_blocks_a_skip_committed_on_the_ticket_branch(repo):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.skip();\n")
    _git(repo, "commit", "-qam", "healer")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 1


@pytest.mark.parametrize("line", [
    "test('skipper', async ({ page }) => { await page.getByRole('button').click(); });",
    "const skip = true;",
    "await page.getByTestId('skip-link').click();",
])
def test_skips_allows_changes_that_add_no_skip(repo, line):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + line + "\n")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 0


def test_skips_ignores_a_skip_that_predates_the_base(repo):
    base = _base(repo)
    _write(repo, "tests/old.spec.ts", "test.skip('already skipped before the ticket', () => {});\n"
                                      "test('new', () => {});\n")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 0


def test_skips_ignores_skip_text_outside_spec_files(repo):
    base = _base(repo)
    _write(repo, "src/app.ts", "list.skip(1);\n")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 0


@pytest.mark.parametrize("exclusion", [f"- skip: {SPEC} - owner accepted", f"- skip: `{SPEC}`",
                                       f"- skip: ./{SPEC} \"flaky\""])
def test_skips_allows_a_skip_the_spec_lists_under_exclusions(repo, exclusion):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.skip('flaky', async () => {});\n")
    _spec_exclusions(repo, exclusion)

    code, lines = webtest_guard.check_skips(repo, TICKET, base)

    assert (code, any(ln.startswith("EXCLUDED|") for ln in lines)) == (0, True)


@pytest.mark.parametrize("exclusion", [
    "- skip: tests/other.spec.ts",
    f"- skip: {SPEC} \"some other title\"",
])
def test_skips_blocks_when_the_exclusion_names_something_else(repo, exclusion):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.skip('flaky', async () => {});\n")
    _spec_exclusions(repo, exclusion)

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 1


def test_skips_exclusion_outside_the_exclusions_section_does_not_count(repo):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.skip();\n")
    _write(repo, f".work/tickets/{TICKET}/spec.md",
           f"# spec\n\n## Intent\n- skip: {SPEC}\n\n## Exclusions\n- none\n")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 1


def test_skips_writes_findings_for_the_review(repo):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.fixme();\n")

    webtest_guard.check_skips(repo, TICKET, base)

    with open(os.path.join(repo, ".work", "tickets", TICKET, "webtest", "findings.json"),
              encoding="utf-8") as fh:
        rows = json.load(fh)["findings"]
    assert [(r["path"], r["line"], r["excluded"]) for r in rows] == [(SPEC, 3, False)]


def test_skips_outside_a_repository_is_unknown_not_a_pass(tmp_path):
    code, _lines = webtest_guard.check_skips(str(tmp_path), TICKET, "0" * 40)

    assert code == 2


def test_skips_refuses_a_ticket_id_with_a_path_in_it(repo):
    code, _lines = webtest_guard.check_skips(repo, "../x", _base(repo))

    assert code == 2


@pytest.mark.parametrize("rel", ["playwright/.auth/user.json", "e2e/.auth/admin.json"])
def test_auth_leak_blocks_a_tracked_auth_file(repo, rel):
    _write(repo, rel, "{}")
    _git(repo, "add", "-f", rel)

    code, lines = webtest_guard.check_auth_leak(repo)

    assert (code, f"  {rel}" in lines) == (1, True)


def test_auth_leak_blocks_a_tracked_storage_state_named_in_the_config(repo):
    _write(repo, "playwright.config.ts", "export default { use: { storageState: 'state/admin.json' } };\n")
    _write(repo, "state/admin.json", "{}")
    _git(repo, "add", "-A")

    code, _lines = webtest_guard.check_auth_leak(repo)

    assert code == 1


def test_auth_leak_allows_an_ignored_auth_directory(repo):
    _write(repo, ".gitignore", ".work/\n.crew/\n/playwright/.auth/\n")
    _write(repo, "playwright/.auth/user.json", "{}")
    _write(repo, "playwright.config.ts", "const authFile = 'playwright/.auth/user.json';\n")
    _git(repo, "add", "-A")

    code, _lines = webtest_guard.check_auth_leak(repo)

    assert code == 0


def test_auth_leak_outside_a_repository_is_unknown_not_a_pass(tmp_path):
    code, _lines = webtest_guard.check_auth_leak(str(tmp_path))

    assert code == 2


@pytest.mark.parametrize("image", [None, "", "mcr.microsoft.com/playwright:v1.62.0-noble"])
def test_visual_off_the_pinned_image_is_skipped_as_unverified(repo, monkeypatch, image):
    if image is None:
        monkeypatch.delenv(webtest_guard.IMAGE_ENV, raising=False)
    else:
        monkeypatch.setenv(webtest_guard.IMAGE_ENV, image)
    ran = []

    code, lines = webtest_guard.check_visual(repo, runner=lambda *a, **k: ran.append(a) or 0)

    assert (code, "UNVERIFIED" in lines[0], ran) == (77, True, [])


def _host(tmp, monkeypatch, dockerenv=False, cgroup="0::/init.scope\n", browsers=None):
    """Point the container evidence at files under `tmp`: nothing on the
    real host is read, so these cases say the same thing everywhere."""
    marker = os.path.join(tmp, "dockerenv")
    if dockerenv:
        _write(tmp, "dockerenv", "")
    _write(tmp, "cgroup", cgroup)
    store = os.path.join(tmp, "ms-playwright")
    for name in browsers or ():
        os.makedirs(os.path.join(store, name))
    monkeypatch.setattr(webtest_guard, "CONTAINER_MARKERS", (marker,))
    monkeypatch.setattr(webtest_guard, "CGROUP_FILE", os.path.join(tmp, "cgroup"))
    monkeypatch.setattr(webtest_guard, "BROWSERS_DIR", store)


def _in_image(repo, monkeypatch, version, revision="1200"):
    monkeypatch.setenv(webtest_guard.IMAGE_ENV, webtest_guard.PINNED_IMAGE)
    monkeypatch.setattr(sys, "platform", "linux")
    _host(os.path.dirname(repo), monkeypatch, dockerenv=True, browsers=["chromium-1200"])
    if version:
        _write(repo, "node_modules/@playwright/test/package.json", json.dumps({"version": version}))
    _write(repo, "node_modules/playwright-core/browsers.json",
           json.dumps({"browsers": [{"name": "chromium", "revision": revision}]}))


@pytest.mark.parametrize("rc, expected", [(0, 0), (1, 1), (77, 1)])
def test_visual_inside_the_pinned_image_runs_and_reports_its_exit(repo, monkeypatch, rc, expected):
    _in_image(repo, monkeypatch, webtest_guard.PINNED_PLAYWRIGHT)

    code, _lines = webtest_guard.check_visual(repo, runner=lambda *a, **k: rc)

    assert code == expected


@pytest.mark.parametrize("version", [None, "1.62.0"])
def test_visual_inside_the_image_with_the_wrong_playwright_fails(repo, monkeypatch, version):
    _in_image(repo, monkeypatch, version)

    code, _lines = webtest_guard.check_visual(repo, runner=lambda *a, **k: 0)

    assert code == 1


def test_artifacts_are_bounded_newest_first_and_the_rest_counted(repo):
    _write(repo, "playwright.config.ts", "export default {};\n")
    for i in range(3):
        _write(repo, f"test-results/t{i}/trace.zip", "z" * (i + 1))
        os.utime(os.path.join(repo, "test-results", f"t{i}", "trace.zip"), (1000 + i, 1000 + i))
    _write(repo, "test-results/t0/axe-results.json", "{}")

    listing = webtest_guard.artifacts(repo, limit=2)

    assert ([r["path"] for r in listing["traces"]], listing["omitted"], len(listing["axe"])) == (
        ["test-results/t2/trace.zip", "test-results/t1/trace.zip"], {"traces": 1, "axe": 0}, 1)


def test_artifacts_absent_in_a_repo_with_no_playwright(repo):
    assert webtest_guard.artifacts(repo) is None


def test_review_patch_manifest_lists_the_web_artifacts(repo):
    base = _base(repo)
    _write(repo, "playwright.config.ts", "export default {};\n")
    _write(repo, "test-results/t0/trace.zip", "zip")

    manifest, _patch, _parts = review_patch.compute(repo, base)

    assert [r["path"] for r in manifest["webtest"]["traces"]] == ["test-results/t0/trace.zip"]


def test_review_prompt_hands_open_skips_to_the_reviewer_as_findings(repo):
    _write(repo, SPEC, CLEAN_TEST + "test.skip();\n")
    webtest_guard.check_skips(repo, TICKET, _base(repo))
    manifest = {"webtest": {"root": "test-results", "limit": 20, "traces": [], "axe": [],
                            "omitted": {}}}

    text = review_prompt.build(repo, TICKET, manifest)

    assert (f"FINDING|FIX|healer-skip|{SPEC}:3|test.skip();" in text,
            "MISSING: no trace artefact" in text) == (True, True)


def test_review_prompt_says_when_the_skip_check_never_ran(repo):
    manifest = {"webtest": {"root": "test-results", "limit": 20, "omitted": {},
                            "traces": [{"path": "test-results/a/trace.zip", "bytes": 3,
                                        "sha256": "ab" * 32}], "axe": []}}

    text = review_prompt.build(repo, TICKET, manifest)

    assert ("TRACE: test-results/a/trace.zip" in text,
            "has not run for this ticket" in text) == (True, True)


def test_review_prompt_has_no_web_block_outside_a_playwright_repo(repo):
    assert "== Web tests ==" not in review_prompt.build(repo, TICKET, {})


def test_review_json_carries_only_the_open_skip_rows(repo):
    _write(repo, SPEC, CLEAN_TEST + "test.skip('flaky');\ntest.fixme('kept');\n")
    _spec_exclusions(repo, f"- skip: {SPEC} \"flaky\"")
    webtest_guard.check_skips(repo, TICKET, _base(repo))

    rows = review_run.webtest_findings(repo, TICKET)

    assert [r["line"] for r in rows] == [4]


def test_review_json_webtest_findings_is_none_when_the_check_never_ran(repo):
    assert review_run.webtest_findings(repo, TICKET) is None


def test_rules_emit_the_five_checks_each_local():
    rules = webtest_rules.rules()

    commands = [c for r in rules for c in r["run"]]
    assert ({r["reach"] for r in rules}, [c.split("webtest_guard.py\" ")[-1].split(" ")[0]
                                          for c in commands if "webtest_guard" in c],
            "npx playwright test --reporter=blob" in commands,
            any("merge-reports" in c for c in commands),
            any("--project=axe" in c for c in commands)) == (
        {"local"}, ["auth-leak", "skips", "visual"], True, True, True)


def test_rules_cli_prints_parseable_json(capsys):
    webtest_rules.main([])

    assert len(json.loads(capsys.readouterr().out)["rules"]) == 5


def test_cli_exit_code_is_the_check_result(repo):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.skip();\n")

    done = subprocess.run([sys.executable, _GUARD, "skips", "--root", repo, "--ticket", TICKET,
                           "--base", base], capture_output=True, text=True, check=False)

    assert (done.returncode, "FINDING|FIX|healer-skip" in done.stderr) == (1, True)


# ---- round-1 fixes: every case below failed (exit 0 / CLEAN) before them.

@pytest.mark.parametrize("text", [
    "test['skip']('computed', async () => {});\n",
    "test[\"fixme\"]();\n",
    "test?.skip();\n",
    "test.skip(\n  true,\n  'disabled on purpose',\n);\n",
    "test('x', {\n  annotation: {\n    type:\n      'skip',\n  },\n}, async () => {});\n",
    "const off = test.fixme;\noff('aliased');\n",
])
def test_skips_blocks_computed_aliased_and_multiline_forms(repo, text):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + text)

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 1


@pytest.mark.parametrize("text", [
    "// test.skip('commented out');\n",
    "/* test.fixme();\n   test.skip(); */\n",
    "const s = 'test.skip(';\n",
    "const t = `a ${'test.skip('} b`;\n",
    "const re = /\\.skip\\(/;\n",
])
def test_skips_allows_skip_text_in_comments_strings_and_regexes(repo, text):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + text)

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 0


def test_skips_blocks_a_skip_added_in_a_helper_under_a_test_dir(repo):
    base = _base(repo)
    _write(repo, "tests/helper.ts", "export function off() { test.skip(true, 'disabled'); }\n")

    code, lines = webtest_guard.check_skips(repo, TICKET, base)

    assert (code, any("tests/helper.ts:1" in ln for ln in lines)) == (1, True)


def test_skips_blocks_a_skip_in_a_helper_a_spec_imports_from_anywhere(repo):
    _write(repo, "src/testing/login.ts", "export const login = () => {};\n")
    _write(repo, SPEC, "import { login } from '../src/testing/login';\n" + CLEAN_TEST)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "helper")
    base = _base(repo)
    _write(repo, "src/testing/login.ts", "export const login = () => { test.skip(true); };\n")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 1


def test_skips_ignores_a_skip_in_a_file_no_spec_imports(repo):
    _write(repo, "src/testing/unused.ts", "export const x = 1;\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "unused")
    base = _base(repo)
    _write(repo, "src/testing/unused.ts", "export const x = () => test.skip();\n")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 0


def test_skips_blocks_a_rename_that_turns_a_skipping_helper_into_a_spec(repo):
    _write(repo, "tests/skipper.ts", "test.skip(true, 'disabled');\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "helper")
    base = _base(repo)
    _git(repo, "mv", "tests/skipper.ts", "tests/example.spec.ts")

    code, lines = webtest_guard.check_skips(repo, TICKET, base)

    assert (code, any("tests/example.spec.ts:1" in ln for ln in lines)) == (1, True)


def test_skips_allows_renaming_a_spec_whose_skip_predates_the_base(repo):
    base = _base(repo)
    _git(repo, "mv", "tests/old.spec.ts", "tests/renamed.spec.ts")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 0


@pytest.mark.parametrize("rel", ["tests/foo.spec.cts", "tests/foo.spec.mts", "e2e/foo.test.cjs",
                                 "tests/Foo.spec.jsx", "tests/auth.setup.ts"])
def test_skips_blocks_every_test_capable_extension(repo, rel):
    base = _base(repo)
    _write(repo, rel, "test.fixme('x', () => {});\n")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 1


@pytest.mark.parametrize("body", [
    f"Do not add skip: {SPEC}\n",
    f"- Do not add skip: {SPEC}\n",
    f"- skip: {SPEC} is not something we accept\n",
    f"### Accepted later\n- skip: {SPEC}\n",
])
def test_skips_prose_or_a_subsection_under_exclusions_is_not_an_exemption(repo, body):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.skip();\n")
    _spec_exclusions(repo, body)

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 1


def test_skips_a_title_exclusion_matches_a_call_split_across_lines(repo):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.skip(\n  'flaky',\n  async () => {},\n);\n")
    _spec_exclusions(repo, f"- skip: {SPEC} \"flaky\"")

    code, _lines = webtest_guard.check_skips(repo, TICKET, base)

    assert code == 0


def test_skips_findings_carry_the_head_they_were_computed_at(repo):
    base = _base(repo)

    webtest_guard.check_skips(repo, TICKET, base, bundle_sha256="ab" * 32)

    with open(webtest_guard.findings_path(repo, TICKET), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert (doc["head"], doc["bundle_sha256"]) == (base, "ab" * 32)


def _track_state(repo, config, rel="sessions/user.json"):
    _write(repo, "playwright.config.ts", config)
    _write(repo, rel, "{}")
    _git(repo, "add", "-f", "playwright.config.ts", rel)


@pytest.mark.parametrize("config", [
    "const state = 'sessions/user.json';\nexport default { use: { storageState: state } };\n",
    "const storageState = 'sessions/user.json';\nexport default { use: { storageState } };\n",
    "export default { use: { storageState: 'sessions\\\\user.json' } };\n",
    "export default { use: { storageState: \"./sessions/user.json\" } };\n",
])
def test_auth_leak_resolves_const_shorthand_and_windows_storage_state(repo, config):
    _track_state(repo, config)

    code, lines = webtest_guard.check_auth_leak(repo)

    assert (code, "  sessions/user.json" in lines) == (1, True)


@pytest.mark.parametrize("value", [
    "path.join(__dirname, 'sessions/user.json')",
    "process.env.STATE ?? 'sessions/user.json'",
    "`sessions/${who}.json`",
    "state",
])
def test_auth_leak_fails_closed_on_a_storage_state_it_cannot_resolve(repo, value):
    _write(repo, "playwright.config.ts",
           f"let state = pick();\nexport default {{ use: {{ storageState: {value} }} }};\n")

    code, lines = webtest_guard.check_auth_leak(repo)

    assert (code, any("cannot resolve storageState" in ln for ln in lines)) == (1, True)


def test_auth_leak_a_declared_storage_state_resolves_the_unresolvable(repo):
    _write(repo, "playwright.config.ts", "export default { use: { storageState: pick() } };\n")
    _write(repo, ".crew/config.json", json.dumps({"webtest": {"storageState": "sessions/user.json"}}))

    code, _lines = webtest_guard.check_auth_leak(repo)

    assert code == 0


def test_auth_leak_a_declared_storage_state_that_is_tracked_blocks(repo):
    _write(repo, ".crew/config.json",
           json.dumps({"webtest": {"storageState": ["sessions\\user.json"]}}))
    _track_state(repo, "export default { use: { storageState: pick() } };\n")

    code, lines = webtest_guard.check_auth_leak(repo)

    assert (code, "  sessions/user.json" in lines) == (1, True)


@pytest.mark.parametrize("evidence", [
    {},
    {"dockerenv": True},
    {"cgroup": "0::/system.slice/docker-abc.scope\n"},
    {"dockerenv": True, "browsers": ["chromium-9999"]},
    {"browsers": ["chromium-1200"]},
])
def test_visual_the_pinned_env_without_container_evidence_is_unverified(repo, monkeypatch, tmp_path,
                                                                         evidence):
    monkeypatch.setenv(webtest_guard.IMAGE_ENV, webtest_guard.PINNED_IMAGE)
    monkeypatch.setattr(sys, "platform", "linux")
    _host(str(tmp_path), monkeypatch, **evidence)
    _write(repo, "node_modules/@playwright/test/package.json",
           json.dumps({"version": webtest_guard.PINNED_PLAYWRIGHT}))
    _write(repo, "node_modules/playwright-core/browsers.json",
           json.dumps({"browsers": [{"name": "chromium", "revision": "1200"}]}))
    ran = []

    code, lines = webtest_guard.check_visual(repo, runner=lambda *a, **k: ran.append(a) or 0)

    assert (code, "UNVERIFIED" in lines[0], ran) == (77, True, [])


def test_visual_says_what_it_verified_before_running(repo, monkeypatch):
    _in_image(repo, monkeypatch, webtest_guard.PINNED_PLAYWRIGHT)

    _code, lines = webtest_guard.check_visual(repo, runner=lambda *a, **k: 0)

    assert "chromium-1200" in lines[0] and "dockerenv" in lines[0]


def _gate_matches(path, pat):
    """verify-gate.sh's matcher, restated: fnmatch, plus the `**/`-stripped
    and `/**/`-collapsed forms."""
    cands = {pat, pat.replace("/**/", "/")}
    if pat.startswith("**/"):
        cands.add(pat[3:])
    return any(fnmatch.fnmatch(path, c) for c in cands)


@pytest.mark.parametrize("path", ["tests/helper.ts", "foo.spec.cts", "e2e/a.test.mjs", "src/x.mts",
                                  "tests/Foo.spec.jsx", "helpers/login.cjs", "tests/a.spec.ts"])
def test_rules_the_skip_rule_watches_every_file_the_guard_reads(path):
    skip_rule = [r for r in webtest_rules.rules() if any(" skips " in c for c in r["run"])][0]

    assert any(_gate_matches(path, p) for p in skip_rule["paths"])


@pytest.mark.parametrize("path", [".auth/user.json", "e2e/.auth/a.json", "state/storageState.json",
                                  "x/storage-state.json", "sessions/user.json", ".crew/config.json"])
def test_rules_the_auth_rule_watches_storage_state_files(repo, path):
    _write(repo, "playwright.config.ts",
           "export default { use: { storageState: 'sessions/user.json' } };\n")
    auth_rule = [r for r in webtest_rules.rules(root=repo)
                 if any("auth-leak" in c for c in r["run"])][0]

    assert any(_gate_matches(path, p) for p in auth_rule["paths"])


def _review(repo, tmp_path, base, reads_extra=(), after_bundle=None):
    """Cut a real bundle, reserve a round, and hand finish() a CLEAN reviewer
    answer that READ every part. Returns (exit_code, review.json)."""
    scratch = str(tmp_path / "scratch")
    os.makedirs(scratch, exist_ok=True)
    manifest_path = os.path.join(scratch, "manifest.json")
    manifest, _code = review_patch.build(repo, base, os.path.join(scratch, "diff.txt"), manifest_path)
    if after_bundle:
        after_bundle()
    _ok, number, _msg = review_ledger.reserve(repo, TICKET, "codex")
    output = "\n".join([f"READ|{p['name']}" for p in manifest["parts"]]
                       + [f"READ|{name}" for name in reads_extra] + ["CLEAN"])
    args = types.SimpleNamespace(root=repo, ticket=TICKET, manifest=manifest_path, provider="codex",
                                 model="", work_dir=None, scratch=scratch)
    code = review_run.finish(args, number, output, 0, False)
    with open(os.path.join(repo, ".work", "tickets", TICKET, "review.json"), encoding="utf-8") as fh:
        return code, json.load(fh)


def test_review_a_skip_added_after_a_clean_check_is_found_not_clean(repo, tmp_path):
    base = _base(repo)
    _write(repo, "playwright.config.ts", "export default {};\n")
    webtest_guard.check_skips(repo, TICKET, base)
    _write(repo, SPEC, CLEAN_TEST + "test.skip('healer gave up');\n")

    code, review = _review(repo, tmp_path, base)

    assert (code, review["verdict"], review["webtest_check"]["prior_findings"],
            [r["line"] for r in review["webtest_findings"]]) == (1, "FINDINGS", "stale", [3])


def test_review_an_open_skip_overrides_a_clean_reviewer(repo, tmp_path):
    base = _base(repo)
    _write(repo, SPEC, CLEAN_TEST + "test.fixme();\n")
    webtest_guard.check_skips(repo, TICKET, base)

    code, review = _review(repo, tmp_path, base)

    assert (code, review["verdict"], bool(review["webtest_verdict"])) == (1, "FINDINGS", True)


def test_review_an_excluded_skip_leaves_a_clean_review_clean(repo, tmp_path):
    base = _base(repo)
    _write(repo, "playwright.config.ts", "export default {};\n")
    _write(repo, SPEC, CLEAN_TEST + "test.skip('flaky');\n")
    _spec_exclusions(repo, f"- skip: {SPEC} \"flaky\"")

    code, review = _review(repo, tmp_path, base)

    assert (code, review["verdict"], review["webtest_findings"]) == (0, "CLEAN", [])


def test_review_findings_are_stamped_with_the_reviewed_bundle(repo, tmp_path):
    base = _base(repo)
    _write(repo, "playwright.config.ts", "export default {};\n")

    _code, review = _review(repo, tmp_path, base)

    with open(webtest_guard.findings_path(repo, TICKET), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert (doc["head"], doc["bundle_sha256"]) == (review["head"], review["bundle_sha256"])


def test_review_a_tree_changed_after_the_bundle_is_incomplete(repo, tmp_path):
    base = _base(repo)
    _write(repo, "playwright.config.ts", "export default {};\n")

    code, review = _review(repo, tmp_path, base,
                           after_bundle=lambda: _write(repo, SPEC, CLEAN_TEST + "// later\n"))

    assert (code, review["verdict"]) == (3, "INCOMPLETE")


def test_review_no_webtest_check_outside_a_playwright_repo(repo, tmp_path):
    base = _base(repo)
    _write(repo, "src/app.ts", "export const a = 1;\n")

    code, review = _review(repo, tmp_path, base)

    assert (code, review["webtest_findings"], review["webtest_check"]) == (0, None, None)


def _many_rows(repo, count):
    rows = [{"kind": "healer-skip", "severity": "FIX", "path": SPEC, "line": n,
             "text": f"test.skip('t{n}');", "excluded": False} for n in range(1, count + 1)]
    _write(repo, f".work/tickets/{TICKET}/webtest/findings.json", json.dumps({"findings": rows}))


def test_review_prompt_hands_over_every_row_through_a_file_past_the_inline_limit(repo, tmp_path):
    _many_rows(repo, review_prompt.WEBTEST_FINDINGS_MAX + 1)

    text = review_prompt.build(repo, TICKET, {}, str(tmp_path))

    with open(tmp_path / review_prompt.WEBTEST_FINDINGS_FILE, encoding="utf-8") as fh:
        listed = fh.read().splitlines()
    assert (text.count("FINDING|FIX|healer-skip|"), len(listed),
            f"READ|{review_prompt.WEBTEST_FINDINGS_FILE}" in text) == (
        review_prompt.WEBTEST_FINDINGS_MAX, review_prompt.WEBTEST_FINDINGS_MAX + 1, True)


def test_review_prompt_without_an_out_dir_puts_every_row_inline(repo):
    _many_rows(repo, review_prompt.WEBTEST_FINDINGS_MAX + 1)

    text = review_prompt.build(repo, TICKET, {})

    assert text.count("FINDING|FIX|healer-skip|") == review_prompt.WEBTEST_FINDINGS_MAX + 1


def test_review_prompt_removes_a_previous_rounds_overflow_file(repo, tmp_path):
    _write(str(tmp_path), review_prompt.WEBTEST_FINDINGS_FILE, "stale\n")

    review_prompt.build(repo, TICKET, {}, str(tmp_path))

    assert not os.path.exists(tmp_path / review_prompt.WEBTEST_FINDINGS_FILE)


@pytest.mark.parametrize("reads, expected", [((), 3), ((review_prompt.WEBTEST_FINDINGS_FILE,), 0)])
def test_review_the_overflow_file_needs_its_own_read(repo, tmp_path, reads, expected):
    base = _base(repo)
    _write(repo, "playwright.config.ts", "export default {};\n")
    _write(str(tmp_path / "scratch"), review_prompt.WEBTEST_FINDINGS_FILE, "rows\n")

    code, _review_json = _review(repo, tmp_path, base, reads_extra=reads)

    assert code == expected
