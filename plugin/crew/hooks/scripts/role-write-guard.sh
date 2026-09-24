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

# Case-insensitive `case`/`[[ ]]` pattern matching for the rest of this
# script, so the no-python role check below can compare `agent_type`
# against `_role_write_is_restricted`'s deny list and the `crew:` prefix
# without lower-casing the string first -- see that function's own
# comment for why lower-casing was the wrong tool. `shopt` itself has
# been in bash since long before 3.2, so no guard is needed for its
# presence; `2>/dev/null` only covers a `nocasematch` spelling this
# particular bash build might not recognise, in which case matching
# quietly stays case-sensitive rather than erroring out.
shopt -s nocasematch 2>/dev/null

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
  # NOT memoized. This hook has one call site (`PY=$(_resolve_role_write_python)`
  # below), itself a `$(...)` subshell, so a cache set here never survives
  # even that one caller -- an earlier version carried the cache anyway,
  # copied from `crew_py_strict`'s own (equally dead) memo. Removed for the
  # same reason `_common.sh`'s copy was: see that copy's comment for the
  # full account.
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
        sleep "$_crew_py_strict_probe_timeout" 2>/dev/null || exit 0
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
    # `sys.executable`, not `$candidate`: the PATH-found name may be a shim
    # that re-execs elsewhere, and the probe already paid the cost of
    # asking python where it actually lives.
    printf '%s\n' "$real"
    return 0
  done < <(type -ap python3 python py 2>/dev/null)
  return 1
}

# Deny-list mirror of role_write_guard.py's `_DENY_ROLES`, plus `pm` (that
# module's other restricted role) -- used both when NO python resolves at
# all (below) and by the launch-failure fallback further down, mirroring
# role-write-guard.ps1's own `$RestrictedRolesForFallback`.
# `tests/test_role_write_guard.py`'s parity test re-derives the python side
# from `agents/*.md` on every run and asserts this list matches it.
_role_write_is_restricted() {
  case "$1" in
    explorer|researcher|reviewer|security|pm) return 0 ;;
    *) return 1 ;;
  esac
}

