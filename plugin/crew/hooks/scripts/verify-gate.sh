#!/usr/bin/env bash

# Native Windows (no POSIX layer) runs the .ps1 twin instead; stand down here.
# This MUST come before the claim below: if we claimed first and then stood
# down, we would have taken the marker without doing the work, and verify-gate.ps1
# would lose the race and also not run -- an inert gate that reads as "passed".
case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) exit 0 ;; esac

# End-of-turn gate. Runs the checks that the CHANGED FILES actually require,
# from .crew/verify.json. Exit 2 = the work is not done.
INPUT=$(cat)
read_json() { python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get(sys.argv[1],""))' "$1" <<< "$INPUT" 2>/dev/null; }
SESSION=$(read_json session_id)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=$(command -v python3 || command -v python) || exit 0
"$PY" "$DIR/hook_once.py" verify-gate "$SESSION" || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
grep -q '"verifyGate"[[:space:]]*:[[:space:]]*false' .crew/config.json 2>/dev/null && exit 0

CHANGED=$(git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)
[ -z "$CHANGED" ] && exit 0

if [ ! -f .crew/verify.json ]; then
  [ -x ./scripts/smoke.sh ] || exit 0
  OUT=$(./scripts/smoke.sh 2>&1) || { echo "Smoke FAILED. Work is not complete." >&2; echo "$OUT" | grep -E '^(FAIL|SMOKE:)' >&2; exit 2; }
  exit 0
fi

MATCHED=$(python3 - "$CHANGED" << 'PY'
import json,sys,fnmatch
changed=[l for l in sys.argv[1].split("\n") if l.strip()]
cfg=json.load(open(".crew/verify.json"))
cmds, why, unmatched = [], [], []
for f in changed:
    hit=False
    for r in cfg.get("rules",[]):
        if any(fnmatch.fnmatch(f,p) for p in r["paths"]):
            hit=True
            for c in r["run"]:
                if c not in cmds: cmds.append(c); why.append(f'{c}  <- {f}')
    if not hit: unmatched.append(f)
for c in cfg.get("always",[]):
    if c not in cmds: cmds.append(c)
if not cmds: cmds = cfg.get("default",[])
print("\x1e".join(cmds))
print("\x1e".join(unmatched))
PY
)
CMDS=$(echo "$MATCHED" | sed -n 1p | tr '\036' '\n')
UNMAPPED=$(echo "$MATCHED" | sed -n 2p | tr '\036' '\n')

FAILED=0
while IFS= read -r c; do
  [ -z "$c" ] && continue
  if ! OUT=$(eval "$c" 2>&1); then
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
