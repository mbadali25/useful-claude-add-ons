#!/usr/bin/env bash
# SessionEnd / PreCompact hook. Thin wrapper - the logic lives in
# vault_capture.py so the bash and PowerShell paths cannot drift.
#
# This hook cannot block: neither SessionEnd nor PreCompact has an exit code
# that stops anything the way PostToolUse's exit 2 does, so there is no
# fail-open/fail-closed choice here - only a loud/silent one. Until
# 2026-09-22 the resolver was `command -v python3 || command -v python ||
# command -v py`, which answers "is there a FILE named python on PATH", not
# "is there a working interpreter" - a WindowsApps App Execution Alias
# resolves cleanly to that and is not one. See vault-guard.sh's header for
# the reproduction of the same defect on the guard that CAN block. Adopted
# here so a capture is either written by a real interpreter or the session
# says on stderr that it was skipped, never silently.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Near-copy of vault-guard.sh's `_vault_guard_resolve_python`. Copied, not
# shared, for the same reason recorded there: crew and obsidian-vault install
# independently, and each wrapper's stand-down message needs to name itself.
VAULT_CAPTURE_PY=""
VAULT_CAPTURE_REJECTED=""

_vault_capture_reject() {
  VAULT_CAPTURE_REJECTED="${VAULT_CAPTURE_REJECTED}${VAULT_CAPTURE_REJECTED:+; }$1"
}

