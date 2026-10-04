# T-0057 plain-text routing for the autopilot commands the router knows (status, assign, goal, goal resume, focus)          status: spec   risk: med
## Refreshed 2026-10-04
First spec for this ticket, written against origin/main `155fe6d8` (crew 1.0.322). There was no earlier spec.md and there is no plan.md. The direction (option 1, extend T-0023's table) is kept. What this spec narrows, and why, is in direction.md "Direction check 2026-10-04":
- This ticket is slice 1 of 4. It carries the mechanism and five rows. `wave`, `split`, `sleep` and `wake` rows are L-0662. The sabotage mutations are L-0661 and L-0663, because `plugin/crew/tests/sabotage*.py` is harness and may not ride with feature work.
- "Has the command landed?" is read from `crew_autopilot.route` at decide time. The table holds no second copy.

## Intent
With `route.enabled` true, a short whole-prompt phrase can name an autopilot command: "autopilot status", "take care of <work>", "work toward <goal>", "pick the goal back up", "focus on T-0012". The rows live in the one table (`crew_route.PHRASES`) and keep T-0023's three outcomes. A row routes only when `crew_autopilot.route` says the subcommand runs; otherwise the line says the command is not available yet and tells Claude to answer the prompt as written.

## Design (decided here; the plan may not change it without amending this spec)
Rows, appended to `PHRASES` after the `status` row. The row shape stays `(intent, command, rule, patterns)`.

| intent | command | rule | whole-prompt patterns |
|---|---|---|---|
| `autopilot-status` | `/crew:autopilot status` | `autopilot` | `autopilot status`, `autopilot status <id>`, `what's autopilot doing`, `what is autopilot doing` (these two may end in `?`) |
| `assign` | `/crew:autopilot assign` | `autopilot-text` | `take care of <work>`, `handle <work>` |
| `goal` | `/crew:autopilot goal` | `autopilot-text` | `work toward <goal>`, `work towards <goal>`, `make it so <goal>` |
| `goal-resume` | `/crew:autopilot run --goal` | `autopilot-resume` | `pick the goal back up`, `resume the goal` |
| `focus` | `/crew:autopilot focus` | `autopilot-ticket` | `focus on <id>` (explicit id only) |

Decide, for the three new rule families:
1. The subcommand is the second word of the row's command (`--goal` for `goal-resume`). Call `crew_autopilot.route(top, <that word>)` inside a `try`.
2. It raises, or returns something that is not a dict with `sub`, `stop` and `reason`: `ask`, reason "whether /crew:autopilot <sub> is available could not be read (<type>: <message>)". Never `route`.
3. `sub` is empty (the router does not know the name): `none`. No line.
4. `stop` is true: `ask` with `unavailable: True` and the router's own reason (today "/crew:autopilot assign arrives with T-0019").
5. `stop` is false:
   - `autopilot`: `route`. With an id, the id goes through `_resolve` first (no folder is an `ask`, as for every other row) and is appended to the command.
   - `autopilot-ticket`: `_resolve` the explicit id; `route` to `/crew:autopilot focus <ID>`, or `ask`.
   - `autopilot-text`: if the text holds `'`, `"`, `$`, a backtick or a backslash, `ask` ("autopilot's router refuses those characters; ask the user to rephrase or type the command"). Otherwise `route` to `<command> <text>`, the user's words unchanged.
   - `autopilot-resume`: always `ask` ("routing does not pick a goal; the user types /crew:autopilot run --goal <slug>"). The slug resolver ships with T-0056.

Matching rules added to `match`:
- For `autopilot-text` rows the captured text, casefolded, must not be one of `it`, `this`, `that`, `them`, `these`, `those`, `everything`. Such a prompt is `none`.
- `?` is accepted only where a pattern spells it (`autopilot-status`). `normalise` is unchanged.

Render:
- An `ask` with `unavailable: True` renders as one line: `crew route: the user's prompt reads as <intent>, but <reason>; do not run it. If the user meant autopilot, say so in one line; otherwise answer the prompt as written.` It never says "which ticket".
- A `route` for intent `goal` ends with one more sentence: `After it runs, tell the user in one line what changed and how to undo it.`
- `_answer` gains the key `unavailable` (default `False`), present on every decision.
- The line stays within `MAX_LINE_CHARS`.

Anchor constraint. `sabotage_route.py` holds 29 mutations, most anchored on exact strings in `crew_route.py`, and each string must stay present exactly once. Three are easy to duplicate by accident: `    if outcome == "route":\n` (:36-37 of sabotage_route.py), `    except Exception as exc:  # pylint: disable=broad-except\n        return _answer("ask"` (:87) and the `status` row line (:22). The gate's `except` therefore binds the reason to a name before returning, and the new rows go after the `status` row without rewrapping it.

## Exclusions
- No approval row and no phrase that reaches `/crew:approve` (T-0024 owns plain-text approval).
- No `run` row. "autopilot T-3" and "run autopilot" do not route; `continue` already covers the lifecycle.
- No `wave`, `split`, `sleep` or `wake` row (L-0662).
- No edit to `plugin/crew/tests/sabotage*.py` (harness; L-0661). The existing sabotage anchors in `crew_route.py` stay byte-identical and unique: `test_every_route_sabotage_anchor_is_present_exactly_once` must pass unchanged.
- No edit to `crew_autopilot.py`, `crew_context.py`, `commands/autopilot.md`, `hooks.json` or any config default. No new hook, skill, setting or CLI action.
- No goal slug resolution and no read of goal files (T-0056).
- No change to `normalise`, `MAX_PROMPT_CHARS`, `AMBIGUOUS`, the eight lifecycle rows or their outcomes.
- The hook still runs nothing, blocks nothing and writes nothing.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_route.py:82-94 `PHRASES`, eight rows, none naming autopilot. :62 `MAX_PROMPT_CHARS = 80`. :96 `AMBIGUOUS`. :112-129 `normalise` (drops one trailing `.` or `!`, never `?`). :132-148 `match` (`fullmatch`, returns `intent, command, rule, ticket_arg, topic`). :151-157 `command_for`. :160-167 `_answer`. :170-188 `_resolve`. :211-227 `decide`. :254-284 `render`; the ask tail "ask the user {which}before running anything" at :279-283. :55 already imports `crew_autopilot`.
- plugin/crew/hooks/scripts/crew_autopilot.py:160 `AUTOPILOT = "/crew:autopilot"`. :224-226 `SUBCOMMANDS = ("status", "run", "assign", "goal", "focus")`, `AVAILABLE = frozenset({"status", "run"})`, `ARRIVES`. :1299-1321 `route(root, first)` returns `{"sub", "stop", "reason"}`; unknown word returns `sub: ""` at :1317; a reserved name stops at :1318-1320; `--goal` stops at :1311-1313. :1328-1345 `route_args` (`status <ticket>` accepted).
- plugin/crew/commands/autopilot.md:16-17 the command stops on a quote, `$`, backtick or backslash in its arguments. :25 names the three reserved subcommands.
- plugin/crew/hooks/scripts/crew_context.py:965-990 `route_item`: logs `outcome`, `intent`, `ticket`; any exception costs only the route line. It reads no other decision key, so a new key is safe.
- plugin/crew/tests/test_crew_route.py:28-46 `EXAMPLES`; :54-55 `test_the_table_names_exactly_the_lifecycle_intents` pins the row list; :131-150 `test_no_route_ever_names_approve` unpacks rows as 4-tuples; :554-560 the sabotage-anchor test.
- plugin/crew/tests/sabotage_route.py:20-24 anchors the `status` row line; :26-28 anchors `found = pattern.fullmatch(text)`; the file is 138 lines.
- scripts/check-tooling-pr.py:79 `plugin/crew/tests/sabotage*.py` is in `HARNESS`; `crew_route.py` is in neither `HARNESS` (:58-87) nor `SEAM` (:89-95).
- .crew/verify.json:377-383 maps `crew_route.py` and `test_crew_route*.py` to `python3 -m pytest plugin/crew/tests/test_crew_route.py plugin/crew/tests/test_crew_route_hook.py plugin/crew/tests/test_crew_context.py -q`.
- Docs that describe the table: plugin/crew/README.md:921-942, plugin/crew/CONFIG.md:2727-2737, .crew/codemap/crew.md:823-852. `git grep -niE "plain-text|crew_route" origin/main -- docs/guides/crew/src` prints nothing: no guide describes routing.
- Not done on main: `git log origin/main --grep=T-0057` is empty; `git grep -n "crew:autopilot" origin/main -- plugin/crew/hooks/scripts/crew_route.py` prints nothing.

## Unknowns
- How T-0019 carries free text into `/crew:autopilot assign` (the direction names the router's `--first` form). Resolved by T-0019: this ticket only renders `<command> <text>` and refuses the characters autopilot.md:16 refuses. If T-0019 lands first, re-read `autopilot.md` section 0 before planning.
- Whether T-0025 (approved, not merged) expects every `PHRASES` rule to be one of the four lifecycle rules. Resolved at plan: `git grep -n PHRASES origin/main -- plugin` again; today no other reader exists.
- How often the soft not-landed line fires on ordinary "handle ..." prompts. Accepted as risk; open question 1 in direction.md.
- The next free crew patch version is set at implement time.

## Dependencies
Must land first:
- T-0023 (merged): the table, the hook and the three outcomes.
- T-0018 (merged): `crew_autopilot.route`, `SUBCOMMANDS`, `AVAILABLE`, `/crew:autopilot status`.
- T-0004 (merged): `/crew:autopilot` itself.
- T-0024 (merged): owns plain-text approval, which is why no approve row exists here.

Not blocking (a row asks until each lands, then routes with no change here):
- T-0019 (in-progress) and its follow-up L-0611 (direction): `assign`.
- T-0012 (approved) and L-0541 (direction): `goal` and `--goal`.
- T-0020 (approved): `focus`.
- T-0056 (ready): the goal slug resolver for "pick the goal back up".

This ticket blocks:
- L-0661 (sabotage for these rows), L-0662 (wave, split, sleep, wake rows), L-0663 (sabotage for L-0662).
- T-0054 (ready): the autopilot guide lists every plain-text phrase.
- T-0025 (approved) reads `PHRASES` for `/crew:help`; not blocked, but it should plan against the new rules.

## Size and split
- Estimate: about 120 added production lines, all in `plugin/crew/hooks/scripts/crew_route.py` (rows 15, gate 30, decide branches 40, match guard 10, render 15, docstring 10). Under the 300-line rule.
- No new parser: the same `fullmatch` matcher. One new fail-closed branch (the availability gate).
- Split anyway, for two reasons: the sabotage mutations are harness paths, and the four rows for names the router does not know yet are a separable unit. See `children/1`, `children/2`, `children/3`.

## Touch
- `plugin/crew/hooks/scripts/crew_route.py`
- `plugin/crew/tests/test_crew_route.py`
- `plugin/crew/tests/test_crew_route_hook.py`
- `plugin/crew/README.md` - the "Plain-text lifecycle" section and its table
- `plugin/crew/CONFIG.md` - section 21, one sentence
- `plugin/PLUGINS.md` - version cell, and the crew-context row if it names the routed commands
- `.crew/codemap/crew.md` - the plain-text routing section, re-anchored
- `.claude/rules/crew.md` - regenerated line numbers
- `.crew/verify.json` - rule 30's measured count and seconds only
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `graphify-out/**` - graphify update .

Not in Touch, stated: `plugin/crew/commands/autopilot.md` (the phrases are documented in README; the command file is budget-bound); `docs/guides/crew/src/*.md` and the built guides (no guide describes routing today; T-0054 owns the autopilot guide and its examples; say so in the PR body); `docs/diagrams/` (no box or edge changes; `crew_context.py` is not edited, so its cited lines hold); `plugin/crew/BUDGETS.md` (no command or skill file is edited).

## Acceptance checks
Commands run from the repo root. All map to `.crew/verify.json` rule 30 (the `crew_route.py` rule). On a memory-bound host run pytest through the repo's heavy-run wrapper.
- [ ] The table is the eight lifecycle intents followed by `autopilot-status`, `assign`, `goal`, `goal-resume`, `focus`, in that order, each a 4-tuple. `python3 -m pytest plugin/crew/tests/test_crew_route.py -q -k test_the_table_names_exactly_the_lifecycle_and_autopilot_intents`
- [ ] Every new row matches its examples, including `autopilot status T-12`, `What's autopilot doing?`, `please take care of the login audit.`, `work towards zero flaky tests`, `focus on t-0012`. `-k test_every_row_matches_its_examples`
- [ ] `autopilot status` routes to `/crew:autopilot status` on main as it is, with no ticket; with an id that has a folder it routes to `/crew:autopilot status <ID>`; with an id that has none it asks. `-k test_autopilot_status_routes`
- [ ] Not landed: with origin/main's `AVAILABLE`, `take care of the login audit`, `work toward zero flaky tests`, `focus on T-1` and `pick the goal back up` each decide `ask` with `unavailable` true and a reason containing "arrives with"; the rendered line contains "answer the prompt as written" and not "which ticket". `-k test_a_reserved_subcommand_asks_softly`
- [ ] Landed: with `crew_autopilot.AVAILABLE` monkeypatched to include `assign`, `goal`, `focus`, the same prompts route to `/crew:autopilot assign the login audit`, `/crew:autopilot goal zero flaky tests` and `/crew:autopilot focus T-1`; `focus on T-9` with no folder asks. `-k test_an_available_subcommand_routes`
- [ ] Unknown name: with `crew_autopilot.SUBCOMMANDS` monkeypatched to drop `focus`, `focus on T-1` decides `none`. `-k test_a_subcommand_the_router_does_not_know_is_none`
- [ ] Could not tell: with `crew_autopilot.route` monkeypatched to raise, and again to return `None`, each new row decides `ask`, never `route`. `-k test_an_unreadable_router_asks`
- [ ] `pick the goal back up` asks even when `--goal` no longer stops, and no decision for it ever carries a slug. `-k test_goal_resume_never_picks_a_slug`
- [ ] Must-not-route, each `none`: `take care of it`, `handle this`, `handle that.`, `can you take care of the login audit?`, `I will handle the login audit later`, `focus on this`, `focus on the tests`, `autopilot status please tell me`, `work toward`, `is autopilot status working?`, a 90-character `handle ...` prompt, a two-line prompt, `` `handle the login audit` ``, `/crew:autopilot assign x`. `-k test_autopilot_phrases_that_must_not_route`
- [ ] With `assign` available, a text holding `'`, `"`, `$`, a backtick or a backslash asks and its decision has no command. `-k test_free_text_with_shell_characters_asks`
- [ ] A `goal` route line ends with "tell the user in one line what changed and how to undo it."; no other intent's line does. `-k test_goal_route_line_names_the_undo`
- [ ] Every decision dict has the key `unavailable`; every rendered line for the new rows, with 5000-character fields, is one line of at most `MAX_LINE_CHARS`. `-k "test_render_is_one_bounded_line_whatever_the_fields or test_every_decision_has_every_key"`
- [ ] No row, match or rendered line names approve. `-k test_no_route_ever_names_approve`
- [ ] The existing sabotage anchors are untouched. `-k test_every_route_sabotage_anchor_is_present_exactly_once`, and `git diff origin/main --stat -- plugin/crew/tests/sabotage.py plugin/crew/tests/sabotage_route.py` prints nothing.
- [ ] Through the hook: armed, `autopilot status` puts the `crew route:` line first; unarmed output is byte-identical to before. `python3 -m pytest plugin/crew/tests/test_crew_route_hook.py -q -k "test_armed_autopilot_status_puts_the_route_line_first or test_unarmed_output_is_byte_identical_to_before"`
- [ ] `decide` still writes nothing. `python3 -m pytest plugin/crew/tests/test_crew_route.py -q -k test_decide_writes_nothing`
- [ ] The whole rule passes: `python3 -m pytest plugin/crew/tests/test_crew_route.py plugin/crew/tests/test_crew_route_hook.py plugin/crew/tests/test_crew_context.py -q`
- [ ] README's table lists the five new rows and says a not-landed command gets a line that runs nothing; CONFIG.md section 21 no longer says the table is lifecycle-only. `git grep -n "autopilot status" -- plugin/crew/README.md`
- [ ] Version bumped in `plugin.json`, `marketplace.json`, `PLUGINS.md` and CHANGELOG, committed, then `python3 scripts/check-marketplace.py` exits 0.
- [ ] `python3 scripts/check-tooling-pr.py` accepts the branch as a feature PR (no harness path in the diff).

## Split
- L-0661 (child 1 of T-0057, filed 2026-10-04): sabotage mutations for the autopilot routing rows (tooling-only PR)
- L-0662 (child 2 of T-0057, filed 2026-10-04): plain-text routing rows for autopilot wave, split, sleep and wake
- L-0663 (child 3 of T-0057, filed 2026-10-04): sabotage mutations for the wave, split, sleep and wake routing rows (tooling-only PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
