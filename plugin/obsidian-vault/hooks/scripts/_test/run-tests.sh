#!/usr/bin/env bash
# Regression suite for this plugin's scripts: vault_guard.py (the one blocking
# hook it ships) inline below, then the two Python suites that cover vault
# resolution and the REST bridge's ports, collisions and identity.
# Sabotage-tested: every case here was run once against a broken version of the
# check it covers to confirm it actually goes red, not just that it exists.
#
# Path handling note: on Windows, `python3` here is a native Windows build (not
# an MSYS/Cygwin one), so it does not understand a POSIX-style /tmp/... path
# bash's own mktemp produces. Every path embedded in JSON that Python will
# resolve (config.json's vaultPath, HOME, a payload's file_path) is converted
# with `winpath` first; bash's own mkdir/file writes keep using the POSIX form,
# since Git Bash resolves both forms to the same real directory. On Linux/macOS
# `cygpath` does not exist, `winpath` is a no-op, and this is unnecessary but
# harmless.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "FATAL: no Python interpreter found. Tried python3, python, py on PATH." >&2
  echo "Git Bash ships without python3; install Python or put it on PATH." >&2
  exit 1
fi
PASS=0
FAIL=0

winpath() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
vault="$work/vault"
vault_win="$(winpath "$vault")"
mkdir -p "$vault/wiki/concepts" "$vault/wiki/templates" "$vault/wiki/canvases" "$work/outside"

home_on="$work/home"
home_off="$work/home-off"
home_default="$work/home-default"
mkdir -p "$home_on/.claude/obsidian" "$home_off/.claude/obsidian" \
         "$home_default/.claude/obsidian"

# Config: turn every toggle ON so the suite exercises the checks, mirroring a
# vault whose CLAUDE.md declared all three rules. asciiOnly and requireFrontmatter
# ship OFF; checkCanvas ships ON (vault_guard.py:243, `is not False`), so this
# config overrides two defaults and restates the third. Either way the guard's
# LOGIC must be correct when a vault turns them on. Built via
# json.dumps (not a shell heredoc) so a Windows path's backslashes escape
# correctly no matter what the path looks like.
"$PY" - "$vault_win" "$home_on/.claude/obsidian/config.json" <<'PYEOF'
import json, sys
vault, out = sys.argv[1], sys.argv[2]
json.dump({"vaultPath": vault, "guard": {"asciiOnly": True, "requireFrontmatter": True,
                                          "checkCanvas": True, "notesPrefix": "wiki/"}},
          open(out, "w", encoding="utf-8"))
PYEOF
"$PY" - "$vault_win" "$home_off/.claude/obsidian/config.json" <<'PYEOF'
import json, sys
vault, out = sys.argv[1], sys.argv[2]
json.dump({"vaultPath": vault, "guard": {"asciiOnly": False, "requireFrontmatter": False,
                                          "checkCanvas": False}},
          open(out, "w", encoding="utf-8"))
PYEOF

# A third config carrying vaultPath and NO "guard" key at all - a config with
# a vault and no guard block, which is what /obsidian-vault:init leaves behind
# when a vault's CLAUDE.md states no rule to turn on. (Not "a fresh install":
# before init runs there may be no config file at all, and this fixture has a
# vaultPath.) The two above set every toggle explicitly, so neither can tell a
# DEFAULT apart from an override, and the defaults are stated as a promise in
# seven places (the guard's own docstring, PLUGINS.md, plugin/README.md, this
# plugin's README, the root README, and both manifest descriptions). This
# config is what the DEFAULTS section below holds them to.
"$PY" - "$vault_win" "$home_default/.claude/obsidian/config.json" <<'PYEOF'
import json, sys
vault, out = sys.argv[1], sys.argv[2]
json.dump({"vaultPath": vault}, open(out, "w", encoding="utf-8"))
PYEOF

# Writes the note/canvas to disk for real (the guard reads file content from
# disk, not from the hook payload), then prints the JSON payload path Claude
# Code would actually send: tool_input.file_path plus new content as
# tool_input.content, so the ASCII check (which scans only what an edit
# introduced) also has something to look at.
write_and_payload() {
  local relpath="$1" content="$2"
  local abspath="$vault/$relpath"
  local absdir; absdir="$(dirname "$abspath")"
  mkdir -p "$absdir"
  printf '%s' "$content" > "$abspath"
  local abspath_win; abspath_win="$(winpath "$abspath")"
  local payload_file="$work/payload.json"
  "$PY" - "$abspath_win" "$content" > "$payload_file" <<'PYEOF'
import json, sys
path, content = sys.argv[1], sys.argv[2]
print(json.dumps({"tool_input": {"file_path": path, "content": content}}))
PYEOF
  echo "$payload_file"
}

