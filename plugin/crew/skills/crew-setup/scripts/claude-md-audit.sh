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
    commands*|build*|running*|how\ to\ run*)                 echo "commands" ;;
    where*|layout*|structure*|code\ map*)                    echo "where-things-are" ;;
    scope*|discipline*)                                      echo "scope" ;;
    stop*|ask*|escalat*)                                     echo "stop-and-ask" ;;
    promotion*|production*|deploy*|release*|environments*)   echo "promotion" ;;
    documentation*|docs*|doc\ format*)                        echo "documentation" ;;
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
    documentation)    echo "## Documentation - HTML/PDF/DOCX for humans, Markdown for the repo, all under docs/" ;;
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
# The list the audit REPORTS on. It is deliberately the same set as the test's
# CONCERNS and as label()'s arms: adding a heading to canon() and label() but
# not here made the audit silently accept a CLAUDE.md with no Documentation
# section - recognised, and never asked for.
for k in commands where-things-are scope stop-and-ask promotion documentation reporting memory; do
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

# Unfilled placeholders: lines that still hold one of the TEMPLATE'S OWN blanks.
#
# The blanks are read from the template on every run, so the list cannot drift
# from the file it describes. A blank is an angle-bracket token that stands
# where a value goes: outside any code span (`# <repo-name>`), or as the entire
# content of one (`<path>` alone between backticks, or alone on a fenced line).
# An angle-bracket token that shares its code span or fenced line with other
# text is a command's metavariable (`/crew:promote <env>`, `git checkout --
# <path>`), in the template and in the audited file alike, and is never counted.
#
# This replaced one regex over the whole file - any <word>, any `...`, OWNER_,
# YYYY-MM-DD - which counted a repo's documented commands as unfilled template
# text (`Docs: none - <why>`, `open(...)`), so a CLAUDE.md that explains its own
# commands could never reach "no remaining placeholders". It also missed three
# real blanks, because `<bash | powershell>` is not `<[a-z-]+>`.
#
# awk, not grep -f or an array: one pass, no temp file, bash 3.2 and Git Bash
# both carry it. The template path travels in the environment because `awk -v`
# rewrites backslashes in its value. A count that could not be taken (no awk,
# no readable template, a template with no blanks) is reported as NOT RUN, never
# as zero.
#
# awk reads an operand shaped like name=value as an assignment, not a file, so
# a relative path is given a leading ./ (a drive-letter path cannot be one).
case "$TARGET" in
  /*|*:*) AWK_TARGET="$TARGET" ;;
  *)      AWK_TARGET="./$TARGET" ;;
esac
PLACE=$(CREW_AUDIT_TEMPLATE="$TEMPLATE" awk '
  # The text of one line that can hold a blank, with everything else dropped.
  # Code spans are split on the backtick: even-numbered pieces are inside a span.
  # A span is kept only when it is nothing but one token. A backtick with no
  # partner on the line opens no span, so what follows it still counts. A run
  # of backticks is one delimiter, so a double-backtick span is a span too.
  function visible(s,    n, i, f, out) {
    sub(/\r$/, "", s)
    gsub(/`+/, "`", s)
    n = split(s, piece, "`")
    out = ""
    for (i = 1; i <= n; i++) {
      f = piece[i]
      if (i % 2 == 0 && i < n) {
        gsub(/^[ \t]+|[ \t]+$/, "", f)
        if (f !~ /^<[^<>]+>$/) f = ""
      }
      out = out f "`"
    }
    return out
  }
  # A fenced line is code from end to end: it counts only when it is one token.
  function fenced(s) {
    sub(/\r$/, "", s)
    gsub(/^[ \t]+|[ \t]+$/, "", s)
    return (s ~ /^<[^<>]+>$/) ? s : ""
  }
  # A fence line opens or closes a block. A line that starts with three
  # backticks and closes them again is a code span, not a fence.
  function is_fence(s) { return s ~ /^[ \t]*(```+|~~~+)[^`]*$/ }
  function has_blank(s,    t) {
    for (t = 1; t <= ntok; t++) if (index(s, tok[t]) > 0) return 1
    return 0
  }
  BEGIN {
    tpl = ENVIRON["CREW_AUDIT_TEMPLATE"]
    ntok = 0; infence = 0
    while ((getline line < tpl) > 0) {
      if (is_fence(line)) { infence = !infence; continue }
      v = infence ? fenced(line) : visible(line)
      while (match(v, /<[^<>]+>/)) {
        t = substr(v, RSTART, RLENGTH)
        v = substr(v, RSTART + RLENGTH)
        # A one-line HTML comment is markup, not a blank. A blank written
        # inside a comment (the header note names <repo>) still is one.
        if (t !~ /^<!/) tok[++ntok] = t
      }
    }
    close(tpl)
    infence = 0; count = 0; pending = 0
  }
  {
    if (is_fence($0)) { infence = !infence; pending = 0; next }
    if (!infence) { if (has_blank(visible($0))) count++; next }
    if (has_blank(fenced($0))) count++
    # A fence that never closes hides the rest of the file. Remember what those
    # lines would have counted as ordinary text, and count them at the end.
    else if (has_blank(visible($0))) pending++
  }
  END {
    if (ntok == 0) { print "unknown"; exit }
    if (infence) count += pending
    print count
  }
' "$AWK_TARGET" 2>/dev/null || true)
case "$PLACE" in
  ''|*[!0-9]*)
    # Name which of the three it was: the fix differs for each.
    if ! command -v awk >/dev/null 2>&1; then
      WHY="awk is not on PATH"
    elif [ ! -r "$TEMPLATE" ]; then
      WHY="cannot read the template at $TEMPLATE"
    elif [ "$PLACE" = unknown ]; then
      WHY="the template at $TEMPLATE has no placeholders to look for"
    else
      WHY="awk failed on $TARGET"
    fi
    echo "  Placeholder check NOT RUN: $WHY" ;;
  0) ;;
  *) echo "  $PLACE line(s) still contain template placeholders." ;;
esac

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
