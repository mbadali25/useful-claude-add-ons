#!/usr/bin/env bash
# Compare a repo's CLAUDE.md against the crew template, by section.
#
# Read-only. Reports what is missing, what is extra, and whether the file is
# over budget. It does NOT edit anything - the merge is a judgment call and the
# sections it would add are exactly the ones only the user can fill in.
#
# No associative arrays and no process substitution: macOS still ships bash
# 3.2, where `declare -A` is a hard parse error.
#
# Usage:  bash claude-md-audit.sh [path/to/CLAUDE.md]
set -uo pipefail

TARGET="${1:-CLAUDE.md}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$HERE/../repo-claude-template.md"

if [ ! -f "$TARGET" ]; then
  echo "MISSING $TARGET"
  echo "  No CLAUDE.md in this repo. Create one from the template:"
  echo "    $TEMPLATE"
  exit 1
fi

# Map a heading to the concern it covers, so a repo that renamed a section is
# not reported as missing it. Add rows here rather than loosening the match.
canon() {
  case "$1" in
    commands|build*|running*|how\ to\ run*)                  echo "commands" ;;
    where*|layout*|structure*|code\ map*)                    echo "where-things-are" ;;
    scope*|discipline*)                                      echo "scope" ;;
    stop*|ask*|escalat*)                                     echo "stop-and-ask" ;;
    promotion*|production*|deploy*|release*|environments*)   echo "promotion" ;;
    reporting*|output*|communicat*)                          echo "reporting" ;;
    memory*|context*|notes*)                                 echo "memory" ;;
    *)                                                       echo "other:$1" ;;
  esac
}

label() {
  case "$1" in
    commands)         echo "## Commands - build, test, verify, regression, promote" ;;
    where-things-are) echo "## Where things are - entrypoints, logic, DO NOT TOUCH" ;;
    scope)            echo "## Scope discipline - fix the ticket, not what you notice nearby" ;;
    stop-and-ask)     echo "## Stop and ask - the conditions that should halt work" ;;
    promotion)        echo "## Promotion: development -> qa -> production - smoke, regression, verify" ;;
    reporting)        echo "## Reporting - errors verbatim, say what you did NOT verify" ;;
    memory)           echo "## Memory - where the code map and runbooks live" ;;
  esac
}

HAVE=""
EXTRAS=""
while IFS= read -r h; do
  [ -z "$h" ] && continue
  c=$(canon "$h")
  case "$c" in
    other:*) EXTRAS="${EXTRAS}${c#other:}
" ;;
    *)       HAVE="${HAVE}${c}
" ;;
  esac
done <<EOF
$(grep -E '^## ' "$TARGET" | sed 's/^## //' | tr '[:upper:]' '[:lower:]' | sed 's/[[:space:]]*$//')
EOF

MISSING=0
echo "CLAUDE.md audit: $TARGET"
echo
echo "Sections the template expects:"
for k in commands where-things-are scope stop-and-ask promotion reporting memory; do
  if printf '%s' "$HAVE" | grep -qx "$k"; then
    echo "  present  $(label "$k" | sed 's/ - .*//')"
  else
    echo "  MISSING  $(label "$k")"
    MISSING=$((MISSING+1))
  fi
done

printf '%s' "$EXTRAS" | while IFS= read -r e; do
  [ -n "$e" ] && echo "  extra    ## $e"
done

LINES=$(grep -cv '^[[:space:]]*$' "$TARGET")
echo
echo "Length: $LINES non-blank lines (target 40, hard ceiling 60)"
[ "$LINES" -gt 60 ] && echo "  OVER BUDGET. This file loads into every subagent on every delegation."

PLACE=$(grep -cE '<[a-z-]+>|OWNER_|YYYY-MM-DD|\.\.\.' "$TARGET" 2>/dev/null || true)
[ "${PLACE:-0}" -gt 0 ] && echo "  $PLACE line(s) still contain template placeholders."

echo
if [ "$MISSING" -eq 0 ]; then
  echo "RESULT: all template sections present."
else
  echo "RESULT: $MISSING section(s) missing."
  echo
  echo "Add them by appending to the existing file - never regenerate it. The"
  echo "repo's own sections are the valuable part; the template only supplies"
  echo "the headings the repo has not thought about yet. Ask the user to fill"
  echo "each one in; do not guess a repo's deploy path or its landmines."
fi
exit 0
