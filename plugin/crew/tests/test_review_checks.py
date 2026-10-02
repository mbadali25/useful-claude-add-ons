"""`review_checks.py` (L-0574): no new linter findings in the review bundle,
judged against the bundle's own base, and an unknown that is never a pass.

The linters here are one fake (`_FAKE`), run through each linter's real
`command` slot, that speaks each tool's real output format: a line
`# LINT <rule> <message>` in a file is a finding, `# ABORT` is that tool's
parse-abort marker. The two `test_real_*` tests run the real ruff and the
real PSScriptAnalyzer and are skipped, with the reason, when the tool is
absent. Every repository lives under pytest's tmp_path.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_checks as rc
from review_fixtures import git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_PATCH = os.path.join(_SCRIPTS, "review_patch.py")

_FAKE = textwrap.dedent(r'''
    import json, os, sys, time
    tool, args = sys.argv[1], sys.argv[2:]
    mode = os.environ.get("FAKE_LINT_MODE", "")
    if os.environ.get("FAKE_LINT_ARGV_OUT"):
        with open(os.environ["FAKE_LINT_ARGV_OUT"], "w", encoding="utf-8") as fh:
            json.dump({"argv": sys.argv[1:], "env": dict(os.environ)}, fh)
    if mode == "rc":
        sys.stderr.write("fake: broken\n"); sys.exit(4)
    if mode == "sleep":
        time.sleep(30)
    if mode == "badjson":
        print("this is not json"); sys.exit(0)
    if mode == "empty":
        sys.exit(0)
    if mode == "nomessage":
        if tool == "shellcheck":
            print(json.dumps({"comments": [{"file": f, "code": 2086, "level": "warning"}
                                           for f in args if os.path.isfile(f)]}))
            sys.exit(1)
        print(json.dumps([{"filename": os.path.abspath(f), "filepath": f, "file": f,
                           "code": "BLE001", "kind": "expression", "rule": "R"}
                          for f in (open(args[-2]).read().split() if tool == "pwsh"
                                    else [a for a in args if os.path.isfile(a)])]))
        sys.exit(1 if tool == "actionlint" else 0)
    if mode in ("orphan", "orphan-exit"):
        import subprocess
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        with open(os.environ["FAKE_LINT_PID_OUT"], "w", encoding="utf-8") as fh:
            fh.write(str(child.pid))
        if mode == "orphan":
            time.sleep(60)
        print("[]"); sys.exit(0)
    if mode == "rc1-none":
        print(json.dumps({"comments": []}) if tool == "shellcheck" else "[]"); sys.exit(1)
    if tool == "pwsh":
        files = [l for l in open(args[-2], encoding="utf-8").read().splitlines() if l]
    else:
        files = [a for a in args if not a.startswith("-") and os.path.isfile(a)]
    rows = []
    for name in files:
        for line in open(name, encoding="utf-8").read().splitlines():
            if line.startswith("# LINT "):
                _, _, rule, msg = line.split(" ", 3)
                rows.append((name, rule, msg, False))
            elif line.startswith("# ABORT"):
                rows.append((name, None, "parse stopped here", True))
    bad = os.environ.get("FAKE_LINT_BAD_ROW", "")
    bad_file = next((f for f in files if f.startswith(bad + "/") or f"/{bad}/" in f), None)
    def extra(key, where):
        """One row with no message, after the good ones: in a head or base
        file, or naming no file at all ("nowhere")."""
        if not bad:
            return []
        row = {"code": "X1", "kind": "x", "rule": "R", "severity": "Warning", "level": "warning"}
        if bad_file:
            row[key] = where(bad_file)
        return [row]
    if tool == "ruff":
        print(json.dumps([{"filename": os.path.abspath(n), "message": m,
                           "code": None if a else r} for n, r, m, a in rows]
                         + extra("filename", os.path.abspath))); sys.exit(0)
    if tool == "shellcheck":
        print(json.dumps({"comments": [{"file": n, "code": 1072 if a else int(r),
                                        "level": "error", "message": m} for n, r, m, a in rows]
                          + extra("file", str)}))
        sys.exit(0 if mode == "rc0-rows" else 1 if rows or bad else 0)
    if tool == "actionlint":
        print(json.dumps([{"filepath": n, "kind": "syntax-check" if a else r, "message": m}
                          for n, r, m, a in rows] + extra("filepath", str)))
        sys.exit(0 if mode == "rc0-rows" else 1 if rows or bad else 0)
    if tool == "pwsh":
        print(json.dumps([{"file": n, "rule": r or "", "message": m,
                           "severity": "ParseError" if a else "Warning"}
                          for n, r, m, a in rows] + extra("file", str))); sys.exit(0)
''')

_TOOLS = {  # tool -> (fake argv[1], a file it lints, a rule name it would report)
    "ruff": ("ruff", "pkg/mod.py", "BLE001"),
    "shellcheck": ("shellcheck", "bin/run.sh", "2086"),
    "psscriptanalyzer": ("pwsh", "ps/tool.ps1", "PSAvoidUsingEmptyCatchBlock"),
    "actionlint": ("actionlint", ".github/workflows/ci.yml", "expression"),
}


@pytest.fixture(name="fake")
def _fake(tmp_path):
    path = tmp_path / "fake_lint.py"
    path.write_text(_FAKE, encoding="utf-8")
    return str(path)


def _config(repo, linters):
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "verify.json").write_text(
        json.dumps({"version": 1, "rules": [], rc.CONFIG_KEY: {"linters": linters}}),
        encoding="utf-8")


def _linter(fake, tool, **extra):
    return dict({"tool": tool, "command": [sys.executable, fake, _TOOLS[tool][0]]}, **extra)


def _repo(tmp_path, files):
    repo = init_repo(tmp_path / "r")
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    return repo


def _bundle(repo, tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir(exist_ok=True)
    base = _base(repo)
    subprocess.run([sys.executable, _PATCH, "--root", str(repo), "--base", base,
                    "--out", str(scratch / "diff.txt"), "--manifest", str(scratch / "manifest.json")],
                   check=True, capture_output=True, stdin=subprocess.DEVNULL)
    return str(scratch / "manifest.json")


def _base(repo):
    return (repo / ".base").read_text(encoding="utf-8").strip()


def _start(tmp_path, files, linters_for):
    """A repo whose base commit holds `files`, its sha in .base (untracked,
    ignored by a .gitignore committed with the base)."""
    files = dict(files, **{".gitignore": ".base\n.crew/\n"})
    repo = _repo(tmp_path, files)
    (repo / ".base").write_text(git(repo, "rev-parse", "HEAD").strip(), encoding="utf-8")
    _config(repo, linters_for)
    return repo


def _edit(repo, rel, text):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text, encoding="utf-8")


def _one(repo, tmp_path):
    results, configured = rc.run_checks(str(repo), _bundle(repo, tmp_path))
    assert configured
    assert len(results) == 1, results
    return results[0]


@pytest.mark.parametrize("tool", sorted(_TOOLS))
def test_new_finding_fails(tmp_path, fake, tool):
    _, rel, rule = _TOOLS[tool]
    repo = _start(tmp_path, {rel: "line one\n"}, [_linter(fake, tool)])
    _edit(repo, rel, f"line one\n# LINT {rule} a new problem\n")

    result = _one(repo, tmp_path)

    expected_rule = f"SC{rule}" if tool == "shellcheck" else rule
    assert (result["status"], result["new"]) == (rc.FAIL, [
        {"path": rel, "rule": expected_rule, "message": "a new problem", "count": 1}]), result


@pytest.mark.parametrize("tool", sorted(_TOOLS))
def test_existing_finding_moved_is_not_new(tmp_path, fake, tool):
    _, rel, rule = _TOOLS[tool]
    repo = _start(tmp_path, {rel: f"# LINT {rule} old problem\nline\n"}, [_linter(fake, tool)])
    _edit(repo, rel, f"line\nmore\n# LINT {rule} old   problem\n")

    result = _one(repo, tmp_path)

    assert (result["status"], result["new"]) == (rc.PASS, []), result


def test_fixed_finding_passes(tmp_path, fake):
    repo = _start(tmp_path, {"a.py": "# LINT BLE001 old\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "fixed\n")

    assert _one(repo, tmp_path)["status"] == rc.PASS


def test_a_second_copy_of_an_existing_finding_is_new(tmp_path, fake):
    repo = _start(tmp_path, {"a.py": "# LINT BLE001 same\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "# LINT BLE001 same\n# LINT BLE001 same\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["count"] for r in result["new"]]) == (rc.FAIL, [1]), result


def test_no_matching_files_is_na_and_never_runs_the_tool(tmp_path):
    repo = _start(tmp_path, {"notes.txt": "x\n"},
                  [{"tool": "shellcheck", "command": ["no-such-linter-l0574"]}])
    _edit(repo, "notes.txt", "y\n")

    result = _one(repo, tmp_path)

    assert (result["status"], result["files"]) == (rc.NA, 0), result


def _bogus_blob(manifest_path):
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    for entry in manifest["entries"]:
        entry["new_id"] = "1" * 40
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)


_COULD_NOT = {
    # case -> (linter overrides, env mode, file text in the bundle, base text, detail fragment)
    "missing-tool": ({"command": ["no-such-linter-l0574"]}, "", "x\n", "x0\n", "not on PATH"),
    "unexpected-exit": ({}, "rc", "x\n", "x0\n", "exited 4"),
    "bad-json": ({}, "badjson", "x\n", "x0\n", "not the JSON"),
    "timeout": ({"timeout": 1}, "sleep", "x\n", "x0\n", "timed out"),
    "abort-in-bundle": ({}, "", "# ABORT\n", "x0\n", "bundle: SC1072"),
    "abort-in-base": ({}, "", "x\n", "# ABORT\n", "base: SC1072"),
    "unreadable-blob": ({}, "", "x\n", "x0\n", "cannot read blob"),
    "exit-1-but-no-findings": ({}, "rc1-none", "x\n", "x0\n", "disagree"),
    "bad-base": ({}, "", "x\n", "x0\n", "not a commit"),
}


@pytest.mark.parametrize("case", sorted(_COULD_NOT))
def test_could_not_check_cases(tmp_path, fake, monkeypatch, case):
    overrides, mode, text, base_text, fragment = _COULD_NOT[case]
    repo = _start(tmp_path, {"run.sh": base_text}, [_linter(fake, "shellcheck", **overrides)])
    _edit(repo, "run.sh", text)
    monkeypatch.setenv("FAKE_LINT_MODE", mode)
    manifest = _bundle(repo, tmp_path)
    if case == "unreadable-blob":
        _bogus_blob(manifest)
    if case == "bad-base":
        _tamper(manifest, lambda m: m.update(base="2" * 40))

    results, _ = rc.run_checks(str(repo), manifest)

    assert (results[0]["status"], fragment in results[0]["detail"],
            rc.overall(results)) == (rc.COULD_NOT, True, rc.COULD_NOT), results


@pytest.mark.parametrize("verify_json, fragment", [
    ("{not json", "could not be read"),
    (json.dumps({rc.CONFIG_KEY: {"linters": []}}), "non-empty"),
    (json.dumps({rc.CONFIG_KEY: {"linters": [{"tool": "eslint"}]}}), "tool must be one of"),
    (json.dumps({rc.CONFIG_KEY: {"linters": [{"tool": "ruff", "colour": 1}]}}), "unknown key"),
    (json.dumps({rc.CONFIG_KEY: {"linters": [{"tool": "ruff", "rules": ["X"]}]}}),
     "psscriptanalyzer only"),
    (json.dumps({rc.CONFIG_KEY: {"linters": [{"tool": "ruff", "timeout": 0}]}}),
     "positive integer"),
    (json.dumps({rc.CONFIG_KEY: {"linters": [{"tool": "ruff", "args": "S110"}]}}),
     "list of strings"),
    (json.dumps({rc.CONFIG_KEY: {"linters": [{"tool": "ruff"}], "linter": []}}),
     "unknown key(s) linter"),
    (json.dumps({rc.CONFIG_KEY: {"linters": [{"tool": ["ruff"]}]}}), "tool must be one of"),
])
def test_a_config_it_cannot_read_is_could_not_check(tmp_path, verify_json, fragment):
    repo = _start(tmp_path, {"a.py": "x\n"}, [])
    (repo / ".crew" / "verify.json").write_text(verify_json, encoding="utf-8")
    _edit(repo, "a.py", "y\n")

    results, configured = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert (configured, results[0]["name"], results[0]["status"],
            fragment in results[0]["detail"]) == (True, "config", rc.COULD_NOT, True), results


def test_an_unreadable_manifest_is_could_not_check(tmp_path, fake):
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])

    results, _ = rc.run_checks(str(repo), str(tmp_path / "missing.json"))

    assert (results[0]["name"], results[0]["status"]) == ("manifest", rc.COULD_NOT)


def test_unconfigured_is_reported_as_not_configured(tmp_path):
    repo = init_repo(tmp_path / "r")

    assert rc.run_checks(str(repo), str(tmp_path / "unused.json")) == ([], False)


def test_rename_added_deleted(tmp_path, fake):
    repo = _start(tmp_path, {"old.py": "# LINT BLE001 kept\nbody\nbody\nbody\n",
                             "gone.py": "# LINT BLE001 gone\n"}, [_linter(fake, "ruff")])
    git(repo, "mv", "old.py", "new.py")
    os.remove(repo / "gone.py")
    _edit(repo, "added.py", "# LINT BLE001 fresh\n")

    result = _one(repo, tmp_path)

    assert (result["status"], result["files"], result["new"]) == (rc.FAIL, 2, [
        {"path": "added.py", "rule": "BLE001", "message": "fresh", "count": 1}]), result


def test_the_bundle_blob_is_checked_not_a_later_working_tree(tmp_path, fake):
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "# LINT BLE001 in the bundle\n")
    manifest = _bundle(repo, tmp_path)
    _edit(repo, "a.py", "cleaned after the bundle was built\n")

    results, _ = rc.run_checks(str(repo), manifest)

    assert results[0]["status"] == rc.FAIL, results


@pytest.mark.parametrize("statuses, expected", [
    ([rc.PASS, rc.NA], rc.PASS), ([rc.PASS, rc.COULD_NOT], rc.COULD_NOT),
    ([rc.COULD_NOT, rc.FAIL], rc.FAIL), ([], rc.PASS)])
def test_overall(statuses, expected):
    assert rc.overall([{"status": s} for s in statuses]) == expected


@pytest.mark.parametrize("mode, text, code", [
    ("", "x\n", 0), ("", "# LINT BLE001 new\n", 1), ("rc", "x\n", 3)])
def test_cli_exit_codes(tmp_path, fake, monkeypatch, capsys, mode, text, code):
    repo = _start(tmp_path, {"a.py": "x0\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", text)
    monkeypatch.setenv("FAKE_LINT_MODE", mode)

    assert rc.main(["--root", str(repo), "--manifest", _bundle(repo, tmp_path)]) == code
    assert "pre-review checks: ruff" in capsys.readouterr().out


def test_recorded_is_bound_to_the_bundle(tmp_path):
    rc.record(str(tmp_path), "sha-a", [_ROW], False, False)

    assert (rc.recorded(str(tmp_path), "sha-a")["result"],
            rc.recorded(str(tmp_path), "sha-b")["result"]) == (rc.PASS, rc.NOT_RECORDED)


@pytest.mark.parametrize("content", [None, "{torn"])
def test_a_missing_or_torn_record_is_not_recorded_never_none(tmp_path, content):
    if content is not None:
        (tmp_path / rc.RESULT_FILE).write_text(content, encoding="utf-8")

    found = rc.recorded(str(tmp_path), "sha-a")

    assert (found["result"], bool(found["reason"])) == (rc.NOT_RECORDED, True)


@pytest.mark.parametrize("side", ["base", "bundle"])
@pytest.mark.parametrize("tool", sorted(_TOOLS))
def test_parse_abort_either_side(tmp_path, fake, tool, side):
    """A broken base must not baseline the bundle's new finding away."""
    _, rel, rule = _TOOLS[tool]
    base_text = "# ABORT\n# LINT {0} seen\n" if side == "base" else "line\n"
    bundle_text = "# ABORT\n# LINT {0} seen\n# LINT {0} added\n" if side == "base" else (
        "# ABORT\nline\n")
    repo = _start(tmp_path, {rel: base_text.format(rule)}, [_linter(fake, tool)])
    _edit(repo, rel, bundle_text.format(rule))

    result = _one(repo, tmp_path)

    assert (result["status"], f"{side}:" in result["detail"]) == (rc.COULD_NOT, True), result


