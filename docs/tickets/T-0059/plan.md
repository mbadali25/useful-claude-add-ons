# T-0059 plan            spec: .work/tickets/T-0059/spec.md

Owner approves (risk: high), or T-0010's policy path once it lands. Preconditions: T-0011, T-0037 and T-0052 are merged. Re-read every branch-only and spec-only anchor in the spec on main before step 1, and stop if `ship`, `merge_argv`, the status vocabulary or `crew_split` landed with a different contract. Crew version: one patch past main at merge. Merge commit (D-028).

Split from T-0052 on 2026-09-26 under the owner's standing authorization. This is group C of `.work/tickets/T-0052/plan.pre-split.md`: steps 6-8, the slice constants from step 1, and group C's share of steps 9-10. A plan with more than 8 steps here is itself a candidate for `## PR slices` once step 1 lands.

### Step 1: the `## PR slices` plan section
Files: plugin/crew/hooks/scripts/crew_split.py, plugin/crew/hooks/scripts/crew_ticket.py, plugin/crew/commands/plan.md, plugin/crew/skills/crew-plan/SKILL.md, plugin/crew/tests/test_crew_split.py, plugin/crew/tests/test_crew_ticket.py
Test: python3 -m pytest plugin/crew/tests/test_crew_split.py plugin/crew/tests/test_crew_ticket.py plugin/crew/tests/test_approval_digest.py -q
Risk: med. `crew_ticket.validate` gates every plan, so a parser bug here breaks every ticket, sliced or not.
- [ ] constants in `crew_split.py`, each with its evidence in a comment: `SLICES_MIN, SLICES_MAX = 2, 5` (the same bounds as `CHILDREN_MIN`/`CHILDREN_MAX`, and the ledger evidence in the spec)
- [ ] `parse_slices(plan_text)` returns `(slices, problems)`. A slice is `{n, name, steps, base}`, read from `## PR slices` -> `### Slice N: <name>`, `Steps: <comma list>`, `Base: main|slice <k>`. Problems: fewer than `SLICES_MIN` or more than `SLICES_MAX`; a step in two slices or in none; a slice's steps not one contiguous run, or runs out of order; `Base: slice k` with k not earlier; `Base: main` when the slice's steps' Files (from `crew_ticket.parse_plan` per step) intersect any earlier slice's Files. No section returns `([], [])`
- [ ] `crew_ticket.validate` (`crew_ticket.py:455-495`) appends `parse_slices`' problems, prefixed `PR slices:`. The import is lazy and local, so the PreToolUse guard does not import `crew_split` on every Write
- [ ] `plan.md` step 4 and crew-plan SKILL.md "Task structure": document the section, when to use it (the rulebook said `slices`, or the planner judges a cohesive ticket too large for one review), the base rule, and that each slice runs its own implement/review/done/ship with its own review budget
- [ ] tests: `test_no_slices_section_valid`, `test_slices_partition_ok`, `test_step_in_two_slices_refused`, `test_step_in_no_slice_refused`, `test_non_contiguous_slice_refused`, `test_base_main_with_shared_files_refused`, `test_base_later_slice_refused`, `test_one_slice_refused`, `test_validate_reports_slice_problems` (in `test_crew_ticket.py`); `test_approval_digest.py` stays green

### Step 2: slices run in order - state, per-slice budget, implement and done
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/hooks/scripts/review_ledger.py, plugin/crew/commands/implement.md, plugin/crew/commands/done.md, plugin/crew/tests/test_crew_autopilot_slices.py, plugin/crew/tests/test_review_ledger.py
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_slices.py plugin/crew/tests/test_review_ledger.py -q
Risk: high. A slice counted against the previous slice's rounds is refused review, and one that closes the ticket early leaves the later slices unbuilt.
- [ ] `review_ledger.open_slice(root, ticket, n)` under `_mutate`'s lock: refuses unless the current state is `ACCEPTED`, and n is one past the last `slices` row (or 2 with none). It appends `{"slice": n, "after_round": len(rounds)}` to `slices`, clears `receipt`, and sets `state` to None. `_spent` (`review_ledger.py:196-200`) counts from the larger of the latest successor's and the latest slice's `after_round`. CLI `--open-slice <n>`
- [ ] `<common>/crew/tickets/<id>/slices.json` (`{"current": n, "shipped": [{"slice", "pr", "merge_sha"}]}`, temp + `os.replace`): `next_phase` on a plan with slices names `implement` with `slice <n>: steps a-b`. After slice n's ship result is recorded and more remain, it names `next-slice`, which runs `open_slice` and creates the branch per the base rule (step 3)
- [ ] `implement.md`: when `next` names a slice, implement only that slice's steps. `done.md:61`: when the plan has slices and this is not the last one, set the header to `in-progress`, not `done`, and say "slice n of m done", using T-0037's status vocabulary as merged
- [ ] tests: `test_open_slice_fresh_budget` (2 rounds spent, open_slice, reserve succeeds), `test_open_slice_refused_unless_accepted`, `test_open_slice_out_of_order_refused`, `test_spent_counts_from_latest_slice_or_successor`, `test_next_names_current_slice_steps`, `test_non_final_slice_done_keeps_ticket_open`, `test_final_slice_done_closes`

