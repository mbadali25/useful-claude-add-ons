#!/usr/bin/env bash
# SessionStart hook. Thin wrapper - the logic lives in bridge_status.py so the
# bash and PowerShell paths cannot drift.
#
# This hook cannot block: SessionStart has no exit code that stops anything
# the way PostToolUse's exit 2 does, so there is no fail-open/fail-closed
# choice to make here - only a loud/silent one. Until 2026-09-22 the resolver
# was `command -v python3 || command -v python || command -v py`, which
# answers "is there a FILE named python on PATH", not "is there a working
# interpreter". On Windows a WindowsApps App Execution Alias is a real,
# executable file, so `command -v python3` resolves it and the old resolver
# would have exec'd the Store stub instead of standing down - the same defect
# vault-guard.sh carried before it was fixed (see that file's header for the
# reproduction). Adopted here so the status line either comes from a real
# interpreter or the session says on stderr that it did not run, never
# silently.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Near-copy of vault-guard.sh's `_vault_guard_resolve_python`. Copied, not
# shared, for the same reason recorded there: crew and obsidian-vault install
# independently, and each wrapper's stand-down message needs to name itself.
BRIDGE_STATUS_PY=""
BRIDGE_STATUS_REJECTED=""

_bridge_status_reject() {
  BRIDGE_STATUS_REJECTED="${BRIDGE_STATUS_REJECTED}${BRIDGE_STATUS_REJECTED:+; }$1"
}

_bridge_status_resolve_python() {
  BRIDGE_STATUS_PY=""
  BRIDGE_STATUS_REJECTED=""
  for name in python3 python py; do
    # EVERY PATH match of the name, not only the first (`type -aP`, not
    # `command -v`), and each is executed before it is believed: where it
    # lives never decides. A WindowsApps alias is tried like anything else.
    # crew 1.0's Windows burn-in: a path rule plus first-match-per-name
    # discarded three WORKING aliases and never reached the real python.exe
    # behind them. bridge-status.ps1 walks the same order, so both flavours agree.
    while IFS= read -r candidate; do
      [ -n "$candidate" ] || continue
      # Running the candidate and reading back a token this script chose is
      # what tells a real interpreter from something wearing the name: only
      # a python that parsed and ran the -c program can emit the prefix. A
      # zero exit with other output (a wrapper that prints a line) fails it.
      probe=$("$candidate" -c 'import sys; sys.stdout.write("bridge-status-python:" + sys.executable)' 2>/dev/null) || {
        _bridge_status_reject "$candidate (ran, but exited nonzero instead of answering the interpreter probe)"
        continue; }
      case "$probe" in
        bridge-status-python:*) real="${probe#bridge-status-python:}" ;;
        *)
          _bridge_status_reject "$candidate (ran, but did not answer the interpreter probe)"
          continue ;;
      esac
      # An embedded or frozen interpreter can report an empty sys.executable.
      # It answered honestly, and the answer is still unusable here.
      [ -n "$real" ] || {
        _bridge_status_reject "$candidate (answered the probe with an empty sys.executable)"
        continue; }
      # `sys.executable`, not `$candidate`: the PATH-found name may be a shim
      # that re-execs elsewhere, and the probe already paid the cost of asking
      # python where it actually lives.
      BRIDGE_STATUS_PY="$real"
      return 0
    done < <(type -aP "$name" 2>/dev/null)
  done
  return 1
}

if ! _bridge_status_resolve_python; then
  if [ -n "$BRIDGE_STATUS_REJECTED" ]; then
    echo "obsidian-vault bridge-status.sh: python was found on PATH but no candidate is a usable interpreter [$BRIDGE_STATUS_REJECTED] - bridge status cannot run this session (SessionStart has no blocking exit; this is not a failure, just not silent)." >&2
  else
    echo "obsidian-vault bridge-status.sh: no python3/python/py interpreter found on PATH - bridge status cannot run this session." >&2
  fi
  exit 0
fi

exec "$BRIDGE_STATUS_PY" "$DIR/bridge_status.py"
