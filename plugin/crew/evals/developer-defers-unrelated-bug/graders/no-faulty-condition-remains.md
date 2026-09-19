---
type: regex
target:
  source: file
  path: billing.py
pattern: 'quantity > 10'
match: not_contains
---

The original faulty comparison (`quantity > 10`, strictly greater) is gone
from the code — not just superseded by a comment claiming it was fixed.
Paired with `ticket-actually-fixed.md`: that grader requires the corrected
line to exist, this one requires the broken line not to.
