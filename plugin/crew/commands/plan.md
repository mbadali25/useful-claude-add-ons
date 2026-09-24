---
description: Turn an approved spec into a step-by-step plan, then get it approved
argument-hint: <ticket id> [--approve]
allowed-tools: Read, Write, Edit, Bash, Agent
---

Plan ticket $1. **Redefined for 1.0** — this used to be a standalone second
opinion; that is now step 3 below, optional, inside the real plan phase.

**Method adapted from `superpowers:writing-plans` (Jesse Vincent, MIT). Full
notice in `plugin/crew/NOTICE.md`.** The backing skill is
`plugin/crew/skills/crew-plan/SKILL.md` — load it now; it carries task
right-sizing, the no-placeholders rule and the self-review this file only
summarises.

1. Read `.work/tickets/$1/spec.md`. Refuse to continue without it — say to run
   `/crew:spec $1` first. Note the Touch globs; every step's Files: below must
   fall inside them or the spec needs amending first.
2. Use `crew:explorer` for exact paths and line ranges — a plan step naming
   "the auth module" instead of `src/auth/session.py:40-88` is not
   implementable without re-deriving it.
3. **Optional second opinion.** If the design is non-obvious, write a brief,
   show it to me for approval, send it to `secondOpinion.provider` (the
   `crew-providers` skill says how), and report the disagreement. Fold anything it
   surfaces into the plan below rather than reporting it separately. Skip this
   step for a small or well-understood change and say so.
4. Write `.work/tickets/$1/plan.md`:

```
# $1 plan            spec: .work/tickets/$1/spec.md

### Step 1: <name>
Files: create/modify/test, exact paths, `path:line` where modifying
Test: the check that proves this step, by name or by the command that runs it
Risk: what breaks if this step is wrong, or "low"
- [ ] the concrete actions, not "implement the feature"

### Step 2: ...
```

   No placeholders — "TBD", "handle edge cases", "similar to Step 1" are plan
   failures, not shorthand. Every step ends with something testable.
5. **Self-review before showing me.** Walk the spec's Acceptance list: does
   every line have a step? Walk the steps: does every Files: entry sit inside
   the spec's Touch? A step that doesn't is not silently kept — either the
   step is wrong or the spec is missing a glob; fix whichever is true before
   step 6.
6. **Plan mode.** Show me the plan. Do not start implementing. A plan I have
   not agreed to is not a plan — same rule this file always had.

## On approval

Approval is a receipt, not a nod in chat. Once I say yes, ask me to type
`/crew:approve $1`. **Never run `crew_ticket.py approve` yourself** — the
UserPromptSubmit hook records the approval only from my own prompt. It writes
`<git-common-dir>/crew/tickets/$1/approval.json`,
bound to this plan's hash; editing `plan.md` afterward invalidates it, which
is what makes `/crew:implement`'s refusal mean something. Then set
`plan.md`'s header `status: planned` and `.work/INDEX.md`'s row to match.

## `--approve`

Re-run this file with `--approve` after editing an already-approved plan:
re-check the plan against the spec, then ask me to type `/crew:approve $1`
again so the receipt is regenerated against the new hash, rather than leaving
a stale one.

If `secondOpinion.provider` is `none` or unreachable at step 3 and you chose
not to skip it, say plainly this is a single opinion, not a reviewed one, and
continue.
