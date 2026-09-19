---
type: regex
target: last_message
pattern: '\b(cannot|can.t|unable to|don.t know|not sure)\b'
flags: i
match: not_contains
---

The reply doesn't hedge or decline, even inside an otherwise well-formed
defect line — `FIX|calc.py:3|I cannot review a - b.|Try again.` previously
passed both `verdict-format.md` (the shape is right) and `finds-the-bug.md`
(it names calc.py near "a - b") outright, because a refusal embedded as a
field value still satisfies pattern checks that only look at what's present,
not what it means. This targets the actual tell: refusal language, wherever
it lands.

Not fixed by adding a `tool_used: Read` requirement instead, on purpose —
the diff is given inline in the prompt precisely so this case needs no
`Bash` grant; a QA reviewer that correctly spots the bug from the three-line
diff alone, without re-reading a file that doesn't even exist in this
scaffold-less case, is doing this efficiently and correctly, not failing to
engage.
