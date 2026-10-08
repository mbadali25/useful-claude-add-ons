# L-0642 autopilot's open-questions stop sees through code fences, and stops when it cannot tell          status: spec   risk: high
Split from T-0043 (2026-10-04). A complete ticket on its own; it is filed as L-0642.
## Intent
`crew_autopilot.py`'s `_open_items` no longer loses the items that follow a fenced block under an Open-questions heading. Main's parser stays as the floor, a strict column-0 fence view adds the items main misses, and a fence shape the parser cannot read with certainty stops the ticket as "could not tell" instead of reading as "no questions". The `open-questions` human stop can therefore only gain stops relative to main, never lose one.
## Exclusions
- No CommonMark emulation: no list-nesting, indentation or container rules. A fence that is not at column 0 is never tracked, only reported.
- No edit to any file matching `HARNESS` in `scripts/check-tooling-pr.py`, in particular not `plugin/crew/tests/sabotage_autopilot.py`. The committed mutations are L-0643. The existing anchor `    if questions:\n` stays byte-identical and unique.
- No change to `_ANSWERED`, `_BULLET` or `_HEADING`, to what counts as an answered item, to the stop's phase, or to the questions policy (`question_policy`, `questions-check`).
- No change to the three files `_open_questions` reads, and no new stop id.
- No markdown dependency. `crew_autopilot.py` stays standard-library only.
- No other parser in this ticket. The FINDINGS-stop fixes are T-0043's.
## Evidence
All line numbers are origin/main at `155fe6d8`, read on 2026-10-04. Nothing was executed for this spec; the measurements quoted are from T-0043's 2026-09-27 prototype and are re-run by the plan.
- The parser: `_BULLET` `plugin/crew/hooks/scripts/crew_autopilot.py:294`, `_HEADING` `:295`, `_ANSWERED` `:299`, `_open_items` `:302-328`. It loops over `splitlines()` and matches `_HEADING` on every line (`:308`); there is no fence state. A heading at the same or a higher level ends the section (`:315-316`).
- The fail-open: for a level-2 Open-questions heading followed by a fence, the line `# how to check`, the closing fence, then `- which DB?`, the `#` line is read as a level-1 heading and sets `depth = 0`, so the bullet is skipped at `:317-318`. Expected result on main: an empty list.
- What main already catches: with no `#` line in the block, the fence line and the block's lines are themselves returned as items (`:319-327`: a bare fence strips to backticks, which `strip("\"'`.: ")` at `:324` reduces to empty, but a fence with an info string and each body line survive). So an answered item followed by a fenced example stops on main today. The floor keeps that.
- The consumer: `_open_questions` `:331-336` reads direction.md, spec.md and plan.md; `next` stops at `:447-452` and quotes the first four items in the reason, followed by the policy hint (`_question_hint` `:1123-1126`).
- Existing tests: `test_next_open_questions_stop` `plugin/crew/tests/test_crew_autopilot.py:571-580`, `test_next_answered_open_questions_do_not_stop` `:583-591`, `test_next_open_question_that_only_looks_answered_stops` `:594-606`, `test_next_open_questions_section_ends_at_the_next_peer_heading` `:609-614`. All must pass unchanged.
- Other tests that drive the stop: `plugin/crew/tests/test_crew_autopilot_policy.py:420`, `plugin/crew/tests/test_crew_autopilot_status.py:1161`, `plugin/crew/tests/test_crew_autopilot_assign.py:237`.
- The anchor rule: `test_every_autopilot_sabotage_anchor_is_present_exactly_once` (`test_crew_autopilot.py:1336-1351`); the mutation "open questions do not stop" finds `    if questions:\n` (`plugin/crew/tests/sabotage_autopilot.py:74-77`).
- The two round-2 findings this design answers are recorded on main in `plugin/crew/tests/golden/review/uca-t-0043--T-0043-build--amK3nW/out.txt:23-24`, and round 1's in `plugin/crew/tests/golden/review/uca-t-0043--T-0043-build--7JfxKM/out.txt:18-19`. Those files are harness goldens: read them, do not edit them.
- Docs that describe the stop: `plugin/crew/README.md:888` (the `next` table's open-questions row) and the module docstring's phase table row `crew_autopilot.py:67`.
- The tooling-PR rule: `scripts/check-tooling-pr.py:58-88` (`HARNESS`), `:89-95` (`SEAM`).
- Verify rule: `.crew/verify.json:348-359`, `seconds` 9 at `:355`.
- Prototype measurements, 2026-09-27, to be re-measured: the generated corpus is 68,040 texts and runs in about 1.5 s; 0 floor violations; over 158 real ticket files, 41 stop under main and the same 41 under the new parser.
## Unknowns
- The cost on today's ticket corpus. Resolved before review by a scratch script (not committed; ticket files are untracked) that runs main's and the new `_open_items` over every ticket markdown file available and reports files, stops under each, and every file that newly stops. Any newly stopping file is listed in the PR body.
- The corpus test's wall time inside the 9-second verify rule. Resolved by measuring the rule three times and setting `seconds` to the slowest run rounded up, with the `why` updated; if the corpus pushes the rule past 20 seconds, cut the product (fewer closer and indent variants) rather than marking the test slow.
- Whether a could-not-tell item may be handled by the `autopilot.questions: self` route. Decided: yes, no special case; listed for the owner in direction.md.
- Version number: resolved at land, one patch above origin/main's crew version.
- Sabotage evidence until L-0643 lands: by hand in a scratch copy, quoted in the PR body. Accepted as risk.
- T-0043 edits the same two files. Resolved by landing T-0043 first and merging main in (merge commit, never rebase).
## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/README.md`
- `plugin/crew/commands/autopilot.md` - only if it describes what counts as an open question; keep it at 120 lines or fewer
- `plugin/crew/BUDGETS.md` - only if a recorded line count moves
- `.crew/verify.json` - the rule's seconds and why, re-measured
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `.crew/codemap/**` - refresh only
- `.claude/rules/**` - refresh only
- `docs/diagrams/**` - refresh only
- `graphify-out/**` - refresh only, built with graphify update
## Acceptance checks
Design, fixed by this spec: `_legacy_open_items(text)` is main's `_open_items` body unchanged. `_fence_view(text)` returns `(items, unclear_line)` under the strict rule: outside a fence, a line whose `lstrip()` starts with three or more backticks or tildes opens a fence only at column 0 and, for backticks, with no backtick in its info string; inside a fence, such a line closes it only at column 0, same marker, at least as long, nothing after the run; every other fence-shaped line sets `unclear_line` (first one wins) and changes no state; text ending inside a fence sets `unclear_line` to the opener; lines inside a tracked fence are neither headings nor items; a fence that opens inside a section before any item line adds the item `UNEXPLAINED_FENCE`. `_names_open_questions(text)` is true when any line's `lstrip()` is a heading whose title starts with "open questions", fenced or not. `_open_items(text)` returns the legacy items, then the view's items not already present, then one `UNCLEAR_FENCE` item naming the 1-based line when `unclear_line` is set and `_names_open_questions` is true.

Suite command, verify rule `.crew/verify.json:348-359`'s scope: `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_lifecycle_commands.py -q -p no:cacheprovider`. Write each test first and record it red.
- [ ] Must-stop, the original finding: `test_open_questions_after_a_fence_with_a_hash_line_stop`. A section holding a column-0 fence with a `#` line inside, then `- which DB?`, returns exactly `["which DB?"]`, and `next` gives phase `open-questions`, stop true. The same text with tilde fences does too (`test_open_questions_tilde_fence_is_a_fence`).
- [ ] Must-stop, round 2's two repros, as `next` results (`open-questions`, stop true) with "which DB?" among the items: `test_open_questions_round2_indented_closer_repro_stops` (a column-0 fence whose first closer-shaped line is indented 4 spaces, the real closer, then the section) and `test_open_questions_round2_list_nested_fence_repro_stops` (a 2-space-indented, never-closed fence under a list item, then the section).
- [ ] Must-stop, could not tell: `test_open_questions_ambiguous_fence_could_not_tell`, parametrised, each case's result holding an item that starts with `crew_autopilot.UNCLEAR_FENCE`. Cases: an indented closer inside the section; a list-nested fence pair before an answered section; an unclosed fence after an answered section; a tab-indented opener; inline backticks on a fence line; a shorter run inside a longer fence; a section heading that exists only inside an indented fence.
- [ ] Must-stop, the floor: `test_open_questions_fence_corpus_never_below_main`. The test file holds a verbatim, never-edited copy of main's `_BULLET`, `_HEADING`, `_ANSWERED` and `_open_items` at `155fe6d8` (named `_MAIN_*`, with the commit in a comment). A generator builds the corpus from `itertools.product` over opener, opener indent, closer, closer indent, lead-in, fenced body, position and section tail, plus both round-2 repros verbatim, and computes `clean` from the parameters, never by parsing. For every text, each item of the frozen parser is in `_open_items(text)`; every text that is not clean and names an Open-questions section returns non-empty. Non-vacuity asserts: the corpus holds both repros, at least one text stops where main does not, and at least one clean text returns an empty list.
- [ ] Must-allow: `test_open_questions_clean_fences_do_not_stop` returns an empty list for an answered section followed by a clean column-0 fenced block with a `#` line, for a clean fenced block before an answered section, and for a clean tilde block before an answered section. `test_open_questions_ambiguous_fence_without_a_section_does_not_stop` returns an empty list for an indented fence pair, and for an unclosed fence, in a file with no Open-questions line.
- [ ] Unchanged behaviour: the four existing tests at `test_crew_autopilot.py:571-614` and the policy, status and assign tests named in Evidence pass without edits. `grep -c '^    if questions:$' plugin/crew/hooks/scripts/crew_autopilot.py` prints 1 and `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py -q -p no:cacheprovider -k sabotage_anchor` passes.
- [ ] Hand sabotage in a scratch copy (`git archive HEAD plugin/crew | tar -x -C <scratch>`), each quoted in the PR body with the test that went red: dropping the legacy items from the union; making the `UNCLEAR_FENCE` append unreachable; dropping the column-0 opener check; dropping the column-0 closer check; removing the end-of-text check; removing the `lstrip()` in `_names_open_questions`; and, on the must-allow side, forcing `_names_open_questions` true.
- [ ] `git diff --name-only origin/main...HEAD` lists no path matching `HARNESS`; `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] Docs: `plugin/crew/README.md`'s open-questions row and the `_open_items` docstring state the floor, the column-0 rule and the could-not-tell stop, and tell the reader to put fences at column 0 and close each one. Neither describes CommonMark. `CHANGELOG.md` has an entry under Unreleased with the measured test count and corpus size. `.crew/verify.json`'s rule carries the re-measured `seconds` and a dated `why`.
- [ ] The cost measurement from Unknowns is in the PR body: files read, stops under main, stops under the new parser, and each newly stopping file.
- [ ] Land: crew is one patch above origin/main in `plugin.json`, `marketplace.json` and `plugin/PLUGINS.md`; `python3 scripts/check-marketplace.py` passes after commit; `crew_refresh_check.py --root . --ticket <this ticket's id>` says fresh before review; the PR body carries a `Docs:` line, with `Docs: none` reasons for CONFIG.md and the guides under `docs/guides/crew/src/`.
## Dependencies
Must land first:
- T-0004, merged: `_open_items` and the `open-questions` stop.
- T-0010, merged: the questions policy the stop's reason carries.
- T-0087, merged: the tooling-PR rule that keeps the mutations out of this PR.
- T-0043, ready: not a content dependency, but it edits `crew_autopilot.py` and `test_crew_autopilot.py`; land it first so this ticket merges main once.

This ticket blocks:
- L-0643 (sabotage mutations for this parser).
## Size
About 90 added production lines in `crew_autopilot.py` (`_legacy_open_items` about 27, `_fence_view` about 40, `_names_open_questions` about 6, the new `_open_items` and constants about 17). One new parser with one fail-closed rule, which is the whole ticket. About 200 lines of tests. No harness path.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
