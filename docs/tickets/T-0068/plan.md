# T-0068 plan            spec: .work/tickets/T-0068/spec.md

The owner approves this plan (risk: high, because it changes a guard). Work in a fresh worktree from origin/main. Anchors are origin/main `502cb137` (crew 1.0.42). Re-grep each quoted string before its step. If a line is gone, stop and report it; do not guess a replacement. Every step is guard-grade: write the must-block and must-allow tests first and watch them fail for the stated reason, then fix, then add sabotage mutations that must go red. The fixtures build throwaway repos whose `.gitignore` does NOT ignore `.crew/`, the TSS shape. This repo's own `.gitignore` hides the bug. No second opinion is needed: the design is the existing `.work/` and refresh-artifact exclusion pattern applied to one more list. Steps 2-5 each depend on Step 1 and touch disjoint files. Step 6 then Step 7 run last.

### Step 1: one list, and a test that every crew-written `.crew/` path is classified
Files: plugin/crew/hooks/scripts/crew_common.py, plugin/crew/tests/test_crew_bookkeeping.py
Test: python3 -m pytest plugin/crew/tests/test_crew_bookkeeping.py -q -p no:cacheprovider
Risk: high. A path missing from the list keeps the deadlock. A content path wrongly on it hides a real change from review and the audit. The two-sided test guards both.
- [ ] Write `test_crew_bookkeeping.py` first.
  - `test_every_crew_state_path_is_classified`: walk `plugin/crew/hooks/scripts/*.{py,sh,ps1}`, excluding `_test/`. Collect every `.crew/<first segment>` from string literals (Python via `ast`, and shell and PowerShell via the regex `\.crew/([A-Za-z0-9._<>*${}-]+)`), plus `os.path.join(<x>, ".crew", "<name>", ...)` calls (ast). Normalise a trailing variable part (`${KEY}`, `<session>`, `{…}`) to `*`. Assert each is matched by exactly one of `crew_common.CREW_BOOKKEEPING_PATHS` or `crew_common.CREW_CONTENT_PATHS`, and print every unclassified name. Also assert the expected names are found, so the walk is not vacuous: `.scope-base`, `.verify-gate.record.json`, `metrics.jsonl`, `config.json`.
  - `test_is_crew_bookkeeping_matches_whole_segments_at_the_root`, parametrised: `.crew/.scope-base` True, `.crew/.verify-gate.timings.json` True, `.crew/.autoclear-sent-abc` True, `.crew/event-claims/x` True, `sub/.crew/.scope-base` False, `.crew/.scope-baseX` False, `.crew/verify.json` False, `.crew/codemap/INDEX.md` False, `./.crew/.scope-base` False, `.crew\\.scope-base` False, `` False.
  - `test_git_excludes_are_root_anchored`: `crew_common.bookkeeping_excludes()` returns only `:(exclude,top,glob)` pathspecs, one per list entry.
  - Run it. It must fail with AttributeError (no list yet).
- [ ] In `crew_common.py`, add `CREW_BOOKKEEPING_PATHS`, a tuple of root-relative globs.
  - Single-file entries: `.crew/.scope-base`, `.crew/.verify-verified-at`, `.crew/.verify-gate.*`, `.crew/guard.log`, `.crew/metrics.md`, `.crew/metrics.jsonl`, `.crew/.autoclear.log`, `.crew/.autoclear-sent-*`, `.crew/.handoff-requested*`, `.crew/incident.json`, `.crew/incident-skips.log`, `.crew/.cloud-guard-unpinned-noted`, `.crew/.deploy-in-flight`, `.crew/*.lock`.
  - Directory entries: `.crew/event-claims/**`, `.crew/transcripts/**`, `.crew/handoffs/**`, `.crew/incidents/**`, `.crew/backups/**`, `.crew/tfplan/**`.
  - Each entry carries a comment naming its writer (`path:line`).
  - Add `CREW_CONTENT_PATHS` for what crew reads as config or maps, which must stay reviewable: `.crew/config.json`, `.crew/crew.json`, `.crew/verify.json`, `.crew/endpoints.json`, `.crew/codemap/**`, `.crew/archive/**`, `.crew/state.json`, `.crew/.approved-*`.
  - Add `is_crew_bookkeeping(rel)`. It refuses anything not already normalised (the `is_refresh_artifact` rule, `plugin/crew/hooks/scripts/crew_refresh_check.py:370-390`), then does a segment-wise `fnmatch` from the root, where `**` spans segments.
  - Add `bookkeeping_excludes()`, which returns the pathspec list.
  - Resolve every unclassified name the test prints by adding it to one of the two lists, with its writer. Do not widen a glob to make the test pass.
