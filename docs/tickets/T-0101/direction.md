# T-0101 direction - review prompt says "not yet run (gate follows review)" instead of MISSING

status: new
filed: 2026-09-28 by crew [606220], from T-0085 review round 1 standards proposal #1, accepted by the owner ("Accept all as recommended", 2026-09-28).

## Problem

The review prompt's receipts block prints MISSING for `.crew/.verify-verified-at` and
`.crew/.verify-gate.record.json` when the ticket has not reached /crew:gate yet. The lifecycle runs
gate AFTER review, so no verify receipt can exist for the reviewed head at review time. The T-0085
round-1 reviewer raised a BLOCK on exactly that ("No verify-gate receipt exists for the reviewed head
8ab20e16"), which costs a round on the lifecycle's own ordering.

## Evidence

- `.work/tickets/T-0085/standards-proposals-r1.md`, Finding 1 (verbatim BLOCK line).
- review_prompt.py's receipts block (find the MISSING rendering; cite path:line in the spec).

## Direction (recommended)

When the ticket has not reached gate, print `not yet run (gate follows review)` for those receipts;
keep MISSING for a ticket whose gate was expected to have run. Keep "could not tell" as its own state
(do not collapse an unreadable receipt into either label). Tests: before-gate prints the new wording;
after-gate absent still prints MISSING; unreadable prints could-not-tell. Sabotage entry for the
branch that picks the wording.

## Open questions

- How does review_prompt know the ticket has not reached gate? Recommendation: from the ledger / INDEX
  state already read for the prompt; if that is unknown, print could-not-tell, never "not yet run".

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

Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; the recommended option below was taken as the default.

**What changed.** The premise "the lifecycle runs gate AFTER review" is no longer true on main.
- Gate first landed on 2026-09-29 (`ce4c951a`, "crew: gate first - no review round on a tree the verify gate has not passed"). `plugin/crew/hooks/scripts/review_run.py:672-694` (`preflight`) refuses with exit 5 and reserves no round when the gate state is UNVERIFIED or UNKNOWN, unless `--allow-unverified` is passed.
- The standards now say the same. `plugin/crew/skills/crew-standards/references/generic.md:604` (GEN-12) opens "Before review: ... the verify gate's last clean pass equals HEAD on a clean tree". `plugin/crew/skills/crew-qa-standards/references/review.md:8` (R1) is "The deterministic gate goes first".
- So the wording this ticket asked for, `not yet run (gate follows review)`, would now state something false. It is dropped.
- There is no ledger or INDEX state "reached gate" to read, and none is needed any more: the order is enforced before the round, not inferred in the prompt.

**What is still true.** A reviewer can still read the MISSING line, in one case only: an override round.
- `plugin/crew/hooks/scripts/review_prompt.py:266-268` still prints `MISSING: no .crew/.verify-verified-at ...`, and `:277-278` prints `Gate answer for HEAD: ...`. Nothing in the prompt says that a round on such a tree exists only because the operator passed `--allow-unverified`, or that `review.json` records it (`review_run.py:580`, `:641-647`, key `gate.overridden`).
- The reviewer therefore cannot tell a recorded override from a gap nobody noticed, and raises a BLOCK. This happened again after gate first landed: T-0087 round 4 (2026-09-30) ran with `--allow-unverified` and returned "1 BLOCK (no .crew/.verify-verified-at)" (INDEX row T-0087).
- Override rounds are not rare here: 3 of the 11 `review.json` files under `.work/tickets/` in the main checkout carry `"overridden": true` (measured 2026-10-04 with `grep -l`).
- Nothing on main addresses this: `git grep -n "allow-unverified" origin/main -- plugin/crew/hooks/scripts/review_prompt.py` prints nothing, and `git log origin/main --grep=T-0101` is empty.

**Options.**
1. **Recommended, taken as the default: say the override in the prompt.** In the one branch where the gate is not accepted (local UNVERIFIED or UNKNOWN and no CI receipt VERIFIED), `_receipts_block` adds one fixed line: a round on a tree in this state is reserved only under `--allow-unverified`, `review.json` records it as `gate.overridden`, `/crew:done` still needs a clean gate, and the missing pass on its own is that recorded override, not a defect in the diff. The MISSING line, the `Gate answer for HEAD` line and the UNKNOWN label stay exactly as they are. No new argument, no ticket-state lookup, no new state. About 12 production lines.
2. Pass the fact in: `review_prompt.py --allow-unverified`, set by `commands/review.md` when the operator intends the override. More exact (the line appears only when the override really is given), but the flag must be given twice, `review.md` is at its instruction budget, and a forgotten flag silently restores today's behaviour.
3. Close as superseded by gate first and GEN-12, and accept that an override round always carries one BLOCK that the owner accepts by hand.

**Why 1.** The line is a statement about the tool that is true whenever it prints, so it needs no knowledge of what the operator will pass later. It keeps "could not tell" as its own value (the UNKNOWN state is still named on the `Gate answer` line). It does not weaken the gate: `review_run.py` still refuses without the flag, and `/crew:done` check 2 (`plugin/crew/commands/done.md:21`) still refuses a red gate.

**Tooling PR.** `review_prompt.py` and `sabotage_review.py` are in `HARNESS` (`scripts/check-tooling-pr.py:58-87`), so this lands alone as a tooling-only PR. Tests, README, guides, code map, CHANGELOG and version files may ride along (`ALONGSIDE`, `:99-118`).

**Open questions for the owner**
- Option 1 or option 3? Default taken: 1.
- Should the line tell the reviewer not to report the missing pass on its own (default), or only state the facts and leave the severity to the reviewer? GEN-12 makes a missing pass a real finding for an author; the default treats the operator's recorded override as the answer to it.
- `MISSING: no .crew/.verify-gate.record.json (no per-rule record)` (`review_prompt.py:281-283`) also prints when the gate is VERIFIED. Left alone here. If an absent record is the normal result of a clean pass, that label deserves its own ticket.
