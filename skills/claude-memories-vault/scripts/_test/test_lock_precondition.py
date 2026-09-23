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


def _invocations(step):
    """Lines that actually run the lock script.

    Matches on `-File "$LOCK"` rather than on the literal script name: the
    interpreter and the vault root are both resolved into variables now, so no
    single line carries the interpreter and the script name together any more.
    An earlier version of this helper looked for a line containing both
    `vault-lock.ps1` and `pwsh`, and it went red on a correct document for
    exactly that reason.
    """
    return [line for line in step.splitlines() if '-File "$LOCK"' in line]


def test_status_is_offered_before_acquire():
    """`-Status` is the check that tells an agent which branch it is on.

    Ordering is the assertion, not presence: an agent reads top-down, and a
    `-Status` line printed after `-Acquire` is read only by someone who has
    already run the command whose failure mode this whole section is about.
    """
    invocations = _invocations(_lock_step(_read()))

    assert invocations, f"no {_LOCK_SCRIPT} invocation found in the lock step"
    assert "-Status" in invocations[0]


def test_the_interpreter_is_never_named_bare():
    """A bare `pwsh` is not on Git Bash's PATH on Windows.

    Its "command not found" is indistinguishable, from the exit code alone,
    from a lock that refused you -- the unknown collapsing into a value that
    looks like a check happened, which is the failure this whole step exists
    to prevent. So every invocation must go through the resolved variable.
    """
    text = _read()

    for line in _invocations(_lock_step(text)):
        assert line.lstrip().startswith('"$PWSH"'), f"unresolved interpreter: {line!r}"

    assert not re.search(r"^\s*pwsh\s+-NoProfile", text, re.MULTILINE), (
        "a bare `pwsh -NoProfile` invocation is back in the document"
    )


def test_the_resolver_tries_every_candidate_verify_json_tries():
    """Ported from `.crew/verify.json:178`, and the order is load-bearing.

    Under WSL the reachable binary is the Windows one and is named `pwsh.exe`,
    so omitting the suffix reported TOOL MISSING on a box where PowerShell was
    installed and usable. Both locations are therefore tried with AND without
    the suffix.
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


def test_unavailable_never_collapses_into_held():
    """The two outcomes must stay distinguishable inside the runnable block.

    Prose elsewhere in the step already says so; this pins that the code an
    agent copies branches on it, because the code is what actually runs.
    """
    step = _lock_step(_read())

    assert '[ -z "$PWSH" ] || [ ! -f "$LOCK" ]' in step
    assert "NO VAULT LOCK" in step
    assert "Never read this as contention." in step
    assert "An absent lock is not a held lock." in step


def test_every_lock_invocation_sits_inside_the_lock_step():
    """A copyable command outside the step carries none of the caveats."""
    text = _read()
    step = _lock_step(text)

    assert text.count(_LOCK_SCRIPT) == step.count(_LOCK_SCRIPT)


def test_no_user_profile_path_is_pinned_to_a_username():
    """`C:\\Users\\<name>\\...` is wrong on Linux and fragile on Windows.

    The vault root maps `C:\\repos\\X` <-> `/repos/X` between the two hosts. The
    user profile does NOT: the accounts are unrelated and need not share a
    name. Every remaining mention of a literal `C:\\Users\\` must therefore be
    the prose explaining why not to write one -- never an instruction.
    """
    for line in _read().splitlines():
        if "C:\\Users\\" not in line:
            continue
        assert "<someone>" in line, f"a username is pinned in an instruction: {line!r}"


def test_the_queue_writer_resolves_its_interpreter():
    """`C:\\Python314\\python.exe` names one build directory.

    It stops being true at the next Python upgrade on that same Windows box,
    never mind on a host that is not Windows.
    """
    text = _read()
    flat = _flat(text)

    assert "for c in python3 python py" in flat, "the queue writer pins an interpreter"
    assert '"$PY" "$QUEUE" checkoff' in flat
    assert "NO QUEUE WRITER" in flat, "no named outcome when the writer is absent"

    for line in text.splitlines():
        if "C:\\Python314" not in line:
            continue
        assert "names one build directory" in line, f"pinned interpreter: {line!r}"


def test_case_sensitivity_is_named_as_a_wikilink_consequence():
    """The difference that actually separates NTFS from ext4.

    The section used to list two consequences, both about the forbidden `:`
    and prefix-boundary counting -- neither of which differs by host. The one
    that does was absent, so a link correct on Windows dead-links on Linux and
    is reported broken on neither.
    """
    flat = _flat(_read())

    assert "Match the filename's CASE exactly" in flat
    assert "Three consequences" in flat
    assert "[[Project - Scripts]]" in flat and "Project - scripts.md" in flat
    assert "10 link occurrences resolve case-insensitively only" in flat


def test_the_case_finding_is_tied_to_the_promotion_count():
    """A reference count that differs by host cannot gate promotion silently.

    The 10 occurrences count toward `Project - scripts` on Windows and toward
    nothing on Linux, so the exact-boundary recount that disqualified 2 of 12
    candidates returns a different answer per host.
    """
    flat = _flat(_read())

    assert "host-dependent" in flat
    assert "say which host you counted on" in flat


def test_the_untested_part_is_marked_untested():
    """Whether Obsidian's own resolver papers over the 10 is not known.

    An unknown has to survive as its own value into everything derived from
    it, or the document reads as though it were checked.
    """
    flat = _flat(_read())

    assert "**Unverified:**" in flat
    assert "Nobody has tested it" in flat


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
