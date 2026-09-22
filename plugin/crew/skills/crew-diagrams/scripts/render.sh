#!/usr/bin/env bash
# Render every .mmd under a directory to PNG + SVG. Skips unchanged sources.
# Usage: render.sh [dir] [--force] [--png-only|--svg-only]
set -uo pipefail

usage() {
  echo "usage: render.sh [dir] [--force] [--png-only|--svg-only]" >&2
}

# Flags and the directory are parsed position-independently: `--force` may
# come before or after the dir, so "render.sh --force" (no dir at all) does
# not get read as DIR="--force" and go on to run `mkdir -p "$OUT"` against a
# directory literally named "--force", which used to fail, find no .mmd
# files in a directory called "--force", and exit 0 on that empty-glob path
# -- silently doing nothing while reporting success. Any leading-dash token
# that isn't one of the three known flags is now a hard, loud error instead
# of being silently ignored -- including a single-dash token like "-x",
# which the old `--*)` pattern let fall through to being read as the
# directory. "--" ends option parsing, so a directory whose own name starts
# with a dash can be named at all; DIR is then normalized below with a "./"
# prefix so that name is also safe to hand to mkdir/rm/mmdc, none of which
# would otherwise treat a leading "-" as the start of their own directory
# argument rather than an option.
DIR=""
FORCE=0; WANT_PNG=1; WANT_SVG=1
END_OF_OPTS=0
for a in "$@"; do
  if [ "$END_OF_OPTS" -eq 1 ]; then
    if [ -n "$DIR" ]; then
      usage
      echo "unexpected extra argument: $a" >&2
      exit 2
    fi
    DIR="$a"
    continue
  fi
  case "$a" in
    --) END_OF_OPTS=1 ;;
    --force) FORCE=1 ;;
    --png-only) WANT_SVG=0 ;;
    --svg-only) WANT_PNG=0 ;;
    -*)
      usage
      echo "unknown flag: $a" >&2
      exit 2
      ;;
    *)
      if [ -n "$DIR" ]; then
        usage
        echo "unexpected extra argument: $a" >&2
        exit 2
      fi
      DIR="$a"
      ;;
  esac
done
DIR="${DIR:-docs/diagrams}"
case "$DIR" in
  /*|./*) ;;
  *) DIR="./$DIR" ;;
esac

if [ "$WANT_PNG" -eq 0 ] && [ "$WANT_SVG" -eq 0 ]; then
  usage
  echo "--png-only and --svg-only are mutually exclusive" >&2
  exit 2
fi

if ! command -v mmdc >/dev/null 2>&1; then
  echo "mmdc not found. Install with: npm install -g @mermaid-js/mermaid-cli" >&2
  exit 1
fi

shopt -s nullglob
FILES=("$DIR"/*.mmd)
if [ ${#FILES[@]} -eq 0 ]; then
  # render.sh has exactly one caller shape: point it at a diagrams directory.
  # An empty result there is far more likely a wrong/mistyped path (or one of
  # the flag-parsing bugs above eating a flag as the directory) than a
  # deliberate no-op run, so this fails loudly rather than succeeding on
  # nothing. Also: do not create $DIR/out below this point -- an output
  # directory that exists despite nothing having rendered is exactly the
  # "check the artifact, not the summary" trap this file has shipped before.
  echo "no .mmd files in $DIR" >&2
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
  # mmdc validates its -o extension, so the temp target keeps ".$ext" as the
  # actual suffix (".tmp" in the middle, not on the end) rather than being
  # rejected with "Output file must end with ... .svg/.png/...".
  local tmp="$OUT/$name.tmp.$ext"
  if [ "$FORCE" -eq 0 ] && [ -f "$dst" ] && [ "$dst" -nt "$src" ]; then
    echo "skip  $name.$ext (unchanged)"
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi
  # mmdc's exit code alone is not proof of a fresh render, so this checks the
  # artifact too -- but render to $tmp and move it onto $dst only once both
  # checks pass, rather than removing $dst up front. Wiping $dst first (the
  # previous approach) meant a re-render that genuinely failed -- not just a
  # call that lied about succeeding -- destroyed the last good render along
  # with it. This way a failed --force run leaves $dst exactly as it was.
  rm -f "$tmp"
  if mmdc -i "$src" -o "$tmp" -b "$bg" -s 2 -p "$PCFG_ARG" >/dev/null 2>&1 && [ -s "$tmp" ]; then
    mv -f "$tmp" "$dst"
    echo "ok    $name.$ext"
    OK=$((OK + 1))
    return 0
  fi
  echo "FAIL  $name.$ext" >&2
  mmdc -i "$src" -o "$tmp" -b "$bg" -p "$PCFG_ARG" 2>&1 | tail -5 >&2
  rm -f "$tmp"
  FAILED=$((FAILED + 1))
  return 1
}

OK=0
SKIPPED=0
FAILED=0
for src in "${FILES[@]}"; do
  [ "$WANT_SVG" -eq 1 ] && render_one "$src" svg transparent
  [ "$WANT_PNG" -eq 1 ] && render_one "$src" png white
done
echo "output: $OUT"
echo "done: $OK ok, $SKIPPED skipped, $FAILED failed"
if [ "$FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
