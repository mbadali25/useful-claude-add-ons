#!/usr/bin/env bash
# Regression suite for crew's hook scripts.
#
# The command guard (guard.sh / guard.ps1) was REMOVED in 0.19.52 - it blocked
# development work, and the two gates below are what crew still enforces. Its
# cases went with it; do not re-add them without re-adding the hook.
# Its successor, cloud-guard.sh (crew 1.0 T5, off unless guards.cloudGuard is
# set), has its own section near the end: it judges only the command a
# segment RUNS, never a word inside an argument, which is what sank the old one.
# promote-gate.sh and verify-gate.sh keep their coverage here, and both have
# had real regressions found by running them rather than reading them. This
# file exists so the next edit has a safety net.
#
#   bash hooks/scripts/_test/run-tests.sh
#
# Exit 0 = all pass. Exit 1 = something regressed.
#
# SABOTAGE-TEST THIS SUITE before trusting it: break a rule in promote-gate.sh on
# purpose, run this, and confirm it goes red. A check that has never failed has
# never been shown to be able to fail.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$(cd "$HERE/.." && pwd)"
PLUGIN="$(cd "$SCRIPTS/../.." && pwd)"

PASS=0; FAIL=0
fail() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
pass() { PASS=$((PASS+1)); }

# Resolve a python for building JSON payloads.
PY=$(command -v python3 || command -v python || command -v py) || {
  echo "SKIP: no python available to build test payloads" >&2; exit 0; }

# The command travels on STDIN, and that is not a style choice.
#
# Git Bash's MSYS runtime rewrites anything that looks like a POSIX path on its
# way to a native binary. Handed as `"$PY" - Bash '/usr/bin/ssh prod-web-1
# "ls"'`, the payload this function built said `C:/Program Files/Git/usr/bin/ssh
# prod-web-1 "ls"` -- so every `expect` line naming a command that STARTS with a
# path was asserting about a command the harness had silently rewritten, and the
# guard was answering about a program called `Program`.
#
# Measured here, all three channels, because the obvious repair does not work:
# an ENVIRONMENT variable is converted exactly as an argv value is
# (`CREW_TEST_CMD` came back rewritten too). Only stdin is passed through
# untouched. The tool name still travels in the environment -- `Bash` and
# `PowerShell` have no path shape -- because stdin is now spoken for.
json_cmd() {  # $1 = tool_name, $2 = command
  printf '%s' "$2" | CREW_TEST_TOOL="$1" "$PY" -c 'import os, sys, json; print(json.dumps({"tool_name": os.environ["CREW_TEST_TOOL"], "tool_input": {"command": sys.stdin.read()}}))'
}

# --- jq: covered, but bounded ----------------------------------------------
# promote-gate.sh pipes INTO `jq` for CMD extraction when it
# is on PATH - real, deliberate production behaviour, not
# a test artifact. On a machine with chocolatey's jq (a native, non-MSYS
# Win32 binary) this is also this suite's actual hang: `echo ... | jq ...`
# leaks a Windows handle on every invocation from Git Bash. MSYS-native tools
# do not - 120 back-to-back `echo | grep` calls in one bash session are
# clean - but jq alone wedges the SAME session after roughly 25-45 piped
# calls, and the wedge is session-wide: isolating each call in its own child
# bash does not postpone it. This file drives 90+ gate invocations, which
# crosses that line long before the suite finishes, and is why it has never
# completed here (confirmed by bisecting: swapping in plain `grep`/`cat`
# survives hundreds of calls; jq alone reproduces the exact hang and the
# "OSError ... Invalid argument" symptom in isolation, with nothing from
# promote-gate.sh's own logic involved).
#
# promote-gate.sh already has a real fallback for machines with no jq at all (the
# `elif PY=$(crew_py)` branch, a few lines below the jq branch) - CMD
# extraction is byte-identical either way, only the ~7-line CHOICE of
# extractor differs. So: prove the jq extractor itself still works with a
# small, fixed set of cases up front (well inside the failure threshold
# above), then hide jq from PATH for the rest of this file. That forces
# every remaining gate call through its already-real fallback branch, which
# exercises every actual rule below without ever invoking jq again. A
# developer's real shell, and Claude Code's actual hook launch, are
# untouched - only the PATH these test subshells see is scrubbed.
JQ_BIN=$(command -v jq 2>/dev/null || true)
FULL_PATH="$PATH"
if [ -n "$JQ_BIN" ]; then
  JQ_DIR="$(cd "$(dirname "$JQ_BIN")" && pwd -P)"
  # Compare RESOLVED directories, not the strings PATH happens to hold. On a
  # merged-/usr Linux - Ubuntu, Debian, Fedora, and every GitHub runner - /bin
  # is a symlink to /usr/bin, so PATH lists both and they are the same
  # directory. Dropping the literal "/usr/bin" left "/bin" behind, jq stayed
  # reachable, and this suite refused to run at all on CI while passing on a
  # Windows machine where the two paths are genuinely distinct. Resolving each
  # entry with `cd ... && pwd -P` is what makes the two spellings compare equal.
  #
  # Join with ":" BETWEEN fields, never after each one, and drop empty fields.
  # `ORS=":"` appended a trailing separator, and a trailing - or any empty -
  # PATH component means "the current directory" to every POSIX shell. So the
  # scrub meant to HIDE jq silently put CWD on the PATH for the rest of this
  # file, and `command -v jq` would then find any file named `jq` sitting in
  # whatever directory the suite happened to be launched from - including one
  # committed by a pull request, executed the moment a maintainer runs the
  # suite, with the guard's real tool_input JSON on its stdin.
  # SUBSTITUTE jq's directory, do not drop it. Dropping worked on Windows,
  # where jq sits in its own chocolatey bin. On Linux jq lives in /usr/bin
  # alongside python3, sh, grep and everything else the no-jq fallback needs,
  # so removing that directory did not test the fallback - it removed the
  # interpreter the fallback runs on, and the suite correctly refused with
  # "no WORKING python remains".
  #
  # Instead, mirror the directory into a temp dir as symlinks, minus `jq`
  # itself, and put the mirror where the original was. Everything else in that
  # bin stays reachable at the same PATH position; only jq disappears.
  # Exclude every spelling `command -v jq` can resolve, not just the bare
  # name. On Windows the binary is `jq.exe` and chocolatey adds a `jq.bat`
  # shim; mirroring those and skipping only "jq" left jq findable and the
  # scrub silently did nothing - measured, not assumed. The list stays
  # explicit so a `jq-1.7` or a `jqlang` beside it is still mirrored: those
  # are not what a bare `jq` resolves to, and hiding them would be a
  # different, unasked-for change.
  JQ_SHADOW=$(mktemp -d) || { echo "FATAL: mktemp -d failed" >&2; exit 1; }
  trap 'rm -rf "$JQ_SHADOW"' EXIT
  for _scrub_f in "$JQ_DIR"/*; do
    [ -e "$_scrub_f" ] || continue          # unmatched glob in an empty dir
    _scrub_b=${_scrub_f##*/}
    case $_scrub_b in
      jq|jq.exe|jq.EXE|jq.bat|jq.BAT|jq.cmd|jq.CMD|jq.com|jq.ps1) continue ;;
    esac
    ln -s "$_scrub_f" "$JQ_SHADOW/$_scrub_b" 2>/dev/null || true
  done
  if PATH="$JQ_SHADOW" command -v jq >/dev/null 2>&1; then
    echo "FATAL: the jq mirror still resolves jq - a spelling this loop does" >&2
    echo "       not exclude. Add it to the case above." >&2
    exit 1
  fi

  NOJQ_PATH=""
  _scrub_oldifs=$IFS
  IFS=":"
  for _scrub_dir in $PATH; do
    [ -n "$_scrub_dir" ] || continue
    _scrub_real=$(cd "$_scrub_dir" 2>/dev/null && pwd -P) || _scrub_real="$_scrub_dir"
    if [ "$_scrub_real" = "$JQ_DIR" ]; then
      # First spelling of jq's dir becomes the mirror; later spellings of the
      # same dir (a merged-/usr /bin -> /usr/bin symlink) are dropped, or they
      # would put the real jq back.
      case ":$NOJQ_PATH:" in
        *":$JQ_SHADOW:"*) ;;
        *) NOJQ_PATH="${NOJQ_PATH:+$NOJQ_PATH:}$JQ_SHADOW" ;;
      esac
      continue
    fi
    NOJQ_PATH="${NOJQ_PATH:+$NOJQ_PATH:}$_scrub_dir"
  done
  IFS=$_scrub_oldifs
  unset _scrub_oldifs _scrub_dir _scrub_real _scrub_f _scrub_b
