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
            json.dump({"argv": sys.argv[1:], "env": dict(os.environ),
                       "texts": {a: open(a, encoding="utf-8").read() for a in sys.argv[2:]
                                 if a.endswith(".txt") and os.path.isfile(a)}}, fh)
    if mode == "rc":
        sys.stderr.write("fake: broken\n"); sys.exit(4)
    if mode == "sleep":
        time.sleep(30)
    if mode == "badjson":
        print("this is not json"); sys.exit(0)
    if mode == "empty":
        sys.exit(0)
    if mode == "setsid-holder":
        import subprocess
        child = subprocess.Popen([sys.executable, "-c",
                                  "import os, time; os.setsid(); time.sleep(60)"])
        with open(os.environ["FAKE_LINT_PID_OUT"], "w", encoding="utf-8") as fh:
            fh.write(str(child.pid))
        print("[]"); sys.exit(0)
    if mode == "sleep-pid":
        with open(os.environ["FAKE_LINT_PID_OUT"], "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        sys.stderr.write("x"); sys.stderr.flush()
        time.sleep(60)
    if mode == "detached":
        import subprocess
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        with open(os.environ["FAKE_LINT_PID_OUT"], "w", encoding="utf-8") as fh:
            fh.write(str(child.pid))
        print("[]"); sys.exit(0)
    if mode == "raw":
        out = os.environ.get("FAKE_LINT_STDOUT", "")
        if out == "ROW_AND_NULL":
            head = [f for f in json.load(open(args[-2], encoding="utf-8"))
                    if "head" in f.replace("\\", "/").split("/")]
            out = json.dumps([{"file": head[0], "rule": "R1", "severity": "Warning",
                               "message": "m"}, None])
        print(out); sys.exit(0)
    if mode == "nomessage":
        if tool == "shellcheck":
            print(json.dumps({"comments": [{"file": f, "code": 2086, "level": "warning"}
                                           for f in args if os.path.isfile(f)]}))
            sys.exit(1)
        print(json.dumps([{"filename": os.path.abspath(f), "filepath": f, "file": f,
                           "code": "BLE001", "kind": "expression", "rule": "R",
                           "severity": "Warning"}
                          for f in (json.load(open(args[-2], encoding="utf-8")) if tool == "pwsh"
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
        files = json.load(open(args[-2], encoding="utf-8"))
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
    # Separators normalised: on Windows os.path.join gives `...\\base/ps/x.ps1`.
    bad_file = next((f for f in files if f.replace("\\", "/").startswith(bad + "/")
                     or f"/{bad}/" in f.replace("\\", "/")), None)
    def extra(key, where):
        """One row with no message, after the good ones: in a head or base
        file, or naming no file at all ("nowhere")."""
        if not bad:
            return []
        row = {"code": "X1", "kind": "x", "rule": "R", "severity": "Warning", "level": "warning"}
        if bad_file:
            row[key] = where(bad_file)
        return [row]
    drop = os.environ.get("FAKE_LINT_DROP", "")
    def emit(out, code):
        for row in (out["comments"] if isinstance(out, dict) else out):
            row.pop(drop, None)
        print(json.dumps(out))
        sys.exit(int(os.environ.get("FAKE_LINT_EXIT") or code))
    if tool == "ruff":
        emit([{"filename": os.path.abspath(n), "message": m, "code": None if a else r}
              for n, r, m, a in rows] + extra("filename", os.path.abspath), 0)
    if tool == "shellcheck":
        emit({"comments": [{"file": n, "code": 1072 if a else int(r), "level": "error",
                            "message": m} for n, r, m, a in rows] + extra("file", str)},
             0 if mode == "rc0-rows" else 1 if rows or bad else 0)
    if tool == "actionlint":
        emit([{"filepath": n, "kind": "syntax-check" if a else r, "message": m}
              for n, r, m, a in rows] + extra("filepath", str),
             0 if mode == "rc0-rows" else 1 if rows or bad else 0)
    if tool == "pwsh":
        emit([{"file": n, "rule": r or "", "message": m,
               "severity": "ParseError" if a else "Warning"}
              for n, r, m, a in rows] + extra("file", str), 0)
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


_TICKET, _ROUND = "T-1", 1


def _bound(scratch, bundle, checks, overridden=False, stood_down=False, configured=True):
    """record() stages this run's record; bind_record() keys it to the round."""
    staged = rc.record(str(scratch), bundle, checks, overridden, stood_down, configured)
    rc.bind_record(staged, str(scratch), _TICKET, _ROUND)


def _got(scratch, bundle, ticket=_TICKET, number=_ROUND):
    return rc.recorded(str(scratch), bundle, ticket, number)


def _write_bound(scratch, payload):
    """A hand-written record where the round's record lives."""
    with open(rc.round_record_path(str(scratch), _TICKET, _ROUND), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


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
     "ruff does not use rules"),
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


def _plain(tmp_path):
    """A repo with a .py change and no verify map, its .crew/ ignored."""
    repo = _repo(tmp_path, {"a.py": "x\n", ".gitignore": ".base\n.crew/\n"})
    (repo / ".base").write_text(git(repo, "rev-parse", "HEAD").strip(), encoding="utf-8")
    _edit(repo, "a.py", "y\n")
    return repo


def test_unconfigured_is_reported_as_not_configured(tmp_path):
    repo = _plain(tmp_path)

    assert rc.run_checks(str(repo), _bundle(repo, tmp_path)) == ([], False)


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
    _bound(tmp_path, "sha-a", [_ROW])

    assert (_got(tmp_path, "sha-a")["result"],
            _got(tmp_path, "sha-b")["result"]) == (rc.PASS, rc.NOT_RECORDED)


@pytest.mark.parametrize("content", [None, "{torn"])
def test_a_missing_or_torn_record_is_not_recorded_never_none(tmp_path, content):
    if content is not None:
        with open(rc.round_record_path(str(tmp_path), _TICKET, _ROUND), "w", encoding="utf-8") as fh:
            fh.write(content)

    found = _got(tmp_path, "sha-a")

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


def _pssa_missing(exe="pwsh"):
    """What is missing for a real-PSSA case under `exe`, or '' when nothing is."""
    found = shutil.which(exe)
    if not found:
        return f"{exe} is not on PATH"
    probe = subprocess.run(
        [found, "-NoProfile", "-NonInteractive", "-Command",
         "if (Get-Module -ListAvailable PSScriptAnalyzer) { exit 0 } else { exit 1 }"],
        capture_output=True, stdin=subprocess.DEVNULL, check=False, timeout=120)
    return "" if probe.returncode == 0 else f"{exe} has no PSScriptAnalyzer module"


def _pssa_or_skip(exe="pwsh", require="CREW_REQUIRE_PSSA"):
    """Skip a real-PSSA case when the tool is absent, unless `require` is
    set to 1: then a missing tool FAILS, so a proving run (this host,
    win-repo-2) can never pass by skipping (L-0605)."""
    missing = _pssa_missing(exe)
    if not missing:
        return
    if os.environ.get(require) == "1":
        pytest.fail(f"{require}=1 but {missing}, so this real-tool case could not run")
    pytest.skip(f"{exe} with PSScriptAnalyzer is not installed ({missing}), so this real-tool "
                "case did not run")


def test_real_pssa_catches_empty_catch(tmp_path):
    _pssa_or_skip()
    repo = _start(tmp_path, {"t.ps1": "Write-Output 'a'\n"},
                  [{"tool": "psscriptanalyzer", "rules": ["PSAvoidUsingEmptyCatchBlock"]}])
    _edit(repo, "t.ps1", "try { Write-Output 'a' } catch { }\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["rule"] for r in result["new"]]) == (
        rc.FAIL, ["PSAvoidUsingEmptyCatchBlock"]), result


def test_real_pssa_script_prints_an_empty_list_when_clean(tmp_path):
    """L-0605 (round-10 BLOCK :148): the script's own stdout for a clean file
    is exactly `[]`, never `[null]`, whatever the engine does with an empty
    statement's output."""
    _pssa_or_skip()
    clean = tmp_path / "clean.ps1"
    clean.write_text("Write-Output 'a'\n", encoding="utf-8")
    for path, text in ((tmp_path / "pssa.ps1", rc._PSSA_SCRIPT),  # pylint: disable=protected-access
                       (tmp_path / "files.json", json.dumps([str(clean)])),
                       (tmp_path / "rules.json", json.dumps(["PSAvoidUsingEmptyCatchBlock"]))):
        path.write_text(text + "\n", encoding="utf-8", newline="\n")

    proc = subprocess.run([shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-File",
                           str(tmp_path / "pssa.ps1"), str(tmp_path / "files.json"),
                           str(tmp_path / "rules.json")],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
                          timeout=300)

    assert (proc.returncode, proc.stdout.strip()) == (0, "[]"), proc.stderr


def test_real_pssa_clean_files_pass(tmp_path):
    """L-0605: a modified clean file (linted at its base too) and an added
    one read exactly pass; the dirty-file case beside it proves the tool ran."""
    _pssa_or_skip()
    repo = _start(tmp_path, {"a.ps1": "Write-Output 'a'\n"},
                  [{"tool": "psscriptanalyzer", "rules": ["PSAvoidUsingEmptyCatchBlock"]}])
    _edit(repo, "a.ps1", "Write-Output 'b'\n")
    _edit(repo, "b.ps1", "Write-Output 'c'\n")

    result = _one(repo, tmp_path)

    assert (result["status"], result["detail"]) == (rc.PASS, "no new findings in 2 file(s)"), result


def test_require_pssa_turns_a_missing_tool_into_a_failure(tmp_path):
    """L-0605: with CREW_REQUIRE_PSSA=1 a missing pwsh fails the real-tool
    case; without it the case skips."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    target = f"{os.path.abspath(__file__)}::test_real_pssa_clean_files_pass"
    base = {k: v for k, v in os.environ.items() if k != "CREW_REQUIRE_PSSA"}
    base["PATH"] = str(empty)
    runs = {}
    for flag in ("1", ""):
        env = dict(base, CREW_REQUIRE_PSSA=flag) if flag else dict(base)
        runs[flag] = subprocess.run(
            [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider",
             "-p", "no:randomly", "-o", "addopts="],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, env=env,
            timeout=300)

    assert (runs["1"].returncode, "CREW_REQUIRE_PSSA=1 but pwsh is not on PATH" in runs["1"].stdout,
            runs[""].returncode, "1 skipped" in runs[""].stdout) == (1, True, 0, True), (
        runs["1"].stdout[-2000:], runs[""].stdout[-2000:])


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell 5.1 exists only on Windows")
@pytest.mark.parametrize("dirty", [False, True])
def test_real_pssa_under_windows_powershell_fails_closed(tmp_path, dirty):
    """L-0605 Exclusion: 5.1 is not supported, but it may never pass a new
    finding. Two changed files under command powershell: the right answer
    or could-not-check, and never pass when one file adds an empty catch."""
    _pssa_or_skip("powershell", require="CREW_REQUIRE_PSSA51")
    repo = _start(tmp_path, {"a.ps1": "Write-Output 'a'\n", "b.ps1": "Write-Output 'b'\n"},
                  [{"tool": "psscriptanalyzer", "command": ["powershell"],
                    "rules": ["PSAvoidUsingEmptyCatchBlock"]}])
    _edit(repo, "a.ps1", "try { Write-Output 'a' } catch { }\n" if dirty else "Write-Output 'x'\n")
    _edit(repo, "b.ps1", "Write-Output 'y'\n")

    result = _one(repo, tmp_path)

    allowed = (rc.FAIL, rc.COULD_NOT) if dirty else (rc.PASS, rc.COULD_NOT)
    assert result["status"] in allowed, result
    if result["status"] == rc.FAIL:
        assert [r["rule"] for r in result["new"]] == ["PSAvoidUsingEmptyCatchBlock"], result


@pytest.mark.parametrize("stdout, expected", [
    ("[null]", rc.COULD_NOT), ("null", rc.COULD_NOT), ("{}", rc.COULD_NOT), ("", rc.COULD_NOT),
    ("ROW_AND_NULL", rc.FAIL), ("[]", rc.PASS)])
def test_pssa_output_that_is_not_a_list_of_rows_is_never_pass(tmp_path, fake, monkeypatch,
                                                              stdout, expected):
    """L-0605: a null row is never read as "no findings". A known NEW finding
    beside an unreadable row still FAILs (the existing precedence); with no
    finding established it is could-not-check. Only `[]` passes."""
    repo = _start(tmp_path, {"ps/tool.ps1": "x\n"}, [_linter(fake, "psscriptanalyzer")])
    _edit(repo, "ps/tool.ps1", "y\n")
    monkeypatch.setenv("FAKE_LINT_MODE", "raw")
    monkeypatch.setenv("FAKE_LINT_STDOUT", stdout)

    result = _one(repo, tmp_path)

    assert result["status"] == expected, result
    if expected == rc.FAIL:
        assert ([r["rule"] for r in result["new"]], "could not be read" in result["detail"]) == (
            ["R1"], True), result


def test_real_pssa_unknown_rule_is_could_not_check(tmp_path):
    _pssa_or_skip()
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
    _write_bound(tmp_path, {"bundle_sha256": "sha-a", "ticket": _TICKET, "round": _ROUND})

    assert _got(tmp_path, "sha-a")["result"] == rc.NOT_RECORDED


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
    _write_bound(tmp_path, dict({"overridden": False, "stood_down": False}, bundle_sha256="sha-a",
                                ticket=_TICKET, round=_ROUND, **payload))

    assert _got(tmp_path, "sha-a")["result"] == rc.NOT_RECORDED


@pytest.mark.parametrize("checks, configured", [
    ([_ROW], True), ([dict(_ROW, status=rc.NA, files=0)], True), ([], False),
    ([dict(_ROW, status=rc.FAIL, new=[{"path": "a.py", "rule": "X", "message": "m",
                                       "count": 1}])], True),
    ([dict(_ROW, status=rc.COULD_NOT, detail="tool missing")], True)])
def test_every_record_record_writes_reads_back(tmp_path, checks, configured):
    _bound(tmp_path, "sha-a", checks, False, False, configured)

    assert _got(tmp_path, "sha-a")["result"] == rc.overall(checks, configured)


@pytest.mark.parametrize("checks, overridden, stood_down", [
    ([dict(_ROW, status=rc.COULD_NOT)], True, False),
    ([dict(_ROW, status=rc.COULD_NOT)], False, True),
    ([dict(_ROW, status=rc.FAIL, new=[_NEW])], False, True)])
def test_an_override_or_stand_down_record_reads_back(tmp_path, checks, overridden, stood_down):
    _bound(tmp_path, "sha-a", checks, overridden, stood_down)

    assert _got(tmp_path, "sha-a")["result"] == rc.overall(checks)


@pytest.mark.parametrize("content", ["[]", "null", '"text"', "3"])
def test_a_verify_map_that_is_not_an_object_is_could_not_check(tmp_path, content):
    """Review round 4: valid JSON that is not an object is a broken map, not
    an absent `preReview` key."""
    repo = _plain(tmp_path)
    (repo / ".crew").mkdir()
    (repo / ".crew" / "verify.json").write_text(content, encoding="utf-8")

    results, configured = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert (configured, [(r["name"], r["status"]) for r in results]) == (
        True, [("config", rc.COULD_NOT)]), results


def test_a_verify_map_without_the_key_is_still_not_configured(tmp_path):
    repo = _plain(tmp_path)
    (repo / ".crew").mkdir()
    (repo / ".crew" / "verify.json").write_text('{"version": 1}', encoding="utf-8")

    assert rc.run_checks(str(repo), _bundle(repo, tmp_path)) == ([], False)


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
    first = rc.record(str(tmp_path), "sha-a", [], False, False)
    second = rc.record(str(tmp_path), "sha-a", [], False, False)

    assert (first != second, sorted(os.listdir(tmp_path)) == sorted(
        [os.path.basename(first), os.path.basename(second)])) == (True, True)


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
    _pssa_or_skip()
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


# --- review round 5 (owner grant 2026-10-02) ---------------------------------

def _tracked(tmp_path, fake, files, linters=None):
    """A repo whose verify map is TRACKED (committed in the base), as this
    repository's is, so the bundle carries it."""
    verify = {"version": 1, "rules": [],
              rc.CONFIG_KEY: {"linters": linters or [_linter(fake, "ruff")]}}
    repo = _repo(tmp_path, dict(files, **{".gitignore": ".base\n",
                                          ".crew/verify.json": json.dumps(verify)}))
    (repo / ".base").write_text(git(repo, "rev-parse", "HEAD").strip(), encoding="utf-8")
    return repo


@pytest.mark.parametrize("live", [
    '{"version": 1, "rules": []}',
    "not json",
    None])
def test_the_config_is_the_bundles_not_the_live_trees(tmp_path, fake, live):
    """Review round 5 BLOCK: a verify map edited (or removed) in the working
    tree after the bundle was built does not decide the bundle's checks."""
    repo = _tracked(tmp_path, fake, {"a.py": "x\n"})
    _edit(repo, "a.py", "x\n# LINT BLE001 a new problem\n")
    manifest = _bundle(repo, tmp_path)
    if live is None:
        os.remove(repo / ".crew" / "verify.json")
    else:
        (repo / ".crew" / "verify.json").write_text(live, encoding="utf-8")

    results, configured = rc.run_checks(str(repo), manifest)

    assert (configured, [r["status"] for r in results]) == (True, [rc.FAIL]), results


def test_a_narrowed_live_config_does_not_narrow_the_bundles(tmp_path, fake):
    repo = _tracked(tmp_path, fake, {"a.py": "x\n"})
    _edit(repo, "a.py", "x\n# LINT BLE001 a new problem\n")
    manifest = _bundle(repo, tmp_path)
    (repo / ".crew" / "verify.json").write_text(json.dumps({rc.CONFIG_KEY: {"linters": [
        _linter(fake, "ruff", paths=["nothing/**"])]}}), encoding="utf-8")

    results, _ = rc.run_checks(str(repo), manifest)

    assert [r["status"] for r in results] == [rc.FAIL], results


def test_a_config_change_the_bundle_carries_is_the_one_used(tmp_path, fake):
    """The neighbour: an edit INSIDE the bundle is the bundle's config (the
    reviewer sees it in the diff), whether it widens or removes the checks."""
    repo = _tracked(tmp_path, fake, {"a.py": "x\n"})
    _edit(repo, "a.py", "x\n# LINT BLE001 a new problem\n")
    (repo / ".crew" / "verify.json").write_text('{"version": 1, "rules": []}', encoding="utf-8")
    manifest = _bundle(repo, tmp_path)
    (repo / ".crew" / "verify.json").write_text(json.dumps({rc.CONFIG_KEY: {"linters": [
        _linter(fake, "ruff")]}}), encoding="utf-8")

    assert rc.run_checks(str(repo), manifest) == ([], False)


def test_a_verify_map_the_bundle_deletes_is_not_configured(tmp_path, fake):
    repo = _tracked(tmp_path, fake, {"a.py": "x\n"})
    _edit(repo, "a.py", "x\n# LINT BLE001 a new problem\n")
    git(repo, "rm", "-q", ".crew/verify.json")
    manifest = _bundle(repo, tmp_path)
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / "verify.json").write_text(json.dumps({rc.CONFIG_KEY: {"linters": [
        _linter(fake, "ruff")]}}), encoding="utf-8")

    assert rc.run_checks(str(repo), manifest) == ([], False)


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_verify_map_that_is_a_symlink_in_the_bundle_is_could_not_check(tmp_path, fake):
    repo = _tracked(tmp_path, fake, {"a.py": "x\n", "real.json": "{}"})
    _edit(repo, "a.py", "y\n")
    os.remove(repo / ".crew" / "verify.json")
    os.symlink("../real.json", repo / ".crew" / "verify.json")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert [(r["name"], r["status"]) for r in results] == [("config", rc.COULD_NOT)], results


def test_an_unreadable_manifest_is_could_not_check_even_unconfigured(tmp_path):
    """The config now comes from the bundle, so a manifest that cannot be
    read cannot be judged unconfigured either."""
    repo = _plain(tmp_path)

    results, configured, bundle = rc.run_checks_bound(str(repo), str(tmp_path / "absent.json"))

    assert (configured, [(r["name"], r["status"]) for r in results], bundle) == (
        True, [("manifest", rc.COULD_NOT)], None), results


@pytest.mark.parametrize("value", ["DROP", None, 7, ""])
def test_a_manifest_without_a_bundle_hash_is_could_not_check(tmp_path, fake, value):
    """Review round 5 FIX :648: no usable bundle_sha256 is a broken manifest,
    not a record bound to None."""
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "y\n")
    path = _bundle(repo, tmp_path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if value == "DROP":
        del data["bundle_sha256"]
    else:
        data["bundle_sha256"] = value
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)

    results, _, bundle = rc.run_checks_bound(str(repo), path)

    assert ([(r["name"], r["status"]) for r in results], bundle) == (
        [("manifest", rc.COULD_NOT)], None), results


@pytest.mark.parametrize("wanted", [None, ""])
def test_recorded_never_matches_a_missing_bundle_hash(tmp_path, wanted):
    _bound(tmp_path, wanted, [], configured=False)

    assert _got(tmp_path, wanted)["result"] == rc.NOT_RECORDED


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_symlink_turned_regular_file_has_no_base(tmp_path, fake):
    """Review round 5 FIX :226: the symlink's target text is not the base
    side of the file that replaces it, so it cannot baseline a finding."""
    repo = _repo(tmp_path, {".gitignore": ".base\n.crew/\n"})
    os.symlink("# LINT BLE001 same", repo / "a.py")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "link")
    (repo / ".base").write_text(git(repo, "rev-parse", "HEAD").strip(), encoding="utf-8")
    _config(repo, [_linter(fake, "ruff")])
    os.remove(repo / "a.py")
    _edit(repo, "a.py", "# LINT BLE001 same\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["path"] for r in result["new"]]) == (rc.FAIL, ["a.py"]), result


def test_a_submodule_turned_regular_file_is_linted(tmp_path, fake):
    """The neighbour: a gitlink replaced by a real file was skipped as a
    submodule, so a finding in it was never looked at."""
    repo = _repo(tmp_path, {".gitignore": ".base\n.crew/\n"})
    head = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{head},sub.py")
    git(repo, "commit", "-qm", "gitlink")
    (repo / ".base").write_text(git(repo, "rev-parse", "HEAD").strip(), encoding="utf-8")
    _config(repo, [_linter(fake, "ruff")])
    git(repo, "rm", "-q", "--cached", "sub.py")
    _edit(repo, "sub.py", "# LINT BLE001 inside\n")
    git(repo, "add", "sub.py")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["path"] for r in result["new"]]) == (rc.FAIL, ["sub.py"]), result


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_linter_config_that_is_a_symlink_is_could_not_check(tmp_path, fake):
    """The neighbour on the config side: a symlink's blob is its target
    text, which must not be handed to the linter as its config."""
    repo = _start(tmp_path, {"a.py": "x\n", "real.toml": "line-length = 80\n"},
                  [_linter(fake, "ruff")])
    os.symlink("real.toml", repo / "ruff.toml")
    _edit(repo, "a.py", "y\n")

    result = _one(repo, tmp_path)

    assert (result["status"], "symlink" in result["detail"]) == (rc.COULD_NOT, True), result


def test_taskkill_is_run_by_absolute_path(monkeypatch, tmp_path):
    """Review round 5 FIX :339: never a bare `taskkill` a repository could
    shadow from the current directory. review_run's no-job fallback is its
    only user since review round 8 moved the linters to a job object."""
    _exe(tmp_path / "Windows" / "System32", "taskkill.exe")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))

    assert rc.taskkill() == os.path.join(str(tmp_path / "Windows"), "System32", "taskkill.exe")


