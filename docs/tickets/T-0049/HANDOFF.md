# Cloud handoff: T-0049

**crew in-flight markers: one holder per ticket, a heartbeat with a TTL, and autopilot stops on a live, stale or unknown holder (blocks T-0060)**

Reconstructed in a cloud session on 2026-10-04 from downstream tickets because the owner's .work copy was never published; the owner must approve direction and plan before build.

- **Kanban lane:** Ready (pending owner approval of the reconstruction)
- **INDEX status:** none on this machine (the owner's `.work/INDEX.md` row is not published)
- **Review ledger:** none here. `docs/review/08-qa-rounds-analysis.md` (branch `L-0509-build`) counts T-0049 ledgers with at least two rounds on the owner's machine; they were not published and are not reproduced
- **Branch:** `T-0049-build`
- **Ticket files published here:** `docs/tickets/T-0049/direction.md`, `docs/tickets/T-0049/spec.md`, `docs/tickets/T-0049/plan.md`
- **Branch state:** new branch from origin/main edb2b8ff (crew 1.0.321); no implementation yet (docs only)

What these files are: a reconstruction that satisfies every published downstream expectation (T-0060 on `T-0060-build`, L-0582 on `L-0582-build`, the QA-rounds analysis on `L-0509-build`, the pending-tickets list on `L-0522-build`). Every decision the owner may have made differently is marked `OWNER CHECK:`. If the owner still has `.work/tickets/T-0049/`, that copy wins: diff it against these files and keep this branch only for what the local copy lacks.

Before landing: merge origin/main (never rebase), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for plugin/crew changes, the tooling-PR rule: this ticket touches `SEAM` files and needs a sabotage table, see plan step 7), and remove `docs/tickets/T-0049/` in the final PR unless the owner wants it kept.
