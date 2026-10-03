# T-0068 crew's own bookkeeping writes never trip the completion audit or stale a review receipt (/crew:done deadlock)          status: spec   risk: high
## Intent
`/crew:done` can pass without hand workarounds in a repository whose `.gitignore` does not ignore crew's own bookkeeping. There is one list of the paths crew's scripts write for themselves under `.crew/` (`CREW_BOOKKEEPING_PATHS`). The review bundle and its receipt check, the completion audit, the scope guard's Touch judgement and the verify gate's changed-path list all leave those paths out, the way `.work/` and the refresh artifacts already are. The verify gate also treats the refresh-artifact paths as mapped rather than as unmapped. This is a guard change. Every exclusion gets a must-block test (a real out-of-Touch or unmapped path still fails) and a must-allow test (bookkeeping never does), and each has a sabotage entry that goes red.
## Exclusions
- No `verify.knownFailures` allowance. The direction's "More evidence" proposes one for TSS F496. It is a new config key with expiry semantics and its own must-block cases, so it goes to a separate ticket (open question 1).
- No `.gitignore` or `.git/info/exclude` writes from `/crew:init` or `/crew:migrate`, and no change to `check_crew_ignore_policy`. The exclusions make the ignore state irrelevant to correctness. The shipped template already ignores `.crew/*` (open question 2).
- `.crew/.scope-base` stays refused to Write/Edit in every mode but `off` (`scope_guard` rule 2). Being bookkeeping for the audit and the bundle does not make it writable.
- Nothing crew reads as configuration or as a map becomes bookkeeping. That covers `.crew/config.json`, `.crew/crew.json`, `.crew/verify.json`, `.crew/endpoints.json`, `.crew/codemap/` and anything under `<git-common-dir>/crew/`.
- No reordering of the metrics appends (`/crew:review` step 6, `/crew:done` step 2). Once the bundle excludes them, their order cannot stale a receipt (Unknowns).
- `scope_report.py`'s report-only `_BOOKKEEPING` prefix test is not changed.
- No change to the review ledger format, the receipt format or the approval digest.
## Evidence
All anchors are origin/main `502cb137` (crew 1.0.42) unless marked otherwise.
- The review bundle excludes only `.work/`. `EXCLUDED = (".work/",)` and `_EXCLUDE_SPEC = [":(exclude).work"]` are at `plugin/crew/hooks/scripts/review_patch.py:96-97`, and the docstring reasoning is at `:49-60`. `compute` lists untracked non-ignored files into the bundle (`:283-287`), and the manifest records `excluded` (`:345`). `review_ledger.check_receipt` (`plugin/crew/hooks/scripts/review_ledger.py:366`) rebuilds through `review_patch.compute` (`:360`) and compares `bundle_sha256` (`:391`). So any untracked, non-ignored file written after acceptance stales the receipt.
- The completion audit excludes only `.work/`: `_ONLY = ["--", ".", ":(exclude).work"]` (`plugin/crew/hooks/scripts/completion_audit.py:76`). `changed_paths` (`:153-161`) adds `ls-files --others --exclude-standard`. The docstring says it cannot see ignored files, "`.crew/*` among them" (`:28-30`). That is true only where `.gitignore` ignores `.crew/*`. The only exemption is `_outside_refresh_artifacts` (`:177-187`), which is approval-gated. `audit` fails every other path outside Touch (`:190-225`).
- The scope guard: rule 2 refuses `.crew/.scope-base` (`plugin/crew/hooks/scripts/scope_guard.py:12-16`, `SCOPE_BASE` `:99`, `protected` `:200-214`). `classify` (`:158-185`) allows only the ticket's own files, the refresh artifacts and Touch. An Edit that appends `.crew/metrics.md` (`plugin/crew/commands/review.md:530`, `:539`) is therefore judged against Touch.
- Crew's bookkeeping writers, each a repo-relative `.crew/` path:
  - `.crew/.scope-base`, `plugin/crew/hooks/scripts/scope_base.py:80`.
  - `.crew/.verify-gate.record.json` and `.crew/.verify-gate.timings.json`, `plugin/crew/hooks/scripts/verify_record.py:54-55`.
  - `.crew/.verify-verified-at`, `plugin/crew/hooks/scripts/verify-gate.sh:122`. `.crew/.verify-gate.fingerprint`, `:374`. `.crew/.verify-gate.lock`, `:389`.
  - `.crew/guard.log`, `plugin/crew/hooks/scripts/scope_guard.py:98`. `.crew/metrics.jsonl`, `plugin/crew/hooks/scripts/crew_metrics.py:139`. `.crew/metrics.md`, `plugin/crew/commands/review.md:530`.
  - `.crew/.autoclear.log` and `.crew/.autoclear-sent-*`, `plugin/crew/hooks/scripts/auto-clear.sh:81`, `:111`. `.crew/.handoff-requested-*`, `plugin/crew/hooks/scripts/crew_autocycle.py:65`.
  - `.crew/incident.json` and `.crew/incident-skips.log`, `plugin/crew/hooks/scripts/crew_incident.py:16-17`, `:34`. `.crew/incidents/`, `:36`.
  - `.crew/.cloud-guard-unpinned-noted`, `plugin/crew/hooks/scripts/cloud_guard.py:3225`. `.crew/event-claims/`, `plugin/crew/hooks/scripts/event_claim.py:106`. `.crew/transcripts/`, `plugin/crew/hooks/scripts/handoff-write.sh:62`. `.crew/handoffs/`, `plugin/crew/hooks/scripts/crew_state.py:774`. `.crew/backups/`, `plugin/crew/hooks/scripts/crew_migrate.py:140`.
  - This list came from grepping `.crew/` literals and `os.path.join(..., ".crew", ...)` across `plugin/crew/hooks/scripts/`. It is an input to Step 1's test, which re-derives it, and not a claim of completeness.
