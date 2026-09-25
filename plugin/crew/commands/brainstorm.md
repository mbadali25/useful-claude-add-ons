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

Read `.crew/crew.json` (or `.crew/config.json` on an unmigrated repo) for
`tracker`. **Files and Obsidian Kanban tracker modes**: pick the next free
`T-####`, create `.work/tickets/T-####/`, and append
`T-#### | direction | - | <this-repo> | <title>` to `.work/INDEX.md`. Obsidian
mode also adds the `[[T-####]]` card to the board's `backlog` lane, the way
`/crew:ticket` does — a direction is not yet ready work. <!-- deliberate --> **Jira and
ServiceDesk Plus modes**: create the tracker item now with a one-line
placeholder summary, so the id exists before anything else does, and cache it
at `.work/tickets/<KEY>/`.

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

Update `.work/INDEX.md`'s status cell from `direction` to `ready`. Tell me to
run `/crew:spec <id>` next; do not invoke it yourself.

If this is genuinely small — one subsystem, no new behaviour, a known
cause, nothing touching auth/SQL/IaC/secrets/migrations — say so and suggest
`/crew:fix` instead, which compresses this phase to one line rather than
skipping it.
