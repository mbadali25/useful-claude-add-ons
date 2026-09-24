# crew 1.0 Windows burn-in

**Commit under test:** `84e90591` (crew 1.0.0), checked out as a detached worktree at
`C:\repos\personal\crew-1.0-win`.
**Run by:** session `win-repo [b7cfec]`, 2026-09-23.
**Status:** partial. Sections 0, 1 and the pytest root cause are complete. Sections 2-6 are
NOT RUN at the time of this commit; they are listed with that status rather than omitted.

Report-only. No crew code was changed on this branch.

## 0. Environment

| Probe | Result |
|---|---|
| PowerShell 7 | 7.6.6 |
| Windows PowerShell | 5.1.26100.9444 |
| Git | 2.55.0.windows.5 |
| Bash | GNU bash 5.3.15(2) x86_64-pc-cygwin |
| OS | Windows 11 Pro 10.0.26200 |
| `python` | `…\WindowsApps\python.exe`, `…\Local\Python\bin\python.exe`, `…\localgpu\venv\Scripts\python.exe` |
| `python3` | present |
| `py` | present |
| `node` | `C:\Program Files\nodejs\node.exe` |
| `terraform` | `C:\ProgramData\chocolatey\bin\terraform.exe` |
| `aws` | `C:\Program Files\Amazon\AWSCLIV2\aws.exe` |
| `az` | `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az` |
| `dotnet` | `C:\Program Files\dotnet\dotnet.exe` |
| **`docker`** | **NOT FOUND** — `INFO: Could not find "docker".` |

### `pwsh` IS on Git Bash's PATH on this host

The repo's `CLAUDE.md` landmine states "`pwsh` is not on Git Bash's PATH here. Name it
absolutely. A bare `pwsh` fails as 'command not found'." **Measured on this host, that is
false:** `command -v pwsh` resolves to `/c/Program Files/PowerShell/7/pwsh`.

This is recorded as an environment fact, not as a correction to the landmine. The landmine's
advice — name the interpreter absolutely — stays correct, because a suite that depends on a
bare `pwsh` passes here and fails on a host where it is genuinely absent. That is the worse
direction: the guard looks green on the machine that tests it. Every `pwsh` invocation in
this report names the absolute path.

### Docker is absent

Section 2b.2 (visual baseline through `mcr.microsoft.com/playwright:v1.63.0-noble`) cannot
run on this host. It is NOT RUN, not PASS. Section 2b.4's "with Docker absent, it only warns"
is, by the same token, testable here and is the one Docker-adjacent case this host can prove.

## 1. Suites

| Step | Command | Result | Evidence |
|---|---|---|---|
| marketplace | `python scripts\check-marketplace.py` | **PASS** | exit 0 — `marketplace: 34 skills, 5 plugins` / `all checks passed` |
| instructions | `python scripts\check_instructions.py` | **FAIL** | exit 1 — `19 problem(s)` |
| PowerShell | `pwsh -NoProfile -File scripts\check-powershell.ps1` | **PASS** | exit 0 — `44 PowerShell file(s) checked, all clean` |
| pytest | `python -m pytest plugin\crew\tests -q` | **FAIL (does not finish)** | see root cause below |
| hook parity, both shells | — | NOT RUN | |
| pylint on changed `.py` | — | NOT RUN | |

> **Exit codes here are the command's own, captured before any pipe.** A first pass of this
> table reported `check_instructions.py` as exit 0 because `echo $?` followed
> `python … | tail`, which returns `tail`'s status. That inverted a FAIL into a PASS. Any
> re-run of this table must capture the status directly or use `PIPESTATUS`.

### 1a. `check_instructions.py` — 19 problems, exit 1

Two distinct classes, both real on `84e90591`.

**Command budget overruns** — over the 120-line budget and not listed in
`.budget-allowance.json`: `change.md` (167), `gate.md` (163), `model.md` (249),
`obsidian-sync.md` (176), `onboard.md` (235), `promote.md` (335), `review.md` (551),
`upgrade.md` (375), `verify.md` (211).

**Stale pre-1.0 names inside 1.0 files** — the check's own wording is "stale name … in a
crew 1.0 file":

| Location | Stale name |
|---|---|
| `plugin\crew\README.md:1841, :2180, :2322, :2328` | `qa-reviewer` |
| `plugin\crew\README.md:2140` | `/crew:ticket` |
| `plugin\crew\README.md:2141` | `/crew:work` |
| `plugin\crew\README.md:2194` | `pm-pulse` |
| `plugin\crew\commands\ticket.md:7` | `/crew:ticket` |
| `plugin\crew\commands\work.md:7` | `/crew:work` |
| `plugin\crew\evals\qa-reviewer-stays-read-only\prompt.md:10` | `qa-reviewer` |

