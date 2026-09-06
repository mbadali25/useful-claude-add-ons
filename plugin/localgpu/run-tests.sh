#!/usr/bin/env bash
# Run the localgpu test suites with the interpreter the bootstrap built.
#
# Both suites go into ONE pytest invocation on purpose. mcp/_test and cli/_test
# are each outside any package, so a conftest.py in either imports as the same
# top-level module name and silently shadows the other's fixtures. That only
# shows up when the two are collected together - running them one at a time
# hides exactly the regression this script exists to catch. --mcp and --cli are
# for narrowing a red run, not for the run that decides whether it is green.
#
# Matched pair with run-tests.ps1: same steps, same order, same flags.
#
# Usage:
#   ./run-tests.sh [--mcp | --cli] [--] [extra pytest args]
#
#   --mcp     only mcp/_test (narrowing; skips the conftest-collision check)
#   --cli     only cli/_test (same caveat)
#   -h, --help
#
# The interpreter is $LOCALGPU_HOME/venv, where LOCALGPU_HOME defaults to
# %LOCALAPPDATA%\localgpu on Windows and ~/.local/share/localgpu elsewhere.
# The system python is not enough: the mcp suite needs numpy.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

die() {
  printf '%s\n' "$@" >&2
  exit 1
}

usage() {
  # The header comment, minus the shebang, up to the first line of code.
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
}

SUITE="both"
PYTEST_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --mcp) [ "$SUITE" = "cli" ] && SUITE="both-flags" || SUITE="mcp"; shift ;;
    --cli) [ "$SUITE" = "mcp" ] && SUITE="both-flags" || SUITE="cli"; shift ;;
    --) shift; PYTEST_ARGS+=("$@"); break ;;
    *) PYTEST_ARGS+=("$1"); shift ;;
  esac
done

if [ "$SUITE" = "both-flags" ]; then
  die "--mcp and --cli are mutually exclusive." \
      "Pass neither to run both suites together, which is the run that counts."
fi

# --- Interpreter --------------------------------------------------------------
# A venv built by a POSIX python puts its interpreter in bin/; one built by a
# Windows python that happens to be on a Git Bash PATH puts it in Scripts/.
# Resolve rather than assume - the same order bootstrap.sh uses.
venv_python_in() {
  local venv="$1"
  if [ -x "$venv/bin/python" ]; then printf '%s' "$venv/bin/python"; return 0; fi
  if [ -x "$venv/Scripts/python.exe" ]; then printf '%s' "$venv/Scripts/python.exe"; return 0; fi
  return 1
}

CANDIDATES=()
if [ -n "${LOCALGPU_HOME:-}" ]; then
  CANDIDATES+=("$LOCALGPU_HOME")
else
  # Git Bash on Windows has both LOCALAPPDATA and a HOME, and the bootstrap
  # that ran there was the .ps1, which installs under LOCALAPPDATA.
  [ -n "${LOCALAPPDATA:-}" ] && CANDIDATES+=("$LOCALAPPDATA/localgpu")
  CANDIDATES+=("$HOME/.local/share/localgpu")
fi

PY=""
for home in "${CANDIDATES[@]}"; do
  if PY="$(venv_python_in "$home/venv")"; then
    LOCALGPU_HOME_USED="$home"
    break
  fi
  PY=""
done

if [ -z "$PY" ]; then
  die "run-tests: no localgpu venv found. Looked in:" \
      "$(printf '  %s/venv\n' "${CANDIDATES[@]}")" \
      "" \
      "Build it with the bootstrap:" \
      "  $SCRIPT_DIR/bootstrap.sh" \
      "or on Windows:" \
      "  pwsh -NoProfile -File $SCRIPT_DIR/bootstrap.ps1" \
      "" \
      "Set LOCALGPU_HOME to point at an install somewhere else."
fi

# --- Suites -------------------------------------------------------------------
case "$SUITE" in
  mcp) TARGETS=("mcp/_test") ;;
  cli) TARGETS=("cli/_test") ;;
  *)   TARGETS=("mcp/_test" "cli/_test") ;;
esac

if [ "$SUITE" != "both" ]; then
  printf '%s\n' "run-tests: only $SUITE/_test - this run cannot catch a conftest collision." >&2
fi

printf '%s\n' "run-tests: $PY" "run-tests: install root $LOCALGPU_HOME_USED"

cd "$SCRIPT_DIR"
exec "$PY" -m pytest "${TARGETS[@]}" ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}