# Best-effort `agent_type` extraction from the raw JSON, PURE BASH -- no
# `grep`/`head`/`sed`/`tr` at all. Reported 2026-09-24: the previous version
# of this function piped through exactly those four tools, so on a PATH that
# supplies python-resolution's own coreutils (`dirname`, `cat`) but not
# those four, every one of those pipes failed silently (`command not
# found`), `role` came back empty, and a `pm` write went through UNJUDGED
# even though nothing here needed python at all to see `agent_type: "pm"`
# sitting in the raw JSON. Bash's own `[[ =~ ]]` regex engine is a builtin,
# never an external process, so it works whether or not ANY of those tools
# are on PATH.
#
# `_ROLE_WRITE_FALLBACK_ROLE` / `_ROLE_WRITE_FALLBACK_DETERMINED` are
# GLOBALS this function sets directly, NOT a printed return value captured
# via `$(...)` -- that command-substitution form runs the function in a
# SUBSHELL, and a subshell's variable assignments (`_ROLE_WRITE_FALLBACK_
# DETERMINED=0` included) never escape back to the caller. An earlier draft
# of this function printed the role and left the determined-flag as a
# "global" set the same way `_resolve_role_write_python` sets `PY` via
# `PY=$(...)` -- which works for a value returned on stdout, but silently
# discarded the flag every single time, so the caller always saw
# `_ROLE_WRITE_FALLBACK_DETERMINED` unset/empty regardless of what this
# function actually decided. Direct assignment with NO command substitution
# around the call is what makes the flag visible to the caller at all.
#
# The flag distinguishes two shapes this used to conflate: genuinely NO
# `agent_type` key at all (this hook fired outside a subagent --
# unrestricted, matching role_write_guard.py's own "no agent_type at all"
# case) from a key that IS present in some form this best-effort parse
# could not read a value out of (a non-string value, a `\"`-escaped quote
# inside the string, ...). The second is "cannot tell", not "not a
# subagent", and CLAUDE.md's named recurring bug is exactly an unknown
# wearing the safe-looking value's label -- so the caller fails closed on
# it rather than falling through to the unrestricted branch.
_role_write_fallback_role() {
  local payload="$1"
  _ROLE_WRITE_FALLBACK_ROLE=""
  _ROLE_WRITE_FALLBACK_DETERMINED=1
  if [[ "$payload" =~ \"agent_type\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]]; then
    _ROLE_WRITE_FALLBACK_ROLE="${BASH_REMATCH[1]}"
  elif [[ "$payload" == *'"agent_type"'* ]]; then
    _ROLE_WRITE_FALLBACK_DETERMINED=0
  fi
  # NOT lower-cased here. Bash 3.2 (macOS's shipped /bin/bash) has no
  # `${var,,}` -- that is a bash-4-only case-conversion expansion, and
  # using it here made this function itself die with "bad substitution"
  # on exactly the platform this pure-bash rewrite was meant to make MORE
  # portable, not less: a syntax error in a sourced/executed script is a
  # non-2 exit, which the hook's own contract at the bottom of this file
  # treats as "python never ran" and routes into this SAME fallback for a
  # second, sourceless time. Piping through `tr` instead re-added the
  # exact external-tool dependency this pure-bash rewrite exists to drop
  # -- measured directly: a PATH carrying only `dirname`/`cat` (this
  # file's own FIX-1 repro, no `tr` either) made `tr` itself
  # "command not found" and silently emptied the role right back out.
  # `shopt -s nocasematch`, set once near the top of this script, makes
  # every `case`/`[[ ]]` match below (this prefix strip, and
  # `_role_write_is_restricted`'s deny-list check) case-insensitive
  # instead, so the raw, un-lowered value can be compared directly.
  #
  # NOT `${_ROLE_WRITE_FALLBACK_ROLE#crew:}`. `nocasematch` governs `case`
  # and `[[ ]]` pattern matching only -- it does NOT extend to `#`/`%`
  # parameter-expansion pattern removal, which stays case-sensitive
  # regardless. So `case "CREW:PM" in crew:*)` matched (nocasematch), but
  # `${role#crew:}` on that same value found no case-sensitive `crew:`
  # prefix and left the string untouched -- `_ROLE_WRITE_FALLBACK_ROLE`
  # stayed `"CREW:PM"`, which `_role_write_is_restricted` (an exact
  # `pm`/`explorer`/... match) then read as an unrecognised, unrestricted
  # role and the write was ALLOWED. Fixed 2026-09-24: since the `case`
  # above already proved (case-insensitively) that the first 5 characters
  # spell `crew:`, a fixed-length substring removes exactly those 5
  # characters regardless of their case -- no second case-sensitive match
  # is involved. Pure bash 3.2-compatible substring expansion (`${var:N}`),
  # no `${var,,}`, no `tr`.
  case "$_ROLE_WRITE_FALLBACK_ROLE" in
    crew:*) _ROLE_WRITE_FALLBACK_ROLE="${_ROLE_WRITE_FALLBACK_ROLE:5}" ;;
  esac
}

# THE NO-PYTHON CONTRACT (PM decision, superseding an earlier fallback that
# parsed `guards.roleWrites` and pm's path allowances without python at
# all -- removed here along with `_role_write_layer_policy`,
# `_role_write_effective_policy`, `_role_write_pm_path_allowed` and
# `_role_write_fallback_file_path`, none of which survive this rewrite).
#
# That policy-honouring fallback carried its own defects (F1 review): a
# dangling config symlink read as absent rather than corrupt; the lexical
# `pm`-scope check accepted `..` traversal and symlink escapes; the
# grep-based policy reader accepted truncated/corrupt JSON as a clean
# "off"; and it read the CURRENT PROCESS's cwd rather than the hook
# payload's own `cwd`, so a policy read could come from the wrong repo
# entirely. Removing the class is simpler than re-fixing each one: without
# python, this hook cannot actually EVALUATE `guards.roleWrites` (off,
# report, or pm's own allowed patterns) at all -- role_write_guard.py is
# the only thing that reads that policy correctly -- so it no longer
# pretends to. It only tells a restricted role from an unrestricted one
# (the deny-list mirror above, `_role_write_is_restricted`, is a floor
# that needs no config to apply) and fails CLOSED on the restricted side,
# or on any role it cannot read at all. `off`/`report`/pm's allowances
# need python; without it, a restricted role's write is always blocked.
# See `plugin/crew/CONFIG.md`, next to `guards.roleWrites`.
#
# `$1` is the raw JSON payload; `$2` is why this fallback is being
# consulted at all, for the stderr message.
_role_write_fallback_decision() {
  local input="$1" why="$2" role
  # NOT `role=$(_role_write_fallback_role "$input")` -- see that function's
  # own comment: calling it through command substitution would run it in a
  # subshell and silently discard `_ROLE_WRITE_FALLBACK_DETERMINED`.
  _role_write_fallback_role "$input"
  role="$_ROLE_WRITE_FALLBACK_ROLE"

  if [ "$_ROLE_WRITE_FALLBACK_DETERMINED" != "1" ]; then
    echo "role-write-guard: $why; the hook payload names an agent_type this fallback could not read a value out of - install python so guards.roleWrites can be evaluated, or the write is blocked." >&2
    exit 2
  fi

  if ! _role_write_is_restricted "$role"; then
    echo "role-write-guard: $why; allowing it unjudged (role '$role' is not restricted)." >&2
    exit 0
  fi

  echo "role-write-guard: $why - python is unavailable, so guards.roleWrites (off/report/allowances) cannot be evaluated for restricted role '$role' - install python, or the write is blocked." >&2
  exit 2
}

PY=$(_resolve_role_write_python) || {
  # No candidate resolved at all -- a DIFFERENT failure than the
  # launch-failure fallback further down (a candidate that resolved, was
  # proven executable, and then still failed to launch
  # role_write_guard.py).
  _role_write_fallback_decision "$INPUT" "no usable python found"
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
  _role_write_fallback_decision "$INPUT" "could not launch the python interpreter ($PY) to judge this write (exit $status)"
fi

exit "$status"
