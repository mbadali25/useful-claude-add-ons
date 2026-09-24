#!/usr/bin/env bash
# Shared helpers for crew hook scripts. Sourced, never run directly.
#
# Two problems this solves:
#   1. Every hook is registered TWICE in hooks.json - once as bash, once as
#      its .ps1 twin with `shell: powershell` - because hooks.json cannot know
#      which shell a given machine has. So a .sh script here is only ever
#      reached through bash, and `crew_tool_dispatch` below is the OTHER shape
#      for the same problem: a single bash-registered script handing off to its
#      twin when the command being judged came from the PowerShell tool. The
#      branch is which TOOL was used, not which OS is running. `guard.sh` and
#      `promote-gate.sh` call it, and it is harmless alongside the dual
#      registration - the dual-matcher entries mean a PowerShell tool call
#      reaches guard.ps1 directly and the dispatch never fires.
#   2. python3 is not a given. Git Bash ships without it, and every script
#      here parses hook JSON from stdin.

# Hand control to the PowerShell twin when the command being judged is
# PowerShell. The branch is WHICH TOOL Claude used, not which OS you are on:
# a Bash-tool command is bash syntax even on Windows, and judging it with
# PowerShell rules blocks the correct capture form and misses the wrong one.
#
# $1 = twin filename, $2 = the raw hook JSON (already read from stdin).
crew_tool_dispatch() {
  case "$2" in
    *'"tool_name"'*'"PowerShell"'*) ;;
    *) return 0 ;;
  esac
  local twin
  twin="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)/$1"
  [ -f "$twin" ] || return 0
  local ps
  ps=$(command -v powershell.exe 2>/dev/null || command -v pwsh.exe 2>/dev/null \
       || command -v powershell 2>/dev/null || command -v pwsh 2>/dev/null) || return 0
  printf '%s' "$2" | "$ps" -NoProfile -ExecutionPolicy Bypass -File "$twin"
  exit $?   # NOT exec: on the right of a pipe it replaces the subshell only
}

# Strip carriage returns. jq and some Windows tools emit CRLF, and a trailing
# CR breaks every regex anchored with $.
crew_strip_cr() { printf '%s' "$1" | tr -d '\r'; }

# Resolve a usable Python. Echoes nothing when there is none.
#
# DELIBERATELY NOT hardened against a WindowsApps App Execution Alias. Most
# callers of this are mitigated downstream -- they check the status of the
# python they invoked and fail closed with a named message (verify-gate.sh,
# promote-gate.sh) -- and widening this one would change the behaviour of
# every hook that calls it for a bug that only matters where the caller
# `exec`s the interpreter and has nothing left to check afterwards. Those
# callers use `crew_py_strict` below instead.
crew_py() {
  command -v python3 2>/dev/null && return 0
  command -v python  2>/dev/null && return 0
  command -v py      2>/dev/null && return 0
  return 1
}

