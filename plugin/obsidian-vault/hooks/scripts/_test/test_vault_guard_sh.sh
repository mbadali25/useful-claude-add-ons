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
# A FIFTH shape, added 2026-09-24, models the opposite defect: a resolver that
# rejects on a WindowsApps path SUBSTRING throws out a genuine Store Python
# install too, because a real Store interpreter's own sys.executable lives
# under that path. `real-windowsapps-stub` behaves exactly like a real
# interpreter (parses the probe, exits 0, reports itself) from a directory
# literally named WindowsApps, and must be ACCEPTED.
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
SKIP=0

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

# real-in-windowsapps: models a genuine Microsoft Store Python install, not a
# stub. It behaves EXACTLY like a real interpreter answering the probe (parses
# the -c program, exits 0, reports a real sys.executable) - the only thing
# unusual about it is that its own path lives under a directory literally
# named WindowsApps, which is where a real Store install's sys.executable
# actually lives
# (...\WindowsApps\PythonSoftwareFoundation.Python.3.x_<hash>\python.exe).
# A resolver that rejects on that path SUBSTRING (pre- or post-execution)
# throws this out even though it works; only a failing probe may reject it,
# and this probe succeeds. This is the 2026-09-24 regression: reproduced
# against a real PreToolUse Write payload where a working Python 3.14 was
# discarded untested because its path matched WindowsApps.
# A hand-written canned probe answer (main's original shape here) cannot
# ALSO run vault_guard.py when the guard launches it a second time as the
# resolved interpreter - it would print the same canned probe text
# regardless of the arguments it was actually given, so the guard's own
# exit code would be the stub's hard-coded 0, not a real judgement. `exec
# "$PY" "$@"` makes it behave as a genuinely working interpreter no matter
# how it is invoked (probed with `-c ...`, or launched against
# vault_guard.py).
#
# TWO path components matter, and this fixture must exercise BOTH, because
# the 2026-09-24 regression removed TWO separate rejects, not one (see
# role-write-guard.sh's own resolver comment: "used to sit here on both
# $candidate above and $real here"). Before 2026-09-24 this called with a
# label like "WindowsAppsReal", NOT a directory literally named
# WindowsApps - "WindowsAppsReal" happens to satisfy a bare substring reject
# too (it contains "WindowsApps"), so the gap was invisible to a substring
# sabotage test, but a reintroduced `*/WindowsApps/*` EXACT PATH-SEGMENT
# reject - which is the shape role-write-guard.sh's own comment describes
# as the one actually removed - does not match "WindowsAppsReal" as a
# component, and would have passed the old fixture untested. Separately,
# `exec "$PY" "$@"` alone forwards to THIS TEST'S real system interpreter,
# whose own `sys.executable` is never under WindowsApps either - so a
# reintroduced reject on the RESOLVED ("real") path, not just the candidate
# one, was equally untested. Fixed by making BOTH literal: the alias lives
# under a directory named exactly WindowsApps, and it execs a COPY (not a
# symlink, which resolves straight through to wherever this test's real
# python actually lives) of the interpreter placed under a SECOND directory
# that also carries a literal WindowsApps segment - modelling the genuine
# Store shape where the alias forwards to another WindowsApps-rooted path.
real_windowsapps_stub() {
  local label="$1" name="$2"
  local alias_dir="$work/$label/WindowsApps"
  local real_dir_path="$work/$label-target/WindowsApps/PythonSoftwareFoundation.Python.3.x_hash"
  mkdir -p "$alias_dir" "$real_dir_path"
  cp "$PY" "$real_dir_path/python.exe"
  chmod 755 "$real_dir_path/python.exe"
  cat > "$alias_dir/$name" <<STUB
#!/bin/sh
exec "$real_dir_path/python.exe" "\$@"
STUB
  chmod 755 "$alias_dir/$name"
  printf '%s' "$alias_dir"
}

