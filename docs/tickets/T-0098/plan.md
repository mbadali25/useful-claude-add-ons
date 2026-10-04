# H1 harness bundle plan - T-0098 + T-0109 + T-0101 (review ledger and prompt)

One harness-only PR (#418, branch `T-0098-build`), owner approval 2026-10-04 to bundle the
sabotage/harness tickets into 3-4 harness-only PRs. #461 (T-0109) and #422 (T-0101) are merged
into this branch (merge, never rebase) and are closed at landing. Each ticket's spec.md is the
contract; this plan covers all three.

## Harness rule (T-0087)

Every production path changed is in `HARNESS` (`scripts/check-tooling-pr.py`):
`plugin/crew/hooks/scripts/review_ledger.py`, `plugin/crew/hooks/scripts/review_prompt.py`,
`plugin/crew/tests/sabotage_review.py`, `plugin/crew/commands/review.md`. Everything else is in
`ALONGSIDE` (tests, README, docs, codemap, CHANGELOG, version files, rules). No `SEAM` path is
edited, so no `Tooling-seam:` trailer is needed. `python3 scripts/check-tooling-pr.py` must print
`tooling-pr: OK`, and `.crew/verify.json`'s harness rule (tooling-pr suite, golden replay, seam
contracts, canary) is run.

## review_ledger.py - T-0098 and T-0109 designed together

Both edit `reject`'s neighbourhood, `summary` and `main()`'s action group.

1. `reject(root, ticket, by, supersede_accepted=False)` (T-0109). Plain `--reject` is unchanged
   except that its refusal on ACCEPTED names `--supersede-accepted`. The existing refusal line
   (`if data.get("state") in (NEEDS_REPLAN, ACCEPTED):`) keeps its text so the existing sabotage
   anchor still matches exactly once. With the flag: `--by` non-empty and not `auto:` (any case);
   ledger `ok`; state exactly ACCEPTED (NEEDS_REPLAN and every other state refuse, never a
   fallback); receipt a dict of kind `clean` / `owner-accepted` / `auto-accepted` with an int
   (not bool) round; latest round a completed dict for that round; `superseded` absent or a list
   of dicts. Success appends `{receipt, by, at}` to `superseded`, writes `rejected` with
   `superseded: <kind>`, clears `receipt`, sets NEEDS_REPLAN. No bundle rebuild.
2. `correct_acceptance(root, ticket, by, reason)` (T-0098). `--by`/`--reason` one line, non-empty,
   UTF-8 encodable (shared helper `_one_line_arg`); `--by` not `auto:`; ledger `ok`; receipt kind
   exactly `owner-accepted`; current `accepted_by` a non-empty string; `acceptance_corrections`
   absent or a list of dicts; new name differs. Success appends `{round, was, now, reason, at}` to
   top-level `acceptance_corrections` and rewrites `receipt.accepted_by` only. Never reads the
   state, never calls `_current_hash`.
3. `summary` gains `acceptance_corrections` (`[]` when absent), `rejected` (row or null) and
   `superseded` (`[]` when absent). No existing key changes.
4. CLI: `--correct-acceptance` joins the action group; `--reason` and `--supersede-accepted` are
   new options. Usage errors (exit 2): `--reason` without `--correct-acceptance`;
   `--correct-acceptance` with `--follow-up`; `--supersede-accepted` without `--reject`.
5. Interaction: a superseded receipt is history and is not corrected (T-0098 Unknowns, T-0109
   Unknowns); after a supersede `receipt` is null, so a correction refuses with "no receipt".
   Both history lists survive a successor plan.
6. Module docstring: the third way into NEEDS_REPLAN, `superseded`, and the correction verb.

## review_prompt.py - T-0101

One module constant `OVERRIDE_LINE` appended in the not-accepted branch of `_receipts_block`,
after the unchanged `Gate answer for HEAD` line. Never printed when the gate is accepted. Text is
the spec's proposed sentence. Docstring line.

## Tests (written first, seen red, then green)

- `plugin/crew/tests/test_review_correct_acceptance.py` - T-0098's acceptance list.
- `plugin/crew/tests/test_review_reject_accepted.py` - T-0109's acceptance list, including
  `test_every_reject_sabotage_anchor_is_present_exactly_once`.
- `plugin/crew/tests/test_review_receipt.py` - the plain refusal now names the flag.
- `plugin/crew/tests/test_review_prompt.py` - T-0101's five checks.

## Sabotage (`sabotage_review.py`, harness, in scope here)

T-0098 (a)-(f), T-0109 (a)-(h), T-0101 (a)-(b): 16 entries, each run through `sabotage.py`'s own
`main()` with `MUTATIONS` filtered to them; each must print `RED (good)`. The existing entry
"--reject changes an ACCEPTED or NEEDS_REPLAN ticket" is re-run too.

## Docs and release

`plugin/crew/README.md`, `docs/guides/crew/src/troubleshooting.md`,
`docs/guides/crew/src/working-with-codex.md` (guide outputs rebuilt), `plugin/crew/commands/review.md`
(line 509 rewritten in place, no growth), `.crew/codemap/crew.md` (and
`verification-harness.md` if it documents the receipts block), `plugin/crew/BUDGETS.md` re-measured,
CHANGELOG entry, rules regenerated. Last commit version-only: crew `1.0.400` (coordinator
placeholder) in plugin.json, marketplace.json, PLUGINS.md and the CHANGELOG heading.
`docs/tickets/T-0098/`, `T-0109/`, `T-0101/` are deleted in the final content commit.

## Open questions - recommended option taken in every case

- T-0098: rewrite `accepted_by` + history (1); top-level list (2); no separate who-field (3);
  every state (4); no reach into `rejected.by` or cleared receipts (5).
- T-0109: explicit flag (1); all three kinds (2); name + `auto:` refusal, no owner-authentication
  hook (3) - this keeps today's security posture (the ledger cannot authenticate, and `--reserve`
  already voids an acceptance unattended), so it widens nothing; flagged in the PR body for the
  owner; L-0569 narrowing (4) not edited here.
- T-0101: build the narrowed fix (1); tell the reviewer not to report the missing pass alone (2);
  the record-label question (3) left out.
