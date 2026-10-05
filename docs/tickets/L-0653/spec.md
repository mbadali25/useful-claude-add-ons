# L-0653 sleep log and morning summary          status: spec   risk: med
Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`. T-0053 and L-0652 must be
merged first; re-read their code before planning.

## Intent
Every decision autopilot makes while asleep is appended to one local log with the ticket, what was
decided and the setting that allowed it. When sleep has ended, the next autopilot run and `wake`
print the entries not yet reported, once.

## Design
- Log: `.work/autopilot/sleep-log.md`, append-only, one line per entry:
  `- <ISO local time> | <ticket> | <kind> | <text> | <setting>`, where `<kind>` is `approved`,
  `answered` or `note`, and `<setting>` is for example `sleep.approval=self (day risk)`. Every
  field is folded to one line and `|` inside a field is replaced, so no field can forge a second
  entry.
- Writers:
  - `approve` appends an `approved` entry after the receipt is written, only when the state is
    `asleep`. A log that cannot be written does not undo the approval; the command prints
    `warning: sleep log not written (<why>)`.
  - `crew_autopilot.py sleep-note --root . --ticket <id> --kind answered|note --text "<one line>"`
    appends one entry, only while asleep; awake it exits 2 and writes nothing. The command
    procedure calls it after each `taken:` line it adds.
- Summary: `crew_autopilot.py sleep-summary --root .` prints the entries after the last
  `- reported <ISO time>` marker line, grouped by ticket, then appends a new marker. With nothing
  unreported it prints `no unreported sleep decisions` and writes nothing. Asleep, it prints the
  entries and writes no marker.
- Trigger: `settings` adds `warning: <n> sleep decisions are unreported - run crew_autopilot.py
  sleep-summary` when the state is not `asleep` and unreported entries exist. `wake` prints the
  summary itself after changing state.
- A log that exists and cannot be read: `settings` warns "sleep log could not be read", and
  `sleep-summary` exits 1. It never reads as "nothing to report".

## Exclusions
- No Telegram, email or other send (L-0656, after T-0051).
- No log of review verdicts, phase runs or deploys. Deploy entries arrive with T-0045's consumer.
- The log is never committed and never read to make a decision: it grants nothing.
- No rotation or trimming.
- No edit to a harness path; no sabotage mutations (L-0655).

## Evidence
Read at origin/main `155fe6d8`.
- plugin/crew/hooks/scripts/crew_autopilot.py:1129-1151 `approve`; :1145-1147 the
  `crew_ticket.approve` call the log entry follows. :1558-1559 `_one_line`. :1602-1616
  `_policy_main`. :1725-1729 the `settings` CLI.
- plugin/crew/commands/autopilot.md section 3 ("add `taken: Option <id> by autopilot (<policy>)`")
  and section 5 (the final report lists every `self-approved` and `taken:` line).
- plugin/crew/tests/test_crew_autopilot_policy.py:682 the only-writer test, which L-0652 extended.
- .gitignore:273 ignores `.work/` entirely.
- CLAUDE.md landmine: `open(p, "w")` truncates before the payload exists. The log is opened in
  append mode with the full line already built.

## Unknowns
- Two worktrees of one repo have two `.work/` directories, so two logs. Accepted: each run reports
  what it did. Stated in CONFIG.md.
- Concurrent appends from two sessions in one worktree. Resolved at implement: one `write` call of
  one line under `O_APPEND`; a test appends from two processes and counts lines.
- Whether `autopilot.md` has a line to spare for the `sleep-note` call. Resolved as in L-0652:
  reword inside the budget, else stop and ask.

## Touch
- plugin/crew/hooks/scripts/crew_sleep.py
- plugin/crew/hooks/scripts/crew_autopilot.py
- plugin/crew/commands/autopilot.md
- plugin/crew/tests/test_crew_autopilot_sleep.py
- plugin/crew/tests/test_crew_autopilot_policy.py
- plugin/crew/tests/test_lifecycle_commands.py
- plugin/crew/CONFIG.md
- plugin/crew/README.md
- plugin/crew/BUDGETS.md
- plugin/PLUGINS.md
- docs/guides/crew/src/daily-workflow-scope.md
- `docs/guides/crew/**` - rebuilt outputs
- .crew/codemap/crew.md
- .crew/verify.json
- `.claude/rules/**` - regenerated with the code map
- `graphify-out/**` - rebuilt by graphify update
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json

## Acceptance checks
New tests go in `plugin/crew/tests/test_crew_autopilot_sleep.py`.
- [ ] `approve` asleep appends exactly one `approved` entry naming the ticket and the setting;
  awake it appends nothing.
  `python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q -k test_approve_asleep_logs_one_entry`
- [ ] `sleep-note` asleep appends one entry; awake it exits 2 and the log is byte-identical.
  `-k test_sleep_note`
- [ ] Injection: a `--text` holding a newline, a `|` or a line starting `- reported` produces one
  entry and no marker. `-k test_log_fields_cannot_forge_an_entry`
- [ ] `sleep-summary` awake prints the unreported entries grouped by ticket and appends one
  marker; a second run prints `no unreported sleep decisions` and leaves the log byte-identical.
  `-k test_summary_reports_once`
- [ ] `sleep-summary` asleep prints and writes no marker. `-k test_summary_asleep_marks_nothing`
- [ ] `settings` awake with unreported entries prints the warning with the right count; with none
  it does not. `-k test_settings_names_unreported_decisions`
- [ ] `wake` prints the summary after its state line. `-k test_wake_prints_the_summary`
- [ ] Unreadable log: `settings` warns, `sleep-summary` exits 1, neither prints "no unreported".
  `-k test_unreadable_log_is_not_empty`
- [ ] A log directory that cannot be created does not fail `approve`: exit 0, the receipt stands,
  the warning is printed. `-k test_approve_survives_an_unwritable_log`
- [ ] Only-writer test: `sleep-note` and `sleep-summary` write exactly
  `.work/autopilot/sleep-log.md`. `python3 -m pytest plugin/crew/tests/test_crew_autopilot_policy.py -q -k only_writing`
- [ ] `autopilot.md` at most 110 lines: `python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` exits 0; no `HARNESS` path in the diff.
- [ ] Docs: CONFIG.md section 20 and README describe the log, its location, that it is local and
  ignored, and the summary trigger; guide outputs rebuilt. Crew bumped with a CHANGELOG entry;
  `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0053 (ready; slice 1) and L-0652: must be merged first.
- T-0010 (merged): `approve` and the `taken:` record.
Blocks: L-0655 (its mutations), L-0656 (sends this summary by Telegram), T-0054 (the guide's
morning-summary example).

## Size
About 140 added production lines (`crew_sleep.py` about 85, `crew_autopilot.py` about 55). One
small line parser (the log reader); no state machine.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
