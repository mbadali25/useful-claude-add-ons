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
`/crew:done` refuses without a clean review receipt, a verify gate settled for
HEAD, and a passing completion audit. Settled means every rule passed here, or
the `verify-gate` CI receipt for HEAD is VERIFIED: a rule too big for the Stop
budget is deferred to CI, and a Stop turn where 0 rules ran proves nothing.

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

If the ticket cannot start before others close, the spec carries an optional
`depends-on: [T-0088, T-0090]` line under its header. `blocked` is then derived
from it, never typed: any dependency that is open, `cancelled`, `superseded` or
cannot be read blocks, and `done` or `merged` unblocks
(`hooks/scripts/crew_ticket_state.py`). The line is hashed with the spec, so
changing it needs `/crew:approve` again. `needs-replan` is derived the same way,
from the review ledger.

**3. Plan.** You type `/crew:plan T-0091`. The session reads `spec.md`, writes
one step per unit of work in `plan.md` (Files/Test/Risk/Standards each), checks every
Files: entry against the spec's Touch globs, and enters **plan mode** to show
you the whole thing. You review it. On your yes, it asks you to type
`/crew:approve T-0091`. crew's prompt hook sees that you typed it and writes
the approval receipt, bound to this plan's exact contents — edit `plan.md` after this and
the receipt no longer matches.

**4. Implement.** You type `/crew:implement T-0091`. First thing it does:
checks the receipt. If you skipped step 3, or edited the plan after
approving it, it refuses here and tells you which. Assuming it passes, it
records the scope base (`scope_base.py --record`; kept if `crew_ticket.py
activate` already recorded it, and measured against `tickets.baseBranch`
when your branches come from `development`), works the plan step by
step — test first, watch it fail, implement, watch it pass — and the
**plan-approval + scope guard hook** blocks any write outside the spec's
Touch globs before it happens, not after. Before the first step it prints the
recurring-findings checklist (`recurring_findings.py --ticket T-0091`): the
defect classes earlier reviews kept finding on paths like the spec's Touch
list, a few probes each, kept open while the plan is worked and handed to
whichever developer types.

**5–6. Tests and docs.** Coverage lands as part of implementing the plan's
steps. `/crew:docs` runs next and usually says "none" — most tickets touch no
document that needs updating. Then `crew_gitignore.py check` asks whether the
ticket brought a language or manifest whose ignore patterns are missing: it adds
them only if the spec's Touch covers `.gitignore`, and otherwise the PR body lists
them and the next `/crew:onboard` adds them.

**6b. The standards self-check.** Before the review, the session answers every
development standard in the effective set (crew's generic GEN standards, any
per-language set a changed file matches, and this repository's
`.crew/standards.md` overlay) in `.work/tickets/T-0091/selfcheck.md`:
`addressed` with evidence, or `n/a` with a reason. `crew_standards.py stamp`
refuses an incomplete answer sheet and binds a complete one to the exact
review bundle, so any later edit needs a new stamp.

**7. Review.** `/crew:implement` calls `/crew:review T-0091` last, after tests,
docs and the self-check; without a current stamp the review refuses before it
spends a round. Codex reviews the bundle (or Copilot, or the Claude fallback,
whichever survives the author-family strike), reports BLOCK/FIX/NIT lines,
and you fix the BLOCKs. Two rounds total, ticket-wide — a third is refused and
the ticket becomes `NEEDS_REPLAN`. Under `/crew:autopilot`, a final round with a
BLOCK stops for you unless you set `autopilot.maxAutoReplans` (default `0`, off):
then autopilot rejects it itself, writes a successor plan that quotes every BLOCK
and FIX line, approves it under `autopilot.approval` and reviews again, at most
that many successor plans per ticket. Each round's findings go into a
`standards-proposals-r<N>.md` file, one row per finding, once the review ledger
records that round as CLEAN or FINDINGS (an INCOMPLETE round gets none); you
approve or reject each proposed standard, and nothing is added to a standards
file on its own.

