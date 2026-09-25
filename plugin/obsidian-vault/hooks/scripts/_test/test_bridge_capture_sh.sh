#!/usr/bin/env bash
# Regression suite for the python-resolver WRAPPERS on the plugin's three
# non-blocking hooks: bridge-status.sh/.ps1 (SessionStart) and
# vault-capture.sh/.ps1 (SessionEnd/PreCompact). test_vault_guard_sh.sh covers
# the one hook that CAN block; until this file existed, nothing exercised
# python resolution on the other three at all - which is exactly the gap
# .crew/codemap/obsidian-vault.md's Landmines section names: "the two
# remaining naive wrappers ... still carry the naive one-liner". They no
# longer do; this pins it.
#
# All three hooks here fail OPEN on principle, not just in the code that was
# already there: none of SessionStart/SessionEnd/PreCompact has a blocking
# exit code the way PostToolUse's exit 2 does, so refusing a bad interpreter
# can only ever mean "skip this session's status/capture, loudly" - never
# "stop the session". The thing under test is the LOUD half of that, not the
# fail-open half, which was never in question.
#
# Sabotage-tested: the naive `command -v python3 || command -v python ||
# command -v py` resolver was put back in each of the four wrappers and the
# stub cases below went red (silent/wrong-exit) before this suite existed to
# require better. See test_vault_guard_sh.sh's header for the WindowsApps
# reproduction these stubs model; the same three stub shapes are reused here.
# Run: bash plugin/obsidian-vault/hooks/scripts/_test/test_bridge_capture_sh.sh
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE_SH="$DIR/bridge-status.sh"
BRIDGE_PS1="$DIR/bridge-status.ps1"
CAPTURE_SH="$DIR/vault-capture.sh"
CAPTURE_PS1="$DIR/vault-capture.ps1"

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
mkdir -p "$work/tools"
for t in dirname; do
  ln -s "$(command -v "$t")" "$work/tools/$t"
done
TOOLS="$work/tools"

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

# liar-stub: prints a plausible interpreter path and exits 0. The path must
# NOT exist on the test machine, or a weakened resolver that only checks "did
# it print something" could pick up a real interpreter behind it and the case
# would go red for a machine-dependent reason rather than the one under test.
liar_stub() {
  local dir="$work/$1" name="$2"
  mkdir -p "$dir"
  printf '#!/bin/sh\necho /opt/no-such-dir/python3\nexit 0\n' > "$dir/$name"
  chmod 755 "$dir/$name"
  printf '%s' "$dir"
}

# real-in-windowsapps: models a genuine Microsoft Store Python install, not a
# stub - behaves exactly like a real interpreter answering the probe, from a
# directory literally named WindowsApps, which is where a real Store
# install's sys.executable actually lives. See test_vault_guard_sh.sh's header
# for the 2026-09-24 regression this models: a resolver that rejects on a
# WindowsApps path SUBSTRING throws this out even though it works.
# A hand-written canned probe answer (main's original shape here) cannot
# ALSO run the real hook script when it launches the resolved interpreter a
# second time - it would print the same canned probe text regardless of the
# arguments it was actually given, so the hook's own behaviour would be the
# stub's hard-coded exit, not a real run. `exec "$PY" "$@"` makes it behave
# as a genuinely working interpreter no matter how it is invoked (probed
# with `-c ...`, or launched against the real script).
#
# TWO path components matter, and both are exercised here, same reasoning
# as test_vault_guard_sh.sh's own copy of this fixture (see that file's
# header): the call sites used to pass a label like "WindowsAppsRealBridge"
# / "WindowsAppsRealCapture", NOT a directory literally named WindowsApps -
# which happens to satisfy a bare substring reject (it CONTAINS
# "WindowsApps") but not a reintroduced EXACT PATH-SEGMENT reject
# (`*/WindowsApps/*`), the shape role-write-guard.sh's own resolver comment
# says was actually removed. Separately, `exec "$PY" "$@"` alone forwards
# straight through to this test's real system interpreter, whose own
# `sys.executable` is never under WindowsApps either, so a reintroduced
# reject on the RESOLVED path (not just the candidate) went untested too.
# Fixed the same way: the alias lives under a directory named exactly
# WindowsApps, and it execs a COPY (not a symlink) of the interpreter
# placed under a SECOND directory that also carries a literal WindowsApps
# segment. `$1` is now a LABEL used to keep each call site's fixture
# directories from colliding, not the leaf directory name itself - the leaf
# is always exactly "WindowsApps". `prefix` (the caller's per-hook probe
# token, `$3`) is still unused, kept as a parameter so call sites do not
# need to change their argument COUNT.
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

