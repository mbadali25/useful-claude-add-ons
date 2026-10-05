# 5. A pre-review linter's leftover processes are ended before the linter is reaped

**Status:** accepted, 2026-10-03
**Decided by:** the owner (crew-chat AskUserQuestion, 2026-10-03), on the L-0605 lane's recommendation

## Context

`review_checks.py` runs each pre-review linter (ruff, ShellCheck, PSScriptAnalyzer, actionlint) in
a process group of its own. L-0574 review round 9 (FIX `review_checks.py:727`) stopped signalling
that group after a clean exit: `communicate()` had already reaped the linter, so its pid, and the
group id equal to it, were free for the OS to hand to an unrelated process. The cost was that a
background process a linter leaves behind after a CLEAN exit survived on POSIX, while on Windows
the job object still ended it. L-0605 had to decide whether to keep that.

## Decision

1. **End the leftovers, while it is safe.** On Linux the checks read both pipes to EOF themselves
   (a `selectors` loop, no threads), then wait for the linter with
   `os.waitid(P_PID, pid, WEXITED | WNOWAIT | WNOHANG)`, which sees the exit without reaping. The
   linter is then a zombie: its pid cannot be reused, and neither can its group id. Only then is
   the group sent `SIGKILL`, and only then is the linter reaped.
2. **An unknown is not clean.** `ProcessLookupError` from that signal means nothing was left. Any
   other refusal (`PermissionError`) is "could not check". So is a failed read, a selector or
   `waitid` error, and a pipe still open at the deadline.
3. **Bounded.** One `timeout` deadline covers the read and the wait. Past it, or on an error, the
   group is killed (the linter is still unreaped), and one `_REAP_SECONDS` post-kill deadline
   covers the last drain and the reap. The selector and both pipes are always closed.
4. **Where it does not apply.** macOS: CPython has no `os.waitid`, so behaviour stays as round 9
   left it (no signal after the reap; leftovers survive). Windows: unchanged, the job object ends
   them. The review runner's provider (`review_run.py`) is unchanged: its leftovers after a clean
   exit are not the runner's to end (`kill_on_close=False`).

## Rejected option

Keep round 9's behaviour on POSIX, as `review_run.py` does for the reviewer. It is simpler, but it
leaves the same linter behaving differently on POSIX and Windows, and once the signal is sent
before the reap it buys no safety.

## Consequences

- A process that left the linter's group (`setsid`, a new process group) before the linter exited
  is out of reach. If it holds a pipe open the run times out, at most `timeout + _REAP_SECONDS`,
  and the detail says such a process may still be running.
- The POSIX path no longer uses `communicate()` where `os.waitid` exists, and decodes the output
  itself (`utf-8`, `surrogateescape`, universal newlines, as `text=True` did).
- Tests: `test_a_clean_linter_s_detached_leftover_is_ended`,
  `test_a_reaped_linter_s_group_is_never_signalled` (every signal is sent to a zombie leader's
  group), `test_a_leftover_that_left_the_group_cannot_hang_the_check`,
  `test_the_post_kill_drain_and_reap_share_one_deadline`,
  `test_a_leftover_that_cannot_be_signalled_is_could_not_check`, with sabotage entries S5a-S5g in
  `plugin/crew/tests/sabotage_prereview.py`.