### Step 3: ship per slice
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_ship.py, plugin/crew/tests/test_crew_autopilot_slices.py
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_ship.py plugin/crew/tests/test_crew_autopilot_slices.py -q
Risk: high. A slice PR based on the wrong branch either carries an earlier slice's diff twice or fails to build.
- [ ] `slice_base(top, ticket, n, slices, shipped)`: `main` (the default branch from T-0011's `_default_branch`) when every earlier slice is merged, or when slice n's `Base:` is `main`. Otherwise the branch of the latest unmerged earlier slice named by its `Base:` (stacked). Slice n's branch is `<ticket branch>-s<n>` for n >= 2
- [ ] `ship` (T-0011, `crew_autopilot.py:473` on b5bffe4e): on a sliced ticket, `gh pr create --head <slice branch> --base <slice_base> --fill`, and the title prefixed `<id> slice <n>/<m>:`. Merge only through `merge_argv`. Record `{slice, pr, merge_sha}` in `slices.json`. Refuse to ship slice n while slice n-1 is neither merged nor, under `ship: pr`, opened
- [ ] tests (stubbed gh adapter, as T-0011's tests do): `test_first_slice_pr_against_default_branch`, `test_independent_slice_bases_on_default_branch`, `test_stacked_slice_bases_on_predecessor_branch`, `test_slice_n_refused_before_n_minus_1`, `test_slice_merge_uses_merge_argv`, `test_unsliced_ticket_ship_unchanged` (T-0011's existing tests stay green)

### Step 4: sabotage
Files: plugin/crew/tests/sabotage_split.py, plugin/crew/tests/test_crew_split.py
Test: python3 plugin/crew/tests/sabotage_split.py (every mutation red on its named test, tree restored byte-identical)
Risk: low. An anchor that drifts makes its mutation test nothing, so the anchor-presence test holds each one.
- [ ] append to `SPLIT_MUTATIONS`: `Base: main` overlap check removed (`test_base_main_with_shared_files_refused`); contiguity check removed (`test_non_contiguous_slice_refused`); predecessor-merged check removed (`test_slice_n_refused_before_n_minus_1`); `_spent` ignoring slice rows (`test_open_slice_fresh_budget`). `test_every_split_sabotage_anchor_is_present_exactly_once` covers all four
- [ ] run it and record every mutation, the earlier tickets' included, with its red test in the PR body. A mutation still green is a finding

### Step 5: verify map, docs, version
Files: .crew/verify.json, plugin/crew/README.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md
Test: python3 scripts/check-marketplace.py; python3 scripts/_test/self-claims.py; python3 -m pytest plugin/crew/tests/ -q (serially)
Risk: low. A missed version bump leaves every installed machine shipping one PR per ticket.
- [ ] `.crew/verify.json`: T-0052's `crew_split` rule gains the paths and run entries for `plugin/crew/tests/test_crew_autopilot_slices.py`, `plugin/crew/tests/test_crew_ticket.py` and `plugin/crew/tests/test_review_ledger.py`
- [ ] README: PR slices, the base rule and the per-slice review budget
- [ ] bump crew one patch past main at merge in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and PLUGINS.md's claim, with a CHANGELOG entry
- [ ] PR body: which dependency anchors moved; that `drift-detection.sh` was not run, unless it was
