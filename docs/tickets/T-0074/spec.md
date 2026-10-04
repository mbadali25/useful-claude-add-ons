# T-0074 autopilot auto-rejects an out-of-rounds review that has a BLOCK and continues with a successor plan, capped          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket (none existed). Written against origin/main `155fe6d8` (crew 1.0.322); see direction.md "Direction check 2026-10-04". No plan.md exists yet.

What differs from the 2026-09-27 direction, and why:
- The opt-in is this ticket's own key, `autopilot.maxAutoReplans` (default `0`, off). The direction hung it on T-0073's `autopilot.reviewAcceptance: all`, which was never built; L-0510 shipped the 0-BLOCK auto-accept as a constant policy instead.
- The cap counts the successor plans already on the ledger. No new ledger field, so no review/gate harness file changes in this ticket.
- No separate exclusion list: the reject is allowed only where `approval_policy` would approve the successor plan.
- Self-approval of the successor plan is already on main (T-0010) and is not rebuilt here.
- Narrowed to the first of three slices. See "Size and split".

## Intent
With `autopilot.maxAutoReplans` set to 1 or more, autopilot no longer stops when a ticket's last review round is FINDINGS with at least one BLOCK and no round is left. It rejects the review itself through one policy route (`crew_autopilot.py auto-reject`), recorded under a fixed non-owner name, then `next` names `/crew:plan` for a successor plan, the existing approval policy approves it, and review continues with fresh rounds. After `maxAutoReplans` successor plans on one ticket it stops for the owner with the history. At the default `0` nothing changes.

## Design (for the planner; decisions taken with the owner unavailable)
- **Setting.** `autopilot.maxAutoReplans`, repo only like the rest of the block. A non-negative integer; a bool, a string, a float, a negative number or `null` reads as `0` with a warning naming the value. An unreadable config or a non-object `autopilot` block reads as `0` (the existing could-not-tell path in `settings`). `settings` returns it and prints it on its second text line.
- **Policy.** `crew_autopilot.auto_replan_policy(root, ticket)` returns `{"allow", "reason", "used", "cap", "round", "blocks"}`. Pure read. It allows only when every one of these holds, and each failure has its own reason:
  1. autopilot is armed (`autopilot.mode` is `plan`);
  2. `maxAutoReplans` is 1 or more;
  3. `approval_policy(top, ticket)["allow"]` is true, so the successor plan can be self-approved. Otherwise a reject would only move the ticket to NEEDS_REPLAN and take the owner's accept option away;
  4. the ledger loads (`review_ledger.load`) and its state is `REVIEWED`;
  5. the latest round is under the current plan (`_current_rounds`), `completed`, verdict exactly `FINDINGS`;
  6. its `counts` is a dict whose BLOCK, FIX and NIT are non-negative ints (never a bool), BLOCK is 1 or more, and `findings` is a list of single-line strings holding exactly as many `BLOCK|` lines as the BLOCK count;
  7. `rounds_left` is the int `0`. With a round left the answer stays today's (fix, then `/crew:review`);
  8. the reviewer is another model family than the author's: `provider` in `review_ledger.AUTO_PROVIDERS` and `model_family` a non-empty string that is not `review_ledger.AUTHOR_FAMILY`;
  9. the number of rows in the ledger's `successors` is less than `maxAutoReplans`. Every successor counts, whoever approved it.
  Anything that raises, or any value of the wrong type, is a refusal that says "could not tell". Nothing reads as permission by default.
