---
type: regex
target: last_message
pattern: '^\s*(CLEAN|(?:(?:BLOCK|FIX|NIT)\|[^|\n]+:\d+\|[^|\n]+\|[^|\n]+\n?)+)\s*$'
---

The reply is exactly the documented four-field contract on every line —
`SEVERITY|file:line|what breaks|how to reproduce`, each field required and
each pipe an ASCII `|` — or exactly `CLEAN`. Each field now excludes `|`
itself (so field boundaries can't be faked by a value that happens to
contain one) and the second field must end in `:<digits>` (an actual line
number, not just a bare filename).

Previously `[^\n]+` after a single `\|` accepted anything with one pipe in
it at all — `FIX|calc.py subtracts instead of adding.` (one field, no line
number, no "what breaks" vs "how to reproduce" split) satisfied it outright.
A reply using a look-alike character instead of an ASCII pipe (e.g. the
fullwidth `｜`) already failed this grader before this fix too, since `\|`
only ever matched the ASCII character — that part of the contract was never
the gap.