def test_path_dependent_config_applies(tmp_path):
    if not _ruff_present():
        pytest.skip("ruff is not importable by this python, so this real-tool case did not run")
    toml = '[lint]\nselect = ["F"]\n[lint.per-file-ignores]\n"**/_test/**" = ["BLE001"]\n'
    repo = _start(tmp_path, {"ruff.toml": toml, "pkg/_test/t.py": "x = 1\n",
                             "pkg/m.py": "x = 1\n"},
                  [{"tool": "ruff", "args": ["--extend-select", "BLE001"]}])
    blind = "x = 1\ntry:\n    x = 2\nexcept Exception:\n    x = 3\n"
    _edit(repo, "pkg/_test/t.py", blind)
    _edit(repo, "pkg/m.py", blind)

    result = _one(repo, tmp_path)

    assert (result["status"], [r["path"] for r in result["new"]]) == (
        rc.FAIL, ["pkg/m.py"]), result


def test_config_is_taken_from_the_bundle_not_the_live_tree(tmp_path):
    if not _ruff_present():
        pytest.skip("ruff is not importable by this python, so this real-tool case did not run")
    repo = _start(tmp_path, {"ruff.toml": '[lint]\nselect = ["F"]\n', "m.py": "x = 1\n"},
                  [{"tool": "ruff", "args": ["--extend-select", "BLE001"]}])
    _edit(repo, "m.py", "x = 1\ntry:\n    x = 2\nexcept Exception:\n    x = 3\n")
    manifest = _bundle(repo, tmp_path)
    _edit(repo, "ruff.toml", '[lint]\nselect = ["F"]\nignore = ["BLE001"]\n'
                             '[lint.per-file-ignores]\n"*" = ["BLE001"]\n')

    results, _ = rc.run_checks(str(repo), manifest)

    assert results[0]["status"] == rc.FAIL, results