# Resolve a python that has been PROVED to be an interpreter. Echoes nothing
# when there is none.
#
# `crew_py` above asks `command -v` and stops there. On Windows that is not
# enough: the Store App Execution Alias at
# %LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe IS a real, executable
# file, so `command -v python3` resolves it, the non-empty test passes, and
# the stub gets run -- producing no output and a nonzero status that a caller
# which already `exec`ed has no way left to report. Reported 2026-09-19
# against role-write-guard.sh and again 2026-09-22 against the since-deleted
# PM pulse hook, where it cost blocking findings in total silence.
#
# The probe, not the path, is what decides: a candidate is only accepted once
# it has run `print(sys.executable)` and handed back a path. `sys.executable`
# rather than the PATH hit because the name found may be a shim that re-execs
# elsewhere, and the probe already paid for asking.
#
# BYTE-FOR-BYTE the body of `_resolve_role_write_python` in
# role-write-guard.sh, which keeps its own copy for the reason its header
# records (that hook is the one that can BLOCK a tool call, and its test
# suite patches that file textually). `tests/test_context_watch_python_resolver.py`
# asserts the two copies still agree -- a hand-copy with no guard is this
# repository's most repeated defect.
crew_py_strict() {
  for name in python3 python py; do
    candidate=$(command -v "$name" 2>/dev/null) || continue
    real=$("$candidate" -c 'import sys; print(sys.executable)' 2>/dev/null) || continue
    # A trailing CR must not survive into the `-x` test below: a real native
    # Windows interpreter run under Git Bash can leave one on its stdout, and
    # `-x "$real"` on a path with a stray \r appended never matches an actual
    # file, rejecting every real interpreter on that combination.
    real=$(printf '%s' "$real" | tr -d '\r')
    [ -n "$real" ] || continue
    # NOT a blanket "reject anything containing WindowsApps" -- that used to
    # sit here (on both $candidate above and $real here) and rejected a
    # genuine Microsoft Store Python install, which runs from EXACTLY that
    # shape: `command -v python3` resolves the alias at
    # `...\Microsoft\WindowsApps\python3.exe`, and that alias, when Python IS
    # actually installed through the Store, relays to a REAL working
    # interpreter whose own `sys.executable` is
    # `...\WindowsApps\PythonSoftwareFoundation.Python.3.x_<hash>\python.exe`
    # -- also under a WindowsApps-rooted path, so the substring match caught
    # it too. Reported 2026-09-22: on a Store-Python machine this made
    # `crew_py_strict` report "no usable python" every turn, on a machine
    # where python plainly works.
    #
    # The substring check was defense in depth against the NON-Store-install
    # case: a placeholder alias with no real Python behind it, which the
    # OS reroutes to opening the Store GUI. But the exec-and-probe below
    # already proves the difference without needing to know WHERE the
    # interpreter lives -- a placeholder alias run non-interactively via
    # `-c` produces no usable stdout (rejected by `-n` above) or a status
    # this loop never reaches success on either way, and `-x "$real"`
    # further down still requires whatever path IS printed to be a real,
    # executable file. Removing the substring check trusts that proof
    # instead of a location guess that happened to reject the working case.
    # A native Windows `sys.executable` (e.g. `C:\fakepy\python.exe`) must be
    # normalised into a form THIS shell can actually stat before `-x` runs on
    # it -- the raw backslash-drive-letter form never matches a real file
    # under Git Bash, WSL, or plain Linux. `cygpath -u`, when present, is the
    # accurate conversion (`C:\fakepy\...` -> `/c/fakepy/...`); its absence
    # (no Windows compat layer at all) falls back to the SAME shape by hand:
    # lower-case the drive letter, drop the `:`, and put it under a leading
    # `/` -- `C:\fakepy\python.exe` -> `/c/fakepy/python.exe`. NOT a bare
    # backslash->forward-slash swap (`C:/fakepy/python.exe`, no leading `/`):
    # that string is RELATIVE, so `-x` on it silently depends on the
    # resolver's own cwd, and any `cd` between here and the caller breaks it
    # -- `-x` on the absolute `/c/...` form does not.
    case "$real" in
      [A-Za-z]:\\*|[A-Za-z]:/*)
        if command -v cygpath >/dev/null 2>&1; then
          real=$(cygpath -u "$real")
        else
          drive=$(printf '%s' "$real" | cut -c1 | tr '[:upper:]' '[:lower:]')
          rest=$(printf '%s' "$real" | cut -c3- | tr '\\\\' '/')
          real="/$drive$rest"
        fi
        ;;
    esac
    # Non-empty stdout is not proof: a wrapper could print a plausible-looking
    # path to something that is not there, or not runnable, and the printed
    # string is never executed to confirm it. `-x` requires the path to both
    # EXIST and be executable, which `sys.executable` from a real interpreter
    # always is. This line is BEHAVIOURALLY load-bearing, not decorative --
    # `tests/test_context_watch_python_resolver.py`'s
    # `test_resolver_rejects_a_real_but_non_executable_target` runs this function
    # end-to-end against a candidate that prints a real, existing, but
    # non-executable file and fails if the check is missing OR merely present
    # after the `return 0` below where it can never run.
    [ -x "$real" ] || continue
    printf '%s\n' "$real"
    return 0
  done
  return 1
}

# --- Emergency lane -------------------------------------------------------
#
# Is an incident open, unexpired, and allowed to stand the gates down?
# See hooks/scripts/crew_incident.py for the file format: expiresAtEpoch is an
# integer of seconds so the comparison is arithmetic rather than a date parse,
# which in bash would mean a date(1) that behaves differently on macOS.
#
# Four separate conditions, deliberately not collapsed:
#   1. a state file exists
#   2. emergency.standDown is not false (a repo can forbid stand-downs)
#   3. it PARSES as JSON, in full
#   4. the clock has not passed the expiry
#
# (4) is the safety property: forgetting to close an incident cannot leave a
# repository permanently ungated. (3) is why this parses instead of grepping the
# epoch out with sed: `{ not json "expiresAtEpoch": 9999999999` is not a valid
# incident, but sed would happily find a future epoch in it and stand every gate
# down, while the PowerShell twin's ConvertFrom-Json rejects the document. That
# is a gate that can be switched off with a typo, and one that behaves
# differently per flavour.
#
# Every failure here - including no python at all - returns "not active", so the
# gates keep gating. That is the only safe direction: a gate that cannot read
# its own state must not assume it has been told to stand down.
crew_incident_active() {
  [ -f .crew/incident.json ] || return 1
  grep -q '"standDown"[[:space:]]*:[[:space:]]*false' .crew/config.json 2>/dev/null && return 1
  local py exp now
  py=$(crew_py) || return 1
  exp=$("$py" - << 'PY' 2>/dev/null
import json
try:
    d = json.load(open(".crew/incident.json", encoding="utf-8"))
    print(int(d["expiresAtEpoch"]) if isinstance(d, dict) else 0)
except Exception:
    print(0)
PY
)
  [ -n "$exp" ] || return 1
  [ "$exp" -gt 0 ] 2>/dev/null || return 1
  now=$(date -u +%s 2>/dev/null) || return 1
  [ "$now" -lt "$exp" ]
}

# Record a gate that did not run. $1 = gate name, $2 = detail.
#
# One row per gate+detail per incident, not per turn. Stop fires every turn and
# on Windows with Git Bash installed BOTH flavours of the hook run, so a
# ten-turn incident would otherwise report forty skipped gates - a number that
# measures how long the incident lasted, not what is owed. The closing report
# is a debt list, and the same unrun check is one debt however many times the
# gate declined to run it. crew_incident.log_skip applies the same rule.
crew_incident_log() {
  mkdir -p .crew 2>/dev/null
  local row gate detail
  # The log is tab-separated and line-oriented, and a detail can carry an
  # environment name, a rollback path or a rollbackReason straight out of
  # .crew/verify.json. A tab or a newline in one of those would forge a row.
  # crew_incident.py normalises the same way.
  gate=$(printf '%s' "$1" | tr '\t\r\n' '   ')
  detail=$(printf '%s' "$2" | tr '\t\r\n' '   ')
  row="$(printf '%s\t%s' "$gate" "$detail")"
  # -F: the detail is prose and contains regex metacharacters. Anchored to
  # after the epoch field, so a detail cannot match a different gate's row.
  if [ -f .crew/incident-skips.log ] \
     && cut -f2- .crew/incident-skips.log | grep -qxF "$row"; then
    return 0
  fi
  # Best-effort dedupe: two hook flavours appending at the same instant can both
  # miss the row above. The consequence is a duplicated line in a debt list, not
  # a gate that failed to fire, and crew_incident.read_skips dedupes again on
  # read so the count stays right either way. Not worth a lock file.
  printf '%s\t%s\n' "$(date -u +%s)" "$row" >> .crew/incident-skips.log
}

# Read one top-level string field out of hook JSON on stdin.
# Usage: crew_json_field "$INPUT" transcript_path
crew_json_field() {
  local py; py=$(crew_py) || return 1
  printf '%s' "$1" | "$py" -c \
    'import sys,json;print(json.load(sys.stdin).get(sys.argv[1],""))' "$2" 2>/dev/null
}
