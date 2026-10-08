# T-0103 direction - T-0075 round-6 follow-up

status: new
filed: 2026-09-28 by crew [606220]. The owner accepted T-0075 review round 6 with "Accept, follow-up" and chose "Disable at land" for the pylint R1732 failure. T-0075 merged as PR #258 (e878cc31, crew 1.0.59).

## Accepted findings to fix (round 6, verbatim summaries)

1. BLOCK: two round-5 checks have no sabotage entry - `_content_problem`'s object-at-a-leaf branch
   (`plugin/crew/hooks/scripts/crew_config.py`, the `if shape == "leaf" and isinstance(value, dict):`
   line) and `value_allowed`'s `if shape == "under"` branch. The lane re-ran both mutations and the
   tests go RED (`test_a_pre_existing_object_at_a_leaf_is_named_not_tolerated[repo]`,
   `test_a_path_through_a_leaf_is_refused[machine-pm.authority.a]`), so what is missing is the two
   sabotage entries in `plugin/crew/tests/sabotage_config.py`.
2. FIX: `crew_config_menu.apply_delete`'s catch-all `except OSError` prints "left in place" and exits 2
   even when the file was already moved to `.bak-<UTC>` (move-back failing with EPERM/ENOSPC, or
   `_regular_bytes` failing on the moved file), and reports a machine_lock failure as "could not be
   moved to a backup". Split the handler so a failure after the move names the backup path.
3. From the landing: `plugin/crew/tests/test_config_menu.py` carries a file-level
   `# pylint: disable=consider-using-with` (89 inline `open()` calls, ruff SIM115 too). Rewrite them as
   `with` blocks and remove the disable.
4. From the landing: `crew_config_files.os_error_text` (Windows path text in OS-error refusals,
   1.0.57) has no sabotage entry; one that restores `{exc}` at a site goes RED on Windows only - record
   it as Windows-evidenced (a second, Windows machine can run it).
5. The round-6 NITs (5) are in the round-6 out.txt under .work/review/ for T-0075; triage them in the spec.

## Evidence

- T-0075 round 6 ledger: "round 6 FINDINGS accepted by the owner at 2026-09-28T19:42:38+00:00", bundle 9690e1ff7bc2.
- PR #258 body lists the accepted findings.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322). The owner was not available; where a question came up the recommended option was taken and is listed in spec.md under "Open questions for the owner".

Still true (nothing merged since PR #258 touched these; `git log origin/main --grep=T-0103` is empty, and the last commits to the three files are the T-0075 landing commits `93da92af`, `a98ce3f5`, `b044f1d7`, `b6e6e697`):
1. No sabotage entry removes `_content_problem`'s object-at-a-leaf branch (plugin/crew/hooks/scripts/crew_config.py:2827) or `value_allowed`'s `shape == "under"` branch (:2788). The existing entries at plugin/crew/tests/sabotage_config.py:588-603 mutate `_shape`'s `return "under"`, `value_allowed`'s leaf branch and `_content_problem`'s `under` branch.
2. `apply_delete`'s catch-all `except OSError` (plugin/crew/hooks/scripts/crew_config_menu.py:906-910) still prints "could not be moved to a backup ... left in place" and returns 2 for every OS error: a lock failure before any move, and a failure after the file has moved (`_fsync_dir` or `_regular_bytes` inside `move_aside`, or the move-back).
3. plugin/crew/tests/test_config_menu.py:11 still carries `# pylint: disable=consider-using-with`. The count of inline `open()` calls has drifted from 89; re-measure with `grep -c "open(" ` minus the `with` lines rather than trusting a number.
4. `os_error_text` (plugin/crew/hooks/scripts/crew_config_files.py:82) has three call sites (crew_config.py:2969, :3184, crew_config_menu.py:908) and no sabotage entry that puts `{exc}` back, and no direct unit test.
5. Round-6 NITs, triaged:
   - `_content_problem` tolerates a block held as a scalar: **declined** (recommended). Its docstring records the judgement that a refusal of a write is not a refusal of content, and the value is discarded on read. Listed as an open question.
   - `widening_note` for a repo `null` on a ratcheted key describes `normalise(None)`, not the value in force (crew_config.py:3189-3193): **kept**, fixed in this ticket after a reproducing test.
   - codemap `98 mutations` (`.crew/codemap/crew.md:502`; the tuple holds more now): **kept**, fixed in L-0682 where the count changes anyway.
   - `.crew/codemap/INDEX.md` orphaned fragment and the 1.0.55 CHANGELOG wording: **dropped**. The code map was re-derived since (anchor `42effe14`) and the cited lines no longer hold that text; a historical CHANGELOG entry is not rewritten.

What changed since the direction was filed:
- T-0087 merged (crew 1.0.76): a change to `plugin/crew/tests/sabotage*.py` is a tooling PR and lands alone (`HARNESS`, scripts/check-tooling-pr.py:58-87). Items 1 and 4 are sabotage entries; item 2 is production code outside the harness. They cannot share a PR.
- `sabotage.py` has no per-platform skip: an entry that stays green on Linux fails the suite (`STILL GREEN`, plugin/crew/tests/sabotage.py:3377). A "Windows-evidenced" entry therefore cannot sit in the tuple.

Options for item 4:
1. **Recommended, taken:** make it red on every platform. A test raises an `OSError` whose filename is a backslash path and asserts the refusal names it as written. `str(exc)` repr-quotes the filename and doubles the backslashes on any OS, so restoring `{exc}` fails the test on Linux too. The entry then sits in the tuple like any other.
2. Record it outside the tuple as Windows-evidenced, with a run on the Windows box as proof. Needs a second machine for every re-check and nothing in CI holds it.

Recommended split (standing rule: feature PR, then tooling PR):
- T-0103 (this ticket): the `apply_delete` fix, the `widening_note` fix, the `with`-block rewrite of test_config_menu.py, docs. No harness path.
- L-0682: tooling-only. Sabotage entries for items 1 and 4 and for this ticket's two fixes, the tests those entries name, the codemap count.
