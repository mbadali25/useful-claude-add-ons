anchor: useful-claude-add-ons@62b1c7a

# Verification harness

Three layers, fastest to slowest: `_verify/smoke.sh` (seconds), the direct
`scripts/check-marketplace.py` invocation (all checks, including the slow
one — see `marketplace-registration.md`), and `_verify/run-all.sh` (minutes).
`.crew/verify.json` maps a changed path to which of these to run.

## `_verify/smoke.sh` — 10 checks, not 9

**DERIVED.** The file's own header comment says *"9 checks, target is under
90 seconds"* (`_verify/smoke.sh:3`). Counting the actual `check "..." ...`
invocations in the file finds **10**:

| # | Line | What it runs |
|---|---|---|
| 1 | `_verify/smoke.sh:82-83` | `run_marketplace_check registration` — every dir registered, every source resolves, no nested marketplace |
| 2 | `_verify/smoke.sh:84-85` | `run_marketplace_check skills` — `SKILL.md` present, frontmatter name matches directory |
| 3 | `_verify/smoke.sh:86-87` | `run_marketplace_check plugins` — `plugin.json` version agrees with `marketplace.json` |
| 4 | `_verify/smoke.sh:88-89` | `run_marketplace_check catalogs` — catalog rows in all three READMEs (calls both `check_catalogs` and `check_docs`, `_verify/smoke.sh:65`) |
| 5 | `_verify/smoke.sh:90-91` | `run_marketplace_check menus` — `.sh`/`.ps1` menus are a matched pair (`check_menu_parity` + `check_group_parity`, `_verify/smoke.sh:66`) |
| 6 | `_verify/smoke.sh:92-93` | `run_marketplace_check hooks` — hook command quoting and `; exit $LASTEXITCODE` |
| 7 | `_verify/smoke.sh:97-124` (registered `:124`) | `ps_check` — every `.ps1`/`.psm1` parses, tracked via CI mode plus one pass per untracked file |
| 8 | `_verify/smoke.sh:126-127` | `plugin/crew/skills/crew-setup/scripts/_test/round-trip.sh` — the audit's `canon()` contract |
| 9 | `_verify/smoke.sh:239` (context) | localgpu CLI console script on the persistent PATH (skips if not bootstrapped on this machine) |
| 10 | `_verify/smoke.sh:356-357` | `version_agreement_check` — `pyproject.toml`/`plugin.json`/`marketplace.json`/hardcoded version literals all agree |

This task's own closing verification ran `bash _verify/smoke.sh` and got
`10 passed, 0 failed`, matching the actual check count rather than the
stale "9 checks" in the header comment. **Not fixed here** — this task does
not touch `_verify/`; recorded so the discrepancy is not mistaken for a
run-time failure by the next reader.

## `scripts/check-marketplace.py` — the direct gate

`main()` (`scripts/check-marketplace.py:377-403`) runs, in this order:
`check_registration`, `check_skill_manifests`, `check_plugin_manifests`,
`check_catalogs`, `check_menu_parity`, `check_group_parity`, `check_docs`,
`check_hook_commands`, `check_versions`. All eight run every time this
script is invoked directly — see `marketplace-registration.md` for the
correction to the "runs everything except check_versions" claim, which is
true only of `_verify/smoke.sh`'s internal fast-path helper, not of this
script.

`check_versions` (`scripts/check-marketplace.py:298-326`) is skipped
entirely, with a printed note, outside a git checkout or when
`marketplace.json` has no commit history — both early-return branches at
lines 306-311.

## `.crew/verify.json` — the mechanism, path to command

**DERIVED**, read directly: 13 rules as of this anchor, mapping a glob of
changed paths to shell commands (plus, for one rule, a required review
agent). Notable ones relevant to the subsystems covered elsewhere in this
codemap:

- `plugin/localgpu/cli/**`, `plugin/localgpu/mcp/**` → `bash _verify/run-all.sh`
  — its `why` field records that until 2026-09-05 neither this file nor
  `_verify/smoke.sh` ran `cli/_test`'s pytest suite at all; `run-all.sh` now
  covers both `cli/_test` and `mcp/_test`.
- `.claude-plugin/marketplace.json`, `skills/**`, `plugin/**` →
  `bash _verify/smoke.sh` — the one-script-covers-everything registration
  gate, plus version drift (drift here means the *smoke* checks proxy for
  the direct script's checks; see the version-path correction above for the
  one case where they diverge).
- `plugin/*/hooks/**` → `bash _verify/smoke.sh` **and**
  `bash plugin/crew/hooks/scripts/_test/run-tests.sh`, with a required
  `security` review agent — the only rule in the file requiring a named
  reviewer, because a hook runs unconditionally and this is the suite that
  sabotage-tests the guard actually blocking what it claims to.
- `scripts/install-prerequisites.sh`, `.ps1` → `bash _verify/smoke.sh` **and**
  `bash scripts/_test/menu-groups.sh` — the matched-pair proof plus the
  sub-picker / group-flag behavior smoke.sh's check 5 does not reach.

## What was run to close this task

`python scripts/check-marketplace.py` → `marketplace: 25 skills, 4 plugins`,
`all checks passed`. `bash _verify/smoke.sh` → 10 passed, 0 failed (verbatim
output not reproduced here; re-run it to see the same). Neither moved from
before this task's file additions to after — this task added files only
under `.crew/codemap/`, which no rule in `.crew/verify.json` and no check in
either script currently reads.

`_verify/run-all.sh` was **not run** for this task — it drives pytest suites
against a bootstrapped localgpu venv and a real PowerShell, neither of which
this documentation-only change touches or requires. Its own header estimates
minutes, not seconds, which is also why it was not run speculatively.
