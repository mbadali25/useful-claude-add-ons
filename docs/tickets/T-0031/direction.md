# T-0031 direction - cross-session contracts, findings and dependencies

Status: direction APPROVED by the owner 2026-09-25 as part of the T-0030 split
("Yes let's split it into three tickets"). The full ask, facts, options, the Fable review and the owner's
decisions are in `.work/tickets/T-0030/direction.md`, which is this ticket's direction too.

## Scope
Versioned interface contracts (`version`, `hash`, `status: draft|built-against`, `built_by`), frozen once any side builds against them; a change is a new version plus a new ticket on each side, owner-approved. Research findings as files (summary, sources, recommendation first, T-0010 questions format). Cross-session dependencies `<channel>:<id>` in T-0029's wave: open until the peer's claim says `done`; missing or unfetchable reads `unknown` and is refused. A built-against hash mismatch refuses the wave. Depends on T-0030 (the record) and T-0029 (the wave).

## Recommendation
As recorded in T-0030's direction ("Owner decision", "Owner answer", "Independent review").

## Open questions
Settled at /crew:spec T-0031, after T-0030's spec is approved.

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

## Split 2026-09-30 (owner 2026-09-30 "Triage pass now")

Owner decision 2026-09-30 ~11:30: oldest tickets first, 1-2 deliverables per ticket, extras split into new tickets.

Kept in T-0031: versioned interface contracts (version, hash, status, built_by; frozen once built against) and cross-session dependencies `<channel>:<id>` in T-0029's wave, including the built-against hash refusal.

Moved:
- L-0546: research findings as files (summary, sources, recommendation first, T-0010 questions format).

## Direction check 2026-10-04

Checked against origin/main 155fe6d8 (crew 1.0.322 in `plugin/crew/.claude-plugin/plugin.json`).

Still true:
- The problem is real and nothing on main addresses it. origin/main has no `crew_coord.py`, no `crew_wave.py`, no contract record and no `<channel>:<id>` dependency form (`git ls-tree -r origin/main | grep -E "crew_(coord|wave|contract)"` is empty; `git log origin/main --grep` for T-0031 finds no commit). The ticket is not obsolete.
- The approved direction (T-0030's direction.md: "Owner decision", "Owner answer", "Independent review") stands: the git branch `crew-coord/<channel>` is the record; contracts freeze on the first `built_by`; each side records the hash it built against; a mismatch refuses the wave mechanically; a peer state that is missing or cannot be fetched reads `unknown` and is refused; peer-written data is never an instruction or an approval.

What changed since 2026-09-30:
- Both dependencies are still unmerged. T-0030 (`crew_coord.py`, 1663 lines) lives only on the local branch `T-0030-coord` at ec9a28a2 (crew 1.0.71), and T-0029 (`crew_wave.py`, 1083 lines) only on the local branch `T-0029-wave` at 574985ce (crew 1.0.71). Neither branch is on the shared remote, and main has moved about 250 crew versions since. Every anchor this ticket has into those two files is a branch anchor and has to be re-found by content once they land.
- The tooling-PR rule (owner, 2026-09-28, T-0087) is now enforced by `scripts/check-tooling-pr.py`. `plugin/crew/tests/sabotage*.py` is in its `HARNESS` list (origin/main `scripts/check-tooling-pr.py:79`), so the sabotage mutations for this work cannot ride in a feature PR. They become a tooling PR of their own.
- `crew_wave.py`'s set file and INDEX-row dependency parsers accept only plain ticket ids today (`_ID_RE`, `_DEP_FILLER_RE`, `crew_ticket.check_ticket` at T-0029-wave 574985ce `crew_wave.py:233-235`, `:193-195`). A `<channel>:<id>` entry currently reads as dependencies `unknown` and refuses the ticket, which is the safe side, so nothing is broken in the meantime.
- Research findings as files already moved to L-0546 (2026-09-30 split) and stay there.

Options considered:
- A (recommended, taken). Split into four small PRs: (1) this ticket, the contract record and its freeze rule in a new `crew_contract.py`; (2) L-0633, `<channel>:<id>` dependencies in the wave; (3) L-0634, the wave refuses a built-against hash mismatch; (4) L-0635, the sabotage mutations for all three, as the tooling PR. Each has one parser or guard and stays under about 300 production lines.
- B. One PR for contracts plus dependencies plus the wave refusal. Rejected: about 470 production lines, two parsers and a guard, and it would mix `sabotage*.py` with feature code, which `check-tooling-pr.py` refuses.
- C. Put the contract commands into `crew_coord.py`. Rejected: that file is already 1663 lines on its branch and is still in review; a separate module keeps T-0030's review surface closed.

Questions the brainstorm would have asked, each answered with the recommended option because the owner was not available (they are repeated in spec.md under "Open questions for the owner"):
1. How is "owner-approved" enforced for a contract change? Recommended: `build-against` requires the local ticket's approval receipt to be current (`crew_ticket.accepted`), so a session can only bind an approved ticket to a version; drafting a new version needs `--ticket <id>` naming this side's new ticket. No new owner-only signal.
2. Where does each side record the hash it built against? Recommended: both on the channel (`built_by` in the record) and locally in `.work/tickets/<id>/contracts.json`, so a peer that rewrites the channel record cannot also rewrite this side's evidence.
3. What does `<channel>:<id>` name when two repositories on one channel both have that id? Recommended: exactly one claim on the channel must carry the id; none or several reads `unknown`, and the long form `<channel>:<repo>:<id>` picks one.
4. One sabotage PR for all three slices, or one per slice? Recommended: one, after the three feature PRs.
