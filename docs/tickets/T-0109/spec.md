# T-0109 review_ledger: an owner-attributed rejection supersedes an accepted receipt          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket; there was no earlier spec or plan. Written against origin/main `155fe6d8` (crew 1.0.322) from direction.md and its "Direction check 2026-10-04". The owner was not available, so the recommended option (1: an explicit `--supersede-accepted` flag on `--reject`) is taken; the four open questions are repeated under Unknowns. No plan.md exists.

## Design (for the owner to confirm at approval)
- CLI: `review_ledger.py --ticket <id> --reject --by <who> --supersede-accepted`. `--supersede-accepted` is a plain flag, valid only with `--reject` (argparse usage error, exit 2, otherwise).
- Plain `--reject --by <who>` behaves exactly as today in every state. On an ACCEPTED ticket it still refuses and changes nothing; the refusal text now also names `--supersede-accepted`.
- With the flag, under the ledger lock, in this order. Every refusal raises `LedgerError`, exits 1 and leaves the ledger file byte-identical:
  1. `--by` is a non-empty string after strip (existing rule), and does not begin `auto:` in any case (new for this path; the `AUTO_PREFIX` rule `--accept` has).
  2. The ledger loads as `ok`. `absent` and `corrupt` refuse.
  3. The state is exactly ACCEPTED. NEEDS_REPLAN refuses as today. Any other state (IN_REVIEW, REVIEWED, missing, unknown) refuses with "nothing accepted to supersede": the flag never falls back to a plain rejection, so the record cannot claim a supersession that did not happen.
  4. `receipt` is a dict whose `kind` is one of `clean`, `owner-accepted`, `auto-accepted`, and whose `round` is an int (not a bool).
  5. The latest row in `rounds` is a dict with `status` `completed` and `round` equal to the receipt's `round`.
  6. `superseded`, when the key is present, is a list of dicts.
  A failure of 4, 5 or 6 is "could not tell what would be superseded", never an implicit reopen.
- On success, one write:
  - `superseded` (list, created if absent) gains `{"receipt": <the old receipt, whole and unchanged>, "by": <who>, "at": <now>}`. Append-only: nothing in this change removes or rewrites a row.
  - `rejected` = `{"by", "at", "round"}` as today, plus `"superseded": <the old receipt's kind>`.
  - `receipt` = `None`; `state` = NEEDS_REPLAN.
  - stdout: `review-ledger: <id> is NEEDS_REPLAN, rejected by <who> at <at>; superseded the round <n> <kind> receipt (bundle <first 12>)`.
- The bundle hash is not rebuilt or compared: the owner is rejecting, and the head may have moved.
- `summary` (what `--status` prints) gains two keys: `rejected` (the row or null) and `superseded` (the list, `[]` when absent). No existing key changes.
- What follows is unchanged code: NEEDS_REPLAN refuses `reserve`, `record`, `accept` and `auto_accept`; `check_receipt` fails; an approved, different successor plan (`continue_with_successor_plan`) opens the normal budget of two rounds.
- What this guard does and does not promise. The ledger cannot authenticate a caller: `--by` is free text, as it is for `--accept`. A refused or successful `--reserve` already voids an acceptance with no name (measured, see Evidence). So this verb widens nothing; it adds the route that records who. It can only take a receipt away, which blocks `/crew:done`; it can never mint one.

## Intent
An owner who finds an accepted head unshippable (for example a CI-only platform failure after acceptance) can send the ticket to NEEDS_REPLAN with one command that records the decision as theirs and keeps the receipt it replaced, instead of a refused third `--reserve` or a hand edit of the ledger file. A plain `--reject`, an `auto:` name, and any ledger the verb cannot read still refuse and change nothing.