else
  NOJQ_PATH="$PATH"
fi

if [ -n "$JQ_BIN" ]; then
  echo "== PATH scrub: hide jq to exercise the no-jq fallback =="
  # From here on, every guard()/pgate() call in this file runs with jq
  # hidden from PATH - see the note above for why.
  # The scrub removes jq's whole DIRECTORY, not just the jq binary, because
  # PATH has no finer granularity. On a layout that installs several tools into
  # one bin (chocolatey does exactly this) that directory can also hold python -
  # and promote-gate.sh's no-jq fallback NEEDS python. Without it the gate prints
  # "no jq and no python" and stands down, so every case below would assert
  # against a guard that never ran and the suite would go green while testing
  # nothing. Prove both halves of the scrub before trusting a single result.
  if PATH="$NOJQ_PATH" command -v jq >/dev/null 2>&1; then
    echo "FATAL: the PATH scrub did not hide jq ($JQ_BIN)." >&2
    echo "       Every case below would take the jq fast path, so the fallback" >&2
    echo "       this section exists to exercise would go untested." >&2
    exit 1
  fi
  # Walk crew_py's OWN resolution order (python3, python, py) and then RUN the
  # winner. Resolving is not enough: on Windows, `command -v python` succeeds on
  # the App Execution Alias in WindowsApps, a stub that opens the Microsoft
  # Store and is not an interpreter. crew_py hands that stub back, promote-gate.sh's
  # `$PY -c ...` produces nothing, CMD comes back empty, and `[ -z "$CMD" ]`
  # exits 0 - the guard stands down and every must-BLOCK case below silently
  # passes for the wrong reason. An existence check cannot see that; executing
  # it can.
  if ! PATH="$NOJQ_PATH" sh -c '
    for c in python3 python py; do
      command -v "$c" >/dev/null 2>&1 || continue
      # FIRST match wins, exactly as crew_py does - it returns the first name
      # that resolves and never tries the next one. So if this one does not
      # execute, the guard is dead even though a working interpreter may sit
      # further down the list; checking the rest would pass where crew_py fails.
      "$c" -c "print(1)" >/dev/null 2>&1 && exit 0
      exit 1
    done
    exit 1'; then
    echo "FATAL: with jq's directory ($JQ_DIR) hidden, no WORKING python remains." >&2
    echo "       promote-gate.sh would report 'no jq and no python' and exit 0 - standing" >&2
    echo "       down - so every must-BLOCK case below would pass against a guard" >&2
    echo "       that never ran." >&2
    exit 1
  fi
  export PATH="$NOJQ_PATH"
else
  echo "== PATH scrub SKIPPED - no jq on PATH, already testing the fallback =="
fi

echo "== verify-gate.sh =="
D=$(mktemp -d) || exit 1
(
  cd "$D" || exit 1
  git init -q .
  mkdir -p .crew sql
  echo '{}' > .crew/config.json
  cat > .crew/verify.json <<'EOF'
{"version":1,
 "rules":[{"paths":["**/*.tf"],"run":["true"]},
          {"paths":["**/*.py"],"run":["true"]},
          {"paths":["sql/**"],"run":["true"]}],
 "always":[],"default":[],"unmapped":"fail"}
EOF
  touch main.tf handler.py sql/proc.sql README.md
)
export CLAUDE_PROJECT_DIR="$D"

# Root-level main.tf must match "**/*.tf". fnmatch's * spans '/', so an
# unpatched gate silently skips every file that is not in a subdirectory.
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "verify-gate: unmapped README.md should fail the turn (root-level globs may not be matching)"

# A blocking Stop hook re-fires; without this check it blocks its own retry.
echo '{"stop_hook_active":true}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "0" ] && pass || fail "verify-gate: stop_hook_active must exit 0 or the session wedges"

# --- the matcher's two failure modes must be told apart -----------------------
# The gate used to report ANY non-zero status from the embedded python as
# ".crew/verify.json could not be parsed". It is not the only way that exec can
# fail, and the wrong diagnosis sends the reader to debug a healthy file. Both
# still fail CLOSED - the severity was never the bug.

# must-BLOCK, and must say PARSE: a genuinely corrupt verify.json (python exits 3
# from the explicit json.load guard).
CORRUPT=$(mktemp -d) || exit 1
(
  cd "$CORRUPT" || exit 1
  git init -q .
  mkdir -p .crew
  echo '{}' > .crew/config.json
  printf '{"rules": [ THIS IS NOT JSON' > .crew/verify.json
  touch main.tf
)
export CLAUDE_PROJECT_DIR="$CORRUPT"
OUT=$(echo '{}' | bash "$SCRIPTS/verify-gate.sh" 2>&1); RC=$?
[ "$RC" = "2" ] && pass || fail "verify-gate: a corrupt verify.json must block the turn (got $RC)"
case "$OUT" in
  *"could not be parsed"*) pass ;;
  *) fail "verify-gate: a corrupt verify.json must be REPORTED as a parse failure, got: $OUT" ;;
esac
unset CLAUDE_PROJECT_DIR

# must-BLOCK, and must NOT say PARSE: the matcher cannot run at all. Simulated by
# pointing CREW_PY at an interpreter that exits non-zero without ever reading the
# config - the same observable shape as the E2BIG exec failure this fix was for.
#
# The stubs must answer crew_py_strict's OWN proof (`-c 'import sys;
# print(sys.executable)'`) with their own absolute path and exit 0 - only then
# does crew_py_strict accept one of them as $PY, past the top-level check at
# verify-gate.sh's `PY=$(crew_py_strict) || ...`, so it is the MATCHER
# invocation (a different shape - `"$PY" - args << script`) that fails, which
# is the actual code path this case exists to exercise. A stub that exits 9
# unconditionally (the previous shape) fails crew_py_strict's proof too, so it
# never resolves to $PY at all and the matcher is never even reached - the
# hollow shape review round 6 caught: it was quietly testing "no python
# resolves", not "the matcher could not run", and a case arm was added here to
# paper over that instead of fixing the fixture.
UNRUNNABLE=$(mktemp -d) || exit 1
(
  cd "$UNRUNNABLE" || exit 1
  git init -q .
  mkdir -p .crew
  echo '{}' > .crew/config.json
  printf '{"version":1,"rules":[],"always":[],"default":[],"unmapped":"fail"}' > .crew/verify.json
  touch main.tf
  mkdir -p fakebin
  # crew_py resolves python3/python/py off PATH, so shadow it there rather than
  # inventing an override the gate does not have. Answers crew_py_strict's
  # proof with its OWN absolute path (so crew_py_strict accepts it as $PY),
  # then exits 9 on anything else, including the matcher's own `- args <<
  # script` invocation - the same observable shape as the E2BIG exec failure
  # this fix is for, and deliberately NOT 3, which is the parse status.
  cat > fakebin/python3 <<STUB
#!/bin/sh
if [ "\$1" = "-c" ] && [ "\$2" = "import sys; print(sys.executable)" ]; then
  printf '%s\n' "$UNRUNNABLE/fakebin/python3"
  exit 0
fi
exit 9
STUB
  cat > fakebin/python <<STUB
#!/bin/sh
if [ "\$1" = "-c" ] && [ "\$2" = "import sys; print(sys.executable)" ]; then
  printf '%s\n' "$UNRUNNABLE/fakebin/python"
  exit 0
fi
exit 9
STUB
  cat > fakebin/py <<STUB
#!/bin/sh
if [ "\$1" = "-c" ] && [ "\$2" = "import sys; print(sys.executable)" ]; then
  printf '%s\n' "$UNRUNNABLE/fakebin/py"
  exit 0
fi
exit 9
STUB
  chmod +x fakebin/python3 fakebin/python fakebin/py
)
export CLAUDE_PROJECT_DIR="$UNRUNNABLE"
SAVED_PATH="$PATH"
export PATH="$UNRUNNABLE/fakebin:$PATH"
OUT=$(echo '{}' | bash "$SCRIPTS/verify-gate.sh" 2>&1); RC=$?
[ "$RC" = "2" ] && pass || fail "verify-gate: a matcher that cannot run must still block (got $RC)"
case "$OUT" in
  *"could not be parsed"*)
    fail "verify-gate: a matcher that could not RUN was misreported as a parse failure: $OUT" ;;
  *"could not RUN the matcher"*) pass ;;
  *) fail "verify-gate: unrecognised message for an unrunnable matcher: $OUT" ;;
