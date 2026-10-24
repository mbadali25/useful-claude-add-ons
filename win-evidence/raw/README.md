# Windows RAW evidence for crew's Linux lane

Every `.log`, `.txt` and `.json` in this directory is **raw bytes**, copied out of a file or
captured straight from a process. Nothing was retyped, reformatted or summarised. This README is
the only prose here; where it states a number, the number is in one of the files beside it.

## Environment

| | |
|---|---|
| Host | `dadeush-desktop`, Windows 11 Pro 10.0.26200, 20 logical processors |
| Shell | Git Bash `MINGW64_NT-10.0-26200 3.6.10-710e5275.x86_64`, bash `5.3.15(2)-release` |
| Python | `C:\Users\d3ade\AppData\Local\Python\pythoncore-3.14-64\python.exe`, 3.14.6 (MSC v.1944 64-bit) |
| crew | 1.2.68, from the plugin cache: `C:\Users\d3ade\.claude\plugins\cache\useful-claude-add-ons\crew\1.2.68\hooks\scripts\verify-gate.sh` (162967 bytes, mtime 2026-10-23 13:57:15 -05:00) |
| Repo under test | `C:\repos\personal\useful-claude-add-ons` |
| Load | **CPU was loaded by concurrent sabotage runs throughout.** `_Total` processor time sampled 32.9 % → 45.5 % around the repriced run and 40.0 % → 15.0 % around the main run; ~910 processes on the box. Every wall time below is a loaded-machine number, not a quiet-machine one, and the two runs did not see identical load. |

## 1. WinError 6 — `01-stop-hook-winerror6-tracebacks.log` (7145 bytes)

**Method: copied from the gate's own detail log. No re-run was needed** — the log already carried
the full tracebacks, so the detached-child / invalid-stdin reproduction described as the fallback
was not used.

Source: `C:\repos\personal\useful-claude-add-ons\.crew\.verify-gate.log`, size 35133 bytes,
mtime **2026-10-23T23:52:11.469-05:00** (UTC `2026-10-24T04:52:11.469Z`). That mtime is the only
time anchor available: **the detail log carries no per-line timestamps.** What it carries per
command is an elapsed duration (`verify-gate: 6s  python3 -m pytest ...`), and those lines are
included whole.

The slice is lines 109–176 of that log, byte-for-byte, and holds both failing-command sections
complete: the `VERIFY FAILED:` header, the `subprocess.py` frames, the
`OSError: [WinError 6] The handle is invalid` line, the `short test summary info` block and the
following `verify-gate: Ns` duration line.

- `plugin/crew/tests/test_diagram_doc.py::test_render_sh_records_the_source_hash_and_rerenders_on_a_new_one`
  — 1 failed, 49 passed in 1.61s. Failing handle: a `bash.exe` Popen.
- `plugin/crew/tests/test_qa_audit_env.py` — 4 failed, 264 passed, 6 skipped in 4.92s. Failing
  handle: a `git -C D:\temp\pytest-of-d3ade\...` Popen.

Both die in the same place: `subprocess.py:1431`, `_make_inheritable` →
`_winapi.DuplicateHandle` on the **stdin** handle (`p2cread`), handle value 496 in both. The Stop
hook hands the child an invalid stdin handle; `DuplicateHandle` on it raises WinError 6.

### Not captured

- **`verify-gate: FAILED ... budget ...` is not in this log, and is not recoverable for the 23:52
  run.** That summary is written to the gate's **stdout**, not to the detail log, and the 23:52
  run's stdout was not captured. The nearest things the detail log does hold are included in the
  slice set: `verify-gate: stop budget 60s; ran 60s of stated cost, deferred 95.` (line 108) and
  `verify-gate: 382s total across 20 rule command(s)` (line 201). The real summary line *is*
  captured, from a fresh run, in `03a-stop-run-repriced.out` — see item 3.

## 2. The Windows command-line limit at `verify-gate.sh:2826`

### (a) The command text — `02a-verify-gate-2826-code.txt` (1657 bytes)

Lines 2813–2851 of the 1.2.68 `verify-gate.sh`, byte-for-byte. The exec at 2826 is:

    "$PY" -c '<inline script>' "$EXTRAS" "$SYNC_SHA" "$BUDGET_FLAG" <<< "$CMD_LOG" | tr -d '\r' | gate_record_sync "$PY" "$SYNC_PY"

