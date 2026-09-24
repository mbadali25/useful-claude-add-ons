# crew 1.0 Windows burn-in — re-run at `1da86f78`

**Commit under test:** `1da86f78` (crew 1.0.3, obsidian-vault 0.4.7), detached worktree at
`C:\repos\personal\crew-1.0-win`. Versions confirmed from each `plugin.json`.
**Run by:** session `win-repo [b7cfec]`, 2026-09-24. Report only; no crew code changed.
**Status:** partial. Everything below is labelled `1da86f78`.

## Previously-reported FAILs, retested

| FAIL | Status at `1da86f78` | Evidence |
|---|---|---|
| 0 — PowerShell python resolver | **FIXED** | `completion-audit.ps1 -PrintPython` → `C:\Users\…\Local\Python\pythoncore-3.14-64\python.exe`, a real interpreter, not the WindowsApps alias |
| 2 — `check_instructions.py` | **STILL FAILING, unchanged** | exit 1, still **19 problems**, byte-identical list |
| pytest throughput | improved but see below | 9m30s for 2890 tests with `-n auto` |

### FAIL 2 is not fixed, and the diagnosis sent to this session was right

The Linux side's theory — "backslash paths missing POSIX allowance keys" — is **correct**,
and the fix is not in `1da86f78`. Proven rather than inferred:

```
rel() ->               'plugin\\crew\\commands\\change.md'
allowance has ->       'plugin/crew/commands/change.md'
match?                 False
posix form matches?    True
```

`scripts/check_instructions.py:195` is:

```python
def rel(path: str) -> str:
    return os.path.relpath(path, ROOT)
```

`os.path.relpath` returns `os.sep`-joined output, so on Windows every lookup into
`plugin/crew/.budget-allowance.json` — whose nine keys are all POSIX — misses. **All nine
budget failures are this one line.** The fix is `.replace(os.sep, "/")` on the return.

The remaining **ten** problems are a different, real matter and are not path-related: stale
pre-1.0 names inside 1.0 files — `qa-reviewer` at `README.md:1841,:2180,:2322,:2328` and
`evals/qa-reviewer-stays-read-only/prompt.md:10`; `/crew:ticket` at `README.md:2140` and
`commands/ticket.md:7`; `/crew:work` at `README.md:2141` and `commands/work.md:7`;
`pm-pulse` at `README.md:2194`. `commands/ticket.md` and `commands/work.md` still exist and
still name themselves.

## Suite: `-n auto --timeout=120 --durations=20`

```
124 failed, 2766 passed, 22 skipped in 570.59s (0:09:30)
```

Zero per-test timeouts fired at 120s. 70 distinct failing test functions across 124 node
ids. Grouped by cause, largest first:

| n | Test function | Cause |
|---|---|---|
| 26 | `test_the_machine_can_narrow_auto_clear_to_listed_repos_and_sessions` | the new `onlyRepos`/`onlySessions` feature — environment, see below |
| 11 | `test_every_new_file_is_lf_only`, `test_wrappers_and_modules_are_lf_only` | **committed CRLF — real** |
| 8 | `test_a_crashed_python_fails_closed_unless_scope_is_provably_off`, `test_no_python_fails_closed_…` | |
| 6 | `test_handoff_read_sh_stands_down_…`, `test_bash_flavour_emits_…` | |
| 2 | `test_resolver_accepts_a_proven_python_38` | |

Most frequent error lines:

```
 26  assert ('', "2026-09...'^[^ -~] '\n") == ('', '')
 18  AssertionError: autoclear: refusing - the terminal that owns this session (pid 74368)
       has no window whose ...
 15  FileNotFoundError: [WinError 2] The system cannot find the file specified
 11  AssertionError: autoclear: refusing - method tmux but tmux is not on PATH
  3  OSError: [WinError 1920] The file cannot be accessed by the system
```

