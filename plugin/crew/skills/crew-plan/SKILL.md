---
name: crew-plan
description: Turn an approved spec into a step-by-step implementation plan - files, tests and risk per step, no placeholders, self-reviewed against the spec before it is shown. Use once a ticket has an approved spec.md and before any code is touched.
---

# crew-plan

**Adapted from `superpowers:writing-plans` by Jesse Vincent, MIT licensed. The
full copyright and permission notice is in `plugin/crew/NOTICE.md`.** Upstream:
<https://github.com/obra/superpowers>. The task-sizing rule, the no-placeholder
list and the self-review below are upstream's. What crew changed: upstream's
plan header carries its own Global Constraints and Review Focus sections
copied out of a design doc; crew's spec (`spec.md`) already carries Exclusions,
Evidence and Acceptance, so the plan cites it by path instead of duplicating
it, and Files: entries are checked against the spec's Touch globs rather than
against nothing.

Backs `/crew:plan`. That command owns reading the spec, writing `plan.md` and
getting the approval receipt; this skill is the method for building it.

## Core principle

Write for an engineer with zero context on this codebase and no assumed good
taste: which files, what test, how it's proven. The plan already did the
thinking; the person or session executing it should not have to.

## Task right-sizing

A task is the smallest unit that carries its own test cycle and is worth a
fresh reviewer's gate. Fold setup, config and doc steps into the task whose
deliverable needs them. Split only where a reviewer could meaningfully accept
one task while rejecting its neighbor. Each step is one action: write the
failing test, run it, implement the minimal code, run it again, commit.

## Task structure

```
### Step N: <name>
Files: create/modify/test, exact paths, `path:line` where modifying existing code
Test: the check that proves this step, by name or by the command that runs it
Risk: what breaks if this step is wrong, or "low"
- [ ] concrete actions - what to actually do, not what the result should be
```

## No placeholders

These are plan failures, not shorthand - never write them:
- "TBD", "handle edge cases", "add appropriate validation"
- "similar to Step N" (repeat the content; a step may be read out of order)
- a step that names a type, function or file no earlier step defined

## Files: must sit inside the spec's Touch

Before finalizing, walk every step's Files: entries against `spec.md`'s Touch
globs. A step that reaches outside them is not silently kept - either narrow
the step or amend the spec first (`/crew:spec`, then re-approve). This is the
check the scope guard enforces mechanically later; catching it here is
cheaper than catching it from a refused write.

## Self-review, before showing the human

1. **Spec coverage.** Walk each line in the spec's Acceptance list - is there
   a step for it? List any gap and add the missing step.
2. **Placeholder scan.** Re-read for the patterns above.
3. **Interface consistency.** Do names and signatures used in a later step
   match what an earlier step actually defined?
4. **Touch coverage.** Confirmed above - restate it here rather than skip it
   because it was "already checked": this is the review that catches the
   check being forgotten under time pressure, not the check itself.

Fix inline. No need to re-review once fixed - just fix and move on. This is a
checklist you run yourself, not a subagent dispatch.

## The gate

Plan mode. Show the complete plan. Do not start implementing - a plan the
human has not agreed to is not a plan. Once agreed, the command computes and
records the approval receipt; this skill's job ends at a plan worth approving.
