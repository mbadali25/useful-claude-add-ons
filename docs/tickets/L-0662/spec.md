# L-0662: plain-text routing rows for autopilot wave, split, sleep and wake          status: spec   risk: med
Split from T-0057. Written 2026-10-04 against origin/main `155fe6d8`. It builds on T-0057's availability gate and rule families; re-read `crew_route.py` on main after T-0057 merges.

## Intent
Four more rows in `crew_route.PHRASES` let a whole-prompt phrase name `/crew:autopilot wave`, `split`, `sleep` and `wake`. Each row is inert (no line) until the autopilot router knows its subcommand, asks softly while the name is reserved, and routes once the command runs. The must-not-route cases are pinned by tests.

## Design
Rows, appended after T-0057's `focus` row:

| intent | command | rule | whole-prompt patterns |
|---|---|---|---|
| `wave` | `/crew:autopilot wave` | `autopilot-tickets` (new) | `run <id> and <id> in parallel`, `run <id>, <id> and <id> in parallel` (two or more ids, separated by `,`, `and` or `, and`) |
| `split` | `/crew:autopilot split` | `autopilot-ref` (new) | `split this ticket`, `split it`, `split <id>`, `this ticket is too big`, `<id> is too big` |
| `sleep` | `/crew:autopilot sleep` | `autopilot` | `I'm heading to bed`, `heading to bed`, `going to sleep`, `I'm going to sleep`, `good night` |
| `wake` | `/crew:autopilot wake` | `autopilot` | `I'm back`, `morning`, `good morning` |

- All four go through T-0057's gate first. Router does not know the name: `none`. Reserved: soft ask. Raises: ask.
- `autopilot-tickets`: every id is upper-cased, de-duplicated in order, and must have a `.work/tickets/<id>/` folder. Any id without one: `ask`, naming it. Fewer than two distinct ids: `none`. Route: `/crew:autopilot wave <ID> <ID> ...`.
- `autopilot-ref`: an explicit id, or it/this/nothing, resolved by the existing `_resolve` (active ticket, else the only open INDEX ticket, else `ask`). Route: `/crew:autopilot split <ID>`.
- `sleep` joins `goal` in the set of intents whose route line ends "After it runs, tell the user in one line what changed and how to undo it."
- `decision["ticket"]` for a wave is the first id; the full list is in the command. No new decision key.

## Exclusions
- No edit to `crew_autopilot.py`: this ticket does not add `wave`, `split`, `sleep` or `wake` to `SUBCOMMANDS`. Each command's own ticket does.
- No route to `/crew:split` (the Jira split command, plugin/crew/commands/split.md). The row names `/crew:autopilot split` only.
- No sleep state, schedule, timer or echo text of its own: T-0053 owns them.
- No change to `normalise`, `MAX_PROMPT_CHARS`, `AMBIGUOUS`, the gate, or any existing row.
- No edit to `plugin/crew/tests/sabotage*.py` (harness; L-0663).
- No approval row.

## Evidence
Read at origin/main `155fe6d8`.
- plugin/crew/hooks/scripts/crew_autopilot.py:224 `SUBCOMMANDS` holds none of the four names; :1316-1317 an unknown first word returns `{"sub": "", "stop": True, "reason": UNKNOWN_SUB}`.
- plugin/crew/hooks/scripts/crew_route.py:75-76 `_ID` and `_REF`; :143-147 `match` reads one `id` group; :170-188 `_resolve`; :62 the 80-character cap (about eight ids in a wave phrase).
- plugin/crew/commands/split.md:2 "Split an oversized Jira ticket into sub-tickets".
- `git ls-tree -r --name-only origin/main | grep -iE "wave|sleep"` prints nothing: neither command exists on main.
- plugin/crew/tests/sabotage_route.py anchors must stay unique (plugin/crew/tests/test_crew_route.py:554-560).

## Unknowns
- The final argument shape of `wave`, `split`, `sleep` and `wake` (T-0029, T-0058, T-0053 are not merged). Resolved by whichever lands second: if a command's arguments differ from the row's rendering, that ticket amends the row. Accepted as risk.
- Whether T-0053 wants `wake` to be silent when sleep is not on. T-0053's decision; the row only routes.
- `match` returns a single `ticket_arg`. A wave needs a list. Resolved at plan: add a `tickets` key to the match dict, default empty.