### (b) The argv byte length — `02c-argv-byte-length.txt`, `02c-extras-record6-argv3.json` (37237 bytes)

**Method: the matcher stage was reproduced read-only, then measured.** The matcher is the
heredoc python block at `verify-gate.sh:1344–2063`; it was extracted verbatim and run with the
same four arguments the gate passes, against `C:\repos\personal\useful-claude-add-ons` at HEAD
`32122ca33`, with `BASE` set to the stale marker `734b8214` — i.e. `verify-gate.sh:774`'s branch.
`BUDGET_FLAG` was empty, which is what a Stop run passes. Nothing was written to the repo. These
are **fresh bytes measured on the current tree**, not a recovery of the exact bytes the 23:52 run
built. `02c-extras-record6-argv3.json` is the resulting record 6 — the actual oversized argument.

The stale marker produces **1620 changed files / 69693 bytes of paths**, and **96 matched rules**.

**The changed-file list is not what overflows argv.** It goes through a temp file by design —
`verify-gate.sh:1324` says so in terms, and records a 2026-09-07 measurement of the same failure
at 74 files. What overflows is record 6, the matched-rules JSON:

| | bytes |
|---|---|
| `argv[0]` `$PY` as bash execs it | 65 |
| `argv[1]` `-c` | 2 |
| `argv[2]` inline python script | 483 |
| **`argv[3]` `$EXTRAS` (record 6 JSON, 96 rules)** | **37237** |
| `argv[4]` `$SYNC_SHA` | 40 |
| `argv[5]` `$BUDGET_FLAG` (empty on Stop) | 0 |
| sum | 37827 |
| sum + one terminator per element | **37833** |

Windows' `CreateProcess` `lpCommandLine` limit is 32767 characters. `argv[3]` **alone** exceeds it
by 4470; the whole vector exceeds it by 5066.

### (c) The raw error

    C:/Users/d3ade/.claude/plugins/cache/useful-claude-add-ons/crew/1.2.68/hooks/scripts/verify-gate.sh: line 2826: /c/Users/d3ade/AppData/Local/Python/pythoncore-3.14-64/python.exe: Argument list too long

Captured twice, both raw: `02b-argument-list-too-long.log` (lines 200–211 of the 23:52 detail log,
with the `NOT VERIFIED` summary block around it) and `03a-stop-run-repriced.out` (a fresh run, see
item 3).

**Consequence, visible in the artifacts:** `gate_record_sync` never runs, so the per-rule record is
never written. `D:\temp\claude\wt-winrun\.crew\.verify-gate.record.json` after the fresh run holds
`{"rules": {}}` — zero entries. The baseline cannot advance, so the marker stays stale, so the next
Stop sees the same ~1600 files, rebuilds the same oversized argv and fails the same way. It is
self-sustaining.

### (d) Minimal standalone repro — `02d-e2big-threshold-repro.txt`

**Method: captured from a run of `harness/repro-e2big.sh` under Git Bash** with `--noprofile
--norc`. No crew code and no repo state: one `python.exe` call with a single argv element of `n`
bytes, swept and then bisected. Environment measured at 7991 bytes (E2BIG counts argv **plus**
environment).

    largest single argv element that execs: 32684 bytes
    smallest that fails:                    32685 bytes

At and above 32685 the error text is identical to the gate's, down to the wording:
`python.exe: Argument list too long`, exit 126.

## 3. Stop-hook run time on a repriced checkout

Headline: **111.0 s repriced vs 661.6 s on main**, neither capped, both exiting 2, both hitting
line 2826. But see the caveat under the table before quoting that as a 6x speedup.

**Method: captured from a real `verify-gate.sh` Stop run** (no flags, so the 60s stop budget
applies) via `harness/run-stop-gate.cmd`, launched by `harness/launch-stop.ps1`. The batch puts
`C:\Program Files\Git\usr\bin` then `C:\Program Files\Git\bin` first on `PATH`, `cd`s to the
worktree and redirects **stdin from `NUL`**. The timer and the 700s cap are in the PowerShell
launcher. Throwaway detached worktrees, no markers present, so the marker was stale by
construction. The two runs were **sequential, not concurrent**, so they contend with the sabotage
load but not with each other.