esac
export PATH="$SAVED_PATH"
unset CLAUDE_PROJECT_DIR

# must-ALLOW: a large changed-file list must not blow the exec. E2BIG counts argv
# PLUS the environment, so this pads the environment too - the measured failure
# was 74 files / 2.6KB of paths against a 7.9KB environment, which argv alone
# would not have reproduced.
BIG=$(mktemp -d) || exit 1
(
  cd "$BIG" || exit 1
  git init -q .
  mkdir -p .crew
  echo '{}' > .crew/config.json
  # `**` as well as `**/*.txt`: the fixture's own .crew/*.json files are changed
  # files too, and leaving them unmapped would fail this case for a reason that
  # has nothing to do with the size of the list it is here to measure.
  printf '{"version":1,"rules":[{"paths":["**/*.txt","**"],"run":["true"]}],"always":[],"default":[],"unmapped":"fail"}' > .crew/verify.json
  i=0
  while [ "$i" -lt 400 ]; do
    printf 'x' > "a-very-long-file-name-to-make-argv-large-$i.txt"
    i=$((i+1))
  done
)
export CLAUDE_PROJECT_DIR="$BIG"
export CREW_TEST_PAD="$(head -c 60000 /dev/zero 2>/dev/null | tr ' ' 'p')"
OUT=$(echo '{}' | bash "$SCRIPTS/verify-gate.sh" 2>&1); RC=$?
case "$OUT" in
  *"could not be parsed"*|*"could not RUN the matcher"*)
    fail "verify-gate: 400 changed files + a padded environment broke the matcher: $OUT" ;;
  *) pass ;;
esac
[ "$RC" = "0" ] && pass || fail "verify-gate: 400 mapped files should pass the gate (got $RC): $OUT"
unset CREW_TEST_PAD
unset CLAUDE_PROJECT_DIR


# --- scope report: must-ALLOW in every branch ------------------------------
# The scope layer added in crew 0.19.63 is REPORT-ONLY. verify-gate can exit 2,
# so the one thing that must never regress is the scope branch changing the
# exit code. These cases assert the gate's status is whatever it would have
# been, while the report itself is present and specific.
#
# The unknown branches are asserted too, and that is the point of the case
# rather than padding: a scope layer that prints an empty `outside-scope:` when
# it could not read the ticket is worse than none, because the empty line is
# also what "checked, nothing outside" looks like.
SCOPEFX=$(mktemp -d) || exit 1
(
  cd "$SCOPEFX" || exit 1
  git init -q .
  git config user.email t@t; git config user.name t
  mkdir -p .crew .work/tickets
  echo '{}' > .crew/config.json
  printf '{"version":1,"rules":[],"always":[],"default":[],"unmapped":"skip"}' > .crew/verify.json
  echo x > tracked.txt
  git add -A >/dev/null 2>&1; git commit -qm init >/dev/null 2>&1
  printf 'inside
' > in-scope.txt
  printf 'outside
' > wandered.txt
)

# (a) an open ticket that declares paths: the wandering file is NAMED, and the
#     gate's exit code is unchanged by saying so.
printf '| T-0001 | scope case | in progress |
' > "$SCOPEFX/.work/INDEX.md"
printf '## Scope
- touch: in-scope.txt
' > "$SCOPEFX/.work/tickets/T-0001.md"
export CLAUDE_PROJECT_DIR="$SCOPEFX"
OUT=$(echo '{}' | bash "$SCRIPTS/verify-gate.sh" 2>&1); RC=$?
[ "$RC" != "2" ] && pass || fail "verify-gate: the scope report must not block the turn (got $RC)"
case "$OUT" in
  *"wandered.txt"*)
    # And crew bookkeeping must NOT appear: a ticket edit is the process
    # working, not scope creep, and reporting it teaches people to skim.
    case "$OUT" in
      *".work/INDEX.md"*) fail "verify-gate: crew bookkeeping must be excluded from the scope report, got: $OUT" ;;
      *) pass ;;
    esac ;;
  *) fail "verify-gate: a file outside the ticket's declared paths must be named, got: $OUT" ;;
esac

# (b) ticket file missing: a DISTINCT sentence, never an empty report.
rm -f "$SCOPEFX/.work/tickets/T-0001.md"
OUT=$(echo '{}' | bash "$SCRIPTS/verify-gate.sh" 2>&1); RC=$?
[ "$RC" != "2" ] && pass || fail "verify-gate: a missing ticket file must not block (got $RC)"
case "$OUT" in
  *"is missing"*) pass ;;
  *) fail "verify-gate: a missing ticket file must say so, not report an empty scope, got: $OUT" ;;
esac

# (c) no open ticket at all: also its own sentence.
rm -f "$SCOPEFX/.work/INDEX.md"
OUT=$(echo '{}' | bash "$SCRIPTS/verify-gate.sh" 2>&1); RC=$?
[ "$RC" != "2" ] && pass || fail "verify-gate: no open ticket must not block (got $RC)"
case "$OUT" in
  *"no open ticket"*) pass ;;
  *) fail "verify-gate: with no ticket open the report must say so, got: $OUT" ;;
esac
unset CLAUDE_PROJECT_DIR

# (d) BACK-OFF SILENCE. When another flavour holds the lock this gate stands
#     aside and runs no checks, so any scope-shaped line would assert a check
#     that did not happen -- the same rule as (b) and (c), one level up. The
#     scope report lives INSIDE the lock for exactly this reason; an earlier
#     draft printed it before the lock and turned one Stop into two reports,
#     which four lock tests caught. This case is the standing guard on that.
printf '| T-0002 | back-off case | in progress |
' > "$SCOPEFX/.work/INDEX.md"
printf '## Scope
- touch: in-scope.txt
' > "$SCOPEFX/.work/tickets/T-0002.md"
mkdir -p "$SCOPEFX/.crew/.verify-gate.lock"
date +%s > "$SCOPEFX/.crew/.verify-gate.lock/at" 2>/dev/null
export CLAUDE_PROJECT_DIR="$SCOPEFX"
OUT=$(echo '{}' | bash "$SCRIPTS/verify-gate.sh" 2>&1); RC=$?
[ "$RC" = "0" ] && pass || fail "verify-gate: a held lock must back off cleanly (got $RC)"
case "$OUT" in
  *outside-scope*) fail "verify-gate: the back-off path must print NOTHING scope-shaped; it ran no checks, so a scope line claims one happened. Got: $OUT" ;;
  *) pass ;;
esac
rm -rf "$SCOPEFX/.crew/.verify-gate.lock"
unset CLAUDE_PROJECT_DIR

rm -rf "$SCOPEFX"

