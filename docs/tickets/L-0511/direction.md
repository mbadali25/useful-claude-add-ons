# L-0511 direction - Version bump and artifact refresh (codemap re-anchor, rules regen, graphify) happen ONCE at land, after the final catch-up merge, not on the build branch

Status: approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority (open questions take the recommended option, recorded below as "default taken").

Decision 5 (crew change). Measured: 57% of commits are overhead (re-bump, re-anchor, graph rebuild, catch-up merges; 2.3 catch-ups per PR). The CLAUDE.md rule 'content change needs a version bump' must stay satisfied at land. Touches commands implement.md/done.md, REPO-03 in .crew/standards.md, refresh-check expectations on build branches; docs per the crew-docs rule.

Source: owner decisions 2026-09-30 ("All recommended", relayed by crew-chat) on a measured CI/review/QA review of 2026-09-28..30; raw data at /tmp/claude-0/.../ci-review/, copied to .work/ci-review-2026-09-30/ (every number there carries its source; copy what you cite into this folder, the scratchpad is not durable).

## Ask

Stop paying for release bookkeeping on every catch-up. A build branch carries no version bump and no
refreshed artifacts (code map re-anchor, `.claude/rules/` regeneration, diagram re-anchor, graphify
rebuild). All of it happens ONCE, at land, after the final catch-up merge. CLAUDE.md's first
stop-and-ask ("content change with no version bump") must still be impossible to ship: the bump is
still required, only later.

## What origin/main `a555ff37` (crew 1.1.0) already does

- **The bump rule already says "land only".** `.crew/standards.md:73-86` (REPO-03): "the build branch
  carries none". Nothing enforces it, and two gates contradict it: CI's Marketplace job runs
  `python3 scripts/check-marketplace.py` on every pull_request including drafts
  (`.github/workflows/marketplace.yml:6-10`, `:42`), and verify rule 0 runs the same command at Stop
  (`.crew/verify.json:80-86`). Its version-drift check (`scripts/check-marketplace.py:518-550`) fails a
  build branch that changed plugin content, so lanes bump on the build branch to get a green PR and a
  green gate, then re-bump after every main merge. L-0522 PR 1 (#377) reviewed with
  `--allow-unverified` for exactly this reason (its PR body).
- **Refresh is per review round, not per land.** `/crew:implement` step 6 refreshes before review
  (`plugin/crew/commands/implement.md:88-115`); autopilot refreshes before every review round
  (`plugin/crew/hooks/scripts/crew_autopilot.py:188-197`); `/crew:done` check 4 refuses anything not
  fresh (`plugin/crew/commands/done.md:55-66`). L-0522 PR 1 added a landing order after each catch-up
  (`plugin/crew/hooks/scripts/crew_train.py:1235-1237`, `done.md:106-115`): bump, refresh, commit, gate,
  re-review if stale. That is right for the LAST catch-up and pure overhead for every earlier one.
- **Why refresh must precede review today.** The review bundle excludes only `.work/`, `graphify-out/`
  and `.crew/metrics.md` (`plugin/crew/hooks/scripts/review_patch.py:135-136`), so a re-anchor after an
  accepted receipt stales it. L-0522 PR 2 (the delta gate, branch `L-0522-tooling`, unmerged, owned by
  crew-chat) keeps a receipt across an anchor-only re-anchor, regenerated rules, version tokens and
  bookkeeping prose (`review_delta.py` `EXEMPT_*`), but only while the clone's merge train is armed
  (owner decision 2026-10-03, that branch's head commit). T-0033 is to close as superseded when it lands
  (owner 2026-10-04, `.work/HANDOFF.md`).

## Options

1. **Land-time bookkeeping, gated by the armed train (recommended).** Two PRs under this ticket.
   PR 1 (repo gate, no crew content): `check-marketplace.py --pending-bump` reports a version-drift
   finding as a `pending at land:` line and exits 0 for that check only (every other check unchanged);
   verify rule 0 and CI's Marketplace job on a DRAFT pull request use it; a ready-for-review pull
   request and every push to main run the full check, so the stop-and-ask bug still cannot merge.
   REPO-03 says so. PR 2 (crew): when `crew_train.py status` says `armed: yes`, `/crew:implement`
   step 6 and autopilot run the refresh check read-only before review and report `pending at land`
   instead of refreshing; `/crew:done`'s landing sequence does catch-up, bump, refresh, commit, gate,
   delta-gate receipt check, `gh pr ready`, check-land, once. Unarmed clones keep today's order.
   Tradeoff: depends on L-0522 PR 2; two gates gain a mode; the reviewer reads code maps one re-anchor
   behind (acceptable: the delta gate admits only anchor-shaped changes at land).
2. **Process only: lanes stop pushing until land.** No code; the build branch is never pushed or
   opened as a PR until the land step, so CI runs once. Tradeoff: no CI signal during the build
   (Windows legs, self-hosted runners), and nothing enforces it; every lane prompt must obey prose.
   Rejected: the 2026-09-30 decisions asked for mechanism, and the Lessons rule "put the check where the
   evidence is dropped" applies.
3. **Exclude refresh artifacts and version files from the review bundle outright.** Simplest receipt
   story. Tradeoff: a reviewer never sees a hand-edited code map claim or a wrong version; it reverses
   the owner's 2026-10-03 decision that the delta gate keeps nothing unarmed, and it is a harness
   change (`review_patch.py`). Rejected.

## Recommendation

Option 1. PR 1 is small and independent (it only makes REPO-03 true in CI and the Stop gate). PR 2
waits for L-0522 PR 2: without the delta gate a land-time refresh stales the receipt and costs a
review round, which is worse than today.

## Open questions (default taken)

1. **How does CI tell a build branch from a land?** (A, taken) the PR's draft flag: drafts get
   `--pending-bump`, ready PRs and main get the full check; the land step runs `gh pr ready` after the
   bump. (B) a `land` label. (C) the head declares a version above main's. A is GitHub-native and is
   already how cloud-handoff PRs are opened (`--draft`).
2. **What happens unarmed?** (A, taken) today's order exactly (refresh before every review round). (B)
   land-time refresh anyway and pay the re-review. A keeps single-session users untouched.
3. **Graphify.** (A, taken) the graph rebuild moves to land in both modes: `graphify-out/` is already
   outside the bundle (`review_patch.py:135`), so moving it never stales a receipt. (B) leave it with
   the other refreshes.
4. **Can `--pending-bump` weaken main?** (A, taken) no: the flag is ignored, and the full check runs,
   when the checked-out branch is `main` (`git symbolic-ref --short HEAD`), and the script says so on a
   `note:` line. CI on main is a push to `main` and never passes the flag anyway. (B) trust callers.
