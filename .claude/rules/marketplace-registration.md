---
paths:
  - "scripts/**"
  - "plugin/PLUGINS.md"
---
<!-- crew:generated source=.crew/codemap/marketplace-registration.md sha256=ca696576c405b82a -- do not hand-edit; regenerate with crew_instructions.py rules -->
# marketplace-registration
Code map anchor `90186613`; if it is behind HEAD, re-check with `git diff --name-only 90186613..HEAD -- <cited paths>`.
Covers: The marketplace itself: what registers a skill vs. a plugin, the two install scripts, and the two separate version-check paths (check-marketplace.py vs. _verify/smoke.sh).; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes); re-anchored to 14b52c91 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86); re-anchored to 0c3508e9 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86); re-anchored to 6e581365 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91); re-anchored to 9580571e (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91); re-anchored to 9580571e (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91); re-anchored to b1d8a4e8 (L-0557: per-test XDG_CACHE_HOME for every pwsh the suites spawn, crew 1.0.89, obsidian-vault 0.4.16); re-anchored to d9ccfd5a (L-0557 merges main 0c0275e8 (W-0116 #292, crew 1.0.89) and re-sets crew 1.0.95); re-anchored to 97ace923 (L-0557 review round 1 fixes, crew 1.0.96); re-anchored to 550c39cd (L-0557 merges main 6fe0e0db (T-0505 #296, crew 1.0.92); crew stays 1.0.96); re-anchored to 038d5d10 (L-0557 merges main 44d3dbc6 (T-0110 #297, crew 1.0.97) and re-sets crew 1.0.99); re-anchored to 90186613 (L-0557 merges main 52489039 (T-0040 #290, crew 1.0.98) and re-sets crew 1.0.101)
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
