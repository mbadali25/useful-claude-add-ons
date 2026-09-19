---
type: regex
target:
  source: file
  path: billing.py
pattern: '^\s*if quantity >= 10:'
flags: m
---

The corrected comparison appears as a live `if` statement — line-anchored,
so a comment trailing the still-buggy line (`if quantity > 10:  # quantity
>= 10`) does not satisfy it the way a bare substring search would.
