# T-0098 review_ledger --correct-acceptance: fix who accepted a review, keep the history          status: spec   risk: low
## Written 2026-10-04
First spec for this ticket; there was no earlier spec.md or plan.md. Every `path:line` below was read at origin/main `155fe6d8` (crew 1.0.322). The owner was not available: defaults are named in direction.md and repeated under "Open questions for the owner".

## Intent
`review_ledger.py --ticket <id> --correct-acceptance --by <who> --reason <text>` changes `accepted_by` on an `owner-accepted` receipt and appends one row to a top-level `acceptance_corrections` list saying what the field was, what it is now, why, and when. It changes nothing else: not the state, the rounds, the bundle hash, the base or `accepted_at`. So `--check-receipt` gives the same answer before and after.

## Design
- New function `correct_acceptance(root, ticket, by, reason)`, run through `_mutate` (under the ledger lock, atomic replace). Returns the appended row.
- It refuses, raising `LedgerError` and writing nothing, when:
  - the ledger is absent or corrupt (`state != "ok"`);
  - `receipt` is not a dict, or its `kind` is not exactly `owner-accepted` (the message names the kind found: `clean` has no accepter, `auto-accepted` has a fixed one);
  - the receipt's current `accepted_by` is not a non-empty string (could not tell what is being corrected);
  - `acceptance_corrections` is present and is not a list of dicts (could not tell the history, so it is not extended);
  - `--by` or `--reason` is missing, empty after strip, contains `\n` or `\r`, or cannot be encoded as UTF-8 (a lone surrogate would be written and then crash the success line);
  - `--by` starts with `auto:` in any case (same rule as `accept`, `review_ledger.py:427`);
  - `--by` after strip equals the current `accepted_by` (nothing to correct).
- On success it appends `{"round": <receipt round>, "was": <old>, "now": <new>, "reason": <reason>, "at": _now()}` and sets `receipt["accepted_by"]` to the new value. Rows are only ever appended; no verb removes or edits one.
- It does not read the ledger state and does not call `_current_hash`. A correction is normally made after the ticket merged, when the tree no longer rebuilds the reviewed bundle.
- `summary()` gains `"acceptance_corrections": data.get("acceptance_corrections") or []`, so `--status` prints the history.
- CLI: `--correct-acceptance` joins the mutually exclusive action group; `--reason` is a new option. `--reason` with any other verb, and `--correct-acceptance` with `--follow-up`, are usage errors (exit 2). Success prints one line: `review-ledger: round <n> accepted_by corrected from <was> to <now> at <at> (<k> correction(s) recorded)`, exit 0. A refusal prints `review-ledger: <reason>` on stderr, exit 1.
- `_load` is not changed. A ledger with a malformed `acceptance_corrections` still reserves, records and checks as today; only the correction verb refuses it.

## Exclusions
- No change to `accept`, `auto_accept`, `reject`, `record`, `reserve`, `check_receipt`, `receipt_stands`, `check_follow_up`, `continue_with_successor_plan` or `_load`.
- No correction of `accepted_at`, `kind`, `round`, `verdict`, `bundle_sha256`, `base`, or of a `rejected` row's `by`.
- No correction of a `clean` or `auto-accepted` receipt, and none of a receipt a successor plan already cleared.
- No undo verb. A wrong correction is fixed by another correction, which adds a row.
- No authentication of the caller, no config key, no hook, no new parser. No scope-guard rule for the verb: T-0029 owns the subagent never-list, and adds this verb to it there.
- No path from ACCEPTED to NEEDS_REPLAN or to a successor (T-0109, L-0569). No ledger hardening from L-0565, L-0596 or L-0580.
- No edit to `crew_status.py`, `crew_autopilot.py`, `crew_resume.py` or `plugin/crew/commands/done.md`. No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at `.pylintrc:140` `max-module-lines=3400`).

