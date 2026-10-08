# L-0656: sleep overrides for keys that do not exist yet (review policy, held pings)

Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`.

## Ask
Owner, 2026-09-26. While asleep, autopilot also:
- accepts clean reviews (no BLOCK and no FIX) and lands the ticket; any finding still waits;
- holds Telegram pings and sends one morning summary when sleep ends. A deploy failure still pings
  at once.

## What exists (and what does not)
- `autopilot.reviewPolicy` is not on main. T-0029 (in-progress) and T-0067 (ready) define
  `stop|clean-only|fix-and-rereview`. Today a CLEAN round needs no acceptance, and L-0510 (done)
  auto-accepts a final 0-BLOCK round at every hour.
- Landing a ticket (PR or merge) is T-0011 (approved, not merged). `autopilot.md` section 4 says
  "No ... merge or PR (T-0011)".
- Rebuilt notify with Telegram subjects is T-0051 (approved, not merged). `notify.sh` on main
  sends `phase|gate|review|waiting|done` events with no hold.
- After T-0053, any of these keys under `autopilot.sleep` reads "not available in this crew
  version; it has no effect". After L-0653, the morning summary exists as printed text.

## Options
1. **Wait, then add each override when its key lands (recommended).** `sleep.reviewPolicy` after
   T-0029 / T-0067; `sleep.notifyHold` and the Telegram summary after T-0051. Each is a small
   addition to the overlay T-0053 built.
2. Define the keys now and leave them inert. Refused: a key that is accepted and does nothing is
   what "inert settings are loud" (T-0070) exists to stop.
3. Build a sleep-only review acceptance now. Refused: it would be a second acceptance path beside
   `review_ledger.py`, in a harness file.

## Recommendation
Option 1. This child is blocked until at least one of its dependencies merges, and may be planned
as two tickets then (review policy, notify) if both are not ready together.

## Open questions
- Should sleep be stricter than day about findings (the 2026-09-26 guardrail "never accept a
  review with any finding asleep")? L-0510 is the later owner decision and applies at every hour.
  Recommendation taken: leave L-0510 alone.

## Depends on
T-0053, L-0653, and T-0029 / T-0067, T-0051, T-0011.

## Approval
Not yet approved. Prepared for hand-off on 2026-10-04 under the owner's go for T-0053.
