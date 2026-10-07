# T-0106 direction - crew auto-clear setup (plugin/crew/hooks/scripts/crew_autoclear_setup.py)

Status: seed (not yet approved; the Brainstorm phase settles it under the owner's standing authority).

## Ask
the owner, 2026-09-29 ~05:15 CDT, verbatim: "@<another repository> reporting gizmo duck plugin issues please take that, and address them at the same time as this , put them in a workflow brainstorm -> spec -> approve -> implement -> fix -> gate -> land"

## Report (verbatim, from another repository's session (crew 1.0.59, gizmoduck 0.5.3), found 2026-09-28/29, relayed cross-session 2026-09-29 ~05:10 CDT; its line numbers are the reporter's at crew 1.0.59 / gizmoduck 0.5.3 - re-verify against origin/main)
7. crew_autoclear_setup.py apply-migrate: detect_onlyRepos_widening (:344-378) can only propose the current repo, so with widening=true and no local opt-in it proposes [] - I had to scan <repos-root>/**/.crew/config.json by hand to find the 6 repos with autoClear.enabled=true. A --scan-root option would fix it.

## Notes
- Every claim above is the reporter's; Brainstorm verifies each against the code before designing.
- Siblings from the same report: T-0104 (items 1-5), T-0105 (6), T-0106 (7), T-0107 (8, 12), T-0108 (9-11).

## Added item (follow-up report, 2026-09-29 ~06:40 CDT, verbatim)
15. crew_autoclear_setup.py apply-migrate printed each note twice ("context.autoClear.onlyRepos was set in the repo file..." x2, same for onlySessions) - one per file (config.json and crew.json) but the text doesn't say which file, so it reads as duplicate output.

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
Checked against origin/main `155fe6d8` (crew 1.0.322). Status: direction settled under the owner's standing authority; the owner was not available, so each open choice below took the recommended option.

### Still true
- **Item 7 is real and unfixed.** `plugin/crew/hooks/scripts/crew_autoclear_setup.py` has not changed since crew 1.0.25 (`git log origin/main -- <that path>` shows one commit, `6c497a14`), so the reporter's line numbers still hold. `detect_onlyRepos_widening` (`:344-381`) builds the proposal from the current repo alone (`:362`), and its own message says "This process can only see this repo" (`:371-373`). `apply-migrate` has no `--scan-root` (`:727-732`), and `git grep -n "scan-root\|scan_root" origin/main -- plugin/crew` prints nothing.
- **Item 15 is real and unfixed.** `apply_migrate_to_repo` converts `.crew/config.json` and `.crew/crew.json` separately (`:595-608`) and joins their notes into one list (`:610`). Each note starts with the repo label only (`:318`, `:329`) and the method-rename note has no label at all (`:285-287`), so two files with the same legacy block print the same text twice and nothing says which file each line is about.

### Found while checking (not in the report)
- **`--yes-widen` with an empty proposal turns auto-clear off on the whole machine.** In the reporter's exact case (machine file `enabled: true`, `onlyRepos: null`, this repo with no local opt-in) the proposal is `[]` (`:362`). `apply_migrate_to_repo` writes whatever the proposal is (`:615-617`), and `[]` "arms nothing" (`plugin/crew/CONFIG.md:743`, `crew_autocycle.py:276-297`). The message printed beside it says "nothing is proposed to add", which does not warn that applying it disarms every repo. `commands/migrate.md:83` routes the write through `crew_config.py --set` after a question, so the command path is less exposed than the flag, but the flag is documented in `--help`.
- **A repo that was already migrated cannot be found by any scan.** The first `apply-migrate` run strips the repo's `enabled: true` (`:315-316`, and the docstring at `:568-576`). A scan can only find repos that have not been converted yet. The reporter's six were found because they were unconverted.
- **`plugin/crew/tests/test_worktree_config.py:201` counts the config-path joins in this module** (2 today). A scan that joins `.crew` with a config file name adds a site, so that count and its reason have to move with the change.

### What changed since the seed
- Nothing in the module. Around it: T-0088 (merged) added the worktree config-reader count above; `commands/migrate.md` is at 111 of its 120-line budget (`plugin/crew/BUDGETS.md:34`); crew is at 1.0.322.
- `docs/handoff/cloud/T-0106.md` and its row in `docs/handoff/cloud/README.md` are on main and must be deleted by this ticket's PR (the note's own cleanup rule).

### Options
1. **(Recommended, taken) `apply-migrate --scan-root <dir>`, read-only discovery, plus file-named notes.** The flag is repeatable. Each root is walked to a bounded depth (`--scan-depth`, default 3); a directory holding `.crew/config.json` or `.crew/crew.json` is a candidate and is not descended into; hidden directories, `node_modules` and symlinked directories are skipped. A candidate whose file has `context.autoClear.enabled: true` joins the proposal next to the current repo. A candidate that cannot be read is reported as could-not-read, never as "not opted in", and blocks `--yes-widen`. `--yes-widen` with an empty proposal is refused instead of writing `[]`. Every `apply-migrate` note is prefixed with the file it is about. The scan never writes to another repo.
   Tradeoff: about 120 production lines in one module, one new walker. It cannot find repos that were already converted, and says so.
2. **Scan the default places without a flag** (the parent of the current repo, or the home directory). Rejected: an unrequested walk of someone's disk from a migration command, with a guess about where repos live. The reporter asked for an option.
3. **Record each converted repo's opt-in in the machine file as the migration runs**, so later runs can rebuild the list. Rejected for this ticket: a new machine-file key, a new writer and a schema change, for a one-time migration. It would fix the already-converted case; it is listed as an open question.
4. **Docs only**: tell the user to search by hand. Rejected: that is what the reporter had to do.

### Recommendation
Option 1. Item 15 and the empty-proposal refusal ride in the same ticket: all three are in `apply_migrate_to_repo` and its CLI, and together they are well under the split size.

### Open questions for the owner
Each took the recommended default; none blocks the work.
1. Default scan depth. Taken: 3 levels below each root (covers `<root>/<group>/<repo>` with one level to spare), settable with `--scan-depth`. Alternative: unlimited depth with the same pruning.
2. `--yes-widen` with an empty proposal. Taken: refuse (exit 1, nothing written, the message names `--scan-root` and the by-hand command). Alternative: keep writing `[]` and only reword the message. The refusal changes what an existing flag does in one case.
3. `--yes-widen` when a scanned candidate could not be read. Taken: refuse, so a repo that might have opted in is not silently left out of the list. Alternative: write the readable ones and warn.
4. Already-converted repos (option 3 above). Taken: out of scope, stated in the output and the docs. Say if a follow-up ticket is wanted.
5. Linked worktrees found under a scan root are listed when their own file carries the opt-in, the same as any other directory. Taken: accept; the list is shown before anything is written.
