"""The vault write lock is prose, and prose is what went wrong.

`SKILL.md` told every agent to acquire a lock at
`C:\\repos\\claude-memories\\.claude\\vault-lock.ps1` with no precondition and no
failure branch. On a host where that script is not installed -- which is every
non-Windows host, and was the Linux host this was found on -- the instruction
has no defined outcome, and **both** available responses are unsafe: an agent
that stops leaves the vault unwritable, and an agent that skips the lock
reinstates the exact collision the lock exists to prevent (one agent's 68-file
commit swallowing another's staged-but-uncommitted edits).

**Why this suite does not check that the path exists.** It cannot, and no
suite can. The lock is host-local *by design*: the vault's own `CLAUDE.md`
records `.claude/` as "host-local only", outside the Obsidian Sync payload, and
`git log --all -- .claude` in the vault returns nothing, so the script is in no
clone and no sync. "The cited path resolves" is therefore not a property of
this repository and asserting it would fail on every machine including the ones
where the lock genuinely works.

The property that IS checkable, and the one whose absence caused the defect, is
that the document **declares its own precondition and names an outcome for the
case where the precondition does not hold**. That is what each assertion below
pins. An instruction that cannot be followed is worse than an acknowledged gap,
because the agent that cannot follow it has nowhere to go.

Runs standalone (`python3 test_lock_precondition.py`) as well as under pytest,
because this directory is not in any CI pytest invocation yet -- see the
registration note in the ticket report.
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL = os.path.normpath(os.path.join(_HERE, os.pardir, os.pardir, "SKILL.md"))

_LOCK_SCRIPT = "vault-lock.ps1"


def _read():
    with open(_SKILL, encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    """Collapse whitespace so a probe is not defeated by where a line wrapped.

    Every prose assertion below runs against this. Asserting on raw text made
    one of them fail for the single reason that `*Stopping* leaves ...` broke
    across a newline -- a false red that says nothing about the claim, and the
    kind that gets a check deleted rather than fixed.
    """
    return re.sub(r"\s+", " ", text)


def _lock_step(text):
    """The numbered `Take the lock` step, up to the next top-level list item."""
    start = text.index("**Take the lock")
    rest = text[start:]
    end = re.search(r"^3\. \*\*", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def test_lock_step_declares_the_script_is_host_local():
    step = _flat(_lock_step(_read()))

    assert "host-local" in step
    assert "Obsidian Sync" in step
    assert "git history" in step


def test_lock_step_states_the_lock_does_not_serialize_across_hosts():
    step = _flat(_lock_step(_read()))

    assert "serializes agents on this box only" in step
    assert "not** a case this lock covers" in step


def test_no_lock_case_is_named_and_rejects_both_unsafe_responses():
    step = _flat(_lock_step(_read()))

    assert "No lock on this host" in step
    assert "both reflexes are wrong" in step.lower()
    assert "Stopping* leaves the vault unwritable" in step
    assert "as though you had taken it* reinstates" in step


def test_no_lock_case_gives_the_agent_something_to_do():
    step = _flat(_lock_step(_read()))

    assert "git add -- <the exact files you wrote>" in step
    assert "git status --porcelain" in step
    for sweep in ("git add -A", "git add .", "git commit -a"):
        assert f"Never `{sweep}`" in step or f"never `{sweep}`" in step


def test_the_fallback_is_not_described_as_a_lock():
    step = _flat(_lock_step(_read()))

    assert "None of that is a lock" in step
    assert "It serializes nothing" in step


def test_status_is_offered_before_acquire():
    """`-Status` is the check that tells an agent which branch it is on.

    Ordering is the assertion, not presence: an agent reads top-down, and a
    `-Status` line printed after `-Acquire` is read only by someone who has
    already run the command whose failure mode this whole section is about.
    """
    step = _lock_step(_read())
    invocations = [
        line for line in step.splitlines() if _LOCK_SCRIPT in line and "pwsh" in line
    ]

    assert invocations, f"no {_LOCK_SCRIPT} invocation found in the lock step"
    assert "-Status" in invocations[0]


def test_every_lock_invocation_sits_inside_the_lock_step():
    """A copyable command outside the step carries none of the caveats."""
    text = _read()
    step = _lock_step(text)

    assert text.count(_LOCK_SCRIPT) == step.count(_LOCK_SCRIPT)


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
