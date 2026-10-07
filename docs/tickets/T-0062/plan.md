# T-0062 plan (written by the implementing session, 2026-10-05, rush/g4-deploy)

Built on release/1.2.0 after T-0009 (PR #336) was ported onto the same branch. The dispatch
reader lives in `plugin/crew/hooks/scripts/crew_dispatch.py` there (split out of `crew_guards.py`
for `.pylintrc`'s module ceiling), so U1's `dispatch_read` is added to `crew_dispatch`, not
`crew_guards`; its contract is U1's.

1. RED: `test_promote_gate_dispatch.py` (sh flavour) and `test_promote_dispatch_reader.py`, one
   test per acceptance bullet.
2. `crew_dispatch.dispatch_read(text, shell, helpers=None)` -> `("none" | "unsure" | "read", why,
   scopes)`: `dispatch_answer`'s steps up to `dispatch_scopes`, no `dispatch_engaged`, no
   classification. `dispatch_answer` is NOT re-expressed: `test_dispatch_answer_is_the_only_road`
   reads its source, and no T-0009 assertion may change. A table test holds the two readings to
   one answer instead.
3. `_promote_dispatch.py`: reads the map(s) and the command through `dispatch_read`; prints
   `env<TAB>name` / `block<TAB>why` / nothing. U2 (file names, `.github/workflows/` dropped), U3
   (declared literal inputs present and equal; `*` or an unreadable command input is
   could-not-tell; a declared `$(...)`/backtick value becomes `SUBSTITUTED` and is not compared),
   U4 (no declared dispatch: nothing changes). Committed map first when dirty.
4. `promote-gate.sh`: call the helper only when containment matched nothing; a helper failure
   blocks ("This is not a pass"); `block()` moved above it so the incident lane records the row.
5. Mutations in `promote_tree_mutations.py` (not harness), one per acceptance mutation, each RED.
6. Docs: promote.md (in place, 380 lines), README, PLUGINS.md, INSTALLATION.md,
   crew-verification and troubleshooting, CONFIG.md; verify.json's promote rule; CHANGELOG.

U5 measured: `_promote_tree.py` emits `hex` for a sha in `'inputs[ref]=<sha>'` (no change needed).