def _ruff_present():
    return subprocess.run([sys.executable, "-m", "ruff", "--version"], capture_output=True,
                          stdin=subprocess.DEVNULL, check=False).returncode == 0


def test_real_ruff_catches_blind_except(tmp_path):
    if not _ruff_present():
        pytest.skip("ruff is not importable by this python, so this real-tool case did not run")
    repo = _start(tmp_path, {"ruff.toml": '[lint]\nselect = ["F"]\n', "m.py": "x = 1\n"},
                  [{"tool": "ruff", "args": ["--extend-select", "BLE001"]}])
    _edit(repo, "m.py", "x = 1\ntry:\n    x = 2\nexcept Exception:\n    x = 3\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["rule"] for r in result["new"]]) == (rc.FAIL, ["BLE001"]), result


def _pssa_present():
    pwsh = shutil.which("pwsh")
    return pwsh and subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command",
         "if (Get-Module -ListAvailable PSScriptAnalyzer) { exit 0 } else { exit 1 }"],
        capture_output=True, stdin=subprocess.DEVNULL, check=False, timeout=120).returncode == 0


def test_real_pssa_catches_empty_catch(tmp_path):
    if not _pssa_present():
        pytest.skip("pwsh with PSScriptAnalyzer is not installed, so this real-tool case did not run")
    repo = _start(tmp_path, {"t.ps1": "Write-Output 'a'\n"},
                  [{"tool": "psscriptanalyzer", "rules": ["PSAvoidUsingEmptyCatchBlock"]}])
    _edit(repo, "t.ps1", "try { Write-Output 'a' } catch { }\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["rule"] for r in result["new"]]) == (
        rc.FAIL, ["PSAvoidUsingEmptyCatchBlock"]), result


