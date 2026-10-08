# L-0675 plan

Written by the implementing session (feature rush 1.2.0, branch rush/g3b-bridge, base release/1.2.0 e84a8bfe).
T-0083 is merged (`vault_recall.py` accepts `--project`), so the end-to-end test runs.

1. Tests first, in `plugin/crew/tests/test_crew_recall_project.py`: every acceptance check in spec.md
   by its name. `context_fixtures.STUB_CLI` gains `STUB_MODE=noproject` (exit 2 when an argument
   starts with `--project`, answer otherwise).
2. `crew_recall.py`: `projects(crew_cfg, root)`; `recall(..., root=None)` appends
   `--project=<a,b>`, retries once without it on exit 2 inside one `CLI_TIMEOUT_SECONDS` deadline
   (no retry under 0.5 s left); result keys `project` and `projectUsed`. The sabotage-anchored
   lines (the sort line, the `label` line, the `_CONTROL_RE` filter) stay byte-identical.
3. `crew_context.py`: `recall_items(query, cfg, budget, root)`; both callers pass `root`; both log
   records carry `project` and `projectUsed`. `test_a_broken_cli_is_a_logged_miss_not_a_failure`'s
   expected dict gains the two keys in the same commit.
4. Config: `memory.recall.projects: []` in `crew_config.default_config()`, the template, the
   `crew_keys.KEY_META` row; regenerate the reference tables; re-pin the measured leaf counts.
5. Docs: README, CONFIG.md, crew-setup SKILL.md, memory-recall-proof.md, memory-and-obsidian.md,
   code map. Version set last (placeholder).
