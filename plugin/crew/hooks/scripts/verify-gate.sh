#!/usr/bin/env bash

. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

# --price is an OPERATOR command only, and is handled here, before ANYTHING
# else in this file - before the stdin read below, which a terminal
# invocation of this flag would otherwise block on forever. It is never
# reachable from the Stop hook: hooks.json invokes this script with no
# argument or with "--all", never "--price", and the dispatch below is keyed
# on that exact literal. .crew/verify.json is TRACKED in this repo (git
# ls-files .crew/ lists it), so a --price that ran unattended would dirty a
# committed file on every Stop - the one thing this early return exists to
# make impossible. Build fixtures and point this at a COPY; do not run it
# against the real map unless you mean to commit the result.
if [ "${1:-}" = "--price" ]; then
  cd "${CLAUDE_PROJECT_DIR:-.}" || exit 1
  PRICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PRICE_PY=$(crew_py) || { echo "verify-gate --price: no python available" >&2; exit 1; }
  shift
  PRICE_TARGET=".crew/verify.json"
  PRICE_FORCE=""
  for a in "$@"; do
    case "$a" in
      --force) PRICE_FORCE="--force" ;;
      *) PRICE_TARGET="$a" ;;
    esac
  done
  "$PRICE_PY" "$PRICE_DIR/verify_price.py" "$PRICE_TARGET" $PRICE_FORCE
  exit $?
fi

# End-of-turn gate. Runs the checks that the CHANGED FILES actually require,
# from .crew/verify.json. Exit 2 = the work is not done.
#
# No hook_once claim here on purpose: Stop fires once per TURN against a
# stable session id, so a session-scoped claim taken on turn 1 would suppress
# every later turn's gate -- a 600-second gate that silently never runs again
# reads as "the work passed", which is worse than the double-run a claim
# would prevent. Both flavours are registered for every Stop so a
# single-shell machine always gets exactly one; on a machine with both
# shells they race for the same turn's gate, and a short-lived per-turn lock
# right before the expensive part lets whichever gets there first do the
# real work while the other backs off (see LOCK below).
#
# Bounded, and the twin of verify-gate.ps1's read below. A Stop hook always
# pipes JSON here, but nothing enforces that the pipe is ever actually
# closed, and a bare `cat` blocks the WHOLE script on it -- the same
# parked-process shape a hung interpreter probe produces, for a different
# cause. `[ -t 0 ]` is true only for an interactive terminal (nothing was
# ever going to arrive), so nothing is read at all in that case.
#
# THE BOUND IS TOTAL, NOT PER LINE. A `while read -t 5` loop gives EACH read
# call its own fresh 5s, so a producer that trickles bytes slowly enough to
# keep completing one read just under the wire (without ever closing the
# pipe) resets the clock forever and parks the whole script -- the same
# hang this bound exists to prevent, just spread across more reads. A
# single `read -t 5 -d ''` has one deadline for the WHOLE operation: it
# reads everything that arrives (embedded newlines included, since the
# delimiter is NUL, not newline) until either EOF or the 5s bound, whichever
# comes first, and preserves whatever partial input arrived either way. The
# Stop hook's payload is one line and arrives immediately in every real
# invocation, so this never differs from the old behaviour on the real path.
INPUT=""
if [ ! -t 0 ]; then
  IFS= read -r -t 5 -d '' INPUT || true
fi

# Claude Code re-fires Stop after a blocking Stop hook. Without this check the
# gate blocks its own retry forever, and a failing check becomes a stuck session.
case "$INPUT" in *'"stop_hook_active": true'*|*'"stop_hook_active":true'*) exit 0 ;; esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
grep -q '"verifyGate"[[:space:]]*:[[:space:]]*false' .crew/config.json 2>/dev/null && exit 0

# Emergency lane. An incident is open, so this turn is not blocked and the
# checks do not run - that is the entire point of declaring one, since these
# are the checks that take minutes. What would have run is written down
# instead, and /crew:emergency end reports the debt.
#
# The deploy-record check below stands down too, deliberately: an incident is
# exactly when a deploy goes out ahead of its paperwork. It is recorded as
# owed rather than enforced now.
if crew_incident_active; then
  CHANGED_N=$( { git -c core.quotePath=false diff --name-only HEAD 2>/dev/null; git -c core.quotePath=false ls-files --others --exclude-standard 2>/dev/null; } | grep -c . )
  crew_incident_log verify "stop gate stood down with $CHANGED_N changed file(s) unverified"
  if [ -f .crew/.deploy-in-flight ]; then
    read -r DENV DSHA < .crew/.deploy-in-flight
    crew_incident_log verify "deploy of $DENV at $DSHA has no row in .work/PROMOTIONS.md"
  fi
  exit 0
fi

# A deploy ran this turn (promote-gate.sh let it through and left a marker).
# It does not get to end without a row in the promotions log. A deploy nobody
# wrote down is a deploy nobody can audit, and "is prod running what qa signed
# off on" becomes unanswerable one turn later.
if [ -f .crew/.deploy-in-flight ]; then
  read -r DENV DSHA < .crew/.deploy-in-flight
  if grep -qE "\|[[:space:]]*$DENV[[:space:]]*\|[[:space:]]*$DSHA" .work/PROMOTIONS.md 2>/dev/null; then
    rm -f .crew/.deploy-in-flight
  else
    echo "DEPLOY NOT RECORDED: $DENV was deployed at $DSHA and .work/PROMOTIONS.md has no row for it." >&2
    echo "" >&2
    echo "Run the remaining gates against $DENV - smoke, then regression, then verify" >&2
    echo "after the soak - and append one row with the real result of each, failures" >&2
    echo "included. A deploy that moved bytes successfully and broke the application" >&2
    echo "looks identical to a good one until those gates run." >&2
    exit 2
  fi
fi

# Records the commit this gate has proven clean. Called on every exit-0 path
# below and on none that exit nonzero: a marker written before the checks ran
# would turn a FAILING turn into a verified baseline for the next one, and the
# gate would wave the same unverified code through forever after blocking once.
# A dirty tree is deliberately not recorded either -- HEAD is the only thing a
# future diff can be taken against, and the working tree the checks actually
# saw is not addressable by any sha.
record_verified() {
  VERIFIED=$(git rev-parse HEAD 2>/dev/null) || return 0
  [ -n "$VERIFIED" ] || return 0
  mkdir -p .crew 2>/dev/null && printf '%s\n' "$VERIFIED" > .crew/.verify-verified-at
}

# The fingerprint twin, written ONLY where everything ran and everything
# passed. Deliberately NOT written when the Stop budget deferred a rule: a
# deferred rule was never checked, so recording it would turn "we ran out of
# budget" into "this tree is verified" and the deferred checks would never
# run again on an unchanged tree. $NOTICES is non-empty exactly when the
# budget had something to say, which is the signal being tested.
# ONE predicate for BOTH records. A run may only be recorded as verified
# when nothing was deferred: a deferred rule was never checked, so
# recording over it turns "we ran out of budget" into "this tree is
# verified". FAILED is not tested here because every caller is already
# past `[ "$FAILED" -eq 0 ] || exit 2`; the count is the whole question.
#
# This used to be `[ -z "$NOTICES" ]` on the fingerprint and NOTHING at
# all on the sha baseline, which is how a deferred rule still advanced
# the baseline and dropped a committed file out of CHANGED for every
# later run -- including --all, which correctly ignores the fingerprint
# and was still diffing against the advanced baseline.
# DEFERRED_COUNT counts only ACUTE (budget-contention) deferrals as of the
# per-rule record feature. A rule that is permanently over budget on its own
# (rules[8] here, 185s vs a 60s default) or excluded for reach no longer
# counts here -- it cannot fit no matter how the budget is spent, so
# freezing this baseline forever over it just forces every OTHER rule to
# re-match and re-run every turn from then on. It stays unverified anyway:
# verify_record.py persists it by content hash and reports it every run
# until it is actually checked, via /crew:verify --all.
fully_verified() { [ "${DEFERRED_COUNT:-1}" -eq 0 ]; }

record_verified_fingerprint() {
  [ -n "$FINGERPRINT" ] || return 0
  fully_verified || return 0
  mkdir -p .crew 2>/dev/null && printf '%s\n' "$FINGERPRINT" > "$FP_FILE"
}

# SCOPE. This used to diff the WORKING TREE against HEAD, which meant a change
# that had been committed was invisible and COMMITTING WAS ENOUGH TO END A TURN
# the gate would otherwise have blocked. Measured, not theorised: with a rule
# mapping `**/*.py` to a failing command, a dirty `mod.py` exited 2 and the
# same file exited 0 once committed. A gate you can pass by running `git
# commit` is not a gate.
#
# The baseline is now the last commit this gate actually verified, so work that
# was committed mid-turn is still in scope. Three sources, in order, and the
# order is the decision:
#
#   1. `.crew/.verify-verified-at`, written ONLY on a pass. It means "everything
#      up to this sha was checked and was clean", which is exactly the question
#      a baseline has to answer. It is machine-local -- `.crew/*` is ignored and
#      the un-ignore list is `codemap/`, `endpoints.json`, `verify.json`, so this
#      marker is not on it -- because "what has been verified here" is a fact
#      about this checkout and travels with nobody. Note `verify.json` IS
#      tracked: the MAP travels, the record of what was checked against it does
#      not, and conflating the two is how a clone inherits a pass it never ran.
#   2. The merge-base with the default branch, when there is no marker or it
#      names a commit this repo no longer contains (a squash merge, a rebase).
#      Nothing on this branch has been shown to be verified, so all of it is in
#      scope. Unknown resolves to checking MORE, never less.
#   3. HEAD, when there is no branch point to use -- a detached checkout, or
#      sitting ON the default branch, where merge-base(HEAD, main) IS HEAD.
#
# That third case is the one narrowing that survives, and it is worth stating
# plainly rather than leaving to be discovered: with no marker yet, ON the
# default branch, a commit still ends the turn. It lasts exactly one turn,
# because the marker is written on EVERY clean exit below -- including the
# "nothing changed" one -- so the first quiet turn in a checkout establishes a
# baseline and every turn after it is covered. Closing even that window needs a
# turn-start signal this script does not receive.
#
# The rejected alternative was a marker written at turn start by another hook.
# It dates the turn precisely, but a missing marker degrades to today's
# behaviour, and a gate that silently verifies less when its input is absent is
# this repo's recurring bug: an unknown collapsing into the permissive value.
# This baseline fails the other way.
BASE=""
if [ -f .crew/.verify-verified-at ]; then
  read -r CAND < .crew/.verify-verified-at
  # Trust it only if it still names a commit. A marker surviving a squash merge
  # would otherwise diff against nothing and report the whole branch as clean.
  if [ -n "$CAND" ] && git cat-file -e "${CAND}^{commit}" 2>/dev/null; then
    BASE="$CAND"
  fi
fi
if [ -z "$BASE" ]; then
  # `... | sed ... || echo main` does NOT work here: the || binds to the whole
  # pipeline and sed exits 0 even when symbolic-ref failed, so merge-base gets
  # an empty string. Branch on the ref itself.
  DEF=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null) || DEF=""
  DEF=${DEF#origin/}
  [ -z "$DEF" ] && DEF=main
  BASE=$(git merge-base HEAD "$DEF" 2>/dev/null) || BASE=""
fi
[ -z "$BASE" ] && BASE=HEAD
# `-c core.quotePath=false` on every path-listing git call. With the default
# (true) git renders a non-ASCII path as an escaped, DOUBLE-QUOTED string --
# measured here: `cafÃ©.txt` comes back as `"caf\\303\\251.txt"`. That string
# then matches no rule, and the fingerprint hashes it as an absent file, so
# a later edit to that file kept the passing digest and verification was
# skipped. Fixed at the SOURCE rather than by unquoting downstream, because
# the matcher and the scope report read the same list.
if [ "${1:-}" = "--all" ]; then
  # --all does not diff against ANY commit. A commit-range diff, however
  # wide, is still bounded by SOME ancestor, and on a single-branch repo
  # (or one sitting ON its own default branch) merge-base(HEAD, main) IS
  # HEAD -- an empty diff. That is exactly the tree the per-rule record
  # needs --all to still reach: the sha marker can now advance past the
  # commit that added a CHRONIC/reach-excluded/skipped rule's own files
  # (see verify_record.py), so a commit-range fallback would silently
  # narrow --all's scope to match Stop's, which defeats the whole feature.
  # --all instead sees EVERY tracked file plus every untracked one -- the
  # full working tree, matching its own name.
  #
  # `git ls-files` alone MISSES a path staged for deletion: `git rm` (or an
  # unstaged `rm` plus `git add`) removes it from the INDEX, so it is no
  # longer "a file this repo has" by ls-files' own definition, even though
  # the commit that lands will delete it and the rule that covers it needs
  # to run once more against the deletion itself. Measured: a.py mapped to
  # a failing rule, `git rm a.py`, then --all selected zero commands and
  # exited 0. Two more sources close it: `--diff-filter=D` against the
  # index catches a STAGED deletion; the plain `diff --name-only HEAD`
  # catches an UNSTAGED one (`rm a.py` with no `git add`). `matches()`
  # below does not care whether a changed path still exists on disk - a
  # rule maps a PATH, and a path that used to match still does.
  #
  # A STAGED RENAME is a separate hole from a staged delete: `git mv old
  # new` (or `mv` + `git add`) stages both halves in the index, and
  # DEFAULT rename detection means `--diff-filter=D` never reports `old` at
  # all - it is paired into an R status instead, invisible to the D-only
  # scan above. Measured: `old.txt` mapped to a failing rule, `git mv
  # old.txt new.txt`, `--diff-filter=D --cached` returned NOTHING even
  # though old.txt is gone from ls-files. `--name-status -M --diff-filter=R`
  # names both columns (old path, new path) per rename; `cut -f2-` drops
  # the leading R### status column and `tr '\t' '\n'` splits the remaining
  # two paths onto their own lines, matching CHANGED's one-path-per-line
  # shape.
  CHANGED=$(git -c core.quotePath=false ls-files 2>/dev/null; \
            git -c core.quotePath=false diff --name-only --cached --diff-filter=D 2>/dev/null; \
            git -c core.quotePath=false diff --name-only HEAD 2>/dev/null; \
            git -c core.quotePath=false diff --name-status --cached -M --diff-filter=R 2>/dev/null | cut -f2- | tr '\t' '\n'; \
            git -c core.quotePath=false ls-files --others --exclude-standard 2>/dev/null)
else
  CHANGED=$(git -c core.quotePath=false diff --name-only "$BASE" 2>/dev/null; git -c core.quotePath=false ls-files --others --exclude-standard 2>/dev/null)
fi
CHANGED=$(printf '%s\n' "$CHANGED" | sort -u | sed '/^$/d')
if [ -z "$CHANGED" ]; then
  # A turn that changed nothing still owes a reminder for any rule this
  # tree has never actually been checked against - a chronic over-budget
  # rule, a reach-excluded one, or one still SKIPping on rc 77. Without
  # this, the moment the sha marker advances past the commit where that
  # rule's own files last changed, it goes quiet with nobody told. Best
  # effort and read-only: no python, no script, or a corrupt record file
  # all mean "say nothing extra", never "invent a status".
  REPORT_PY=$(crew_py 2>/dev/null) || REPORT_PY=""
  REPORT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -n "$REPORT_PY" ] && [ -f "$REPORT_DIR/verify_record.py" ]; then
    "$REPORT_PY" "$REPORT_DIR/verify_record.py" report >&2 2>/dev/null || true
  fi
  record_verified
  exit 0