echo "== promote-gate.sh =="
PD=$(mktemp -d) || exit 1
trap 'rm -rf "$D" "$PD"' EXIT
(
  cd "$PD" || exit 1
  git init -q .
  git config user.email t@example.com
  git config user.name t
  mkdir -p .crew .work docs/runbooks scripts
  # .crew/ and .work/ are gitignored in a real repo. They must be, or the gate's
  # own marker file dirties the tree and blocks the next deploy.
  printf '.crew/\n.work/\n' > .gitignore
  cat > .crew/verify.json <<'EOF'
{"version":1,"rules":[],"always":[],"default":[],"unmapped":"warn",
 "environments":{
   "qa":{"deploy":["./scripts/deploy.sh qa"],"smoke":["true"],
         "rollback":"none","rollbackReason":"qa is rebuilt on every push","promotesTo":"production"},
   "staging":{"deploy":["./scripts/deploy.sh staging"],"smoke":["true"]},
   "production":{"requires":["qa"],"deploy":["./scripts/deploy.sh prod"],
                 "rollback":"docs/runbooks/rollback.md","requireHuman":true}}}
EOF
  echo '{}' > .crew/config.json
  printf '#!/bin/sh\necho deployed\n' > scripts/deploy.sh
  git add -A && git commit -qm init
)
export CLAUDE_PROJECT_DIR="$PD"
SHA=$(git -C "$PD" rev-parse --short HEAD)
RB="$PD/docs/runbooks/rollback.md"
ROW="$PD/.work/PROMOTIONS.md"

pgate() {
  json_cmd Bash "$1" | bash "$SCRIPTS/promote-gate.sh" >/dev/null 2>&1
  echo $?
}
pexpect() {
  local got; got=$(pgate "$2")
  if [ "$got" = "$1" ]; then pass; else fail "promote-gate want=$1 got=$got  $3"; fi
}
qa_row() {  # write an all-pass qa row for $1
  printf '| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n| now | qa | %s | pass | pass | pass | tester |\n' "$1" > "$ROW"
}

# Same jq note as above: promote-gate.sh has the identical jq/python-fallback
# split at its own CMD-extraction line. Prove the jq branch here too, with a
# couple of cases, then go straight back to the scrubbed PATH for the rest of
# this section - PATH is already scrubbed from the jq section above; this
# just restores it for these two calls and puts it back down immediately after.
if [ -n "$JQ_BIN" ]; then
  PATH="$FULL_PATH"
  pexpect 0 'npm test'               'jq fast path: unrelated command must pass straight through'
  pexpect 0 './scripts/deploy.sh qa' 'jq fast path: qa has no requires and an explicit rollback:none+reason - allowed'
  rm -f "$PD/.crew/.deploy-in-flight"
  PATH="$NOJQ_PATH"
fi

pexpect 0 'npm test'                 'an unrelated command must pass straight through'
pexpect 0 './scripts/deploy.sh qa'   'qa has no requires and an explicit rollback:none+reason - allowed'
rm -f "$PD/.crew/.deploy-in-flight"

# D1: an absent 'rollback' key must fail CLOSED, not open. "staging" declares
# no rollback key at all.
pexpect 2 './scripts/deploy.sh staging' 'no rollback key at all - must block, not silently allow'

# D1: rollback:"none" with no rollbackReason is still not an opt-out.
"$PY" - "$PD/.crew/verify.json" <<'PY'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg["environments"]["staging"]["rollback"] = "none"
json.dump(cfg, open(p, "w"))
PY
pexpect 2 './scripts/deploy.sh staging' 'rollback:none with no rollbackReason - must still block'

# D1: rollback:"none" plus a stated rollbackReason IS a valid opt-out.
"$PY" - "$PD/.crew/verify.json" <<'PY'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg["environments"]["staging"]["rollbackReason"] = "staging has no user traffic; redeploying dev is the rollback"
json.dump(cfg, open(p, "w"))
PY
pexpect 0 './scripts/deploy.sh staging' 'rollback:none with a stated rollbackReason - allowed'
rm -f "$PD/.crew/.deploy-in-flight"

# Each precondition proven in isolation: start from all-satisfied, break one.
printf 'last verified: %s\n' "$(date +%Y-%m-%d)" > "$RB"
( cd "$PD" && git add -A && git commit -qm runbook >/dev/null )
SHA=$(git -C "$PD" rev-parse --short HEAD)
qa_row "$SHA"
touch "$PD/.crew/.approved-production-$SHA"
rm -f "$PD/.crew/.deploy-in-flight"

pexpect 0 './scripts/deploy.sh prod' 'all preconditions satisfied - must ALLOW'
[ -f "$PD/.crew/.deploy-in-flight" ] && pass || fail "promote-gate: an allowed deploy must write .crew/.deploy-in-flight"

# break: no qa pass row for this sha
rm -f "$PD/.crew/.deploy-in-flight"; rm -f "$ROW"
pexpect 2 './scripts/deploy.sh prod' 'no qa all-pass row for this sha - must block'
qa_row "$SHA"

# break: qa row exists but a gate in it failed
rm -f "$PD/.crew/.deploy-in-flight"
printf '| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n| now | qa | %s | pass | FAIL | pass | tester |\n' "$SHA" > "$ROW"
pexpect 2 './scripts/deploy.sh prod' 'qa row records a FAILED gate - must block'
qa_row "$SHA"

# break: rollback runbook older than 90 days
rm -f "$PD/.crew/.deploy-in-flight"
printf 'last verified: 2020-01-01\n' > "$RB"
pexpect 2 './scripts/deploy.sh prod' 'rollback runbook verified over 90 days ago - must block'
printf 'last verified: %s\n' "$(date +%Y-%m-%d)" > "$RB"

# break: rollback runbook missing entirely
rm -f "$PD/.crew/.deploy-in-flight"; mv "$RB" "$RB.bak"
pexpect 2 './scripts/deploy.sh prod' 'rollback runbook missing - must block'
mv "$RB.bak" "$RB"

# break: no human approval marker
rm -f "$PD/.crew/.deploy-in-flight"; rm -f "$PD/.crew/.approved-production-$SHA"
pexpect 2 './scripts/deploy.sh prod' 'requireHuman with no approval marker - must block'
touch "$PD/.crew/.approved-production-$SHA"

# break: dirty working tree
rm -f "$PD/.crew/.deploy-in-flight"; echo "uncommitted" > "$PD/scratch.txt"
pexpect 2 './scripts/deploy.sh prod' 'dirty working tree - must block'
rm -f "$PD/scratch.txt"

echo "== verify-gate.sh: a deploy must be recorded =="
printf 'production %s\n' "$SHA" > "$PD/.crew/.deploy-in-flight"
rm -f "$ROW"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "verify-gate: a deploy with no PROMOTIONS row must not end the turn"

printf '| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n| now | production | %s | pass | pass | pass | tester |\n' "$SHA" > "$ROW"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ ! -f "$PD/.crew/.deploy-in-flight" ] && pass || fail "verify-gate: a recorded deploy must clear .deploy-in-flight"

echo "== emergency lane: the gates stand down =="
# Writes .crew/incident.json expiring $1 seconds from now. Negative = expired.
# The gates read expiresAtEpoch and nothing else; see crew_incident.py.
inc() {
  "$PY" - "$PD/.crew/incident.json" "$1" <<'PYEOF'
import json, sys, time
json.dump({"id": "INC-TEST", "summary": "suite", "standDown": True,
           "expiresAtEpoch": int(time.time()) + int(sys.argv[2])},
          open(sys.argv[1], "w"))
PYEOF
}
SKIPS="$PD/.crew/incident-skips.log"

inc 3600

# promote-gate: a deploy that must block with no incident is allowed with one,
# and every unmet precondition is written down instead.
rm -f "$PD/.crew/.deploy-in-flight" "$SKIPS" "$ROW"
pexpect 0 './scripts/deploy.sh prod' 'incident open: a deploy with no qa row must be ALLOWED'
grep -q 'promote' "$SKIPS" 2>/dev/null && pass \
  || fail "emergency: an allowed-but-ungated deploy must be recorded in incident-skips.log"
grep -q 'no all-pass row' "$SKIPS" 2>/dev/null && pass \
  || fail "emergency: the skip row must name the precondition that was unmet, not just the gate"

# verify-gate: the deploy-record check stands down too - an incident is exactly
# when a deploy goes out ahead of its paperwork - and records what is owed.
printf 'production %s\n' "$SHA" > "$PD/.crew/.deploy-in-flight"
rm -f "$ROW"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "0" ] && pass || fail "emergency: an open incident must not block the turn"
grep -q 'no row in .work/PROMOTIONS.md' "$SKIPS" 2>/dev/null && pass \
  || fail "emergency: an unrecorded deploy must be logged as owed"

