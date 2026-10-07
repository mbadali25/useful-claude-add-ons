# L-0511: version bump and artifact refresh happen once at land, after the final catch-up merge          status: spec   risk: high
Decision 5 of the owner's 2026-09-30 CI/review/QA decisions ("All recommended"). Written against origin/main
`a555ff37` (crew 1.1.0). PR 1 is buildable now. **PR 2 is not buildable until L-0522 PR 2 (the delta gate,
branch `L-0522-tooling`) has merged**; re-find every line by content then.

## Intent
A build branch carries no version bump and no refreshed artifacts. All release bookkeeping (the version bump
one past the base, code map and diagram re-anchors, `.claude/rules/` regeneration, the graphify rebuild) runs
ONCE, at land, after the final catch-up merge, and the gate and delta-gated receipt then cover the tree that
lands. PR 1 makes the repo's gates agree with REPO-03: `scripts/check-marketplace.py --pending-bump` reports
version drift as `pending at land:` and exits 0 for that check alone; verify rule 0 and CI's Marketplace job
on a draft pull request pass it; a ready pull request and every push to `main` run the full check, so a
content change with no bump still cannot merge. PR 2 moves crew's refresh to land when the clone's merge train
is armed: `/crew:implement` step 6 and autopilot run the refresh check read-only and report `pending at land`
instead of refreshing before review, and `/crew:done`'s landing sequence runs catch-up, bump, refresh, commit,
gate, receipt check (L-0522's delta gate keeps it), `gh pr ready`, then `check-land`. An unarmed clone keeps
today's order exactly.

## Exclusions
- No change to the review bundle or the ledger (`review_patch.py`, `review_ledger.py`, `review_delta.py`):
  those are harness paths and the receipt rule is L-0522's. This ticket consumes the delta gate; it does not
  widen it.
- No change to what counts as drift, to `bump_candidates`, or to any other `check-marketplace.py` check: only
  the version-drift finding changes severity, and only under `--pending-bump` off `main`.
- No change to CLAUDE.md (owner's file). Its "Commit, then run it, then push" line stays true for a ready PR.
- No change to the unarmed path: with `crew_train.py status` not `armed: yes`, `implement.md` step 6,
  autopilot's `_toward_review` and `done.md` check 4 behave byte-for-byte as on `a555ff37`.
- No new config key (armed-ness is the train's, per L-0520), no new hook, command, skill or agent.
- No change to the machine-local lane scripts; the PR body says what they must change (stop re-bumping on
  catch-up; open PRs as drafts; land via `/crew:done`'s sequence).
- No sabotage entries in this ticket's PRs (`plugin/crew/tests/sabotage*.py` is a harness path): a follow-up
  tooling-only ticket carries them; `scripts/_test/version-drift.py` is not harness and gains its cases here.

## Evidence
origin/main `a555ff37` unless marked:
- REPO-03 rule: `.crew/standards.md:73-86` ("the build branch carries none ... version-drift check reports
  ... on a build branch ... expected until landing and is not a finding"); self-check `:91-96`.
- Version drift: `check_versions` `scripts/check-marketplace.py:518-550` (`fail(...)` "has changed since
  version {version} was set" `:545-550`); `main()` `:1796`. Its suite `scripts/_test/version-drift.py`
  (`run_check` `:115`, cases from `:130`), verify rule `.crew/verify.json:111`.
- CI runs it on every pull_request, drafts included: `.github/workflows/marketplace.yml:6-10` (`on: push:
  [main]`, `pull_request:`), step `:41-42`. `scripts/gate-runner.py:153-154` pins that CI command string
  (`ci=(("marketplace.yml", "python3 scripts/check-marketplace.py"),)`), checked by `scripts/_test/gate-runner.py`.
- Verify rule 0 at Stop: `.crew/verify.json:80-86` (`"run": ["python3 scripts/check-marketplace.py"]`).
- Build-branch review blocked by drift: PR #377 body ("Both rounds ran with `--allow-unverified`, because the
  gate's only failure was the version drift expected on a build branch (REPO-03)").
- Refresh before review: `plugin/crew/commands/implement.md:88-115` (`:94` the check, `:105` "Commit the
  refresh before `/crew:review $1` builds its bundle", `:114-115`); ordering pinned by
  `plugin/crew/tests/test_refresh_check.py:545` (`test_implement_refreshes_between_docs_and_review`) and `:814`.
- Autopilot: `plugin/crew/hooks/scripts/crew_autopilot.py:188-197` ("Refresh runs after implement and before
  every review round, never after an accepted receipt"), `_refresh_state` `:861`, `_toward_review` (search
  `def _toward_review`), `stale-after-review` phase (README `plugin/crew/README.md:915`).
- Done: check 4 `plugin/crew/commands/done.md:55-66`; landing `:98-115` (order `:110-112`). done.md is 115 of
  120 lines; implement.md is 120 of 120 (`plugin/crew/BUDGETS.md` "Command file budget" `:32-36`).
- Landing order: `LANDING_ORDER` `plugin/crew/hooks/scripts/crew_train.py:1235-1237`, used `:1268`, `:1275`;
  pinned by `plugin/crew/tests/test_crew_train.py:556`, `:562`, `:934`.
- Bundle exclusions: `plugin/crew/hooks/scripts/review_patch.py:135-136` (`.work/`, `graphify-out/`,
  `.crew/metrics.md`).
- Docs that state the current order: `plugin/crew/README.md:824` ("The order is implement, then refresh
  artifacts, then review, then done"), `:926`, train section `:785-791`;
  `docs/guides/crew/src/daily-workflow.md:105-118`; `docs/guides/crew/src/troubleshooting.md:198`, `:217`.
- Delta gate (branch `L-0522-tooling` `ddd9b2a7`, not on main): `plugin/crew/hooks/scripts/review_delta.py`
  docstring `:1-47`, `EXEMPT_ANCHORED`/`EXEMPT_PROSE`/`EXEMPT_MANIFEST`; head commit "say the delta gate
  keeps nothing until the clone's merge train is armed (owner decision 2026-10-03)".
- Measured overhead: the seed (`direction.md`): 57% of commits are overhead, 2.3 catch-ups per PR, from
  `.work/ci-review-2026-09-30/` (gitignored; copy the cited rows into `docs/tickets/L-0511/` if the PR quotes them).

## Unknowns
- **Draft detection in CI** (default taken): `github.event.pull_request.draft`; the job passes
  `--pending-bump` only when it is `true`. A `ready_for_review` event must re-run the job: add `types:
  [opened, synchronize, reopened, ready_for_review]` to `pull_request` if the default set lacks it.
- **gate-runner's pinned CI string**: whether `scripts/gate-runner.py`'s step table can express two CI
  invocations of one step; if not, add a second step entry. Decided at plan from its suite.
- **Merge queue / branch protection**: whether `main`'s required checks run on the ready PR's last head.
  Measured at plan with `gh api repos/{owner}/{repo}/branches/main/protection` (read-only); if a required
  check could pass on a draft run and stay green after `gh pr ready` with no new run, the land step pushes or
  re-runs the job after `ready`.
- **Rule 0 on a detached HEAD** (a CI merge ref): `--pending-bump` applies when HEAD is detached; only the
  branch name `main` disables it.
- **Delta gate shape after merge**: PR 2's receipt step uses whatever `review_ledger.check_receipt` returns
  once L-0522 PR 2 lands; anchors re-read then.
- Next free crew patch version set at land (main is 1.1.0 at `a555ff37`).

## Size and split
PR 1: about 40 production lines (`check-marketplace.py` flag and branch test, workflow condition, verify rule
0), 4-6 `version-drift.py` cases, REPO-03 text. No crew plugin content, so no crew bump. PR 2: about 80
production lines (`crew_autopilot.py` routing on armed-ness, `crew_train.py` `LANDING_ORDER` text) plus
command and doc text, and ~10 tests. Two PRs under one ticket, PR 1 first; PR 2 after L-0522 PR 2. No harness
path in either (checked against `HARNESS` in `scripts/check-tooling-pr.py:58-87`); `crew_autopilot.py` is a
SEAM path (`:89-95`) and lands as ordinary feature code here.

## Touch
PR 1:
- `scripts/check-marketplace.py`
- `scripts/_test/version-drift.py`
- `.github/workflows/marketplace.yml`
- `scripts/gate-runner.py` and `scripts/_test/gate-runner.py` (only if the pinned CI string changes)
- `.crew/verify.json` (rule 0's `run` and `why`)
- `.crew/standards.md` (REPO-03 rule and self-check)
- `CHANGELOG.md`
- `docs/tickets/L-0511/`

PR 2:
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_train.py`
- `plugin/crew/commands/implement.md`
- `plugin/crew/commands/done.md`
- `plugin/crew/tests/test_crew_autopilot_status.py` (or the autopilot suite that holds the refresh rows)
- `plugin/crew/tests/test_crew_train.py`
- `plugin/crew/tests/test_refresh_check.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/README.md` (artifacts paragraph, autopilot table and "Refresh sits between" paragraph, train section)
- `plugin/crew/CONFIG.md` only if a key is touched (expected: none; PR body says `Docs: none - CONFIG.md, no config key`)
- `docs/guides/crew/src/daily-workflow.md`, `docs/guides/crew/src/troubleshooting.md`, `docs/guides/crew/src/auto-cycle.md`
- `docs/guides/crew/**` - HTML, DOCX and PDF rebuilt by `docs/guides/crew/src/build.py`
- `docs/diagrams/process-crew-lifecycle*.mmd` and their rendered pages (the implement/done refresh edges)
- `.crew/codemap/crew.md`, `.crew/codemap/INDEX.md`
- `CHANGELOG.md`, `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`
- `docs/tickets/L-0511/` (removed in the final PR)

Not in Touch: `review_*.py`, `completion_audit.py`, `scope_guard.py` (harness); `crew_refresh_check.py`
(its verdicts are unchanged; only who acts on them changes); CLAUDE.md.

## Acceptance checks
Commands from the repo root; pytest through the heavy-run wrapper on a memory-bound host.
PR 1:
- [ ] On a fixture branch that changed plugin content under main's version, `check-marketplace.py
  --pending-bump` prints `pending at land: <plugin>: ...` and exits 0 when no other check fails; without the
  flag it exits 1 with today's message. `python3 scripts/_test/version-drift.py` (new cases
  `s_pending_bump_reports_and_passes`, `s_no_flag_still_fails`).
- [ ] On a fixture with branch `main` checked out, `--pending-bump` is ignored, a `note:` line says so, and
  drift exits 1. `python3 scripts/_test/version-drift.py` (case `s_pending_bump_ignored_on_main`).
- [ ] `--pending-bump` changes no other check: a fixture with drift AND an unregistered plugin exits 1 naming
  the registration. `python3 scripts/_test/version-drift.py` (case `s_pending_bump_keeps_other_failures`).
- [ ] Sabotage by hand, quoted in the PR: make `--pending-bump` apply on `main` and confirm
  `s_pending_bump_ignored_on_main` goes red; drop the flag check and confirm `s_pending_bump_reports_and_passes` goes red.
- [ ] `marketplace.yml` passes `--pending-bump` only when `github.event.pull_request.draft` is true and runs on
  `ready_for_review`: `grep -n "pending-bump\|ready_for_review" .github/workflows/marketplace.yml` shows both,
  and `python3 scripts/_test/gate-runner.py` passes.
- [ ] `python3 scripts/check-marketplace.py` exits 0 at the PR's head (no plugin content changed in PR 1).
PR 2 (armed train fixtures; unarmed fixtures for the must-allow side):
- [ ] Armed: autopilot's phase after implement is `review` with reason `artifacts pending at land` when the
  refresh check says `stale`, and never `refresh`; unarmed: the phase is `refresh` exactly as today.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_status.py -q -k "pending_at_land or unarmed_refreshes_before_review"`
- [ ] Armed: a `receipt current, artifacts not fresh` state routes to the land sequence, not
  `stale-after-review`; unarmed it stays `stale-after-review`. `-k "armed_stale_after_review_goes_to_land or unarmed_stale_after_review_stops"`
- [ ] An unreadable train state (`crew_train.py status` exit 3) reads as could-not-tell and keeps today's
  order, never as armed or unarmed silently; the reason names it. `-k train_state_unknown_keeps_todays_order`
- [ ] `LANDING_ORDER` names, in order: bump, refresh, commit, gate, receipt check, `gh pr ready`, check-land;
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_train.py -q -k "landing_order"`
- [ ] `implement.md` step 6 says the armed path reports `pending at land` and the unarmed path refreshes before
  review; `done.md` states the land sequence once; both stay within budget (implement.md 120, done.md 120).
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_refresh_check.py plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] Both guides state the land sequence (`test_guides_state_landing_order_after_every_catch_up` updated):
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_train.py -q -k guides_state_landing_order`
- [ ] At the PR's head after the land sequence: `python3 scripts/check-marketplace.py` exits 0 (no flag) and
  `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0511` prints `fresh`.
- [ ] `python3 scripts/check-tooling-pr.py` reports no harness path changed, for each PR.

## Dependencies
- L-0522 PR 2 (delta gate, branch `L-0522-tooling`, crew-chat's, paused): must merge before PR 2. Not
  before PR 1.
- L-0520 / L-0558 (merged): the train and its `status`. L-0526 (planned): `review_run.py` takes the train;
  independent.
- T-0033 (ready, owner: close as superseded when L-0522 PR 2 lands): not needed.
- L-0620 (direction): receipt fast path; independent.
- Coordinates with the machine-local lane scripts (not in the repo): PR body lists their changes.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve authority, 2026-10-05. Plan: to be written by the implementing session.
