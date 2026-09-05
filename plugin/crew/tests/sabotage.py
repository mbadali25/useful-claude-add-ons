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
PLATFORM = os.path.join(CREW, "hooks", "scripts", "crew_platform.py")

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
        # The half of the one-slot fix that a green suite could hide. Both
        # spellings are the same value in the proven path, so a suite that
        # only exercises that path stays green with the bug restored.
        "dispatch history filtered by the record instead of the checkout",
        STATE,
        '            and (keep_all or item.get("branch") == here)',
        '            and item.get("branch") == there',
        ("tests/test_provider_table.py::"
         "test_a_stale_record_does_not_forget_this_branch_history"),
    ),
    (
        # `here is None` has two causes and only one is evidence. Dropping
        # keep_all makes an unreadable branch discard every named-branch
        # record, which is the Critical half of Codex's round-1 review.
        "an unreadable branch discards the named-branch history",
        STATE,
        "        keep_all = here is None and in_repo is not False",
        "        keep_all = False",
        ("tests/test_provider_table.py::"
         "test_an_unreadable_branch_keeps_the_named_branch_history"),
    ),
    (
        # Ten slots keyed on the model instead of the family means one
        # provider's model churn evicts the family that wrote the diff.
        "the history bound is spent per model instead of per family",
        STATE,
        '        fam = family(item.get("provider"), item.get("model"))',
        "        fam = None",
        ("tests/test_provider_table.py::"
         "test_the_history_bound_is_spent_per_family_not_per_model"),
    ),
    (
        # An atomic write stops a torn read and does nothing about two
        # dispatches both reading the same history and each publishing it
        # plus itself.
        "the dispatch read happens outside the lock",
        STATE,
        ("        with _dispatch_lock(root):\n"
         "            record = _write_dispatch(root, kind, entry)"),
        "        record = _write_dispatch(root, kind, entry)",
        ("tests/test_provider_table.py::"
         "test_the_dispatch_read_happens_inside_the_lock"),
    ),
    (
        # Skipping the backup when the name is taken destroys the newer
        # original and then reports that it was saved.
        "a second corruption is rewritten without its own backup",
        PLATFORM,
        "                if os.path.exists(candidate):\n                    continue",
        ("                if os.path.exists(candidate):\n"
         "                    saved_to = candidate\n"
         "                    break"),
        ("tests/test_platform_sync.py::"
         "test_a_second_corruption_gets_its_own_backup"),
    ),
    (
        "an empty config is adopted instead of healed",
        PLATFORM,
        "        if isinstance(parsed, dict) and parsed:",
        "        if isinstance(parsed, dict):",
        ("tests/test_platform_sync.py::"
         "test_heal_config_recreates_an_empty_object"),
    ),
    (
        # Without the republish, a clobbered write is simply gone -- which is
        # the whole reason the lock alone was not enough.
        "a clobbered write does not republish itself",
        STATE,
        "    for _attempt in range(DISPATCH_WRITE_TRIES):",
        "    for _attempt in range(1):",
        ("tests/test_provider_table.py::"
         "test_a_write_that_loses_a_race_republishes_itself"),
    ),
    (
        # Ordering derived from the file's layout instead of from what the
        # entries say puts the bound back at the mercy of the layout.
        "history order is taken from the file instead of from `at`",
        STATE,
        "        key=lambda item: float_or(item.get(\"at\"), 0.0),",
        "        key=lambda item: 0.0,",
        ("tests/test_provider_table.py::"
         "test_history_written_in_the_wrong_order_is_still_read_newest_first"),
    ),
    (
        # The clock is not monotonic, so it cannot be what decides that
        # the dispatch happening right now is the newest one.
        "the new entry is sorted by the clock instead of prepended",
        STATE,
        ('    history = [entry] + sorted(\n'
         '        [h for h in record.get(f"{kind}History") or []\n'
         '         if isinstance(h, dict)],'),
        ('    history = sorted(\n'
         '        [entry] + [h for h in record.get(f"{kind}History")'
         ' or []\n'
         '                   if isinstance(h, dict)],'),
        ("tests/test_provider_table.py::test_a_backward_clock_does_not"
         "_evict_the_dispatch_that_just_happened"),
    ),
    (
        # Without `at`, a writer's verification passes on an identical
        # entry another writer landed, and its own record never appears.
        "the write verification cannot tell two writers apart",
        STATE,
        '               for key in ("provider", "model", "branch",'
        ' "at")):',
        '               for key in ("provider", "model", "branch")):',
        ("tests/test_provider_table.py::"
         "test_a_writer_does_not_mistake_an_identical_entry_for_its_own"),
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

    # The copy and the write fail in ways that need opposite responses, so
    # they cannot share a handler. `shutil.copy` never modifies the SOURCE:
    # if it fails the original is still intact and the `.bak` is the damaged
    # one, so restoring from it is precisely what would corrupt the file this
    # is trying to protect. Discard the partial backup instead.
    try:
        shutil.copy(target, target + ".bak")
    except BaseException:
        try:
            if os.path.exists(target + ".bak"):
                os.remove(target + ".bak")
        except OSError as cleanup_error:
            print(f"WARNING: stray backup at {target}.bak: {cleanup_error}")
        raise

    # Past this point the backup is known complete, so a failed write is the
    # case restoring exists for.
    try:
        write(target, text.replace(find, replace, 1))
    except BaseException:
        # Best-effort, and it must not replace the exception that explains
        # the failure: a restore blocked by a read-only target would
        # otherwise report the wrong cause.
        try:
            restore(target)
        except OSError as restore_error:
            print(f"WARNING: could not restore {target}: {restore_error}")
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
