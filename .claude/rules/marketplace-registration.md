---
paths:
  - "scripts/**"
  - "plugin/PLUGINS.md"
---
<!-- crew:generated source=.crew/codemap/marketplace-registration.md sha256=1392d2c5ebde6197 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# marketplace-registration
Code map anchor `8bf710ed`; if it is behind HEAD, re-check with `git diff --name-only 8bf710ed..HEAD -- <cited paths>`.
Covers: The marketplace itself: what registers a skill vs. a plugin, the two install scripts, and the two separate version-check paths (check-marketplace.py vs. _verify/smoke.sh).; re-anchored to c4e2eb98 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)); re-anchored to 0be97503 (L-0520 PR 1 merges main 42af3fb7 (L-0531)); re-anchored to 14bb59ef (L-0520 PR 1 merges main 6a8c60b1 (T-0099)); re-anchored to 8bf710ed (L-0520 PR 1 review round 1 fixes)
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
