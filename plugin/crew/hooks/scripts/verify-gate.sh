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
  CHANGED_N=$( { git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | grep -c . )
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
#      a baseline has to answer. It is machine-local (`.crew/` is gitignored),
#      because "what has been verified here" is a fact about this checkout and
#      travels with nobody.
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
CHANGED=$(git diff --name-only "$BASE" 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)
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
LOCK=".crew/.verify-gate.lock"
LOCK_TTL=700
RECLAIMED=0
# GNU stat and BSD stat spell this differently and neither accepts the
# other's flag; `date -r` is not portable here either, since BSD `date -r`
# reads its argument as epoch seconds rather than as a file.
lock_mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null; }
mkdir -p .crew 2>/dev/null
if ! mkdir "$LOCK" 2>/dev/null; then
  HOLDER_AT=$(lock_mtime "$LOCK" | tr -dc '0-9')
  # Unreadable mtime: assume held rather than reclaim on a guess.
  [ -z "$HOLDER_AT" ] && exit 0
  NOW=$(date +%s)
  [ $((NOW - HOLDER_AT)) -le "$LOCK_TTL" ] 2>/dev/null && exit 0
  rm -rf "$LOCK" 2>/dev/null
  mkdir "$LOCK" 2>/dev/null || exit 0
  RECLAIMED=1
fi
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

MATCHED=$("$PY" - "$CHANGED_FILE" << 'PY'
import json,sys,fnmatch,io
changed=[l for l in io.open(sys.argv[1],encoding="utf-8").read().split("\n") if l.strip()]
try:
    cfg=json.load(open(".crew/verify.json"))
except (OSError, ValueError) as e:
    print(f"PARSE_ERROR: {e}", file=sys.stderr)
    sys.exit(3)

def matches(path, pat):
    # fnmatch's * spans '/', so '**/*.tf' demands a literal slash and silently
    # skips every root-level file - exactly the ones a Terraform module keeps
    # at its root. Test the '**/'-stripped form as well.
    cands = {pat}
    if pat.startswith("**/"): cands.add(pat[3:])
    cands.add(pat.replace("/**/", "/"))
    return any(fnmatch.fnmatch(path, c) for c in cands)

cmds, unmatched = [], []
for f in changed:
    hit=False
    for r in cfg.get("rules",[]):
        if any(matches(f,p) for p in r["paths"]):
            hit=True
            for c in r["run"]:
                if c not in cmds: cmds.append(c)
    if not hit: unmatched.append(f)
for c in cfg.get("always",[]):
    if c not in cmds: cmds.append(c)
if not cmds: cmds = cfg.get("default",[])
print("\x1e".join(cmds))
print("\x1e".join(unmatched))
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
elif [ "$PY_STATUS" -ne 0 ]; then
  echo "VERIFY GATE: could not RUN the matcher - python exited $PY_STATUS before parsing. .crew/verify.json was NOT shown to be invalid; do not go looking for corruption there. Verification did NOT run. Work is not complete." >&2
  exit 2
fi
CMDS=$(echo "$MATCHED" | sed -n 1p | tr '\036' '\n')
UNMAPPED=$(echo "$MATCHED" | sed -n 2p | tr '\036' '\n')

FAILED=0
while IFS= read -r c; do
  [ -z "$c" ] && continue
  # </dev/null: a check that reads stdin (some test runners do) would otherwise
  # consume the rest of $CMDS from the here-string and silently skip those checks.
  if ! OUT=$(eval "$c" 2>&1 </dev/null); then
    echo "VERIFY FAILED: $c" >&2
    echo "$OUT" | tail -25 >&2
    FAILED=1
  fi
done <<< "$CMDS"

if [ -n "$UNMAPPED" ] && grep -q '"unmapped"[[:space:]]*:[[:space:]]*"fail"' .crew/verify.json; then
  echo "UNMAPPED CHANGES - .crew/verify.json has no rule for:" >&2
  echo "$UNMAPPED" >&2
  echo "Add a rule (or mark it deliberately unchecked) before reporting this complete." >&2
  FAILED=1
fi

[ "$FAILED" -eq 0 ] || exit 2

record_verified
exit 0
