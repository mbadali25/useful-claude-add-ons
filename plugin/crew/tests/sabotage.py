"""Sabotage test: reintroduce each bug and confirm the suite goes red.

Run it directly: `python3 plugin/crew/tests/sabotage.py`. For each mutation it
patches one file, runs the test that should catch the change, and restores the
file whether or not the run succeeded.

A test that stays green with the behaviour deleted is not coverage. Three of
the tests in this directory did exactly that until a review named them, so the
claim "this is tested" is checked here rather than asserted.

A mutation whose anchor no longer matches is a FAILURE, not a skip: the anchor
drifting is how this suite would quietly stop testing anything.

It edits real source in place, so putting the file back is as load-bearing as
the mutation. `d362a2bd` shipped `crew_state.py` with a live mutation still in
it -- a killed run had skipped the `finally`, the next run copied the mutated
file over the good backup, and nothing compared the restored bytes to anything,
so the suite reported PASS over a corrupted tree. Four things prevent that now:
`main` refuses to start when a `.bak` is present, `install_exit_handlers`
restores on SIGTERM and on interpreter exit rather than on `finally` alone,
`apply_mutation` writes its backup under a second name and renames it into
place so a `.bak` is never partial, and every restore -- on the loop's path,
the signal path and the atexit path alike -- is verified against a sha256
taken before the first mutation. SIGKILL is still uncatchable; the startup
refusal is what covers it, on the next run.

Which is why a mutation whose CODE is deliberately deleted must be deleted
here too, with the reason written down -- never re-anchored onto whatever line
is nearest. Five went when the dispatch record stopped being a single shared
file: they proved things about a lock, a retry loop and a self-verifying write
that an append-only directory cannot get wrong, and a suite still listing them
would have read as concurrency coverage while testing nothing.
"""
import atexit
import hashlib
import io
import os
import shutil
import signal
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
CREW = os.path.join(ROOT, "plugin", "crew")
STATE = os.path.join(CREW, "hooks", "scripts", "crew_state.py")
# The endpoint ledger and the three shared readers left crew_state.py in
# 0.16.21. A mutation patches the file its anchor actually lives in --
# an anchor that no longer matches is a FAILURE here, not a skip, so a
# split that left these pointing at the old file would have been caught
# by this suite rather than by the absence of one.
ENDPOINTS = os.path.join(CREW, "hooks", "scripts", "crew_endpoints.py")
COMMON = os.path.join(CREW, "hooks", "scripts", "crew_common.py")
LADDER_DOC = os.path.join(CREW, "skills", "crew-scaling", "SKILL.md")
PLATFORM = os.path.join(CREW, "hooks", "scripts", "crew_platform.py")
CONFIG = os.path.join(CREW, "hooks", "scripts", "crew_config.py")
UPGRADE = os.path.join(
    CREW, "skills", "crew-graph", "scripts", "crew_upgrade.py")
PM_BRIEF = os.path.join(CREW, "hooks", "scripts", "pm_brief.py")

GUARD = '    if out["family"] is not None and out["family"] in authors:'
ROLE_PIN = '    decided = resolve_role(cfg, "dev", "developer")'
BLOCK_ONLY = (
    '    decided = {"family": family((dict_or_empty('
    'dict_or_empty(cfg).get("dev")).get("provider") or "claude"), None)}'
)