# ghost-python: answers the interpreter probe correctly but names an
# executable that cannot run the guard, so resolution succeeds and the LAUNCH
# then fails. This is what the wrapper's exit-status check exists for; under
# the old `exec` form it was a bare numeric exit. The named executable EXISTS:
# since the crew 1.0 burn-in (FAIL 3) the resolver refuses a sys.executable
# that does not, so a nonexistent one no longer gets as far as a launch -
# _test/test_python_probe_proof.py pins that refusal.
ghost_dir="$work/ghost"
mkdir -p "$ghost_dir"
printf '#!/bin/sh\nexit 7\n' > "$ghost_dir/not-an-interpreter"
chmod 755 "$ghost_dir/not-an-interpreter"
cat > "$ghost_dir/python3" <<STUB
#!/bin/sh
printf 'vault-guard-python:3:12:cpython:%s' "$ghost_dir/not-an-interpreter"
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

echo "== vault-guard.sh: a working interpreter under a WindowsApps path is ACCEPTED =="

# The regression this fixes: a genuine Store Python install answers the probe
# correctly, but a resolver that also rejects on a WindowsApps path substring
# throws it out anyway. Only the probe's own failure may reject a candidate.
real_winapps_dir="$(real_windowsapps_stub winapps-case python3)"
run_sh "$real_winapps_dir:$TOOLS" "$bad_canvas_payload"
check_exit "a working interpreter under WindowsApps still blocks the write" 2
check_err_has "and the violation is named on stderr" "DOES NOT PARSE"
check_err_lacks "and it is NOT rejected as an unusable candidate" \
  "no candidate is a usable interpreter"

echo "== vault-guard.sh: a real interpreter behind a stub still wins =="

# A real `python` after a stub `python3` is found...
mixed_real="$(real_dir mixedreal python)"
run_sh "$store_dir:$mixed_real:$TOOLS" "$bad_canvas_payload"
check_exit "stub python3 + real python: the real one runs and blocks" 2
check_err_has "and the violation is named" "DOES NOT PARSE"

# ...and so, since the crew 1.0 Windows burn-in, is a second python3 further
# down PATH. The resolver walks EVERY match of a name (`type -aP`), and
# vault-guard.ps1 walks the same order, so the two flavours still reach one
# verdict. This case used to assert a stand-down: on a host whose every name
# hits WindowsApps first, that rule never reached the real python.exe.
shadowed_real="$(real_dir shadowedreal python3)"
run_sh "$store_dir:$shadowed_real:$TOOLS" "$bad_canvas_payload"
check_exit "stub python3 ahead of a real python3: the real one runs and blocks" 2
check_err_has "and the violation is named" "DOES NOT PARSE"

# A WindowsApps alias that WORKS (Python installed behind it) is an
# interpreter. Where it lives never decides; the probe does.
working_alias="$(real_dir aliases/WindowsApps python3)"
run_sh "$working_alias:$TOOLS" "$bad_canvas_payload"
check_exit "a working WindowsApps alias is used, and blocks" 2
check_err_has "and the violation is named" "DOES NOT PARSE"

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

