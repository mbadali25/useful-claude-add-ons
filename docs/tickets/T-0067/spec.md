# T-0067 autopilot fixes round-1 review findings itself: autopilot.reviewPolicy and the single-ticket fix phase          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket; there was no earlier spec.md or plan.md. Written against origin/main `155fe6d8` (crew 1.0.322). See direction.md, "Direction check 2026-10-04".

What this spec changes from the approved direction, and why:
- **Narrowed to the first slice.** The direction's option 1 held three mechanisms. This ticket keeps the review policy and the fix phase. The stop-message contract is L-0666, `/crew:graph` is L-0667, and the sabotage mutations are L-0668 (a tooling-only PR). Their contracts are in `children/<k>/`.
- **The key is added here, not by T-0029.** T-0029 is still in progress and 1736 commits behind main, so `autopilot.reviewPolicy` does not exist. Same name, values and default as T-0029's spec.
- **"INCOMPLETE twice" is dropped.** Main's sabotage rule "an INCOMPLETE round is rerun unattended" must stay red-capable; an unrefunded INCOMPLETE keeps stopping.
- **The last round is unchanged.** L-0510's auto-accept (0 BLOCK, other-family reviewer) already decides it; this ticket adds nothing there.
- **No sabotage file is edited here** (harness path, tooling-PR rule). Lines that existing mutations anchor stay byte-identical.

## Design (for the owner to confirm at approval)
- **Setting.** `autopilot.reviewPolicy`: `stop` (default), `clean-only`, `fix-and-rereview`. Repo layer only, like the rest of the `autopilot` block. `crew_autopilot.settings` returns it as `reviewPolicy`. A value that is not exactly one of the three strings reads `stop`, with a warning. A config that cannot be read reads `unknown`, which never fixes (the same could-not-tell rule `approval` and `questions` follow). `stop` and `clean-only` behave exactly as main does today in a single-ticket run; `clean-only` is accepted so T-0029 can give it a wave meaning later.
- **New phase `fix`.** In `_review_phase`, where main returns the `accept-review` stop for a FINDINGS round no receipt stands on, the policy is asked first. `next` returns `phase=fix stop=0 command=fix-findings <ticket> round <n>` only when ALL of these hold:
  - `reviewPolicy` is exactly `fix-and-rereview`;
  - the ledger is readable and not NEEDS_REPLAN (those branches come first and are untouched);
  - `rounds_left` is an int (never a bool) and at least 1;
  - the round's row carries `findings` as a list of strings, with at least one `BLOCK|` or `FIX|` line;
  - the fix is not yet complete (next bullet).
