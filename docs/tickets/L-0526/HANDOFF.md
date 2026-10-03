# Cloud handoff: L-0526

**Merge train, slice 1b (tooling): review_run.py takes the train before a gate round (exit 6), the reviewer's rerere block, /crew:review's exit 6, sabotage S1-S15 - split from L-0520 (owner 2026-09-30)**

Handed to a cloud session on 2026-10-03 by owner instruction. Do not pick up locally.

- **Kanban lane:** Ready
- **INDEX status:** planned (priority: -)
- **Review ledger:** none (no review round reserved)
- **Branch:** `L-0526-build`
- **Ticket files published here:** `docs/tickets/L-0526/direction.md`, `docs/tickets/L-0526/plan.2026-09-30-v1.md`, `docs/tickets/L-0526/plan.md`, `docs/tickets/L-0526/spec.2026-09-30-v1.md`, `docs/tickets/L-0526/spec.md`
- **Branch state:** new branch from origin/main; no implementation yet (docs only)

The ticket files are copies of the gitignored `.work/tickets/L-0526/` as of 2026-10-03. `direction.md` is the approved direction, `spec.md` the ticket contract, and `plan.md` the approved step plan where present. Read them before writing code.

Before landing: merge origin/main (this branch may be far behind it), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for plugin/crew changes, tooling-PR rule), and remove `docs/tickets/L-0526/` in the final PR unless the owner wants it kept.