## Exclusions
- No change to plain `--reject` behaviour, to `--accept`, `--auto-accept`, `--check-receipt`, `--check-follow-up`, `reserve`, `record`, refunds, `BUDGET` or `REFUND_LIMIT`.
- No change to `continue_with_successor_plan`: it still requires NEEDS_REPLAN, and a successor still opens two rounds. A per-successor round grant (`--rounds N`) stays with L-0569.
- No owner authentication, no new hook, no config key. `--reserve`'s ability to void an acceptance is not closed here.
- No `accepted_by` correction (T-0098), no autopilot auto-reject (T-0074), no hardening from L-0565, L-0596 or L-0580, nothing of L-0522 or T-0033.
- No migration or repair of ledgers already edited by hand (the L-0510 ledger with a hand-written `superseded_receipt`). They keep whatever state they are in.
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at the pylint module limit), `crew_ticket.py`, `crew_status.py`, `crew_autopilot.py`, `crew_resume.py`, `review_run.py`, `commands/done.md`, `commands/status.md` or `commands/autopilot.md`.
- `plugin/crew/commands/review.md` does not grow: it is 548 lines against an allowance of 551, and growth fails `check_instructions.py`. The edit rewrites line 509 in place.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/review_ledger.py:803 `reject`; :813-815 refuses NEEDS_REPLAN and ACCEPTED with "--reject does not change that state"; :816-818 writes `rejected` (`by`, `at`, `round`) and sets NEEDS_REPLAN.
- review_ledger.py:427-429 `accept` refuses a `--by` beginning `AUTO_PREFIX`; :140-142 `AUTO_KIND`, `AUTO_BY`, `AUTO_PREFIX`.
- review_ledger.py:328-333 `reserve`: NEEDS_REPLAN returns without writing; otherwise `_charged(data) >= BUDGET` sets NEEDS_REPLAN and appends a `refused` row. There is no ACCEPTED check on either branch.
- review_ledger.py:855 `check_receipt`; :864-865 NEEDS_REPLAN means "no receipt stands"; :866-869 a receipt that is not for the latest round does not count.
- review_ledger.py:907 `continue_with_successor_plan`; :924-927 refuses any state but NEEDS_REPLAN; :935 clears `receipt`.
- review_ledger.py:946-958 `summary` returns no `rejected` key, so a rejection is invisible in `--status` today.
- review_ledger.py:203-229 `_load`: `rounds` and `successors` are type-checked; no other key is.
- review_ledger.py:989-990 the `--reject` argument; :1000 `--by`; :1003-1004 the `parser.error` precedent for a flag used with the wrong action; :1022-1026 the `--reject` branch of `main`.
- review_ledger.py:17-22 (docstring): the refused reservation and `--reject --by` "are the only ways into NEEDS_REPLAN".
- Measured 2026-10-04, throwaway repo, origin/main's module:
  - round 1 FINDINGS, `accept`, then `reserve`: `(True, 2, ...)`, state IN_REVIEW, `check_receipt` -> "receipt is for round 1, not the latest recorded round";
  - round 2 FINDINGS, `accept`, `reject` -> "B is ACCEPTED; --reject does not change that state"; then `reserve` -> refused, state NEEDS_REPLAN, ledger keys `budget, receipt, refused, rounds, state, ticket` (no `rejected`), old receipt still under `receipt`.
- Tests today: plugin/crew/tests/test_review_receipt.py:221 `_reject_cli`, :227 `test_reject_sets_needs_replan_and_accept_is_then_refused`, :238 `test_reject_is_refused_and_changes_nothing` (parametrised `needs_replan`, `accepted`, `no_by`); :29-47 the `repo`, `_review` fixtures; :192 `_accept_cli`. The file is 430 lines.
- Sabotage today: plugin/crew/tests/sabotage_review.py:262-268, "--reject changes an ACCEPTED or NEEDS_REPLAN ticket", anchored on the exact line at review_ledger.py:813 and naming `test_reject_is_refused_and_changes_nothing`. sabotage_review.py is 1156 lines; plugin/crew/tests/sabotage.py:69 imports `REVIEW_FIX_MUTATIONS` from it.
- Docs that state the rule: plugin/crew/README.md:764 and :772; plugin/crew/commands/review.md:509; docs/guides/crew/src/troubleshooting.md:119 and :179-183 ("Refuses on a ticket already ACCEPTED or already NEEDS_REPLAN").
- Harness: scripts/check-tooling-pr.py:58-87 `HARNESS` holds `plugin/crew/hooks/scripts/review_*.py`, `plugin/crew/tests/sabotage*.py` and `plugin/crew/commands/review.md`; :99-118 `ALONGSIDE` lets `plugin/crew/tests/**`, README, BUDGETS, version files, CHANGELOG, `docs/**` and `.crew/codemap/**` ride along.
- .crew/verify.json:415-419 maps `review_*.py`, `commands/review.md` and `test_review_*.py` to `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_*.py -q`. No new rule is needed.
- Consumers of `summary`: plugin/crew/hooks/scripts/crew_status.py:146, plugin/crew/hooks/scripts/review_run.py:605, both by key; plugin/crew/tests/test_review_contracts.py:292-299 stubs it. None pins the key set.
- Nothing on main implements this: `git grep -n -e supersede-accepted -e superseded origin/main -- plugin/crew/hooks/scripts/review_ledger.py` prints nothing.
- The two incidents: T-0087 (2026-09-29, the refused-reserve route) and L-0510 (2026-10-01, a hand edit of the ledger), recorded in direction.md and in L-0569's direction.md.

