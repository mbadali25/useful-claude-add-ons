# Cloud handoff: T-0016

**auto-clear that is safe for child processes: bind the clear to this session's own process and terminal; a headless child gets a notify naming the parent restart (blocks T-0017)**

Reconstructed in a cloud session on 2026-10-04 from downstream tickets because the owner's .work copy was never published; the owner must approve direction and plan before build.

- **Kanban lane:** Ready (pending owner approval of the reconstruction)
- **INDEX status:** spec (reconstructed; the original was built locally to review round 2 and never pushed)
- **Review ledger:** none on this branch. The local build had two rounds (r1 @1275d2c4, r2 @57656e34); their findings survive as golden replays and are folded into `spec.md` as acceptance checks.
- **Branch:** `T-0016-build`
- **Ticket files published here:** `docs/tickets/T-0016/direction.md`, `docs/tickets/T-0016/spec.md`, `docs/tickets/T-0016/plan.md`
- **Branch state:** new branch from origin/main edb2b8ff (crew 1.0.321); no implementation yet (docs only)

Sources used: T-0017's published ticket (`origin/T-0017-build:docs/tickets/T-0017/*`), the two T-0016 golden review replays on main (`plugin/crew/tests/golden/review/uca-t0016--T-0016-teUWH9/out.txt` = r1, `uca-t0016--T-0016-5S2mzB/out.txt` = r2), the standards that cite them (`.crew/standards.md` REPO-01, `plugin/crew/skills/crew-standards/references/generic.md`, `python.md`), and the code on main. Every decision the owner may have made differently is marked `OWNER CHECK:`.

Before landing: merge origin/main (never rebase), take a crew version one patch above main's at land time (`.crew/standards.md` REPO-03), follow CLAUDE.md (scope discipline, doc updates, the tooling-PR rule: the sabotage entries are HARNESS and land as their own PR), and remove `docs/tickets/T-0016/` in the final PR unless the owner wants it kept.
