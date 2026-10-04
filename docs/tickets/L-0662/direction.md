# L-0662: plain-text routing rows for autopilot wave, split, sleep and wake

Split from T-0057. Status: direction. Risk: med.

## Ask
The owner asked (2026-09-26) for every autopilot command to be reachable by what they say. T-0057 covers the names the autopilot router knows today. Four commands are left: `wave` (T-0029), `split` (T-0058), `sleep` and `wake` (T-0053). None is a subcommand on origin/main `155fe6d8`: `crew_autopilot.SUBCOMMANDS` is `("status", "run", "assign", "goal", "focus")`.

## What T-0057 leaves in place
- An availability gate: a row asks `crew_autopilot.route` whether its subcommand runs. Unknown name: no line at all. Reserved name: a soft "not available yet" line. Available: route.
- So these four rows can land before their commands. They do nothing until the command's ticket adds the name to `SUBCOMMANDS`, and they go live with no further edit to `crew_route.py`.

## Options
1. **Add the four rows now, behind T-0057's gate (recommended).** The must-not-route cases get written and reviewed once, in one place, and each command ticket only has to register its name.
2. Each command's ticket adds its own row. Three tickets then each edit the one table and re-argue the false-positive cases; a row is easy to forget.
3. Wait until all three command tickets land. Nothing is gained by waiting; the gate already makes an early row inert.

## Recommendation
Option 1. Phrases, from the approved direction with the 2026-10-04 adjustments:
- `wave`: "run T-0020 and T-0022 in parallel" (two or more explicit ids).
- `split`: "split this ticket", "split it", "split T-0012", "this ticket is too big", "T-0012 is too big". Not bare "this is too big".
- `sleep`: "I'm heading to bed", "heading to bed", "going to sleep", "I'm going to sleep", "good night".
- `wake`: "I'm back", "morning", "good morning".

`sleep` raises how much autopilot does without the owner, so its route line also tells Claude to say in one line what changed and how to undo it. "go to sleep mode later", a question about sleep mode and quoted text must never route.

## Open questions for the owner (default applied)
- "morning" and "I'm back" are everyday greetings. Default: keep them as approved; the command decides what to do when sleep is not on.
- Bare "this is too big". Default: not a row.

## Depends on
T-0057. For each row to do anything: T-0029 (wave), T-0058 and T-0052 (split), T-0053 (sleep, wake).

## Approval
Split written 2026-10-04 under the owner's standing authorization; not yet approved as a ticket.
