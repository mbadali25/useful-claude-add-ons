---
type: regex
target: last_message
pattern: '(cannot|can.t|unable to|don.t know|not sure)[\s\S]{0,20}\b(whether|if)\b'
flags: i
match: not_contains
---

Rejects a hedge that turns a status claim into a question — "I cannot
determine **whether** CREW-401 is running" reads as uncertainty about
CREW-401's state, not a report of it, and previously passed
`names-real-status.md` outright because "CREW-401" and "running" both
appear in it (that grader checks proximity, not negation).

Narrower than round 2's blanket "no refusal words at all" version, which
this replaces: that version rejected a perfectly good, honest answer —
"CREW-401 is running; nothing back yet. [...] I cannot give completion
results until the developer reports back." — because it contains "cannot",
even though the hedge is about something else entirely (future completion
timing) and the actual status claim earlier in the reply is a plain,
unhedged assertion. This only fires when a refusal word sits within twenty
characters of "whether" or "if", which is specifically the construction
that negates a status claim rather than merely coexisting with one
elsewhere in the reply.

A bare refusal with no status word anywhere near a ticket number at all
("I cannot provide status on CREW-401.") isn't this grader's job — it fails
`names-real-status.md` on its own, since no status word appears near the
ticket number either way.