fi

# LOCK: from here on is the real (possibly minutes-long) smoke/verify work,
# and both this script and verify-gate.ps1 are firing for the same Stop
# event. `mkdir` is atomic even across a bash/PowerShell pair on the same
# filesystem, so whichever of the two gets here first claims the lock; the
# other backs off (exit 0) instead of redoing the work -- the winner's exit
# code still governs the turn either way.
#
# The lock records a TIMESTAMP, never a PID. The two flavours do not share a
# PID namespace on Windows: bash's $$ is an MSYS pid and PowerShell's $PID is
# a Windows pid, and neither can test the other's for liveness -- `kill -0` on
# a live Windows pid reports dead, `Get-Process -Id` on a live MSYS pid
# reports dead. A PID-based lock therefore fails in exactly the cross-shell
# case it exists for: each side calls the other's fresh lock stale and runs
# anyway. It fails the other way too, since the two id spaces overlap
# numerically -- a coincidental match reads as a live holder and the gate is
# silently skipped, which is worse than the double-run (see the header).
#
# So: the holder REMOVES its own lock on exit (trap below), and age comes
# from the lock DIRECTORY's own mtime, which `mkdir` stamps atomically as it
# creates it. There is no separate timestamp file to be caught half-written,
# and no window in which a lock exists with no age -- a crash between the
# two would otherwise wedge the gate for every later turn. A lock older than
# 700s (comfortably above the hook's own 600s timeout) is one whose holder
# was hard-killed before its trap ran, and is reclaimed.
#
# BACKING OFF IS NOT PASSING, so every path that exits 0 here has to have
# seen an actual holder. `mkdir` failing is not that evidence on its own: it
# fails for ENOTDIR, EACCES and a read-only filesystem exactly as it fails
# for EEXIST, and the first version of this block read every one of them as
# "someone else is working". Measured in a fixture: with `.crew` present as a
# FILE the gate exited 0 in 0.65s on every turn, for ever, against a
# verify.json a running gate exits 2 on -- the whole point of the gate,
# silently off, with nothing on stderr to say so. With the lock path itself a
# file it did the same for the 700s window. So the three questions are kept
# apart below, and only the first of them may back off:
#
#   1. A lock DIRECTORY is there      -> a holder plausibly exists.
#   2. mkdir failed and none is there -> no holder; there is no lock to wait
#                                        for. Run the checks unlocked and say
#                                        so. The worst case is the double-run
#                                        this lock exists to avoid, which the
#                                        header already ranks below a silent
#                                        skip.
#   3. A directory whose age is unreadable -> undatable, so it cannot be told
#                                        from a corpse. Same answer as 2, and
#                                        loudly, rather than a permanent
#                                        silent stand-down.
#
# WHAT THIS DOES NOT FIX, and the measurement is the reason. Case 1 is still
# only plausible, not proven: a lock DIRECTORY left behind by a hard-killed
# holder backs every later gate off for the rest of the age window, so a
# manual re-run exits 0 in under a second with nothing on stderr. The obvious
# narrowing is to read the pid out of the token and ask whether that process
# is alive -- only for a token THIS flavour wrote, so the cross-namespace
# objection above would not apply. It does not work on the platform it would
# have to work on. Measured 2026-09-13 on Git for Windows bash: a bash process
# was started, its `$$` recorded, hard-killed, and a SECOND bash asked
# `kill -0 <that pid>` at +0.5s, +5s and +15s. All three reported the dead
# process ALIVE (exit 0), while a pid that never existed correctly reported
# "No such process". A same-flavour liveness check would therefore read every
# corpse as a live holder -- it would never reclaim, and the one time it fired
# it would be on evidence that does not hold. The age window stays the only
# answer for a lock directory that can be dated.
# --all runs the WHOLE map with no Stop budget. /crew:verify is the caller
# that wants it; the Stop hook never passes it. Anything else leaves the flag
# empty so the matcher always sees the same argv shape.
BUDGET_FLAG=""
[ "${1:-}" = "--all" ] && BUDGET_FLAG="--all"

# --- the unchanged-turn skip ---------------------------------------------
#
# Stop fires once per TURN, so a turn that changed nothing the gate cares
# about re-runs the whole map to reach the answer it reached a minute ago.
# The event is not the gate; the STATE is.
#
# The digest comes from verify_fingerprint.py, shared with the .ps1 so the
# two cannot drift, and covers HEAD, the changed paths AND their bytes,
# verify.json and config.json. NOT a stat() comparison: an mtime is wrong in
# the direction that matters here.
#
# THE MARKER IS ONLY EVER WRITTEN AFTER A CLEAN, COMPLETE RUN (see
# record_verified_fingerprint below), so a skip can only mean "this exact
# tree was fully checked and passed". A failure or a budget-deferred rule
# leaves no marker and the next turn runs again.
#
# It also SAYS it skipped. 0.19.65 had to fix a silent exit 0 that was
# byte-identical to a pass; a silent skip would reintroduce exactly that.
# No python means no fingerprint and no skip -- the safe direction.
FP_PY=$(crew_py 2>/dev/null) || FP_PY=""
FP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FP_FILE=".crew/.verify-gate.fingerprint"
FINGERPRINT=""
if [ -n "$FP_PY" ] && [ -f "$FP_DIR/verify_fingerprint.py" ] && [ "$BUDGET_FLAG" != "--all" ]; then
  FINGERPRINT=$(printf '%s\n' "$CHANGED" | "$FP_PY" "$FP_DIR/verify_fingerprint.py" "$PWD" 2>/dev/null)
  if [ -n "$FINGERPRINT" ] && [ "$FINGERPRINT" = "$(cat "$FP_FILE" 2>/dev/null)" ]; then
    echo "verify-gate: nothing the gate depends on has changed since the last CLEAN run (fingerprint $FINGERPRINT) - checks were SKIPPED, not re-run. Edit a file, or run the gate with --all, to force them." >&2
    # The fingerprint only proves nothing changed; it says nothing about a
    # rule that was chronic/skipped/reach-excluded on a PRIOR run and has
    # not been touched since. Read-only reminder, same fail-safe direction
    # as the empty-CHANGED path above.
    [ -f "$FP_DIR/verify_record.py" ] && "$FP_PY" "$FP_DIR/verify_record.py" report >&2 2>/dev/null
    exit 0
  fi
fi

LOCK=".crew/.verify-gate.lock"
# 700 until crew 0.19.65, sized to exceed the hook's own 600s timeout because
# a held lock was only ever dated at acquisition. It now has a HEARTBEAT (see
# lock_touch below), so the mtime tracks the last rule that FINISHED rather
# than when the run began, and the TTL only has to exceed the longest single
# rule instead of the longest whole run. Measured on a quiet tree: the slowest
# rule is the gate pytest set at 57.6s, the whole run 115.7s.
#
# The cut matters because of what the window costs when it is wrong. A lock
# left by a hard-killed holder backs every later gate off for the REST of the
# window -- see "WHAT THIS DOES NOT FIX" above -- so at 700s a cancelled gate
# disabled verification for up to twelve minutes. At 180s, with the heartbeat
# keeping a live run from ever looking stale, a false "held" costs one skipped
# turn and that turn now says so out loud.
LOCK_TTL=180
# Overridable so the regression suite can exercise the boundary without
# burning the real window in wall-clock time. Read from the environment, not
# from config: this is a TEST SEAM, and a repo that sets it in .crew/config
# would be quietly changing how long one flavour waits for the other.
#
# NARROWS ONLY. A value greater than the compiled default (or 0, or anything
# that fails to parse as a positive integer) is ignored and the default
# stands -- the seam exists so a test can make the window SMALLER and finish
# in seconds, never to make a live repo's window LARGER by an env var nobody
# would think to look for. Unparseable falls back to the compiled default,
# not to zero, which would make every lock look expired on the next read.
#
# READ AS DECIMAL, EXPLICITLY. `08` and `09` are all digits, so they pass the
# filter below and then die inside `$(( ))`, which reads a leading zero as
# OCTAL: measured, `CREW_VERIFY_LOCK_TTL=08` printed
# `line 383: 1789805222 + 08: value too great for base (error token is "08")`
# twice and published NO deadline at all -- the seam silently disabling the
# very mechanism it exists to test. PowerShell has no octal literal, so
# `[int]"08"` is 8 over there and the two flavours disagreed on the same
# value; `10#` is what makes them agree.
case "${CREW_VERIFY_LOCK_TTL:-}" in
  ''|*[!0-9]*) ;;
  *) ENV_TTL=$((10#$CREW_VERIFY_LOCK_TTL))
     [ "$ENV_TTL" -gt 0 ] && [ "$ENV_TTL" -le "$LOCK_TTL" ] 2>/dev/null \
       && LOCK_TTL=$ENV_TTL ;;
esac
RECLAIMED=0
# Set when the checks run with no lock held. Nothing is cleaned up on that
# path -- no token is written, so the trap has nothing to match and another
# process's lock is never removed on a guess.
UNLOCKED=0
# GNU stat and BSD stat spell this differently and neither accepts the
# other's flag; `date -r` is not portable here either, since BSD `date -r`
# reads its argument as epoch seconds rather than as a file.
lock_mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null; }
# Date the lock by its TOKEN FILE, falling back to the directory.
#
# MEASURED, and it is why the heartbeat needed a second pass: rewriting a file
# inside a directory does NOT update that directory's mtime. Checked here on
# 2026-09-18 -- dir mtime 1789788907 before and after a token rewrite two
# seconds later, while the token itself moved to 1789788909. So a heartbeat
# that touches the token while the age is read off the directory refreshes
# nothing, and with the TTL cut to 180s the other flavour would have reclaimed
# a lock from a still-running gate: two gates, two verdicts, one turn. The
# no-op version passed every existing test, because nothing tested that a long
# run keeps its lock.
#
# The directory fallback covers a lock written by a version with no heartbeat.
lock_age_source() {
  [ -f "$LOCK/token" ] && { echo "$LOCK/token"; return; }
  echo "$LOCK"
}
# HEARTBEAT. Called after each rule finishes, so a run that legitimately takes
# longer than the TTL never looks abandoned to the other flavour. Without it,
# cutting the TTL would let the .ps1 reclaim a lock the .sh is still using and
# two gates would run the same turn -- two verdicts, doubled load, and the
# double-report the lock exists to prevent. Only the token holder touches it:
# `mkdir -p` on an existing directory updates nothing on some filesystems, so
# write through the token file, which we own and which the trap already keys on.
# HOW LONG THIS RUN MAY LEGITIMATELY GO QUIET.
#
# The heartbeat fires BETWEEN rules, so a SINGLE rule longer than LOCK_TTL
# still lets the other flavour reclaim a live lock and run concurrently --
# two gates, two verdicts, one turn. That is not hypothetical here: this
# repo's own map declares a 185s rule against a 180s TTL.
#
# So the holder publishes a DEADLINE sized from the map's own measured
# numbers: max(LOCK_TTL, 2 x the largest stated cost among the rules actually
# selected). The challenger honours the deadline when it finds one and falls
# back to the token-mtime window when it does not, so a lock written by an
# older version still ages exactly as before.
#
# WHY NOT A BACKGROUND HEARTBEAT DURING THE RULE, which was the reviewer's
# stated preference: a backgrounded toucher is ORPHANED when the holder is
# SIGKILLed, and an orphan keeps refreshing the token forever -- the lock
# never goes stale and verification is disabled permanently. Bounding that
# needs either pid liveness, measured unreliable on this platform (see the
# 2026-09-13 note above), or a pipe-EOF trick whose PowerShell equivalent is
# different machinery, which is the .sh/.ps1 drift this pair exists to avoid.
# The deadline is bounded BY CONSTRUCTION and is the same arithmetic in both
# shells.
#
# THE COST, stated plainly: a hard-killed holder now holds the lock for up to
# max(LOCK_TTL, 2 x max stated cost) rather than LOCK_TTL. On this repo that
# is 370s instead of 180s. It is bounded, proportionate to what the map says
# the work takes, and the back-off announces itself (0.19.65), so the window
# is visible rather than silent.
#
# RESIDUAL GAP, not closed: a rule with NO stated cost contributes 0, so a map
# with no `seconds` keeps exactly today's behaviour and an unstated rule
# longer than LOCK_TTL can still lose its lock. Giving that rule a `seconds`
# closes it, which is the same incentive 0.19.69 set up.
lock_window() {
  W=$LOCK_TTL
  if [ -n "${MAX_COST:-}" ] && [ "$MAX_COST" -gt 0 ] 2>/dev/null; then
    [ $((MAX_COST * 2)) -gt "$W" ] && W=$((MAX_COST * 2))
  fi
  echo "$W"
}

# Publishes the deadline. Only the token holder writes it, same as lock_touch.
lock_extend() {
  [ "$UNLOCKED" -eq 0 ] || return 0
  [ "$(cat "$LOCK/token" 2>/dev/null)" = "${LOCK_TOKEN:-}" ] || return 0
  printf '%s\n' "$(( $(date +%s) + $(lock_window) ))" > "$LOCK/deadline" 2>/dev/null || true
}

lock_touch() {
  [ "$UNLOCKED" -eq 0 ] || return 0
  [ "$(cat "$LOCK/token" 2>/dev/null)" = "${LOCK_TOKEN:-}" ] || return 0
  printf '%s
' "$LOCK_TOKEN" > "$LOCK/token" 2>/dev/null || true
}
mkdir -p .crew 2>/dev/null
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ ! -d "$LOCK" ]; then
    echo "VERIFY GATE: could not create the lock at $LOCK and nothing is holding it (is .crew a file, read-only, or is the lock path not a directory?). No other gate can be waited for, so the checks are running WITHOUT the lock - at worst they run twice this turn." >&2
    UNLOCKED=1
  else
    HOLDER_AT=$(lock_mtime "$(lock_age_source)" | tr -dc '0-9')
    if [ -z "$HOLDER_AT" ]; then
      echo "VERIFY GATE: a lock directory is present at $LOCK but its age cannot be read, so a live holder cannot be told from one that was killed. The checks are running WITHOUT the lock rather than standing down for a holder that may not exist." >&2
      UNLOCKED=1
    else
      NOW=$(date +%s)
      # BACKING OFF IS NOT PASSING, and until crew 0.19.65 the two were
      # byte-identical: exit 0, no output, in under half a second. Measured
      # 2026-09-18 against a real abandoned lock -- 474ms, rc=0, empty. A
      # reader, a metrics file and the next session all read that as a gate
      # that ran and found nothing wrong. Say it instead.
      #
      # NOT a liveness check. Reading the pid out of the token and asking
      # whether it is alive is measured dead on this platform: see the
      # 2026-09-13 note above, where a hard-killed Git Bash pid reported ALIVE
      # at +0.5s, +5s and +15s. The heartbeat is what makes the age window
      # honest without needing liveness at all.
      # A published deadline wins over the age window: it is the holder
      # saying how long THIS run may take, from the map's own numbers.
      # Absent or unreadable falls back to the age window, so a lock from
      # a version that never wrote one ages exactly as it used to.
      #
      # AN UNPARSEABLE DEADLINE MEANS NOT HELD. It used to be read with
      # `tr -dc "0-9"`, which DELETES the characters it does not like instead
      # of rejecting the value -- so `-9999999999` became `9999999999`, a
      # deadline in the year 2286, and the gate backed off with
      # "may run for another 8210194761s" and verified nothing for the rest of
      # the century. Measured, exactly that, before this line changed.
      #
      # That is this repository's named recurring defect wearing its inverse:
      # not an unknown collapsing into the permissive value, but a MALFORMED
      # value being repaired into one. Same discipline as DEFERRED_COUNT
      # defaulting to 1 and the TTL seam falling back to 180 -- when the input
      # cannot be read, assume UNVERIFIED, which here means "no deadline", and
      # fall through to the age window below.
      #
      # `tr -d '[:space:]' ` removes WHITESPACE ONLY, because the .ps1
      # flavour writes this file with Set-Content and a native line ending, so
      # bash reads a trailing CR that is framing rather than content. Anything
      # left that is not a pure run of digits is refused outright -- a sign, a
      # decimal point, a second number, a word.
      #
      # `10#` for the same reason as the TTL seam above: a leading zero would
      # otherwise be read as octal inside `$(( ))`. Neither writer can emit
      # one (an epoch has not started with 0 since 1970), which is exactly why
      # it is cheap to be sure here rather than to argue about it.
      HOLD_DEADLINE=$(tr -d '[:space:]' < "$LOCK/deadline" 2>/dev/null)
      case "$HOLD_DEADLINE" in
        ''|*[!0-9]*) HOLD_DEADLINE="" ;;
      esac
      if [ -n "$HOLD_DEADLINE" ] && [ "$((10#$HOLD_DEADLINE))" -gt 0 ] 2>/dev/null && [ "$NOW" -lt "$((10#$HOLD_DEADLINE))" ] 2>/dev/null; then
        echo "verify-gate: backed off, lock held by $(cat "$LOCK/token" 2>/dev/null || echo 'an unreadable token') (holder declared it may run for another $((10#$HOLD_DEADLINE - NOW))s); NOTHING WAS VERIFIED this turn." >&2
        exit 0
      fi
      if [ $((NOW - HOLDER_AT)) -le "$LOCK_TTL" ] 2>/dev/null; then
        echo "verify-gate: backed off, lock held by $(cat "$LOCK/token" 2>/dev/null || echo 'an unreadable token') ($((NOW - HOLDER_AT))s old, ttl ${LOCK_TTL}s); NOTHING WAS VERIFIED this turn." >&2
        exit 0
      fi
      rm -rf "$LOCK" 2>/dev/null
      mkdir "$LOCK" 2>/dev/null || exit 0
      RECLAIMED=1
    fi
  fi