MUTATIONS = (
    (
        # The pre-0.18.0 default, restored. This is the mutation that matters
        # on this change, because restoring it breaks NOTHING visible: the key
        # still has no consumer, so no document comes out differently and no
        # other test notices. It only becomes a de-branding bug later, when the
        # wiring lands and every upgraded repo starts passing an explicit
        # `--brand neutral` over an installed pack. A defect whose damage is
        # deferred to a future commit is exactly the kind a suite forgets to
        # hold, so it is pinned here rather than left to the templates.
        "docs.theme default goes back to the string neutral",
        UPGRADE,
        '    "theme": None,\n    "reportTheme": None,',
        '    "theme": "neutral",\n    "reportTheme": None,',
        ("tests/test_upgrade.py::"
         "test_upgrade_config_adds_the_docs_and_bitbucket_blocks"),
    ),
    (
        # The migration silently does nothing. The template change alone is
        # NOT the fix: `_merged` lets a supplied value win, so an existing
        # config carrying "neutral" keeps it forever and only NEW repos get
        # null. Deleting the rewrite leaves every already-installed machine in
        # the broken state while a fresh clone looks correct -- the "exists
        # only on other people's machines" shape this repo keeps paying for.
        "the neutral -> null migration is dropped",
        UPGRADE,
        '    if (crew_state.dict_or_empty(cfg.get("docs")).get("theme")\n'
        '            == _DOCS_THEME_REWRITTEN_FROM):\n'
        '        notes["rewrittenKeys"].append("docs.theme")\n'
        '        out["docs"]["theme"] = None',
        '    pass',
        ("tests/test_upgrade.py::"
         "test_upgrade_rewrites_the_old_neutral_theme_default_to_null"),
    ),
    (
        # The rewrite stops being announced. The value still changes under the
        # user; only the sentence explaining it disappears. That is the worse
        # half of the two: a config that differs from what someone wrote, with
        # the upgrade report silent about which value moved and why it was
        # allowed to.
        "a rewritten theme is no longer reported",
        UPGRADE,
        '    if "docs.theme" in notes["rewrittenKeys"]:',
        '    if False:',
        ("tests/test_upgrade.py::"
         "test_the_report_explains_a_rewritten_theme_and_stays_quiet_otherwise"),
    ),
    (
        # The rewrite over-reaches and catches every theme, not just the old
        # default. This is the fix performing the exact bug it exists to
        # prevent: a user who deliberately set `solomon` gets silently
        # de-branded BY THE MIGRATION. Cheap to write by accident -- it is one
        # comparison loosened to a truthiness check.
        "the migration rewrites any theme, not only the old default",
        UPGRADE,
        '    if (crew_state.dict_or_empty(cfg.get("docs")).get("theme")\n'
        '            == _DOCS_THEME_REWRITTEN_FROM):',
        '    if crew_state.dict_or_empty(cfg.get("docs")).get("theme"):',
        ("tests/test_upgrade.py::"
         "test_upgrade_rewrites_only_the_exact_old_default"),
    ),
    (
        # The type guard goes. `docs: "oops"` is kept verbatim and reported,
        # so `cfg["docs"]` is a STRING here -- `.get` on it raises
        # AttributeError partway through `upgrade_config`, after run() has
        # already written the backup and begun the migration.
        #
        # This mutation replaced an earlier one that wrapped the same block
        # in `isinstance(out.get("docs"), dict)`. That wrapper could not be
        # driven red: `dict_or_empty` had already made it unreachable, so
        # sabotaging it left the suite GREEN and the vacuous result is what
        # exposed it as dead code. The guard that holds is this one, so this
        # is the line the suite mutates.
        "the wrong-typed docs block guard is removed",
        UPGRADE,
        '    if (crew_state.dict_or_empty(cfg.get("docs")).get("theme")',
        '    if (cfg.get("docs", {}).get("theme")',
        ("tests/test_upgrade.py::"
         "test_a_wrong_typed_docs_block_is_not_rewritten_and_is_reported"),
    ),
    (
        # The pre-0.17.0 form, restored. It is wrong in BOTH directions once a
        # third tier exists: act -> autonomous reads as no widening (the widest
        # grant crew offers, shipped unannounced), and autonomous -> act reads
        # as a widening when it is a narrowing. The matrix test is what makes
        # the second half visible -- a suite carrying only the two transitions
        # that existed at two tiers stays green with this bug restored, which
        # is precisely why the matrix is enumerated as data.
        "widening test compares authority by equality instead of rank",
        CONFIG,
        "                and crew_state.authority_rank(value)\n"
        "                > crew_state.authority_rank(\n"
        "                    None if before is _MISSING else before)",
        "                and crew_state.normalise_authority(value) == \"act\"\n"
        "                and crew_state.normalise_authority(\n"
        "                    None if before is _MISSING else before) != \"act\"",
        ("tests/test_crew_config.py::"
         "test_every_authority_transition_is_classified"),
    ),
    (
        # Codex's round-1 FIX on this branch, restored. The `!` line named a
        # hardcoded tier, so setting `autonomous` warned about `act` and
        # described only what `act` grants -- omitting the one thing the tier
        # adds. Same bug class as the rank fix two entries up: the warning
        # under-describes the grant it is there to announce.
        "the widening warning names a hardcoded tier",
        CONFIG,
        '                granted = crew_state.normalise_authority('
        'change["after"])\n'
        '                print(f"  ! pm.authority widens to `{granted}`: "\n'
        '                      + _WIDENING_NOTES[granted])',
        '                print("  ! pm.authority widens to `act`: the PM will '
        'dispatch "\n'
        '                      "roles itself and report after.")',
        ("tests/test_crew_config.py::"
         "test_the_widening_warning_names_the_tier_it_grants"),
    ),
    (
        # A capability gate that names a rung instead of a floor. Restoring it
        # makes `autonomous` -- the WIDER tier -- unable to act at all, which
        # presents as "the new tier does nothing" rather than as a guard bug.
        "can_act names a rung instead of a floor",
        STATE,
        '    return authority_rank(pm.get("authority")) >= authority_rank("act")',
        '    return normalise_authority(pm.get("authority")) == "act"',
        "tests/test_pm_brief.py::test_autonomous_can_act_too",
    ),
    (
        # An unknown authority collapsing UPWARD is the repo's named recurring
        # bug class, in the one field where it grants capability. `index` on a
        # raw value would raise, so the mutation returns the top rank instead:
        # the shape a "be permissive on bad input" fix would actually take.
        "an unreadable authority ranks highest instead of lowest",
        STATE,
        "    return AUTHORITIES.index(normalise_authority(value))",
        "    return (AUTHORITIES.index(value) if value in AUTHORITIES\n"
        "            else len(AUTHORITIES) - 1)",
        "tests/test_pm_brief.py::test_authority_rank_is_ordered_and_fails_closed",
    ),
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
        "        except ValueError:\n            _note_lost(lost, name)\n"
        "            continue\n"
        "        if not isinstance(entry, dict) or not entry.get(\"kind\"):",
        "        except ValueError:\n            _note_lost(lost, name)\n"
        "            return []\n"
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
        #
        # Same anchor as round 7's below, on purpose. Round 3's `if not
        # known` was subsumed by `unnamed` rather than deleted, so one line
        # now carries both guarantees -- and turning it off has to be caught
        # by the empty case AND the mixed one. An entry running only one of
        # them would leave the other's claim unchecked.
        "an unknown author family is reported as proven",
        STATE,
        "        unnamed = None in recorded_families",
        "        unnamed = False",
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
        '        if not entry.get("provider"):',
        "        if False:",
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
        # Round 7, Critical. Capturing the unnamed family AFTER the
        # discard is the same as not capturing it: the mixed set then
        # reads as proven provenance.
        "an unnamed family beside a named one still says proven",
        STATE,
        "        unnamed = None in recorded_families",
        "        unnamed = False",
        ("tests/test_provider_table.py::"
         "test_one_unnamed_family_makes_the_whole_provenance_unproven"),
    ),
    (
        # Round 7, Critical. A dispatch the store refused, reported as
        # one it took.
        "a lost entry write is reported as a recorded dispatch",
        STATE,
        '        record["unrecorded"] = True',
        '        record["unrecorded"] = False',
        ("tests/test_provider_table.py::"
         "test_a_dispatch_the_store_refused_is_not_silent"),
    ),
    (
        # Round 7, Critical. The CLI swallowing it is the other half:
        # the dispatch path is what the caller reads.
        "the dispatch CLI exits 0 on a store that refused the entry",
        STATE,
        '        if record.get("unrecorded"):',
        "        if False:",
        ("tests/test_provider_table.py::"
         "test_the_dispatch_cli_exits_non_zero_when_nothing_was_recorded"),
    ),
    (
        # Round 8, Critical. A record that would not parse, reported as
        # a record that was never there.
        "unreadable evidence reads as absent evidence",
        STATE,
        '        return known, ("unknown" if unnamed or unread '
        'else "dispatch")',
        '        return known, ("unknown" if unnamed else "dispatch")',
        ("tests/test_provider_table.py::test_a_later_dispatch_cannot_"
         "certify_over_an_unreadable_legacy_record"),
    ),
    (
        # And the half with no store entry at all: `config` asserts that
        # nothing was recorded, which an unopenable file cannot support.
        "an unopenable record still claims nothing was recorded",
        STATE,
        '            "unknown" if unread else "config")',
        '            "config")',
        ("tests/test_provider_table.py::test_a_malformed_dispatch_file_"
         "reads_as_unknown_not_as_no_dispatch"),
    ),
    (
        # The reader has to NOTICE. Silence here makes both of the
        # above unreachable while they still read as covered.
        "a skipped entry file is not reported as lost",
        STATE,
        "    if lost:",
        "    if False:",
        ("tests/test_provider_table.py::"
         "test_a_malformed_entry_costs_one_entry_and_not_the_record"),
    ),
    (
        # Round 8, edge. An unparseable slot that may be overwritten is
        # a signal the next dispatch erases.
        "an unreadable record may be overwritten",
        STATE,
        "        return False                    # unreadable; "
        "overwriting loses the",
        "        return True                     # unreadable; "
        "overwriting loses the",
        ("tests/test_provider_table.py::"
         "test_the_next_dispatch_does_not_erase_an_unreadable_record"),
    ),
    (
        # Round 8, edge. A repo-wide, permanent condition reported
        # without the file that causes it.
        "the unreadable report does not name its file",
        STATE,
        '        record["unreadable"] = sorted(set(lost))',
        '        record["unreadable"] = True',
        ("tests/test_provider_table.py::test_a_malformed_dispatch_file_"
         "reads_as_unknown_not_as_no_dispatch"),
    ),
    (
        # Round 9, High. A reader that fails closed over a file it
        # could not read is undone by a pruner that deletes it.
        "the pruner deletes the evidence that evidence was lost",
        STATE,
        "    protected.update(lost)",
        "    protected.update([])",
        ("tests/test_provider_table.py::test_the_pruner_does_not_delete_"
         "the_evidence_that_evidence_was_lost"),
    ),
    (
        # Round 10, High. Skipping a record that names no author is
        # right; skipping it in SILENCE lets the next dispatch on the
        # branch answer `dispatch` over a record nobody could read.
        "a record naming no author is dropped in silence",
        STATE,
        '            _note_lost(lost, entry.get("_file") or '
        'DISPATCH_PATH[-1])',
        "            pass",
        ("tests/test_provider_table.py::test_a_legacy_history_entry_"
         "naming_no_author_is_not_silently_dropped"),
    ),
    (
        # Round 11, High. A `.tmp` left by a crash between the write
        # and the rename is a dispatch that may have landed. The suffix
        # filter ran before the reader learned to distrust it.
        "an interrupted write is skipped without a word",
        STATE,
        '            _note_lost(lost, name)\n            continue'
        "\n        path = os.path.join(directory, name)",
        "            continue\n        path = os.path.join(directory, name)",
        ("tests/test_provider_table.py::test_an_interrupted_write_in_"
         "the_store_is_not_an_empty_directory"),
    ),
    (
        # Round 11, High. A filter upstream of the funnel empties the
        # pipe before the funnel can report anything.
        "a mangled legacy history member is filtered out in silence",
        STATE,
        "            else:\n                # A history whose members "
        "are not records is a mangled file,",
        "            elif False:\n                # A history whose "
        "members are not records is a mangled file,",
        ("tests/test_provider_table.py::test_a_mangled_legacy_history_"
         "member_is_not_silently_dropped"),
    ),
    (
        # Round 11, High, and a regression on round 10: the legacy slot
        # was the one record shape that never reached the funnel.
        "the legacy slot is filtered before it reaches the funnel",
        STATE,
        "        if isinstance(slot, dict):",
        # Reproduces the SILENCE, not just the filter: a provider-less dict
        # slot falls through with no report, exactly as it did before, while
        # a non-dict still reaches the `else` that reports it. Mutating the
        # condition alone was vacuous -- it rerouted the slot into the new
        # `else` branch, which reports it by another road.
        '        if isinstance(slot, dict) and not slot.get("provider"):\n'
        "            pass\n"
        "        elif isinstance(slot, dict):",
        ("tests/test_provider_table.py::test_a_legacy_slot_that_names_"
         "no_author_reaches_the_funnel"),
    ),
    (
        # The non-dict half: a key present holding nothing is a record
        # that was written and lost.
        "a slot holding nothing reads as a slot never written",
        STATE,
        "    if kind in record:",
        "    if record.get(kind) is not None:",
        ("tests/test_provider_table.py::test_a_legacy_slot_holding_"
         "nothing_is_a_record_that_was_lost"),
    ),
    (
        "bogus documented role",
        LADDER_DOC,
        "| 1 | + security",
        "| 1 | + ghost-reviewer, + security",
        "tests/test_role_ladder.py",
    ),
    # --- The endpoint ledger and endpointUnscanned (BLOCK 1, BLOCK 2, findings
    # 2-11 of this round). ---------------------------------------------------
    (
        # This repo SHIPS plugin/gizmoduck/ as source; that must never read
        # as installation on its own.
        "in-repo plugin/gizmoduck/ counts as installed",
        ENDPOINTS,
        '    scopes = []\n    if root:\n        scopes.append(os.path.join('
        'root, ".claude", "settings.local.json"))',
        '    if root and os.path.isdir(os.path.join(root, "plugin", '
        '"gizmoduck")):\n        return True\n    scopes = []\n    if root:'
        '\n        scopes.append(os.path.join(root, ".claude", '
        '"settings.local.json"))',
        ("tests/test_endpoints.py::"
         "test_in_repo_source_directory_is_not_installation"),
    ),
    (
        # `"false"` (a JSON string) is truthy in Python -- only a real
        # boolean may decide this.
        "a truthy non-bool value counts as installed",
        ENDPOINTS,
        '        if not isinstance(value, bool):\n            continue\n'
        '        return value\n    return False',
        '        if value:\n            return True\n    return False',
        "tests/test_endpoints.py::test_string_false_does_not_count_as_installed",
    ),
    (
        # Project scope must win over global; reordering the scope list
        # undoes that.
        "global scope is consulted before project scope",
        ENDPOINTS,
        '    scopes = []\n    if root:\n        scopes.append(os.path.join('
        'root, ".claude", "settings.local.json"))\n        scopes.append('
        'os.path.join(root, ".claude", "settings.json"))\n    home = '
        'os.path.expanduser("~")\n    scopes.append(os.path.join(home, '
        '".claude", "settings.local.json"))\n    scopes.append(os.path.join('
        'home, ".claude", "settings.json"))',
        '    scopes = []\n    home = os.path.expanduser("~")\n    scopes.'
        'append(os.path.join(home, ".claude", "settings.local.json"))\n'
        '    scopes.append(os.path.join(home, ".claude", "settings.json"))'
        '\n    if root:\n        scopes.append(os.path.join(root, '
        '".claude", "settings.local.json"))\n        scopes.append(os.path.'
        'join(root, ".claude", "settings.json"))',
        ("tests/test_endpoints.py::"
         "test_project_explicit_false_wins_over_global_true"),
    ),
    (
        # More than one manifest anywhere below root must flip _is_monorepo;
        # `hits > 0` fires on the FIRST one instead.
        "a single manifest counts as a monorepo",
        ENDPOINTS,
        "            if hits > 1:\n                return True",
        "            if hits > 0:\n                return True",
        ("tests/test_endpoints.py::"
         "test_single_go_mod_at_root_is_not_a_monorepo"),
    ),
    (
        # scan_artifact_path must reject an id it cannot safely use in a
        # path, not merely at mint time.
        "an unsafe id is not rejected at read time",
        ENDPOINTS,
        '    record_id = record.get("id")\n    if not _valid_endpoint_id('
        'record_id):\n        return None',
        '    record_id = record.get("id")',
        ("tests/test_endpoints.py::"
         "test_scan_artifact_path_rejects_a_traversal_id"),
    ),
    (
        # declare_endpoint must refuse an unsafe caller-supplied id, not
        # only scan_artifact_path reading one back later.
        "an unsafe id is not rejected at mint time",
        ENDPOINTS,
        '    if endpoint_id is not None and not _valid_endpoint_id('
        'endpoint_id):\n        return {"error": f"refusing to declare an '
        'unsafe endpoint id: {endpoint_id!r}"}',
        "    pass",
        ("tests/test_endpoints.py::"
         "test_declare_endpoint_rejects_an_unsafe_endpoint_id"),
    ),
    (
        # A record that already landed a scan must keep ITS OWN frozen
        # path; recomputing ignores finding 6 entirely.
        "a frozen scan-artifact path is recomputed instead of kept",
        ENDPOINTS,
        '    frozen = record.get("artifactPath")\n    if isinstance(frozen, '
        'str):\n        frozen = frozen.replace("\\\\", "/")\n    if frozen '
        'is not None:\n        return _relative_safe(root, frozen, '
        'default)\n    return default',
        "    return default",
        ("tests/test_endpoints.py::"
         "test_frozen_artifact_path_survives_a_later_monorepo_flip"),
    ),
    (
        # BLOCK 5: a hand-edited artifactPath that escapes the repo must
        # fall back to the computed default, never be trusted as-is.
        "the traversal guard on a frozen artifact path is deleted",
        ENDPOINTS,
        "    return value if inside else default",
        "    return value",
        ("tests/test_endpoints.py::"
         "test_frozen_artifact_path_traversal_falls_back_to_the_computed_"
         "default"),
    ),
    (
        # BLOCK 12: a frozen path must resolve on ANY OS, not just the one
        # that froze it -- a legacy/hand-edited native-separator value must
        # be normalised before use.
        "a frozen artifact path is not normalised to POSIX on read",
        ENDPOINTS,
        '    if isinstance(frozen, str):\n        frozen = frozen.replace('
        '"\\\\", "/")',
        "    if False:\n        frozen = frozen",
        ("tests/test_endpoints.py::"
         "test_scan_artifact_path_normalises_backslashes_in_a_frozen_path"),
    ),
    (
        # `len(records) + 1` collides the moment any record is removed from
        # the committed, hand-editable ledger.
        "declared endpoint ids are minted from record count, not a sequence",
        ENDPOINTS,
        "        else:\n            doc[\"nextSeq\"] += 1\n            "
        "new_id = f\"ep-{doc['nextSeq']:04d}\"",
        '        else:\n            new_id = f"ep-{len(records) + 1:04d}"',
        ("tests/test_endpoints.py::"
         "test_declare_endpoint_ids_do_not_collide_after_a_deletion"),
    ),
    (
        # Write-then-rename is what makes a failed write leave the original
        # untouched; write-in-place already clobbers it before any failure
        # can be detected.
        "the ledger write is not atomic",
        ENDPOINTS,
        '        # newline="\\n": this file is JSON, not one of the `.sh` '
        'scripts the\n        # CRLF landmine names, but pinning it costs '
        'nothing and keeps every\n        # file this module writes '
        'consistent on Windows.\n        with open(tmp_path, "w", '
        'encoding="utf-8", newline="\\n") as handle:\n            json.dump'
        '(doc, handle, indent=2, sort_keys=True)\n            handle.write'
        '("\\n")\n            handle.flush()\n            os.fsync(handle.'
        'fileno())\n        os.replace(tmp_path, path)',
        '        with open(path, "w", encoding="utf-8", newline="\\n") as '
        'handle:\n            json.dump(doc, handle, indent=2, '
        'sort_keys=True)\n            handle.write("\\n")\n            '
        'handle.flush()\n            os.fsync(handle.fileno())',
        ("tests/test_endpoints.py::"
         "test_write_endpoints_leaves_the_original_intact_if_replace_fails"),
    ),
    (
        # A gate that stops running still has to be REMOVABLE -- a mutation
        # that deletes the early return must be caught, not just trusted.
        "the gizmoduck gate is removed from read_endpoints",
        ENDPOINTS,
        '    if not gizmoduck_installed(root):\n        return {"installed"'
        ': False, "unscanned": []}',
        '    if False:\n        return {"installed": False, "unscanned": []}',
        ("tests/test_endpoints.py::"
         "test_trigger_does_not_fire_when_gizmoduck_absent"),
    ),
    (
        "closed records are still counted as unscanned",
        ENDPOINTS,
        '        if record.get("status") not in ("open", "candidate"):\n'
        '            continue',
        '        if False:\n            continue',
        "tests/test_endpoints.py::test_closed_records_never_count_as_unscanned",
    ),
    (
        # Non-empty is necessary but not sufficient -- the text must
        # actually reference the endpoint it claims to cover.
        "a scan artifact for a different endpoint still confirms this one",
        ENDPOINTS,
        "    needle = _endpoint_needle(record.get(\"endpoint\"))\n    if "
        "needle is None:\n        return record.get(\"source\") != "
        '"declared"\n    return needle.lower() in text.lower()',
        "    return True",
        ("tests/test_endpoints.py::"
         "test_artifact_for_a_different_endpoint_does_not_confirm_this_one"),
    ),
    (
        # BLOCK 4: the scan marker itself -- without it, a hand-typed note
        # that merely mentions the URL passes for free.
        "the scan marker is not required to confirm a scan",
        ENDPOINTS,
        '    if not _SCAN_MARKER_RE.search(text):\n        return False',
        "    if False:\n        return False",
        "tests/test_endpoints.py::test_todo_note_does_not_confirm_a_scan",
    ),
    (
        # BLOCK 3: a declared record with no matchable needle must fail
        # CLOSED, not pass on the marker alone.
        "a declared record with no needle fails open instead of closed",
        ENDPOINTS,
        '    if needle is None:\n        return record.get("source") != '
        '"declared"',
        "    if needle is None:\n        return True",
        ("tests/test_endpoints.py::"
         "test_declared_bare_description_endpoint_fails_closed_with_no_"
         "needle"),
    ),
    (
        # BLOCK 3: the needle derivation must cover a bare hostname, not
        # only a URL or an absolute path.
        "the needle derivation does not cover a bare hostname",
        ENDPOINTS,
        '    if stripped.startswith("/") or _HOSTNAME_RE.match(stripped):\n'
        "        return stripped",
        '    if stripped.startswith("/"):\n        return stripped',
        "tests/test_endpoints.py::test_endpoint_needle_covers_a_bare_hostname",
    ),
    (
        # Finding 4's related bug: a bare "/" would match almost any
        # markdown file that contains a slash anywhere.
        "a bare slash is treated as a specific needle",
        ENDPOINTS,
        '    if stripped == "/":\n        return None',
        "    if False:\n        return None",
        "tests/test_endpoints.py::test_endpoint_needle_rejects_a_bare_slash",
    ),
    (
        # Attribution to the owning package is the whole point of the
        # mono-repo path rule; ignoring it silently falls back to root.
        "mono-repo scan artifacts ignore package attribution",
        ENDPOINTS,
        '        package_dir = _owning_package_dir(root, record.get('
        '"location"))',
        '        package_dir = ""',
        ("tests/test_endpoints.py::"
         "test_monorepo_path_rule_attributes_to_owning_package"),
    ),
    (
        # BLOCK 1: candidates are computed, never persisted as declared.
        "an ephemeral candidate is built as a declared record",
        ENDPOINTS,
        '        "id": f"cand-{digest}",\n        "endpoint": candidate.get'
        '("label") or "unidentified endpoint candidate",\n        "source":'
        ' "inferred", "status": "candidate",',
        '        "id": f"cand-{digest}",\n        "endpoint": candidate.get'
        '("label") or "unidentified endpoint candidate",\n        "source":'
        ' "declared", "status": "open",',
        ("tests/test_endpoints.py::"
         "test_read_endpoints_surfaces_an_inferred_hit_as_an_ephemeral_"
         "candidate"),
    ),
    (
        # declare_endpoint is the ONLY function allowed to write
        # source="declared", status="open" -- a status downgrade here is
        # the whole guarantee failing at its one writer.
        "declare_endpoint writes status=candidate instead of open",
        ENDPOINTS,
        '        record = {\n            "id": new_id, "endpoint": '
        'endpoint, "source": "declared",\n            "status": "open", '
        '"location": location, "ticket": ticket,\n            "createdAt": '
        'now,\n        }\n        records.append(record)',
        '        record = {\n            "id": new_id, "endpoint": '
        'endpoint, "source": "declared",\n            "status": '
        '"candidate", "location": location, "ticket": ticket,\n            '
        '"createdAt": now,\n        }\n        records.append(record)',
        ("tests/test_endpoints.py::"
         "test_declare_endpoint_writes_an_authoritative_open_record"),
    ),
    (
        # The dedup/id key for an ephemeral candidate must include location,
        # or two different diff lines sharing a signal collide onto one id
        # and one scan artifact silently discharges both.
        "an ephemeral candidate id ignores location",
        ENDPOINTS,
        "    digest = hashlib.sha1(\n        f\"{candidate.get('signal')}:"
        "{candidate.get('location')}\".encode(\"utf-8\")\n    ).hexdigest()"
        "[:8]",
        "    digest = hashlib.sha1(\n        f\"{candidate.get('signal')}\""
        ".encode(\"utf-8\")\n    ).hexdigest()[:8]",
        ("tests/test_endpoints.py::"
         "test_ephemeral_candidate_ids_differ_by_location"),
    ),
    (
        # A location already covered by a persisted record must not ALSO
        # surface as a fresh inferred candidate under a different id.
        "a promoted location still surfaces as a fresh candidate",
        ENDPOINTS,
        '        if candidate.get("location") in covered_locations:\n'
        '            continue',
        "        if False:\n            continue",
        ("tests/test_endpoints.py::"
         "test_a_promoted_location_no_longer_surfaces_as_a_fresh_candidate"),
    ),
    (
        # Finding 9: a comment describing the shape must not itself be read
        # as the shape.
        "inference does not skip comment lines",
        ENDPOINTS,
        '        stripped = added.strip()\n        if stripped.startswith('
        '_COMMENT_PREFIXES):\n            next_line += 1\n            '
        "continue",
        "        stripped = added.strip()",
        ("tests/test_endpoints.py::"
         "test_infer_endpoints_ignores_a_commented_out_example"),
    ),
    (
        "inference does not skip a match inside someone else's string",
        ENDPOINTS,
        'if match and not _inside_quoted_string(added, match.start()):',
        "if match:",
        ("tests/test_endpoints.py::test_infer_endpoints_ignores_a_match_"
         "inside_someone_elses_string"),
    ),
    (
        # crew's own source comments on the shapes it looks for; excluding
        # it is what stops the trigger crying wolf on every session opened
        # in this repo.
        "inference no longer excludes crew's own source",
        ENDPOINTS,
        "        if current_excluded:\n            next_line += 1\n"
        "            continue",
        "        if False:\n            next_line += 1\n            continue",
        ("tests/test_endpoints.py::"
         "test_infer_endpoints_excludes_crews_own_source_even_without_a_"
         "comment"),
    ),
    (
        "inference no longer gates openapi-path to spec-shaped files",
        ENDPOINTS,
        "            if extensions and current_ext not in extensions:\n"
        "                continue",
        "            if False:\n                continue",
        ("tests/test_endpoints.py::"
         "test_infer_endpoints_gates_openapi_path_to_spec_files"),
    ),
    (
        # Finding 10: `status`, not `source`, is authoritative -- a record
        # whose fields disagree must still render as a candidate.
        "the brief splits declared vs. candidate on source, not status",
        PM_BRIEF,
        'candidates = [hit for hit in hits if hit.get("status") == '
        '"candidate"]\n    declared = [hit for hit in hits if hit.get('
        '"status") != "candidate"]',
        'candidates = [hit for hit in hits if hit.get("source") != '
        '"declared"]\n    declared = [hit for hit in hits if hit.get('
        '"source") == "declared"]',
        ("tests/test_pm_brief.py::"
         "test_endpoint_finding_keys_on_status_not_source"),
    ),
    (
        # The hard requirement behind the whole feature: a candidate must
        # say, in its own text, that it is not confirmed.
        "the candidate finding text drops its NOT confirmed wording",
        PM_BRIEF,
        '"candidates are NOT confirmed endpoints until researched"',
        '""',
        ("tests/test_pm_brief.py::"
         "test_endpoint_finding_distinguishes_declared_from_candidate"),
    ),
    (
        # Finding 7: an unsafe-id hit must still carry location.
        "an unsafe-id unscanned hit drops location",
        ENDPOINTS,
        '            "status": record.get("status"),\n            '
        '"location": record.get("location"),\n            "path": None,',
        '            "status": record.get("status"),\n            '
        '"path": None,',
        "tests/test_endpoints.py::test_unsafe_id_hit_surfaces_location_too",
    ),
    (
        # Finding 7: an ordinary unscanned hit must carry location too.
        "an unscanned hit drops location",
        ENDPOINTS,
        '        "status": record.get("status"),\n        "location": '
        'record.get("location"),\n        "path": artifact,',
        '        "status": record.get("status"),\n        "path": '
        'artifact,',
        "tests/test_endpoints.py::test_unscanned_hit_surfaces_location",
    ),
    (
        # Finding 8: a confirmed-but-never-frozen scan must be surfaced,
        # not silently indistinguishable from a properly frozen one.
        "a confirmed but never-frozen scan is not surfaced",
        ENDPOINTS,
        '        elif (record.get("source") == "declared"\n              '
        'and record.get("artifactPath") is None):',
        "        elif False:",
        "tests/test_endpoints.py::test_unfrozen_confirmed_scan_is_surfaced",
    ),
    (
        # Finding 9: a closed record's location must ALSO stay excluded
        # from fresh inference, not just an open/candidate one.
        "a closed record's location re-surfaces as a fresh candidate",
        ENDPOINTS,
        'covered_locations = {record.get("location") for record in '
        'declared}',
        'covered_locations = {record.get("location") for record in '
        'declared if record.get("status") != "closed"}',
        ("tests/test_endpoints.py::"
         "test_a_closed_records_location_does_not_surface_as_a_fresh_"
         "candidate"),
    ),
    (
        # Finding 10: a vendored/generated tree with its own manifests must
        # not itself flip a repo into monorepo classification.
        "the monorepo skip-dirs list is emptied",
        ENDPOINTS,
        '_MONOREPO_SKIP_DIRS = frozenset({\n    "node_modules", '
        '"graphify-out", "vendor", ".venv", "venv", "dist", "build",\n})',
        "_MONOREPO_SKIP_DIRS = frozenset()",
        ("tests/test_endpoints.py::"
         "test_vendored_manifests_do_not_count_toward_monorepo_detection"),
    ),
    (
        # Finding 11: re-declaring an existing id must not silently reopen
        # a record a human deliberately closed.
        "re-declaring an existing id forces status back to open",
        ENDPOINTS,
        '                    record.update(endpoint=endpoint, '
        'source="declared",\n                                  '
        "location=location, ticket=ticket,\n                                  "
        "updatedAt=now)",
        '                    record.update(endpoint=endpoint, '
        'source="declared",\n                                  '
        'status="open", location=location, ticket=ticket,\n                                  '
        "updatedAt=now)",
        ("tests/test_endpoints.py::"
         "test_redeclare_does_not_reopen_a_closed_record"),
    ),
    (
        # Finding 12: record_scan_artifact must store POSIX separators
        # regardless of the OS this runs on.
        "the frozen artifact path is stored with native separators",
        ENDPOINTS,
        '                path = path.replace("\\\\", "/")',
        "                pass",
        ("tests/test_endpoints.py::"
         "test_record_scan_artifact_stores_posix_separators"),
    ),
    (
        # BLOCK 2: declare_endpoint must hold the ledger lock across its
        # whole read-modify-write cycle, or concurrent callers lose each
        # other's records with no error raised on either side.
        "declare_endpoint no longer holds the endpoints lock",
        ENDPOINTS,
        '    """\n    path = _endpoints_path(root) + ".lock"\n    deadline'
        " = time.time() + _ENDPOINTS_LOCK_TIMEOUT_SECONDS",
        '    """\n    return None\n    path = _endpoints_path(root) + '
        '".lock"\n    deadline = time.time() + _ENDPOINTS_LOCK_TIMEOUT_SECONDS',
        ("tests/test_endpoints.py::"
         "test_concurrent_threads_declaring_distinct_endpoints_all_survive"),
    ),
    (
        # Nit 15: `--declare-endpoint ""` is falsy and must not silently
        # fall through to printing full state and exiting 0.
        "an empty --declare-endpoint value is not rejected",
        STATE,
        "    if args.declare_endpoint is not None:\n        # `is not "
        'None`, not truthiness (nit 15): `--declare-endpoint ""`\n        '
        "# is falsy, and a bare-truthiness check let it fall through to "
        "the\n        # unconditional `print(json.dumps(collect(root), "
        "...))` below --\n        # printing full state and exiting 0 for "
        "a call that asked to\n        # declare an endpoint and got "
        "silently ignored, the same way a\n        # missing "
        "`--location` is not silently ignored.\n        if not "
        "args.declare_endpoint:\n            print(\"--declare-endpoint "
        'needs a non-empty value",\n                  file=sys.stderr)\n'
        "            return 2",
        "    if args.declare_endpoint:",
        "tests/test_endpoints.py::test_declare_endpoint_cli_rejects_an_empty_value",
    ),
    # --- The unguarded QA read path (the security hole). `validate_providers`
    # only ever ran on WRITE, and hand-editing `.crew/config.json` was always
    # the bypass -- `resolve_role` is what actually decides who reviews, so it
    # has to refuse an illegitimate provider on its own. Three mutations,
    # each reintroducing one half of the fix. -------------------------------
    (
        # `provider_problems` had zero callers before this round. Removing
        # the one added here is the reporter going back to being a reporter
        # nobody calls -- the read-side counterpart to `validate_providers`
        # existing in name only.
        "provider_problems is no longer called from the read path",
        CONFIG,
        "    provider_problems_found = provider_problems(cfg)",
        "    provider_problems_found = []",
        ("tests/test_provider_table.py::"
         "test_model_report_surfaces_provider_problems_from_a_hand_edited_"
         "config"),
    ),
    (
        # Without this, an unrecognised `qa` provider falls through to the
        # family guard alone -- which only fires on a NAMED match, so a
        # provider outside `QA_PROVIDERS` cleared review the moment its
        # family (real or absent) differed from the author's.
        "resolve_role no longer bars an unrecognised qa provider",
        STATE,
        '    if kind == "qa" and provider not in QA_PROVIDERS:',
        "    if False:",
        ("tests/test_provider_table.py::"
         "test_an_entirely_unknown_qa_provider_is_barred"),
    ),
    (
        # The narrower half: the bar survives for a NAMED family (a pinned
        # model) but a provider left unpinned -- `family() is None` -- slips
        # back through, which is the exact "unknown reads as no conflict"
        # bug the fix exists to close.
        "an unpinned provider's family of None skips the new guard too",
        STATE,
        '    if kind == "qa" and provider not in QA_PROVIDERS:',
        '    if kind == "qa" and provider not in QA_PROVIDERS '
        'and out["family"] is not None:',
        ("tests/test_provider_table.py::"
         "test_an_unpinned_localgpu_qa_reviewer_is_still_barred"),
    ),
)


