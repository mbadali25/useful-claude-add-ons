"""L-0572: `verify-gate --all` credits a rule that DECLARES `coveredBy` when
the rule it names ran and passed earlier in the same run, on the same tree.

`verify-gate --all` spent 536s of a 992s run re-running crew test-subset rules
whose tests the full-suite rule (rules[9]) had just run and passed
(/root/crew-tmp/l-0558/verify-final.log). The superset rule now carries
`"id"`, each subset `"coveredBy": "<id>"`; nothing is inferred.

MUST-ALLOW: the superset passes, the tree did not move, nothing else names the
subset's command -> the subset is not run, says COVERED, the marker advances,
the record is cleared for it and no 0s timing is cached for it.

MUST-BLOCK (the subset RUNS): the superset failed, skipped (77), was killed
(137/143), had one failing command of two, did not match, or edited the tree;
PYTEST_ADDOPTS is set; Stop mode; the subset's command is also named by
`always` or by an undeclared rule; the declaration is invalid; the planner is
unavailable.

The .ps1 flavour is exercised wherever pwsh exists: on a non-Windows host it
is run with OS=Windows_NT, which is the only thing its first line checks
(`verify-gate.ps1:45`); Resolve-CrewBash then finds the host's bash.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import
import verify_record

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = os.path.join(_ROOT, "hooks", "scripts")
_SH = os.path.join(_SCRIPTS, "verify-gate.sh")
_PS1 = os.path.join(_SCRIPTS, "verify-gate.ps1")
_REPO = os.path.dirname(os.path.dirname(_ROOT))

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(_PWSH is None, reason="needs pwsh")),
]

SUB = "echo sub >> {log}"
SUP_ID = "suite"


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S).stdout


def _repo(tmp_path, rules, always=None):
    """A committed fixture repo plus a log file OUTSIDE it, so a rule's side
    effect never changes the tree the coverage snapshot hashes."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text(".crew/.verify*\n", encoding="utf-8")
    log = (tmp_path / "log.txt").as_posix()
    vmap = {"version": 1, "rules": json.loads(json.dumps(rules).replace("{log}", log)),
            "default": [], "unmapped": "ignore"}
    if always is not None:
        vmap["always"] = [c.replace("{log}", log) for c in always]
    (root / ".crew" / "verify.json").write_text(json.dumps(vmap), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root, tmp_path / "log.txt"


def _rule(run, **extra):
    rule = {"paths": ["a.py"], "seconds": 1, "reach": "local", "run": run}
    rule.update(extra)
    return rule


def _sup(*run, **extra):
    return _rule(list(run) or ["echo sup >> {log}"], id=SUP_ID, **extra)


def _sub(cmd=SUB, **extra):
    return _rule([cmd], coveredBy=SUP_ID, **extra)


def _run(flavour, root, *extra, env=None, scripts=None):
    sh = os.path.join(scripts, "verify-gate.sh") if scripts else _SH
    ps1 = os.path.join(scripts, "verify-gate.ps1") if scripts else _PS1
    if flavour == "sh":
        cmd = [_BASH, sh, *extra]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", ps1,
               *[a.replace("--all", "-All") for a in extra]]
    full = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    full.pop("PYTEST_ADDOPTS", None)
    if flavour == "ps1" and not sys.platform.startswith("win"):
        full["OS"] = "Windows_NT"
    full.update(env or {})
    return crew_fixtures.run_gate(cmd, input="{}", cwd=str(root), env=full, capture_output=True,
                                  text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _lines(log):
    return log.read_text(encoding="utf-8").split() if log.exists() else []


def _marker(root):
    p = root / ".crew" / ".verify-verified-at"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


def _head(root):
    return _git(root, "rev-parse", "HEAD").strip()


def _json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


# --- must-allow ------------------------------------------------------------

@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_superset_pass_credits_subset(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sup(), _sub()])
    sub_rule = json.loads((root / ".crew" / "verify.json").read_text(encoding="utf-8"))["rules"][1]
    key = verify_record.rule_key(sub_rule)
    (root / ".crew" / ".verify-gate.record.json").write_text(json.dumps(
        {"rules": {key: {"status": "skipped", "reason": "seeded", "label": "rules[1]"}}}),
        encoding="utf-8")
    (root / ".crew" / ".verify-gate.timings.json").write_text(
        json.dumps({"rules": {key: 7}}), encoding="utf-8")

    res = _run(flavour, root, "--all")

    assert res.returncode == 0, res.stderr
    assert _lines(log) == ["sup"], res.stderr
    assert "verify-gate: COVERED by rules[0] (passed this run): " + SUB.split(" >>", 1)[0] in res.stderr
    assert _marker(root) == _head(root), res.stderr
    assert key not in _json(root / ".crew" / ".verify-gate.record.json").get("rules", {})
    assert _json(root / ".crew" / ".verify-gate.timings.json")["rules"][key] == 7


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_subset_declared_before_superset_is_still_credited(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sub(), _sup()])

    res = _run(flavour, root, "--all")

    assert res.returncode == 0, res.stderr
    assert _lines(log) == ["sup"], res.stderr
    assert "COVERED by rules[1]" in res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_env_identity_is_credited_and_recorded(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sup(env={"ENV": "qa"}), _sub(env={"ENV": "qa"})])
    sub_rule = json.loads((root / ".crew" / "verify.json").read_text(encoding="utf-8"))["rules"][1]
    key = verify_record.rule_key(sub_rule)
    (root / ".crew" / ".verify-gate.record.json").write_text(json.dumps(
        {"rules": {key: {"status": "skipped", "reason": "seeded", "label": "rules[1]"}}}),
        encoding="utf-8")

    res = _run(flavour, root, "--all")

    assert res.returncode == 0, res.stderr
    assert _lines(log) == ["sup"], res.stderr
    assert key not in _json(root / ".crew" / ".verify-gate.record.json").get("rules", {})


