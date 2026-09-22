#!/usr/bin/env bash
# Regression suite for the vault-guard WRAPPERS - vault-guard.sh and, where
# pwsh exists, vault-guard.ps1. run-tests.sh drives vault_guard.py directly
# with its own interpreter, so until this file existed nothing exercised the
# wrappers' python resolution at all, which is where the defect was.
#
# THE DEFECT, reproduced before it was fixed (2026-09-22, Linux):
#
#   PATH whose only python3 is a WindowsApps App Execution Alias stub
#   -> vault-guard.sh exits 49 with ZERO bytes on stderr.
#
# `command -v python3` answers "is there a FILE named python on PATH", and the
# Store alias is a real executable file, so the stand-down branch never ran
# and the alias was exec'd as the interpreter. It prints its Store message to
# STDOUT and exits 9009; 9009 & 0xFF = 49. PostToolUse shows stderr and treats
# any status but 2 as non-blocking, so the guard checked nothing and said
# nothing - while its own header promises "it must say so on stderr rather
# than exiting silently".
#
# THE STUB IS MODELLED, NOT OBSERVED. This file was written and run on Linux.
# The alias's two load-bearing properties - resolves as a real executable,
# does not behave like an interpreter - are what every case below depends on,
# and those are modelled from its documented behaviour. Three different stub
# shapes are used so no single guess about the real one carries the suite:
#
#   store-stub    prints the Store message on STDOUT, exits 9009 (the shape
#                 that produced the observed 49/empty-stderr reproduction)
#   silent-stub   no output at all, exits 0 (the shape crew's own
#                 test_role_write_guard.py models)
#   liar-stub     prints a plausible interpreter path, exits 0 (the
#                 neighbouring case: passes "did it print something")
#
# Sabotage-tested: the naive resolver was put back and the stub cases go red.
# Run: bash plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SH="$DIR/vault-guard.sh"
PS1="$DIR/vault-guard.ps1"

PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$(command -v "$cand")"; break; fi
done
if [ -z "$PY" ]; then
  echo "FATAL: no Python interpreter found. Tried python3, python, py on PATH." >&2
  echo "Git Bash ships without python3; install Python or put it on PATH." >&2
  exit 1
fi

BASH_BIN="${BASH:-$(command -v bash)}"

PASS=0
FAIL=0

winpath() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# ---------------------------------------------------------------- fixtures --
#
# `tools/` carries symlinks to the few external commands the wrapper itself
# needs, so a fixture PATH can exclude every python on the machine without
# also breaking the script under test. The first version of this reproduction
# used the stub directory ALONE and produced 328 bytes of stderr that were
# `dirname: command not found` - an artifact of the measurement, not the
# guard, and exactly the "check what you changed about the measurement"
# failure CLAUDE.md records.
mkdir -p "$work/tools"
for t in dirname; do
  ln -s "$(command -v "$t")" "$work/tools/$t"
done
TOOLS="$work/tools"

# A directory holding a genuine interpreter under the name given.
real_dir() {
  local dir="$work/$1" name="$2"
  mkdir -p "$dir"
  ln -s "$PY" "$dir/$name"
  printf '%s' "$dir"
}

# store-stub: the observed-failure shape. Message on STDOUT, exit 9009.
store_stub() {
  local dir="$work/$1" name="$2"
  mkdir -p "$dir"
  cat > "$dir/$name" <<'STUB'
#!/bin/sh
echo "Python was not found; run without arguments to install from the Microsoft Store: https://go.microsoft.com/fwlink/?linkID=2082640"
exit 9009
STUB
  chmod 755 "$dir/$name"
  printf '%s' "$dir"
}

# silent-stub: no output, exit 0.
silent_stub() {
  local dir="$work/$1" name="$2"
  mkdir -p "$dir"
  printf '#!/bin/sh\nexit 0\n' > "$dir/$name"
  chmod 755 "$dir/$name"
  printf '%s' "$dir"
}

