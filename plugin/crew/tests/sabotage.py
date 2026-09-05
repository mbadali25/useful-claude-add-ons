"""Sabotage test: reintroduce each bug and confirm the suite goes red.

Run it directly: `python3 plugin/crew/tests/sabotage.py`. For each mutation it
patches one file, runs the test that should catch the change, and restores the
file whether or not the run succeeded.

A test that stays green with the behaviour deleted is not coverage. Three of
the tests in this directory did exactly that until a review named them, so the
claim "this is tested" is checked here rather than asserted.

A mutation whose anchor no longer matches is a FAILURE, not a skip: the anchor
drifting is how this suite would quietly stop testing anything.
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
CREW = os.path.join(ROOT, "plugin", "crew")
STATE = os.path.join(CREW, "hooks", "scripts", "crew_state.py")
LADDER_DOC = os.path.join(CREW, "skills", "crew-scaling", "SKILL.md")

GUARD = '    if out["family"] is not None and out["family"] in authors:'
ROLE_PIN = '    decided = resolve_role(cfg, "dev", "developer")'
BLOCK_ONLY = (
    '    decided = {"family": family((dict_or_empty('
    'dict_or_empty(cfg).get("dev")).get("provider") or "claude"), None)}'
)

MUTATIONS = (
    (
        "family guard deleted",
        STATE,
        GUARD,
        "    if False:",
        ("tests/test_provider_table.py"
         "::test_an_unknown_author_family_bars_nothing"),
    ),
    (
        "author_families ignores role pins",
        STATE,
        ROLE_PIN,
        BLOCK_ONLY,
        ("tests/test_provider_table.py::"
         "test_author_family_honours_a_per_role_dev_pin_over_the_block_default"),
    ),
    (
        "bogus documented role",
        LADDER_DOC,
        "| 1 | + security",
        "| 1 | + ghost-reviewer, + security",
        "tests/test_role_ladder.py",
    ),
)


def run_test(target):
    """Run one pytest target from the crew directory; return its exit code."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-x"],
        cwd=CREW, capture_output=True, text=True, check=False)
    return completed.returncode


def read(target):
    with io.open(target, encoding="utf-8") as handle:
        return handle.read()


def write(target, text):
    with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def apply_mutation(target, find, replace):
    """Patch `target`, backing it up. False when the anchor is not unique.

    The backup is taken BEFORE the write and restored here if the write
    itself fails -- a disk error or an interrupt between `shutil.copy` and
    the last byte would otherwise leave the caller with a truncated source
    file and a `.bak` beside it, which is a worse outcome than the bug this
    script exists to find.
    """
    text = read(target)
    if text.count(find) != 1:
        return False
    shutil.copy(target, target + ".bak")
    try:
        write(target, text.replace(find, replace, 1))
    except BaseException:
        restore(target)
        raise
    return True


def restore(target):
    """Put `target` back if a backup is present. Safe to call twice."""
    backup = target + ".bak"
    if os.path.exists(backup):
        shutil.move(backup, target)


def main():
    """Run every mutation; return 0 only when all of them go red."""
    ok = True
    for label, target, find, replace, test in MUTATIONS:
        if not apply_mutation(target, find, replace):
            print(f"{'ANCHOR LOST -- suite is not testing this':40} {label}")
            ok = False
            continue
        try:
            code = run_test(test)
        finally:
            restore(target)
        if code == 0:
            print(f"{'STILL GREEN -- TEST IS VACUOUS':40} {label}")
            ok = False
        else:
            print(f"{'RED (good)':40} {label}")

    print("\nSABOTAGE SUITE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