def test_real_pssa_unknown_rule_is_could_not_check(tmp_path):
    if not _pssa_present():
        pytest.skip("pwsh with PSScriptAnalyzer is not installed, so this real-tool case did not run")
    repo = _start(tmp_path, {"t.ps1": "Write-Output 'a'\n"},
                  [{"tool": "psscriptanalyzer", "rules": ["PSNoSuchRuleL0574"]}])
    _edit(repo, "t.ps1", "Write-Output 'b'\n")

    result = _one(repo, tmp_path)

    assert (result["status"], "PSNoSuchRuleL0574" in result["detail"]) == (rc.COULD_NOT, True), result


def _tamper(manifest_path, change):
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    change(manifest)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)


@pytest.mark.parametrize("change", ["entries-not-list", "entry-not-dict", "path-not-str"])
def test_a_manifest_of_the_wrong_shape_is_could_not_check(tmp_path, fake, change):
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "y\n")
    manifest = _bundle(repo, tmp_path)
    _tamper(manifest, {
        "entries-not-list": lambda m: m.update(entries={"a.py": 1}),
        "entry-not-dict": lambda m: m.update(entries=["a.py"]),
        "path-not-str": lambda m: m["entries"][0].update(path=7)}[change])

    results, _ = rc.run_checks(str(repo), manifest)

    assert (results[0]["name"], results[0]["status"]) == ("manifest", rc.COULD_NOT), results


@pytest.mark.parametrize("path", ["../escape.py", "/abs/escape.py"])
def test_a_path_outside_the_tree_is_could_not_check(tmp_path, fake, path):
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "y\n")
    manifest = _bundle(repo, tmp_path)
    _tamper(manifest, lambda m: m["entries"][0].update(path=path))

    result = rc.run_checks(str(repo), manifest)[0][0]

    assert (result["status"], "outside the tree" in result["detail"],
            os.path.exists(tmp_path / "escape.py")) == (rc.COULD_NOT, True, False), result


