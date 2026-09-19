---
type: tool_used
tool: Bash
input_match: '"command"\s*:\s*"sleep 5 && echo done"'
min: 1
---

The Bash tool's `command` argument was the actual requested command — not
just some call whose input happened to contain the substring "sleep 5",
which `echo 'sleep 5 && echo done'` (printing the text without running it)
satisfied before this fix without ever executing anything.
