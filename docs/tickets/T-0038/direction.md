# T-0038 direction - fold /crew:upgrade into /crew:migrate

Status: direction APPROVED by the owner 2026-09-26 ("Fold into /crew:migrate (Recommended)"). The owner's OK
covers removing the `/crew:upgrade` command file (CLAUDE.md "Stop and ask": deleting a registered entry).

## Ask (owner, Matthew Badali, 2026-09-26, verbatim)
"another ticket is remove the /crew:upgrade command if it has been truly depracated"

## Facts (origin/main 3c1f94a9)
- Not truly deprecated. `plugin/crew/commands/upgrade.md:1-8`: "On crew 1.0, a 0.20 repo upgrades with
  `/crew:migrate --preview`, not this. Use this only for a config `/crew:migrate` refuses (no integer
  `schema`), then migrate." So it is still the only route for a pre-0.20 config.
- `crew_upgrade.py` (`plugin/crew/skills/crew-graph/scripts/crew_upgrade.py`) is shared: `/crew:onboard
  --refresh` runs it for the graph rebuild (`plugin/crew/commands/onboard.md:210-220`), CONFIG.md documents
  its migrations (`:108`, `:338-351`, `:436`, `:1382` SCHEMA_7_KEYS), and 10 test files use it
  (test_upgrade.py, test_crew_config.py, test_crew_state.py, conftest.py, sabotage.py, and others).
- README lists `/crew:upgrade [--force]` in the command table (`plugin/crew/README.md:2169`) and refers to
  it at `:822`, `:856`, `:1035`.

## Recommendation (approved)
- `/crew:migrate` detects a config with no integer `schema` (pre-0.20) and runs the upgrade step itself
  (`crew_upgrade.upgrade_config`, the same code), then continues its normal preview/backup/atomic-apply/
  rollback. The preview shows both stages, and the rollback covers both.
- Delete `plugin/crew/commands/upgrade.md`. `crew_upgrade.py` stays as a library, and onboard and the
  tests keep using it.
- A user who types `/crew:upgrade` gets told what happened, e.g. via a short removal stub like `/crew:work`
  and `/crew:ticket` have ("Removed in crew 1.x - use /crew:migrate"), rather than "unknown command".
  Decide in spec: a stub, or a clean removal.
- Update every doc that names the command: README table and prose, onboard.md's references, migrate.md,
  CONFIG.md, and the lifecycle/command-count tests and budgets.
- Tests: migrate on a pre-0.20 fixture upgrades then migrates in one run, with preview showing both
  stages and rollback restoring the original bytes. A 0.20 and a 1.0 config behave exactly as today.

## Open questions
- Removal stub or clean delete? Recommendation: a stub for one minor version, as with `/crew:work`.
- T-0025 (contextual help) and T-0018 list commands too; whichever lands second updates its list.

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
