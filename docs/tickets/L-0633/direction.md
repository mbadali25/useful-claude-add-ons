# Cross-session dependencies `<channel>:<id>` in the autopilot wave

Split from T-0031 (2026-10-04 size check). Filed as L-0633.

Status: direction inherited. The owner approved the parent direction on 2026-09-25 (`.work/tickets/T-0030/direction.md`, parts 4 and "Independent review"); this slice adds no new decision of principle.

## Scope
A ticket in a wave may depend on a ticket another session is working, written `<channel>:<id>`. The wave treats that dependency as open until the peer's claim on the channel reads `done`. A claim that is missing, corrupt, ambiguous, or on a channel that cannot be fetched reads `unknown`, and the ticket is refused. Nothing a peer wrote is ever read as an instruction.

## Why it is a separate ticket
The parent's whole scope was about 470 production lines with two parsers and a guard. This slice is the second parser (the dependency grammar) and its refusal, and it is the only slice that needs both T-0029 (the wave) and T-0030 (the record).

## Options
- A (recommended, taken). Accept the form in both places the wave already reads dependencies: the set file's `deps` and the INDEX row's `(depends on ...)`. One shared parse function.
- B. Set file only. Smaller, but a ticket named without a set file would keep reading a cross-session dependency as `unknown` with no way to state it.
- C. A new `coordDeps` key beside `deps`. Rejected: two lists for one idea, and the set-file schema is shared with T-0012.

## Questions answered with the recommended option (owner not available 2026-10-04)
1. Which claim does `<channel>:<id>` name when several repositories on the channel use that id? Taken: exactly one claim with that id must exist; none or several is `unknown`; the long form `<channel>:<repo>:<id>` names one.
2. Does a stale `working` claim count as open or unknown? Taken: open (not `done`), reported with its age.
3. Does a `released` claim close the dependency? Taken: no. Only `done` closes it.