- [ ] Run the Test command. It must be all green.
- [ ] Sabotage, in `plugin/crew/tests/sabotage_refresh.py` with target `crew_common.py`: "the gate records are not bookkeeping" deletes the `.crew/.verify-gate.*` entry (red on `tests/test_crew_bookkeeping.py::test_every_crew_state_path_is_classified`). "bookkeeping matches below the root" makes the matcher a suffix test (red on `test_is_crew_bookkeeping_matches_whole_segments_at_the_root`).

### Step 2: the review bundle and its receipt leave bookkeeping out
Files: plugin/crew/hooks/scripts/review_patch.py, plugin/crew/tests/test_review_patch.py, plugin/crew/tests/test_review_ledger.py, plugin/crew/tests/sabotage_review.py
Test: python3 -m pytest plugin/crew/tests/test_review_patch.py plugin/crew/tests/test_review_ledger.py -q -p no:cacheprovider
Risk: high. An exclusion that is too wide hides a real change from the reviewer. The must-block tests pin the neighbours.
- [ ] Must-allow: `test_review_patch.py::test_bookkeeping_never_enters_the_bundle`. Use a fixture repo with no `.crew` ignore and one committed source change. Build the bundle, then write every bookkeeping file (one per list entry, using a concrete name for each glob) untracked and build again. Assert the same `bundle_sha256`, and that `manifest["excluded"]` contains `.work/` and every list entry. It must fail first: today the hash changes.
- [ ] Must-block: `test_a_crew_content_path_still_enters_the_bundle`, parametrised over `.crew/verify.json` (modified), `.crew/codemap/x.md` (new) and `sub/.crew/.scope-base` (new). Each changes the hash and appears in the patch.
- [ ] Receipt: `test_review_ledger.py::test_bookkeeping_written_after_acceptance_keeps_the_receipt`. Record a receipt with the existing fixture helpers. Then write `.crew/.verify-gate.record.json` and `.crew/.verify-gate.timings.json`, append a line to `.crew/metrics.md` and `.crew/metrics.jsonl`, and rewrite `.crew/.scope-base`. `check_receipt` must pass. This is the TSS-510 repro (`1028da4e` -> `edee5c83`), and it must fail first. The neighbour `test_a_source_edit_after_acceptance_still_stales_the_receipt` must stale.
- [ ] Fix: re-grep `EXCLUDED = (".work/",)` (`plugin/crew/hooks/scripts/review_patch.py:96`). Set `EXCLUDED = (".work/",) + crew_common.CREW_BOOKKEEPING_PATHS` and `_EXCLUDE_SPEC = [":(exclude).work"] + crew_common.bookkeeping_excludes()`. Extend the docstring at `:49-60`: bookkeeping is excluded for the same reason as `.work/`, and never through `git add` (the existing note applies unchanged). If T-0046 has landed first, merge with its graphify-out handling rather than replacing it.
- [ ] Sabotage, in `sabotage_review.py` with target `review_patch.py`: "bookkeeping enters the bundle" puts back `_EXCLUDE_SPEC = [":(exclude).work"]` (red on `tests/test_review_patch.py::test_bookkeeping_never_enters_the_bundle`). "the bundle exclusion is not root-anchored" drops `top` from the magic (red on `test_a_crew_content_path_still_enters_the_bundle`, via its nested case).
- [ ] Run the Test command. It must be all green.

