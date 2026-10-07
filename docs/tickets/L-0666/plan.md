# L-0666 plan: every autopilot stop names an owner decision, never a mechanical step

Written by the implementing session (rush g6a, 2026-10-07) on `rush/g6a-autopilot`, after T-0067
(its prerequisite, built first on this branch although it was listed after this ticket).

What changed against the spec, because the branch moved:
- **Stop sites.** The spec counted about 20; the branch has 72 in `crew_autopilot.py` and the
  modules `_phase` hands its `answer` (`crew_autopilot_gates.py`, `_docs.py`, `_split.py`). The
  walk covers all four; `crew_ship.merged_phase` (also handed `answer`) is not walked, stated in
  the code map. Each case is traced (`sys.settrace`) to the line of its own site, so a case cannot
  count for a site it never reached.
- **The decision is set in one place.** `_phase`'s `answer` takes an optional `decision` and adds
  `crew_autopilot_stops.decided(phase, stop, decision)`; the review sites with more than one
  meaning name theirs; `next_phase`'s guard stops and `_drift`/`_inflight` name theirs; a phase
  that runs carries none. New module `crew_autopilot_stops.py` (C-0034: `crew_autopilot.py`
  does not grow).
- **One id added to the spec's table:** `approve-split` (`/crew:split <id>`), for T-0058's
  `split-approval` stop, which postdates the spec. Stops the table does not fit (ship, slices,
  docs, hold, landing, blocked, in-flight, drift, folder-elsewhere) are `look`.
- **Commands dropped from stops** whose command is not their decision's: `docs`
  (`/crew:docs`), the size check's `split-check-unknown` (`/crew:autopilot split`, `/crew:plan`),
  the guard stops (ticket mismatch, no progress); max-phases now carries `/crew:autopilot <id>`.
- **T-0043 is superseded on one point:** its FINDINGS stop named the refresh check and the next
  round; this contract forbids both, so the stop names the accept and `autopilot.reviewPolicy`.
- **CLI:** `decision=` goes before `reason=` (the reason is free text to the end of the line, so
  appending after it would fold the field into the reason).

### Step 1: tests first
Files: `plugin/crew/tests/test_crew_autopilot_stop_contract.py` (225 cases), and the reason-text
assertions in `test_crew_autopilot.py`, `_focus.py`, `_replan.py`, `_review_policy.py`

### Step 2: the decision and the rewording
Files: `plugin/crew/hooks/scripts/crew_autopilot_stops.py`, `crew_autopilot.py`,
`crew_autopilot_docs.py`, `crew_autopilot_split.py`, `plugin/crew/commands/autopilot.md`

### Step 3: docs and verify
Files: `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `.crew/codemap/crew.md`,
`.crew/verify.json`, `CHANGELOG.md`
