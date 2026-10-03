# T-0100 direction          status: approved   risk: med
## Ask
Owner, 2026-09-28, accepted T-0092's review round 2 ("Accept, fix at land") and had its two NITs filed as tickets. This is NIT (b), widened by the owner ("Waive, land", 2026-09-28): both `review_patch.py`'s bundle base AND `completion_audit.py`'s scope base use the ticket's recorded start, so merged-in main changes are re-reviewed and flagged out of Touch.
## Facts
T-0092 round 2 (Claude reviewer, same family; bundle 3f3be3f2d187 at 68d34203), verbatim NIT: "plugin/crew/commands/review.md:125|The review base is the ticket's recorded start, `f54af3fa`. After three merges of main, this bundle carries the already-landed T-0076, T-0091 and T-0089 diffs as well as T-0092's own: `crew_context.py`, `uv-install.sh`, `CLAUDE.md` and about 12 test files. The reviewer re-reviews merged work, and the bundle is several times larger than the ticket. This is existing `scope_base` behaviour and not introduced here. File it separately." Evidence given: "`git merge-base HEAD origin/main` = `ff59160f`, but manifest `base` = `f54af3fa`."
Same cause at the gate: `/crew:done` check 3 (`completion_audit.py --check --ticket T-0092`) at 68d34203 printed "COMPLETION AUDIT: 16 changed path(s) outside T-0092's spec ## Touch", every one byte-identical between main `ff59160f` and the branch (merged-in T-0076/T-0089/T-0091 files). The owner waived check 3 for T-0092 as a merge artifact. Both read the base from `scope_base.resolve` (the `.crew/.scope-base` record written at ticket start).
## Options
1. **Account for merged main in both (recommended):** diff from the ticket start, then drop any path whose content at HEAD equals its content at the latest merged main commit (or diff against `merge-base HEAD <merged main>` when the branch has merged main), in `review_patch.compute` and `completion_audit.changed_paths` alike, so the receipt hash and the audit agree; must-block: a ticket edit to a file main also changed stays in; must-allow: a merged-in main file identical to main drops out.
2. Re-record `.crew/.scope-base` at each merge of main - simpler, but loses the ticket-start evidence and needs every merge path to remember to do it.
## Recommendation
Option 1; TOOLING change touching the review receipt, so it lands alone with a regression suite and sabotage entries.
## Open questions
none - settled 2026-09-28 under the owner's standing authority (2026-09-26 "no longer ask me for approvals. You can self-approve"; 2026-09-27 "You should have the authority to approve these"), which takes the written recommendation for every open question:
- Which "main" commit counts as merged when a branch merged main more than once: the LATEST merged main, i.e. the newest commit reachable from HEAD that is also an ancestor of the integration ref (`git merge-base HEAD <integration ref>`, which after a merge of main is that merged commit). A path drops out only when its content at HEAD is byte-identical to its content at that commit; every other path the ticket-start diff lists stays in. When no merge of main is reachable from HEAD past the ticket start, behaviour is unchanged. When that merged commit cannot be determined (ref missing, git error), the result is "could not tell" and nothing is dropped - never a silent narrowing.
- The integration ref is origin/main today; T-0061 (ticket base branch, `tickets.baseBranch`) owns making it configurable. T-0100 reads the ref through one helper so T-0061 can swap it, and does not implement T-0061.
- T-0094 (refresh artifacts in scope) is a separate Touch-membership rule in the same audit; T-0100 changes only which paths enter the changed set, not which count as in scope, and does not implement T-0094.
- Receipt coupling: the bundle hash changes for any branch that merged main, so a receipt recorded before this lands no longer matches a rebuilt bundle. The spec states how an existing receipt is treated (re-bundle vs. honoured), and review_patch.compute and completion_audit.changed_paths share one implementation so the two cannot disagree.
- Guard class: completion audit is a blocking check. Regression suite with must-block (a ticket edit on top of a merged-main edit to the same file stays flagged; an out-of-Touch edit after a merge stays flagged) and must-allow (a merged-in path byte-identical to merged main drops out), plus sabotage entries confirming the suite goes red when the drop rule is removed or widened.
## Approval
Status `approved` 2026-09-28 under the owner's standing authority above; run go 2026-09-28 ~15:00 CDT ("Ok let's move all those, a backlog or 2 and a critical path in a. Workflow Brainstorm -> spec -> approve -> implement -> review -> fix -> gate -> land"; backlog pick "T-0100 + T-0094"). Option 1 (recommended). Next: /crew:spec T-0100.

## REVIEW WHILE CODEX IS OUT (owner decision 2026-09-28)
Codex is out of credits until 2026-10-03 12:26 PM; reviews run with the Claude reviewer (owner: "if we hit a codex limit please use claude ads the reviewer"), announced as same-family.

## BUDGETS.md standing rule (owner decision 2026-09-28 ~06:00 CDT)
"Always in scope (Recommended)": until T-0046 lands, any ticket that edits a plugin/crew .md file may update plugin/crew/BUDGETS.md's line-count claim without a Touch amendment; the PR body says so.

## Refresh-artifact standing rule (owner decision 2026-09-28 ~06:40 CDT)
Any ticket may re-anchor .crew/codemap/**, regenerate .claude/rules/**, refresh docs/diagrams/** and rebuild graphify-out/** when its own changes made them stale - re-anchor/regenerate only, never a content rewrite - without a Touch amendment; say so in the PR body and tell the reviewer.

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
