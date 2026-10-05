# Land-prep procedure (useful-claude-add-ons)

Goal: bring PR branch <BRANCH> up to date with origin/main by a MERGE commit (never rebase/force-push), keep it review-clean, set a crew version placeholder in the LAST commit, push.

1. Worktree: `cd /home/user/useful-claude-add-ons && git fetch -q origin && git worktree add -f /home/user/pr-<N> origin/<BRANCH> -B <BRANCH>`; work only in /home/user/pr-<N>. Git identity is already Claude <noreply@anthropic.com>.
2. `git merge --no-edit origin/main`. `git config rerere.enabled false`. Resolve conflicts:
   - graphify-out/*, .claude/rules/*: take main's side (`git checkout --theirs` is the PR side during merge — careful: during `git merge origin/main`, "ours" = PR branch, "theirs" = main). Take MAIN = `--theirs`.
   - .crew/codemap/* and docs/diagrams/* conflicts that are only `anchor:` lines or line-number cites: take main's, then re-apply the PR's real content changes if any.
   - plugin versions (plugin/*/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, CHANGELOG headings, BUDGETS): take main's in the merge commit; the version is re-set in the final commit.
   - Real content conflicts: keep BOTH sides' intent; read both diffs (`git log origin/main` for what main changed) before choosing.
   Then regenerate rules: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root .` and commit the merge with message "<TICKET>: merge origin/main <short-sha>" + blank line + trailer.
3. Final commit = version only: set crew version to <VERSION> everywhere it is stated (plugin/crew/.claude-plugin/plugin.json, marketplace.json crew entry, CHANGELOG top heading for this PR's entry, any `<!-- claim: plugin-version:crew -->` lines, and the PR's own "since crew X"/arrival text if it states its version). If the PR also bumped another plugin (e.g. localgpu), make sure that plugin is one past main's value. Re-measure plugin/crew BUDGETS if check-marketplace asks.
4. Commit messages: end with exactly one trailer line `Claude-Session: https://claude.ai/code/session_016wQA2o38aSB65bpjaGpMVJ`. NEVER add Co-Authored-By.
5. Verify (report each command and result verbatim on failure): `python3 scripts/check-marketplace.py` (after committing), `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check`, plus the pytest files `.crew/verify.json` maps to the files that CONFLICTED or that main changed and the PR also changed. Do NOT run the entire plugin/crew/tests suite (container is shared). Watch the pylint 3400-line cap on test files that grew (C0302): `python3 -m pylint --disable=all --enable=C0302 <file>`.
6. Ensure the version commit is the LAST commit, then `git push origin <BRANCH>` (plain push; it is a fast-forward of the remote branch). Retry network failures up to 4 times (2s,4s,8s,16s).
7. Report: new head sha, version, list of conflicts and how each was resolved, tests run with pass counts, anything you could not verify. Keep it under 25 lines. Do not open/close/merge PRs.

## Ticket IDs (owner rule 2026-10-04)
Before reporting, confirm the PR title starts with its ticket id(s) and the body has a `Tickets:` line naming every ticket (bundles: all of them). Fix the title/body via `gh api -X PATCH repos/mbadali25/useful-claude-add-ons/pulls/<N> -f title=... -f body=...` if not.

