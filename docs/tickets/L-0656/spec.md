# L-0656 sleep overrides for keys that do not exist yet (review policy, held pings)          status: spec   risk: high
Split from T-0053. Written 2026-10-04 against origin/main `155fe6d8`.

**BLOCKED - do not implement yet.** The keys this overrides are not on main. Unblock rule: the
review half when `autopilot.reviewPolicy` is merged (T-0029 or T-0067); the notify half when T-0051
is merged. Re-read the merged code and rewrite Evidence and the key names before planning. If only
one half is unblocked, build that half and leave the other here.

## Intent
While asleep, autopilot uses the sleep value of the review policy, and it holds the pings that
only ask for attention, sending the morning summary once when sleep ends. Pings that report a
failure are never held.

## Design (to confirm against the merged dependencies)
- `autopilot.sleep.reviewPolicy`: `null` or one of the values `autopilot.reviewPolicy` accepts
  when it lands. Applied by the same overlay as `approval`. An invalid value keeps the day value,
  with a warning.
- `autopilot.sleep.notifyHold`: `null` or `true`. While asleep and `true`, the notify path drops
  events of the "waiting on you" kind and counts them; failure events (a failed deploy, a failed
  gate) are sent at once.
- Morning summary send: where L-0653 prints the summary (the first run after the window, and
  `wake`), the same text is passed to the notifier once, followed by the count of held pings.
- The hold is decided where the event is sent, in code, not in command prose.

## Exclusions
- No new review acceptance path and no edit to `review_ledger.py` or any `review_*.py`. Sleep does
  not make L-0510's auto-accept stricter or looser.
- No merge, PR or landing of a ticket: that is T-0011's ship policy. If T-0011 adds a key, its
  sleep override is a further small ticket.
- No change to which events exist or how Telegram is configured (T-0051).
- No machine-global layer.
- Sabotage mutations for this child land in their own tooling-only PR afterwards, under the
  standing rule.

## Evidence
Read at origin/main `155fe6d8`. These show what is absent; the positive evidence is written when
the dependencies merge.
- `git grep -n reviewPolicy origin/main -- plugin/crew ':!plugin/crew/tests'` prints nothing.
- plugin/crew/hooks/scripts/notify.sh:5: events are `phase | gate | review | waiting | done`;
  :33-35 the provider and the `notify.events` filter. No hold.
- plugin/crew/hooks/scripts/crew_autopilot.py:512-520: a FINDINGS round stands only through
  `review_ledger.receipt_stands`; the `--auto-accept` route is `/crew:review` step 3 (L-0510).
- plugin/crew/commands/autopilot.md section 4: "No deploy (T-0005), merge or PR (T-0011)".
- scripts/check-tooling-pr.py:58-87: `review_*.py` and `commands/review.md` are `HARNESS`. If the
  review policy's reader turns out to live there, this child's review half is a tooling PR.

## Unknowns
- The final name, values and reader of `autopilot.reviewPolicy`. Resolved when T-0029 / T-0067
  merge.
- The notifier's entry point and event names after T-0051. Resolved when it merges. On main the
  notifier is a shell script pair (`notify.sh`, `notify.ps1`); a hold there must be added to both
  flavours and read the sleep state through `crew_autopilot.py settings --json`, not re-derive it.
- Whether a held ping is dropped or queued. Default: dropped and counted; the summary carries what
  the owner needs. Owner question if T-0051's design keeps a queue.

## Touch
To be confirmed at unblock; expected:
- plugin/crew/hooks/scripts/crew_sleep.py
- plugin/crew/hooks/scripts/crew_autopilot.py
- plugin/crew/hooks/scripts/crew_state.py
- plugin/crew/hooks/scripts/crew_config_menu.py
- plugin/crew/hooks/scripts/notify.sh
- plugin/crew/hooks/scripts/notify.ps1
- plugin/crew/templates/config.template.json
- plugin/crew/tests/test_crew_autopilot_sleep.py
- plugin/crew/tests/test_crew_config.py
- plugin/crew/CONFIG.md
- plugin/crew/README.md
- plugin/crew/skills/crew-setup/SKILL.md
- plugin/crew/BUDGETS.md
- plugin/PLUGINS.md
- `docs/guides/crew/**` - guide sources and rebuilt outputs
- .crew/codemap/crew.md
- .crew/verify.json
- `.claude/rules/**` - regenerated with the code map
- `graphify-out/**` - rebuilt by graphify update
- CHANGELOG.md
- plugin/crew/.claude-plugin/plugin.json
- .claude-plugin/marketplace.json

## Acceptance checks
Test names are fixed now; commands are `python3 -m pytest plugin/crew/tests/test_crew_autopilot_sleep.py -q -k <name>`.
- [ ] `test_asleep_review_policy_override_applies`: asleep, the effective review policy is the
  sleep value; awake and state `unknown`, the day value.
- [ ] `test_invalid_sleep_review_policy_keeps_the_day_value`: a value outside the accepted set
  warns and changes nothing.
- [ ] `test_asleep_never_accepts_a_block`: with any sleep review policy, a round with a BLOCK
  still stops at `accept-review`.
- [ ] `test_held_ping_is_not_sent_asleep`: asleep with `notifyHold: true`, a "waiting" event sends
  nothing and the held count rises by one. Both shell flavours, the `.ps1` case skipping without
  `pwsh` (named absolutely, per the repo landmine).
- [ ] `test_failure_ping_is_sent_asleep`: a failure event is sent at once with the hold on.
- [ ] `test_hold_is_off_awake_and_when_unknown`: awake, or with a malformed schedule, every event
  sends as on main.
- [ ] `test_morning_summary_is_sent_once`: the first run after the window sends one message
  holding L-0653's summary and the held count; a second run sends none.
- [ ] `settings` no longer reports the two keys as "not available".
- [ ] `python3 scripts/check-tooling-pr.py` exits 0, or the review half is cut into a tooling PR
  if its reader is a harness path.
- [ ] Docs per the repo rule for a `plugin/crew/` change, guide outputs rebuilt, crew bumped with
  a CHANGELOG entry, `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
Must land first:
- T-0053 (ready; slice 1) and L-0653 (the summary text).
- T-0029 (in-progress) or T-0067 (ready): `autopilot.reviewPolicy`. Blocks the review half.
- T-0051 (approved): rebuilt notify. Blocks the notify half.
Coordinates with: T-0011 (approved; ship policy), T-0045 (direction; deploy results that ping),
T-0073 (direction; `reviewAcceptance`), T-0070 (spec; inert settings are loud).
Blocks: T-0054's "sleep mode" guide section being complete.

## Size
About 90 added production lines when both halves are built (overlay keys about 25, notifier hold
about 40 across both flavours, summary send about 25). One guard (the hold). If the notifier hold
grows past that, split the two halves.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
