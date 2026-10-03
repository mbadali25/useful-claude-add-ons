# T-0025 contextual help - /crew:help, nudges that name the fix, and a simpler surface          status: spec   risk: med
## Decisions (planning, 2026-09-25 - owner to confirm at /crew:approve)
- ONE state reader: T-0004's `crew_autopilot.resume_target` and `next_phase`. `crew_help.py` adds no parsing of INDEX, receipts or ledgers of its own. `crew_status.py` stays the 40-line full report; `/crew:help` is the 8-line "what now".
- ONE phrase table: T-0023's `crew_route.PHRASES`. This ticket adds the `help` rows ("help", "what now", "what's next", "where are we", "how do i <x>") there, and `/crew:help <question>` resolves questions through `crew_route.match`. `crew_help.py` carries no regexes over prompts, and a test asserts that.
- `/crew:help` never runs the command it recommends. It prints; the user or `/crew:autopilot` runs it.
- The surface recommendation below is ADVISORY. Nothing is deleted, renamed, merged or hidden in this ticket (CLAUDE.md "Stop and ask": deleting or renaming a registered entry). This ticket only orders `/crew:help commands` by group, and files the rest to TODO.md for the owner.
## Surface recommendation (advisory, not implemented here)
`plugin/crew/commands/` holds 33 files on main (34 with T-0004's `autopilot.md`, 35 with this ticket's `help.md`).
- **Core, shown first everywhere (11):** brainstorm, spec, plan, approve, implement, review, done, fix, autopilot, status, help.
- **Reached through `/crew:help` or `/crew:autopilot`, off the README's primary table (13):** docs, diagram, onboard, reference, verify, runbook (the refresh commands T-0008 names, which autopilot's refresh phase runs); handoff (context-watch asks for it); init, config, model, migrate, upgrade (setup and one-time); debug, survey (investigation).
- **Merge candidates, owner to decide:** jira-sync + sdp-sync + obsidian-sync -> one `/crew:sync` dispatching on the tracker mode; migrate + upgrade -> one `/crew:migrate` that runs the pre-0.20 upgrade first when needed.
- **Keep, specialist:** change, emergency, gate, promote, split, webtest.
- **Remove at the next major, ask first:** `ticket.md`, `work.md`. These are 10-line removal stubs (`plugin/crew/commands/ticket.md`, `work.md`).
## Intent
`/crew:help` with no argument prints at most 8 lines: the active ticket and its phase from disk, what the ticket waits on, the one next command and why, and 2-3 related commands. `/crew:help <command>` prints the command's purpose, when to use it, its arguments, and what comes next. `/crew:help <question>` maps the question to a command through T-0023's table and answers as for that command. `/crew:help commands` lists every command by group, core first. The lifecycle refusals that today leave the user stuck end with the one command that fixes it.
## Exclusions
- No deleting, renaming, merging or hiding any command file, and no change to any command's behaviour beyond the refusal text named in Evidence.
- No second state reader and no second phrase table.
- No running of the recommended command; `/crew:help` is read-only (git with `GIT_OPTIONAL_LOCKS=0`, no file written).
- No approval: help names `/crew:approve <id>` as something the USER types, never something it or Claude runs.
- No new hook, and no change to hook exit codes or to what any guard decides. The scope guard change is message text only.
## Evidence
- State reader (T-0004, branch commit ac413569 in the `uca-t0004` worktree, not on main): `crew_autopilot.resume_target` (`plugin/crew/hooks/scripts/crew_autopilot.py:338` there) returns ticket, source, stop, reason and `next`. `next_phase` (`:277`) returns phase, stop, reason and command, with the phase table in its module docstring (`:15-33`). `open_index_tickets` is `:131`. The module is read-only and exits 0 (docstring `:10-13`).
- `crew_status.py` is the full read-only report, capped at 40 lines (`plugin/crew/hooks/scripts/crew_status.py:36`, `collect` `:185-210`). Its open-ticket list reads INDEX itself (`_ticket_lines` `:85-103`), and it is left as is.
- Phrase table: T-0023's `crew_route.PHRASES` / `match` (`.work/tickets/T-0023/spec.md`, plan step 1).
- Command frontmatter carries `description` and `argument-hint` (e.g. `plugin/crew/commands/implement.md:1-5`, `approve.md:1-6`). Lifecycle command files are capped at 120 lines and listed in `NEW_COMMANDS` (`plugin/crew/tests/test_lifecycle_commands.py:25`, `:27-28`).
- Refusal audit. These leave the user stuck or send them the wrong way:
  - `plugin/crew/commands/implement.md:15-26`: step 0 runs `crew_ticket.py validate`, which checks the contract, not approval (`crew_ticket.py:427-460` never reads a receipt). It then points at `/crew:plan $1 --approve`, which records nothing (`plugin/crew/commands/plan.md:61-66` only asks the user to type `/crew:approve $1`). The fix is `crew_ticket.py status --ticket $1` (`crew_ticket.py:482`, CLI `:769-772`) and "the user types `/crew:approve $1`", or `/crew:plan $1` when plan.md is missing.
  - `plugin/crew/commands/review.md:21-22`: "no ticket id and no single active ticket - stop and ask" names no command. The fix: name `/crew:review <ticket-id>` and `/crew:help`.
  - `plugin/crew/hooks/scripts/scope_guard.py:157-159` + `:291-296`: when the ticket has NO approved plan, the deny text says "To widen scope: amend ... ## Touch" before `/crew:approve`, which is misleading. The fix: for status `none`, "no approved plan: the user types `/crew:approve <id>`" (or `/crew:plan <id>` when plan.md is missing); the widen-scope text stays for an out-of-Touch path.
