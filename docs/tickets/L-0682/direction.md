# L-0682 direction - sabotage entries for the T-0075 round-6 follow-up (tooling PR)

status: new
Split from T-0103 on 2026-10-04. T-0103 itself carries the production fixes (`apply_delete`, `widening_note`) and the `with`-block rewrite. This child carries everything that edits `plugin/crew/tests/sabotage_config.py`, which is review/gate harness (`HARNESS`, scripts/check-tooling-pr.py:58-87) and so lands in a PR with no production code.

## Problem (checked at origin/main `155fe6d8`, crew 1.0.322)
1. T-0075 round 6, BLOCK: no sabotage entry removes `_content_problem`'s object-at-a-leaf branch (plugin/crew/hooks/scripts/crew_config.py:2827) or `value_allowed`'s `shape == "under"` branch (:2788). The T-0075 lane ran both mutations by hand and the named tests went red; only the entries are missing.
2. From the T-0075 landing: `os_error_text` (plugin/crew/hooks/scripts/crew_config_files.py:82) has no entry that puts `{exc}` back at a call site, and no direct test. On Linux the only visible difference is quoting, so today's tests pass either way.
3. T-0103's two fixes need their own entries, which a feature PR may not add.
4. Round-6 NIT: `.crew/codemap/crew.md:502` says `98 mutations` for `CONFIG_MENU_MUTATIONS`; the tuple is larger.

## Options for item 2
1. **Recommended, taken:** add tests that raise an `OSError` whose filename is a backslash path and assert the refusal names it as written. `str(exc)` doubles the backslashes on every OS, so the mutation is red on Linux and Windows alike and the entries sit in the tuple.
2. Keep it Windows-only and record the evidence outside the tuple. `sabotage.py` has no per-platform skip (an entry green on Linux prints `STILL GREEN` and fails the suite, plugin/crew/tests/sabotage.py:3377), so this needs either a harness change or a hand-kept record.

## Recommendation
One tooling-only PR after T-0103 merges: new tests, new entries, the codemap count. No production code.