run_guard() {
  # $1 = path to a JSON payload file, $2 = HOME to run under (Windows form)
  HOME="$2" "$PY" "$DIR/vault_guard.py" < "$1" >/dev/null 2>&1
  echo $?
}

guard_stderr() {
  # Same call, but returns what the guard wrote to stderr instead of its exit
  # code. The redirect order matters: `2>&1 >/dev/null` dups stderr onto the
  # still-original stdout and only then sends stdout to the bin, so what is
  # captured is stderr alone. The reverse order captures nothing.
  HOME="$2" "$PY" "$DIR/vault_guard.py" < "$1" 2>&1 >/dev/null
}

check() {
  local desc="$1" expect="$2" got="$3"
  if [ "$got" = "$expect" ]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    echo "FAIL: $desc (expected exit $expect, got $got)"
  fi
}

check_stderr_has() {
  local desc="$1" needle="$2" got="$3"
  case "$got" in
    *"$needle"*) PASS=$((PASS+1)) ;;
    *) FAIL=$((FAIL+1)); echo "FAIL: $desc (stderr did not contain '$needle'; got: $got)" ;;
  esac
}

check_stderr_lacks() {
  local desc="$1" needle="$2" got="$3"
  case "$got" in
    *"$needle"*) FAIL=$((FAIL+1)); echo "FAIL: $desc (stderr contained '$needle'; got: $got)" ;;
    *) PASS=$((PASS+1)) ;;
  esac
}

check_stderr_empty() {
  local desc="$1" got="$2"
  if [ -z "$got" ]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    echo "FAIL: $desc (expected silent stderr, got: $got)"
  fi
}

home_on_win="$(winpath "$home_on")"
home_off_win="$(winpath "$home_off")"
home_default_win="$(winpath "$home_default")"
today="$(date +%F)"

echo "== vault_guard.py: must BLOCK (exit 2) =="

good_fm="---
type: concept
title: \"widget-caching\"
created: 2026-08-20
updated: $today
status: seed
tags:
  - concept
---
Body.
"

f=$(write_and_payload "wiki/concepts/no-frontmatter.md" "Just prose, no frontmatter block.")
check "note with no frontmatter" 2 "$(run_guard "$f" "$home_on_win")"
check_stderr_has "note with no frontmatter names the violation on stderr" \
  "NO FRONTMATTER" "$(guard_stderr "$f" "$home_on_win")"

bad_fm="---
type: concept
title: \"Widget caching\"
created: 2026-08-20
updated: $today
tags:
  - concept
---
Body.
"
f=$(write_and_payload "wiki/concepts/missing-status.md" "$bad_fm")
check "note missing a required frontmatter key" 2 "$(run_guard "$f" "$home_on_win")"

title_mismatch="---
type: concept
title: \"Wrong Title Entirely\"
created: 2026-08-20
updated: $today
status: seed
tags:
  - concept
---
Body.
"
f=$(write_and_payload "wiki/concepts/actual-filename.md" "$title_mismatch")
check "title does not match filename" 2 "$(run_guard "$f" "$home_on_win")"

em_dash_fm="---
type: concept
title: \"em-dash\"
created: 2026-08-20
updated: $today
status: seed
tags:
  - concept
---
"
em_dash_body="${em_dash_fm}Body has an em dash - right here: EMDASH"
em_dash_body="${em_dash_body/EMDASH/$'\xe2\x80\x94'}"
f=$(write_and_payload "wiki/concepts/em-dash.md" "$em_dash_body")
check "non-ASCII character introduced" 2 "$(run_guard "$f" "$home_on_win")"

f=$(write_and_payload "wiki/canvases/broken.canvas" "{not valid json")
check "canvas is not valid JSON" 2 "$(run_guard "$f" "$home_on_win")"

bad_canvas='{"nodes":[{"id":"a","type":"text","text":"x"}],"edges":[{"id":"e1","fromNode":"a","toNode":"ghost"}]}'
f=$(write_and_payload "wiki/canvases/dangling-edge.canvas" "$bad_canvas")
check "canvas edge references a missing node id" 2 "$(run_guard "$f" "$home_on_win")"