def test_a_batch_shim_is_could_not_check(tmp_path):
    shim = tmp_path / "lint.cmd"
    shim.write_text("@echo off\n", encoding="utf-8")
    repo = _start(tmp_path, {"a.py": "x\n"}, [{"tool": "ruff", "command": [str(shim)]}])
    _edit(repo, "a.py", "y\n")

    result = _one(repo, tmp_path)

    assert (result["status"], "batch-file shim" in result["detail"]) == (rc.COULD_NOT, True)


def test_the_linter_gets_no_secrets_and_no_user_config(tmp_path, fake, monkeypatch):
    out = tmp_path / "seen.json"
    repo = _start(tmp_path, {"run.sh": "x\n"}, [_linter(fake, "shellcheck")])
    _edit(repo, "run.sh", "y\n")
    monkeypatch.setenv("FAKE_LINT_ARGV_OUT", str(out))
    monkeypatch.setenv("GH_TOKEN", "do-not-pass")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "user-config"))

    assert _one(repo, tmp_path)["status"] == rc.PASS
    seen = json.loads(out.read_text(encoding="utf-8"))

    assert ("GH_TOKEN" in seen["env"], seen["env"]["XDG_CONFIG_HOME"].startswith(
        str(tmp_path / "user-config")), "--norc" in seen["argv"]) == (False, False, True), seen


def test_shellcheck_reads_the_bundles_rc_file(tmp_path, fake, monkeypatch):
    out = tmp_path / "seen.json"
    repo = _start(tmp_path, {".shellcheckrc": "disable=SC2086\n", "run.sh": "x\n"},
                  [_linter(fake, "shellcheck")])
    _edit(repo, "run.sh", "y\n")
    monkeypatch.setenv("FAKE_LINT_ARGV_OUT", str(out))

    _one(repo, tmp_path)
    argv = json.loads(out.read_text(encoding="utf-8"))["argv"]

    assert argv[argv.index("--rcfile") + 1].endswith(os.path.join("head", ".shellcheckrc")), argv


@pytest.mark.parametrize("mode", ["rc1-none", "empty"])
def test_actionlint_output_that_contradicts_its_status_is_could_not_check(
        tmp_path, fake, monkeypatch, mode):
    rel = ".github/workflows/ci.yml"
    repo = _start(tmp_path, {rel: "x\n"}, [_linter(fake, "actionlint")])
    _edit(repo, rel, "y\n")
    monkeypatch.setenv("FAKE_LINT_MODE", mode)

    assert _one(repo, tmp_path)["status"] == rc.COULD_NOT


def test_a_note_in_the_block_is_an_unknown_key(tmp_path, fake):
    """Review round 3: only `linters` is allowed under preReview, so a `_note`
    fails closed like any other unknown key (owner 2026-10-02)."""
    repo = _start(tmp_path, {"a.py": "x\n"}, [])
    (repo / ".crew" / "verify.json").write_text(json.dumps({rc.CONFIG_KEY: {
        "_note": ["prose"], "linters": [_linter(fake, "ruff")]}}), encoding="utf-8")
    _edit(repo, "a.py", "y\n")

    result = _one(repo, tmp_path)

    assert (result["name"], result["status"], "_note" in result["detail"]) == (
        "config", rc.COULD_NOT, True), result


@pytest.mark.parametrize("name", ["actionlint.yaml", "actionlint.yml"])
def test_actionlint_is_handed_the_bundles_config_by_name(tmp_path, fake, monkeypatch, name):
    out = tmp_path / "seen.json"
    rel = ".github/workflows/ci.yml"
    repo = _start(tmp_path, {f".github/{name}": "self-hosted-runner:\n  labels: []\n", rel: "x\n"},
                  [_linter(fake, "actionlint")])
    _edit(repo, rel, "y\n")
    monkeypatch.setenv("FAKE_LINT_ARGV_OUT", str(out))

    _one(repo, tmp_path)
    argv = json.loads(out.read_text(encoding="utf-8"))["argv"]

    assert argv[argv.index("-config-file") + 1].endswith(name), argv


def test_a_record_of_the_wrong_shape_is_not_recorded(tmp_path):
    (tmp_path / rc.RESULT_FILE).write_text(json.dumps({"bundle_sha256": "sha-a"}),
                                           encoding="utf-8")

    assert rc.recorded(str(tmp_path), "sha-a")["result"] == rc.NOT_RECORDED


_ROW = {"name": "ruff", "status": rc.PASS, "files": 1, "new": [], "detail": ""}
_NEW = {"path": "a.py", "rule": "X", "message": "m", "count": 1}


