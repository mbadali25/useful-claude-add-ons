"""The T-0085 development-standards mutations, appended to `sabotage.py`'s
MUTATIONS. Kept apart only because `sabotage.py` sits at `.pylintrc`'s
max-module-lines; the runner, its restore guarantees and its reporting are
all `sabotage.py`'s. Run that file, not this one.

Each entry weakens one refusal the required self-check depends on and names
the test that must go red: the review gate, the stamp's completeness check,
the reviewer's independence from the author's answers, the overlay's
could-not-tell reading, and both halves of the stamp's binding. Review round
1 added six: an overlay reusing a plugin id, an overlay supplementing a
standard no plugin set has, a plugin set claiming the overlay's set name, an
approval receipt that cannot be proven absent, a checklist built from unusable
file lists, and a self-check that changes while it is being stamped.

Review round 2 added nineteen. The scope base: a kept record that no longer
resolves (its commit gone, or no longer an ancestor of HEAD) refused again
instead of stamping against the merge-base fallback `/crew:review` bundles
with, and the refusal naming `--record` over an entry `--record` would keep.
The gate's completeness re-check of a record edited after stamping. A broken
effective set ignored by `init`, by `stamp`, and by the gate. Twelve further
refusal branches, each pinned by its own message: an approval lookup error read
as no receipt, a manifest that is not an object, an empty change stamped, a
malformed row, an unparseable stamp line, a second stamp line, a repeated
field, a repeated front matter key, Supplements in a plugin set, two plugin
files sharing a set, no GEN set, and a set file defining no standard. And
review.md's exit-2 paragraph losing the self-check refusal.

Review round 3 added nine. A start `--record` wrote as the merge-base guess
refused by the stamp, or used without "(fallback)"; an unreadable
`.crew/.scope-base` read as no record (and a record that does not parse
read as readable), so the refusal named the `--record` that would rewrite
it; proposals written from an INCOMPLETE out.txt; a `std:none` row and an
unreadable `std:` token each counted in the metric's baseline; the
self-check gate answering before a spent review budget; and GEN-07 citing only
two of the three change sets it names.

The land branch (owner decision 2026-09-30, "Preflight first") added one:
the self-check gate asked before main's #264 preflight (the order swapped).
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STANDARDS = os.path.join(CREW, "hooks", "scripts", "crew_standards.py")
REVIEW_RUN = os.path.join(CREW, "hooks", "scripts", "review_run.py")
REVIEW_MD = os.path.join(CREW, "commands", "review.md")
GENERIC = os.path.join(CREW, "skills", "crew-standards", "references", "generic.md")

STANDARDS_MUTATIONS = (
    (
        "the self-check gate finds no problem",
        STANDARDS,
        '                            f"({seal[\'standards\'][:8]} then, {found[\'digest\'][:8]} now)")\n'
        "    return problems, found[\"digest\"]\n",
        '                            f"({seal[\'standards\'][:8]} then, {found[\'digest\'][:8]} now)")\n'
        "    return [], found[\"digest\"]\n",
        ("tests/test_review_run_standards.py::"
         "test_run_refuses_before_reserve_without_selfcheck"),
    ),
    (
        "review_run skips the self-check gate",
        REVIEW_RUN,
        "        sys.stderr.write(f\"review-run: {note}\\n\")\n"
        "    if problems:\n",
        "        sys.stderr.write(f\"review-run: {note}\\n\")\n"
        "    if False:\n",
        ("tests/test_review_run_standards.py::"
         "test_run_refuses_before_reserve_without_selfcheck"),
    ),
    (
        "the stamp ignores a standard with no row",
        STANDARDS,
        "    for sid in wanted:\n"
        "        if sid not in seen:\n",
        "    for sid in wanted:\n"
        "        if False:\n",
        "tests/test_crew_standards.py::test_stamp_refuses_incomplete_record",
    ),
    (
        "the reviewer's checklist carries the author's answers",
        STANDARDS,
        "    out.append(summary_line(found))\n",
        "    out.append(summary_line(found))\n"
        "    out += [open(p, encoding=\"utf-8\").read() for p in __import__(\"glob\").glob(\n"
        "        os.path.join(root, \".work\", \"tickets\", \"*\", SELFCHECK_NAME))]\n",
        "tests/test_review_prompt.py::test_prompt_never_carries_selfcheck_answers",
    ),
    (
        "an overlay that cannot be read reads as absent",
        STANDARDS,
        "    except OSError as exc:\n"
        "        return None, f\"cannot be read: {exc.__class__.__name__}: {exc.strerror or exc}\"\n",
        "    except OSError as exc:\n"
        "        return None, \"absent\"\n",
        ("tests/test_crew_standards.py::"
         "test_overlay_that_is_a_directory_is_unknown_not_absent"),
    ),
    (
        "an overlay that is not UTF-8 reads as absent",
        STANDARDS,
        "        return None, [f\"{label}: not UTF-8 ({exc.reason} at byte {exc.start})\"], raw\n",
        "        return None, [\"absent\"], raw\n",
        "tests/test_crew_standards.py::test_bad_overlay_refuses",
    ),
    (
        "a stamp for another bundle passes",
        STANDARDS,
        "        if seal[\"bundle\"] != manifest.get(\"bundle_sha256\"):\n",
        "        if False:\n",
        "tests/test_review_run_standards.py::test_run_refuses_stale_selfcheck",
    ),
    (
        "a stamp for another standards set passes",
        STANDARDS,
        "        if seal[\"standards\"] != found[\"digest\"]:\n",
        "        if False:\n",
        ("tests/test_crew_standards.py::"
         "test_gate_refuses_a_stamp_for_another_standards_set"),
    ),
    (
        "an overlay may reuse a plugin id",
        STANDARDS,
        "                    overlay_problems.append(f\"{OVERLAY_REL}: {std['id']} reuses a "
        "plugin id\")\n",
        "                    pass\n",
        "tests/test_crew_standards.py::test_overlay_may_not_reuse_a_plugin_id",
    ),
    (
        "an overlay may supplement a standard no plugin set has",
        STANDARDS,
        "                if target not in plugin_ids:\n",
        "                if False:\n",
        "tests/test_crew_standards.py::test_bad_overlay_refuses",
    ),
    (
        "a plugin set may claim the overlay's set name",
        STANDARDS,
        "        if parsed[\"set\"] == OVERLAY_SET:\n",
        "        if False:\n",
        "tests/test_crew_standards.py::test_plugin_set_may_not_claim_the_overlay_set",
    ),
    (
        "an approval receipt that cannot be looked up reads as absent",
        STANDARDS,
        "        os.lstat(path)\n"
        "    except FileNotFoundError:\n",
        "        os.lstat(path)\n"
        "    except OSError:\n",
        ("tests/test_crew_standards.py::"
         "test_gate_applies_when_the_receipt_cannot_be_looked_up"),
    ),
    (
        "the checklist lists nothing when the file lists are unusable",
        STANDARDS,
        "    if unknown:\n"
        "        out.append(unknown)\n",
        "    if unknown:\n"
        "        return out + [unknown]\n",
        ("tests/test_crew_standards.py::"
         "test_checklist_lists_the_always_on_sets_when_file_lists_are_unusable"),
    ),
    (
        "the stamp writes a record that changed while it was stamped",
        STANDARDS,
        "    if now != raw:\n",
        "    if False:\n",
        ("tests/test_crew_standards.py::"
         "test_stamp_refuses_a_record_that_changes_while_stamping"),
    ),
    (
        "an unusable record refuses again",
        STANDARDS,
        "    elif source == \"merge-base\" and base and has_entry:\n",
        "    elif False:\n",
        ("tests/test_crew_standards.py::"
         "test_stamp_scope_fallback_when_the_record_is_unusable"),
    ),
    (
        "the refusal names --record over a kept entry",
        STANDARDS,
        "        if has_entry:\n",
        "        if False:\n",
        ("tests/test_crew_standards.py::"
         "test_stamp_refusal_never_names_a_record_that_would_be_kept"),
    ),
    (
        "the gate skips the completeness re-check",
        STANDARDS,
        "    if not read_problems or rows:\n",
        "    if False:\n",
        ("tests/test_review_run_standards.py::"
         "test_run_refuses_a_selfcheck_edited_after_stamping"),
    ),
    (
        "init ignores a broken set",
        STANDARDS,
        "    if found[\"problems\"]:\n"
        "        return 1, [\"the effective standards set could not be read:\"] + "
        "found[\"problems\"]\n",
        "",
        "tests/test_crew_standards.py::test_init_refuses_a_broken_effective_set",
    ),
    (
        "stamp ignores a broken set",
        STANDARDS,
        "        problems += found[\"problems\"] + record_problems(rows, found)\n",
        "        problems += record_problems(rows, found)\n",
        "tests/test_crew_standards.py::test_stamp_refuses_a_broken_effective_set",
    ),
    (
        "the gate ignores a broken set",
        STANDARDS,
        "    problems += found[\"problems\"]\n"
        "    rows, seal, read_problems = read_selfcheck(root, ticket)\n",
        "    rows, seal, read_problems = read_selfcheck(root, ticket)\n",
        "tests/test_review_run_standards.py::test_run_refuses_a_broken_effective_set",
    ),
    (
        'the approval lookup error reads as no receipt',
        STANDARDS,
        ("    except crew_ticket.TicketError as exc:\n"
         "        return True, f\"the approval receipt could not be looked up ({exc}); "
         "gating anyway\"\n"),
        ("    except crew_ticket.TicketError as exc:\n"
         "        return False, \"x\"\n"),
        'tests/test_crew_standards.py::test_refusal_branch_gate_applies_lookup_error',
    ),
    (
        'a manifest that is not an object is read anyway',
        STANDARDS,
        '    if not isinstance(manifest, dict):\n',
        '    if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_manifest_not_an_object',
    ),
    (
        'the stamp stamps an empty change',
        STANDARDS,
        '        if not manifest.get("bundle_sha256"):\n',
        '        if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_nothing_to_review',
    ),
    (
        'a malformed self-check row is skipped silently',
        STANDARDS,
        ("        if len(cells) < 3 or not _ID_RE.match(cells[0]):\n"
         "            problems.append("),
        ("        if len(cells) < 3 or not _ID_RE.match(cells[0]):\n"
         "            continue\n"
         "            problems.append("),
        'tests/test_crew_standards.py::test_refusal_branch_malformed_row',
    ),
    (
        'an unparseable stamp line is ignored',
        STANDARDS,
        ("            if not match:\n"
         "                problems.append(f\"line {number}: the stamp line does not parse\")\n"),
        ("            if not match:\n"
         "                pass\n"),
        'tests/test_crew_standards.py::test_refusal_branch_unparseable_stamp',
    ),
    (
        'a second stamp line is allowed',
        STANDARDS,
        '    if len(stamps) > 1:\n',
        '    if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_second_stamp',
    ),
    (
        'a set file may repeat a field',
        STANDARDS,
        '            if field in current[1]["fields"]:\n',
        '            if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_repeated_field',
    ),
    (
        'a set file may repeat a front matter key',
        STANDARDS,
        '        if key in meta:\n',
        '        if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_repeated_front_matter_key',
    ),
    (
        'a plugin set may carry Supplements',
        STANDARDS,
        '        if parsed["supplements"]:\n',
        '        if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_plugin_set_supplements',
    ),
    (
        'two plugin files may share a set',
        STANDARDS,
        '        if parsed["set"] in owners:\n',
        '        if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_duplicate_plugin_set',
    ),
    (
        'the plugin sets may lack GEN',
        STANDARDS,
        '    if "GEN" not in owners:\n',
        '    if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_no_gen_set',
    ),
    (
        'a set file may define no standard',
        STANDARDS,
        '    if not standards and not supplements:\n',
        '    if False:\n',
        'tests/test_crew_standards.py::test_refusal_branch_empty_set',
    ),
    (
        "review.md loses the self-check refusal",
        REVIEW_MD,
        ("cause. Exit 2 means nothing launched and no round was spent: not on PATH (walk\n"
         "to the next eligible provider), or `review-run: self-check: ...` - the standards\n"
         "self-check is missing or stale for this bundle (every provider): answer\n"
         "`.work/tickets/$TICKET/selfcheck.md`, run the `crew_standards.py stamp` it names, "
         "rebuild."),
        ("cause. Exit 2 means nothing launched (not on PATH) and no round was spent; walk\n"
         "to the next eligible provider."),
        "tests/test_lifecycle_commands.py::test_commands_name_the_standards_steps",
    ),
    (
        "a start recorded as a merge-base guess refuses the stamp",
        STANDARDS,
        "    if source == \"record-fallback\" and base:\n",
        "    if False:\n",
        "tests/test_crew_standards.py::test_stamp_marks_a_record_written_as_a_fallback",
    ),
    (
        "a start recorded as a merge-base guess is not marked",
        STANDARDS,
        "        note = why\n",
        "        note = None\n",
        "tests/test_crew_standards.py::test_stamp_marks_a_record_written_as_a_fallback",
    ),
    (
        "an unreadable scope record reads as no record",
        STANDARDS,
        "    if unreadable:\n",
        "    if False:\n",
        ("tests/test_crew_standards.py::"
         "test_stamp_refuses_an_unreadable_scope_record_without_naming_record"),
    ),
    (
        "a scope record that does not parse reads as readable",
        STANDARDS,
        "        return False, \"does not parse as a JSON object\"\n",
        "        return False, None\n",
        ("tests/test_crew_standards.py::"
         "test_stamp_refuses_an_unreadable_scope_record_without_naming_record"),
    ),
    (
        "proposals are written from an INCOMPLETE output",
        STANDARDS,
        "    if parsed[\"verdict\"] == review_verdict.INCOMPLETE:\n",
        "    if False:\n",
        ("tests/test_crew_standards.py::"
         "test_proposals_refuses_an_incomplete_output_and_writes_nothing"),
    ),
    (
        "a std:none row counts in the baseline",
        STANDARDS,
        "    if match.group(1) == \"none\":\n"
        "        return \"std_none\"\n",
        "    if match.group(1) == \"none\":\n"
        "        return \"before\"\n",
        ("tests/test_crew_standards.py::"
         "test_metric_keeps_a_row_without_a_digest_out_of_the_baseline"),
    ),
    (
        "an unreadable std: token counts in the baseline",
        STANDARDS,
        "    return \"std_unreadable\"\n",
        "    return \"before\"\n",
        ("tests/test_crew_standards.py::"
         "test_metric_keeps_a_row_without_a_digest_out_of_the_baseline"),
    ),
    (
        "the self-check gate answers before a spent budget",
        REVIEW_RUN,
        "    if not (ledger.get(\"state\") == review_ledger.NEEDS_REPLAN\n"
        "            or ledger.get(\"rounds_left\") == 0):\n",
        "    if True:\n",
        ("tests/test_review_run_standards.py::"
         "test_run_reports_a_spent_budget_before_the_selfcheck"),
    ),
    (
        "GEN-07 cites two of its three change sets",
        GENERIC,
        "- main(B1-B3) r3 @8b8a4028+dirty, FIX `plugin/crew/skills/crew-graph/",
        "- (B1-B3) r3 @8b8a4028+dirty, FIX `plugin/crew/skills/crew-graph/",
        ("tests/test_crew_standards.py::"
         "test_every_generic_standard_cites_three_of_its_change_sets"),
    ),
    (
        "the self-check gate runs before main's preflight",
        REVIEW_RUN,
        "    short = preflight(args)\n"
        "    if short is not None:\n"
        "        return short\n"
        "\n"
        "    # A spent budget",
        "    refused = standards_gate(args)\n"
        "    if refused is not None:\n"
        "        return refused\n"
        "    short = preflight(args)\n"
        "    if short is not None:\n"
        "        return short\n"
        "\n"
        "    # A spent budget",
        ("tests/test_review_run_standards.py::"
         "test_preflight_answers_before_the_selfcheck_is_asked_for"),
    ),
)
