# T-0020 /crew:autopilot focus - a scope lock on one ticket          status: spec   risk: high
## Decisions (owner, Matthew Badali, 2026-09-25)
- `/crew:autopilot focus [<ticket>]` locks autopilot onto one ticket, and `focus off` releases it. While focus is on, autopilot refuses to start or switch to any other ticket.
- Out-of-scope findings are filed to TODO.md and never fixed in the diff. That restates `plugin/crew/commands/implement.md:62-63` as a lock.
- Focus state is per worktree, in crew state. It reuses the active-ticket pointer rather than new state. No new hook.
- Autopilot reminds the owner that Claude Code's built-in `/focus` only toggles the display and that only the user can type it.
## Intent
Focus is this worktree's active-ticket pointer, and nothing else:
- `focus <ticket>` runs `crew_ticket.activate`. It refuses a ticket with no `.work/tickets/<id>/`, and a pointer already naming a different ticket.
- `focus off` runs `crew_ticket.deactivate`.
- `focus` alone shows the pointer and `scope.mode`.

While the pointer is set (`resolve_active` source `active-ticket`), the router (T-0018) refuses several things:
- `run` for any other ticket, whether named or taken from the handoff;
- `assign`;
- `goal`.

Each refusal names the focused ticket and `/crew:autopilot focus off`. A broken pointer refuses everything except `status` and `focus off`. After the ticket's plan is approved, each `next` also runs the completion audit's own `audit(root, ticket)` read-only. Any changed path outside the ticket's Touch stops `run` as `drift` and lists the paths. `focus --findings` names where an out-of-scope finding goes: `TODO.md` when Touch covers it, otherwise `.work/tickets/<id>/out-of-scope.md` (always writable), because the scope guard exempts nothing outside Touch. Every `focus` output ends with the `/focus` reminder. This answers the owner's "rabbit holes" ask: autopilot cannot wander to another ticket, cannot carry an unrelated change past the next phase, and has somewhere to put what it noticed.
## Exclusions
- No new state file, no new config key, and no change to `crew_ticket.py`, `scope_guard.py`, `completion_audit.py` or `plugin/crew/hooks/hooks.json`.
- No new hook: see the direction's option 3. Under `scope.mode` off, focus is enforced by autopilot's router and drift stop only, and `focus` says so.
- No change to `scope.mode`. Focus never arms or relaxes the guard.
- Autopilot never releases focus itself. `crew_ticket.deactivate` is called only from `focus off` typed by the owner as the command's arguments.
- No `/focus` emulation, and no claim that the built-in `/focus` scopes anything.
- No fixing of an out-of-scope finding in the focused ticket's diff.
## Evidence
- The pointer: `plugin/crew/hooks/scripts/crew_ticket.py:68-82` (a JSON map from worktree top-level to ticket id under `<git-common-dir>/crew/active-ticket`; a broken pointer never falls back to INDEX). `activate` is at `:621` and checks only the id shape via `check_ticket`, not the folder. `deactivate` is at `:632`. `resolve_active` is at `:642`, returning `(ticket, source, broken)` with source `active-ticket` or `.work/INDEX.md`. The CLI is at `:734-735`. No lifecycle command calls `activate` on main (only the README table `plugin/crew/README.md:759` and the guard messages).
- The guard reads the same pointer: `plugin/crew/hooks/scripts/scope_guard.py:271`. With `scope.mode` off it exits first (`:10-11`). A broken pointer is refused (`:17-19`). With no active ticket it allows (`:20-21`). Otherwise only the ticket's own files and Touch are allowed, and "Nothing else is exempt: not `.crew/`, not `TODO.md`" (`:22-30`). The pointer file is refused to Write/Edit (`:12-16`). Running `crew_ticket.py activate` from Bash is must-allow (`plugin/crew/tests/test_scope_guard.py:325`).
- The audit: `completion_audit.audit(root, ticket)` `plugin/crew/hooks/scripts/completion_audit.py:112` returns `(ok, lines)`. It is paths only, runs with `GIT_OPTIONAL_LOCKS=0` (`:12-18`), and returns every changed path outside Touch, or all of them when Touch is not approved (`:126-145`). `--check` runs it whatever `scope.mode` says (`:46`). As a Stop hook it is silent under `off` (`:171`) and reads the pointer at `:173`.
- Registered hooks, unchanged: scope guard `plugin/crew/hooks/hooks.json:31-33`, completion audit `:62-63`.
- The out-of-scope rule today: `plugin/crew/commands/implement.md:62-63` ("File it to `TODO.md`, not to the diff"). TODO entry shape: `plugin/crew/skills/crew-docs/SKILL.md:85-96` (why deferred, what would unblock it) and `TODO.md:3-5` (each entry carries the `path:line` it came from).
- Claude Code's `/focus`: display-only, "just your prompt, summary, and response", fullscreen rendering only, no documented model or hook invocation (https://code.claude.com/docs/en/commands.md, read 2026-09-25 via crew's claude-code-guide; documented, not tested here).
- The open ask: `/root/.claude/projects/-repos-personal-useful-claude-add-ons/memory/crew-plan-before-execute.md` ("roles drifting into unrelated rabbit holes"; machine-local, not in the repo).
## Unknowns
- **Depends on T-0004 (hard) and T-0018 (hard, the router).** The router checks run before `assign` (T-0019) and `goal` (T-0012) whether or not those have landed.
- **Every explicit pointer becomes a focus.** Someone who ran `crew_ticket.py activate` for the scope guard is now also focused. This is accepted deliberately: under `report`/`block` the guard already judges every write against that ticket's Touch, so driving another ticket beside it was already refused write-by-write. The INDEX fallback (`resolve_active` source `.work/INDEX.md`) is never a focus.
- **TODO.md is writable only when Touch covers it.** The scope guard exempts nothing (`scope_guard.py:28-30`). Findings go to `.work/tickets/<id>/out-of-scope.md` otherwise, and `done`-time filing to TODO.md is left to the owner or a later ticket, as T-0014 did. Named so the owner can instead require `TODO.md` in every focused ticket's Touch.
- **Drift before approval is not judged.** Before approval, `audit` fails every changed path because Touch is unapproved. The drift stop therefore runs only once `crew_ticket.accepted` is `approved`, and before that the spec and plan phases write only `.work/`, which the audit excludes.
- **Not a security boundary.** A session can run `crew_ticket.py deactivate` itself. The code-side rule (one call site) and review hold it, which is the same threat model as `scope_guard.py:34-41`.
- Codex is out until 2026-10-01, so the review is same-family. That is accepted as a risk and announced.
## Touch
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_focus.py`
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/README.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
## Acceptance checks
- [ ] `crew_autopilot.py focus --root . --ticket <id>` activates the pointer for this worktree only, and a second worktree of the same repo is unaffected. It refuses a ticket with no folder, and a pointer already on another ticket, with nothing written. `--off` clears this worktree's entry only. With neither flag it shows `focus=<id>|none|broken <why>` and `scope.mode` (tests in `test_crew_autopilot_focus.py`)
- [ ] `focus_guard`: with focus on T-A, `route` refuses `run T-B`, a handoff naming T-B, `assign` and `goal`. It allows `run`/`run T-A`, `status` and `focus off`. A broken pointer refuses all but `status` and `focus off`. The INDEX fallback is never a focus (tests per case)
- [ ] drift: focused and approved, a changed path outside Touch makes `next` stop as `drift` and list the path. Unapproved means no drift judgement. Not focused means `next` behaves exactly as in T-0004 (tests)
- [ ] `focus --findings --ticket <id>` prints `TODO.md` when Touch covers it, else `.work/tickets/<id>/out-of-scope.md` with the reason (test)
- [ ] every `focus` output ends with the reminder that Claude Code's `/focus` only toggles the display and only the user can type it (test)
- [ ] `crew_ticket.deactivate` has exactly one call site in `crew_autopilot.py`, inside the `--off` path (AST test), and `autopilot.md` names `focus off` only in its focus section (text test)
- [ ] `autopilot.md`'s focus section is 6 lines or fewer and the file stays at 120 lines or fewer. `hooks.json` is byte-identical to main (test)
- [ ] sabotage: the INDEX fallback read as a focus, `focus_guard` allowing a switch, drift reading `audit`'s failure as a pass, and a second `deactivate` call in `next_phase`. Each turns a named test red
- [ ] `.crew/verify.json` maps the new test. The crew version is one patch past main at merge, with a CHANGELOG entry. The README's "Scope and approval" states that focus is the active-ticket pointer