- **When the fix is complete.** Both must be true, read from disk:
  - `.work/tickets/<id>/fixes.md` has a `## Round <n>` section holding every `BLOCK|` and `FIX|` line of the round verbatim, each as a whole line, as many times as the row carries it (the rule `review_ledger.check_follow_up` uses for a follow-up's direction.md). NIT lines are not required.
  - The bundle rebuilt now from the row's `base` (`review_patch.compute`) has a different `bundle_sha256` than the row's. `.work/` is outside the bundle, so writing fixes.md alone never satisfies this.

  Then `next` goes through `_toward_review` as a not-ok receipt does: refresh first if an artifact is stale, then `/crew:review <ticket>`.
- **Fail closed.** Each of these returns the existing `accept-review` stop, with the cause named in the reason: policy `stop`, `clean-only` or `unknown`; `rounds_left` missing, not an int, or 0; a row with no `findings` list, a non-string entry, or no `base` or `bundle_sha256`; a bundle that cannot be rebuilt; fixes.md unreadable (present but not UTF-8). A missing fixes.md is known and means "not fixed yet".
- **Loop bound.** The existing no-progress guard is the bound: when `fix` is named again right after a `fix` phase ran, `next` stops. With a budget of 2 there is at most one fix phase per plan.
- **The fix phase procedure** (`commands/autopilot.md`, section 3). Read the round's findings from the ledger row. For each BLOCK and FIX: write the failing test first, then the fix, inside the spec's Touch. Run the verify gate. Commit. Write the fixes.md section: each finding line verbatim, followed by a `fixed:` line naming the test and what changed. Go back through `next`. The phase stops, naming the finding, when a finding needs a path outside Touch, disputes the spec or the plan, or the implementer disagrees with it. No BLOCK or FIX is skipped silently. The review phase still ends at its verdict; fixing happens only in this phase, named by `next`.
- **Stops list.** `PROCEDURE_STOPS` gains `fix-refused` (a finding the fix phase could not or would not fix: the owner decides). `review-acceptance` is unchanged: nothing here accepts a review.
- **Status.** `WAITING` maps `fix` to the owner key like every other phase; a `fix` phase with `stop=0` already prints "autopilot - run ... to continue" through `_waiting`.

## Intent
A single-ticket `/crew:autopilot` run, in a repo that set `autopilot.reviewPolicy: fix-and-rereview`, no longer stops to ask the owner to fix round-1 review findings and start round 2. It fixes every BLOCK and FIX test-first, records the fixes, refreshes and runs the next round itself. It still stops for everything that is the owner's: accepting findings, a final round the auto-accept guard refuses, an INCOMPLETE round, NEEDS_REPLAN, and any finding it cannot fix inside the ticket's Touch. The default (`stop`) leaves today's behaviour unchanged.

## Exclusions
- No stop-message contract or rewording of existing stops (L-0666). The one stop text this ticket edits is the FINDINGS stop it sits beside, and only to name the policy.
- No `/crew:graph` command and no change to `crew_refresh_check.py` (L-0667).
- No edit to any harness path: `plugin/crew/tests/sabotage*.py`, `plugin/crew/hooks/scripts/review_*.py`, `plugin/crew/commands/review.md`, `crew_ticket.py`, `scope_guard.py`. The mutations for this change are L-0668.
- No acceptance of a review, no change to `--auto-accept` or its guard, no change to the budget (2) or the refund rule. T-0073 owns acceptance policy.
- No rerun of an unrefunded INCOMPLETE round. The branch at `crew_autopilot.py:540-544` stays as it is.
- No wave or lane behaviour (T-0029). No machine-layer key. The default stays `stop`: autonomy is opt-in.
- The lines existing sabotage mutations anchor stay byte-identical: `crew_autopilot.py:527` and `:540`, `crew_state.py:1134` (the first line of `AUTOPILOT_DEFAULTS`), `who = WAITING.get(phase, UNKNOWN)`, and `never fix and rerun inside the phase` in `autopilot.md`.
- No change to this repo's own `.crew/config.json` (untracked; the owner's setting).

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_autopilot.py:491 `_review_phase`. :515-525 the FINDINGS branch: `accept-review`, stop, "the owner accepts with review_ledger.py --accept --by <owner>, or fixes then /crew:review". :526 `left = ledger.get("rounds_left", 0)`. :527-531 no round left and no receipt. :532-539 a refunded round reruns. :540-544 an unrefunded INCOMPLETE stops. :548-565 `_toward_review` (refresh, then review, then done).
- plugin/crew/hooks/scripts/crew_autopilot.py:568-601 `next_phase`; the no-progress guard at :597-600. :203-207 `PROCEDURE_STOPS`; :204 `review-verdict`. :209-221 `HUMAN_STOPS`. :1350-1354 `WAITING`; :1388 `_waiting`.
- plugin/crew/hooks/scripts/crew_autopilot.py:759 `settings`; :776-785 the could-not-tell return (`approval` and `questions` read `UNKNOWN`). :788 `_settings_at`; :820-826 the policy keys and the returned dict. :995 `_policy_setting`.
- plugin/crew/hooks/scripts/crew_state.py:1134-1135 `AUTOPILOT_DEFAULTS` (`mode`, `maxPhases`, `deploy`, `approval`, `questions`).
- `git grep reviewPolicy origin/main` prints nothing. T-0029's spec (`.work/tickets/T-0029/spec.md:6`, `:106`) names the key, its values and its default.
- plugin/crew/hooks/scripts/review_ledger.py:133 `BUDGET = 2`. :388-390 a completed row stores `verdict`, `counts`, `bundle_sha256`, `base`. :560-595 `auto_accept_refusal`; :584-586 "not the final round ... fix and run the next round". :757 `check_follow_up` (the whole-line verbatim rule). :824-831 `_current_hash` calls `review_patch.compute(root, base)`.
- plugin/crew/hooks/scripts/review_patch.py:374 `compute(root, base, ...)`, which reads staged, unstaged and untracked changes (:388-391). :135-136 `.work/` and `graphify-out/` are excluded from the bundle.
- plugin/crew/commands/autopilot.md:63-70 the loop (`stop=0` follows the command; any other `stop=1` stops). :82-90 "A review phase ends at its verdict ... never fix and rerun inside the phase ... fixing, `review_ledger.py --accept` and `gh pr review` are the human's". :93-97 the stop lists.
- plugin/crew/tests/sabotage_autopilot.py:54-57 anchors `    if not ok and (not isinstance(left, int) or left < 1):`. :58-61 "an INCOMPLETE round is rerun unattended" anchors `    if latest.get("verdict") != "CLEAN" and not ok:`. :62-65 anchors `never fix and rerun inside the phase` in the command. :217 anchors the first line of `AUTOPILOT_DEFAULTS`. :497 anchors `    who = WAITING.get(phase, UNKNOWN)`.
- plugin/crew/tests/test_sabotage_harness.py:371 `test_every_shipped_anchor_is_present_in_its_target_exactly_once`.
- plugin/crew/tests/test_crew_autopilot.py:1256 `test_command_names_every_fixed_and_human_stop` (covers `PROCEDURE_STOPS`). :1267 `test_command_ends_the_review_phase_at_the_verdict`. :481 `test_next_incomplete_round_stops`.
- Config surfaces: plugin/crew/templates/config.template.json:215-221; plugin/crew/skills/crew-setup/SKILL.md:232 (the inline copy); plugin/crew/hooks/scripts/crew_config_menu.py:80 (`autopilot.mode` in `_KNOWN_VALUES`); plugin/crew/CONFIG.md:844-848 (key table), :2591-2608 (section 20), :166 (130 leaves, 58 repo-only).
- Docs that describe the behaviour: plugin/crew/README.md:857 (autopilot section), :915 (stops); .crew/codemap/crew.md:666 (the autopilot section), :253-274 (leaf counts). No file under `docs/guides/crew/src/` mentions autopilot (`git grep -n autopilot origin/main -- docs/guides/crew/src` prints nothing).
- Harness rule: scripts/check-tooling-pr.py:58-87 `HARNESS` (includes `plugin/crew/tests/sabotage*.py` and `plugin/crew/commands/review.md`), :89-95 `SEAM` (includes `crew_autopilot.py` and `commands/autopilot.md`), :189 prints `tooling-pr: no harness path changed`.
- .crew/verify.json:348-359 the autopilot rule; its `run` line names each test file, so a new test file must be added to it.

