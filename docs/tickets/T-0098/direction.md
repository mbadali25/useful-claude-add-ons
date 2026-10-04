# T-0098 direction - review_ledger can correct who accepted a review, with the history kept

Status: direction written 2026-10-04 for cloud hand-off (owner go 2026-10-04). No direction.md existed before; the only earlier record is the INDEX row.   risk: low

## Ask
INDEX row: "review_ledger has no way to correct accepted_by (a peer recorded an owner decision under its own name); add an append-only --correct-acceptance with reason and timestamp".

A peer session ran `review_ledger.py --accept --by <its own name>` for a decision the owner made. The receipt now names the wrong party, and no verb can fix it: `--accept` runs once per round, `--reject` refuses an ACCEPTED ledger, and there is no edit verb. The only way out today is a hand edit of the ledger file, which leaves no trace of what the field used to say or why it changed.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322).

Still true:
- `accept` writes `accepted_by` once, from `--by` (plugin/crew/hooks/scripts/review_ledger.py:460-464), and refuses a second accept of the same round (:453-455).
- `reject` refuses on ACCEPTED (:813-815).
- The CLI has eight verbs and none edits a receipt (:983-997).
- Nothing on main implements a correction: `git grep -n -E "correct-acceptance|correct_acceptance|acceptance_corrections" origin/main -- plugin scripts docs` prints nothing, and `git log origin/main --oneline -i --grep="correct-acceptance"` prints nothing.

Changed since the row was filed (2026-09-28):
- L-0510 added a second receipt kind, `auto-accepted`, whose `accepted_by` is a fixed string (`AUTO_BY`, :141) that `receipt_stands` compares (:729). A correction must never touch that kind: changing the string would make the receipt stop standing.
- L-0510 also reserved the `auto:` prefix for `--auto-accept` (:427-429). A correction must refuse it too, or it becomes a way to write that string without the guard.
- T-0100 changed `_current_hash` to return a tuple (:824-831). Not relevant: a correction does not rebuild the bundle.

## Options
1. **Recommended: a `--correct-acceptance --by <who> --reason <text>` verb that rewrites `receipt.accepted_by` and appends a history row.** The row (`round`, `was`, `now`, `reason`, `at`) goes in a top-level `acceptance_corrections` list. Every existing reader of `accepted_by` sees the right name with no change. The list sits beside `refused` and `successors`, so a successor plan clearing the receipt does not erase the history. Cost: one field is rewritten, so "append-only" is a property of the history list, not of the receipt.
2. A verb that never touches `accepted_by` and only appends the row; readers compute the effective name. Cost: every reader (the duplicate-accept message, `--status`, any script that reads the JSON) has to learn the list, and one that does not keeps showing the wrong name.
3. Document the hand edit. Cost: no record, no refusals, and the next hand edit can change the hash or the state by accident.

Default taken: option 1.

## Decisions taken without the owner (each is listed in spec.md's open questions)
- Option 1 over option 2.
- Only an `owner-accepted` receipt can be corrected. `clean` has no accepter; `auto-accepted` has a fixed one.
- The verb works in any ledger state and never changes the state, the rounds, the hash or `accepted_at`. A correction is usually made after the ticket has merged, when the tree no longer matches the bundle, so it must not rebuild the bundle.
- `--reason` is required. There is no separate "who made the correction" field: the ledger cannot authenticate anyone, so the reason carries the context (for example, the owner's words).
- Receipts already cleared by a successor plan are out of scope.

## Size
About 70 production lines, all in `plugin/crew/hooks/scripts/review_ledger.py`. One verb, no parser, no state machine. Every production path is in the harness list, so this is one tooling-only PR. No split.
