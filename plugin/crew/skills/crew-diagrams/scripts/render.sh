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
# mmdc is a Windows Node program on Git Bash/MSYS; it cannot resolve the POSIX
# /tmp path mktemp gives us there. MSYS usually rewrites that argument for us,
# but a caller with MSYS_NO_PATHCONV=1 set (common to avoid it mangling other
# args) turns that rewrite off, and mmdc then fails with the config "file"
# missing while still creating $OUT and printing a summary line. Resolve the
# path ourselves when cygpath exists; where it doesn't (Linux/macOS, or plain
# Windows without Git tools), $PCFG is already usable as-is.
PCFG_ARG="$PCFG"
if command -v cygpath >/dev/null 2>&1; then
  CONVERTED="$(cygpath -w "$PCFG" 2>/dev/null)"
  [ -n "$CONVERTED" ] && PCFG_ARG="$CONVERTED"
fi

render_one() { # render_one <src> <ext> <bg>
  local src="$1" ext="$2" bg="$3"
  local name; name="$(basename "$src" .mmd)"
  local dst="$OUT/$name.$ext"
  if [ "$FORCE" -eq 0 ] && [ -f "$dst" ] && [ "$dst" -nt "$src" ]; then
    echo "skip  $name.$ext (unchanged)"; return 0
  fi
  if mmdc -i "$src" -o "$dst" -b "$bg" -s 2 -p "$PCFG_ARG" >/dev/null 2>&1; then
    echo "ok    $name.$ext"
  else
    echo "FAIL  $name.$ext" >&2
    mmdc -i "$src" -o "$dst" -b "$bg" -p "$PCFG_ARG" 2>&1 | tail -5 >&2
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