- **Writer.** `crew_autopilot.py auto-reject --root . --ticket <id>`: asks `auto_replan_policy` in-process, then calls `review_ledger.reject(top, ticket, AUTO_REJECT_BY)`. `AUTO_REJECT_BY` is a constant, `"autopilot (policy: autopilot.maxAutoReplans)"`; no flag sets it. Exit 0 prints `auto-rejected <id>: round <n>, <b> BLOCK / <f> FIX, replan <used+1> of <cap>` and then every BLOCK and FIX line verbatim. Exit 2 prints `refused: <reason>` and writes nothing. A `LedgerError` from `reject` is exit 2 with its text. This is the module's second writing subcommand; its only write is the ledger, through `review_ledger.reject`.
- **Routing in `next`.**
  - Latest round FINDINGS with no standing receipt: when the policy allows, the answer is phase `auto-replan`, stop false, command the `auto-reject` line above. When it refuses because the cap is reached, the answer is still `accept-review` with stop, and the reason names `autopilot.maxAutoReplans (<cap>) reached` and lists each successor row (plan hash prefix, `after_round`, `approved_by`). Any other refusal leaves today's text unchanged.
  - Ledger NEEDS_REPLAN: stop false with command `/crew:plan <id>` only when the ledger's `rejected.by` equals `AUTO_REJECT_BY`, `rejected.round` is the latest round's number, autopilot is armed, `maxAutoReplans` is 1 or more, the successor count is under the cap and `approval_policy` allows. In every other case it is today's `replan` stop, byte for byte.
  - The approve, implement, refresh and review phases after that are unchanged.
- **Stops.** `FIXED_STOPS` gains `auto-replan-cap`. The `review-acceptance` entry in `HUMAN_STOPS` is reworded: a BLOCK is never accepted by autopilot; with `maxAutoReplans` it is rejected and replanned instead. `WAITING` gains `auto-replan` so `status` never reads it as `unknown`.
- **Procedure (`commands/autopilot.md`).** On `auto-replan`: run the command, report its lines verbatim, send the review notification with the same text, go back through `next`. On a non-stop `replan`: run `/crew:plan` for a successor plan whose steps address every BLOCK and FIX line of the rejected round, each quoted verbatim, each with a neighbouring-case check; a plan identical to an earlier approved one is refused by the ledger, so it must differ. The final report names every auto-reject and every successor plan.

