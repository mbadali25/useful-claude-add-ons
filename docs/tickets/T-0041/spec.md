# T-0041 crew verifies before it states: verified-or-labelled claims, prior decisions looked up, bytes copied not retyped, "Not verified" enforced in reports and review          status: spec   risk: med
## Intent
Crew's own prompts carry one rule: a claim about code, config, history or state is either verified in this session (a `path:line`, the command and its output, or the ref it was measured at) or labelled `not verified` / `inferred`. "Could not tell" is its own answer, and a prior decision is looked up (CHANGELOG, `docs/adr/`, the ticket's `direction.md`) before a change to it is proposed. The rule is in the four agent prompts, in `crew-best-practices` (whose description is the always-loaded part), and in the plan and brainstorm self-checks. `/crew:done` and `/crew:debug` end with a "Not verified" section.

The rule is also checked by machine. `validate-prompts.py` fails when an agent report template (all but `reviewer`, whose output is a machine contract) or the done/debug report has no "Not verified" section. It also fails when the shared review prompt and `reviewer.md` lose the new "claims without evidence" FIX category. The review verdict parser treats only ASCII line breaks as line breaks, so a finding that quotes U+2028 is no longer split and the round is no longer spent as INCOMPLETE. Each `review.json` records the sha256 of the output bytes the verdict was computed from, so a later hand-edited or retyped `out.txt` is detectable.