# pytest's own exit codes (documented, not this file's invention): 0 all
# passed; 1 at least one test FAILED (a real assertion, or an error raised
# during a test); 2 execution interrupted; 3 an internal pytest error; 4 a
# usage error, which is what a collection failure -- an import blowing up
# on a SyntaxError, say -- actually produces; 5 no tests were collected at
# all. Only 1 is evidence that the TARGET TEST caught the mutation. Finding
# 13: the previous version of this treated every non-zero code the same,
# so a mutation that broke the whole file's syntax (crashing collection
# for every test in the suite, this one included) reported "RED (good)"
# indistinguishably from a mutation the target test actually caught -- and
# only 4 of the round's 18 new mutations had been hand-verified as the real
# thing rather than this.
_REAL_TEST_FAILURE = 1


def run_test(target):
    """Run one pytest target from the crew directory; return
    (exit_code, combined_output).

    PYTHONDONTWRITEBYTECODE=1: two mutations back to back can produce a
    source file of the SAME byte length (many of these are single-character
    swaps, e.g. "hits > 1" -> "hits > 0"), written within the same mtime
    tick. Python's default (mtime, size) pyc-invalidation check cannot tell
    those two versions apart, so the SECOND mutation's subprocess can load a
    stale bytecode cache left by the FIRST -- observed here as an
    intermittent "STILL GREEN" for a mutation that goes red on every
    isolated re-run. Never writing bytecode removes the cache entirely
    rather than trying to invalidate it correctly.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "-x"],
        cwd=CREW, capture_output=True, text=True, check=False, env=env)
    return completed.returncode, completed.stdout + completed.stderr


def read(target):
    with io.open(target, encoding="utf-8") as handle:
        return handle.read()


def write(target, text):
    with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def digest(target):
    """sha256 of the bytes on disk.

    Taken once per target before the first mutation and compared after every
    restore. Without it `restore` is assumed rather than checked, and a restore
    that silently did nothing is indistinguishable from one that worked -- the
    suite still prints PASS because `ok` tracks only whether each mutation went
    red. That is this repo's recurring shape: the signal and its absence look
    identical.
    """
    sha = hashlib.sha256()
    with open(target, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def stale_backups(targets):
    """Targets that already have a `.bak` beside them, before anything runs.

    A `.bak` present at startup means a previous run died between
    `apply_mutation` and `restore` -- so the file in the tree is MUTATED and
    the `.bak` is the only good copy. Running anyway would `shutil.copy` the
    mutated file over that backup and destroy the original permanently, which
    is the exact defect class this suite's own mutation table flags for the
    code under test.
    """
    return [t for t in sorted(set(targets)) if os.path.exists(t + ".bak")]


# Targets with a mutation applied RIGHT NOW. `finally` unwinds on an exception
# and on KeyboardInterrupt, but a SIGTERM from an external timeout -- how this
# script is actually killed in practice -- terminates without unwinding, so
# neither the `finally` nor anything after it runs. This set plus the handlers
# below are what put the file back on those paths. SIGKILL and a hard process
# kill still cannot be caught by anything; `stale_backups` above is what covers
# that case on the NEXT run, which is why it refuses to start rather than
# repairing silently.
_LIVE = set()

# target -> sha256 of its bytes before the first mutation. Module state rather
# than a local in `main` because the signal and atexit paths restore too, and a
# restore nobody verified is the defect this whole section exists to close --
# verifying only on the path that happens to be convenient would leave the
# claim "every restore is verified" true of one path and false of three.
_PRISTINE = {}


def _verify(target):
    """Print and return False when `target` is not what it was. Never raises.

    Called from signal and atexit context, where an exception would replace
    the reason the process is exiting with a traceback about the cleanup.
    """
    expected = _PRISTINE.get(target)
    if expected is None:
        return True  # Nothing was recorded for it, so there is nothing to claim.
    try:
        found = digest(target)
    except OSError as err:
        print(f"WARNING: could not verify {target}: {err}")
        return False
    if found != expected:
        print(f"RESTORE FAILED -- source left modified\n  {target}\n"
              f"  expected {expected}\n  found    {found}")
        return False
    return True


def _restore_all(*_args):
    """Restore every live target, verify each, and keep the ones that failed.

    `_LIVE` is NOT cleared wholesale. `restore` discards a target only after
    its move succeeded, so a failure leaves the name in the set and the atexit
    pass tries again -- which is what the comment in `restore` promises. An
    unconditional clear here would silently make that promise false, and the
    only symptom would be a file left mutated after a signal.
    """
    ok = True
    for target in sorted(_LIVE):
        try:
            restore(target)
        except OSError as err:
            print(f"WARNING: could not restore {target}: {err}")
            ok = False
            continue
        if not _verify(target):
            ok = False
    return ok


def _on_signal(signum, _frame):
    _restore_all()
    # SystemExit unwinds, so atexit still runs -- and every target restored
    # here is already out of `_LIVE`, which is why restoring twice is safe and
    # why one that FAILED here gets a second attempt there. Exiting 128+signum
    # is the shell convention for "killed by this signal" and keeps the
    # caller's timeout distinguishable from a suite failure.
    sys.exit(128 + signum)


def install_exit_handlers():
    """Restore on every exit path this process can observe.

    SIGBREAK exists only on Windows and SIGHUP only on POSIX, so both are
    looked up by name rather than referenced -- an unguarded `signal.SIGBREAK`
    is an AttributeError on Linux, which would take the whole suite down at
    import time on the platform CI runs.
    """
    atexit.register(_restore_all)
    for name in ("SIGTERM", "SIGINT", "SIGBREAK", "SIGHUP"):
        num = getattr(signal, name, None)
        if num is None:
            continue
        try:
            signal.signal(num, _on_signal)
        except (ValueError, OSError, RuntimeError):
            # Not the main thread, or a platform that refuses this signal.
            # A handler crew could not install is not a reason to skip the run.
            pass


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

    # Never copy over an existing backup. `main` refuses to start when one is
    # present, so reaching here means a restore failed mid-run; overwriting
    # would replace the last good copy with the already-mutated file.
    if os.path.exists(target + ".bak"):
        raise RuntimeError(
            f"{target}.bak already exists -- the previous mutation was not "
            f"restored. Refusing to overwrite the only good copy.")

    # The backup is built beside the target and RENAMED into place, so
    # `<target>.bak` never exists in a partial state. That matters because the
    # startup guard treats any `.bak` it finds as the only good copy and tells
    # the user to move it over the target: a half-written backup left by a
    # signal during a plain `shutil.copy` would make that instruction destroy
    # the intact source. `os.replace` is atomic on both platforms.
    #
    # The copy and the write still fail in ways that need opposite responses,
    # so they cannot share a handler. `shutil.copy` never modifies the SOURCE:
    # if it fails the original is intact and the partial copy is the damaged
    # one, so restoring from it is precisely what would corrupt the file this
    # is trying to protect. Discard the partial instead.
    partial = target + ".bak.partial"
    try:
        shutil.copy(target, partial)
        os.replace(partial, target + ".bak")
    except BaseException:
        try:
            if os.path.exists(partial):
                os.remove(partial)
        except OSError as cleanup_error:
            print(f"WARNING: stray partial backup at {partial}: {cleanup_error}")
        raise

    # Past this point the backup is known complete, so a failed write is the
    # case restoring exists for.
    # Registered BEFORE the write: a signal arriving mid-write must still find
    # this target in `_LIVE`, because the backup is already complete and the
    # file on disk is already the thing that needs putting back.
    _LIVE.add(target)
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
    # Discarded only after the move succeeded. A move that raised leaves the
    # target registered, so the atexit pass tries again rather than treating a
    # failed restore as a finished one.
    _LIVE.discard(target)


def main():
    """Run every mutation; return 0 only when all of them go red FOR REAL --
    a genuine assertion failure in the named test, not merely a non-zero
    exit code (finding 13)."""
    targets = [m[1] for m in MUTATIONS]

    # Before anything is touched. A stale `.bak` means the tree already holds
    # a mutation from a killed run, and the next `shutil.copy` would destroy
    # the only original. Refuse, name the files, and say how to recover.
    stale = stale_backups(targets)
    if stale:
        print("REFUSING TO RUN -- a previous run left a backup behind, so the "
              "file in the tree is the MUTATED one:")
        for target in stale:
            print(f"  {target}.bak")
        print("\nRecover by moving each backup over its target, which undoes "
              "the mutation:")
        for target in stale:
            print(f"  mv {target}.bak {target}")
        print("Then re-run. (`git checkout -- <target>` works too, and also "
              "discards any real edit you had in that file.)")
        return 2

    # A `.bak.partial` is a backup that was interrupted before it was renamed
    # into place. The target is intact in that case -- that is the point of
    # building it under a second name -- so it is litter, not evidence, and
    # removing it is safe where removing a `.bak` never is.
    for target in sorted(set(targets)):
        partial = target + ".bak.partial"
        if os.path.exists(partial):
            print(f"note: discarding an interrupted backup at {partial} "
                  f"(the target was never modified)")
            os.remove(partial)

    install_exit_handlers()
    # The answer key for every restore, on every path. Module state, because
    # the signal and atexit handlers verify too. Taken here, once, from files
    # known unmutated because of the guard above.
    _PRISTINE.clear()
    _PRISTINE.update({target: digest(target) for target in sorted(set(targets))})

    ok = True
    for label, target, find, replace, test in MUTATIONS:
        if not apply_mutation(target, find, replace):
            print(f"{'ANCHOR LOST -- suite is not testing this':40} {label}")
            ok = False
            continue
        try:
            # `output` is deliberately dropped: a mutation's job is to make
            # the suite go red, and the failure text is the suite's to report.
            code, _ = run_test(test)
        finally:
            restore(target)
            if not _verify(target):
                print(f"{'  ^ above, restoring for':40} {label}")
                ok = False
        if code == 0:
            print(f"{'STILL GREEN -- TEST IS VACUOUS':40} {label}")
            ok = False
        elif code != _REAL_TEST_FAILURE:
            # Went red, but not because the target test caught anything --
            # a collection/import error (SyntaxError, a bad import) crashed
            # the whole run before the test ever executed, or nothing
            # matching `test` was even collected. Reported separately, and
            # counted as a failure of THIS suite, because it proves nothing
            # about whether the mutation is real.
            print(f"{'RED BUT UNPROVEN -- exit ' + str(code) + ', not a test failure':40} "
                  f"{label}")
            ok = False
        else:
            print(f"{'RED (good)':40} {label}")

    print("\nSABOTAGE SUITE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
