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
# WHICH tree (T-0505). The sha and the clean-tree check are read from the tree
# the deploy RUNS FROM, not from CLAUDE_PROJECT_DIR: the payload `cwd` (else
# the project dir), moved by a leading `cd <dir> &&` chain, and named by any
# `git -C <dir>` in the command. It must be a worktree of the SAME repository
# as the project dir, and every literal sha in the command must be its HEAD.
# Judging the project dir blocked a clean worktree for the main checkout's
# dirt, named a sha that was not being deployed, and let a clean main checkout
# wave a dirty or wrong-sha worktree through.
#
# Policy and state stay in the project dir, deliberately: .crew/verify.json,
# .work/PROMOTIONS.md, .crew/.approved-<env>-<sha>, the rollback runbook, the
# incident files and .crew/.deploy-in-flight. `.work/` and `.crew/*` are
# per-checkout, gitignored state: a fresh worktree has none of it (reading it
# there would refuse every worktree deploy for a missing PASS row) and a
# throwaway worktree can hold a forged copy (reading it there would launder a
# sha). verify-gate.sh reads the in-flight marker and PROMOTIONS.md from the
# project dir too, so the Stop-time check keeps matching.
#
# What it cannot enforce, and does not pretend to: that smoke, regression and
# verify actually ran AFTER the deploy. verify-gate.sh picks that up at Stop by
# refusing to end a turn that deployed and recorded nothing.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

INPUT=$(cat)
crew_tool_dispatch promote-gate.ps1 "$INPUT"

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
# NO map at all is an opt-out: a repo that never wrote one is not gated, and
# that is the only state this line may pass. `-e`, not `-f`, on purpose -- a
# DIRECTORY named .crew/verify.json is not an opt-out, it is a map that cannot
# be read, and `-f` answered false for it and exited 0 here. Everything that
# exists goes on to the read below, which decides readable from unreadable.
#
# T-0505: "no map at all" means none in the working copy AND none committed.
# The map is read from this checkout while its dirt no longer blocks a deploy
# from a linked worktree, so an uncommitted change to it - an edit, a deletion,
# an untracked file - must not become policy. The working bytes are compared
# with HEAD's blob by `git hash-object` rather than trusted to `git status`,
# which skip-worktree and assume-unchanged silence (Codex r1). MAP_DIRTY is
# acted on once the command is known to be a deploy, matched against the
# working map AND the committed one, so an edit that renames the deploy
# command cannot make it match nothing.
HEAD_MAP=$(git rev-parse -q --verify "HEAD:./.crew/verify.json" 2>/dev/null)
MAP_DIRTY=""
if [ ! -e .crew/verify.json ]; then
  [ -z "$HEAD_MAP" ] && exit 0
  MAP_DIRTY="deleted, and committed at HEAD"
elif [ -n "$HEAD_MAP" ]; then
  WORK_MAP=$(git hash-object -- .crew/verify.json 2>/dev/null)
  if [ -z "$WORK_MAP" ]; then
    MAP_DIRTY="could not be hashed to compare with HEAD"
  elif [ "$WORK_MAP" != "$HEAD_MAP" ]; then
    MAP_DIRTY="differs from HEAD"
  fi
elif [ -n "$(git ls-files --others --exclude-standard -- .crew/verify.json 2>/dev/null)" ]; then
  MAP_DIRTY="untracked - in no commit"
fi

PY=$(crew_py) || exit 0   # no python: cannot read the map, so do not pretend to gate

if command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
  RUN_CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
else
  CMD=$(printf '%s' "$INPUT" | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)
  RUN_CWD=$(printf '%s' "$INPUT" | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("cwd") or "")' 2>/dev/null)
fi
CMD=$(crew_strip_cr "$CMD")
RUN_CWD=$(crew_strip_cr "$RUN_CWD")
[ -z "$CMD" ] && exit 0

