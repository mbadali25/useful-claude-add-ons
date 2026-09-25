# Instruction-surface budgets (crew 1.0, T8)

Tracks the size targets `docs/review/04-redesign.md`'s "Instruction surface" table sets, and
what `scripts/check_instructions.py` actually measures. Refresh both the count below and
`.budget-allowance.json` together — a stale number here is worse than none, because it looks
checked.

## Plugin Markdown total

<!-- claim: crew-markdown-lines -->
`git ls-files 'plugin/crew/*.md'` currently totals 17,774 lines across 120 files (including this
file). Target: ≤6,000 lines (`docs/review/04-redesign.md`). This number moves every time a tracked
`plugin/crew/*.md` file is added, removed or resized — including this one — so re-measure rather
than trusting it; the marker above is what keeps that honest.

The crew 1.0 T2 deletions (the PM, pulse, journal and 51 retired agents) landed the "held" half of
this gap: 58 files and roughly 11,400 lines, as T8 estimated. What remains:

- **To trim** (`.budget-allowance.json`, reason `T8: to trim`): 9 command files still over the
  120-line command budget that T8 judged too large or too test-coupled to safely rewrite in
  this pass — `review.md` (551 lines, the brief's own example) foremost among them, since nine
  test files assert specific sentences inside it and moving that prose to a reference doc means
  updating every one of those assertions, not just the command file. Trimming all nine to exactly
  120 would save about 1,382 more lines. (`work.md` left the list in T2: it is a removal stub now.)

That still stays nowhere near 6,000. The rest of the reduction is guide and skill work assigned
to later tickets (T12-trim in `TODO.md`), not deletions a lane can make unilaterally.
`check_instructions.py` does not fail the build on this aggregate number for that reason — it is
tracked here for accuracy (`check_self_claims`), not gated. What IS gated: the 120-line command
budget (with the allowance file as the only exception, and growth even there is a hard fail).

## Command file budget

≤120 lines per `plugin/crew/commands/*.md`, checked file-by-file. A path listed in
`.budget-allowance.json` is exempted up to its recorded `lines` value; growing past that value
fails even for a listed path — the allowance covers today's debt, not tomorrow's.
