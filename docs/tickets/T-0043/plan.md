# T-0043 plan: the FINDINGS stop names the refresh; an accepted FINDINGS round is not called INCOMPLETE

Written by the implementing session (rush g6a, 2026-10-05) against `rush/g6a-autopilot`
(release/1.2.0 plus the G2 autopilot ports and the G0 coord/wave port). Anchors were re-read
there: the FINDINGS stop is in `_review_phase`, the INCOMPLETE line is unique, `_settles` is
unchanged from the spec's reading.

### Step 1: tests first (red)
Files: `plugin/crew/tests/test_crew_autopilot.py`
- `test_next_accept_review_names_the_refresh_before_the_next_round` (FIX 1).
- `test_next_accepted_findings_then_an_edit_goes_through_refresh`, stale and fresh (FIX 2 must-allow).
- `test_next_round_without_a_verdict_stops` and the `round-2-findings-accepted-gone-stale` id on
  `test_next_budget_spent_without_a_receipt_stops` (FIX 2 must-block).
- `test_refresh_stale_artifact_marked_not_refreshable_stops` and its twin
  `test_refresh_stale_artifact_without_the_key_settles` (`_settles` control; no production change).

### Step 2: FIX 1 and FIX 2 in `crew_autopilot.py`
Files: `plugin/crew/hooks/scripts/crew_autopilot.py`
- The un-accepted FINDINGS reason's tail names `crew_refresh_check.py --root . --ticket <id>`
  (each `refresh with` command, committed) before `/crew:review <id>`. The L-0510 clause in front
  is untouched.
- A new branch above `if latest.get("verdict") != "CLEAN" and not ok:` (byte-identical, still
  unique): a FINDINGS round that reached it has a standing receipt, so it goes through
  `_toward_review`. Docstring phase table: a new row, and the INCOMPLETE row reads
  "latest round INCOMPLETE or no verdict".

### Step 3: docs and the INSTALLATION claim
Files: `plugin/crew/commands/autopilot.md`, `plugin/crew/README.md`, `INSTALLATION.md`,
`CHANGELOG.md`
- autopilot.md and README stop claiming `next` puts a refresh before every later round: the
  FINDINGS stop names the refresh the human runs after fixing; `next` refreshes before a round
  only when it reaches that round. autopilot.md stays at 120 lines or fewer.
- `INSTALLATION.md`: `36 slash commands<!-- claim: plugin-commands:crew -->`.

### Step 4: verify
`python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q`,
the anchor grep, hand sabotage in a `git archive` scratch copy (three mutations), check-tooling-pr
and check-marketplace after commit.
