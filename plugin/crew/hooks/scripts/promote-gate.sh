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
#      .work/PROMOTIONS.md for THIS sha. Not "a pass row" - this sha, written
#      out in full: a 7-character (or any short) row never counts (L-0703).
#   2. `rollback` - required for every gated environment. Either a runbook path
#      that exists and whose `last verified` is inside 90 days, or the literal
#      "none" plus a `rollbackReason`. An absent key blocks the deploy.
#   3. `requireHuman` - refuses unless an explicit approval marker for this sha
#      was written this session.
#   4. A clean tree - you cannot deploy a sha that is not what is committed.
#   5. Review evidence (L-0703) - an accepted review receipt whose reviewed
#      head has this commit's tree, unless the environment sets
#      `requireReview: false` plus a `reviewReason`. See _promote_review.py
#      for what that proves and what it does not.
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
# POLICY is the map committed in the sha being deployed (L-0768): requires,
# rollback, requireHuman and requireReview come from `git -C <tree> ls-tree
# <sha> -- .crew/verify.json`'s blob, which is what a checkout of that sha
# reads, so a worktree can do nothing a checkout of the same sha could not.
# Only a sha carrying no map falls back to the project dir's map. WHICH
# command deploys, and to which environment, is still matched against the
# project dir's map (working and committed): that runs before the tree is
# known, and matching more only blocks more.
#
# State stays in the project dir, deliberately: .work/PROMOTIONS.md,
# .crew/.approved-<env>-<sha>, the rollback runbook file, the incident files
# and .crew/.deploy-in-flight. `.work/` and `.crew/*` are
# per-checkout, gitignored state: a fresh worktree has none of it (reading it
# there would refuse every worktree deploy for a missing PASS row) and a
# throwaway worktree can hold a forged copy (reading it there would launder a
# sha). verify-gate.sh reads the in-flight marker and PROMOTIONS.md from the
# project dir too, so the Stop-time check keeps matching.
#
# What it cannot enforce, and does not pretend to: that smoke, regression and
# verify actually ran AFTER the deploy. verify-gate.sh picks that up at Stop by
# refusing to end a turn that deployed and recorded nothing.
#
# HOW IT RUNS (crew 1.3.41). The whole decision above is _promote_gate.py, ONE
# python process: the containment match (_promote_match.py), the dispatch, tree
# and github readers, the verdict (_promote_verdict.py) and the review search
# (_promote_review.py) are modules it calls in-process. This script keeps only
# what needs a shell: the PowerShell hand-off, the no-map opt-out, the python
# lookup, and the jq fallback for a host with no python at all. On Git Bash every
# process start is an MSYS fork (0.3-0.5 s on a quiet host, seconds under load);
# a deploy-shaped command used to cost about forty-five of them against a 20 s
# hook timeout, which timed out, and a timeout is not a block. The deadline the
# python gate keeps is `promote.deadlineSeconds` (config), else the row's hook
# timeout less four seconds; the 16 s below is the jq fallback's alone.
set -uo pipefail

# L-0703: one deadline for the whole gate, 16s, under the 20s hook timeout
# (hooks.json) with room for the helper's 2s reap, as a Unix time. A hook that runs out of time is not a block,
# so the review search below is given this deadline, never a fixed slice of
# its own: python's start-up and every check before it count against it.
# Taken FIRST, before the payload read and every git probe (L-0703 review r1),
# and backdated by SECONDS, the time this shell has already run. The clock is
# printf's builtin `%(%s)T` (bash 4.2+), not `$(date +%s)`: on Git Bash every
# fork is an MSYS process start. An older bash, which has no `%(...)T`, or a
# strftime without `%s`, gives no number and still asks date(1).
printf -v GATE_NOW '%(%s)T' -1 2>/dev/null || GATE_NOW=""
case "$GATE_NOW" in '' | *[!0-9]*) GATE_NOW=$(date +%s) ;; esac
GATE_DEADLINE=$(( GATE_NOW - SECONDS + 16 ))
# When this shell began, as a Unix time: the python gate measures its own deadline from it.
GATE_START=$(( GATE_NOW - SECONDS ))