### The CRLF failures are real, but they are a WINDOWS-CHECKOUT defect, not a shipped one

**Corrected. An earlier revision of this file claimed the committed blobs carry CR and
called it a shipping defect. That was wrong, and the measurement behind it was broken.**

Re-measured by writing each blob to a file and counting bytes equal to 13:

| File | blob bytes | CR in committed blob | CR in worktree |
|---|---|---|---|
| `approval-hook.ps1` | 9647 | **0** | 204 |
| `approval_hook.py` | 5999 | **0** | 141 |
| `completion-audit.ps1` | 14036 | **0** | 293 |

The committed objects are LF. What an installer receives is LF.

**The broken measurement, recorded because the failure mode is reusable.** The original
count came from:

```sh
git cat-file blob HEAD:$f | head -c 2000 | od -c | grep -c '\\r'
```

In single quotes the shell passes `\\r` to grep, and this grep collapsed it to match a
plain `r`. `grep -o '\\r'` on that same stream returns **98 matches, every one the letter
"r"** — so the "CR count" was really a count of `od` lines containing the letter r, which
in English source text is most of them. The control settles it: a genuinely CRLF stream,
`printf 'a\r\nb\r\n' | od -c | grep -c '\\r'`, returns **1**. The pattern was wrong in both
directions, reporting large numbers for LF files and small ones for CRLF files. Count bytes
(`tr -cd '\r' | wc -c`), never `od` text through a regex.

**What survives is still a real defect, with a different owner.** The eleven
`test_every_new_file_is_lf_only` / `test_wrappers_and_modules_are_lf_only` failures stand,
because the tests read **working-tree** bytes. `.gitattributes` pins `*.sh text eol=lf` and
nothing else, so under `core.autocrlf=true` a Windows checkout of the `.py` and `.ps1` files
gets CRLF — 204, 141 and 293 CR respectively above — and the assertion `b"\r" not in
read_bytes()` fails correctly. The fix is to extend `eol=lf` to those types, which changes
what a checkout produces rather than what is stored.

### The 26 auto-clear narrowing failures are environment, not the feature

`onlyRepos`/`onlySessions` is the new narrowing added for burn-in FAIL 5-7. Its failures
here read `method tmux but tmux is not on PATH` (11) and `the terminal that owns this
session (pid …) has no window whose …` (18). Both are this host lacking the thing the
fixture assumes — tmux is not a Windows tool, and the owner-process walk finds no matching
window from a non-interactive runner. **The narrowing logic itself is not shown wrong by
these**, and is not shown right either: these tests could not exercise it here.

## 2a — RUN. The Windows sender does nothing at all, silently.

Operator approved a live run. **Scope was narrowed first, and 1.0.3's own narrowing made
that possible** — `onlyRepos` was set to this worktree and proven to exclude the other repos
on this host before anything was armed:

```
C:/repos/personal/crew-1.0-win          -> True
C:/repos/personal/useful-claude-add-ons -> False
C:/repos/anew/SRL                       -> False
```

Recorded separately because it surprised me: **`autoClear.enabled` was already `true` on
this machine with no narrowing**, so it had been armed for every session all along. The
machine config was backed up and restored afterwards; it is unchanged.

### PASS — the handoff gate chain

Driving `crew_autocycle.py plan` refused at each condition in turn and named it: a marker
recording a different session, then no request time, then the handoff file, then its age
against the request. Each refusal distinct and accurate. The gates fail closed and say why.

### FAIL — the Windows sender

`auto-clear.sh` / `crew_autocycle.py` correctly decline Windows: `resolve_method` returns
`none` with *"Inside tmux this works with no configuration; on X11 install xdotool"*, and
the `.ps1` twin states the division explicitly — *"method tmux is auto-clear.sh's job; this
is the native-Windows flavour."* So on Windows the sender is `auto-clear.ps1`, using
`System.Windows.Forms.SendKeys`.