def test_no_taskkill_without_a_system_root(monkeypatch):
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.delenv("SYSTEMROOT", raising=False)

    assert rc.taskkill() is None


def test_a_linter_is_never_found_in_the_current_directory(tmp_path, monkeypatch):
    """The neighbour of :339: `_command` resolves a bare name from absolute
    PATH entries only. On Windows shutil.which searches the current
    directory first, so it is not used there."""
    here = tmp_path / "repo"
    here.mkdir()
    for name in ("lintme", "lintme.EXE"):
        (here / name).write_text("", encoding="utf-8")
        os.chmod(here / name, 0o755)
    monkeypatch.chdir(here)
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", str(tmp_path / "empty")]))
    monkeypatch.setenv("PATHEXT", ".EXE")

    # The posix branch calls shutil.which, which decides from sys.platform:
    # on a real Windows host it always searches the current directory, so
    # POSIX can only be simulated on a host that is not Windows. The nt branch
    # (the one production takes on Windows) runs on both.
    for system in ("nt",) if sys.platform == "win32" else ("posix", "nt"):
        monkeypatch.setattr(rc.os, "name", system)
        with pytest.raises(rc.CouldNotCheck):
            rc._command({"tool": "ruff", "command": ["lintme"]})  # pylint: disable=protected-access


