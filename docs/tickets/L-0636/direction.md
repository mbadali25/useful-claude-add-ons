# Cross-session messaging: an unanswered doorbell reads `could not tell` and is surfaced to the owner

Split from T-0032 (L-0636), 2026-10-04. The approved direction is `.work/tickets/T-0030/direction.md` (owner, 2026-09-25), part 6: "Silence is not agreement. An unanswered message, an offline peer, or a held message is `could not tell`, surfaced to the owner, never read as consent."

## Problem
T-0032 composes and classifies a doorbell. It keeps no memory of having rung. Over Remote Control a send has no delivery confirmation, a peer in another permission mode may hold the message, and a cloud session cannot reply. So after `ring`, a session cannot tell "the peer read the record" from "the message never arrived", and after `/clear` it does not even know it rang.

## Options
- A (recommended, taken): the ring is written to the record. `crew_bridge.py ring --to <peer-label>` appends a `rang` line to the channel log, and `crew_bridge.py pending` reports every ring that no later log line from another holder follows. Such a ring reads `could not tell`, with its age. It never becomes "delivered" or "agreed" by time passing.
- B: keep pending rings in a local file. Rejected: lost on another machine, and the record is the only thing a session resuming after `/clear` rebuilds from.
- C: prose only. Rejected: an unknown must not collapse into the safe-looking value, and prose does not survive `/clear`.

## Open questions
- Whether `pending` should also be a `/crew:autopilot` stop when the active ticket waits on a `<channel>:<id>` dependency. Taken: it is printed by status and by the resume step; a new stop reason in `crew_autopilot.py` is left out because that file is a seam of the review harness and the wave (T-0029, T-0031) owns dependency stops.
