---
paths:
  - "mcp-servers/packages/**"
  - "mcp-servers/scripts/**"
---
<!-- crew:generated source=.crew/codemap/mcp-servers.md sha256=6c119962accf2ef4 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# mcp-servers
Code map anchor `43d0efc8`; if it is behind HEAD, re-check with `git diff --name-only 43d0efc8..HEAD -- <cited paths>`.
Covers: The TypeScript monorepo — four stdio MCP servers over one shared core. Holds the two recorded adminAuth.ts defects (TODO items 2 and 3), still open. GraphClient sends its token only to its base origin (T-0090). Not a marketplace plugin; nothing registers it.; then to e71ad41f (T-0505, after merging T-0094's main); then to f1ccd055 (T-0505 merges L-0531's main); then to 43d0efc8 (T-0505 merges T-0099's main)
## Landmines
- The credential chain caches its winner for the process lifetime.
- `scopesOverride` silently broadens a narrow scope request.
- `dist/` is what runs, `src/` is what you edit.
- The stale-build gap in the TEST path is CLOSED (2026-09-06, commit `4e2bfb78`).
- `o365-user` does not use the admin credential chain at all.
- Each server pins an exact core version, not a range.
Full note: `.crew/codemap/mcp-servers.md`.