# One turn, one row. Both flavours of the hook run on the same Stop on Windows,
# and Stop fires every turn, so an immediate repeat has to be dropped or a
# ten-turn incident reports twenty skipped gates.
BEFORE=$(wc -l < "$SKIPS")
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
AFTER=$(wc -l < "$SKIPS")
[ "$BEFORE" = "$AFTER" ] && pass \
  || fail "emergency: an identical consecutive skip must not be logged twice ($BEFORE -> $AFTER)"

# THE safety property. An expired incident is inert: no command is run and no
# file is touched to re-gate, the clock alone does it. Forgetting to close an
# incident is the realistic failure mode, and it must not leave a repository
# permanently ungated.
inc -60
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: an EXPIRED incident must gate again"
pexpect 2 './scripts/deploy.sh prod' 'expired incident: promote-gate must block again'

# A repo can forbid stand-downs outright: the incident is still declared, still
# recorded, still briefed - and the gates still gate.
inc 3600
printf '{"emergency":{"standDown":false}}\n' > "$PD/.crew/config.json"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: standDown false must keep the verify gate blocking"
pexpect 2 './scripts/deploy.sh prod' 'standDown false: promote-gate must block anyway'

# A malformed state file must fail CLOSED. A gate that cannot read its own
# state and assumes an incident is a gate that can be switched off with a typo.
printf '{ not json\n' > "$PD/.crew/incident.json"
echo '{}' > "$PD/.crew/config.json"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: an unparseable incident file must gate, not stand down"

# The same, with a FUTURE EPOCH inside the garbage. This is the case a grep or
# sed for the number gets wrong and ConvertFrom-Json gets right, so the two
# flavours disagreed and the bash one stood every gate down for a file that is
# not an incident at all. Codex review finding.
printf '{ not json "expiresAtEpoch": 9999999999 \n' > "$PD/.crew/incident.json"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: a future epoch inside INVALID json must not stand a gate down"
pexpect 2 './scripts/deploy.sh prod' 'a future epoch inside invalid json must not allow a deploy'

# Valid JSON, but the epoch is a string rather than a number. int() of "abc"
# must not throw its way into standing the gate down either.
printf '{"id":"INC-X","expiresAtEpoch":"not-a-number"}\n' > "$PD/.crew/incident.json"
echo '{}' | bash "$SCRIPTS/verify-gate.sh" >/dev/null 2>&1
[ "$?" = "2" ] && pass || fail "emergency: a non-numeric expiry must gate"

# A detail carrying a newline must not forge a second row in the skip log.
inc 3600
rm -f "$SKIPS"
"$PY" - "$PD/.crew/verify.json" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
cfg["environments"]["production"]["rollback"] = "none"
cfg["environments"]["production"]["rollbackReason"] = ""
json.dump(cfg, open(sys.argv[1], "w"))
PYEOF
pexpect 0 './scripts/deploy.sh prod' 'incident open: still allowed with a broken rollback declaration'
ROWS=$(wc -l < "$SKIPS")
FIELDS=$(awk -F'\t' 'NF!=3 {c++} END {print c+0}' "$SKIPS")
[ "$FIELDS" = "0" ] && pass \
  || fail "emergency: every skip row must have exactly 3 tab-separated fields (got $ROWS rows, $FIELDS malformed)"

rm -f "$PD/.crew/incident.json" "$SKIPS" "$PD/.crew/.deploy-in-flight"

unset CLAUDE_PROJECT_DIR

# jq is no longer on the leaking path here - nothing below this line pipes
# into it, so put PATH back to what the rest of this shell actually had.
PATH="$FULL_PATH"

echo "== claude-md-audit.sh =="
A="$PLUGIN/skills/crew-setup/scripts/claude-md-audit.sh"
if [ -f "$A" ]; then
  OUT=$(bash "$A" "$PLUGIN/skills/crew-setup/repo-claude-template.md" 2>&1)
  case "$OUT" in *"all template sections present"*) pass ;;
    *) fail "claude-md-audit: template should report all sections present" ;; esac

  L=$(mktemp -d); printf '# legacy\n\n## Commands\nx\n' > "$L/CLAUDE.md"
  OUT=$(bash "$A" "$L/CLAUDE.md" 2>&1); rm -rf "$L"
  case "$OUT" in *"MISSING  ## Promotion"*) pass ;;
    *) fail "claude-md-audit: a legacy file should report the Promotion section missing" ;; esac
fi

echo "== resolve-tools.sh: bash <script> resolution =="
RD=$(mktemp -d) || exit 1
(
  cd "$RD" || exit 1
  mkdir -p .crew _verify
  # Three call shapes the ticket named: bash script.sh, bash -x script.sh, and
  # a quoted path. Each script shells out to a tool that is invisible unless
  # resolve-tools.sh looks inside it.
  printf '#!/bin/sh\nterraform validate\nruff check .\n' > _verify/smoke.sh
  printf '#!/bin/sh\nsqlcmd -Q "select 1"\n' > "_verify/has space.sh"
  cat > .crew/verify.json <<'EOF'
{"version":1,"rules":[
  {"paths":["**/*.tf"],"run":["bash _verify/smoke.sh"],"why":"smoke wraps terraform+ruff"},
  {"paths":["sql/**"],"run":["bash -x \"_verify/has space.sh\""],"why":"quoted, flagged"}
 ],"always":[],"default":[],"unmapped":"warn"}
EOF
)
export CLAUDE_PROJECT_DIR="$RD"
OUT=$(bash "$PLUGIN/skills/crew-setup/scripts/resolve-tools.sh" 2>&1)
unset CLAUDE_PROJECT_DIR
echo "$OUT" | grep -qE '^terraform ' && pass || fail "resolve-tools: bash _verify/smoke.sh should surface terraform  ($OUT)"
echo "$OUT" | grep -qE '^ruff '      && pass || fail "resolve-tools: bash _verify/smoke.sh should surface ruff      ($OUT)"
echo "$OUT" | grep -qE '^sqlcmd '    && pass || fail "resolve-tools: bash -x \"quoted path\" should surface sqlcmd  ($OUT)"
rm -rf "$RD"

# ---------------------------------------------------------------------------
# pm_pulse.py -- a BLOCKING Stop hook, so it owes must-block/must-allow cases.
#
# The failure that matters most is not a missed finding, it is a LOOP: a Stop
# hook that blocks unconditionally never lets a turn end, and the user cannot
# fix it from inside the session. stop_hook_active is tested first for that
# reason.
#
# SABOTAGE-TEST: delete the `if payload.get("stop_hook_active")` guard in
# pm_pulse.py and confirm the first case below goes red.
# ---------------------------------------------------------------------------
echo "== pm_pulse.py: Stop hook =="

pulse_payload() {  # $1 = cwd, $2 = session id, $3 = stop_hook_active (true/false)
  "$PY" - "$1" "$2" "$3" <<'PYEOF'
import sys, json
print(json.dumps({
    "cwd": sys.argv[1],
    "session_id": sys.argv[2],
    "stop_hook_active": sys.argv[3] == "true",
}))
PYEOF
}

pulse() {  # $1 = cwd, $2 = session, $3 = active -> echoes exit code
  pulse_payload "$1" "$2" "$3" | "$PY" "$SCRIPTS/pm_pulse.py" >/dev/null 2>&1
  echo $?
}

expect_pulse() {  # $1 = wanted exit, $2..$4 = cwd session active, $5 = label
  local got; got=$(pulse "$2" "$3" "$4")
  if [ "$got" = "$1" ]; then pass; else fail "pm_pulse: want=$1 got=$got  $5"; fi
}

PD=$(mktemp -d) || exit 1
mkdir -p "$PD/.crew"
# schema 2 keeps upgradeNeeded quiet; the absent graph is what fires graphStale,
# which is a real, non-quiet trigger and therefore a legitimate reason to block.
#
# authority=act because the stderr-content assertions below are about the
# work-order directive specifically. The exit-code cases above it are
# authority-agnostic -- both directives block -- so this does not weaken them.
printf '{"schema":2,"tier":1,"roles":["explorer"],"pm":{"authority":"act"}}\n' \
  > "$PD/.crew/config.json"

