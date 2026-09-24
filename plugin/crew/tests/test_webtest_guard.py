"""`webtest_guard.py`: the healer-skip, auth-leak and visual-placement checks.

Must-block and must-allow cases for each, against real git repositories under
`tmp_path` -- the questions are what git answers (what was added since a base,
what is tracked). The bash and PowerShell drivers run the same CLI the way the
verify gate does (`bash -c` from both flavours): see `_test/run-tests.sh`'s
webtest section and `_test/webtest-guard.ps1`, driven by
`test_webtest_guard_pwsh.py`.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
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


def _in_image(repo, monkeypatch, version):
    monkeypatch.setenv(webtest_guard.IMAGE_ENV, webtest_guard.PINNED_IMAGE)
    monkeypatch.setattr(sys, "platform", "linux")
    if version:
        _write(repo, "node_modules/@playwright/test/package.json", json.dumps({"version": version}))


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
