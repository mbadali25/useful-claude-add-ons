# shellcheck shell=bash
# Sourced by the vpn shims: find a python that actually RUNS and hand it tsadmin.py.
# Every PATH match of python3/python/py is tried, not the first per name: a Windows
# WindowsApps python3 stub can sit ahead of a real interpreter and fail on launch.

vpn_python() {
  local cand
  while IFS= read -r cand; do
    [ -n "$cand" ] || continue
    if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1 </dev/null; then
      printf '%s\n' "$cand"
      return 0
    fi
  done < <(type -ap python3 python py 2>/dev/null)
  return 1
}

vpn_run() {
  local here py
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if ! py="$(vpn_python)"; then
    echo "ai-connect vpn: no working Python 3.8+ found on PATH (tried python3, python, py)" >&2
    exit 1
  fi
  exec "$py" "$here/tsadmin.py" "$@"
}
