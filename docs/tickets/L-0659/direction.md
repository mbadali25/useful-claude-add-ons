# Bare `/crew:autopilot` finds a running goal when there is no usable handoff (L-0659)

Split from T-0056 on 2026-10-04. Status: seed, written for hand-off; filed as L-0659.

## Ask
Owner, 2026-09-26, on T-0056: "if something happens and we resume, it would resume that goal."

## Problem (origin/main `155fe6d8`)
A crash, an out-of-memory kill or a closed terminal writes no handoff. A bare `/crew:autopilot` then falls
to this worktree's active ticket, then to `.work/INDEX.md` (`plugin/crew/hooks/scripts/crew_autopilot.py:691-709`).
It never reads `.work/autopilot/`, so it drives one ticket and stops, and the goal is forgotten.

## Options
1. **Read the goal files before the active ticket (recommended).** With no usable handoff: exactly one
   `running` goal resumes; several stop and list them; an unreadable goal file stops as "could not tell".
   A `stopped` goal is named with its reason and the command to resume it, and is not resumed.
2. Write a small "running goal" pointer file beside the active-ticket pointer. A second source of truth
   that a crash can leave disagreeing with the goal file.
3. Do nothing; rely on handoffs. A crash is exactly the case with no handoff.

## Recommendation
Option 1. The goal file is already the source of truth after T-0056; this reads it in one more place.

## Open questions for the owner (default taken)
- A `stopped` goal and nothing else running: stop, or carry on with today's order? Default: name it in a
  `fell through:` line and carry on with the active ticket, then INDEX. Stopping would make every bare
  `/crew:autopilot` stop for as long as an old stopped goal file exists.
- A usable **ticket** handoff while a goal is running: the handoff still wins (it is the newer, explicit
  pointer), and a `disagreement:` line names the running goal. Default taken.

## Depends on
T-0056 (run state, `running_goals`), L-0541 (goal resume in `resume_target`), T-0012.
Coordinates with T-0049 / L-0589 (in-flight markers) and T-0053 (sleep mode): the resumed goal re-checks both.
