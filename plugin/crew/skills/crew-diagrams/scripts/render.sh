#!/usr/bin/env bash
# Render every .mmd under a directory to PNG + SVG. Skips unchanged sources.
# Usage: render.sh [dir] [--force] [--png-only|--svg-only]
set -uo pipefail
DIR="${1:-docs/diagrams}"; shift 2>/dev/null || true
FORCE=0; WANT_PNG=1; WANT_SVG=1
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    --png-only) WANT_SVG=0 ;;
    --svg-only) WANT_PNG=0 ;;
  esac
done

if ! command -v mmdc >/dev/null 2>&1; then
  echo "mmdc not found. Install with: npm install -g @mermaid-js/mermaid-cli" >&2
  exit 1
fi

OUT="$DIR/out"; mkdir -p "$OUT"
# Headless Chromium needs --no-sandbox in containers and most CI runners.
PCFG="$(mktemp -t puppeteer-XXXX.json)"
printf '{"args":["--no-sandbox","--disable-dev-shm-usage"]}' > "$PCFG"
trap 'rm -f "$PCFG"' EXIT

render_one() { # render_one <src> <ext> <bg>
  local src="$1" ext="$2" bg="$3"
  local name; name="$(basename "$src" .mmd)"
  local dst="$OUT/$name.$ext"
  if [ "$FORCE" -eq 0 ] && [ -f "$dst" ] && [ "$dst" -nt "$src" ]; then
    echo "skip  $name.$ext (unchanged)"; return 0
  fi
  if mmdc -i "$src" -o "$dst" -b "$bg" -s 2 -p "$PCFG" >/dev/null 2>&1; then
    echo "ok    $name.$ext"
  else
    echo "FAIL  $name.$ext" >&2
    mmdc -i "$src" -o "$dst" -b "$bg" -p "$PCFG" 2>&1 | tail -5 >&2
    return 1
  fi
}

FAILED=0
shopt -s nullglob
FILES=("$DIR"/*.mmd)
if [ ${#FILES[@]} -eq 0 ]; then echo "no .mmd files in $DIR"; exit 0; fi
for src in "${FILES[@]}"; do
  [ "$WANT_SVG" -eq 1 ] && { render_one "$src" svg transparent || FAILED=1; }
  [ "$WANT_PNG" -eq 1 ] && { render_one "$src" png white || FAILED=1; }
done
echo "output: $OUT"
exit $FAILED
