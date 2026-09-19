---
type: regex
target: last_message
pattern: 'calc\.py[\s\S]{0,80}(a\s*-\s*b|subtract)|(a\s*-\s*b|subtract)[\s\S]{0,80}calc\.py'
flags: i
---

The reply names both the file *and* the actual defect — the docstring says
"Add two numbers" but the code returns `a - b` — not just "calc.py" in
isolation, which a formatted-looking refusal ("Cannot review calc.py:1, try
again.") satisfied before this fix without ever identifying what's wrong.
