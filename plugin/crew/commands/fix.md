---
description: The light path - every lifecycle phase present, each compressed to one step
argument-hint: <one sentence - what is wrong and where>
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Fix: $ARGUMENTS

**Only for:** one subsystem, no new behaviour, a known cause, nothing
touching auth, SQL, IaC, secrets or a migration. If any of those is untrue,
say so and switch to the full path (`/crew:brainstorm`) instead of forcing
this one to fit — the ratchet is one way: hidden complexity discovered
mid-fix upgrades the path, nothing downgrades mid-task.

**Compressed, not skipped.** Every phase below is the full lifecycle's phase,
shortened to its smallest useful form — not a shortcut around approval or
review.

## 0. Debug first if this is a defect

A defect (broken, wrong, flaky, regressed) gets `/crew:debug` before anything
below; a feature does not. Feed its root-cause line into step 2.

## 1. Direction — one line

Read the tracker kind first, as `/crew:brainstorm` step 1 does:
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py resolve --root .`;
on `could not tell`, show me its line and stop. **Files and Obsidian**: mint
the ticket the way `/crew:brainstorm` step 1 does (next free id, this box's prefix), then
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py create --root . --ticket <id> --title "<title>"`.
If a line says `id taken`, that id is not yours: pick the next free id, run
`create` again, and write nothing under the taken one. On any other failure,
stop: show me its lines and write nothing under that id. Only then create
`.work/tickets/<id>/`. **Jira and ServiceDesk Plus**: no local `T-####`;
create the item through MCP as `/crew:brainstorm` step 1 says, use its key as
`<id>`, and cache it at `.work/tickets/<KEY>/`; a `delegated` line or exit 3
from `create` is that instruction, not a failure to stop on. Then write
`.work/tickets/<id>/direction.md` as one line: `Fix: $ARGUMENTS`. Show it,
get a yes, move on — no options table, no multi-question round.

**Every later tracker call in this file**: print its lines
verbatim; on exit 3 run the command it printed; on exit 1 tell me
`tracker not updated: <reason>` and carry on — the phase stands, nothing is
undone.

## 2. Spec — six short sections

Write `.work/tickets/<id>/spec.md`:

```
# <id> <title>          status: spec   risk: low
## Intent
one sentence
## Exclusions
none - light path
## Evidence
none - light path
## Unknowns
none - light path
## Touch
- `path/or/glob/**` - one per bullet, from crew:explorer if not obvious
## Acceptance checks
- [ ] the existing verify.json rule this maps to
```

Exclusions, Evidence and Unknowns carry a one-line `none - light path`
rather than real content: a known cause and one subsystem leave little to
exclude or leave unknown. They are written, not omitted, because
`/crew:approve` validates all six headings (`crew_ticket.py` `SECTIONS`) and
refuses a spec missing or leaving empty any one of them. Each heading goes on
its own line - `## Intent      one sentence` on one line is read as a heading
named `Intent      one sentence`, not as `Intent`. Touch takes one path or
glob per bullet. If `crew:explorer` or `/crew:debug` surfaced a landmine, add
it after the path on that bullet, keeping the path in backticks
(`` - `src/x.py` landmine: ... ``) and writing the note itself WITHOUT
backticks - an unquoted path followed by a note is refused as "not one path",
and a second backtick span in the note is refused as "one path per bullet".

Then `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket <id> --to spec`.

## 3. Plan — one step

Write `.work/tickets/<id>/plan.md` with exactly one step: Files, Test, Risk.
Show it. **Approval is still a receipt, not a nod**: ask me to type
`/crew:approve <id>`. Never run `crew_ticket.py approve` yourself — same rule
as the full `/crew:plan`. Once approved,
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket <id> --to planned`.

## 4. Implement, tests, docs

Same as `/crew:implement` steps 0–6, compressed by the plan already being one
step: refuse without the approval receipt, record scope base, print the
recurring-findings checklist for the ticket's paths and keep it open while you
implement, verify, print the changed-file list, `/crew:docs` (usually "none" at this
scope), then the self-check and its stamp. The tracker moves as there:
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket <id> --to in-progress`
when implementing starts, and
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket <id> --to review`
before step 5.

## 5. Review — one round

`/crew:review <id>` after tests and docs, same as the full path, but this
path's review is **one Codex round**, not the normal two — a same-family
fallback still applies if Codex is unreachable, announced the same way
`/crew:review` always announces it.

## 6. Done

`/crew:done <id>` — the same three checks, no exception for having taken the
short path. A fix that skipped its own gate is not a fix, it is an edit.

If at any point the change grows past "one subsystem, known cause, no new
behaviour", stop, say so, and hand off to `/crew:spec <id>` to replace the
`none - light path` sections with real content before continuing.
