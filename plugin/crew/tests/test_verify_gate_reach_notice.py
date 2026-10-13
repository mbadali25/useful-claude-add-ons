"""L-0733: a map whose rules predate `reach` gets ONE notice, not a wall.

TheSelectSource (crew 1.2.1): 29 of 30 rules in `.crew/verify.json` declared no
`reach`. Every Stop printed a `rules[N] wrapper or inline shell ...` line per
matched rule and a `NOT VERIFIED ON THIS TREE - rules[N]` line per record
entry, and once the map was edited the old entries were orphaned and held
`.crew/.verify-verified-at` for good: the only exit named was
`/crew:verify --all`, which also runs the `network`/`host` rules. Nothing
pointed at `/crew:verify --stamp-reach` (L-0562), which already declares them.

Now: the full notice once per map content (keyed on the map's bytes in
`.crew/.verify-gate.reach-notice`), then one summary line per Stop; the
deferral itself is unchanged; an undeclared-reach orphan no longer holds the
marker; and an orphan that still does names `verify_record.py forget-orphans`,
which runs nothing.

Folded in by owner decision (2026-10-08), from TSS PR #1143, which re-keyed
every rule by adding `reach`/`seconds` and left 17 orphans: an orphan whose
rule was EDITED (a new rule on the same paths, not a sibling that already sat
beside it) is superseded and dropped; one that nothing replaced stays. And
every exit 2 leaves a line on stdout, because Claude Code downgrades a Stop
hook that exits 2 with empty stdout and a "No such file" stderr to
non-blocking ("Hook script appears to be missing").

Both flavours: `verify-gate.ps1` runs under pwsh with OS=Windows_NT, as
`test_verify_gate_bookkeeping.py` runs it, and is skipped BY NAME when pwsh
does not resolve - a skip is not a pass.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import verify_fingerprint
import verify_record

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = os.path.join(_ROOT, "hooks", "scripts")
_SH = os.path.join(_SCRIPTS, "verify-gate.sh")
_PS1 = os.path.join(_SCRIPTS, "verify-gate.ps1")
_RECORD_PY = os.path.join(_SCRIPTS, "verify_record.py")
_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        _PWSH is None, reason="pwsh not installed - the .ps1 flavour was NOT run")),
]

_HEADER = "declare no `reach`, so Stop did NOT run them"
_SUMMARY = "with no `reach` not run on Stop"
_STAMP = "/crew:verify --stamp-reach"


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL,
                          timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S).stdout.strip()


def _write(root, rel, text):
    target = root.joinpath(*rel.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def _legacy_rules():
    """The TSS shape: a wrapper rule, a shell-syntax rule, both with no
    `reach`, and one declared-local rule that runs."""
    smoke = "bash _verify/smoke.sh a"
    return [
        {"paths": ["src/**"], "seconds": 1, "run": [smoke]},
        {"paths": ["src/**"], "seconds": 1, "run": ["true && true"]},
        {"paths": ["src/**"], "seconds": 1, "reach": "local", "run": ["true"]},
    ]


def _repo(tmp_path, rules, sentinel=None):
    root = tmp_path / "r"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    body = "#!/bin/sh\n"
    if sentinel:
        body += f"echo ran > '{sentinel}'\n"
    _write(root, "_verify/smoke.sh", body + "exit 0\n")
    _write(root, ".gitignore", ".crew/.verify*\n.crew/.scope-base\n")
    _write(root, ".crew/verify.json", json.dumps(
        {"version": 1, "rules": rules, "always": [], "default": [], "unmapped": "ignore"}))
    _write(root, "src/a.py", "x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "fixture")
    return root


def _run(flavour, root, *extra):
    if flavour == "sh":
        cmd = [_BASH, _SH, *extra]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1,
               *[{"--all": "-All", "--ci": "-Ci"}.get(a, a) for a in extra]]
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT")
    return crew_fixtures.run_gate(cmd, input="{}", cwd=str(root), env=env,
                                  capture_output=True, text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _change(root, n):
    _write(root, "src/a.py", f"x = {n}\n")


def _commit(root, msg):
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", msg)


def _record(root):
    return json.loads((root / ".crew" / ".verify-gate.record.json").read_text(encoding="utf-8"))


def _per_rule_lines(stderr):
    """The matcher's per-rule reach lines (`verify-gate: rules[N] ...`); the
    record's `NOT VERIFIED` lines are counted separately."""
    return [line for line in stderr.splitlines()
            if line.startswith("verify-gate: rules[")
            and ("wrapper or inline shell" in line or "shell syntax in an undeclared" in line)]


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_first_stop_shows_the_notice_once_with_each_rule(flavour, tmp_path):
    root = _repo(tmp_path, _legacy_rules())
    _change(root, 2)

    first = _run(flavour, root)

    assert first.returncode == 0, first.stderr
    header = [line for line in first.stderr.splitlines() if _HEADER in line]
    assert len(header) == 1 and _STAMP in first.stderr and "--set N=" in first.stderr, first.stderr
    assert len(_per_rule_lines(first.stderr)) == 2, first.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_later_stops_say_it_in_one_line(flavour, tmp_path):
    root = _repo(tmp_path, _legacy_rules())
    _change(root, 2)
    _run(flavour, root)
    _commit(root, "c2")
    _change(root, 3)

    second = _run(flavour, root)

    owed = [line for line in second.stderr.splitlines() if "NOT VERIFIED ON THIS TREE" in line]
    assert (second.returncode, _per_rule_lines(second.stderr), _HEADER in second.stderr) == (
        0, [], False), second.stderr
    assert len(owed) == 1 and "2 rule(s) " + _SUMMARY in owed[0] and _STAMP in owed[0], second.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_quiet_turn_reports_the_one_line_too(flavour, tmp_path):
    """cmd_report (empty changed set) shares the summary with the sync."""
    root = _repo(tmp_path, _legacy_rules())
    _change(root, 2)
    _run(flavour, root)
    _commit(root, "c2")
    _run(flavour, root)

    quiet = _run(flavour, root)

    owed = [line for line in quiet.stderr.splitlines() if "NOT VERIFIED ON THIS TREE" in line]
    assert len(owed) == 1 and _SUMMARY in owed[0], quiet.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_editing_the_map_shows_the_notice_again(flavour, tmp_path):
    rules = _legacy_rules()
    root = _repo(tmp_path, rules)
    _change(root, 2)
    _run(flavour, root)
    rules[2]["why"] = "edited"
    _write(root, ".crew/verify.json", json.dumps(
        {"version": 1, "rules": rules, "always": [], "default": [], "unmapped": "ignore"}))
    _change(root, 3)

    again = _run(flavour, root)

    assert _HEADER in again.stderr, again.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_undeclared_wrapper_still_never_runs_on_stop(flavour, tmp_path):
    sentinel = tmp_path / "smoke-ran"
    root = _repo(tmp_path, _legacy_rules(), sentinel=str(sentinel))
    _change(root, 2)

    stop = _run(flavour, root)

    assert (stop.returncode, sentinel.exists()) == (0, False), stop.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_undeclared_wrapper_runs_under_all(flavour, tmp_path):
    sentinel = tmp_path / "smoke-ran"
    root = _repo(tmp_path, _legacy_rules(), sentinel=str(sentinel))
    _change(root, 2)

    full = _run(flavour, root, "--all")

    assert (full.returncode, sentinel.exists()) == (0, True), full.stderr