# liar-stub: prints a plausible interpreter path and exits 0. Passes any
# resolver that only asks "did it print something".
#
# The path it prints must NOT exist on the test machine: an earlier version
# echoed /usr/bin/python3, so under sabotage the weakened resolver picked up a
# REAL interpreter and the case went red for a machine-dependent reason. A
# fixture that behaves differently depending on what is installed is not a
# fixture.
liar_stub() {
  local dir="$work/$1" name="$2"
  mkdir -p "$dir"
  printf '#!/bin/sh\necho /opt/no-such-dir/python3\nexit 0\n' > "$dir/$name"
  chmod 755 "$dir/$name"
  printf '%s' "$dir"
}

# ghost-python: answers the interpreter probe correctly but names an
# executable that does not exist, so resolution succeeds and the LAUNCH then
# fails. This is what the wrapper's exit-status check exists for; under the
# old `exec` form it was a bare numeric exit.
ghost_dir="$work/ghost"
mkdir -p "$ghost_dir"
cat > "$ghost_dir/python3" <<'STUB'
#!/bin/sh
printf 'vault-guard-python:%s' "/nonexistent/python-that-was-deleted"
exit 0
STUB
chmod 755 "$ghost_dir/python3"

# ------------------------------------------------------------- vault + HOME --
vault="$work/vault"
mkdir -p "$vault/wiki/canvases" "$vault/wiki/concepts"
vault_win="$(winpath "$vault")"

home="$work/home"
mkdir -p "$home/.claude/obsidian"
"$PY" - "$vault_win" "$home/.claude/obsidian/config.json" <<'PYEOF'
import json, sys
vault, out = sys.argv[1], sys.argv[2]
json.dump({"vaultPath": vault,
           "guard": {"asciiOnly": False, "requireFrontmatter": False,
                     "checkCanvas": True, "notesPrefix": "wiki/"}},
          open(out, "w", encoding="utf-8"))
PYEOF
home_win="$(winpath "$home")"

# checkCanvas is the one toggle that ships ON, so the canvas cases below are
# what a default install actually enforces - the right thing for a wrapper
# suite to lean on. The note contract has its own coverage in run-tests.sh.
write_payload() {
  local relpath="$1" content="$2" out="$3"
  local abspath="$vault/$relpath"
  mkdir -p "$(dirname "$abspath")"
  printf '%s' "$content" > "$abspath"
  "$PY" - "$(winpath "$abspath")" "$content" > "$out" <<'PYEOF'
import json, sys
print(json.dumps({"tool_input": {"file_path": sys.argv[1], "content": sys.argv[2]}}))
PYEOF
}

bad_canvas_payload="$work/payload-bad.json"
write_payload "wiki/canvases/broken.canvas" "{not valid json" "$bad_canvas_payload"

good_canvas_payload="$work/payload-good.json"
write_payload "wiki/canvases/fine.canvas" \
  '{"nodes":[{"id":"a","type":"text","text":"x"}],"edges":[]}' "$good_canvas_payload"

# ------------------------------------------------------------------ runners --
# Each run gets an explicit PATH so the machine's own python can never leak
# in, and an explicit HOME so no real config is read.
RC=0
OUT=""
ERR=""
run_sh() {
  # $1 = PATH to run under, $2 = payload file
  local outf="$work/.out" errf="$work/.err"
  # bash by ABSOLUTE path: the fixture PATH deliberately carries nothing but
  # the stub/real directories and tools/, so a bare `bash` here resolves to
  # nothing and every case fails as 127 with the harness's own error on
  # stderr - a measurement artifact that looks exactly like a guard failure.
  PATH="$1" HOME="$home_win" "$BASH_BIN" "$SH" < "$2" > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

run_ps1() {
  local outf="$work/.out" errf="$work/.err"
  # OS=Windows_NT is set deliberately. A flavour guard standing this script
  # down off Windows is in flight on another branch; without this the suite
  # would silently stop testing anything the moment that lands, which is the
  # worst failure mode a regression suite has.
  PATH="$1:$PWSH_DIR" HOME="$home_win" OS="Windows_NT" \
    "$PWSH" -NoProfile -File "$PS1" < "$2" > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

ok() { PASS=$((PASS+1)); }
bad() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

check_exit() {
  local desc="$1" expect="$2"
  if [ "$RC" = "$expect" ]; then ok; else bad "$desc (expected exit $expect, got $RC)"; fi
}

check_exit_not() {
  local desc="$1" forbidden="$2"
  if [ "$RC" != "$forbidden" ]; then ok; else bad "$desc (exit was $forbidden)"; fi
}

check_err_has() {
  local desc="$1" needle="$2"
  case "$ERR" in
    *"$needle"*) ok ;;
    *) bad "$desc (stderr lacked '$needle'; stderr was: [$ERR])" ;;
  esac
}

