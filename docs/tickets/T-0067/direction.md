# T-0067 direction          status: ready   risk: high

## Ask
Owner (the owner, 2026-09-27), quoting an autopilot stop in another repository ("Still waiting on you: <ticket>: run
graphify . --no-viz --code-only, then /crew:review <ticket> for round 2, the last in the budget."):
"Create a ticket another short coming. It shouldn't be asking me these questions on auto pilot and
also isn't there a crew command for graphify".

## Measured (origin/main 502cb137, crew 1.0.42)
- **Single-ticket autopilot always stops on a FINDINGS round.** `crew_autopilot.py` returns
  `accept-review` with stop=true whenever the latest round is FINDINGS and not accepted
  (`plugin/crew/hooks/scripts/crew_autopilot.py:32`, `:416-419`; the fixed stop `review-acceptance`,
  `:142`). So with rounds left, the owner is still asked to start the next round.
- T-0029 adds `autopilot.reviewPolicy: stop | clean-only | fix-and-rereview`, but only for wave lanes
  (`.work/tickets/T-0029/spec.md:6`, `:92`). The owner's config already says `fix-and-rereview`
  (2026-09-26), and a plain `/crew:autopilot` run ignores it.
- **No crew command for the graph.** There is a `crew-graph` skill, but no `commands/graph.md`. So a stop
  can only name a raw tool, and that stop named `graphify . --no-viz --code-only`. That is the form this
  repo's CLAUDE.md says does NOT reproduce the tracked pair (use `graphify update .`), and it is the
  form T-0064 makes safe against a secrets denylist.

## Options
1. **Autopilot runs mechanical steps itself; stops name only owner decisions (recommended).**
   - `reviewPolicy` applies to single-ticket runs as well as waves. Under `fix-and-rereview`, a
     FINDINGS round with rounds left means: fix every BLOCK/FIX test-first, refresh, and run the next
     round, with no stop. It stops only on the LAST round's FINDINGS (acceptance is the owner's), on
     INCOMPLETE twice, or on NEEDS_REPLAN. `clean-only` and `stop` keep today's behaviour.
   - A **stop-message contract**: a stop may name only a command the owner must type (`/crew:approve`,
     review accept/reject, a production deploy, an `AUTONOMOUS_STOPS` item) or a question. A test
     walks every stop reason in `crew_autopilot.py` and fails if one tells the owner to run a
     mechanical step (refresh, graph, next review round within budget, a suite).
   - A new `/crew:graph` command (`--refresh`, `--status`, `--query`) backed by the `crew-graph` skill.
     It runs the repo's sanctioned refresh (`graphify update .` unless the repo config says otherwise),
     honours T-0064's secrets denylist, and verifies that the tracked pair agrees (the node/link counts
     in both files). The refresh phase and every refresh-check hint name it.
   - When a mechanical step truly cannot run (for example the graph refresh is unsafe until T-0064
     lands), the stop says why and which ticket fixes it. It never hands the owner a raw tool line.
2. **Only the command and the message contract, no reviewPolicy change.** Fewer moving parts, but the
   owner is still asked to start every review round, the exact complaint.
3. **Make `fix-and-rereview` the default for everyone.** Rejected: autonomy stays opt-in (T-0029's
   decision); this owner has opted in.

## Recommendation
Option 1. It honours the setting the owner already chose, and the contract test turns "don't ask me
mechanical things" into a checked rule rather than a hope.

## Open questions (recommendation applies)
- Fix-and-rereview on a guard ticket (`risk: high` touching a guard): still automatic? Yes, but the
  last round always stops for acceptance, which is where the owner's judgement matters.
- Should `/crew:graph` replace the `crew-graph` skill? No: keep the skill as the method and add the
  command as the entry point, the pattern the other lifecycle commands use.

## Depends on
T-0029 (reviewPolicy key), T-0064 (denylist-safe graph refresh; `/crew:graph --refresh` stops with
"unsafe until T-0064" before then). Relates to T-0063 (graph freshness when topology is unchanged).

## Approval
Direction approved under the owner's standing authorization (2026-09-26).

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
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; the recommended option is taken and the questions are listed at the end. Mentions of another repository in the text above were made generic on this date (the files are published); nothing else above was edited.

