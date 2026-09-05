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
PY=$(command -v python3 || command -v python)
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

check() {
  local desc="$1" expect="$2" got="$3"
  if [ "$got" = "$expect" ]; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
    echo "FAIL: $desc (expected exit $expect, got $got)"
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