check_err_lacks() {
  local desc="$1" needle="$2"
  case "$ERR" in
    *"$needle"*) bad "$desc (stderr contained '$needle'; stderr was: [$ERR])" ;;
    *) ok ;;
  esac
}

check_err_nonempty() {
  local desc="$1"
  if [ -n "$ERR" ]; then ok; else bad "$desc (stderr was EMPTY - the silent failure this suite exists for)"; fi
}

check_err_empty() {
  local desc="$1"
  if [ -z "$ERR" ]; then ok; else bad "$desc (expected silent stderr, got: [$ERR])"; fi
}

# =============================================================== vault-guard.sh
echo "== vault-guard.sh: must BLOCK, with a working interpreter =="

realpath_dir="$(real_dir realpy python3)"
run_sh "$realpath_dir:$TOOLS" "$bad_canvas_payload"
check_exit "malformed canvas blocks" 2
check_err_has "and the violation is named on stderr" "DOES NOT PARSE"
check_err_lacks "and it is not reported as an interpreter problem" "standing down"

echo "== vault-guard.sh: must ALLOW, with a working interpreter =="

run_sh "$realpath_dir:$TOOLS" "$good_canvas_payload"
check_exit "well-formed canvas is allowed" 0
check_err_empty "and a clean write says nothing on stderr"

echo "== vault-guard.sh: the WindowsApps stub must not pass for an interpreter =="

# The reproduction case, asserted in the three ways it failed: it must not
# exit 49, it must not be silent, and it must name the candidate it refused.
store_dir="$(store_stub WindowsApps python3)"
run_sh "$store_dir:$TOOLS" "$bad_canvas_payload"
check_exit_not "the Store stub is not exec'd as the interpreter" 49
check_exit "and the guard stands down rather than passing the status on" 0
check_err_nonempty "and it does NOT exit silently"
check_err_has "and stderr says no candidate was usable" "no candidate is a usable interpreter"
check_err_has "and stderr names the rejected candidate" "python3"
check_err_lacks "and does NOT claim python is absent when it is on PATH" \
  "no python3/python/py interpreter found"

# The path filter alone would carry the case above. This one is the same stub
# NOT under a WindowsApps directory, so only the execute-and-read-back probe
# can reject it - a resolver that pattern-matches the path and skips the probe
# passes the case above and fails this one.
plain_store_dir="$(store_stub plainstore python3)"
run_sh "$plain_store_dir:$TOOLS" "$bad_canvas_payload"
check_exit_not "a Store-shaped stub outside a WindowsApps path is not exec'd" 49
check_exit "and the guard stands down" 0
check_err_has "and says the candidate was not usable" "no candidate is a usable interpreter"

silent_dir="$(silent_stub silentstub python3)"
run_sh "$silent_dir:$TOOLS" "$bad_canvas_payload"
check_exit "a stub that exits 0 with no output is refused, not believed" 0
check_err_has "and refusing it is reported" "no candidate is a usable interpreter"
check_err_lacks "and the canvas is NOT reported as clean" "DOES NOT PARSE"