# MUST ALLOW: the loop guard. Same state that blocks below, but on a turn that
# only exists because a Stop hook already blocked -- blocking again never ends.
expect_pulse 0 "$PD" sess-loop true "stop_hook_active must never block"

# MUST BLOCK: a crew repo with a real finding, first time this state is seen.
expect_pulse 2 "$PD" sess-a false "graphStale should block once"

# MUST ALLOW: the identical state a second time. This is the state-change gate
# AND the cross-flavour de-duplicator -- .sh and .ps1 both fire on Stop, and
# exactly one of them may speak per changed state.
expect_pulse 0 "$PD" sess-a false "unchanged state must not block twice"

# MUST ALLOW: not a crew repo at all. Every plain git checkout on the machine
# would otherwise block on graphStale, because there is genuinely no graph.
ND=$(mktemp -d) || exit 1
expect_pulse 0 "$ND" sess-b false "non-crew directory must not block"
rm -rf "$ND"

# MUST ALLOW: the PM switched off in config. An off switch that still blocks
# the end of every turn is not an off switch.
DD=$(mktemp -d) || exit 1
mkdir -p "$DD/.crew"
printf '{"schema":2,"pm":{"enabled":false}}\n' > "$DD/.crew/config.json"
expect_pulse 0 "$DD" sess-c false "pm.enabled false must not block"
rm -rf "$DD"

# MUST ALLOW: no session id. claim() fails CLOSED here (unlike hook_once), so
# an unkeyable pulse stays silent rather than blocking every turn forever.
expect_pulse 0 "$PD" "" false "missing session id must not block"

# The per-session cap. Standing down has to MEAN standing down: the notice is
# said once and then the hook is quiet, however many times the state changes
# afterwards. Keying that claim on the state fingerprint instead of on a fixed
# marker is the bug this pair exists to catch -- every later change would be a
# new fingerprint, would claim cleanly, and would block the turn again to
# repeat the same "standing down" line, which is not a cap.
#
# SABOTAGE-TEST: key the over-cap claim on `digest` in pm_pulse.py's main() and
# confirm the second case below goes red.
CAPS=sess-cap
for _n in $(seq 1 12); do
  : > "$PD/.crew/.pm-pulse-$CAPS-filler$_n"
done
# MUST BLOCK: the pulse that trips the cap says so, once.
expect_pulse 2 "$PD" "$CAPS" false "over the cap, the stand-down notice is given"
# MUST ALLOW: a genuinely new state afterwards. It has to move a field the
# FINGERPRINT actually covers -- tier and roles are not among them, so a config
# edit alone would leave the digest identical and the case would pass for the
# wrong reason. A pending handoff is one of the five that count.
mkdir -p "$PD/.work"
: > "$PD/.work/HANDOFF.md"
expect_pulse 0 "$PD" "$CAPS" false "past the cap, a new state must not block again"
rm -rf "$PD/.work"
rm -f "$PD/.crew/.pm-pulse-$CAPS-"*

# A block with empty stderr is a block that says nothing: the turn fails and
# the model is told to continue with no reason. Exit code alone cannot catch
# that, so assert the content -- through the WRAPPER, which is the path
# hooks.json actually uses and the only one that proves `exec` propagates the 2.
PERR="$PD/pulse-stderr.txt"
pulse_payload "$PD" sess-stderr false | bash "$SCRIPTS/pm-pulse.sh" \
  >/dev/null 2>"$PERR"
PRC=$?
[ "$PRC" = 2 ] && pass || fail "pm_pulse: wrapper must propagate exit 2 (got $PRC)"
grep -q 'Crew PM' "$PERR" && pass || fail "pm_pulse: blocking stderr must name the PM"
grep -q 'priorit' "$PERR" && pass \
  || fail "pm_pulse: stderr must carry the user-priority override"
grep -q 'graph' "$PERR" && pass \
  || fail "pm_pulse: stderr must carry the actual finding, not just the directive"

# pm.authority gates what the pulse TELLS the model to do. Leaking the `act`
# directive into a report-only repo makes the switch a lie: config says "ask
# me", hook says "go". Asserted through the wrapper, on real config files.
AD=$(mktemp -d); mkdir -p "$AD/.crew"
printf '{"schema":2,"pm":{"authority":"act"}}\n' > "$AD/.crew/config.json"
pulse_payload "$AD" auth-act false | bash "$SCRIPTS/pm-pulse.sh" \
  >/dev/null 2>"$AD/err.txt"
grep -q 'Act on them' "$AD/err.txt" && pass \
  || fail "pm_pulse: authority=act must send the work-order directive"
grep -qv 'do NOT dispatch' "$AD/err.txt" && pass \
  || fail "pm_pulse: authority=act must not send the report-only directive"

RD2=$(mktemp -d); mkdir -p "$RD2/.crew"
printf '{"schema":2,"pm":{"authority":"report-only"}}\n' > "$RD2/.crew/config.json"
pulse_payload "$RD2" auth-ro false | bash "$SCRIPTS/pm-pulse.sh" \
  >/dev/null 2>"$RD2/err.txt"
grep -q 'do NOT dispatch' "$RD2/err.txt" && pass \
  || fail "pm_pulse: authority=report-only must forbid dispatching"
grep -q 'Act on them in the order given' "$RD2/err.txt" \
  && fail "pm_pulse: report-only leaked the act directive" || pass

# A config with NO authority key at all must behave as report-only -- this is
# the upgrade path, where an existing install gains the pulse without ever
# having opted into autonomy.
UD=$(mktemp -d); mkdir -p "$UD/.crew"
printf '{"schema":2,"tier":1}\n' > "$UD/.crew/config.json"
pulse_payload "$UD" auth-absent false | bash "$SCRIPTS/pm-pulse.sh" \
  >/dev/null 2>"$UD/err.txt"
grep -q 'do NOT dispatch' "$UD/err.txt" && pass \
  || fail "pm_pulse: absent authority must default to report-only"

# And a typo must fail closed rather than widening permissions.
TD=$(mktemp -d); mkdir -p "$TD/.crew"
printf '{"schema":2,"pm":{"authority":"acr"}}\n' > "$TD/.crew/config.json"
pulse_payload "$TD" auth-typo false | bash "$SCRIPTS/pm-pulse.sh" \
  >/dev/null 2>"$TD/err.txt"
grep -q 'do NOT dispatch' "$TD/err.txt" && pass \
  || fail "pm_pulse: a typo'd authority must fail closed to report-only"
rm -rf "$AD" "$RD2" "$UD" "$TD"

# The cap is a backstop against a repo whose state oscillates every turn. If
# `pulses_taken`'s marker prefix ever drifts it silently returns 0 forever and
# the cap stops existing -- which is invisible without a test.
"$PY" - "$SCRIPTS" "$PD" <<'PYEOF' && pass || fail "pm_pulse: session cap"
import os, sys
sys.path.insert(0, sys.argv[1])
root = sys.argv[2]
import pm_pulse

before = pm_pulse.pulses_taken(root, "cap-sess")
for i in range(3):
    pm_pulse.claim(root, "cap-sess", f"{i:016x}")
after = pm_pulse.pulses_taken(root, "cap-sess")
if before != 0 or after != 3:
    print(f"  unit FAIL: pulses_taken {before} -> {after}, want 0 -> 3")
    sys.exit(1)
# A marker for a different session must not be counted against this one.
pm_pulse.claim(root, "other-sess", "ffffffffffffffff")
if pm_pulse.pulses_taken(root, "cap-sess") != 3:
    print("  unit FAIL: another session's markers leaked into the count")
    sys.exit(1)
# The same digest twice is one pulse, not two -- this is the de-duplicator.
if pm_pulse.claim(root, "cap-sess", "0000000000000000"):
    print("  unit FAIL: re-claiming the same digest must return False")
    sys.exit(1)
sys.exit(0)
PYEOF