# Which environment, if any, does this command deploy to? And - separately -
# could the map be read AT ALL?
#
# Fail CLOSED on a map that will not parse. `except Exception: sys.exit(0)`
# collapsed three different facts into one: an ABSENT verify.json (handled
# above, and an opt-out), an UNREADABLE one, and one holding something other
# than a map of environments. The last two are corruption, and a single stray
# comma in .crew/verify.json therefore removed every pre-deploy check while the
# deploy went ahead looking gated - no output, exit 0, byte-identical to "this
# command deploys nothing". promote-gate.ps1 fixed this first and carries the
# same reasoning at its own `ConvertFrom-Json`; this is the port.
#
# The EXIT STATUS carries the distinction, and the ONLY thing this step writes
# to stdout is an environment name: 3 unreadable, 4 malformed, 0 for a name or
# for nothing matching. Every reason goes to STDERR, unredirected, which is both
# how the reader sees it and what keeps the status check load-bearing - a reason
# printed to stdout would land in ENVNAME, be read as the name of an environment
# nobody declared, and block for an unrelated reason further down while this
# check was disabled. `VAR=$(cmd)` captures stdout only, so nothing on stderr
# can pollute ENVNAME and there is no reason to suppress it.
#
# A traceback lands as a non-zero status too, which blocks for the same reason
# and says so.
#
# Deliberately ABOVE the emergency lane, matching the .ps1: an incident turns an
# unmet precondition into a recorded skip, and every skip row names the
# environment - which is precisely what could not be determined here. There is
# nothing to record and nothing to stand down.
ENVNAME=$(CREW_HEAD_MAP="$HEAD_MAP" CREW_MAP_DIRTY="$MAP_DIRTY" "$PY" - "$CMD" <<'PY'
import json, os, shutil, subprocess, sys
cmd = sys.argv[1]


def unreadable(why, status):
    print(why, file=sys.stderr)
    sys.exit(status)


def matches(envs):
    """The first environment whose declared deploy matches `cmd`, or None.
    Only for the COMMITTED map below; the working map keeps its own strict
    reading."""
    for name, cfg in envs.items():
        declared = cfg.get("deploy", []) if isinstance(cfg, dict) else []
        declared = [declared] if isinstance(declared, str) else declared
        if not isinstance(declared, list):
            continue
        for d in declared:
            if isinstance(d, str) and d and (d in cmd or cmd in d):
                return name
    return None


# A dirty map is matched against the committed one too (T-0505). A committed
# map that cannot be read or has no readable environments is could-not-tell,
# status 3: with the working map dirty, "matched nothing" would be a guess.
if os.environ.get("CREW_MAP_DIRTY") and os.environ.get("CREW_HEAD_MAP"):
    git = shutil.which("git")
    if git is None:
        unreadable("the deploy map is uncommitted and git is not on PATH, so the "
                   "committed map cannot be read to compare with", 3)
    try:
        proc = subprocess.run([git, "cat-file", "blob", os.environ["CREW_HEAD_MAP"]],
                              capture_output=True, check=False, timeout=10,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        unreadable(f"the committed .crew/verify.json could not be read: {exc}", 3)
    if proc.returncode != 0:
        unreadable("the committed .crew/verify.json could not be read "
                   f"(git cat-file exited {proc.returncode})", 3)
    try:
        committed = json.loads(proc.stdout.decode("utf-8-sig", errors="replace"))
    except ValueError as exc:
        unreadable(f"the committed .crew/verify.json does not parse as JSON: {exc}", 3)
    committed_envs = committed.get("environments", {}) if isinstance(committed, dict) else None
    if not isinstance(committed_envs, dict):
        unreadable("the committed .crew/verify.json holds no object of environments", 3)
    hit = matches(committed_envs)
    if hit:
        print(hit); sys.exit(0)
    if not os.path.exists(".crew/verify.json"):
        sys.exit(0)


try:
    with open(".crew/verify.json", encoding="utf-8-sig", errors="replace") as fh:
        raw = fh.read()
except OSError as exc:
    unreadable(f".crew/verify.json exists and could not be read: {exc}", 3)
try:
    doc = json.loads(raw)
except ValueError as exc:
    unreadable(f".crew/verify.json does not parse as JSON: {exc}", 4)
if not isinstance(doc, dict):
    unreadable(f".crew/verify.json holds a JSON {type(doc).__name__}, "
               "not an object", 4)
envs = doc.get("environments", {})
if not isinstance(envs, dict):
    unreadable(f"`environments` in .crew/verify.json is a "
               f"{type(envs).__name__}, not an object, so no environment can "
               "be read out of it", 4)
for name, cfg in envs.items():
    if not isinstance(cfg, dict):
        unreadable(f"environment `{name}` in .crew/verify.json is a "
                   f"{type(cfg).__name__}, not an object", 4)
    declared = cfg.get("deploy", [])
    if isinstance(declared, str):
        # ONE command, not a list of them. The .ps1's `foreach` already reads a
        # bare string as a single entry; this loop iterated its CHARACTERS, so
        # `deploy: "deploy-prod"` matched any command containing a `d` and
        # `echo done` wrote a .crew/.deploy-in-flight marker for a deploy that
        # never happened - which the Stop gate then demands a PROMOTIONS row
        # for. Normalised here so both flavours read the same shape.
        declared = [declared]
    if not isinstance(declared, list) or not all(
            isinstance(d, str) for d in declared):
        unreadable(f"environment `{name}` in .crew/verify.json has a `deploy` "
                   "that is not a command or a list of commands", 4)
    for d in declared:
        # Substring both ways: the declared command may be run with extra flags,
        # or wrapped. Deliberately generous - a missed match means no gate.
        if d and (d in cmd or cmd in d):
            print(name); sys.exit(0)
PY
)
ENV_STATUS=$?

# Immediately after the substitution, like VERDICT_STATUS below: `set -uo
# pipefail` is on and `-e` is not, so anything between the two lines eats $?.
if [ "$ENV_STATUS" -ne 0 ]; then
  echo "PROMOTION BLOCKED: .crew/verify.json could not be read as a deployment map (exit $ENV_STATUS)." >&2
  echo "  The reason is printed above this line, on stderr, by the check itself" >&2
  echo "  - or, if nothing is there, the check crashed and the traceback is." >&2
  echo "  This is NOT a pass. Crew cannot tell whether this command deploys," >&2
  echo "  so it cannot tell whether a pre-deploy gate applies to it. Fix the" >&2
  echo "  JSON, or delete .crew/verify.json if this repo should not be gated." >&2
  exit 2
fi
[ -z "$ENVNAME" ] && exit 0

# Emergency lane: an open incident turns every block into a recorded skip.
# Deliberately here rather than at the top of the script, so the checks still
# RUN during an incident - they are file reads, not test suites, and the debt
# list is worth far more when it names the precondition that was unmet than
# when it says only "the promote gate stood down".
block() {
  if crew_incident_active; then
    crew_incident_log promote "$ENVNAME at ${SHA:-unknown-sha}: $1"
    exit 0
  fi
  echo "PROMOTION BLOCKED ($ENVNAME): $1" >&2
  exit 2
}

if [ -n "$MAP_DIRTY" ]; then
  block ".crew/verify.json in the project dir ($(pwd -P)) has uncommitted changes: it $MAP_DIRTY. The deploy map is policy; commit the change (it is then reviewed like any other) or revert it."
fi

PROJECT_TOP=$(git rev-parse --show-toplevel 2>/dev/null)
[ -z "$PROJECT_TOP" ] && block "not a git repository - cannot establish what is being deployed."

# The tree this deploy runs from (T-0505; the header says why). `cd` in a
# subshell resolves each step the way the shell running the command will,
# MSYS and Windows paths included; `pwd -P` makes two spellings of one
# directory compare equal.
resolve_dir() {
  local t=$2
  case "$t" in
    "~") t=$HOME ;;
    "~/"*) t="$HOME/${t#\~/}" ;;
  esac
  ( cd "$1" 2>/dev/null && cd "$t" 2>/dev/null && pwd -P )
}
# The common dir identifies the repository: every linked worktree shares it.
common_dir() {
  ( cd "$1" 2>/dev/null && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P )
}