## Exclusions
- No acceptance of a round with a BLOCK, at any setting. `review_ledger.py --accept` stays the owner's.
- No edit to any review/gate harness path: `review_ledger.py`, `crew_ticket.py`, `scope_guard.py`, `commands/review.md`, `plugin/crew/tests/sabotage*.py`. The sabotage entries and the `review.md` sentence are L-0671.
- No mechanical check that the successor plan quotes the findings. That is L-0670; here it is procedure text only.
- No `autopilot.reviewAcceptance` key and nothing else of T-0073. No change to the L-0510 auto-accept.
- No change to `BUDGET`, refunds, the successor-plan rules or the "approved before" refusal.
- No exclusion-list key. No machine-layer key: the `autopilot` block stays repo only.
- No new model routing for who writes the successor plan. `/crew:plan` runs as configured.
- No fix-and-rereview while a round is left (T-0067). No handling of an INCOMPLETE last round: that still stops.
- No new hook. No change to `crew_status.py` or `crew_resume.py`.
- Wave lanes (T-0029) are out: a lane does not run `auto-reject` until that ticket says so.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_autopilot.py:497-501 NEEDS_REPLAN answers `replan` with stop true and command `/crew:plan <id>`. :515-524 a FINDINGS round with no standing receipt answers `accept-review` with stop true. :483-488 `_current_rounds`. :72 and :479 the approve phase stops "unless the policy allows".
- plugin/crew/hooks/scripts/crew_autopilot.py:186-200 `FIXED_STOPS`; :214-216 `HUMAN_STOPS` `review-acceptance` ("is the owner's, at every setting"). :1350-1354 `WAITING`. :1283 `stops`.
- plugin/crew/hooks/scripts/crew_autopilot.py:759-786 `settings` and its could-not-tell path; :788-826 `_settings_at`, block read at :791, `maxPhases` validation at :799-804. :1034-1072 `approval_policy`. :1129-1151 `approve`, the one writer today. :1602 `_policy_main`; :1674 and :1703 where the policy subcommands are registered and dispatched. 1768 lines; `.pylintrc:140` `max-module-lines=3400`.
- plugin/crew/hooks/scripts/crew_state.py:1134-1135 `AUTOPILOT_DEFAULTS`. plugin/crew/hooks/scripts/crew_config.py:394 deep-copies it into the repo defaults.
- plugin/crew/hooks/scripts/review_ledger.py:803-821 `reject(root, ticket, by)`: refuses ACCEPTED and NEEDS_REPLAN, writes `rejected: {by, at, round}`. :133 `BUDGET = 2`. :151-152 `AUTHOR_FAMILY`, `AUTO_PROVIDERS`. :389-399 a round row stores `counts`, `model_family`, `findings`. :475 `_family_problem` and :498 `_auto_row_problem` (private). :946-958 `summary` returns `rounds_left` and `successors` but not `rejected`. :907-940 `continue_with_successor_plan`; :887-904 the "approved before" refusal.
- Nothing on main implements this: `git grep -iE "maxAutoReplans|auto.?replan|auto.?reject" origin/main -- plugin scripts` prints nothing.
- scripts/check-tooling-pr.py:58-87 `HARNESS` (:79 `plugin/crew/tests/sabotage*.py`, :83 `plugin/crew/commands/review.md`); :89-95 `SEAM` (:91 `crew_autopilot.py`, :94 `commands/autopilot.md`). A branch that changes no `HARNESS` path exits 0.
- plugin/crew/commands/review.md:507 any BLOCK "stops for me with 2-4 options". plugin/crew/commands/autopilot.md:9-12, :84-90 (section 3's review rules) and :94-99 (section 4, Stops); 109 lines.
- Docs that state the behaviour: plugin/crew/README.md:859 ("One writer, by design"), :892-898 (phase table), :915 (Stops), :917 (Settings); plugin/crew/CONFIG.md:844-848 and :2603-2608 (key tables, section 20), :170-180 (the key-count paragraph); plugin/PLUGINS.md:130 ("review acceptance always stops"); docs/guides/crew/src/daily-workflow.md:82 and :179; docs/guides/crew/src/daily-workflow-scope.md:58 and :132; docs/guides/crew/src/troubleshooting.md:118-128; plugin/crew/templates/config.template.json:215-221; plugin/crew/skills/crew-setup/SKILL.md:232.
- Tests that pin today's contract: plugin/crew/tests/test_crew_autopilot_policy.py:682 `test_approve_is_the_only_writing_subcommand`; plugin/crew/tests/test_crew_autopilot_deploy.py:851 `test_settings_line_names_deploy`; plugin/crew/tests/test_crew_autopilot.py:1239-1240 (the defaults dict); plugin/crew/tests/test_crew_config.py:335-340 (declared-key count).
- .crew/verify.json:360-367 maps `crew_autopilot.py` and `test_crew_autopilot_policy.py` to `pytest_rule.py plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_scope_guard.py -q`; :348-359 is the wider autopilot rule.
- plugin/crew/hooks/scripts/scope_guard.py:59-64 allows only `crew_autopilot.py approve` by name; it holds no rule on `review_ledger.py --reject`, and `auto-reject` does not match its approve pattern (:118-121).

## Unknowns
- Reviewer-family check: `review_ledger._family_problem` is private. Resolved at plan: either call it with the same pylint waiver the module already uses for `crew_ticket._read_json` (crew_autopilot.py:746), or restate the rule from the two public constants. Either way a test holds the two in step. No edit to `review_ledger.py`.
- Check-then-write gap: the policy is read before `reject` takes the ledger lock. `reject` itself refuses ACCEPTED and NEEDS_REPLAN under the lock, but a round reserved in the gap would be rejected. Accepted as risk for this slice (one session drives a ticket); a harness follow-up could give `reject` an expected-round argument.
- `AUTO_REJECT_BY` can be typed by hand with `review_ledger.py --reject --by`. Accepted as risk: it is the same forge-local-state threat README "Scope and approval" already states, and the effect is only that autopilot writes a plan the approval policy still has to allow.
- Whether the owner wants the cap to count owner-approved successors too. Taken: yes (it can only stop sooner).
- T-0029's subagent never-list is not on main. If it lands first and refuses `crew_autopilot.py` subcommands other than `approve` in a lane, re-read `scope_guard.py` before planning.
- The next free crew patch version is set at implement time.

## Open questions for the owner
Each has a default already taken in this spec.
1. Opt-in key: `autopilot.maxAutoReplans` with default `0` (taken), or wait for T-0073's `reviewAcceptance: all`.
2. Cap value when turned on: 2 (the direction's recommendation, the owner sets it), 1, or no upper bound.
3. On the cap: stop for the owner (taken), or park the ticket and move on.
4. Exclusions: rely on `autopilot.approval` (taken), or add a path-glob exclusion list for guard and production-authority tickets.
5. Successor plan author: `/crew:plan` as configured (taken), or force a different model family or tier.
6. Cap counts every successor plan (taken), or only the ones that followed an automatic reject. The second needs a rejection history in `review_ledger.py`, a harness change.

## Size and split
- This slice: about 150 added production lines (`crew_autopilot.py` about 145, `crew_state.py` 2, `config.template.json` 1). One guard (`auto_replan_policy`). No harness path. Under the 300-line rule.
- L-0670: the successor-plan check (a second guard, about 80 lines in `crew_autopilot.py`).
- L-0671: sabotage entries for both guards and the `review.md` sentence. Tooling-only PR, no production lines.
- Land order: this ticket, L-0670, L-0671. L-0671 may land after this ticket alone if L-0670 is delayed, with only this ticket's mutations.

## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_state.py` - the one AUTOPILOT_DEFAULTS key and its comment
- `plugin/crew/templates/config.template.json`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_autopilot_replan.py` - new
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_policy.py`
- `plugin/crew/tests/test_crew_autopilot_deploy.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/test_config_menu.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/skills/crew-setup/SKILL.md`
- `plugin/PLUGINS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `CHANGELOG.md`
- `docs/guides/crew/src/daily-workflow.md`
- `docs/guides/crew/src/daily-workflow-scope.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/crew-1.0-*` - the rebuilt HTML, DOCX and PDF
- `docs/diagrams/**` - the lifecycle review diagram and its rendered outputs
- `.crew/codemap/**`
- `.crew/verify.json` - the new test file joins the policy rule
- `.claude/rules/**` - regenerated
- `graphify-out/**` - rebuilt

## Acceptance checks
Rules are `.crew/verify.json`'s: "policy rule" is the one at :360-367, "autopilot rule" the one at :348-359. Run pytest through the repo's heavy-run wrapper where the host needs it.
- [ ] New file, policy rule: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_replan.py -q` passes, and holds at least these tests:
  - `test_default_zero_changes_nothing`: with no key set, `next` on an out-of-rounds 1-BLOCK ledger answers `accept-review`, stop true, with the same reason text as before this change.
  - `test_next_names_auto_reject_when_policy_allows`: `maxAutoReplans: 2`, armed, `approval: self`, `allowCliApproval: true`, codex round 2 FINDINGS with 1 BLOCK: phase `auto-replan`, stop false, command ends `crew_autopilot.py auto-reject --root . --ticket <id>`.
  - `test_auto_reject_moves_ledger_and_names_the_policy`: the subcommand exits 0, the ledger is NEEDS_REPLAN, `rejected.by` equals `AUTO_REJECT_BY`, stdout quotes every BLOCK and FIX line verbatim.
  - `test_auto_reject_refusals_write_nothing` (parametrised, one case per policy condition 1 to 9): not armed; key `0`; `approval: human`; `allowCliApproval` false; `approval: risk` on a `risk: high` spec; state IN_REVIEW, ACCEPTED, NEEDS_REPLAN, corrupt ledger; round reserved; verdict INCOMPLETE; 0 BLOCK; BLOCK count a bool or a string; `findings` missing or holding fewer `BLOCK|` lines than the count; one round left; provider `claude`; provider `copilot`; `model_family` missing or `claude`; cap reached. Each exits 2 with `refused:` and leaves the ledger bytes unchanged.
  - `test_setting_garbage_reads_zero_with_warning` (parametrised: `true`, `"2"`, `2.5`, `-1`, `null`).
  - `test_unreadable_config_reads_zero`.
  - `test_replan_after_auto_reject_is_not_a_stop` and `test_replan_after_owner_reject_still_stops` (`rejected.by` an owner name: stop true, reason text unchanged).
  - `test_replan_stops_when_rejected_round_is_not_latest`.
  - `test_cap_reached_stops_and_lists_successors`: two successor rows, cap 2: `accept-review`, stop true, reason names the cap and both plan-hash prefixes.
  - `test_full_cycle_reject_plan_approve_opens_fresh_rounds`: auto-reject, write a different plan, `crew_autopilot.py approve` exits 0, ledger IN_REVIEW, `next` answers `implement`.
  - `test_family_rule_matches_review_ledger`: for each provider and family pair the test table holds, the policy's family verdict equals `review_ledger.auto_accept_refusal`'s family verdict on a 0-BLOCK copy of the row.
- [ ] Policy rule: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_scope_guard.py -q` passes; `test_approve_is_the_only_writing_subcommand` is replaced by a test naming exactly two writers, `approve` and `auto-reject`, and showing every other subcommand writes nothing.
- [ ] Autopilot rule: the run line at `.crew/verify.json:357` passes unchanged in shape; `settings` text prints `maxAutoReplans=` on its second line and `--json` carries the key; `stops` lists `auto-replan-cap`; the test that checks `commands/autopilot.md` names every stop passes with the new stop.
- [ ] `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_config_menu.py -q` passes with `autopilot.maxAutoReplans` in the declared keys and the count re-measured by running the test; CONFIG.md's count paragraph and both key tables state the new key.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 and reports no harness path changed. `git diff --name-only origin/main...HEAD` lists nothing under `plugin/crew/tests/sabotage*.py`, `review_*.py`, `crew_ticket.py`, `scope_guard.py` or `commands/review.md`.
- [ ] `git diff origin/main...HEAD -- plugin/crew/hooks/scripts plugin/crew/templates | grep -c '^+[^+]'` is under 300.
- [ ] Docs: README (:859 two writers, phase table, Stops, Settings), CONFIG.md section 20, PLUGINS.md's autopilot row, the three guide sources and their rebuilt outputs (`python3 docs/guides/crew/src/build.py`), the lifecycle review diagram, and the code map all describe the key, the `auto-replan` phase and the cap. `grep -rn "maxAutoReplans" plugin/crew/README.md plugin/crew/CONFIG.md plugin/crew/commands/autopilot.md docs/guides/crew/src` prints at least one line per file named.
- [ ] Version: crew bumped one patch past origin/main in `plugin/crew/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, with a CHANGELOG entry. After the commit, `python3 scripts/check-marketplace.py` exits 0.
- [ ] `python3 -m pylint plugin/crew/hooks/scripts/crew_autopilot.py plugin/crew/tests/test_crew_autopilot_replan.py` scores 10.00 and ruff reports no new finding against the merge base.
- [ ] Not run here and to say so in the PR body: `scripts/_test/drift-detection.sh` (skipped by default), and the sabotage run for the new guard (L-0671 adds its entries).
- [ ] PR body carries the docs list, and names L-0670 and L-0671 as the follow-ups.

## Dependencies
Must land first:
- T-0010, merged (PR #261): the approval policy and `crew_autopilot.py approve`, which approves the successor plan and moves NEEDS_REPLAN to IN_REVIEW.
- L-0510, done (on main: 50e9fc66): round rows carry `findings`, `provider` and `model_family`; the 0-BLOCK case is already handled, so this ticket covers only rounds with a BLOCK.
- T-0004 and T-0018, merged: `next` and the subcommand router this extends.

Related, not blocking:
- T-0073, direction: its `reviewAcceptance` key is no longer needed by this ticket (see the direction check). Its `fix-only` half shipped as L-0510.
- T-0067, ready: fix-and-rereview while a round is left. Independent; this ticket acts only at zero rounds left.
- T-0029, in-progress: wave lanes and the subagent never-list. See Unknowns.
- T-0109, direction, and T-0098, direction: `reject` and `accepted_by` corrections in the ledger. Independent.
- T-0037, ready: a derived `needs-replan` ticket status. Independent.

Blocks:
- L-0670 and L-0671.
- T-0053, ready (sleep mode), and T-0060, spec (out-of-rounds pings), read better once this lands, but neither is blocked by it.

## Split
- L-0670 (child 1 of T-0074, filed 2026-10-04): autopilot approves a successor plan after an automatic reject only when it quotes every BLOCK and FIX line
- L-0671 (child 2 of T-0074, filed 2026-10-04): sabotage entries for the auto-replan policy and the successor-plan check; review.md names the policy (tooling-only PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
