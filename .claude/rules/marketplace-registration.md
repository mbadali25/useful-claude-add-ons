---
paths:
  - "scripts/**"
  - "plugin/PLUGINS.md"
---
<!-- crew:generated source=.crew/codemap/marketplace-registration.md sha256=a02246fbeaafb3fd -- do not hand-edit; regenerate with crew_instructions.py rules -->
# marketplace-registration
Code map anchor `70993489`; if it is behind HEAD, re-check with `git diff --name-only 70993489..HEAD -- <cited paths>`.
Covers: The marketplace itself: what registers a skill vs. a plugin, the two install scripts, and the two separate version-check paths (check-marketplace.py vs. _verify/smoke.sh).; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to 6e581365 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91); re-anchored to 9580571e (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91); re-anchored to 89ebda03 (L-0558 merges main 52489039)
## Entry points
- `.claude-plugin/marketplace.json:217` — crew's `description`, now correct against disk on every measured count.
- `scripts/check-marketplace.py:1639` — `main()`, sixteen checks in the same order as `verification-harness.md` records.
- `scripts/check-marketplace.py:104` — `check_registration`.
- `scripts/check-marketplace.py:301`, `:329`, `:383` — `check_catalogs`, `check_menu_parity`, `check_group_parity`.
- `scripts/check-marketplace.py:413` — `check_docs`, the three-file, link-substring-only check.
- `scripts/check-marketplace.py:673`, `:904`, `:918`, `:1026`, `:1081` — `check_self_claims`, `DESCRIPTION_CLAIMS`, `check_description_claims`, `CATALOG_CLAIMS`, `check_catalog_claims`.
- `scripts/install-prerequisites.sh:1298`, `:1383`, `:1422`, `:1448` — `SKILL_KEYS`, `PLUGIN_KEYS`, `TEAM_KEYS`, `COMMUNITY_KEYS`.
- `scripts/install-prerequisites.ps1:1127`, `:1173`, `:1188`, `:1205` — the four PowerShell catalog arrays, in the same order.
Full note: `.crew/codemap/marketplace-registration.md`.
