# L-0517: heavy-run logs each lane's slot wait (lane, slot, waited seconds, start/end) so contention is measurable          status: spec   risk: low
Written against origin/main `a555ff37`. Repository tooling: no plugin version, no `plugin/crew/` change.
Two parts: a machine-local edit to `/root/crew-tmp/heavy-run` (untracked; shipped here as a reviewed patch the
owner's local session applies) and an in-repo change to `scripts/gate-runner.py` (L-0513's runner).

## Intent
Every heavy-run invocation appends one JSON line to `/root/crew-tmp/heavy-run-waits.jsonl` (path overridable by
`HEAVY_RUN_WAITS_LOG`) when it exits, from its existing EXIT trap:
`{"lane", "slot", "prio", "pid", "requested", "acquired", "released", "waited_s", "held_s", "rc", "cmd"}` with
UTC ISO-8601 times, `slot` the basename of the lock file taken (`heavy.lock`, `heavy.lock.2`, `heavy.lock.prio`,
`heavy.lock.prio.2`), and `cmd` the first 120 characters of the command. A call that exits before it gets a slot
(signal while waiting) logs `slot: null, acquired: null, held_s: null` and `waited_s` so far. `lane` is the
matched priority tag, else the `TMPDIR` basename when `TMPDIR` is under `/root/crew-tmp/`, else the basename of
`git rev-parse --show-toplevel` run in `$PWD`, else `"unknown"`. While it holds a slot the wrapper exports
`HEAVY_RUN_SLOT=<slot basename>` to the command. `scripts/gate-runner.py --inner` records `HEAVY_RUN_SLOT` (or
`null` when unset or empty) as `slot` in `heavy-part.json`; the outer runner copies it to `status.json`'s
`heavy_run.slot` beside the existing `waited_seconds`. Contention becomes measurable with `jq` over one file.

## Exclusions
- No move of heavy-run into the repo, no install-script change (direction Option 3, rejected).
- No change to slot selection, priority ranking, the memory cap, `PYTEST_XDIST_AUTO_NUM_WORKERS`, the exit code
  or anything the wrapped command sees except the one new `HEAVY_RUN_SLOT` variable.
- No log rotation, no aggregator script, no dashboard.
- No change to gate-runner's step table, states, exit codes, `waited_seconds` computation or `SLOT_WAIT_ALLOWANCE`.
  `HEAVY_RUN_SLOT` never affects a step's state: it is recorded, not trusted.
- No `plugin/crew/` change and no crew version bump (repository tooling, like L-0513).
- No harness path (`HARNESS` in `scripts/check-tooling-pr.py`): `scripts/gate-runner.py` is not one.

## Evidence
origin/main `a555ff37`; the wrapper at its 2026-10-03 06:44 copy (89 lines, sha256 `171b95c2...`), snapshotted to
`docs/tickets/L-0517/heavy-run.snapshot` because a cloud session cannot read `/root/crew-tmp`:
- heavy-run slots `heavy-run.snapshot:7` (`heavy.lock`, `heavy.lock.2`); priority slot list and 6 GB gate for
  `heavy.lock.prio.2` `:60-67`; `resolve_prio` (tag match on TMPDIR / command / PWD) `:16-27`; existing EXIT trap
  (marker removal only) `:32`; acquisition `flock -n "$fd"` `:69`; run under `systemd-run --scope` `:77-78`, else
  direct `:80`; release and `exit $rc` `:82-84`; poll `sleep 5` `:88`. Nothing is logged anywhere.
- `scripts/gate-runner.py:102` `DEFAULT_HEAVY_RUN = "/root/crew-tmp/heavy-run"`; `:112` `SLOT_WAIT_ALLOWANCE = 3600`.
- `scripts/gate-runner.py:830-831` `run_inner` writes `{"started": time.time(), "pid", "steps"}` to the part file.
- `scripts/gate-runner.py:905` `_part` reads `steps` and `started` (finite non-bool number, else None).
- `scripts/gate-runner.py:1040-1052` outer: `launched = time.time()`, then
  `hr["waited_seconds"] = round(inner_started - launched, 1)` when `started` is valid.
- `scripts/gate-runner.py:1420` `hr = {"mode", "path", "launched", "rc", "waited_seconds", "note"}`, written as
  `status["heavy_run"]` `:983`. No slot field.
- `scripts/_test/gate-runner.py:496` asserts the `heavy_run` keys; `:992-1006` the neighbour case (malformed
  `started` leaves `waited_seconds` absent) is the model for the new malformed-slot case; `fake_heavy_run` builds
  the fake wrapper; `CASES` `:1722`.
