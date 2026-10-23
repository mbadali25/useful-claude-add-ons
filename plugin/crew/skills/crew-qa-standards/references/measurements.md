# Checks and measurements that can fail

Two rules for any check or number a session reports: the check must be able to fail, and a
performance number must survive seven questions. The seven are adapted from pstack's
benchmark checklist, and the first rule from its verification skill (see `NOTICE.md`).

## A1 - Able to fail

A check that cannot fail proves nothing. A gate rule, a test, a smoke command, an audit item, a
benchmark and a verification script each state, in one line, how it would fail, and show that it
failed once.

- **Check.** For each new check, find the line that says what breaks it, and the evidence of the
  red run: a removed guard, a reordered step, a wrong input, a deleted line, with the failing
  output quoted. A check never seen red is reported as "not shown to fail", not as passing.
- **Apply.** Break the code the check guards, run the check, see it go red, restore, see it go
  green. Keep the broken variant (a sabotage case) when the check blocks work. For a report,
  say which variant you broke.
- Do not weaken the check or its model until it passes. A finding stays a finding.

## M1 - A performance number

Applies when a report gives a speedup, a regression, a limit or a choice between options.
For a ballpark the owner asked for, one run is enough: say it is one run and still answer 4 and 7.
A choice between options is never a ballpark.

Before running: write the claim you expect to make, in the words you would ship; read the script and
note what it times, counts and ignores; check the load (`uptime`, `nproc`) and, if the machine is
busy, interleave the sides and say so.

1. **Limiter.** Name what bounds the number (CPU, I/O, a lock, the load generator) from a profile
   taken in a run you do not report. If a change did not move the number, the limiter says why.
2. **Tuned.** Every side runs as production runs it: release build, production flags, warm or cold
   caches as production sees them, same versions and data. An untuned side means you compared
   settings, not implementations.
3. **Limits.** Do the arithmetic. A result past disk or network bandwidth, or past what the changed
   piece could save (removing 10% of the run saves at most about 11%), measured something else.
4. **Errors.** Count failures and non-success responses and check the outputs are correct. Fast
   rejections and slow timeouts both distort a timing.
5. **Repeats.** At least 5 runs per side, alternating A, B, A, B. Report median and range. A gap
   smaller than the run-to-run spread is no measurable difference.
6. **Matters.** Put the micro result next to the end-to-end path a user waits on, as a share of it.
7. **Happened.** Confirm the work ran inside the timed region: the request arrived, the rows were
   written, the result was used. Lazy code and timeouts produce numbers for work that never ran.

**Report.** Lead with the verdict: faster, slower, no measurable difference, or inconclusive. Give the
number with its unit, the run count, the range and the limiter. Call it inconclusive if you claim a
difference but cannot name the limiter, a side ran untuned, or you could not check 4 and 7, and name
the gap. Apply A1 to the harness itself: show the benchmark go red on a deliberately slowed or
broken variant before you trust its green.
