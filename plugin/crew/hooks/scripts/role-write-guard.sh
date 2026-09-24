#!/usr/bin/env bash
#
# PreToolUse gate on Write/Edit, keyed on `agent_type`. Thin wrapper: the
# whole decision lives in role_write_guard.py so bash and PowerShell cannot
# drift -- same shape as crew-context.sh -> crew_context.py.
#
# Registered on matcher `Write|Edit`, not branched by tool_name the way
# promote-gate.sh branches on Bash vs PowerShell: Write and Edit are the same
# tool regardless of which shell is installed, so both flavours here are
# simply wired to the event, like verify-gate.sh/.ps1, and one is expected to
# be the flavour that actually runs on a given machine.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"

INPUT=$(cat)

# NOT plain `crew_py()`. That resolver is `command -v python3 || python ||
# py` with no filtering at all, shared by seven other hooks that all fail
# OPEN the same way on a WindowsApps App Execution Alias -- reported
# 2026-09-19: on a machine where a WindowsApps python3 stub sits ahead of a
# real interpreter on PATH, bash silently skipped enforcement (the stub
# produces no usable output and this script fell through the same way it
# does when no python exists at all) while role-write-guard.ps1's own
# hardened Resolve-CrewPython found the real interpreter and ran the check
# -- so which SHELL FLAVOUR Claude Code happened to invoke on a given turn
# decided whether `guards.roleWrites: block` did anything. Changing
# `crew_py()` in _common.sh would fix this hook by widening the blast
# radius to every hook that calls it for a bug specific to the one hook
# that can BLOCK a tool call, so this one carries its own narrower resolver
# instead -- the bash twin of `role-write-guard.ps1`'s
# `Resolve-CrewPython`, not a shared one.
_resolve_role_write_python() {
  # EVERY PATH match of every name, in order -- `type -ap` lists them all,
  # where `command -v` stops at the first. Windows burn-in 2026-09-23 (FAIL
  # 3): a broken WindowsApps python3 ahead of a real python3 made this
  # function give up while role-write-guard.ps1's Resolve-CrewPython, which
  # tries every match, found the real one -- so the two flavours disagreed
  # about whether python existed, and notify.sh failed open and sent a ping
  # its PowerShell twin then sent again.
  while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    # `command -v` finding a name on PATH is not enough -- the WindowsApps
    # alias IS a real, executable file, so `command -v python3` resolves it
    # cleanly. Running it and reading back `sys.executable` is what
    # actually tells real python from the stub: the stub produces no
    # parseable stdout (it either does nothing or launches the Store, which
    # cannot happen in this non-interactive pipe) rather than a real
    # interpreter path.
    # BOUNDED, and the whole process tree dies with it. A candidate that
    # never exits would otherwise hang the hook forever, and one that spawns
    # a child holding stdout (a py.exe-style launcher) would hang this `$()`
    # even after the candidate itself was killed. `timeout` is absent on Git
    # Bash, so a watchdog kills at 3s instead; `wait` returns the moment the
    # candidate exits, so a working interpreter costs no added latency.
    # `set -m` puts the candidate in its own process group, which the kill
    # takes whole -- on a timeout, and after a normal exit too, for any child
    # it left behind. Under MSYS a native child is outside that group, so
    # `taskkill /T` takes the Windows tree when /proc exposes its winpid
    # (MODELLED, not observed on a Windows host). No `sleep` at all means no
    # watchdog: unbounded, as before, rather than killing every candidate.
    # stdin is /dev/null: the candidate must not read the hook payload or
    # this loop's own input.
    real=$(
      set -m
      "$candidate" -c 'import sys; sys.version_info>=(3,8) and print(sys.executable)' </dev/null 2>/dev/null &
      pid=$!
      (
        sleep 3 2>/dev/null || exit 0
        if [ -r "/proc/$pid/winpid" ] && read -r winpid < "/proc/$pid/winpid"; then
          MSYS2_ARG_CONV_EXCL='*' taskkill /F /T /PID "$winpid"
        fi
        kill -9 -- "-$pid" || kill -9 "$pid"
      ) </dev/null >/dev/null 2>&1 &
      watchdog=$!
      wait "$pid"
      status=$?
      kill -9 -- "-$watchdog" "-$pid" 2>/dev/null
      exit "$status"
    ) || continue
    # A trailing CR must not survive into the `-x` test below: a real native
    # Windows interpreter run under Git Bash can leave one on its stdout, and
    # `-x "$real"` on a path with a stray \r appended never matches an actual
    # file, rejecting every real interpreter on that combination.
    real=$(printf '%s' "$real" | tr -d '\r')
    [ -n "$real" ] || continue
    # The `sys.version_info>=(3,8) and print(...)` guard above is the version
    # floor, BYTE-FOR-BYTE the same fix `_common.sh`'s `crew_py_strict` got
    # (see that copy's comment for the full reasoning): a genuine Python 3.7
    # answers `-c` correctly but prints NOTHING, so `$real` is empty and is
    # rejected right here, matching role-write-guard.ps1's own >= 3.8 floor.
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
    # this resolver report "no usable python" every turn, on a machine
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
    # `sys.executable`, not `$candidate`: the PATH-found name may be a shim
    # that re-execs elsewhere, and the probe already paid the cost of
    # asking python where it actually lives.
    printf '%s\n' "$real"
    return 0
  done < <(type -ap python3 python py 2>/dev/null)
  return 1
}