## Batch landing (owner decision 2026-10-04: batches of 3-4; RAISED to 5-6 the same evening)
A batch is a stack of land-preps, each PR still its own merge commit:
1. PR A: `git merge origin/main`, carry its NITs, version = main+1 (last commit). Push.
2. PR B: `git merge origin/main` then `git merge origin/<A branch at its new head>`, carry its NITs, version = main+2 (last commit). Push. Same for C (merges B's head, main+3), D (main+4).
3. All heads are pushed together so CI runs on all of them in parallel. Each PR's own CI must be green on its own head.
4. Merge A, then B, then C, then D (merge commits, expectedHeadSha). Heads do not change, so no re-run.
5. If a PR's CI is red: fix on that PR, then re-merge it into every later PR in the batch (their heads change, CI re-runs).
Owner decision 2026-10-04: no separate merge-only review agent when a catch-up merge conflicts only in version/CHANGELOG/BUDGETS/generated rules/rebuilt guide binaries — the coordinator reviews the remerge-diff itself; any real content conflict still gets a review.

## Pre-flight (coordinator rule, 2026-10-04)
A PR joins a batch only when ITS OWN head has a green Windows run (crew-windows-default k/6, crew-windows-slow k/3, crew-shell-matrix (windows-latest)). For a head with no run, start one without a commit: `gh api -X POST repos/mbadali25/useful-claude-add-ons/actions/workflows/pytest-crew.yml/dispatches -f ref=<branch>` (at most 3 at a time: 20-job concurrency limit). Two Windows-only bugs stalled batch 2 because this was skipped.

## Merge-resolution review
Any REAL content conflict in a land-prep merge gets a review agent (`git show --remerge-diff <merge>`); version/CHANGELOG/BUDGETS/rules/guide-binary/codemap-anchor conflicts are reviewed by the coordinator.

## Version rule during cloud sessions - WITHDRAWN 2026-10-04 23:1x (check-marketplace requires a bump per PR; owner kept per-PR bumps). Historical text below
ONE crew version bump per BATCH, not per PR. Land the batch's PRs without their own bump (each PR's placeholder version commit is reverted at land-prep, no new one), then the LAST PR of the batch carries the single version-only commit (main + 1, covering every PR in the batch; its CHANGELOG heading lists all of them). PRs in a batch no longer stack on each other for version numbers, so they can be land-prepped and CI'd in parallel; merge order still matters only for real content dependencies. Any other plugin a batch touches (obsidian-vault, localgpu, ...) also gets one bump in that last PR. check-marketplace's version-drift check runs per PR: if it refuses an intermediate PR for content-without-bump, put the bump on that PR instead and tell the owner; never work around the checker.

## Batch PR (owner decision 2026-10-04 23:1x): ONE version bump per batch
A feature batch of 5-6 review-clean, Windows-green PRs lands as ONE batch PR:
1. Branch `batch-<n>-build` from origin/main.
2. For each PR in order: revert that PR's placeholder version commit ON THE BATCH BRANCH is not possible, so instead `git merge --no-edit origin/<pr-branch>` and resolve; then in a follow-up commit restore every version file (plugin.json, marketplace.json, PLUGINS.md claim, CHANGELOG headings, arrival text) to main's value. Each merge commit subject: `<TICKET>: merge #<n> into batch <n>`.
3. One version-only commit LAST: crew = main+1 (and +1 for every other plugin the batch touches). CHANGELOG: one heading for the version listing every ticket in the batch, each PR's entry beneath it.
4. Re-measure BUDGETS, regenerate rules, rebuild changed guides (before the version commit).
   Once #499 (L-1518) is on main: run `python3 scripts/sync-updates.py` IN the version commit, after the CHANGELOG heading is final, so the README "What's new" block matches. CI's `--check` fails otherwise. The batch heading `### crew X.Y.Z — batch <n>: <tickets>` with `####` per-PR entries renders as one line listing the parts.
5. Open the batch PR: title `Batch <n>: <TICKET>, <TICKET>, ...`, body `Tickets: ...` naming every ticket and `Lands: #a, #b, ...`. Its CI is the gate (all 6+3 Windows shards and the gate job). A merge-resolution review covers any real content conflict.
6. Merge the batch PR (merge commit). GitHub marks each original PR merged because its head is now in main; if one is not, close it with a comment "landed in batch PR #N".
Harness PRs still land ALONE, never in a batch PR.

## Cloud ticket IDs (owner rule 2026-10-05)
New untracked cloud-session tickets are numbered C-0001, C-0002, ... (next free: see CLOUD-SESSION-TICKETS.md). L-1500 to L-1518 keep their IDs.