def test_a_linter_on_an_absolute_path_entry_is_found(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("lintme", "lintme.EXE"):
        (bindir / name).write_text("", encoding="utf-8")
        os.chmod(bindir / name, 0o755)
    monkeypatch.setenv("PATH", str(bindir))
    monkeypatch.setenv("PATHEXT", ".EXE")
    found = {}
    # shutil.which decides PATHEXT from sys.platform, so POSIX can only be
    # simulated on a host that is not Windows; the nt branch runs on both.
    systems = ("nt",) if sys.platform == "win32" else ("posix", "nt")
    for system in systems:
        monkeypatch.setattr(rc.os, "name", system)
        found[system] = os.path.basename(
            rc._command({"tool": "ruff", "command": ["lintme"]})[0])  # pylint: disable=protected-access

    assert found == {s: {"posix": "lintme", "nt": "lintme.EXE"}[s] for s in systems}, found


# --- round-7 class sweep (owner decision 2026-10-02) --------------------------
import ast  # noqa: E402  pylint: disable=wrong-import-position,wrong-import-order
import review_run  # noqa: E402  pylint: disable=wrong-import-position,wrong-import-order

_SWEPT = [os.path.join(_SCRIPTS, "review_checks.py"), os.path.join(_SCRIPTS, "review_run.py")]


def _calls(path):
    tree = ast.parse(open(path, encoding="utf-8").read())  # pylint: disable=consider-using-with
    owner = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                owner.setdefault(id(node), fn.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node, owner.get(id(node), "<module>")


def _dotted(func):
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


# class a - executables ---------------------------------------------------------

def test_class_a_every_executable_comes_from_the_resolver():
    """No shutil.which outside resolve_executable, and no subprocess argv that
    starts with a literal program name, in either swept file."""
    bad = []
    for path in _SWEPT:
        for node, fn in _calls(path):
            name = _dotted(node.func)
            if name == "shutil.which" and fn != "resolve_executable":
                bad.append(f"{os.path.basename(path)}:{node.lineno} shutil.which in {fn}")
            if name.startswith("subprocess.") and name.rsplit(".", maxsplit=1)[-1] in (
                    "run", "Popen", "call", "check_call", "check_output") and node.args:
                first = node.args[0]
                if isinstance(first, (ast.List, ast.Tuple)) and first.elts and isinstance(
                        first.elts[0], ast.Constant) and isinstance(first.elts[0].value, str):
                    bad.append(f"{os.path.basename(path)}:{node.lineno} bare "
                               f"{first.elts[0].value!r} in {fn}")
    assert not bad, bad


def _exe(folder, name, body="#!/bin/sh\nexit 0\n"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(body, encoding="utf-8")
    os.chmod(folder / name, 0o755)
    return folder / name


@pytest.mark.skipif(os.name == "nt", reason="a POSIX shell script stands in for git")
def test_git_is_never_taken_from_the_current_directory(tmp_path, fake, monkeypatch):
    """Review round 6 BLOCK :245: a `git` in the repository root, with `.` on
    PATH, must not answer for the real one."""
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "x\n# LINT BLE001 a new problem\n")
    manifest = _bundle(repo, tmp_path)
    marker = tmp_path / "spoofed"
    _exe(repo, "git", f"#!/bin/sh\ntouch {marker}\nexit 0\n")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("PATH", os.pathsep.join([".", os.path.dirname(shutil.which("git"))]))

    results, _ = rc.run_checks(str(repo), manifest)

    assert ([r["status"] for r in results], marker.exists()) == ([rc.FAIL], False), results


def test_git_missing_is_could_not_check(tmp_path, fake, monkeypatch):
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "y\n")
    manifest = _bundle(repo, tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))

    results, configured = rc.run_checks(str(repo), manifest)

    assert (configured, [r["status"] for r in results]) == (True, [rc.COULD_NOT]), results