# --- must-block: the subset runs -----------------------------------------

@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("rc", [1, 77, 137, 143])
def test_superset_not_passing_runs_subset(flavour, rc, tmp_path):
    root, log = _repo(tmp_path, [_sup(f"echo sup >> {{log}}; exit {rc}"), _sub()])

    res = _run(flavour, root, "--all")

    assert _lines(log) == ["sup", "sub"], res.stderr
    assert "COVERED" not in res.stderr
    assert res.returncode == (0 if rc == 77 else 2), res.stderr
    assert _marker(root) is None


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_two_command_superset_with_one_failure_runs_subset(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sup("echo sup >> {log}", "exit 1"), _sub()])

    res = _run(flavour, root, "--all")

    assert res.returncode == 2, res.stderr
    assert _lines(log) == ["sup", "sub"], res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_tree_changed_after_superset_runs_subset(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sup("echo sup >> {log}; echo 'x = 2' >> a.py"), _sub()])

    res = _run(flavour, root, "--all")

    assert _lines(log) == ["sup", "sub"], res.stderr
    assert "working tree changed during this run" in res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("addopts", ["-m slow", " "])
def test_pytest_addopts_runs_subset(flavour, addopts, tmp_path):
    root, log = _repo(tmp_path, [_sup(), _sub()])

    res = _run(flavour, root, "--all", env={"PYTEST_ADDOPTS": addopts})

    assert res.returncode == 0, res.stderr
    assert _lines(log) == ["sup", "sub"], res.stderr
    assert "PYTEST_ADDOPTS is set" in res.stderr


_POSIX = pytest.mark.skipif(os.name == "nt", reason="symlinks and mode bits are POSIX cases")


