# T-0083 plan: vault recall relevance, slice 1 (the obsidian-vault recall CLI)

Written 2026-10-04 by the implementing session from spec.md and origin/main `86d96fa1`
(obsidian-vault 0.4.16). No plan.md existed before. The spec is the contract; this file only
orders the work.

## Re-checked at origin/main 86d96fa1

- HANDOFF.md dependency table: T-0021, T-0087 (a7524aac, #281) and T-0088 (a61a6f38, #262)
  are all merged. Nothing blocks.
- Spec anchors still hold: plugin/obsidian-vault/hooks/scripts/vault_recall.py:40 `SKIP_DIRS`,
  :50-56 `terms_of`, :59-78 `split_note`, :110-115 `iter_notes`, :135 `score <= 0`, :139 sort,
  :197-199 JSON keys, :222-231 `add_parsers`; test_memory_ops.py:320-375 `_t_recall`, :1350 case list.
- `.crew/verify.json` still has no rule running test_memory_ops.py for a vault_recall.py change.
- No real vault exists in this cloud container (no `~/.claude/obsidian`, no `.obsidian/app.json`
  anywhere), so the spec's two implement-time hand checks cannot run here (see "Not verifiable").

## Decisions taken with the owner unavailable

- decision taken with the owner unavailable: another project's notes when `--project` is given -> rank last, never dropped.
- decision taken with the owner unavailable: excluded folders -> built-in `wiki/sessions/archive/` plus the vault's plain `userIgnoreFilters` entries.
- decision taken with the owner unavailable: relevance floor -> 1 matched term for 1-2 query terms, 2 for 3-5, 3 for 6+.
- decision taken with the owner unavailable: obsidian-vault version -> the spec recommends a minor bump (0.5.0); this build sets a placeholder one patch past main (0.4.17) per the coordinator, re-bumped at landing. The CHANGELOG still says "behaviour change: default recall results".
- decision taken with the owner unavailable: replace other projects' names in direction.md -> already done in the published copy.

## Steps (test-first)

1. Tests first: add `_t_recall_relevance` to test_memory_ops.py with every acceptance-check label
   from spec.md, register it in the case list, run, see it red against current vault_recall.py.
2. vault_recall.py, in this order, re-running the suite after each:
   a. stop words + 3-character minimum in `terms_of`;
   b. `matched` per note and the floor (`need`, `--min-terms`), `below_floor` count;
   c. excluded folders: built-in prefix + plain `userIgnoreFilters` from `.obsidian/app.json`,
      pruned in `iter_notes`, `excluded_dirs`, `skipped_filters`, `--include-excluded`;
   d. note kind from path and its rank;
   e. `project:` scalar from frontmatter, `--project` (comma-separated, repeatable,
      case-insensitive), folder match, rank match/none/other;
   f. sort key: project rank, kind rank, -score, path; JSON additions.
3. Whole suite green: `python3 plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py` and
   `bash plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh`; `_t_recall` unedited.
4. Sabotage (a)-(g) from the spec by hand, each red on its named label and green on restore.
   `.work/` is untracked, so the record goes in the PR body.
5. Docs: README recall section, obsidian-setup SKILL.md table row, memory-vault.md layout,
   memory-recall-proof.md and troubleshooting.md (empty recall can be the floor; `--min-terms 1`,
   `--include-excluded`), guide outputs rebuilt if the build tools exist here, codemap
   obsidian-vault.md re-anchored, CHANGELOG entry, verify.json rule with a measured `seconds`.
6. Delete docs/tickets/T-0083/ in the final content commit.
7. Last commit, version only: obsidian-vault in plugin.json, marketplace.json, PLUGINS.md,
   CHANGELOG heading. No crew file changes, so crew is not bumped.
8. Verify after committing: check-marketplace.py, rules --check, run-tests.sh, smoke, pwsh-isolation
   rule, check-tooling-pr.py (no harness path), ruff + pylint on vault_recall.py and the test.

## Not verifiable here

- The shape of `userIgnoreFilters` against a real `.obsidian/app.json`: built from Obsidian's
  documented form (a list of strings; a `/.../` string is a regex). Ships per the spec's taken
  option; flagged in the PR body for a check on the owner's vault.
- The hand run of five recent prompts over a real vault (floor thresholds): no vault here.