With parallel lanes in one clone, arm its **merge train** once (`crew_train.py arm`, L-0520).
Lanes still implement at the same time, overlapping Touch or not; only gate and land queue.
The review round takes the train itself (L-0526; `crew_train.py acquire --ticket T-0091` does
the same by hand): a ticket whose Touch overlaps one already holding it waits - `/crew:review`
stops with exit 10, colliding paths named, no round spent - and gates next, in the order the lanes
reached their gate, while a ticket with a disjoint Touch gates at once. Catch up with `crew_train.py catch-up --ticket
T-0091` - a `git merge` of the base, never a rebase, with git rerere on so a conflict resolved
once replays next time. A replay is left unstaged and listed: inspect it and `git add` it; the
review prompt lists it for the reviewer. crew never turns on `rerere.autoupdate`, and the version files
(`plugin.json`, `marketplace.json`, `PLUGINS.md`, `CHANGELOG.md`) are never replayed - they come
back conflicted, named as forgotten, for you to resolve by hand.

**8. Done.** You type `/crew:done T-0091`. Three checks, all required: the
review receipt rebuilds clean, the verify gate is clean, and the completion
audit (the whole tree diffed against the scope base, not counting a file that
is byte-identical to main as last merged) finds nothing outside scope. Any one failing refuses the close and names what to fix. On success it
appends a metrics row, marks the ticket done, and clears a stale handoff.

With the train armed, landing is part of done: `crew_train.py check-land --ticket T-0091 --pr
<n>` refuses unless T-0091 holds the train, `git merge-tree` against the base is clean, the base
has not moved in Touch paths, and HEAD carries the review receipt and a green gate; then it prints
`gh pr merge <n> --merge --match-head-commit <sha>` for you to run (the train never merges; only
autopilot's ship step does, under `autopilot.ship`; with `autopilot.deploy` set, its deploy
phase then names `/crew:promote <env>` for the first GitHub environment, or stops at
`deploy-target` / `failed-deploy`). When it
refuses, land in this order: `crew_train.py catch-up` (resolve any conflict), bump the version one
past the base's, refresh the artifacts, commit, gate the merged head, review it again if
`review_ledger.py --check-receipt` reads stale, then `check-land` again, so the tree the gate
passed is the tree that lands. After the review, a re-anchor changes only the
`anchor:` sha and regenerates the rules; its provenance goes in the ticket's `notes.md`. After the
merge, `crew_train.py release --ticket T-0091 --merged <merge sha>` frees the train and tells every
overlapping lane to merge the base now.

## What each hook does, in order

| When | Hook | Does |
|---|---|---|
| Every write | plan-approval + scope guard (`PreToolUse`) | refuses an edit with no approval receipt, or outside the spec's Touch |
| End of turn | verify gate (`Stop`) | runs the rules for what changed that fit `verify.stopBudgetSeconds`; refuses to end the turn on a red check, never on a deferral (a rule too big for the budget goes to CI) |
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

## Web testing — `/crew:webtest`

For a ticket whose acceptance criteria describe UI behaviour (the `stack-web` skill
triggers on `playwright.config.*`, `@playwright/test`, or an Angular e2e suite),
`/crew:webtest` sits inside the normal eight phases rather than replacing them:

1. **Planner.** `playwright-test-planner` reads the ticket's acceptance criteria and
   writes `specs/<ticket>.md` — what to test, not code yet.
2. **Plan.** crew's own `/crew:plan` reads that spec the same way it reads any other
   Files/Test/Risk plan, and needs the same approval receipt before implement starts.
3. **Generator.** `/crew:implement` calls `playwright-test-generator` against the
   approved spec to write the actual `*.spec.ts` files.
4. **Healer.** A failing generated test goes to `playwright-test-healer` for
   locator/wait repairs only. **A Healer "skip" is a finding, not a pass** — it means
   the healer decided the feature itself is broken, and review is where that surfaces
   rather than sailing through as a green suite.
