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
# Prefers the first PATH match of python3/python/py -- EVERY match, not the
# first per name -- that actually RUNS (`-c pass`, exit 0, bounded at 3s with
# its process tree killed, exactly as `crew_py_strict` bounds its probe). The
# Windows burn-in (FAIL 3) had a failing WindowsApps python3 ahead of a real
# one: the first-match version handed hooks the stub, so handoff-write.sh
# read no payload fields, while the PowerShell twin found the real python.
#
# When NOTHING runs it still returns the first match, as it always did,
# rather than nothing. That is the fail-closed half of its contract: callers
# like promote-gate.sh and verify-gate.sh invoke what this returns, check the
# status and refuse with a named message, and "no python at all" means
# something else to them (promote-gate.sh stands down). Returning nothing
# for a broken stub would turn a refusal into a stand-down. Callers that
# `exec` the interpreter and have nothing left to check use `crew_py_strict`.
crew_py() {
  # NOT memoized. An earlier version of this function cached its result in
  # process-global variables, but every call site invokes it as
  # `PY=$(crew_py)` -- a `$(...)` command substitution runs the function in
  # a SUBSHELL, so any variable it set was discarded the moment that
  # subshell exited and the next call started from nothing regardless. The
  # cache never once survived a caller; reported 2026-09-24 and removed
  # rather than repaired, because making it real would mean rewriting every
  # `$(crew_py...)` call site across this directory to avoid a subshell --
  # a change to the whole hook layer to speed up a function nothing here
  # calls more than once or twice per process anyway.
  local candidate first=""
  # An OVERALL deadline on top of each candidate's own 3s probe bound: a
  # PATH with several hung candidates would otherwise cost 3s EACH, adding
  # up past the shortest hook timeout that calls this (bridge-status.ps1's
  # twin, 10s) even though every individual probe is bounded. Kept well
  # inside that: the walk gives up on the probing (falling back to the
  # first PATH match, as it always did when nothing runs) once this much of
  # the budget is spent.
  local deadline=$((SECONDS + 8))
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    [ -n "$first" ] || first=$candidate
    # The remaining budget, not a flat 3s, bounds THIS candidate's probe: a
    # fixed 3s watchdog checked only before launch can still overrun the
    # deadline by up to 3s once it is entered, which on a run of several
    # near-8s-but-under candidates followed by one hung one can overrun both
    # this deadline and the 10s hook timeout it exists to stay inside.
    local remaining=$((deadline - SECONDS))
    [ "$remaining" -gt 0 ] || break
    local probe_timeout=$remaining
    [ "$probe_timeout" -le 3 ] || probe_timeout=3
    (
      set -m
      "$candidate" -c pass </dev/null >/dev/null 2>&1 &
      pid=$!
      set +m
      exec 3> >(
        {
          line=
          read -r -t "$probe_timeout" line
          [ "$line" = done ] && exit 0
          if [ -r "/proc/$pid/winpid" ] && read -r winpid < "/proc/$pid/winpid"; then
            MSYS2_ARG_CONV_EXCL='*' taskkill /F /T /PID "$winpid"
          fi
          kill -9 -- "-$pid" || kill -9 "$pid"
        } >/dev/null 2>&1
      )
      wait "$pid"
      status=$?
      trap '' PIPE
      echo done >&3 2>/dev/null
      exit "$status"
    ) || continue
    printf '%s\n' "$candidate"
    return 0
  done < <(type -ap python3 python py 2>/dev/null)
  if [ -n "$first" ]; then
    printf '%s\n' "$first"
    return 0
  fi
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
  # NOT memoized. An earlier version of this function cached its result in
  # process-global variables, but every call site invokes it as
  # `PY=$(crew_py_strict)` -- a `$(...)` command substitution runs the
  # function in a SUBSHELL, so any variable it set was discarded the moment
  # that subshell exited and verify-gate.sh's second call (PY, then
  # SHIM_PY) started from nothing regardless of the cache. Reported
  # 2026-09-24 and removed rather than repaired: making it real would mean
  # rewriting every `$(crew_py_strict)` call site in this directory to avoid
  # a subshell, for a saving that never actually happened.
  # EVERY PATH match of every name, in order -- `type -ap` lists them all,
  # where `command -v` stops at the first. Windows burn-in 2026-09-23 (FAIL
  # 3): a broken WindowsApps python3 ahead of a real python3 made this
  # function give up while role-write-guard.ps1's Resolve-CrewPython, which
  # tries every match, found the real one -- so the two flavours disagreed
  # about whether python existed, and notify.sh failed open and sent a ping
  # its PowerShell twin then sent again.
  #
  # An OVERALL deadline on top of each candidate's own 3s probe bound: a
  # PATH with several hung candidates would otherwise cost 3s EACH, adding
  # up past the shortest hook timeout that calls this (bridge-status.ps1's
  # twin, 10s) even though every individual probe is bounded. Kept well
  # inside that: the walk gives up and reports "no python" rather than keep
  # trying once this much of the budget is spent.
  local _crew_py_strict_deadline=$((SECONDS + 8))
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    # The remaining budget, not a flat 3s, bounds THIS candidate's probe: a
    # fixed 3s watchdog checked only before launch can still overrun the
    # deadline by up to 3s once it is entered, which on a run of several
    # near-8s-but-under candidates followed by one hung one can overrun both
    # this deadline and the 10s hook timeout it exists to stay inside.
    local _crew_py_strict_remaining=$((_crew_py_strict_deadline - SECONDS))
    [ "$_crew_py_strict_remaining" -gt 0 ] || break
    local _crew_py_strict_probe_timeout=$_crew_py_strict_remaining
    [ "$_crew_py_strict_probe_timeout" -le 3 ] || _crew_py_strict_probe_timeout=3
    # BOUNDED, and the whole process tree dies with it. A candidate that
    # never exits would otherwise hang the hook forever, and one that spawns
    # a child holding stdout (a py.exe-style launcher) would hang this `$()`
    # even after the candidate itself was killed. `timeout` is absent on Git
    # Bash, so a watchdog kills at 3s instead; `wait` returns the moment the
    # candidate exits, so a working interpreter costs no added latency.
    # `set -m` puts the candidate in its own process group, which the kill
    # takes whole on a timeout. Under MSYS a native child is outside that
    # group, so `taskkill /T` takes the Windows tree when /proc exposes its
    # winpid (MODELLED, not observed on a Windows host).
    # The watchdog is the builtin `read -t` in a process substitution, on a
    # pipe whose only writer is fd 3 of this subshell, which writes `done`
    # once the candidate has exited. That line alone stands the watchdog
    # down; a timeout, EOF without it, or an error kills -- bash 3.2 answers
    # a timed-out `read -t` with 1, as EOF does, so the status cannot decide.
    # No kill runs after a clean exit, not even at the reaped candidate's
    # group: a child it left behind is not killed (under MSYS a native one
    # never was), and one holding stdout is bounded by the hook's own
    # timeout, not by this probe. The candidate's stdout is a process
    # substitution that reads ONE line, bounded by the same `read -t`, and
    # prints it to this `$()`: a child the candidate leaves holding its
    # stdout holds that pipe, not this `$()`'s, so it cannot keep the probe
    # waiting for EOF past the hook's timeout (review round 2). Not a temp
    # file: that made every hook's python depend on `mktemp`, whose failure
    # the hooks handle on purpose. The reader is in the candidate's group,
    # so a timeout's kill takes it too.
    # `trap '' PIPE`: a watchdog that already timed out is gone, and
    # writing to it must not signal this subshell. A same-user process can
    # write `done` through /proc/<probe>/fd/3 and stand the watchdog down
    # early; that is the user's own processes, outside what this bounds.
    # L-1512: the previous `sleep`
    # watchdog was SIGKILLed, group and all, on EVERY call, while still
    # alive; on Windows CI a SIGKILL sent there ended the hook's own bash.exe
    # (exit 2304, `9 << 8`, empty stderr), which PreToolUse reads as
    # non-blocking -- a guard that never judged, letting the command through.
    # stdin is /dev/null: the candidate must not read the hook payload or
    # this loop's own input.
    real=$(
      set -m
      "$candidate" -c 'import sys; sys.version_info>=(3,8) and print(sys.executable)' </dev/null 2>/dev/null > >(
        line=
        IFS= read -r -t "$_crew_py_strict_probe_timeout" line
        printf '%s\n' "$line"
      ) &
      pid=$!
      set +m
      exec 3> >(
        {
          line=
          read -r -t "$_crew_py_strict_probe_timeout" line
          [ "$line" = done ] && exit 0
          if [ -r "/proc/$pid/winpid" ] && read -r winpid < "/proc/$pid/winpid"; then
            MSYS2_ARG_CONV_EXCL='*' taskkill /F /T /PID "$winpid"
          fi
          kill -9 -- "-$pid" || kill -9 "$pid"
        } >/dev/null 2>&1
      )
      wait "$pid"
      status=$?
      trap '' PIPE
      echo done >&3 2>/dev/null
      exit "$status"
    ) || continue
    # A trailing CR must not survive into the `-x` test below: a real native
    # Windows interpreter run under Git Bash can leave one on its stdout, and
    # `-x "$real"` on a path with a stray \r appended never matches an actual
    # file, rejecting every real interpreter on that combination.
    real=$(printf '%s' "$real" | tr -d '\r')
    [ -n "$real" ] || continue
    # The `sys.version_info>=(3,8) and print(...)` guard above is the version
    # floor: a genuine, working Python 3.7 answers `-c` correctly but prints
    # NOTHING, so `$real` comes back empty and is rejected right here by the
    # check above, same as a broken candidate. Reported 2026-09-24: this
    # function had no version floor at all while role-write-guard.ps1's
    # Resolve-CrewPython already required >= 3.8, so a host with nothing but
    # a real Python 3.7 on PATH had the two flavours disagree about whether
    # python existed at all. Deliberately NOT the .ps1 probe's full
    # JSON-proof-of-implementation shape (CPython/PyPy, major/minor as a
    # structured object): that would need the candidate to answer a SECOND,
    # differently-shaped probe, and dozens of fixtures across this suite are
    # narrow shell stubs that only ever answer the exact single `-c` string
    # this function has always sent -- a second probe would reject all of
    # them regardless of their fixture's own intent (TODO.md's
    # "crew_py_strict not proving Python 3" entry, closed by this narrower
    # form). Folding the floor into the SAME `-c` argument costs nothing
    # extra: a delegating stub falls through to a real interpreter, which
    # answers correctly either way, and a stub that special-cases the exact
    # OLD command still matches, since only the printed CONTENT changed.
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
    #
    # DECIDED CONTRACT (PM, Windows burn-in FAIL 3/4): this function returns
    # the interpreter path in the form THIS bash itself execs as "$py" --
    # POSIX-shaped under Git Bash/MSYS, whatever `sys.executable` printed.
    # A caller that only does `"$PY" ...` (execs it, bash-to-bash) needs
    # nothing further; a caller that hands this path to a DIFFERENT
    # interpreter as DATA -- embedded in a python/pwsh argument, a JSON
    # payload, a file a python script will `open()` -- must convert it at
    # THAT boundary with `cygpath -w`, guarded (`command -v cygpath` first;
    # do nothing if absent, same fail-open shape as the conversion above).
    # `tests/test_context_watch_python_resolver.py`'s
    # `test_resolver_accepts_a_crlf_terminated_real_interpreter` asserts the
    # POSIX-vs-native side of this by asking `_BASH` the same question this
    # function asks (`command -v cygpath`), not by asking the test's own
    # python process -- FAIL 3/4 was exactly that asymmetry: bash's own MSYS
    # runtime finds `cygpath.exe` under its compiled-in `/usr/bin`
    # regardless of what the PARENT (a native python.exe running pytest)
    # was given, so the two can disagree about whether cygpath exists at
    # all on the very host this combination is meant to cover.
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
  done < <(type -ap python3 python py 2>/dev/null)
  return 1
}

