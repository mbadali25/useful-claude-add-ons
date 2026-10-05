# T-0033 plan            spec: .work/tickets/T-0033/spec.md

> **STALE (noted 2026-10-05, published unchanged otherwise).** Written 2026-09-26 against `1e0706ac`: its line numbers, its CHANGELOG rules (old bullet shape) and its missing `auto_accept` step do not match origin/main `a555ff37`. The ticket is on HOLD (see spec.md). Re-plan from spec.md before building.

Four steps. Every step writes its tests first. They must fail against today's raw-hash comparison, then pass. The ticket loosens what a gate accepts (`/crew:done` check and `crew_autopilot` both act on `check_receipt`). So each must-allow case has must-block neighbours, and step 3 sabotages every narrowing rule. Line numbers are from origin/main 1e0706ac. Second opinion skipped: the design is settled in the spec's Design choice section, and it mirrors T-0026's dual-read, which landed.

### Step 1: `normalise_versions` and `receipt_sha256` in review_patch.py
Files: plugin/crew/hooks/scripts/review_patch.py, plugin/crew/tests/test_review_receipt_hash.py
Where: `_DIFF_FLAGS` `review_patch.py:102`, `bundle_sha256` `:261-266`, the manifest `:331-349`, and the docstring `:39-47` ("SPLITTING" paragraph)
Test: python3 -m pytest plugin/crew/tests/test_review_receipt_hash.py plugin/crew/tests/test_review_patch.py -q
Risk: high. If the normalisation is one byte too wide, a reviewed branch gains unreviewed content and `/crew:done` passes. If it is too narrow, the re-bump still stales and nothing improves.
- [ ] Add constants:
  - `RECEIPT_SCHEME = "crew-review/2"`
  - `_SEMVER = rb"[0-9]+\.[0-9]+\.[0-9]+"`
  - `_VERSION_MARK = b"\0version\0"`
  - `_BLOB_MARK = b"\0blob\0"`
- [ ] Add `_bookkeeping(path: str) -> bool`. It is true only for:
  - `re.fullmatch(r"(?:[^/]+/)*\.claude-plugin/plugin\.json", path)`
  - `.claude-plugin/marketplace.json`
  - `plugin/PLUGINS.md`
  - `CHANGELOG.md`
- [ ] Add `normalise_versions(patch: bytes) -> bytes`:
  - Split at `diff --git ` section starts with the same boundary rule `split_parts` uses (`:229-237`).
  - A section qualifies only if its header line is exactly `diff --git a/P b/P` with `_bookkeeping(P)`, it has no `rename from`/`copy from` line, and it has no line starting `Binary files`.
  - In a qualifying section, replace only the new id on the `index <old>..<new>` line with `_BLOB_MARK`. The old id and the mode suffix stay.
  - Replace semver groups only on `+` lines after the first `@@`, excluding the `+++ ` header:
    - JSON paths: fullmatch `\+[ \t]*"version":[ \t]*"(SEMVER)",?`
    - PLUGINS.md: fullmatch `\+\| \*\*Version\*\* \| (SEMVER)<!-- claim: plugin-version:[a-z0-9-]+ --> \|`
    - CHANGELOG.md: match at line start ``\+- \*\*`[a-z0-9-]+` (SEMVER):``, plus every ``Bumped `(SEMVER) -> (SEMVER)` `` span.
  - Replace only group spans with `_VERSION_MARK`. Every other byte is kept.
- [ ] Add `receipt_sha256(patch)`, which returns `sha256(RECEIPT_SCHEME.encode() + b"\0" + normalise_versions(patch)).hexdigest()`.
- [ ] `compute` adds `"receipt_scheme": RECEIPT_SCHEME` and `"receipt_sha256": receipt_sha256(patch) if parts else None` to the manifest. `bundle_sha256` and the patch are untouched.
- [ ] Update the docstring: the raw hash is what the reviewer read, and the receipt hash normalises version tokens only.
- [ ] Tests. They build a tmp repo with `review_fixtures.init_repo` (`review_fixtures.py:40`), seeded with copies of origin/main's plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md and a CHANGELOG.md holding the 1.0.41 entry's first 12 lines. The base commit sits at 1.0.37. The branch bumps to 1.0.40 across all four and adds a code file, and the manifest is computed. Then:
  - Must-allow: `test_normalised_hash_survives_a_pure_rebump` (1.0.40 -> 1.0.42 in all four, including both `Bumped` tokens) and `test_normalised_hash_survives_a_rebump_of_json_files_only`.
  - Must-block (receipt hash differs): `test_changelog_prose_edit_changes_the_receipt_hash`, `test_new_plugin_json_key_changes_the_receipt_hash`, `test_code_change_changes_the_receipt_hash`, `test_version_on_a_line_with_another_edit_changes_the_receipt_hash`, `test_version_and_adjacent_line_in_one_hunk_change_the_receipt_hash`, `test_non_semver_version_changes_the_receipt_hash`, `test_version_line_outside_bookkeeping_files_changes_the_receipt_hash`, `test_renamed_plugin_json_changes_the_receipt_hash`, `test_plugin_json_mode_change_changes_the_receipt_hash`, `test_binary_edit_outside_the_set_changes_the_receipt_hash`, `test_binary_plugin_json_is_not_normalised`, `test_minus_line_rewrite_changes_the_receipt_hash`.
  - Unchanged input: `test_bundle_patch_and_hash_are_unchanged` asserts `bundle_sha256 == sha256(patch)`, `b"".join(parts) == patch`, and that the patch holds no `\0`.

