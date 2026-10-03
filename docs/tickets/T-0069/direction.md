# T-0069 direction          status: ready   risk: high
## Ask
Filed on acceptance on 2026-09-27. On 2026-09-27 the owner accepted the final review rounds' FINDINGS for T-0024 (round 4), T-0042 (round 2) and T-0023 (round 2) ("go with your recommendations"). The six accepted FIXes are fixed here, not on those branches:
- T-0024 r4 (`.work/review/T-0024-build--M5RnMP/out.txt` in uca-t-0024): `plugin/crew/hooks/scripts/crew_ticket.py:751`, where a closed ticket with an all-letter or all-digit id reads as open. `plugin/crew/hooks/scripts/approval_hook.py:518`, where, with an unreadable pre-write history count and no prompt_id, a confirm can report an earlier same-session approval as its own write.
- T-0042 r2 (`.work/review/T-0042-build--LhfZn9/out.txt` in uca-t-0042): `plugin/crew/hooks/scripts/crew_resume.py:340`, where a failed author invalidation never falls back to blanking the record. `plugin/crew/tests/test_crew_resume_hook.py:433`, which raises TypeError on pwsh-only hosts.
- T-0023 r2 (`.work/review/T-0023-build--v6wqvg/out.txt` in uca-t-0023): `plugin/crew/hooks/scripts/crew_route.py:243`, where clipping cuts a real command argument. `plugin/crew/hooks/scripts/crew_route.py:118`, where U+2028, U+0085 and the other Unicode line separators bypass the multiline exclusion.

Every anchor is BRANCH-ONLY: T-0023-build at `ad74ed35`, T-0024-build at `474aea8b`, T-0042-build at `3a6bdcf5`. None of them is on main yet.
## Options
1. Fix each finding on its own branch before it lands. Rejected, because the owner accepted the rounds so that each branch lands as reviewed.
2. One follow-up ticket for all six, landed after the three branches, each fix test-first with a sabotage entry and its neighbouring case. Recommended.
3. Three follow-up tickets, one per source ticket. This triples the lifecycle overhead for six small fixes, and the three share nothing that needs keeping apart.
## Recommendation
Option 2. Fail closed wherever a fix has to choose. A bare id that could be an index column is "could not tell", and a confirm that cannot tell its own entry says so. An author record that cannot be deleted is blanked. A route command that would have to be cut asks instead of routing. Depends on T-0023, T-0024 and T-0042 landing.
## Open questions
none - each FIX carries its own repro, and the direction for each is in the Recommendation.
## Approval
Status `ready`: approved under the owner's standing authorization; filed on acceptance 2026-09-27.

## From T-0042's landing
Added 2026-09-27 on the owner's decision at T-0042's landing ("Yes, let's T-021, T-042, and T-023 land."; rule 15 SKIP accepted until rule 15 gets its own re-baseline ticket). `uvx ruff check .` (ruff 0.16.9, unpinned) reports 1212 findings on origin/main `502cb137` and 1228 on T-0042's merged tree (T-0042-build `3a6bdcf5`). The 16 new findings are T-0042's and are fixed here:
- 1x BLE001 (blind `except Exception`) in `plugin/crew/hooks/scripts/crew_context.py`.
- 15x ISC004 (unparenthesized implicit string concatenation in a collection) in `plugin/crew/tests/sabotage_resume.py`.
Re-measure with `uvx ruff check --output-format concise .` on origin/main after T-0042 lands; these are not in the approved spec or plan, so adding them to scope needs the spec's Touch and an approval.
- Windows CI, PR #242 (both `crew-shell-matrix (windows-latest)` runs, 38 failed against main `502cb137`'s 37): one new failure, `plugin/crew/tests/test_crew_resume_hook.py::test_never_emits_initial_user_message`. Owner decision 2026-09-27: merge, send the test here. Verbatim:
  ```
  FAILED plugin/crew/tests/test_crew_resume_hook.py::test_never_emits_initial_user_message - AssertionError: Skipping command-line '"C:\Users\runneradmin\AppData\Local\Temp\pytest-of-runneradmin\pytest-0\popen-gw2\test_never_emits_initial_user_0\run\claude-author\..\usr\bin\bash.exe"'
    ('C:\Users\runneradmin\AppData\Local\Temp\pytest-of-runneradmin\pytest-0\popen-gw2\test_never_emits_initial_user_0\run\claude-author\..\usr\bin\bash.exe' not found)
    Need a valid command-line; Edit the string resources accordingly
  assert 1 == 0
  ```
  Hypothesis, UNCONFIRMED: the test's fake `claude` ancestor is a copied Git-for-Windows `bash.exe` launcher, which resolves `..\usr\bin\bash.exe` relative to its new directory and finds nothing, so this is test portability rather than resume behaviour. Logs: jobs 108645921026 and 108646018802.

## Native Windows confirmation (win-repo-2, 2026-09-27, f0b12ee6, crew 1.0.43)
`test_crew_resume_hook.py::test_never_emits_initial_user_message` run alone: "1 failed in 0.86s", same as CI. Verbatim:
    E       AssertionError: Skipping command-line '"D:\temp\pytest-of-d3ade\pytest-92\test_never_emits_initial_user_0\run\claude-author\..\usr\bin\bash.exe"'
    E         ('D:\temp\...\run\claude-author\..\usr\bin\bash.exe' not found)
Fails at `plugin/crew/tests/test_crew_resume_hook.py:142` (`_in_claude`), called from `:433`. The copied-bash.exe hypothesis is CONFIRMED: `crew_fixtures.resolve_bash()` (`plugin/crew/tests/crew_fixtures.py:667-720`) picks Git's `bin/bash.exe` shim (42.4K), which launches `<own dir>\..\usr\bin\bash.exe`; copied alone by `_claude()` (`:111-118`) that path does not exist. Config-independent. Fix options (untested): copy the real `usr/bin/bash.exe` (resolve_bash's comment says it cannot find its mount table when launched from python.exe), or build the fake claude so the shim keeps a matching `..\usr\bin` beside it.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
