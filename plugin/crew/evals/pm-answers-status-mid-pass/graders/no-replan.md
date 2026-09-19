---
type: regex
target: last_message
pattern: "(here's the plan|step 1|step one|## plan)"
flags: i
match: not_contains
---

The reply does not re-issue the plan from turn 1 instead of answering the
status question.
