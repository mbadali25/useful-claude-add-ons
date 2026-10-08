# T-0067 plan: `autopilot.reviewPolicy` and the single-ticket `fix` phase

Written by the implementing session (rush g6a, 2026-10-07) on `rush/g6a-autopilot`, after L-0550.

What changed against the spec, because the branch moved:
- **T-0029 already added the key** (rush G0): `AUTOPILOT_DEFAULTS`, the template, crew-setup's
  inline copy, `crew_keys`, both CONFIG.md tables and `crew_wave.settings`. This ticket reads it
  for a single-ticket run instead of adding it; the four config surfaces need no new line, and
  CONFIG.md's leaf counts do not move. `crew_config_menu._KNOWN_VALUES` gains its three values.
- **`crew_autopilot.py` is over pylint's 3,400-line cap** (C-0034), so the decision lives in a new
  module, `plugin/crew/hooks/scripts/crew_autopilot_fix.py` (`review_policy`, `decide`,
  `PROCEDURE_STOPS`); `crew_autopilot.py` ends no longer than it started this group.
- **T-0043 reworded the FINDINGS stop** first. Its text stays; a cause is appended only when the
  policy is `unknown` or `fix-and-rereview` cannot act, so `stop`'s reason is unchanged.
- **The settings CLI** prints `reviewPolicy=` on a line of its own: the approval line is a
  sabotage anchor and stays byte-identical.
- `status` (policy=False) shows the `fix` phase too; `WAITING` maps it to `owner`, and its stop=0
  prints `autopilot - run ... to continue`. `crew_status.py` renders no autopilot phase list
  (checked), so it is not touched.

### Step 1: tests first
Files: `plugin/crew/tests/test_crew_autopilot_review_policy.py` (41 cases; 33 fail on the old code)

### Step 2: the setting and the phase
Files: `plugin/crew/hooks/scripts/crew_autopilot_fix.py`, `plugin/crew/hooks/scripts/crew_autopilot.py`,
`plugin/crew/hooks/scripts/crew_config_menu.py`, `plugin/crew/commands/autopilot.md`

### Step 3: docs and verify
Files: `plugin/crew/hooks/scripts/crew_keys.py` and the regenerated configuration reference,
`plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `.crew/codemap/crew.md`, `.crew/verify.json`,
`CHANGELOG.md`
