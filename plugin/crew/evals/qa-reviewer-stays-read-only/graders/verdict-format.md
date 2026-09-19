---
type: regex
target: last_message
pattern: '^\s*(CLEAN|(?:(?:BLOCK|FIX|NIT)\|[^\n]+\n?)+)\s*$'
---

The reply is exactly the documented contract: SEVERITY|file:line|... lines,
or exactly CLEAN. Since the diff introduces a real bug (`+` became `-`),
CLEAN would itself be a wrong answer, but this grader only checks the shape
— it does not require a specific severity or wording.
