"""Every Resolve-CrewBash call site must refuse by name on an empty return
(B2, BLOCKER).

test_verify_gate_bash_resolver.py's
test_prints_nothing_not_the_bare_name_when_every_candidate_is_rejected
proves the resolver ITSELF now returns '' rather than the bare string
'bash' when every PATH candidate is rejected. That alone does not fix the
defect: a caller that treats an empty return as "fall through to a
default" and invokes `& $bashExe` anyway reintroduces exactly the same
hang, just one call site downstream. This module is the STRING-level check
-- same reasoning as test_verify_gate_bash_resolver_extension_guard.py --
that both remaining call sites in verify-gate.ps1 that actually EXECUTE the
resolved bash (the smoke lane and the per-rule loop; the third call site,
-PrintBash, only echoes the value back and never invokes it) check for an
empty result and refuse instead of calling through it.

The rule loop ALSO has a true behavioural test now:
test_verify_gate_bash_resolver.py's
test_gate_refuses_by_name_instead_of_hanging_on_an_all_rejected_path runs
the real gate end to end, with `git` wrapped as a PowerShell function so
the gate's own `git diff`/`git ls-files` calls (needed before the rule
loop is ever reached) keep working while Resolve-CrewBash's tier a still
falls through to tier b -- the same technique
test_falls_through_when_git_is_a_powershell_function already validates in
that file. The smoke lane has no behavioural twin: it only runs when
.crew/verify.json is ABSENT, which is a distinct fixture shape from the
rule-loop test above, so its coverage here stays string-level.
"""
import pathlib

import context  # noqa: F401  pylint: disable=unused-import

_PS1 = pathlib.Path(context._ROOT) / "hooks" / "scripts" / "verify-gate.ps1"  # pylint: disable=protected-access


def _src():
    return _PS1.read_text(encoding="utf-8")


def test_the_resolver_no_longer_falls_back_to_the_bare_name():
    body = _src()
    start = body.index("function Resolve-CrewBash {")
    end = body.index("\nfunction Resolve-CrewPython {", start)
    resolver = body[start:end]
    assert "return 'bash'" not in resolver, (
        "Resolve-CrewBash still returns the bare string 'bash' as its "
        "final fallback -- '& $bashExe' re-resolves that through "
        "PowerShell's own PATH lookup and lands back on the exact "
        "candidate this function's own loop just rejected, hanging.")
    assert resolver.rstrip().endswith("return ''\n}") or "return ''" in resolver, (
        "no empty-string fallback found in Resolve-CrewBash - callers "
        "need an unambiguous 'nothing usable' value to refuse on")


def test_the_smoke_lane_refuses_named_before_invoking(tmp_path):  # pylint: disable=unused-argument
    body = _src()
    marker = 'if ($smoke) {\n    $bashExe = Resolve-CrewBash'
    assign_pos = body.index(marker)
    invoke_marker = "& $bashExe $smoke"
    invoke_pos = body.index(invoke_marker, assign_pos)
    between = body[assign_pos:invoke_pos]

    assert "if (-not $bashExe)" in between, (
        "the smoke lane assigns $bashExe from Resolve-CrewBash and then "
        "invokes it with no empty-return guard in between - an empty "
        "result falls straight through to '& $bashExe $smoke'. Text "
        "between assignment and invocation:\n" + between)
    # The guard must actually LEAVE without reaching the invocation -
    # `exit` is the only way this function's flat (non-nested-function)
    # top-level code stops here; a guard that only logs and falls through
    # would still hit '& $bashExe $smoke' on the next line with an empty
    # $bashExe.
    guard_pos = between.index("if (-not $bashExe)")
    assert "exit" in between[guard_pos:], (
        "the smoke lane's empty-bash guard does not exit - it would fall "
        "through to the invocation anyway. Guard body:\n" + between[guard_pos:])


def test_the_rule_loop_refuses_named_before_invoking():
    body = _src()

    # B3 changed the per-rule invocation shape: bash now does its own
    # redirect via a wrapper script (`eval "$CMD" > "$OUT" 2>&1 </dev/null`,
    # driven by CREW_VERIFY_RULE_CMD/CREW_VERIFY_RULE_OUT env vars) rather
    # than PowerShell redirecting bash's own stdout with
    # `& $bashExe -c $c > $ruleOutFile`. That older shape no longer exists
    # in the file - anchor on the real invocation instead of the comment
    # text near it, and fail loudly (not with a bare ValueError) if either
    # anchor is missing or ambiguous.
    reset_marker = "$ruleOutFile = $null\n"
    invoke_marker = "$null | & $bashExe -c $wrapperScript"

    reset_count = body.count(reset_marker)
    assert reset_count == 1, (
        f"expected exactly one {reset_marker!r} (the per-rule capture-file "
        f"reset) in verify-gate.ps1, found {reset_count} - cannot anchor "
        "the rule-loop region unambiguously. Either the reset was "
        "duplicated/removed, or this marker needs updating for a new "
        "shape of the reset line.")
    reset_pos = body.index(reset_marker)

    invoke_count = body.count(invoke_marker)
    assert invoke_count == 1, (
        f"expected exactly one {invoke_marker!r} (B3's per-rule bash "
        f"invocation) in verify-gate.ps1, found {invoke_count} - cannot "
        "anchor the rule loop's invocation. If the invocation shape "
        "changed again, update this marker to match it.")
    invoke_pos = body.find(invoke_marker, reset_pos)
    assert invoke_pos != -1, (
        f"found {invoke_marker!r} in verify-gate.ps1, but not after the "
        f"{reset_marker!r} reset - the reset and the invocation are out "
        "of order (or belong to unrelated code), so the region between "
        "them cannot be trusted to be the per-rule loop.")

    chain = body[reset_pos:invoke_pos]

    guard_marker = "if (-not $bashExe)"
    guard_count = chain.count(guard_marker)
    assert guard_count == 1, (
        f"expected exactly one {guard_marker!r} empty-bash refusal between "
        f"the {reset_marker!r} reset and the invocation, found "
        f"{guard_count} - the guard may be missing, duplicated, or moved "
        "outside this region. Region:\n" + chain)
    guard_pos = chain.index(guard_marker)

    # The guard must be an EARLIER branch of the SAME if/elseif chain that
    # gates the invocation, not an unrelated check elsewhere that happens
    # to contain the same substring - the invocation itself must be
    # reached only via 'elseif', proving it is mutually exclusive with the
    # empty-bash refusal branch.
    elseif_marker = "} elseif ($ruleOutFile) {"
    elseif_count = chain.count(elseif_marker)
    assert elseif_count == 1, (
        f"expected exactly one {elseif_marker!r} following the empty-bash "
        f"guard in this region, found {elseif_count} - the invocation's "
        "branch may not be exclusive with the refusal branch. Region:\n"
        + chain)
    elseif_pos = chain.index(elseif_marker, guard_pos)
    assert elseif_pos > guard_pos, (
        "the '} elseif ($ruleOutFile) {' branch that gates the invocation "
        "comes before the empty-bash refusal guard, not after - the "
        "invocation is not proven mutually exclusive with refusal. "
        "Region:\n" + chain)

    guard_body = chain[guard_pos:elseif_pos]
    assert "$rc = 1" in guard_body or "$rc=1" in guard_body, (
        "the rule-loop's empty-bash guard does not set a non-zero $rc, so "
        "the rule would be recorded as passing with no output rather than "
        "FAILED with a named reason. Guard body:\n" + guard_body)
