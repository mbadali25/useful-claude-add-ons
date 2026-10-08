# L-0653: sleep log and morning summary

Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`.

## Ask
Owner, 2026-09-26: while asleep autopilot makes its own decisions, and one morning summary says
what it did. The direction's words: "The log turns overnight decisions into something you can
review in the morning, not something you have to take on trust."

## What exists
- After T-0053 and L-0652: decisions made asleep are printed (`self-approved ... (asleep ...)`,
  `taken:` lines) and listed in the run's final report. Nothing collects them across runs or
  sessions, and a `/clear` loses the report.
- `crew_autopilot.py approve` is the one place a self-approval is written
  (`crew_autopilot.py:1129-1151`). A taken answer is written by the session into `questions.md`
  and checked by `questions-check` (`autopilot.md` section 3).
- `.work/` is gitignored, so a log there is local to the machine.
- Telegram pings are T-0051 (approved, not merged). Until then a summary can only be printed.

## Options
1. **An append-only `.work/autopilot/sleep-log.md`, written by `approve` and by a small `sleep-note`
   subcommand; `sleep-summary` prints what is unreported (recommended).** `settings` says when
   unreported entries exist, so the first `/crew:autopilot` after the window prints the summary.
2. Derive the summary from receipts and `questions.md` files. No new writer, but the receipt does
   not say it was written asleep, and a closed ticket's files are not all kept.
3. Send it only by Telegram. Blocked on T-0051 and silent where notify is off.

## Recommendation
Option 1. Sending the same text by Telegram is L-0656.

## Open questions
- Summary trigger. Recommendation taken (from the 2026-09-26 direction): at the first autopilot
  run after the window ends, and on `wake`.

## Depends on
T-0053, L-0652 (for `wake`).

## Approval
Not yet approved. Prepared for hand-off on 2026-10-04 under the owner's go for T-0053.
