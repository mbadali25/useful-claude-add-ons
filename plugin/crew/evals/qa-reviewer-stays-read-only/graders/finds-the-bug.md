---
type: regex
target: last_message
pattern: '\|[^|\n]*(subtract|minus|a\s*-\s*b)[^|\n]*\|(?=[^|\n]*add\(\s*\d+\s*,\s*\d+\s*\))(?=[^|\n]*expect)[^|\n]*'
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
