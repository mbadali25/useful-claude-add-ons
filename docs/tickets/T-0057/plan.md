# T-0057 plan          status: plan   risk: med

Written by the implementing session on 2026-10-04 from spec.md (unchanged) and origin/main
`baf193aa` (crew 1.0.325). The spec's Design is the contract; this plan only orders the work.

## Re-checked at baf193aa
- `crew_route.py`: `PHRASES` :82-94 (eight rows), `match` :132, `command_for` :151, `_answer`
  :160, `_resolve` :170, `decide` :211, `render` :254. Same shape the spec read at `155fe6d8`.
- `crew_autopilot.py`: `SUBCOMMANDS` / `AVAILABLE` / `ARRIVES` :224-226 and `route` :1299 are
  unchanged. T-0019 (#379) has merged, but it landed `crew_ticket` mint/assign only: `assign` is
  still not in `AVAILABLE` and `commands/autopilot.md` section 0 still stops on it. So `assign`
  asks softly today, exactly as the spec expects; no plan change.
- No reader of `PHRASES` outside `crew_route.py` except prose in README/CONFIG (Unknowns 2).
- `sabotage_route.py` anchors re-read; the three duplication-prone strings are as the spec says.

## Steps (each test-first: write, see red, implement, see green)
1. Table. Extend `EXAMPLES` with the five rows and rename the row-list test to
   `test_the_table_names_exactly_the_lifecycle_and_autopilot_intents`. Add the rows after the
   `status` row (that line untouched). Free-text captures are `[^?]+` so `?` is accepted only
   where the status pattern spells it.
2. Match guard. A bare pronoun (`it`, `this`, `that`, `them`, `these`, `those`, `everything`) as
   an `autopilot-text` capture is no match. Must-not-route list from the spec.
3. Gate. `_available(top, found)` calls `crew_autopilot.route(top, sub)` in a `try`; a raise or a
   malformed answer asks (the `except` binds a reason, so the existing `except ... return
   _answer("ask"` anchor stays unique); `sub == ""` is `none`; `stop` asks with `unavailable`.
4. Decide branches for `autopilot`, `autopilot-ticket`, `autopilot-text` (shell characters ask),
   `autopilot-resume` (always asks, no slug). `command_for` learns the new rules.
5. Render. The `unavailable` ask line; the `goal` route's undo sentence; `_answer` carries
   `unavailable` on every decision; bounded-line cases for the new rows.
6. Hook. `test_armed_autopilot_status_puts_the_route_line_first` through both wrappers.
7. Docs: README "Plain-text lifecycle" table and text, CONFIG.md section 21, codemap
   `.crew/codemap/crew.md` routing section re-anchored, `.claude/rules/crew.md` regenerated,
   verify.json rule `why` re-measured, CHANGELOG. Delete `docs/tickets/T-0057/` in the last
   content commit. `graphify update .` if the tool is present.
8. Version-only commit: crew 1.0.399 everywhere stated.

## Not in this PR
Sabotage mutations for the new rows (L-0661, harness); wave/split/sleep/wake rows (L-0662); any
edit to `crew_autopilot.py`, `autopilot.md`, `crew_context.py`, `hooks.json` (T-0053 is editing
the first two in parallel).
