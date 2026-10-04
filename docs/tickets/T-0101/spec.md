# T-0101 the review prompt says when a missing verify pass is a recorded override          status: spec   risk: low
## Refreshed 2026-10-04
First spec for this ticket; there was no earlier spec.md and there is no plan.md. Written against origin/main `155fe6d8` (crew 1.0.322). The direction changed, see direction.md "Direction check 2026-10-04":
- The original wording `not yet run (gate follows review)` is dropped. Since `ce4c951a` (2026-09-29) the gate runs before review, so that sentence would be false.
- The ticket is narrowed to the one case where a reviewer still reads the MISSING line: a round run with `--allow-unverified`.
- No ticket-state lookup ("has the ticket reached gate") is built. Main has no such state and no longer needs one.
- The owner was not available. Option 1 of the direction check was taken as the default.

## Intent
When the verify gate has not passed the reviewed tree, the review prompt's receipts block adds one fixed line. It says that `review_run.py` reserves a round on such a tree only under `--allow-unverified`, that `review.json` records this as `gate.overridden`, that `/crew:done` still needs a clean gate, and that the missing pass on its own is that recorded override and not a defect in the diff. A reviewer can then tell a recorded override from an unnoticed gap, and stops spending a BLOCK on it. Every existing line and label stays as it is.

## Exclusions
- No change to when a round is reserved. `review_run.py`, `review_gate.py`, `review_ledger.py` and `ci_receipt.py` are not edited.
- The `MISSING: no .crew/.verify-verified-at` line, the `Last clean verify pass ... NOT been through the gate` line and the `Gate answer for HEAD: <state>: ...` line are not reworded, reordered or removed. UNKNOWN stays UNKNOWN on that line.
- The line is not printed when the gate is accepted: a clean pass at HEAD, a local VERIFIED, NO_GATE, or a CI receipt VERIFIED.
- No new command-line argument on `review_prompt.py`, and no edit to `plugin/crew/commands/review.md` (it is at its instruction budget).
- No change to the per-rule record lines (`MISSING: no .crew/.verify-gate.record.json`, `UNREADABLE`, `NOT VERIFIED`).
- No edit to `plugin/crew/skills/crew-standards/**` or `plugin/crew/skills/crew-qa-standards/**`. They are outside `HARNESS` and `ALONGSIDE`, so they would make this a mixed PR. GEN-12 and R1 are not changed in meaning.
- No edit to `plugin/crew/tests/sabotage.py` (3400 lines, at `.pylintrc:140` `max-module-lines=3400`). Mutations go in `sabotage_review.py`.
- No new hook, no config setting, no golden file edited.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/review_prompt.py:237 `_receipts_block`. :252 the clean-pass branch. :255-259 local VERIFIED and NO_GATE. :261-264 CI receipt VERIFIED. :265-278 the not-accepted branch: :266-268 the `MISSING: no .crew/.verify-verified-at` line, :270-273 the stale-marker line, :277-278 `Gate answer for HEAD`. :279-295 the per-rule record lines. :206-214 `REASON_MAX` and `_reason` (one-line rule for anything printed here). File is 402 lines.
- plugin/crew/hooks/scripts/review_run.py:672 `preflight`; :683-694 UNVERIFIED or UNKNOWN is refused with `EXIT_UNVERIFIED` (5) unless `args.allow_unverified`. :641-647 `gate_record` sets `overridden`; :580 stores it under `"gate"` in review.json. :966 the `--allow-unverified` argument.
- plugin/crew/hooks/scripts/review_gate.py:47 the four states; :131-134 the UNVERIFIED reason when the marker is absent.
- Gate first: commit `ce4c951a` (2026-09-29) on origin/main. plugin/crew/skills/crew-qa-standards/references/review.md:8-14 (R1, names `gate.overridden`). plugin/crew/skills/crew-standards/references/generic.md:604-606 (GEN-12, "Before review").
- plugin/crew/commands/done.md:21 "Check 2 - the verify gate": the gate is still required to close.
- The finding that opened the ticket: `.work/tickets/T-0085/standards-proposals-r1.md`, Finding 1. The same BLOCK after gate first: INDEX row T-0087, round 4 with `--allow-unverified`.
- Nothing on main does this: `git grep -n "allow-unverified" origin/main -- plugin/crew/hooks/scripts/review_prompt.py` prints nothing.
- Tests today: plugin/crew/tests/test_review_prompt.py:233 `_gate` (stubs the local gate and the CI receipt); :286 `test_a_receipt_the_gate_does_not_accept_leaves_the_local_answer`; :310 clean pass; :325 local VERIFIED on a dirty tree; :345 NO_GATE; :264 CI receipt VERIFIED; :392 `test_every_gate_line_is_one_prompt_line`; :415 marker behind HEAD; :453 UNKNOWN local gate.
- Sabotage: plugin/crew/tests/sabotage_review.py:14 `REVIEW_PROMPT`; :19 `REVIEW_FIX_MUTATIONS`, entries of (name, file, original, mutated, test id). 1156 lines.
- Harness: scripts/check-tooling-pr.py:58-87 `HARNESS` holds `plugin/crew/hooks/scripts/review_*.py` and `plugin/crew/tests/sabotage*.py`; :99-118 `ALONGSIDE` holds `plugin/crew/tests/**`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, the version files, `CHANGELOG.md`, `docs/**`, `.crew/codemap/**`, `graphify-out/**`.
- Verify rules that already cover the files: .crew/verify.json:432-442 and :531-535 map `review_prompt.py` to `test_review_prompt.py`.
- Docs that describe this part of the review: plugin/crew/README.md:766 (the checks before a round), docs/guides/crew/src/working-with-codex.md:92-97, .crew/codemap/crew.md:1337 and :1352-1354.

