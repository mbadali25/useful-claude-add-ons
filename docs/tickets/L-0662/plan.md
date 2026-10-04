# L-0662 plan: plain-text routing rows for autopilot wave, split, sleep and wake

Written 2026-10-04 by the implementing session on `L-0662-build`, after merging origin/main
(`b863b773`+, T-0069's `_route` guard) and origin/T-0057-build (`2eaac674`, PR #416). The spec
is the contract; this plan only orders it and records the readings taken.

## Readings taken (spec ambiguities, recommended option each time)

1. Open questions: "morning" and "I'm back" stay wake phrases; bare "this is too big" is not a
   split phrase; `sleep` by phrase without a schedule is allowed (T-0053 decides).
2. T-0057's `_screen` applies to all four new rows (orchestrator instruction). None has free
   text, so the approv / nothing-word / leading-dash / negation checks have nothing to read; the
   printable-ASCII allowlist is the one that bites (a long s or Kelvin sign that IGNORECASE folds
   onto a pattern letter asks). Sleep and wake add exactly one character to the allowlist, the
   ASCII apostrophe their own patterns spell (`I'm`); a curly `’` matches the pattern but asks.
   The rule for sleep/wake stays `autopilot` as the spec says; the screen is keyed on intent.
3. Wave's "fewer than two distinct ids: none" is decided in `match` (the row does not match), so
   it is `none` whatever the gate says. Missing folders are decided after the gate: `ask`.
4. The match dict gains `tickets` (default `[]`); `ticket_arg` for a wave is the first id.
5. `split` joins `_TICKETED` so a split ask with no candidates says "which ticket"; wave does not.
6. Every new route goes through `_route` (T-0069): a command `_clip` would change asks.

## Steps (test-first: each test red, then code, then green)

1. Table: `test_the_table_names_exactly_...` with EXAMPLES for the four rows; add rows.
2. Inert on main: `test_rows_for_unknown_subcommands_emit_nothing`.
3. Reserved: `test_reserved_wave_split_sleep_wake_ask_softly` (SUBCOMMANDS monkeypatched).
4. Available (AVAILABLE = every subcommand): `test_available_wave_split_sleep_wake_route`.
5. `autopilot-tickets`: `test_wave_needs_two_real_tickets`.
6. `autopilot-ref`: `test_split_without_a_resolvable_ticket_asks`.
7. Must-not-route list: `test_wave_split_sleep_wake_phrases_that_must_not_route`, plus the
   screen's must-ask cases (lookalike letters, curly apostrophe) and must-allow (`I'm`, `Morning!`).
8. Undo line: `test_sleep_route_line_names_the_undo`.
9. Bounded line / no approve / anchors still pass; hook wrappers (sh and ps1) still pass.
10. Sabotage locally (not committed: `sabotage*.py` is harness, L-0663).
11. Docs: README routing table, codemap section, CHANGELOG, verify.json rule 30 figures, rules
    regenerated, graph. Delete `docs/tickets/L-0662/` in the final content commit.
12. Version-only last commit: crew 1.0.406.
