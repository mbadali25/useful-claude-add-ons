# T-0081 direction          status: direction   risk: med
## Ask
Filed 2026-09-27 ~22:45 CDT on the owner's acceptance of T-0077 review round 2 ("Accept, narrow spec, follow-up"). The reviewer's line, verbatim (codex/gpt-5.6-luna, bundle dc567adde158):

`FIX|plugin/crew/hooks/scripts/crew_tracker.py:1082|A board or note directory can be renamed and replaced after '_vault_paths' checks but before '_hold_dirs' opens it; only the vault identity is verified, so the replacement is pinned and written successfully|On Windows, swap 'vault\B' for an impostor 'B' between the initial checks and '_win_open_dir'; run 'move' or 'create' and observe bytes written to the impostor instead of refusal`

The same gap exists on POSIX (another machine's assessment): `_vault_paths` records only the vault's identity (crew_tracker.py:1010 on T-0077-winpin), and the POSIX walk (:1117-1125) opens each component by name from the vault fd with O_NOFOLLOW without checking any component's identity. Bounded: links, reparse points and junctions are refused, and the write cannot leave the vault. What remains is a real directory swapped for another real directory inside the vault, in the check-to-pin window.

Direction to settle at brainstorm: record each component's identity ((dev, ino) on POSIX, volume serial + file id on Windows) in `_vault_paths` and check it against the fd/handle on the walk, on both platforms; a mismatch or an identity that cannot be told (st_ino 0) refuses. Tests and sabotage per platform. Restores T-0077's original spec line 6 promise.
## Options
none yet - to be settled at /crew:brainstorm.
## Approval
Status `direction`. Depends on T-0077 landing.

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
Checked against origin/main `155fe6d8` (crew 1.0.322). The owner was not available; the recommended option is taken and the questions are listed below.

**Still true.** The gap is on main exactly as filed.
- `_vault_paths` records one identity, the vault's (`plugin/crew/hooks/scripts/crew_tracker.py:1012`).
- The POSIX walk matches the vault (`:1122`) and then opens each component by name with `O_DIRECTORY|O_NOFOLLOW` (`:1124-1127`), with no identity check on any component.
- The Windows walk refuses a reparse point, a non-directory and a zero file id on every component (`:1086-1092`), but matches identity for `index == 0` only (`:1093`).
- So a real directory inside the vault that is renamed away and replaced by another real directory, after `_vault_paths` and before the walk, is pinned and written. Links, junctions and anything outside the vault are still refused, so the write cannot leave the vault.
- Nothing merged since T-0077 touches this: the only later commit on the file is `55b4ca2d` (T-0088, config resolver). `git log origin/main --grep=T-0081` prints nothing.

**What changed since the ticket was filed.**
- Line numbers moved (the reviewer's `:1082` is now `_hold_dirs` at `:1068-1098`).
- T-0087 landed the rule that a review/gate harness change lands alone. `plugin/crew/tests/sabotage*.py` is in `HARNESS` (`scripts/check-tooling-pr.py:78`) and `crew_tracker.py` is not. So the guard and its sabotage mutations cannot share a PR. The direction's "tests and sabotage per platform" is therefore two PRs: this ticket (guard, tests, docs) and L-0672 (the mutations).
- `test_every_tracker_sabotage_anchor_is_present_exactly_once` (`plugin/crew/tests/test_crew_tracker.py:894`) holds the 87 existing anchors to exactly one occurrence each. The guard PR must not duplicate or move any of them, because it cannot edit `sabotage_tracker.py` to follow.

**Options.**
1. **Recommended, taken: record each component's identity in `_vault_paths` and match it on the walk, both platforms.** `(st_dev, st_ino)` per real component, per label, checked against the fd (POSIX) or the held handle (Windows). A mismatch refuses. An identity that cannot be told (no recorded identity, or `st_ino` 0 on either side) refuses as "could not tell". This is the direction as filed and restores T-0077's promise.
2. Match only the last component (the directory written to). Smaller, but a swapped middle directory is then found only if the last one also differs, which it always does when the middle one was replaced by a copy. It reaches the same refusals with a weaker statement; rejected because the per-component check costs a few lines more and the README can then say "every directory" plainly.
3. Document the window as a residual race and close. Rejected: the owner accepted the finding as a FIX.

**Defaults taken where the brainstorm would have asked.**
- A component that was absent or not a directory when `_vault_paths` ran gets no identity (None). Existing refusals for a missing board keep their wording; the walk refuses None as "could not tell".
- The POSIX walk also refuses a vault or component whose `st_ino` is 0. Today POSIX compares `(dev, 0)` with `(dev, 0)` and passes. A file system that reports no inodes would lose vault writes; that is the stated rule ("no id is could not tell, never the same") and Windows already behaves this way.
- Identities are recorded with `os.lstat`, so the check-time read and the no-follow open see the same object.

## Open questions for the owner
1. POSIX `st_ino` 0 on the vault or a component now refuses the write (default taken: refuse). Is there a vault on a file system that reports no inodes that this would break?
2. The sabotage mutations land in a second, tooling-only PR after the guard (L-0672), so main carries the guard without its mutations for one PR. Default taken: accept that order, with a by-hand sabotage of each new branch recorded in the guard PR's body. The alternative is mutations first, which cannot work: their anchors would not exist yet.