## Unknowns
- **Owner questions** (direction.md, "Open questions for the owner"): add the key here or wait for T-0029; INCOMPLETE keeps stopping; a round-1 BLOCK is fixed unattended. The recommended answers are built in above.
- **`status` under `policy=False`.** `_phase(policy=False)` is `status`'s read and today changes only reason wording. Resolved at plan by reading `plugin/crew/tests/test_crew_autopilot_status.py`: the default is that `status` shows the `fix` phase under the setting, and the reason names no policy value.
- **`crew_status.py`.** Whether `/crew:status` renders autopilot phases from a closed list. Resolved at plan with `git grep -n accept-review origin/main -- plugin/crew/hooks/scripts/crew_status.py`; if it does, the file joins Touch by amendment before any edit.
- **Rows recorded before L-0510 carry no `findings`.** Accepted: such a round reads could-not-tell and stops, as today.
- **A bundle that changed for another reason** (a catch-up merge, a version bump) while fixes.md is complete would send unfixed code to round 2. Accepted as risk: fixes.md is the implementer's signed claim, and round 2 is the check.
- **CONFIG.md's leaf counts** (130 / 58) move by one. Re-measure with `leaf_paths(default_config())` at implement; do not edit the number by hand.
- **T-0029's catch-up.** When T-0029 merges main it will find the key present. Its spec line 106 must change from "adds" to "reads". Noted in Dependencies; not this ticket's edit.
- The next free crew patch version is set at implement time.