# Pure-function cases: cheaper and sharper than driving the hook for each.
"$PY" - "$SCRIPTS" <<'PYEOF' && pass || fail "pm_pulse: unit cases"
import sys
sys.path.insert(0, sys.argv[1])
import pm_pulse

ok = True

def check(cond, label):
    global ok
    if not cond:
        print(f"  unit FAIL: {label}")
        ok = False

# A finding that is a standing condition is not worth interrupting a turn for.
check(not pm_pulse.should_pulse({
    "isCrew": True, "triggers": ["ticketsTooLarge", "reviewNotWorking"]}),
    "quiet-only triggers must not pulse")
# ...but a real one alongside them is.
check(pm_pulse.should_pulse({
    "isCrew": True, "triggers": ["ticketsTooLarge", "graphStale"]}),
    "a real trigger alongside quiet ones must pulse")
# A healthy crew says nothing.
check(not pm_pulse.should_pulse({"isCrew": True, "triggers": []}),
    "no triggers must not pulse")

# The fingerprint is the state-change gate: equal states must agree, and a
# changed trigger set must not. If this stops holding, the hook either never
# fires again or fires every turn.
a = {"isCrew": True, "triggers": ["graphStale"],
     "work": {"ticket": "T-1"}, "health": {"verdict": "ok"}}
b = dict(a, triggers=["graphStale", "diagramsStale"])
c = dict(a, work={"ticket": "T-2"})
check(pm_pulse.fingerprint(a) == pm_pulse.fingerprint(dict(a)),
      "same state must fingerprint equal")
check(pm_pulse.fingerprint(a) != pm_pulse.fingerprint(b),
      "changed triggers must fingerprint differently")
check(pm_pulse.fingerprint(a) != pm_pulse.fingerprint(c),
      "changed ticket must fingerprint differently")
# health.rate deliberately excluded -- it moves on every review and would fire
# the hook on changes nobody asked to hear about.
check(pm_pulse.fingerprint(a) == pm_pulse.fingerprint(
      dict(a, health={"verdict": "ok", "rate": 1.7})),
      "health.rate must not move the fingerprint")

sys.exit(0 if ok else 1)
PYEOF
rm -rf "$PD"

# ---------------------------------------------------------------------------
# crew_state.py -- diagram freshness. Anchor-based, never mtime-based.
# ---------------------------------------------------------------------------
echo "== crew_state.py: diagrams =="
"$PY" - "$SCRIPTS" <<'PYEOF' && pass || fail "crew_state: diagram cases"
import os, subprocess, sys, tempfile
sys.path.insert(0, sys.argv[1])
import crew_state

ok = True

def check(cond, label):
    global ok
    if not cond:
        print(f"  unit FAIL: {label}")
        ok = False

root = tempfile.mkdtemp()
run = lambda *a: subprocess.run(a, cwd=root, capture_output=True, text=True)
run("git", "init", "-q")
run("git", "config", "user.email", "t@t")
run("git", "config", "user.name", "t")
os.makedirs(os.path.join(root, "docs", "diagrams"))
open(os.path.join(root, "seed.txt"), "w").write("x")
run("git", "add", "-A")
run("git", "commit", "-qm", "seed")
head = run("git", "rev-parse", "--short=7", "HEAD").stdout.strip()

d = os.path.join(root, "docs", "diagrams")
# Current: anchored at HEAD, in the exact header crew-diagrams documents. A
# bare `anchor:` line is invalid Mermaid, so this is the form that must work.
open(os.path.join(d, "architecture.mmd"), "w").write(
    f"%% Generated from myrepo@{head} on 2026-08-27. Verify before trusting.\n"
    "%% Anchors: src/api/orders.ts\ngraph TD\n")
# Behind: anchored at something else. Hand-written `%% anchor:` form, which is
# accepted on purpose -- provenance that is right there in the text must not
# read as absent.
open(os.path.join(d, "data-flow-orders.mmd"), "w").write(
    "%% anchor: 0000000\ngraph TD\n")
# Unanchored counts as behind -- unknown provenance resolves to stale.
open(os.path.join(d, "process-refund.mmd"), "w").write("graph TD\n")

got = crew_state.read_diagrams(root, {})
check(got["total"] == 3, f"total should be 3, got {got['total']}")
check("architecture" not in got["behind"], "anchored-at-HEAD must not be behind")
check("data-flow-orders" in got["behind"], "wrong anchor must be behind")
check("process-refund" in got["behind"], "missing anchor must be behind")
# Exact-stem matching: `data-flow-orders.mmd` is a diagram ABOUT one flow,
# not the data-flow overview, so it does NOT discharge that kind. Same for
# `process-refund.mmd`. Only `architecture.mmd` matches a kind here. This
# assertion was inverted when the prefix clause was dropped: it used to
# encode the bug, letting one narrow diagram stand in for the overview.
check(got["missing"] == ["data-flow", "process"],
      f"a specific diagram must not satisfy its kind, got missing={got['missing']}")

# A directory with no diagrams at all reports every kind missing, and must not
# raise on the absent directory.
empty = crew_state.read_diagrams(tempfile.mkdtemp(), {})
check(empty["total"] == 0, "absent diagrams dir must read as zero, not raise")
check(set(empty["missing"]) == set(crew_state.DIAGRAM_KINDS),
      f"absent dir must report all kinds missing, got {empty['missing']}")

# diagramsMissing must stay quiet until there is a codemap to draw from --
# otherwise every fresh setup is nagged about three diagrams on session one.
check("diagramsMissing" not in crew_state.evaluate_triggers({
    "isCrew": True, "knowledge": {"subsystems": 0},
    "diagrams": {"missing": ["architecture"]}}),
    "diagramsMissing must not fire without a codemap")
check("diagramsMissing" in crew_state.evaluate_triggers({
    "isCrew": True, "knowledge": {"subsystems": 3},
    "diagrams": {"missing": ["architecture"]}}),
    "diagramsMissing must fire once subsystems are mapped")
check("diagramsStale" in crew_state.evaluate_triggers({
    "isCrew": True, "diagrams": {"behind": ["architecture"]}}),
    "diagramsStale must fire on a behind anchor")
# Wrong-typed config must not raise -- this runs from SessionStart.
check(crew_state.read_diagrams(root, {"docs": "nonsense"})["total"] == 3,
      "wrong-typed docs config must fall back, not raise")

sys.exit(0 if ok else 1)
PYEOF