### Step 3: the completion audit never judges bookkeeping
Files: plugin/crew/hooks/scripts/completion_audit.py, plugin/crew/tests/test_completion_audit.py, plugin/crew/tests/sabotage_scope.py
Test: python3 -m pytest plugin/crew/tests/test_completion_audit.py plugin/crew/tests/test_completion_audit_refresh_artifacts.py -q -p no:cacheprovider
Risk: high. This is the check `/crew:done` trusts for "zero unapproved scope changes", so a real out-of-Touch path must still fail.
- [ ] Must-allow: `test_bookkeeping_is_never_out_of_touch`. Approve a ticket with Touch `src/**`, change `src/a.py`, then write every bookkeeping file untracked and also commit `.crew/metrics.jsonl`. `audit` returns `(True, [])`. It must fail first, listing `.crew/.scope-base`.
- [ ] Must-block: `test_an_out_of_touch_file_beside_bookkeeping_still_fails` (the same, plus `lib/b.py`). It fails, names `lib/b.py`, and names no bookkeeping path. `test_unapproved_touch_still_fails_but_lists_no_bookkeeping`: with no approval the audit fails, and the changed list omits the bookkeeping paths.
- [ ] Fix: re-grep `_ONLY = ["--", ".", ":(exclude).work"]` (`plugin/crew/hooks/scripts/completion_audit.py:76`). Build it as `["--", ".", ":(exclude).work"] + crew_common.bookkeeping_excludes()`, importing `crew_common` at the top, since it is stdlib-only. Rewrite the docstring's "What it cannot see" (`:28-30`): bookkeeping is excluded by name whatever `.gitignore` says, and ignored files remain invisible.
- [ ] Sabotage, in `sabotage_scope.py` with target `AUDIT`: "the audit judges bookkeeping" puts back the old `_ONLY` (red on `tests/test_completion_audit.py::test_bookkeeping_is_never_out_of_touch`). "the audit drops every .crew path" swaps the addition for `":(exclude).crew"` (red on `test_an_out_of_touch_file_beside_bookkeeping_still_fails`, extended with a `.crew/verify.json` change outside Touch that must be named).
- [ ] Run the Test command. It must be all green.

### Step 4: the scope guard allows bookkeeping and still refuses `.crew/.scope-base`
Files: plugin/crew/hooks/scripts/scope_guard.py, plugin/crew/tests/test_scope_guard.py, plugin/crew/tests/sabotage_scope.py
Test: python3 -m pytest plugin/crew/tests/test_scope_guard.py plugin/crew/tests/test_scope_guard_refresh_artifacts.py -q -p no:cacheprovider
Risk: high. `.crew/.scope-base` is what the audit trusts. A guard that let it be edited would let a session move its own base.
- [ ] Must-allow: `test_an_edit_to_bookkeeping_is_allowed_outside_touch`, parametrised over `.crew/metrics.md` and `.crew/metrics.jsonl`, under `block`, with an approved ticket whose Touch is `src/**`, and again with no approval. It is allowed with reason "crew bookkeeping". It must fail first under `block`.
- [ ] Must-block: `test_scope_base_stays_refused_though_it_is_bookkeeping`, parametrised over Write and Edit and over `report`, `block` and `auto`. It is refused, with the existing rule-2 reason. `test_a_bookkeeping_lookalike_is_still_judged`: `.crew/metrics.md.bak`, `.crew/metricsX.md` and `docs/.crew/guard.log` stay outside Touch.
- [ ] Fix, in `classify` (`plugin/crew/hooks/scripts/scope_guard.py:158-185`): after the ticket's-own-files check, `if all(crew_common.is_crew_bookkeeping(r) for r in checks): return True, "crew bookkeeping"`. Both the real and the named path must qualify, as for refresh artifacts. `protected` (`:200-214`) runs before `classify` (`:298`), so rule 2 is untouched. Add rule 5a to the docstring (`:8-40`).
- [ ] Sabotage, target `GUARD`: "bookkeeping is judged against Touch" removes the new branch (red on `tests/test_scope_guard.py::test_an_edit_to_bookkeeping_is_allowed_outside_touch[...]`). "the scope base is writable as bookkeeping" moves the bookkeeping check ahead of `protected` in `main` (red on `test_scope_base_stays_refused_though_it_is_bookkeeping[...]`). "one side of a link decides" swaps `all` for `any` (red on a symlink case added to the must-block test).
- [ ] Run the Test command. It must be all green.

