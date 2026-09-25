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

Behavioural coverage for the smoke lane and the rule loop is not
practical here: both run after this gate's own `git diff`/`git ls-files`
calls, which need a REAL git on PATH -- and a real git for Windows install
always has a real bash.exe two directories from git.exe, so any PATH
built to exercise tier b (no usable bash) also breaks the gate's own git
calls before either lane is ever reached. -PrintBash exits before any of
that runs, which is why it is the one call site with a true behavioural
test.
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
    # The per-rule invocation inside the try/finally block, guarded by
    # $ruleOutFile (temp-file capture) succeeding.
    invoke_marker = "& $bashExe -c $c > $ruleOutFile"
    invoke_pos = body.index(invoke_marker)
    # Back up to the start of the enclosing if/elseif/else chain that
    # decides whether to invoke at all (the closest preceding
    # '$ruleOutFile = $null' resets the capture-file state for this rule).
    chain_start = body.rindex("$ruleOutFile = $null", 0, invoke_pos)
    between = body[chain_start:invoke_pos]

    assert "if (-not $bashExe)" in between, (
        "the per-rule loop has no empty-bash guard between resetting "
        "$ruleOutFile and invoking '& $bashExe -c $c' - an empty $bashExe "
        "(every PATH candidate rejected) falls straight through to that "
        "invocation, which PowerShell resolves right back to the "
        "rejected shim and hangs. Text in between:\n" + between)

    # The guard must be an EARLIER branch of the SAME if/elseif chain that
    # gates the invocation, not an unrelated check elsewhere that happens
    # to contain the same substring - the invocation itself must be
    # reached only via 'elseif', proving it is mutually exclusive with the
    # empty-bash refusal branch. `between` ends mid-line (right before the
    # invocation text itself), so look for the 'elseif' that opens the
    # invocation's own branch rather than the last whole line, which is
    # only the invocation's own leading pipe.
    guard_pos = between.index("if (-not $bashExe)")
    assert "} elseif ($ruleOutFile) {" in between[guard_pos:], (
        "the invocation is not reached via an 'elseif' following the "
        "empty-bash refusal branch, so both could run, or the refusal "
        "could be bypassed entirely. Text after the guard:\n"
        + between[guard_pos:])

    guard_pos = between.index("if (-not $bashExe)")
    guard_body = between[guard_pos:]
    assert "$rc = 1" in guard_body or "$rc=1" in guard_body, (
        "the rule-loop's empty-bash guard does not set a non-zero $rc, so "
        "the rule would be recorded as passing with no output rather than "
        "FAILED with a named reason. Guard body:\n" + guard_body)