## Unknowns
- The exact sentence. Resolved at implement; the tests pin only the tokens `--allow-unverified`, `gate.overridden`, `review.json` and `/crew:done`, and that it is one line. Proposed text: `Order: review_run.py reserves no round on a tree in this state unless the operator passes --allow-unverified, and review.json then records gate.overridden. /crew:done still needs a clean gate. The missing pass is that recorded override: do not report it as a defect on its own. Report anything in the diff a gate run would catch.`
- Whether the line should tell the reviewer not to report the missing pass, or only state the facts. Default: tell it. Open question for the owner; changing it is a wording edit inside the same Touch.
- Whether a reviewer model actually stops raising the BLOCK. Not testable in a unit test. Accepted as risk; the canary review that the harness rule runs shows the prompt still parses, and the next override round is the real check.
- The prompt is built before `review_run.py` runs, so the gate can pass in between. The line is worded as a rule about the tool, so it stays true in that case. Accepted.
- The next free crew patch version is set at implement time, one past origin/main's.

## Size and split
- Estimate: about 12 added production lines, all in `plugin/crew/hooks/scripts/review_prompt.py` (one module constant, one `out.append`, docstring lines).
- No new parser, guard or state machine. No split.
- Every production path is in `HARNESS`, and every other path in Touch is in `ALONGSIDE`, so this is one tooling-only PR with no feature work.

## Touch
- `plugin/crew/hooks/scripts/review_prompt.py`
- `plugin/crew/tests/test_review_prompt.py`
- `plugin/crew/tests/sabotage_review.py`
- `plugin/crew/README.md`
- `docs/guides/crew/src/working-with-codex.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by docs/guides/crew/src/build.py
- `.crew/codemap/crew.md`
- `.crew/codemap/verification-harness.md`
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`

Not in Touch, stated: `plugin/crew/commands/review.md` (its comment at :345-347 already says "test receipts"; no behaviour it describes changes); `plugin/crew/CONFIG.md` (no setting); `plugin/crew/skills/**` (see Exclusions); `docs/diagrams/` and `graphify-out/` (no box or edge changes; a regenerated anchor or graph is a refresh artifact).