### Step 5: the verify gate drops bookkeeping and maps refresh artifacts, in both flavours
Files: plugin/crew/hooks/scripts/crew_refresh_check.py, plugin/crew/hooks/scripts/verify-gate.sh, plugin/crew/hooks/scripts/verify-gate.ps1, plugin/crew/tests/test_refresh_check.py, plugin/crew/tests/test_verify_gate_bookkeeping.py, plugin/crew/tests/sabotage_refresh.py
Test: python3 -m pytest plugin/crew/tests/test_refresh_check.py plugin/crew/tests/test_verify_gate_bookkeeping.py plugin/crew/tests/test_verify_gate_baseline.py plugin/crew/tests/test_gates_powershell.py -q -p no:cacheprovider
Risk: high. The two flavours are a matched pair, and a fix in one alone is the Windows landmine (CLAUDE.md). An over-wide mapping would silence `unmapped: fail` for real code.
- [ ] `test_refresh_check.py::test_classify_names_each_kind`: `crew_refresh_check.py --root <fixture> --classify` reads newline-separated paths on stdin and prints `bookkeeping\t.crew/.scope-base`, `artifact\t.crew/codemap/crew.md`, `artifact\tdocs/diagrams/x.mmd` and `other\tsrc/a.py`, in input order. A path containing a tab or a newline is `other`, never dropped. `test_ticket_is_still_required_without_classify` passes. Implement `--classify` in `main` (`plugin/crew/hooks/scripts/crew_refresh_check.py:676-681`), making `--ticket` required unless `--classify` is given. It classifies with `crew_common.is_crew_bookkeeping` and `is_refresh_artifact(p, refresh_artifact_paths(root))`, and reads nothing else.
- [ ] Write `test_verify_gate_bookkeeping.py` first, modelled on `test_verify_gate_baseline.py`'s fixture. Each case is parametrised over `sh` and `ps1`, and `ps1` skips by name when pwsh does not resolve (`crew_fixtures`). The fixture's `.crew/verify.json` has one rule, `src/**` -> `true`, `"unmapped": "fail"`, and no `.crew` ignore.
  - Must-allow: `test_untracked_bookkeeping_is_not_unmapped`, where the only changes are the gate's own record files and `.crew/.scope-base`. The gate exits 0, and stderr has no `UNMAPPED CHANGES`.
  - `test_a_refresh_artifact_with_no_rule_is_not_unmapped`: `.crew/codemap/x.md` changed, exit 0.
  - `test_a_refresh_artifact_a_rule_names_still_runs_it`: a second rule `.crew/codemap/**` -> `exit 1`. The gate fails naming that command.
  - Must-block: `test_an_ordinary_unmapped_file_still_fails`, with `lib/x.py` changed beside bookkeeping. The gate exits 2, and `UNMAPPED CHANGES` names `lib/x.py` and no bookkeeping path.
  - All must fail first on the allow cases.
- [ ] Fix `verify-gate.sh`. In the python matcher, before `for f in changed:` (`plugin/crew/hooks/scripts/verify-gate.sh:1013`), import `crew_common` and `crew_refresh_check` (the scripts dir is already on `sys.path`, `:762`). Drop bookkeeping from `changed`, and at `if not hit: unmatched.append(f)` (`:1066`) skip refresh artifacts. Re-grep both lines first.
- [ ] Fix `verify-gate.ps1`. Pipe `$changed` once to `crew_refresh_check.py --classify` through the interpreter it already resolves for `scope_report.py` (`plugin/crew/hooks/scripts/verify-gate.ps1:811`). Drop the `bookkeeping` rows from `$changed` before matching, and never add an `artifact` row to `$unmapped` (`:914`). If the classifier cannot run, the gate says so and treats every path as `other`, which fails closed toward unmapped, never toward pass.
- [ ] Sabotage, in `sabotage_refresh.py`:
  - "the sh gate reports bookkeeping as unmapped" removes the drop (red on `tests/test_verify_gate_bookkeeping.py::test_untracked_bookkeeping_is_not_unmapped[sh]`).
  - "the sh gate maps every unmatched path" makes the artifact skip unconditional (red on `test_an_ordinary_unmapped_file_still_fails[sh]`).
  - The same two for `.ps1`, red on the `[ps1]` ids. If pwsh is absent the ps1 pair cannot go red, so report it NOT run rather than green.
  - "classify calls everything bookkeeping" (red on `test_classify_names_each_kind`).
- [ ] Run the Test command. It must be all green, and `-rs` must show which ps1 cases were skipped, if any.

