# T-0053 direction          status: ready   risk: high

## Ask
Owner (the owner, 2026-09-26): "Also, could we set a sleep mode where we could change
self-approve to risk and self based on time of day or setting? Essentially, if I'm setting settings
overnight, instead of letting it sit there, it can make its own decisions while I'm not there."

Owner answers during brainstorm (2026-09-26). While asleep, autopilot also:
- answers its own questions (`questions: self`), taking the researched recommendation and recording
  why;
- accepts clean reviews (no BLOCK and no FIX) and lands the ticket; any finding still waits;
- runs non-production deploys (T-0045's `deploy: nonprod`); production always waits;
- holds Telegram pings (T-0051) and sends one morning summary when sleep ends. A deploy failure
  still pings at once.

## What exists
- T-0010 defines `autopilot.approval` and `autopilot.questions`, each `human|self|risk`, default
  `risk`, read by `approval_policy` on every call (`T-0010-policies` branch,
  `plugin/crew/hooks/scripts/crew_autopilot.py:691-776`). The policy is a single static value; nothing
  varies it by time.
- T-0029 has `autopilot.reviewPolicy stop|clean-only|fix-and-rereview`; T-0045 has
  `autopilot.deploy none|nonprod`; T-0051 decides what pings.
- The owner's configs today: this repo and one other repo of the owner's have `approval: self`. Sleep mode gives a safer default
  (`risk` while present) without losing overnight progress.

## Options
1. **A `sleep` overlay on the autopilot block, entered by schedule or by command (recommended).**
   - `autopilot.sleep` holds `schedule` (for example `"22:00-07:00"`, machine local time, may cross
     midnight) and `overrides`: the owner's four answers as values of existing keys (`approval`,
     `questions`, `reviewPolicy`, `deploy`, plus `notify.hold`).
   - `/crew:autopilot sleep` and `/crew:autopilot wake` switch it by hand. A manual state beats the
     schedule until the next window edge, and it records who set it and when.
   - One resolver, `effective_settings(now)`, is what every policy reader calls. Settings are
     re-resolved per decision, never cached for a run, so a run that crosses 07:00 goes back to the
     day values at the next decision.
   - Every decision made asleep is logged to `.work/autopilot/sleep-log.md`: ticket, what was
     decided, the recommendation it took, and the setting that allowed it. The morning summary is
     built from that log.
2. **Time-of-day values inside each policy** (`approval: {day: risk, night: self}`). No new block,
   but every policy key grows a second shape, each reader has to parse it, and "which window is
   this" is decided in five places.
3. **Manual only** (`sleep`/`wake`, no schedule). Simplest. But forgetting `sleep` at night means
   the exact idle night this is meant to prevent, and forgetting `wake` leaves it on self all day.

## Recommendation
Option 1. One overlay and one resolver keep "is it night" in a single place. The overrides reuse the
exact values the underlying tickets define, so there is no second vocabulary. The log turns overnight
decisions into something you can review in the morning, not something you have to take on trust.

## Guardrails (fixed, not settings)
- Never in sleep: production deploys, `AUTONOMOUS_STOPS` (git destruction, deleting the codemap,
  rewriting metrics, offboarding a role), accepting a review with any finding, and Jira-mode splits
  (T-0052).
- "Could not tell" wakes. If the clock, the schedule or the manual state cannot be read, the day
  values apply.

## Open questions (resolve at spec; the recommendation applies unless measurement says otherwise)
- Layer: sleep is about the person, not the repo, so global with a repo override? That depends on
  T-0050 making `autopilot` settable globally. Recommendation: global once T-0050 lands, repo-only
  until then.
- Morning summary trigger: the schedule edge fires only if something is running at 07:00.
  Recommendation: send it at the first autopilot decision after the window ends, and on `wake`.

## Depends on
T-0010 (policies). Coordinates with T-0029 (`reviewPolicy`), T-0045 (`deploy`), T-0051 (notify hold)
and T-0050 (global layer). Each override is inert until the ticket defining its key has landed, and
it reads as "not available yet", never as silently on.

## Approval
Direction approved under the owner's standing authorization (2026-09-26, "no longer ask me for
approvals"). Open questions take the recommendation.

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
Checked against origin/main `155fe6d8` (crew 1.0.322). The owner was not available; each question
below takes the recommended option and is listed again under "Open questions for the owner".

### Still true
- Nothing on main implements sleep mode. `git grep -nIiE "autopilot\.sleep|effective_settings|sleep-log" origin/main -- plugin/crew scripts docs`
  prints nothing, `git log origin/main -i --grep=sleep` shows only test-timing commits, and
  `crew_autopilot.SUBCOMMANDS` is `("status", "run", "assign", "goal", "focus")`
  (`plugin/crew/hooks/scripts/crew_autopilot.py:224`).
- The two policies are static. `_settings_at` reads `autopilot.approval` and `autopilot.questions`
  once per call from the repo config (`crew_autopilot.py:788-827`), and nothing varies them by time.
- They are re-read on every decision: `_decision` calls `settings` each time (`:1022-1026`), and
  `crew_ticket.accepted` and `scope_guard.py` re-ask `approval_policy` on every read
  (`crew_ticket.py:670-684`, `scope_guard.py:247`). So one overlay inside `_settings_at` reaches
  every reader. Option 1's "one resolver" still fits the code.