def test_the_resolver_refuses_relative_names_and_entries(tmp_path, monkeypatch):
    here = tmp_path / "repo"
    _exe(here, "tool")
    _exe(here / "sub", "tool")
    monkeypatch.chdir(here)
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", "sub"]))

    assert [rc.resolve_executable(n) for n in ("tool", "./tool", "sub/tool")] == [None] * 3


def test_the_resolver_accepts_an_absolute_regular_file_only(tmp_path):
    tool = _exe(tmp_path / "bin", "tool")
    (tmp_path / "dir").mkdir()

    assert [rc.resolve_executable(str(p)) for p in (tool, tmp_path / "dir",
                                                    tmp_path / "absent")] == [str(tool), None, None]


def test_review_run_finds_providers_through_the_resolver(monkeypatch):
    seen = []
    monkeypatch.setattr(review_run.review_checks, "resolve_executable",
                        seen.append)
    args = type("A", (), {"provider": "codex", "model": "m", "root": ".", "ticket": "T-1",
                          "scratch": ".", "effort": "high", "probe_timeout": 1})()
    monkeypatch.setattr(review_run.review_limit, "recorded", lambda *a: None)

    review_run.probe(args)

    assert seen == ["codex"], seen


def test_review_run_taskkill_is_absolute(monkeypatch, tmp_path):
    monkeypatch.setattr(review_run.os, "name", "nt")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    _exe(tmp_path / "Windows" / "System32", "taskkill.exe")

    assert rc.taskkill() == str(tmp_path / "Windows" / "System32" / "taskkill.exe")


# class b - file reads ----------------------------------------------------------

def test_class_b_every_file_read_goes_through_read_regular():
    """open() for reading, os.open, os.fdopen for reading, read_text and
    read_bytes appear only inside read_regular, in either swept file."""
    bad = []
    for path in _SWEPT:
        for node, fn in _calls(path):
            name = _dotted(node.func)
            mode = None
            if name in ("open", "io.open", "os.fdopen"):
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    mode = node.args[1].value
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = kw.value.value
                reading = mode is None or not any(c in str(mode) for c in "wax")
            else:
                reading = name in ("os.open",) or name.endswith((".read_text", ".read_bytes"))
            if reading and fn not in ("read_regular", "_walk_to_parent"):
                bad.append(f"{os.path.basename(path)}:{node.lineno} {name} in {fn}")
    assert not bad, bad


def test_read_regular_reads_a_regular_file(tmp_path):
    (tmp_path / "f").write_bytes(b"abc")

    assert rc.read_regular(str(tmp_path / "f"), str(tmp_path)) == b"abc"


@pytest.mark.skipif(os.name == "nt", reason="FIFOs and symlinks are POSIX here")
@pytest.mark.parametrize("kind", ["symlink", "fifo", "dir", "device"])
def test_read_regular_refuses_what_is_not_a_regular_file(tmp_path, kind):
    path = tmp_path / "f"
    (tmp_path / "real").write_text("{}", encoding="utf-8")
    if kind == "symlink":
        os.symlink(tmp_path / "real", path)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "dir":
        path.mkdir()
    else:
        path = "/dev/null"

    with pytest.raises(rc.NotRegularFile):
        rc.read_regular(str(path), os.path.dirname(str(path)))


def test_read_regular_says_absent(tmp_path):
    with pytest.raises(FileNotFoundError):
        rc.read_regular(str(tmp_path / "absent"), str(tmp_path))


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_an_untracked_symlinked_verify_map_is_could_not_check(tmp_path, fake):
    """Review round 6 BLOCK :177: never followed to a file without preReview."""
    repo = _plain(tmp_path)
    (repo / ".crew").mkdir()
    (tmp_path / "elsewhere.json").write_text('{"version": 1}', encoding="utf-8")
    os.symlink(tmp_path / "elsewhere.json", repo / ".crew" / "verify.json")

    results, configured = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert (configured, [(r["name"], r["status"]) for r in results]) == (
        True, [("config", rc.COULD_NOT)]), results


_NO_HANG = textwrap.dedent('''
    import sys
    sys.path.insert(0, sys.argv[1])
    import review_checks as rc
    results, configured, _ = rc.run_checks_bound(sys.argv[2], sys.argv[3])
    print(configured, [(r["name"], r["status"]) for r in results])
''')


@pytest.mark.skipif(os.name == "nt", reason="FIFOs are POSIX")
@pytest.mark.parametrize("where", ["map", "manifest"])
def test_a_fifo_is_could_not_check_and_never_blocks(tmp_path, where):
    """Review round 6 FIX :181: a FIFO with no writer, as the untracked map
    or as the manifest, is could-not-check at once."""
    repo = _plain(tmp_path)
    manifest = _bundle(repo, tmp_path)
    if where == "map":
        (repo / ".crew").mkdir()
        os.mkfifo(repo / ".crew" / "verify.json")
    else:
        os.remove(manifest)
        os.mkfifo(manifest)

    proc = subprocess.run([sys.executable, "-c", _NO_HANG, _SCRIPTS, str(repo), manifest],
                          capture_output=True, text=True, timeout=60, check=False,
                          stdin=subprocess.DEVNULL)

    name = "config" if where == "map" else "manifest"
    assert proc.stdout.strip() == f"True [('{name}', '{rc.COULD_NOT}')]", proc.stderr


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_symlinked_record_is_not_recorded(tmp_path):
    _bound(tmp_path, "sha-a", [_ROW])
    real = rc.round_record_path(str(tmp_path), _TICKET, _ROUND)
    os.rename(real, tmp_path / "moved.json")
    os.symlink(tmp_path / "moved.json", real)

    assert _got(tmp_path, "sha-a")["result"] == rc.NOT_RECORDED


# class c - config values -------------------------------------------------------

@pytest.mark.parametrize("key", ["command", "args", "paths", "timeout", "rules"])
def test_an_explicit_null_is_could_not_check(tmp_path, fake, key):
    """Review round 6 FIX :225: `null` is not "use the default"."""
    tool = "psscriptanalyzer" if key == "rules" else "ruff"
    repo = _start(tmp_path, {"a.py": "x\n"}, [dict(_linter(fake, tool), **{key: None})])
    _edit(repo, "a.py", "y\n")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert ([(r["name"], r["status"]) for r in results], key in results[0]["detail"]) == (
        [("config", rc.COULD_NOT)], True), results


@pytest.mark.parametrize("block", [{"linters": None}, None, {"linters": [None]}])
def test_a_null_block_or_linter_is_could_not_check(tmp_path, fake, block):
    repo = _start(tmp_path, {"a.py": "x\n"}, [])
    (repo / ".crew" / "verify.json").write_text(json.dumps({rc.CONFIG_KEY: block}),
                                                encoding="utf-8")
    _edit(repo, "a.py", "y\n")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert [(r["name"], r["status"]) for r in results] == [("config", rc.COULD_NOT)], results


def test_psscriptanalyzer_args_are_rejected(tmp_path, fake):
    """Review round 6 FIX :608: accepted but never passed is rejected."""
    repo = _start(tmp_path, {"ps/tool.ps1": "x\n"},
                  [_linter(fake, "psscriptanalyzer", args=["-Severity", "Error"])])
    _edit(repo, "ps/tool.ps1", "y\n")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert ([(r["name"], r["status"]) for r in results], "args" in results[0]["detail"]) == (
        [("config", rc.COULD_NOT)], True), results


def test_class_c_every_accepted_key_is_honoured(tmp_path, fake, monkeypatch):
    """Every (tool, key) TOOL_KEYS accepts reaches the run: args into argv,
    rules into the rules file, paths into the selection, timeout into the
    timer. A key accepted for a tool and not listed here fails this test."""
    honoured = set()
    out = tmp_path / "seen.json"
    monkeypatch.setenv("FAKE_LINT_ARGV_OUT", str(out))
    for tool, (_, rel, _) in sorted(_TOOLS.items()):
        for key in sorted(rc.TOOL_KEYS[tool] - {"tool", "command"}):
            case = tmp_path / f"{tool}-{key}"
            value = {"args": ["--sentinel-arg"], "rules": ["SentinelRule"],
                     "paths": ["nothing/**"], "timeout": 1}[key]
            repo = _start(case, {rel: "x\n"}, [dict(_linter(fake, tool), **{key: value})])
            _edit(repo, rel, "y\n")
            if key == "timeout":
                monkeypatch.setenv("FAKE_LINT_MODE", "sleep")
            result = _one(repo, case)
            monkeypatch.delenv("FAKE_LINT_MODE", raising=False)
            seen = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
            if out.exists():
                out.unlink()
            if key == "args" and "--sentinel-arg" in seen.get("argv", []):
                honoured.add((tool, key))
            if key == "rules" and any("SentinelRule" in t for t in seen.get("texts", {}).values()):
                honoured.add((tool, key))
            if key == "paths" and result["status"] == rc.NA:
                honoured.add((tool, key))
            if key == "timeout" and "timed out after 1s" in result["detail"]:
                honoured.add((tool, key))
    expected = {(t, k) for t in _TOOLS for k in rc.TOOL_KEYS[t] - {"tool", "command"}}
    assert honoured == expected, sorted(expected - honoured)