# --- The repo config's directory (T-0096) ---------------------------------
#
# Sets CREW_CFG_DIR (the `.crew/` to read config.json or crew.json from) and
# CREW_CFG_SOURCE (own, main or unknown) for the checkout at $1 (default: the
# cwd). The twin of crew_common.repo_config_dir (T-0088), held to it case by
# case by tests/test_worktree_config_shell.py, and of Get-CrewRepoConfigDir in
# the .ps1 hooks. No python: the guards' no-python fallbacks read through it.
# Own files win whole and are never merged. `.git` not a regular file is own
# with no git call. Git names the common directory; a submodule (git dir ==
# common dir) or a bare repository (common dir not named .git) is own. When
# git cannot tell, the source is `unknown`, CREW_CFG_DIR is the own `.crew/`,
# and nothing is inherited -- a guard must not read that as "absent".
# Only READS follow this: markers, logs and incident.json stay in the own .crew/.
crew_repo_config_dir() {
  local root="${1:-.}" n out g c nl='
'
  CREW_CFG_DIR="$root/.crew" CREW_CFG_SOURCE=own
  for n in crew.json config.json; do
    { [ -e "$root/.crew/$n" ] || [ -L "$root/.crew/$n" ]; } && return 0
  done
  [ -f "$root/.git" ] || return 0
  CREW_CFG_SOURCE=unknown
  # No --path-format: git before 2.31 echoes it back as a line of its own.
  out=$(git -C "$root" rev-parse --git-dir --git-common-dir 2>/dev/null) || return 0
  case "$out" in *"$nl"*"$nl"*) return 0 ;; *"$nl"*) ;; *) return 0 ;; esac
  g=$(CDPATH=; cd -- "$root" 2>/dev/null && cd -P -- "${out%%"$nl"*}" 2>/dev/null && pwd -P) || return 0
  c=$(CDPATH=; cd -- "$root" 2>/dev/null && cd -P -- "${out#*"$nl"}" 2>/dev/null && pwd -P) || return 0
  CREW_CFG_SOURCE=own
  [ "$g" != "$c" ] && [ "${c##*/}" = ".git" ] || return 0
  for n in crew.json config.json; do
    if [ -e "${c%/*}/.crew/$n" ] || [ -L "${c%/*}/.crew/$n" ]; then
      CREW_CFG_DIR="${c%/*}/.crew" CREW_CFG_SOURCE=main
      return 0
    fi
  done
}

