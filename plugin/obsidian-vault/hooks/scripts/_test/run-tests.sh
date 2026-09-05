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
mkdir -p "$home_on/.claude/obsidian" "$home_off/.claude/obsidian"

# Config: turn every toggle ON so the suite exercises the checks, mirroring a
# vault whose CLAUDE.md declared all three rules - the defaults ship OFF, but
# the guard's LOGIC must still be correct when a vault turns them on. Built via
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

# These four basenames are agent-instruction files, not notes. They can never
# carry the six-key contract - a YAML header in CLAUDE.md is read as part of
# Claude's instructions - so demanding one is a false report on every legitimate
# edit. The guard is PostToolUse, so exit 2 does not prevent the write; it hands
# Claude stderr and tells it to go back and "fix" a file that is not broken.
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

# The exemption is frontmatter-only. An exempt basename is still held to every
# other rule the vault turned on, so the ASCII check must still fire here.
ascii_readme="README carrying an em dash that should still be caught: EMDASH"
ascii_readme="${ascii_readme/EMDASH/$'\xe2\x80\x94'}"
f=$(write_and_payload "wiki/ascii/README.md" "$ascii_readme")
check "an exempt basename is still ASCII-checked" 2 "$(run_guard "$f" "$home_on_win")"
check_stderr_has "and it is reported as an ASCII violation" \
  "NON-ASCII" "$(guard_stderr "$f" "$home_on_win")"
# The "not a frontmatter one" half has to be asserted, not just named: without
# this, stderr carrying both needles keeps the check above green.
check_stderr_lacks "and not as a frontmatter one" \
  "NO FRONTMATTER" "$(guard_stderr "$f" "$home_on_win")"

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
readme_note="---
type: concept
title: \"not-the-filename\"
created: 2026-08-20
updated: $today
status: seed
tags:
  - concept
---
A real note that happens to be called README.md."
f=$(write_and_payload "wiki/concepts/README.md" "$readme_note")
check "an exempt basename WITH frontmatter is fully contract-checked" 2 "$(run_guard "$f" "$home_on_win")"
# Exit 2 alone would also be satisfied by an implementation that rejects every
# frontmatter-bearing README outright, which is a different wrong answer. Name
# the violation, the same way the ASCII pair above does.
check_stderr_has "and it is the title check that caught it" \
  "does not match filename" "$(guard_stderr "$f" "$home_on_win")"

# Codex round 3: the title case alone still left a wrong implementation that
# runs ONLY the title check for an exempt file and skips the rest. These two
# pin the other checks independently, each naming its own violation.
readme_missing="---
type: concept
title: \"README\"
created: 2026-08-20
updated: $today
tags:
  - concept
---
Required key status: is absent."
f=$(write_and_payload "wiki/concepts/README.md" "$readme_missing")
check "an exempt basename is still held to the required keys" 2 "$(run_guard "$f" "$home_on_win")"
check_stderr_has "and the missing key is named" \
  "MISSING required frontmatter" "$(guard_stderr "$f" "$home_on_win")"

readme_stale="---
type: concept
title: \"README\"
created: 2026-08-20
updated: 2020-01-01
status: seed
tags:
  - concept
---
The updated date is stale."
f=$(write_and_payload "wiki/concepts/README.md" "$readme_stale")
check "an exempt basename is still held to the updated date" 2 "$(run_guard "$f" "$home_on_win")"
check_stderr_has "and the stale date is named" \
  "bump to" "$(guard_stderr "$f" "$home_on_win")"

echo "== vault_guard.py: config-off means silent (sabotage: prove the toggle matters) =="

f=$(write_and_payload "wiki/concepts/no-frontmatter-2.md" "Still no frontmatter block.")
check "all toggles off: the same broken note is allowed" 0 "$(run_guard "$f" "$home_off_win")"

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
