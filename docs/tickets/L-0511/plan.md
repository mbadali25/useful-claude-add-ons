# L-0511 plan            spec: docs/tickets/L-0511/spec.md

PR 1 only (repo gate, no crew content, no crew bump). PR 2 is deferred: it waits for L-0522 PR 2
(the delta gate, `review_delta.py`, a HARNESS path) to land on main through its own harness PR.

Measured at plan (read-only `gh api repos/mbadali25/useful-claude-add-ons/branches/main/protection`,
2026-10-05): required check `check` (this job), `strict: true`, no merge queue. A draft run's green
`check` would stand on the same head after `gh pr ready` with no new run, so the workflow adds
`ready_for_review` to `pull_request.types`: marking a PR ready re-runs the full check on that head.

### Step 1: `--pending-bump` (test-first)
Files: scripts/check-marketplace.py, scripts/_test/version-drift.py
Test: python3 scripts/_test/version-drift.py
- [ ] `main(argv)` takes `--pending-bump`; `pending_bump_applies()` is false on branch `main` (`git symbolic-ref --short HEAD`), with a `note:` line; a detached HEAD is not `main`
- [ ] only `check_versions` is routed to the pending list; `report()` prints `pending at land: <finding>` and exits 1 only on problems
- [ ] cases: `s_pending_bump_reports_and_passes`, `s_no_flag_still_fails`, `s_pending_bump_ignored_on_main`, `s_pending_bump_detached_head`, `s_pending_bump_keeps_other_failures` (the real `main()` with every other `check_*` stubbed)
- [ ] sabotage by hand: flag applies on main; flag ignored; drift routed to pending without the flag; registration routed to pending

### Step 2: CI, Stop gate, REPO-03
Files: .github/workflows/marketplace.yml, scripts/gate-runner.py, .crew/verify.json, .crew/standards.md, CHANGELOG.md
Test: python3 scripts/gate-runner.py --check-ci; python3 scripts/_test/gate-runner.py; python3 scripts/check-marketplace.py
- [ ] two `if:`-guarded steps: `draft != true` runs the full check, `draft == true` runs `--pending-bump`; `ready_for_review` in the trigger types
- [ ] gate-runner's check-marketplace step pins both CI strings (a lane still runs the full check)
- [ ] verify rule 0 runs `--pending-bump`; REPO-03 rule text and self-check say so
