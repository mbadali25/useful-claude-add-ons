# T-0033: a version-only re-bump does not stale a review receipt          status: spec   risk: high
## Refreshed 2026-10-05
**Still HOLD.** Re-checked against origin/main `a555ff37` (crew 1.1.0) for cloud hand-off. L-0522's delta gate is
still not on main (`git grep -l review_delta origin/main -- plugin scripts` prints nothing; PR #377, part 1 of 3,
merged 2026-10-04; part 2 is not open), so the 2026-10-04 default stands: hold, then close as superseded when
L-0522 part 2 lands. Every decision below is kept. What moved:
- Line anchors re-found by content at `a555ff37` and updated in Evidence (most `review_ledger.py` sites moved by one
  line; `crew_autopilot.py` and `crew_train.py` callers moved; `.crew/verify.json`'s review rule is now `:466-471`;
  `ALONGSIDE` is `:99-120`).
- `plugin/crew/tests/sabotage.py` is 3381 lines now, 19 under `.pylintrc:140` `max-module-lines=3400`. The decision
  not to touch it stands (new entries go in `sabotage_review.py`, already imported at `sabotage.py:68`).
- **CHANGELOG heading shape moved again.** Batch landings since crew 1.0.345 write `### crew <v> — batch N: ...`,
  `### crew <v>, gizmoduck <v> — ...` and `### Fixed — crew <v>, notify <v>: ...` (no backticks, several plugins in
  one heading, `CHANGELOG.md:12`, `:27`, `:163`), beside the older ``### Fixed — `crew` <v>: ...`` shape (`:875`) and
  a hyphen variant (`:909`). The CHANGELOG rule in Design choice is widened accordingly (still a closed, full-line
  grammar; only the semver tokens are replaced). Default taken; the owner confirms it at approval if this is built.
- plan.md is published as it was (2026-09-26, anchors from `1e0706ac`). It does **not** match: re-plan before building.

## Refreshed 2026-10-04
**HOLD - do not implement without an owner decision.** Checked against origin/main `155fe6d8` (crew 1.0.322); see direction.md "Direction check 2026-10-04". The default taken there is to hold this ticket and close it as superseded when L-0522's delta gate lands. This spec is kept as the fallback contract if the owner chooses to build the bump-only normaliser anyway.

