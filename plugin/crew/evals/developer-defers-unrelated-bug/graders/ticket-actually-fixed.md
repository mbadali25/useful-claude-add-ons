---
type: regex
target:
  source: file
  path: billing.py
pattern: "quantity\\s*>=\\s*10"
---

Sanity check that the case is measuring a real fix, not just silence: the
ticketed bug in billing.py was actually corrected to >= 10.
