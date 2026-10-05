# L-0517 plan            spec: docs/tickets/L-0517/spec.md

Repository tooling: no plugin version, no `plugin/crew/` change, no harness path.

### Step 1: the gate runner records its slot (test-first)
Files: scripts/gate-runner.py, scripts/_test/gate-runner.py
Where: `run_inner` (part file `started`), `_part` (reads `started`), the outer's `waited_seconds` line, `hr` in `main`
Test: flock $S/heavy.lock python3 scripts/_test/gate-runner.py; python3 scripts/gate-runner.py --check-ci
Risk: low - recorded, never trusted: no step state reads it
- [ ] `run_inner` writes `"slot": os.environ.get("HEAVY_RUN_SLOT") or None` into heavy-part.json
- [ ] `_part` returns `(steps, started, slot)`; `slot` is a non-empty `str` of at most 64 chars with no `/`, else `None`
- [ ] outer copies it to `status["heavy_run"]["slot"]`; `hr` starts with `"slot": None`
- [ ] the suite's `run_gate` strips an inherited `HEAVY_RUN_SLOT` (a suite run under heavy-run must not leak its own slot into a fixture)
- [ ] cases: `case_heavy_run_slot_recorded`, `case_heavy_run_slot_absent_is_null`, `case_heavy_part_bad_slot_is_null`; the `heavy_run` keys assertion gains `slot`

### Step 2: the machine-local wrapper patch
Files: docs/tickets/L-0517/heavy-run.patch
Test: cp heavy-run.snapshot $T/hr && patch $T/hr heavy-run.patch && bash -n $T/hr; a run against a temp lock dir (paths rewritten by sed) for a parseable line, a held-slot wait, and a TERM while waiting
Risk: low - the LOCAL checks in the spec run on the owner's host
- [ ] EXIT trap writes one JSONL line (lane, slot, prio, pid, requested, acquired, released, waited_s, held_s, rc, cmd) to `${HEAVY_RUN_WAITS_LOG:-/root/crew-tmp/heavy-run-waits.jsonl}`
- [ ] `export HEAVY_RUN_SLOT=<basename>` while a slot is held; `slot`/`acquired`/`held_s` null without one; `lane` per the spec's order, else `"unknown"`
- [ ] `\` and `"` escaped, control characters dropped, `cmd` cut to 120 characters

### Step 3: records
Files: .crew/verify.json, .crew/codemap/verification-harness.md, CHANGELOG.md
- [ ] verify rule `why` names the slot; `seconds` re-measured
- [ ] codemap gate-runner paragraph names `heavy_run.slot`; CHANGELOG repository-tooling entry
