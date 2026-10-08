# Cross-session messaging: the main session is the hub, lanes never ring a peer

Split from T-0032 (L-0637), 2026-10-04. The approved direction is `.work/tickets/T-0030/direction.md` (owner, 2026-09-25), part 5: "The main session of each side talks; lanes never message peers. A lane's question for the other side is batched up to its main session like any other question."

## Problem
A subagent's `SendMessage` goes out under its parent session's address, and the reply lands in the parent's conversation, not the subagent's (T-0030 direction, "Facts this rests on"). A lane that messages a peer therefore speaks for the main session without it knowing, and never sees the answer.

## Options
- A (recommended, taken): two cheap controls. `crew_bridge.py ring` refuses inside a wave lane, and no crew agent or lane prompt is granted `SendMessage` or `ListAgents`, asserted by the prompt validator. The lane prompt says a question for another session goes back to the main session in the lane's report.
- B: a PreToolUse hook that blocks `SendMessage` in a lane. Not taken: a new blocking hook is a stop-and-ask in this repo, must default OFF, needs a must-block and must-allow suite with sabotage, and it is not measured whether hooks fire for that tool or can tell a lane from the main session.
- C: prose only. Rejected: nothing would notice a later prompt edit that grants the tool.

## Open questions
- Does the owner want option B as a later ticket? Taken: no, until A is shown to be insufficient.
