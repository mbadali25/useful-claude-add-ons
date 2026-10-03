# Cloud handoff: T-0104

**webtest scaffold for multi-module repos: detect modules, honour testDir, close the gaps it reports, no auth project without credentials, per-session config at the repo root (aws-ops report items 1-5) - HANDED TO CLOUD 2026-09-30 (owner) - do not pick up locally; see docs/handoff/cloud/T-0104.md**

Handed to a cloud session on 2026-10-03 by owner instruction. Do not pick up locally.

- **Kanban lane:** Ready
- **INDEX status:** approved (priority: -)
- **Review ledger:** none (no review round reserved)
- **Branch:** `T-0104-build` (existing draft PR #274)
- **Ticket files published here:** `docs/tickets/T-0104/CLOUD-HANDOFF.md`, `docs/tickets/T-0104/direction.md`, `docs/tickets/T-0104/plan.md`, `docs/tickets/T-0104/sabotage-by-hand.md`, `docs/tickets/T-0104/spec.md`
- **Branch state:** existing local branch, 19 commit(s) not on main

The ticket files are copies of the gitignored `.work/tickets/T-0104/` as of 2026-10-03. `direction.md` is the approved direction, `spec.md` the ticket contract, and `plan.md` the approved step plan where present. Read them before writing code.

Before landing: merge origin/main (this branch may be far behind it), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for plugin/crew changes, tooling-PR rule), and remove `docs/tickets/T-0104/` in the final PR unless the owner wants it kept.
