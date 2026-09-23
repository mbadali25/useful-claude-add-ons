# Instruction-surface budgets (crew 1.0, T8)

Tracks the size targets `docs/review/04-redesign.md`'s "Instruction surface" table sets, and
what `scripts/check_instructions.py` actually measures. Refresh both the count below and
`.budget-allowance.json` together — a stale number here is worse than none, because it looks
checked.

## Plugin Markdown total

<!-- claim: crew-markdown-lines -->
`git ls-files 'plugin/crew/*.md'` currently totals 29,148 lines across 176 files (including this
file). Target: ≤6,000 lines (`docs/review/04-redesign.md`). This number moves every time a tracked
`plugin/crew/*.md` file is added, removed or resized — including this one — so re-measure rather
than trusting it; the marker above is what keeps that honest.

That gap will not close in T8. Two components:

- **Held** (`.budget-allowance.json`, reason `held: awaiting owner decision on T2 deletions`):
  58 files, 11,375 lines — the agents, commands and skills lane D built additively but cannot
  delete without the owner's yes (`TODO.md`, "crew-1.0 T2 (lane D, additive) deferred items").
  Landing those deletions alone takes the total to roughly 17,771 lines.
- **To trim** (`.budget-allowance.json`, reason `T8: to trim`): 10 command files still over the
  120-line command budget that T8 judged too large or too test-coupled to safely rewrite in
  this pass — `review.md` (552 lines, the brief's own example) foremost among them, since nine
  test files assert specific sentences inside it and moving that prose to a reference doc means
  updating every one of those assertions, not just the command file. Trimming all ten to exactly
  120 would save about 1,506 more lines.

Even both together (≈16,265 lines) stay nowhere near 6,000. The rest of the reduction is guide
and skill work assigned to later tickets (T9-T12), not additive deletions T8 can make unilaterally.
`check_instructions.py` does not fail the build on this aggregate number for that reason — it is
tracked here for accuracy (`check_self_claims`), not gated. What IS gated: the 120-line command
budget (with the allowance file as the only exception, and growth even there is a hard fail).

## Command file budget

≤120 lines per `plugin/crew/commands/*.md`, checked file-by-file. A path listed in
`.budget-allowance.json` is exempted up to its recorded `lines` value; growing past that value
fails even for a listed path — the allowance covers today's debt, not tomorrow's.
