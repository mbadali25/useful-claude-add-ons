# T-0074 direction: opt-in auto-reject and replan when the last round has a BLOCK

status: approved (owner request 2026-09-27; spec and plan still to write)
risk: high

## Request
Owner, 2026-09-27, own words: "I'd like an option to have these gone entirely. Please create tickets for those and prioritize those after the playable path." "These" = the two review questions crew still stops for: accepting, or rejecting, a review whose last round came back with findings.

## What exists (verify at spec time)
- Rejecting moves the ledger to NEEDS_REPLAN (`review_ledger.py --reject`); an approved successor plan then opens fresh rounds (today: T-0018 twice, T-0009, T-0021).
- The "approved before" refusal: a plan approved twice counts as approved before (crew_ticket.earlier_plan_hashes, history[:-1]); a successor must be a different plan.
- Plan self-approval arrives with T-0010; until then the owner's standing CLI authority is used by agents.

## Recommendation
Under `autopilot.reviewAcceptance: all` (T-0073's setting), when rounds are exhausted and the last round has any BLOCK: autopilot rejects (`rejected_by: "Claude (policy: reviewAcceptance=all)"`), writes a successor plan whose steps address every BLOCK and FIX verbatim (with the neighbouring-case check), validates it, self-approves it through T-0010's policy route, and continues with fresh rounds.
- Cap: at most N automatic replans per ticket (default 2, configurable, e.g. `autopilot.maxAutoReplans`); on the cap, stop for the owner with the history. This prevents an endless reject/replan loop on a ticket whose design is wrong (T-0009 needed a redesign, not more patches).
- Same exclusions as T-0073 (guard and production-authority tickets by default) and the same refusals (INCOMPLETE round, same-family reviewer, could-not-tell).
- Report each auto-reject and replan by name.

## Open questions (recommendation first)
1. Default cap 2 replans (recommended), 1, or unlimited.
2. On the cap: stop for the owner (recommended), or park the ticket in Backlog and move on.
3. Successor plans written by the same model that built the ticket, or a different one (recommended: a different model family or tier, e.g. the owner's Fable 5.1 choice for T-0009).

## Depends on / order
T-0010, T-0073 (shares its setting and guard carve-out). PRIORITY: start after the critical path lands, right after T-0073.

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
Checked against origin/main `155fe6d8` (crew 1.0.322). The owner was not available, so each question below takes the recommended option and is listed again in spec.md under "Open questions for the owner".

Still true:
- The problem is real. With no round left and a last round that holds a BLOCK, autopilot stops for the owner: `crew_autopilot.py` `_review_phase` answers `accept-review` with stop (plugin/crew/hooks/scripts/crew_autopilot.py:515-524), and `HUMAN_STOPS` says a round with any BLOCK "is the owner's, at every setting" (:214-216). `commands/review.md:507` stops with options for any BLOCK.
- Rejecting is still `review_ledger.reject` (plugin/crew/hooks/scripts/review_ledger.py:803-821): REVIEWED -> NEEDS_REPLAN, `rejected: {by, at, round}`.
- A successor plan must be a different plan (`review_ledger._plan_approval_receipt`, :887-904) and opens a fresh budget (`continue_with_successor_plan`, :907-940).
- Nothing on main implements this ticket: `git grep -iE "maxAutoReplans|auto.?replan|auto.?reject" origin/main -- plugin scripts` prints nothing.

What changed since 2026-09-27:
- T-0010 is merged (PR #261). Plan self-approval exists: `crew_autopilot.py approve` under `autopilot.approval`, and it already continues a NEEDS_REPLAN ledger with a distinct successor plan (crew_autopilot.py:1129-1151). The "self-approve the successor" half of this ticket is done; only the reject, the routing and the cap are missing.
- L-0510 is done and on main (commits 50e9fc66, db11d212, 523046b2). A final round with 0 BLOCK auto-accepts through `review_ledger.py --auto-accept`. That is T-0073's `fix-only` behaviour, shipped as a constant policy with no config key. So `autopilot.reviewAcceptance` does not exist, and T-0073 is still at `direction`.
- Since L-0510 each round row stores its finding lines verbatim (`findings`, review_ledger.py:399) and the reviewer's `provider` and `model_family` (:389-391). The reject decision can read BLOCK lines and the reviewer family from the ledger.
- A new owner rule (2026-09-28, T-0087): a change to the review/gate harness lands alone. `plugin/crew/tests/sabotage*.py` and `plugin/crew/commands/review.md` are harness paths; `crew_autopilot.py` and `commands/autopilot.md` are seam paths, not harness (scripts/check-tooling-pr.py:58-95).

Recommended option (taken):
1. T-0074 owns its opt-in. One repo-only key, `autopilot.maxAutoReplans`, a non-negative integer, default `0` (off, today's behaviour). It is the switch and the cap in one. The direction's "under `reviewAcceptance: all`" is dropped, because that key was never built and L-0510 replaced its `fix-only` half. If T-0073 later adds `reviewAcceptance`, `all` can read as "maxAutoReplans is at least 1".
2. The cap counts every successor plan already on the ticket's ledger, whoever approved it. It needs no new ledger field, so no harness file changes, and it can only over-count. Owner's recommended value when turned on: 2.
3. On the cap: stop for the owner with the history (direction question 2, recommended option).
4. No separate exclusion list. The auto-reject is allowed only when `approval_policy` would let autopilot approve the successor plan. Under `autopilot.approval: risk` that already excludes every ticket that is not `risk: low`, which covers guard and production-authority tickets. Under `self` the owner has already chosen self-approval at any risk. This replaces "same exclusions as T-0073".
5. The same refusals as the direction: an INCOMPLETE round, a same-family or unknown reviewer, and anything that cannot be told all stop for the owner.
6. Who writes the successor plan (direction question 3): `/crew:plan` as configured. The owner picks a different model for the planner role with `/crew:model`. No new model routing in this ticket.
7. Split into three slices (spec.md "Size and split"): this ticket is the policy, the `auto-reject` subcommand, the routing and the docs. L-0670 is the check that a successor plan quotes every BLOCK and FIX line. L-0671 is the sabotage entries and the `review.md` sentence, a tooling-only PR.

Verdict: not obsolete. Spec-ready.