| | repriced (`origin/win-reprice-patch`, `89fb57963`) | main (`origin/main`, `3e7d397da`) |
|---|---|---|
| wall | **111.04 s** | **661.59 s** |
| window | 00:04:35.997 → 00:06:27.037 -05:00 | 00:06:29.592 → 00:17:31.177 -05:00 |
| commands run / deferred | 12 run, 104 deferred | 17 run, 68 deferred |
| stated cost vs budget | 65 s / 60 s | 598 s / 60 s |
| capped at 700 s? | no | no |
| gate exit | 2 (`VERIFY_GATE_EXIT=2`) | 2 (`VERIFY_GATE_EXIT=2`) |
| line 2826 failure | yes, reproduced | yes, reproduced |
| WinError 6 | none in the 12 that ran | **yes** — `test_recurring_findings.py::test_data_comes_from_the_plugin_not_the_root` |
| `_Total` CPU before / after | 32.9 % / 45.5 % | 40.0 % / 15.0 % |

**Read the wall times as `wall (N run, M deferred)`, never as like-for-like.** The two trees price
rules differently and therefore select different numbers of commands; a smaller wall time can mean
"deselected more", not "faster".

`exit_code=0` in the `.meta` files is **`cmd.exe`'s** exit status, not the gate's. The gate's own
status is the `VERIFY_GATE_EXIT=` line at the end of the `.out` file.

The repriced run is the only place the real stdout summary exists:

    verify-gate: FAILED 1 cmd | PASSED 12 cmd | NOT VERIFIED 83 item(s) (reach 0, over-budget 38, dirty tree 0, deferred 45, skipped 0, other 0) | credited 0 | budget 65s/60s | detail: .crew/.verify-gate.log

### A third WinError 6, on a different handle

The main run reproduced WinError 6 under this harness — see `03b-stop-run-main.out`. It is **not**
the same site as the two in item 1:

| | item 1 (23:52 Stop hook) | item 3 main run (NUL stdin) |
|---|---|---|
| failing frame | `subprocess.py:1380 _get_handles` | `subprocess.py:1422 _get_handles` |
| handle duplicated | `p2cread` — **stdin** | `errwrite` — **stderr** |
| handle value | 496 | 1232 |
| test | `test_diagram_doc`, `test_qa_audit_env` | `test_recurring_findings::test_data_comes_from_the_plugin_not_the_root` |

Same mechanism, different std handle: `_winapi.DuplicateHandle` on a std handle the gate inherited
and that is not valid in this process. Redirecting stdin from `NUL` fixes only the stdin half, and
`03b` shows the stderr half failing in its place.

### Two things these runs do NOT show

1. **Item 3 is not evidence that the reprice fixes WinError 6.** Of the two rules that produced
   WinError 6 at 23:52, one — `test_diagram_check.py test_diagram_doc.py` — *did* run on the
   repriced tree, in 5 s, and passed; the other, the `test_qa_audit*` rule, was **deferred, not
   passed**. The repriced run ran 12 of its selected commands and deferred 104, so "0 WinError 6 in
   `03a`" means "those rules mostly did not run", not "fixed" — and the main run, under the same
   harness, hit WinError 6 anyway on the stderr handle.
2. **What the repriced run's one `FAILED` command was: could not tell.** Its stdout says
   `FAILED 1 cmd | PASSED 12 cmd`, but its detail log has exactly 12 `verify-gate: Ns` duration
   lines and **zero** `VERIFY FAILED:` sections, so the failing command named itself nowhere in the
   artifacts. The failed record sync at line 2826 is consistent with it, but the artifacts do not
   prove it. (The main run's single failure *is* named — the `test_recurring_findings` rule above.)

## Files

`harness/` holds the scripts that produced items 2(b), 2(d) and 3, so the measurements can be
re-run. It is tooling, not evidence.

**Four files have a `.txt` extension but are `.log` content**, byte-for-byte unaltered:
`01-stop-hook-winerror6-tracebacks.txt`, `02b-argument-list-too-long.txt`,
`03a-stop-run-repriced-detail.txt` and `03b-stop-run-main-detail.txt`. The repo's `.gitignore:117`
is a blanket `*.log`, so they could not be committed under their real names. They were renamed
rather than force-added, and `.gitignore` was deliberately not touched.

No secrets: the directory was scanned for token, key and credential patterns before the commit and
came back clean. Paths are kept as captured; the username appears only inside filesystem paths,
never in a token.