echo "== vault_guard.py: must ALLOW (exit 0) =="

f=$(write_and_payload "wiki/concepts/widget-caching.md" "$good_fm")
check "well-formed note" 0 "$(run_guard "$f" "$home_on_win")"

f=$(write_and_payload "wiki/templates/concept.md" "no frontmatter here, it is a template")
check "template file is exempt" 0 "$(run_guard "$f" "$home_on_win")"

claude_md_body="This doc uses a real em dash - on purpose: EMDASH"
claude_md_body="${claude_md_body/EMDASH/$'\xe2\x80\x94'}"
f=$(write_and_payload "CLAUDE.md" "$claude_md_body")
check "CLAUDE.md is ASCII-exempt" 0 "$(run_guard "$f" "$home_on_win")"

good_canvas='{"nodes":[{"id":"a","type":"text","text":"x"}],"edges":[]}'
f=$(write_and_payload "wiki/canvases/fine.canvas" "$good_canvas")
check "well-formed canvas" 0 "$(run_guard "$f" "$home_on_win")"

mkdir -p "$work/outside"
printf 'no frontmatter, but not in the vault' > "$work/outside/note.md"
outside_win="$(winpath "$work/outside/note.md")"
payload_file="$work/payload-outside.json"
"$PY" - "$outside_win" "no frontmatter, but not in the vault" > "$payload_file" <<'PYEOF'
import json, sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1], "content": sys.argv[2]}}))
PYEOF
check "file outside the vault is ignored" 0 "$(run_guard "$payload_file" "$home_on_win")"

echo "== vault_guard.py: FRONTMATTER_EXEMPT_NAMES (TODO #4) =="

# These four basenames are agent-instruction files, not notes, so the guard must
# not DEMAND frontmatter of them - a YAML header in CLAUDE.md is read as part of
# Claude's instructions. The guard is PostToolUse, so exit 2 does not prevent the
# write; it hands Claude stderr and tells it to go back and "fix" a file that is
# not broken.
#
# "Can never carry the contract" is what an earlier version of this comment
# said, and it is wrong: a genuine note that happens to be called README.md can
# carry frontmatter, and when it does it is held to all of it. The exemption is
# only from the demand. The frontmatter-bearing cases further down are the ones
# that pin that.
#
# Every case here lives UNDER "wiki/" on purpose. notesPrefix is "wiki/", so a
# vault-root CLAUDE.md never reaches check_note at all and would pass with or
# without the exemption - it proves nothing. Only these go red when
# FRONTMATTER_EXEMPT_NAMES is emptied.
for exempt_name in CLAUDE.md README.md AGENTS.md GEMINI.md; do
  f=$(write_and_payload "wiki/$exempt_name" "Instructions for this vault. No frontmatter, by design.")
  check "$exempt_name inside notesPrefix is frontmatter-exempt" 0 "$(run_guard "$f" "$home_on_win")"
done

f=$(write_and_payload "wiki/Readme.MD" "Mixed-case basename. Still no frontmatter, still exempt.")
check "the exemption is case-insensitive (Readme.MD)" 0 "$(run_guard "$f" "$home_on_win")"

f=$(write_and_payload "wiki/CLAUDE.md" "Instructions for this vault. No frontmatter, by design.")
check_stderr_empty "an exempt file reports nothing at all on stderr" \
  "$(guard_stderr "$f" "$home_on_win")"

# The exemption is frontmatter-only for three of the four names. CLAUDE.md is
# ALSO in ASCII_EXEMPT_NAMES, by a separate and older decision, so "still held
# to every other rule" is true of README/AGENTS/GEMINI and false of CLAUDE.md.
#
# Codex round 6: this pair ran on README.md alone, which is the frontmatter
# hole one axis over. Narrowing ASCII_EXEMPT_NAMES to
# {"claude.md","agents.md","gemini.md"} - silently ASCII-exempting two names the
# hook table, the setup skill and the guard's own comment all promise are
# checked - passed the whole suite. Each name is pinned on its own now.
for ascii_name in README.md AGENTS.md GEMINI.md; do
  ascii_body="$ascii_name carrying an em dash that should still be caught: EMDASH"
  ascii_body="${ascii_body/EMDASH/$'\xe2\x80\x94'}"
  f=$(write_and_payload "wiki/ascii/$ascii_name" "$ascii_body")
  check "$ascii_name is frontmatter-exempt but still ASCII-checked" 2 "$(run_guard "$f" "$home_on_win")"
  check_stderr_has "and for $ascii_name it is reported as an ASCII violation" \
    "NON-ASCII" "$(guard_stderr "$f" "$home_on_win")"
  # The "not a frontmatter one" half has to be asserted, not just named: without
  # this, stderr carrying both needles keeps the check above green.
  check_stderr_lacks "and for $ascii_name not as a frontmatter one" \
    "NO FRONTMATTER" "$(guard_stderr "$f" "$home_on_win")"