## Acceptance checks
Commands run from the repo root. Use the repo's heavy-run wrapper for pytest and sabotage on a memory-bound host.
- [ ] Not accepted, no marker: with the local gate UNVERIFIED and no CI receipt VERIFIED, the block holds the unchanged `MISSING: no .crew/.verify-verified-at` line, the unchanged `Gate answer for HEAD: UNVERIFIED: ...` line, and the new line naming `--allow-unverified`, `gate.overridden`, `review.json` and `/crew:done`. `python3 -m pytest plugin/crew/tests/test_review_prompt.py -q -k test_an_unverified_tree_names_the_recorded_override`
- [ ] Not accepted, marker behind HEAD: the `NOT been through the gate` line is unchanged and the new line is present. `-k test_a_marker_behind_head_names_the_recorded_override`
- [ ] UNKNOWN stays UNKNOWN: with the local gate UNKNOWN and the receipt UNKNOWN, `Gate answer for HEAD: UNKNOWN:` is still printed, the new line is present, and the words "not yet run" appear nowhere in the block. `-k test_an_unknown_gate_keeps_its_label_beside_the_override_line`
- [ ] Accepted states never carry the line, one parametrized test over four cases: clean pass at HEAD, local VERIFIED on a dirty tree, NO_GATE, CI receipt VERIFIED. `-k test_an_accepted_gate_never_carries_the_override_line`
- [ ] The line is one prompt line (no newline or control character) in every not-accepted case; `test_every_gate_line_is_one_prompt_line` is extended to cover it. `-k test_every_gate_line_is_one_prompt_line`
- [ ] The existing receipts tests pass unchanged in meaning: `python3 -m pytest plugin/crew/tests/test_review_prompt.py -q` (`.crew/verify.json` rules at :432-442 and :531-535).
- [ ] Sabotage, two mutations in `sabotage_review.py`, each red through `python3 plugin/crew/tests/sabotage.py`:
  - (a) the line is no longer appended: `test_an_unverified_tree_names_the_recorded_override` goes red;
  - (b) the line is appended in every branch: `test_an_accepted_gate_never_carries_the_override_line` goes red.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` exits 0, and the harness rule in `.crew/verify.json` (tooling-pr suite, golden replay, seam contracts, canary review) passes.
- [ ] Docs in the same PR: `plugin/crew/README.md` and `docs/guides/crew/src/working-with-codex.md` say that an override round's prompt names the override; the guide outputs are rebuilt with `python3 docs/guides/crew/src/build.py`; the code map entries are re-anchored. `python3 scripts/check-marketplace.py` exits 0 after the commit, with the crew version bumped in `plugin.json`, `marketplace.json` and `PLUGINS.md` and a CHANGELOG entry.

## Dependencies
Must land first (all already on origin/main):
- Gate first, commit `ce4c951a` (PR #264), merged 2026-09-29: the refusal the new line describes.
- T-0085, merged: the standards checklist and GEN-12, and the finding that opened this ticket.
- T-0087, merged: the tooling-PR rule, golden replay and canary this PR runs under.
- T-0100, INDEX says approved, merged on origin/main as PR #371 (`155fe6d8`): last change to `review_prompt.py`'s receipts block (reasons capped apart).
- L-0574, done: the pre-review checks share exit 5 and `--allow-unverified`; the new line is about the gate override only.

Blocks: none. Related, no ordering: T-0033 and L-0522 (review receipts; they do not touch `review_prompt.py`'s receipts block).

## Open questions for the owner
- Build this narrowed fix (default), or close T-0101 as superseded by gate first and GEN-12?
- Should the line instruct the reviewer not to report the missing pass on its own (default), or only state the facts?
- Does the `MISSING: no .crew/.verify-gate.record.json` label on a VERIFIED tree need its own ticket?

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