### What changed since 2026-09-26
- T-0010 is merged (PR #261, crew 1.0.61). Its code is on main, not on a branch: `POLICIES` at
  `crew_autopilot.py:989`, `approval_policy` at `:1034`, `question_policy` at `:1075`.
- T-0072 is merged: `autopilot.deploy` is `none|nonprod|all` and `deploy_allowed` answers the policy
  (`crew_autopilot.py:162`, `:957`). Nothing dispatches a deploy yet (T-0045 is still `direction`),
  and `settings` says so in a warning (`:811`).
- `autopilot.reviewPolicy` does not exist on main (T-0029 in-progress, T-0067 ready). A CLEAN round
  already writes its receipt and `next` goes on to `/crew:done` with no owner step, and L-0510 (done)
  auto-accepts a final round with 0 BLOCK at every hour (`crew_autopilot.py:512-520`). So "accept
  clean reviews" needs no sleep code today.
- Notify hold has no key to override: T-0051 is `approved`, not merged. `notify.sh` on main knows
  `phase|gate|review|waiting|done` events only.
- The `autopilot` block is still repo-only (`crew_config.py:389-394`). T-0050 and T-0070, which
  would allow a machine-global layer, are both at `spec`. So sleep is repo-only for now, as the
  direction's first open question already recommended.
- T-0087 is merged: `plugin/crew/tests/sabotage*.py` is a harness path
  (`scripts/check-tooling-pr.py:79`), so sabotage mutations cannot ride in the PR that changes
  `crew_autopilot.py`. Under the standing split rule they land as a tooling-only PR after it.
- `plugin/crew/commands/autopilot.md` is 109 lines against a tested budget of 110
  (`plugin/crew/tests/test_lifecycle_commands.py:112`). New behaviour has to be explained by
  `crew_autopilot.py` output and CONFIG.md, not by new command prose.

### Found while checking (not in the 2026-09-26 direction)
- **A plan self-approved asleep stops standing in the morning.** `crew_ticket.accepted` keeps an
  `autopilot` receipt only while `approval_policy` still allows it. With day `risk` and night
  `self`, a `risk: high` ticket approved at 23:00 reads unapproved at 07:00 and autopilot stops at
  `approve` until the owner types `/crew:approve <id>`. The work done overnight stays. Recommended:
  keep this. It costs one command per in-flight ticket, the owner sees each plan the night
  approved, and changing it means editing `crew_ticket.py`, a harness path.
- **A manual `sleep` is something the session itself could run.** The schedule is the owner's
  config; a CLI `sleep` is a command. Recommended (L-0652): honour a manual `sleep` only where
  `scope.allowCliApproval` is exactly `true`, the same opt-in that lets a CLI approval count.
  `wake` is always allowed, because it only lowers authority.

### Recommended option
Option 1 still: one `autopilot.sleep` overlay, one resolver, re-resolved per decision. Two changes
to its shape:
1. The overrides are direct keys of `autopilot.sleep` (`autopilot.sleep.approval`,
   `autopilot.sleep.questions`), with no `overrides` sub-object. Every default is then a scalar
   leaf (`null`), which the config menu, `merge_defaults` and CONFIG.md's leaf counts already handle
   (`tickets.baseBranch` is the precedent).
2. It is built in slices, because the whole direction is over the size rule and mixes a harness
   path with feature work:
   - T-0053 (this ticket): the schedule, the resolver and the `approval` / `questions` overrides.
   - L-0651: the sabotage mutations for that slice (tooling-only PR).
   - L-0652: manual `/crew:autopilot sleep` and `wake`.
   - L-0653: the sleep log and the morning summary.
   - L-0654: the `deploy` override (`nonprod` only) and "production always waits" while asleep.
   - L-0655: the sabotage mutations for L-0652 to L-0654 (tooling-only PR).
   - L-0656: the overrides whose keys do not exist yet (`reviewPolicy`, held pings). Blocked on
     T-0029 / T-0067 and T-0051.

### Open questions for the owner
Each has a default already taken in the specs.
1. Morning re-ask (above). Default: keep it. Alternative: a receipt written asleep stands until the
   ticket closes, which needs a `crew_ticket.py` change in its own tooling PR.
2. One window for every day. Default: yes, one `HH:MM-HH:MM` string. Alternative: per-weekday
   windows (weekends all day), a later ticket.
3. Manual `sleep` gating (L-0652). Default: needs `scope.allowCliApproval: true`.
4. A manual `sleep` with no schedule configured (L-0652). Default: it ends after 12 hours or at
   `wake`, whichever is first.
5. Should sleep be stricter than day about review findings? L-0510's 0-BLOCK auto-accept runs at
   every hour today. Default: sleep leaves it alone. The 2026-09-26 guardrail "never accept a
   review with any finding while asleep" would need a harness change in `review_ledger.py`.
6. `autopilot.md`'s 110-line budget (L-0652 and L-0653). Default: reword inside the budget and put
   the detail in command output. Alternative: raise the budget.
