# T-0500 direction - crew init/migrate phase status

Status: approved 2026-09-30 under standing authority (owner Matthew Badali, 2026-09-26 "no longer ask me for approvals. You can self-approve"; 2026-09-27 "You should have the authority to approve these"; open questions take the written recommendation). Approved by the T-0500 Brainstorm phase of the aws-ops follow-up run (owner choice 2026-09-29 ~06:45 CDT "New workflow, 2 lanes (Recommended)").

## Ask

Verbatim, from the aws-managed-services "automation" session (crew 1.0.59, bitbucket and obsidian-vault plugins), follow-up report relayed cross-session 2026-09-29 ~06:40 CDT; the reporter's line numbers are at crew 1.0.59:

> 13. /crew:init after /crew:migrate had nothing to resume: .crew/STATUS.md (written under 0.20, updated 2026-08-28) marks all 9 phases `done`, so the 1.0 Phase 6 web-scaffold step was never offered and the Phase 2 row still says `done` although its own note records notify broken since 2026-08-27 (notify.provider none). Suggest: migrate (or init) flags phases whose definition changed since they were marked done, and a phase whose note contains a recorded breakage cannot stay `done` without re-verification.

Siblings from this follow-up: T-0501 (14), T-0106 gains item 15, T-0502 (16), T-0503 (18-20). Item 17 is T-0088. None of them is touched here.

## Verification against origin/main (a61a6f38, crew 1.0.69)

The item reproduces, by reading: the resume logic is prose the model follows, not a script, so there is no code path to run in a throwaway repo. Evidence:

- `plugin/crew/skills/crew-setup/phases.md:9-10`: "Read `.crew/STATUS.md`. If it does not exist, start at Phase 0. If it does, resume at the first phase not marked `done`." `plugin/crew/commands/init.md:15` repeats it ("no argument - resume at the first phase not marked `done`"). A table with every row `done` therefore resumes nowhere, whatever changed in the phase definitions since.
- `plugin/crew/skills/crew-setup/phases.md:25-45` defines the STATUS.md format: `repo:`, `updated: <date>`, and a `# | Phase | State | Notes` table. Nothing records which crew version (or which revision of a phase) a row was marked against, so a later reader cannot tell a stale `done` from a current one.
- The Phase 6 web step is newer than the reporter's status file: `plugin/crew/commands/init.md`'s "Web phase (inside Phase 6, Browser tests)" and `phases.md`'s `webtest_scaffold.py` line both first appear in 6c497a14 (crew 1.0.25, 2026-09-25) (`git log -S"Web phase" -- plugin/crew/commands/init.md`); the reporter's STATUS.md was last updated 2026-08-28 under 0.20. Seven commits have touched `phases.md` since 2026-08-28.
- `plugin/crew/commands/migrate.md` and `plugin/crew/hooks/scripts/crew_migrate.py` never read or mention `.crew/STATUS.md` or setup phases (`git grep -i "STATUS.md\|phase"` on both: only `crew_migrate.py:135`, an unrelated metrics key list). So migrate carries a 0.20 phase table into 1.0 unexamined.
- No script under `plugin/crew/hooks/scripts/` parses `.crew/STATUS.md` (`git grep "STATUS.md" origin/main -- plugin/crew/hooks/scripts` is empty), and no test covers it.
- On breakage in notes: `phases.md:46-47` says "Be honest with `partial` and `blocked`. A status file that says `done` when a thing half works is how the whole system quietly stops meaning anything", and Phase 2's "Done when" (`phases.md:287-290`) requires a test message to have actually arrived. Neither is re-checked at resume, and nothing reads a `done` row's note. A row reading `done | ... notify broken ...` passes silently.

## Constraints that shape the options