- `.crew/verify.json` rule for `scripts/gate-runner.py` + `scripts/_test/gate-runner.py` (`seconds: 60`, search
  `"L-0513: the one local gate runner"`).
- `.crew/codemap/verification-harness.md:778` describes the gate-runner rule (anchor `9cdc9eb3`).
- `CHANGELOG.md:3429` L-0513's entry, the form for a "repository tooling, no plugin version" entry.

## Unknowns
- `git rev-parse` in the wrapper costs a fork per call and runs in `$PWD`; if `$PWD` is not a work tree it falls
  through to `"unknown"`. Acceptable (default taken in direction.md).
- JSON escaping in bash: `cmd` and `lane` may hold quotes or backslashes. The patch escapes `\` and `"` and drops
  control characters before `printf`; a line that would not parse is the failure the acceptance check targets.
- Who applies the wrapper patch: the owner's local session, before landing; the cloud session writes and
  checks only that the patch applies to `heavy-run.snapshot` and passes `bash -n` (the lock paths are
  hard-coded to `/root/crew-tmp`, which a cloud host does not have). The LOCAL checks below are the proof.

## Size and split
About 25 changed lines in the wrapper (one function, trap change, three timestamps, one export), about 6
production lines in `gate-runner.py`, two or three new suite cases. No split.

## Touch
- `scripts/gate-runner.py`
- `scripts/_test/gate-runner.py`
- `.crew/verify.json` (the gate-runner rule's `why` and re-measured `seconds`)
- `.crew/codemap/verification-harness.md` (gate-runner rule paragraph; re-anchor)
- `CHANGELOG.md` (repository tooling entry, no plugin version)
- `docs/tickets/L-0517/heavy-run.patch` (new: unified diff against `heavy-run.snapshot`)
- `docs/tickets/L-0517/` (removed in the final PR after the patch is applied locally)
- Refresh artifacts per standing rule (`graphify-out/`, codemap anchors).

Not in Touch: `plugin/**` (no crew change), install scripts, `docs/diagrams/` (no box changes),
`scripts/check-tooling-pr.py`.

## Acceptance checks
Commands from the repo root unless marked LOCAL (owner's host, after applying the patch).
- [ ] Gate runner records the slot: with a fake heavy-run that exports `HEAVY_RUN_SLOT=heavy.lock.2`,
  `status.json` has `heavy_run.slot == "heavy.lock.2"`; unset or empty gives `null`; `waited_seconds` unchanged.
  `python3 scripts/_test/gate-runner.py` (new cases `case_heavy_run_slot_recorded`, `case_heavy_run_slot_absent_is_null`)
- [ ] A malformed `slot` in `heavy-part.json` (non-string, over 64 chars, containing `/`) reads `null`, never an
  exception, and no step's state changes. Same suite, `case_heavy_part_bad_slot_is_null`.
- [ ] `heavy_run` keys assertion (`:496`) extended with `slot`. Same suite.
- [ ] `python3 scripts/gate-runner.py --check-ci` still passes (no table change).
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` (no harness path).
- [ ] Patch applies: `cp docs/tickets/L-0517/heavy-run.snapshot $T/hr && patch $T/hr docs/tickets/L-0517/heavy-run.patch && bash -n $T/hr`.
- [ ] LOCAL: `/root/crew-tmp/heavy-run true; tail -1 /root/crew-tmp/heavy-run-waits.jsonl | jq -e '.slot != null and .waited_s >= 0 and .rc == 0 and .lane != null'`.
- [ ] LOCAL contention: with `HEAVY_RUN_WAITS_LOG=$T/w.jsonl`, hold both shared slots
  (`flock /root/crew-tmp/heavy.lock sleep 12 & flock /root/crew-tmp/heavy.lock.2 sleep 12 &`), then
  `/root/crew-tmp/heavy-run true` from a non-priority lane; its line has `waited_s >= 5`.
- [ ] LOCAL signal while waiting: same held slots, `timeout -s TERM 3 /root/crew-tmp/heavy-run true`; the line has
  `acquired == null` and `slot == null`. Every line in `$T/w.jsonl` parses: `jq -c . $T/w.jsonl >/dev/null`.
- [ ] LOCAL: `HEAVY_RUN_SLOT` reaches the command: `/root/crew-tmp/heavy-run sh -c 'echo $HEAVY_RUN_SLOT'` prints a slot basename.
- [ ] `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- L-0513 (gate runner): merged (PR #301).
- L-0570 (gate-runner review-r6 FIX findings, direction): touches `scripts/gate-runner.py` at other lines; no
  ordering needed, merge conflicts only.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
