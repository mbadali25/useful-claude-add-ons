# Instruction-surface budgets (crew 1.0, T8)

Tracks the size targets `docs/review/04-redesign.md`'s "Instruction surface" table sets, and
what `scripts/check_instructions.py` actually measures. Refresh both the count below and
`.budget-allowance.json` together — a stale number here is worse than none, because it looks
checked.

## Plugin Markdown total

<!-- claim: crew-markdown-lines -->
`git ls-files 'plugin/crew/*.md'` currently totals 19,241 lines across 142 files (including this
file). Target: ≤6,000 lines (`docs/review/04-redesign.md`). This number moves every time a tracked
`plugin/crew/*.md` file is added, removed or resized — including this one — so re-measure rather
than trusting it; the marker above is what keeps that honest.

The crew 1.0 T2 deletions (the PM, pulse, journal and 51 retired agents) landed the "held" half of
this gap: 58 files and roughly 11,400 lines, as T8 estimated. What remains:

- **To trim** (`.budget-allowance.json`, reason `T8: to trim`): 5 command files still listed over
  the 120-line command budget (`change.md`, `gate.md`, `model.md`, `onboard.md`, `verify.md`; `autopilot.md`
  is listed for bytes only, and L-0727 cuts it). `review.md` (L-0726 slice 1: 551 to 46 lines) and
  `promote.md` (slice 2: 394 to 96 lines, 10,560 bytes) are no longer debts: their rationale moved to
  `docs/crew/review.md` and `docs/crew/promote.md`, and their allowances are gone, so either file
  over 120 lines or 12,288 bytes fails `check_instructions.py`. Every command file is also capped at
  12,288 bytes unless listed with a `bytes` ceiling, and a listed file may not grow in bytes.
  `plugin/crew/README.md` is capped at 800 lines (564 now); its reference sections live in
  `docs/crew/reference/`. (`work.md` left the list in T2: it is a removal stub now.)
- **The gap to 6,000, by area** (`git ls-files 'plugin/crew/*.md'`, this ticket's close): skills
  12,581 lines, `CONFIG.md` 3,914 (L-0725 generates it), commands 3,585, agents 675, README 564,
  evals 117, and the other `plugin/crew/*.md` files (docs, NOTICE, BUDGETS) the rest. The 6,000
  target is carried as a Phase 4 close-out measured after L-0724 and L-0725 land, plus a skill-trim
  ticket; L-0726 meets its own ceilings and does not reach it.

That still stays nowhere near 6,000. The rest of the reduction is guide and skill work assigned
to later tickets (T12-trim in `TODO.md`), not deletions a lane can make unilaterally.
`check_instructions.py` does not fail the build on this aggregate number for that reason — it is
tracked here for accuracy (`check_self_claims`), not gated. What IS gated: the 120-line command
budget (with the allowance file as the only exception, and growth even there is a hard fail).

## Command file budget

≤120 lines per `plugin/crew/commands/*.md`, checked file-by-file. A path listed in
`.budget-allowance.json` is exempted up to its recorded `lines` value; growing past that value
fails even for a listed path — the allowance covers today's debt, not tomorrow's.