done

# The mirror image, and it has to be here: the exemption that IS real must be
# pinned as tightly as the three that are not, or the next narrowing of
# ASCII_EXEMPT_NAMES drops CLAUDE.md's unnoticed. Under "wiki/" so it sits
# beside the three above - the ASCII check is not gated by notesPrefix, so this
# is the same assertion the vault-root case makes, held one directory deeper.
claude_ascii="CLAUDE.md may carry the real character, by design: EMDASH"
claude_ascii="${claude_ascii/EMDASH/$'\xe2\x80\x94'}"
f=$(write_and_payload "wiki/ascii/CLAUDE.md" "$claude_ascii")
check "CLAUDE.md inside notesPrefix is ASCII-exempt" 0 "$(run_guard "$f" "$home_on_win")"

# Codex, on PR #68: the first version of this exemption skipped check_note
# ENTIRELY, which also dropped the required-keys, title-matches-filename and
# updated-date checks -- while the comment beside it claimed the exemption was
# "frontmatter-only". For CLAUDE.md that difference is invisible: a file with no
# frontmatter never reaches those checks anyway. It is visible exactly here -- a
# genuine note that happens to be called README.md and DOES carry frontmatter
# was silently excused from the entire contract.
#
# This case pins the narrow reading: under the broad implementation it exits 0
# with nothing checked, so it is what keeps `fm_optional` honest.
# Codex round 4: every frontmatter-bearing case used README.md, so an
# implementation that ran the full checks for README and returned early for the
# other three passed the whole suite. Round 5: parameterising only the title
# case left the same hole one rung narrower - required-keys and updated-date
# were still README-only, so an implementation that ran the title check for all
# four and those two for README alone passed 39 of 39. Every frontmatter-bearing
# case below is parameterised over all four names, so each check is pinned for
# each name independently.
#
# Codex round 3: the title case alone still left a wrong implementation that
# runs ONLY the title check for an exempt file and skips the rest. The other
# two cases pin those checks separately, each naming its own violation - a
# guard that blocked the file for some other reason is not a pass.
for exempt_name in CLAUDE.md README.md AGENTS.md GEMINI.md; do
  # The title must equal the filename stem in the two cases that are NOT about
  # the title, or the title check fires instead of the one being pinned.
  stem="${exempt_name%.md}"

  fm_note="---
type: concept
title: \"not-the-filename\"
created: 2026-08-20
updated: $today
status: seed
tags:
  - concept
---
A real note that happens to be called $exempt_name."
  f=$(write_and_payload "wiki/concepts/$exempt_name" "$fm_note")
  check "$exempt_name WITH frontmatter is fully contract-checked" 2 "$(run_guard "$f" "$home_on_win")"
  check_stderr_has "and for $exempt_name it is the title check that caught it" \
    "does not match filename" "$(guard_stderr "$f" "$home_on_win")"

  fm_missing="---
type: concept
title: \"$stem\"
created: 2026-08-20
updated: $today
tags:
  - concept
---
Required key status: is absent."
  f=$(write_and_payload "wiki/concepts/$exempt_name" "$fm_missing")
  check "$exempt_name is still held to the required keys" 2 "$(run_guard "$f" "$home_on_win")"
  check_stderr_has "and for $exempt_name the missing key is named" \
    "MISSING required frontmatter" "$(guard_stderr "$f" "$home_on_win")"

  fm_stale="---
type: concept
title: \"$stem\"
created: 2026-08-20
updated: 2020-01-01
status: seed
tags:
  - concept
---
The updated date is stale."
  f=$(write_and_payload "wiki/concepts/$exempt_name" "$fm_stale")
  check "$exempt_name is still held to the updated date" 2 "$(run_guard "$f" "$home_on_win")"
  check_stderr_has "and for $exempt_name the stale date is named" \
    "bump to" "$(guard_stderr "$f" "$home_on_win")"
done

echo "== vault_guard.py: config-off means silent (sabotage: prove the toggle matters) =="

