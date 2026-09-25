---
description: Fill the ticket contract from an approved direction - Intent, Exclusions, Evidence, Unknowns, Touch, Acceptance checks
argument-hint: <ticket id>
allowed-tools: Read, Write, Edit, Bash, Agent
---

Spec ticket $1. Replaces `/crew:ticket` in 1.0; that command is now a <!-- deliberate -->
removal stub with no behaviour.

1. Read `.work/tickets/$1/direction.md`. If it is missing, this ticket has no
   approved direction — stop and say to run `/crew:brainstorm` first, or
   `/crew:fix` for the light path, which writes a one-line direction inline.
2. Use `crew:explorer` for anything the direction did not already establish —
   the Evidence section below needs `path:line`, not a description.
3. Write `.work/tickets/$1/spec.md`. Every tracker mode writes to the same
   path — `/crew:brainstorm` already created `.work/tickets/$1/` for all four
   modes, so unlike 0.20's `.work/cache/<KEY>.md` split there is one location
   here, not one per mode:

```
# $1 <title>          status: spec   risk: low|med|high
## Intent
2-3 sentences: the outcome, taken from direction.md's Recommendation.
## Exclusions
What this ticket must NOT do. Scope creep starts here, not at implement.
## Evidence
path:line facts this spec rests on, from explorer or the codemap. Not prose.
## Unknowns
Each with how it will be resolved before implement, or "accepted as risk".
## Touch
- `src/area/**` - one path or glob per bullet, in backticks when a note follows
- `tests/area/test_area.py`
## Acceptance checks
- [ ] observable checks, naming the `.crew/verify.json` rule(s) they map to
- [ ] the new test this ticket adds, by name (add one if none exists)
```

   Touch feeds the scope guard (PreToolUse) and `/crew:plan`'s validation: a
   plan step whose Files: are not covered here needs this section amended
   first, not a plan that quietly reaches outside it. `/crew:approve` reads it
   one bullet at a time - one path or glob per bullet, and a bullet that
   carries a note after the path keeps the path in backticks.

4. Append `.work/INDEX.md`: `$1 | spec | <risk> | <this-repo> | <title>`
   (files and Obsidian modes) or push the tracker item to the equivalent state
   (Jira, ServiceDesk Plus) — same rule `/crew:ticket` states for its own
   append. <!-- deliberate -->
5. `/crew:plan`, `/crew:implement`, `/crew:review` and `/crew:done` all refuse
   to run without this file. An empty or placeholder Acceptance list is the
   same as no spec — say so rather than writing one to satisfy the section
   heading.

## Amending an already-planned or already-implementing ticket

Scope expansion is not a quiet edit. Update this file, say what changed and
why, then require a fresh `/crew:plan $1` approval — an approval receipt is
bound to the plan's hash, and a plan written against the old spec does not
cover the new Touch or Acceptance lines. Do this **before** touching any file
the old Touch section did not already cover; the scope guard will refuse the
write anyway, but re-deriving that from a hook message costs more than
stopping here first.

## Multi-repo and cross-references

One ticket per repo. A ticket whose direction spans repos gets one spec here,
cross-referenced by id in the sibling repo's own spec — never one spec that
silently claims two repos' Touch sections.