_vault_capture_resolve_python() {
  # NOT memoized. This hook has one call site (`if ! _vault_capture_resolve_python`
  # below), so a cache here would never see a second call to save -- an
  # earlier version carried one anyway, copied from crew's own (there,
  # actually dead: every crew call site invokes its resolver through a
  # `$(...)` subshell, which discards whatever the cache set). Removed here
  # too rather than kept as inert weight.
  VAULT_CAPTURE_PY=""
  VAULT_CAPTURE_REJECTED=""
  # An OVERALL deadline on top of each candidate's own 3s probe bound: a
  # PATH with several hung candidates would otherwise cost 3s EACH, adding
  # up past this hook's own timeout even though every individual probe is
  # bounded. Kept well inside the shortest hook timeout that resolves
  # python this way (bridge-status.ps1's twin, 10s).
  local _vault_capture_deadline=$((SECONDS + 8))
  local _vault_capture_remaining _vault_capture_probe_timeout
  for name in python3 python py; do
    # EVERY PATH match of the name, not only the first (`type -aP`, not
    # `command -v`), and each is executed before it is believed: where it
    # lives never decides. A WindowsApps alias is tried like anything else.
    # crew 1.0's Windows burn-in: a path rule plus first-match-per-name
    # discarded three WORKING aliases and never reached the real python.exe
    # behind them. vault-capture.ps1 walks the same order, so both flavours agree.
    while IFS= read -r candidate; do
      [ -n "$candidate" ] || continue
      # The remaining budget, not a flat 3s, bounds THIS candidate's probe: a
      # fixed 3s watchdog checked only before launch can still overrun the
      # deadline by up to 3s once entered, which on a run of several
      # near-8s-but-under candidates followed by one hung one can overrun
      # both this deadline and the 10s hook timeout it exists to stay inside.
      _vault_capture_remaining=$((_vault_capture_deadline - SECONDS))
      if [ "$_vault_capture_remaining" -le 0 ]; then
        _vault_capture_reject "PATH walk stopped: the overall resolver deadline was reached before every candidate could be probed"
        break 2
      fi
      _vault_capture_probe_timeout=$_vault_capture_remaining
      [ "$_vault_capture_probe_timeout" -le 3 ] || _vault_capture_probe_timeout=3
      # Running the candidate and reading back a token this script chose is
      # what tells a real interpreter from something wearing the name: only
      # a python that parsed and ran the -c program can emit the prefix. A
      # zero exit with other output (a wrapper that prints a line) fails it.
      # The answer is `<prefix><major>:<minor>:<implementation>:<executable>`
      # and all four are checked below: Python 3.8 or later, CPython or PyPy,
      # and an executable that exists -- the same proof crew's
      # Resolve-CrewPython demands. Python 2 has no sys.implementation, so it
      # exits nonzero here rather than answering.
      #
      # BOUNDED at 3s, process tree included, by the same watchdog crew's
      # `crew_py_strict` uses (`timeout` is absent on Git Bash): a candidate
      # that never exits would otherwise stall this hook forever, and a
      # launcher's child holding stdout would hang the `$()` after the
      # launcher itself died. `set -m` gives the candidate its own process
      # group for the kill; under MSYS `taskkill /T` takes the native tree
      # (MODELLED, not observed on Windows). No `sleep` means no watchdog.
      probe=$(
        set -m
        "$candidate" -c 'import sys; v = sys.version_info; sys.stdout.write("vault-capture-python:" + "%d:%d:%s:" % (v[0], v[1], sys.implementation.name) + sys.executable)' </dev/null 2>/dev/null &
        pid=$!
        (
          sleep "$_vault_capture_probe_timeout" 2>/dev/null || exit 0
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
      ) || {
        _vault_capture_reject "$candidate (ran, but exited nonzero or did not finish within 3s instead of answering the interpreter probe)"
        continue; }
      case "$probe" in
        vault-capture-python:*) answer="${probe#vault-capture-python:}" ;;
        *)
          _vault_capture_reject "$candidate (ran, but did not answer the interpreter probe)"
          continue ;;
      esac
      major="${answer%%:*}"; answer="${answer#*:}"
      minor="${answer%%:*}"; answer="${answer#*:}"
      impl="${answer%%:*}"; real="${answer#*:}"
      real=${real%$'\r'}
      case "$major:$minor" in
        *[!0-9:]*|:*|*:)
          _vault_capture_reject "$candidate (answered the probe without a version, implementation and executable)"
          continue ;;
      esac
      if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 8 ]; }; then
        _vault_capture_reject "$candidate (answered the probe as Python $major.$minor; 3.8 or later is required)"
        continue
      fi
      case "$impl" in
        cpython|pypy) ;;
        *)
          _vault_capture_reject "$candidate (answered the probe as implementation '$impl', not cpython or pypy)"
          continue ;;
      esac
      # An embedded or frozen interpreter can report an empty sys.executable.
      # It answered honestly, and the answer is still unusable here.
      [ -n "$real" ] || {
        _vault_capture_reject "$candidate (answered the probe with an empty sys.executable)"
        continue; }
      # A native Windows sys.executable (C:\...) is normalised to a path this
      # shell can stat -- `cygpath -u` when present, else the same /c/...
      # shape by hand -- exactly as crew's `crew_py_strict` does.
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
      [ -x "$real" ] || {
        _vault_capture_reject "$candidate (answered the probe with a sys.executable that does not exist: $real)"
        continue; }
      # `sys.executable`, not `$candidate`: the PATH-found name may be a shim
      # that re-execs elsewhere, and the probe already paid the cost of asking
      # python where it actually lives.
      VAULT_CAPTURE_PY="$real"
      return 0
    done < <(type -aP "$name" 2>/dev/null)
  done
  return 1
}

if ! _vault_capture_resolve_python; then
  if [ -n "$VAULT_CAPTURE_REJECTED" ]; then
    echo "obsidian-vault vault-capture.sh: python was found on PATH but no candidate is a usable interpreter [$VAULT_CAPTURE_REJECTED] - session capture skipped (not a failure, just not silent)." >&2
  else
    echo "obsidian-vault vault-capture.sh: no python3/python/py interpreter found on PATH - session capture skipped." >&2
  fi
  exit 0
fi

exec "$VAULT_CAPTURE_PY" "$DIR/vault_capture.py" "$1"