# class d - records -------------------------------------------------------------

def test_two_runs_sharing_a_scratch_keep_their_own_records(tmp_path):
    """Review round 6 FIX :788: records are bound to the reserved round, so a
    second run for the same bundle cannot overwrite the first one's."""
    first = rc.record(str(tmp_path), "sha-a", [dict(_ROW, status=rc.COULD_NOT)], True, False)
    second = rc.record(str(tmp_path), "sha-a", [dict(_ROW, status=rc.COULD_NOT)], False, False)
    rc.bind_record(first, str(tmp_path), _TICKET, 6)
    rc.bind_record(second, str(tmp_path), _TICKET, 7)

    assert (_got(tmp_path, "sha-a", number=6)["overridden"],
            _got(tmp_path, "sha-a", number=7)["overridden"]) == (True, False)


@pytest.mark.parametrize("ticket, number", [("T-2", _ROUND), (_TICKET, 2)])
def test_a_record_for_another_ticket_or_round_is_not_recorded(tmp_path, ticket, number):
    _bound(tmp_path, "sha-a", [_ROW])
    os.replace(rc.round_record_path(str(tmp_path), _TICKET, _ROUND),
               rc.round_record_path(str(tmp_path), ticket, number))

    assert _got(tmp_path, "sha-a", ticket=ticket, number=number)["result"] == rc.NOT_RECORDED


# ---- review round 7 (owner granted round 8, 2026-10-02) ----

@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_an_untracked_map_behind_a_symlinked_crew_directory_is_could_not_check(tmp_path, fake):
    """Round 7 BLOCK :172: `.crew` itself a symlink to a directory holding a
    map with no preReview. The leaf is a regular file; the parent is not."""
    repo = _plain(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "verify.json").write_text('{"version": 1}', encoding="utf-8")
    os.symlink(elsewhere, repo / ".crew")

    results, configured = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert (configured, [(r["name"], r["status"]) for r in results]) == (
        True, [("config", rc.COULD_NOT)]), results


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
@pytest.mark.parametrize("depth", [1, 2])
def test_read_regular_refuses_a_symlink_at_any_component_below_its_base(tmp_path, depth):
    real = tmp_path / "real" / "a" / "b"
    real.mkdir(parents=True)
    (real / "f").write_bytes(b"x")
    base = tmp_path / "base"
    base.mkdir()
    if depth == 1:
        os.symlink(tmp_path / "real" / "a", base / "a")
    else:
        (base / "a").mkdir()
        os.symlink(real, base / "a" / "b")

    with pytest.raises(rc.NotRegularFile):
        rc.read_regular(str(base / "a" / "b" / "f"), str(base))


def test_read_regular_reads_a_nested_regular_file_and_says_a_missing_parent(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "f").write_bytes(b"x")

    assert rc.read_regular(str(tmp_path / "a" / "b" / "f"), str(tmp_path)) == b"x"
    with pytest.raises(FileNotFoundError):
        rc.read_regular(str(tmp_path / "gone" / "f"), str(tmp_path))


@pytest.mark.parametrize("rel", ["../outside", "."])
def test_read_regular_refuses_a_path_outside_its_base(tmp_path, rel):
    (tmp_path / "outside").write_bytes(b"x")
    base = tmp_path / "base"
    base.mkdir()

    with pytest.raises(rc.NotRegularFile):
        rc.read_regular(os.path.join(str(base), rel), str(base))


def test_class_b_every_read_names_the_directory_it_trusts():
    """Round 7: a reader with no base checks the leaf only. Every call of
    read_regular in the swept files passes a base."""
    bad = []
    for path in _SWEPT:
        for node, fn in _calls(path):
            name = _dotted(node.func)
            if name.endswith("read_regular") and len(node.args) + len(node.keywords) < 2:
                bad.append(f"{os.path.basename(path)}:{node.lineno} in {fn}")
    assert not bad, bad


@pytest.mark.skipif(os.name == "nt", reason="a newline in a file name is POSIX here")
def test_a_newline_in_a_powershell_name_never_splits_the_file_list(tmp_path, fake):
    """Round 7 BLOCK :679: the finding-bearing file is linted as itself, never
    as the two clean files its name splits into."""
    repo = _start(tmp_path, {"first.ps1": "clean\n", "second.ps1": "clean\n"},
                  [_linter(fake, "psscriptanalyzer")])
    _edit(repo, "first.ps1\nhead/second.ps1", "# LINT PSAvoidUsingEmptyCatchBlock bad\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [r["path"] for r in result["new"]]) == (
        rc.FAIL, ["first.ps1\nhead/second.ps1"]), result


@pytest.mark.skipif(os.name == "nt", reason="a newline in a file name is POSIX here")
def test_real_pssa_lints_a_name_with_a_newline(tmp_path):
    _pssa_or_skip()
    repo = _start(tmp_path, {"first.ps1": "Write-Output 'a'\n", "second.ps1": "Write-Output 'b'\n"},
                  [{"tool": "psscriptanalyzer", "rules": ["PSAvoidUsingEmptyCatchBlock"]}])
    _edit(repo, "first.ps1\nhead/second.ps1", "try { Write-Output 'a' } catch { }\n")

    result = _one(repo, tmp_path)

    assert (result["status"], [(r["path"], r["rule"]) for r in result["new"]]) == (
        rc.FAIL, [("first.ps1\nhead/second.ps1", "PSAvoidUsingEmptyCatchBlock")]), result


def test_a_rule_name_with_a_newline_is_rejected(tmp_path, fake):
    """Neighbour: a newline in a rule would have split one allowlist entry into two."""
    repo = _start(tmp_path, {"a.ps1": "x\n"},
                  [_linter(fake, "psscriptanalyzer", rules=["PSAvoidUsingEmptyCatchBlock\nX"])])
    _edit(repo, "a.ps1", "y\n")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert [(r["name"], r["status"]) for r in results] == [("config", rc.COULD_NOT)], results


@pytest.mark.parametrize("tool", sorted(_TOOLS))
@pytest.mark.parametrize("in_base, expected", [(False, rc.FAIL), (True, rc.COULD_NOT)])
def test_an_unexpected_exit_keeps_the_rows_it_printed(tmp_path, fake, monkeypatch, tool,
                                                     in_base, expected):
    """Round 7 BLOCK :630: valid rows and exit 4. A NEW finding among them
    still FAILs, which --allow-unverified never overrides; with nothing new
    the exit makes it COULD NOT CHECK."""
    _, rel, rule = _TOOLS[tool]
    finding = f"# LINT {rule} a problem\n"
    repo = _start(tmp_path, {rel: finding if in_base else "line one\n"}, [_linter(fake, tool)])
    _edit(repo, rel, finding + "more\n")
    monkeypatch.setenv("FAKE_LINT_EXIT", "4")

    result = _one(repo, tmp_path)

    assert (result["status"], "exited 4" in result["detail"]) == (expected, True), result


@pytest.mark.parametrize("tool, field", [("actionlint", "kind"), ("psscriptanalyzer", "rule"),
                                         ("psscriptanalyzer", "severity"),
                                         ("shellcheck", "code"), ("ruff", "code")])
@pytest.mark.parametrize("side", ["head", "both"])
def test_a_row_missing_a_field_is_could_not_check_never_a_default(tmp_path, fake, monkeypatch,
                                                                  tool, field, side):
    """Round 7 BLOCK :664: a missing kind, rule, severity or code is never
    filled with "?" (or read as a parse abort): the row is unreadable."""
    _, rel, rule = _TOOLS[tool]
    finding = f"# LINT {rule} a problem\n"
    repo = _start(tmp_path, {rel: finding if side == "both" else "line one\n"},
                  [_linter(fake, tool)])
    _edit(repo, rel, finding + "more\n")
    monkeypatch.setenv("FAKE_LINT_DROP", field)

    result = _one(repo, tmp_path)

    assert (result["status"], result["new"], "could not read" in result["detail"]) == (
        rc.COULD_NOT, [], True), result


@pytest.mark.parametrize("tool, value", [("shellcheck", "2086"), ("shellcheck", True),
                                         ("psscriptanalyzer", "Severe")])
def test_a_field_of_the_wrong_type_or_value_is_could_not_check(tmp_path, fake, monkeypatch,
                                                               tool, value):
    """Neighbour: a shellcheck code that is not an int, a PSScriptAnalyzer
    severity it does not have."""
    _, rel, rule = _TOOLS[tool]
    repo = _start(tmp_path, {rel: "line one\n"}, [_linter(fake, tool)])
    _edit(repo, rel, f"line one\n# LINT {rule} a problem\n")
    shim = tmp_path / "shim.py"
    key = "code" if tool == "shellcheck" else "severity"
    shim.write_text(textwrap.dedent(f'''
        import json, subprocess, sys
        out = subprocess.run([sys.executable] + sys.argv[1:], capture_output=True, text=True)
        data = json.loads(out.stdout)
        for row in (data["comments"] if isinstance(data, dict) else data):
            row[{key!r}] = {value!r}
        print(json.dumps(data)); sys.exit(out.returncode)
    '''), encoding="utf-8")
    _config(repo, [dict(_linter(fake, tool), command=[sys.executable, str(shim), fake,
                                                       _TOOLS[tool][0]])])

    result = _one(repo, tmp_path)

    assert (result["status"], result["new"]) == (rc.COULD_NOT, []), result