## Unknowns
- Owner questions, defaults taken (direction.md, "Open questions for the owner"): flag or no flag; all three receipt kinds or only `owner-accepted`; whether a name plus the `auto:` refusal is enough or an owner-typed marker is wanted; whether L-0569 narrows to the round grant. Resolved at approval. A different answer to the first two changes one condition and its tests, not the shape.
- T-0098, L-0569, L-0565 and L-0596 edit the same file and none is on main. Whichever lands second merges main and re-reads `reject` and `main()`'s argument group before building. Resolved at plan time by re-reading origin/main.
- T-0098's spec notes that a receipt copy kept under another key is not corrected by its verb. Accepted: a `superseded` row is history and is never read for a decision.
- Whether a contract or golden test pins `--status`'s exact key set. None found by grep; resolved at implement by running `plugin/crew/tests/test_review_contracts.py` and `test_review_golden.py`.
- Windows: no new file read, path or subprocess, so no new platform case is expected. Confirmed by the crew-shell-matrix job on the PR, not locally.
- The next free crew patch version is set at implement time, one past origin/main's.

## Size and split
- Estimate: about 45 added production lines, all in `plugin/crew/hooks/scripts/review_ledger.py` (the guard in `reject` about 30, `summary` 2, `main` and argparse about 8, docstring about 6). `sabotage_review.py` gains about 45 lines; it is a test path.
- One guard, no parser, no new state. Under the 300-line rule. **No split.**
- Harness rule: every production path here is in `HARNESS`, so this is a tooling-only PR. Its tests, README, guide, code map, CHANGELOG and version files are in `ALONGSIDE`. No feature path is touched, so nothing has to be carved out.

## Touch
- plugin/crew/hooks/scripts/review_ledger.py
- plugin/crew/tests/test_review_reject_accepted.py
- plugin/crew/tests/test_review_receipt.py
- plugin/crew/tests/sabotage_review.py
- plugin/crew/commands/review.md
- plugin/crew/README.md
- docs/guides/crew/src/troubleshooting.md
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by docs/guides/crew/src/build.py
- .crew/codemap/crew.md
- .crew/codemap/INDEX.md
- CHANGELOG.md
- plugin/crew/BUDGETS.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting); `docs/diagrams/` (no box or edge changes; a regenerated anchor is a refresh artifact); `.crew/verify.json` (the rule at :415-419 already covers the new test file); `plugin/crew/commands/status.md` (it describes the rendered line, which does not change); `graphify-out/` (refresh artifact).

## Acceptance checks
Commands run from the repo root. Each pytest command goes through the repo's heavy-run wrapper on a memory-bound host. All new tests live in `plugin/crew/tests/test_review_reject_accepted.py` unless named otherwise; they map to the `.crew/verify.json` rule at :415-419.
- [ ] Must-allow, owner-accepted: round 2 FINDINGS accepted, then `--reject --by "the owner" --supersede-accepted` exits 0; state is NEEDS_REPLAN, `receipt` is null, `superseded` has one row whose `receipt` equals the old receipt exactly and whose `by` is `the owner`, `rejected.superseded` is `owner-accepted`, and stdout names the round, kind and 12-character bundle prefix. `python3 -m pytest plugin/crew/tests/test_review_reject_accepted.py -q -k test_supersede_moves_an_owner_accepted_ticket_to_needs_replan`
- [ ] Must-allow, the other kinds: the same for a `clean` receipt and for an `auto-accepted` receipt (row built as `test_review_auto_accept.py` builds one). `-k test_supersede_takes_each_known_receipt_kind`
- [ ] Must-allow, round 1: an accepted round 1 with budget left is superseded the same way, and no round is reserved. `-k test_supersede_with_budget_left_reserves_nothing`
- [ ] Must-allow, the edited tree: the override succeeds after the tree changed since review (no hash comparison). `-k test_supersede_does_not_need_a_current_bundle`
- [ ] After the override: `--check-receipt` exits 1 with "NEEDS_REPLAN; no receipt stands"; `--accept`, `--auto-accept` and `--reserve` are refused; a second `--reject --supersede-accepted` is refused and `superseded` still has one row. `-k test_after_supersede_only_a_successor_plan_continues`
- [ ] The full cycle: override, an approved different successor plan, a round recorded CLEAN writes a new receipt; `superseded` still holds the first one. A second override on the new receipt appends a second row and leaves the first unchanged. `-k test_supersede_survives_a_successor_and_appends`
- [ ] Must-block, one parametrised test, each case exit 1 with the ledger file byte-identical before and after (compare bytes, not `status()`). `-k test_supersede_is_refused_and_changes_nothing`:
  - no `--by`; a `--by` of spaces only
  - `--by "auto: anything"` and `--by "AUTO:x"`
  - plain `--reject --by x` on an ACCEPTED ticket (no flag), and its stderr names `--supersede-accepted`
  - the flag on a REVIEWED ticket, on an IN_REVIEW ticket, on a NEEDS_REPLAN ticket, and on a ticket with no ledger
  - a corrupt ledger (not JSON)
  - `receipt` null, a string, a list; a receipt whose `kind` is missing or `superseded-by-hand`; a receipt whose `round` is `true` or a string
  - a receipt for round 1 while round 2 is the latest row; a latest row that is `reserved`; a latest row that is not a dict
  - `superseded` present as a dict, a string, or a list holding a non-dict
