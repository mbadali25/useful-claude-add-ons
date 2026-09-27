---
description: Brainstorm a request into an approved direction, before it becomes a spec
argument-hint: <what needs doing>
allowed-tools: Read, Write, Bash, Agent, AskUserQuestion
---

Brainstorm: $ARGUMENTS

**Method adapted from `superpowers:brainstorming` (Jesse Vincent, MIT). Full
notice in `plugin/crew/NOTICE.md`.** The backing skill is
`plugin/crew/skills/crew-brainstorm/SKILL.md` — load it now with the `Skill`
tool; it carries the full method and the "one question per message" rule this
file only summarises.

## 1. Mint the ticket

Brainstorm mints the key, before any code is touched or any branch named — the
same rule `commands/ticket.md` states ("the key exists before the branch
does"), moved one phase earlier because 1.0 starts the ticket at brainstorm,
not at spec.

Read the tracker kind with `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py resolve --root .`
— it reads `.crew/crew.json` and `.crew/config.json` alike. `could not tell`
means the two disagree: show me its line and stop; never pick one.
**Files and Obsidian Kanban**: pick the next free `T-####`, then run

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py create --root . --ticket T-#### --title "<title>"
```

It appends `T-#### | direction | - | <this-repo> | <title>` to `.work/INDEX.md`
and, for Obsidian, adds the `[[T-####]]` card to the board's backlog lane and
the vault ticket note — a direction is not yet ready work. Print its lines
verbatim. If a line says `id taken`, that id is not yours — another session or
repo holds it: pick the next free id, run `create` again, and write nothing
under the taken one. Then create `.work/tickets/T-####/`. On exit 3 run the
command it printed. On any other exit 1 tell me `tracker not updated: <reason>`
and carry on — the ticket exists; nothing is undone. **Jira and ServiceDesk Plus**: create the tracker item now through MCP
with a one-line placeholder summary, so the id exists before anything else
does, and cache it at `.work/tickets/<KEY>/`.

## 2. Establish shared understanding

Discover intent: identify the outcome, who it is for, what success looks
like. Ask **one question per message** — never a batch. Prefer multiple
choice; open-ended is fine when there is no natural set of options. When the
request already states purpose and constraints, reflect that back instead of
re-asking.

Use `crew:explorer` for any question whose answer is "what does this repo
already do" — never grep it yourself, and nothing explorer returns leaves this
session except the question it informs.

## 3. Propose, don't just ask

Once the shape is clear, propose 2–3 approaches with tradeoffs, **recommendation
first**, and say why. This is the direction the ticket takes, not an
implementation plan — no file list, no steps; that is `/crew:plan`'s job once
a spec exists.

## 4. Write the direction and stop for approval

Write `.work/tickets/<id>/direction.md`:

```
# <id> direction
## Ask         the original request, verbatim
## Options     each considered, with tradeoffs
## Recommendation   the one proposed, and why
## Open questions   anything still unresolved, or "none"
```

Show it and stop. Do not proceed to `/crew:spec` in the same turn — a
direction I have not agreed to is not a direction.

## 5. On approval

Move the ticket from `direction` to `ready` — never by editing `.work/INDEX.md`:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket <id> --to ready
```

Print its lines verbatim; the card stays in the backlog lane until a spec
exists. On exit 3 run the command it printed; on exit 1 tell me
`tracker not updated: <reason>`. Tell me to run `/crew:spec <id>` next; do not
invoke it yourself.

If this is genuinely small — one subsystem, no new behaviour, a known
cause, nothing touching auth/SQL/IaC/secrets/migrations — say so and suggest
`/crew:fix` instead, which compresses this phase to one line rather than
skipping it.
