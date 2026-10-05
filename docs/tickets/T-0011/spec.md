# T-0011 autopilot ship policy          status: spec   risk: high
## Intent
After `/crew:done` passes, `/crew:autopilot` ships the ticket under `autopilot.ship: pr|merge` (default `merge`). With `pr` it pushes the branch and opens a PR, then stops. With `merge` it also merges with a merge commit (D-028: squash and rebase rewrite the commits that refresh anchors name) once every required check is green, or failing only on a check named in `autopilot.knownFailures`. It never merges a `high`-risk ticket whose only reviews are same-family, and it never merges on a check state it could not read. Every merge is reported with the PR, the checks and the review families it rested on.
## Exclusions
- Depends on T-0004 (`next_phase`, `parse_risk`, the `autopilot` block); adds a `ship` phase after `done`, changes no earlier phase.
- No `gh pr merge --admin`, no bypass of branch protection, no force-push, no change to cloud_guard's `adminMerge` finding or to the mergeGate skill.
- No deploy, terraform or production write (T-0005); no goal/backlog continuation to the next ticket (T-0012).
- No guessing a known-fixture failure: only a check name listed in config counts.
- No approval or questions behaviour (T-0010).
## Evidence
- Merge today: cloud_guard flags `gh pr merge` only with `--admin` (`plugin/crew/hooks/scripts/cloud_guard.py:1131-1134`).
- Review families: each completed round row carries `model_family` (`plugin/crew/hooks/scripts/review_ledger.py:273`); the receipt has no family field (`:276-280`), so the family must be read from the rounds.
- Risk: T-0004's `crew_ticket.parse_risk` (unknown reads `high`).
- Known fixture failures exist on this repo's CI: the Windows fixture failures noted in `.work/HANDOFF.md` (T-0001 "Windows fixture failures are known").
- Codex (the only cross-family reviewer here) is out until 2026-10-01, so every review until then is same-family - `high`-risk tickets will stop at `ship: merge` until then, by design.
- Pre-split requirement: `.work/tickets/T-0004/spec.pre-split.md` (ship check); direction `.work/tickets/T-0004/direction.md` ("ship" bullet: owner's answer "merge when CI is green").
## Unknowns
- The exact `gh` surface for required checks on this machine's gh version (`gh pr checks --required --json name,state,bucket` vs parsing text): resolved in plan step 1 by reading `gh pr checks --help`; the decision function takes a parsed list, so only the adapter depends on it. An unreadable or pending state is never green.
- Author family: the session's own family is not recorded anywhere; a review is "same-family" when its `model_family` is `claude` OR absent (unknown counts as same-family, the refusing direction).
- CI wait: `autopilot.ciTimeoutMinutes` (default 60); still pending at the timeout -> stop, never merge.
- Codex out until 2026-10-01: this ticket's review is same-family - accepted as risk and announced.
- Owner decision - how required checks are read (review round 2). gh 2.46's `gh pr checks` has no `--json`, and its non-TTY rows are tab-separated with the check name and the description printed unescaped, so a tab inside either shifts every field after it; no text parser can tell those rows apart. Recommendation: keep the text adapter and make it fail closed - a row whose field count is not the count measured from this machine's gh 2.46 on a real PR (recorded in the step's commit and in a comment beside `_BUCKETS`) makes the whole read unreadable, so ship stops and never merges. The cost is that a repository whose required check name or description holds a tab never ships unattended. Rejected for now: reading required checks through `gh api graphql` (`statusCheckRollup` with `isRequired`), which returns exact names but replaces the adapter the plan and the tests are built on; it is the follow-up if the owner wants tab-bearing names to ship.
- Owner decision - a merge gh queues after the preflight said no queue (review round 2). `read_merge_queue` reads False, a queue is enabled before `gh pr merge` reads the PR, gh queues the PR instead of merging it, and ship then stops on OPEN while the queued merge proceeds with the queue's own method (D-028). Recommendation: after any merge call that does not leave the PR MERGED, read `isInMergeQueue` again; when it is true or unreadable, run the GraphQL `dequeuePullRequest` mutation once for the PR's node id, and stop naming the queue and whether the dequeue succeeded. It adds one mutating gh call, used only to undo ship's own action. Rejected: stopping with a message only (the queued merge still lands, squashed), and enabling nothing but documenting the window (the reviewer showed it is reachable).
## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_config.py`
- `plugin/crew/templates/config.template.json`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_autopilot_ship.py`
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/skills/crew-setup/SKILL.md`
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/CONFIG.md`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
- `TODO.md`
## Acceptance checks
- [ ] `ship_decision(policy, risk, checks, families, known_failures) -> {"action": "open-pr"|"merge"|"wait"|"stop", "reason"}` in `test_crew_autopilot_ship.py`: `pr` never merges; `merge` merges only when every required check is `pass` or a failing check is listed in `knownFailures`; pending -> wait; unreadable -> stop
- [ ] never merges a `high` or unknown-risk ticket whose completed review rounds are all same-family (`claude` or missing `model_family`); a cross-family round allows it (tests)
- [ ] `next_phase` gains `ship` after `done`: PR state read via `gh pr view --json state`; MERGED -> `closed`; `pr` with an open PR -> `closed` with "PR open, merge by hand"; `gh` failure -> stop (tests with a stubbed adapter)
- [ ] the merge command is exactly `gh pr merge <n> --merge` (never `--squash`, `--rebase` or `--admin`), asserted by a test on the built argv
- [ ] `autopilot.ship` (default `merge`), `autopilot.knownFailures` (default `[]`) and `autopilot.ciTimeoutMinutes` (default 60) in defaults and the template; a bad `ship` value reads as `pr` and says so; `test_crew_config.py` leaf count re-measured
- [ ] sabotage: merging on pending, dropping the same-family refusal, treating a missing `model_family` as cross-family, and matching known failures by substring each turn a named test red
- [ ] `.crew/verify.json` maps the new test; crew version 1.0.34 with a CHANGELOG entry; README and CONFIG.md document the three keys and the Codex-outage consequence
