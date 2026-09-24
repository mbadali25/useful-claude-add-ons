# crew 1.0 Windows burn-in - re-run at `485a1b08` (crew 1.0.5, obsidian-vault 0.4.10)

Previous report: `1823925c`, against `1da86f78`. Everything below is measured on this sha.

**Both claims about the sha were verified before anything was run.**
`git merge-base --is-ancestor b6ab350e 485a1b08` returns 0, so `main` up to #221/#222/#223 is
genuinely in. `e61bb354 auto-clear: gate on .crew/ existing, not .crew/config.json` is present.

## The three previously-failed steps

| Step | At `1da86f78` | At `485a1b08` |
|---|---|---|
| `scripts/check_instructions.py` | exit 1, 19 problems | **exit 0**, `instruction budgets: all checks passed` |
| `lf_only` tests | 11 failed | **15 passed, 0 failed** |
| full crew suite | 124 failed | 97 under `-n auto`, **87 confirmed serially** |

`check_instructions.py`'s exit code was captured directly rather than after a pipe. That inversion
turned a FAIL into a PASS earlier in this burn-in and is the reason the method is stated here.

The `lf_only` result is corroborated independently of the tests: **0 of 41 `.sh` files** under
`plugin/` contain a CR byte in this worktree, counted by reading bytes rather than grepping `od`
output - the method that produced the CRLF claim this burn-in had to withdraw.

## The auto-clear gate fix works - and it overshot. This is the finding.

### It works

The exact case that produced nothing at `1da86f78` - `.crew/` present, `config.json` absent - now
reaches its logger:

    exit=0   stdout: 0 bytes   stderr: 78 bytes
    stderr:  autoclear: refusing - no session id, so no way to tell whose handoff this is
    .crew/.autoclear.log:  2026-09-24T14:35:54Z  refusing - no session id, ...

That is the refusal path the original §2a report predicted and could never reach. The header's
contract - "every refusal is written to `.crew/.autoclear.log`" - now actually holds. No keystrokes
were sent to establish this.

### It also writes a log where the suite explicitly forbids one

`auto-clear.sh` at this sha:

    81: [ -d .crew ] || exit 0
    82: LOG=".crew/.autoclear.log"
    84: note() {  # one line to the log and to stderr

The logger is now armed **whenever `.crew/` exists**, independent of opt-in - and something reaches
`note()` before the enabled check. The suite says that is wrong, by name:

    def test_absent_block_does_nothing_and_writes_no_log(flavor, tmp_path):
        # The default. A repo that never asked for this must not even discover the
        # feature exists by finding a log file in .crew/.

    def test_enabled_false_does_nothing(flavor, tmp_path):
        ...
        assert not (root / ".crew" / ".autoclear.log").exists()

Both now fail with `AssertionError: assert not True ... '.crew' / '.autoclear.log').exists`.

**I own a share of this.** I recommended moving the gate below the logger and did not say that the
**enabled check must still precede any write**. 0.20.17 had that right and said so at its own gate:
*"Enabled is checked FIRST and silently: a repo that has not opted in must not even get a log file
out of this."* The fix restored diagnosability for opted-in repos and lost the silence for everyone
else. Both properties are wanted; they are not in tension, they just need the order
`.crew/` exists -> **enabled?** -> arm the logger.

This is also why the two behaviours must be tested separately, which the suite already does.

## The 87 serial failures

`-n auto`: **97 failed, 2831 passed, 32 skipped in 23m28s**. Re-running the 21 affected files
serially: **87 failed, 691 passed, 24 skipped, 435 deselected in 27m02s**. So **87 of 97 are real**
and 10 were xdist artifacts - a far smaller artifact fraction than the 17-of-43 measured on
`main`, and worth noting because it means the parallel count was closer to the truth here than the
earlier lesson would predict.

Crew's Linux gates at this sha are clean (`2745 passed, 202 skipped, 827 deselected`), so this set
is Windows-specific.

| Count | File |
|---|---|
| 33 | `test_auto_cycle.py` |
| 10 | `test_auto_clear.py` |
| 10 | `test_context_watch_python_resolver.py` |
| 6 | `test_ps1_python_probe.py` |
| 5 | `test_rules_generation_path.py` |
| 4 | `test_lifecycle_commands.py` |
| 2 each | `test_review_ledger.py`, `test_approval_hook.py`, `test_event_claim_crash_safety.py`, `test_gate_command.py`, `test_webtest_scaffold.py` |
| 1 each | `test_verify_gate_stop_gate_record.py`, `test_crew_instructions.py`, `test_review_prompt.py`, `test_role_write_guard.py`, `test_completion_audit.py`, `test_scope_guard.py`, `test_stack_skills.py`, `test_verify_gate_lock_window.py`, `test_verify_gate_python3_shim.py` |

They fall into four mechanisms, not 87 problems:

**A. The log-written-when-it-should-not-be regression above.** The `assert not ...exists()` family.

**B. Method resolution picks a Unix sender on Windows** - roughly 25 failures carrying
`refusing - method tmux but tmux is not on PATH` or `method xdotool but xdotool is not on PATH`,
where the test expected the Windows path. The bash flavour is being exercised through Git Bash and
resolves as if it were on Linux.

**C. No matching terminal window** - about 20 carrying
`refusing - the terminal that owns this session (pid N) has no window whose title contains`.
Under pytest there is no such window, so this is the harness, not the product.

**D. `FileNotFoundError: [WinError 2]`** - 7 failures where a binary the test assumes is absent.

**E. A path-shape contract disagreement**, 4 failures, worth deciding rather than patching:

    must return the interpreter path with the CR stripped.
    got      ['/c/Users/.../WindowsApps/python3.EXE']
    expected ['C:\\Users\\...\\WindowsApps\\python3.EXE']

The resolver returns the POSIX form; the test wants the native form. Both are defensible. The
recommendation sent to the crew is that bash resolvers return the POSIX form bash actually execs
and callers convert with `cygpath -w` at the boundary into Python or PowerShell, with the test
asserting that. Note the path is a **WindowsApps alias**, which this burn-in already proved
*forwards* to a real interpreter - so accepting it is correct, and only the shape is in dispute.

## 2a steps 3/5/6 - NOT RUN, deliberately

They send keystrokes into a live terminal window. Skipped at this sha on the crew's own advice,
because the SendKeys sender is about to become opt-in only behind a foreground and active-tab
check; running them once against that path on the r1 sha is worth more than running them twice.
The gate fix needed no keystrokes to prove.

## The `notify` default - NOT PRESENT at this sha

Lanes r1/r2 are still in progress, so nothing here exercises it. When it lands the four checks are:
no keystroke is sent (measured with a foreground-window sentinel and an input probe, not by exit
code); the message is visible, reporting **where** it surfaced; the handoff text is in the new
context after a manual `/clear`; and the same after a real auto-compact. The last one cannot be
forced - auto-compact fires on Claude Code's own schedule and crew neither causes nor tunes it - so
it runs opportunistically and is reported NOT RUN with the reason if the session does not compact.
It will not be simulated and called measured.