BASE=$(pwd -P)
if [ -n "$RUN_CWD" ]; then
  BASE=$(resolve_dir "$BASE" "$RUN_CWD")
  [ -z "$BASE" ] && block "the command runs from '$RUN_CWD', which does not exist, so it is not inside a git worktree - cannot establish what is being deployed."
fi
RECORDS=$(PYTHONIOENCODING=utf-8 "$PY" "$(dirname "${BASH_SOURCE[0]}")/_promote_tree.py" "$CMD") \
  || block "the deploy command could not be parsed for the directory it runs from (_promote_tree.py failed). This is not a pass."
TREES=()
RUNDIRS=()
BARE=0
HEXES=()
while IFS=$'\t' read -r kind tok; do
  case "$kind" in
    cd)
      NEXT=$(resolve_dir "$BASE" "$tok")
      [ -z "$NEXT" ] && block "cannot tell which directory the deploy runs from: 'cd $tok' does not resolve from '$BASE'."
      BASE=$NEXT ;;
    bad)
      block "cannot tell which directory the deploy runs from: '$tok' is not a form the gate reads with certainty (a shell-expanded path, an unlisted git option, git inside quoted text), and it will not guess. Use a literal 'cd <dir> &&' or 'git -C <dir>'." ;;
    C)
      D=$(resolve_dir "$BASE" "$tok")
      [ -z "$D" ] && block "cannot tell which directory the deploy runs from: 'git -C $tok' does not resolve from '$BASE'."
      TREES+=("$D") ;;
    Crun)
      D=$(resolve_dir "$BASE" "$tok")
      [ -z "$D" ] && block "cannot tell which directory the deploy runs from: 'git -C $tok' does not resolve from '$BASE'."
      RUNDIRS+=("$D") ;;
    midcd)
      block "cannot tell which directory the deploy runs from: the command changes directory after it starts ('$tok'). Put the cd first - 'cd <dir> && <deploy>' - so the gate judges the tree the deploy runs in." ;;
    gitdir)
      block "cannot tell which tree the deploy reads: '$tok' points git at a repository by a route the gate does not follow. Use 'cd <dir> &&' or 'git -C <dir>'." ;;
    bare) BARE=1 ;;
    hex) HEXES+=("$tok") ;;
  esac
