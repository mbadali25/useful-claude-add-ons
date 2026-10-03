# T-0051 direction          status: ready   risk: high   priority: high

## Ask
Owner (Matthew Badali, 2026-09-26): "Another thing to bring back is crew notify. We need to make it
more useful and less spammy, so only notify on blockers, deployments, and if it has questions.
Currently, we're using Telegram. I have a notify skill in this repo that I would like to base it off
of, but if you want to search another repo for Telegram notify, please do if it's better than mine."

Owner answers during brainstorm (2026-09-26):
- Questions: **ping only**. Telegram never carries anything back into a session; approvals stay a
  typed `/crew:approve`.
- Blockers, all four: a plan waiting on approval (batched, one message per run, including approvals an
  edit made stale); a ticket out of review rounds with BLOCKs still open; a lane or agent that died or
  stalled; the verify gate or completion audit refusing at Stop after the session's own retry.
- Deployments: **every `/crew:promote` result**. A pass is a silent message; a failure is a loud one.
- Questions: an AskUserQuestion / MCP elicitation, **and** a tool-permission prompt. A plain
  "finished, idle" never pings.

## What exists today (measured 2026-09-26 on T-0001-spec-templates @ c5f4aa62)
- crew sends nothing here: `.crew/config.json` has `notify.provider: "none"`.
- `plugin/crew/hooks/scripts/notify.sh` reads **only** `.crew/config.json`, while
  `plugin/crew/hooks/scripts/crew_config.py:414` says `notify` belongs to the global layer ("the
  person's own chat, not the project's"). A Telegram block in `~/.claude/crew/config.json` is ignored.
  Needs checking whether `notify.ps1` does the same.
- The spam source: `hooks.json`'s `Notification` entry sends `waiting` on **every** Notification,
  whatever its type, so idle prompts ping too. `/crew:review` pings per review and `/crew:done` per
  ticket.
- Send side: one `curl -m 10`, no retry, no 429 handling, no dedupe. Windows twin `notify.ps1` with
  `event_claim.py` electing one sender.
- Your notify skill (`skills/notify/`) has the best-engineered Telegram send path found: honors 429
  `retry_after` (`skills/notify/scripts/tg.py:53-59`), paces to about 1/s (`tg.py:21`), HTML with
  escaping (`tg.py:80`), stdlib only, Windows-aware. On this machine its `~/.config/notify/config.json`
  still holds the example `chat_id` and `notifyd` is not running, so it is not delivering either.
- Other repos searched. The only idea worth taking is from
  `/repos/anew/tss-owed-findings/scripts/monitoring/proposed/` (v2): dedupe by fingerprint with a
  re-alert window, and **advance the dedupe state only after a confirmed send** (`v2.sh:183-197`).
  The official Telegram channel plugin is a two-way chat bridge, which the owner ruled out.

## Options
1. **Rebuild crew's sender as one Python module, porting the notify skill's send path
   (recommended).** New `crew_notify.py`: the event vocabulary `blocker | deploy | question`, the
   config read from the global layer with the repo layer overriding it, a fingerprint dedupe that
   advances only on a confirmed send, 429 `retry_after` and pacing ported from `tg.py`, and silent
   vs loud per event. `notify.sh` and `notify.ps1` become thin wrappers that keep `event_claim.py`.
   The `Notification` hook filters on the payload's notification type. Tradeoff: copies about 60
   lines from `tg.py` instead of sharing them, because crew cannot depend on a separate marketplace
   entry being installed.
2. **crew calls the notify skill's `notify.py` when it is installed.** One Telegram code path and
   per-job topics for free. Tradeoff: a hard runtime dependency across two marketplace entries.
   crew would go silent wherever the skill is missing, and a skill-side change could break crew
   without a crew version bump. Two config files (`~/.config/notify/` and crew's) would also
   describe one bot.
3. **Keep bash + PowerShell and only change events and filtering.** Smallest diff. Tradeoff: every
   new rule (dedupe, 429, config layering) is written twice and drifts between the twins. That drift
   is how the unknown-provider claim leak shipped (`notify.sh:66-74`).

## Recommendation
Option 1. It keeps crew self-contained, puts the dedupe and retry logic in one place instead of two
shells, and bases the Telegram handling on your skill as asked.

The shape, sized down:
- **Events.** `blocker` (four reasons above), `deploy` (pass silent, fail loud) and `question`
  (loud). `phase`, `review`, `done` and `waiting` are retired. An old config naming them maps to the
  new set with a one-line notice, never a silent drop.
- **Where each fires.**
  - Approval-waiting: when autopilot, a wave or a workflow stops on approval, one batched message
    names the ids and the exact commands to type.
  - Out of rounds: the review ledger's last round records BLOCK.
  - Lane died or stalled: T-0049's in-flight marker going stale, once T-0049 lands. Until then,
    only a workflow lane that returns an error.
  - Gate or audit refused: the second consecutive Stop refusal for the same ticket.
  - Deploy: `/crew:promote`'s existing notify line.
  - Question: the `Notification` hook, permission and elicitation types only.
- **Payload.** Keeps today's one-line discipline: repo/branch, ticket, reason and the command that
  unblocks it. No diffs, findings text or secrets.
- **Anti-spam.** A fingerprint of event + ticket + reason, re-alerting after a window (default 6h).
  State lives under `<git-common-dir>/crew/notify/` and advances only on HTTP 200.
- **Config.** Global `notify` block honored, repo overrides. Telegram only is proven here. The
  Teams branch is kept, but no live test is claimed for it.
- **Hook rule.** No new hook is registered; the existing `Notification` hook changes behaviour. It
  blocks nothing (exit 0 always), so the must-block suite rule does not apply. A must-send /
  must-stay-quiet suite covers the event filter and dedupe, sabotage-tested.
- crew version bump in both `plugin.json` and `marketplace.json`.

## Open questions (resolve at spec)
- Which `notification_type` values a real AskUserQuestion and a permission prompt produce. Measure
  them from a live hook payload; do not take them from docs.
- Reuse `~/.config/notify/config.json`'s `telegram` block as a fallback, so one bot is configured
  once for both? Recommendation: yes, read-only, with crew's own block winning.
- Re-alert window default: 6h (taken from the TSS watcher) or per event?
- "Stalled" needs a timeout. Take it from T-0049's heartbeat TTL rather than inventing a second one.

## Depends on
Nothing to start. The "lane died" reason becomes complete with T-0049; the approval batch message
reads better once T-0024 (group approval) lands, since it can then name one command.

## Approval
Direction approved by the owner, 2026-09-26: "You can self-approve on these tickets." Recorded as INDEX status `ready`. Open questions take the recommendation given above.
Split 2026-09-26 by owner decision: "Those features will be a new ticket." The failure/blocker pings (the `blocker` event and its four reasons) moved to T-0060; this ticket keeps the sender, the deploy ping and the question/"stopped" ping (`.work/tickets/T-0051/spec.md` `## Split`).

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