@pytest.mark.parametrize("payload", [
    {"result": rc.PASS, "checks": [{"status": rc.FAIL}]},
    {"result": rc.PASS, "checks": [dict(_ROW, status=rc.FAIL)]},
    {"result": rc.PASS, "checks": [dict(_ROW, status=rc.COULD_NOT)]},
    {"result": rc.FAIL, "checks": [_ROW]},
    {"result": rc.NOT_CONFIGURED, "checks": [_ROW]},
    {"result": rc.PASS, "checks": [dict(_ROW, status="green")]},
    {"result": rc.PASS, "checks": [{k: v for k, v in _ROW.items() if k != "files"}]},
    {"result": rc.PASS, "checks": [dict(_ROW, files=True)]},
    {"result": rc.PASS, "checks": [dict(_ROW, new="none")]},
    {"result": rc.PASS, "checks": [dict(_ROW, detail=None)]},
    {"result": rc.FAIL, "checks": [dict(_ROW, status=rc.FAIL, new=[{"path": "a.py"}])]},
    # review round 4: each row's status has to agree with its own findings
    {"result": rc.PASS, "checks": [dict(_ROW, new=[_NEW])]},
    {"result": rc.COULD_NOT, "checks": [dict(_ROW, status=rc.COULD_NOT, new=[_NEW])]},
    {"result": rc.PASS, "checks": [dict(_ROW, status=rc.NA, new=[_NEW])]},
    {"result": rc.FAIL, "checks": [dict(_ROW, status=rc.FAIL)]},
    {"result": rc.FAIL, "checks": [dict(_ROW, status=rc.FAIL, new=[dict(_NEW, count=0)])]},
    {"result": rc.PASS, "checks": [dict(_ROW, status=rc.NA, files=2)]},
    # ... and the flags with the result they can only come with
    {"result": rc.PASS, "checks": [_ROW], "overridden": True},
    {"result": rc.FAIL, "checks": [dict(_ROW, status=rc.FAIL, new=[_NEW])], "overridden": True},
    {"result": rc.PASS, "checks": [_ROW], "stood_down": True},
    {"result": rc.NOT_CONFIGURED, "checks": [], "stood_down": True},
    {"result": rc.COULD_NOT, "checks": [dict(_ROW, status=rc.COULD_NOT)],
     "overridden": True, "stood_down": True}])
def test_a_record_that_contradicts_itself_is_not_recorded(tmp_path, payload):
    """Review round 3: a same-bundle record is accepted only in the shape
    record() writes, and only when its result is what its checks add up to."""
    (tmp_path / rc.RESULT_FILE).write_text(json.dumps(dict(
        dict(overridden=False, stood_down=False), bundle_sha256="sha-a", **payload)),
        encoding="utf-8")

    assert rc.recorded(str(tmp_path), "sha-a")["result"] == rc.NOT_RECORDED


@pytest.mark.parametrize("checks, configured", [
    ([_ROW], True), ([dict(_ROW, status=rc.NA, files=0)], True), ([], False),
    ([dict(_ROW, status=rc.FAIL, new=[{"path": "a.py", "rule": "X", "message": "m",
                                       "count": 1}])], True),
    ([dict(_ROW, status=rc.COULD_NOT, detail="tool missing")], True)])
def test_every_record_record_writes_reads_back(tmp_path, checks, configured):
    rc.record(str(tmp_path), "sha-a", checks, False, False, configured)

    assert rc.recorded(str(tmp_path), "sha-a")["result"] == rc.overall(checks, configured)


@pytest.mark.parametrize("checks, overridden, stood_down", [
    ([dict(_ROW, status=rc.COULD_NOT)], True, False),
    ([dict(_ROW, status=rc.COULD_NOT)], False, True),
    ([dict(_ROW, status=rc.FAIL, new=[_NEW])], False, True)])
def test_an_override_or_stand_down_record_reads_back(tmp_path, checks, overridden, stood_down):
    rc.record(str(tmp_path), "sha-a", checks, overridden, stood_down)

    assert rc.recorded(str(tmp_path), "sha-a")["result"] == rc.overall(checks)


@pytest.mark.parametrize("content", ["[]", "null", '"text"', "3"])
def test_a_verify_map_that_is_not_an_object_is_could_not_check(tmp_path, content):
    """Review round 4: valid JSON that is not an object is a broken map, not
    an absent `preReview` key."""
    repo = init_repo(tmp_path / "r")
    (repo / ".crew").mkdir()
    (repo / ".crew" / "verify.json").write_text(content, encoding="utf-8")

    results, configured = rc.run_checks(str(repo), str(tmp_path / "unused.json"))

    assert (configured, [(r["name"], r["status"]) for r in results]) == (
        True, [("config", rc.COULD_NOT)]), results


def test_a_verify_map_without_the_key_is_still_not_configured(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / ".crew").mkdir()
    (repo / ".crew" / "verify.json").write_text('{"version": 1}', encoding="utf-8")

    assert rc.run_checks(str(repo), str(tmp_path / "unused.json")) == ([], False)


@pytest.mark.parametrize("tool", sorted(_TOOLS))
@pytest.mark.parametrize("where", ["head", "nowhere"])
def test_a_bad_row_does_not_discard_a_known_new_finding(tmp_path, fake, monkeypatch, tool,
                                                        where):
    """Review round 4: a row the checks cannot read, after a good one, leaves
    the good rows standing. A NEW finding still FAILs (never overridable);
    the bad row is named in the detail."""
    _, rel, rule = _TOOLS[tool]
    repo = _start(tmp_path, {rel: "line one\n"}, [_linter(fake, tool)])
    _edit(repo, rel, f"line one\n# LINT {rule} a new problem\n")
    monkeypatch.setenv("FAKE_LINT_BAD_ROW", where)

    result = _one(repo, tmp_path)

    assert (result["status"], len(result["new"]), "could not read" in result["detail"]) == (
        rc.FAIL, 1, True), result


@pytest.mark.parametrize("tool", sorted(_TOOLS))
def test_a_bad_base_row_leaves_that_file_unchecked(tmp_path, fake, monkeypatch, tool):
    """The base output for that file is incomplete, so a head finding in it
    may already be in the base: that file is could-not-check, like a base
    parse abort."""
    _, rel, rule = _TOOLS[tool]
    repo = _start(tmp_path, {rel: "line one\n"}, [_linter(fake, tool)])
    _edit(repo, rel, f"line one\n# LINT {rule} a new problem\n")
    monkeypatch.setenv("FAKE_LINT_BAD_ROW", "base")

    result = _one(repo, tmp_path)

    assert (result["status"], result["new"]) == (rc.COULD_NOT, []), result