fi
# --- shared cleanup registry -----------------------------------------
# Every exit-path cleanup from here on (this lock's own release when a lock
# is actually held, the python3 shim's temp dir below, and a still-running
# rule's escaped process group further down) registers a FUNCTION here
# instead of splicing `trap -p` text - two chained `trap -p`-based layers
# already sit at the edge of what that idiom can do: `trap -p` re-quotes its
# output as a single-quoted string literal, escaping any embedded `'`
# as `'\''`, and splicing that ALREADY-escaped text into a third trap's
# own double-quoted body leaves the escape unresolved - not valid
# shell, and a mid-run `unexpected EOF` at whichever signal fires it. A
# third stage was tried exactly that way once (to reap a rule's
# backgrounded jobs on every exit) and reverted for this reason - see
# the rule loop's own comment, below, for the fuller account and the
# test that caught it (test_shim_cleanup_does_not_clobber_the_lock_release_trap).
# A function registered by NAME has nothing to re-quote at all, at any
# depth: every stage just appends its own cleanup function to this
# array, and the dispatcher below calls each in turn at signal time,
# reading whatever variables that function closes over fresh, not a
# frozen string captured at registration time.
#
# UNCONDITIONAL, unlike the lock registration below it: the shim (further
# down this file) and the rule-pgid stage both register into this array
# regardless of whether a lock was ever acquired - an UNLOCKED run (the
# lock path is a regular file, or otherwise unwritable) still has to clean
# up its own shim tempdir and kill its own rule's process group on
# TERM/INT/HUP. Defining the registry only inside the locked branch left
# both calls below hitting "command not found" on stderr on every unlocked
# run, and an interrupted rule's process group outliving the gate entirely,
# because neither the array nor the traps existed for it to register into.
_CREW_GATE_CLEANUP_FNS=()
_crew_gate_register_cleanup() { _CREW_GATE_CLEANUP_FNS+=("$1"); }
_crew_gate_run_cleanup() {
  local _crew_gate_cleanup_i
  for (( _crew_gate_cleanup_i=${#_CREW_GATE_CLEANUP_FNS[@]} - 1;
         _crew_gate_cleanup_i >= 0; _crew_gate_cleanup_i-- )); do
    "${_CREW_GATE_CLEANUP_FNS[_crew_gate_cleanup_i]}" 2>/dev/null
  done
}
# Installed ONCE, here - the first point this script has anything to
# clean up. INT/TERM/HUP each run the dispatcher and then exit with the
# conventional 128+signal status: an asynchronous signal this script has
# trapped no longer terminates it on its own, so without an explicit
# `exit` here a rule stuck mid-command would run its cleanup and then
# simply CONTINUE running - not what sent the signal wanted, and the
# exact gap that let a rule's own escaped process group outlive this
# whole gate being killed. EXIT needs no explicit exit of its own - the
# script is already on its way out with whatever code got it there.
trap '_crew_gate_run_cleanup; exit $((128 + 15))' TERM
trap '_crew_gate_run_cleanup; exit $((128 + 2))' INT
trap '_crew_gate_run_cleanup; exit $((128 + 1))' HUP
trap '_crew_gate_run_cleanup' EXIT

if [ "$UNLOCKED" -eq 0 ]; then
  # A token of our own, so a SECOND reclaimer that deleted our fresh lock and
  # took its own is detectable: whoever's token is on disk once both have
  # written owns the turn, and the other backs off instead of both running.
  LOCK_TOKEN="sh-$$-$(date +%s)-${RANDOM:-0}"
  _crew_gate_cleanup_lock() {
    if [ "$(cat "$LOCK/token" 2>/dev/null)" = "$LOCK_TOKEN" ]; then
      rm -rf "$LOCK" 2>/dev/null
    fi
  }
  _crew_gate_register_cleanup _crew_gate_cleanup_lock
  printf '%s\n' "$LOCK_TOKEN" > "$LOCK/token" 2>/dev/null
  # Only the reclaim path can race another reclaimer; the plain-mkdir winner
  # cannot be clobbered, since its lock is far too young for anyone to reclaim.
  # Do not tax the common path with the settle wait.
  if [ "$RECLAIMED" -eq 1 ]; then
    sleep 1
    [ "$(cat "$LOCK/token" 2>/dev/null)" = "$LOCK_TOKEN" ] || exit 0
  fi
fi

# MOVED HERE from before the lock in the same change that added it.
# Placed earlier, it printed on EVERY Stop -- including the flavour that
# backs off for a lock the other one holds, so a single Stop produced two
# scope reports and the lock suite's 'the loser is silent' assertions went
# red. Correctly so: they are asserting that exactly one flavour speaks.
# Inside the lock, the winner reports and the loser stays quiet.
# --- scope report: REPORT-ONLY, and it must never touch the exit code ------
# This gate can exit 2. The scope layer deliberately cannot: report-only was
# chosen so it would not take on the blocking-hook regression obligation, and
# an exit code escaping from here would take it on by accident. Hence the
# `|| true` and the explicit `:` -- a python that dies, is missing, or writes
# nothing must leave this gate exactly as it found it.
#
# The logic lives in scope_report.py, not here, because the bash and
# PowerShell flavours must not drift, and the ticket is
# resolved by crew_state.read_work, whose rules (done markers, table status,
# None rather than a guess) are not worth re-deriving twice in two shells.
# $DIR is NOT defined in this script -- only `dirname` inline at the top. An
# earlier draft used "$DIR/scope_report.py", which expanded to "/scope_report.py"
# and MSYS rewrote that to "C:\Program Files\Git\scope_report.py". The gate then
# printed a python "No such file" line as its scope report. Resolve it here.
SCOPE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOPE_PY=$(crew_py 2>/dev/null) || SCOPE_PY=""
# The two preconditions are reported APART. Both used to fall into one
# "(no python)" sentence, so a missing scope_report.py -- a different
# cause with a different fix -- was announced as an absent interpreter.
# verify-gate.ps1 says the same two things in the same two cases.
if [ -z "$SCOPE_PY" ]; then
  echo "outside-scope: (no python; scope not checked)" >&2
elif [ ! -f "$SCOPE_DIR/scope_report.py" ]; then
  echo "outside-scope: (scope_report.py not found at $SCOPE_DIR/scope_report.py; scope not checked)" >&2
else
  printf '%s
' "$CHANGED" | "$SCOPE_PY" "$SCOPE_DIR/scope_report.py" "$PWD" || true
fi
: # keep the scope report from ever deciding this script's status

if [ ! -f .crew/verify.json ]; then
  # _verify/ is the canonical home; scripts/smoke.sh is honoured as legacy.
  SMOKE=""
  for cand in ./_verify/smoke.sh ./scripts/smoke.sh; do
    [ -f "$cand" ] && { SMOKE="$cand"; break; }
  done
  [ -n "$SMOKE" ] || exit 0
  OUT=$(bash "$SMOKE" 2>&1) || { echo "Smoke FAILED. Work is not complete." >&2; echo "$OUT" | grep -E '^(FAIL|SMOKE:)' >&2; exit 2; }
  exit 0
fi

# PM ruling, 2026-09-22 (superseding the exit-0 this line used to have):
# no python resolving at all must NOT exit 0. An exit-0 Stop hook does not
# block the turn - so on a python-less host this was reaching the calling
# agent as an unblocked, silently-unverified turn, indistinguishable from a
# turn that actually passed. That is this repo's own named recurring
# defect (CLAUDE.md: "the recurring bug is an unknown collapsing into the
# safe-looking value") and the exact shape CLAUDE.md's Git-Bash-python3
# landmine already warns against ("fail loudly ... rather than
# suppressing the error and exiting 0"). Fails closed instead, using the
# SAME pattern this file already uses when .crew/verify.json itself fails
# to parse (see the PY_STATUS -eq 3 / -eq 4 branches below): a single
# named `VERIFY GATE: ... exit 2` line, re-evaluated fresh every turn - no
# separate one-shot suppression exists or is needed, because the failure
# clears itself the moment python is actually installed, the same way a
# parse error clears itself the moment the JSON is fixed.
#
# crew_py_strict, NOT plain crew_py, resolves the interpreter that runs the
# MATCHER below - review round 6 finding: plain crew_py (`command -v`
# alone) happily resolves a WindowsApps App Execution Alias stub, which is
# a real, executable file that does nothing when actually run. With plain
# crew_py, that stub became $PY, the matcher invocation "succeeded" (exit
# 0, zero output), and the fall-through below treated empty output as
# "nothing matched" rather than "nothing ran" - the gate exited 0 having
# checked precisely nothing, the DEFAULT state on a Windows host with no
# real python. crew_py_strict actually RUNS each candidate and rejects a
# WindowsApps path outright (see its own header in _common.sh), so that
# stub can no longer become $PY at all; see the `elif [ -z "$MATCHED" ]`
# branch below the matcher invocation for the second, independent check
# that exists in case some OTHER broken-but-`command -v`-resolvable
# interpreter ever slips past crew_py_strict the same way.
PY=$(crew_py_strict) || { echo "VERIFY GATE: no python (python3, python or py) resolves to a PROVED working interpreter anywhere on PATH - .crew/verify.json cannot be read and nothing can be verified. Work is not complete. Install python (3.10+) on this machine, or set \"verifyGate\": false in .crew/config.json to stand this gate down deliberately (honoured at the top of this file)." >&2; exit 2; }

# The changed-file list goes through a temp FILE, never argv. E2BIG counts argv
# PLUS the environment, so a hook invoked with a large environment fails to exec
# here even when the list itself is small - which was then misreported below as a
# corrupt verify.json. Measured 2026-09-07: 74 files / 2.6KB of paths, env 7.9KB,
# and the exec still failed with 'Argument list too long'.
# NOTE: deliberately no trap. A `trap ... EXIT INT TERM` above already releases
# the lock, and a second EXIT trap would REPLACE it and leak the lock directory.
CHANGED_FILE=$(mktemp 2>/dev/null) || { echo "VERIFY GATE: cannot create temp file. Verification did NOT run. Work is not complete." >&2; exit 2; }
printf '%s
' "$CHANGED" > "$CHANGED_FILE"

MATCHED=$("$PY" - "$CHANGED_FILE" "$BUDGET_FLAG" "$FP_DIR" << 'PY'
import json,sys,fnmatch,io,os,re
try:
    sys.stdout.reconfigure(newline="\n")
except (AttributeError, ValueError):
    pass
# Shared canonical hashing (see verify_record.py's rule_key docstring for
# why "shared" is load-bearing): this process already IS python, so import
# in-process rather than shelling out per rule. sys.argv[3] is the scripts
# directory - passed explicitly because this file is fed via stdin (`- `),
# so __file__ is not a real path to derive it from.
if len(sys.argv) > 3 and sys.argv[3]:
    sys.path.insert(0, sys.argv[3])
try:
    import verify_record as _vr
except ImportError:
    _vr = None

# Shared by per-rule classification AND the default/always fallback below -
# Codex round 4 BLOCK verify-gate.sh:950: `default`/`always` used to run
# with NO reach check at all, so a command a matching RULE had just been
# excluded from Stop for could still execute via the fallback, reintroducing
# exactly what reach exclusion exists to stop. One function, called from
# both places, so neither can drift from the other again.
def _classify_run_reach(run):
    """(kind, reason) if `run` should be excluded from Stop for reach, else
    None. `run` is a list of command strings - a rule's `.run`, or a single
    default/always command wrapped in a one-item list."""
    _status, _detail = (_vr.scan_reach(run, os.getcwd())
                         if _vr is not None else
                         ("wrapper", "the shared scanner (verify_record.py) is not importable"))
    if _status == "verb":
        return ("reach_undeclared",
                "remote verb %r - declare `reach` or run /crew:verify --all" % _detail)
    # Codex round 6: a command containing ANY shell metacharacter is
    # deferred unconditionally, before anything else about it is read -
    # see verify_record.py's module docstring for why this scan stopped
    # trying to model shell at all.
    if _status == "syntax":
        return ("reach_syntax",
                'shell syntax in an undeclared rule - declare `"reach": "local"` '
                "(or network/host) to run it on Stop")
    if _status == "wrapper":
        return ("reach_wrapper",
                'wrapper or inline shell (%s) - declare `"reach": "local"` '
                "(or network/host) to run it on Stop" % _detail)
    return None

changed=[l for l in io.open(sys.argv[1],encoding="utf-8").read().split("\n") if l.strip()]
try:
    cfg=json.load(open(".crew/verify.json"))
except (OSError, ValueError) as e:
    print(f"PARSE_ERROR: {e}", file=sys.stderr)
    sys.exit(3)

# `verify.stopBudgetSeconds`, default 60. None means NO budget -- what
# `--all` asks for, and what /crew:verify uses to run the whole map. An
# unreadable or malformed config falls back to the DEFAULT rather than to no
# limit: "could not read the config" must not quietly become "no limit".
budget = 60
if len(sys.argv) > 2 and sys.argv[2] == "--all":
    budget = None
else:
    try:
        _cc = json.load(open(".crew/config.json"))
        _v = (_cc.get("verify") or {}).get("stopBudgetSeconds")
        if isinstance(_v, (int, float)) and not isinstance(_v, bool) and _v >= 0:
            budget = _v
    except (OSError, ValueError, AttributeError):
        pass

# A command is ONE LINE, and a command that is not is REJECTED rather than
# split or quietly accepted. Two separate places assume it:
#
#   1. This matcher returns two records - the commands, and the paths no rule
#      matched - down one text channel. A `\n` inside a command moved the
#      record boundary, so the rest of that command and EVERY command after it
#      landed in the unmapped record and never ran.
#   2. The caller feeds the command record to `eval` from a line-oriented read
#      loop, which would split a surviving multi-line command into separately
#      evaled lines even with the boundary right.
#
# Measured on a fixture with run = ["echo first\necho second", "exit 1"]:
# with "unmapped": "warn" the gate exited 0 while the rule contained `exit 1`;
# with "fail" it exited 2 but named `echo second` and `exit 1` as unmapped
# PATHS, pointing the reader at files that do not exist.
#
# So: a rule crew cannot represent is not a rule that passed. The separators
# below are the belt; this rejection is the braces, and it names the entry.
# The set is every character that can move a record or line boundary - the two
# separators included, since a command carrying one would split exactly the
# way a newline used to.
FRAMING = {"\n": "a newline", "\r": "a carriage return",
           "\x1d": "an ASCII group separator (0x1d)",
           "\x1e": "an ASCII record separator (0x1e)",
           "\x1c": "an ASCII file separator (0x1c)"}

def reject_unrepresentable(where, entries):
    if not isinstance(entries, list):
        return
    for i, c in enumerate(entries):
        if not isinstance(c, str):
            continue
        for ch, name in FRAMING.items():
            if ch in c:
                head = c.split(ch, 1)[0].strip()[:60]
                print(f"PARSE_ERROR: .crew/verify.json {where}[{i}] contains "
                      f"{name}, so crew cannot represent it as one command. "
                      f"The entry begins: {head!r}. Split it into separate "
                      f"entries, or move it into a script and call that.",
                      file=sys.stderr)
                sys.exit(4)

for ri, rule in enumerate(cfg.get("rules", []) or []):
    if isinstance(rule, dict):
        reject_unrepresentable(f"rules[{ri}].run", rule.get("run"))
reject_unrepresentable("always", cfg.get("always"))
reject_unrepresentable("default", cfg.get("default"))

def matches(path, pat):
    # fnmatch's * spans '/', so '**/*.tf' demands a literal slash and silently
    # skips every root-level file - exactly the ones a Terraform module keeps
    # at its root. Test the '**/'-stripped form as well.
    cands = {pat}
    if pat.startswith("**/"): cands.add(pat[3:])
    cands.add(pat.replace("/**/", "/"))
    return any(fnmatch.fnmatch(path, c) for c in cands)

cmds, unmatched = [], []
# THE UNIT OF THE BUDGET IS THE RULE, AND `seconds` IS CHARGED ONCE.
#
# Say it here because the spec never did: it said "run matched rules in
# ascending seconds" and left the unit unstated, so the first implementation
# charged every COMMAND in a rule the whole rule's cost. A rule with
# `"seconds": 40` and two commands under the default 60s budget then ran its
# first command, priced the second at another 40, and deferred it -- the rule
# split in half, with the half that did not run reported as unverified. A
# rule's `seconds` is what the rule costs in total; a rule runs WHOLE or
# defers WHOLE.
#
# Two structures come out of the match, and they are not the same shape:
#
#   `cost` is per COMMAND and stays. It prices the deferral notices and sizes
#   the lock window (max_cost, below), both of which ask about a command. The
#   MAX is taken where several rules contribute the same command, because
#   under-stating there costs a too-short lock window.
#
#   `rule_cmds` / `rule_secs` are per matched RULE, in first-match order, and
#   are what the budget actually spends against.
#
# AND `mandatory` IS THE OBLIGATION, WHICH DEDUPLICATION MUST NOT WEAKEN.
# The same command string reaches `cmds` from several sources and is merged
# into one entry; the merged entry has to carry the STRONGEST obligation of
# any source, never the weakest. Three levels, strongest first:
#
#   `always`                 unconditional. The map says run it every turn.
#   a rule with no `seconds` unconditional-until-priced: the budget refuses
#                            to defer on a number nobody wrote down.
#   a rule with `seconds`    deferrable. This is the ONLY deferrable level.
#
# Merging resolves toward RUN. It used to resolve toward DEFER, because the
# classification asked only "does this command have a cost?" and any one
# priced rule set one -- so `"always": ["x"]` beside a 90s rule naming `x`
# DEFERRED the mandatory check and the gate exited 0 without running it.
# Measured in both flavours. The same reading deferred a command named by an
# unpriced rule as well, whenever a priced rule happened to name it too.
cost = {}
mandatory = set()  # commands no budget may defer, whatever they cost
rule_cmds = {}     # rule index -> its commands, in `run` order
rule_secs = {}     # rule index -> its stated cost, only when one is stated
rule_order = []    # matched rule indices, in the order they were first hit
def note_cost(cmd, rule):
    secs = rule.get("seconds")
    if not isinstance(secs, (int, float)) or isinstance(secs, bool) or secs < 0:
        return
    cost[cmd] = max(cost.get(cmd, 0), secs)
# --- reach ------------------------------------------------------------
#
# `local` | `network` | `host`. The Stop gate runs ONLY `local` rules;
# `network`/`host` rules run under /crew:verify --all (and the merge gate),
# never unattended on Stop. STOP_MODE is false exactly when --all was passed
# (budget is None then), which is the one case reach never excludes anything.
#
# UNDECLARED reach is NOT quietly treated as local. That was this brief's
# first draft and it is this repo's own named failure mode -- an unknown
# collapsing into the safe-looking value. TheSelectSource is the case that
# forced the correction: rules with no `reach` ran `bash _verify/smoke.sh`
# with no --ci, which reached a live dev host over SSM on every Stop, held
# safe only by an inherited `ENV` default. So an UNDECLARED rule whose
# command matches a reach verb is DEFERRED and NAMED at Stop time, exactly
# like a declared non-local rule -- it is not run, and it is not silent
# about why. An undeclared rule that matches nothing stays `local`, so an
# ordinary repo with no remote commands is unaffected.
STOP_MODE = budget is not None
# Reach scanning is verify_record.scan_reach - ONE function, shared with
# verify-gate.ps1 (which shells out to it) and verify_price.py (which
# imports it directly, same as here). Round 2 deleted the THREE independent
# copies of this logic that used to exist (a python heredoc inline here, a
# native PowerShell copy over there, and NOTHING at all in --price) and
# made this the only one.
#
# REJECT-ONLY as of round 4 - see scan_reach's module docstring in
# verify_record.py for the full rationale. Status is now "verb" | "wrapper"
# | "local"; there is no more "could not tell" middle ground - a wrapper
# this scan cannot fully read is classified "wrapper" the same as one it
# reads and finds nothing in, never a softer category.
stop_excluded = {}   # rule index -> (kind, reason) for a rule Stop will not run

# --- measure-and-cache --------------------------------------------------
#
# An unpriced rule that RUNS gets its wall time recorded (by the caller,
# after this matcher returns) into .crew/.verify-gate.timings.json --
# machine-local, never verify.json, which is tracked. From the SECOND Stop
# onward this matcher folds that cached number into rule_secs as if it were
# a declared `seconds`, labelled "(measured, not declared)" below, so the
# rule becomes deferrable instead of mandatory-forever. No measurement means
# no change from today: the rule stays unknown and runs. verify_record.py
# owns the file format; this only reads it.
_rule_keys = {}   # rule index -> content-hash key, shared with verify_record.py
_timings = {}
try:
    with open(".crew/.verify-gate.timings.json", encoding="utf-8") as _tf:
        _td = json.load(_tf)
    # `isinstance(_td, dict)` FIRST. A structurally wrong cache - `[]` is
    # valid JSON, just the wrong shape - parsed fine and then crashed on
    # `_td.get("rules")`: a list has no `.get`, AttributeError is not caught
    # by `except (OSError, ValueError)`, and the whole matcher died before a
    # single check ran. A corrupt CACHE is not a reason to block the turn;
    # it is a reason to treat it as absent, same as everything else here.
    if isinstance(_td, dict) and isinstance(_td.get("rules"), dict):
        _timings = _td["rules"]
except (OSError, ValueError):
    _timings = {}
def _rule_key(rule):
    # See verify_record.py's rule_key docstring for why this delegates
    # rather than hashing independently.
    if _vr is not None:
        return _vr.rule_key(rule)
    blob = json.dumps({"paths": rule.get("paths"), "run": rule.get("run")},
                       sort_keys=True, separators=(",", ":"))
    import hashlib
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]

measured_used = {}   # rule index -> True when its cost came from the cache
truly_unknown = {}   # rule index -> True when it needs a fresh measurement

# COMMAND IDENTITY includes the rule's declared env, not just its text. Two
# rules that both run `test "$ENV" = x` but declare DIFFERENT env used to
# collapse into ONE `cmds` entry (deduped on bare text), so only the LAST
# rule's env ever actually ran and BOTH rules were recorded as verified
# against a command neither of them, individually, was shown to pass under
# its own environment. An identity is the bare text alone when the rule
# declares no env, so nothing changes for the common case; when it does,
# `\x1c` (rejected in a raw command above, so this can never collide with
# one) joins the canonical env JSON, and the caller downstream strips it
# back off for eval and for display.
def _identity(cmd, env):
    if not env:
        return cmd
    return cmd + "\x1c" + json.dumps(env, sort_keys=True, separators=(",", ":"))
def _identity_text(identity):
    return identity.split("\x1c", 1)[0]

for f in changed:
    hit=False
    for ri, r in enumerate(cfg.get("rules",[])):
        if any(matches(f,p) for p in r["paths"]):
            hit=True
            if ri not in rule_cmds:
                rule_cmds[ri] = []
                rule_order.append(ri)
                key = _rule_key(r)
                _rule_keys[ri] = key
                secs = r.get("seconds")
                if (isinstance(secs, (int, float))
                        and not isinstance(secs, bool) and secs >= 0):
                    rule_secs[ri] = secs
                else:
                    cached = _timings.get(key)
                    if isinstance(cached, int) and cached > 0:
                        rule_secs[ri] = cached
                        measured_used[ri] = True
                if STOP_MODE:
                    # requiresCleanTree shares this exclusion plumbing with
                    # reach: a rule that refuses on a dirty tree (the SRL
                    # case: sabotage-test.sh's "REFUSING TO RUN: the working
                    # tree is not clean") is a permanent red on every Stop
                    # during ordinary work, where the tree is dirty by
                    # definition. Stop never runs it at all - not "run it
                    # and see if it refuses" - and pushes it to --all and
                    # the merge gate, where a genuinely clean checkout (CI,
                    # or a deliberate `/crew:verify --all` before a PR) lets
                    # it actually check something. Checked BEFORE reach so a
                    # rule naming both gets the clean-tree reason, since that
                    # is the more specific precondition of the two.
                    if r.get("requiresCleanTree") is True:
                        stop_excluded[ri] = ("clean_tree_required",
                            "requires a clean working tree - not run on Stop, run /crew:verify --all")
                    else:
                        reach = r.get("reach")
                        if isinstance(reach, str) and reach != "local":
                            stop_excluded[ri] = ("reach_declared",
                                "declared reach: %s - not run on Stop, run /crew:verify --all" % reach)
                        elif reach is None:
                            _cls = _classify_run_reach(r.get("run"))
                            if _cls is not None:
                                stop_excluded[ri] = _cls
            if ri in stop_excluded:
                continue
            r_env = {}
            if isinstance(r.get("env"), dict):
                r_env = {k: v for k, v in r["env"].items()
                         if isinstance(k, str) and isinstance(v, str)}
            for c in r["run"]:
                ident = _identity(c, r_env)
                if ident not in cmds: cmds.append(ident)
                if ident not in rule_cmds[ri]: rule_cmds[ri].append(ident)
                note_cost(ident, r if r.get("seconds") is not None else {"seconds": rule_secs.get(ri)})
    if not hit: unmatched.append(f)
for ri in rule_order:
    if ri not in stop_excluded and ri not in rule_secs:
        truly_unknown[ri] = True
# A matched rule that states no cost makes every command it names
# unconditional -- including commands a priced rule also names. A
# reach-excluded rule contributes no commands at all (its `rule_cmds[ri]`
# stayed empty above), so it cannot make anything else mandatory.
for ri in rule_order:
    if ri not in rule_secs:
        mandatory.update(rule_cmds[ri])
# `default`/`always` commands go through the SAME reach classification as
# a rule's `run` - Codex round 4 BLOCK: they used to skip it entirely, so a
# command a matching RULE had just been excluded from Stop for could still
# reach Stop unattended through the fallback (default/always have no
# `reach` field of their own to declare, so every command here is treated
# as an undeclared rule would be). fallback_notices holds the reasons;
# `notices` itself is not defined yet at this point in the file.
fallback_notices = []
for c in cfg.get("always",[]) or []:
    _cls = _classify_run_reach([c]) if STOP_MODE else None
    if _cls is not None:
        fallback_notices.append("`always` command %r %s" % (c, _cls[1]))
        continue
    if c not in cmds: cmds.append(c)
    mandatory.add(c)
if not cmds:
    _default_kept = []
    for c in cfg.get("default",[]) or []:
        _cls = _classify_run_reach([c]) if STOP_MODE else None
        if _cls is not None:
            fallback_notices.append("`default` command %r %s" % (c, _cls[1]))
            continue
        _default_kept.append(c)
    cmds = _default_kept
    mandatory.update(cmds)

# --- the Stop budget ------------------------------------------------------
#
# A Stop gate that takes two minutes is a Stop gate people turn off, and
# .crew/verify.json carried its costs as PROSE in each `why` ("8s", "29s",
# "245s") which nothing could read. `seconds` is that number in a field.
#
# UNKNOWN COST IS NOT FREE. A rule with no `seconds` RUNS -- it is never
# deferred on the strength of a number nobody wrote down -- and the output
# says its cost is unstated. It is also left OUT of the budget arithmetic,
# because adding a guess would make the total a fiction; the summary says so
# rather than printing a number it cannot stand behind. Same rule this repo
# applies everywhere else: an unknown that cannot be measured stays an unknown
# and is labelled, instead of collapsing into a safe-looking value.
notices = []
deferred = []
chronic_rules = []
acute_rules = []

# Reach exclusions are decided at match time and do not depend on the
# budget arithmetic below - report them unconditionally.
for _ri in rule_order:
    if _ri in stop_excluded:
        _kind, _reason = stop_excluded[_ri]
        notices.append("verify-gate: rules[%d] %s" % (_ri, _reason))
for _fn in fallback_notices:
    notices.append("verify-gate: %s" % _fn)
for _ri in sorted(measured_used):
    notices.append("verify-gate: rules[%d] priced from a cached measurement (%ss, measured not declared) - "
                    "add `seconds` to verify.json to make this permanent" % (_ri, int(rule_secs[_ri])))

if budget is not None:
    unknown = [c for c in cmds if c not in cost]
    # MANDATORY-NESS IS A PROPERTY OF THE RULE, NOT OF A COMMAND ON ITS OWN,
    # and everything below follows from that.
    #
    # 0.19.94 hoisted each mandatory COMMAND to the front of the list and
    # charged it there. Both halves of that were wrong:
    #
    #   ORDER. A rule that declares `run: ["prepare", "check"]` has stated a
    #   dependency, and hoisting `check` ran it FIRST -- measured, in both
    #   flavours. The check then fails for a reason that is not the user's:
    #   they see their check red and go debugging their own code while the
    #   gate is what reordered it. A check that reports the wrong cause is
    #   worse than no check. A command's position inside its rule is part of
    #   the rule's meaning; being mandatory changes whether it can be
    #   DEFERRED, never where it RUNS.
    #
    #   CHARGE. The hoisted command was charged its rule's cost, and then the
    #   rule was charged again for the rest of its commands. Measured: a 40s
    #   rule running [A, B] with A in `always`, under the 60s default, ran A
    #   and DEFERRED B -- 40 + 40 against a rule that costs 40 once. That is
    #   the per-command double-charge 0.19.92 removed, reintroduced from the
    #   other end. Each command is charged exactly once however many sources
    #   name it, because each RULE is charged exactly once.
    #
    # So the obligation is lifted from the command to the rule that carries
    # it: a rule is mandatory when it states no cost, or when ANY command it
    # names is unconditional. Whole-rule is forced by the two invariants
    # together -- a rule runs whole or defers whole (0.19.92), and a command
    # keeps its place inside it, so `check` cannot run without the `prepare`
    # that precedes it.
    def rule_is_mandatory(ri):
        return (ri not in rule_secs
                or any(c in mandatory for c in rule_cmds[ri]))

    priced = [ri for ri in rule_order if ri in rule_secs]
    # Mandatory rules first, in first-match order -- they are not competing
    # for the budget, so sorting them by cost would only shuffle the order
    # the map was written in. Then the deferrable ones, ascending cost with
    # first-match order breaking ties: cheapest-first fits the most RULES in,
    # and a stable sort keeps the run order reproducible across two turns.
    must = [ri for ri in priced if rule_is_mandatory(ri)]
    may = sorted((ri for ri in priced if not rule_is_mandatory(ri)),
                 key=lambda ri: (rule_secs[ri], rule_order.index(ri)))
    spent, keep, overrun = 0, [], []
    for ri in must + may:
        # Only the commands this rule would ADD. A rule every one of whose
        # commands an earlier rule already scheduled asks for no new work, so
        # it is charged nothing rather than billed for a second run of the
        # same commands. This is also what keeps each command to one charge.
        fresh = [c for c in rule_cmds[ri] if c in cost and c not in keep]
        if not fresh:
            continue
        if ri in must:
            # Charged, so the arithmetic tells the truth about the turn and
            # the remaining budget shrinks by what the mandatory work costs.
            # The cost simply cannot buy a deferral.
            if spent + rule_secs[ri] > budget:
                overrun.extend(fresh)
            keep.extend(fresh)
            spent += rule_secs[ri]
        elif spent + rule_secs[ri] <= budget:
            # WHOLE, in the rule's own `run` order. Half a rule is not a
            # cheaper rule; it is a rule nobody can say ran.
            keep.extend(fresh)
            spent += rule_secs[ri]
        else:
            for c in fresh:
                if c not in deferred: deferred.append(c)
            # CHRONIC: this one rule alone costs more than the whole Stop
            # budget, so no reordering ever lets it fit - the OLD behaviour
            # (block the sha marker forever) turned a single expensive rule
            # into every rule re-running every turn, because the marker
            # never advanced and CHANGED kept accumulating from the same old
            # base. It must not silently block the baseline; it must also
            # never silently read as verified - see verify_record.py, which
            # persists it until it actually runs clean under --all.
            # ACUTE: it would fit alone; the budget was just spent by other
            # rules this turn. This still blocks the baseline, same as
            # before this feature existed - a fluke of ordering is not the
            # same claim as "this can never fit".
            if ri not in chronic_rules and ri not in acute_rules:
                (chronic_rules if rule_secs[ri] > budget else acute_rules).append(ri)
    # A command can be deferred by one rule and kept by a later, cheaper one
    # -- keeping wins, because the command does run.
    deferred = [c for c in deferred if c not in keep]
    # Unknown-cost commands run FIRST, so a map with no `seconds` anywhere
    # behaves exactly as it did before this feature existed.
    cmds = unknown + keep
    for c in unknown:
        notices.append("verify-gate: " + _identity_text(c) + " has no `seconds` in verify.json - cost UNSTATED, ran anyway")
    for c in overrun:
        notices.append("verify-gate: " + _identity_text(c) + " belongs to an unconditional rule (`always`, or no `seconds`) - it RAN past the budget; the cost is charged but cannot defer it")
    for c in deferred:
        notices.append("deferred to /crew:verify: " + _identity_text(c) + " (" + str(int(cost[c])) + "s)")
    for _ri in chronic_rules:
        notices.append("verify-gate: rules[%d] is permanently over budget (%ss > %ss stop budget) - "
                        "deferred every Stop; the baseline still advances past it, but this rule stays "
                        "UNVERIFIED until /crew:verify --all runs it." % (_ri, int(rule_secs[_ri]), int(budget)))
    if deferred:
        notices.append(
            "verify-gate: stop budget " + str(int(budget)) + "s; ran " + str(int(spent))
            + "s of stated cost"
            + (" plus " + str(len(unknown)) + " of unstated cost" if unknown else "")
            + ", deferred " + str(len(deferred))
            + ". The deferred ones were NOT checked - run /crew:verify.")
# Two records down one channel. The RECORD separator is \x1d (ASCII group
# separator) and the FIELD separator inside each record is \x1e; neither can
# appear in a command, because reject_unrepresentable above refused the map
# outright if one did. It used to be a bare newline, which a command
# containing one silently moved.
# Record 4 is now the ACUTE-deferred RULE count (budget contention this
# turn) rather than the deferred COMMAND count. A CHRONIC (permanently over
# budget) or reach-excluded rule is deliberately NOT counted here - see
# verify_record.py for why the baseline may advance past one of those while
# it still stays reported, forever, instead of collapsing into "verified".
acute_count = len(acute_rules)
# Record 5: the largest STATED cost among the commands actually selected.
# The lock uses it to size how long this run may legitimately go quiet
# for; 0 means nothing selected declared a cost. See lock_window below.
max_cost = max([cost[c] for c in cmds if c in cost] or [0])
# Record 6: JSON, everything the caller needs to persist per-rule status
# (via verify_record.py), pin env per rule, and cache a fresh measurement
# for a rule that ran with no declared or cached cost. Kept separate from
# records 1-5, which predate this feature, rather than folded into them.
matched_rules = []
for _ri in rule_order:
    if _ri in stop_excluded:
        _kind, _reason = stop_excluded[_ri]
    elif _ri in chronic_rules:
        _kind = "chronic"
        _reason = ("permanently over budget (%ss > %ss) - run /crew:verify --all"
                   % (int(rule_secs.get(_ri, 0)), int(budget) if budget is not None else 0))
    else:
        _kind, _reason = "normal", ""
    # rule_cmds[_ri] stays empty for a reach-excluded rule (it never runs),
    # so fall back to the rule's own `run` list straight from the map for
    # the label text. Either way, strip a possible \x1c+env suffix - the
    # label is for a human, not a lookup key.
    _first_cmd = _identity_text((rule_cmds.get(_ri) or (cfg["rules"][_ri].get("run") or [""]))[0])
    matched_rules.append({
        "key": _rule_keys.get(_ri, str(_ri)),
        "ri": _ri,
        "label": "rules[%d]: %s" % (_ri, _first_cmd[:80]),
        "kind": _kind,
        "reason": _reason,
        # IDENTITIES (text+env), not bare text - see _identity above. Kept
        # exactly as `cmds` carries them so cmd_log (built from the same
        # identities in the run loop) matches these one-to-one; a rule
        # sharing its command TEXT but not its ENV with another rule must
        # not be classified from the other rule's outcome.
        "cmds": rule_cmds.get(_ri, []),
        "unknown": bool(truly_unknown.get(_ri)),
    })
extras = json.dumps({"matched_rules": matched_rules})
sys.stdout.write("\x1e".join(cmds) + "\x1d" + "\x1e".join(unmatched) + "\x1d" + "\x1e".join(notices)
                 + "\x1d" + str(acute_count)
                 + "\x1d" + str(int(max_cost))
                 + "\x1d" + extras + "\n")
PY
)
# CAPTURE FIRST, STRIP SECOND - not piped directly through `tr -d '\r'` on
# the invocation line. A pipe's `$?` is the LAST command in it (tr, which
# always exits 0), so a `| tr -d '\r'` here would have thrown away
# PY_STATUS entirely: sys.exit(3)/sys.exit(4) (a corrupt or unrepresentable
# verify.json) silently read as 0, and every case below that exists to
# catch those two stopped firing. Measured: it broke four rule-framing
# tests outright, all expecting exit 2 and getting 0.
PY_STATUS=$?
MATCHED=$(printf '%s' "$MATCHED" | tr -d '\r')
rm -f "$CHANGED_FILE"
# Exit 3 is the ONLY status meaning "verify.json is bad" - it is raised by the
# explicit json.load guard above. Any other non-zero status means the matcher
# could not RUN at all, and reporting that as a parse error sends the reader
# off to debug a healthy file. Both still fail CLOSED - the severity was never
# the bug, the diagnosis was.
if [ "$PY_STATUS" -eq 3 ]; then
  echo "VERIFY GATE: .crew/verify.json could not be parsed. Verification did NOT run. Work is not complete." >&2
  exit 2
