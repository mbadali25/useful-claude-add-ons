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

CHANGED=$(git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)
[ -z "$CHANGED" ] && exit 0

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

MATCHED=$("$PY" - "$CHANGED" << 'PY'
import json,sys,fnmatch
changed=[l for l in sys.argv[1].split("\n") if l.strip()]
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
if [ "$PY_STATUS" -ne 0 ]; then
  echo "VERIFY GATE: .crew/verify.json could not be parsed. Verification did NOT run. Work is not complete." >&2
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
exit 0
