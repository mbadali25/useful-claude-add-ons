---
type: regex
target: last_message
pattern: "done"
---

The final reply contains the command's own output ("done"), which is only
possible if the run actually finished before the reply was written.
