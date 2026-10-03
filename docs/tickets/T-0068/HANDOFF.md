# Cloud handoff: T-0068

**crew's own bookkeeping writes (.scope-base, metrics, verify-gate records) never trip the completion audit or stale a review receipt; /crew:done deadlock from TSS-510 (PRIORITY)**

Handed to a cloud session on 2026-10-03 by owner instruction. Do not pick up locally.

- **Kanban lane:** Ready
- **INDEX status:** spec (priority: high)
- **Review ledger:** none (no review round reserved)
- **Branch:** `T-0068-build`
- **Ticket files published here:** `docs/tickets/T-0068/direction.md`, `docs/tickets/T-0068/plan.md`, `docs/tickets/T-0068/spec.md`
- **Branch state:** existing local branch, 0 commit(s) not on main; pushed as is

The ticket files are copies of the gitignored `.work/tickets/T-0068/` as of 2026-10-03. `direction.md` is the approved direction, `spec.md` the ticket contract, and `plan.md` the approved step plan where present. Read them before writing code.

Before landing: merge origin/main (this branch may be far behind it), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for plugin/crew changes, tooling-PR rule), and remove `docs/tickets/T-0068/` in the final PR unless the owner wants it kept.
