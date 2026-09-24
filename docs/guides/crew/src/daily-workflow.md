---
title: Daily workflow
guide: 2 of 5
produced-by: T4
status: current for crew 1.0 - the commands and the enforcing hooks (plan approval, scope guard, completion audit) below are shipped and wired into hooks.json
---

# Daily workflow

One interactive session owns a ticket through eight phases: brainstorm, spec,
plan, implement, tests, docs, review, done. Every phase but the light one below
writes a file under `.work/tickets/<id>/`, and two of them cannot be skipped
by accident — `/crew:implement` refuses without an approved plan, and
`/crew:done` refuses without a clean review receipt, a clean verify gate, and
a passing completion audit.

For how the scope guard decides what a ticket may touch and what a report
looks like when it refuses a write, see
[`daily-workflow-scope.md`](daily-workflow-scope.md) (T3).

## Full path — worked example

**1. Brainstorm.** You type:

```text
/crew:brainstorm add a --dry-run flag to the migrate command
```

The session mints `T-0091`, creates `.work/tickets/T-0091/`, and asks **one
question at a time**:

> Should `--dry-run` also print what it would do to files that already match
> (no-op writes), or only the ones that would actually change?

You answer. It proposes two approaches, recommendation first, then writes
`.work/tickets/T-0091/direction.md` and stops. You say yes.

**2. Spec.** You type `/crew:spec T-0091`. The session reads the direction,
uses `crew:explorer` to pin down `path:line` evidence, and writes
`spec.md` with Intent, Exclusions, Evidence, Unknowns, Touch and Acceptance.
`.work/INDEX.md` gets a row.

**3. Plan.** You type `/crew:plan T-0091`. The session reads `spec.md`, writes
one step per unit of work in `plan.md` (Files/Test/Risk each), checks every
Files: entry against the spec's Touch globs, and enters **plan mode** to show
you the whole thing. You review it. On your yes, it asks you to type
`/crew:approve T-0091`. crew's prompt hook sees that you typed it and writes
the approval receipt, bound to this plan's exact contents — edit `plan.md` after this and
the receipt no longer matches.

**4. Implement.** You type `/crew:implement T-0091`. First thing it does:
checks the receipt. If you skipped step 3, or edited the plan after
approving it, it refuses here and tells you which. Assuming it passes, it
records the scope base (`scope_base.py --record`), works the plan step by
step — test first, watch it fail, implement, watch it pass — and the
**plan-approval + scope guard hook** blocks any write outside the spec's
Touch globs before it happens, not after.

**5–6. Tests and docs.** Coverage lands as part of implementing the plan's
steps. `/crew:docs` runs next and usually says "none" — most tickets touch no
document that needs updating.

**7. Review.** `/crew:implement` calls `/crew:review T-0091` last, after tests
and docs. Codex reviews the bundle (or Copilot, or the Claude fallback,
whichever survives the author-family strike), reports BLOCK/FIX/NIT lines,
and you fix the BLOCKs. Two rounds total, ticket-wide — a third is refused and
the ticket becomes `NEEDS_REPLAN`.

**8. Done.** You type `/crew:done T-0091`. Three checks, all required: the
review receipt rebuilds clean, the verify gate is clean, and the completion
audit (the whole tree diffed against the scope base) finds nothing outside
scope. Any one failing refuses the close and names what to fix. On success it
appends a metrics row, marks the ticket done, and clears a stale handoff.

## What each hook does, in order

| When | Hook | Does |
|---|---|---|
| Every write | plan-approval + scope guard (`PreToolUse`) | refuses an edit with no approval receipt, or outside the spec's Touch |
| End of turn | verify gate (`Stop`) | refuses to end the turn on a red check |
| End of turn | completion scope audit (`Stop`) | diffs the whole tree against the scope base, catches shell-made writes too |
| Session start | context | brief on branch, open ticket, gate state, codemap freshness |

None of these ask you anything mid-turn — a blocked write or a red gate shows
up as a refusal with a reason, not a prompt.

## Light path — `/crew:fix`

For a small, well-understood change (one subsystem, no new behaviour, known
cause, nothing touching auth/SQL/IaC/secrets/migrations):

```text
/crew:fix the changed-file list in implement.md prints nothing on an empty diff
```

Every phase still runs, compressed:

- **Direction:** one line, not a question round — `Fix: <what you typed>`.
- **Spec:** six lines — Intent, Touch, Acceptance — Exclusions, Evidence and
  Unknowns omitted, not forgotten.
- **Plan:** exactly one step, still shown, still needing the approval receipt.
- **Implement, tests, docs:** same as the full path, sized to one step.
- **Review:** one Codex round instead of two.
- **Done:** the same three checks — the light path does not skip its own gate.

If the change turns out to be bigger than it looked — a second subsystem
shows up, the cause wasn't what you thought — the session says so and hands
off to `/crew:spec <id>` to fill in what the light path left out, rather than
forcing the rest of the ticket through a path that no longer fits it.

## If something refuses

| Refusal | Means | Do |
|---|---|---|
| `/crew:implement` says no approved plan | step 3 was skipped, or `plan.md` changed after approval | `/crew:plan <id>`, then type `/crew:approve <id>` |
| a write is blocked outside Touch | the file isn't in the spec's declared scope | amend `spec.md`'s Touch and re-approve the plan, or don't make the edit |
| `/crew:done` reports `NEEDS_REPLAN` | the review budget (two rounds) is spent | `/crew:plan <id>` for a successor plan; no third round |
| `/crew:done` fails the completion audit | a path outside scope changed, including one a shell command wrote | file it to `TODO.md`, not to this ticket, then rerun |

See [Troubleshooting](troubleshooting.md) for the rest.
