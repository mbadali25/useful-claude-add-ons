---
paths:
  - "mcp-servers/packages/**"
  - "mcp-servers/scripts/**"
---
<!-- crew:generated source=.crew/codemap/mcp-servers.md sha256=7ef9a54a2cc0d208 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# mcp-servers
Code map anchor `4a48f594`; if it is behind HEAD, re-check with `git diff --name-only 4a48f594..HEAD -- <cited paths>`.
Covers: The TypeScript monorepo — four stdio MCP servers over one shared core. Holds the two recorded adminAuth.ts defects (TODO items 2 and 3), still open. GraphClient sends its token only to its base origin (T-0090). Not a marketplace plugin; nothing registers it.; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to fe524012 (L-0513, the shared gate runner: verify.json rule 22 runs its suite and rule 40 is appended, CLAUDE.md +2 lines in Commands; no plugin version, crew stays 1.0.86); re-anchored to 4eacfacf (L-0513 step 6 fix; verify.json why text only)
## Landmines
- The credential chain caches its winner for the process lifetime.
- `scopesOverride` silently broadens a narrow scope request.
- `dist/` is what runs, `src/` is what you edit.
- The stale-build gap in the TEST path is CLOSED (2026-09-06, commit `4e2bfb78`).
- `o365-user` does not use the admin credential chain at all.
- Each server pins an exact core version, not a range.
Full note: `.crew/codemap/mcp-servers.md`.
