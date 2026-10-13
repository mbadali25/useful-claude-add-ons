#!/usr/bin/env bash
# Placeholder-count test for claude-md-audit.sh.
#
# Phase 1 closes on "no remaining placeholders", so the count has two ways to be
# wrong and both cost a user the phase: counting a repo's own documented commands
# as unfilled template text (the phase can never close), and missing a blank the
# template really left (the phase closes on an unfinished file).
#
# What shipped was the first: one regex over the whole file - any <word>, any
# `...` - reported 8 lines of this repository's CLAUDE.md, every one of them a
# command metavariable or ordinary code. Those 8 lines are the must-not-flag
# cases below, verbatim. The must-flag cases are the template's own blank lines,
# one fixture each, so restoring the old regex turns this suite red in both
# directions (it also never saw `<bash | powershell>`).
#
# Every fixture is built under one mktemp directory, and the only removal in this
# file refuses any path that is not that directory.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
AUDIT="$HERE/../claude-md-audit.sh"
TEMPLATE="$HERE/../../repo-claude-template.md"

[ -f "$AUDIT" ]    || { echo "FAIL: cannot find claude-md-audit.sh at $AUDIT"; exit 1; }
[ -f "$TEMPLATE" ] || { echo "FAIL: cannot find repo-claude-template.md at $TEMPLATE"; exit 1; }

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/crew-audit-suite.XXXXXX")" || { echo "FAIL: mktemp -d failed"; exit 1; }
cleanup() {
  case "$ROOT" in
    */crew-audit-suite.??????) [ -d "$ROOT" ] && rm -rf "$ROOT" ;;
    *) echo "refusing to remove '$ROOT': not this suite's temp root" >&2 ;;
  esac
}
trap cleanup EXIT

# This suite's own comparisons read an LF copy of the template. `*.md` is not
# pinned to LF in .gitattributes, so a Windows checkout with core.autocrlf=true
# holds it CRLF, and `grep -x` against that matches no line at all. The audit is
# still run against the real file; its CRLF handling has its own cases below.
TEMPLATE_LF="$ROOT/template.lf"
tr -d '\r' < "$TEMPLATE" > "$TEMPLATE_LF"
crlf() { awk '{ sub(/\r$/, ""); printf "%s\r\n", $0 }' "$1" > "$2"; }