## Dependencies
- T-0057 (ready): must be merged first (gate, rule families, soft ask).
- T-0023 (merged), T-0018 (merged): table and router.
- Not blocking, each makes one row live: T-0029 (in-progress) wave; T-0052 (spec) and T-0058 (spec) split; T-0053 (ready) sleep and wake.
- Blocks: L-0663 (sabotage for these rows); T-0054 (ready), whose guide lists the phrases.

## Size
About 70 added production lines in `crew_route.py` (rows 14, id-list parsing 20, two decide branches 25, render 3, docstring 8). No harness path. Under the 300-line rule.

## Touch
- `plugin/crew/hooks/scripts/crew_route.py`
- `plugin/crew/tests/test_crew_route.py`
- `plugin/crew/README.md` - the routing table
- `plugin/PLUGINS.md` - version cell
- `.crew/codemap/crew.md`
- `.claude/rules/crew.md` - regenerated
- `.crew/verify.json` - rule 30's measured figures only
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `graphify-out/**`

Not in Touch, stated: `plugin/crew/CONFIG.md` (T-0057 already made section 21 general); the guides (T-0054); `docs/diagrams/` (no box or edge changes).

## Acceptance checks
All in `plugin/crew/tests/test_crew_route.py`, run as `python3 -m pytest plugin/crew/tests/test_crew_route.py -q -k <name>` (`.crew/verify.json` rule 30).
- [ ] The table ends `..., focus, wave, split, sleep, wake`. `-k test_the_table_names_exactly_the_lifecycle_and_autopilot_intents`
- [ ] Inert on main as it is: every example phrase of the four rows decides `none`. `-k test_rows_for_unknown_subcommands_emit_nothing`
- [ ] Reserved: with the four names added to `SUBCOMMANDS` (monkeypatch) and not to `AVAILABLE`, each example decides `ask` with `unavailable` true. `-k test_reserved_wave_split_sleep_wake_ask_softly`
- [ ] Available (monkeypatch both): `run T-1 and T-2 in parallel` routes to `/crew:autopilot wave T-1 T-2`; `run t-1, T-2 and T-3 in parallel` to `... wave T-1 T-2 T-3`; `split it` to `/crew:autopilot split <active>`; `T-1 is too big` to `... split T-1`; `I'm heading to bed.` to `/crew:autopilot sleep`; `Morning!` to `/crew:autopilot wake`. `-k test_available_wave_split_sleep_wake_route`
- [ ] Wave asks when any id has no folder, naming it, and is `none` for `run T-1 and T-1 in parallel` and `run T-1 in parallel`. `-k test_wave_needs_two_real_tickets`
- [ ] Split with several open tickets and no active one asks and lists them. `-k test_split_without_a_resolvable_ticket_asks`
- [ ] Must-not-route with all four available, each `none`: `go to sleep mode later`, `is sleep mode on?`, `what does going to sleep do`, `"going to sleep"`, `` `going to sleep` ``, `I'm going to sleep on it`, `this is too big`, `the diff is too big`, `split the file`, `split this function`, `I'm back to square one`, `morning standup notes`, `back`, `run the tests in parallel`, `run T-1 and the tests in parallel`. `-k test_wave_split_sleep_wake_phrases_that_must_not_route`
- [ ] A `sleep` route line ends with the undo sentence; `wake`, `wave` and `split` lines do not. `-k test_sleep_route_line_names_the_undo`
- [ ] Bounded line, no approve, anchors intact: `-k "test_render_is_one_bounded_line_whatever_the_fields or test_no_route_ever_names_approve or test_every_route_sabotage_anchor_is_present_exactly_once"`
- [ ] The whole rule passes: `python3 -m pytest plugin/crew/tests/test_crew_route.py plugin/crew/tests/test_crew_route_hook.py plugin/crew/tests/test_crew_context.py -q`
- [ ] README's table lists the four rows and says they do nothing until the command exists. `git grep -n "in parallel" -- plugin/crew/README.md`
- [ ] `git diff origin/main --stat -- plugin/crew/tests/sabotage.py plugin/crew/tests/sabotage_route.py plugin/crew/hooks/scripts/crew_autopilot.py` prints nothing; `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] Version bumped, committed, then `python3 scripts/check-marketplace.py` exits 0.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
