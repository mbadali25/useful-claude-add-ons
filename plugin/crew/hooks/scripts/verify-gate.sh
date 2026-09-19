#!/usr/bin/env bash

. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

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
INPUT=$(cat 2>/dev/null)

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
CHANGED=$(git -c core.quotePath=false diff --name-only "$BASE" 2>/dev/null; git -c core.quotePath=false ls-files --others --exclude-standard 2>/dev/null)
CHANGED=$(printf '%s\n' "$CHANGED" | sort -u | sed '/^$/d')
if [ -z "$CHANGED" ]; then
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
# The event is not the gate; the STATE is -- pm_pulse.py makes the same
# argument in its own header for the same reason.
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
if [ "$UNLOCKED" -eq 0 ]; then
  # A token of our own, so a SECOND reclaimer that deleted our fresh lock and
  # took its own is detectable: whoever's token is on disk once both have
  # written owns the turn, and the other backs off instead of both running.
  LOCK_TOKEN="sh-$$-$(date +%s)-${RANDOM:-0}"
  trap 'if [ "$(cat "$LOCK/token" 2>/dev/null)" = "$LOCK_TOKEN" ]; then rm -rf "$LOCK" 2>/dev/null; fi' EXIT INT TERM
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
# The logic lives in scope_report.py, not here, for the reason pm-pulse.sh
# gives: the bash and PowerShell flavours must not drift, and the ticket is
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

PY=$(crew_py) || { echo "crew verify-gate: no python - cannot read .crew/verify.json" >&2; exit 0; }

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

MATCHED=$("$PY" - "$CHANGED_FILE" "$BUDGET_FLAG" << 'PY'
import json,sys,fnmatch,io
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
           "\x1e": "an ASCII record separator (0x1e)"}

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
for f in changed:
    hit=False
    for ri, r in enumerate(cfg.get("rules",[])):
        if any(matches(f,p) for p in r["paths"]):
            hit=True
            if ri not in rule_cmds:
                rule_cmds[ri] = []
                rule_order.append(ri)
                secs = r.get("seconds")
                if (isinstance(secs, (int, float))
                        and not isinstance(secs, bool) and secs >= 0):
                    rule_secs[ri] = secs
            for c in r["run"]:
                if c not in cmds: cmds.append(c)
                if c not in rule_cmds[ri]: rule_cmds[ri].append(c)
                note_cost(c, r)
    if not hit: unmatched.append(f)
# A matched rule that states no cost makes every command it names
# unconditional -- including commands a priced rule also names.
for ri in rule_order:
    if ri not in rule_secs:
        mandatory.update(rule_cmds[ri])
for c in cfg.get("always",[]) or []:
    if c not in cmds: cmds.append(c)
    mandatory.add(c)
if not cmds:
    cmds = cfg.get("default",[])
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
if budget is not None:
    unknown = [c for c in cmds if c not in cost]
    # Priced, and carrying an unconditional obligation from somewhere else.
    # These RUN. Their stated cost is still charged, so the arithmetic below
    # tells the truth about the turn and the remaining budget shrinks by what
    # the mandatory work actually costs -- it just cannot buy their deferral.
    forced = [c for c in cmds if c in cost and c in mandatory]
    # Ascending cost, first-match order breaking ties: cheapest-first fits the
    # most RULES into the budget, and a stable sort keeps the run order
    # reproducible for anyone comparing two turns.
    priced = sorted((ri for ri in rule_order if ri in rule_secs),
                    key=lambda ri: (rule_secs[ri], rule_order.index(ri)))
    spent, keep = 0, []
    for c in forced:
        keep.append(c)
        spent += cost[c]
    for ri in priced:
        # Only the commands this rule would ADD. A rule every one of whose
        # commands an earlier, cheaper rule already scheduled asks for no new
        # work, so it is charged nothing rather than billed for a second run
        # of the same commands -- the per-command double-charge one level up.
        fresh = [c for c in rule_cmds[ri] if c in cost and c not in keep]
        if not fresh:
            continue
        if spent + rule_secs[ri] <= budget:
            # WHOLE, in the rule's own `run` order. Half a rule is not a
            # cheaper rule; it is a rule nobody can say ran.
            keep.extend(fresh)
            spent += rule_secs[ri]
        else:
            for c in fresh:
                if c not in deferred: deferred.append(c)
    # A command can be deferred by one rule and kept by a later, cheaper one
    # -- keeping wins, because the command does run.
    deferred = [c for c in deferred if c not in keep]
    # Unknown-cost commands run FIRST, so a map with no `seconds` anywhere
    # behaves exactly as it did before this feature existed.
    cmds = unknown + keep
    for c in unknown:
        notices.append("verify-gate: " + c + " has no `seconds` in verify.json - cost UNSTATED, ran anyway")
    for c in forced:
        notices.append("verify-gate: " + c + " is unconditional (`always`, or named by a rule with no `seconds`) - it RAN; its stated " + str(int(cost[c])) + "s is charged but cannot defer it")
    for c in deferred:
        notices.append("deferred to /crew:verify: " + c + " (" + str(int(cost[c])) + "s)")
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
# Record 4 is the deferred COUNT, an integer, and it exists because the
# recording guard used to be `[ -z "$NOTICES" ]` -- a string-emptiness
# test doing a boolean's job. NOTICES is prose for a human and mixes two
# different facts: "a rule was deferred" and "a rule had no stated cost".
# Only the first means "not verified", so the two must not share a signal.
# Deriving the boolean by grepping the prose would be the same defect one
# layer along.
# Record 5: the largest STATED cost among the commands actually selected.
# The lock uses it to size how long this run may legitimately go quiet
# for; 0 means nothing selected declared a cost. See lock_window below.
max_cost = max([cost[c] for c in cmds if c in cost] or [0])
sys.stdout.write("\x1e".join(cmds) + "\x1d" + "\x1e".join(unmatched) + "\x1d" + "\x1e".join(notices)
                 + "\x1d" + str(len(deferred))
                 + "\x1d" + str(int(max_cost)) + "\n")
PY
)
PY_STATUS=$?
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
if [ -n "$NOTICES" ]; then
  printf '%s\n' "$NOTICES" >&2
fi

FAILED=0
TOTAL_ELAPSED=0
# BEFORE the first rule, not only after it: the first rule is as able to
# exceed the TTL as any later one, and until this ran the lock carried no
# deadline at all.
lock_extend
while IFS= read -r c; do
  [ -z "$c" ] && continue
  # </dev/null: a check that reads stdin (some test runners do) would otherwise
  # consume the rest of $CMDS from the here-string and silently skip those checks.
  RULE_START=$(date +%s)
  if ! OUT=$(eval "$c" 2>&1 </dev/null); then
    echo "VERIFY FAILED: $c" >&2
    echo "$OUT" | tail -25 >&2
    FAILED=1
  fi
  RULE_ELAPSED=$(( $(date +%s) - RULE_START ))
  TOTAL_ELAPSED=$(( TOTAL_ELAPSED + RULE_ELAPSED ))
  echo "verify-gate: ${RULE_ELAPSED}s  $c" >&2
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

[ "$FAILED" -eq 0 ] || exit 2

if fully_verified; then
  record_verified
  record_verified_fingerprint
else
  echo "verify-gate: the verified baseline was NOT advanced - $DEFERRED_COUNT rule command(s) were deferred and have not been checked against this tree." >&2
fi
exit 0
