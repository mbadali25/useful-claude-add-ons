# L-0530: crew_tracker names an INDEX status crew does not know (and the crew word for a retired one) instead of reporting `expects None`          status: spec   risk: low
Reshaped from the seed ("map merged/approved/new/land-blocked to lanes") by the owner rule of 2026-10-05: INDEX
statuses are crew-known only. Written against origin/main `a555ff37` (crew 1.1.0). See direction.md for why.

## Intent
`crew_tracker.py` keeps its ten-word vocabulary and every refusal, and gets better at saying what is wrong when
an INDEX cell holds a word outside it. A new `RETIRED_STATUSES` table (`approved -> spec`, `merged -> done`,
`closed -> done`, `new -> direction`, `parked -> needs-owner`) supplies a text-only hint. Three places use it:
- `read` (obsidian kind): an INDEX status not in `LANE_FOR_STATUS` gives `disagree: "could not tell"` (the
  module's `COULD_NOT_TELL`), and the note `INDEX status <s> is not a status crew knows (direction, ready,
  needs-owner, spec, planned, in-progress, review, done, cancelled, superseded)`, plus `; the crew word is <w>`
  for a retired word. It no longer prints `expects None`. A known status reads exactly as today.
- `move --to <s>` with `<s>` retired: the existing refusal `status <s> maps to no lane` gains `; the crew word
  is <w>`. Nothing is written, same exit 1.
- `move` from a retired current status: the existing `_backwards` "could not tell whether ..." refusal gains the
  same hint. `--reopen` still overrides as today.
A hint is never applied: no write, no lane and no exit code comes from `RETIRED_STATUSES`.

## Exclusions
- No new row in `LANE_FOR_STATUS`, `STATUS_ORDER`, `OWNER_STATUSES` or `CLOSED_STATUSES`. No status is mapped to
  a lane that is not mapped today (owner rule 2026-10-05).
- No hint for `land-blocked` or any other word: no owner decision maps it.
- No rewrite of `.work/INDEX.md` by any command (no `normalize` subcommand); the 2026-10-05 data fix is done.
- No change to jira/sdp push behaviour (`_PUSH_AT`), files-kind `read` output (it reports the cell verbatim
  already), board parsing, or exit codes.
- No edit to `plugin/crew/tests/sabotage*.py` (harness path, T-0087). The sabotage entries (drop the
  `could not tell` branch in read; apply a hint as a write) are a separate tooling-only follow-up ticket.
- No other harness path: `crew_tracker.py` is not in `HARNESS` or `SEAM` (`scripts/check-tooling-pr.py:58`, `:89`).

## Evidence
origin/main `a555ff37`:
- Vocabulary: `STATUS_ORDER` `plugin/crew/hooks/scripts/crew_tracker.py:100`, `OWNER_STATUSES` `:101`,
  `CLOSED_STATUSES` `:102`, `LANE_FOR_STATUS` `:103-114` (ten words; T-0037 added the last three).
  Module docstring on the vocabulary and the unknown-word refusal `:34-40`.
- `read`'s board half `_obsidian_read` `:1510`: `expected = settings["columns"].get(LANE_FOR_STATUS.get(status,
  ""), None)` `:1526`, `disagree = card["lane"] != expected` `:1527`, note `INDEX status {status} expects
  {expected}` `:1528` - for an unknown word `expected` is `None`, so every card "disagrees" and the note says
  `expects None`, the line the seed quotes (crew 1.0.75, 52 tickets).
- `move` refusal `status {status} maps to no lane` `:1572-1573`; `_backwards` unknown-current refusal
  "could not tell whether {current} -> {status} goes backwards ({current!r} is not a status crew knows); pass
  --reopen if the move is meant" `:677-679` (T-0037).
- CLI line format `_line` `:1599-1606` (prints `obsidian: <lane> (<reason>)` for a READ result).
- Tests: `test_read_reports_disagreement` / `test_read_reports_agreement`
  `plugin/crew/tests/test_crew_tracker.py:760-782`; `test_files_move_unknown_status_writes_nothing` `:190-197`;
  `test_the_new_words_are_table_rows` `:2632-2640` pins the vocabulary; `plugin/crew/tests/test_status_vocabulary.py:75-88`
  holds the README, obsidian-sync and guide copies to `LANE_FOR_STATUS`.
- Existing sabotage entry "tracker move accepts a status that maps to no lane" `plugin/crew/tests/sabotage_tracker.py:52-57`.
- Docs that describe the vocabulary: `plugin/crew/commands/obsidian-sync.md:63-74` (table and "Any other status
  maps to no lane ... say which value you found and stop"); `plugin/crew/README.md:940-944` (Ticket statuses);
  `docs/guides/crew/src/memory-and-obsidian.md:269` (lane table); `.crew/codemap/crew.md:1460-1486` (tracker).
- Data, main checkout `.work/INDEX.md` 2026-10-05 (read-only, gitignored): 344 rows, all crew-known.
- Owner rule 2026-10-05 (session memory `index-statuses-crew-known-only`): the five retired words and their
  replacements, as listed in Intent; `merged` is in the rule's never-list and `done` is the closed word.

## Unknowns
- Whether any external consumer reads `read --json`'s `disagree` as a strict boolean. None in the repo (only
  `crew_tracker.py:1530` writes it and `test_crew_tracker.py:772-782` reads it). Taken: the string is acceptable;
  the CHANGELOG entry says the field can now be `"could not tell"`.
- Next free crew version, set at implement time (main is at 1.1.0 on `a555ff37`).

## Size and split
About 20 production lines in `crew_tracker.py` (one dict, one helper for the hint, three call sites), about 8
tests, doc edits in four files. No split.

## Touch
- `plugin/crew/hooks/scripts/crew_tracker.py`
- `plugin/crew/tests/test_crew_tracker.py`
- `plugin/crew/tests/test_status_vocabulary.py` (`RETIRED_STATUSES` disjoint from `LANE_FOR_STATUS`)
- `plugin/crew/commands/obsidian-sync.md` (the "Any other status" paragraph: the read note and hint)
- `plugin/crew/README.md` (Ticket statuses: retired words get a hint, never a lane)
- `docs/guides/crew/src/memory-and-obsidian.md` (beside the lane table)
- `docs/guides/crew/**` - HTML, DOCX and PDF rebuilt by `docs/guides/crew/src/build.py`
- `.crew/codemap/crew.md` (tracker section; re-anchor)
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md` (version)
- `plugin/crew/BUDGETS.md` (only if the .md line counts it tracks move)
- `docs/tickets/L-0530/` (removed in the final PR)

Not in Touch: `plugin/crew/CONFIG.md` (no config key), `commands/jira-sync.md` / `sdp-sync.md` (they map no
INDEX words to lanes), `plugin/crew/tests/sabotage*.py` (follow-up tooling ticket), `docs/diagrams/` (no box
changes; say so in the PR).

## Acceptance checks
`T` is `plugin/crew/tests/test_crew_tracker.py`; run as `python3 plugin/crew/tests/pytest_rule.py T -q -k <name>`.
- [ ] `read` with INDEX status `merged` and the card in Done: obsidian result `disagree == "could not tell"`,
  reason `INDEX status merged is not a status crew knows (direction, ready, needs-owner, spec, planned,
  in-progress, review, done, cancelled, superseded); the crew word is done`; no `expects None` anywhere in the output.
  `-k test_read_retired_status_names_the_crew_word`
- [ ] `read` with `land-blocked` (not retired, not known): same `could not tell` and list, no `the crew word` hint.
  `-k test_read_unknown_status_has_no_hint`
- [ ] Known statuses read unchanged: `test_read_reports_disagreement` and `test_read_reports_agreement` pass unedited.
  `-k "test_read_reports_disagreement or test_read_reports_agreement"`
- [ ] `move --to approved`: exit 1, `files: could not update: status approved maps to no lane; the crew word is
  spec`, INDEX and board byte-identical. `-k test_move_to_retired_status_hints_and_writes_nothing`
- [ ] `move` from INDEX `new` to `spec` without `--reopen`: refused with the existing could-not-tell text plus
  `; the crew word is direction`, nothing written; with `--reopen` it moves as today.
  `-k test_move_from_retired_status_hints`
- [ ] No hint changes a lane, a write or an exit code: parametrised over the five retired words for `move --to`
  and `read`, the state and exit match an unknown word's. `-k test_retired_hint_is_text_only`
- [ ] `RETIRED_STATUSES` keys are disjoint from `LANE_FOR_STATUS` and every value is a `LANE_FOR_STATUS` key;
  `test_the_new_words_are_table_rows` passes unedited (vocabulary unchanged).
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_status_vocabulary.py -q`
- [ ] Full tracker suites: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_tracker.py plugin/crew/tests/test_status_vocabulary.py plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] `grep -rn "expects None" plugin/ docs/guides/crew/src/` is empty.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` (no harness path).
- [ ] Docs: obsidian-sync.md, README, the guide source and `.crew/codemap/crew.md` describe the not-crew-known
  note and the retired-word hint; guides rebuilt (`python3 docs/guides/crew/src/build.py`); crew bumped to the
  next free patch with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0037 (#394, merged): the ten-word vocabulary and the unknown-current refusal this builds on.
- Follow-up (to be minted by the orchestrator): tooling-only sabotage entries for the new read branch and the
  text-only hint. Not blocking.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