### Still true
- **A single-ticket run still stops on a round-1 FINDINGS.** `plugin/crew/hooks/scripts/crew_autopilot.py:515-525` returns `accept-review` with stop for any FINDINGS round no receipt stands on, and its text tells the owner to accept "or fixes then /crew:review". The auto-accept guard refuses round 1 by rule ("not the final round ... fix and run the next round", `plugin/crew/hooks/scripts/review_ledger.py:584-586`), so with a round left the owner is still the one asked to fix and start round 2.
- **`autopilot.reviewPolicy` does not exist on main.** `git grep reviewPolicy origin/main` prints nothing. `crew_state.AUTOPILOT_DEFAULTS` (`plugin/crew/hooks/scripts/crew_state.py:1134-1135`) holds `mode`, `maxPhases`, `deploy`, `approval`, `questions`.
- **No `/crew:graph` command.** `plugin/crew/commands/` has 36 files and no `graph.md`; the `crew-graph` skill is still the only entry point.
- **Stops still hand the owner mechanical steps.** `crew_autopilot.py:519-521` ("run review_ledger.py --auto-accept --follow-up <id>"), `:591` ("run crew_autopilot.py resume"), `:368-371` (an unsettled-artifact stop lists `(refresh: <command>)` for the artifacts a refresh would settle). No test walks the stop reasons for this.
- `git log origin/main --grep` for T-0067, `crew:graph`, `reviewPolicy` and `fix-and-rereview` finds no commit that built any part of this ticket.

### Changed since the direction was written (1.0.42)
- **T-0029 has not landed and is far behind.** INDEX: in-progress. Its branch is 1736 commits behind origin/main and was last committed 2026-09-30. The key this ticket was to reuse is therefore not available. Decision taken: this ticket adds `autopilot.reviewPolicy` itself, with T-0029's exact name, values and default (`stop | clean-only | fix-and-rereview`, default `stop`). T-0029 then consumes the key instead of adding it. T-0029 stops being a blocker and becomes a ticket that must re-read this one when it catches up.
- **L-0510 (done) added auto-accept of a final round with 0 BLOCK** (`review_ledger.py:560-595`, `auto_accept`). The "last round always stops for acceptance" line in Options is now narrower: the last round stops only when the guard refuses (a BLOCK, a same-family reviewer, a recovered verdict, could-not-tell). This ticket does not change that. It overlaps T-0073, which should be re-read against L-0510.
- **The review budget is 2 rounds** (`review_ledger.py:133`), so fix-and-rereview means exactly one unattended fix between round 1 and round 2.
- **The refresh phase already runs the right graph command itself.** `crew_refresh_check.py:1226-1227` names `graphify update .` when the report is tracked, and `crew_autopilot.py:548-565` returns `refresh` without a stop when every pending artifact has a command that settles it. The stop that started this ticket ("run graphify ...") no longer happens for a settle-able graph. `/crew:graph` is still wanted as the one entry point, but it is no longer what unblocks autopilot.
- **"INCOMPLETE twice" is dropped.** Main carries a must-block for the opposite: the sabotage mutation "an INCOMPLETE round is rerun unattended" (`plugin/crew/tests/sabotage_autopilot.py:58-61`) must turn `test_next_incomplete_round_stops` red. Tool failures are already refunded and rerun (`crew_autopilot.py:532-539`); an unrefunded INCOMPLETE keeps stopping.
- **T-0064 is in flight** (INDEX: approved; a draft PR is open). It adds `crew_graph_ignore.py` and edits `crew_refresh_check._graph`. The "unsafe until T-0064" shim is dropped: the `/crew:graph` slice simply waits for T-0064 to merge.
- **The tooling-PR rule (T-0087) now applies.** `plugin/crew/tests/sabotage*.py` and `plugin/crew/commands/review.md` are harness paths (`scripts/check-tooling-pr.py:58-87`). `crew_autopilot.py` and `commands/autopilot.md` are seam paths (`:89-95`). A feature PR may not touch a sabotage file, so the sabotage mutations for this work land in their own tooling-only PR.

### Recommended option
Option 1, unchanged in intent, delivered as four PRs instead of one:
1. **T-0067 (this ticket, narrowed):** the `autopilot.reviewPolicy` key and the single-ticket `fix` phase.
2. **L-0666:** the stop-message contract (a test over every stop, and the rewording it forces).
3. **L-0667:** `/crew:graph` (`--status`, `--refresh`, `--query`), after T-0064 merges.
4. **L-0668:** tooling-only PR with the sabotage mutations for 1 and 2.

Why split: three unrelated mechanisms (a fail-closed phase decision, a message contract, a new command with a pair verifier), and a harness path that cannot ride with feature work. Each slice is under 300 added production lines.

### Open questions for the owner (recommendation applies until answered)
- T-0067 adds `autopilot.reviewPolicy` itself instead of waiting for T-0029 (recommended), or waits for T-0029.
- An unrefunded INCOMPLETE round keeps stopping, as main's sabotage rule demands (recommended), or is rerun once under `fix-and-rereview` as the original direction said.
- Under `fix-and-rereview`, a round-1 BLOCK is fixed unattended like a FIX (recommended; the original direction said so, and round 2 still judges the fix), or a BLOCK always stops.
- When the auto-accept guard passes but no receipt was written (a session died between the verdict and step 3.3), the stop names only the owner's accept (recommended, L-0666), or autopilot finishes the auto-accept itself (belongs with T-0073).
- `/crew:graph --refresh` waits for T-0064 (recommended), or ships first with a refusal that names T-0064.
