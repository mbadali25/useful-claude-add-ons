# L-0653 plan - sleep log and morning summary

Written by the implementing session, 2026-10-05, on `rush/g6b-goals-sleep` (T-0053 and L-0652 on the base).

## Decisions

- **Split.** The pure text (entry and marker lines, the reader, the summary) is in `crew_sleep.py`, which
  a test holds to opening nothing; the file I/O is in `crew_autopilot_sleep.py` with `sleep`/`wake`.
  `crew_autopilot.py` (pylint's 3400-line limit) gains call sites only: `approve`, `settings`,
  `EXTRA_ACTIONS` (compacted to make room).
- **Append.** One `os.write` of one whole line to an O_APPEND descriptor; a two-process test counts lines.
- **Settings of an entry.** `sleep.<key>=<night> (day <day>)` when the night value applied, else
  `<key>=<value>`; a `note` names the sleep source.
- **`wake`** prints the summary only when there is something to report, so its one-line answer is
  unchanged otherwise.
- **`autopilot.md`** has no line to spare (117 of 117 after L-0541 and T-0056): the `sleep-note` call
  and the summary trigger are reworded into the existing questions line.

## Steps
### Step 1: text, file, call sites
Files: crew_sleep.py, crew_autopilot_sleep.py, crew_autopilot.py, test_crew_autopilot_sleep.py,
test_crew_autopilot_policy.py
### Step 2: the command and docs
Files: commands/autopilot.md, test_lifecycle_commands.py, CONFIG.md, README, daily-workflow-scope.md
(daily workflow guide rebuilt), codemap, CHANGELOG, BUDGETS.

Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_sleep.py plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_lifecycle_commands.py -q
