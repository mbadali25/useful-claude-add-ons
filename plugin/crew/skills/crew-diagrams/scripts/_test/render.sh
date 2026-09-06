#!/usr/bin/env bash
# Regression test for render.sh's puppeteer-config path.
#
# render.sh writes its puppeteer config with mktemp, which on Git Bash/MSYS
# gives a POSIX /tmp path. mmdc is a Windows Node program there and cannot
# resolve it, but only when MSYS_NO_PATHCONV=1 is set in the caller's
# environment - MSYS otherwise rewrites the argument for us, which is why the
# bug went unnoticed until a caller with that variable set (a common workaround
# for MSYS mangling *other* arguments) hit it. The failure was never loud: mmdc
# exits 1 and prints "Configuration file ... doesn't exist" to stderr, but
# render.sh still creates the output directory and prints a summary line, so a
# check that only looks at the exit code or the directory's existence would
# have passed the broken script. Every case below asserts on the actual output
# file's byte size instead.
#
# Needs: bash, mmdc (npm install -g @mermaid-js/mermaid-cli). Skips, not fails,
# if mmdc is not on PATH - it is an optional tool for this skill, same as
# render.sh's own check.
#     ./plugin/crew/skills/crew-diagrams/scripts/_test/render.sh
# Exit status is 0 when every case passes, 1 otherwise.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDER="$HERE/../render.sh"
PASS=0
FAIL=0
red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

[ -f "$RENDER" ] || { echo "FAIL: cannot find render.sh at $RENDER"; exit 1; }
command -v mmdc >/dev/null 2>&1 || { echo "SKIP: mmdc is not on PATH"; exit 0; }

# A relative dir under $HERE, not an absolute /tmp (or /c/...) path: real
# callers pass render.sh a relative dir like "docs/diagrams", so -i/-o only
# ever need to resolve a relative path. The bug is specifically about the
# absolute /tmp path render.sh's own mktemp gives its puppeteer config - an
# absolute fixture dir would make -i and -o fail the same way under
# MSYS_NO_PATHCONV=1 and mask which argument the fix actually has to cover.
cd "$HERE"
TMP="$(mktemp -d -p .)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/diagrams"
cat > "$TMP/diagrams/smoke.mmd" <<'EOF'
graph TD
  A[Start] --> B[End]
EOF

nonzero_svg() {
  # $1 label. Renders into a fresh out/ each time so a stale file from a
  # previous case can't make a broken run look like it produced something.
  local label="$1"; shift
  rm -rf "$TMP/diagrams/out"
  local out
  out="$("$@" bash "$RENDER" "$TMP/diagrams" --svg-only --force 2>&1)"
  local status=$?
  local dst="$TMP/diagrams/out/smoke.svg"
  local size=0
  [ -f "$dst" ] && size="$(wc -c < "$dst" | tr -d ' ')"
  if [ "$status" -eq 0 ] && [ "$size" -gt 0 ]; then
    green "  PASS  $label (exit 0, ${size} bytes)"; PASS=$((PASS+1))
  else
    red "  FAIL  $label (exit $status, ${size} bytes)"
    printf '%s\n' "$out" | sed 's/^/        /'
    FAIL=$((FAIL+1))
  fi
}

echo "1. plain invocation renders a non-empty SVG"
nonzero_svg "no env override" env

echo "2. MSYS_NO_PATHCONV=1 - the setting that turned off MSYS's automatic"
echo "   /tmp rewrite and made mmdc fail on this repo on 2026-09-05"
nonzero_svg "MSYS_NO_PATHCONV=1" env MSYS_NO_PATHCONV=1

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1
