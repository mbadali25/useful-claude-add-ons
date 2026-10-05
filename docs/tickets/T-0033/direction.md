# T-0033 direction - a version bump does not stale a review receipt

Status: direction APPROVED by the owner 2026-09-25 ("Let's go with your recommendations on ... (b) File a
ticket so version-bump files don't count toward the review hash").

## Ask
Offered: "(b) File a ticket so version-bump files don't count toward the review hash. That removes the
problem for every future landing". Owner chose it, with (a), T-0006's rebase-only successor plan, now.

## Problem (measured 2026-09-25)
- A review receipt stands only while the tree still hashes to the reviewed bundle. `check_receipt`
  compares `_current_hash` (`plugin/crew/hooks/scripts/review_ledger.py:356-363`), which is
  `review_patch.compute(root, base)["bundle_sha256"]`, the whole diff. `accept` refuses when the tree no
  longer matches the bundle that round read.
- Landing requires crew's version to be above origin/main (CLAUDE.md "Content change with no `version`
  bump"). When another ticket lands first, re-bumping a reviewed branch changes the bundle, the
  receipt goes stale, and with no rounds left the ticket needs a successor plan, an owner approval and
  another review round, for a one-line version change. It hit T-0006 and T-0008 on 2026-09-25, and
  forced a hand-maintained land-order version table in `.work/HANDOFF.md`.
- The same edit also changes `CHANGELOG.md`'s version heading and `plugin/PLUGINS.md`'s version cell.

## Recommendation (to be settled at /crew:spec)
Compute the receipt's bundle hash over the diff with **version-only hunks** in the release-bookkeeping
files normalised: the `"version"` value in `**/.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json`, the `<!-- claim: plugin-version:... -->` cell in `plugin/PLUGINS.md`,
and the version number in a `CHANGELOG.md` entry heading. Mechanically:
- Only the version token is normalised. Any other change in those files, including CHANGELOG prose,
  still stales the receipt, so a re-bump cannot smuggle content past review.
- The reviewer still reads the real diff. Only the receipt comparison normalises.
- A receipt written under the old scheme still verifies (dual-read, as T-0026 does for approvals).
  A hash scheme the checker does not know reads stale.
- Must-block tests: a prose edit in CHANGELOG, a new key in plugin.json, a code change, and a
  version edit smuggled inside a larger hunk. Must-allow: a pure re-bump across all four files.
  Sabotage: normalise the whole file instead of the token.

## Open questions
- Does the same normalisation belong in T-0026's approval digest (plan.md often names the version)?
  Probably not: the owner re-approves plans rarely, and T-0006's plan fixes its version on purpose.
- Depends on nothing unmerged; touches review_ledger.py / review_patch.py (T-0008 and T-0026 do not).

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

## Direction check 2026-10-04

Checked against origin/main `155fe6d8` (crew 1.0.322). Recommended option, taken as the default because
the owner was not available: **hold T-0033, do not hand it to an implementer, and close it as superseded
when L-0522's delta gate lands.** The spec is refreshed as a fallback contract only.

### What is still true
- Nothing on origin/main normalises version tokens. `git grep -E "receipt_scheme|normalise_versions|receipt_sha256|crew-review/2" origin/main -- plugin scripts` prints nothing, and no commit on origin/main names T-0033.
- The receipt is still a whole-bundle comparison: `plugin/crew/hooks/scripts/review_ledger.py:824-831` (`_current_hash`), `:878` (`check_receipt`), `:457` (`accept`), `:691` (`auto_accept`).
- A re-bump still stales a receipt. Lanes cover it today with a hand waiver, not a mechanism.

### What changed since 2026-09-26
1. **The bundle is rebuilt against merged main (T-0100, on origin/main as crew 1.0.322).** `plugin/crew/hooks/scripts/review_patch.py:75-95` (docstring "MERGED MAIN") and `plugin/crew/hooks/scripts/merged_main.py:12-18`: a path main also changed is diffed from the merged commit, not from the ticket start.
2. **Every re-bump now follows a catch-up merge.** Owner rule 2026-09-30 (above): merge main, then set the version one patch past it. The 2026-09-26 design excludes exactly that case ("A branch that merges or rebases main after review is not covered").
3. **Measured 2026-10-04** in a throwaway repo with origin/main's `review_patch.compute`:
   - Bump only, no merge: the bundle differs in the `+` version line, the CHANGELOG `+` entry line and the two new blob ids. The 2026-09-26 design covers this.
   - Catch-up merge, then bump: the bundle also differs in the `-` version line (`-  "version": "1.0.1"` becomes `-  "version": "1.0.2"`), both blob ids on each `index` line, and two CHANGELOG context lines (main's new entry). The 2026-09-26 design hashes `-` lines, context lines and the old blob id raw, so the receipt still stales.
   - In this repo a catch-up is also followed by a refresh (code map anchors, rules, diagrams, BUDGETS count), which no version-token rule can cover.
4. **L-0522 (in-progress) is the mechanism for the real case.** Its delta gate keeps a receipt across catch-up merge, version bump, CHANGELOG and anchor-only refresh, and it names the bump-only case too (`test_bump_only_without_a_merge_keeps_the_receipt`, `test_catch_up_then_version_bump_and_changelog_keeps_the_receipt` on its tooling branch). PR 1 of 3 is open (#377); PR 2 (`review_delta.py`) is built on a local branch, not on origin/main. It ships fail-closed: it keeps nothing until the merge train is armed (owner decision 2026-10-03).
5. **Two decisions in the 2026-09-26 spec no longer match main:**
   - The CHANGELOG shape. Entries since crew 1.0.242 are headings (``### Changed — `crew` 1.0.322: ...``, `CHANGELOG.md:7`), not bold bullets with a ``Bumped `a -> b` `` span.
   - "CHANGELOG prose still stales the receipt". L-0522 exempts CHANGELOG, TODO, PLUGINS.md and BUDGETS.md in full (its U6, owner-accepted as "refresh or bookkeeping only").
6. **Every file the design edits is review/gate harness** (`scripts/check-tooling-pr.py:58-87`: `review_*.py`, `sabotage*.py`, `commands/review.md`), and L-0522 PR 2 edits the same functions (`check_receipt`, `review_run.py`, `sabotage_review.py`). Building both means two lanes in one function, and L-0522's own U3 says its plan must be re-checked if T-0033 lands first.
7. `plugin/crew/tests/sabotage.py` is now 3400 lines, exactly `.pylintrc:140` `max-module-lines=3400`. It cannot take one more line.

### Options
1. **Hold, then close as superseded by L-0522 (recommended, taken as the default).** No code. When L-0522 PR 2 is on main and the train is armed, check that a catch-up plus re-bump keeps a receipt in this repo, then close T-0033. Cost: nothing. Risk: if L-0522 PR 2 is cut, the waiver stays until another ticket replaces it.
2. Build the 2026-09-26 design as refreshed in spec.md. About 190 production lines, all harness, in two tooling PRs. It keeps a receipt only for a bump with no merge, which the current workflow does not produce, and it collides with L-0522 PR 2.
3. Widen the normaliser to the catch-up case (`-` lines, old blob ids, CHANGELOG context). That rebuilds a weaker L-0522 inside the hash and still stales on the refresh. Not recommended.

### Open questions for the owner
- Close T-0033 as superseded by L-0522 (option 1), or build the bump-only normaliser anyway (option 2)? Default taken: option 1, hold.
- One gap neither ticket closes: `accept` stays strict in L-0522 (owner-accepting a FINDINGS round after a catch-up is refused; accept first, then catch up). Is that worth its own ticket? Default taken: no, the order "accept, then catch up" is already what lanes do.

## Direction check 2026-10-05 (cloud hand-off)

Re-checked against origin/main `a555ff37` (crew 1.1.0). Nothing on main normalises version tokens
(`git grep -E "receipt_scheme|normalise_versions|receipt_sha256|crew-review/2" origin/main -- plugin scripts`
prints nothing), and L-0522's delta gate is still not on main (`git grep -l review_delta origin/main -- plugin
scripts` prints nothing; PR #377, part 1 of 3, merged 2026-10-04; no part 2 PR is open). So the ticket is neither
done nor yet superseded.

## Ask
Publish T-0033's existing direction, spec and plan for cloud hand-off, with the spec's anchors re-verified at
current main, keeping its decisions.

## Options
1. **Publish as a held fallback (recommended, taken).** Spec anchors refreshed, the hold decision of 2026-10-04
   kept, plan.md published as-is and marked stale. A cloud session that picks it up checks L-0522 first and, if
   part 2 has landed, closes T-0033 as superseded instead of building.
2. Publish as buildable now. Rejected: it collides with L-0522 part 2 in `check_receipt` and keeps a receipt only
   for a bump without a catch-up merge, which the current workflow does not produce.
3. Close now as superseded by L-0522. Rejected: L-0522 part 2 is not on main, and closing before it lands would
   leave the bump-only case with no ticket if part 2 is cut.

## Recommendation
Option 1. One spec change beyond line numbers: the CHANGELOG heading grammar is widened to the heading shapes main
writes now (batch headings with several plugins, no backticks; see spec "Refreshed 2026-10-05").

## Open questions (default taken)
- Build or close (2026-10-04 question, still open for the owner): default taken, hold and close as superseded
  when L-0522 part 2 lands.
- The widened CHANGELOG grammar: default taken, a closed full-line grammar over the five shapes at `a555ff37`;
  confirmed by the owner at approval if the ticket is built.
- plan.md: published unchanged and marked stale; default taken, re-plan only if built.

Approved 2026-10-05 for cloud hand-off (as a held fallback) by the orchestrator under the owner's standing
self-approve authority.