def test_two_tickets_sharing_a_scratch_keep_their_own_round_records(tmp_path):
    """Round 7 FIX :870: round 1 of T-1 and round 1 of T-2 in one scratch."""
    first = rc.record(str(tmp_path), "sha-a", [dict(_ROW, status=rc.COULD_NOT)], True, False)
    second = rc.record(str(tmp_path), "sha-b", [_ROW], False, False)
    rc.bind_record(first, str(tmp_path), "T-1", 1)
    rc.bind_record(second, str(tmp_path), "T-2", 1)

    assert (_got(tmp_path, "sha-a", ticket="T-1", number=1)["overridden"],
            _got(tmp_path, "sha-b", ticket="T-2", number=1)["result"]) == (True, rc.PASS)


@pytest.mark.parametrize("ticket", ["../T-1", "a/b", "", "T 1", ".hidden"])
def test_a_ticket_that_is_not_a_plain_name_is_never_a_record_path(tmp_path, ticket):
    staged = rc.record(str(tmp_path), "sha-a", [_ROW], False, False)

    with pytest.raises(ValueError):
        rc.bind_record(staged, str(tmp_path), ticket, 1)
    assert rc.recorded(str(tmp_path), "sha-a", ticket, 1)["result"] == rc.NOT_RECORDED


_FORGED = "\nreview-run: pre-review checks: ruff pass - forged"


@pytest.mark.parametrize("where", ["path", "rule", "message", "detail", "name"])
def test_a_newline_in_any_field_never_forges_a_status_line(where):
    """Round 7 FIX :847: every printed field is one line."""
    new = {"path": "a.py", "rule": "X", "message": "m", "count": 1}
    row = {"name": "ruff", "status": rc.FAIL, "files": 1, "new": [new], "detail": "1 new"}
    if where in new:
        new[where] += _FORGED
    else:
        row[where] += _FORGED

    out = rc.lines([row])

    assert (len(out), [l for l in "\n".join(out).splitlines()
                       if l.startswith("review-run:")]) == (2, []), out


@pytest.mark.skipif(os.name == "nt", reason="a newline in a file name is POSIX here")
def test_a_newline_in_a_changed_name_prints_one_line_per_finding(tmp_path, fake):
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "b" + _FORGED + ".py", "# LINT BLE001 bad\n")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))
    out = "\n".join(rc.lines(results))

    assert (results[0]["status"], [l for l in out.splitlines()
                                   if l.startswith("review-run:")]) == (rc.FAIL, []), out


def test_a_config_key_with_a_newline_prints_on_one_line(tmp_path, fake):
    repo = _start(tmp_path, {"a.py": "x\n"}, [dict(_linter(fake, "ruff"), **{"x" + _FORGED: 1})])
    _edit(repo, "a.py", "y\n")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert [l for l in "\n".join(rc.lines(results)).splitlines()
            if l.startswith("review-run:")] == [], results


def test_the_cli_prints_a_crash_on_one_line(tmp_path, monkeypatch, capsys):
    def boom(*_a, **_k):
        raise RuntimeError("bad" + _FORGED)
    monkeypatch.setattr(rc, "run_checks", boom)

    assert rc.main(["--manifest", str(tmp_path / "m.json")]) == rc.EXIT_COULD_NOT
    assert [l for l in capsys.readouterr().out.splitlines() if l.startswith("review-run:")] == []


# ---- review round 8 (owner decision 2026-10-02: fix all four, last round) ----

@pytest.mark.parametrize("message, other", [
    ("requires 12:30:00", "requires 13:30:00"),
    ("port mapping 8080:80:tcp is open", "port mapping 8081:80:tcp is open"),
    ("aspect ratio 16:9: unsupported", "aspect ratio 4:3: unsupported"),
    ("timestamp 2026-10-02T12:30:00Z", "timestamp 2026-10-02T12:31:00Z")])
def test_a_value_shaped_like_a_position_still_tells_findings_apart(message, other):
    """Review round 8 BLOCK :97: only a position FIELD reads as N:N; a time,
    a port pair or a ratio in the message is a value."""
    assert rc._normalise(message) != rc._normalise(other)  # pylint: disable=protected-access


def test_shellcheck_positions_quoted_by_actionlint_still_read_as_n():
    assert rc._normalise("SC2086:info:2:28: Double quote") == rc._normalise(  # pylint: disable=protected-access
        "SC2086:warning:7:3: Double quote".replace("warning", "info"))


def test_a_changed_time_in_a_message_is_a_new_finding(tmp_path, fake):
    repo = _start(tmp_path, {"a.sh": "# LINT 2086 expires 12:30:00\n"}, [_linter(fake, "shellcheck")])
    _edit(repo, "a.sh", "# LINT 2086 expires 13:30:00\n")

    result = _one(repo, tmp_path)

    assert (result["status"], len(result["new"])) == (rc.FAIL, 1), result


class _FakeJob:
    """Stands in for a Windows job object: records what _spawn asks of it
    and, on terminate, kills the orphan the fake linter left behind."""
    def __init__(self, pid_file):
        self.calls, self.pid_file = [], pid_file

    def adopt(self, proc):
        self.calls.append(("adopt", proc.pid))

    def terminate(self):
        self.calls.append(("terminate",))
        try:
            with open(self.pid_file, encoding="utf-8") as fh:
                os.kill(int(fh.read()), 9)
        except (OSError, ValueError):
            pass

    def close(self):
        self.calls.append(("close",))


@pytest.mark.skipif(os.name == "nt", reason="drives the Windows branch with a fake job on POSIX")
@pytest.mark.parametrize("mode", ["orphan", "orphan-exit"])
def test_the_windows_timeout_kills_the_whole_job(tmp_path, fake, monkeypatch, mode):
    """Review round 8 FIX :574: taskkill /T /PID cannot find a linter that
    already exited, so its child kept the pipe. On Windows the linter runs in
    a job object, and a timeout terminates the job, orphans included."""
    pid_file = tmp_path / "pid"
    job = _FakeJob(str(pid_file))
    monkeypatch.setattr(rc, "_WINDOWS", True)
    monkeypatch.setattr(rc, "new_job", lambda kill_on_close: job)
    monkeypatch.setattr(rc, "_group_flags", lambda: {"start_new_session": True})
    monkeypatch.setenv("FAKE_LINT_MODE", mode)
    monkeypatch.setenv("FAKE_LINT_PID_OUT", str(pid_file))

    with pytest.raises(rc.CouldNotCheck, match="timed out"):
        rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 2)  # pylint: disable=protected-access

    assert [c[0] for c in job.calls] == ["adopt", "terminate", "close"], job.calls


@pytest.mark.skipif(os.name == "nt", reason="drives the Windows branch with a fake job on POSIX")
def test_a_job_that_cannot_be_made_is_could_not_check(tmp_path, fake, monkeypatch):
    def broken(kill_on_close):
        raise OSError(5, "access denied")
    monkeypatch.setattr(rc, "_WINDOWS", True)
    monkeypatch.setattr(rc, "new_job", broken)

    with pytest.raises(rc.CouldNotCheck, match="job object"):
        rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 5)  # pylint: disable=protected-access


@pytest.mark.skipif(os.name == "nt", reason="drives the Windows branch with a fake job on POSIX")
def test_a_linter_that_exits_cleanly_still_has_its_job_ended(tmp_path, fake, monkeypatch):
    """Like killpg after a clean exit on POSIX: nothing it started outlives it."""
    job = _FakeJob(str(tmp_path / "pid"))
    monkeypatch.setattr(rc, "_WINDOWS", True)
    monkeypatch.setattr(rc, "new_job", lambda kill_on_close: job)
    monkeypatch.setattr(rc, "_group_flags", lambda: {"start_new_session": True})
    monkeypatch.setenv("FAKE_LINT_MODE", "empty")

    rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 5)  # pylint: disable=protected-access

    assert [c[0] for c in job.calls] == ["adopt", "terminate", "close"], job.calls


class _RefusingJob(_FakeJob):
    """A job whose TerminateJobObject fails: WindowsJob.terminate raises."""
    def terminate(self):
        self.calls.append(("terminate",))
        raise OSError(5, "TerminateJobObject failed")


@pytest.mark.skipif(os.name == "nt", reason="drives the Windows branch with a fake job on POSIX")
def test_a_job_that_cannot_end_after_a_clean_exit_is_could_not_check(tmp_path, fake, monkeypatch):
    """L-0605 (Sonnet review of 73af42d7): a clean exit whose leftovers could
    not be ended is could-not-check (ADR 0005), never a raw OSError."""
    job = _RefusingJob(str(tmp_path / "pid"))
    monkeypatch.setattr(rc, "_WINDOWS", True)
    monkeypatch.setattr(rc, "new_job", lambda kill_on_close: job)
    monkeypatch.setattr(rc, "_group_flags", lambda: {"start_new_session": True})
    monkeypatch.setenv("FAKE_LINT_MODE", "empty")

    with pytest.raises(rc.CouldNotCheck, match="could not end what .* left running"):
        rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 5)  # pylint: disable=protected-access

    assert [c[0] for c in job.calls] == ["adopt", "terminate", "close"], job.calls