elif [ "$PY_STATUS" -eq 4 ]; then
  # Exit 4 is the OTHER kind of bad map: it parsed as JSON, and one of its
  # commands cannot be represented as a single command. The PARSE_ERROR line
  # above names the entry. A separate status from 3 because the two send the
  # reader to different places - a JSON error is a typo anywhere in the file,
  # this is one named entry that has to be rewritten.
  echo "VERIFY GATE: .crew/verify.json names a command crew cannot represent (see the PARSE_ERROR above for which one and why). Verification did NOT run. Work is not complete." >&2
  exit 2
elif [ "$PY_STATUS" -ne 0 ]; then
  echo "VERIFY GATE: could not RUN the matcher - python exited $PY_STATUS before parsing. .crew/verify.json was NOT shown to be invalid; do not go looking for corruption there. Verification did NOT run. Work is not complete." >&2
  exit 2
elif [ -z "$MATCHED" ]; then
  # PY_STATUS is 0 here (every nonzero case above already exited), yet the
  # matcher wrote NOTHING - not even the empty-but-structured six-field
  # record it always emits (`"\x1e".join(cmds) + "\x1d" + ...`) when
  # genuinely nothing matched. That is the signature of an interpreter that
  # "succeeded" without actually running any python at all - a WindowsApps
  # App Execution Alias stub is the concrete case: it is a real, executable
  # file, so plain `command -v` (and even this script's OLD `crew_py`-based
  # $PY) happily resolved it, invoked it, and it exited 0 having printed
  # nothing and evaluated no code. Before this check, that meant PY_STATUS
  # stayed 0, $MATCHED stayed empty, every field derived from it (CMDS,
  # NOTICES, ...) was empty too, ZERO rules ever ran, and the gate reached
  # the "everything passed" branch by default - a python-less Windows host's
  # DEFAULT state, exiting 0 having verified nothing. `$PY` is now resolved
  # via crew_py_strict (below the top-level `.crew/verify.json` read),
  # which already refuses a WindowsApps stub outright - see its own header
  # in _common.sh - so this specific reproduction should not reach here at
  # all any more. Kept as a second, independent line of defence rather than
  # trusting crew_py_strict alone to never have a gap: "the matcher produced
  # nothing" is treated as UNKNOWN, and unknown must never collapse into the
  # safe-looking (exit 0, zero rules) value - see CLAUDE.md's own named
  # recurring defect. `.crew/verify.json` is already known to exist here
  # (the `[ ! -f .crew/verify.json ]` check above returned long before this
  # point), so its absence is not the explanation either.
  echo "VERIFY GATE: the matcher produced no output at all, even though it exited 0 and .crew/verify.json exists. This is the signature of a broken interpreter (for example a WindowsApps stub) succeeding without actually running any python code. Work is not complete. Install python (3.10+) on this machine, or set \"verifyGate\": false in .crew/config.json to stand this gate down deliberately (honoured at the top of this file)." >&2
  exit 2