@_POSIX
@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("change", ["chmod +x a.py", "ln -sfn missing-b link"])
def test_tree_metadata_change_after_superset_runs_subset(flavour, change, tmp_path):
    """Review r1: a mode flip or a retargeted (dangling) symlink leaves every
    file's BYTES alone, so a content-only snapshot would still credit."""
    root, log = _repo(tmp_path, [_sup("echo sup >> {log}; " + change), _sub()])
    os.symlink("missing-a", root / "link")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "link")

    res = _run(flavour, root, "--all")

    assert _lines(log) == ["sup", "sub"], res.stderr
    assert "working tree changed during this run" in res.stderr


@_POSIX
def test_tree_snapshot_refuses_a_fifo_without_blocking(tmp_path):
    _git(tmp_path, "init", "-q")
    os.mkfifo(tmp_path / "pipe")

    res = subprocess.run([sys.executable, os.path.join(_SCRIPTS, "verify_record.py"), "tree-snapshot"],
                         cwd=str(tmp_path), capture_output=True, text=True, check=False, timeout=60)

    assert (res.returncode, res.stdout) == (1, "")


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_superset_not_matched_runs_subset(flavour, tmp_path):
    sup = _sup()
    sup["paths"] = ["nothing-matches-this.txt"]
    root, log = _repo(tmp_path, [sup, _sub()])

    res = _run(flavour, root, "--all")

    assert res.returncode == 0, res.stderr
    assert _lines(log) == ["sub"], res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_stop_mode_never_credits(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sup(), _sub()])
    (root / "a.py").write_text("x = 3\n", encoding="utf-8")

    res = _run(flavour, root)

    assert res.returncode == 0, res.stderr
    assert sorted(_lines(log)) == ["sub", "sup"], res.stderr
    assert "COVERED" not in res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_command_also_in_always_runs(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sup(), _sub()], always=[SUB])

    res = _run(flavour, root, "--all")

    assert res.returncode == 0, res.stderr
    assert sorted(_lines(log)) == ["sub", "sup"], res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_command_shared_with_undeclared_rule_runs(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sup(), _sub(), _rule([SUB])])

    res = _run(flavour, root, "--all")

    assert res.returncode == 0, res.stderr
    assert sorted(_lines(log)) == ["sub", "sup"], res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_shared_command_disqualifies_whole_rule_and_keeps_order(flavour, tmp_path):
    """Review r1 FIX 4: covered [prepare, check] + uncovered [check, cleanup],
    failing superset - the run order is exactly the order without coveredBy."""
    rules = [_rule(["echo prepare >> {log}", "echo check >> {log}"], coveredBy=SUP_ID),
             _rule(["echo check >> {log}", "echo cleanup >> {log}"]),
             _sup("echo sup >> {log}; exit 1")]
    plain = json.loads(json.dumps(rules))
    del plain[0]["coveredBy"]
    root, log = _repo(tmp_path / "with", rules)
    root2, log2 = _repo(tmp_path / "without", plain)

    _run(flavour, root, "--all")
    _run(flavour, root2, "--all")

    assert _lines(log) == _lines(log2) and _lines(log), (_lines(log), _lines(log2))


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_each_subset_is_credited_only_by_its_own_superset(flavour, tmp_path):
    rules = [_rule(["echo supA >> {log}"], id="A"), _rule(["echo supB >> {log}; exit 1"], id="B"),
             _rule(["echo subA >> {log}"], coveredBy="A"),
             _rule(["echo subB >> {log}"], coveredBy="B")]
    root, log = _repo(tmp_path, rules)

    res = _run(flavour, root, "--all")

    assert res.returncode == 2, res.stderr
    assert "subA" not in _lines(log) and "subB" in _lines(log), res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_failing_superset_fails_gate_and_subset_runs_after_it(flavour, tmp_path):
    root, log = _repo(tmp_path, [_sub(), _sup("echo sup >> {log}; exit 1")])

    res = _run(flavour, root, "--all")

    assert res.returncode == 2, res.stderr
    assert _lines(log) == ["sup", "sub"], res.stderr


