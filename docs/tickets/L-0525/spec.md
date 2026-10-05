# L-0525: sabotage suite: 13 vacuous entries and 1 unproven keep the whole run from going green          status: spec   risk: medium
Written against origin/main `a555ff37` (2026-10-05). Entry 15 of the direction (the cloud guard r1 OOM) is
already fixed by T-0080 (PR #399, crew 1.0.337) and is out of scope beyond confirming it.

## Intent
One uninterrupted `python3 plugin/crew/tests/sabotage.py` run on a Linux host with pwsh ends
`SABOTAGE SUITE: PASS`, exit 0, with no index skipped. Every entry is either `RED (good)` or
`NOT RUN -- windows-only`, a declared verdict that is named in a footer and never silent. The runner now
tells "the target test was skipped" apart from "the target test passed". A skip that was not declared fails
the suite as `NOT EXERCISED`. The entries that run on Linux (promote-gate.ps1 unreadable map, frozen-path
separators, the schema 5 install floor, `docs.theme`) each go RED on a real test.

## Exclusions
- No production code. If a mutation shows a real defect rather than a weak test, the entry records it and a
  new ticket is filed. The fix does not land here (this is a tooling-only PR).
- No change to T-0080's bound (`sabotage_bound.limits`, `run`, the memory and timeout caps).
- No new sabotage entries beyond these 14. No change to T-0086's standards content.
- Making the Windows-only verify-gate tests run under Linux pwsh is out of scope (direction Option 2, rejected).
- No growth of `plugin/crew/tests/sabotage.py` past pylint's `max-module-lines=3400` (`.pylintrc:140`).
  It is at 3381 lines, so the Windows-only label set lives in `sabotage_bound.py` or a new `sabotage_*.py` module.

## Evidence
origin/main `a555ff37`:
- Verdicts: `plugin/crew/tests/sabotage_bound.py:125-136`. Exit 0 becomes `STILL GREEN -- TEST IS VACUOUS`
  (`:129-130`), and any code other than 1 or 124 becomes `RED BUT UNPROVEN -- exit N` (`:136`). pytest's exit
  codes are documented at `:72-82`. A run whose only target is skipped exits 0.
- The runner loop is `plugin/crew/tests/sabotage.py:3358-3377` (`for label, target, find, replace, test in MUTATIONS`), and
  `run_test` is at `:3077-3099` (`-q --no-header -x --run-slow`). The tuple shape is unpacked as five fields, so a
  per-entry platform field would change every entry. A label set avoids that.
- `sabotage.py` is 3381 lines against `.pylintrc:140` `max-module-lines=3400`.
- Entries 4-12 (`plugin/crew/tests/sabotage.py:2465`, `:2604`, `:2668`, `:2691`, `:2710`, `:2760`, `:2785`, `:2862`, `:2874`) target tests
  that are skipped unless `sys.platform` is Windows and pwsh is present: `plugin/crew/tests/test_verify_gate_stop_budget.py:56-62`,
  `:253-254`, `:370-371`; `plugin/crew/tests/test_verify_gate_lock_window.py:61-67`, `:309-310`, `:615-616`;
  `plugin/crew/tests/test_verify_gate_rule_framing.py:285`. Entry 7 ("the bash gate stops publishing a deadline") targets
  `test_each_flavour_honours_a_deadline_the_other_published`, which is skipped off Windows too
  (`test_verify_gate_lock_window.py:309-313`), although the mutation is in `verify-gate.sh`.
- Entry 13: `plugin/crew/tests/sabotage_autocycle.py:472-479` targets `test_auto_clear_review_fixes.py::test_child_rechecks_tab_safety_after_the_delay_before_typing`
  (Windows only). Its Linux structural twin is `:480-494`.
- Entry 1: `plugin/crew/tests/sabotage.py:497-504`, target `plugin/crew/tests/test_promote_gate_unreadable_map.py:183-201` (`@needs_pwsh`).
  pwsh comes from `crew_fixtures.resolve_pwsh()` (`plugin/crew/tests/crew_fixtures.py:973-1002`), and this host has `/snap/bin/pwsh`.
  Whether the entry is vacuous or merely skipped here is unmeasured.
- Entry 2: `plugin/crew/tests/sabotage.py:1970-1977` removes `path = path.replace("\\", "/")` at
  `plugin/crew/hooks/scripts/crew_endpoints.py:1085`. Its target `plugin/crew/tests/test_endpoints.py:1041-1048` builds the
  path on POSIX, so the path never holds a backslash. The portable neighbour
  `test_scan_artifact_path_normalises_backslashes_in_a_frozen_path` (`:1051-1063`) covers `:1038`, which is a different line.
- Entry 3: `plugin/crew/tests/sabotage.py:2217-2223` mutates `INSTALL_DEFAULTS` at `plugin/crew/hooks/scripts/crew_guards.py:48`. That constant is read by
  `crew_config.default_config` (`plugin/crew/hooks/scripts/crew_config.py:356`) and `default_global_config` (`:592`), but not by the
  migration. The target `plugin/crew/tests/test_install_policy.py:235-252` asserts `"install" not in out` and
  `INSTALL_POLICY_DEFAULT == "manual"`, so a mutated `INSTALL_DEFAULTS` never reaches it.
- Entry 14: `plugin/crew/tests/sabotage.py:1003-1010` names `tests/test_upgrade.py::test_upgrade_config_adds_the_docs_and_bitbucket_blocks`.
  No test by that name exists. It was renamed to `test_upgrade_config_recognises_the_docs_and_bitbucket_blocks`
  (`plugin/crew/tests/test_upgrade.py:219`), which no longer asserts the default theme. pytest exits 4 (usage error) on a missing node id.
  The mutated line is `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:110`. An existing test already pins it:
  `test_upgrade_config_does_not_alias_the_shared_docs_block` (`plugin/crew/tests/test_upgrade.py:263-279`) asserts
  `DOCS_BLOCK == {"theme": None, "reportTheme": None}`, so re-pointing the entry there is expected to go RED. Measure it.
- Entry 15 is done. The T-0080 bound is in `plugin/crew/tests/sabotage_bound.py` (CHANGELOG "crew 1.0.337 ... T-0082 + T-0080, harness PR H2a",
  `CHANGELOG.md:1478`). The azureProfile entry is at `plugin/crew/tests/sabotage_cloud.py:566-575`, and the runner documentation is at `plugin/crew/README.md:3212-3225`.
- Harness: `scripts/check-tooling-pr.py:58-87` (`plugin/crew/tests/sabotage*.py` at `:79`). Tests and docs are in `ALONGSIDE` (`:99-120`).

## Unknowns
- For entries 1-3, whether each is vacuous (the test is too weak) or exposes a defect. Measure each in
  isolation first: `python3 plugin/crew/tests/sabotage.py` has no single-entry flag, so use a scratch
  driver that imports `MUTATIONS` and runs one entry. The default when it is a defect is stated in
  direction.md.
- The exact pytest summary forms to parse for "all skipped": `1 skipped`, `2 skipped, 1 deselected`, and
  `-x` early stop. They are pinned by tests in `test_sabotage_bound.py`. A summary that cannot be read is
  "could not tell", which fails.
- Whether the Windows-only label set should also be checked on Windows: every labelled entry must then go
  RED there. The default is yes, and the run on win-repo-2 is reported in the PR, not gated here.
- The next free crew patch version is set at implement time.

## Size and split
About 60 lines in `sabotage_bound.py` (the skip-aware verdict and the Windows-only label set) and about 10
in `sabotage.py`, including entries 1-3 and 14 re-pointed. Up to 3 new or strengthened tests (the
separator on a mocked `os.sep` or a backslash input, the `INSTALL_DEFAULTS` floor through `default_config`,
and the promote-gate message if needed), plus about 8 `test_sabotage_bound.py` cases. No production line.
Harness: **yes, tooling-only PR**. No further split.

## Touch
- `plugin/crew/tests/sabotage.py` (entries 1-3 and 14 re-pointed; must stay at or under 3400 lines)
- `plugin/crew/tests/sabotage_bound.py` (the `NOT RUN -- windows-only` and `NOT EXERCISED -- target skipped` verdicts, the label set, the footer)
- `plugin/crew/tests/sabotage_autocycle.py` (only if entry 13's label needs a marker there)
- `plugin/crew/tests/test_sabotage_bound.py`
- `plugin/crew/tests/test_sabotage_harness.py` (only if it pins the verdict strings)
- `plugin/crew/tests/test_upgrade.py` (only if the re-pointed target does not go RED)
- `plugin/crew/tests/test_endpoints.py`
- `plugin/crew/tests/test_install_policy.py`
- `plugin/crew/tests/test_promote_gate_unreadable_map.py` (only if entry 1 needs a stronger test)
- `plugin/crew/README.md` (the sabotage section near `:3212`: the two new verdicts and the footer)
- `.crew/codemap/verification-harness.md` (the sabotage runner block near `:398-416`)
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md` (only if `.md` line counts move)
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `docs/tickets/L-0525/` (removed in the final PR)

Not in Touch: any `plugin/crew/hooks/scripts/*` (no production code); `docs/guides/crew/src/*` (none mention
the sabotage verdicts; say so in the PR); `docs/diagrams/` (no box changes); `plugin/crew/CONFIG.md` (no
setting); `.crew/verify.json` (rule 11 already maps `sabotage_bound.py` and `test_sabotage_bound.py`, `.crew/verify.json:256-258`).

## Acceptance checks
Commands from the repo root. Run pytest and the sabotage run through the heavy-run wrapper on a memory-bound host.
- [ ] A target whose only test is skipped, with no Windows-only declaration, reads
  `NOT EXERCISED -- target skipped` and fails the suite. A declared Windows-only entry on a non-Windows host
  reads `NOT RUN -- windows-only` and does not fail it. An unreadable pytest summary fails it.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_sabotage_bound.py -q`
- [ ] Every label in the Windows-only set names an entry that exists in `MUTATIONS` (a stale label fails).
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_sabotage_bound.py -q -k windows_only_labels_exist`
- [ ] The `docs.theme` entry names a test that exists, and it passes on main (expected:
  `test_upgrade_config_does_not_alias_the_shared_docs_block`).
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_upgrade.py -q -k test_upgrade_config_does_not_alias_the_shared_docs_block`
- [ ] The separator and install-floor targets pass on main.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_endpoints.py plugin/crew/tests/test_install_policy.py plugin/crew/tests/test_promote_gate_unreadable_map.py -q`
- [ ] One uninterrupted full run on Linux with pwsh: `python3 plugin/crew/tests/sabotage.py` prints
  `SABOTAGE SUITE: PASS`, exits 0, and has no `STILL GREEN`, `RED BUT UNPROVEN` or `ANCHOR LOST` line. Each of
  the ten Windows-only entries prints `NOT RUN -- windows-only`, and the azureProfile entry prints `RED (good)`.
  Attach the log to the PR.
- [ ] `wc -l plugin/crew/tests/sabotage.py` is at most 3400, and `python3 -m pylint plugin/crew/tests/sabotage.py plugin/crew/tests/sabotage_bound.py` reports no `C0302`.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and the harness rule's suites pass
  (`python3 scripts/_test/tooling-pr.py`, the golden replay, seam contracts, and canary review, per `.crew/verify.json`).
- [ ] Docs: the README sabotage section and `.crew/codemap/verification-harness.md` describe both new verdicts.
  crew is bumped to the next free patch with a CHANGELOG entry, and `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0080 (sabotage bound): merged, PR #399 (crew 1.0.337). It is what made entry 15 RED.
- T-0087 (tooling PRs land alone): merged.
- Blocks nothing. Unblocks the "whole sabotage run is green" check that T-0086 round 1 waived.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