@pytest.mark.skipif(os.name == "nt", reason="drives the Windows branch with a fake job on POSIX")
def test_a_job_that_ends_after_a_clean_exit_returns_the_run(tmp_path, fake, monkeypatch):
    """The must-allow side: a terminate that succeeds hands back the run."""
    job = _FakeJob(str(tmp_path / "pid"))
    monkeypatch.setattr(rc, "_WINDOWS", True)
    monkeypatch.setattr(rc, "new_job", lambda kill_on_close: job)
    monkeypatch.setattr(rc, "_group_flags", lambda: {"start_new_session": True})
    monkeypatch.setenv("FAKE_LINT_MODE", "empty")

    result = rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 5)  # pylint: disable=protected-access

    assert isinstance(result, subprocess.CompletedProcess), result


# ---- review round 9 (owner grant 2026-10-02: final round 10) ----

def test_a_later_linter_that_raises_never_discards_an_earlier_new_finding(tmp_path, fake):
    """Round 9 BLOCK :948: a `paths` glob that makes matching raise (1200
    `**/` segments: RecursionError) is that linter's COULD NOT CHECK only;
    the first linter's NEW finding still FAILs."""
    repo = _start(tmp_path, {"a.py": "x\n"},
                  [_linter(fake, "ruff"),
                   _linter(fake, "shellcheck", paths=["**/" * 1200 + "*.sh"])])
    _edit(repo, "a.py", "x\n# LINT BLE001 new\n")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert ([(r["name"], r["status"]) for r in results], rc.overall(results)) == (
        [("ruff", rc.FAIL), ("shellcheck", rc.COULD_NOT)], rc.FAIL), results


def test_a_linter_that_raises_anything_is_its_own_could_not_check(tmp_path, fake, monkeypatch):
    """Neighbour: any exception out of one linter's run stays in that row."""
    repo = _start(tmp_path, {"a.py": "x\n", "b.sh": "x\n"},
                  [_linter(fake, "ruff"), _linter(fake, "shellcheck")])
    _edit(repo, "a.py", "x\n# LINT BLE001 new\n")
    _edit(repo, "b.sh", "y\n")
    real = rc.RUNNERS["shellcheck"]
    def boom(*_a, **_k):
        raise RuntimeError("runner bug")
        yield  # pylint: disable=unreachable
    monkeypatch.setitem(rc.RUNNERS, "shellcheck", boom)

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))
    monkeypatch.setitem(rc.RUNNERS, "shellcheck", real)

    assert [(r["name"], r["status"]) for r in results] == [
        ("ruff", rc.FAIL), ("shellcheck", rc.COULD_NOT)], results


@pytest.mark.parametrize("tool", ["shellcheck", "actionlint", "ruff"])
def test_duplicate_keys_in_linter_output_are_could_not_check(tmp_path, fake, tool):
    """Round 9 BLOCK :810: `{"comments": [finding], "comments": []}` read by
    json.loads keeps the empty list and passes. A duplicate key is refused."""
    _, rel, rule = _TOOLS[tool]
    repo = _start(tmp_path, {rel: "line one\n"}, [_linter(fake, tool)])
    _edit(repo, rel, f"line one\n# LINT {rule} a problem\n")
    shim = tmp_path / "dup.py"
    shim.write_text(textwrap.dedent('''
        import json, subprocess, sys
        out = subprocess.run([sys.executable] + sys.argv[1:], capture_output=True, text=True)
        data = json.loads(out.stdout)
        if isinstance(data, dict):
            text = out.stdout.rstrip()[:-1] + ', "comments": []}'
        else:
            rows = [json.dumps(r)[:-1] + ', "message": "m2"}' for r in data]
            text = "[" + ", ".join(rows) + "]"
        print(text); sys.exit(0 if isinstance(data, dict) else out.returncode)
    '''), encoding="utf-8")
    _config(repo, [dict(_linter(fake, tool), command=[sys.executable, str(shim), fake,
                                                       _TOOLS[tool][0]])])

    result = _one(repo, tmp_path)

    assert (result["status"], "duplicate" in result["detail"]) == (rc.COULD_NOT, True), result


def test_a_verify_map_with_a_duplicate_key_is_could_not_check(tmp_path, fake):
    """Neighbour: two `preReview` blocks, the second a narrower valid one,
    never read as whichever came last."""
    repo = _plain(tmp_path)
    (repo / ".crew").mkdir()
    (repo / ".crew" / "verify.json").write_text(
        '{"version": 1, "preReview": {"linters": [{"tool": "ruff"}]}, '
        '"preReview": {"linters": [{"tool": "shellcheck"}]}}',
        encoding="utf-8")

    results, configured = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert (configured, [(r["name"], r["status"]) for r in results]) == (
        True, [("config", rc.COULD_NOT)]), results


_BIDI = ["\u061c", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
         "\u2066", "\u2067", "\u2068", "\u2069"]


@pytest.mark.parametrize("char", _BIDI, ids=[f"U+{ord(c):04X}" for c in _BIDI])
def test_one_line_escapes_every_bidi_control(char):
    """Review round 10 FIX :159: every Bidi_Control code point is escaped, so
    a name or message cannot visually reorder a status line."""
    assert rc.one_line("a" + char + "b") == f"a\\u{ord(char):04x}b"


def test_a_bidi_control_in_a_changed_name_prints_escaped(tmp_path, fake):
    name = "x\u202e.py"
    repo = _start(tmp_path, {"m.py": "x\n"}, [_linter(fake, "ruff")])
    try:
        _edit(repo, name, "# LINT BLE001 new\n")
    except OSError:
        pytest.skip("this filesystem refuses a bidi control in a file name")

    printed = rc.lines([_one(repo, tmp_path)])

    assert ([l for l in printed if "\\u202e" in l and "NEW" in l] != [],
            [l for l in printed if "\u202e" in l]) == (True, []), printed


def test_a_bidi_control_in_a_rule_name_is_a_config_problem(tmp_path, fake):
    repo = _start(tmp_path, {"a.ps1": "x\n"},
                  [_linter(fake, "psscriptanalyzer", rules=["PSAvoidUsingEmptyCatchBlock\u202e"])])
    _edit(repo, "a.ps1", "y\n")

    results, _ = rc.run_checks(str(repo), _bundle(repo, tmp_path))

    assert any("rules must not hold a control character" in r["detail"] for r in results), results


def test_a_lone_surrogate_prints_escaped():
    """Round 9 FIX :165: one_line escapes a lone surrogate too, so a strict
    UTF-8 stream never raises on it."""
    assert rc.one_line("bad \ud800 key").encode("utf-8") == b"bad \\ud800 key"


def test_the_cli_exits_could_not_check_never_1_on_a_surrogate(tmp_path, fake):
    """End to end: an escaped surrogate in an unknown key; the CLI on a strict
    UTF-8 stdout prints it and exits 3, never 1 (new findings)."""
    repo = _start(tmp_path, {"a.py": "x\n"}, [dict(_linter(fake, "ruff"), **{"k\ud800": 1})])
    (repo / ".crew" / "verify.json").write_text(
        (repo / ".crew" / "verify.json").read_text(encoding="utf-8").replace(
            "\\ud800", "\\\\ud800").replace("\\\\ud800", "\\ud800"), encoding="utf-8")
    _edit(repo, "a.py", "y\n")
    manifest = _bundle(repo, tmp_path)
    env = dict(os.environ, PYTHONIOENCODING="utf-8:strict", PYTHONUTF8="1")

    proc = subprocess.run([sys.executable, os.path.join(_SCRIPTS, "review_checks.py"),
                           "--root", str(repo), "--manifest", manifest],
                          capture_output=True, text=True, env=env, check=False,
                          stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")

    assert (proc.returncode, "\\ud800" in proc.stdout) == (rc.EXIT_COULD_NOT, True), (
        proc.stdout, proc.stderr)


def test_any_crash_in_the_cli_is_could_not_check(monkeypatch):
    """Neighbour: a crash after the checks (in printing) is not exit 1."""
    monkeypatch.setattr(rc, "run_checks", lambda *a: ([{"name": "ruff", "status": rc.PASS,
                                                        "files": 1, "new": [], "detail": "x"}],
                                                      True))
    monkeypatch.setattr(rc, "lines", lambda results: (_ for _ in ()).throw(RuntimeError("x")))

    assert rc.main(["--manifest", "m.json"]) == rc.EXIT_COULD_NOT


_LINUX_WAITID = pytest.mark.skipif(
    not (hasattr(os, "waitid") and hasattr(os, "WNOWAIT") and os.path.isdir("/proc/self")),
    reason="needs os.waitid with WNOWAIT and /proc (Linux); elsewhere a clean exit's leftovers "
           "are not ended")


def _zombie(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return fh.read().split(") ", 1)[1][0] == "Z"
    except OSError:
        return False


@_LINUX_WAITID
def test_a_reaped_linter_s_group_is_never_signalled(tmp_path, fake, monkeypatch):
    """Round 9 FIX :727, kept by L-0605: the group is signalled only while
    the leader is an unreaped zombie, whose pid and group id cannot be reused."""
    seen = []
    real = os.killpg

    def recording(pgid, sig):
        seen.append(_zombie(pgid))
        real(pgid, sig)
    monkeypatch.setattr(rc.os, "killpg", recording)
    monkeypatch.setenv("FAKE_LINT_MODE", "empty")

    rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 10)  # pylint: disable=protected-access

    assert (len(seen) >= 1, all(seen)) == (True, True), seen


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_without_waitid_a_clean_linter_s_group_is_never_signalled(tmp_path, fake, monkeypatch):
    """Where os.waitid is missing (macOS) the leader is reaped by
    communicate() first, so nothing may be signalled after it."""
    seen = []
    monkeypatch.delattr(rc.os, "waitid", raising=False)
    monkeypatch.setattr(rc.os, "killpg", lambda pgid, sig: seen.append(pgid))
    monkeypatch.setenv("FAKE_LINT_MODE", "empty")

    rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 10)  # pylint: disable=protected-access

    assert seen == [], seen


