---
name: crew-execute
description: Execute an approved plan task by task, in this session - TDD per step, a ruling instead of a silent deviation, and only four conditions that stop for a check-in. Use once a ticket has an approved plan.md and implementation is starting.
---

# crew-execute

**Adapted from `superpowers:executing-plans` by Jesse Vincent, MIT licensed.
The full copyright and permission notice is in `plugin/crew/NOTICE.md`.**
Upstream: <https://github.com/obra/superpowers>. The core discipline below -
prove each step with a test watched fail then pass, rule rather than stall,
the four stop conditions - is upstream's. What crew changed: upstream tracks
progress in its own `.superpowers/sdd/` ledger and hands off to a separate
finishing skill; crew already has a scope base, a changed-file print and a
Stop-hook scope audit doing that job, so this rewrite defers to those instead
of building a second ledger.

Backs `/crew:implement` and `/crew:fix`'s implementation phase. Both commands
own the approval check, the scope-base record and the changed-file print;
this skill is the per-step discipline in between.

## Core principle

The plan already did the thinking. Execute it exactly, prove each step with a
test you watched fail and then pass, and leave a record that survives your
own forgetting - the changed-file list and your report, since this method
does not keep a separate ledger file the way upstream's does.

## Per step

1. Read the step's Files, Test and Risk.
2. Write the test first. Run it. Confirm it fails for the reason the step
   expects, not for an unrelated reason (a typo, a missing import) that would
   pass trivially once fixed and prove nothing about the real code.
3. Implement the minimal change the step describes.
4. Run the test again. Confirm it passes.
5. Move to the next step. Do not batch several steps' tests into one run at
   the end - a later step's passing test does not tell you an earlier one's
   assumption was ever validated.

## Rulings, not stalls

Conflicts, ambiguities and plan defects get decided, not escalated by
default. The spec is the binding authority, the plan is its argument, your
judgment settles what neither answers. State the ruling in your report:
`Ruling: <what you decided> - <why> - <what it costs if wrong>`. Deviating
from the plan without stating the ruling is a decision made in secret, and
the next reader of this ticket has no way to tell a deliberate change from a
mistake.

## Four things stop you, and only these

- An irreversible or destructive operation.
- A security-sensitive action.
- A side effect outside this ticket's own branch that norms say to ask about
  first - a merge, a push to a shared branch, a publish.
- A plan so broken every path forward is a guess.

Nothing else pauses execution to check in. The human chose this path to
spend less attention per task, not to approve each one individually - that
approval already happened at the plan gate.

## When a step's output does not match the plan's expectation

Two branches, and only one applies at a time:
- **The plan is wrong** (an assumption about the code that turned out false,
  a step that assumed an interface differently than it exists): rule on it,
  state the ruling, adjust, continue.
- **The code is wrong** (the test fails for a reason inside the change, not
  inside the plan's assumptions): this is a defect, not a planning gap - use
  `crew-debugging`'s Iron Law rather than patching the symptom the failing
  test happened to surface.

## Narration

Between tool calls, narrate at most one short line. The test output and your
final report carry the record; a step-by-step travelogue does not add
evidence, it adds noise a later reader has to skip past.