### Step 2: dual-read in review_ledger.py, recording in review_run.py
Files: plugin/crew/hooks/scripts/review_ledger.py, plugin/crew/hooks/scripts/review_run.py, plugin/crew/tests/test_review_receipt_hash.py
Where:
- `record` `review_ledger.py:238-286` (row `:270-274`, CLEAN receipt `:276-280`)
- `accept` `:289-332` (compare `:320-323`)
- `_current_hash` `:356-363`
- `check_receipt` `:366-396`
- docstring `:49-55`
- `review_run.py` review dict `:334-336`
- `bundle_problems` `:228-256`

Test: python3 -m pytest plugin/crew/tests/test_review_receipt_hash.py plugin/crew/tests/test_review_receipt.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_review_fallback_bundle.py plugin/crew/tests/test_crew_autopilot.py -q
Risk: high. A fallback to raw, or an unknown scheme read as `/2`, lets a stale receipt pass or blocks every landing.
- [ ] `record` copies `receipt_scheme` and `receipt_sha256` from `review` into the row, and into the CLEAN receipt, only when both are strings. Otherwise it writes neither, and the round is a raw (v1) round.
- [ ] Add `_current_receipt_hash(root, base)`. It returns `review_patch.compute(root, base)[0]["receipt_sha256"]` and raises `LedgerError` exactly as `_current_hash` does.
- [ ] Add `_scheme_matches(root, entry) -> (ok, current, why)`. It requires `entry["receipt_scheme"] == review_patch.RECEIPT_SCHEME` and a string `entry["receipt_sha256"]`. Otherwise it returns `(False, None, "receipt hash scheme <x> is not one this crew reads")` or `(False, None, "receipt_sha256 is missing")`. It then compares `_current_receipt_hash`.
- [ ] `check_receipt`: before the existing `try: current = _current_hash(...)` block, add `if receipt.get("receipt_scheme") is not None:` and return through `_scheme_matches`. Stale messages keep today's wording plus the scheme. The v1 block below stays byte-identical, including the line `    if current != receipt["bundle_sha256"]:` that sabotage.py:3023 anchors on.
- [ ] `accept`: add the same branch on the row's `receipt_scheme`. The v1 comparison `:320-323` stays as it is. The receipt it writes copies `receipt_scheme`/`receipt_sha256` from the row when present.
- [ ] `review_run.py`: the review dict adds `"receipt_scheme": manifest.get("receipt_scheme")` and `"receipt_sha256": manifest.get("receipt_sha256")`. `bundle_problems` keeps each part's bytes. When no problem was found and the manifest carries `receipt_sha256`, it appends `"the bundle parts do not hash to the manifest's receipt_sha256"` if `review_patch.receipt_sha256(b"".join(chunks))` differs.
- [ ] Update the docstring: the receipt carries both hashes, `/2` compares the normalised one, no scheme compares raw, and an unknown scheme is stale.
- [ ] Tests. They go through the `review_ledger.py --check-receipt` / `--accept` CLI (what `done.md:13` runs), on the step 1 fixture, recording rounds with the manifest's fields:
  - Must-allow: `test_pure_rebump_keeps_the_receipt` and `test_pure_rebump_then_accept_findings_succeeds`.
  - Must-block: `test_changelog_prose_edit_stales_the_receipt`, `test_new_plugin_json_key_stales_the_receipt`, `test_code_change_stales_the_receipt`, and `test_prose_edit_then_accept_findings_is_refused`.
  - Dual-read: `test_receipt_without_scheme_verifies_an_unchanged_tree`, `test_receipt_without_scheme_stales_on_a_rebump`, `test_unknown_receipt_scheme_is_stale`, and `test_scheme_two_receipt_without_receipt_sha256_is_stale`.
  - Recording: `test_review_run_records_the_receipt_scheme` runs a CLEAN round end to end with `review_fixtures.fake_reviewer_bin` (`:114`), then asserts the round row and the receipt carry both fields. `test_manifest_receipt_hash_not_matching_the_parts_is_incomplete` rewrites `receipt_sha256` in the manifest, and the round is INCOMPLETE with no receipt.
- [ ] Existing `test_review_receipt.py::test_check_receipt_fails_after_the_tree_is_edited` and `test_dropped_part_with_a_rewritten_bundle_hash_is_incomplete` pass unchanged.

