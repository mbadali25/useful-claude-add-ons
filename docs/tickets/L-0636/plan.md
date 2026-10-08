# L-0636 plan            spec: docs/tickets/L-0636/spec.md

Written by the implementing session (rush g3d-bridge, 2026-10-05), on T-0030's ported
`crew_coord.py` and T-0032's `crew_bridge.py` (#434, the commit before this one). Crew version: the
group's placeholder, set in the group's last commit.

Anchors re-checked on this base: `crew_coord.Channel.write(change, message)` fetches, reads, calls
`change(files)` and pushes without force, retrying at most `MAX_RETRIES`; `LOG` is `log.jsonl`;
`log_line` writes `{at, event, ticket, holder, detail}` with `holder` the session id;
`current_holder`, `machine`, `stamp`, `parse_stamp`, `age_text`, `utcnow`, `safe`, `peer` keep
their names. `cmd_status` reads only `claims/` and never the log, so a new `rang` event is ignored
safely (the spec's stop condition does not apply). Nothing in `crew_coord.py` changes.

Decisions taken inside the spec:
- `change(files)` is not handed the fetched tip, so `crew_bridge.py` uses a `Channel` subclass that
  remembers the tip of its last fetch; the tip `change` sees is the one `write` just read.
- The `rang` line keeps `log_line`'s keys (`ticket` is the doorbell's `ref`) and adds `to`, `tip`,
  `machine` and `worktree`, so `pending` finds this worktree's rings after `/clear` changes the
  session id (the direction's "after `/clear` it does not even know it rang").
- A ring is this session's when its `holder` is this session id or its machine and worktree are
  this one's. It is cleared only by a later log line (file order) whose `holder` is neither the
  ring's nor this session's, so neither the ringer's own heartbeats nor the resumed session's lines
  clear it. Any line that is not a JSON object with the expected fields is `unknown`, never skipped.

### Step 1: `ring --to` and `pending`
Files: plugin/crew/hooks/scripts/crew_bridge.py, plugin/crew/tests/test_crew_bridge_pending.py
Test: python3 -m pytest plugin/crew/tests/test_crew_bridge_pending.py -q
Risk: high - a pending ring that disappears reads as consent
- [ ] `--to` checked against `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` (exit 2) before any fetch
- [ ] no session id: `unknown` exit 3, nothing written, no doorbell
- [ ] the write: one `rang` line in one commit on the fetched tip; absent channel refused; push
      failure `unknown - could not push` exit 3 with no doorbell; the push argv never forces
- [ ] `pending`: fetch failed `unknown` exit 3; corrupt line `unknown` exit 3; each pending ring
      `could not tell - ...` through `safe` and `[peer-written]`, exit 3; none `no pending doorbells`
- [ ] tests per the acceptance list, the clock injected through `crew_coord.utcnow`

### Step 2: the command text and docs
Files: plugin/crew/commands/autopilot.md, plugin/crew/README.md, .crew/verify.json,
.crew/codemap/crew.md, CHANGELOG.md, plugin/crew/BUDGETS.md
Test: python3 -m pytest plugin/crew/tests/test_crew_bridge_pending.py -q -k command; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py
- [ ] section 1 and the resume step (section 2's coord line) run `pending`; a `could not tell` line
      is reported to the owner and is never agreement; edited in place (120-line budget)
- [ ] README: `--to`, `pending`, and the limit that any other holder's line clears a ring
