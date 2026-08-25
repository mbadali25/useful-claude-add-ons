#!/usr/bin/env bash
#
# PreToolUse gate on deploys. Turns the parts of /crew:promote that ARE
# checkable from a hook into something that cannot be argued with.
#
# It fires only when the command being run matches a `deploy` command declared
# in .crew/verify.json -> environments. Everything else passes untouched.
#
# What it enforces, before the deploy runs:
#   1. `requires` - the upstream environment has a PASS row in
#      .work/PROMOTIONS.md for THIS sha. Not "a pass row" - this sha.
#   2. `rollback` - required for every gated environment. Either a runbook path
#      that exists and whose `last verified` is inside 90 days, or the literal
#      "none" plus a `rollbackReason`. An absent key blocks the deploy.
#   3. `requireHuman` - refuses unless an explicit approval marker for this sha
#      was written this session.
#   4. A clean tree - you cannot deploy a sha that is not what is committed.
#
# What it cannot enforce, and does not pretend to: that smoke, regression and
# verify actually ran AFTER the deploy. verify-gate.sh picks that up at Stop by
# refusing to end a turn that deployed and recorded nothing.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

INPUT=$(cat)
crew_tool_dispatch promote-gate.ps1 "$INPUT"

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
[ -f .crew/verify.json ] || exit 0

PY=$(crew_py) || exit 0   # no python: cannot read the map, so do not pretend to gate

if command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  CMD=$(printf '%s' "$INPUT" | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)
fi
CMD=$(crew_strip_cr "$CMD")
[ -z "$CMD" ] && exit 0

# Which environment, if any, does this command deploy to?
ENVNAME=$("$PY" - "$CMD" <<'PY' 2>/dev/null
import json, sys
cmd = sys.argv[1]
try:
    envs = json.load(open(".crew/verify.json")).get("environments", {})
except Exception:
    sys.exit(0)
for name, cfg in envs.items():
    for d in cfg.get("deploy", []):
        # Substring both ways: the declared command may be run with extra flags,
        # or wrapped. Deliberately generous - a missed match means no gate.
        if d and (d in cmd or cmd in d):
            print(name); sys.exit(0)
PY
)
[ -z "$ENVNAME" ] && exit 0

block() { echo "PROMOTION BLOCKED ($ENVNAME): $1" >&2; exit 2; }

SHA=$(git rev-parse --short HEAD 2>/dev/null)
[ -z "$SHA" ] && block "not a git repository - cannot establish what is being deployed."

# 4. clean tree
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  block "the working tree is dirty. You would be deploying \"$SHA\" plus changes that are in no commit and no review. Commit or stash first."
fi

# 1-3, read from the map
VERDICT=$("$PY" - "$ENVNAME" "$SHA" <<'PY' 2>/dev/null
import json, sys, os, re, datetime
env, sha = sys.argv[1], sys.argv[2]
cfg = json.load(open(".crew/verify.json")).get("environments", {}).get(env, {})
out = []

rows = ""
if os.path.exists(".work/PROMOTIONS.md"):
    rows = open(".work/PROMOTIONS.md", encoding="utf-8", errors="replace").read()

def passed(name, sha):
    for line in rows.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        # when | env | sha | smoke | regression | verify | by
        if cells[1] == name and cells[2].startswith(sha[:7]):
            return all(c.lower() == "pass" for c in cells[3:6])
    return False

for upstream in cfg.get("requires", []):
    if not passed(upstream, sha):
        out.append(f"'{upstream}' has no all-pass row for sha {sha} in .work/PROMOTIONS.md. "
                   f"Run /crew:promote {upstream} first, and let it record the result.")

# Fail CLOSED: an absent "rollback" key used to mean "no rollback needed".
# It now means "nobody said". The only way to deploy with no rollback plan is
# an explicit rollback: "none" plus a rollbackReason explaining why.
if "rollback" not in cfg:
    out.append(f"'{env}' has no 'rollback' key in .crew/verify.json. Add rollback: "
               f"\"<path to a runbook>\", or rollback: \"none\" plus a rollbackReason "
               f"string explaining why {env} does not need one. Fix: edit the "
               f"'{env}' block in .crew/verify.json.")
else:
    rb = cfg.get("rollback")
    if rb == "none":
        reason = str(cfg.get("rollbackReason") or "").strip()
        if not reason:
            out.append(f"'{env}' sets rollback: \"none\" but has no rollbackReason. "
                       f"State why {env} does not need a rollback plan. Fix: add a "
                       f"rollbackReason string next to rollback in .crew/verify.json.")
    elif not rb:
        out.append(f"'{env}' has rollback: {rb!r}, which is not a valid runbook path. "
                   f"Fix: set rollback to a runbook path, or to the literal string "
                   f"\"none\" plus a rollbackReason.")
    elif not os.path.exists(rb):
        out.append(f"the rollback runbook '{rb}' does not exist. No verified rollback, no deploy.")
    else:
        txt = open(rb, encoding="utf-8", errors="replace").read()
        m = re.search(r"last[ _-]?verified\s*[:=]\s*(\d{4}-\d{2}-\d{2})", txt, re.I)
        if not m:
            out.append(f"'{rb}' has no 'last verified: YYYY-MM-DD' line. An unverified rollback is not a rollback.")
        else:
            age = (datetime.date.today() - datetime.date.fromisoformat(m.group(1))).days
            if age > 90:
                out.append(f"'{rb}' was last verified {age} days ago (ceiling is 90). Re-run it against a real environment first.")

if cfg.get("requireHuman"):
    marker = f".crew/.approved-{env}-{sha}"
    if not os.path.exists(marker):
        out.append(f"this environment requires explicit human approval. Show the sha, the diff summary and the "
                   f"last promotion, get a yes, then: touch {marker}")

print("\x1e".join(out))
PY
)

if [ -n "$VERDICT" ]; then
  echo "PROMOTION BLOCKED ($ENVNAME, sha $SHA):" >&2
  printf '%s' "$VERDICT" | tr '\036' '\n' | sed 's/^/  - /' >&2
  echo "" >&2
  echo "These are the pre-deploy gates from .crew/verify.json. Fix them, or set" >&2
  echo "verifyGate:false in .crew/config.json if this repo should not be gated." >&2
  exit 2
fi

# Allowed. Record that a deploy happened so the Stop gate can insist on a
# PROMOTIONS row - a deploy nobody wrote down is a deploy nobody can audit.
mkdir -p .crew 2>/dev/null
printf '%s %s\n' "$ENVNAME" "$SHA" > .crew/.deploy-in-flight
exit 0
