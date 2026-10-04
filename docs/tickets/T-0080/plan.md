# T-0080 plan - sabotage harness bounds each entry          status: plan
Bundled with T-0082 in harness PR H2a (#399). Spec decisions taken as written (owner questions 1-3:
recommended defaults; question 5: no single test exempted).

## Measured first (spec Unknown 1), 2026-10-04, this container, before any change
Each entry alone, under a 6 GiB RLIMIT_AS safety wrapper (no cgroup wrapper here), peak RSS of reaped
descendants:
- `:544` "a FIFO or device is opened as a plan": RED (good), peak 59 MiB, 34 s. Constant memory, as
  the code reads (1 MiB blocks). The plan-dev-zero test does not need tightening.
- `:565` "azureProfile.json opened whatever it is": RED (good) only because of the 6 GiB wrapper cap,
  peak 5908 MiB, 61 s. This is the unbounded reader.

## Steps (test-first)
1. `plugin/crew/tests/test_sabotage_bound.py` (new): the seven named tests of the spec.
2. `plugin/crew/tests/sabotage_bound.py` (new): `limits`, `describe`, `run`, `TIMED_OUT = 124`,
   group stop on timeout and on harness exit.
3. `test_sabotage_harness.py`: the three named tests (timed-out entry unproven; unreadable limit
   refused before any mutation; run_test hands pytest to the bounded runner).
4. `sabotage.py`: `run_test` calls `sabotage_bound.run` (signature kept); `main` reads `limits` once,
   returns 2 on ValueError, prints `describe`, reports 124 as `RED BUT UNPROVEN -- timed out after
   <n>s`. Lines freed so the file stays at or under 3400 (net zero or fewer).
5. `sabotage_tooling.py`: three mutations of the bound (cap not applied; timeout stops only the
   leader; unreadable limit read as the default).
6. `sabotage_cloud.py`: comments on the two entries only. verify.json sabotage rule gets the two new
   files; README sabotage paragraph; CHANGELOG; codemap/rules refresh.

## Acceptance runs planned here
The two entries alone with the bound and no wrapper (peak under 4.5 GiB); the crew suite with and
without `ulimit -v 4194304` (same counts, `-n 4`); the bound's own mutations. The full uninterrupted
sabotage run (~hours, 600+ entries) is not planned in this shared container; reported as not verified.