f=$(write_and_payload "wiki/concepts/no-frontmatter-2.md" "Still no frontmatter block.")
check "all toggles off: the same broken note is allowed" 0 "$(run_guard "$f" "$home_off_win")"

echo "== vault_guard.py: the DEFAULTS, under a config with no 'guard' key =="

# Codex round 7: every case above runs under a config that writes all three
# toggles explicitly, so flipping any ONE default in main() - checkCanvas to
# OFF, requireFrontmatter to ON, asciiOnly to ON - passed all 57 of them. The
# defaults are a stated promise in seven places; nothing shipped could tell that
# promise from a lie. These run under $home_default, whose config has no
# "guard" key at all, and each pins exactly one default.

f=$(write_and_payload "wiki/canvases/default-broken.canvas" "{not valid json")
check "default config: checkCanvas defaults ON, so a malformed canvas is reported (exit 2)" 2 \
  "$(run_guard "$f" "$home_default_win")"
check_stderr_has "and it is the canvas parse failure that is reported" \
  "DOES NOT PARSE" "$(guard_stderr "$f" "$home_default_win")"

# A basename that is NOT in FRONTMATTER_EXEMPT_NAMES, or the exemption carries
# this case and a requireFrontmatter default flipped ON stays green.
f=$(write_and_payload "wiki/concepts/plain-note.md" "Just prose, no frontmatter block.")
check "default config: requireFrontmatter defaults OFF, so a bare note is allowed" 0 \
  "$(run_guard "$f" "$home_default_win")"
check_stderr_empty "and the bare note reports nothing at all" \
  "$(guard_stderr "$f" "$home_default_win")"

# Frontmatter that satisfies the whole contract - required keys, title equal to
# the filename stem, today's updated date - so the em dash is the ONLY thing
# wrong with this note. Without that, a requireFrontmatter default flipped ON
# blocks it for a frontmatter reason and the asciiOnly default stays unpinned.
default_ascii="---
type: concept
title: \"default-em-dash\"
created: 2026-08-20
updated: $today
status: seed
tags:
  - concept
---
Body has an em dash - right here: EMDASH"
default_ascii="${default_ascii/EMDASH/$'\xe2\x80\x94'}"
f=$(write_and_payload "wiki/concepts/default-em-dash.md" "$default_ascii")
check "default config: asciiOnly defaults OFF, so a non-ASCII note is allowed" 0 \
  "$(run_guard "$f" "$home_default_win")"
check_stderr_empty "and the non-ASCII note reports nothing at all" \
  "$(guard_stderr "$f" "$home_default_win")"

echo "== vault_guard.py: notesPrefix scopes the note contract =="

# Every frontmatter case above sits under "wiki/", which is exactly what
# notesPrefix is set to in the ON config, so none of them discriminates on it.
# Codex round 7: deleting the scoping check in check_note outright - the guard
# then demands the six-key contract of every .md in the vault, including
# scratch files, attachments and anything a non-note tool wrote - passed all 57
# cases. This file is inside the vault and outside notesPrefix; its basename is
# not frontmatter-exempt, it is not under templates/, and it is pure ASCII, so
# the note contract is the only rule that could fire here and it must not.
f=$(write_and_payload "attachments/stray-note.md" \
  "A scratch file outside notesPrefix. No frontmatter, by design.")
check "a note outside notesPrefix is not held to the frontmatter contract" 0 \
  "$(run_guard "$f" "$home_on_win")"
check_stderr_empty "and the out-of-prefix note reports nothing at all" \
  "$(guard_stderr "$f" "$home_on_win")"

echo "== python suites (own temp HOME, no live Obsidian, no sockets) =="

# Each of these is runnable on its own and exits non-zero on the first failed
# assertion set; the whole file counts as one case here, with its output shown
# only when it fails. They manage their own throwaway HOME internally, so no
# winpath conversion is needed - the paths they build never cross the bash
# boundary.
py_suite() {
  local desc="$1" script="$2" out rc
  out="$("$PY" "$DIR/_test/$script" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    echo "FAIL: $desc (exit $rc)"
    echo "$out"
  fi
}

py_suite "obsidian_common: multi-vault resolution" test_obsidian_common.py
py_suite "ports, collisions, identity, vault_ops CLI" test_vault_ops.py
py_suite "profiles: the three sets, detection, the 50k line, split breakage" test_vault_profiles.py
py_suite "the four bridge states, told apart" test_bridge_states.py

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
