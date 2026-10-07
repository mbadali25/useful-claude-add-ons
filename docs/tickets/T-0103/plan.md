# T-0103 plan

Written by the implementing session (feature rush 1.2.0, branch rush/g3b-bridge, base release/1.2.0 a555ff37).

1. Commit 1, alone: `test_config_menu.py` reads fixtures through two `with`-block helpers (`_bytes`,
   `_text`); the file-level `consider-using-with` disable goes. No assertion or test name changes
   (166 tests collected before and after).
2. Reproduce round-6 NIT 2 first: `test_a_repo_null_that_widens_is_described_by_the_value_in_force`.
   Measured on this base: worse than the NIT said -- a repo `null` on `pm.authority` under a wider
   machine value was not marked as a widening at all (`repo_widens`' `_RATCHETED` branch ranked the
   written `null`, not the inherited value). Fix there: rank the value in force, carry it as
   `inForce`, and `print_changes` passes it to `widening_note`; the token stays `null`.
3. `apply_delete`: a `stage` local ("before", "moving", "moving-back") set on lines of their own so
   the three sabotage anchor lines stay byte-identical and un-nested; `_delete_os_error` probes both
   names with `os.path.lexists` from the move on. The move-back `Displaced` names `path` and the
   parked name, never "the original is at <backup>".
4. Docs: config-menu.md step 3, commands/config.md, README, the code map's `apply_delete` paragraph
   and the regenerated `.claude/rules/crew.md`. CONFIG.md and troubleshooting.md: none, they do not
   describe delete's exits.
