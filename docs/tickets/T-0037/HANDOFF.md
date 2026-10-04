# Cloud handoff: T-0037

**ticket status vocabulary: `needs-owner`, `cancelled` and `superseded`, read the same by every reader and tracker (unblocks T-0052, T-0058, T-0059; named by T-0039, T-0040)**

Reconstructed in a cloud session on 2026-10-04 from downstream tickets because the owner's .work copy was never published; the owner must approve direction and plan before build.

- **Kanban lane:** Ready (proposed)
- **INDEX status:** spec (priority: high, because it blocks #364, #365 and #366)
- **Review ledger:** none (no review round reserved)
- **Branch:** `T-0037-build` (PR A). PR B, `T-0037-sabotage`, is cut after A merges (plan step 6)
- **Ticket files published here:** `docs/tickets/T-0037/direction.md`, `docs/tickets/T-0037/spec.md`, `docs/tickets/T-0037/plan.md`
- **Branch state:** new branch from origin/main edb2b8ff (crew 1.0.321); no implementation yet (docs only)

These files are a reconstruction, not copies. Each decision the owner may have made differently is marked `OWNER CHECK:`. `spec.md`'s `## Downstream contract` table quotes every downstream expectation with its `ref:path:line`. Lines `:9` and `:30` of `spec.md` carry the two rules that downstream cites as `.work/tickets/T-0037/spec.md:9` and `:30`. When approved, copy the three files to `.work/tickets/T-0037/` so those citations resolve.

Before landing: merge origin/main (this branch may be far behind it), take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for plugin/crew changes, tooling-PR rule: PR A carries no `HARNESS` path, and PR B is the sabotage registration alone), and remove `docs/tickets/T-0037/` in the final PR unless the owner wants it kept.