def test_a_bad_base_row_in_one_file_does_not_hide_a_new_finding_in_another(
        tmp_path, fake, monkeypatch):
    repo = _start(tmp_path, {"a.py": "x\n", "b.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "y\n")
    _edit(repo, "b.py", "x\n# LINT BLE001 a new problem\n")
    monkeypatch.setenv("FAKE_LINT_BAD_ROW", "base")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["path"] for r in result["new"]]) == (rc.FAIL, ["b.py"]), result


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return fh.read().split(") ", 1)[1][0] != "Z"
    except OSError:
        return True


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups; Windows uses taskkill /T")
@pytest.mark.parametrize("mode", ["orphan", "orphan-exit"])
def test_the_timeout_holds_when_a_child_keeps_the_output_open(tmp_path, fake, monkeypatch, mode):
    """Review round 4: a linter (or one it leaves behind after exiting)
    whose child holds stdout open must still time out, and the whole group is
    killed, not only the direct child."""
    import time  # pylint: disable=import-outside-toplevel
    pid_out = tmp_path / "child.pid"
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff", timeout=2)])
    _edit(repo, "a.py", "y\n")
    monkeypatch.setenv("FAKE_LINT_MODE", mode)
    monkeypatch.setenv("FAKE_LINT_PID_OUT", str(pid_out))

    started = time.monotonic()
    result = _one(repo, tmp_path)
    elapsed = time.monotonic() - started
    pid = int(pid_out.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)

    assert (result["status"], "timed out" in result["detail"], elapsed < 20, _alive(pid)) == (
        rc.COULD_NOT, True, True, False), (result, elapsed)


def test_a_config_renamed_away_is_gone_from_the_bundle(tmp_path, fake, monkeypatch):
    """Review round 3 BLOCK: a root config the bundle renames away must not
    be reloaded from the base, where it could disable a new finding."""
    out = tmp_path / "seen.json"
    repo = _start(tmp_path, {".shellcheckrc": "disable=SC2086\n", "run.sh": "x\n"},
                  [_linter(fake, "shellcheck")])
    (repo / "docs").mkdir()
    git(repo, "mv", ".shellcheckrc", "docs/old.shellcheckrc")
    _edit(repo, "run.sh", "y\n")
    monkeypatch.setenv("FAKE_LINT_ARGV_OUT", str(out))

    _one(repo, tmp_path)
    argv = json.loads(out.read_text(encoding="utf-8"))["argv"]

    assert ("--rcfile" in argv, "--norc" in argv) == (False, True), argv


def test_a_config_renamed_into_place_is_the_bundles(tmp_path, fake, monkeypatch):
    out = tmp_path / "seen.json"
    repo = _start(tmp_path, {"docs/new.shellcheckrc": "disable=SC2086\n", "run.sh": "x\n"},
                  [_linter(fake, "shellcheck")])
    git(repo, "mv", "docs/new.shellcheckrc", ".shellcheckrc")
    _edit(repo, "run.sh", "y\n")
    monkeypatch.setenv("FAKE_LINT_ARGV_OUT", str(out))

    _one(repo, tmp_path)
    argv = json.loads(out.read_text(encoding="utf-8"))["argv"]

    assert argv[argv.index("--rcfile") + 1].endswith(os.path.join("head", ".shellcheckrc")), argv


def test_record_leaves_no_staging_file(tmp_path):
    rc.record(str(tmp_path), "sha-a", [], False, False)
    rc.record(str(tmp_path), "sha-a", [], False, False)

    assert sorted(os.listdir(tmp_path)) == [rc.RESULT_FILE]


def test_a_shell_shellcheck_does_not_support_is_could_not_check(tmp_path, fake):
    repo = _start(tmp_path, {"run.sh": "# LINT 1071 zsh is not supported\n"},
                  [_linter(fake, "shellcheck")])
    _edit(repo, "run.sh", "# LINT 1071 zsh is not supported\nmore\n")

    result = _one(repo, tmp_path)

    assert (result["status"], "SC1071" in result["detail"]) == (rc.COULD_NOT, True), result


@pytest.mark.parametrize("message, same_as", [
    ("Redefinition of unused `os` from line 3", "Redefinition of unused `os` from line 5"),
    ("SC2086:info:2:28: Double quote", "SC2086:info:7:3: Double  quote"),
    ("defined at line 4, column 9", "defined at line 40, column 1")])
def test_line_numbers_inside_a_message_do_not_make_a_finding_new(message, same_as):
    assert rc._normalise(message) == rc._normalise(same_as)  # pylint: disable=protected-access


@pytest.mark.parametrize("message, other", [
    ("requires 2 approvals", "requires 3 approvals"),
    ("Line too long (120 > 110)", "Line too long (140 > 110)"),
    ("SC2086 at depth 1", "SC2086 at depth 2")])
def test_digits_that_are_not_positions_still_tell_findings_apart(message, other):
    assert rc._normalise(message) != rc._normalise(other)  # pylint: disable=protected-access