# --- cloud-guard.sh: the cloud/destructive guard ---------------------------
# The bash flavour, end to end, through the real wrapper. The full matrix -
# every case through python, bash AND pwsh - is tests/test_cloud_guard.py;
# this is the must-block / must-allow floor that runs wherever bash does.
# A decision is PreToolUse JSON on stdout with exit 0: `deny` or `ask` in
# `permissionDecision`, or NO output at all, which is the only spelling of
# allow (the guard never prints `allow`).
echo "== cloud-guard.sh =="
CG=$(mktemp -d) || exit 1
mkdir -p "$CG/repo/.crew" "$CG/home"
printf '{"guards":{"cloudGuard":"block"}}' > "$CG/repo/.crew/config.json"
cguard_raw() {  # $1 = raw stdin -> the wrapper's stdout
  # `-u OS`: on Windows, Git Bash inherits OS=Windows_NT, and there the bash
  # flavour stands down for PowerShell CALLS, which its twin judges -- which
  # would make every PowerShell case below an allow. Bash calls it judges
  # whatever OS says; the Windows_NT cases after this list prove that.
  printf '%s' "$1" | env -u AWS_PROFILE -u AWS_DEFAULT_PROFILE \
        -u AWS_ACCESS_KEY_ID -u CI -u CREW_UNATTENDED -u AZURE_SUBSCRIPTION_ID \
        -u OS HOME="$CG/home" CLAUDE_PROJECT_DIR="$CG/repo" \
        bash "$SCRIPTS/cloud-guard.sh" 2>/dev/null
}
cguard() {  # $1 = tool, $2 = command -> echoes deny|ask|allow
  local out
  out=$(cguard_raw "$(json_cmd "$1" "$2")")
  # A `systemMessage` with no decision (report mode, the one-time unpinned
  # note) is an allow. A printed `allow` is not: it would skip the user's own
  # prompt, so it is reported as unparsed and fails the case.
  case "$out" in
    *'"permissionDecision": "deny"'*) echo deny ;;
    *'"permissionDecision": "ask"'*)  echo ask ;;
    *'"permissionDecision"'*) echo "unparsed:$out" ;;
    '{"systemMessage": '*) echo allow ;;
    '') echo allow ;;
    *) echo "unparsed:$out" ;;
  esac
}
cexpect() {  # $1 = want, $2 = tool, $3 = command
  local got; got=$(cguard "$2" "$3")
  if [ "$got" = "$1" ]; then pass; else fail "cloud-guard want=$1 got=$got  [$2] $3"; fi
}
cexpect deny  Bash 'terraform apply -auto-approve'
cexpect deny  Bash 'cd infra && sudo -E env TF_LOG=1 tofu destroy'
cexpect deny  Bash 'aws ec2 terminate-instances --instance-ids i-1'
cexpect deny  Bash 'aws s3 rm s3://bucket --recursive'
cexpect deny  Bash 'az group delete -n rg --yes'
cexpect deny  Bash "psql -h db -c 'DROP TABLE users'"
cexpect deny  Bash "$(printf 'psql <<SQL\nTRUNCATE t;\nSQL')"
cexpect deny  Bash 'git push --force origin main'
cexpect deny  PowerShell 'Invoke-Sqlcmd -Query "DROP TABLE t" -ServerInstance s'
cexpect deny  PowerShell "& 'C:\\tools\\terraform.exe' destroy"
cexpect allow Bash 'terraform plan'
cexpect allow Bash 'aws s3 ls'
cexpect allow Bash 'az group list'
cexpect allow Bash "psql -c \"SELECT 'DROP TABLE x'\""
cexpect allow Bash 'git push'
cexpect allow Bash 'git commit -m "terraform destroy; DROP TABLE t; git push --force"'
cexpect allow PowerShell 'Get-ChildItem; terraform plan'
# Review round 1 (Codex): each of these was the other answer before its fix.
cexpect deny  Bash "echo 'DROP TABLE t;' | tee /tmp/q | psql"
cexpect deny  Bash 'echo destroy | xargs terraform'
cexpect deny  Bash 'echo --force | xargs git push'
cexpect deny  Bash 'az group --subscription prod delete -n rg'
cexpect deny  Bash "bash -c -- 'terraform destroy'"
cexpect deny  Bash 'echo $(echo $(echo $(echo $(echo $(echo $(echo $(echo $(ls))))))))'
cexpect deny  PowerShell '(((((((((Get-Date)))))))))'
cexpect deny  PowerShell "Write-Output 'DROP TABLE t' | Tee-Object -FilePath q | mysql app"
cexpect allow Bash 'aws ec2 terminate-instances --instance-ids i-1 --dry-run'
cexpect allow Bash 'terraform apply -help'
cexpect allow PowerShell 'Remove-AzResourceGroup -Name rg -WhatIf'
cexpect allow Bash 'git ls-files -m | xargs git add'
# Review round 2 (Codex): each of these was the other answer before its fix.
# The psql case was an allow in round 1; with standard_conforming_strings off
# the server reads `\'` as an escape and the DROP as live, so it is refused.
cexpect deny  Bash "psql -c \"SELECT 'C:\\' AS p, 'DROP TABLE x' AS s\""
cexpect deny  Bash "mysql -e \"SELECT 'a\\' ; DROP TABLE t; -- '\""
cexpect deny  PowerShell "Remove-AzResourceGroup -Name '-WhatIf'"
cexpect deny  Bash 'xargs -a input -I CMD CMD destroy'
cexpect deny  Bash 'aws ec2 terminate-instances --dry-run --no-dry-run'
cexpect deny  Bash "terraform destroy -auto-approve -var-file '--help'"
cexpect allow Bash "mysql -e 'SELECT 1 -- DROP TABLE t'"
cexpect allow Bash 'aws ec2 terminate-instances --no-dry-run --dry-run'
cexpect allow Bash 'terraform apply -var-file x.tfvars -help'
cexpect allow PowerShell 'Remove-AzResourceGroup -Name rg -Force -WhatIf'
# By the TOOL, not the OS: under OS=Windows_NT this flavour still judges a
# Bash call, and stands down only for a PowerShell one, which the .ps1 judges.
cg_windows() {  # $1 = tool, $2 = command -> the wrapper's stdout
  json_cmd "$1" "$2" | env -u AWS_PROFILE -u AWS_DEFAULT_PROFILE \
      -u AWS_ACCESS_KEY_ID -u CI -u CREW_UNATTENDED OS=Windows_NT \
      HOME="$CG/home" CLAUDE_PROJECT_DIR="$CG/repo" \
      bash "$SCRIPTS/cloud-guard.sh" 2>/dev/null
}
case "$(cg_windows Bash 'terraform destroy')" in
  *'"permissionDecision": "deny"'*) pass ;;
  *) fail "cloud-guard: OS=Windows_NT stood the bash flavour down for a Bash call" ;;
esac
if [ -z "$(cg_windows PowerShell 'terraform destroy')" ]; then pass; else
  fail "cloud-guard: OS=Windows_NT, the bash flavour judged a PowerShell call its twin judges"
fi
# Malformed input is refused while armed.
case "$(cguard_raw '{not json')" in
  *'"permissionDecision": "deny"'*) pass ;;
  *) fail "cloud-guard: malformed input was not refused while armed" ;;
esac
# A pin configured anywhere makes an unnameable identity unknown, read-only
# included; unattended, unknown is refused.
printf '{"guards":{"cloudGuard":"block"},"cloud":{"awsRegions":["eu-*"]}}' \
  > "$CG/repo/.crew/config.json"
out=$(json_cmd Bash 'aws s3 ls --region eu-west-1' | env -u AWS_PROFILE \
      -u AWS_DEFAULT_PROFILE -u AWS_ACCESS_KEY_ID -u OS CI=true \
      HOME="$CG/home" CLAUDE_PROJECT_DIR="$CG/repo" \
      bash "$SCRIPTS/cloud-guard.sh" 2>/dev/null)
case "$out" in
  *'"permissionDecision": "deny"'*'[cloudIdentity]'*) pass ;;
  *) fail "cloud-guard: unknown identity with a region pinned passed in CI: $out" ;;
esac
# A malformed `cloud` block is an invalid layer: armed, it fails closed.
printf '{"guards":{"cloudGuard":"report"},"cloud":null}' > "$CG/repo/.crew/config.json"
cexpect deny  Bash 'terraform destroy'
# Report mode prints NO decision, only a visible note of what block would do.
printf '{"guards":{"cloudGuard":"report"}}' > "$CG/repo/.crew/config.json"
case "$(cguard_raw "$(json_cmd Bash 'terraform destroy')")" in
  '{"systemMessage": '*'report mode'*) pass ;;
  *) fail "cloud-guard: report mode printed a decision or no note" ;;
esac
# Off is the default: the same destroy with no `cloudGuard` key is not judged.
printf '{}' > "$CG/repo/.crew/config.json"
cexpect allow Bash 'terraform destroy -auto-approve'
rm -rf "$CG"

# --- the PowerShell flavour guard ------------------------------------------
# hooks.json registers every event TWICE, once per flavour. On a host with
# BOTH interpreters both would run unless each .ps1 stands down off Windows.
# The suite derives its file list from hooks.json, so a newly registered hook
# with no guard turns this red on its own. Exit 77 means no pwsh here, so the
# guard could only have been checked statically -- reported as a SKIP and
# never folded into the pass count, because a static pass is not the same
# evidence as a behavioural one.
fg_out="$("$PY" "$HERE/test_flavour_guard.py" 2>&1)"; fg_rc=$?
case "$fg_rc" in
  0)  PASS=$((PASS+1)) ;;
  77) echo "SKIP: PowerShell flavour guard -- $fg_out" ;;
  *)  FAIL=$((FAIL+1)); echo "FAIL: PowerShell flavour guard (exit $fg_rc)"; echo "$fg_out" ;;
esac

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
