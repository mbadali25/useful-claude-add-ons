# Cross-session messaging: an unanswered doorbell reads `could not tell` and is surfaced to the owner          status: spec   risk: high
Split from T-0032 (L-0636), 2026-10-04. Filed as L-0636.
## Intent
`crew_bridge.py ring --to <peer-label>` records the ring in the channel log (`event: rang`, the announced tip, the label, the time) in the same no-force write path T-0030 uses. `crew_bridge.py pending --channel <c> --remote <r>` fetches the record and lists every ring by this holder that has no later log line written by a different holder. Each is printed as `could not tell - no record change from <label> since the doorbell at <time> (<age>)`. A ring with a later peer line is not listed. Nothing turns a pending ring into consent: there is no timeout, no retry count and no "delivered" state. `commands/autopilot.md` runs `pending` in its resume step and in section 1 (status), and tells the session to report the lines to the owner and not to act as if the peer agreed.
## Exclusions
- No new autopilot stop reason and no change to `crew_autopilot.py`, `crew_status.py` or `crew_resume.py` (`SEAM` paths, `scripts/check-tooling-pr.py:89-95`).
- No re-ring, no automatic retry, no escalation message to the peer.
- No delivery receipt. The tool contract gives none; the record moving is the only acknowledgement.
- No `sabotage*.py` file (L-0638). No hook. No config key.
- No force push, as in T-0030.
## Evidence
- T-0030's direction, part 6 and "Facts this rests on" (remote and cloud sends give no delivery confirmation; a session may hold messages; cloud sessions cannot reply): `.work/tickets/T-0030/direction.md`.
- On branch `T-0030-coord` (ec9a28a2), not on origin/main: `crew_coord.py` `log_line` (`:1190`) appends to `log.jsonl` (`LOG`, `:164`); `Channel.write(change, message)` (`:704` area) commits on the fetched tip and pushes without force, retrying at most `MAX_RETRIES` (`:159`); `current_holder` (`:428`) and `same_holder` (`:442`). Re-check after T-0030 merges.
- `plugin/crew/commands/autopilot.md:29-36` (origin/main 155fe6d8) is section 1, status.
- T-0032's `crew_bridge.py` does not exist on origin/main; this ticket extends it.
## Unknowns
- **The log line's shape after T-0030 lands.** `rang` must be a new event value that T-0030's `status` prints or ignores safely. If `crew_coord.py` refuses unknown events, stop and return to the owner: changing it is outside Touch.
- **What counts as "the peer moved the record".** Taken: any log line after the ring whose holder is not this holder. A third session on the channel would also clear it. With `--to` recorded, a stricter match is possible only if T-0030's holder record carries a label a peer can be matched to; it does not today. Stated in the README as a limit.
- **Log growth.** One line per ring. No pruning here.
## Touch
- `plugin/crew/hooks/scripts/crew_bridge.py`
- `plugin/crew/tests/test_crew_bridge_pending.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `.crew/codemap/crew.md`
- `CHANGELOG.md`
## Acceptance checks
Tests in `plugin/crew/tests/test_crew_bridge_pending.py`, against a local bare remote: `python3 -m pytest plugin/crew/tests/test_crew_bridge_pending.py -q`.
- [ ] `ring --to <label>` appends exactly one `rang` log line (holder, label, tip, time) in one commit whose parent is the fetched tip, then prints the doorbell line. Without `--to`, `ring` behaves as in T-0032 and writes nothing (two tests).
- [ ] Must-block: when the push fails after the retries, `ring` prints `unknown - could not push` and exits 3 without printing a doorbell line. Every `git push` argv is asserted to hold no `--force`, `-f`, `--force-with-lease` or `+` refspec (test).
- [ ] `pending` lists a ring with no later line from another holder as `could not tell`, with its age from an injected clock, and exits 3. A ring followed by another holder's line is not listed, and with none pending it prints `no pending doorbells` and exits 0 (three tests).
- [ ] Must-block: a ring followed only by this holder's own lines stays pending. A ring 30 days old stays pending. A failed fetch prints `unknown - could not fetch` and exits 3, never `no pending doorbells`. A corrupt log line reads `unknown`, never skipped (one test each).
- [ ] `--to` accepts only `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`; anything else exits 2. The label is printed through `safe` and labelled `[peer-written]` when read back (test).
- [ ] `commands/autopilot.md` runs `pending` in section 1 and in the resume step, and states that a `could not tell` line is reported to the owner and is never agreement (test on the command text). `python3 plugin/crew/hooks/scripts/_test/validate-prompts.py` passes.
- [ ] README documents `--to`, `pending`, and the limit that any other holder's line clears a ring. `.crew/verify.json` maps the new test file. Crew is bumped one patch above origin/main with a CHANGELOG entry; `python3 scripts/check-marketplace.py` passes after the commit and `python3 scripts/check-tooling-pr.py` exits 0.
## Dependencies
Must land first: T-0030 (in-progress; the write path and log), T-0032 (ready; `crew_bridge.py`). Ordering only: T-0031 (ready). Blocks: L-0638.
## Size
About 150 added production lines. One fail-closed state (pending or cleared). No harness path.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