# ================================================ non-ASCII stdin round-trip --
# The wrapper's PATH-resolution defect (above) is not the only "unknown
# collapsing into the safe-looking value" this hook carried: vault_guard.py's
# `payload = json.load(sys.stdin)` decodes with whatever the PROCESS's
# locale/console code page says, not necessarily UTF-8. On Windows, without
# PYTHONUTF8=1, that is the ANSI code page - and decoding UTF-8 bytes as, say,
# cp1252 does not raise: three UTF-8 bytes for one em dash (U+2014) silently
# become three WRONG characters (a, EUR-sign, right-quote), and check_ascii
# reports the wrong codepoint entirely rather than failing loudly. Reproduced
# here with PYTHONIOENCODING=cp1252, which forces the same wrong-decode shape
# `sys.stdin` gets from a non-UTF-8 console code page, without needing a
# Windows machine to prove it.
#
# Two layers were added against this (see vault_guard.py's main() and
# vault-guard.sh's own `export PYTHONUTF8=1`), but only ONE of them is
# sabotage-tested BEHAVIOURALLY here, and this header said otherwise until
# corrected below: the python-level explicit decode, by calling
# vault_guard.py DIRECTLY (bypassing the wrapper, so the wrapper's own
# PYTHONUTF8=1 backstop is never in play for these cases) under a forced
# `PYTHONIOENCODING=cp1252`, then sabotaging that decode on a throwaway COPY
# and confirming the case goes red. The wrapper's own `export PYTHONUTF8=1`
# is checked only STATICALLY - a grep that the line still exists - because
# the behavioural claim a first version of this comment made for it
# ("removing the python-level fix, the wrapper's backstop alone still saves
# it") was written, tested, and found FALSE: an explicit PYTHONIOENCODING in
# the calling environment overrides PYTHONUTF8's encoding choice for every
# python stream, so the backstop cannot rescue a decode PYTHONIOENCODING has
# already corrupted. See the "MEASURED, not assumed" comment further down for
# the disproof and what the backstop actually protects instead.
ascii_home="$work/ascii-home"
mkdir -p "$ascii_home/.claude/obsidian"
"$PY" - "$vault_win" "$ascii_home/.claude/obsidian/config.json" <<'PYEOF'
import json, sys
vault, out = sys.argv[1], sys.argv[2]
json.dump({"vaultPath": vault,
           "guard": {"asciiOnly": True, "requireFrontmatter": False,
                     "checkCanvas": False, "notesPrefix": "wiki/"}},
          open(out, "w", encoding="utf-8"))
PYEOF
ascii_home_win="$(winpath "$ascii_home")"

# Written with ensure_ascii=False and encoded UTF-8 explicitly: a real hook
# payload on the wire carries the note's actual UTF-8 bytes, not a `\uXXXX`
# escape (json.dumps' DEFAULT), and only the raw-bytes shape can mis-decode
# under the wrong code page. Using the default helper above would have hidden
# the whole defect class inside an already-ASCII-safe escape sequence.
note_rel="wiki/concepts/ascii-roundtrip.md"
note_abs="$vault/$note_rel"
mkdir -p "$(dirname "$note_abs")"
printf 'em dash test \xe2\x80\x94 end\n' > "$note_abs"
ascii_payload="$work/payload-ascii.json"
"$PY" - "$(winpath "$note_abs")" "$ascii_payload" <<'PYEOF'
import json, sys
path, out = sys.argv[1], sys.argv[2]
content = "em dash test — end\n"
with open(out, "wb") as fh:
    fh.write(json.dumps({"tool_input": {"file_path": path, "content": content}},
                         ensure_ascii=False).encode("utf-8"))
PYEOF

echo "== vault_guard.py: non-ASCII stdin round-trip (direct, python-level fix) =="

