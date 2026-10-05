# L-0517 direction - heavy-run logs each lane's slot wait (lane, slot, waited seconds, start/end) so contention is measurable

Status: approved 2026-10-05 for cloud hand-off (orchestrator, owner standing self-approve authority).

Small. /root/crew-tmp/heavy-run is machine-local (not tracked); if the fix belongs in-repo (L-0513's runner) say so. Output one line per acquisition to a log the review can aggregate.

Source: owner decisions 2026-09-30 ("All recommended", relayed by crew-chat) on a measured CI/review/QA review of 2026-09-28..30; raw data at /tmp/claude-0/.../ci-review/, copied to .work/ci-review-2026-09-30/ (every number there carries its source; copy what you cite into this folder, the scratchpad is not durable).

## Ask
Make heavy-run slot contention measurable: for every heavy-run acquisition, one line saying which lane
waited, for which slot, how long, and when it started and ended, in a log a later CI/review/QA review can
aggregate. The seed asks whether the fix belongs in the machine-local wrapper or in-repo in L-0513's
`scripts/gate-runner.py`.

Found at origin/main `a555ff37`: the wrapper `/root/crew-tmp/heavy-run` (89 lines, untracked, sha256
`171b95c2...`) is the only code that knows which slot it took and the only one every heavy caller goes
through (`pytest_rule.py` runs, review runs, the gate runner). It logs nothing. `scripts/gate-runner.py`
already measures its own wait (`hr["waited_seconds"] = inner_started - launched`, `:1052`) into the run's
`status.json`, but not the slot, and only for gate-runner runs, in a per-run file under `$TMPDIR`.

## Options
1. **Wrapper logs every acquisition; gate runner records the slot it was given (recommended).** heavy-run
   appends one JSON line per acquisition to `/root/crew-tmp/heavy-run-waits.jsonl` (lane, slot, pid,
   requested/acquired/released UTC, waited and held seconds, rc, priority tag) and exports
   `HEAVY_RUN_SLOT` to the command it runs. `gate-runner.py --inner` records that slot in
   `heavy-part.json`; the outer runner copies it to `status.json`'s `heavy_run.slot`, `null` when not
   exported. Covers every caller, and the gate runner's own record names its slot. Cost: the wrapper is
   machine-local, so its edit ships as a reviewed patch in this ticket folder that the owner's local
   session applies; a cloud session cannot reach `/root/crew-tmp`.
2. **In-repo only: gate runner appends the line.** gate-runner writes the line itself after the heavy-run
   call. Fully tracked and testable, but misses every non-gate-runner caller (most heavy runs: lane
   pytest and review runs) and cannot name the slot without a wrapper edit anyway. Measures the wrong
   population.
3. **Move heavy-run into the repo** (`scripts/heavy-run` plus an install step). Tracked and tested, but
   it hard-codes this host's `/root/crew-tmp` paths, priority list and 6G cap, adds an install-script pair
   change (both scripts, matched), and is far beyond "Small".

## Recommendation
Option 1. The wrapper is where the evidence is (CLAUDE.md lesson: put the check where the evidence is
dropped); the in-repo part is the few lines that let the gate runner's own record name its slot.

## Open questions (default taken)
- Log location and format: `/root/crew-tmp/heavy-run-waits.jsonl`, one JSON object per line, appended with
  a single `printf >>` (under `PIPE_BUF`, so lines do not interleave). Default taken.
- Lane identity: priority tag when matched, else `TMPDIR` basename when it is under `/root/crew-tmp/`,
  else the basename of `git rev-parse --show-toplevel` from `$PWD`, else `"unknown"` (never guessed).
  Default taken.
- When the line is written: once per heavy-run invocation, from the existing EXIT trap, so a SIGTERM/SIGINT
  still logs; a call that gave up while waiting logs `acquired: null` and its wait so far (that is contention
  too). SIGKILL or an OOM kill of the wrapper itself writes nothing; a separate line at acquisition was
  rejected as doubling the log for that rare case. Default taken.
- Rotation: none; the file grows about 300 bytes per run. Default taken.
- No aggregator script; `jq` over the JSONL is enough for the review. Default taken.

Approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority.