### Step 3: sabotage every narrowing rule
Files: plugin/crew/tests/sabotage_review.py, plugin/crew/tests/test_review_receipt_hash.py
Where: `REVIEW_FIX_MUTATIONS` `sabotage_review.py:15`. It is already imported at `sabotage.py:69`, so sabotage.py is untouched.
Test: python3 plugin/crew/tests/sabotage.py (it has no label filter, so the whole suite runs; every `RECEIPT HASH:` line must read RED on its named test and the run ends `SABOTAGE SUITE: PASS`); python3 -m pytest plugin/crew/tests/test_sabotage_harness.py plugin/crew/tests/test_review_receipt_hash.py -q
Risk: low. This step is what proves steps 1-2 can fail.
- [ ] Append one mutation each to `REVIEW_FIX_MUTATIONS`, labelled `RECEIPT HASH: ...`:
  - (a) Every `+` line of a qualifying section is replaced by the mark. Red: `test_changelog_prose_edit_changes_the_receipt_hash`.
  - (b) The semver group becomes `[^"]+`. Red: `test_non_semver_version_changes_the_receipt_hash`.
  - (c) The JSON rule uses `search` instead of `fullmatch`. Red: `test_version_on_a_line_with_another_edit_changes_the_receipt_hash`.
  - (d) `_bookkeeping` accepts any path ending `.json`. Red: `test_version_line_outside_bookkeeping_files_changes_the_receipt_hash`.
  - (e) The blob id is blanked in every section. Red: `test_binary_edit_outside_the_set_changes_the_receipt_hash`.
  - (f) The `Binary files` skip is dropped. Red: `test_binary_plugin_json_is_not_normalised`.
  - (g) `check_receipt`'s `is not None` branch becomes `if True:`. Red: `test_receipt_without_scheme_verifies_an_unchanged_tree`.
  - (h) An unknown scheme falls back to the raw comparison. Red: `test_unknown_receipt_scheme_is_stale`.
  - (i) The `receipt_sha256` check is removed from `bundle_problems`. Red: `test_manifest_receipt_hash_not_matching_the_parts_is_incomplete`.
- [ ] `test_every_receipt_hash_sabotage_anchor_is_present_exactly_once` asserts that each mutation's anchor occurs once in its target file. The existing `the receipt check ignores the bundle hash` mutation still goes red on `test_check_receipt_fails_after_the_tree_is_edited`.
- [ ] Record in the PR body which test went red for each mutation.

### Step 4: docs, verify rule, version
Files: plugin/crew/README.md, plugin/crew/commands/review.md, .crew/verify.json, CHANGELOG.md, plugin/crew/BUDGETS.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json
Where: README "The receipt is bound to the bundle" `README.md:743`, review.md step 3 `:511-512` (edit in place, no added line), and verify rules at the end of `.crew/verify.json` (after the rule at `:281`)
Test: python3 scripts/check-marketplace.py; (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py); python3 -m pytest plugin/crew/tests/test_lifecycle_commands.py -q; python3 -m pytest plugin/crew/tests/ -q (run alone, with no other suite in parallel)
Risk: low. A missed version bump leaves every installed machine on the raw comparison (CLAUDE.md "Content change with no `version` bump").
- [ ] README:743: the receipt carries the raw bundle hash and a `crew-review/2` hash, which differ only in the version token of the four release bookkeeping shapes. List those shapes and what still stales. A receipt from before this change compares raw.
- [ ] review.md:512: "fails if anything changed since, other than a version-only re-bump of the release bookkeeping files".
- [ ] New verify rule. Paths: plugin/crew/hooks/scripts/review_patch.py, plugin/crew/hooks/scripts/review_ledger.py, plugin/crew/hooks/scripts/review_run.py, plugin/crew/tests/test_review_receipt_hash.py, plugin/crew/tests/sabotage_review.py. Run: `python3 -m pytest plugin/crew/tests/test_review_receipt_hash.py plugin/crew/tests/test_review_receipt.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_review_patch.py -q`. `seconds` is measured, not estimated, and `reach: local`.
- [ ] Bump crew to the next free patch in plugin.json, marketplace.json and PLUGINS.md. Add a CHANGELOG entry naming T-0033. Update BUDGETS.md if check-marketplace flags the Markdown line count.

## Self-review
- Spec coverage:
  - Must-allow and must-block at the hash level, and the unchanged reviewer input: step 1.
  - Must-allow and must-block through the CLI, accept, dual-read, recording and the `bundle_problems` integrity check: step 2.
  - Sabotage, including the existing receipt mutation and the anchor test: step 3.
  - The verify rule, README, review.md and the version: step 4.
  - The "existing suites pass unchanged" line: step 2's Test command plus the serial full run in step 4.
- Placeholders: none. Every test is named, and every rule is given as its regex or literal.
- Interface consistency: `RECEIPT_SCHEME`, `normalise_versions`, `receipt_sha256` and the manifest keys `receipt_scheme`/`receipt_sha256` are defined in step 1. Step 2 uses them by the same names, and step 3's mutations target them.
- Touch coverage: every Files: entry in steps 1-4 is in the spec's Touch. `crew_autopilot.py`, `commands/done.md`, `sabotage.py`, `test_review_receipt.py`, `test_review_ledger.py` and `test_review_patch.py` are run or read, not modified.
- Not verified while planning:
  - Whether git ever emits a qualifying section with a `similarity index` line and no rename. Step 1's rename test covers the rename case only.
  - How long the new verify rule takes. It is measured at step 4.