PY=$(_resolve_role_write_python) || {
  echo "role-write-guard: no usable python - cannot judge this write, allowing it unjudged." >&2
  exit 0
}

# Deny-list mirror of role_write_guard.py's `_DENY_ROLES`, plus `pm` (that
# module's other restricted role) -- used ONLY by the launch-failure
# fallback below, mirroring role-write-guard.ps1's own
# `$RestrictedRolesForFallback`. `tests/test_role_write_guard.py`'s parity
# test re-derives the python side from `agents/*.md` on every run and
# asserts this list matches it.
_role_write_is_restricted() {
  case "$1" in
    explorer|researcher|reviewer|security|pm) return 0 ;;
    *) return 1 ;;
  esac
}

# Best-effort `agent_type` extraction from the raw JSON -- never fails, and
# a value this cannot find or parse answers empty (unrestricted). Mirrors
# role-write-guard.ps1's `Get-FallbackRole`: only consulted when python
# could not run at all, so there is no real decision to defer to and this
# never needs to be more than "good enough to fail closed for pm/deny".
_role_write_fallback_role() {
  role=$(printf '%s' "$1" | grep -o '"agent_type"[[:space:]]*:[[:space:]]*"[^"]*"' \
         | head -n 1 | sed -E 's/.*:[[:space:]]*"([^"]*)"/\1/')
  role=$(printf '%s' "$role" | tr '[:upper:]' '[:lower:]')
  case "$role" in
    crew:*) role="${role#crew:}" ;;
  esac
  printf '%s' "$role"
}

# PYTHONUTF8=1 / PYTHONIOENCODING=utf-8 in the CHILD's environment only --
# defense in depth alongside role_write_guard.py's own `sys.stdin.buffer`
# read (which does not depend on either), and the actual fix for that
# script's stdout/stderr writes of a non-ASCII path, which DO depend on the
# interpreter's text-mode default. Reported 2026-09-19 against the .ps1
# twin, where a caller's environment explicitly unsetting these could still
# reach python; set here too so neither flavour depends on the CALLER never
# having touched them.
printf '%s' "$INPUT" | PYTHONUTF8=1 PYTHONIOENCODING=utf-8 "$PY" "$DIR/role_write_guard.py"
status=$?

if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  # The interpreter did not actually judge this write -- role_write_guard.py
  # itself only ever exits 0 or 2 (hardened against its own exceptions), so
  # ANY other status means python never ran to completion: resolved
  # successfully by the probe above, then deleted, made unexecutable, or
  # otherwise failed to launch before this line (`bash: $PY: No such file
  # or directory` is exit 127; "found but not executable" is 126, but this
  # check does not special-case either -- any status outside {0, 2} is
  # equally "no real decision was reached"). `PreToolUse` treats any exit
  # code other than 0 or 2 as NON-BLOCKING, so without this check the write
  # went through unjudged with only a shell error on stderr -- role-write-
  # guard.ps1's own header already promised this hook fails closed for a
  # restricted role; this closes the same gap on the bash side. Reported
  # and fixed 2026-09-19.
  fallback_role=$(_role_write_fallback_role "$INPUT")
  if _role_write_is_restricted "$fallback_role"; then
    echo "role-write-guard: could not launch the python interpreter ($PY) to judge this write (exit $status); failing closed for role '$fallback_role'." >&2
    exit 2
  fi
  echo "role-write-guard: could not launch the python interpreter ($PY) to judge this write (exit $status); allowing it unjudged." >&2
  exit 0
fi

exit "$status"