## Size and split
- Estimate: about 150 added production lines. `crew_autopilot.py` about 110 (setting, the phase decision, the fixes.md matcher, `fix-refused`, `WAITING`, the CLI field), `autopilot.md` about 30, the four config surfaces about 6.
- One fail-closed state machine (the phase decision). The fixes.md matcher is a whole-line comparison, not a grammar.
- No harness path. Split out: L-0666 (stop contract), L-0667 (`/crew:graph`), L-0668 (sabotage, tooling-only).

## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_state.py` - one key added to AUTOPILOT_DEFAULTS, first line unchanged
- `plugin/crew/hooks/scripts/crew_config_menu.py` - the known values of the new key
- `plugin/crew/templates/config.template.json`
- `plugin/crew/skills/crew-setup/SKILL.md` - the inline copy of the autopilot block
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_autopilot_review_policy.py` - new
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/tests/test_config*.py` - only where a test pins the autopilot block or the leaf count
- `.crew/verify.json` - the new test file joins the autopilot rule's paths and run line
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/PLUGINS.md`
- `.crew/codemap/**`
- `docs/diagrams/**`
- `.claude/rules/**` - regenerated, never hand-edited
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

Not in Touch, stated: `docs/guides/crew/**` (no guide mentions autopilot; the PR body says `Docs: guides none - no guide describes autopilot`); every harness path; `crew_refresh_check.py`; `.crew/config.json`.

## Acceptance checks
Commands run from the repo root. `T` is `plugin/crew/tests/test_crew_autopilot_review_policy.py`. Each maps to the autopilot rule in `.crew/verify.json` unless it names another.
- [ ] Default. With no key set, `settings` returns `reviewPolicy: stop` and the CLI prints `reviewPolicy=stop`. `python3 -m pytest T -q -k test_settings_review_policy_defaults_to_stop`
- [ ] Invalid values. Each of `"Fix-And-Rereview"`, `"fix"`, `True`, `1` and `""` reads `stop` with a warning naming the value. `-k test_settings_review_policy_invalid_value_warns_and_reads_stop`
- [ ] Could-not-tell. A `.crew/config.json` that is not valid JSON, and an `autopilot` value that is not an object, read `reviewPolicy: unknown`. `-k test_settings_unreadable_config_reads_review_policy_unknown`
- [ ] Must-allow. Round 1 FINDINGS with one FIX line, a round left, policy `fix-and-rereview`: `next` prints `phase=fix stop=0 command=fix-findings <id> round 1`. `-k test_next_round1_findings_names_the_fix_phase`
- [ ] Must-allow. The same with a BLOCK line. `-k test_next_round1_block_names_the_fix_phase`
- [ ] Must-allow. After a commit that changes a bundled file and a fixes.md that holds every BLOCK and FIX line under `## Round 1`: `next` names the refresh command when an artifact is stale and `/crew:review <id>` when all are fresh. `-k test_next_after_the_fix_goes_toward_review`
- [ ] Must-block, one test each. Each returns `phase=accept-review stop=1` (or the named stop):
  - policy `stop` and policy `clean-only` (parametrised): today's stop, byte-identical reason to main's for `stop`;
  - policy `unknown` (unreadable config);
  - the final round (0 rounds left) under `fix-and-rereview`;
  - `rounds_left` missing, a bool, or a string;
  - a row with no `findings`, with a non-string entry, with only NIT lines, with no `base`, with no `bundle_sha256`;
  - a bundle rebuild that raises;
  - fixes.md present but not UTF-8;
  - fixes.md complete but the bundle unchanged: `phase=fix`, and a second `next` with `--last-command "fix-findings <id> round 1"` stops for no progress;
  - the bundle changed but fixes.md is missing a FIX line, holds it only as part of a longer line, or holds it under `## Round 2`: `phase=fix`;
  - a line the row carries twice and fixes.md holds once: `phase=fix`;
  - an unrefunded INCOMPLETE round under `fix-and-rereview`: `accept-review` stop (`-k test_next_incomplete_round_stops_under_fix_and_rereview`);
  - NEEDS_REPLAN under `fix-and-rereview`: the `replan` stop;
  - a reserved round with no result under `fix-and-rereview`: the `review` stop.
- [ ] `stops` lists `fix-refused` under `procedure`, and `autopilot.md` names it. `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q -k test_command_names_every_fixed_and_human_stop`
- [ ] The command describes the fix phase: test first, inside Touch, verify gate, commit, the fixes.md shape, and the three refusals that stop. The sentence `never fix and rerun inside the phase` is still present once. `-k test_command_describes_the_fix_phase` and `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q -k test_command_ends_the_review_phase_at_the_verdict`
- [ ] Status maps `fix`: a `fix` phase prints `autopilot - run ... to continue`, never `unknown (phase ...)`. `python3 -m pytest plugin/crew/tests/test_crew_autopilot_status.py -q -k fix`
- [ ] Existing anchors intact, no sabotage file edited: `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q -k test_every_shipped_anchor_is_present_in_its_target_exactly_once` passes and `git diff --name-only origin/main...HEAD -- 'plugin/crew/tests/sabotage*.py'` prints nothing.
- [ ] Existing suites pass unchanged: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_autopilot_policy.py -q`.
- [ ] Config surfaces agree: the template, crew-setup's inline copy, `AUTOPILOT_DEFAULTS` and CONFIG.md's two tables all carry `reviewPolicy` with default `stop`; the leaf counts in CONFIG.md and the code map are re-measured. `python3 -m pytest plugin/crew/tests/ -q -k "config and autopilot"` and the prompts rule `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)`.
- [ ] Not a tooling PR: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`.
- [ ] Docs: README (autopilot section and stops), CONFIG.md section 20 and the key table, PLUGINS.md's crew row where it describes autopilot, the code map's autopilot section and the lifecycle diagram describe the `fix` phase and the key. Crew is bumped to the next free patch in `plugin.json` and `marketplace.json` with a CHANGELOG entry. After the commit, `python3 scripts/check-marketplace.py` passes.

## Dependencies
Must land first:
- T-0004 (merged): `/crew:autopilot` and `next`.
- T-0010 (merged): the policy pattern (`approval`, `questions`, could-not-tell reads `unknown`).
- T-0018 (merged): `status` and the `WAITING` map.
- T-0008 (merged): the refresh check `_toward_review` uses.
- L-0510 (done): the `findings` list on a round row, `check_follow_up`'s verbatim rule, the final-round auto-accept.
- T-0087 (merged): the tooling-PR rule that shapes the split.

No longer a blocker:
- T-0029 (in-progress): was to add `reviewPolicy`. This ticket adds it; T-0029 must read it instead when it catches up with main.
- T-0064 (approved, draft PR open): needed only by L-0667.

Related, same files, no order forced: T-0063 (approved; autopilot's INDEX read from a worktree), T-0070 (spec; inert settings are loud - should list `reviewPolicy`), L-0522 (in-progress; receipt after a catch-up merge).

Blocks:
- L-0666 (edits the same function; lands after this).
- L-0668 (sabotage for this change).
- T-0073 (direction): `autopilot.reviewAcceptance`; names T-0067 as a dependency.
- T-0029: its lane prompt's "fix and re-review within the ledger budget" should reuse this phase's fixes.md rule.

## Split
- L-0666 (child 1 of T-0067, filed 2026-10-04): autopilot stop messages name only owner decisions (a contract test over every stop)
- L-0667 (child 2 of T-0067, filed 2026-10-04): /crew:graph - one command for graph status, the sanctioned refresh and queries
- L-0668 (child 3 of T-0067, filed 2026-10-04): sabotage mutations for the review policy, the fix phase and the stop contract (tooling-only PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
