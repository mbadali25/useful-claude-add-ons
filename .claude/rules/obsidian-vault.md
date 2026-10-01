---
paths:
  - "plugin/obsidian-vault/**"
  - "plugin/crew/**"
---
<!-- crew:generated source=.crew/codemap/obsidian-vault.md sha256=4c860a7e97b4e921 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# obsidian-vault
Code map anchor `e41bc6fd`; if it is behind HEAD, re-check with `git diff --name-only e41bc6fd..HEAD -- <cited paths>`.
Covers: The obsidian-vault plugin: four hook events registered as bash+PowerShell pairs, the three guard checks and their unequal defaults, the two differently-sized exemption sets, and per-vault MCP registration. The guard is PostToolUse, so it reports a bad write rather than blocking it.; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to fe524012 (L-0513, the shared gate runner: verify.json rule 22 runs its suite and rule 40 is appended, CLAUDE.md +2 lines in Commands; no plugin version, crew stays 1.0.86); re-anchored to 4eacfacf (L-0513 step 6 fix; verify.json why text only)
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
- Crew 1.0 retired two adjacent memory systems this note used to reference by name; both are gone from the marketplace.
- A refused capture is now a distinct, named outcome, not a queued garbage line.
- All six wrappers (three `.sh`, three `.ps1`) now share one resolver shape, not three independently-drifting ones.
- New this pass: vault roles (`primary`/`recall`/`ignore`) via `vault_setup.py adopt`, layered under three new CLI modules `vault_ops.py` now dispatches to.
- `bridge-status.sh`/`.ps1` and `vault-capture.sh`/`.ps1` now carry their own proven-interpreter resolvers, closing the gap the previous version of this note flagged as open risk.
- The two retired `claude-memories-*` skills' conventions did not disappear - they moved into this plugin as portable "profiles".
Full note: `.crew/codemap/obsidian-vault.md`.