_INVALID = {
    "unknown id": ([_sup(), _rule([SUB], coveredBy="nope")], "names no rule id"),
    "duplicate id": ([_sup(), _rule(["echo dup >> {log}"], id=SUP_ID), _sub()],
                     "more than one rule"),
    "self": ([_sup(), _rule([SUB], id="me", coveredBy="me")], "the rule itself"),
    "chain": ([_sup(), _rule(["echo mid >> {log}"], id="mid", coveredBy=SUP_ID),
               _rule([SUB], coveredBy="mid")], "no chains"),
    "blank superset command": ([_sup("echo sup >> {log}", "  "), _sub()],
                               "no runnable commands"),
    "env mismatch": ([_sup(), _sub(env={"ENV": "qa"})], "env different"),
    "not a string": ([_sup(), _rule([SUB], coveredBy=["suite"])], "not a non-empty string"),
}


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("case", sorted(_INVALID))
def test_invalid_declaration_runs_subset_and_says_why(flavour, case, tmp_path):
    rules, why = _INVALID[case]
    root, log = _repo(tmp_path, rules)

    res = _run(flavour, root, "--all")

    assert "sub" in _lines(log), res.stderr
    assert why in res.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_no_planner_runs_subset(flavour, tmp_path):
    scripts = tmp_path / "scripts"
    shutil.copytree(_SCRIPTS, scripts, ignore=shutil.ignore_patterns("__pycache__", "_test"))
    (scripts / "verify_record.py").unlink()
    root, log = _repo(tmp_path, [_sup(), _sub()])

    res = _run(flavour, root, "--all", scripts=str(scripts))

    assert sorted(_lines(log)) == ["sub", "sup"], res.stderr
    assert "COVERED" not in res.stderr


# --- the planner, the snapshot and the record, as units ----------------------

def _decl(*rules):
    return verify_record.cover_declarations(list(rules))


def test_declarations_valid_map():
    valid, notices = _decl({"id": "s", "run": ["x"]}, {"coveredBy": "s", "run": ["y"]})

    assert (valid, notices) == ({1: 0}, [])


def test_plan_moves_candidates_to_the_end_with_earlier_guards():
    rules = [{"run": ["sub"], "coveredBy": "s"}, {"run": ["other"]}, {"id": "s", "run": ["s1", "s2"]}]
    rule_cmds = {0: ["sub"], 1: ["other"], 2: ["s1", "s2"]}

    order, guards, notices = verify_record.cover_plan(rules, [0, 1, 2], rule_cmds,
                                                      ["sub", "other", "s1", "s2"], environ={})

    assert (order, notices) == (["other", "s1", "s2", "sub"], [])
    assert guards == [None, None, None, {"rules": [2], "pos": [1, 2]}]


@pytest.mark.parametrize("always,shared,environ", [
    (["sub"], False, {}),
    ([], True, {}),
    ([], False, {"PYTEST_ADDOPTS": "-m slow"}),
])
def test_plan_declines(always, shared, environ):
    rules = [{"run": ["sub"], "coveredBy": "s"}, {"id": "s", "run": ["s1"]}, {"run": ["sub"]}]
    rule_cmds = {0: ["sub"], 1: ["s1"], 2: ["sub"] if shared else ["z"]}

    order, guards, _ = verify_record.cover_plan(rules, [0, 1, 2], rule_cmds,
                                                ["sub", "s1"] + ([] if shared else ["z"]),
                                                always, environ=environ)

    assert guards == [None] * len(order)