# Print the resolved path of repo config file $1 (default config.json) for the
# checkout at $2 (default: the cwd).
crew_repo_config_file() {
  crew_repo_config_dir "${2:-.}"
  printf '%s/%s\n' "$CREW_CFG_DIR" "${1:-config.json}"
}

# Print where the handoff note lives, relative to the cwd (the checkout root):
# context.handoffPath from config file $2, read with python $1 through
# crew_state.handoff_path -- the Python readers' own containment
# (crew_freshness.contained_path): a value that leaves the checkout (absolute,
# `..`, a symlink out) is the default .work/HANDOFF.md, with a warning on
# stderr; so is one naming a directory (`.`, `notes/`, an existing folder),
# which cannot hold the note. Printed with forward slashes on every OS. Matters most in a linked worktree that inherits the main checkout's
# config (L-0680): an absolute path there would name the main checkout's file.
# Any failure prints the default, which is inside the checkout.
crew_handoff_path() {
  "$1" - "$(dirname "${BASH_SOURCE[0]}")" "$2" << 'PY'
import json, os, sys
default = ".work/HANDOFF.md"
try:
    sys.path.insert(0, sys.argv[1])
    from crew_state import handoff_path
    try:
        with open(sys.argv[2], encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        cfg = {}
    cfg = cfg if isinstance(cfg, dict) else {}
    root = os.path.realpath(os.getcwd())
    got = handoff_path(root, cfg)
    ctx = cfg.get("context")
    value = ctx.get("handoffPath") if isinstance(ctx, dict) else None
    if isinstance(value, str) and value and os.path.realpath(os.path.join(root, value)) != got:
        sys.stderr.write("crew: context.handoffPath leaves this checkout - using %s\n" % default)
    elif got == root or os.path.isdir(got) or (isinstance(value, str) and value.endswith(("/", os.sep))):
        sys.stderr.write("crew: context.handoffPath names a directory - using %s\n" % default)
        got = os.path.join(root, default)
    print(os.path.relpath(got, root).replace(os.sep, "/"))
except Exception:
    print(default)
PY
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
#   2. emergency.standDown is not false (a repo can forbid stand-downs; read
#      from the resolved repo config, so a lane inherits the main checkout's)
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
  crew_repo_config_dir .
  grep -q '"standDown"[[:space:]]*:[[:space:]]*false' "$CREW_CFG_DIR/config.json" 2>/dev/null && return 1
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
