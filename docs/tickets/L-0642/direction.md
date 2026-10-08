# L-0642 direction: autopilot's open-questions stop sees through code fences, and stops when it cannot tell
Split from T-0043 on 2026-10-04 (the NIT "code fences in Open questions", which grew into its own parser across two review rounds). Checked against origin/main `155fe6d8` (crew 1.0.322).

## Problem
`_open_items` in `plugin/crew/hooks/scripts/crew_autopilot.py:302-328` decides whether a ticket has an unanswered item under an Open-questions heading; a non-empty answer is the `open-questions` human stop (`:447-452`). It matches headings on every line with no notion of a code fence. A fenced block under the section that contains a line starting with `#` closes the section, and the items after it are never seen. Text of that shape: a level-2 Open-questions heading, a fence, a line `# how to check`, the closing fence, then the bullet "which DB?". Main returns no items for it, so autopilot drives past a question a person was meant to answer.

## History
T-0043's first build tracked fences by emulating CommonMark (indentation, list nesting, run lengths). Review round 1 found two ways that hid a section, and round 2 found two more, each a regression against main: a 4-space-indented closer accepted as a closer, and a fence nested in a list surviving the end of the list. The owner rejected round 2 on 2026-09-27 and set the rule below.

## Recommendation (the owner's 2026-09-27 rule, kept)
- Main's parser is the floor. For any text, the new `_open_items` returns every item main's returns. It is implemented as a union, so it cannot fall below main by construction.
- A strict fence view adds what main misses. Only a fence opened at column 0 and closed at column 0 by a run of the same marker, at least as long, with nothing after it, is tracked. Lines inside a tracked fence are neither headings nor items.
- Anything else fence-shaped is "could not tell", and "could not tell" stops. An indented fence line, a backtick run with a backtick in its info string, a shorter run inside a fence, or a fence still open at the end of the text adds one item naming the line, whenever the file names an Open-questions section anywhere (indented or fenced included). A file with no such section is never stopped by its fences.
- No more CommonMark emulation.

Accepted cost: a file with an answered Open-questions section and a valid but indented fence (inside a list item, say) stops until the fence is moved to column 0. Measured on 2026-09-27 over 158 real ticket files with a prototype: 0 files newly stop.

## Options not taken
- Leave main as it is: keeps a confirmed fail-open in a human stop.
- A markdown library: crew's hook scripts are standard-library only, and the two failed rounds were about ambiguity, which a library resolves silently instead of stopping on.
- Treat every fence under the section as an open item: stops every ticket that shows a command in an answered section, which the measurement says is common.

## Open questions for the owner
- [x] Under `autopilot.questions: self` the could-not-tell item reaches the same policy route as a real question, so autopilot may "answer" it by rewriting the fence. Taken: allowed, because the item text says exactly what to fix and the result is re-parsed on the next `next`. Say so if a could-not-tell item should always be a person's.