# -------------------------------------------------------- HOME + isolation --
# No obsidian config.json and no obsidian.json app registry: list_vaults()
# and resolve_vault_path() both come up empty, so bridge_status.py and
# vault_capture.py exit as pure no-ops with no filesystem writes and NO
# NETWORK CALL - safe to run with a genuinely resolved interpreter. Proof
# that the real interpreter under test actually EXECUTED (rather than the
# wrapper resolving cleanly and the script being a silent no-op either way)
# uses two different positive markers per script, since neither would
# otherwise leave evidence on a no-vault machine:
#   bridge-status.sh  -> claim() writes a marker to TMPDIR when a session_id
#                        is on the payload; assert the marker exists.
#   vault-capture.sh  -> `--selftest` prints "selftest FAIL: no vault
#                        resolved" to stderr and exits 1 when none is
#                        configured (it runs `vault_capture.py --selftest`
#                        as its trigger argument) - a script that never ran
#                        cannot produce that specific line.
home="$work/home"
mkdir -p "$home"
home_win="$(winpath "$home")"
tmpdir="$work/tmp"
mkdir -p "$tmpdir"
tmpdir_win="$(winpath "$tmpdir")"

# ------------------------------------------------------------------ runners --
RC=0
OUT=""
ERR=""
run_sh() {
  # $1 = script, $2 = PATH to run under, $3.. = args
  local script="$1" path="$2" outf="$work/.out" errf="$work/.err"
  shift 2
  PATH="$path" HOME="$home_win" TMPDIR="$tmpdir_win" \
    "$BASH_BIN" "$script" "$@" < /dev/null > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

run_sh_stdin() {
  # $1 = script, $2 = PATH, $3 = stdin payload
  local script="$1" path="$2" outf="$work/.out" errf="$work/.err"
  PATH="$path" HOME="$home_win" TMPDIR="$tmpdir_win" \
    "$BASH_BIN" "$script" < <(printf '%s' "$3") > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

run_ps1() {
  local script="$1" path="$2"; shift 2
  local outf="$work/.out" errf="$work/.err"
  # OS=Windows_NT is set deliberately, same reasoning as
  # test_vault_guard_sh.sh: a flavour guard standing this script down off
  # Windows must never silently stop this suite from testing anything.
  PATH="$path:$PWSH_DIR" HOME="$home_win" TMPDIR="$tmpdir_win" OS="Windows_NT" \
    "$PWSH" -NoProfile -File "$script" "$@" < /dev/null > "$outf" 2> "$errf"
  RC=$?
  OUT="$(cat "$outf")"
  ERR="$(cat "$errf")"
}

run_ps1_stdin() {
  local script="$1" path="$2" payload="$3"
  local outf="$work/.out" errf="$work/.err"
  PATH="$path:$PWSH_DIR" HOME="$home_win" TMPDIR="$tmpdir_win" OS="Windows_NT" \
    "$PWSH" -NoProfile -File "$script" < <(printf '%s' "$payload") > "$outf" 2> "$errf"
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

check_err_empty() {
  local desc="$1"
  if [ -z "$ERR" ]; then ok; else bad "$desc (expected silent stderr, got: [$ERR])"; fi
}

realpath_dir="$(real_dir realpy python3)"
store_dir="$(store_stub WindowsApps python3)"
silent_dir="$(silent_stub silentstub python3)"
liar_dir="$(liar_stub liarstub python3)"
real_winapps_bridge_dir="$(real_windowsapps_stub winapps-bridge python3 bridge-status-python:)"
real_winapps_capture_dir="$(real_windowsapps_stub winapps-capture python3 vault-capture-python:)"

# ================================================================ bridge-status.sh
echo "== bridge-status.sh: must run, with a working interpreter =="

sid="bridge-status-test-$$"
rm -f "$tmpdir/obsidian-vault-bridge-status-$sid.claim"
run_sh_stdin "$BRIDGE_SH" "$realpath_dir:$TOOLS" "{\"session_id\": \"$sid\"}"
check_exit "no vault configured: SessionStart is still a clean no-op" 0
check_err_empty "and a clean no-op session says nothing on stderr"
if [ -f "$tmpdir/obsidian-vault-bridge-status-$sid.claim" ]; then ok
else bad "the interpreter actually ran (claim marker was not written - bridge_status.py never executed)"
fi

echo "== bridge-status.sh: the WindowsApps stub must not pass for an interpreter =="

run_sh "$BRIDGE_SH" "$store_dir:$TOOLS"
check_exit "SessionStart cannot block; the stub still must not run" 0
check_err_has "and it says so instead of exiting silently" "no candidate is a usable interpreter"
check_err_has "and it names the rejected candidate" "python3"
check_err_lacks "and does NOT claim python is absent when it is on PATH" \
  "no python3/python/py interpreter found"

run_sh "$BRIDGE_SH" "$silent_dir:$TOOLS"
check_exit "a silent exit-0 stub is refused, not believed" 0
check_err_has "and refusing it is reported" "no candidate is a usable interpreter"

run_sh "$BRIDGE_SH" "$liar_dir:$TOOLS"
check_exit "a stub that prints a plausible path is refused" 0
check_err_has "and refusing it is reported" "did not answer the interpreter probe"

echo "== bridge-status.sh: a working interpreter under WindowsApps is ACCEPTED =="

sid2="bridge-status-winapps-test-$$"
rm -f "$tmpdir/obsidian-vault-bridge-status-$sid2.claim"
run_sh_stdin "$BRIDGE_SH" "$real_winapps_bridge_dir:$TOOLS" "{\"session_id\": \"$sid2\"}"
check_exit "a working interpreter under a WindowsApps path still runs" 0
check_err_empty "and it runs silently, like any other working interpreter"
if [ -f "$tmpdir/obsidian-vault-bridge-status-$sid2.claim" ]; then ok
else bad "the WindowsApps-path interpreter actually ran (claim marker was not written)"
fi

echo "== bridge-status.sh: nothing named python at all =="

run_sh "$BRIDGE_SH" "$TOOLS"
check_exit "no interpreter: stand down" 0
check_err_has "and the message is the ABSENCE one, distinct from the stub one" \
  "no python3/python/py interpreter found on PATH"

# ================================================================ vault-capture.sh
echo "== vault-capture.sh: must run, with a working interpreter =="

run_sh "$CAPTURE_SH" "$realpath_dir:$TOOLS" --selftest
check_exit "no vault configured: --selftest reports FAIL, proving python ran" 1
check_err_has "and it says why" "no vault resolved"

echo "== vault-capture.sh: the WindowsApps stub must not pass for an interpreter =="

run_sh "$CAPTURE_SH" "$store_dir:$TOOLS" --selftest
check_exit "SessionEnd/PreCompact cannot block; the stub still must not run" 0
check_err_has "and it says so instead of exiting silently" "no candidate is a usable interpreter"
check_err_lacks "and it is not the vault-resolution failure (python never ran)" "no vault resolved"

run_sh "$CAPTURE_SH" "$silent_dir:$TOOLS" --selftest
check_exit "a silent exit-0 stub is refused, not believed" 0
check_err_has "and refusing it is reported" "no candidate is a usable interpreter"

run_sh "$CAPTURE_SH" "$liar_dir:$TOOLS" --selftest
check_exit "a stub that prints a plausible path is refused" 0
check_err_has "and refusing it is reported" "did not answer the interpreter probe"

echo "== vault-capture.sh: a working interpreter under WindowsApps is ACCEPTED =="

run_sh "$CAPTURE_SH" "$real_winapps_capture_dir:$TOOLS" --selftest
check_exit "a working interpreter under a WindowsApps path still runs --selftest" 1
check_err_has "and it reports the real vault-resolution failure (python ran)" "no vault resolved"
check_err_lacks "and it is NOT rejected as an unusable candidate" \
  "no candidate is a usable interpreter"

echo "== vault-capture.sh: nothing named python at all =="

run_sh "$CAPTURE_SH" "$TOOLS" --selftest
check_exit "no interpreter: stand down" 0
check_err_has "and the message is the ABSENCE one, distinct from the stub one" \
  "no python3/python/py interpreter found on PATH"

# ============================================================== .ps1 flavour
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

  echo "== bridge-status.ps1: the same verdicts, PowerShell flavour =="

  sid_ps1="bridge-status-ps1-test-$$"
  rm -f "$tmpdir/obsidian-vault-bridge-status-$sid_ps1.claim"
  run_ps1_stdin "$BRIDGE_PS1" "$realpath_dir:$TOOLS" "{\"session_id\": \"$sid_ps1\"}"
  check_exit "ps1: no vault configured, still a clean no-op" 0
  if [ -f "$tmpdir/obsidian-vault-bridge-status-$sid_ps1.claim" ]; then ok
  else bad "ps1: the interpreter actually ran (claim marker was not written)"
  fi

  run_ps1 "$BRIDGE_PS1" "$store_dir:$TOOLS"
  check_exit "ps1: the Store stub is refused, not invoked" 0
  check_err_has "ps1: and stderr says no candidate was usable" \
    "no candidate is a usable interpreter"

  run_ps1 "$BRIDGE_PS1" "$silent_dir:$TOOLS"
  check_exit "ps1: a silent exit-0 stub is refused" 0
  check_err_has "ps1: and refusing it is reported" "no candidate is a usable interpreter"

  run_ps1 "$BRIDGE_PS1" "$liar_dir:$TOOLS"
  check_exit "ps1: a stub that prints a plausible path is refused" 0
  check_err_has "ps1: and refusing it is reported" "did not answer the interpreter probe"

  sid_ps1_winapps="bridge-status-ps1-winapps-test-$$"
  rm -f "$tmpdir/obsidian-vault-bridge-status-$sid_ps1_winapps.claim"
  run_ps1_stdin "$BRIDGE_PS1" "$real_winapps_bridge_dir:$TOOLS" "{\"session_id\": \"$sid_ps1_winapps\"}"
  check_exit "ps1: a working interpreter under WindowsApps still runs" 0
  if [ -f "$tmpdir/obsidian-vault-bridge-status-$sid_ps1_winapps.claim" ]; then ok
  else bad "ps1: the WindowsApps-path interpreter actually ran (claim marker was not written)"
  fi

  run_ps1 "$BRIDGE_PS1" "$TOOLS"
  check_exit "ps1: nothing named python: stand down" 0
  check_err_has "ps1: and the ABSENCE message is the distinct one" \
    "no python3/python/py interpreter found on PATH"

  echo "== vault-capture.ps1: the same verdicts, PowerShell flavour =="

  # vault-capture.ps1 always `exit 0` after invoking python (pre-existing,
  # not this ticket's scope - filed in TODO.md), unlike vault-capture.sh's
  # `exec`, which makes the shell's own exit code python's. So the PROOF the
  # interpreter ran is the stderr text alone here, not the exit code.
  run_ps1 "$CAPTURE_PS1" "$realpath_dir:$TOOLS" -Trigger "--selftest"
  check_exit "ps1: no vault configured, still exits 0 (pre-existing; see TODO.md)" 0
  check_err_has "ps1: but --selftest still says FAIL on stderr, proving python ran" \
    "no vault resolved"

  run_ps1 "$CAPTURE_PS1" "$store_dir:$TOOLS" -Trigger "--selftest"
  check_exit "ps1: SessionEnd/PreCompact cannot block; the stub still must not run" 0
  check_err_has "ps1: and stderr says no candidate was usable" \
    "no candidate is a usable interpreter"
  check_err_lacks "ps1: and it is not the vault-resolution failure (python never ran)" \
    "no vault resolved"

  run_ps1 "$CAPTURE_PS1" "$silent_dir:$TOOLS" -Trigger "--selftest"
  check_exit "ps1: a silent exit-0 stub is refused" 0
  check_err_has "ps1: and refusing it is reported" "no candidate is a usable interpreter"

  run_ps1 "$CAPTURE_PS1" "$liar_dir:$TOOLS" -Trigger "--selftest"
  check_exit "ps1: a stub that prints a plausible path is refused" 0
  check_err_has "ps1: and refusing it is reported" "did not answer the interpreter probe"

  run_ps1 "$CAPTURE_PS1" "$real_winapps_capture_dir:$TOOLS" -Trigger "--selftest"
  check_exit "ps1: a working interpreter under WindowsApps still exits 0 (pre-existing)" 0
  check_err_has "ps1: but --selftest still says FAIL, proving python ran" "no vault resolved"
  check_err_lacks "ps1: and it is NOT rejected as an unusable candidate" \
    "no candidate is a usable interpreter"

  run_ps1 "$CAPTURE_PS1" "$TOOLS" -Trigger "--selftest"
  check_exit "ps1: nothing named python: stand down" 0
  check_err_has "ps1: and the ABSENCE message is the distinct one" \
    "no python3/python/py interpreter found on PATH"
else
  # Counted, not just printed: run-tests.sh's `sh_suite` folds this whole
  # file into one PASS on a clean exit, and only echoes this script's OWN
  # stdout when it FAILS - so on a host with no pwsh, every .ps1 case above
  # (10 of them) was silently never run, and the parent's RESULT line looked
  # identical to a run where they all passed. Folding this into $SKIP, not
  # $PASS, and printing it in OUR OWN "RESULT" line is what lets run-tests.sh
  # forward a real count instead of manufacturing a false "all clear".
  SKIP=$((SKIP+1))
  echo "SKIP: bridge-status.ps1 / vault-capture.ps1 - no pwsh on PATH (12 cases not run)"
fi

echo
echo "RESULT: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ]
