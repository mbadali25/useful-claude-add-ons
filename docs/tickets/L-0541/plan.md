# L-0541 plan - mint the approved split, drive the goal's tickets, per-ticket approval, caps, `--goal` resume

Written by the implementing session, 2026-10-05, on `rush/g6b-goals-sleep` (T-0012's port on
`rush/g2-autopilot` merged with `release/1.2.0`). Every anchor below was re-found by content.

## Decisions on the spec's Unknowns

- **Where the code lives.** `crew_autopilot.py` is over pylint's module limit, so the goal run is a new
  module, `crew_autopilot_backlog.py`: the picker, the mint loop, the caps, the run record and the
  per-ticket approval. `crew_autopilot.py` gains only call sites: `settings` arming on `backlog`,
  `resume_target(goal=)`, the handoff's goal branch, `route`'s `--goal <slug>`, status's resume line.
- **Mint runs inside `goal-approve`.** After `split_approved` says yes, the same call mints every ticket
  that has no id, in list order. A re-run after a failure mints only what is missing. Each minted
  direction.md carries `goal-ticket: <slug> <n>/<m>`; a ticket folder already carrying that line is
  adopted rather than minted again (the window between `mint` returning and the id reaching the goal file).
  The goal file is written under `.work/autopilot/<slug>.lock` (exclusive create; a lock that is there
  stops, naming the file).
- **Which transcript.** `goal-run --session <id>` (the command passes `${CLAUDE_SESSION_ID}`), resolved to
  `<CLAUDE_CONFIG_DIR or ~/.claude>/projects/*/<id>.jsonl`; exactly one match is the transcript.
  `--transcript <path>` overrides. No id, a malformed one, no match or several: the token cap reads
  "could not tell" and stops.
- **Pointer.** A goal-picked ticket may replace an active pointer that names another ticket of the same goal
  which is closed: `resume_target` answers `activate=1` instead of the mismatch stop. Any other pointer still stops.
- **`runs` shape.** `{"started", "session", "tickets": [ids]}`; one entry per session id. The ticket cap
  counts the current entry's ids. T-0056 adds its run state beside it.
- **Closed and stopped.** INDEX `done|closed|merged|shipped|complete|completed`, or a spec header `done`,
  is closed. INDEX `cancelled|superseded|needs-owner`, or a header `cancelled|superseded`, stops the picker
  naming that ticket. A ticket with no INDEX row, or a spec that cannot be read, is "could not tell": a stop.
- **Layers.** `autopilot.mode` gains the tier `backlog` above `plan` (`crew_guards.PERSONAL_KEYS`), so where
  both files set it the stricter wins as before. The two cap keys are repo-only (`REPO_ONLY_AUTOPILOT`).
  `crew_guards.py` is outside the spec's Touch list; without the tier a machine `plan` and a repo `backlog`
  would rank `backlog` below the floor and return it raw, arming backlog. Noted in the PR.

## Steps

### Step 1: keys, arming and the token fields
Files: crew_state.py, crew_guards.py, crew_keys.py, crew_config.py, crew_autopilot.py (`_settings_at`),
crew_metrics.py, templates/config.template.json, CONFIG.md, test_crew_config.py, test_crew_metrics.py,
test_crew_autopilot_backlog.py
- `AUTOPILOT_DEFAULTS` gains `maxTicketsPerRun: 3`, `maxTokensPerSession: 2000000`; the COMING rows and the
  L-0541 INERT_PENDING rows go; `settings` reports `maxTicketsPerRun`, `maxTokensPerSession`, and arms on
  exactly `plan` or `backlog`.
- `transcript_tokens(path, fields=TOKEN_FIELDS)`.

### Step 2: mint on approval
Files: crew_autopilot_backlog.py, crew_autopilot_goal.py, test_crew_autopilot_backlog.py, test_crew_autopilot_goals.py

### Step 3: picker, run record, caps, per-ticket approval
Files: crew_autopilot_backlog.py (`next_goal_ticket`, `goal_run`, `ticket_approve`), crew_autopilot_goal.py
(`goal-run`, `goal-approve --ticket`), test_crew_autopilot_backlog.py

### Step 4: `--goal` resume and the command
Files: crew_autopilot.py (`route`, `route_args`, `resume_target`, `_handoff_ticket`, `_resume_line`, `main`),
commands/autopilot.md, test_crew_autopilot_status.py, test_crew_autopilot_goals.py, test_lifecycle_commands.py,
test_crew_autopilot_policy.py

### Step 5: docs
README, CONFIG.md, the guide sources (rebuilt), codemap, CHANGELOG, BUDGETS.

Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_backlog.py plugin/crew/tests/test_crew_autopilot_goals.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_crew_metrics.py -q