fi
# \035 is the record separator the matcher wrote between the two records, and
# \036 the field separator inside each. `sed -n 1p` used to take the first
# NEWLINE-delimited line, which is what a command containing a newline moved.
CMDS=$(printf '%s\n' "$MATCHED" | tr '\035' '\n' | sed -n 1p | tr '\036' '\n')
UNMAPPED=$(printf '%s\n' "$MATCHED" | tr '\035' '\n' | sed -n 2p | tr '\036' '\n')
# Record 3: the budget's own account of itself -- which commands were
# deferred and what they cost, and which ran with no stated cost at all.
# Printed BEFORE the run, so a turn that is killed part-way still says what
# it was never going to check.
NOTICES=$(printf '%s\n' "$MATCHED" | tr '\035' '\n' | sed -n 3p | tr '\036' '\n')
# The deferred COUNT, kept apart from the notice text on purpose -- see the
# matcher. This is what decides whether this run may be recorded as verified.
# Defaults to 1 ("assume something was deferred") if the record is missing or
# not a number, so a matcher that cannot say leaves the baseline where it is.
# An unknown must never resolve to the permissive answer here.
DEFERRED_COUNT=$(printf '%s\n' "$MATCHED" | tr '\035' '\n' | sed -n 4p | tr '\036' '\n')
case "$DEFERRED_COUNT" in
  ""|*[!0-9]*) DEFERRED_COUNT=1 ;;
