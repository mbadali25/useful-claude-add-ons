# T-0041 plan            spec: .work/tickets/T-0041/spec.md

Work in the worktree `/repos/personal/uca-t-0041` on branch `T-0041-build`, created from origin/main at implement time. Copy `.work/tickets/T-0041/` into it and confirm with `cmp`. Anchors are origin/main `bebbb97f` (crew 1.0.46). Re-grep each quoted anchor before its step. T-0028 and T-0060 may land first and move lines. If a line is gone or its meaning changed, stop and re-read. Never re-anchor by guess.

Each step writes its tests first and runs them red, then implements, then runs them green. Heavy runs (pytest over more than one file, sabotage.py, build.py, graphify) go through `/root/crew-tmp/heavy-run <command>` with `TMPDIR=/root/crew-tmp/t-0041`, one at a time. No test reads or writes a real config or a real `.work/`. Every fixture is under `tmp_path`.

The rule text below is used verbatim in Steps 3 and 4. It is called RULE from here on:

> **Verify before you state.** A claim about code, config, history or state is either verified in this session (a `path:line` you read, the command you ran and what it printed, or the ref you measured at) or labelled `not verified` or `inferred`. "Could not tell" is an answer. Never fill the gap with the likely value. Before proposing to change something, look up whether it was already decided (`CHANGELOG.md`, `docs/adr/`, the ticket's `direction.md`) and cite what you found, or say you found nothing. Quoted output, errors and fixtures move by copying the bytes, never by re-typing them.

### Step 1: the verdict parser splits on ASCII line breaks only
Files: plugin/crew/hooks/scripts/review_verdict.py, plugin/crew/tests/test_review_verdict.py
Test: python3 -m pytest plugin/crew/tests/test_review_verdict.py -q -p no:cacheprovider
Risk: med. A helper that stops splitting on `\r` would merge a CRLF reviewer's READ and CLEAN lines into one unparseable line. The neighbour test pins all three ASCII forms.
- [ ] Tests first, in `test_review_verdict.py`:
  - `UNICODE_BREAKS = sorted({c for c in map(chr, range(0x110000)) if len(("a" + c + "b").splitlines()) == 2} - {"\n", "\r"})`.
  - `test_unicode_break_set_is_pinned`: `UNICODE_BREAKS == ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " "]`. A Python release that adds a break fails this test, not silently.
  - `test_parse_unicode_line_separators_are_content`, parametrised over `UNICODE_BREAKS`. `parse(f"READ|p\nFIX|a.py:1|text with a {sep} inside|repro\n", 0, expected_parts=("p",))` returns verdict `FINDINGS`, `counts["FIX"] == 1`, `reasons == []`, and one finding that contains `sep`.
  - `test_parse_ascii_line_breaks_still_split`, parametrised over `"\r\n"`, `"\r"` and `"\n"`. `parse(f"READ|p{brk}CLEAN{brk}", 0, expected_parts=("p",))` is `CLEAN`.
  - `test_codex_final_message_keeps_a_unicode_separator_inside_a_message`. A stream built with `json.dumps(event, ensure_ascii=False)`, whose `item.completed` agent message is `"FIX|a.py:1|x y|r"`, followed by `turn.completed`, returns `("FIX|a.py:1|x y|r", None)`.
- [ ] Run the Test command. The new U+2028-family cases and the Codex case must fail before the change: they come back INCOMPLETE and `unparseable Codex event line`.
- [ ] In `review_verdict.py`, add `_ASCII_BREAK = re.compile(r"\r\n|\r|\n")` and `def _lines(text): return _ASCII_BREAK.split(text or "")`, with a docstring that names T-0030 round 1 and `.work/followups.md:22` as the cause. Replace `(text or "").splitlines()` at `:61` and `(jsonl or "").splitlines()` at `:131` with `_lines(text)` and `_lines(jsonl)`. Add one sentence to the module docstring's contract: lines are split on `\n`, `\r\n` and a bare `\r` only, and every other Unicode line boundary is content.
- [ ] Run the Test command. It must be all green, including the pre-existing `test_codex_final_message_an_unparseable_event_line_is_an_error` (the neighbour: garbage is still an error).

### Step 2: review.json records which bytes were judged
Files: plugin/crew/hooks/scripts/review_run.py, plugin/crew/tests/test_review_output_integrity.py
Test: python3 -m pytest plugin/crew/tests/test_review_output_integrity.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_review_receipt.py plugin/crew/tests/test_review_run_launch.py -q -p no:cacheprovider
Risk: med. A hash taken from the decoded text instead of the file bytes would not match `out.txt` on a CRLF file. The Claude-path test writes CRLF on purpose. A missing output must record `None`, never the hash of an empty string, which would be an unknown collapsing into a safe-looking value.
- [ ] Tests first, in the new `test_review_output_integrity.py`. Reuse `review_fixtures.init_repo`, `review_fixtures.fake_reviewer_bin` and `review_fixtures.env_with_path`, and the bundle-building pattern of `plugin/crew/tests/test_review_receipt.py:134-158`:
  - `test_claude_round_with_a_u2028_finding_is_findings_not_incomplete`. The `out.txt` holds the READ lines for every part plus `FIX|a.py:1|x y|repro`. `--reserve-only`, then `--round 1 --output out.txt --exit-code 0`, exits 1.
  - `test_review_json_records_the_output_sha256_claude`. The `out.txt` is written as bytes with CRLF line endings. `review.json["output_sha256"] == hashlib.sha256(out_txt.read_bytes()).hexdigest()` and `review.json["output_source"] == "handed"`.
  - `test_review_json_records_the_output_sha256_launched`. On a fake-Codex CLEAN round, `output_sha256` equals the sha256 of `<scratch>/out.txt`'s bytes and `output_source == "launched"`.
  - `test_output_sha256_changes_when_out_txt_is_edited`. After the Claude round, replace one character in `out.txt`. Its sha256 no longer equals the recorded value.
  - `test_missing_output_records_no_hash`: `--output` names a file that does not exist. The verdict is INCOMPLETE (empty output), `output_sha256 is None`, and `output_source == "handed"`.
- [ ] Run the Test command. The new tests fail: there is no `output_sha256` key, and the U+2028 case fails until Step 1 is in (it is).
- [ ] In `review_run.py`:
  - Add `def _sha256_file(path)`. It returns the hex digest of the file's bytes, or None when the file does not exist.
  - `finish()` (`:309`) takes `output_path` and `output_source` keyword arguments. The review dict at `:328-341` gains `"output_sha256": _sha256_file(output_path)` and `"output_source": output_source`.
  - `run()` passes `os.path.join(args.scratch, "out.txt")` and `"launched"` after its `_write_atomic` at `:396`.
  - The Claude path at `:429-430` passes `args.output` and `"handed"`.
  - The module docstring's review.json sentence names both fields.
- [ ] Run the Test command. It must be all green. The ledger and receipt suites are unchanged, which shows neither reads the new fields.

### Step 3: the rule and the report sections in crew's prompts
Files: plugin/crew/agents/explorer.md, plugin/crew/agents/researcher.md, plugin/crew/agents/security.md, plugin/crew/agents/reviewer.md, plugin/crew/commands/review.md, plugin/crew/commands/done.md, plugin/crew/commands/debug.md, plugin/crew/skills/crew-best-practices/SKILL.md, plugin/crew/skills/crew-plan/SKILL.md, plugin/crew/skills/crew-brainstorm/SKILL.md, plugin/crew/tests/test_verify_before_stating.py
Test: python3 -m pytest plugin/crew/tests/test_verify_before_stating.py plugin/crew/tests/test_lifecycle_commands.py -q -p no:cacheprovider
Risk: med. `review.md` is at its 551-line allowance, so any net line added fails `test_lifecycle_commands.py` and `scripts/check_instructions.py`. Every review.md edit replaces lines in place, and a test asserts `<= 551`.
- [ ] Tests first, in the new `test_verify_before_stating.py`. These are text-presence tests read from the tracked files. Each assertion message names the file and the missing phrase.
  - `test_every_agent_carries_the_rule`: every `agents/*.md` and `skills/crew-best-practices/SKILL.md` contains `Verify before you state` and, case-insensitively, `could not tell`.
  - `test_free_form_agents_report_not_verified`: `explorer.md`, `researcher.md` and `security.md` each contain `**Not verified`. `researcher.md` no longer contains `**Unverified`.
  - `test_reviewer_contract_is_unchanged`: reviewer.md's `## Output` section still contains `SEVERITY is BLOCK, FIX or NIT`, `READ|<part file name>` and `` `CLEAN` ``, and it contains `not reproduced:`.
  - `test_claims_without_evidence_in_prompt_and_reviewer`: the review.md text between the line `cat > "$SCRATCH/prompt.txt" <<EOF` and the next line equal to `EOF` contains `claims without evidence` and `FIX`. reviewer.md's hunt list, from `Hunt for:` to the next `## `, contains `claims without evidence`.
  - `test_review_md_stays_at_its_allowance`: `len(text.splitlines()) <= json.load(.budget-allowance.json)["plugin/crew/commands/review.md"]["lines"]`.
  - `test_claude_path_says_copy_the_bytes`: the review.md line that contains `dispatch crew:reviewer;` also contains `never re-type`. reviewer.md's frontmatter `tools` has no `Write` or `Edit`.
  - `test_done_and_debug_report_not_verified`: `done.md` contains `**Not verified:**`, `exited 77` and `drift-detection.sh`. The body of `debug.md`'s `## 4. Report` section contains `**Not verified**`. Each file is at most 120 lines.
  - `test_plan_and_brainstorm_look_up_prior_decisions`: `crew-plan/SKILL.md`'s `## Self-review` section has an item `5.` containing `docs/adr/` and `direction.md`. `crew-brainstorm/SKILL.md` contains `docs/adr/` in its `## The method` section.
- [ ] Run the Test command. It must fail on every new test.
- [ ] Edits:
  - `explorer.md`: insert RULE as its own paragraph after the numbered list (after `:53`). Add `**Not verified:** anything above you inferred rather than read or ran, named plainly` after `:61`'s `**Not checked:**`.
  - `researcher.md`: insert RULE after `## Refuse to answer from memory`'s first paragraph. Rename `**Unverified**` to `**Not verified**` at `:74`, `:96` and `:109`.
  - `security.md`: insert RULE before `Output:` (`:143`). Add a line `**Not verified** - what you could not confirm (a precondition, a runtime value, a version you did not fetch), named plainly.` after the NOTE line.
  - `reviewer.md`:
    - insert RULE after the opening paragraph (`:18-19`)
    - add a hunt bullet after `:51`: `- claims without evidence: a comment, doc, CHANGELOG line or test name in the diff that states a fact about code, config, history or a measurement with no path:line, command or ref behind it - a FIX`
    - add to `## Output` one sentence: a finding you could not reproduce says `not reproduced: <why>` in its how-to-reproduce field
  - `review.md`, line-neutral:
    - `:413` becomes `change makes reachable that was not before, every acceptance check, and claims without evidence - a comment, doc or CHANGELOG line in the diff that states a fact about code, config, history or a measurement with no path:line, command or ref behind it is a FIX.`
    - `:464` becomes `# ... dispatch crew:reviewer; Write its returned text to $SCRATCH/out.txt unedited - copy the bytes, never re-type them ...`
    - `wc -l` is still 551.
  - `done.md`: add step 5 under `## On all four passing`, the report. It lists the four checks' results. Then `**Not verified:**` names every verify rule that exited 77 (a missing tool, not a pass), any suite that did not run on this OS, and `drift-detection.sh`, which is skipped by default. It also names anything checked only by reading. It ends with "Nothing" only when that is true.
  - `debug.md`: add a bullet to `## 4. Report` after "Confidence": `**Not verified** - each claim above you inferred rather than reproduced or read at path:line, named plainly.`
  - `crew-best-practices/SKILL.md`:
    - append to the `description` (`:3`): `Also use before stating a fact about code, config, history or state that has not been verified this session.`
    - add a `## Verify before you state` section after `## The rules worth applying` containing RULE
    - add the sentence: the rule is crew's own and is not written into repos crew sets up
  - `crew-plan/SKILL.md`: add self-review item 5, **Recorded decisions**. A step that changes behaviour someone decided (a default, a model tier, a guard) cites where that decision is recorded (`CHANGELOG.md`, `docs/adr/`, a ticket's `direction.md`), or says it searched and found none. It never reverses a recorded decision silently.
  - `crew-brainstorm/SKILL.md`: add to method step 4 (`:39-43`) one sentence with the same lookup, before any option that changes a recorded decision.
- [ ] Run the Test command. It must be all green. `wc -l plugin/crew/commands/review.md` prints 551.

### Step 4: `validate-prompts.py` enforces it
Files: plugin/crew/hooks/scripts/_test/validate-prompts.py, plugin/crew/tests/test_verify_before_stating.py
Test: python3 -m pytest plugin/crew/tests/test_verify_before_stating.py -q -p no:cacheprovider && (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)
Risk: low. The check is a text-presence check. The tmp-tree tests prove it can fail, and the real-tree run proves it passes.
- [ ] Tests first, appended to `test_verify_before_stating.py`. A helper `_tree(tmp_path)` runs `shutil.copytree(CREW, tmp_path / "plugin" / "crew", ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))`. The script `chdir`s to three levels above itself, so it validates the copy. A helper `_run(root)` runs `sys.executable <root>/plugin/crew/hooks/scripts/_test/validate-prompts.py` and returns `(returncode, stdout)`.
  - `test_validate_prompts_passes_on_the_real_tree`: exit 0.
  - `test_validate_prompts_fails_without_not_verified`: remove explorer.md's `**Not verified` line in the copy. Exit 1, and stdout names `explorer.md` and `Not verified`.
  - `test_validate_prompts_fails_when_done_loses_not_verified`: the same for `done.md`.
  - `test_validate_prompts_fails_without_claims_category`: remove `claims without evidence` from the copy's review.md heredoc line. Exit 1, and stdout names `review.md`.
  - `test_validate_prompts_fails_without_the_rule`: remove `Verify before you state` from the copy's `security.md`. Exit 1.
  - `test_validate_prompts_exempts_the_reviewer_report`: the real reviewer.md has no `**Not verified` section, and the real-tree run still exits 0. The exemption is by name, with its reason.
- [ ] Run the Test command. The failure-expecting tests fail, because today the script exits 0 on every copy.
- [ ] In `validate-prompts.py`, add constants beside `MODEL_TIER` (`:104`), each with a comment giving the reason:
  - `RULE_PHRASE = "Verify before you state"`
  - `RULE_FILES = sorted(glob agents/*.md) + ["skills/crew-best-practices/SKILL.md"]`
  - `NOT_VERIFIED_AGENTS = ("explorer", "researcher", "security")`, whose comment explains that reviewer's output is the machine contract `review_verdict.py` parses, so it carries `not reproduced:` in the repro field instead
  - `NOT_VERIFIED_COMMANDS = ("done.md", "debug.md")`
  - `CLAIMS_PHRASE = "claims without evidence"`
- [ ] Add `check_verification_rule()`, printing `=== VERIFICATION RULE ===`. It calls `ok`/`bad` per file for RULE_PHRASE, `**Not verified`, and CLAIMS_PHRASE inside review.md's prompt heredoc and inside reviewer.md. Call it from `main()` after `check_skills()` (`:320`). Run the Test command. It must be all green.

### Step 5: sabotage entries
Files: plugin/crew/tests/sabotage_review.py
Test: /root/crew-tmp/heavy-run python3 plugin/crew/tests/sabotage.py
Risk: low. An entry whose `find` string is not unique, or not present, is reported by the harness as an error, not as RED. Confirm that each new label prints RED, not SKIPPED or ERROR.
- [ ] Append to `REVIEW_FIX_MUTATIONS` in `sabotage_review.py`, in the (label, target, find, replace, test) shape `plugin/crew/tests/sabotage_review.py:15-30` uses. Each `find` is copied from the file as written in Steps 1-4. Update the module docstring to say T-0041's entries live here too, because `sabotage.py` sits at 3381 of 3400 lines. The entries:
  - "the verdict parser splits on Unicode line breaks again": target `review_verdict.py`, `for raw in _lines(text):` -> `for raw in (text or "").splitlines():`, test `tests/test_review_verdict.py::test_parse_unicode_line_separators_are_content`.
  - "the Codex stream splits on Unicode line breaks again": `for line in _lines(jsonl):` -> `for line in (jsonl or "").splitlines():`, test `tests/test_review_verdict.py::test_codex_final_message_keeps_a_unicode_separator_inside_a_message`.
  - "a bare carriage return no longer splits": `r"\r\n|\r|\n"` -> `r"\r\n|\n"`, test `tests/test_review_verdict.py::test_parse_ascii_line_breaks_still_split`.
  - "review.json loses output_sha256": the `"output_sha256": _sha256_file(output_path),` line -> `"output_sha256": None,`, test `tests/test_review_output_integrity.py::test_review_json_records_the_output_sha256_claude`.
  - "a missing output is hashed as empty": `_sha256_file`'s `return None` -> `return hashlib.sha256(b"").hexdigest()`, test `tests/test_review_output_integrity.py::test_missing_output_records_no_hash`.
  - "validate-prompts stops checking the rule": `    check_verification_rule()\n` -> `\n`, test `tests/test_verify_before_stating.py::test_validate_prompts_fails_without_not_verified`.
  - "explorer loses its Not verified line": the explorer.md `**Not verified:**` line -> empty, test `tests/test_verify_before_stating.py::test_free_form_agents_report_not_verified`.
  - "the review prompt drops claims without evidence": in review.md `, and claims without evidence` -> `` (empty), test `tests/test_verify_before_stating.py::test_claims_without_evidence_in_prompt_and_reviewer`.
- [ ] Run the Test command. Every new label is RED. The non-RED count equals origin/main's count at the same run, with no new non-RED entry. Record both counts in the commit message.

### Step 6: verify map, docs, version, refresh, gate
Files: .crew/verify.json, plugin/crew/README.md, docs/guides/crew/**, plugin/crew/BUDGETS.md, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, .crew/codemap/**, docs/diagrams/**, .claude/rules/**
Test: python3 scripts/check-marketplace.py && /root/crew-tmp/heavy-run python3 -m pytest plugin/crew/tests -q -p no:cacheprovider && python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0041
Risk: med. A version bump not set last is overtaken by whatever lands first. Re-read origin/main's crew version immediately before bumping, and set it one past. A doc sentence that restates the parser rule wrongly is itself a claim without evidence, so every new sentence carries its `path:line`.
- [ ] `.crew/verify.json`: append one rule at the end. Its paths are `plugin/crew/hooks/scripts/review_verdict.py`, `plugin/crew/hooks/scripts/review_run.py`, `plugin/crew/tests/test_review_verdict.py`, `plugin/crew/tests/test_review_output_integrity.py`, `plugin/crew/tests/test_verify_before_stating.py` and `plugin/crew/tests/sabotage_review.py`. Its command is `python3 -m pytest plugin/crew/tests/test_review_verdict.py plugin/crew/tests/test_review_output_integrity.py plugin/crew/tests/test_verify_before_stating.py plugin/crew/tests/test_review_ledger.py plugin/crew/tests/test_review_receipt.py -q`. Existing indices do not move.
- [ ] `plugin/crew/README.md`:
  - the verdict section (`:731-739`) gets one sentence, with `review_verdict.py`'s line cited: lines split on `\n`, `\r\n` and a bare `\r` only
  - its review.json field list adds `output_sha256` and `output_source`
  - the Agents table (`:2505-2515`) gets a sentence: every agent carries the verify-before-you-state rule; explorer, researcher and security reports end with **Not verified**; the reviewer marks `not reproduced:` and treats claims without evidence as a FIX
- [ ] `docs/guides/crew/src/troubleshooting.md`: add a row. Symptom: a round is INCOMPLETE with "match no part of the contract" on a finding that quotes U+2028. Cause: crew before this version split on Unicode line breaks. Fix: upgrade. The round is spent, so accept or replan. `working-with-codex.md:64`: one sentence saying the event stream is split on `\n` only. Rebuild with `/root/crew-tmp/heavy-run python3 docs/guides/crew/src/build.py`. Confirm the rebuilt HTML, DOCX and PDF for those two guides changed and are non-empty (`ls -l`, then `file`).
- [ ] Re-measure `plugin/crew/BUDGETS.md`'s `<!-- claim: crew-markdown-lines -->` figure with `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` after all Markdown edits.
- [ ] Version: `git show origin/main:plugin/crew/.claude-plugin/plugin.json`, then bump to the next patch in `plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md:14`. Add a CHANGELOG `[Unreleased]` entry naming T-0041. It states the behaviour change: a Unicode line separator in reviewer output is content, not a line break. It also names the new review.json fields.
- [ ] Commit. Then run `crew_refresh_check.py --root . --ticket T-0041`, run each command a `stale` line names (codemap `/crew:onboard --refresh crew`, diagrams, and `crew_instructions.py rules` if a note changed), commit, and re-run until every line is `fresh`. An `unknown` with `stop` is a STOP, reported verbatim.
- [ ] Run the Test command. It must be all green: `check-marketplace` "all checks passed", pytest with 0 failed, refresh `fresh`. Report which suites ran, and that `scripts/_test/drift-detection.sh` did not run (skipped by default; this ticket does not touch the plugin update path).
