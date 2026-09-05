"""Sabotage test: reintroduce each bug and confirm the suite goes red.

Run it directly: `python3 plugin/crew/tests/sabotage.py`. For each mutation it
patches one file, runs the test that should catch the change, and restores the
file whether or not the run succeeded.

A test that stays green with the behaviour deleted is not coverage. Three of
the tests in this directory did exactly that until a review named them, so the
claim "this is tested" is checked here rather than asserted.

A mutation whose anchor no longer matches is a FAILURE, not a skip: the anchor
drifting is how this suite would quietly stop testing anything.

Which is why a mutation whose CODE is deliberately deleted must be deleted
here too, with the reason written down -- never re-anchored onto whatever line
is nearest. Five went when the dispatch record stopped being a single shared
file: they proved things about a lock, a retry loop and a self-verifying write
that an append-only directory cannot get wrong, and a suite still listing them
would have read as concurrency coverage while testing nothing.
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
CONFIG = os.path.join(CREW, "hooks", "scripts", "crew_config.py")

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
        '        fam = family(entry.get("provider"), entry.get("model"))',
        "        fam = None",
        ("tests/test_provider_table.py::"
         "test_model_churn_collapses_to_one_entry_per_family"),
    ),
    (
        # Round 3, Critical. Every dispatch writing the same name is the old
        # shared-file design wearing a directory: writers overwrite each
        # other and the lost one may be the family that wrote the diff.
        "every dispatch writes the same entry file",
        STATE,
        '    base = os.path.join(directory, f"{kind}-{stamp}-'
        '{uuid.uuid4().hex[:12]}")',
        '    base = os.path.join(directory, f"{kind}-entry")',
        ("tests/test_provider_table.py::"
         "test_three_concurrent_dispatches_all_survive"),
    ),
    (
        # Round 3, Critical. One malformed file must cost one entry. Failing
        # the whole read is the single-file design's worst property -- the
        # guard falls back to the config and looks like it checked.
        "one malformed entry file discards the whole directory",
        STATE,
        "        except ValueError:\n            continue\n"
        "        if not isinstance(entry, dict) or not entry.get(\"kind\"):",
        "        except ValueError:\n            return []\n"
        "        if not isinstance(entry, dict) or not entry.get(\"kind\"):",
        ("tests/test_provider_table.py::"
         "test_a_malformed_entry_costs_one_entry_and_not_the_record"),
    ),
    (
        # Round 3. A wall-clock value inside the legacy file must not be able
        # to outrank the store, or a stepped clock evicts the dispatch that
        # just happened -- the write-time hazard, relocated to read time.
        "the legacy file can outrank the store",
        STATE,
        '    return (0 if entry.get("adopted") else 1, key)',
        "    return (0, key)",
        ("tests/test_provider_table.py::"
         "test_a_backward_clock_does_not_evict_the_dispatch_that_just"
         "_happened"),
    ),
    (
        # Round 3. A repo upgraded mid-branch has its only record in the slot
        # about to be overwritten. Losing it clears the family that wrote the
        # branch to review its own diff.
        "a pre-store record is overwritten instead of adopted",
        STATE,
        "    return _append_dispatch(root, kind, dict(slot, adopted=True))",
        "    return True",
        ("tests/test_provider_table.py::"
         "test_a_dispatch_recorded_before_the_store_existed_is_not_lost"),
    ),
    (
        # Round 3, Critical. An empty author set labelled as proven
        # provenance -- an unknown collapsing into the safe-looking value,
        # wearing the label of a check that happened.
        "an unknown author family is reported as proven",
        STATE,
        '            return frozenset(), "unknown"',
        '            return frozenset(), "dispatch"',
        ("tests/test_provider_table.py::"
         "test_a_proven_dispatch_with_an_unknown_family_is_not_called"
         "_proven"),
    ),
    (
        # And the teeth: `eligible` means only "not struck", so with nothing
        # struck every candidate certified a review it had no basis for.
        "an unknown author still certifies an independent review",
        CONFIG,
        '        "independentReviewer": (author_source != "unknown"\n'
        '                                and any(c["eligible"] '
        'for c in candidates)),',
        '        "independentReviewer": any(c["eligible"] for c in '
        'candidates),',
        ("tests/test_provider_table.py::"
         "test_an_unknown_author_cannot_certify_an_independent_review"),
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
        # Round 4, Critical. An entry naming no author cannot BE the
        # author, so it must not displace one that can.
        "an entry with no provider still spends a slot",
        STATE,
        '        if not entry.get("provider"):\n            continue',
        '        if False:\n            continue',
        ("tests/test_provider_table.py::"
         "test_an_entry_with_no_provider_cannot_evict_one_that_has_one"),
    ),
    (
        # Round 5, Critical. ANY cap on families within a branch evicts the
        # one that wrote the diff, given enough later dispatches.
        "families within a branch are capped",
        STATE,
        "        seen.add(key)\n        kept.setdefault(branch, [])"
        ".append((rank, entry))",
        "        seen.add(key)\n"
        "        if len(kept.setdefault(branch, [])) < "
        "DISPATCH_HISTORY_MAX:\n"
        "            kept[branch].append((rank, entry))",
        ("tests/test_provider_table.py::"
         "test_no_number_of_later_families_evicts_the_one_that_wrote_the"
         "_diff"),
    ),
    (
        # Round 5. The cap has to fall on something and it must not fall on
        # the checkout the reviewer is standing on.
        "the branch cap can evict the branch under review",
        STATE,
        "        if here is not None and here in kept and here not in live:\n"
        "            live = live[:DISPATCH_BRANCHES_MAX - 1] + [here]",
        "        live = live",
        ("tests/test_provider_table.py::"
         "test_the_branch_cap_never_evicts_the_branch_under_review"),
    ),
    (
        # Round 5, Medium. `read_dispatch` runs at session start, so an
        # unbounded live set is unbounded startup cost.
        "the branch cap does not bound the store",
        STATE,
        "        live = ranked[:DISPATCH_BRANCHES_MAX]",
        "        live = ranked",
        ("tests/test_provider_table.py::"
         "test_the_branch_cap_bounds_the_store"),
    ),
    (
        # Round 4, Critical. A hygiene cap that can delete the record
        # under review is the cap deciding which family is remembered.
        "pruning ignores what the reader still keeps",
        STATE,
        "        if name in protected:\n            continue",
        "        if False:\n            continue",
        ("tests/test_provider_table.py::"
         "test_pruning_never_removes_an_entry_the_reader_still_keeps"),
    ),
    (
        # Round 4, Critical. Overwriting the slot before its contents are
        # in the store makes the retry read from a record that is gone.
        "the slot is overwritten whether or not the adoption landed",
        STATE,
        "    if _adopt_slot(root, kind):\n"
        "        _write_slot(root, kind, entry)",
        "    _adopt_slot(root, kind)\n"
        "    _write_slot(root, kind, entry)",
        ("tests/test_provider_table.py::"
         "test_a_failed_adoption_is_retried_on_the_next_dispatch"),
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
