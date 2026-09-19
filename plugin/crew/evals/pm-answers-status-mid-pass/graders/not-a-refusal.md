---
type: regex
target: last_message
pattern: '\b(cannot|can.t|unable to|don.t know|not sure)\b'
flags: i
match: not_contains
---

The reply doesn't hedge or decline — "I cannot determine whether CREW-401 is
running." previously passed `names-real-status.md` outright, because
"CREW-401" and "running" both appear in it; that grader checks proximity,
not negation, and can't tell an assertion from a question about one. This
targets the actual tell: refusal language, wherever it lands in the reply.

Not fixed by adding a `tool_used: Read` requirement instead, on purpose — a
PM that answers correctly and efficiently from what's already in context
(the point of this case: the status is already known, no re-investigation
needed) would then fail this case for the crime of not making a wasted tool
call.
