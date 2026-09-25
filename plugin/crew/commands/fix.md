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

Mint the ticket the way `/crew:brainstorm` does: next free `T-####`, create
`.work/tickets/$1/`, append `.work/INDEX.md`. Write
`.work/tickets/<id>/direction.md` as one line: `Fix: $ARGUMENTS`. Show it,
get a yes, move on — no options table, no multi-question round.

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
- globs, from crew:explorer if not obvious
## Acceptance checks
- [ ] the existing verify.json rule this maps to
```

Exclusions, Evidence and Unknowns carry a one-line `none - light path`
rather than real content: a known cause and one subsystem leave little to
exclude or leave unknown. They are written, not omitted, because
`/crew:approve` validates all six headings (`crew_ticket.py` `SECTIONS`) and
refuses a spec missing or leaving empty any one of them. Each heading goes on
its own line - `## Intent      one sentence` on one line is read as a heading
named `Intent      one sentence`, not as `Intent`. If `crew:explorer` or
`/crew:debug` surfaced a landmine, put it in Touch's line as a comment.

## 3. Plan — one step

Write `.work/tickets/<id>/plan.md` with exactly one step: Files, Test, Risk.
Show it. **Approval is still a receipt, not a nod**: ask me to type
`/crew:approve <id>`. Never run `crew_ticket.py approve` yourself — same rule
as the full `/crew:plan`.

## 4. Implement, tests, docs

Same as `/crew:implement` steps 0–6, compressed by the plan already being one
step: refuse without the approval receipt, record scope base, implement,
verify, print the changed-file list, `/crew:docs` (usually "none" at this
scope).

## 5. Review — one round

`/crew:review <id>` after tests and docs, same as the full path, but this
path's review is **one Codex round**, not the normal two — a same-family
fallback still applies if Codex is unreachable, announced the same way
`/crew:review` always announces it.

## 6. Done

`/crew:done <id>` — the same three checks, no exception for having taken the
short path. A fix that skipped its own gate is not a fix, it is an edit.

If at any point the change grows past "one subsystem, known cause, no new
behaviour", stop, say so, and hand off to `/crew:spec <id>` to fill in the
sections this path omitted before continuing.
