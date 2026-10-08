"""L-0710: the Stop gate fits its budget, and says so when it checked nothing.

Measured on origin/main c25ef990 before this file existed: a Stop on a clean
default-branch checkout ran no rule, exited 0, and WROTE
`.crew/.verify-verified-at` = HEAD - a verified claim about a tree nothing
had checked. And a rule priced over `verify.stopBudgetSeconds` on its own
(chronic) was deferred "until /crew:verify --all runs it", which nobody runs:
its real home is the CI gate (`.github/workflows/verify-gate.yml`), and
`/crew:done` reads that gate's receipt.

The contract, each half in BOTH flavours (the .ps1 under pwsh through the
`OS=Windows_NT` seam the other gate suites use):

1. A clean tree exits 0, fast, and says "0 rules ran".
2. Zero rules ran never writes or advances the verified marker.
3. A chronic rule is deferred, named on a NOT VERIFIED line that names CI,
   and the turn exits 0 - a deferral alone is never a block. `--ci` on the
   same tree runs it.
4. A rule that runs in budget and fails still exits 2 beside a deferral.
5. The neighbouring case: with no verified marker on the default branch, a
   quiet turn used to establish the DIFF BASELINE by writing the marker. It
   no longer writes the marker, so `.crew/.verify-gate.base-at` holds that
   baseline instead - otherwise merge-base(HEAD, main) is HEAD forever and a
   commit made on main is never in scope.
"""
import json
import os
import shutil
import subprocess
import time

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")
_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None, reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(_PWSH is None, reason="needs pwsh")),
]

_MARKER = os.path.join(".crew", ".verify-verified-at")
_BASE_AT = os.path.join(".crew", ".verify-gate.base-at")
_ZERO = "verify-gate: 0 rules ran"
# A clean Stop must finish well inside this (acceptance 1). The gate itself
# takes well under a second; the bound is loose so a loaded box stays green.
_CLEAN_BOUND_S = 15

_CHRONIC = {"paths": ["a.py"], "seconds": 90, "run": ["echo RAN-chronic-90"],
            "why": "priced over the 60s default budget on its own"}
_FAILING = {"paths": ["a.py"], "seconds": 5, "reach": "local",
            "run": ["sh -c 'echo BOOM; exit 1'"], "why": "fails, in budget"}
