---
paths:
  - "mcp-servers/packages/**"
  - "mcp-servers/scripts/**"
---
<!-- crew:generated source=.crew/codemap/mcp-servers.md sha256=132b3fd32af6f0ef -- do not hand-edit; regenerate with crew_instructions.py rules -->
# mcp-servers
Code map anchor `11f476a2`; if it is behind HEAD, re-check with `git diff --name-only 11f476a2..HEAD -- <cited paths>`.
Covers: The TypeScript monorepo — four stdio MCP servers over one shared core. Holds the two recorded adminAuth.ts defects (TODO items 2 and 3), still open. GraphClient sends its token only to its base origin (T-0090). Not a marketplace plugin; nothing registers it.; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to 6e581365 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91); re-anchored to 9580571e (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91); re-anchored to 5ab63076 (L-0516: deadline polls replace fixed sleeps in the flaky crew tests, crew 1.0.89; verify.json gains rule 10 so later rules shift by one and six lines); re-anchored to 805b0a25 (L-0516 split per the tooling-PR rule: sabotage_qa.py back to main's copy, its four entries move to L-0563; verify.json rule 10's why and CHANGELOG reworded in place); re-anchored to 7ecbdc7f (L-0516 re-bumps crew to 1.0.91 after the split; version files, CHANGELOG heading and the two version sentences only); re-anchored to a9c0d9ab (L-0516: pylint R1732 fix in test_poll_fixtures.py (with-blocks, no line this map cites moves) and crew re-bumped to 1.0.92; version files, CHANGELOG heading and the two version sentences in place); re-anchored to 083cda66 (L-0516 merges main 64b04c6b (W-0116 #292: crew_refresh_check.py gains the Windows _FINAL_PATH check, test_refresh_admission.py two Windows premises; runner-autostart.yml) and crew re-bumped to 1.0.93; version files, CHANGELOG heading and the two version sentences in place); re-anchored to 908c03af (L-0516 review round 1 fixes: poll_until reads the clock before each probe after the first, test_poll_fixtures.py reaps its children with wait(timeout=10), CHANGELOG corrected; crew re-bumped to 1.0.97; version files, CHANGELOG heading and the two version sentences in place); re-anchored to 11f476a2 (L-0516 merges main 6fe0e0db, T-0505 #296, without rerere; crew 1.0.98; no body citation moved)
## Landmines
- The credential chain caches its winner for the process lifetime.
- `scopesOverride` silently broadens a narrow scope request.
- `dist/` is what runs, `src/` is what you edit.
- The stale-build gap in the TEST path is CLOSED (2026-09-06, commit `4e2bfb78`).
- `o365-user` does not use the admin credential chain at all.
- Each server pins an exact core version, not a range.
Full note: `.crew/codemap/mcp-servers.md`.