- Refusals that already name their fix (left alone): `spec.md:10-12` (`/crew:brainstorm` or `/crew:fix`), `plan.md:16-17` (`/crew:spec`), `done.md:17-19` (`/crew:review` or `/crew:plan`), `approve.md:23-25` (`crew_ticket.py validate`), `plugin/crew/hooks/scripts/completion_audit.py:129-135` (`/crew:approve`), and the scope guard's broken pointer (`scope_guard.py:223-233`, activate/deactivate).
- The scope guard's sabotage rows anchor on its source text (`plugin/crew/tests/sabotage_scope.py:31-35`, `GUARD`), so the message change must keep each anchor present exactly once. Registry: `plugin/crew/tests/sabotage.py:2927`.
## Unknowns
- **Depends on T-0004 (hard)** for `crew_autopilot`, and **on T-0023 (hard)** for `crew_route.PHRASES`/`match`. This ticket starts after both merge. The phase names `where` covers are read from T-0004's `next_phase` table at implementation. If T-0004 exposes no constant listing them, step 1's coverage test lists them from its docstring and says so.
- Whether Claude Code has a frontmatter field that hides a plugin command from the `/` menu was not verified. "Hide" in the recommendation means off the README's primary table and `/crew:help`'s first screen.
- Coordination with T-0018 (`crew_autopilot.py status`, 12 lines, `.work/tickets/T-0018/spec.md`). It reads the same `crew_autopilot` state and defines a "waiting on" mapping per phase. Whichever of T-0018 and this ticket lands second reuses the other's waiting-on function and does not define a second one. `/crew:autopilot status` is the per-ticket detail view; `/crew:help` is the 8-line "what now".
- Coordination: T-0023 and this ticket both edit `crew_route.py`, and T-0023 lands first. The crew version is assigned at implementation.
- Codex is out until 2026-10-01, so this ticket's review is same-family (crew:reviewer). Accepted as risk, and announced.
## Touch
- `plugin/crew/hooks/scripts/crew_help.py`
- `plugin/crew/hooks/scripts/crew_route.py`
- `plugin/crew/hooks/scripts/scope_guard.py`
- `plugin/crew/commands/help.md`
- `plugin/crew/commands/implement.md`
- `plugin/crew/commands/review.md`
- `plugin/crew/tests/test_crew_help.py`
- `plugin/crew/tests/test_crew_route.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/tests/test_scope_guard.py`
- `plugin/crew/tests/sabotage_help.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/README.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
- `TODO.md`
## Acceptance checks
- [ ] `crew_help.py where --root .` prints at most 8 lines for every state (one test per `next_phase` phase, plus no ticket, several open tickets, broken pointer). Line 1 is where (ticket, source, phase). Line 2 is what it waits on. Then one `next:` line with exactly one command and why, and 2-3 `also:` lines. A `stop` phase's `next:` is the human command (e.g. "you type `/crew:approve T-1`"). Several open tickets -> it lists them and says `/crew:help` cannot pick one, never the first.
- [ ] `crew_help.py about <x>`: every file in `plugin/crew/commands/` resolves by name, with or without `/crew:`, to purpose, when, arguments and next. A question resolves through `crew_route.match` (`test_help_questions_use_the_route_table`). `test_help_has_no_phrase_table_of_its_own` finds no prompt regex in `crew_help.py`. An unknown input lists the core group.
- [ ] `crew_help.py about commands` groups every command file. `test_every_command_is_in_exactly_one_group` fails when a new file is added without a group, and the removal stubs are in `removed`.
- [ ] `crew_help.py` writes nothing (mtime snapshot) and exits 0.
- [ ] `/crew:help` (`commands/help.md`) is under 120 lines, is in `NEW_COMMANDS`, passes `test_lifecycle_commands.py` and `validate-prompts.py`, and prints the script's output verbatim.
- [ ] T-0023's table gains the `help` rows. `test_crew_route.py` covers them, and "next" and "done" alone still route nowhere.
- [ ] Nudges: `implement.md` step 0 runs `crew_ticket.py status` and names `/crew:approve $1` / `/crew:plan $1`, never `--approve` (`test_implement_refusal_names_the_fix`). `review.md`'s no-ticket stop names `/crew:review <ticket-id>` and `/crew:help`. The scope guard's no-approval deny names `/crew:approve <id>` (or `/crew:plan <id>` with plan.md absent) and not "To widen scope" (`test_scope_guard.py`, module and both flavours). The existing scope-guard must-block/must-allow suite is unchanged and green.
- [ ] `sabotage_help.py` is registered in `sabotage.py:2927`. Each of these turns a named test red: a 9th line in `where`; picking the first of several open tickets; a local regex table in `crew_help.py`; implement.md back to `--approve`; the scope-guard no-approval text back to "To widen scope". The `sabotage_scope.py` anchors are still present exactly once.
- [ ] README documents `/crew:help`, with the core group first. TODO.md carries the advisory surface recommendation as an owner decision. `.crew/verify.json` maps `crew_help.py`, `commands/help.md` and the new tests to `python3 -m pytest plugin/crew/tests/test_crew_help.py plugin/crew/tests/test_crew_route.py plugin/crew/tests/test_lifecycle_commands.py -q`. `python3 scripts/check-marketplace.py` passes. The version is bumped, with a CHANGELOG entry.
