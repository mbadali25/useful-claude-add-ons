# L-0551 plan: `/crew:status --owner` and the waiting line

Written by the implementing session (rush g6a, 2026-10-07) on `rush/g6a-autopilot`, after L-0550,
T-0067 and L-0666, which already sit on this branch (so the slice-2 dependencies of L-0687 are met).

What changed against the spec, because the branch moved:
- **`owner_items` lives in a new module**, `plugin/crew/hooks/scripts/crew_autopilot_owner.py`,
  not in `crew_autopilot.py`: that file is over pylint's 3,400-line cap (C-0034). It imports
  `crew_autopilot` and calls `_phase(policy=False, deep=False)`; `crew_status.py` imports it lazily.
- **`deep=False` stops at three places**, not one: before `check_receipt` (the spec's), in
  T-0067's fix decision (whether a fix is complete needs a bundle rebuild), and in `_ship_phase`
  before `gh` (G2's armed ship path postdates the spec). All three are `review-unread`, counted
  as "in review not read".
- **The accept-review action** drops "or fix then /crew:review" (L-0666's contract forbids handing
  the owner a review round): `review_ledger.py --accept --ticket <id> --by <owner>, or reject it`.
- **`--owner` is refused with `--approvals` too** (T-0070's flag postdates the spec).
- **The `owner` line** (T-0037's needs-owner rows) stays; the `waiting` line is added after the
  ticket lines. Open question 7 (merge them) is still the owner's.
- **Timing**, measured instead of the spec's real-`.work/` run (this container has none): a
  30-ticket fixture, each awaiting approval, took 0.96s with the waiting line and 0.13s without.
  About 28 ms per open ticket on a loaded 4-CPU container, so a repo with 70 or more open tickets
  passes the spec's 2-second line: reported to the owner, not tuned.
- The status diagram (`docs/diagrams/process-crew-brief-status.mmd`) is not regenerated here.

### Step 1: tests first
Files: `plugin/crew/tests/test_crew_autopilot_status.py`, `plugin/crew/tests/test_status.py`,
`plugin/crew/tests/test_crew_autopilot_stop_contract.py` (the three `review-unread` sites)

### Step 2: deep, owner_items, the waiting line and --owner
Files: `crew_autopilot.py`, `crew_autopilot_fix.py`, `crew_autopilot_stops.py`,
`crew_autopilot_owner.py`, `crew_status.py`, `plugin/crew/commands/status.md`

### Step 3: docs and verify
Files: `plugin/crew/README.md`, `plugin/PLUGINS.md`, `docs/guides/crew/src/daily-workflow.md`
and its build, `.crew/codemap/crew.md`, `.crew/verify.json`, `CHANGELOG.md`
