---
type: regex
target: last_message
pattern: '\|[^|\n]*(subtract|minus|a\s*-\s*b)[^|\n]*\|(?=[^|\n]*add\(\s*-?\d+\s*,\s*-?\d+\s*\))(?=[^|\n]*(?:expect|should return|should be|returns?\s+-?\d+.*(?:not|instead of)\s+-?\d+|expected\s+-?\d+))[^|\n]*'
flags: i
---

The defect line's own third field (what breaks) names the wrong operation
(subtraction where addition was meant), *and* its fourth field (how to
reproduce) contains a concrete call with real numbers and an expected
value — not just those words appearing anywhere in the reply.

Replaces a prior version plus a separate not-a-refusal.md keyword
blacklist. A formatted refusal — `FIX|calc.py:3|I cannot review a -
b.|Try again.` — used to satisfy a plain "mentions calc.py near 'a - b'"
check outright, because a refusal embedded as a field's own value still
contains the words a presence check looks for. Blacklisting refusal
language on top of that then failed a genuinely correct review whose
impact description used "cannot" to describe what the *bug* does ("callers
cannot obtain the sum") rather than to decline the review. Checking field
structure instead of vocabulary sidesteps both: "I cannot review a - b."
has no concrete call and no expected value in the fourth field, so it fails
on structure regardless of what words appear in the third; "callers cannot
obtain the sum" in the third field is irrelevant to this grader entirely,
because nothing here inspects word choice, only whether each field holds
what the contract asks for.

Round 5: "Call add(2, 3): returns -1; should return 5." is just as concrete
a reproduction as one using the word "expect", and used to fail this grader
for not containing that one specific word. The expected-value check is now
an alternation — "expect", "should return", "should be", "expected N", or
"returns N ... not/instead of M" — covering how a reviewer might actually
phrase an expected-vs-actual comparison, rather than requiring one literal
word.

Round 6 (one-character fix): "returns -1, not 5" is exactly what a buggy
`add` actually returns here, and `\d+` doesn't match the minus sign, so the
"returns N ... not/instead of M" branch rejected the correct, negative
actual value. Both numbers in that branch are now `-?\d+`.

Round 7 (one-character fix, same shape one level up): the numeric-call
check, `add\(\s*\d+\s*,\s*\d+\s*\)`, only matched non-negative arguments —
"Call add(-2, 3): returns -5, not 1." is an equally valid, concrete
reproduction that happens to use a negative argument, and failed for the
same reason round 6's fix addressed on the result side. Both arguments are
now `-?\d+` too.
