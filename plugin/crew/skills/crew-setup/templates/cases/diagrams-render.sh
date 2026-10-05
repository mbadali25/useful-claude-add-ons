#!/usr/bin/env bash
# _verify/cases/diagrams-render.sh - every Mermaid source renders (crew T-0502).
# readonly: yes
#
# crew-setup copies this into _verify/cases/ only in a repo that has .mmd
# files. It renders each source in $DIAGRAMS_DIR (default docs/diagrams) to a
# temp directory, never next to the sources, and always passes puppeteer
# --no-sandbox: headless Chromium refuses to start as root, which is how CI
# containers run, so a bare `mmdc` call fails there. Same config as crew's
# own render.sh. Calls nothing in the plugin (CLAUDE_PLUGIN_ROOT is not set in
# CI or under the gate).
#
# Exit 0 every source rendered; 1 one did not (its last 5 mmdc lines are
# printed under its FAIL line) or there is nothing to render; 77 mmdc is not
# installed (SKIP: a missing tool, not a failed check). --env is accepted and
# ignored: rendering does not depend on the environment.
set -uo pipefail

while [ $# -gt 0 ]; do
  case "$1" in
    --env) [ $# -ge 2 ] || { echo "FAIL --env needs a value"; exit 1; }; shift 2 ;;
    *) shift ;;
  esac
done

DIR="${DIAGRAMS_DIR:-docs/diagrams}"

if ! command -v mmdc >/dev/null 2>&1; then
  echo "SKIP diagrams-render: mmdc not found - install it with: npm install -g @mermaid-js/mermaid-cli" >&2
  exit 77
fi

shopt -s nullglob
SRCS=("$DIR"/*.mmd)
if [ ${#SRCS[@]} -eq 0 ]; then
  echo "FAIL no .mmd files in $DIR"
  exit 1
fi

WORK="$(mktemp -d)" || { echo "FAIL cannot create a temp directory"; exit 1; }
trap 'rm -rf "$WORK"' EXIT
PCFG="$WORK/puppeteer.json"
printf '{"args":["--no-sandbox","--disable-dev-shm-usage"]}' > "$PCFG"
# mmdc is a Windows Node program under Git Bash: it cannot open a POSIX temp
# path when MSYS_NO_PATHCONV=1 turns MSYS's own rewrite off.
winpath() {
  local p="$1" w
  if command -v cygpath >/dev/null 2>&1; then
    w="$(cygpath -w "$p" 2>/dev/null)" && [ -n "$w" ] && p="$w"
  fi
  printf '%s\n' "$p"
}
PCFG_ARG="$(winpath "$PCFG")"

# PASS lines as it goes; every FAIL block after the count line, so a runner
# that keeps only the last lines of the output still shows a failure's cause.
PASS=0; FAIL=0; FAILS="$WORK/failures"
: > "$FAILS"
for src in "${SRCS[@]}"; do
  name="$(basename "$src" .mmd)"
  out="$WORK/$name.svg"
  # One render; its own output is what a failure shows.
  log="$(mmdc -i "$(winpath "$src")" -o "$(winpath "$out")" -p "$PCFG_ARG" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ] && [ -s "$out" ]; then
    echo "PASS $name"; PASS=$((PASS+1))
  else
    {
      if [ "$rc" -eq 0 ]; then
        echo "FAIL $name (mmdc exited 0 and wrote nothing)"
      else
        echo "FAIL $name (mmdc exit $rc)"
      fi
      [ -z "$log" ] || printf '%s\n' "$log" | tail -n 5 | sed 's/^/    /'
    } >> "$FAILS"
    FAIL=$((FAIL+1))
  fi
done

echo "diagrams-render: $PASS passed, $FAIL failed in $DIR"
cat "$FAILS"
[ "$FAIL" -eq 0 ] || exit 1