# The script's directory without a subshell when the path is absolute, as the
# dispatcher starts every guard; a relative one falls back to dirname.
case "${BASH_SOURCE[0]}" in
  /*|[A-Za-z]:/*) DIR=${BASH_SOURCE[0]%/*} ;;
  *) DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" ;;
esac
. "$DIR/_common.sh"

# The payload is read with the `read` builtin: `$(cat)` was one fork, on the
# path of every Bash call. A payload with no trailing newline is what `-d ''`
# copes with (it returns non-zero at end of input, hence `|| :`).
IFS= read -r -d '' INPUT || :
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
# L-0703 review r2: a map that exists but is neither a regular file nor a
# directory (a FIFO, a socket, a device) would hold `git hash-object` below,
# and every later read, past the hook timeout - which is not a block. Refuse it
# here, before anything opens it. (A directory is read below and refused as
# unreadable, as before.)
if [ -e .crew/verify.json ] && [ ! -f .crew/verify.json ] && [ ! -d .crew/verify.json ]; then
  echo "PROMOTION BLOCKED: .crew/verify.json is not a regular file (a FIFO, socket or device), so crew cannot read the deployment map without hanging. This is not a pass. Replace it with the map file." >&2
  exit 2
fi
HEAD_MAP=""
MAP_DIRTY=""
if [ ! -e .crew/verify.json ]; then
  HEAD_MAP=$(git rev-parse -q --verify "HEAD:./.crew/verify.json" 2>/dev/null)
  [ -z "$HEAD_MAP" ] && exit 0
  MAP_DIRTY="deleted, and committed at HEAD"
fi

# No python is NOT an opt-out (L-0703). It used to `exit 0` here, so a host
# without python ran every declared deploy ungated. Without python the map
# cannot be parsed the way the gate parses it, so this asks the cheaper
# question "could this command be a deploy?" and blocks when the answer is
# not "no":
#   - with jq: every string VALUE in the working map and, when that map is
#     uncommitted, the committed one too, decoded by jq at any depth. A value
#     the command contains, or that contains the command (the matcher's own
#     two-way rule, ASCII case ignored), blocks. That is a superset of the
#     declared `deploy` commands. A map jq cannot read blocks;
#   - with neither: the command cannot even be read, and a textual key scan
#     is evadable (`"depl\u006fy"`), so every command blocks while a map
#     exists. Doubly degraded, a deploy cannot be told from anything else.
PY=$(crew_py) || PY=""

# The python gate (crew 1.3.41). It decides everything below in one process and
# exits 0 (allow) or 2 (block). Any other status - a crash, a kill, an interpreter
# that would not start - is a block too: an error is not permission.
if [ -n "$PY" ]; then
  if ! crew_py_script "$DIR/_promote_gate.py" GATE_PY; then
    echo "PROMOTION BLOCKED: _promote_gate.py is missing or its path could not be resolved, so crew cannot judge this command. This is not a pass. Reinstall crew." >&2
    exit 2
  fi
  CREW_GATE_START="$GATE_START" CREW_HEAD_MAP="$HEAD_MAP" CREW_MAP_DIRTY="$MAP_DIRTY" PYTHONIOENCODING=utf-8 "$PY" "$GATE_PY" <<<"$INPUT"
  GATE_STATUS=$?
  case "$GATE_STATUS" in
    0 | 2) exit "$GATE_STATUS" ;;
  esac
  # Two failures carry their own status (the protocol is in _promote_gate.py's
  # docstring): 10 + N, the containment match could not read the map; 20 + N, the
  # pre-deploy check could not be evaluated. The reason is already on stderr.
  ENV_STATUS=0
  VERDICT_STATUS=0
  if [ "$GATE_STATUS" -ge 10 ] && [ "$GATE_STATUS" -lt 20 ]; then
    ENV_STATUS=$(( GATE_STATUS - 10 ))
  elif [ "$GATE_STATUS" -ge 20 ] && [ "$GATE_STATUS" -lt 30 ]; then
    VERDICT_STATUS=$(( GATE_STATUS - 20 ))
  fi
  # An error is not permission: the check itself failing blocks.
  if [ "$ENV_STATUS" -ne 0 ]; then
    echo "PROMOTION BLOCKED: .crew/verify.json could not be read as a deployment map (exit $ENV_STATUS)." >&2
    echo "  The reason is printed above this line, on stderr, by the check itself" >&2
    echo "  - or, if nothing is there, the check crashed and the traceback is." >&2
    echo "  This is NOT a pass. Crew cannot tell whether this command deploys," >&2
    echo "  so it cannot tell whether a pre-deploy gate applies to it. Fix the" >&2
    echo "  JSON, or delete .crew/verify.json if this repo should not be gated." >&2
    exit 2
  fi
  if [ "$VERDICT_STATUS" -ne 0 ]; then
    echo "    This is not a pass. Something in .crew/verify.json or a rollback" >&2
    echo "    runbook could not be read - a malformed 'last verified' date does" >&2
    echo "    exactly this. Fix the input and re-run; the traceback is above." >&2
    exit 2
  fi
  echo "PROMOTION BLOCKED: the promote gate (_promote_gate.py) failed to run (exit $GATE_STATUS), so crew cannot tell whether this command deploys. This is not a pass. Its reason is above." >&2
  exit 2
fi

if [ -e .crew/verify.json ]; then
  HEAD_MAP=$(git rev-parse -q --verify "HEAD:./.crew/verify.json" 2>/dev/null)
  if [ -n "$HEAD_MAP" ]; then
    WORK_MAP=$(git hash-object -- .crew/verify.json 2>/dev/null)
    if [ -z "$WORK_MAP" ]; then
      MAP_DIRTY="could not be hashed to compare with HEAD"
    elif [ "$WORK_MAP" != "$HEAD_MAP" ]; then
      MAP_DIRTY="differs from HEAD"
    fi
  elif [ -n "$(git ls-files --others --exclude-standard -- .crew/verify.json 2>/dev/null)" ]; then
    MAP_DIRTY="untracked - in no commit"
  fi
fi

if [ -z "$PY" ]; then
  if ! command -v jq >/dev/null 2>&1; then
    echo "PROMOTION BLOCKED: no usable python and no jq, and this repository has a deployment map (.crew/verify.json). Crew cannot read the command or the map, so it cannot tell whether this command deploys. This is not a pass. Install python 3.8+ (every crew hook needs it)." >&2
    exit 2
  fi
  # Every jq call is bounded by what is left of GATE_DEADLINE (a stalled jq
  # would otherwise outlive the hook timeout, which is not a block); a jq that
  # runs out of it, or no `timeout` to bound it with, blocks: every caller
  # treats a non-zero status as could-not-tell (it runs inside $(...), where an
  # `exit` would leave only the subshell).
  np_jq() {
    local left=$(( GATE_DEADLINE - $(date +%s) ))
    if [ "$left" -lt 1 ] || ! command -v timeout >/dev/null 2>&1; then
      echo "PROMOTION BLOCKED: no usable python, and the jq fallback cannot be bounded inside the hook's deadline (no time left, or no timeout command). This is not a pass. Install python 3.8+." >&2
      return 2
    fi
    timeout "$left" jq "$@"
  }
  NP_RAW=$(printf '%s' "$INPUT" | np_jq -r '.tool_input.command // empty') || {
    echo "PROMOTION BLOCKED: no usable python, and jq could not read the tool payload, so crew cannot tell whether this command deploys. This is not a pass. Install python 3.8+." >&2
    exit 2
  }
  NP_CMD=$(crew_strip_cr "$NP_RAW")
  [ -z "${NP_CMD//[[:space:]]/}" ] && exit 0
  NP_HIT=""
  # A key repeated in one object: jq keeps only the LAST value, so the first
  # is never scanned, and python refuses such a map. Comparing leaf paths
  # missed `"prod": {"deploy": ...}, "prod": {"rollback": ...}`, whose leaves
  # differ (L-0703 Codex r2). So: a path is FINISHED once a leaf at it is seen
  # or the container at it closes (a closing event `[p]` closes p[:-1]), and
  # any later event at or under a finished path is a repeated key.
  NP_DUP='
    reduce inputs as $e ({fin: {}, dup: false};
      if .dup then . else
        ($e[0]) as $p
        | if ($e | length) == 2 then
            .fin as $f
            | if any(range(1; ($p | length) + 1); $f[$p[:.] | tojson] != null) then .dup = true
              else .fin[$p | tojson] = true end
          else .fin[$p[:-1] | tojson] = true end
      end) | .dup'
  # A value and the command are compared under a fold COARSER than python's
  # (L-0703 Codex r2): python upper-cases per character over Unicode, so
  # `DÉPLOY` matches `déploy`, which ascii_downcase never saw. ASCII letters
  # fold to lower case; the only non-ASCII characters python folds onto ASCII,
  # U+0131 (dotless i) and U+017F (long s), fold onto i and s; every other
  # non-ASCII character folds onto one placeholder. Two strings python calls
  # equal are equal here too, so this matches everything python matches (and
  # more, which only blocks). `python3 -c` over sys.maxunicode re-measures the
  # set: characters whose single-character upper() is ASCII.
  NP_FOLD='def coarse: explode | map(if . >= 65 and . <= 90 then . + 32 elif . < 128 then . elif . == 305 then 105 elif . == 383 then 115 else 65533 end) | implode;'
  # ONE jq process per map, never one per string: a fork per value cost 20.8s
  # on this repo's own 847-string map, past the hook timeout (L-0703 security
  # review). An empty text, a map jq cannot parse, and a key repeated in one
  # object (jq keeps only the last value, so the first would never be
  # scanned; python refuses such a map) all block as unreadable.
  # Then the map's SHAPE, held to python's reading below (L-0703 Codex r1):
  # a map python refuses is could-not-tell here too, never "no string
  # matched". `"deploy": true` holds no string at all, so the scan alone
  # passed every command while python refused the map. $3 is "strict" for the
  # working map (python's strict=True: an environment that is not an object, a
  # `deploy` that is not a string or a list of strings, a list or object
  # `requireHuman`, a `github` that is not an object or a non-empty list of
  # objects - main's L-0648 rule, added when rush 1.2.1 merged L-0703) and
  # "lenient" for the committed one, which python reads leniently but still refuses when it is not an object, has no object of
  # environments, or carries a bad environment name. Keys are compared with
  # ASCII case folded; python folds Unicode, so a key holding any non-ASCII
  # character is one this fallback cannot compare and blocks.
  NP_SHAPE='
    def ci($k): [to_entries[] | select(.key | ascii_downcase == $k)];
    def has_ci($k): ci($k) | length > 0;
    def get_ci($k): ci($k) | .[0].value;
    def bad_name: . == "" or (explode | any(. == 44 or . < 32 or (. >= 127 and . <= 159)));
    def twins: any(.. | objects | keys_unsorted | map(ascii_downcase); length != (unique | length));
    def non_ascii: any(.. | objects | keys_unsorted[]; explode | any(. > 127));
    def deploy_ok: type == "string" or (type == "array" and all(.[]; type == "string"));
    def github_ok: type == "object" or (type == "array" and length > 0 and all(.[]; type == "object"));
    if type != "object" then "it holds a JSON \(type), not an object"
    elif twins then "it holds two keys in one object that differ only by case"
    elif non_ascii then "a key holds a non-ASCII character, which crew cannot compare ignoring case without python"
    else (if has_ci("environments") then get_ci("environments") else {} end) as $envs
      | if ($envs | type) != "object" then "`environments` is not an object"
        elif any($envs | keys_unsorted[]; bad_name) then "an environment name is empty, holds a control character or holds a comma"
        elif $mode != "strict" then "ok"
        else first(($envs | to_entries[] | .key as $n | .value
            | if type != "object" then "environment `\($n)` is not an object"
              elif has_ci("requirehuman") and (get_ci("requirehuman") | type == "array" or type == "object") then "environment `\($n)` has a `requireHuman` that is a list or an object"
              elif has_ci("deploy") and (get_ci("deploy") | deploy_ok | not) then "environment `\($n)` has a `deploy` that is not a command or a list of commands"
              elif has_ci("github") and (get_ci("github") | github_ok | not) then "environment `\($n)` has a `github` that is not an object or a non-empty list of objects"
              else empty end), "ok")
        end
    end'
  np_scan() {
    local text=$1 where=$2 mode=$3 dup shape
    dup=$(printf '%s' "$text" | np_jq -n --stream "$NP_DUP" 2>/dev/null)
    if [ -z "${text//[[:space:]]/}" ] || [ "$dup" != "false" ]; then
      echo "PROMOTION BLOCKED: no usable python, and $where is empty, does not parse, or repeats a key, so crew cannot tell whether this command deploys. This is not a pass. Install python 3.8+, or fix the map." >&2
      exit 2
    fi
    shape=$(printf '%s' "$text" | np_jq -r --arg mode "$mode" "$NP_SHAPE" 2>/dev/null)
    if [ "$shape" != "ok" ]; then
      echo "PROMOTION BLOCKED: no usable python, and crew cannot classify $where as a deployment map: ${shape:-jq could not read it}. This is not a pass. Install python 3.8+, or fix the map." >&2
      exit 2
    fi
    # The hit is printed as JSON (`tojson`), never raw: a value of only
    # newlines would otherwise be stripped by $(...) to nothing and read as
    # "no match" (L-0703 review r1).
    NP_HIT=$(printf '%s' "$text" | np_jq -r --arg c "$NP_CMD" \
      "$NP_FOLD"' ($c | coarse) as $c | first(.. | strings | select(length > 0) | select(coarse as $v | ($c | contains($v)) or ($v | contains($c))) | tojson) // empty' 2>/dev/null) || {
      echo "PROMOTION BLOCKED: no usable python, and jq could not scan $where, so crew cannot tell whether this command deploys. This is not a pass. Install python 3.8+." >&2
      exit 2
    }
    if [ -n "$NP_HIT" ]; then
      echo "PROMOTION BLOCKED: no usable python, and this command and the map's string $NP_HIT contain one another, so it may be a declared deploy. Without python crew cannot evaluate any pre-deploy check. This is not a pass. Install python 3.8+." >&2
      exit 2
    fi
  }
  # A map that is not a regular file (a FIFO with no writer would hold `cat`
  # past the hook timeout) is refused; the read itself is bounded too.
  if [ -e .crew/verify.json ]; then
    if [ ! -f .crew/verify.json ]; then
      echo "PROMOTION BLOCKED: no usable python, and .crew/verify.json is not a regular file, so crew cannot read the map. This is not a pass." >&2
      exit 2
    fi
    NP_LEFT=$(( GATE_DEADLINE - $(date +%s) ))
    [ "$NP_LEFT" -ge 1 ] || NP_LEFT=1
    NP_MAP=$(timeout "$NP_LEFT" cat .crew/verify.json 2>/dev/null) || {
      echo "PROMOTION BLOCKED: no usable python, and .crew/verify.json could not be read inside the hook's deadline. This is not a pass." >&2
      exit 2
    }
    np_scan "$NP_MAP" ".crew/verify.json" strict
  fi
  # Bounded like the working map's read (L-0703 Codex r3): a stalled
  # `git cat-file` would otherwise hold the hook past its timeout.
  if [ -n "$MAP_DIRTY" ] && [ -n "$HEAD_MAP" ]; then
    NP_LEFT=$(( GATE_DEADLINE - $(date +%s) ))
    [ "$NP_LEFT" -ge 1 ] || NP_LEFT=1
    NP_HEAD_MAP=$(timeout "$NP_LEFT" git cat-file blob "$HEAD_MAP" 2>/dev/null) || {
      echo "PROMOTION BLOCKED: no usable python, and the committed .crew/verify.json could not be read inside the hook's deadline, so crew cannot tell whether this command deploys. This is not a pass. Install python 3.8+." >&2
      exit 2
    }
    np_scan "$NP_HEAD_MAP" "the committed .crew/verify.json" lenient
  fi
  exit 0
fi