esac
# Record 5: the largest stated cost among the selected commands. Sizes the
# lock deadline (lock_window). Missing or unreadable means 0, which leaves
# the window at LOCK_TTL -- the behaviour before the deadline existed.
MAX_COST=$(printf '%s\n' "$MATCHED" | tr '\035' '\n' | sed -n 5p | tr '\036' '\n')
case "$MAX_COST" in
  ""|*[!0-9]*) MAX_COST=0 ;;
esac
# Record 6: JSON, everything verify_record.py needs after the run loop to
# persist per-rule status and update the measured-timings cache. A single
# line (json.dumps with no indent), so sed -n 6p on the \x1d split is safe.
EXTRAS=$(printf '%s\n' "$MATCHED" | tr '\035' '\n' | sed -n 6p)
if [ -n "$NOTICES" ]; then
  printf '%s\n' "$NOTICES" >&2
fi

# A rule's `run` string is bash-flavoured and most of .crew/verify.json's
# rules hardcode `python3` - but CLAUDE.md's own landmine holds here too:
# Git Bash ships with no python3 at all, so a rule that is otherwise
# perfectly satisfiable (this machine DOES have a working python, just as
# `python` or `py`) fails with "command not found", a false failure that has
# nothing to do with what the rule actually checks.
#
# Review round 1 correction: the FIRST version of this fix shimmed python3
# AND python AND py, unconditionally. That broke `py -3 -c ...` rules on a
# machine where `py` already worked: Windows' `py` launcher accepts a
# `-3`/`-2` version-select flag, and the naive `exec "$REAL" "$@"` wrapper
# forwarded `-3` straight into a plain CPython binary, which does not
# understand it ("Unknown option: -3"). Shimming a name that ALREADY
# resolves to a real, working interpreter can only break something that
# already worked - so this shims ONLY `python3`, and ONLY when `python3`
# itself does not already resolve. `python` and `py` are never touched.
#
# Built from crew_py_strict, NOT the plain crew_py $PY already resolved
# above - crew_py_strict is the PROVED resolver (it actually RUNS the
# candidate and checks `sys.executable`, rejecting a WindowsApps stub that
# `command -v` alone cannot tell from a real interpreter; see its header in
# _common.sh), so the shim wraps a genuinely working, absolute path rather
# than whatever `command -v` merely found on PATH.
#
# NOT rewriting every rule's `run` array to reference a $CREW_PY variable
# instead - .crew/verify.json is read by more than this gate (see
# verification-harness.md's "What .crew/verify.json actually maps" and any
# /crew:verify tooling that reads `run` directly), and a command string is
# only portable to those OTHER readers if it still says `python3`, not a
# variable this gate alone exports. The shim is invisible to anything that
# does not go through this loop's PATH, and every rule command keeps
# reading exactly as written.
if ! command -v python3 >/dev/null 2>&1; then
  # crew_py_strict (in _common.sh) now OWNS the native-Windows-path
  # normalisation - cygpath -u when present, or (its own absence) lower-
  # casing the drive letter, dropping the `:`, and prepending a leading
  # `/` by hand, so EITHER way the result is the SAME absolute `/c/...`
  # shape, never a bare relative `C:/...` backslash->forward-slash swap
  # (that shape depends on the resolver's own cwd under `-x`, which the
  # absolute form does not - see crew_py_strict's own comment on this
  # exact point) - AND proves the result with `-x` before ever returning
  # it - see that function's own header comment. This file used to repeat
  # that exact conversion on crew_py_strict's OUTPUT, from when the two
  # were fixed independently in different review lanes; once crew_py_strict
  # started normalising internally, the copy here became DEAD CODE (never
  # reached - crew_py_strict either returns an already-POSIX, already-`-x`-
  # proved path, or nothing at all) and a second place the exact same bug
  # could silently regress back into. Removed rather than left "harmless" -
  # trust the one function that owns this, not a second copy of its logic.
  SHIM_PY=$(crew_py_strict) || SHIM_PY=""
  if [ -n "$SHIM_PY" ]; then
    SHIM_DIR=$(mktemp -d 2>/dev/null) || SHIM_DIR=""
    if [ -n "$SHIM_DIR" ]; then
      # Single-quoted in the WRITTEN shim's own exec line, so it cannot be
      # tricked into expanding a `$` or backtick if the resolved path ever
      # contained one - any embedded single quote in $SHIM_PY is itself
      # escaped the standard POSIX way (close quote, backslash-escaped
      # quote, reopen quote) before being placed inside that pair.
      SHIM_PY_ESCAPED=$(printf '%s' "$SHIM_PY" | sed "s/'/'\\\\''/g")
      if printf '#!/bin/sh\nexec '\''%s'\'' "$@"\n' "$SHIM_PY_ESCAPED" > "$SHIM_DIR/python3" 2>/dev/null \
         && chmod +x "$SHIM_DIR/python3" 2>/dev/null; then
        PATH="$SHIM_DIR:$PATH"
        export PATH
        # Cleaned up on EVERY exit path (EXIT INT TERM HUP), via the shared
        # cleanup registry above rather than a `trap -p`-spliced string -
        # see that registry's own comment for why: this is the SECOND
        # stage registered into it (the lock's release is the first), and
        # a naive splice-based chain breaks on exactly a stage this deep.
        # Registering a function has no such depth limit at all.
        _crew_gate_cleanup_shim() { rm -rf "$SHIM_DIR" 2>/dev/null; }
        _crew_gate_register_cleanup _crew_gate_cleanup_shim
      else
        rm -rf "$SHIM_DIR" 2>/dev/null
        echo "verify-gate: could not build the python3 shim (temp dir not writable) - a rule hardcoding python3 may fail where python3 itself is absent" >&2
      fi
    else
      echo "verify-gate: could not build the python3 shim (no writable temp dir) - a rule hardcoding python3 may fail where python3 itself is absent" >&2
    fi
  else
    echo "verify-gate: no python3, python or py resolves to a PROVED working interpreter - a rule hardcoding python3 will fail with 'command not found'" >&2
  fi
fi
# $PY itself being empty (no python resolvable AT ALL via plain crew_py) is
# not handled here - the script already exited loudly ABOVE (`VERIFY GATE:
# no python ... exit 2`, at the top of this file) long before any rule
# could run, because reading the map at all requires it. See that comment
# for the PM ruling and why exit 2 - not 0 - is correct there.

