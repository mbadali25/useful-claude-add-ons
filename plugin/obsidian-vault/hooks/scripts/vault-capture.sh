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
  VAULT_CAPTURE_PY=""
  VAULT_CAPTURE_REJECTED=""
  for name in python3 python py; do
    # `command -v` takes only the FIRST match for a name and then moves to
    # the NEXT NAME - it never searches the same name further down PATH.
    candidate=$(command -v "$name" 2>/dev/null) || continue
    # NOT a blanket "reject anything under a WindowsApps path" - a genuine
    # Microsoft Store Python install reports its real interpreter under
    # exactly that path
    # (.../WindowsApps/PythonSoftwareFoundation.Python.3.x_<hash>/python.exe),
    # so a path-substring reject throws out a working interpreter along with
    # the stub. Reported 2026-09-24 against vault-guard.sh's identical check
    # (see its own comment); fixed here in parallel. Running the candidate and
    # reading back a token this script chose is what actually tells a real
    # interpreter from something wearing the name - the WindowsApps alias
    # resolves cleanly as a file but fails the probe below (nonzero exit or no
    # token), which is proof enough without knowing WHERE it lives.
    probe=$("$candidate" -c 'import sys; sys.stdout.write("vault-capture-python:" + sys.executable)' 2>/dev/null) || {
      _vault_capture_reject "$candidate (ran, but exited nonzero instead of answering the interpreter probe)"
      continue; }
    case "$probe" in
      vault-capture-python:*) real="${probe#vault-capture-python:}" ;;
      *)
        _vault_capture_reject "$candidate (ran, but did not answer the interpreter probe)"
        continue ;;
    esac
    # An embedded or frozen interpreter can report an empty sys.executable.
    # It answered honestly, and the answer is still unusable here.
    [ -n "$real" ] || {
      _vault_capture_reject "$candidate (answered the probe with an empty sys.executable)"
      continue; }
    # No post-execution WindowsApps check either, for the same reason: a real
    # Store-installed interpreter's OWN sys.executable lives under that path
    # too. The launch itself is already the proof that matters here.
    # `sys.executable`, not `$candidate`: the PATH-found name may be a shim
    # that re-execs elsewhere, and the probe already paid the cost of asking
    # python where it actually lives.
    VAULT_CAPTURE_PY="$real"
    return 0
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
