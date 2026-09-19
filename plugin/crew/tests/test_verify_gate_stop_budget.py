"""The Stop budget: verify-gate runs what fits and SAYS what it deferred.

`.crew/verify.json` carried each rule's cost as PROSE inside its `why` ("8s",
"29s", "245s") and nothing could read it, so a Stop gate that had grown to two
minutes had no way to spend that time cheapest-first. `seconds` is that number
in a field; `verify.stopBudgetSeconds` (default 60) is the bound.

Five properties are load-bearing and each has a case here, in BOTH flavours:

0. **`seconds` is PER RULE and is charged ONCE.** A rule runs whole or defers
   whole. The spec that introduced the budget said "run matched rules in
   ascending seconds" and never said what the unit was, so the first
   implementation charged every COMMAND in a rule the whole rule's cost: a
   rule with `"seconds": 40` and two commands ran the first, priced the second
   at another 40, and deferred it under the 60s default -- splitting the rule
   and reporting the half that did not run as unverified. That is a
   specification error rather than an implementation one, which is why the
   unit is now stated in the code beside the arithmetic.
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


# ------------------------------------------------------------ the unit
#
# `seconds` prices the RULE, not each command in it. Every map above happens
# to have one command per rule, so every case above passes under either
# reading -- which is exactly how the unit went unstated for a release.


_TWO_COMMAND_RULE = {
    "version": 1,
    "rules": [
        {"paths": ["a.py"], "seconds": 40,
         "run": ["echo RAN-one", "echo RAN-two"],
         "why": "ONE rule costing 40s in total, under the 60s default"},
    ],
    "default": [],
    "unmapped": "ignore",
}


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_that_fits_is_not_split_across_its_commands(flavour, tmp_path):
    """MUST-ALLOW, and the reported defect. The whole rule costs 40s and the
    budget is 60, so both of its commands run -- charging the second another
    40 defers a check the budget has room for and splits a rule in half."""
    root = _repo(tmp_path, verify_map=_TWO_COMMAND_RULE)
    result = _run(flavour, root)

    assert result.returncode == 0, result.stderr
    ran = _ran(result)
    assert ran == ["echo RAN-one", "echo RAN-two"], (
        "a 40s rule with two commands fits a 60s budget WHOLE. Charging each "
        "command the rule's cost makes it 80 and defers the second. ran="
        + repr(ran) + chr(10) + result.stderr
    )
    assert "deferred to /crew:verify" not in result.stderr, (
        "nothing should have been deferred: the rule costs 40 of 60. "
        + result.stderr
    )
    assert "the verified baseline was NOT advanced" not in result.stderr, (
        "a rule that ran whole leaves nothing unchecked, so the baseline must "
        "advance. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_rule_that_does_not_fit_defers_WHOLE(flavour, tmp_path):
    """MUST-BLOCK, and the other half of the unit. Charging once must not turn
    into running part of a rule that does not fit: a half-run rule is not a
    cheaper rule, it is a rule nobody can say was checked."""
    straddling = {
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 5, "run": ["echo RAN-cheap"],
             "why": "fits"},
            {"paths": ["a.py"], "seconds": 90,
             "run": ["echo RAN-big-a", "echo RAN-big-b"],
             "why": "does not fit, and must not fit HALF"},
        ],
        "default": [],
        "unmapped": "ignore",
    }
    root = _repo(tmp_path, verify_map=straddling)
    result = _run(flavour, root)

    ran = _ran(result)
    assert ran == ["echo RAN-cheap"], (
        "the 90s rule does not fit a 60s budget and must defer entirely. ran="
        + repr(ran) + chr(10) + result.stderr
    )
    for cmd in ("echo RAN-big-a", "echo RAN-big-b"):
        assert "deferred to /crew:verify: " + cmd + " (90s)" in result.stderr, (
            "every command of a deferred rule must be named, or the reader "
            "cannot tell what went unchecked. " + result.stderr
        )
    assert "deferred 2" in result.stderr, result.stderr
    assert "the verified baseline was NOT advanced" in result.stderr, (
        "a deferred rule was never checked, so the tree is not verified. "
        + result.stderr
    )


@pytest.mark.skipif(
    _BASH is None or not sys.platform.startswith("win") or _PWSH is None,
    reason="parity needs both flavours on the same machine",
)
def test_both_flavours_charge_the_rule_once(tmp_path):
    """The unit is a place the two implementations can drift silently: the
    arithmetic lives in a python heredoc on one side and in PowerShell on the
    other, and a fix applied to one reads as done. Same map, same selection.
    """
    sh_result = _run("sh", _repo(tmp_path / "sh",
                                 verify_map=_TWO_COMMAND_RULE))
    ps_result = _run("ps1", _repo(tmp_path / "ps",
                                  verify_map=_TWO_COMMAND_RULE))

    assert _ran(sh_result) == _ran(ps_result) == ["echo RAN-one",
                                                  "echo RAN-two"], (
        "the two flavours priced the same rule differently." + chr(10)
        + "sh : " + repr(_ran(sh_result)) + chr(10)
        + "ps1: " + repr(_ran(ps_result))
    )


# ------------------------------------------------------- the obligation
#
# The same command string reaches the run list from several sources and is
# merged into one entry. THE MERGED ENTRY CARRIES THE STRONGEST OBLIGATION OF
# ANY SOURCE -- merging resolves toward RUN, never toward DEFER.
#
#   `always`                 unconditional.
#   a rule with no `seconds` unconditional-until-priced.
#   a rule with `seconds`    deferrable, and the only deferrable level.
#
# It used to resolve the other way, because the classification asked only
# "does this command have a cost?" and any one priced rule set one. Measured
# in BOTH flavours: `"always": ["sh -c \"exit 1\""]` beside a 90s rule naming
# the same command deferred the mandatory check and the gate exited 0 -- a
# failing check the map calls unconditional, never run, turn passed.


def _shared(always=None, rules=None):
    m = {"version": 1, "rules": rules or [], "default": [],
         "unmapped": "ignore"}
    if always is not None:
        m["always"] = always
    return m


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_always_command_is_not_deferred_by_a_priced_rule(flavour, tmp_path):
    """MUST-BLOCK, and the reported case verbatim. The command fails, so a
    gate that runs it exits 2 and a gate that defers it exits 0 -- the
    strongest possible signal that dedup weakened the obligation."""
    cmd = 'sh -c "exit 1"'
    root = _repo(tmp_path, verify_map=_shared(
        always=[cmd],
        rules=[{"paths": ["a.py"], "seconds": 90, "run": [cmd],
                "why": "priced well over the 60s budget"}]))
    result = _run(flavour, root)

    assert result.returncode == 2, (
        "an `always` command was deferred because a priced rule happened to "
        "name it too, so a mandatory failing check never ran and the turn "
        "passed. rc=" + str(result.returncode) + " " + result.stderr
    )
    assert "deferred to /crew:verify: " + cmd not in result.stderr, (
        "`always` is unconditional; it must never appear as deferred. "
        + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_an_unpriced_rule_makes_its_commands_unconditional(flavour, tmp_path):
    """MUST-BLOCK for the variant nobody reported, which only became visible
    from stating the property rather than the repair: a command named by BOTH
    an unpriced rule and a priced one. The unpriced rule is
    unconditional-until-priced, so the merged entry must run."""
    root = _repo(tmp_path, verify_map=_shared(rules=[
        {"paths": ["a.py"], "seconds": 90, "run": ["echo RAN-mixed"],
         "why": "priced, does not fit"},
        {"paths": ["a.py"], "run": ["echo RAN-mixed"],
         "why": "NO seconds -- deferring it acts on a number nobody wrote"},
    ]))
    result = _run(flavour, root)

    assert "echo RAN-mixed" in _ran(result), (
        "a command an unpriced rule names must RUN; deferring it acts on a "
        "cost that rule never stated. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_two_priced_rules_keep_the_affordable_instance(flavour, tmp_path):
    """MUST-ALLOW. Both sources are deferrable, so neither is mandatory -- but
    dedup must still keep the instance that FITS rather than the one that does
    not. This came out correct from charging per rule in 0.19.92 (the cheap
    rule is reached first and claims the command); the case is here so a later
    change to the merge cannot quietly reverse it."""
    root = _repo(tmp_path, verify_map=_shared(rules=[
        {"paths": ["a.py"], "seconds": 5, "run": ["echo RAN-shared"],
         "why": "affordable"},
        {"paths": ["a.py"], "seconds": 90, "run": ["echo RAN-shared"],
         "why": "same command, unaffordable"},
    ]))
    result = _run(flavour, root)

    assert "echo RAN-shared" in _ran(result), (
        "one of the two rules naming this command fits the budget, so the "
        "command runs. " + result.stderr
    )
    assert "deferred to /crew:verify" not in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_command_with_no_unconditional_source_is_still_deferrable(
        flavour, tmp_path):
    """The paired MUST-ALLOW for all three above, and the one that stops
    "resolve toward RUN" degenerating into "never defer anything" -- which
    would pass every case in this section and delete the budget."""
    root = _repo(tmp_path, verify_map=_shared(rules=[
        {"paths": ["a.py"], "seconds": 90, "run": ["echo RAN-big"],
         "why": "priced, and named by nothing unconditional"},
    ]))
    result = _run(flavour, root)

    assert "echo RAN-big" not in _ran(result), (
        "90s does not fit a 60s budget and nothing makes this command "
        "unconditional, so it must still defer. " + result.stderr
    )
    assert "deferred to /crew:verify: echo RAN-big (90s)" in result.stderr, (
        result.stderr
    )


# --------------------------------- where a mandatory command RUNS, and what
# --------------------------------- it costs
#
# 0.19.94 attached mandatory-ness to a COMMAND and hoisted each mandatory
# command to the front of the list, charging it there. Both halves were wrong,
# and the first one fails in the expensive direction -- quietly and with the
# blame in the wrong place.
#
# ORDER. A rule that declares `run: ["prepare", "check"]` has stated a
# dependency. Hoisting `check` ran it FIRST, so the check fails for a reason
# that is not the user's: they see their own check red and go debugging their
# own code, while it was the gate that reordered it. A check that reports the
# wrong cause is worse than no check.
#
# CHARGE. The hoisted command was charged its rule's cost and the rule was
# then charged again for the rest -- the per-command double-charge 0.19.92
# removed, reintroduced from the other end.
#
# Both are fixed by lifting the obligation from the command to the RULE that
# carries it. That is forced rather than chosen: a rule runs whole or defers
# whole (0.19.92) and a command keeps its place inside its rule, so `check`
# cannot run without the `prepare` in front of it.


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_mandatory_command_keeps_its_place_inside_its_rule(flavour, tmp_path):
    """MUST-BLOCK for the ORDER half, on its own. `echo check` is in `always`
    and is the SECOND command of its rule; it must still run second."""
    root = _repo(tmp_path, verify_map={
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 10,
                   "run": ["echo prepare", "echo check"],
                   "why": "check depends on prepare -- that is what `run` order means"}],
        "always": ["echo check"],
        "default": [], "unmapped": "ignore",
    })
    result = _run(flavour, root)

    assert _ran(result) == ["echo prepare", "echo check"], (
        "`echo check` is mandatory, so it was hoisted out of its rule and run "
        "before the `echo prepare` its own rule puts in front of it. Being "
        "mandatory decides whether a command can be DEFERRED, never where it "
        "RUNS. ran=" + repr(_ran(result)) + chr(10) + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_mandatory_command_does_not_double_charge_its_rule(flavour, tmp_path):
    """MUST-BLOCK for the CHARGE half. The rule costs 40 ONCE. Charging `A`
    as mandatory and then the rule again makes it 80, and B -- which the
    budget has room for -- is deferred."""
    root = _repo(tmp_path, verify_map={
        "version": 1,
        "rules": [{"paths": ["a.py"], "seconds": 40,
                   "run": ["echo A", "echo B"],
                   "why": "the whole rule costs 40, under the 60s default"}],
        "always": ["echo A"],
        "default": [], "unmapped": "ignore",
    })
    result = _run(flavour, root)

    assert _ran(result) == ["echo A", "echo B"], (
        "a 40s rule fits a 60s budget whole. Charging the mandatory command "
        "separately makes it 80 and defers the rest of its own rule. ran="
        + repr(_ran(result)) + chr(10) + result.stderr
    )
    assert "deferred to /crew:verify" not in result.stderr, result.stderr
    assert "the verified baseline was NOT advanced" not in result.stderr, (
        "nothing was deferred, so the baseline must advance. " + result.stderr
    )


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_a_mandatory_rule_is_charged_once_against_the_rest_of_the_budget(
        flavour, tmp_path):
    """MUST-BLOCK for the CHARGE invariant, and the shape where it is actually
    observable.

    The case above no longer detects the double charge on its own, and that is
    worth writing down rather than quietly replacing: lifting the obligation
    to the RULE means the mandatory rule runs whole whatever it is charged, so
    inflating `spent` stops changing which of ITS commands run. It still
    changes what is left for everything else. Caught by sabotage -- the
    hoist-and-charge mutation came back GREEN against that case and RED
    against this one.

    40s mandatory rule plus a 15s deferrable rule, budget 60. Charged once,
    55 fits and `echo C` runs. Charged twice, `spent` reaches 80 and a rule
    the budget had room for is deferred.
    """
    root = _repo(tmp_path, verify_map={
        "version": 1,
        "rules": [
            {"paths": ["a.py"], "seconds": 40, "run": ["echo A", "echo B"],
             "why": "mandatory, and costs 40 ONCE"},
            {"paths": ["a.py"], "seconds": 15, "run": ["echo C"],
             "why": "deferrable, and fits in what is left of the budget"},
        ],
        "always": ["echo A"],
        "default": [], "unmapped": "ignore",
    })
    result = _run(flavour, root)

    assert _ran(result) == ["echo A", "echo B", "echo C"], (
        "40 + 15 fits a 60s budget. Charging the mandatory command separately "
        "from its rule makes it 80 and defers a rule there was room for. ran="
        + repr(_ran(result)) + chr(10) + result.stderr
    )
    # NOT asserted on the "ran Ns of stated cost" summary: the gate prints
    # that line only when something WAS deferred, so on a clean selection it
    # is absent and an assertion on it fails against correct behaviour. The
    # observable property is which commands ran -- checked above, and it is
    # what the mutation flips.
    assert "deferred to /crew:verify" not in result.stderr, result.stderr


@pytest.mark.parametrize("flavour", _FLAVOURS)
def test_being_mandatory_does_not_change_what_a_rule_costs(flavour, tmp_path):
    """The mirror of the 0.19.92 unit, checked against it rather than in
    isolation: the SAME rule, once with a mandatory command in it and once
    without, must run the same commands for the same charge. A rule's cost is
    a fact about the rule, not about who else names its commands."""
    rule = {"paths": ["a.py"], "seconds": 40,
            "run": ["echo A", "echo B"], "why": "40s, two commands"}
    plain = _run(flavour, _repo(tmp_path / "plain", verify_map={
        "version": 1, "rules": [rule], "default": [], "unmapped": "ignore"}))
    marked = _run(flavour, _repo(tmp_path / "marked", verify_map={
        "version": 1, "rules": [rule], "always": ["echo A"],
        "default": [], "unmapped": "ignore"}))

    assert _ran(plain) == _ran(marked) == ["echo A", "echo B"], (
        "marking one command mandatory changed which commands ran." + chr(10)
        + "plain : " + repr(_ran(plain)) + chr(10)
        + "marked: " + repr(_ran(marked))
    )


# ----------------------------------------------------- the named neighbours
#
# Every round on this branch has closed two defects in this arithmetic and
# opened others one rung along, so the cases next to the one being fixed are
# checked here as a table rather than left to the next review. Each is a
# MUST-ALLOW: it states what the merge rule implies, so a later change that
# quietly re-derives the merge has to keep implying it.

_NEIGHBOURS = {
    # A mandatory command pulls BOTH rules that name it, and `T` rides along
    # because its rule runs whole. That is not incidental -- running `S` out
    # of the middle of the 90s rule is exactly the ordering defect above.
    "always-plus-two-costed-rules": (
        {"rules": [
            {"paths": ["a.py"], "seconds": 5, "run": ["echo S"], "why": "a"},
            {"paths": ["a.py"], "seconds": 90, "run": ["echo S", "echo T"],
             "why": "b"}],
         "always": ["echo S"]},
        ["echo S", "echo T"], []),
    # Nothing mandatory: the affordable rule claims the shared command and the
    # unaffordable one defers what is left of it.
    "two-costed-rules-no-always": (
        {"rules": [
            {"paths": ["a.py"], "seconds": 5, "run": ["echo S"], "why": "a"},
            {"paths": ["a.py"], "seconds": 90, "run": ["echo S", "echo T"],
             "why": "b"}]},
        ["echo S"], ["echo T"]),
    # Unconditional-until-priced reaches the priced rule that shares a
    # command with it, and that rule runs whole.
    "unpriced-command-also-in-a-costed-rule": (
        {"rules": [
            {"paths": ["a.py"], "seconds": 90, "run": ["echo M", "echo N"],
             "why": "priced"},
            {"paths": ["a.py"], "run": ["echo M"], "why": "unpriced"}]},
        ["echo M", "echo N"], []),
    # An empty `always` must add no obligation at all -- the ordinary budget
    # still applies.
    "empty-always": (
        {"rules": [
            {"paths": ["a.py"], "seconds": 5, "run": ["echo P"], "why": "a"},
            {"paths": ["a.py"], "seconds": 90, "run": ["echo Q"], "why": "b"}],
         "always": []},
        ["echo P"], ["echo Q"]),
    # Every command mandatory: the rule runs whole and is charged once, well
    # past the budget, because none of it can be deferred.
    "whole-rule-mandatory": (
        {"rules": [{"paths": ["a.py"], "seconds": 90,
                    "run": ["echo X", "echo Y"], "why": "a"}],
         "always": ["echo X", "echo Y"]},
        ["echo X", "echo Y"], []),
}


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("case", sorted(_NEIGHBOURS))
def test_the_neighbouring_merge_shapes(flavour, case, tmp_path):
    extra, expect_ran, expect_deferred = _NEIGHBOURS[case]
    verify_map = {"version": 1, "default": [], "unmapped": "ignore"}
    verify_map.update(extra)
    result = _run(flavour, _repo(tmp_path, verify_map=verify_map))

    assert _ran(result) == expect_ran, (
        case + ": ran " + repr(_ran(result)) + ", expected "
        + repr(expect_ran) + chr(10) + result.stderr
    )
    for cmd in expect_deferred:
        assert "deferred to /crew:verify: " + cmd in result.stderr, (
            case + ": expected " + cmd + " to be deferred. " + result.stderr
        )
    if not expect_deferred:
        assert "deferred to /crew:verify" not in result.stderr, (
            case + ": nothing should have deferred. " + result.stderr
        )


@pytest.mark.parametrize("flavour", _FLAVOURS)
@pytest.mark.parametrize("case", sorted(_NEIGHBOURS))
def test_the_neighbouring_shapes_do_not_reorder_a_rule(flavour, case,
                                                       tmp_path):
    """The ordering invariant over the same table. Whatever the merge selects,
    two commands of one rule that both run must run in the rule's `run`
    order -- checked here as well as in its own case, because the merge is
    where the order was lost."""
    extra = _NEIGHBOURS[case][0]  # only the shape matters here; the ran-set is the other table's job
    verify_map = {"version": 1, "default": [], "unmapped": "ignore"}
    verify_map.update(extra)
    result = _run(flavour, _repo(tmp_path, verify_map=verify_map))
    ran = _ran(result)

    for rule in verify_map["rules"]:
        positions = [ran.index(c) for c in rule["run"] if c in ran]
        assert positions == sorted(positions), (
            case + ": the commands of one rule ran out of their `run` order. "
            "rule=" + repr(rule["run"]) + " ran=" + repr(ran) + chr(10)
            + result.stderr
        )
