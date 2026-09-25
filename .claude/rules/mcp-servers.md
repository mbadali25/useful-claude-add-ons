---
paths:
  - "mcp-servers/packages/**"
  - ".claude-plugin/marketplace.json"
---
<!-- crew:generated source=.crew/codemap/mcp-servers.md sha256=93370fbd7d510a06 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# mcp-servers
Code map anchor `f2bb919b`; if it is behind HEAD, re-check with `git diff --name-only f2bb919b..HEAD -- <cited paths>`.
Covers: The TypeScript monorepo — four stdio MCP servers over one shared core. Holds the two recorded adminAuth.ts defects (TODO items 2 and 3), still open. Not a marketplace plugin; nothing registers it. mcp-servers/ is untouched by crew 1.0.
## Landmines
- The credential chain caches its winner for the process lifetime.
- `scopesOverride` silently broadens a narrow scope request.
- `dist/` is what runs, `src/` is what you edit.
- The stale-build gap in the TEST path is CLOSED (2026-09-06, commit `4e2bfb78`).
- `o365-user` does not use the admin credential chain at all.
- Each server pins an exact core version, not a range.
Full note: `.crew/codemap/mcp-servers.md`.
