# Cloud handoff: T-0103

**T-0075 round-6 follow-up, part 1: config delete names the backup when a failure follows the move; the `widening_note` fix; `test_config_menu.py` rewritten to `with` blocks**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent ticket, narrowed to the feature PR. Child: L-0682 (the sabotage entries, tooling PR).
- **INDEX status:** new (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Priority: med.
- **Branch:** `T-0103-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0103/direction.md`, `docs/tickets/T-0103/spec.md`
- **Size:** about 55 production lines (`crew_config_menu.py` about 40, `crew_config.py` about 15), plus a mechanical test-file rewrite. No harness path: this is a feature PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0075 | done (merged as PR #258) | The code this ticket corrects (`apply_delete`) and the review round whose findings it follows up. |
| T-0087 | merged | The tooling-PRs-land-alone rule that forces the sabotage entries into L-0682. |

Nothing open blocks this ticket. It blocks L-0682: that ticket's sabotage entries name tests and anchor lines this ticket adds.

Related, no order forced: L-0614 (direction) edits the same menu module's save path, not `apply_delete`. Whichever lands second merges main and re-checks its anchors.

Family order:

1. T-0103 (this ticket): the `apply_delete` fix, the `widening_note` fix, the `with`-block rewrite, docs.
2. L-0682: tooling-only; sabotage entries, their tests, the code map mutation count.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published (none existed). The implementing session writes the plan.
- In spec.md, `children/1/` and "child 1" mean L-0682.
- Nothing was run when the spec was written: no pytest, no sabotage. The `widening_note` finding (round-6 NIT 2) was read, not reproduced. Step 1 is the reproducing test; if it passes on main unchanged, keep the test as a pin, drop the production change, and say so in the PR body.
- Three sabotage anchor lines inside `apply_delete` must stay byte-identical, indentation included (listed in the spec's Exclusions). The fix adds no nesting around them. No edit to `sabotage_config.py` or `sabotage.py` here.
- Commit order: the mechanical `with` rewrite first, alone; it changes no assertion and no test name.
- The count of inline `open()` calls has drifted (89 at filing, 83 at `155fe6d8`); re-measure rather than trusting a number.
- direction.md holds two owner decisions from 2026-09-30 that still apply: catch up with main by merge, never rebase, force-push or squash; and the parallel-suite instructions. The heavy-run wrapper they name is a local tool of the original host; the cloud session uses its own equivalent.
- Whether `CONFIG.md` and the troubleshooting guide state the delete's exit codes: could not tell beyond a grep that found neither. They are in Touch; if nothing needs changing, the PR body says so.

## Open questions for the owner (recommended option taken)

1. Exit code for an OS error after the config file has moved: 1 (file not at its path, everything kept and named). Alternative: keep 2 and fix only the text.
2. Round-6 NIT 1 (`_content_problem` tolerates a block held as a scalar or `{}`): declined, per the function's own recorded judgement. Alternative: a new ticket that names it as pre-existing.
3. The `os_error_text` sabotage (done in L-0682): red on every platform through a backslash-filename test. Alternative: a Windows-evidenced record outside the tuple, as the direction first said. The test design was not run.
4. The `with`-block rewrite rides in this PR as its own first commit. Alternative: a separate test-only PR.
5. Round-6 NITs on `.crew/codemap/INDEX.md` and the 1.0.55 CHANGELOG wording were dropped: the cited lines no longer hold that text. Owner to confirm.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0103/` in the final PR unless the owner wants it kept.