done <<EOF
$RECORDS
EOF
# The sha comes from `git -C`'s tree when there is one; from the chain's
# directory when there is none, or when a bare `git` also reads it. The chain's
# directory is ALSO where the deploy process runs, so it is checked for dirt
# and repository below whatever `-C` says (Codex r1: a clean `-C` tree must not
# launder a dirty tree the deploy executes in).
if [ "${#TREES[@]}" -eq 0 ] || [ "$BARE" -eq 1 ]; then
  TREES+=("$BASE")
fi
RUN_TOP=$(git -C "$BASE" rev-parse --show-toplevel 2>/dev/null)
[ -z "$RUN_TOP" ] && block "the deploy runs from '$BASE', which is not inside a git worktree - cannot establish what is being deployed."
# A `git -C` outside a command substitution feeds the deploy nothing, so it
# may only name the tree the deploy runs in (`deploy; echo git -C <wt>` must
# not make the gate judge <wt> while the deploy ships the payload cwd's sha).
for D in ${RUNDIRS[@]+"${RUNDIRS[@]}"}; do
  if [ "$(git -C "$D" rev-parse --show-toplevel 2>/dev/null)" != "$RUN_TOP" ]; then
    block "the command names 'git -C $D' outside a command substitution, which is not the tree the deploy runs in ('$RUN_TOP'). Use 'cd <dir> &&' so the deploy runs there, or '\$(git -C <dir> ...)' to feed it a sha."
  fi
done

TREE=""
for D in "${TREES[@]}"; do
  TOP=$(git -C "$D" rev-parse --show-toplevel 2>/dev/null)
  [ -z "$TOP" ] && block "the deploy runs from '$D', which is not inside a git worktree - cannot establish what is being deployed."
  if [ -z "$TREE" ]; then
    TREE=$TOP
  elif [ "$TOP" != "$TREE" ]; then
    block "the deploy command names more than one tree ('$TREE' and '$TOP'), so which sha is being deployed is ambiguous. Run it from one tree."
  fi
done

TREE_COMMON=$(common_dir "$TREE")
PROJECT_COMMON=$(common_dir "$PROJECT_TOP")
# Two failed lookups compare equal as two empty strings; that is not "same
# repository", it is "could not tell".
if [ -z "$TREE_COMMON" ] || [ -z "$PROJECT_COMMON" ]; then
  block "could not read the git common dir of '$TREE' or of '$PROJECT_TOP', so the gate cannot tell whether the deploy runs from this repository."
fi
if [ "$TREE_COMMON" != "$PROJECT_COMMON" ]; then
  block "the deploy runs from '$TREE', which is a worktree of a different repository than this project ('$PROJECT_TOP'). Its sha has no PASS row, marker or map here."
fi
if [ "$RUN_TOP" != "$TREE" ] && [ "$(common_dir "$RUN_TOP")" != "$PROJECT_COMMON" ]; then
  block "the deploy process runs in '$RUN_TOP', which is not a worktree of this project ('$PROJECT_TOP')."
fi

SHA=$(git -C "$TREE" rev-parse --short HEAD 2>/dev/null)
FULL=$(git -C "$TREE" rev-parse HEAD 2>/dev/null)
[ -z "$SHA" ] && block "'$TREE' has no commit at HEAD - cannot establish what is being deployed."

