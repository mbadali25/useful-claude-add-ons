---
paths:
  - "plugin/obsidian-vault/**"
---
<!-- crew:generated source=.crew/codemap/obsidian-vault.md sha256=a8463e2a962a3980 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# obsidian-vault
Code map anchor `60c79407`; if it is behind HEAD, re-check with `git diff --name-only 60c79407..HEAD -- <cited paths>`.
Covers: The obsidian-vault plugin: four hook events registered as bash+PowerShell pairs, the three guard checks and their unequal defaults, the two differently-sized exemption sets, and per-vault MCP registration. PR #210 added a proven-interpreter resolver to the two remaining "naive" wrappers, a loud stdin-decode failure mode, and a PowerShell legacy-argument-passing fix.
## Landmines
- The three guard checks do not ship the same way.
- The guard only ever sees the DEFAULT vault.
- `.base` files reach no structural check.
- Two differently-sized exemption sets, 20 lines apart.
- The frontmatter exemption is one check wide, not the whole function.
- `notesPrefix` scopes the note contract only - not the ASCII check and not the canvas check.
- The guard reads file content from disk rather than from the hook payload (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:321-322`).
- A malformed or undecodable hook payload used to fail silently; as of PR #210 it fails loudly.
- Every claim above is about `vault_guard.py`.
- Both PowerShell flavours no longer run on one host.
- The regression suite is `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh`, sabotage-tested per its own header (`:5-6`), with must-block and must-allow sections and four Python suites (`:476-479`).
- A PowerShell legacy-argument-passing bug rejected every real interpreter, in the opposite direction from the WindowsApps defect above - fail-open-by-standing-down rather than fail-open- by-running-a-stub, but still si...
- `bridge-status.sh`/`.ps1` and `vault-capture.sh`/`.ps1` now carry their own proven-interpreter resolvers, closing the gap the previous version of this note flagged as open risk.
Full note: `.crew/codemap/obsidian-vault.md`.