run_direct_py() {
  # $1 = payload file. Bypasses the wrapper entirely - straight to the
  # TRACKED, real vault_guard.py - so this isolates its own decode from
  # vault-guard.sh's PYTHONUTF8=1 backstop. PYTHONUTF8 explicitly unset (not
  # just absent from this env block) in case the calling shell already
  # exports it. Never mutated - see run_direct_py_copy for the sabotage path.
  local outf="$work/.out" errf="$work/.err"
  env -u PYTHONUTF8 PYTHONIOENCODING=cp1252 HOME="$ascii_home_win" \
    "$PY" "$DIR/vault_guard.py" < "$1" > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

# A throwaway COPY the sabotage case below mutates, so the checked-out
# vault_guard.py is NEVER touched. An earlier version of this suite edited
# `$DIR/vault_guard.py` in place and restored it from a backup kept only
# inside `$work` (deleted by the EXIT trap) - an interrupt between the edit
# and the restore left the real checkout mutated with no backup to recover
# from, reproduced with SIGTERM. `obsidian_common.py` is copied alongside it
# because vault_guard.py inserts its OWN directory onto sys.path and imports
# that module from there; without a copy in $work too, the sandboxed script
# cannot even start.
vg_copy="$work/vault_guard_sandbox.py"
cp "$DIR/vault_guard.py" "$vg_copy"
cp "$DIR/obsidian_common.py" "$work/obsidian_common.py"

# Snapshot taken before any sabotage in this run - the baseline the later
# "tracked file was never touched" check compares against.
vg_pristine="$work/vault_guard.py.pristine"
cp "$DIR/vault_guard.py" "$vg_pristine"

run_direct_py_copy() {
  # $1 = payload file. Same shape as run_direct_py, but against the
  # SANDBOXED copy - use this and only this for anything that sabotages
  # vault_guard.py's source.
  local outf="$work/.out" errf="$work/.err"
  env -u PYTHONUTF8 PYTHONIOENCODING=cp1252 HOME="$ascii_home_win" \
    "$PY" "$vg_copy" < "$1" > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

# run_sh always uses $home_win (asciiOnly OFF, the shared fixture config
# above). The round-trip cases need asciiOnly ON, so they go through this
# instead - same wrapper, different HOME.
run_sh_ascii() {
  local outf="$work/.out" errf="$work/.err"
  PATH="$1" HOME="$ascii_home_win" "$BASH_BIN" "$SH" < "$2" > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

run_direct_py "$ascii_payload"
check_exit "asciiOnly blocks the em dash, decoded straight" 2
check_err_has "and the CORRECT codepoint is named" "U+2014"
check_err_lacks "and NOT the mojibake cp1252 would have produced" "U+00E2"

echo "== vault_guard.py: sabotage the python-level fix, on the SANDBOXED copy only =="

# "$PY", not a bare `python3` - Git Bash ships without one, and this suite
# already resolved a real interpreter into $PY at the top for exactly this
# reason; a bare `python3` here would have been the one line in this file
# that did not follow its own rule.
cp "$vg_pristine" "$vg_copy"  # fresh baseline for this sabotage test
"$PY" - "$vg_copy" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
# Two edits, not one: reverting only the parse line while leaving the raw
# stdin read in place would consume stdin TWICE (once into `raw`, discarded,
# then again - empty - by `json.load(sys.stdin)`), which fails for a
# different reason (no bytes left to read) than the bug this case exists to
# reproduce (locale-dependent decode). Both lines revert together to the
# pre-fix shape: a single `json.load(sys.stdin)`, decoded however the
# process's locale says - which is the actual historical bug.
read_needle = "raw = sys.stdin.buffer.read()"
parse_needle = 'payload = json.loads(raw.decode("utf-8", errors="surrogateescape"))'
assert read_needle in text, "fixture assumption broken: the stdin-read line moved"
assert parse_needle in text, "fixture assumption broken: the parse line moved"
text = text.replace(read_needle, "pass  # sabotage: stdin read merged into the line below")
text = text.replace(parse_needle, "payload = json.load(sys.stdin)")
open(path, "w", encoding="utf-8").write(text)
PYEOF

run_direct_py_copy "$ascii_payload"
case "$ERR" in
  *"U+2014"*) bad "sabotaged python-level fix should mis-decode, but still reported U+2014 correctly (stderr: [$ERR])" ;;
  *) ok ;;
esac

echo "== vault_guard.py: the TRACKED file was never touched =="

# The whole point of sabotaging $vg_copy instead of $DIR/vault_guard.py: this
# passes trivially because nothing here ever wrote to the tracked file, not
# because anything was restored. Checked against $vg_pristine - a snapshot
# taken before ANY sabotage in this run, at the top of this section - rather
# than `git show HEAD:...`, because the tracked file may legitimately be
# uncommitted mid-development; comparing against git HEAD would report a
# mutation on every ordinary dirty worktree, not just a real one.
diff -q "$vg_pristine" "$DIR/vault_guard.py" >/dev/null \
  && ok || bad "vault_guard.py in the worktree changed during this test run - it should never have been touched"

# MEASURED, not assumed: the obvious next case to write was "sabotage
# vault_guard.py's fix, keep vault-guard.sh's `export PYTHONUTF8=1`, confirm
# the backstop alone still saves the decode" - the shape every other backstop
# case in this file takes. Running it (not shown, since it does not hold)
# found the opposite: an explicit `PYTHONIOENCODING` in the CALLING
# environment overrides PYTHONUTF8's encoding choice for every python stream,
# stdin included, so `export PYTHONUTF8=1` does NOT rescue a stdin decode
# corrupted by an explicit PYTHONIOENCODING already set before the hook runs.
# That is real, documented CPython precedence, not a bug in this script - but
# it means PYTHONUTF8=1 only ever helps the "nothing else named an encoding,
# so python fell back to the process's default locale" case, which is what
# Windows actually hits (no PYTHONIOENCODING is normally set; the OS locale
# supplies the default). This sandbox has no non-UTF-8 default locale to
# reproduce THAT case behaviourally (`locale -a` here offers only C/POSIX,
# which python's own PEP 538 coercion turns into UTF-8 anyway, and a list of
# already-UTF-8 `*.utf8` locales) - so the claim above is not re-asserted as
# a passing case here. vault-guard.sh's own comment on `export PYTHONUTF8=1`
# was corrected to say exactly this after the disproof, rather than leaving
# the stronger, false claim in place. What IS checked, statically, is that
# the line still exists - so the defense-in-depth intent does not silently
# regress even though its Windows-only payoff cannot run in this suite.
if grep -q '^export PYTHONUTF8=1$' "$SH"; then ok
else bad "vault-guard.sh no longer sets PYTHONUTF8=1 before invoking python"
fi
if grep -q '\$env:PYTHONUTF8 = "1"' "$PS1"; then ok
else bad "vault-guard.ps1 no longer sets \$env:PYTHONUTF8 before invoking python"
fi

echo "== vault_guard.py: the python-level fix is what actually survives a bad PYTHONIOENCODING =="

# This is the case that DOES hold, and it is the one the round-trip cases
# above already exercised through the wrapper (which also sets
# PYTHONIOENCODING=cp1252 no differently from a bare python invocation,
# since - per the finding above - the wrapper's own PYTHONUTF8=1 cannot
# override it either). Restated here explicitly as the fix that matters:
# `sys.stdin.buffer.read().decode("utf-8")` never consults PYTHONIOENCODING
# at all, because it never asks for a decoded text stream in the first
# place - it decodes the bytes itself.
export PYTHONIOENCODING=cp1252
run_sh_ascii "$realpath_dir:$TOOLS" "$ascii_payload"
unset PYTHONIOENCODING
check_exit "wrapper + fixed python: blocks the em dash even under a forced bad PYTHONIOENCODING" 2
check_err_has "and still names the correct codepoint" "U+2014"

echo "== vault_guard.py: an invalid UTF-8 byte in the content must still BLOCK =="

# Not a decode question this time - a single byte that is not valid UTF-8 AT
# ALL (0xFF can never start a UTF-8 sequence), the case `errors=` exists for.
# `bad \xff\xe2\x80\x94 x`: the invalid byte AND a valid em dash in the same
# payload, so a regression that only re-breaks the em dash half would still
# be caught even if the invalid byte were somehow tolerated.
note_bad_abs="$vault/wiki/concepts/invalid-utf8.md"
note_bad_payload="$work/payload-invalid-utf8.json"
mkdir -p "$(dirname "$note_bad_abs")"

# The note on disk carries the same invalid byte - it must exist for
# `edited_paths` to consider it, even though `check_ascii` prefers the
# payload's own `content` (below) when present.
"$PY" - "$note_bad_abs" <<'PYEOF'
import sys
with open(sys.argv[1], "wb") as fh:
    fh.write(b"bad \xff\xe2\x80\x94 x")
PYEOF

# The payload's own JSON, built as raw bytes rather than via json.dumps -
# json.dumps cannot encode a byte that is not valid Unicode at all, and that
# is exactly the byte this case needs to carry.
"$PY" - "$note_bad_abs" "$note_bad_payload" <<'PYEOF'
import json, sys
note_path, out = sys.argv[1], sys.argv[2]
content = b"bad \xff\xe2\x80\x94 x"
prefix = b'{"tool_input": {"file_path": '
mid = b', "content": "'
suffix = b'"}}'
path_json = json.dumps(note_path).encode("utf-8")
with open(out, "wb") as fh:
    fh.write(prefix + path_json + mid + content + suffix)
PYEOF

run_direct_py "$note_bad_payload"
check_exit "invalid UTF-8 byte: still blocks, as before this change" 2
check_err_has "and names the invalid byte as a synthetic codepoint" "U+DCFF"
check_err_has "and the valid em dash alongside it is still named correctly" "U+2014"

echo "== vault_guard.py: sabotage removes surrogateescape - degrades to a LOUD stand-down, not silence =="

cp "$vg_pristine" "$vg_copy"  # fresh baseline for this sabotage test
"$PY" - "$vg_copy" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
needle = 'payload = json.loads(raw.decode("utf-8", errors="surrogateescape"))'
assert needle in text, "fixture assumption broken: the fix text moved"
text = text.replace(needle, 'payload = json.loads(raw.decode("utf-8"))')
open(path, "w", encoding="utf-8").write(text)
PYEOF

run_direct_py_copy "$note_bad_payload"
check_exit "sabotaged: no longer blocks the invalid byte (fails OPEN, not closed)" 0
check_err_has "but it is LOUD about not having checked, not silent" "NOT checked"
check_err_lacks "and does not misreport this as a clean pass" "DOES NOT PARSE"

diff -q "$vg_pristine" "$DIR/vault_guard.py" >/dev/null \
  && ok || bad "vault_guard.py in the worktree changed during the invalid-UTF-8 sabotage - it should never have been touched"

# =============================================================== vault-guard.ps1
PWSH="$(command -v pwsh 2>/dev/null || true)"
if [ -n "$PWSH" ]; then
  # Isolated, not $(dirname "$PWSH") directly: on GitHub's ubuntu-latest image
  # pwsh lives at /usr/bin/pwsh, which is also where the system's real
  # python3 lives - appending that whole directory to a fixture PATH meant to
  # simulate "no usable interpreter" leaks a real, working python3 into every
  # such case, so the guard finds it, runs for real, and every must-refuse
  # case turns into a false PASS-through instead of the expected stand-down.
  # A directory holding nothing but a symlink to pwsh keeps the fixture PATH
  # able to launch pwsh without also handing it a real interpreter.
  PWSH_DIR="$work/pwsh-only"
  mkdir -p "$PWSH_DIR"
  ln -sf "$PWSH" "$PWSH_DIR/pwsh"
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

  run_ps1 "$real_winapps_dir:$TOOLS" "$bad_canvas_payload"
  check_exit "ps1: a working interpreter under WindowsApps still blocks" 2
  check_err_has "ps1: and the violation is named" "DOES NOT PARSE"

  # The two crew 1.0 burn-in cases, same verdicts as the .sh above: a
  # second python3 behind a stub is reached, and a WORKING WindowsApps alias
  # is used rather than skipped by its path.
  run_ps1 "$store_dir:$shadowed_real:$TOOLS" "$bad_canvas_payload"
  check_exit "ps1: stub python3 ahead of a real python3: the real one blocks" 2

  run_ps1 "$working_alias:$TOOLS" "$bad_canvas_payload"
  check_exit "ps1: a working WindowsApps alias is used, and blocks" 2

  run_ps1 "$TOOLS" "$bad_canvas_payload"
  check_exit "ps1: nothing named python: stand down" 0
  check_err_has "ps1: and the ABSENCE message is the distinct one" \
    "no python3/python/py interpreter found on PATH"
else
  # Counted, not just printed - same reasoning as
  # test_bridge_capture_sh.sh's twin of this branch: run-tests.sh's
  # `sh_suite` folds this whole file into one PASS on a clean exit and only
  # shows this script's OWN stdout when it FAILS, so a host with no pwsh
  # silently never runs any of the 9 .ps1 cases below and the parent's
  # RESULT line reads no differently than a run where they all passed.
  SKIP=$((SKIP+1))
  echo "SKIP: vault-guard.ps1 - no pwsh on PATH (9 cases not run)"
fi

echo
echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ]