FAILED=0
TOTAL_ELAPSED=0
# ANY_SKIPPED tracks whether ANY command this turn came back rc=77. A SKIP
# is neither a pass nor a fail, but it is also not a CHECK - recording the
# tree as verified (marker + fingerprint) over a rule that was SKIPPED, not
# run, would let the SAME skip silently keep skipping forever: the next Stop
# would hit the fingerprint match and never even attempt the command again,
# on the strength of a run that never actually checked it.
ANY_SKIPPED=0
# NDJSON accumulator: one line per command actually run this turn, with its
# outcome and elapsed time, fed to verify_record.py sync below. Built from
# python's own JSON encoding of $c rather than hand-quoted in bash, so a
# command carrying an unusual byte cannot corrupt the record the way a
# hand-built separator could.
CMD_LOG=""
# BEFORE the first rule, not only after it: the first rule is as able to
# exceed the TTL as any later one, and until this ran the lock carried no
# deadline at all.
lock_extend
# A THIRD chained trap layer (on top of the lock's own release trap and,
# when it fires, the python3 shim's) was tried here once, spliced the same
# way the shim splices onto the lock, to `kill $(jobs -p)` on every exit
# path - reaping whatever a rule's own command left backgrounded in THIS
# shell's job table. Reverted at the time: `trap -p SIG` re-quotes its
# output as a single-quoted string literal, escaping any embedded `'` as
# `'\''` (see the shim's own `SHIM_DIR` fragment two screens up, which is
# itself wrapped in literal quotes) - correct as a self-contained
# `trap -- '...' SIG` statement, but the shim's sed-based extraction (copied
# there) only strips the outer quoting and never un-escapes what is left,
# so splicing that text into a THIRD trap's double-quoted body left a bare
# `'\''` behind - not valid shell, and `bash: exit trap: ... unexpected
# EOF` at whichever signal actually fired it. Caught by
# test_shim_cleanup_does_not_clobber_the_lock_release_trap going from a
# clean EXIT to exactly that error the moment it ran after the shim. Two
# links of that chain (lock -> shim) survived only because the LOCK's own
# trap body had no embedded single quotes for the shim's extraction to
# mis-handle; a third link exposed the idiom's actual limit.
#
# Fixed generally since (BLOCK finding: a rule's own escaped process group
# outlived the whole gate being killed, because RULE_OUT_FILE alone - see
# its own comment two screens up - only ever protected this script's OWN
# read of a rule's output, never reached a rule still running when the
# gate itself is interrupted or times out): the lock's and the shim's
# trap-setting both now register a FUNCTION into the shared cleanup array
# declared just above the lock (`_crew_gate_register_cleanup`), and this
# rule loop registers a third stage there too, `_crew_gate_cleanup_rule_pgid`
# below, to kill whatever this rule's process group currently is on TERM,
# INT, HUP or EXIT - see that function's own comment for how it learns the
# right pgid despite the rule running inside its own subshell.
#
# `_CREW_GATE_RULE_PGID_FILE` names a file the CURRENTLY running rule's
# subshell writes its own target(s) into - a plain shell variable set
# inside that subshell would never be visible out here, since a
# subshell's assignments do not propagate to its parent, but a file both
# can read and write does. Reset to empty by the rule loop itself once a
# rule's subshell returns normally (nothing left to chase); this function
# only ever reads whatever is on disk RIGHT NOW, so it needs no
# coordination beyond that.
#
# Each line is "MODE ID": MODE is `g` (ID is a verified process-GROUP id,
# signalled via the negative-pid form) or `p` (ID is a bare pid, signalled
# directly, never negated). See `_crew_gate_pgid_of` and the writer below
# for why a single unconditional `g` is not safe for every line here.
_CREW_GATE_RULE_PGID_FILE=""
# Portable pgid lookup for THIS OWN process (never another user's, so no
# `ps -p` privilege gap applies): tries `/proc/<pid>/stat` first (no
# subprocess, Linux), falling back to `ps -o pgid=` (macOS's BSD ps and
# Git Bash's bundled ps both accept it) when /proc is absent or unreadable
# -- rather than branching on `uname`/`$OSTYPE`, per this repo's own rule
# to branch on what the tool actually does, not what OS it claims to be.
# Prints nothing (not a guess) when neither source yields a clean digit
# string, which the caller below treats as "cannot verify" and takes the
# safe branch accordingly.
_crew_gate_pgid_of() {
  local _crew_pid="$1" _crew_stat _crew_after _crew_pgid=""
  if [ -r "/proc/$_crew_pid/stat" ]; then
    _crew_stat=$(cat "/proc/$_crew_pid/stat" 2>/dev/null)
    # Field 5 (process group) is the 3rd field after `comm`'s closing
    # paren - split on the LAST `)`, not the first, since `comm` itself
    # may contain one; matches crew_fixtures.py's `_proc_start_ticks`.
    _crew_after=${_crew_stat##*\)}
    set -- $_crew_after
    _crew_pgid="${3:-}"
    case "$_crew_pgid" in ''|*[!0-9]*) _crew_pgid="" ;; esac
  fi
  if [ -z "$_crew_pgid" ]; then
    _crew_pgid=$(ps -o pgid= -p "$_crew_pid" 2>/dev/null | tr -d '[:space:]')
    case "$_crew_pgid" in ''|*[!0-9]*) _crew_pgid="" ;; esac
  fi
  printf '%s' "$_crew_pgid"
}
# BLOCK finding: a bare `p`-mode id names the RULE SUBSHELL itself, not a
# verified process group - unlike the `g` lines, signalling it is a direct
# `kill` on a single pid number, never negated. That subshell can already
# have exited (and been reaped by the rule loop's own `wait`, below) by the
# time this trap fires, and once reaped its pid is free for the OS to hand
# to a brand-new, entirely unrelated process. A stale sidecar plus that
# reuse means this trap would TERM/KILL a process this gate never started.
# Proof of ownership before any bare-pid signal: the id's OWN ppid, read via
# `ps` (portable across Linux/macOS/Git Bash, unlike a `/proc` read which
# assumes Linux), must equal this shell's own `$$` - every `p`-mode id is a
# direct child of this same top-level script, forked with a bare `&`, never
# a grandchild. Returns "unknown" (never a guess) when `ps` itself is
# unavailable or the pid is already gone, and the caller skips signalling
# rather than trust a check that could not run.
_crew_gate_pid_is_our_child() {
  local _crew_pid="$1" _crew_ppid
  _crew_ppid=$(ps -o ppid= -p "$_crew_pid" 2>/dev/null | tr -d '[:space:]')
  case "$_crew_ppid" in ''|*[!0-9]*) return 1 ;; esac
  [ "$_crew_ppid" = "$$" ]
}
_crew_gate_cleanup_rule_pgid() {
  [ -n "$_CREW_GATE_RULE_PGID_FILE" ] || return 0
  [ -f "$_CREW_GATE_RULE_PGID_FILE" ] || return 0
  local _crew_mode _crew_id _crew_pg_any_alive=0
  while IFS=' ' read -r _crew_mode _crew_id; do
    case "$_crew_id" in ''|*[!0-9]*) continue ;; esac
    case "$_crew_mode" in
      g) kill -TERM -- "-$_crew_id" 2>/dev/null ;;
      p) _crew_gate_pid_is_our_child "$_crew_id" && kill -TERM -- "$_crew_id" 2>/dev/null ;;
    esac
  done < "$_CREW_GATE_RULE_PGID_FILE"
  # Same "only pay the grace sleep when something is actually left" rule
  # the ordinary post-rule cleanup already follows, just below - never an
  # unconditional sleep on the signal path either.
  while IFS=' ' read -r _crew_mode _crew_id; do
    case "$_crew_id" in ''|*[!0-9]*) continue ;; esac
    case "$_crew_mode" in
      g) kill -0 -- "-$_crew_id" 2>/dev/null && _crew_pg_any_alive=1 ;;
      p) _crew_gate_pid_is_our_child "$_crew_id" && kill -0 -- "$_crew_id" 2>/dev/null && _crew_pg_any_alive=1 ;;
    esac
  done < "$_CREW_GATE_RULE_PGID_FILE"
  if [ "$_crew_pg_any_alive" -eq 1 ]; then
    sleep 0.2
    while IFS=' ' read -r _crew_mode _crew_id; do
      case "$_crew_id" in ''|*[!0-9]*) continue ;; esac
      case "$_crew_mode" in
        g) kill -KILL -- "-$_crew_id" 2>/dev/null ;;
        p) _crew_gate_pid_is_our_child "$_crew_id" && kill -KILL -- "$_crew_id" 2>/dev/null ;;
      esac
    done < "$_CREW_GATE_RULE_PGID_FILE"
  fi
}
_crew_gate_register_cleanup _crew_gate_cleanup_rule_pgid
while IFS= read -r IDENT; do
  [ -z "$IDENT" ] && continue
  # IDENT is a matcher IDENTITY: the literal command text, and - only when
  # its rule declared "env" - a \x1c-joined canonical env JSON. Split it via
  # python (never hand-parsed: IDENT can carry any byte a real command can)
  # rather than bash pattern matching, and `tr -d '\r'` the result: native
  # Windows python writes text-mode stdout, which turns every embedded '\n'
  # into '\r\n' -- and `sys.stdout.reconfigure(newline="\n")` upstream is
  # belt, this is suspenders. Measured without it: `unset "$VAR"` where $VAR
  # was "AWS_PROFILE\r" (a name nothing ever exports) silently left the
  # REAL AWS_PROFILE inherited from the caller's shell exported into the
  # check the pin exists to isolate from it.
  if [ -n "$PY" ]; then
    SPLIT=$("$PY" -c '
import sys
ident = sys.argv[1]
text, sep, envjson = ident.partition("\x1c")
print(text + "\x1e" + (envjson if sep else ""), end="")
' "$IDENT" 2>/dev/null | tr -d '\r')
  else
    SPLIT="$IDENT"$'\x1e'
  fi
  c="${SPLIT%%$'\x1e'*}"
  ENV_JSON="${SPLIT#*$'\x1e'}"
  # --- env pinning ---------------------------------------------------
  # Every PINNED_VARS name (verify_record.py: ENV, AWS_PROFILE, ... TF_VAR_environment) is
  # unset for every rule command UNLESS the owning rule declares "env" for
  # it, in which case exactly those declared values are exported instead.
  # A gate whose target is chosen by whatever the calling shell happened to
  # have set cannot be reasoned about - this is what stops an inherited
  # `ENV=prod` (or nothing at all, defaulting some downstream script at a
  # live host) from silently riding along into a check nobody pointed there.
  PIN_REPORT=""
  if [ -n "$PY" ] && [ -n "$ENV_JSON" ]; then
    ENV_LINES=$(printf '%s' "$ENV_JSON" | "$PY" -c '
import json, sys
try:
    spec = json.loads(sys.stdin.read() or "{}")
except ValueError:
    spec = {}
for v in ("ENV", "AWS_PROFILE", "AWS_DEFAULT_REGION", "KUBECONFIG", "TF_WORKSPACE",
          "AWS_REGION", "AWS_DEFAULT_PROFILE", "AZURE_SUBSCRIPTION_ID",
          "ARM_SUBSCRIPTION_ID", "TF_VAR_environment"):
    val = spec.get(v)
    if isinstance(val, str):
        print("SET\x1f" + v + "\x1f" + val)
    else:
        print("UNSET\x1f" + v)
' 2>/dev/null | tr -d '\r')
  else
    ENV_LINES=""
    for v in ENV AWS_PROFILE AWS_DEFAULT_REGION KUBECONFIG TF_WORKSPACE \
             AWS_REGION AWS_DEFAULT_PROFILE AZURE_SUBSCRIPTION_ID \
             ARM_SUBSCRIPTION_ID TF_VAR_environment; do
      ENV_LINES="${ENV_LINES}UNSET"$'\x1f'"$v"$'\n'
    done
  fi
  while IFS=$'\x1f' read -r ACTION VAR VAL; do
    [ -z "$ACTION" ] && continue
    if [ "$ACTION" = "SET" ]; then
      export "$VAR=$VAL"
      PIN_REPORT="$PIN_REPORT $VAR=(declared)"
    else
      unset "$VAR" 2>/dev/null || true
      PIN_REPORT="$PIN_REPORT $VAR=unset"
    fi
  done <<< "$ENV_LINES"
  echo "verify-gate: env pinned -$PIN_REPORT" >&2
  # </dev/null: a check that reads stdin (some test runners do) would otherwise
  # consume the rest of $CMDS from the here-string and silently skip those checks.
  RULE_START=$(date +%s)
  # Captured through a REGULAR FILE, not the `$(...)` pipe this used before
  # (kept as the fallback below for the one case a temp file cannot be
  # made). `$(...)` only reports EOF once EVERY process holding its
  # write end has closed it, not just the one command this line is
  # waiting on - so a rule that backgrounds something and does not itself
  # wait for it (`long-thing &`, a lock-extend-style loop, anything left
  # with `disown`) hands that write end to the grandchild too, and the
  # grandchild holding it open wedges THIS shell forever: not bounded by
  # anything the rule declared, and not something an external caller's own
  # timeout can fix by killing the direct child alone, since the
  # grandchild keeps the pipe open regardless. See
  # test_verify_gate_stop_gate_record.py's account of test_34 for the run
  # that first exposed a version of this. Reading a regular file has no
  # such rule: a read returns whatever bytes are on disk right now and
  # hits EOF at the file's current size regardless of who else still has
  # it open for writing, so a background grandchild can no longer hold
  # this shell's own read hostage.
  #
  # TMPDIR is not the only place this can be written, and it must never be
  # the pipe form again if it is unwritable: falling back to `$(eval "$c"
  # 2>&1 </dev/null)` re-opens exactly the wedge this file capture exists to
  # close (a rule that backgrounds something and does not wait on it hangs
  # THIS shell forever on a TMPDIR-unwritable host, e.g. `sh -c "sleep 60
  # &"`). `.crew/` already exists (verify.json lives there) and is inside
  # the repo this gate is already running against, so it is tried as a
  # second, repo-local location before refusing the rule outright.
  RULE_OUT_FILE=$(mktemp 2>/dev/null) || RULE_OUT_FILE=""
  if [ -z "$RULE_OUT_FILE" ]; then
    RULE_OUT_FILE=$(mktemp ".crew/.verify-rule-out.XXXXXX" 2>/dev/null) || RULE_OUT_FILE=""
  fi
  if [ -n "$RULE_OUT_FILE" ]; then
    # Sidecar to RULE_OUT_FILE, same directory, so it is writable wherever
    # RULE_OUT_FILE already proved writable - the rule's subshell (below)
    # writes its own pgid(s) into this the moment each becomes known, and
    # `_crew_gate_cleanup_rule_pgid` (registered above, before this loop
    # started) is what reads it back if TERM/INT/HUP/EXIT lands while this
    # rule is still running.
    _CREW_GATE_RULE_PGID_FILE="$RULE_OUT_FILE.pgid"
    : > "$_CREW_GATE_RULE_PGID_FILE" 2>/dev/null
    # `( ... )`, not a bare `eval "$c"`: `$(...)` (the old form) forks a
    # subshell IMPLICITLY, which is why a rule command calling `exit N`
    # (`.crew/verify.json` rules do this routinely - "run": ["exit 1"]) only
    # ever exited THAT subshell rather than this whole script. Dropping the
    # pipe without also keeping an explicit subshell here loses that
    # isolation silently: `exit 77` in a rule would `exit 77` this entire
    # gate mid-loop instead of just failing the one rule. Caught by this
    # suite's own exit-77/exit-1 rule fixtures going from a named assertion
    # to a bare wrong-returncode failure, not by inspection.
    #
    # Wrapped in its own `( set -m; ... & wait ...)` subshell so the rule
    # runs in its OWN process group, not this script's: a rule that
    # backgrounds something and never waits on it itself (`sh -c 'yes &'`)
    # used to be recorded as PASSED (the foreground part of the rule can
    # exit 0 in under a second) while the orphaned background process kept
    # appending to $RULE_OUT_FILE's fd long after RC below was captured and
    # the file itself unlinked - an unlinked inode a backgrounded `yes`
    # can grow without bound, exhausting disk with nothing left in the
    # directory listing to show for it. `set -m` (job control) inside this
    # subshell only, not the whole script, makes bash give the backgrounded
    # job its own process group whose id equals its own pid - see the kill
    # below, which targets exactly that group and never the calling
    # script's own. A rule this well-behaved (nothing left running once its
    # own foreground command exits) is unaffected: the kill below finds
    # nothing left to signal.
    #
    # `set -m` also takes THIS subshell itself out of the gate's own
    # process group on some hosts (job-control shells that enable it
    # commonly re-group themselves, needed or not, to manage a controlling
    # terminal) - measured directly: signalling the gate's own group from
    # outside left this subshell (and everything backgrounded from it)
    # running, because by then it belonged to a group that signal never
    # reached. `$BASHPID` (this subshell's own pid, hence its own pgid IF
    # it re-grouped) is recorded FIRST, before anything is backgrounded, so
    # `_crew_gate_cleanup_rule_pgid` has a target even if the gate is
    # signalled before `RULE_PID` exists at all.
    #
    # BLOCK (review): recording `$BASHPID` as a GROUP id used to be
    # unconditional - correct only on hosts where `set -m` actually did
    # re-group this subshell. Where it did NOT (the "some hosts" above is
    # not every host), `$BASHPID`'s real process group is still whatever
    # this subshell inherited - almost certainly the GATE's own - and
    # `kill -TERM -- "-$BASHPID"` at that exact window either signals a
    # process group that does not happen to be numbered `$BASHPID` (a
    # silent no-op: the rule survives, uncancelled) or, worse, the gate's
    # own group, by coincidence of numbering. `_crew_gate_pgid_of` proves
    # which case this is BEFORE anything is recorded: verified as its own
    # leader, `$BASHPID` is written in `g` (group) mode exactly as before;
    # otherwise it is written in `p` (plain pid) mode instead, so cleanup
    # signals this ONE subshell process directly rather than guessing at
    # a group it cannot prove exists.
    (
      set -m
      if [ "$(_crew_gate_pgid_of "$BASHPID")" = "$BASHPID" ]; then
        printf 'g %s\n' "$BASHPID" >> "$_CREW_GATE_RULE_PGID_FILE" 2>/dev/null
      else
        printf 'p %s\n' "$BASHPID" >> "$_CREW_GATE_RULE_PGID_FILE" 2>/dev/null
      fi
      ( eval "$c" ) >"$RULE_OUT_FILE" 2>&1 </dev/null &
      RULE_PID=$!
      # RULE_PID needs no such verification: `set -m` (enabled just above,
      # in THIS subshell) is what makes bash give a background job its own
      # process group whose id equals its own pid in the first place -
      # documented job-control behaviour, not a per-host implementation
      # detail the way this subshell's OWN re-grouping is.
      printf 'g %s\n' "$RULE_PID" >> "$_CREW_GATE_RULE_PGID_FILE" 2>/dev/null
      wait "$RULE_PID" 2>/dev/null
      RC=$?
      # TERM the whole group first, then a short grace period, then KILL
      # anything that ignored it (some fixtures do this on purpose, e.g.
      # `trap '' TERM`). `-$RULE_PID` is a process-GROUP id here (the
      # negative-pid form of `kill`), never the direct pid alone - a lone
      # `kill "$RULE_PID"` only reaches the rule's own foreground process,
      # which has usually already exited by the time we get here, and does
      # nothing about a grandchild it backgrounded.
      kill -TERM -- "-$RULE_PID" 2>/dev/null
      # Only pay the grace period when TERM had something left to reach:
      # an ordinary rule (nothing backgrounded, or a backgrounded child
      # that already exited with its foreground command) has an empty
      # group the instant `wait` above returns, so both `kill`s here are
      # already no-ops against a group with no members left - `kill -0`
      # on that same negative pid reports exactly that, and this skips
      # the fixed 0.2s otherwise charged to every rule regardless. A rule
      # that DOES leave something running (this suite's own `trap ''
      # TERM` fixtures) still sees a member alive here and still gets the
      # grace period before KILL.
      if kill -0 -- "-$RULE_PID" 2>/dev/null; then
        sleep 0.2
        kill -KILL -- "-$RULE_PID" 2>/dev/null
      fi
      exit "$RC"
    ) &
    # Backgrounded and `wait`-ed on by PID, rather than run as a plain
    # foreground compound command (which is what this was before this
    # fix) - NOT to change what this subshell does, only how THIS shell,
    # the gate itself, blocks on it. A signal for which a trap is set is
    # deferred, by bash's own documented behaviour, until whatever
    # FOREGROUND command is currently running completes - so a bare
    # `kill $gate_pid` (as opposed to a whole-process-GROUP kill, which
    # reaches this subshell directly too) landed on the gate alone used to
    # sit unactioned for as long as the rule itself ran, defeating the
    # TERM/INT/HUP trap above entirely for that one repro shape. The
    # `wait` BUILTIN is the documented exception: interrupted immediately
    # by a trapped signal, trap runs, `wait` returns >128 right away -
    # exactly the promptness `_crew_gate_cleanup_rule_pgid` needs to act
    # on a rule that is still running.
    RULE_SUBSHELL_PID=$!
    wait "$RULE_SUBSHELL_PID" 2>/dev/null
    RC=$?
    # The subshell above has already returned, taking with it every group
    # it could have made for itself or for RULE_PID (see the comment
    # beside `set -m` above) - nothing is left for
    # `_crew_gate_cleanup_rule_pgid` to chase for THIS rule, and a LATER
    # signal must not try. The GUARD VARIABLE is cleared first, as the very
    # next statement after RC is captured (nothing may go between them
    # besides that capture itself, or a signal landing in the gap would see
    # a not-yet-cleared guard) - the trap checks this variable before ever
    # reading the file, so clearing it is what actually closes the window,
    # not the file truncation that follows. Truncating the file first and
    # the variable second (the previous order) left exactly that window
    # open: the subshell's own pid had already been reaped by the `wait`
    # above, freeing it for OS reuse, while the sidecar still named it and
    # the trap's own check still passed. See `_crew_gate_pid_is_our_child`
    # above for the second half of this fix - the proof required before a
    # `p`-mode id already past this point is ever signalled at all.
    _CREW_GATE_RULE_PGID_DONE_FILE="$_CREW_GATE_RULE_PGID_FILE"
    _CREW_GATE_RULE_PGID_FILE=""
    : > "$_CREW_GATE_RULE_PGID_DONE_FILE" 2>/dev/null
    # Snapshot the size the moment the rule's OWN process exits, then read
    # exactly that many bytes -- never the whole file as it stands when
    # `cat` gets around to it. A backgrounded grandchild that keeps writing
    # after RC is captured (`sh -c 'yes &'`, continuously appending to the
    # same fd) keeps a bare `cat`/`$(<file)` read chasing a file that never
    # stops growing, which is the same non-terminating shape the pipe
    # capture produced, moved from "EOF never arrives on a pipe" to "EOF
    # never arrives on a file being appended to concurrently". `stat` is one
    # syscall against the size on disk right now; it does not read the
    # file's growing content and so cannot itself be made to wait on it.
    # Capped as well, independent of the grandchild: nothing downstream
    # needs more than a `tail -25` of this, and a rule that legitimately
    # writes megabytes of its own output before backgrounding anything
    # should not turn a bounded gate into an unbounded read either. The
    # env override exists for this suite's own tests only (proving the cap
    # is enforced without writing gigabytes to prove it) - no operator-facing
    # doc names it, and it must never be set outside a test process.
    RULE_OUT_SIZE=$(stat -c%s "$RULE_OUT_FILE" 2>/dev/null || stat -f%z "$RULE_OUT_FILE" 2>/dev/null || echo 0)
    case "$RULE_OUT_SIZE" in ''|*[!0-9]*) RULE_OUT_SIZE=0 ;; esac
    RULE_OUT_CAP=${CREW_VERIFY_GATE_TEST_RULE_OUT_CAP:-1048576}
    # Digits only, and (once digits are confirmed) actually in range: the
    # override is test-only, but an out-of-range value here is not a
    # hypothetical - 0 disables the cap entirely (every rule's full
    # output, unbounded) and anything past 1 MiB defeats the reason this
    # cap exists at all. The 8-`?` glob rejects an over-long digit string
    # BEFORE the numeric compare below - `[ -lt ]` on a huge digit string
    # can itself error ("integer expression expected") rather than compare
    # cleanly - without rejecting a valid 7-digit value first: every
    # in-range value is at most 7 digits (1048576 itself is 7), so the
    # glob only needs to catch 8 OR MORE, and the numeric compare right
    # below still does the actual 1..1048576 validation. A 7-`?` glob
    # (matching length >= 7, not > 7) used to reject every valid 7-digit
    # value too, including in-range ones like 1000000.
    case "$RULE_OUT_CAP" in
      ''|*[!0-9]*|????????*) RULE_OUT_CAP=1048576 ;;
    esac
    if [ "$RULE_OUT_CAP" -lt 1 ] || [ "$RULE_OUT_CAP" -gt 1048576 ]; then
      RULE_OUT_CAP=1048576
    fi
    if [ "$RULE_OUT_SIZE" -gt "$RULE_OUT_CAP" ]; then RULE_OUT_SIZE=$RULE_OUT_CAP; fi
    # `tail -c`, not `head -c`: what a failing rule needs downstream is its
    # LAST `tail -25` lines - the actual error, which for any rule producing
    # more than the cap is at the END of the file, not the start. Reading
    # the first $RULE_OUT_SIZE bytes instead (the old `head -c` form)
    # discarded exactly the diagnostic this capture exists to preserve: a
    # rule that prints megabytes of build noise before its one real failure
    # line read as an opaque, truncated wall of noise with the actual error
    # cut off. `tail -c N` on a REGULAR file seeks near EOF directly rather
    # than reading the whole file to get there, so this keeps the same
    # bounded-cost property `stat`+cap already established - it is not a
    # return to an unbounded read.
    OUT=$(tail -c "$RULE_OUT_SIZE" "$RULE_OUT_FILE" 2>/dev/null)
    rm -f "$RULE_OUT_FILE" "$RULE_OUT_FILE.pgid"
  else
    # Neither TMPDIR nor .crew/ is writable: refuse this rule with a named
    # reason instead of running it through the pipe form. A check that
    # cannot capture its own output safely is not a check that ran. The
    # "VERIFY FAILED: $c" header and this message both print below, through
    # the same RC-ne-0 branch every other rule failure goes through.
    OUT="verify-gate: cannot create an output-capture file (TMPDIR and .crew/ both unwritable) - refusing rather than falling back to a pipe capture that a backgrounded grandchild can wedge forever"
    RC=1
  fi
  # Exit 77 is SKIP, the _verify/smoke.sh and GNU automake convention for
  # "skipped, environment absent" -- not a pass, not a fail. It must not
  # fail the turn, and it must not be recorded as verified either: it is
  # listed with the deferred/chronic ones below, via CMD_STATUS.
  if [ "$RC" -eq 77 ]; then
    echo "verify-gate: SKIP (rc 77, environment absent): $c" >&2
    CMD_STATUS="skip77"
    ANY_SKIPPED=1
  elif [ "$RC" -ne 0 ]; then
    echo "VERIFY FAILED: $c" >&2
    echo "$OUT" | tail -25 >&2
    FAILED=1
    CMD_STATUS="fail"
  else
    CMD_STATUS="pass"
  fi
  RULE_ELAPSED=$(( $(date +%s) - RULE_START ))
  TOTAL_ELAPSED=$(( TOTAL_ELAPSED + RULE_ELAPSED ))
  echo "verify-gate: ${RULE_ELAPSED}s  $c" >&2
  if [ -n "$PY" ]; then
    # $IDENT, not $c: matched_rules[...].cmds carries identities (text+env),
    # so the record-sync classification (which matches THIS log against
    # those lists) has to key on the same thing, or two rules sharing
    # command text under different env would collide back into one entry.
    LOG_LINE=$("$PY" -c 'import json,sys; print(json.dumps({"cmd": sys.argv[1], "status": sys.argv[2], "elapsed": int(sys.argv[3])}))' "$IDENT" "$CMD_STATUS" "$RULE_ELAPSED" 2>/dev/null | tr -d '\r')
    [ -n "$LOG_LINE" ] && CMD_LOG="$CMD_LOG