def test_a_changed_value_in_a_message_is_a_new_finding(tmp_path, fake):
    repo = _start(tmp_path, {"a.py": "# LINT X99 requires 2 approvals\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "# LINT X99 requires 3 approvals\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["message"] for r in result["new"]]) == (
        rc.FAIL, ["requires 3 approvals"]), result


def test_actionlint_runs_without_its_host_dependent_passes(tmp_path, fake, monkeypatch):
    out = tmp_path / "seen.json"
    rel = ".github/workflows/ci.yml"
    repo = _start(tmp_path, {rel: "x\n"}, [_linter(fake, "actionlint")])
    _edit(repo, rel, "y\n")
    monkeypatch.setenv("FAKE_LINT_ARGV_OUT", str(out))

    _one(repo, tmp_path)
    argv = json.loads(out.read_text(encoding="utf-8"))["argv"]

    assert ("-shellcheck=" in argv, "-pyflakes=" in argv) == (True, True), argv


def test_real_ruff_moved_redefinition_is_not_new(tmp_path):
    if not _ruff_present():
        pytest.skip("ruff is not importable by this python, so this real-tool case did not run")
    repo = _start(tmp_path, {"ruff.toml": '[lint]\nselect = ["F"]\n',
                             "a.py": "import os\nimport os\n"}, [{"tool": "ruff"}])
    _edit(repo, "a.py", "\n\nimport os\nimport os\n")

    assert _one(repo, tmp_path)["status"] == rc.PASS


def test_real_ruff_unreadable_file_is_could_not_check(tmp_path):
    if not _ruff_present():
        pytest.skip("ruff is not importable by this python, so this real-tool case did not run")
    repo = _start(tmp_path, {"ruff.toml": '[lint]\nselect = ["F"]\n'},
                  [{"tool": "ruff", "args": ["--extend-select", "BLE001"]}])
    (repo / "a.py").write_bytes(b"# -*- coding: latin-1 -*-\nx = 'caf\xe9'\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "latin-1")
    (repo / ".base").write_text(git(repo, "rev-parse", "HEAD").strip(), encoding="utf-8")
    (repo / "a.py").write_bytes(b"# -*- coding: latin-1 -*-\nx = 'caf\xe9'\ntry:\n    x = 1\n"
                                b"except Exception:\n    x = 2\n")

    result = _one(repo, tmp_path)

    assert (result["status"], "E902" in result["detail"]) == (rc.COULD_NOT, True), result


@pytest.mark.parametrize("name, encoding", [("t/a[1].ps1", "utf-8"), ("u.ps1", "utf-16")])
def test_real_pssa_reads_awkward_names_and_utf16(tmp_path, name, encoding):
    if not _pssa_present():
        pytest.skip("pwsh with PSScriptAnalyzer is not installed, so this real-tool case did not run")
    repo = _start(tmp_path, {}, [{"tool": "psscriptanalyzer",
                                  "rules": ["PSAvoidUsingEmptyCatchBlock"]}])
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text("Write-Output 'a'\n", encoding=encoding)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "ps")
    (repo / ".base").write_text(git(repo, "rev-parse", "HEAD").strip(), encoding="utf-8")
    (repo / name).write_text("try { Write-Output 'a' } catch { }\n", encoding=encoding)

    result = _one(repo, tmp_path)

    assert (result["status"], [r["rule"] for r in result["new"]]) == (
        rc.FAIL, ["PSAvoidUsingEmptyCatchBlock"]), result


@pytest.mark.parametrize("tool", sorted(_TOOLS))
def test_a_row_with_no_message_is_could_not_check(tmp_path, fake, monkeypatch, tool):
    _, rel, _ = _TOOLS[tool]
    repo = _start(tmp_path, {rel: "x\n"}, [_linter(fake, tool)])
    _edit(repo, rel, "y\n")
    monkeypatch.setenv("FAKE_LINT_MODE", "nomessage")

    result = _one(repo, tmp_path)

    assert (result["status"], "message" in result["detail"]) == (rc.COULD_NOT, True), result


def test_a_parse_failure_does_not_hide_a_new_finding_elsewhere(tmp_path, fake):
    repo = _start(tmp_path, {"a.sh": "x\n", "b.sh": "x\n"}, [_linter(fake, "shellcheck")])
    _edit(repo, "a.sh", "x\n# LINT 2086 a new problem\n")
    _edit(repo, "b.sh", "# ABORT\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["path"] for r in result["new"]],
            "b.sh" in result["detail"]) == (rc.FAIL, ["a.sh"], True), result


def test_a_parse_failure_alone_is_still_could_not_check(tmp_path, fake):
    repo = _start(tmp_path, {"a.sh": "x\n", "b.sh": "x\n"}, [_linter(fake, "shellcheck")])
    _edit(repo, "a.sh", "x\nmore\n")
    _edit(repo, "b.sh", "# ABORT\n")

    assert _one(repo, tmp_path)["status"] == rc.COULD_NOT


@pytest.mark.parametrize("tool", ["actionlint", "shellcheck"])
@pytest.mark.parametrize("in_base, expected", [(False, rc.FAIL), (True, rc.COULD_NOT)])
def test_a_status_that_disagrees_with_its_rows_keeps_the_rows(tmp_path, fake, monkeypatch, tool,
                                                              in_base, expected):
    """Neighbour of review round 4's bad-row BLOCK: exit 0 beside finding rows
    is a partial answer, but the rows it did print are kept, so a NEW finding
    among them still FAILs. With nothing new it is could-not-check."""
    _, rel, rule = _TOOLS[tool]
    finding = f"# LINT {rule} a problem\n"
    repo = _start(tmp_path, {rel: finding if in_base else "line one\n"}, [_linter(fake, tool)])
    _edit(repo, rel, finding + "more\n")
    monkeypatch.setenv("FAKE_LINT_MODE", "rc0-rows")

    result = _one(repo, tmp_path)

    assert (result["status"], "disagree" in result["detail"]) == (expected, True), result