- `review_run.py` writes nothing under `.crew/`: `grep -n "\.crew\|metrics" plugin/crew/hooks/scripts/review_run.py` is empty on origin/main. The direction's problem 3 ("`review_run.py` appends `.crew/metrics.md`") does not reproduce on origin/main. The appends are the prose steps `plugin/crew/commands/review.md:530` and `:539` and `plugin/crew/commands/done.md:66-70` (`crew_metrics.py record`).
- The verify gate: the changed list takes in untracked non-ignored files (`plugin/crew/hooks/scripts/verify-gate.sh:258-264`, `plugin/crew/hooks/scripts/verify-gate.ps1:520-523`). A changed path that no rule's `paths` match is appended to `unmatched` (`verify-gate.sh:1013-1066`, `:1356`), and under `"unmapped": "fail"` it fails the gate (`:1748-1752`). The PowerShell twin builds `$unmapped` (`verify-gate.ps1:914`). No refresh-artifact or bookkeeping exemption exists in either flavour.
- One definition for the refresh artifacts already exists: `REFRESH_ARTIFACT_PATHS` (`plugin/crew/hooks/scripts/crew_refresh_check.py:168-173`), `refresh_artifact_paths` (`:339-367`) and `is_refresh_artifact` (`:370-390`). Its CLI (`:676-681`) requires `--ticket`. `crew_refresh_check` imports `completion_audit` (`:134`), so `completion_audit` imports it lazily (`completion_audit.py:185`).
- `crew_common.py` is 80 lines, stdlib-only, and imported by `crew_ticket` (`plugin/crew/hooks/scripts/crew_ticket.py:133`). `crew_ticket.py:359` records that the PreToolUse guard avoids importing `crew_state` on every Write.
- In this repo `.gitignore` ignores `.crew/*` and un-ignores a named list (`.gitignore:292`, `:301`, `:308`, `:330`). The shipped template does the same (`plugin/crew/skills/crew-setup/SKILL.md:360-392`), so this repo cannot reproduce the deadlock. Measured on 2026-09-27 in TSS (`/repos/anew/TheSelectSource`, HEAD `b853583a`): `git check-ignore -v` on `.crew/.scope-base`, `.crew/metrics.md`, `.crew/.verify-gate.record.json`, `.crew/.verify-verified-at`, `.crew/metrics.jsonl` and `.crew/guard.log` exits 1 (none ignored), and `.crew/STATUS.md` and `.crew/codemap/*` are tracked there.
- The docs that state the current behaviour: `plugin/crew/README.md:766` ("Nothing else is exempt: not the rest of `.crew/`"), `plugin/crew/CONFIG.md:2104` (the gate record is "machine-local, gitignored, never tracked", which is false in TSS), `plugin/crew/commands/done.md:11-46` (checks 1-3) and `plugin/crew/commands/verify.md:95-102`.
- The direction's receipt evidence, from TSS [a8ac98] and not re-run here: `verify-gate.sh --all` wrote the two `.verify-gate.*.json` files untracked, and the bundle went `1028da4e` -> `edee5c83`. Deleting both restored it.
- Verify rules: rule 25 (`crew_refresh_check.py`, `scope_guard.py`, `completion_audit.py`, `scope_base.py` and their tests), rule 4 (`verify-gate.sh`/`.ps1`, `test_verify_gate*.py`, `test_gates_powershell.py`) and rule 8 (`crew_common.py`) in `.crew/verify.json`. No rule names `review_patch.py` or `review_ledger.py` except the catch-all rule 0 (`check-marketplace.py`).
- Existing tests: `plugin/crew/tests/test_review_patch.py`, `test_review_ledger.py`, `test_completion_audit.py`, `test_completion_audit_refresh_artifacts.py`, `test_scope_guard.py`, `test_refresh_check.py`. Sabotage lists: `sabotage_scope.py` (targets `GUARD` and `AUDIT`), `sabotage_review.py` and `sabotage_refresh.py`, all registered in `plugin/crew/tests/sabotage.py:69-75`.
## Unknowns
- Receipts accepted before the upgrade: a receipt whose bundle held a non-ignored bookkeeping path reads stale once the rebuilt bundle drops that path, and costs one re-review. Accepted as risk. The CHANGELOG entry says so.
- T-0046 also edits `review_patch.py` (graphify-out listed by hash). Whichever lands second rebases onto the other's `EXCLUDED` handling. Step 2 re-greps `EXCLUDED` before editing.
- Git pathspec magic: the exclusions use `:(exclude,top,glob)<pattern>`, which is anchored at the repository root, so a nested `sub/.crew/.scope-base` is not excluded. Step 2 and Step 3 each prove this with a test on this host's git. Older gits are not tested (accepted as risk).
- PowerShell flavour: `pwsh` is installed here, so `test_gates_powershell.py`'s pattern runs the `.ps1` gate. Native Windows is not run, and the report says so.
- Metrics ordering: with the exclusion, an append after acceptance cannot stale a receipt. Step 2 proves this (must-allow), so the direction's reorder is not done.
- Reviewer independence: Codex is at its usage limit until 2026-10-01, so the review may be same-family (crew:reviewer). Accepted as risk, and announced when the review runs.
## Touch
- `plugin/crew/hooks/scripts/crew_common.py`
- `plugin/crew/hooks/scripts/review_patch.py`
- `plugin/crew/hooks/scripts/completion_audit.py`
- `plugin/crew/hooks/scripts/scope_guard.py`
- `plugin/crew/hooks/scripts/crew_refresh_check.py`
- `plugin/crew/hooks/scripts/verify-gate.sh`
- `plugin/crew/hooks/scripts/verify-gate.ps1`
- `plugin/crew/tests/test_crew_bookkeeping.py` - new
- `plugin/crew/tests/test_review_patch.py`
- `plugin/crew/tests/test_review_ledger.py`
- `plugin/crew/tests/test_completion_audit.py`
- `plugin/crew/tests/test_scope_guard.py`
- `plugin/crew/tests/test_refresh_check.py`
- `plugin/crew/tests/test_verify_gate_bookkeeping.py` - new
- `plugin/crew/tests/sabotage_scope.py`
- `plugin/crew/tests/sabotage_review.py`
- `plugin/crew/tests/sabotage_refresh.py`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/commands/done.md`
- `plugin/crew/commands/review.md`
- `plugin/crew/commands/verify.md`
- `plugin/crew/commands/implement.md`
- `plugin/PLUGINS.md`
- `docs/guides/crew/**` - src/*.md plus the rebuilt HTML, DOCX and PDF
- `.crew/codemap/**`
- `docs/diagrams/**`
- `.crew/verify.json`
- `CHANGELOG.md`
- `TODO.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
## Acceptance checks
- [ ] `test_crew_bookkeeping.py::test_every_crew_state_path_is_classified` passes. Every `.crew/<name>` a crew hook script names (string literal or `os.path.join(..., ".crew", ...)`) is in `CREW_BOOKKEEPING_PATHS` or in the declared `CREW_CONTENT_PATHS` (config, maps, receipts), never both and never neither. `test_is_crew_bookkeeping_matches_whole_segments_at_the_root` passes: `.crew/.scope-base` yes, `sub/.crew/.scope-base` no, `.crew/.scope-baseX` no, `.crew/verify.json` no. (rule 8)
- [ ] Bundle, must-allow: `test_review_patch.py::test_bookkeeping_never_enters_the_bundle`. In a repo that does not ignore `.crew/`, adding every bookkeeping file untracked leaves `bundle_sha256` unchanged, and the manifest's `excluded` lists them. Must-block: `test_a_crew_content_path_still_enters_the_bundle` (`.crew/verify.json`, `.crew/codemap/x.md` and a nested `sub/.crew/.scope-base` change the hash). (new review rule)
- [ ] Receipt: `test_review_ledger.py::test_bookkeeping_written_after_acceptance_keeps_the_receipt`. Accept, then write the gate records, append `.crew/metrics.md` and `.crew/metrics.jsonl`, and rewrite `.crew/.scope-base`, and `--check-receipt` still passes. `test_a_source_edit_after_acceptance_still_stales_the_receipt` fails the check. (new review rule)
- [ ] Audit, must-allow: `test_completion_audit.py::test_bookkeeping_is_never_out_of_touch` passes with every bookkeeping file untracked and the ticket approved. Must-block: `test_an_out_of_touch_file_beside_bookkeeping_still_fails` names the real path and no bookkeeping path. `test_unapproved_touch_still_fails_but_lists_no_bookkeeping` covers the unapproved case. (rule 25)
- [ ] Guard: `test_scope_guard.py::test_an_edit_to_bookkeeping_is_allowed_outside_touch` (`.crew/metrics.md` under `block`) passes. `test_scope_base_stays_refused_though_it_is_bookkeeping` passes for Write and Edit in `report`, `block` and `auto`. (rule 25)
- [ ] Gate: `test_verify_gate_bookkeeping.py`, each case for bash and for pwsh (a named skip when pwsh is absent). Untracked bookkeeping is neither unmapped nor matched. A refresh-artifact path no rule names is not unmapped. A refresh-artifact path a rule names still runs that rule. An unmapped ordinary file still fails under `"unmapped": "fail"`. (rule 4)
- [ ] `crew_refresh_check.py --classify` (paths on stdin, `<kind>\t<path>` out, kind in `bookkeeping|artifact|other`) is covered by `test_refresh_check.py::test_classify_names_each_kind`, and `--ticket` is still required without `--classify`. (rule 25)
- [ ] Sabotage: every new mutation in `sabotage_scope.py`, `sabotage_review.py` and `sabotage_refresh.py` goes red on its named test through `python3 plugin/crew/tests/sabotage.py`, and the non-RED set equals origin/main's by label.
- [ ] Docs: README.md:766's "Nothing else is exempt" paragraph, CONFIG.md's gate-record sentence, done.md checks 1-3, review.md step 6, verify.md, implement.md step 6, the daily-workflow and troubleshooting guide sources plus the rebuilt outputs (`docs/guides/crew/src/build.py`), `.crew/codemap/crew.md` and `verification-harness.md`, and `docs/diagrams/process-crew-lifecycle.mmd` where it names the exclusions. Each is updated or named in the PR body as checked-and-unchanged.
- [ ] `python3 scripts/check-marketplace.py` passes after crew is bumped one patch in plugin.json, marketplace.json and PLUGINS.md, with a CHANGELOG entry that names the receipt-restale risk. `.crew/verify.json` gains a rule for `review_patch.py`/`review_ledger.py` and their tests, and rules 4 and 25 list the new tests.