- An unknown stays its own value (this repo's recurring bug). A legacy STATUS.md that carries no record of what it was marked against is "could not tell", never "current".
- `done` is not re-derived automatically. The report asks for flagging and re-verification, not for crew to demote the operator's rows on its own; demotion happens when the operator re-runs the phase and it does not pass.
- No hook is added (project CLAUDE.md "Adding a hook"). Whatever checks this runs when `/crew:init` or `/crew:migrate` is invoked.

## Options

1. **Record what each row was marked against, and check it at resume and at migrate (recommended).** Each phase section in `phases.md` carries a machine-readable revision marker naming the crew version at which its definition last changed materially (Phase 6's is 1.0.25 at minimum); STATUS.md gains a `crew: <version>` header line written with every rewrite. A small read-only checker (a subcommand of an existing crew script or a new one; the spec decides) parses STATUS.md and prints one line per `done` row that is (a) older than its phase's revision marker - "definition changed since marked", (b) unknown because the file carries no `crew:` line - "could not tell when marked; re-verify", and (c) carrying a note that records a breakage. `/crew:init` (no argument and `--status`) runs it before choosing where to resume and offers each flagged phase for re-verification before the first non-`done` one; `/crew:migrate` preview and apply print its lines so a migrated 0.20 table is flagged at the moment it enters 1.0. `phases.md` states the rule in prose: a `done` row whose note records a breakage is not `done` - re-verify, then mark `done`, `partial` or `blocked`. For (c), the checker uses a short, documented list of breakage wording (for example `broken`, `failing`, `not working`, `provider none`) and is advisory, reported as "note may record a breakage" - it never rewrites the row. Tradeoffs: someone must bump a phase's marker when its definition changes materially, and the checker cannot tell a material edit from a typo fix (a test can at least require every phase section to carry a marker that parses); the breakage list is a heuristic that can miss wording, which is why the prose rule, not the checker, is the authority.
2. **Hash each phase section and store the hash per row.** Precise, no manual bump. Tradeoff: every wording edit, typo fix or reflow flips every hash, so every repo is told to re-verify phases whose meaning did not change; the flag stops meaning anything within a few releases, which is the failure the report is about. Rejected.
3. **Migrate resets every phase to `todo` (or a new `re-verify` state).** Simple and certain. Tradeoff: forces the operator to redo nine phases, most of which have not changed, and adds a state value the format and every reader must learn; it also does nothing for a repo already on 1.0 when a phase later changes. Rejected.
4. **Prose only** - tell the model in `phases.md` to re-check `done` rows on resume. Tradeoff: the model has no record of what a row was marked against, so it cannot know which definitions changed; it is today's "be honest" sentence again. Rejected as insufficient alone; its prose half is part of option 1.

## Recommendation

Option 1. It fixes both halves of the report with the smallest durable mechanism: a version stamp on the file plus a per-phase revision marker makes "definition changed since marked" a comparison rather than a guess, a missing stamp surfaces as "could not tell" instead of silently current, and a `done` row with a breakage note is named at resume. It runs from the two commands the report names, writes nothing on its own, and adds no hook. YAGNI: no auto-demotion, no new state value, no per-phase hashing.

Scope note (not a file list; that is the spec's): this is a `plugin/crew/` change, so the project CLAUDE.md doc rule applies - every document describing `/crew:init`, `/crew:migrate`, the crew-setup skill and the STATUS.md format is updated in the same PR, and the crew version is bumped one patch past origin/main at push time. No hook is added.

## Open questions

Settled under standing authority with the written recommendations (no owner answer was recorded for any of them):

1. Which option? - Option 1.
2. Should the checker ever change a row's state? - No; it reports, and the operator's re-run of the phase sets the state.
3. Legacy STATUS.md with no `crew:` line: flag every `done` row, or only those whose phase has a marker newer than 0.20? - Every `done` row, as "could not tell when marked" (an unknown stays its own value). The migrate output says this is expected once for a 0.20 table.
4. Should `/crew:migrate` apply stamp the migrated STATUS.md? - No: stamping would claim the rows were checked against 1.0 when they were not. The stamp is written only when a phase is actually run or re-verified.

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