## Evidence
All at origin/main `155fe6d8`, file `plugin/crew/hooks/scripts/review_ledger.py` unless another path is given.
- :422-468 `accept`. :425-429 the `--by` checks, including the reserved `auto:` prefix. :453-455 a second accept of the same round is refused. :460-464 the receipt it writes; `accepted_by` is `by.strip()`.
- :408-413 `record` writes the `clean` receipt with `accepted_by: None`.
- :141 `AUTO_BY`; :694-703 the `auto-accepted` receipt; :729 `receipt_stands` requires `accepted_by == AUTO_BY` for that kind and only `kind == "owner-accepted"` for the other (:727-728).
- :803-821 `reject` refuses on ACCEPTED and NEEDS_REPLAN (:813-815).
- :855-884 `check_receipt` reads `bundle_sha256`, `base`, `round` and `kind`; it never reads `accepted_by` for an `owner-accepted` receipt.
- :931-936 a successor plan appends to `successors` and sets `receipt` to None, so history kept on the receipt would be lost there.
- :269-279 `_mutate`; :231-236 `_save` (text built first, temp file, `os.replace`); :203-228 `_load`.
- :946-958 `summary`; :978-1048 `main`; the action group is :983-997, `--by` :1000, `--follow-up` :1001.
- Other readers of the receipt: `plugin/crew/hooks/scripts/crew_autopilot.py:511-515` (through `receipt_stands`), `plugin/crew/hooks/scripts/review_run.py:677` (reads `kind` only). `plugin/crew/hooks/scripts/crew_status.py` does not read the receipt (`git grep -n -i receipt origin/main -- plugin/crew/hooks/scripts/crew_status.py` prints nothing).
- `plugin/crew/hooks/scripts/crew_resume.py:489-494` `progress_fingerprint` hashes the review ledger, so a correction changes the fingerprint.
- Nothing on main implements this: `git grep -n -E "correct-acceptance|correct_acceptance|acceptance_corrections" origin/main -- plugin scripts docs` prints nothing.
- Docs that describe `--accept`: `plugin/crew/README.md:772`, `plugin/crew/commands/review.md:507-510`, `docs/guides/crew/src/troubleshooting.md:156-157` and `:179-183` (the neighbouring `--reject` symptom), `.crew/codemap/crew.md:707-711`.
- Tests: `plugin/crew/tests/test_review_receipt.py:29-47` (`repo`, `_review`, `_check`), :105-111 the accept test; `plugin/crew/tests/test_review_ledger.py:38-41` `_cli`.
- Sabotage: `plugin/crew/tests/sabotage_review.py:19` `REVIEW_FIX_MUTATIONS` (1156 lines; rows are `(name, file, anchor, replacement, test id)`), imported by `plugin/crew/tests/sabotage.py`.
- Harness: `scripts/check-tooling-pr.py:58-87` `HARNESS` holds `plugin/crew/hooks/scripts/review_*.py`, `plugin/crew/tests/sabotage*.py` and `plugin/crew/commands/review.md`; :99-118 `ALONGSIDE` holds `plugin/crew/tests/**`, the README, BUDGETS.md, the version files, CHANGELOG.md, `docs/**` and `.crew/codemap/**`.
- `.crew/verify.json:414-419` already maps `review_*.py` and `test_review_*.py` to `pytest_rule.py plugin/crew/tests/test_review_*.py`, so a new `test_review_*.py` file needs no map edit.
- Version: `plugin/crew/.claude-plugin/plugin.json:3` is 1.0.322; `CHANGELOG.md:7` is the newest entry heading.

## Unknowns
- `crew_resume.progress_fingerprint` moves when a correction is written. Accepted as risk: a correction is a real ledger change, and the fingerprint only decides whether a resume counts as progress.
- argparse prefix matching (`allow_abbrev` is not set, so `--correct` reaches the verb). Left as is; T-0029 owns rejecting abbreviated flags for every verb at once.
- T-0109, L-0569, L-0565 and L-0596 edit the same file. None is on main. Whichever lands second merges main and re-reads `main()`'s action group. If T-0109 or L-0569 keeps the old receipt under another key (for example `superseded_receipt`), that copy is not corrected by this verb; resolved when those specs are written.
- The next free crew patch version is set at implement time.

## Touch
- plugin/crew/hooks/scripts/review_ledger.py
- plugin/crew/tests/test_review_correct_acceptance.py
- plugin/crew/tests/sabotage_review.py
- plugin/crew/commands/review.md
- plugin/crew/README.md
- docs/guides/crew/src/troubleshooting.md
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by docs/guides/crew/src/build.py
- .crew/codemap/crew.md
- CHANGELOG.md
- plugin/crew/BUDGETS.md
- plugin/crew/.claude-plugin/plugin.json
- plugin/PLUGINS.md
- .claude-plugin/marketplace.json

Not in Touch, stated: `plugin/crew/CONFIG.md` (no setting), `docs/diagrams/` (no box or edge changes; a regenerated anchor is a refresh artifact), `.crew/verify.json` (the existing glob covers the new test file), `plugin/crew/tests/sabotage.py` (at the line limit).

