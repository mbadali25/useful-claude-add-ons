# T-0004 crew autopilot: drive a ticket through the phases unattended          status: spec   risk: high
## Intent
`/crew:autopilot` drives one ticket from direction to done without a human at every gate: `next` names the phase a ticket is in and the one action that moves it on, `resume` picks a run back up after a clear, an approval and a question policy decide who says yes, a mint path turns a goal into tickets, and a ship policy opens and merges the PR once every required check is green.
## Exclusions
- No deploy, terraform or production write.
- No change to the scope guard's or the approval hook's blocking rules.
- No bypass of branch protection, no `--admin` merge, no force-push.
## Evidence
- The phase vocabulary is the INDEX status column and the spec header's `status:`.
- Approval receipts are written by `crew_ticket.approve`.
## Unknowns
- How required checks are read from `gh` on this machine.
- Who answers a question when the owner is away.
## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_ticket.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_config.py`
- `plugin/crew/hooks/scripts/crew_resume.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/templates/config.template.json`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/CONFIG.md`
- `plugin/crew/README.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
- `TODO.md`
## Acceptance checks
- [ ] `next_phase(top, ticket)` returns the phase and the one next action for every INDEX status, and an unreadable INDEX row is a stop, never a phase (tests)
- [ ] `resume` after a clear reads the run record and continues from the recorded phase without repeating a completed one (tests)
- [ ] `crew_autopilot.py next` and `resume` print one line each and exit 0, or name the stop and exit 1 (tests)
- [ ] the `autopilot` block (`mode`, `approval`, `questions`) is in the defaults and the template, and a bad value reads as the refusing one and says so (tests)
- [ ] `autopilot.approval: human|self|risk` decides who approves a plan; `human` always stops for the owner (tests)
- [ ] `risk` self-approves only a `low`-risk ticket, and an unknown risk reads as `high` (tests)
- [ ] `autopilot.questions` decides whether an open question stops the run or takes the recommendation, and the answer is recorded in the spec (tests)
- [ ] after `/crew:done` passes, `autopilot.ship: pr|merge` opens the PR, and `merge` merges only when every required check is green (tests)
- [ ] the merge command is exactly `gh pr merge <n> --merge`, never `--squash`, `--rebase` or `--admin` (tests)
- [ ] a `high`-risk ticket whose reviews are all same-family is never merged unattended (tests)
- [ ] `/crew:autopilot goal <file>` mints one ticket per goal line, `ready`, with a direction pointing back to the goal (tests)
- [ ] `.crew/verify.json` maps the new tests; crew version bumped with a CHANGELOG entry; README and CONFIG.md document every new key
