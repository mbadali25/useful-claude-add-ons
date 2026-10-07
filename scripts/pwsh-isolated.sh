#!/bin/sh
# pwsh-isolated.sh - start pwsh on a private, throwaway startup-profile cache (T-0506).
#
#   sh scripts/pwsh-isolated.sh <pwsh arguments>
#
# PowerShell keeps its startup profile under $XDG_CACHE_HOME/powershell on
# Linux and macOS. Two pwsh processes writing it at once can corrupt it, and
# a corrupt profile makes every later pwsh die ("Stack overflow.", SIGABRT)
# until the file is removed (L-0557, CHANGELOG). Every pwsh this repo's own
# gate scripts start goes through here, so none of them shares that file.
#
# 1. pwsh: $PWSH when set and non-empty, else pwsh, pwsh.exe, then the four
#    known Windows install paths. None runnable: TOOL MISSING, exit 77.
# 2. XDG_CACHE_HOME is ASSIGNED a path inside a fresh mktemp -d directory
#    (an ambient value is the shared one). No directory: TOOL BROKEN, exit 1,
#    pwsh is not started on the shared cache.
# 3. pwsh runs with the arguments exactly as given and stdin from /dev/null
#    (callers loop over `while read`, whose input pwsh must not consume).
# 4. TERM, INT or HUP to this script ends the pwsh child too (with TERM:
#    a background child of sh ignores INT): `timeout` signals only its
#    direct child, which is this script. That death gets a TOOL BROKEN line.
# 5. The directory is removed on every exit path, and the exit status is
#    pwsh's own. No retry, ever.
# 6. A status of 128 or more adds one `TOOL BROKEN: pwsh` line to stderr
#    (the tool died; a .ps1 did not fail its check). The status is unchanged.
#
# Windows: the variable is set and changes nothing there; Windows pwsh keeps
# the profile under LOCALAPPDATA. Not verified under Git Bash.

resolve_pwsh() {
  if [ -n "${PWSH:-}" ]; then
    # A path must be an executable file (command -v accepts any existing
    # path); a bare name is looked up on PATH.
    case "$PWSH" in
      */*) if [ -f "$PWSH" ] && [ -x "$PWSH" ]; then printf '%s\n' "$PWSH"; return 0; fi
           return 1 ;;
    esac
    command -v "$PWSH" 2>/dev/null && return 0
    return 1
  fi
  for c in pwsh pwsh.exe; do
    command -v "$c" 2>/dev/null && return 0
  done
  for c in "/c/Program Files/PowerShell/7/pwsh" \
           "/c/Program Files/PowerShell/7/pwsh.exe" \
           "/mnt/c/Program Files/PowerShell/7/pwsh.exe" \
           "/mnt/c/Program Files/PowerShell/7/pwsh"; do
    if [ -x "$c" ]; then printf '%s\n' "$c"; return 0; fi
  done
  return 1
}

if ! exe=$(resolve_pwsh); then
  echo "TOOL MISSING: pwsh (PowerShell 7) not found${PWSH:+ - PWSH=$PWSH is not runnable}; install it or set PWSH" >&2
  exit 77
fi

if ! dir=$(mktemp -d "${TMPDIR:-/tmp}/pwsh-isolated.XXXXXX" 2>/dev/null) || [ ! -d "$dir" ]; then
  echo "TOOL BROKEN: pwsh not started - could not create a private cache directory under ${TMPDIR:-/tmp}" >&2
  exit 1
fi
XDG_CACHE_HOME="$dir/xdg-cache"
export XDG_CACHE_HOME

child=""
cleanup() { rm -rf "$dir"; }
# shellcheck disable=SC2329  # invoked from the traps below
# The child gets TERM whatever arrived: a background job of a non-interactive
# shell starts with INT ignored, so a forwarded INT would not end it.
forward() {
  sig=$1
  if [ -n "$child" ]; then
    kill -TERM "$child" 2>/dev/null
    wait "$child" 2>/dev/null
    crc=$?
    if [ "$crc" -ge 128 ]; then
      echo "TOOL BROKEN: pwsh exited ${crc} (signal $((crc - 128))) after this launcher got SIG${sig} and ended it - no .ps1 check result" >&2
    fi
  fi
  cleanup
  trap - "$sig"
  kill "-$sig" "$$"
}
trap 'forward TERM' TERM
trap 'forward INT' INT
trap 'forward HUP' HUP

"$exe" "$@" </dev/null &
child=$!
wait "$child"
rc=$?
cleanup
if [ "$rc" -ge 128 ]; then
  echo "TOOL BROKEN: pwsh exited ${rc} (signal $((rc - 128))) on a private empty startup-profile cache, so the shared profile is ruled out - the tool died; no .ps1 check result" >&2
fi
exit "$rc"
