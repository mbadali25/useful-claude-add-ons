# Feature rush 1.2.0 — group builder brief

Repo: `/home/user/useful-claude-add-ons` (origin `mbadali25/useful-claude-add-ons`). Integration
branch: `release/1.2.0` (cut from main `e84a8bfe`, crew 1.0.351). Every group branch is cut from
`origin/release/1.2.0` and its PR targets `release/1.2.0`. Scratchpad (call it `$S`):
`/tmp/claude-0/-home-user-useful-claude-add-ons/cf8010ca-0ad0-5d92-8922-7bbd28b697af/scratchpad`.

## Read first (mandatory)

1. `CLAUDE.md` at the repo root. It is policy and wins over this brief on any conflict.
2. `.claude/skills/steward/SKILL.md`.
3. `scripts/check-tooling-pr.py` — the `HARNESS` and `SEAM` tuples.

## Setup

```
cd /home/user/useful-claude-add-ons && git fetch origin -q
git worktree add /home/user/rush-<group> -b rush/<group> origin/release/1.2.0
```
Work only in your worktree. Never touch `/home/user/useful-claude-add-ons` itself, `main`, another
group's branch, or another worktree. Push only `rush/<group>` (`git push -u origin rush/<group>`).
Do NOT open PRs, merge PRs, comment on GitHub, or close anything — the coordinator does that.

## Per assigned PR, in the order given

**Real-code PR (branch is far behind main):** port it. Try `git merge --no-ff origin/<branch>` into
your group branch first; resolve conflicts by reading both sides (main has moved ~1,000+ commits:
the old code may already be partly on main, renamed, or superseded — check before re-adding). For
`graphify-out/`, `.claude/rules/`, code-map anchor lines and diagrams: take your side
(`git checkout --ours`), never hand-edit `graphify-out/`. If a merge is hopeless, instead re-apply
the PR's intent by hand on top of current code (`git diff <merge-base> origin/<branch>`), commit
with a message naming the PR and ticket. If the work is already fully on main, record it as
"superseded" with the evidence (commit sha) and move on.

**Docs-only handoff PR (`docs/tickets/<T>/HANDOFF.md`, `spec.md`, `direction.md`):** build it.
Bring the three docs files in (merge the branch), read all three, write `docs/tickets/<T>/plan.md`
if the spec says the implementer writes the plan, then implement test-first exactly to the spec's
acceptance list. Scope = the spec; nothing nearby.

**Blocked** (the HANDOFF says "not buildable" and the prerequisite is not on your branch / main):
skip it, report why. Do not build prerequisites that are not assigned to you.

## Rules that bite

- **Harness-alone (T-0087).** If a change needs a `HARNESS` path (sabotage_*.py, review_*.py,
  scope_guard, verify-gate, crew_ticket.py, approval hook, completion_audit …), do NOT commit that
  part. Build the feature half, and report the harness half as a follow-up (file list + what it
  needs). `python3 scripts/check-tooling-pr.py` must exit 0 on your branch before you push.
- **Versions.** In your LAST commit set crew to the placeholder version you were given in
  `.claude-plugin/marketplace.json` AND `plugin/crew/.claude-plugin/plugin.json` (plus any
  `<!-- claim: plugin-version:crew -->` line). Any other plugin/skill you changed: bump its patch
  in every place it is declared. The coordinator re-bumps at landing.
- **Line budgets.** `plugin/crew/commands/*.md` are line-budgeted
  (`plugin/crew/.budget-allowance.json`, `plugin/crew/BUDGETS.md`); edit in place.
- **Registration** of any new skill/plugin = every place in the same commit (CLAUDE.md "Scope").
- **Install scripts** are a matched pair. **Hooks** default OFF and need must-block/must-allow tests.
- Landmines in CLAUDE.md (open(p,"w"), newline="\n" for .sh, pwsh absolute path) apply.
- Commit trailer: end every commit message with exactly
  `Claude-Session: https://claude.ai/code/session_01QLY3kk7DCXpucXGu3wSniW` (no Co-Authored-By;
  owner rule). Never put a model name in a commit.

## Tests (the machine has 4 cores; five builders share it)

Wrap EVERY pytest / suite run in the shared lock so builders take turns:
`flock $S/heavy.lock <command>`. Run targeted tests only (the files the ticket touches and their
tests, per `.crew/verify.json`'s rules for your paths), `-p no:randomly -x -q`, no `-n` above 2.
Cheap checks without the lock: `python3 scripts/check-tooling-pr.py`,
`python3 scripts/check-marketplace.py` (commit FIRST, then run it). CI runs the full suite.

## Codex review per ticket (mandatory)

After each ticket's commits, run
`$S/codex-review.sh /home/user/rush-<group> <sha-before-this-ticket> <group>-<T>`
(model gpt-6-sol, high reasoning, read-only). It prints `verdict=… block=n fix=n nit=n` and writes
JSON to `$S/reviews/`. Fix every BLOCK and FIX (verify each first — if a finding is wrong, record
why in your report instead of changing code), commit, and re-run the review on the same range until
block=0 fix=0. NITs: apply the plainly-correct ones. It takes minutes; run it in the background and
start reading the next ticket meanwhile if you like, but finish the loop before you report.

## Report (your final message, concise)

A table: PR | ticket | outcome (ported / built / superseded / skipped-blocked / partial) | commits |
tests run (and result) | codex verdict on final round | harness follow-ups | notes. Then: branch
head sha, `check-tooling-pr.py` and `check-marketplace.py` exit codes, anything you did NOT verify,
and any new work you found that needs a ticket (one line each: title, why, blocked-by).

## Addendum for HARNESS lanes (groups named h*)

- Base and target are `main`, not `release/1.2.0`: `git worktree add /home/user/rush-<group> -b rush/<group> origin/main`.
- The branch must be harness-ONLY (owner rule T-0087): `HARNESS` paths plus what may ride along
  (tests, docs, version files, code map, graph). Any feature/production code outside `HARNESS` in a
  source PR is NOT committed here: report it as a feature half (files + intent) so the coordinator
  routes it to a release group. `SEAM` files only with a `Tooling-seam: <path>` trailer per CLAUDE.md.
- Run what `.crew/verify.json`'s harness rule lists when a `HARNESS` path changes (check-tooling-pr,
  `scripts/_test/tooling-pr.py`, the golden replay, the seam contracts; the canary review only if it
  can run here — say if it cannot). Wrap heavy runs in the flock as usual.
- A sabotage entry for a feature that is not on `main` or `release/1.2.0` yet: skip and report.

## RESUME after a container restart (2026-10-05 ~10:45 UTC)

The container restarted and killed every builder mid-flight. Your worktree, its commits, any
uncommitted edits, and `$S/reviews/` survived. Every branch's committed state was pushed by the
coordinator right after the restart.

1. Do not re-create the worktree. `cd` into it, then read `git status`, `git log --oneline
   <base>..HEAD` and `git diff` (uncommitted = work in progress from before the restart: finish it,
   or discard it with a stated reason). Ignore any extra detached worktrees (`rush-*-review*`).
2. `ls -t $S/reviews/ | grep '^<group>-'` and read the newest JSON for each ticket: it tells you
   where its codex loop stood (BLOCK/FIX findings still open, or CLEAN).
3. A suite or review that was running when the container died did not finish: rerun it.
4. NEW RULE: `git push` after EVERY commit (not after each ticket).
5. Continue the ticket list in order. Tickets with a CLEAN final review and green targeted suites
   are done; don't redo them.