## Acceptance checks
Commands run from the repo root. Locally, pytest and sabotage go through the repo's heavy-run wrapper. All tests are in `plugin/crew/tests/test_review_correct_acceptance.py`; run one with `python3 -m pytest plugin/crew/tests/test_review_correct_acceptance.py -q -k <name>`. These map to `.crew/verify.json`'s review rule (:414-419) and the harness rule (:446-470).
- [ ] Must-allow: after `accept(..., "a peer")`, a correction to `the owner` sets `receipt.accepted_by` to `the owner` and appends one row with `round`, `was: "a peer"`, `now: "the owner"`, the reason and a timestamp. `-k test_correction_rewrites_accepted_by_and_appends_a_row`
- [ ] Nothing else moves: the ledger before and after differs only in `receipt.accepted_by` and `acceptance_corrections`; `accepted_at`, `bundle_sha256`, `base`, `kind`, `round`, `state` and `rounds` are equal. `-k test_correction_changes_only_the_name_and_the_history`
- [ ] `--check-receipt` exits the same before and after: 0 on an unchanged tree, 1 after the tree is edited, and the correction itself succeeds in both. `-k test_check_receipt_is_unchanged_by_a_correction`
- [ ] A second correction appends a second row and keeps the first row byte-equal. `-k test_second_correction_appends_and_keeps_the_first_row`
- [ ] The history survives a successor plan: after a correction, a ledger moved to NEEDS_REPLAN and continued still carries the row. `-k test_corrections_survive_a_successor_plan`
- [ ] `--status` output carries `acceptance_corrections`: `[]` on a ledger without the key, the rows on one with it. `-k test_status_lists_corrections`
- [ ] Must-block, one parametrised case each, every one leaving the ledger file byte-identical and exiting 1 from the CLI (`-k test_correction_refused`):
  - no ledger; a corrupt ledger
  - no receipt; a receipt that is a string
  - a `clean` receipt
  - an `auto-accepted` receipt
  - a receipt of an unknown kind
  - a current `accepted_by` that is null, empty or not a string
  - `acceptance_corrections` that is a dict, a string, or a list holding a non-dict
  - `--by` missing, empty, whitespace only, carrying `\n` or `\r`, or holding a lone surrogate
  - `--reason` missing, empty, whitespace only, carrying `\n` or `\r`, or holding a lone surrogate
  - `--by` of `auto: x` and of `AUTO: x`
  - `--by` equal to the current `accepted_by`
- [ ] After a correction, a second `--accept` on that round is still refused as already accepted, and the message names the corrected accepter. `-k test_corrected_round_is_still_already_accepted`
- [ ] CLI usage: `--reason` with `--accept`, and `--correct-acceptance` with `--follow-up`, exit 2. `-k test_correction_usage_errors`
- [ ] Two concurrent corrections both land as two rows, or one is refused; never one row lost. `-k test_concurrent_corrections_lose_no_row`
- [ ] Sabotage: each mutation below is a row in `sabotage_review.py` and turns its named test red through `python3 plugin/crew/tests/sabotage.py`:
  - (a) the kind check accepts `auto-accepted`
  - (b) the `auto:` prefix check is dropped
  - (c) the row is written over the list instead of appended
  - (d) `accepted_at` is refreshed on correction
  - (e) the malformed-history refusal is dropped
  - (f) the line-break check on `--reason` is dropped
- [ ] Existing suites pass unchanged: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_*.py -q` and `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_status.py -q`.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` on the branch.
- [ ] Docs: the module docstring of `review_ledger.py`, `plugin/crew/README.md` (the receipt paragraph at :772), `plugin/crew/commands/review.md` step 3 and `docs/guides/crew/src/troubleshooting.md` (a new symptom, "the receipt names the wrong accepter") describe the verb, what it refuses, and that it is the owner's call; the guide outputs are rebuilt with `python3 docs/guides/crew/src/build.py`; `.crew/codemap/crew.md` names the function with its `path:line`. Crew is bumped to the next free patch in plugin.json, marketplace.json and PLUGINS.md with a CHANGELOG entry, and `python3 scripts/check-marketplace.py` passes after the commit.

## Size and split
- Estimate: about 70 added production lines, all in `plugin/crew/hooks/scripts/review_ledger.py` (the function about 40, the CLI about 15, `summary` 1, the docstring about 12).
- One verb with a flat list of refusals. No new parser and no new state machine: the ledger state is not read or written.
- Harness rule: `review_ledger.py`, `sabotage_review.py` and `commands/review.md` are all in `HARNESS`; every other Touch path is in `ALONGSIDE`. The PR is tooling-only and carries no feature work.
- No split.

## Dependencies
Must land first: none open.
- L-0510 (done): added the `auto-accepted` kind and the reserved `auto:` prefix that this verb must respect. On origin/main.
- T-0100 (INDEX: approved; its build is on origin/main as crew 1.0.322): last change to `review_ledger.py`. Already accounted for.
- T-0087 (merged): the tooling-PRs-land-alone rule this PR follows.

Related, same file, no order forced: T-0109 (direction; `--reject` on an accepted receipt), L-0569 (direction; ACCEPTED to successor), L-0565 (direction), L-0596 (direction), L-0580 (direction), L-0522 (in-progress; edits `check_receipt`, which this ticket does not touch), T-0033 (spec, on hold).

Blocks: nothing by id. T-0029 (in-progress; the subagent never-list for accept and reject) should list `--correct-acceptance` once both exist.

## Open questions for the owner
1. Rewrite `accepted_by` and keep the old value in the history (taken, recommended), or leave `accepted_by` as first written and have readers compute the effective name?
2. History on a top-level list that survives a successor plan (taken, recommended), or on the receipt itself?
3. Record who ran the correction in a separate field? Taken: no, `--reason` is required and carries it, because the ledger cannot authenticate a caller.
4. Allow the verb in every ledger state (taken, recommended, because it never changes the state), or only while the state is ACCEPTED?
5. Should the verb also reach a `rejected` row's `by`, or a receipt a successor plan cleared? Taken: no, out of scope.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