def test_record_covered_is_clean_and_never_cached(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".crew").mkdir()
    matched = [{"key": "k1", "label": "covered only", "kind": "normal", "cmds": ["a"], "unknown": True},
               {"key": "k2", "label": "pass and covered", "kind": "normal", "cmds": ["b", "c"],
                "unknown": True},
               {"key": "k3", "label": "covered and fail", "kind": "normal", "cmds": ["d", "e"]}]
    prior = {"rules": {k: {"status": "skipped", "label": k} for k in ("k1", "k2", "k3")}}
    (tmp_path / ".crew" / ".verify-gate.record.json").write_text(json.dumps(prior), encoding="utf-8")
    cmd_log = [{"cmd": "a", "status": "covered", "elapsed": 0},
               {"cmd": "b", "status": "pass", "elapsed": 3},
               {"cmd": "c", "status": "covered", "elapsed": 0},
               {"cmd": "d", "status": "covered", "elapsed": 0},
               {"cmd": "e", "status": "fail", "elapsed": 1}]

    verify_record._sync("sha", matched, cmd_log)  # pylint: disable=protected-access

    assert sorted(_json(tmp_path / ".crew" / ".verify-gate.record.json")["rules"]) == ["k3"]
    assert _json(tmp_path / ".crew" / ".verify-gate.timings.json").get("rules") == {}


def test_tree_snapshot_moves_with_the_tree(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.py").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "x")
    first = verify_record.tree_snapshot(str(tmp_path))
    (tmp_path / "b.py").write_text("new", encoding="utf-8")
    untracked = verify_record.tree_snapshot(str(tmp_path))
    (tmp_path / "b.py").unlink()
    (tmp_path / "a.py").write_text("2", encoding="utf-8")

    assert first and untracked and first != untracked
    assert verify_record.tree_snapshot(str(tmp_path)) not in (first, untracked)
    assert verify_record.tree_snapshot(str(tmp_path / "missing")) is None


@pytest.mark.parametrize("payload", ["not json", "[]", '{"rules": []}',
                                     '{"rules": {}, "rule_order": [], "rule_cmds": {}, "cmds": []}',
                                     '{"rules": [], "rule_order": [], "rule_cmds": {}, "cmds": [1]}',
                                     '{"rules": [], "rule_order": [true], "rule_cmds": {}, "cmds": []}',
                                     '{"rules": [], "rule_order": [], "rule_cmds": {"x": []}, "cmds": []}'])
def test_cover_plan_cli_refuses_malformed_input(payload):
    res = subprocess.run([sys.executable, os.path.join(_SCRIPTS, "verify_record.py"), "cover-plan"],
                         input=payload, capture_output=True, text=True, check=False, timeout=60)

    assert (res.returncode, res.stdout) == (1, "")


# --- this repo's own map ------------------------------------------------------

def _pytest_targets_are_inside_the_suite(cmd):
    parts = cmd.split()
    if parts[:3] != ["python3", "-m", "pytest"] or parts[-1] != "-q":
        return False
    targets = parts[3:-1]
    if not targets or any(t.startswith("-") for t in targets):
        return False
    suite = os.path.join(_REPO, "plugin", "crew", "tests")
    for target in targets:
        path = target.split("::", 1)[0]
        if not path.startswith("plugin/crew/tests/") or "/" in path[len("plugin/crew/tests/"):]:
            return False
        hits = [h for h in glob.glob(os.path.join(_REPO, path))
                if os.path.dirname(h) == suite]
        if not hits or not all(os.path.basename(h).startswith("test_") and h.endswith(".py")
                                for h in hits):
            return False
    return True


def test_repo_map_declarations_are_valid_and_plausible():
    with open(os.path.join(_REPO, ".crew", "verify.json"), encoding="utf-8") as fh:
        rules = json.load(fh)["rules"]
    valid, notices = verify_record.cover_declarations(rules)
    supersets = {rules[j]["run"][0] for j in valid.values()}

    assert notices == []
    assert len(valid) >= 20
    assert len(supersets) == 1 and "python3 -m pytest plugin/crew/tests/ -q" in supersets.pop()
    bad = [i for i in valid if not all(_pytest_targets_are_inside_the_suite(c) for c in rules[i]["run"])]
    assert bad == []
