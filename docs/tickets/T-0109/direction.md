# T-0109 direction - owner rejection of an ACCEPTED review

Status: seed.

## Ask
the owner, 2026-09-29 ~05:50 CDT, choice "Refused reserve + ticket (Recommended)" for T-0087: use the refused-reservation route now, and file a ticket so `--reject --by owner` can override an owner-accepted receipt.

## Evidence
T-0087 Replan (run wf_0de36989-34e): the ledger refused both `--reject --by 'the owner ...'` and `--successor-plan` because round 2's owner acceptance left the ledger ACCEPTED; --reject is allowed only outside ACCEPTED and NEEDS_REPLAN. The only documented way from ACCEPTED to NEEDS_REPLAN was a refused third `--reserve` with rounds_left 0, which records a refused reservation instead of the owner's decision.

## Wanted
An owner-attributed rejection that supersedes an owner-accepted receipt (for when the accepted head turns out to be unshippable, e.g. a CI-only platform failure), recorded as such, then NEEDS_REPLAN. Guard-class: must-block (a non-owner/unattended caller cannot void an owner acceptance) and must-allow, sabotage-tested.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; the recommended option is taken and the questions are listed at the end.

### Still true
- Not fixed on main. `git log origin/main --grep T-0109` is empty, and `reject` still refuses both states: plugin/crew/hooks/scripts/review_ledger.py:813-815 (`if data.get("state") in (NEEDS_REPLAN, ACCEPTED)` -> "--reject does not change that state"). The existing test and sabotage entry pin that refusal (plugin/crew/tests/test_review_receipt.py:238, plugin/crew/tests/sabotage_review.py:262-268).
- `continue_with_successor_plan` still refuses anything but NEEDS_REPLAN (review_ledger.py:924-927), so an ACCEPTED ledger has no owner-attributed way to a successor plan.
- It happened a second time: L-0510, 2026-10-01, was moved ACCEPTED -> NEEDS_REPLAN by a hand edit of the ledger file (L-0569 direction.md). Two incidents, same gap.

### What changed since the seed
- Measured 2026-10-04 in a throwaway repo with origin/main's `review_ledger.py` (states run, not reasoned):
  - Round 1 FINDINGS owner-accepted, then `reserve`: round 2 is reserved, state IN_REVIEW, `--check-receipt` fails with "receipt is for round 1, not the latest recorded round".
  - Round 2 FINDINGS owner-accepted, then `reserve`: refused, state becomes NEEDS_REPLAN, `--check-receipt` fails with "NEEDS_REPLAN; no receipt stands". The ledger gains one `refused` row (`at`, `provider`) and no `rejected` row. The old receipt stays under `receipt` until a successor plan clears it.
  - So **any caller can already void an owner acceptance with `--reserve`**, with no name recorded. The seed's "a non-owner caller cannot void an owner acceptance" is not true of the ledger today, and this ticket does not make it true. What this ticket adds is the attributed route, and it does not widen who can void: voiding only ever blocks `/crew:done`; getting back to a receipt still needs an approved successor plan and a fresh review.
- The ledger has no way to authenticate an owner. `--by` is free text for `--accept` and `--reject` alike; the only reserved value is the `auto:` prefix, refused by `--accept` (review_ledger.py:427-429) so it can come only from `--auto-accept` (L-0510). The must-block set below is built from what the ledger can actually check.
- L-0510 added a third receipt kind, `auto-accepted` (review_ledger.py:140-142). A CLEAN receipt on a head that later proves unshippable has the same need as an owner-accepted one.
- L-0569 (direction) asks for the same transition under another name (`--reopen --by`), plus a `--rounds N` grant. T-0098 (direction) adds an `accepted_by` correction verb to the same file. T-0074 (direction) wants autopilot to reject unattended. None is on main.
- `plugin/crew/hooks/scripts/review_ledger.py`, `plugin/crew/tests/sabotage*.py` and `plugin/crew/commands/review.md` are in `HARNESS` (scripts/check-tooling-pr.py:58-87), so this is a tooling-only PR. README, `docs/**`, the code map, CHANGELOG and version files ride along (`ALONGSIDE`, :99-118).
- The two 2026-09-30 owner decisions above (merge main, never rebase; suites under the heavy-run wrapper with `-n 4`) still apply to the build.

### Options
1. **(Recommended, taken.) `--reject --by <who> --supersede-accepted`.** One extra flag on the existing verb. Plain `--reject` keeps refusing an ACCEPTED ticket, so no existing prompt or script starts voiding receipts by accident; the refusal now names the flag. With the flag, an ACCEPTED ledger whose receipt is readable and is for the latest round moves to NEEDS_REPLAN, the old receipt is kept in an append-only `superseded` list with who and when, and `receipt` is cleared. `--by` beginning `auto:` is refused. Everything the ledger cannot read is a refusal that changes nothing. About 45 production lines, one guard.
2. `--reject --by` works on ACCEPTED with no extra flag (the INDEX title read literally). Smaller, but the existing must-block case (`test_reject_is_refused_and_changes_nothing[accepted]`) flips to allow, and a prompt that says "reject" on the wrong ticket voids a receipt.
3. A new verb `--reopen --by` (L-0569 option 1). Same behaviour as option 1 under a second name; two verbs into NEEDS_REPLAN to document and sabotage.
4. Let `--successor-plan` accept ACCEPTED directly (L-0569 option 2). No owner name is recorded at the moment the acceptance is voided, which is the thing the seed asks for.

### Recommended scope decisions (taken as defaults)
- All three known receipt kinds (`clean`, `owner-accepted`, `auto-accepted`) can be superseded; the row records which. An unknown kind is could-not-tell and refuses.
- The override does not check the bundle hash: the owner is rejecting, and the head may already have moved.
- No per-successor round grant. A successor plan after the override opens the normal budget of two. The one-round grant stays with L-0569 (its option 3).
- `--status` shows `rejected` and `superseded`, so the override is visible without opening the ledger file.
- T-0109 covers L-0569's options 1 and 2. L-0569 should be narrowed to its option 3 (the `--rounds N` grant) by whoever owns the INDEX; this lane did not edit it.

### Open questions for the owner
1. Flag or no flag (option 1 against option 2)? Default taken: the extra `--supersede-accepted` flag.
2. Should a `clean` or `auto-accepted` receipt be supersedable, or only `owner-accepted` as the title says? Default taken: all three.
3. The ledger cannot tell the owner from any other caller, and `--reserve` already voids an acceptance unattended. Is the `auto:` refusal plus a required name enough for "must-block", or do you want an owner-typed marker (a UserPromptSubmit hook, as plan approval has)? Default taken: name plus `auto:` refusal; a hook would be its own ticket, default OFF, with its own suite.
4. Should L-0569 be narrowed to the `--rounds N` grant once this lands? Default assumed: yes.