What the refresh changed, and why:
- Scope statement. The design keeps a receipt only for a re-bump with **no** catch-up merge since review. Measured 2026-10-04 with origin/main's `review_patch.compute`: after a catch-up merge the version sections are diffed from the merged commit (T-0100), so the `-` version line, both blob ids and the CHANGELOG context lines change too, and this design reads stale. That case is L-0522's. Intent and Exclusions now say so plainly.
- CHANGELOG shape. Entries are now headings (`CHANGELOG.md:7`, ``### Changed — `crew` 1.0.322: ...``), so the normalised line is the heading. The bold-bullet and ``Bumped `a -> b` `` shapes are dropped: 49 heading entries carry the current format, and a re-bump only ever edits the newest entry.
- Evidence: every `path:line` re-read at origin/main `155fe6d8`. Three comparison sites now, not two: `auto_accept` (L-0510) is the third.
- Touch: `plugin/crew/tests/sabotage.py` is at the pylint line limit (3400 of 3400), unchanged decision: not touched. Docs added per the repo rule for a `plugin/crew/` change (guide source and rebuilt outputs, code map, done.md). `.crew/verify.json` dropped: rule at `:414-419` already maps `review_*.py` and `test_review_*.py`.
- Split: if built, it lands as two tooling-only PRs (see "Size and split"). No child tickets were written, because the recommendation is not to build.
- Dual-read, the NUL placeholders, the path set, the full-line anchors and the must-block list are unchanged from the 2026-09-26 design.
- plan.md does **not** match any more: its line numbers are from `1e0706ac`, its CHANGELOG rules are the old shape, and it has no step for `auto_accept`. Re-plan before building.

## Design choice (planner, 2026-09-26 - for the owner to confirm at approval)
- Chosen: a second, normalised hash sits beside the raw one. `review_patch.compute` keeps `bundle_sha256` exactly as today (the sha256 of the patch the reviewer reads). It adds `receipt_sha256` = sha256(`crew-review/2` NUL `normalise_versions(patch)`) and `receipt_scheme: "crew-review/2"`. The reviewer's patch, its parts and `bundle_sha256` are byte-identical to today. Only the receipt comparison reads the normalised hash.
- What `normalise_versions` touches, and nothing else. It works per `diff --git a/P b/P` section, and only when P is one of: any `.claude-plugin/plugin.json` (at any depth), the root `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md` or `CHANGELOG.md`. A section is skipped (hashed raw) if it is a rename or copy (a/P differs from b/P), or carries a `Binary files` line. Inside a qualifying section it changes exactly two things:
  - The new blob id on the `index <old>..<new>` line becomes a fixed placeholder. This is needed: `--full-index` (`review_patch.py:141`) puts the whole-file blob id there, so a re-bump changes that line even when the hunks match. For a text section, the old blob (fixed by the receipt's base) plus the hunks determine the new blob, so the placeholder hides nothing the hunks do not show.
  - On `+` hunk lines only, a closed-grammar semver token `[0-9]+\.[0-9]+\.[0-9]+` becomes a placeholder, in exactly these line shapes:
    - JSON files: the whole line is `+<spaces>"version":<spaces>"<semver>"` with an optional trailing comma.
    - PLUGINS.md: the whole line is `+| **Version** | <semver><!-- claim: plugin-version:<name> --> |`.
    - CHANGELOG.md (refreshed 2026-10-05): a `+### ` line whose prefix, up to the first ` — `, ` - ` or `:` that follows the version list, fullmatches: optional (`Added`|`Changed`|`Fixed`|`Removed`) + (` — `|` - `), then one or more `<plugin> <semver>` items separated by `, `, where `<plugin>` is `[a-z0-9-]+` with or without backticks. Only the semver tokens in that list are replaced; the rest of the heading is hashed raw. Shapes at `a555ff37`: `CHANGELOG.md:12`, `:27`, `:163`, `:875`, `:909`.
  - `-` lines, context lines, the `+++` header, other tokens and every other byte are hashed as they are.
- Placeholders carry NUL bytes (`\0version\0`, `\0blob\0`). git classes NUL-bearing content as binary, so no text hunk line can contain one, and a raw line can never collide with a normalised one.
- Dual-read. A round row and its receipt gain `receipt_scheme` and `receipt_sha256` beside the unchanged raw `bundle_sha256`. The comparison depends on the receipt:
  - No `receipt_scheme` (a receipt written before this change): `check_receipt` and `accept` compare the raw hash, byte-for-byte as today. The code path is unchanged.
  - `crew-review/2`: they compare `receipt_sha256`. `auto_accept` (`review_ledger.py:692`) follows the same rule as `accept`.
  - Any other scheme, or a missing or non-string `receipt_sha256` under `/2`: the receipt reads stale and names the reason. There is never a fallback.
  - An older crew reading a `/2` receipt uses the raw field and stales on a re-bump, as it does today. It fails closed.
- The review-run integrity check (`review_run.bundle_problems`) recomputes `receipt_sha256` from the part bytes the reviewer read. A manifest whose `receipt_sha256` does not match those parts makes the round INCOMPLETE, the same as a rewritten `bundle_sha256` does today.
## Intent
A branch whose review receipt stands can have its version re-bumped, **with no catch-up merge since the review**, and the receipt still stands, with no successor plan, re-approval or review round. The re-bump may touch the `"version"` value in plugin.json and marketplace.json, the PLUGINS.md version cell and the version token in the CHANGELOG entry heading. Any other change, including CHANGELOG prose, a new key, a code edit or a version token outside those exact shapes, still stales the receipt.
## Exclusions
- **A catch-up merge after review is not covered.** After `git merge origin/main` the bundle diffs the version files from the merged commit (`review_patch.py:75-95`), so `-` lines, old blob ids and context change. That case reads stale here and belongs to L-0522's delta gate. Under the current workflow (merge main, then bump) this is the usual case, which is why the ticket is on hold.
- The reviewer's input does not change. The patch, the parts, `bundle_sha256` and the prompt stay the same.
- No change to T-0026's approval digest (`crew_ticket.approval_digest`), and no edit to `crew_ticket.py`.
- No normalisation of `-` lines, context lines, renames, binary sections, mode lines or any file outside the four shapes. No normalisation of prerelease or non-semver version strings, or of the pre-1.0.242 CHANGELOG bullet shape.
- No receipt migration or rewrite. The ledger at `<git-common-dir>/crew/review/` is written only by review_ledger.py.
- No change to the budget, reservation, refunds, successor-plan rules, `_review_json_problem`'s raw-hash binding (`review_ledger.py:653`), `review_run.py`'s webtest raw-hash comparison (`:488-510`), `merged_main.py`, `review_gate.py`, `crew_train.py`, `crew_autopilot.py` or `commands/done.md`'s command. The last three inherit the change through `review_ledger.check_receipt`.
- No new hook. No edit to `plugin/crew/tests/sabotage.py` (3381 lines at `a555ff37`, `.pylintrc:140` `max-module-lines=3400`; entries go in `sabotage_review.py`).
- Nothing of L-0522 (`review_delta.py`, the landing order, refresh artifacts) and nothing of L-0620 (the fast-path hole).
## Evidence
All re-read at origin/main `a555ff37` on 2026-10-05 (first read at `155fe6d8` on 2026-10-04).
- plugin/crew/hooks/scripts/review_patch.py:141 `_DIFF_FLAGS` includes `--full-index`. :366-371 `bundle_sha256(parts)`. :374 `compute`. :460-469 the manifest, `bundle_sha256` at :468, `merged_main` at :463. :44-46 (docstring) says `--check-receipt` recomputes it. :75-95 the merged-main rebuild (T-0100).
- plugin/crew/hooks/scripts/review_ledger.py:357 `record`; the round row stores `bundle_sha256`/`base` at :391 and the CLEAN receipt at :410-411. :423 `accept`, comparison at :457-458. :671 `auto_accept`, comparison at :692. :825-832 `_current_hash` returns `(manifest["bundle_sha256"], manifest.get("merged_main"))`. :856 `check_receipt`, comparison at :879.
- plugin/crew/hooks/scripts/review_run.py:434 `bundle_problems`, whole-bundle check at :457-458. :574-575 the review dict's `bundle_sha256`/`base`/`head`. :587 the only `review_ledger.record` caller.
- `check_receipt` consumers: plugin/crew/commands/done.md:13, plugin/crew/hooks/scripts/crew_autopilot.py:452, :528, :1271, plugin/crew/hooks/scripts/crew_train.py:1279, plugin/crew/hooks/scripts/review_run.py:675.
- Nothing on main implements this: `git grep -E "receipt_scheme|normalise_versions|receipt_sha256|crew-review/2" origin/main -- plugin scripts` prints nothing.
- Measured 2026-10-04, throwaway repo, origin/main's `review_patch.compute`:
  - bump only: the bundle changes in 4 lines (two `index` lines' new blob id, the `+  "version"` line, the `+` CHANGELOG entry line);
  - catch-up merge then bump: also the `-  "version"` line, the old blob id on both `index` lines and two CHANGELOG context lines.
- Version-bearing lines: plugin/crew/.claude-plugin/plugin.json:3, .claude-plugin/marketplace.json:224, plugin/PLUGINS.md:14 (`| **Version** | 1.1.0<!-- claim: plugin-version:crew --> |`), CHANGELOG.md:12 (newest entry heading, `### crew 1.1.0 — C-0006: ...`). Five plugin.json files exist, all under `plugin/*/.claude-plugin/`.
- Harness: scripts/check-tooling-pr.py:58-87 `HARNESS` lists `plugin/crew/hooks/scripts/review_*.py`, `plugin/crew/tests/sabotage*.py` and `plugin/crew/commands/review.md`; :99-120 `ALONGSIDE` lets tests, README, BUDGETS, version files, CHANGELOG, `docs/**`, `.crew/codemap/**`, `.crew/verify.json` and `graphify-out/**` ride along. `plugin/crew/commands/done.md` is in neither list.
- Sabotage: plugin/crew/tests/sabotage.py:3036-3041 anchors `    if current != receipt["bundle_sha256"]:\n` in review_ledger.py. sabotage.py:68 imports `REVIEW_FIX_MUTATIONS` from plugin/crew/tests/sabotage_review.py:19 (1156 lines). sabotage.py is 3381 lines.
- Test fixtures: plugin/crew/tests/test_review_receipt.py:29-47 (`repo`, `_review`, `_check`), :61 `test_check_receipt_fails_after_the_tree_is_edited`, :297 `test_dropped_part_with_a_rewritten_bundle_hash_is_incomplete`. plugin/crew/tests/review_fixtures.py:34 `git`, :41 `init_repo`, :186 `fake_reviewer_bin`.
- Docs that state the rule: plugin/crew/README.md:772, plugin/crew/commands/review.md:510, plugin/crew/commands/done.md:15-16, docs/guides/crew/src/troubleshooting.md:163.
- .crew/verify.json:466-471 already maps `review_*.py`, `commands/review.md` and `test_review_*.py` to `pytest_rule.py plugin/crew/tests/test_review_*.py`.
- L-0522's delta gate is not on origin/main (`git grep -l review_delta origin/main -- plugin scripts` prints nothing at `a555ff37`); PR #377, its part 1 of 3, merged 2026-10-04.
## Unknowns
- Whether to build this at all: owner decision (direction.md, option 1 against option 2). Default taken: hold.
- If L-0522 PR 2 lands first, `check_receipt` gains a delta-gate branch after the hash comparison. The dual-read then has to sit before it and the delta gate's rebuild has to use the scheme the receipt carries (L-0522 spec U3). Re-read `check_receipt` on origin/main before planning.
- Line alignment. A token-only change could shift git's line alignment only if the new line equals another line in the file. Resolved at implement: the must-allow test runs on copies of the real origin/main files.
- In-flight receipts without `receipt_scheme` still stale on a re-bump, once, as today. Accepted: widening an old receipt's meaning after the fact is rejected, as T-0026 rejected it.
- Whether git ever emits a qualifying section with a `similarity index` line and no rename. The rename test covers the rename case only.
- The next free crew patch version is set at implement time (main is at 1.1.0 on `a555ff37`).
## Size and split
- Estimate: about 190 added production lines, all under `plugin/crew/hooks/scripts/` (`review_patch.py` about 100, `review_ledger.py` about 65, `review_run.py` about 25). Under the 300-line rule.
- It holds one parser (`normalise_versions`) and one fail-closed state (the scheme dual-read). If built, land it as two tooling-only PRs so each carries one of them:
  1. `review_patch.py` only: `normalise_versions`, `receipt_sha256`, the two manifest keys. Nothing reads them yet, so no receipt changes meaning. Must-allow and must-block at the hash level, sabotage (a)-(f).
  2. `review_ledger.py` and `review_run.py`: record, dual-read in `check_receipt`, `accept` and `auto_accept`, the `bundle_problems` check. CLI tests, sabotage (g)-(i), docs.
- No child ticket folders were written: the default is not to build, and children would enter the hand-off as work.
- Harness rule: every production path here is in `HARNESS`, so each PR is tooling-only. `plugin/crew/commands/done.md` is outside `HARNESS` and `ALONGSIDE`; its one-line wording change needs its own docs PR, as L-0568 and L-0626 did.
## Touch
- plugin/crew/hooks/scripts/review_patch.py
- plugin/crew/hooks/scripts/review_ledger.py
- plugin/crew/hooks/scripts/review_run.py
- plugin/crew/tests/test_review_receipt_hash.py
- plugin/crew/tests/sabotage_review.py
- plugin/crew/commands/review.md
- plugin/crew/README.md
- docs/guides/crew/src/troubleshooting.md
- docs/guides/crew/** (the HTML, DOCX and PDF rebuilt by `docs/guides/crew/src/build.py`)
- .crew/codemap/crew.md
- .crew/codemap/verification-harness.md
- CHANGELOG.md
- plugin/crew/BUDGETS.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

Not in Touch, stated: `plugin/crew/commands/done.md` (separate docs PR, see above); `plugin/crew/CONFIG.md` (no setting); `docs/diagrams/` (no box or edge changes; a regenerated anchor is a refresh artifact).
## Acceptance checks
Commands run from the repo root. Each pytest command goes through the repo's heavy-run wrapper when the host is memory-bound.
- [ ] Must-allow: after a CLEAN round, a pure re-bump across plugin.json, marketplace.json, PLUGINS.md and the CHANGELOG entry heading, with no merge, leaves `review_ledger.py --check-receipt` exit 0. The fixture uses copies of the origin/main files. `python3 -m pytest plugin/crew/tests/test_review_receipt_hash.py -q -k test_pure_rebump_keeps_the_receipt`
- [ ] Must-allow: a FINDINGS round followed by a pure re-bump can still be accepted with `--accept --by`. `-k test_pure_rebump_then_accept_findings_succeeds`
- [ ] Must-block, one test each in `test_review_receipt_hash.py`. Each of these stales the receipt:
  - a CHANGELOG prose edit
  - a CHANGELOG heading whose text after the version changed
  - a new key in plugin.json
  - a code change
  - a version change on the same line as another edit
  - a version line plus an adjacent line changed in one hunk
  - a non-semver version value
  - a `"version"` line re-bumped in a JSON file outside the set
  - a renamed plugin.json
  - a mode change on plugin.json
  - a binary edit to a file outside the set
  - a NUL-bearing (binary) plugin.json
  - a re-bump followed by rewriting a `-` line
  - a catch-up merge followed by a re-bump (stale here by design; the test pins the exclusion)
- [ ] The reviewer's input is unchanged. `bundle_sha256` still equals sha256 of the patch, and the patch bytes are identical with or without normalisation. `-k test_bundle_patch_and_hash_are_unchanged`
- [ ] Dual-read, one test each:
  - a receipt with no `receipt_scheme` verifies an unchanged tree and stales on a re-bump;
  - an unknown `receipt_scheme` reads stale, naming the scheme;
  - a `/2` receipt with a missing or non-string `receipt_sha256` reads stale;
  - `auto_accept` on a `/2` round compares `receipt_sha256` and refuses a prose edit.
- [ ] `review_run.py` records `receipt_scheme`/`receipt_sha256` in the round and the CLEAN receipt. A manifest whose `receipt_sha256` does not match its parts makes the round INCOMPLETE. `-k test_manifest_receipt_hash_not_matching_the_parts_is_incomplete`
- [ ] Sabotage, each mutation in `sabotage_review.py` turning its named test red through `python3 plugin/crew/tests/sabotage.py`:
  - (a) normalise every `+` line of a bookkeeping section
  - (b) widen the token to `[^"]+`
  - (c) drop the full-line anchor
  - (d) widen the path set to any `.json`
  - (e) blank the blob id in every section
  - (f) drop the `Binary files` skip
  - (g) read a no-scheme receipt as `/2`
  - (h) fall back to raw on an unknown scheme
  - (i) drop the receipt-hash check from `bundle_problems`

  The existing `the receipt check ignores the bundle hash` mutation (sabotage.py:3036) still goes red, and `test_every_receipt_hash_sabotage_anchor_is_present_exactly_once` passes.
- [ ] Existing suites pass unchanged: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_*.py -q` and `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_train.py -q`.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` on each PR's branch.
- [ ] Docs: README.md:772, review.md:510 and troubleshooting.md:163 state the version-only exception and that a catch-up merge is not covered; the guide outputs are rebuilt (`python3 docs/guides/crew/src/build.py`); the two code maps describe the second hash. Crew is bumped to the next free patch with a CHANGELOG entry, and `python3 scripts/check-marketplace.py` passes after the commit.
## Dependencies
Must land or be decided first:
- Owner decision on direction.md's options (open). Without it this ticket is not built.
- L-0522 (in-progress; PR #377, part 1 of 3, merged 2026-10-04; the delta gate is part 2, not on main at `a555ff37`): supersedes this ticket for the catch-up case and edits the same functions. Build T-0033 only after L-0522 PR 2 has merged or been cut, never beside it.
- T-0100 (INDEX: approved; its build is on origin/main as crew 1.0.322, PR #371): changed how the bundle is rebuilt after a merge. Already accounted for above.
- T-0026 (merged): the dual-read precedent this design copies.
- L-0510 (done): added `auto_accept`, the third comparison site.
- T-0087 (merged): the tooling-PRs-land-alone rule that shapes the split.
- T-0006, T-0008 (merged): where the problem was first measured.

Related, same files, no order forced: T-0068 (spec; crew's own bookkeeping writes stale a receipt), L-0620 (direction; fast-path hole), L-0596 (direction; review_ledger hardening), T-0109 (direction; `--reject` on an accepted receipt).

Blocks: L-0584 (direction). Its second option, "a sanctioned post-receipt bump that does not stale the receipt", is this ticket or L-0522; L-0584 cannot be settled until one of them is chosen.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05, **as a held fallback contract**: the default taken (direction.md, option 1) is not to build
this and to close it as superseded once L-0522 part 2 is on main. A session that picks it up checks L-0522 first.
Plan: the published plan.md is stale (2026-09-26, `1e0706ac`); to be re-written by the implementing session if built.