# Would cost the clean-tree test 30s if the gate ever ran it there.
_SLOW = {"paths": ["a.py"], "seconds": 5, "run": ["sleep 30"],
         "why": "must never run on a clean tree"}


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True,
                          capture_output=True, text=True,
                          timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _repo(tmp_path, rules, with_a=True):
    """A default-branch (`main`) repo with everything committed, verify.json
    included, and the gate's own `.crew/.*` files ignored the way a real
    crew repo ignores them, so a second run sees only what the test changed."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / ".gitignore").write_text(".crew/.*\n", encoding="utf-8")
    (root / "README.md").write_text("committed", encoding="utf-8")
    if with_a:
        (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": rules, "default": [], "unmapped": "ignore"}),
        encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _run(flavour, root, *args):
    if flavour == "sh":
        cmd = [_BASH, _SH, *args]
    else:
        flags = {"--ci": "-Ci", "--all": "-All"}
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1,
               *[flags.get(a, a) for a in args]]
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), OS="Windows_NT")
    return crew_fixtures.run_gate(cmd, input="{}", cwd=str(root), env=env,
                                  capture_output=True, text=True, check=False,
                                  timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)


def _ran(result):
    out = []
    for line in result.stderr.splitlines():
        if line.startswith("verify-gate: ") and "s  " in line and "total across" not in line:
            out.append(line.split("s  ", 1)[1])
    return out


def _head(root):
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _read(root, rel):
    path = root / rel
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


@pytest.mark.wallclock
@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_clean_tree_exits_0_fast_and_says_0_rules_ran(flavour, tmp_path):
    """Acceptance 1 and 4: nothing changed on main, so nothing runs - and the
    gate says so instead of recording HEAD as verified."""
    root = _repo(tmp_path, [_SLOW])

    started = time.monotonic()
    result = _run(flavour, root)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < _CLEAN_BOUND_S, f"{elapsed:.1f}s: {result.stderr}"
    assert _ZERO in result.stderr, result.stderr
    assert _read(root, _MARKER) is None, (
        "zero rules ran, so nothing may be recorded as verified. " + result.stderr)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_zero_rules_ran_does_not_advance_an_existing_marker(flavour, tmp_path):
    """Acceptance 4, the 'nor advanced' half: HEAD moves (an empty commit, so
    the tree is identical) and a quiet turn must leave the marker where the
    last real check put it."""
    root = _repo(tmp_path, [_SLOW])
    first = _head(root)
    (root / _MARKER).write_text(first + "\n", encoding="utf-8")
    _git(root, "commit", "-q", "--allow-empty", "-m", "same tree")

    result = _run(flavour, root)

    assert _read(root, _MARKER) == first, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_changed_file_matching_nothing_runnable_says_0_rules_ran(flavour, tmp_path):
    """Acceptance 4 on the other zero-rules path: a file changed, and the map
    selected no command for it (`unmapped: ignore`)."""
    root = _repo(tmp_path, [_FAILING])
    (root / "notes.txt").write_text("unmapped", encoding="utf-8")

    result = _run(flavour, root)

    assert result.returncode == 0, result.stderr
    assert _ZERO in result.stderr, result.stderr
    assert _read(root, _MARKER) is None, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_chronic_rule_is_named_as_ci_and_exits_0(flavour, tmp_path):
    """Acceptance 2: over budget on its own, so Stop never runs it. It is
    deferred, named NOT VERIFIED with CI as where it runs, and the turn ends."""
    root = _repo(tmp_path, [_CHRONIC])
    (root / "a.py").write_text("x = 2", encoding="utf-8")

    result = _run(flavour, root)

    assert result.returncode == 0, (
        "a deferral alone is never a block. " + result.stderr)
    assert "echo RAN-chronic-90" not in _ran(result), result.stderr
    named = [ln for ln in result.stderr.splitlines()
             if "NOT VERIFIED" in ln and "deferred to CI" in ln]
    assert named, "the chronic rule must be named NOT VERIFIED, deferred to CI. " + result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_chronic_only_turn_is_zero_rules_ran(flavour, tmp_path):
    """Acceptance 4 again: a turn whose only matched rule was deferred ran
    nothing, so it records nothing."""
    root = _repo(tmp_path, [_CHRONIC])
    (root / "a.py").write_text("x = 2", encoding="utf-8")

    result = _run(flavour, root)

    assert _ZERO in result.stderr, result.stderr
    assert _read(root, _MARKER) is None, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_the_same_tree_under_ci_runs_the_chronic_rule(flavour, tmp_path):
    """Acceptance 2, second half: `--ci` has no budget, so CI runs what Stop
    defers."""
    root = _repo(tmp_path, [_CHRONIC])

    result = _run(flavour, root, "--ci")

    assert result.returncode == 0, result.stderr
    assert "echo RAN-chronic-90" in _ran(result), result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_in_budget_failure_beside_a_chronic_rule_exits_2(flavour, tmp_path):
    """Acceptance 3, MUST-BLOCK: the budget never turns a real failure into a
    passing turn, chronic deferral or not."""
    root = _repo(tmp_path, [_FAILING, _CHRONIC])
    (root / "a.py").write_text("x = 2", encoding="utf-8")

    result = _run(flavour, root)

    assert result.returncode == 2, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_commit_on_the_default_branch_after_a_quiet_turn_is_in_scope(flavour, tmp_path):
    """MUST-BLOCK, the neighbouring case. No verified marker, on main: the
    quiet turn records the diff baseline (not a verified claim), so the
    commit made after it is still diffed and its failing rule still blocks."""
    root = _repo(tmp_path, [_FAILING], with_a=False)
    quiet = _run(flavour, root)
    assert quiet.returncode == 0, quiet.stderr
    assert _read(root, _MARKER) is None, quiet.stderr
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "-m", "a commit made on main mid-turn")

    result = _run(flavour, root)

    assert result.returncode == 2, (
        "a.py was committed after the quiet turn and maps to a failing rule. "
        + result.stderr)


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_the_diff_baseline_is_never_read_as_verified(flavour, tmp_path):
    """The base-at file is a baseline, not a verdict: the quiet turn writes
    it at HEAD and leaves the verified marker absent."""
    root = _repo(tmp_path, [_FAILING], with_a=False)

    result = _run(flavour, root)

    assert _read(root, _BASE_AT) == _head(root), result.stderr
    assert _read(root, _MARKER) is None, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_real_pass_writes_the_marker_and_retires_the_baseline(flavour, tmp_path):
    """MUST-ALLOW: when rules actually ran and passed, the marker is written
    as before, and the base-at file it supersedes is removed."""
    passing = {"paths": ["a.py"], "seconds": 1, "run": ["echo RAN-pass"], "why": "passes"}
    root = _repo(tmp_path, [passing], with_a=False)
    _run(flavour, root)
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "-m", "a.py")

    result = _run(flavour, root)

    assert result.returncode == 0, result.stderr
    assert "echo RAN-pass" in _ran(result), result.stderr
    assert _read(root, _MARKER) == _head(root), result.stderr
    assert _read(root, _BASE_AT) is None, result.stderr


def _lines(result):
    keep = ("0 rules ran", "deferred to CI", "NOT VERIFIED")
    return [ln for ln in result.stderr.splitlines() if any(k in ln for k in keep)]


@pytest.mark.skipif(_BASH is None or _PWSH is None, reason="parity needs both flavours")
@pytest.mark.parametrize("case", ["clean", "unmapped", "chronic", "failing"])
def test_both_flavours_agree_on_exit_and_lines(case, tmp_path):
    """Acceptance 7: same exit, same budget lines, for checks 1-4."""
    def build(where):
        rules = {"clean": [_SLOW], "unmapped": [_FAILING], "chronic": [_CHRONIC],
                 "failing": [_FAILING, _CHRONIC]}[case]
        root = _repo(where, rules)
        if case == "unmapped":
            (root / "notes.txt").write_text("unmapped", encoding="utf-8")
        elif case in ("chronic", "failing"):
            (root / "a.py").write_text("x = 2", encoding="utf-8")
        return root

    sh_result = _run("sh", build(tmp_path / "sh"))
    ps_result = _run("ps1", build(tmp_path / "ps"))

    assert (sh_result.returncode, _lines(sh_result)) == (ps_result.returncode, _lines(ps_result)), (
        "sh : " + repr((sh_result.returncode, _lines(sh_result))) + "\n"
        + "ps1: " + repr((ps_result.returncode, _lines(ps_result))))
