# L-0675 direction: crew tells the recall CLI which project it is in          status: direction   risk: med
Split from T-0083 on 2026-10-04. Filed as L-0675.

## Ask
T-0083 found that the vault recall crew injects on every prompt was off-topic. Slice 1 (T-0083 itself) fixes ranking inside the obsidian-vault CLI and adds a `--project` option. This slice is crew's half: crew never says which project the session is in, so the CLI cannot prefer this repo's notes.

Evidence (origin/main `155fe6d8`):
- plugin/crew/hooks/scripts/crew_recall.py:244-245 builds the CLI call with `--query`, `--vaults`, `--max-chars`, `--json` only.
- plugin/crew/hooks/scripts/crew_context.py:604-606 `recall_items(query, cfg, budget)` has no repo root to derive a project from; its two callers (:1190, :1313) both have `root`.
- plugin/crew/hooks/scripts/crew_config.py:303-304 `memory.recall` holds `vaults` and `maxChars`; there is no project key.

## Options
1. **Recommended: pass `--project`, with one retry without it when the CLI rejects the option.** The project is `memory.recall.projects` when the repo sets it, else the main checkout's directory name. An obsidian-vault older than T-0083 slice 1 exits 2 on the unknown option; crew then asks once more without it inside the same time budget and logs that the project was not used. Recall never goes dark because of a version mismatch.
2. Pass the project in an environment variable. An older CLI ignores it silently. Rejected: crew could not tell whether the project was used, and "could not tell" would read as "used".
3. Pass `--project` with no fallback. Rejected: a machine that updates crew before obsidian-vault loses all recall, with only a `cli-exit-2` line in a log.

## Approval
Status `direction`. Option 1 taken as the default on 2026-10-04 with the owner unavailable; see the open questions in spec.md.
