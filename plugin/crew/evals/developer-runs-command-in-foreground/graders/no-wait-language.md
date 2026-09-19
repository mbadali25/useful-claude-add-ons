---
type: regex
target: last_message
pattern: "(wait for|notification|check back|let you know when)"
flags: i
match: not_contains
---

The final reply doesn't tell the user to wait for a background job or
notification — because there shouldn't be one to wait for.