$LOG_LINE"
  fi
  # Heartbeat AFTER the rule, not before: the lock's age then means "no rule
  # has finished in this long", which is the only reading that distinguishes a
  # slow live run from an abandoned one without asking whether a pid is alive
  # -- a question this platform answers wrongly (see the 2026-09-13 note).
  lock_touch
  # Re-publish the deadline after each rule for the same reason the
  # heartbeat is here: it means 'measured from the last rule that
  # finished', so a long run keeps extending while it makes progress.
  lock_extend
done <<< "$CMDS"

echo "verify-gate: ${TOTAL_ELAPSED}s total across $(printf '%s
' "$CMDS" | grep -c .) rule command(s)" >&2

if [ -n "$UNMAPPED" ] && grep -q '"unmapped"[[:space:]]*:[[:space:]]*"fail"' .crew/verify.json; then
  echo "UNMAPPED CHANGES - .crew/verify.json has no rule for:" >&2
  echo "$UNMAPPED" >&2
  echo "Add a rule (or mark it deliberately unchecked) before reporting this complete." >&2
  FAILED=1
fi

# DELETE THE STALE FINGERPRINT BEFORE ANY EARLY EXIT, including the sync
# and the FAILED check below it - Codex round 4 FIX: this delete used to
# sit AFTER `[ "$FAILED" -eq 0 ] || exit 2`, so a turn where ONE command
# returned 77 (SKIP) and a DIFFERENT command failed outright never reached
# it at all - `exit 2` fired first. The earlier PASS fingerprint then
# survived a SKIP it should have invalidated, and the very next Stop could
# fingerprint-skip past the outstanding SKIP once the failing command was
# reverted. Depends on nothing but ANY_SKIPPED, so it runs before every
# other way this script can leave early.
if [ "$ANY_SKIPPED" -ne 0 ]; then
  rm -f "$FP_FILE" 2>/dev/null
fi

# Per-rule record sync now runs BEFORE the FAILED early exit below, on
# EVERY turn -- round 5 FIX (verify-gate.sh:1403, this comment's own former
# home). It used to sit AFTER `[ "$FAILED" -eq 0 ] || exit 2`, reached "only
# on a turn where nothing FAILED", on the reasoning that "an unreliable run
# should not overwrite what a previous clean run recorded". That reasoning
# is right at the SHA-marker/fingerprint granularity (a failed turn must
# never look fully verified) and wrong at the PER-RULE granularity the sync
# actually writes at: one failing rule among many discarded every OTHER
# rule's passing evidence too, because the whole sync call was skipped.
# `.crew/verify.json:193` recorded the measured cost of that: one absent
# `node_modules` kept three unrelated rules UNVERIFIED and the sha marker
# frozen 14 commits behind HEAD.
#
# What may now be written on a FAILED turn: per-rule PASS/SKIP/chronic/
# reach-excluded entries exactly as before. The FAILING rule's own outcome
# is deliberately NOT persisted -- an earlier version of this fix DID write
# a "failed" entry, and was itself reviewed BLOCK: that entry orphaned the
# moment the rule was EDITED to fix the failure, because rule_key() hashes
# `run`, so the old "failed" key stopped matching _current_rule_keys() and
# the stale-obligation prune held the marker hostage behind a rule that was
# already fixed. See verify_record.py's `_sync`, the "fail" branch, for the
# full reasoning -- the exit code (2) already carries the failure for THIS
# turn, and nothing needs to survive to the next one, because a FAILED turn
# never advances either marker anyway (see the next paragraph). What still
# may NOT happen on a FAILED turn: either whole-tree marker advancing. That
# guarantee does
# not come from anything in the sync call itself -- it comes from the
# `exit 2` immediately below still running AFTER the sync, unconditionally
# on $FAILED, and BEFORE the marker-advance block further down. A sync
# write failure changes nothing about that: SYNC_STATUS is not consulted by
# the exit-2 check, only by the marker-advance block a FAILED turn never
# reaches.
#
# SENTINEL, NOT 0. This used to start at 0 ("success") and only get
# reassigned INSIDE the `-n "$PY"` / `-f "$SYNC_PY"` guards -- so with no
# python on PATH, or verify_record.py missing, SYNC_STATUS silently stayed
# 0 and the decision below read "sync succeeded" from a sync that never
# even RAN. Found by the powershell-security-hardening review: hide python,
# add a reach-excluded rule, run Stop once -- the notice printed, the
# record was never touched, and both markers advanced anyway. 99 means "not
# yet confirmed"; only a sync that actually completed may set it to 0.
SYNC_STATUS=99
if [ -n "$PY" ] && [ -n "$EXTRAS" ]; then
  SYNC_PY="$FP_DIR/verify_record.py"
  if [ -f "$SYNC_PY" ]; then
    SYNC_SHA=$(git rev-parse HEAD 2>/dev/null)
    "$PY" -c '
import json, sys
try:
    sys.stdout.reconfigure(newline="\n")
except (AttributeError, ValueError):
    pass
extras = json.loads(sys.argv[1])
cmd_log = []
for line in sys.stdin.read().split("\n"):
    line = line.strip()
    if not line:
        continue
    try:
        cmd_log.append(json.loads(line))
    except ValueError:
        pass
print(json.dumps({"sha": sys.argv[2], "all": sys.argv[3] == "--all", "matched_rules": extras.get("matched_rules", []), "cmd_log": cmd_log}))
' "$EXTRAS" "$SYNC_SHA" "$BUDGET_FLAG" <<< "$CMD_LOG" | tr -d '\r' | "$PY" "$SYNC_PY" sync >&2
    SYNC_STATUS=$?
  else
    echo "verify-gate: could not sync the record (verify_record.py not found at $SYNC_PY); NOT advancing the marker" >&2
  fi
else
  echo "verify-gate: could not sync the record (no python, or the matcher produced no record data); NOT advancing the marker" >&2
fi

# A FAILED turn stops here, after its own evidence (and every passing
# rule's) has just been synced above -- never before. SYNC_STATUS plays no
# part in this decision on purpose: whether the record write succeeded or
# not, a turn with a real failure exits 2 either way.
[ "$FAILED" -eq 0 ] || exit 2

# THREE things must ALL hold before either marker may advance: nothing was
# ACUTELY deferred (fully_verified), nothing SKIPPED (rc 77 is not a check),
# and the per-rule record actually made it to disk (SYNC_STATUS). Any one
# of the three failing means SOMETHING about this turn was not actually
# verified, or was verified but the record of it was lost - and the second
# case is exactly as dangerous as the first, since a lost chronic/skipped
# entry is a lost warning that never comes back on its own.
if fully_verified && [ "$ANY_SKIPPED" -eq 0 ] && [ "$SYNC_STATUS" -eq 0 ]; then
  record_verified
  record_verified_fingerprint
elif [ "$SYNC_STATUS" -ne 0 ]; then
  : # verify_record.py already printed why, on stderr, above.
elif [ "$ANY_SKIPPED" -ne 0 ]; then
  echo "verify-gate: the verified baseline was NOT advanced - at least one command exited 77 (SKIP) and was not actually checked this turn." >&2
else
  echo "verify-gate: the verified baseline was NOT advanced - $DEFERRED_COUNT rule command(s) were deferred and have not been checked against this tree." >&2
fi
exit 0
