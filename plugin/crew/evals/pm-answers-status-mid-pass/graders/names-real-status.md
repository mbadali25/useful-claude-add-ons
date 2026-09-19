---
type: regex
target: last_message
pattern: 'CREW-401[\s\S]{0,80}(dispatch|progress|running|flight|waiting)|(dispatch|progress|running|flight|waiting)[\s\S]{0,80}CREW-401'
flags: i
---

The reply states CREW-401's *actual* seeded status — dispatched / in
progress / in flight / waiting on it, from turn1.jsonl — not just the ticket
number in isolation. A bare mention of "CREW-401" (as in a refusal like "I
cannot provide status on CREW-401.") no longer passes: the ticket number and
a real status word have to appear near each other.
