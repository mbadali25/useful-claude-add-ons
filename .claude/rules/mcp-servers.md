---
paths:
  - "mcp-servers/packages/**"
  - "mcp-servers/scripts/**"
---
<!-- crew:generated source=.crew/codemap/mcp-servers.md sha256=4c9152ab0368c46e -- do not hand-edit; regenerate with crew_instructions.py rules -->
# mcp-servers
Code map anchor `53936abb`; if it is behind HEAD, re-check with `git diff --name-only 53936abb..HEAD -- <cited paths>`.
Covers: The TypeScript monorepo — four stdio MCP servers over one shared core. Holds the two recorded adminAuth.ts defects (TODO items 2 and 3), still open. GraphClient sends its token only to its base origin (T-0090). Not a marketplace plugin; nothing registers it.; re-anchored to fd269296 (L-0520 PR 1, the merge train CLI, after merging main 549cda24); re-anchored to 53936abb (L-0520 PR 1: crew_train.py meets the PYTHON standards set)
## Landmines
- The credential chain caches its winner for the process lifetime.
- `scopesOverride` silently broadens a narrow scope request.
- `dist/` is what runs, `src/` is what you edit.
- The stale-build gap in the TEST path is CLOSED (2026-09-06, commit `4e2bfb78`).
- `o365-user` does not use the admin credential chain at all.
- Each server pins an exact core version, not a range.
Full note: `.crew/codemap/mcp-servers.md`.