- [ ] Usage: `--supersede-accepted` with `--accept`, `--status` or `--reserve` exits 2 and writes nothing. `-k test_supersede_flag_needs_reject`
- [ ] `--status` prints `rejected` and `superseded` after an override, `rejected: null` and `superseded: []` on a ledger that never had one, and every key it printed before. `-k test_status_shows_the_rejection_and_what_it_superseded`
- [ ] Existing behaviour is unchanged: `python3 -m pytest plugin/crew/tests/test_review_receipt.py -q -k "reject"` passes with at most the refusal-text assertion adjusted; `test_reject_is_refused_and_changes_nothing[accepted]` still refuses.
- [ ] Sabotage, each mutation added to `plugin/crew/tests/sabotage_review.py` and turning its named test red through `python3 plugin/crew/tests/sabotage.py` (run the new entries, not the whole file, on a memory-bound host):
  - (a) the override runs without the flag
  - (b) the `auto:` refusal is dropped from the override path
  - (c) the state check accepts REVIEWED
  - (d) the receipt-kind check accepts any kind
  - (e) the latest-round check is dropped
  - (f) the old receipt is not appended to `superseded`
  - (g) `superseded` is replaced instead of appended to
  - (h) `receipt` is left in place after the override

  The existing entry "--reject changes an ACCEPTED or NEEDS_REPLAN ticket" (sabotage_review.py:262) is re-anchored if its line moved and still goes red. A test `test_every_reject_sabotage_anchor_is_present_exactly_once` asserts each anchor string occurs exactly once in `review_ledger.py`.
- [ ] The review suite passes: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_*.py -q`. So do the seam consumers: `python3 -m pytest plugin/crew/tests/test_status.py plugin/crew/tests/test_crew_autopilot.py -q`.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` on the branch.
- [ ] Lint: `python3 -m pylint plugin/crew/hooks/scripts/review_ledger.py plugin/crew/tests/test_review_reject_accepted.py plugin/crew/tests/sabotage_review.py` scores 10.00, and ruff reports no new finding against the merge base.
- [ ] Docs, in the same PR:
  - `review_ledger.py`'s module docstring states the third way into NEEDS_REPLAN and the `superseded` list;
  - plugin/crew/README.md:764 and :772 and docs/guides/crew/src/troubleshooting.md:119 and :179-183 state it, including that plain `--reject` still refuses an ACCEPTED ticket and that `--by` is a recorded name, not a check of who is calling;
  - plugin/crew/commands/review.md:509 names the flag with no line added (`git show origin/main:plugin/crew/commands/review.md | wc -l` and the branch's count are both 548);
  - the guide outputs are rebuilt with `python3 docs/guides/crew/src/build.py`;
  - `.crew/codemap/crew.md` describes the verb with a `path:line` and is re-anchored;
  - `plugin/crew/BUDGETS.md`'s marked line count is re-measured.
- [ ] Release: crew is bumped to the next free patch in `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`, with a CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` passes and `python3 plugin/crew/hooks/scripts/_test/validate-prompts.py` reports 0 failures.

## Dependencies
Must land first: none is open.
- T-0087 (merged): the tooling-PRs-land-alone rule this PR follows, and the ticket where the gap was found.
- L-0510 (done): added the `auto-accepted` receipt kind and the `auto:` prefix rule this guard reuses; the second incident.
- T-0026 (merged): the approval receipt `continue_with_successor_plan` reads after the override. Unchanged here.

Same file, no order forced; the second to land merges main and re-reads `reject` and `main()`:
- L-0569 (direction): ACCEPTED to successor. This ticket covers its options 1 and 2; its option 3 (a per-successor round grant) remains.
- T-0098 (direction): `accepted_by` correction verb.
- L-0565 (direction), L-0596 (direction), L-0580 (direction): ledger hardening.
- L-0522 (in-progress): edits `check_receipt`, which this ticket does not touch.
- T-0033 (ready, on hold): receipt hash normalisation; touches `accept`, `auto_accept`, `check_receipt`, not `reject`.

Blocks:
- L-0569 (direction): cannot be scoped until this ticket's verb exists or is refused; its remaining part builds on the `superseded` row.
- T-0074 (direction): autopilot's out-of-rounds handling needs to know that an unattended `auto:` name can reject a REVIEWED ticket and can never supersede an accepted one.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