fails=0
checked=0
ok()  { echo "ok    $1"; checked=$((checked+1)); }
bad() { echo "FAIL  $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/         /'; fails=$((fails+1)); checked=$((checked+1)); }

# What the audit said about placeholders: a number, 0 when it printed no
# placeholder line, "notrun" when it said it could not check, "garbled" otherwise.
placeholder_count() {
  local out="$1" n
  if printf '%s\n' "$out" | grep -q 'Placeholder check NOT RUN'; then echo notrun; return; fi
  n=$(printf '%s\n' "$out" | sed -n 's/^  \([0-9][0-9]*\) line(s) still contain template placeholders\.$/\1/p')
  if [ -n "$n" ]; then echo "$n"; return; fi
  # The temp root is not named after the word this looks for: the report's first
  # line carries the fixture's path, and a path containing it read as garbled.
  if printf '%s\n' "$out" | grep -qi 'placeholder'; then echo garbled; return; fi
  echo 0
}

# A CLAUDE.md with every template section and nothing left to fill in.
filled() {
  cat > "$1" <<'EOF'
# widget-service

**Stack:** Python 3.12, FastAPI   **Runs:** make dev
**Platform:** linux   **Shell:** bash
**Talks to:** Postgres, the billing API

## Commands
| build | `make build` |
| test  | `make test` |

## Where things are
- entrypoint: `app/main.py`   logic: `app/core/`   data access: `app/db/`
- DO NOT TOUCH: `vendor/`

## Scope discipline
- Fix the ticket, not what you notice nearby.

## Stop and ask
- You are unsure. A question costs less than a wrong guess.

## Promotion: development -> qa -> production
- That order, no skipping.

## Documentation
- Under docs, as HTML.

## Reporting
- Report failures verbatim.

## Memory
Code map: `.crew/codemap/INDEX.md`.
EOF
}

N=0
# fixture <line>...: a filled CLAUDE.md with the given lines appended. Sets $FIX.
fixture() {
  N=$((N+1))
  FIX="$ROOT/case-$N/CLAUDE.md"
  mkdir -p "$ROOT/case-$N"
  filled "$FIX"
  printf '\n' >> "$FIX"
  while [ "$#" -gt 0 ]; do printf '%s\n' "$1" >> "$FIX"; shift; done
}

# expect <want> <name>: run the audit on $FIX and compare the placeholder count.
expect() {
  local want="$1" name="$2" out rc got
  out=$(bash "$AUDIT" "$FIX" 2>&1); rc=$?
  got=$(placeholder_count "$out")
  if [ "$rc" -ne 0 ]; then
    bad "$name: audit exited $rc, expected 0" "$out"
  elif [ "$got" = "$want" ]; then
    ok "$name"
  else
    bad "$name: placeholder lines reported = $got, expected $want" "$(tail -4 "$FIX")"
  fi
}

# must_flag <template line>: the line has to exist in the template verbatim (so
# this list cannot outlive the template), and alone it has to count as 1.
FLAG_CASES=0
must_flag() {
  FLAG_CASES=$((FLAG_CASES+1))
  if ! grep -qxF -- "$1" "$TEMPLATE_LF"; then
    bad "must-flag case is not a line of the template any more: $1" \
        "The template moved. Update this suite's must-flag list to its current blank lines."
    return
  fi
  fixture "$1"
  expect 1 "flags the template's blank line: $1"
}

# must_not_flag <name> <line>...
must_not_flag() {
  local name="$1"; shift
  fixture "$@"
  expect 0 "does not flag $name"
}

echo "-- a filled file --"
N=$((N+1)); mkdir -p "$ROOT/case-$N"; FIX="$ROOT/case-$N/CLAUDE.md"; filled "$FIX"
expect 0 "a CLAUDE.md with nothing left to fill reports no placeholder line"
out=$(bash "$AUDIT" "$FIX" 2>&1)
if printf '%s\n' "$out" | grep -qx 'RESULT: all template sections present.'; then
  ok "and still reports all template sections present"
else
  bad "the filled fixture lost its sections verdict" "$out"
fi

echo "-- must flag: every blank line of the template --"
must_flag '<!-- <repo>/CLAUDE.md — target 40 lines, hard ceiling 60.'
must_flag '# <repo-name>'
must_flag '**Stack:** <...>   **Runs:** <one line to start locally>'
must_flag '**Platform:** <linux | wsl2/Ubuntu | windows>   **Shell:** <bash | powershell>'
must_flag '**Talks to:** <db, upstream services, consumers>'
must_flag '| build | `<...>` |'
must_flag '| test  | `<...>` |'
must_flag '| migrate | `<...>` |'
must_flag '- entrypoint: `<path>`   logic: `<path>`   data access: `<path>`'
must_flag '- DO NOT TOUCH: `<vendor/, generated/, legacy/>`'

# The untouched template, whole. The expected number is the list above, not a
# second run of the audit's own logic: a blank added to the template with no case
# here fails with a count one higher than the list.
N=$((N+1)); mkdir -p "$ROOT/case-$N"; FIX="$ROOT/case-$N/CLAUDE.md"; cp "$TEMPLATE" "$FIX"
expect "$FLAG_CASES" "an untouched copy of the template reports all $FLAG_CASES of its blank lines"
out=$(bash "$AUDIT" "$FIX" 2>&1)
if printf '%s\n' "$out" | grep -qx 'RESULT: all template sections present.'; then
  ok "and the untouched template still has every section"
else
  bad "the untouched template lost its sections verdict" "$out"
fi

# The same template with every angle-bracket token replaced: nothing left.
N=$((N+1)); mkdir -p "$ROOT/case-$N"; FIX="$ROOT/case-$N/CLAUDE.md"
sed 's/<[^<>]*>/filled/g' "$TEMPLATE" > "$FIX"
expect 0 "the template with every blank replaced reports no placeholder line"

echo "-- must not flag: the template's own command lines --"
for line in '| promote | `/crew:promote <development\|qa\|production>` |' \
            '  alarms, queues - after a soak, not immediately). Run `/crew:promote <env>`.'; do
  if grep -qxF -- "$line" "$TEMPLATE_LF"; then
    must_not_flag "a template command line: $line" "$line"
  else
    bad "must-not-flag case is not a line of the template any more: $line"
  fi
done

echo "-- must not flag: the 8 lines of this repository's CLAUDE.md the old regex reported --"
must_not_flag 'a trailer format (`Docs: none - <why>`)' \
  'no doc impact says so in its PR body, with the reason (`Docs: none - <why>`), never silently.'
must_not_flag 'an HTML comment marker with <name>' \
  '`<!-- claim: skills-count -->` or `<!-- claim: plugin-version:<name> -->` beside it and'
must_not_flag 'a trailer with <path> beside other text' \
  '`Tooling-seam: <path>` trailer, a claim the reviewer holds the diff to.'
must_not_flag 'a slash command argument <subsystem>' \
  '  Refresh with `/crew:onboard --refresh <subsystem>`. Anchor length does not matter (7-40'
must_not_flag 'a git command with <anchor> and <paths ...>' \
  'first — `git diff --name-only <anchor>..HEAD -- <paths the map documents>` — because a repo-wide'
must_not_flag 'code with an ellipsis, open(...)' \
  '  not this trap; the `with open(...) as fh:` form is. Repair with `git checkout --`. The per-site'
must_not_flag 'a git command ending in <path>' \
  '  `git checkout -- <path>`.'
must_not_flag 'a git command with <anchor> and <paths>' \
  '  `git diff --name-only <anchor>..HEAD -- <paths>`.'

echo "-- must not flag: what the old regex matched and no template blank is --"
must_not_flag 'a date format mentioned in prose' 'Runbooks carry `last verified: YYYY-MM-DD` in their header.'
must_not_flag 'an OWNER_ identifier'             'The variable is OWNER_TEAM, set in CI.'
must_not_flag 'an ellipsis in prose'             'Wait for the log to stop growing... then measure.'
must_not_flag 'an angle-bracket word the template never had' 'Deploys go to <region> and nowhere else.'
must_not_flag 'a fenced command with a metavariable' '```' 'git checkout -- <path>' '```'
must_not_flag 'a tilde-fenced command with a metavariable' '~~~' 'make deploy ENV=<path>' '~~~'
must_not_flag 'a double-backtick span with a metavariable' 'Undo with ``git checkout -- <path>`` and retry.'

echo "-- CRLF files, as a Windows checkout holds them --"
N=$((N+1)); mkdir -p "$ROOT/case-$N"; FIX="$ROOT/case-$N/CLAUDE.md"; crlf "$TEMPLATE_LF" "$FIX"
expect "$FLAG_CASES" "a CRLF copy of the template reports the same $FLAG_CASES lines"
N=$((N+1)); mkdir -p "$ROOT/case-$N"; FIX="$ROOT/case-$N/CLAUDE.md"
filled "$FIX"; printf '```\n<path>\n```\n' >> "$FIX"; crlf "$FIX" "$FIX.crlf"; FIX="$FIX.crlf"
expect 1 "a CRLF fenced line that is one blank still counts"
# The template itself CRLF, beside a copy of the script: the blanks still read.
mkdir -p "$ROOT/crlf-install/scripts"
cp "$AUDIT" "$ROOT/crlf-install/scripts/claude-md-audit.sh"
crlf "$TEMPLATE_LF" "$ROOT/crlf-install/repo-claude-template.md"
N=$((N+1)); mkdir -p "$ROOT/case-$N"; FIX="$ROOT/case-$N/CLAUDE.md"; cp "$TEMPLATE_LF" "$FIX"
out=$(bash "$ROOT/crlf-install/scripts/claude-md-audit.sh" "$FIX" 2>&1)
got=$(placeholder_count "$out")
if [ "$got" = "$FLAG_CASES" ]; then
  ok "a CRLF template yields the same blanks: $FLAG_CASES lines of an LF copy"
else
  bad "a CRLF template: placeholder lines reported = $got, expected $FLAG_CASES" "$out"
fi

echo "-- must flag: a blank in a position that hides it badly --"
fixture '- entrypoint: `src/main.py`   logic: `<path>`   data access: `src/db/`'
expect 1 "one blank left among filled code spans"
fixture 'Start it with <one line to start locally> and wait.'
expect 1 "a blank left in the middle of a sentence"
fixture 'See `make help` for <path> details.'
expect 1 "a bare blank beside a code span that is not its own"
fixture 'A stray ` backtick, then <repo-name> with no partner on the line.'
expect 1 "a blank after a backtick that opens no span"
fixture '```' '<path>' '```'
expect 1 "a blank that is a fenced line on its own"
fixture '# <repo-name>' '**Talks to:** <db, upstream services, consumers>' '| build | `<...>` |'
expect 3 "three blank lines count as three"
fixture '**Stack:** <...>   **Runs:** <one line to start locally>'
expect 1 "two blanks on one line count as one line"
fixture '```' 'make build' '# <repo-name>' '| test  | `<...>` |'
expect 2 "a fence that never closes does not hide the blanks after it"
fixture '```make deploy ENV=<path>```' '# <repo-name>' '```' 'make build' '```'
expect 1 "a one-line triple-backtick span is not a fence, so the blank after it counts"
# A relative path shaped like name=value: awk would take it as an assignment
# and read nothing, which printed as a clean file.
mkdir -p "$ROOT/rel/env=prod"
filled "$ROOT/rel/env=prod/CLAUDE.md"; printf '# <repo-name>\n' >> "$ROOT/rel/env=prod/CLAUDE.md"
out=$(cd "$ROOT/rel" && bash "$AUDIT" "env=prod/CLAUDE.md" </dev/null 2>&1)
got=$(placeholder_count "$out")
if [ "$got" = 1 ]; then
  ok "a relative path containing = is read as a file"
else
  bad "a relative path containing =: placeholder lines reported = $got, expected 1" "$out"
fi

echo "-- the rest of the audit is unchanged --"
out=$(bash "$AUDIT" "$ROOT/no-such-dir/CLAUDE.md" 2>&1); rc=$?
if [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q "^MISSING $ROOT/no-such-dir/CLAUDE.md$"; then
  ok "a missing CLAUDE.md still exits 1 with the MISSING line"
else
  bad "a missing CLAUDE.md: exit $rc" "$out"
fi

fixture '# <repo-name>'
out=$(bash "$AUDIT" "$FIX" 2>&1)
want_len=$(grep -cv '^[[:space:]]*$' "$FIX")
if printf '%s\n' "$out" | grep -qx "Length: $want_len non-blank lines (target 40, hard ceiling 60)"; then
  ok "the Length line is the same text with the same count"
else
  bad "the Length line changed" "$out"
fi
# The whole report, line for line, for a file with one blank.
want="$ROOT/want.txt"
{
  echo "CLAUDE.md audit: $FIX"
  echo
  echo "Sections the template expects:"
  echo "  present  ## Commands"
  echo "  present  ## Where things are"
  echo "  present  ## Scope discipline"
  echo "  present  ## Stop and ask"
  echo "  present  ## Promotion: development -> qa -> production"
  echo "  present  ## Documentation"
  echo "  present  ## Reporting"
  echo "  present  ## Memory"
  echo
  echo "Length: $want_len non-blank lines (target 40, hard ceiling 60)"
  echo "  1 line(s) still contain template placeholders."
  echo
  echo "RESULT: all template sections present."
} > "$want"
printf '%s\n' "$out" > "$ROOT/got.txt"
if cmp -s "$want" "$ROOT/got.txt"; then
  ok "the full report for a one-blank file is byte-for-byte the expected text"
else
  bad "the full report changed" "$(diff "$want" "$ROOT/got.txt")"
fi

echo "-- a count that cannot be taken is not a zero --"
# A copy of the script with no template beside it: the blanks cannot be read.
mkdir -p "$ROOT/orphan/scripts"
cp "$AUDIT" "$ROOT/orphan/scripts/claude-md-audit.sh"
fixture '# <repo-name>'
out=$(bash "$ROOT/orphan/scripts/claude-md-audit.sh" "$FIX" 2>&1); rc=$?
got=$(placeholder_count "$out")
if [ "$rc" -eq 0 ] && [ "$got" = notrun ] && printf '%s\n' "$out" | grep -q 'NOT RUN: cannot read the template at '; then
  ok "no template beside the script: says NOT RUN and why, exit 0, no count"
else
  bad "no template beside the script: exit $rc, placeholder result '$got', expected notrun" "$out"
fi
# A template with no blanks in it says the same: there is nothing to look for.
mkdir -p "$ROOT/blankless/scripts"
cp "$AUDIT" "$ROOT/blankless/scripts/claude-md-audit.sh"
filled "$ROOT/blankless/repo-claude-template.md"
out=$(bash "$ROOT/blankless/scripts/claude-md-audit.sh" "$FIX" 2>&1); rc=$?
got=$(placeholder_count "$out")
if [ "$rc" -eq 0 ] && [ "$got" = notrun ] && printf '%s\n' "$out" | grep -q 'has no placeholders to look for$'; then
  ok "a template with no blanks: says NOT RUN and why, rather than 0"
else
  bad "a template with no blanks: exit $rc, placeholder result '$got', expected notrun" "$out"
fi

echo "-- this repository's own CLAUDE.md --"
# Only in a checkout of the marketplace. An installed copy of the plugin has no
# repository above it, and that is said rather than passed over.
REPO="$(cd "$HERE/../../../../../.." 2>/dev/null && pwd)"
if [ -n "$REPO" ] && [ -f "$REPO/.claude-plugin/marketplace.json" ] && [ -f "$REPO/CLAUDE.md" ]; then
  out=$(bash "$AUDIT" "$REPO/CLAUDE.md" 2>&1); rc=$?
  got=$(placeholder_count "$out")
  if [ "$rc" -eq 0 ] && [ "$got" = 0 ]; then
    ok "the marketplace's CLAUDE.md reports no placeholder line"
  else
    bad "the marketplace's CLAUDE.md: exit $rc, placeholder lines reported = $got, expected 0" "$out"
  fi
else
  echo "skip  the marketplace's CLAUDE.md: not a checkout of the marketplace (NOT VERIFIED here)"
fi

# A suite that ran nothing must not pass. The floor is the must-flag list itself,
# not a literal that has to be edited whenever the template gains a blank.
if [ "$FLAG_CASES" -eq 0 ] || [ "$checked" -le "$FLAG_CASES" ]; then
  echo "FAIL: only $checked check(s) ran over $FLAG_CASES must-flag case(s) - the suite is broken"
  exit 1
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "PASS: $checked placeholder checks"
  exit 0
fi
echo "FAIL: $fails of $checked placeholder checks"
exit 1
