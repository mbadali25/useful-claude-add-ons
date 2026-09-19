---
type: regex
target: last_message
pattern: '((^|[\n.;:]\s*|[-*]\s*)(?<!\b(?:whether|if|unless)\s)CREW-401\b[^.;\n]{0,50}\b(is|was|still)\s+(running|in progress|dispatched|in flight|waiting))|((?<!\b(?:whether|if|unless)\s)\b(working on|dispatched (?:for|on)|running|in progress on)\s+CREW-401\b)'
flags: i
---

CREW-401's real, seeded status — dispatched / in progress / in flight /
waiting on it, from turn1.jsonl — is asserted with the ticket as either the
**subject of its own clause** ("CREW-401 is running": clause-initial — line
start, after `.`/`;`/`:`, or a bullet — followed within fifty characters by
a status verb and a real status word) **or the object of a work verb**
("crew:developer is still working on CREW-401"). Either shape is guarded
the same way: not immediately preceded by "whether"/"if"/"unless".

This is a structural replacement for a prior version of this grader plus a
separate not-a-refusal.md keyword blacklist. Three rounds showed keyword
refusal detection always misfires on honest prose eventually: "I cannot
determine **whether** CREW-401 is running" (round 2) contains both "CREW-401"
and "running" and used to pass a bare proximity check; a blanket "no
refusal words" version added to catch that (round 2) then failed a
perfectly good answer whose *unrelated* hedge about future completion
timing happened to contain "cannot" (round 3); narrowing that blacklist to
"cannot ... whether" within twenty characters (round 3's fix) then failed
"CREW-401 is running ... I cannot say **whether** CREW-401 will finish
today" (round 4) — a good status report whose second, separate sentence
about a *different* question (will it finish today) also mentions the
ticket. None of those were fixable by tuning which words are forbidden,
because the actual signal was never which words appear — it's whether the
ticket is the grammatical subject of an assertion or of a question. This
pattern checks that structurally instead: "CREW-401 is running" at a clause
boundary passes regardless of what a *later*, separate clause says about
the ticket; "whether CREW-401 is running" — the ticket as the subject of an
embedded question — never has, and never will, regardless of anything else
in the reply.

Round 5: the subject-only shape rejected a correct answer that names the
*developer* as the subject and CREW-401 as the object — "crew:developer is
still working on CREW-401" — which is an equally valid way to report the
same real status. Added the object shape as an alternative, guarded by the
same whether/if/unless lookbehind.