Invoked exactly as `hooks.json` invokes it, it produces **nothing**:

```
pwsh -NoProfile -File ...uto-clear.ps1 -DryRun -Root ...
exit=0   stdout bytes: 0   stderr bytes: 0   .crew/.autoclear.log: does not exist
```

Same with `-Session burnin-2a`, with `-Force` (which skips every handoff gate), and with
**no `-Session` at all** — that last case must reach line 313,
`Stop-CrewAutoClear "no session id, so no way to tell whose handoff this is"`, which calls
`Write-CrewAutoClearNote` and writes both a log line and a stderr line. Neither appeared.

**This contradicts the file's own header contract:** *"Every refusal is written to
`.crew/.autoclear.log`, because a Stop hook's stderr is invisible on exit 0."* On this host
nothing is written anywhere, so a Stop hook using it stands down with no trace — the silent
stand-down shape, in the component whose whole job is to act.

**The flavour guard is not the cause, checked directly.** Line 51 is
`if ($env:OS -ne 'Windows_NT') { exit 0 }`, and under the `-File` invocation hooks.json
uses, from this shell, `$env:OS` is `Windows_NT`, `$IsWindows` is `True`, and the working
directory is correctly the repo. The guard passes; something after it exits first.

**Cause not established.** The behaviour is certain and reproducible; the line it exits at
is not, and I am not guessing it. Steps 3, 5 and 6 — where `/clear` lands, which tab
receives it with two tabs, whether alt-tab suppresses the send — remain **NOT RUN**, because
nothing was ever sent to observe.

## 5.1 vs 7 - the obsidian-vault probes. The `%d` concern is unfounded.

Linux review flagged `%d` tokens that `cmd.exe` might rewrite. **It does not, and both
PowerShell editions agree.** The tokens are real - one per file, all the same shape:

```
plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:109
  $probeArgs = '-c "import sys; v = sys.version_info; sys.stdout.write(''vault-guard-python:''
               + ''%d:%d:%s:'' % (v[0], v[1], sys.implementation.name) + sys.executable)"'
```

Run under both editions, from the same host:

| Probe | pwsh 7.6.6 | Windows PowerShell 5.1 |
|---|---|---|
| `bridge-status.ps1` | correct JSON, bridge UP, Local REST API 5.2.0 | **byte-identical** |
| `vault-guard.ps1 -PrintPython` | `C:\Users\...\pythoncore-3.14-64\python.exe` | **identical** |
| `vault-capture.ps1` | see note | see note |

`vault-guard` resolving a real interpreter under both editions is the proof the review
wanted: if `%d` were being rewritten, the probe string would not round-trip and the resolver
would reject the candidate. It does not - it returns the same genuine interpreter either
way, and it is the non-alias one.

`bridge-status` returning byte-identical JSON under both is a second, independent
confirmation on a different file carrying the same token.

**`vault-capture` returned empty under both, and that was my error, not a defect.** It has
no `-PrintPython` parameter - its param block is `param([string]$Trigger = 'unknown')`, so
an unrecognised flag was ignored. Not a finding; recorded so the blank row above is not read
as one.

**Verdict: PASS on the specific question asked.** No `%d` rewriting under either edition.
Worth stating what this does *not* cover: both probes were invoked directly from Git Bash
via `pwsh -File` / `powershell -File`. It does not test invocation through a `cmd.exe`
wrapper, which is the layer the original concern named. If that layer is the worry, it needs
its own test.

## Sections not yet run

3 (memory/Obsidian), 4 (review/Codex), 5 (Word COM render), 6 (landmines), `/crew:verify
--all`, the 5.1-vs-7 obsidian-vault probes, and 2a steps 3/5/6 are **NOT RUN** at this
commit. 2a's live cycle needs its own operator confirmation each time it is attempted,
because `autoClear` is still read from the machine file — the narrowing changes which
repos/sessions act on it, not where the switch lives.