def _remove_first_rule(root, rules):
    """An undeclared rule REMOVED: its two siblings on the same paths sat
    beside it when it was recorded, so neither replaces it."""
    _write(root, ".crew/verify.json", json.dumps(
        {"version": 1, "rules": rules[1:], "always": [], "default": [], "unmapped": "ignore"}))
    _commit(root, "remove a rule")
    _change(root, 3)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_edited_undeclared_rule_does_not_pin_the_marker(flavour, tmp_path):
    """The TSS case: entries recorded, then a rule removed, so its key is
    orphaned with nothing to replace it. It stays in the record, marked,
    and the marker still advances on a clean Stop."""
    rules = _legacy_rules()
    root = _repo(tmp_path, rules)
    _change(root, 2)
    _run(flavour, root)
    _remove_first_rule(root, rules)

    stop = _run(flavour, root)

    marker = (root / ".crew" / ".verify-verified-at").read_text(encoding="utf-8").strip()
    orphans = [v for v in _record(root)["rules"].values() if v.get("orphaned")]
    assert (marker, [o["status"] for o in orphans]) == (
        _git(root, "rev-parse", "HEAD"), ["reach_wrapper"]), stop.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_undeclared_orphan_is_counted_in_the_one_line(flavour, tmp_path):
    rules = _legacy_rules()
    root = _repo(tmp_path, rules)
    _change(root, 2)
    _run(flavour, root)
    _remove_first_rule(root, rules)

    stop = _run(flavour, root)

    owed = [line for line in stop.stderr.splitlines() if "NOT VERIFIED ON THIS TREE" in line]
    assert len(owed) == 1 and "1 of them from a rule since edited or removed" in owed[0], stop.stderr