# 4. clean tree - the tree being deployed and the tree the deploy runs in,
# not the session's checkout. A status that FAILS is could-not-tell, never
# clean; untracked files are listed whatever status.showUntrackedFiles says;
# an index entry flagged skip-worktree or assume-unchanged hides edits from
# status, so it is refused too (Codex r1).
clean_or_block() {
  local st flags
  st=$(git -C "$1" status --porcelain --untracked-files=all --ignore-submodules=none 2>/dev/null) \
    || block "could not read git status in '$1', so the gate cannot tell whether it is clean. This is not a pass."
  if [ -n "$st" ]; then
    block "the tree this deploy runs from ('$1') is dirty. You would be deploying \"$SHA\" plus changes that are in no commit and no review. Commit or stash there first."
  fi
  flags=$(git -C "$1" ls-files -v 2>/dev/null) \
    || block "could not read the index of '$1', so the gate cannot tell whether it is clean. This is not a pass."
  if printf '%s\n' "$flags" | grep -q '^[a-zS]'; then
    block "'$1' has index entries flagged skip-worktree or assume-unchanged, which hide changes from git status. Clear them (git update-index --no-skip-worktree / --no-assume-unchanged) before deploying."
  fi
}
clean_or_block "$TREE"
[ "$RUN_TOP" != "$TREE" ] && clean_or_block "$RUN_TOP"

# A literal sha in the command must be the tree's HEAD, or the PASS rows below
# are checked for one sha while another ships. A hex token that names no
# commit here (a build id, a digest) is not a sha and is left alone.
for H in ${HEXES[@]+"${HEXES[@]}"}; do
  RESOLVED=$(git -C "$TREE" rev-parse -q --verify "$H^{commit}" 2>/dev/null) || continue
  if [ -n "$RESOLVED" ] && [ "$RESOLVED" != "$FULL" ]; then
    block "the command names commit '$H', but the tree it runs from ('$TREE') is at \"$SHA\". The gate checks the sha being deployed; run it from a tree at '$H', or drop the literal."
  fi
done

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
            # A date-SHAPED string is not a date. The regex accepts \d{4}-\d{2}
            # -\d{2}, so `2026-99-99` reaches fromisoformat and raises - which
            # used to take the whole check down and, because the caller read an
            # empty VERDICT as "nothing wrong", ALLOWED the deploy. Name it as
            # its own unmet precondition instead: the reader needs to know the
            # date is junk, not that a python traceback happened.
            try:
                verified = datetime.date.fromisoformat(m.group(1))
            except ValueError:
                out.append(f"'{rb}' has 'last verified: {m.group(1)}', which is date-shaped but not a real date. An unparseable verification date is not a verification.")
            else:
                age = (datetime.date.today() - verified).days
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
VERDICT_STATUS=$?

# Fail CLOSED when the CHECK ITSELF fails. `VERDICT` comes from a command
# substitution, so a python that raises writes its traceback to stderr and
# nothing to stdout - leaving VERDICT empty, which every test below reads as
# "no unmet preconditions". A malformed `last verified: 2026-99-99` raised in
# `datetime.date.fromisoformat` and the deploy was ALLOWED, silently, with the
# in-flight marker written and not one word on stderr: byte-identical to a
# valid, current rollback. An error is not permission. This is the repo's named
# bug class - an unknown collapsing into the safe-looking value - sitting in the
# gate whose entire job is to refuse.
if [ "$VERDICT_STATUS" -ne 0 ]; then
  echo "PROMOTION BLOCKED ($ENVNAME, sha $SHA, tree $TREE):" >&2
  echo "  - the pre-deploy check could not be evaluated (exit $VERDICT_STATUS)." >&2
  echo "    This is not a pass. Something in .crew/verify.json or a rollback" >&2
  echo "    runbook could not be read - a malformed 'last verified' date does" >&2
  echo "    exactly this. Fix the input and re-run; the traceback is above." >&2
  exit 2
fi

if [ -n "$VERDICT" ] && crew_incident_active; then
  # Every unmet precondition, one row each, so the closing report names them.
  # printf '%s\n', not '%s': VERDICT has no trailing newline (it comes from a
  # command substitution, which strips it), and `read` does not run the loop
  # body for a final line with no terminator - so the single-reason case, the
  # commonest one, logged nothing at all.
  printf '%s\n' "$VERDICT" | tr '\036' '\n' | while IFS= read -r reason; do
    [ -z "$reason" ] && continue
    crew_incident_log promote "$ENVNAME at $SHA: $reason"
  done
  VERDICT=""
fi

if [ -n "$VERDICT" ]; then
  echo "PROMOTION BLOCKED ($ENVNAME, sha $SHA, tree $TREE):" >&2
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
