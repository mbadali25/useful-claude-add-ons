# T-0084 plan          status: plan   risk: med

Written 2026-10-04 by the implementing cloud session, from spec.md and origin/main as merged
into `T-0084-build` (merge of main at `baf193aa`). The owner was unavailable; every open question
takes the spec's recommended option (listed at the end). Scope is spec.md's slice only: the
pointer format, `resolve` and `check`. Read-only; no hook, no config key, no harness path.

## Anchors re-checked at the merged main
- `plugin/crew/hooks/scripts/crew_recall.py` `obsidian_config_path` (honours `CREW_OBSIDIAN_CONFIG`)
  and `_read_json` - reused by import, unchanged.
- `plugin/crew/hooks/scripts/crew_config.py` `resolve_config(root)` - the `memory.vaultPath`
  fallback, unchanged.
- `plugin/obsidian-vault/hooks/scripts/vault_import.py` `contained` - the containment rule,
  restated (not imported).
- `scripts/check-tooling-pr.py` `HARNESS` - none of the paths below is in it.

## Steps (test-first: each test is written and seen red before the code)
1. **Tests** `plugin/crew/tests/test_crew_memory.py`, fixtures under `tmp_path` only (`HOME`,
   `USERPROFILE`, `CREW_OBSIDIAN_CONFIG` and the crew repo root all point at the fixture):
   grammar accept/refuse tables, full-text bodies, resolve happy path (named vault and the
   `memory` fallback), two hosts, one test per degraded state, unparseable config,
   no substitution, symlink containment, `check` rows/sort/counts/`--json`, read-only hash,
   bash + pwsh parity, usage exit 2. Test names exactly as spec.md's acceptance list.
2. **Module** `plugin/crew/hooks/scripts/crew_memory.py` (new, stdlib only, writes nothing):
   `split_frontmatter` (bytes split on the first two `---` lines, never YAML-parsed),
   `classify_body` (pointer / malformed / full-text, in that order), `parse_pointer`,
   `vault_path(name, root)` (Obsidian config `vaults.<name>.path`, `role: ignore` is unknown;
   for `memory` only: crew `memory.vaultPath`, then legacy top-level `vaultPath`; an existing
   directory or a named failure; never another vault), `note_path` (os.path.join over segments,
   no symlink component, realpath under the vault's realpath), `resolve_file`, `check_dir`,
   and the `resolve` / `check` CLI (exit 0/1/2 per the spec's state table; LF-only output).
3. **Sabotage by hand** (not committed; the entries are L-0679): drop the `..` check, drop the
   symlink check, let an unavailable vault fall through to another, and treat an unparseable
   config as empty. Each must turn a named test red; restore.
4. **Skill** `plugin/crew/skills/crew-memory/SKILL.md`: section "Native memories as vault
   pointers" (pointer line, run `resolve` and read the printed path, state table, report a
   non-`resolved` state; writing pointers arrives in a later crew version; `OBSIDIAN_VAULT_PATH`
   is not honoured).
5. **Docs**: README section 14, `plugin/PLUGINS.md` crew-memory row, the guide's memory chapter
   (`docs/guides/crew/src/memory-and-obsidian.md`) and its rebuilt outputs, `.crew/codemap/crew.md`,
   BUDGETS.md if a count moves, CHANGELOG entry.
6. **verify.json**: one rule, paths `crew_memory.py` + `test_crew_memory.py`, run through
   `pytest_rule.py`, measured `seconds`, `why`, `reach: local`. Regenerate rules.
7. **Delete** `docs/tickets/T-0084/` in the final content commit.
8. **Version-only last commit**: crew to the coordinator's placeholder (1.0.398) everywhere stated.

## Decisions taken with the owner unavailable (spec's recommended option)
- Crew writes the vault note itself (later slice), no delegation to obsidian-vault.
- No hook and no SessionStart nudge.
- Default note folder `memories/<project>/<title>.md`, type `concept`, dated `## Update` - writer
  slice (L-0677) decisions, recorded only; nothing here writes.
- `OBSIDIAN_VAULT_PATH` is not honoured; stated in the skill.
