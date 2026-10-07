# T-0102 plan

Written by the implementing session, 2026-10-05, on `rush/g5-platform` (cut from `release/1.2.0`).

1. Tests first: `skills/windows-ssm/tests/test_ssm_output.py` (module name unique in the repo) with
   every must-pass and must-fail case in the spec's acceptance list, the never-echo sentinel case and
   the cites-a-source check over `references/ssm-limits.md`. Confirm red.
2. `skills/windows-ssm/scripts/ssm_output.py`: stdlib, offline. Order of judgement: unreadable or
   not a get-command-invocation object -> could not tell (4); either stream at or over its limit in
   characters or UTF-8 bytes -> truncated (3), naming the S3 URL or the two complete-output routes;
   status `Success`/`Failed` -> complete (0); any other status -> could not tell (4). A cut is
   reported even while the command runs, since it is already certain. UTF-16 input (Windows
   PowerShell 5.1's `>`) is decoded by its BOM.
3. The two references and SKILL.md; every numbered limit row carries its AWS or Microsoft URL.
4. Registration in one commit: marketplace entry (1.0.0, after `web-testing-playwright`), both
   install scripts at the same position and text, both README rows, `skills/UPDATE.md`,
   CHANGELOG, the four `skills-count` claims 35 -> 36, `sync-updates.py`.
5. Test wiring that must agree: `.crew/verify.json` skill-suites rule, `scripts/gate-runner.py`
   `COMBINED_DIRS`, `scripts/ci-select.py` `COMPONENTS` (C-0001 made it the source of the combined
   list; its suite pins gate-runner against it), and the `pytest-crew.yml` fallback list.
6. Sabotage by hand: `>=` -> `>` and the non-terminal branch returning 0 must each turn tests red.