def _kill_quietly(pid):
    try:
        os.kill(pid, 9)
    except OSError:
        pass


@_LINUX_WAITID
def test_a_clean_linter_s_detached_leftover_is_ended(tmp_path, fake, monkeypatch):
    """L-0605 / ADR 0005: a background process a linter leaves after a CLEAN
    exit, its stdio detached, is ended with the group before the reap."""
    pid_out = tmp_path / "child.pid"
    repo = _start(tmp_path, {"a.py": "x\n"}, [_linter(fake, "ruff")])
    _edit(repo, "a.py", "y\n")
    monkeypatch.setenv("FAKE_LINT_MODE", "detached")
    monkeypatch.setenv("FAKE_LINT_PID_OUT", str(pid_out))

    result = _one(repo, tmp_path)
    pid = int(pid_out.read_text(encoding="utf-8"))
    try:
        gone = not _alive_after(pid, 5)
    finally:
        _kill_quietly(pid)

    assert (result["status"], gone) == (rc.PASS, True), result


def _alive_after(pid, wait):
    import time  # pylint: disable=import-outside-toplevel
    deadline = time.monotonic() + wait
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    return _alive(pid)


_LEAVER = textwrap.dedent("""
    import json, os, sys, time
    sys.path[:0] = [{tests!r}, {scripts!r}]
    import review_checks as rc
    import test_review_checks as t
    started = time.monotonic()
    try:
        rc._spawn([sys.executable, {fake!r}, "ruff"], {cwd!r}, {timeout})
        print(json.dumps(["no error", time.monotonic() - started]))
    except rc.CouldNotCheck as exc:
        print(json.dumps([str(exc), time.monotonic() - started]))
""")


@_LINUX_WAITID
def test_a_leftover_that_left_the_group_cannot_hang_the_check(tmp_path, fake, monkeypatch):
    """Spec review r1 BLOCK: a child that setsid()s out of the group and
    keeps stdout open costs at most timeout + _REAP_SECONDS, in a child
    Python under an outer timeout so a hang is a failure, not a stuck suite."""
    pid_out = tmp_path / "child.pid"
    env = dict(os.environ, FAKE_LINT_MODE="setsid-holder", FAKE_LINT_PID_OUT=str(pid_out))
    code = _LEAVER.format(tests=os.path.dirname(os.path.abspath(__file__)), scripts=_SCRIPTS,
                          fake=fake, cwd=str(tmp_path), timeout=2)
    try:
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              env=env, stdin=subprocess.DEVNULL, check=False, timeout=60)
    finally:
        if pid_out.exists():
            _kill_quietly(int(pid_out.read_text(encoding="utf-8")))
    detail, elapsed = json.loads(proc.stdout.strip().splitlines()[-1])

    assert ("timed out" in detail, elapsed < 2 + rc._REAP_SECONDS + 5) == (  # pylint: disable=protected-access
        True, True), (detail, elapsed, proc.stderr)


@_LINUX_WAITID
def test_the_post_kill_drain_and_reap_share_one_deadline(tmp_path, fake, monkeypatch):
    """Spec review r2 FIX: after the kill, the drain and the reap share one
    _REAP_SECONDS deadline; the reap gets only what the drain left."""
    import time  # pylint: disable=import-outside-toplevel
    pid_out = tmp_path / "child.pid"
    monkeypatch.setattr(rc, "_REAP_SECONDS", 2)
    monkeypatch.setenv("FAKE_LINT_MODE", "setsid-holder")
    monkeypatch.setenv("FAKE_LINT_PID_OUT", str(pid_out))
    given = []
    real_wait = subprocess.Popen.wait

    def wait(self, timeout=None):
        given.append(timeout)
        return real_wait(self, timeout=timeout)
    monkeypatch.setattr(subprocess.Popen, "wait", wait)

    started = time.monotonic()
    try:
        with pytest.raises(rc.CouldNotCheck, match="timed out"):
            rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 1)  # pylint: disable=protected-access
    finally:
        if pid_out.exists():
            _kill_quietly(int(pid_out.read_text(encoding="utf-8")))
    elapsed = time.monotonic() - started

    bounded = [g for g in given if g is not None]
    assert (bounded != [] and max(bounded) <= 0.5, elapsed < 6) == (True, True), (given, elapsed)


@_LINUX_WAITID
def test_a_failed_output_read_is_could_not_check(tmp_path, fake, monkeypatch):
    """Spec review r1/r2 FIX: a read error is could-not-check, and the
    still-running linter is killed and reaped before it is raised."""
    import time  # pylint: disable=import-outside-toplevel
    pid_out = tmp_path / "lint.pid"
    monkeypatch.setenv("FAKE_LINT_MODE", "sleep-pid")
    monkeypatch.setenv("FAKE_LINT_PID_OUT", str(pid_out))
    real = rc._read_chunk  # pylint: disable=protected-access

    def failing(stream):
        if stream.fileno() == stderr_fd[0]:
            raise OSError(5, "boom")
        return real(stream)
    stderr_fd = [None]
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)  # pylint: disable=consider-using-with
        stderr_fd[0] = proc.stderr.fileno()
        return proc
    monkeypatch.setattr(rc.subprocess, "Popen", popen)
    monkeypatch.setattr(rc, "_read_chunk", failing)

    started = time.monotonic()
    with pytest.raises(rc.CouldNotCheck, match="could not read"):
        rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 30)  # pylint: disable=protected-access
    elapsed = time.monotonic() - started
    pid = int(pid_out.read_text(encoding="utf-8"))

    assert (elapsed < 10, os.path.exists(f"/proc/{pid}")) == (True, False), elapsed


@_LINUX_WAITID
def test_a_selector_error_still_ends_and_reaps_the_linter(tmp_path, fake, monkeypatch):
    """Spec review r4 FIX: an OSError registering the pipes, after the
    linter started, still kills, closes and reaps it."""
    import selectors  # pylint: disable=import-outside-toplevel
    pid_out = tmp_path / "lint.pid"
    monkeypatch.setenv("FAKE_LINT_MODE", "sleep-pid")
    monkeypatch.setenv("FAKE_LINT_PID_OUT", str(pid_out))
    real = selectors.DefaultSelector

    class Refusing(real):  # pylint: disable=too-many-ancestors
        def register(self, fileobj, events, data=None):
            raise OSError(9, "reg")
    monkeypatch.setattr(selectors, "DefaultSelector", Refusing)
    before = len(os.listdir("/proc/self/fd"))

    with pytest.raises(rc.CouldNotCheck, match="could not watch"):
        rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 30)  # pylint: disable=protected-access
    pid = int(pid_out.read_text(encoding="utf-8")) if pid_out.exists() else None

    assert (pid is None or not os.path.exists(f"/proc/{pid}"),
            len(os.listdir("/proc/self/fd")) - before) == (True, 0)


@_LINUX_WAITID
def test_a_leftover_that_cannot_be_signalled_is_could_not_check(tmp_path, fake, monkeypatch):
    """Spec review r2 BLOCK: PermissionError from the post-exit killpg means
    a member was not ended: could-not-check, and the leader still reaped."""
    reaped = []

    def refusing(pgid, sig):
        reaped.append(pgid)
        raise PermissionError(1, "not permitted")
    monkeypatch.setattr(rc.os, "killpg", refusing)
    monkeypatch.setenv("FAKE_LINT_MODE", "empty")

    with pytest.raises(rc.CouldNotCheck, match="could not end"):
        rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 10)  # pylint: disable=protected-access

    assert (len(reaped), os.path.exists(f"/proc/{reaped[0]}")) == (1, False), reaped


@_LINUX_WAITID
def test_the_drain_closes_its_pipes_on_every_path(tmp_path, fake, monkeypatch):
    """Spec review r3 FIX: no descriptor is left behind, on success or on a
    read error."""
    before = len(os.listdir("/proc/self/fd"))
    monkeypatch.setenv("FAKE_LINT_MODE", "empty")
    for _ in range(20):
        rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 10)  # pylint: disable=protected-access
    monkeypatch.setattr(rc, "_read_chunk", lambda stream: (_ for _ in ()).throw(OSError(5, "x")))
    for _ in range(5):
        with pytest.raises(rc.CouldNotCheck):
            rc._spawn([sys.executable, fake, "ruff"], str(tmp_path), 10)  # pylint: disable=protected-access

    assert len(os.listdir("/proc/self/fd")) == before


@pytest.mark.skipif(os.name != "nt", reason="a real job object exists only on Windows")
def test_windows_job_terminate_failure_raises():
    """L-0605: TerminateJobObject's failure is no longer discarded, so a
    caller never reads an unended tree as ended."""
    job = rc.WindowsJob(kill_on_close=True)

    class _Refusing:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        @staticmethod
        def TerminateJobObject(handle, code):  # pylint: disable=invalid-name
            return 0

    job._k32 = _Refusing(job._k32)  # pylint: disable=protected-access
    try:
        with pytest.raises(OSError, match="TerminateJobObject failed"):
            job.terminate()
    finally:
        job.close()