5. **Review.** The reviewer gets the trace zip (`trace: 'on-first-retry'`) and the axe
   accessibility attachment alongside the diff, the same way it gets the completion
   audit today.

Visual regression (`toHaveScreenshot`) only runs inside
`mcr.microsoft.com/playwright:v1.63.0-noble` — a baseline captured on a bare host does
not match CI's font hinting and subpixel rendering, and fails every later run for
reasons unrelated to the change under test. Outside that image the visual rule reports
**UNVERIFIED**, not a pass; see [Troubleshooting](troubleshooting.md).

## What is waiting on me

`/crew:status` prints one `waiting` line: how many open tickets are stopped on
you. `/crew:status --owner` lists them, one line per ticket with the command
to type or the question to answer, for example `T-5  approve  /crew:approve
T-5`. The list comes from the same phase table `/crew:autopilot` uses, so the
two never disagree. It runs nothing and never rebuilds a review bundle: a
ticket whose finished review would need one shows as `review-unread`, and
`/crew:autopilot status <id>` reads it. A hold whose revisit date is still ahead
and a blocked ticket are only counted (`2 held, 1 blocked`); a hold that is due
is listed as `revisit` with its reason. No `.work/INDEX.md` prints `waiting
unknown (...)`, never "nothing on you".

## After autopilot rejects a review round itself

With `autopilot.maxAutoReplans` set, autopilot may reject an out-of-rounds BLOCK round and plan
again. It approves that successor plan only when the plan quotes every BLOCK and FIX line of the
rejected round as whole lines; `crew_autopilot.py replan-check --ticket <id>` shows the same answer
without approving. Your own `/crew:approve` is never held to it.

## Contracts between two sessions

When two sessions build against each other (a service and its client, two
repositories sharing a format), the interface goes on the coordination channel
the claims use, as a numbered version with a content hash:

1. One side writes the draft: `crew_contract.py put --name <n> --file <path>`.
   While it is a draft, `put` replaces it in place.
2. Each side, once its ticket is approved, records what it built against:
   `crew_contract.py build-against --name <n> --version <N> --ticket <id>`.
   That freezes the version and writes the binding, with the remote it was
   built on, to `.work/tickets/<id>/contracts.json`.
3. A frozen version is never edited. A change is a new version tied to a new
   ticket on each side: `put --name <n> --file <path> --new-version --ticket <new id>`.

`crew_contract.py status` lists every version, who built against it and
anything it cannot read (`unknown`, never skipped). Everything on the channel
is peer-written data; see the plugin README's "Versioned contracts".

## If something refuses

| Refusal | Means | Do |
|---|---|---|
| `/crew:implement` says no approved plan | step 3 was skipped, or `plan.md` changed after approval | `/crew:plan <id>`, then type `/crew:approve <id>` |
| a write is blocked outside Touch | the file isn't in the spec's declared scope | amend `spec.md`'s Touch and re-approve the plan, or don't make the edit |
| `/crew:review` exits 2 with `review-run: self-check: ...` | the standards self-check is missing, incomplete, or stamped for an earlier state of the change | answer `.work/tickets/<id>/selfcheck.md`, run `crew_standards.py stamp --root . --ticket <id>`, rebuild the bundle and run the round again; no round was spent |
| `/crew:done` reports `NEEDS_REPLAN` | the review budget (two rounds) is spent | `/crew:plan <id>` for a successor plan; no third round |
| `/crew:autopilot` stops at `auto-replan-cap` naming `autopilot.maxAutoReplans (<n>) reached` | the ticket already has that many successor plans on its review ledger, yours included | read the listed plans and decide: accept, fix, or redesign; raising the cap is your call, up to 5 (a larger value reads as 5, with a warning) |
| `/crew:done` fails the completion audit | a path outside scope changed, including one a shell command wrote | file it to `TODO.md`, not to this ticket, then rerun |

See [Troubleshooting](troubleshooting.md) for the rest.