liar_dir="$(liar_stub liarstub python3)"
run_sh "$liar_dir:$TOOLS" "$bad_canvas_payload"
check_exit "a stub that prints a plausible path and exits 0 is refused" 0
check_err_has "and refusing it is reported" "did not answer the interpreter probe"

echo "== vault-guard.sh: a real interpreter behind a stub still wins =="

# Name order, not PATH order: bash's `command -v python3` takes the FIRST
# python3 and then moves to the NEXT NAME. So a real `python` after a stub
# `python3` is found...
mixed_real="$(real_dir mixedreal python)"
run_sh "$store_dir:$mixed_real:$TOOLS" "$bad_canvas_payload"
check_exit "stub python3 + real python: the real one runs and blocks" 2
check_err_has "and the violation is named" "DOES NOT PARSE"

# ...while a second python3 further down PATH is NOT, because `command -v`
# never searches the same name twice. That is bash's behaviour, mirrored on
# purpose so the two shell flavours cannot reach different verdicts on one
# machine (crew shipped that divergence once). It is a limitation, and the
# thing that makes it acceptable is that it is LOUD.
shadowed_real="$(real_dir shadowedreal python3)"
run_sh "$store_dir:$shadowed_real:$TOOLS" "$bad_canvas_payload"
check_exit "stub python3 shadowing a real python3: stands down" 0
check_err_nonempty "and says so rather than failing silently"
check_err_has "and names it as an unusable candidate, not as absence" \
  "no candidate is a usable interpreter"

echo "== vault-guard.sh: nothing named python at all =="

run_sh "$TOOLS" "$bad_canvas_payload"
check_exit "no interpreter: stand down" 0
check_err_has "and the message is the ABSENCE one, distinct from the stub one" \
  "no python3/python/py interpreter found on PATH"
check_err_lacks "and it does not claim a candidate was rejected" \
  "no candidate is a usable interpreter"

echo "== vault-guard.sh: resolved, then could not be launched =="

run_sh "$ghost_dir:$TOOLS" "$bad_canvas_payload"
check_exit "a resolved interpreter that cannot launch: stand down, not blocked" 0
check_err_has "and the failure to reach a verdict is stated" \
  "did not complete the check"
check_err_has "and it says the write went unchecked" "NOT checked"

# =============================================================== vault-guard.ps1
PWSH="$(command -v pwsh 2>/dev/null || true)"
if [ -n "$PWSH" ]; then
  PWSH_DIR="$(dirname "$PWSH")"
  echo "== vault-guard.ps1: the same three verdicts, PowerShell flavour =="

  run_ps1 "$realpath_dir:$TOOLS" "$bad_canvas_payload"
  check_exit "ps1 must-block: malformed canvas" 2
  check_err_has "ps1: and the violation is named" "DOES NOT PARSE"

  run_ps1 "$realpath_dir:$TOOLS" "$good_canvas_payload"
  check_exit "ps1 must-allow: well-formed canvas" 0

  run_ps1 "$store_dir:$TOOLS" "$bad_canvas_payload"
  check_exit "ps1: the Store stub is refused, not invoked" 0
  check_err_nonempty "ps1: and it does NOT exit silently"
  check_err_has "ps1: and stderr says no candidate was usable" \
    "no candidate is a usable interpreter"

  run_ps1 "$silent_dir:$TOOLS" "$bad_canvas_payload"
  check_exit "ps1: a silent exit-0 stub is refused" 0
  check_err_has "ps1: and refusing it is reported" "no candidate is a usable interpreter"

  run_ps1 "$liar_dir:$TOOLS" "$bad_canvas_payload"
  check_exit "ps1: a stub that prints a plausible path is refused" 0
  check_err_has "ps1: and refusing it is reported" "did not answer the interpreter probe"

  run_ps1 "$TOOLS" "$bad_canvas_payload"
  check_exit "ps1: nothing named python: stand down" 0
  check_err_has "ps1: and the ABSENCE message is the distinct one" \
    "no python3/python/py interpreter found on PATH"
else
  echo "== vault-guard.ps1: SKIPPED, no pwsh on PATH =="
fi

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