def _chronic_orphan(flavour, tmp_path):
    """test_49's sequence: a chronic entry, then the rule's paths widened."""
    vmap = {"version": 1, "default": [], "unmapped": "ignore",
            "rules": [{"paths": ["a.txt"], "seconds": 999, "reach": "local", "run": ["echo huge"]}]}
    root = tmp_path / "c"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _write(root, ".gitignore", ".crew/.verify*\n.crew/.scope-base\n")
    _write(root, ".crew/verify.json", json.dumps(vmap))
    _commit(root, "fixture")
    _write(root, "a.txt", "x")
    _run(flavour, root)
    _commit(root, "a.txt")
    _run(flavour, root)
    vmap["rules"][0]["paths"] = ["a.txt", "b.txt"]
    _write(root, ".crew/verify.json", json.dumps(vmap))
    _commit(root, "widen the rule")
    return root


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_blocking_orphan_names_forget_orphans(flavour, tmp_path):
    root = _chronic_orphan(flavour, tmp_path)

    stop = _run(flavour, root)

    assert "NOT advancing the marker" in stop.stderr and "forget-orphans" in stop.stderr, stop.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_forget_orphans_clears_the_hold_without_running_a_rule(flavour, tmp_path):
    root = _chronic_orphan(flavour, tmp_path)
    _run(flavour, root)

    forgot = subprocess.run([sys.executable, _RECORD_PY, "forget-orphans"], cwd=str(root),
                            capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    after = _run(flavour, root)

    assert (forgot.returncode, "rules[0]" in forgot.stdout, "huge" in forgot.stdout) == (
        0, True, True), forgot.stdout + forgot.stderr
    assert "belong to a rule that was edited or removed" not in after.stderr, after.stderr


def test_forget_orphans_refuses_a_corrupt_record(tmp_path):
    (tmp_path / ".crew").mkdir()
    (tmp_path / ".crew" / ".verify-gate.record.json").write_text("{ not json", encoding="utf-8")

    forgot = subprocess.run([sys.executable, _RECORD_PY, "forget-orphans"], cwd=str(tmp_path),
                            capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
                            timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)

    assert (forgot.returncode, (tmp_path / ".crew" / ".verify-gate.record.json").read_text(
        encoding="utf-8")) == (1, "{ not json"), forgot.stdout + forgot.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_stamped_map_prints_neither(flavour, tmp_path):
    rules = _legacy_rules()
    for rule in rules:
        rule["reach"] = "local"
    root = _repo(tmp_path, rules)
    _change(root, 2)

    stop = _run(flavour, root)

    assert (stop.returncode, _HEADER in stop.stderr, _SUMMARY in stop.stderr) == (
        0, False, False), stop.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_ci_keeps_its_per_rule_lines_after_the_notice_was_shown(flavour, tmp_path):
    root = _repo(tmp_path, _legacy_rules())
    _change(root, 2)
    _run(flavour, root)
    _commit(root, "c2")

    ci = _run(flavour, root, "--ci")

    assert len(_per_rule_lines(ci.stderr)) == 2, ci.stderr


def _stamp_first_rule(root, rules):
    """TSS PR #1143: the same rule, now declaring `reach` - a new key on the
    same paths."""
    rules[0]["reach"] = "local"
    _write(root, ".crew/verify.json", json.dumps(
        {"version": 1, "rules": rules, "always": [], "default": [], "unmapped": "ignore"}))
    _commit(root, "stamp reach")


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_edited_rule_supersedes_its_orphan(flavour, tmp_path):
    rules = _legacy_rules()
    root = _repo(tmp_path, rules)
    _change(root, 2)
    _run(flavour, root)
    old = {k for k, v in _record(root)["rules"].items() if v.get("status") == "reach_wrapper"}
    _stamp_first_rule(root, rules)

    stop = _run(flavour, root)

    record = _record(root)["rules"]
    assert (stop.returncode, old & set(record), [v for v in record.values() if v.get("orphaned")]
            ) == (0, set(), []), stop.stderr
    assert "dropped the obligation of rules[0]" in stop.stderr and "rules[0] on the same paths" \
        in stop.stderr, stop.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_superseded_chronic_orphan_frees_the_marker(flavour, tmp_path):
    """The blocking kind: a chronic entry whose rule's `run` was edited, paths
    kept. Before, it held the marker until --all. Since L-0710 a turn where
    0 rules ran writes no marker at all, so a cheap rule on the map itself
    runs in the final turn: the marker then advances only if the orphan
    does not hold it."""
    vmap = {"version": 1, "default": [], "unmapped": "ignore",
            "rules": [{"paths": ["a.txt"], "seconds": 999, "reach": "local", "run": ["echo huge"]},
                      {"paths": [".crew/verify.json"], "seconds": 1, "reach": "local",
                       "run": ["echo map"]}]}
    root = tmp_path / "c"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _write(root, ".gitignore", ".crew/.verify*\n.crew/.scope-base\n")
    _write(root, ".crew/verify.json", json.dumps(vmap))
    _commit(root, "fixture")
    _write(root, "a.txt", "x")
    _run(flavour, root)
    _commit(root, "a.txt")
    _run(flavour, root)
    vmap["rules"][0]["run"] = ["echo huger"]
    _write(root, ".crew/verify.json", json.dumps(vmap))
    _commit(root, "edit the run")

    stop = _run(flavour, root)

    marker = (root / ".crew" / ".verify-verified-at").read_text(encoding="utf-8").strip()
    assert (marker, "NOT advancing the marker" in stop.stderr) == (
        _git(root, "rev-parse", "HEAD"), False), stop.stderr


def test_a_pre_l0733_orphan_is_kept(tmp_path, monkeypatch):
    """An entry written before pathsKey existed: which rule replaced it is
    unknown, and unknown keeps the orphan (and its hold)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".crew").mkdir()
    rule = {"paths": ["a.txt"], "reach": "local", "run": ["echo new"]}
    (tmp_path / ".crew" / "verify.json").write_text(json.dumps({"rules": [rule]}), encoding="utf-8")
    (tmp_path / ".crew" / ".verify-gate.record.json").write_text(json.dumps({"rules": {
        "0123456789abcdef": {"status": "chronic", "reason": "r", "label": "rules[0]: echo old",
                             "sha": "x"}}}), encoding="utf-8")

    ok = verify_record._sync("x", [], [])  # pylint: disable=protected-access

    assert (ok, _record(tmp_path)["rules"]["0123456789abcdef"].get("orphaned")) == (False, True)


def test_a_removed_rule_beside_a_peer_is_not_superseded(tmp_path, monkeypatch):
    """Rules A and B watch the same paths; A is removed. B sat beside A when
    A was recorded, so B is a peer, not A's replacement."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".crew").mkdir()
    a = {"paths": ["a.txt"], "seconds": 999, "reach": "local", "run": ["echo a"]}
    b = {"paths": ["a.txt"], "reach": "local", "run": ["echo b"]}
    mp = tmp_path / ".crew" / "verify.json"
    mp.write_text(json.dumps({"rules": [a, b]}), encoding="utf-8")
    key = verify_record.rule_key(a)
    verify_record._sync("x", [{"key": key, "label": "rules[0]: echo a", "kind": "chronic"}], [])  # pylint: disable=protected-access
    mp.write_text(json.dumps({"rules": [b]}), encoding="utf-8")

    ok = verify_record._sync("y", [], [])  # pylint: disable=protected-access

    assert (ok, _record(tmp_path)["rules"][key].get("orphaned")) == (False, True)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_owed_lines_name_the_absolute_record(flavour, tmp_path):
    root = _repo(tmp_path, _legacy_rules())
    _change(root, 2)

    stop = _run(flavour, root)

    owed = [line for line in stop.stderr.splitlines() if "NOT VERIFIED ON THIS TREE" in line]
    record = os.path.abspath(str(root / ".crew" / ".verify-gate.record.json"))
    assert owed and all(f"[record: {record}]" in line for line in owed), stop.stderr


def _blocking_repo(tmp_path, rule_run, map_text=None):
    root = tmp_path / "b"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _write(root, ".gitignore", ".crew/.verify*\n.crew/.scope-base\n")
    _write(root, ".crew/verify.json", map_text or json.dumps(
        {"version": 1, "default": [], "unmapped": "ignore",
         "rules": [{"paths": ["src/**"], "seconds": 1, "reach": "local", "run": [rule_run]}]}))
    _write(root, "src/a.py", "x = 1\n")
    _commit(root, "fixture")
    _change(root, 2)
    return root


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_no_such_file_failure_blocks_with_stdout(flavour, tmp_path):
    """TSS rule 32: `bash _verify/check-mo-matches-po.sh` with the script
    gone, rc 127, stderr "No such file or directory". With stdout empty,
    Claude Code 2.1.293 reads that as a missing hook and does not block."""
    root = _blocking_repo(tmp_path, "bash _verify/check-mo-matches-po.sh")

    stop = _run(flavour, root)

    assert (stop.returncode, "no such file" in stop.stderr.lower(), bool(stop.stdout.strip())
            ) == (2, True, True), (stop.stdout, stop.stderr)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_early_exit_2_writes_stdout_too(flavour, tmp_path):
    root = _blocking_repo(tmp_path, "true", map_text="{ not json")

    stop = _run(flavour, root)

    assert (stop.returncode, "BLOCKED (exit 2)" in stop.stdout) == (2, True), (
        stop.stdout, stop.stderr)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_usage_error_writes_stdout_too(flavour, tmp_path):
    """Refused before the gate installs its own cleanup trap (sh)."""
    root = _blocking_repo(tmp_path, "true")

    stop = _run(flavour, root, "--bogus")

    assert (stop.returncode, "BLOCKED (exit 2)" in stop.stdout) == (2, True), (
        stop.stdout, stop.stderr)


def test_the_notice_file_is_gate_owned():
    assert verify_fingerprint._gate_owned(  # pylint: disable=protected-access
        verify_record.REACH_NOTICE_PATH.replace(os.sep, "/"))