### Step 6: every document that describes these checks
Files: plugin/crew/README.md, plugin/crew/CONFIG.md, plugin/crew/commands/done.md, plugin/crew/commands/review.md, plugin/crew/commands/verify.md, plugin/crew/commands/implement.md, plugin/PLUGINS.md, docs/guides/crew/**, TODO.md
Test: (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py); python3 scripts/check-marketplace.py; python3 docs/guides/crew/src/build.py
Risk: med. A doc left saying "nothing else is exempt" sends the next reader to put bookkeeping in Touch, which is the workaround this ticket removes.
- [ ] `plugin/crew/README.md:766`: replace "Nothing else is exempt: not the rest of `.crew/`" with the bookkeeping allowance. Name the list's home (`crew_common.CREW_BOOKKEEPING_PATHS`) and state that `.crew/.scope-base` is still refused to Write/Edit. At `:725` (the metrics line), add that bookkeeping never stales a receipt.
- [ ] `plugin/crew/CONFIG.md:2104`: the gate record is machine-local and "gitignored by the shipped template". Where a repo does not ignore it, it is excluded by name from the review bundle, the completion audit and the gate.
- [ ] `plugin/crew/commands/done.md`: check 1 says bookkeeping written after acceptance does not stale the receipt. Check 3 says the audit never lists bookkeeping, so a listed `.crew/` path is a real finding. `commands/review.md` step 6 says the metrics append is bookkeeping for the bundle, while still read by `/crew:status`. `commands/verify.md:95-102` says bookkeeping is never unmapped and refresh artifacts are mapped. `commands/implement.md:98` adds bookkeeping beside the refresh-artifact allowance.
- [ ] `docs/guides/crew/src/daily-workflow-scope.md` (the completion-audit section, `:83` onward) and `docs/guides/crew/src/troubleshooting.md` (`:144` onward): the same facts. Add a troubleshooting row: "an older crew's receipt reads stale after upgrade", with the one re-review. Rebuild with `docs/guides/crew/src/build.py` and commit the HTML, DOCX and PDF it writes. Name the renderer it used, which the build prints.
- [ ] `plugin/PLUGINS.md`: the crew row's version, in Step 7.
- [ ] `TODO.md`: file the `verify.knownFailures` follow-up (TSS F496) with the owner's answer to open question 1, unless the owner filed it as a ticket.
- [ ] Grep `plugin/crew` and `docs/guides/crew/src` for `Nothing else is exempt`, `excludes only`, `.work/ is excluded` and `never tracked`, and fix or name each remaining hit.
- [ ] Run the Test command. It must pass.

### Step 7: sabotage run, verify rules, refresh, review, land
Files: .crew/verify.json, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, .crew/codemap/**, docs/diagrams/**
Test: python3 plugin/crew/tests/sabotage.py; python3 -m pytest plugin/crew/tests -q -p no:cacheprovider; python3 scripts/check-marketplace.py; python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0068
Risk: med. Content without a version bump is never delivered, and a refresh after review stales the receipt.
- [ ] Run `python3 plugin/crew/tests/sabotage.py`. Every mutation from Steps 1-5 must be RED on its named test, the non-RED set must equal origin/main's by label, and no `.bak` may be left. Report the wall time and any failure verbatim.
- [ ] `.crew/verify.json`:
  - Add a rule for `plugin/crew/hooks/scripts/review_patch.py`, `plugin/crew/hooks/scripts/review_ledger.py`, `plugin/crew/tests/test_review_patch.py` and `plugin/crew/tests/test_review_ledger.py`, running those two tests.
  - Add `test_crew_bookkeeping.py` to rule 8's paths and run.
  - Add `test_verify_gate_bookkeeping.py` to rule 4's run, and `test_refresh_check.py`'s classify case to rule 25 (already run there).
  - Time each changed rule three times on a quiet host and write `seconds` and `why` with the date, the pass count and the load.
- [ ] Under `## [Unreleased]` in `CHANGELOG.md`, add "`crew` <version>: crew's own bookkeeping never trips the completion audit or stales a review receipt (T-0068)". Name the list, the four consumers, the gate's refresh-artifact mapping, and the one-time re-review for receipts accepted over a tree that held a non-ignored bookkeeping file.
- [ ] Run `crew_refresh_check.py --root . --ticket T-0068` and each `refresh with` command, committing each, until it says `fresh` (`plugin/crew/commands/implement.md:92-104`). `.crew/codemap/crew.md` and `.crew/codemap/verification-harness.md` must state the exclusions with `path:line` anchors. `docs/diagrams/process-crew-lifecycle.mmd` must show that bookkeeping does not feed the receipt, if it draws the bundle. Build the graph with `graphify update .` only.
- [ ] Commit, then run `/crew:review T-0068` and report its BLOCK and FIX lines verbatim. Accepting is the owner's.
- [ ] On the land branch, set crew one patch above `git show origin/main:plugin/crew/.claude-plugin/plugin.json`'s version in plugin.json, marketplace.json (the crew entry), `plugin/PLUGINS.md` and the CHANGELOG headline. Run the gate, and merge with `gh pr merge --merge`.
- [ ] Before closing, reproduce once in a TSS-shaped scratch repo (no `.crew` ignore). Run `verify-gate.sh --all`, append metrics, then `review_ledger.py --check-receipt` and `completion_audit.py --check`. Both must pass with no hand deletion. Report the commands and output verbatim. TSS itself is not touched.