This one is worth more than its line count. 1.0 removes the PM, the pulse and the
`qa-reviewer` role, and `commands\ticket.md` and `commands\work.md` still exist and still
name themselves. Either those commands survive 1.0 and the checker's stale-name list is
wrong, or they do not and the files should be gone. The checker cannot tell which, and
neither can this report — **it is a question for the 1.0 author, not a defect with an
obvious fix.**

### 1b. pytest root cause — process spawn cost, not a hang

**It never hangs. It is doing 3524 tests' worth of Windows process creation.**

Collection is fast: `--collect-only` returns **3524 tests in 3.67s**. So nothing is stuck in
import or collection; the cost is entirely in execution.

Per-file sweep with a 90s cap (partial — the sweep itself was cut off at 10 minutes, having
reached `test_crew_metrics.py` alphabetically):

| File | Result |
|---|---|
| `test_auto_cycle.py`, `test_cloud_guard.py`, `test_completion_audit.py`, `test_context_watch.py` | TIMEOUT at 90s |
| `test_auto_clear.py` | 62s |
| `test_approval_hook.py` | 32s |
| `test_crew_context_fixes.py` | 23s |
| `test_crew_metrics.py` | 19s |
| `test_context_watch_python_resolver.py` | 18s |
| `test_crew_context.py` | 17s |
| `test_crew_context_wrappers.py` | 16s |
| `test_anchor_trigger_fixpoint.py` | 12s |

**The flavour split is the finding.** `test_cloud_guard.py` names its cases
`test_must_block_python` / `_bash` / `_pwsh` — the same assertions re-run through three
interpreters. Timed separately, 84 tests each:

| Flavour | 84 tests | Per test |
|---|---|---|
| python | 13.1s | ~156ms |
| bash | 70.8s | ~843ms |
| **pwsh** | **timed out at 120s, never completed** | **>1429ms** |

Raw interpreter startup, one invocation: `bash` 33ms, `python` 164ms, `pwsh` 318ms,
Windows PowerShell 5.1 299ms.

Ten real guard invocations end to end: `python` 291ms each, `bash`→python 294ms each,
`pwsh`→python **651ms** each.

**So the pwsh path costs ~2.2x the python path per invocation, and bash's cheap startup
(33ms) does not save it — the dominant cost is Windows process creation plus a Python
interpreter start inside each spawned shell, not the shell binary itself.** On a host with
real-time AV scanning each spawned image, this is the expected shape.

At an observed 0.3-1.4s per test across 3524 tests, a full run is tens of minutes. The
10-minute budget is not close, and no single test is at fault.

**This is a throughput problem with ordinary fixes, none of which this report applies:**
run the three flavours as parametrised cases sharing one fixture rather than three
independent spawns; use `pytest-xdist` (`-n auto`) so spawns overlap; mark the pwsh
flavour `slow` and exclude it from the default run while keeping it in CI. Which of those
is right is the 1.0 author's call.

## 2. Hooks, live — NOT RUN

Sections 2, 2a, 2b, 3, 4, 5 and 6 are NOT RUN at the time of this commit.

**2a is deliberately excluded.** It drives `/clear` by sending keystrokes to a terminal
window, and the requester flagged it as needing operator confirmation. This session's
operator approved the burn-in explicitly *minus* 2a. It is not deferred for convenience —
it is withheld pending its own yes.

## 3-6 — NOT RUN

Memory and Obsidian, review and Codex, doc-builder, and the landmine checks are NOT RUN.

Of these, **2b.2 cannot pass on this host at all**: Docker is absent, so the containerised
visual baseline has no runtime. Per the requester's own rule, visual checks on the host
report UNVERIFIED rather than PASS.

## Summary of FAILs

1. **`check_instructions.py` exits 1 with 19 problems** — nine command files over the
   120-line budget and unlisted in `.budget-allowance.json`, plus ten stale pre-1.0 names
   (`qa-reviewer`, `/crew:ticket`, `/crew:work`, `pm-pulse`) inside files 1.0 should have
   purged. `commands\ticket.md` and `commands\work.md` still exist and still name
   themselves; whether that is the checker or the files being wrong is an open question.
2. **pytest does not finish** — 3524 tests at 0.3-1.4s each, dominated by Windows process
   creation with a Python start inside each spawned shell. The pwsh flavour is ~2.2x the
   python flavour per invocation. Not a hang, not one bad test.

## Not verified

- Everything in sections 2-6.
- The full pytest sweep was cut off at 10 minutes partway through the alphabet, so the
  per-file table above is a floor on how many files are slow, not a complete list.
- `docker` is absent, so no containerised step on this host can return anything but NOT RUN.
