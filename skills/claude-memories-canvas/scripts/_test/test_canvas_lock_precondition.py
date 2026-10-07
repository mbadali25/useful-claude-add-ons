"""The canvas skill's write-lock step, held to the same contract as the vault's.

`claude-memories-vault` settled the lock question: the script is a host-local
artifact that reaches a machine only when that machine installs it, so "no lock
here" is a THIRD outcome alongside "I took it" and "someone else holds it", and
both reflexes on that third outcome are unsafe -- stopping leaves the vault
unwritable, skipping reinstates the 68-file collision the lock exists to
prevent.

This skill's step 7 was left behind by that fix. It still told an agent only
that "non-zero from `-Acquire` means someone else holds it: stop", which on a
host with no lock installed is a false reading of a missing answer -- the
unknown collapsing into a value that looks like a check happened.

**Two skills documenting one lock will drift**, and the half that drifts is the
half nobody is testing. That is what these assertions are for: they pin that
this document names the third outcome and points at the vault skill for the
full branch, rather than re-stating it in prose that can go stale
independently.

**Why this suite does not check that the lock path exists.** It cannot, and no
suite can -- the lock is in no clone and no sync, by design. The checkable
property, and the one whose absence caused the defect, is that the document
declares its precondition and names an outcome for the case where it does not
hold.

Runs standalone (`python3 test_lock_precondition.py`) as well as under pytest.
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL = os.path.normpath(os.path.join(_HERE, os.pardir, os.pardir, "SKILL.md"))

_LOCK_SCRIPT = "vault-lock.ps1"
_SIBLING = "claude-memories-vault"


def _read():
    with open(_SKILL, encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    """Collapse whitespace so a probe is not defeated by where a line wrapped."""
    return re.sub(r"\s+", " ", text)


def _lock_step(text):
    """Step 7 of the workflow, up to the next top-level heading."""
    start = text.index("**Take the vault lock")
    rest = text[start:]
    end = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def _invocations(step):
    """Lines that actually run the lock script."""
    return [line for line in step.splitlines() if '-File "$LOCK"' in line]


def test_the_interpreter_is_never_named_bare():
    """A bare `pwsh` is not on Git Bash's PATH on Windows.

    "command not found" and "the lock refused you" are the same exit status to
    an agent reading only the status, so the interpreter must be resolved.
    """
    text = _read()

    for line in _invocations(_lock_step(text)):
        assert line.lstrip().startswith('"$PWSH"'), f"unresolved interpreter: {line!r}"

    assert not re.search(r"^\s*pwsh\s+-NoProfile", text, re.MULTILINE), (
        "a bare `pwsh -NoProfile` invocation is back in the document"
    )


def test_the_resolver_tries_every_candidate_verify_json_tries():
    """Ported from `.crew/verify.json:178`; the order is load-bearing.

    Under WSL the reachable binary is the Windows one and is named `pwsh.exe`,
    so both known locations are tried with AND without the suffix.
    """
    step = _flat(_lock_step(_read()))

    for candidate in (
        "pwsh pwsh.exe",
        '"/c/Program Files/PowerShell/7/pwsh"',
        '"/c/Program Files/PowerShell/7/pwsh.exe"',
        '"/mnt/c/Program Files/PowerShell/7/pwsh.exe"',
        '"/mnt/c/Program Files/PowerShell/7/pwsh"',
    ):
        assert candidate in step, f"resolver does not try {candidate}"


def test_status_is_offered_before_acquire():
    """`-Status` is what tells an agent which branch it is on.

    Ordering is the assertion: a `-Status` line printed after `-Acquire` is
    read only by someone who already ran the command this step is about.
    """
    invocations = _invocations(_lock_step(_read()))

    assert invocations, f"no {_LOCK_SCRIPT} invocation found in the lock step"
    assert "-Status" in invocations[0]


def test_unavailable_never_collapses_into_held():
    """The runnable block must branch on it, not just the prose around it."""
    step = _lock_step(_read())

    assert '[ -z "$PWSH" ] || [ ! -f "$LOCK" ]' in step
    assert "NO VAULT LOCK" in step
    assert "not a failure and not contention" in step


def test_the_third_outcome_is_named_and_both_reflexes_rejected():
    """Neither stopping nor writing-anyway is the answer, and it must say so."""
    step = _flat(_lock_step(_read()))

    assert "No lock on this host is a third outcome, not a refusal" in step
    assert "Both reflexes are wrong" in step
    assert "leaves the vault unwritable" in step
    assert "reinstates the collision" in step


def test_the_host_local_reason_is_given_not_just_asserted():
    """An agent that knows WHY the lock is absent will not go hunting for it."""
    step = _flat(_lock_step(_read()))

    assert "host-local artifact" in step
    assert "Obsidian Sync payload" in step
    assert "git history" in step


def test_it_defers_to_the_vault_skill_for_the_full_branch():
    """One lock, two documents. The pointer is what stops them drifting."""
    step = _flat(_lock_step(_read()))

    assert _SIBLING in step
    assert "Writing into the vault" in step
    assert "drifting apart" in step


def test_the_short_version_is_self_sufficient():
    """An agent that loaded only this skill must not be left stranded.

    Deferring to the sibling is right, but a pointer alone fails the reader who
    never loads it -- so the minimum safe procedure is restated here.
    """
    step = _flat(_lock_step(_read()))

    assert "no vault lock" in step.lower()
    assert "git add -A" in step
    assert "git status --porcelain" in step


def test_the_fallback_is_not_described_as_a_lock():
    """Recording a blast-radius bound as a lock is how the gap gets closed on paper."""
    step = _flat(_lock_step(_read()))

    assert "That is not a lock and must not be recorded as one" in step
    assert "serializes nothing" in step


def _main():
    passed, failures = 0, []
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            passed += 1
            print(f"ok   {name}")
        except AssertionError as exc:
            failures.append(name)
            print(f"FAIL {name}: {exc}")
    print(f"\n{passed} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