## Exclusions
- Nothing is installed into consumer repos. No CLAUDE.md rule is written by `/crew:init`, `crew-setup` or `crew_instructions.py` (`AGENTS.md`, `.claude/rules/`). This was approved in direction.md ("not installed into consumer repos").
- No hook is added or changed. `crew_context.py`'s SessionStart and SubagentStart output is not changed. It is budgeted at 12 lines / 1,500 chars (`plugin/crew/hooks/scripts/crew_context.py:56-57`). Whether a one-line rule belongs there is an open question for the owner, and the recommendation is a separate ticket.
- The reviewer output contract does not change: `READ|`, `SEVERITY|file:line|what breaks|repro`, `CLEAN`. No new severity and no new line type. "Claims without evidence" is a FIX category inside the existing contract. A finding the reviewer could not reproduce says `not reproduced: <why>` in its free-text repro field, which needs no parser change.
- The review ledger, receipt, budget and accept/reject rules are not changed. `output_sha256` goes into `review.json` only, not into the ledger row or the receipt, so no existing receipt goes stale.
- `review_prompt.py` is not changed. The shared prompt's wording lives in `plugin/crew/commands/review.md`'s heredoc.
- `review.md` does not grow. It sits at its `.budget-allowance.json` ceiling of 551 lines, so each edit replaces lines in place, line for line.
- `autopilot.md` (120 lines, at the command cap), `implement.md` and the other dispatching commands get no "Not verified" section in this ticket. Enforcement covers the three agents with a free-form report plus `done.md` and `debug.md`.
- No config key, so no `plugin/crew/CONFIG.md` change (PR body: `Docs: CONFIG.md none - no config key added or changed`).
- `sabotage.py` is not edited. It is at 3381 of `.pylintrc`'s `max-module-lines=3400`. New mutations join `REVIEW_FIX_MUTATIONS` inside `sabotage_review.py`, which `sabotage.py:69` already imports.
- No codemap claim-marker lint (direction's third mechanical candidate). The existing `check_self_claims` already covers marked numbers, and the project CLAUDE.md says not to make it infer unmarked ones.

## Evidence
Anchored to origin/main `bebbb97f` (crew 1.0.46). Read with `git archive origin/main`, because the local main is stale.
- The parser splits on every Unicode line boundary. `plugin/crew/hooks/scripts/review_verdict.py:61` is `for raw in (text or "").splitlines():`. A fragment that matches no contract line is INCOMPLETE (`:88-90`).
- The Codex event stream is split the same way (`plugin/crew/hooks/scripts/review_verdict.py:131`). JSONL is newline-delimited, and a non-JSON fragment sets `error` (`:139-141`), which makes the round INCOMPLETE (`plugin/crew/hooks/scripts/review_run.py:389-393`).
- Measured on T-0030 round 1, `/repos/personal/uca-t0030/.work/review/T-0030-coord--r8XvAI/`:
  - `out.txt` (8262 bytes) holds one raw U+2028 at character 2871. `str.splitlines` gives 33 lines against 32 `\n`.
  - `out.corrected.txt` (8265 bytes) spells it as the six characters ` ` and parses.
  - That scratch directory has no `codex-events.jsonl` and no `stderr.txt`. `review_run.py` writes both beside `out.txt` on the Codex path (`plugin/crew/hooks/scripts/review_run.py:389`, `:396-397`), so this `out.txt` was not written by `review_run.py`.
  - Whether its bytes were retyped (direction.md's claim) is **not verified**. The measured cause of the INCOMPLETE is the U+2028 split.
- The same defect is recorded in `.work/followups.md:22` (T-0030 r1 FIX), with the repro "Feed review_run's parser an out.txt line 'FIX|a.py:1|text with a U+2028 inside|repro'".
- The Claude fallback's output reaches the verdict only through a file the session writes. `plugin/crew/commands/review.md:464` says `# ... dispatch crew:reviewer; write its output to $SCRATCH/out.txt ...`, and `plugin/crew/hooks/scripts/review_run.py:429` reads it with `_read` (`:88-90`, text mode, universal newlines).
- `review.json` is built at `plugin/crew/hooks/scripts/review_run.py:328-341` and records no hash of the output it judged. `_write_atomic` (`:109-114`) writes UTF-8 with `newline="\n"`, so the bytes on disk are exactly `output.encode("utf-8")`.
- The shared review prompt is in `plugin/crew/commands/review.md:407-425`. Its check list (`:411-413`) has no evidence category. `plugin/crew/agents/reviewer.md:45-51` is the reviewer's own hunt list, and `:78-86` is its output contract.
- `plugin/crew/.budget-allowance.json` pins `commands/review.md` at `"lines": 551`, and `wc -l` gives 551. `plugin/crew/BUDGETS.md` says growth past the allowance "is a hard fail".
- Agent report templates today:
  - `plugin/crew/agents/explorer.md:55-61` ends at `**Not checked:**`.
  - `plugin/crew/agents/researcher.md:96-97` has `**Unverified:**` and `**Not checked:**`, and `:74` and `:109` name the Unverified block.
  - `plugin/crew/agents/security.md:143-148` is BLOCKING / SHOULD FIX / NOTE with no not-verified section.
  - `grep -rn -i "not verified"` over `plugin/crew/agents` returns nothing. The direction's "most already do" holds for this harness's subagents, not for crew's.
- `plugin/crew/commands/done.md:59-80` ("On all four passing") has no report step. `plugin/crew/commands/debug.md:70-93` ("## 4. Report") has "Evidence read" and "Confidence", but no "Not verified".
- `plugin/crew/hooks/scripts/_test/validate-prompts.py` checks frontmatter, tools, references and model tier (`:181`, `:232`, `:287`, and `main` at `:316-331`). It checks nothing about report content. Verify rule 12 (`.crew/verify.json`, paths `plugin/crew/commands/**`, `plugin/crew/agents/**` and `plugin/crew/skills/**`) runs it.
- A prior decision that was not looked up: `plugin/crew/hooks/scripts/_test/validate-prompts.py:97-104` records the owner's 2026-09-24 decision to put explorer on opus ("see CHANGELOG.md's 1.0.9 entry"). A planner proposed reversing it without citing it (direction.md, Evidence).
- `plugin/crew/skills/crew-plan/SKILL.md:60-72` is the self-review, with four items and no recorded-decision check. `plugin/crew/skills/crew-brainstorm/SKILL.md:39-43` is the approaches step.
- `plugin/crew/skills/crew-best-practices/SKILL.md:3` is the description, the always-loaded text. `:60-74` holds the rules, with no verification rule.
- Line budgets. Commands are capped at `MAX_LINES = 120` (`plugin/crew/tests/test_lifecycle_commands.py:28`). `wc -l` gives `done.md` 80, `debug.md` 111 and `autopilot.md` 120.
- `plugin/crew/tests/sabotage.py` is 3381 lines. It imports `REVIEW_FIX_MUTATIONS` at `:69` and concatenates it at `:3050`.
- Docs that describe what changes:
  - `plugin/crew/README.md:731-739` (the verdict table and review.json fields) and `:2505-2515` (the Agents table).
  - `docs/guides/crew/src/troubleshooting.md:116-117` (round outcomes) and `docs/guides/crew/src/working-with-codex.md:64`.
  - `.crew/codemap/crew.md:929` (the review pipeline) and `docs/diagrams/process-crew-lifecycle.mmd:102` (the verdict exit codes).
  - `plugin/PLUGINS.md:14` (the version claim).
- No `.crew/verify.json` rule names `review_verdict.py` or `review_run.py` by path. Only rule 0 (`plugin/**`, check-marketplace) and rule 15 (`**/*.py`, lint) reach them.
- `docs/guides/crew/src/build.py:1-12` renders through LibreOffice, and `/usr/bin/soffice` is present on this host.

## Unknowns
- T-0028 (approved, owned by another agent) also edits `review_verdict.py` (a Kimi stream parser), `review.md` and `validate-prompts.py`. Resolution: implement on origin/main, and merge origin/main before review. If T-0028 has landed, its stream parser is switched to the same ASCII-line helper and gets its own U+2028 test in this ticket. A conflict that changes behaviour is a STOP.
- Other in-flight tickets edit `review.md` (T-0060 and the autopilot tickets). Resolution: each edit here is line-neutral, and `test_lifecycle_commands.py` plus `check_instructions.py` assert the 551 ceiling after the merge.
- Whether Codex's JSONL ever carries a raw U+2028 inside a JSON string: not verified. Accepted as risk. Splitting JSONL on `\n` is correct either way, and the test feeds a raw U+2028 inside a JSON string.
- Whether T-0030 round 1's `out.txt` was retyped: not verified (see Evidence). Accepted. The `output_sha256` in review.json covers the retype case from now on, and the parser fix covers the U+2028 case.
- Whether a lone `\r` should still split. Resolution: yes, `\n`, `\r\n` and a bare `\r` are the ASCII breaks. A test pins that set against `str.splitlines`'s full set, as T-0069's route test does.
- Always-loaded injection through `crew_context.py`: an open question for the owner. The recommendation is a separate ticket. The acceptance here does not depend on it.

## Touch
- `plugin/crew/hooks/scripts/review_verdict.py` - ASCII-only line splitting for parse and the Codex stream
- `plugin/crew/hooks/scripts/review_run.py` - output_sha256 and output_source in review.json
- `plugin/crew/hooks/scripts/_test/validate-prompts.py` - Not verified and claims-category checks
- `plugin/crew/agents/explorer.md`
- `plugin/crew/agents/researcher.md`
- `plugin/crew/agents/security.md`
- `plugin/crew/agents/reviewer.md`
- `plugin/crew/commands/review.md` - line-neutral edits only
- `plugin/crew/commands/done.md`
- `plugin/crew/commands/debug.md`
- `plugin/crew/skills/crew-best-practices/SKILL.md`
- `plugin/crew/skills/crew-plan/SKILL.md`
- `plugin/crew/skills/crew-brainstorm/SKILL.md`
- `plugin/crew/tests/test_review_verdict.py`
- `plugin/crew/tests/test_review_output_integrity.py` - new
- `plugin/crew/tests/test_verify_before_stating.py` - new
- `plugin/crew/tests/sabotage_review.py`
- `plugin/crew/BUDGETS.md` - re-measured Markdown line total
- `plugin/crew/README.md`
- `plugin/PLUGINS.md`
- `docs/guides/crew/**` - src/*.md plus the rebuilt HTML, DOCX and PDF
- `.crew/codemap/**`
- `docs/diagrams/**`
- `.claude/rules/**` - regenerated only if a codemap refresh changes a note
- `.crew/verify.json`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

## Acceptance checks
- [ ] Unicode separators are content. `test_review_verdict.py::test_parse_unicode_line_separators_are_content` is parametrised over every character `str.splitlines` breaks on other than `\n` and `\r` (U+000B, U+000C, U+001C, U+001D, U+001E, U+0085, U+2028, U+2029). The set is derived at test time and pinned. `FIX|a.py:1|text with a <sep> inside|repro` then parses as one FIX, with verdict FINDINGS. (new rule, see the last check)
- [ ] Neighbour case: the ASCII breaks still split. `test_parse_ascii_line_breaks_still_split` feeds `READ|p\r\nCLEAN`, `READ|p\rCLEAN` and `READ|p\nCLEAN` with part `p`, and each is CLEAN. `test_parse_garbage_is_incomplete` and the rest of `test_review_verdict.py` stay green.
- [ ] The Codex stream. `test_codex_final_message_keeps_a_unicode_separator_inside_a_message`: a completed stream whose agent message holds a raw U+2028 inside its JSON string (`json.dumps(..., ensure_ascii=False)`) returns that message whole and `error is None`. The neighbour, `test_codex_final_message_an_unparseable_event_line_is_an_error`, stays red on garbage.
- [ ] End to end. `test_review_output_integrity.py::test_claude_round_with_a_u2028_finding_is_findings_not_incomplete`: `review_run.py --provider claude` over an `out.txt` holding READ lines plus a FIX line with a raw U+2028 exits 1 (FINDINGS), not 3.
- [ ] The output hash. `test_review_json_records_the_output_sha256_claude` and `test_review_json_records_the_output_sha256_launched`: after a Claude round and after a fake-Codex round (`review_fixtures.fake_reviewer_bin`), `review.json` has `output_sha256` equal to the sha256 of `out.txt`'s bytes on disk, and `output_source` equal to `handed` or `launched`. `test_output_sha256_changes_when_out_txt_is_edited` rewrites one character after the round, and the file's sha256 no longer matches the recorded value. `test_missing_output_records_no_hash`: an `--output` that does not exist records `output_sha256` None, never the hash of empty bytes. `test_review_ledger.py` and `test_review_receipt.py` stay green, so the receipt and ledger are unchanged.
- [ ] Prompts carry the rule. `test_verify_before_stating.py::test_every_agent_carries_the_rule` covers all 4 agents plus `crew-best-practices/SKILL.md`, which each contain `Verify before you state` and `could not tell`. `test_free_form_agents_report_not_verified` checks that explorer, researcher and security each have a `**Not verified` section in their report template. `test_reviewer_contract_is_unchanged` checks that reviewer.md's Output section still names exactly `BLOCK, FIX or NIT`, `READ|` and `CLEAN`, and that it tells the reviewer to write `not reproduced:` in the repro field. (rule 12)
- [ ] Claims without evidence is a FIX category. `test_claims_without_evidence_in_prompt_and_reviewer` checks that `review.md`'s heredoc (between `cat > "$SCRATCH/prompt.txt" <<EOF` and `EOF`) and `reviewer.md`'s hunt list both contain `claims without evidence` next to `FIX`. `test_review_md_stays_at_its_allowance` checks that `review.md` is at most 551 lines. (rule 12)
- [ ] Copy, don't retype. `test_claude_path_says_copy_the_bytes`: `review.md`'s Claude fallback line says to write the subagent's returned text to `$SCRATCH/out.txt` unedited and never re-typed. `reviewer.md` does not gain Write. (rule 12)
- [ ] Reports list what was not verified. `test_done_and_debug_report_not_verified`: `done.md` has a report step with `**Not verified:**` that names a rule that exited 77, a suite that did not run on this OS, and `drift-detection.sh`, which is skipped by default. `debug.md`'s `## 4. Report` has a `**Not verified**` bullet. Both stay within 120 lines. (rules 12, 25)
- [ ] Prior decisions. `test_plan_and_brainstorm_look_up_prior_decisions`: `crew-plan/SKILL.md`'s self-review has a fifth item. A step that changes recorded behaviour cites where the decision is recorded (CHANGELOG, `docs/adr/`, a `direction.md`) or says none was found. `crew-brainstorm/SKILL.md`'s approaches step says the same. (rule 12)
- [ ] Enforced by `validate-prompts.py`. It gains `check_verification_rule()`, called from `main`. `test_verify_before_stating.py::test_validate_prompts_fails_without_not_verified` copies `plugin/crew/{agents,commands,skills,hooks/scripts/_test}` to a tmp tree, removes explorer's `**Not verified` line, runs the copy, and expects exit 1 with a message naming `explorer.md`. Neighbours: `test_validate_prompts_fails_when_done_loses_not_verified`, `test_validate_prompts_fails_without_claims_category` and `test_validate_prompts_fails_without_the_rule`. `test_validate_prompts_passes_on_the_real_tree`. `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)` exits 0. (rule 12)
- [ ] Sabotage. New entries appended to `REVIEW_FIX_MUTATIONS` in `plugin/crew/tests/sabotage_review.py`, each going RED on its named test:
  - `parse` back to `splitlines()`
  - `codex_final_message` back to `splitlines()`
  - the ASCII helper stops splitting on a bare `\r`
  - `output_sha256` dropped from review.json
  - a missing output hashed as empty bytes
  - `check_verification_rule()` not called from `main`
  - explorer's `**Not verified` line removed
  - `claims without evidence` removed from the review.md heredoc

  `python3 plugin/crew/tests/sabotage.py` reports each one RED. (rule 9)
- [ ] Docs, per project CLAUDE.md:
  - README's verdict table and review.json field list (`plugin/crew/README.md:731-739`), and its Agents table (`:2505-2515`), gain the Not verified report and the rule.
  - `docs/guides/crew/src/troubleshooting.md` gets a row for the U+2028 INCOMPLETE and its fix, and `working-with-codex.md:64` gets the stream note. The outputs are rebuilt by `docs/guides/crew/src/build.py`.
  - `.crew/codemap/crew.md` and `docs/diagrams/process-crew-lifecycle.mmd` are refreshed until `crew_refresh_check.py` reads `fresh`.
  - `BUDGETS.md` is re-measured.
  - `python3 scripts/check-marketplace.py` passes. (rules 0, 1, 2, 24)
- [ ] Version and mapping:
  - crew is bumped one past origin/main's version at implement time, in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`, with a CHANGELOG entry. The entry names the parser change as a behaviour change: a Unicode separator is content, no longer a line break.
  - `.crew/verify.json` gains one rule, appended at the end, that maps `review_verdict.py`, `review_run.py`, `test_review_verdict.py`, `test_review_output_integrity.py`, `test_verify_before_stating.py` and `sabotage_review.py`. It runs `python3 -m pytest` over those tests plus `test_review_ledger.py` and `test_review_receipt.py`.
  - `python3 -m pytest plugin/crew/tests -q -p no:cacheprovider` is green. (rules 0, 9, new)
