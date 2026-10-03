# Cloud handoff: L-0582

**read_metrics and every .crew/metrics.md reader resolve the MAIN checkout's .crew/ when run from a linked worktree (L-0578 follow-up, owner 2026-10-01); SPEC REVIEW 2026-10-02 at origin/main 8d84786d: review.md steps 6/8 left to L-0578, stranded note covers metrics.jsonl too, plan Files fixed; validate clean; approved via cli (plan 8b8fab20f6c5, spec be6807656693)**

Handed to a cloud session on 2026-10-03 by owner instruction. Do not pick up locally.

- **Kanban lane:** Ready
- **INDEX status:** approved (priority: medium)
- **Review ledger:** none (no review round reserved)
- **Branch:** `L-0582-build`
- **Ticket files published here:** `docs/tickets/L-0582/direction.md`, `docs/tickets/L-0582/plan.md`, `docs/tickets/L-0582/spec.md`
- **Branch state:** existing local branch, 0 commit(s) not on main; uncommitted work committed as a WIP handoff commit (unverified)

The ticket files are copies of the gitignored `.work/tickets/L-0582/` as of 2026-10-03. `direction.md` is the approved direction, `spec.md` the ticket contract, and `plan.md` the approved step plan where present. Read them before writing code.

Before landing: merge origin/main (this branch may be far behind it), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for plugin/crew changes, tooling-PR rule), and remove `docs/tickets/L-0582/` in the final PR unless the owner wants it kept.
