# L-0540 direction - T-0094 tooling half: completion_audit.py and scope_guard.py admission of refresh artifacts

Status: seed (not yet approved). **Tooling-only: this change touches the review/gate harness, so it lands alone** (the owner's standing tooling-PR rule, `scripts/check-tooling-pr.py`). Split from T-0094 by the owner on 2026-09-30 ~11:35 CDT ("Reject + split + successor"). Cut from `main` only after T-0094 (the feature half) has merged - merge main, never rebase - with its own ledger, review budget and crew version bump.

## Intent

Wire `completion_audit.audit` (the Stop hook and `/crew:done` check 3) to `crew_refresh_check.artifact_verdicts`, which T-0094 ships: a changed refresh artifact of an approved ticket is admitted without Touch only on a `True` verdict, and a refused one is listed with its reason in brackets. Until this lands the audit admits the whole refresh-artifact dirs under approval (the path test since 1.0.36), while `done.md`, `implement.md`, the README and the daily-workflow guide already describe the narrower rule (T-0094 keeps them: `plugin/crew/commands/*.md` is outside the tooling rule's `ALONGSIDE`, so this ticket could not carry them).

## What is seeded (exact lane versions, not to be re-derived)

The four harness-half files as they stood on T-0094-build after its merge of origin/main `549cda24` (commit `44407f8e`, local branch `L-0540-seed` in a local worktree; not pushed), under `seed/`, plus the same as a patch against origin/main at that time:

- `harness-half.patch` - sha256 `8407a10e1fedc3b5f51fda1734788b55b4fe90d3a3cb0afd73c45283829c5ff9` (843 lines; `git diff origin/main 44407f8e -- <the four paths>`)
- `seed/plugin/crew/hooks/scripts/completion_audit.py` - `9027ca870bed575d157460a63deedeb93ac66c28f2e9c2424a82a4e473f89d0e` (`_verdicts`, `_default_artifacts`, `_outside_refresh_artifacts` after the approval gate, `_entry` printing the reason)
- `seed/plugin/crew/hooks/scripts/scope_guard.py` - `9e6726f1675911134eb6ad9ebb0937407b7e05f0a92f0acbe44d9d5c6e80dea4` (rule-6 docstring only: the guard admits the whole dirs, the audit judges shape)
- `seed/plugin/crew/tests/test_completion_audit_refresh_artifacts.py` - `975dd26c307d4b840ab3ca8e4ac99e6c3ce1e4cc848d65b88e324e9ede693e08` (must-block half unchanged, must-allow half on `refresh_fixtures.refreshed`, reasons, fail-closed cases)
- `seed/plugin/crew/tests/sabotage_refresh.py` - EDITED after the snapshot by the T-0094 lane (so its hash differs from the patch's copy): every T-0094 entry, the round-6 block (`# T-0094 review round 6`, 12 entries) appended, and six entries re-pointed to T-0094's final `crew_refresh_check.py` (`the graph is admitted with no code change`, `a git diff of INDEX.md that failed reads as rows only`, `a map whose presence lstat cannot prove reads as deleted`, `an INDEX.md mode change is admitted`, and the three `INDEX.md compared as decoded lines` via `_INDEX_LINES`/`_INDEX_DECODED`). All 109 of its `crew_refresh_check.py` entries were hand-run RED against T-0094's final code (log in `.work/tickets/T-0094/sabotage-run.md`, "Successor (round 6)"); its 15 `completion_audit.py`, 4 `scope_guard.py` and 1 `verify.json` entries were NOT run (their targets are this ticket's).

Use `seed/`, not the patch, for `sabotage_refresh.py`. For the other three the patch and `seed/` agree.

## Known adjustments this ticket must make (found by the T-0094 lane)

1. `test_an_unreadable_rule_fails_the_audit_as_could_not_tell` (seed test file, ~:213) asserts `.claude/rules/ghost.md [could not tell:` for a DANGLING SYMLINK rule. T-0094 review round 6 refuses any symlink before reading it, so the audit line is now `[a symlink, which no refresh writes]` (verdict False, still never admitted). Either assert the symlink reason, or make the rule unreadable as a regular file (T-0094's unit test now monkeypatches `crew_refresh_check._read_bytes`) and keep `[could not tell:`; the spec decides.
2. Re-check every seed entry's `find` against `main` at cut time (`test_sabotage_harness.py` proves uniqueness) and hand-run the AUDIT and GUARD entries RED.
3. `test_refresh_check.py::test_every_refresh_sabotage_anchor_is_present_exactly_once` will then cover the seed's entries; it passes on T-0094 with main's `sabotage_refresh.py`.
4. The README row for `completion_audit.py`, the README "What the guard judges" paragraph and `docs/guides/crew/src/daily-workflow-scope.md` each carry one interim sentence ("the audit applies it once L-0540 lands" / "until then admits the artifact dirs"). They are in `ALONGSIDE`: remove those sentences here, rebuild the guide, and re-anchor `.crew/codemap/crew.md`'s refresh-artifact bullet (it says `artifact_verdicts` has no caller in the hooks until L-0540, a JUDGEMENT line).
5. Related: L-0539 (check-tooling-pr.py letting a feature's own sabotage entries ride with the feature). If it lands first, the split rationale for `sabotage_refresh.py` changes, not this ticket's content.

## Confirmed split (T-0094 lane, 2026-09-30)

- Feature half on T-0094-build after the split commit `c974f997`: `python3 scripts/check-tooling-pr.py` -> `tooling-pr: no harness path changed`, exit 0.
- Harness half: a throwaway worktree off origin/main `549cda24` with `harness-half.patch` applied and committed -> `tooling-pr: OK - 3 harness path(s), nothing outside tooling`, exit 0. Its suites cannot pass there, because `completion_audit.py` calls `artifact_verdicts`, which reaches main only with T-0094: the runtime dependency runs harness -> feature, never the reverse, which is why T-0094 lands first.

## Acceptance (seed, for the spec)

- `completion_audit.audit` admits a refresh artifact of an approved ticket only on `artifact_verdicts`' `True`; a refused one is printed with its reason in brackets; a raise or unresolvable dirs fail closed with `[could not tell: ...]`.
- The seed's audit suite green on main after T-0094; every seed sabotage entry hand-run RED (all targets).
- The interim sentences in README and the guide removed; crew one past main.
- Lands alone: `check-tooling-pr.py` OK on its own branch.

## MUST-FIX before this ticket wires artifact_verdicts into the completion audit (owner 2026-09-30 ~12:50, "Accept + fix in L-0540")

T-0094 review round 8 (last; independent Codex gpt-5.6-sol at medium, bundle `1e1fcebe5cc7` at `79ef56c4`) came back FINDINGS with these two BLOCKs. The owner accepted the round (ledger receipt, 2026-09-30T18:30:22Z) and moved the fixes here. `artifact_verdicts` has no caller in the hooks until this ticket, so neither hole is reachable before it; both must be fixed, each with a must-block test that fails on T-0094's code and a sabotage entry hand-run RED, BEFORE `completion_audit.audit` calls it. Verbatim:

> BLOCK|plugin/crew/hooks/scripts/crew_refresh_check.py:795|An artifact deleted from the index but recreated as an untracked regular file is admitted from bytes Git will not store: the raw 100644→000000 record is deliberately ignored and an empty `ls-files -s` result is treated like a legitimate new rendered file, so the eventual commit deletes an artifact that received a True re-anchor/regeneration verdict.|On an anchored map run `git rm --cached .crew/codemap/app.md`, leave/rewrite the worktree file with a reachable forward anchor, then call `artifact_verdicts`; it returns True although `git ls-files -s` is empty and committing records the deletion.
>
> BLOCK|plugin/crew/hooks/scripts/crew_refresh_check.py:706|The no-`dir_fd` fallback used on Windows does not bind containment to the open: after the earlier realpath check, a parent can be swapped to a junction/symlink, and the subsequent path-based `open` and `lstat` both resolve through that same replacement, so their inode comparison succeeds and external admissible bytes are judged.|Force `os.supports_dir_fd` empty, start with a non-admissible `docs/diagrams/sub/flow.mmd`, swap `sub` to a link/junction containing an admissible copy after `_on_disk` returns from `realpath(path)` but before `_read_regular` calls `os.open`; `artifact_verdicts` reads the external file and returns True.
>

In short: `:795` - an artifact removed from the git index but left in the working tree gets True, although the commit records its deletion (the `100644 -> 000000` raw record is skipped and an empty `ls-files -s` reads like a new file); `:706` - where `os.open` takes no `dir_fd` (Windows), a directory swapped to a junction/symlink after `_on_disk`'s realpath check is still read, because the path-based open and lstat both follow the replacement.

## Direction check 2026-10-04

Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; defaults are taken here and listed under "Open questions for the owner".

### Still true

- The problem is real. `completion_audit._outside_refresh_artifacts` is still the path test: it drops every path under the refresh-artifact dirs for an approved ticket (plugin/crew/hooks/scripts/completion_audit.py:255-265) and never calls `artifact_verdicts`. `git grep -n artifact_verdicts origin/main -- plugin/crew/hooks/scripts` finds it only in crew_refresh_check.py. No commit on origin/main names L-0540 (`git log origin/main --grep=L-0540 -i` lists only T-0094's own commits).
- The docs still carry the interim sentences: plugin/crew/README.md:821 and :826, docs/guides/crew/src/daily-workflow-scope.md:109-111, .crew/codemap/crew.md:1192-1199 and :1506, and the docstring at plugin/crew/hooks/scripts/crew_refresh_check.py:122-127.
- MUST-FIX `:795` (an artifact removed from the index but left on disk gets True) is still open. `_on_disk` skips every raw record that has `000000` on either side (crew_refresh_check.py:829-833) and an empty `ls-files -s` falls through to `return None, data` (:834-842). No test in test_refresh_admission.py covers `git rm --cached`.
- The tooling-PR rule still applies: completion_audit.py, scope_guard.py and `plugin/crew/tests/sabotage*.py` are in `HARNESS` (scripts/check-tooling-pr.py:58-87).

### What changed since the seed (2026-09-30)

1. **MUST-FIX `:706` is fixed on main.** W-0116 (`7de96ec1`) added `_win_final_path` and the `_FINAL_PATH` check in `_read_regular`'s no-`dir_fd` branch (crew_refresh_check.py:687-716, :753-759), with three tests (test_refresh_admission.py:1462, :1473, :1484). It has no sabotage entry: main's sabotage_refresh.py has not changed since the split.
2. **W-0117 (`e51f9db7`) rewrote `_on_disk`'s mode check** into a loop over the worktree and `--cached` diffs (crew_refresh_check.py:821-833). One seed sabotage entry no longer matches: `git diff --raw failing reads as unchanged` (seed sabotage_refresh.py:630-633) finds 0 occurrences on main. Its sabotage entry for the index-only refusal is L-0624's.
3. **The seed's completion_audit.py cannot be copied over main's.** T-0100 landed in between and added the merged-main narrowing to the same function (`changed_paths(top, base, merged)`, `_as_merged`, `_file_mode`, `_disk_mode`, `_merged_lines`; completion_audit.py:173-239, :268-325). The seed predates all of it. The seed's four admission functions (`_verdicts`, `_default_artifacts`, `_outside_refresh_artifacts`, `_entry`) and its docstring paragraph have to be ported onto main's file by hand. "Not to be re-derived" above no longer holds for this one file.
4. **The seed's sabotage file was checked statically against main** (import the seed list, count each `find` in main's target): 117 crew_refresh_check.py entries, 116 found exactly once and 1 found 0 times (item 2); 4 scope_guard.py and 1 verify.json entries all found once; 15 completion_audit.py entries, 11 of which wait for the port. Main's file has 51 entries, all unique. Nothing was run.
5. **The fix for `:795` is production code outside the harness.** crew_refresh_check.py is in neither `HARNESS` nor `ALONGSIDE`, so a PR that edits completion_audit.py cannot also carry it. The same holds for the interim docstring at crew_refresh_check.py:122-127.
6. A new design question the seed did not face: with T-0100, the audit judges a narrowed path list. README.md:826 already states the answer ("a path the ticket changed since its scope base reaches it — merged-in main paths included"), and `ticket_freshness`, which demands the refresh, measures against the un-narrowed list (crew_refresh_check.py:1332).

### Options

1. **Recommended, taken: two PRs, the fix first.**
   - L-0688 (feature PR, lands first): `_on_disk` refuses an artifact the index no longer holds while its base copy exists; test in test_refresh_admission.py; the interim docstring in crew_refresh_check.py reworded so it is true before and after the wiring.
   - L-0540 (tooling PR, lands second, alone): port the seed's admission functions onto main's completion_audit.py, the scope_guard.py docstring, the seed's audit suite and sabotage entries re-checked against main, the sabotage entries for L-0688's refusal and for W-0116, the interim sentences removed from README, guide and code map.
   - Reach passed to `artifact_verdicts` is the un-narrowed changed set; the artifacts judged are the narrowed ones.
2. One PR with both. Refused by `check-tooling-pr.py` (crew_refresh_check.py is feature work beside a harness path).
3. Wire first, fix `:795` after. Rejected: the owner's 2026-09-30 note says both holes are fixed before the audit calls `artifact_verdicts`.

L-0540 keeps the title, the seed and the tooling half. The slice that lands first is the child, because renaming L-0540 to the fix would detach the seed from its ticket.

### Open questions for the owner

1. Order and identity: L-0688 lands before L-0540. Recommended and taken. The alternative is to make L-0540 the fix and the wiring the child.
2. Fold L-0624 (W-0117's sabotage entry) into L-0540? Both edit sabotage_refresh.py in a tooling-only PR, and L-0540 already has to re-point one seed entry at W-0117's loop. Recommended: fold. Taken: not folded (another ticket's scope), with a note in the spec.
3. Reach after a catch-up merge: un-narrowed (merged-in main paths reach an artifact), matching README.md:826 and `ticket_freshness`. Recommended and taken. The stricter alternative (only the ticket's own paths reach) makes the audit refuse a re-anchor that `/crew:done` check 4 demands.
4. The dangling-symlink rule test ("Known adjustments" 1): keep `[could not tell:` by stubbing `_read_regular`, as T-0094's unit test does (test_refresh_admission.py:552-564), and add one audit test asserting `[a symlink, which no refresh writes]`. Recommended and taken.
