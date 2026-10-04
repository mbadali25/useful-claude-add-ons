# L-0652 plan: manual /crew:autopilot sleep and wake          status: plan

Built on T-0053-build `610deaea` merged over origin/main `86d96fa1`. Line numbers re-read there.

## Decisions on the spec (each the stricter reading)
- D1. A state file that exists but cannot be trusted (not JSON, not an object, a field missing or
  malformed, `at` in the future, `until` more than 24 hours after `at`, unreadable) reads as
  `unknown`, not as "no manual state": per key the stricter of the day value and the night override
  (T-0053's could-not-tell rule), with a warning naming the file and the reason. A file that is
  merely expired (`until` not after now, otherwise valid) is "no manual state", with a warning.
- D2. A manual `asleep` is honoured at READ time too only while `scope.allowCliApproval` is exactly
  `true`; otherwise it reads as `unknown` (tighten-only) with a warning. Turning the switch off
  therefore ends a sleep set earlier, and a forged `asleep` file cannot grant anything the CLI
  would have refused.
- D3. A manual `awake` while the schedule says asleep (or cannot tell) applies only night overrides
  that are STRICTER than the day value. `wake` never refuses (owner question 1), but neither it nor
  a forged `awake` file can loosen a night value the owner made stricter than the day.
- D4. `crew_sleep.py` stays pure (T-0053's test forbids file writes there): it validates the record
  and computes `until`; `crew_autopilot.py` reads and writes the file through
  `crew_ticket._read_json` / `_write_json` (temp file, then `os.replace`).
- D5. `sleep` also refuses when `autopilot.sleep` is not an object or its schedule does not parse
  (could-not-tell). `--by` defaults to `cli`; it is bounded when printed.

## Steps (test first: each test red, then code, then green)
1. crew_sleep: `MANUAL_SLEEP_HOURS`, `MANUAL_FILE`, `read_manual(found, when)`,
   `next_edge(minute, when)`, `sleep_until`, `resolve(..., manual=None, sleep_allowed=True)` with
   `source`, `until`, `by`, `tightenOnly`. Tests: the eight untrusted shapes, expiry, 24-hour cap.
2. crew_autopilot: `_manual_path`, `_manual_found`; `_sleep_at` passes the manual state and the
   gate; `_overlay` honours `tightenOnly`; `_decision` names a manual sleep; `_sleep_line` adds
   `source=` and `until=`.
3. CLI `sleep` / `wake` (`_manual_main`): refusals exit 2 and write nothing; a crash exits 1.
   Tests: acceptance must-allow/must-block list in spec.md, linked worktree.
4. Router: `SUBCOMMANDS` and `AVAILABLE` gain both; `route_args` refuses a second word.
5. Only-writer test extended; every statement of the writer rule names approve, sleep, wake.
6. autopilot.md within its 110 lines; README, CONFIG §20, PLUGINS.md, guides, codemap, verify.json,
   CHANGELOG; docs/tickets/L-0652/ removed in the last content commit; version last.

## Sabotage (run here; entries belong to L-0655)
- S1 untrusted file reads as absent instead of unknown. S2 drop the read-time allowCliApproval
  gate. S3 drop `tightenOnly` from `_overlay`. S4 drop the 24-hour cap. S5 `sleep` skips the gate.
  S6 `route_args` accepts `sleep T-0001`.
