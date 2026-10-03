# Cloud handoff: T-0038

**fold /crew:upgrade into /crew:migrate: migrate upgrades pre-0.20 configs itself; upgrade.md becomes a removal stub (crew_upgrade.py stays as a library)**

Handed to a cloud session on 2026-10-03 by owner instruction. Do not pick up locally.

- **Kanban lane:** Ready
- **INDEX status:** approved (priority: high)
- **Review ledger:** none (no review round reserved)
- **Branch:** `T-0038-build`
- **Ticket files published here:** `docs/tickets/T-0038/direction.md`, `docs/tickets/T-0038/plan.md`, `docs/tickets/T-0038/spec.md`
- **Branch state:** new branch from origin/main; no implementation yet (docs only)

The ticket files are copies of the gitignored `.work/tickets/T-0038/` as of 2026-10-03. `direction.md` is the approved direction, `spec.md` the ticket contract, and `plan.md` the approved step plan where present. Read them before writing code.

Before landing: merge origin/main (this branch may be far behind it), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for plugin/crew changes, tooling-PR rule), and remove `docs/tickets/T-0038/` in the final PR unless the owner wants it kept.
