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
| `podman` (in WSL2) | **4.9.3**, installed during this run — see 2b.2 |

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

## 2. Hooks

| Step | Result | Evidence |
|---|---|---|
| flavour-guard suite | **PASS** | exit 0, `159 passed, 0 failed` |
| `check-powershell.ps1` over all hooks | **PASS** | 44 files, all clean |
| python resolver parity, bash vs PowerShell | **FAIL — blocking** | see 2c |
| each hook fires exactly once | **NOT RUN** | needs a live session; see note |
| python absent from PATH → fails closed | **NOT RUN** | superseded by 2c, which fails closed with python *present* |

### 2c. The PowerShell python resolver rejects every working interpreter on this host

**This is the most serious finding in the run. On this machine crew 1.0's
`completion-audit.ps1` blocks at every Stop, and its bash twin does not.**

Measured, same host, same PATH, same moment:

| Resolver | Verdict |
|---|---|
| `_common.sh`'s `crew_py` | returns `/c/Users/…/WindowsApps/python3` — **accepts** |
| `completion-audit.ps1 -PrintPython` | returns **empty** — no python found |

And python demonstrably works here. From PowerShell, all three names launch and report
**Python 3.14.6**:

```
python   C:\Users\…\WindowsApps\python.exe   -> 3.14.6
python3  C:\Users\…\WindowsApps\python3.exe  -> 3.14.6
py       C:\Users\…\WindowsApps\py.exe       -> 3.14.6
```

**The mechanism is two deliberate fixes interacting.** In `Resolve-CrewPython`:

```powershell
$names = @('python3', 'python', 'py')
foreach ($name in $names) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
  …
  if ($cmd.Source -match 'WindowsApps') { continue }
```

1. The `WindowsApps` path match rejects a candidate **on its path alone, without ever
   executing it** — even though the file's own comments argue at length that metadata is
   untrustworthy and the candidate must be launched to be believed. That execution check
   sits *below* this line and never runs.
2. `Select-Object -First 1` takes only the first match per name, and a rejection
   `continue`s to the next **name**, never the next match of the same name. This was added
   on purpose, to mirror bash's `command -v` taking only the first hit.

Each is defensible alone. Together, on a host where all three names resolve to WindowsApps
first, every candidate is discarded untested and the function returns `''` — while a real
interpreter at `C:\Users\d3ade\AppData\Local\Python\bin\python.exe` sits further down PATH,
unreachable by construction.

**The consequence is the exact asymmetry the file's own comment claims to have fixed.**
That comment describes the old bug as "one shell flavour enforced `guards.roleWrites:
block` and the other silently allowed the write unjudged." It is still here, with the
flavours swapped. Demonstrated on a scratch repo with a `Stop` payload:

```
sh  exit=0   (silent, proceeds)
ps1 exit=2   COMPLETION AUDIT: no usable python - the tree was not audited
             against the ticket's scope.
```

Failing closed is correct behaviour for a genuinely missing python. **Here it fails closed
against three working interpreters**, so on this host the audit never actually audits — it
only blocks. The bash flavour meanwhile proceeds, so which verdict a Windows user gets
depends on which flavour the harness runs.

**Not verified:** whether the harness runs both flavours in one turn. `hooks.json` registers
every event twice with no condition — a bash `command` and a `shell: "powershell"` twin —
and no `.sh` under `hooks/scripts/` carries a reciprocal "stand down on Windows" guard
(checked across all 15). The `.ps1` guard `if ($env:OS -ne 'Windows_NT') { exit 0 }` only
stands the PowerShell twin down *off* Windows. So both proceeding on Windows is the
**necessary** condition for a double fire and it is met, but a live double fire was not
observed and is not claimed here. The flavour-guard suite does not cover this direction: all
four of its cases test the `.ps1` off Windows.

### 2a — withheld, now approved, not yet run

2a drives `/clear` by sending keystrokes to a terminal window. The operator has now approved
running it in a scratch terminal. It is NOT RUN at this commit and is next.

## 2b. Web testing

| Step | Result | Evidence |
|---|---|---|
| 2b.1 Windows `cmd /c` wrapper | **PASS (generator)** | see below |
| 2b.1 both servers connect in `/mcp` | **NOT RUN** | needs a live session |
| 2b.2 containerised visual baseline | **PASS, on Podman not Docker Desktop** | see below |
| 2b.3 `/crew:init` web phase | **NOT RUN** | |
| 2b.4 pinned versions in install script | **PASS** | `@playwright/test@1.63.0`, `@axe-core/playwright@4.13.0` |

### 2b.1 — the wrapper is right, and it is not in `.mcp.json`

There is **no `.mcp.json` at the repo root** on `84e90591`, so the step as written cannot be
read off a file. The entries are generated. `webtest_scaffold.py:161` is the whole of it:

```python
def _npx(windows, *args):
    return ({"command": "cmd", "args": ["/c", "npx"] + list(args)} if windows
            else {"command": "npx", "args": list(args)})
```

Exercised directly rather than read, `mcp_servers(windows=True)` returns:

```json
{"playwright": {"command": "cmd", "args": ["/c", "npx", "@playwright/mcp@0.0.82",
  "--isolated", "--headless", "--caps", "testing"]},
 "chrome-devtools": {"command": "cmd", "args": ["/c", "npx", "chrome-devtools-mcp@1.10.1"]}}
```

Exactly the required form, with the specified flags, and the POSIX branch correctly drops
the wrapper. **Whether both servers then connect in `/mcp` is NOT RUN** — that needs a live
session, and a correct config entry is not evidence that a server starts. `claude mcp add`
records a command without running it, a point the install script itself makes at line 938.

### 2b.2 — runs, on a different runtime than specified

Docker Desktop was **declined** by this host's operator on licensing grounds; WSL2 was
already present, so **Podman 4.9.3** was installed inside WSL2 Ubuntu-24.04 instead.

`podman pull mcr.microsoft.com/playwright:v1.63.0-noble` succeeded, and the container runs:

```
podman run --rm mcr.microsoft.com/playwright:v1.63.0-noble \
  /bin/sh -c "npx --yes playwright@1.63.0 --version"
-> Version 1.63.0
```

**This is evidence about Podman, not about Docker Desktop.** The image, its tag and the
Playwright version are the ones specified, and the container starts and reports the pinned
version. It does not demonstrate anything about Docker Desktop's WSL2 backend, its
networking, or its volume mounts, and it should not be read as a PASS of the step as
written. Visual checks run on the host rather than in this container still report
UNVERIFIED, per the requester's rule.

## 3-6 — NOT RUN

Memory and Obsidian, review and Codex, doc-builder, and the landmine checks are NOT RUN.

## Summary of FAILs

0. **BLOCKING — `completion-audit.ps1` finds no python on a host with three working
   interpreters, and blocks every Stop.** Its `WindowsApps` path match rejects each
   candidate untested, and first-match-per-name means no fallback is ever reached. The bash
   twin accepts the same interpreter and proceeds. Same host, same PATH, opposite verdicts.
   See 2c.

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
