"""The Stop budget: verify-gate runs what fits and SAYS what it deferred.

`.crew/verify.json` carried each rule's cost as PROSE inside its `why` ("8s",
"29s", "245s") and nothing could read it, so a Stop gate that had grown to two
minutes had no way to spend that time cheapest-first. `seconds` is that number
in a field; `verify.stopBudgetSeconds` (default 60) is the bound.

Four properties are load-bearing and each has a case here, in BOTH flavours:

1. **Cheapest-first, up to the budget.** What fits runs; what does not is
   deferred and NAMED with its cost.
2. **Unknown cost is not free.** A rule with no `seconds` RUNS -- it is never
   deferred on the strength of a number nobody wrote down -- and the output
   says its cost is unstated. It is kept out of the budget arithmetic rather
   than given a guessed value, which is this repository's standing rule about
   unknowns: label them, never let them collapse into a safe-looking value.
3. **A deferral is not a pass, and never changes the exit code.** A rule that
   RUNS and fails must still exit 2 even when something else was deferred; a
   turn whose only event is a deferral must still exit 0.
4. **The two flavours agree.** A budget that selects different checks on
   PowerShell than on bash would be a gate whose verdict depends on which
   shell the hook fired in -- the same class of defect as a .ps1 guard that
   stands down on Windows.

`--all` / `-All` removes the budget entirely, which is what /crew:verify uses
to run the whole map.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")
_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

_FLAVOURS = [
    pytest.param("sh", marks=pytest.mark.skipif(_BASH is None,
                                                reason="needs bash")),
    pytest.param("ps1", marks=pytest.mark.skipif(
        not sys.platform.startswith("win") or _PWSH is None,
        reason="the .ps1 gate is the native-Windows flavour")),
]

# Three stated costs and one deliberately unstated. 5 + 40 fits in 60; 90 does
# not; the unstated one runs regardless and is excluded from the arithmetic.
_MAP = {
    "version": 1,
    "rules": [
        {"paths": ["a.py"], "seconds": 5, "run": ["echo RAN-cheap-5"],
         "why": "5s"},
        {"paths": ["a.py"], "seconds": 40, "run": ["echo RAN-mid-40"],
         "why": "40s"},
        {"paths": ["a.py"], "seconds": 90, "run": ["echo RAN-big-90"],
         "why": "90s"},
        {"paths": ["a.py"], "run": ["echo RAN-unstated"],
         "why": "no seconds on purpose"},
    ],
    "default": [],
    "unmapped": "ignore",
}


def _repo(tmp_path, verify_map=None, config=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    for args in (("init", "-q"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t")):
        subprocess.run(("git",) + args, cwd=root, check=True,
                       capture_output=True, text=True)
    (root / "README.md").write_text("committed", encoding="utf-8")
    subprocess.run(("git", "add", "-A"), cwd=root, check=True,
                   capture_output=True, text=True)
    subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root,
                   check=True, capture_output=True, text=True)
    # Untracked, so the gate has a changed file and reaches the rule loop.
    (root / "a.py").write_text("x = 1", encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(
        json.dumps(verify_map if verify_map is not None else _MAP),
        encoding="utf-8")
    if config is not None:
        (root / ".crew" / "config.json").write_text(config, encoding="utf-8")
    return root


def _run(flavour, root, *extra):
    if flavour == "sh":
        cmd = [_BASH, _SH, *extra]
    else:
        cmd = [_PWSH, "-NoProfile", "-NonInteractive", "-File", _PS1,
               *[a.replace("--all", "-All") for a in extra]]
    return subprocess.run(
        cmd, input="{}", cwd=str(root),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True, text=True, check=False,
    )


def _ran(result):
    """The commands the gate actually executed, in order. Read off the
    per-rule elapsed lines the gate prints, not guessed from the map."""
    out = []
    for line in result.stderr.splitlines():
        marker = "verify-gate: "
        if line.startswith(marker) and "s  " in line and "total across" not in line:
            out.append(line.split("s  ", 1)[1])
    return out


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_what_fits_runs_and_what_does_not_is_named(flavour, tmp_path):
    root = _repo(tmp_path)
    result = _run(flavour, root)

    assert result.returncode == 0, result.stderr
    ran = _ran(result)
    assert "echo RAN-cheap-5" in ran, result.stderr
    assert "echo RAN-mid-40" in ran, result.stderr
    assert "echo RAN-big-90" not in ran, (
        "5 + 40 + 90 is over the 60s budget; the 90s rule must be deferred. "
        + result.stderr
    )
    assert "deferred to /crew:verify: echo RAN-big-90 (90s)" in result.stderr, (
        "a deferred rule must be named WITH its cost, or the reader cannot "
        "tell what was skipped. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_unstated_cost_runs_and_says_it_is_unstated(flavour, tmp_path):
    """Unknown is not free. The rule runs, and the output refuses to imply a
    number for it."""
    root = _repo(tmp_path)
    result = _run(flavour, root)

    assert "echo RAN-unstated" in _ran(result), (
        "a rule with no `seconds` must RUN -- deferring it would be acting on "
        "a cost nobody wrote down. " + result.stderr
    )
    assert "UNSTATED" in result.stderr, result.stderr
    assert "echo RAN-unstated has no" in result.stderr, result.stderr
    # The arithmetic must not silently absorb it.
    assert "45s of stated cost" in result.stderr, (
        "only the stated costs may be summed. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_all_removes_the_budget(flavour, tmp_path):
    """What /crew:verify uses: the whole map, nothing deferred."""
    root = _repo(tmp_path)
    result = _run(flavour, root, "--all")

    ran = _ran(result)
    for cmd in ("echo RAN-cheap-5", "echo RAN-mid-40", "echo RAN-big-90",
                "echo RAN-unstated"):
        assert cmd in ran, cmd + " must run with no budget. " + result.stderr
    assert "deferred to /crew:verify" not in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_the_config_key_moves_the_budget(flavour, tmp_path):
    root = _repo(tmp_path,
                 config=json.dumps({"verify": {"stopBudgetSeconds": 10}}))
    result = _run(flavour, root)

    ran = _ran(result)
    assert "echo RAN-cheap-5" in ran, result.stderr
    assert "echo RAN-mid-40" not in ran, (
        "40s does not fit a 10s budget. " + result.stderr
    )
    assert "stop budget 10s" in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_unreadable_config_falls_back_to_the_default_not_to_unbounded(
        flavour, tmp_path):
    """The safe direction. A config that cannot be parsed must not read as
    "no limit" -- that is an unknown collapsing into the permissive value,
    and it would quietly restore the two-minute gate this bounds."""
    root = _repo(tmp_path, config="{not valid json")
    result = _run(flavour, root)

    assert "stop budget 60s" in result.stderr, (
        "a malformed config must fall back to the 60s default. "
        + result.stderr
    )
    assert "echo RAN-big-90" not in _ran(result), result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_deferral_alone_does_not_change_the_exit_code(flavour, tmp_path):
    root = _repo(tmp_path)
    result = _run(flavour, root)
    assert result.returncode == 0, (
        "deferring a rule is not a failure. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_that_runs_and_fails_still_exits_2_beside_a_deferral(
        flavour, tmp_path):
    """The must-block half, and the one that matters most: the budget must
    never be able to turn a real failure into a passing turn."""
    failing = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 5,
             "run": ["sh -c 'echo BOOM; exit 1'"], "why": "fails"},
            {"paths": ["a.py"], "seconds": 90, "run": ["echo RAN-big-90"],
             "why": "deferred"},
        ],
        "default": [],
        "unmapped": "ignore",
    }
    root = _repo(tmp_path, verify_map=failing)
    result = _run(flavour, root)

    assert "deferred to /crew:verify: echo RAN-big-90 (90s)" in result.stderr, (
        "the expensive rule should still have been deferred. " + result.stderr
    )
    assert result.returncode == 2, (
        "a rule that RAN and failed must still block the turn. rc="
        + str(result.returncode) + " " + result.stderr
    )


# ------------------------------------------------------------------ parity

@pytest.mark.skipif(
    _BASH is None or not sys.platform.startswith("win") or _PWSH is None,
    reason="parity needs both flavours on the same machine",
)
def test_both_flavours_select_and_report_the_same_thing(tmp_path):
    """A budget that picks different checks per shell would make the gate's
    verdict depend on which hook fired first. Compares the SELECTION and the
    deferral lines, not the elapsed timings, which legitimately differ."""
    sh_result = _run("sh", _repo(tmp_path / "sh"))
    ps_result = _run("ps1", _repo(tmp_path / "ps"))

    assert _ran(sh_result) == _ran(ps_result), (
        "the two flavours ran different commands for the same map." + chr(10)
        + "sh : " + repr(_ran(sh_result)) + chr(10)
        + "ps1: " + repr(_ran(ps_result))
    )

    def budget_lines(result):
        return [ln for ln in result.stderr.splitlines()
                if ln.startswith("deferred to /crew:verify:")
                or "UNSTATED" in ln or "stop budget" in ln]

    assert budget_lines(sh_result) == budget_lines(ps_result), (
        "the two flavours reported the budget differently." + chr(10)
        + "sh : " + repr(budget_lines(sh_result)) + chr(10)
        + "ps1: " + repr(budget_lines(ps_result))
    )
