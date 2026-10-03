# T-0022 plan            spec: .work/tickets/T-0022/spec.md

Owner approves (risk: high). Preconditions: steps 1-2 need only main (and re-check the order when T-0008 lands); steps 3-4 need T-0004 merged; step 4's tracker calls need T-0021 merged (until then it stops with the named reason). Crew version: the next free patch at approval. Five steps.

### Step 1: `crew_docs_check.py` - per-document verdicts, read-only
Files: plugin/crew/hooks/scripts/crew_docs_check.py, plugin/crew/tests/test_docs_check.py
Where: changed paths from `scope_base.resolve` (`scope_base.py:242`) and `completion_audit.changed_paths` (`completion_audit.py:79`); entries from `.claude-plugin/marketplace.json` (`name`, `source`, `version`); `[Unreleased]` at `CHANGELOG.md:5`; judgement rules `crew-docs/SKILL.md:24-29`
Test: python3 -m pytest plugin/crew/tests/test_docs_check.py -q (tests first, against tmp git repos from `crew_fixtures`; watch them fail on the missing module)
Risk: high - a `not needed` without evidence is the owner's stale-docs complaint wearing a pass
- [ ] `ticket_docs(root, ticket) -> {"status": "ok"|"missing"|"unknown", "documents": [{"doc", "verdict": "updated"|"not needed"|"MISSING"|"not applicable", "reason"}], "not_measured": ["adr", "runbooks"]}`; any `unknown` or MISSING -> not ok
- [ ] changed set = changed paths minus `.work/**` minus `RELEASE_PATHS` (T-0008's list: import it if exported, else define it here and pin equality in a test)
- [ ] CHANGELOG: per marketplace entry whose `source` prefix is in the changed set, the `git diff <base> -- CHANGELOG.md` added lines inside `## [Unreleased]` must name `` `<name>` `` and its current `version`; else MISSING, never waived by docs.json. No marketplace.json -> one unit, judgement (edit or reason); no CHANGELOG.md -> not applicable
- [ ] README: entry README when its `commands/**`, `agents/**`, `skills/*/SKILL.md`, `hooks/hooks.json` or `CONFIG.md` changed; root `README.md` when the set of entry names differs from the base's marketplace.json; changed -> updated, else a docs.json reason -> not needed, else MISSING
- [ ] SECURITY.md: `SECURITY_PATHS` globs (spec Unknowns); none changed -> `not needed (no security-relevant path changed)`; some changed -> updated, or a docs.json reason, else MISSING
- [ ] TODO.md: every docs.json `deferred[].key` must appear in TODO.md's added lines; none deferred -> `not needed (nothing deferred)`
- [ ] docs.json read with the unknown kept distinct: absent -> no reasons; unparseable -> `unknown`, never "no reasons"
- [ ] CLI `crew_docs_check.py --root . --ticket <id> [--json] [--explain]`: exit 0 ok, 1 missing/unknown, 2 usage; never writes
- [ ] tests: `test_changed_plugin_without_changelog_is_missing`, `test_changelog_reason_does_not_waive`, `test_changelog_entry_names_version_is_updated`, `test_release_paths_only_needs_no_changelog`, `test_readme_trigger_without_reason_missing`, `test_readme_reason_not_needed`, `test_security_untouched_not_needed`, `test_security_path_without_reason_missing`, `test_deferred_missing_from_todo`, `test_no_scope_base_unknown`, `test_docs_json_corrupt_unknown`, `test_check_writes_nothing`

### Step 2: `/crew:docs` records decisions; implement orders docs before refresh and review; done verifies
Files: plugin/crew/commands/docs.md, plugin/crew/commands/implement.md, plugin/crew/commands/done.md, plugin/crew/skills/crew-docs/SKILL.md, plugin/crew/tests/test_docs_check.py
Where: `docs.md:3` (argument-hint), `:9-23` (default mode); `implement.md:85-90` (step 6; after T-0008 it names the refresh between docs and review); `done.md:7` and the check list ending `:44`
Test: python3 -m pytest plugin/crew/tests/test_docs_check.py plugin/crew/tests/test_lifecycle_commands.py -q; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py
Risk: med - prose is the mechanism; an order that puts docs after review stales the receipt
- [ ] docs.md: `argument-hint: [ticket id] [--audit]`; with a ticket, write `.work/tickets/$1/docs.json` `{"reasons": {doc: reason}, "deferred": [{"key", "why", "unblock"}]}` (computed in full, then written once), then run `crew_docs_check.py --ticket $1` and act on each MISSING line
- [ ] implement.md step 6: tests, `/crew:docs $1`, the docs check (re-run `/crew:docs $1` on MISSING; stop after the second), the refresh (T-0008), then `/crew:review $1`
- [ ] done.md: a docs check (numbered after T-0008's check 4) that refuses on MISSING/unknown and says "do not edit a document here - a write now stales check 1's receipt; fix, then `/crew:review $1` again"
- [ ] crew-docs SKILL.md: the docs.json record and the three verdicts, one short section
- [ ] tests: `test_implement_orders_docs_check_before_refresh_and_review` (marker order), `test_done_docs_check_never_edits`

### Step 3: autopilot's docs phase
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/commands/autopilot.md, plugin/crew/tests/test_crew_autopilot_docs.py
Where: T-0004's `next_phase` branches 10-12 (`.work/tickets/T-0004/plan.md` step 2) and its `_refresh_state` helper; the receipt rule `review_ledger.py:366`, `:387-394`
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_docs.py -q
Risk: high - a docs write after the receipt fails `/crew:done` check 1; a skipped docs phase is silent
- [ ] `_docs_state(root, ticket)`: `crew_docs_check.ticket_docs`, `unknown` read as missing; the attempt count kept in `.work/tickets/<id>/autopilot-docs.json` (under `.work/`)
- [ ] new branch before T-0004's `refresh`: receipt not current and docs not ok -> `docs`, command `/crew:docs <id>`, reason lists the MISSING documents; after two attempts -> stop "documents still MISSING: <list>"
- [ ] beside `stale-after-review`: receipt current and docs not ok -> `docs-after-review`, stop, "a document is MISSING after an accepted review; writing it now stales the receipt - human decides"; nothing written
- [ ] autopilot.md names the docs phase and both stops (the stop-list test from T-0004 covers the ids)
- [ ] tests: `test_next_docs_before_refresh`, `test_next_docs_two_attempts_then_stop`, `test_next_docs_after_review_stops_without_writing` (tmp repo byte-identical), `test_next_docs_unknown_reads_missing`

### Step 4: autopilot's tracker step, and proof it cannot stale the receipt
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/commands/autopilot.md, plugin/crew/tests/test_crew_autopilot_tracker.py
Where: T-0021's `crew_tracker.move/read`; the bundle rules `review_patch.py:96-97`, `:286`, `:308` and `review_patch.compute` as `review_ledger.py:360` calls it
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_tracker.py -q
Risk: high - a tracker write that entered the bundle would break every `/crew:done` after it
- [ ] `disk_status(root, ticket)`: done if the spec header says done; review if it says review; in-progress if a non-fallback scope base is recorded; planned if `crew_ticket.accepted`; spec if spec.md exists; direction if direction.md exists
- [ ] `crew_autopilot.py tracker --root . --ticket <id>`: `crew_tracker.move(root, id, disk_status)`; `updated`/`unchanged` -> continue; `delegated` -> return the command for autopilot to run in-session; `could not update` -> stop with the reason and `python3 .../crew_tracker.py move --ticket <id> --to <status>` as the retry; module absent -> stop "tracker interface unavailable (T-0021 not landed)"
- [ ] autopilot.md: run the tracker step after every phase that changed `disk_status`, and after `/crew:done` succeeds
- [ ] tests: `test_tracker_step_unchanged_when_agreeing`, `test_tracker_step_could_not_update_stops`, `test_tracker_step_delegated_returns_command`, `test_tracker_step_without_t0021_stops`, and `test_tracker_move_after_receipt_keeps_bundle_hash` parametrised over files, obsidian-outside, obsidian-ignored-inside, obsidian-unignored-inside (refused by T-0021, hash unchanged)

### Step 5: sabotage, verify rule, docs, version
Files: plugin/crew/tests/sabotage_docs.py, plugin/crew/tests/sabotage.py, plugin/crew/tests/test_docs_check.py, .crew/verify.json, plugin/crew/README.md, plugin/crew/BUDGETS.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md, TODO.md
Where: registry `plugin/crew/tests/sabotage.py:2927`
Test: python3 plugin/crew/tests/sabotage.py restricted to DOCS mutations (each red on its named test, tree restored); python3 -m pytest plugin/crew/tests/ -q serially; python3 scripts/check-marketplace.py; python3 scripts/check_instructions.py
Risk: low - the sabotage run is what proves steps 1-4 can fail
- [ ] `DOCS_MUTATIONS`: a docs.json reason waives CHANGELOG -> `test_changelog_reason_does_not_waive`; `unknown` treated as ok -> `test_no_scope_base_unknown`; docs branch placed after `review` -> `test_next_docs_before_refresh`; tracker `could not update` treated as `unchanged` -> `test_tracker_step_could_not_update_stops`
- [ ] register at `sabotage.py:2927`; `test_every_docs_sabotage_anchor_is_present_exactly_once`; record which went red in the PR body
- [ ] `.crew/verify.json` rule: `crew_docs_check.py`, `test_docs_check.py`, `test_crew_autopilot_docs.py`, `test_crew_autopilot_tracker.py`, `sabotage_docs.py` -> `python3 -m pytest plugin/crew/tests/test_docs_check.py plugin/crew/tests/test_crew_autopilot_docs.py plugin/crew/tests/test_crew_autopilot_tracker.py -q`
- [ ] README: the phase order implement -> docs -> refresh -> review -> done, the three verdicts, the CHANGELOG rule, the tracker step and why it may follow review; bump crew to the version assigned at approval; CHANGELOG; BUDGETS.md if flagged; TODO.md: ADR/runbook measurement as a follow-up

## Self-review
- Spec coverage: verdicts, CHANGELOG rule, README/SECURITY/TODO judgement, unknown, no writes -> 1; docs.json, implement order, done check -> 2; autopilot docs phase and after-review stop -> 3; tracker step, delegated, could-not-update stop, bundle-hash proof -> 4; sabotage, verify rule, docs, version -> 5.
- Touch coverage: every Files: entry is under the spec's Touch.
- Interfaces: `ticket_docs` (1) is what 2's prose and 3's `_docs_state` call; `disk_status` and the tracker step (4) call T-0021's `crew_tracker.move`; 3 and 4 extend T-0004's `next_phase`.
- Not verified while planning: T-0004's final branch numbering and helper names (re-read `crew_autopilot.py` when it lands); whether T-0008 exports its release-bookkeeping list; `review_patch.compute`'s exact signature beyond `compute(root, base)` as `review_ledger.py:360` calls it.
