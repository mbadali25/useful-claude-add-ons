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
set -uo pipefail

# L-0703: one deadline for the whole gate, 16s, under the 20s hook timeout
# (hooks.json) with room for the helper's 2s reap, as a Unix time. A hook that runs out of time is not a block,
# so the review search below is given this deadline, never a fixed slice of
# its own: python's start-up and every check before it count against it.
# Taken FIRST, before the payload read and every git probe (L-0703 review r1),
# and backdated by SECONDS, the time this shell has already run.
GATE_DEADLINE=$(( $(date +%s) - SECONDS + 16 ))

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
# L-0703 review r2: a map that exists but is neither a regular file nor a
# directory (a FIFO, a socket, a device) would hold `git hash-object` below,
# and every later read, past the hook timeout - which is not a block. Refuse it
# here, before anything opens it. (A directory is read below and refused as
# unreadable, as before.)
if [ -e .crew/verify.json ] && [ ! -f .crew/verify.json ] && [ ! -d .crew/verify.json ]; then
  echo "PROMOTION BLOCKED: .crew/verify.json is not a regular file (a FIFO, socket or device), so crew cannot read the deployment map without hanging. This is not a pass. Replace it with the map file." >&2
  exit 2
fi
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
# to stdout is environment names, one per line: 3 unreadable, 4 malformed, 0
# for the names (several when several match, L-1503) or for nothing matching. Every reason goes to STDERR, unredirected, which is both
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
ENVNAMES=$(CREW_HEAD_MAP="$HEAD_MAP" CREW_MAP_DIRTY="$MAP_DIRTY" "$PY" - "$CMD" <<'PY'
import json, os, shutil, subprocess, sys, unicodedata

# THE RULE (L-1503), shared word for word with promote-gate.ps1 so both
# flavours choose the same environment for the same command:
#   - normalise the command: drop every CR, then trailing newlines; a command
#     that is then empty or whitespace deploys nothing;
#   - a declared command matches when the command CONTAINS it (L-0689: a
#     fragment of a declared command - `git rev-parse HEAD`, `development` -
#     is no deploy), literally, ignoring case (`*`, `?`, `[` are text, never
#     wildcards);
#   - every key the gate reads (`environments`, `deploy`, and below
#     `requires`, `rollback`, `rollbackReason`, `requireHuman`) is read
#     ignoring case, as PowerShell property access does, and a map holding two
#     keys that differ only by case is refused - ConvertFrom-Json refuses it,
#     and which one is policy cannot be told. Read case-sensitively here,
#     `"RequireHuman": true` demanded a human on PowerShell and nobody on bash.
#     An EXACT duplicate key is refused the same way: both parsers keep the
#     last, so `"requireHuman": true, "requireHuman": false` read as gated
#     and applied as not gated;
#   - an environment name that is empty, holds a control character or holds
#     `,` (the union's join character) refuses the map (bad_name);
#   - in the working map, `"deploy": null` and a `requireHuman` that is a list
#     or an object are malformed and refuse the map; `"deploy": []` and
#     `[""]` declare nothing;
#   - when more than one environment matches, ALL of them apply: every name is
#     printed, and below every one's `requires`, `rollback` and `requireHuman`
#     is checked - the union of their requirements. First-match made qa
#     `target=Prod` and production `target=prod` resolve differently per
#     flavour (#489 FIX1) and gated prod's command as staging; blocking it as
#     ambiguous locked `git push` out of a map with `git push staging main`
#     and `git push prod main` for good (#489 F1).
# Case is ignored because on Windows `./Deploy.ps1` and `./deploy.ps1` are
# one file: a case-sensitive gate fails open there.


def fold(text):
    """Per-character simple upper case from Python's Unicode database: a
    character whose upper case is longer than one character (`\u00df` -> `SS`)
    is kept. This is NOT exactly .NET's OrdinalIgnoreCase, which the .ps1
    uses: they agree on ASCII and almost all of the BMP, and differ on 29 BMP
    characters (#489 N1) - Python folds dotless i (U+0131) and long s
    (U+017F) onto I and S, .NET does not; .NET folds the Greek letters with
    iota subscript onto their title-case pairs, Python keeps them. A deploy
    command differing from the one run only in those characters is matched by
    one flavour and not the other."""
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def blank(text):
    """.NET's String.IsNullOrWhiteSpace: Python's isspace() less U+001C-1F,
    which .NET does not count as white space."""
    return all(c.isspace() and c not in "\x1c\x1d\x1e\x1f" for c in text)


cmd = sys.argv[1].replace("\r", "").rstrip("\n")
if blank(cmd):
    sys.exit(0)
fcmd = fold(cmd)


def unreadable(why, status):
    print(why, file=sys.stderr)
    sys.exit(status)


class CaseTwins(ValueError):
    """Two keys in one JSON object that differ only by case."""


def no_case_twins(pairs):
    seen = {}
    for key, _ in pairs:
        if fold(key) in seen:
            first = seen[fold(key)]
            if first == key:
                raise CaseTwins(f"it contains the duplicate key `{key}`, so which "
                                "value is policy cannot be told")
            raise CaseTwins(f"it contains keys with different casing (`{first}` "
                            f"and `{key}`), so which one is policy cannot be told")
        seen[fold(key)] = key
    return dict(pairs)


def get_ci(obj, name, default):
    """`obj[name]`, the key matched ignoring case (case twins never get this
    far: no_case_twins refused the map)."""
    keys = [k for k in obj if fold(k) == fold(name)]
    return obj[keys[0]] if keys else default


def deploy_of(cfg):
    return get_ci(cfg, "deploy", [])


def bad_name(name):
    """A name the gate cannot carry (#489 F1): empty, holding a control
    character (Unicode Cc, what .NET's Char.IsControl tests), or holding `,`,
    the union's join character. Matched names travel one per line to the
    shell, so `"a\nb"` became the lax environments `a` and `b`.
    promote-gate.ps1's Assert-EnvironmentName applies the same test."""
    return (not name or "," in name
            or any(unicodedata.category(c) == "Cc" for c in name))


def matching(envs, strict):
    """Every environment whose declared deploy matches `cmd`. `strict` is the
    working map's reading, which refuses a malformed entry; the COMMITTED map
    below is read leniently, as it always was - except for a bad name, which
    refuses either map (3 committed, 4 working)."""
    for name in envs:
        if bad_name(name):
            shown = "".join("?" if unicodedata.category(c) == "Cc" else c for c in name)
            unreadable(f"{'.crew/verify.json' if strict else 'the committed .crew/verify.json'} "
                       f"has the environment name `{shown}`, which is empty, holds a "
                       "control character or holds a comma - a name the gate cannot "
                       "report or record", 4 if strict else 3)
    hits = []
    for name, cfg in envs.items():
        if not isinstance(cfg, dict):
            if strict:
                unreadable(f"environment `{name}` in .crew/verify.json is a "
                           f"{type(cfg).__name__}, not an object", 4)
            continue
        if strict and isinstance(get_ci(cfg, "requireHuman", None), (list, dict)):
            unreadable(f"environment `{name}` in .crew/verify.json has a "
                       "`requireHuman` that is a list or an object, not true or "
                       "false", 4)
        # L-0648: the gate reads a `github` entry's sha rule, so a `github`
        # that is not an object or a non-empty list of objects is malformed.
        has_github = any(fold(k) == fold("github") for k in cfg)
        github = get_ci(cfg, "github", None)
        if strict and has_github and not isinstance(github, dict) and not (
                isinstance(github, list) and github
                and all(isinstance(e, dict) for e in github)):
            unreadable(f"environment `{name}` in .crew/verify.json has a `github` "
                       "that is not an object or a non-empty list of objects", 4)
        declared = deploy_of(cfg)
        if isinstance(declared, str):
            # ONE command, not a list of them: iterating a bare string walked
            # its CHARACTERS, so `deploy: "deploy-prod"` matched any command
            # holding a `d`.
            declared = [declared]
        if not isinstance(declared, list) or not all(
                isinstance(d, str) for d in declared):
            if strict:
                unreadable(f"environment `{name}` in .crew/verify.json has a "
                           "`deploy` that is not a command or a list of "
                           "commands", 4)
            continue
        # The command contains the declared text: run verbatim, with extra
        # flags, or wrapped (`cd <dir> && <declared>`). Not the reverse (L-0689):
        # a fragment of a declared command matched it, so `git rev-parse HEAD`
        # wrote an in-flight marker for a deploy that never ran.
        if any(isinstance(d, str) and d and fold(d) in fcmd
               for d in declared):
            hits.append(name)
    return hits


def pick(hits):
    """Every matching environment applies (the union rule above)."""
    if hits:
        print("\n".join(hits))
        sys.exit(0)


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
        committed = json.loads(proc.stdout.decode("utf-8-sig", errors="replace"),
                               object_pairs_hook=no_case_twins)
    except ValueError as exc:
        unreadable(f"the committed .crew/verify.json does not parse as JSON: {exc}", 3)
    committed_envs = get_ci(committed, "environments", {}) if isinstance(committed, dict) else None
    if not isinstance(committed_envs, dict):
        unreadable("the committed .crew/verify.json holds no object of environments", 3)
    pick(matching(committed_envs, strict=False))
    if not os.path.exists(".crew/verify.json"):
        sys.exit(0)


try:
    with open(".crew/verify.json", encoding="utf-8-sig", errors="replace") as fh:
        raw = fh.read()
except OSError as exc:
    unreadable(f".crew/verify.json exists and could not be read: {exc}", 3)
try:
    doc = json.loads(raw, object_pairs_hook=no_case_twins)
except ValueError as exc:
    unreadable(f".crew/verify.json does not parse as JSON: {exc}", 4)
if not isinstance(doc, dict):
    unreadable(f".crew/verify.json holds a JSON {type(doc).__name__}, "
               "not an object", 4)
envs = get_ci(doc, "environments", {})
if not isinstance(envs, dict):
    unreadable(f"`environments` in .crew/verify.json is a "
               f"{type(envs).__name__}, not an object, so no environment can "
               "be read out of it", 4)
pick(matching(envs, strict=True))
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
# Python's stdout is text mode: on Windows every newline it writes reaches
# here as CRLF, and Git Bash's command substitution drops only the final one,
# so `qa\r\nprod` split on LF named an environment `qa\r` that no map holds
# (the Windows pre-flight of L-1503). bad_name refuses a name holding any
# control character, so removing every CR cannot join or invent a name.
ENVNAMES=$(crew_strip_cr "$ENVNAMES")

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

# T-0062: read the command as a workflow dispatch too. `_promote_dispatch.py`
# reads it, and every declared deploy, with T-0009's reader
# (`crew_dispatch.dispatch_read`, the one cloud_guard.py uses), so
# `gh workflow run <wf> -f environment=x` and its `gh api -X POST` REST twin
# with `-f 'inputs[environment]=x'` reach the same environment. It prints
# `env<TAB>name` per environment, `block<TAB>why` when it cannot tell (or a
# declared workflow fits no single environment), and nothing when the command
# is no dispatch of a declared deploy workflow - always nothing in a repo that
# declares no dispatch deploy. It runs whether or not containment matched
# (group review r2): `./deploy-dev.sh && gh api ... inputs[environment]=production`
# matched development only, and production's preconditions went unchecked.
# Its environments are added to containment's. A helper that FAILS is never
# "nothing": that is the unknown-as-safe bug class.
ENVNAME=${ENVNAMES:-workflow dispatch}
ENVNAME=${ENVNAME//$'\n'/,}
DISPATCH=$(CREW_HEAD_MAP="$HEAD_MAP" CREW_MAP_DIRTY="$MAP_DIRTY" PYTHONIOENCODING=utf-8 \
  "$PY" "$(dirname "${BASH_SOURCE[0]}")/_promote_dispatch.py" "$CMD") \
  || block "the command could not be read as a workflow dispatch (_promote_dispatch.py failed). This is not a pass."
DISPATCH=$(crew_strip_cr "$DISPATCH")
while IFS=$'\t' read -r kind tok; do
  case "$kind" in
    block) block "$tok" ;;
    env)
      case $'\n'"$ENVNAMES"$'\n' in
        *$'\n'"$tok"$'\n'*) ;;
        *) ENVNAMES="${ENVNAMES:+$ENVNAMES
}$tok" ;;
      esac ;;
  esac
done <<DISPATCHED
$DISPATCH
DISPATCHED
[ -z "$ENVNAMES" ] && exit 0
# Several matching environments are named together, `staging,prod`, in every
# message, skip row and the in-flight marker; their requirements are checked
# one by one below. (`,`, not `+`: verify-gate.sh greps the marker's name as
# an ERE, where `+` is a quantifier.)
ENVLIST=()
while IFS= read -r line; do ENVLIST+=("$line"); done <<ENVS
$ENVNAMES
ENVS
ENVNAME=$(IFS=,; printf '%s' "${ENVLIST[*]}")

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
# Windows Python ends every record with CRLF and `$(...)` drops only the last
# line's: a `cd` record followed by another kept its CR, so `cd "<dir>\r"`
# resolved nowhere. _promote_tree.py turns a CR inside a token into `bad`, so
# removing every CR here cannot join or invent a path.
RECORDS=$(crew_strip_cr "$RECORDS")
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

# L-0768: WHICH MAP IS POLICY. The map committed in the sha being deployed
# (read by the VERDICT step below, and by _promote_review.py's
# policy_map_text for requireReview): exactly what a deploy from a checkout of that sha reads, so
# a waiver committed on the deployed branch is seen and the main checkout's
# map no longer decides a worktree deploy. The project dir's map is policy
# only when the sha carries no map at all. So the uncommitted-map guard judges
# the map that is policy: the project dir's when the deploy runs from the
# project dir (its own working copy) or when it is the fallback. A linked
# worktree's own dirt, its map included, is refused by the clean-tree check
# below. A dirty map in an unrelated project dir is matched (above, working
# and committed) but never read as policy, so it no longer blocks.
# A listing that FAILS is could-not-tell, never "the sha has no map".
TREE_MAP=$(git -C "$TREE" ls-tree --full-tree "$FULL" -- .crew/verify.json 2>/dev/null) \
  || block "could not list .crew/verify.json in the deployed sha $FULL of '$TREE', so the gate cannot tell which deployment map is policy. This is not a pass."
if [ -n "$MAP_DIRTY" ] && [ "$TREE" = "$PROJECT_TOP" ]; then
  block ".crew/verify.json in the project dir ($(pwd -P)) has uncommitted changes: it $MAP_DIRTY. The deploy map is policy; commit the change (it is then reviewed like any other) or revert it."
fi
POLICY_BLOB=""
if [ -n "$TREE_MAP" ]; then
  read -r _ TM_TYPE TM_OID TM_REST <<TREEMAP
$TREE_MAP
TREEMAP
  case "$TM_OID" in
    *[!0-9a-f]*|"") TM_TYPE=bad ;;
  esac
  [ "$TM_TYPE" = blob ] && [ "${#TM_OID}" -eq 40 ] && [ -n "$TM_REST" ] \
    || block ".crew/verify.json in the deployed sha $FULL is not a file, so it cannot be read as the deployment map. This is not a pass."
  POLICY_BLOB=$TM_OID
fi
if [ -n "$MAP_DIRTY" ] && [ -z "$TREE_MAP" ]; then
  block "the deployed sha $FULL carries no committed .crew/verify.json, so the project dir's map is policy, and .crew/verify.json in the project dir ($(pwd -P)) has uncommitted changes: it $MAP_DIRTY. Commit the change (it is then reviewed like any other) or revert it."
fi

# L-0648: a matched environment's `github` entry with a `shaInput` - the
# command must give that input exactly once, as 40 lowercase hex, equal to
# the full HEAD of the tree judged here. `_promote_github.py` decides it for
# both flavours (promote-gate.ps1 runs it too); a helper that fails blocks.
GH_RULE=$(printf '%s' "$CMD" | PYTHONIOENCODING=utf-8 \
  "$PY" "$(dirname "${BASH_SOURCE[0]}")/_promote_github.py" --shell bash --full "$FULL" \
  --envs "$ENVNAME" --tree "$TREE" --deadline "$GATE_DEADLINE" -) \
  || block "the github entry's sha rule could not be checked (_promote_github.py failed). This is not a pass."
GH_RULE=$(crew_strip_cr "$GH_RULE")
while IFS=$'\t' read -r kind tok; do
  [ "$kind" = block ] && block "$tok"
done <<GHRULE
$GH_RULE
GHRULE

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
VERDICT=$("$PY" - "$TREE" "$POLICY_BLOB" "$GATE_DEADLINE" "$SHA" "$FULL" "${ENVLIST[@]}" \
  <<'PY' 2>/dev/null
import json, sys, os, re, datetime, shutil, subprocess, time
tree, blob, deadline = sys.argv[1], sys.argv[2], float(sys.argv[3])
sha, full, envs = sys.argv[4], sys.argv[5].lower(), sys.argv[6:]


# Keys read ignoring case, case twins refused: the matcher's rule above (and
# PowerShell's), repeated because this is a separate interpreter. A refusal
# raises, which exits non-zero and blocks below as "could not be evaluated".
def fold(text):
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def no_case_twins(pairs):
    seen = set()
    for key, _ in pairs:
        if fold(key) in seen:
            raise ValueError(f"duplicate or case-differing key `{key}`")
        seen.add(fold(key))
    return {fold(k): v for k, v in pairs}


# L-0768: the map committed in the deployed sha - its blob, listed by the
# shell above - or, when the sha carries none, the project dir's map, which
# the guard above has held to the project dir's HEAD. _promote_review.py's
# policy_map_text reads the same map for requireReview. Could-not-tell prints
# its reason and exits 5; the shell blocks on any non-zero status and shows
# what was printed.
source = "sha" if blob else "project"
try:
    if blob:
        shown = subprocess.run([shutil.which("git") or "git", "-C", tree, "cat-file", "blob", blob],
                               capture_output=True, check=False,
                               timeout=max(deadline - time.time(), 0.5),
                               stdin=subprocess.DEVNULL)
        if shown.returncode != 0:
            raise OSError(f"git cat-file exited {shown.returncode}")
        text = shown.stdout.decode("utf-8-sig", errors="replace")
    else:
        with open(".crew/verify.json", encoding="utf-8-sig") as fh:
            text = fh.read()
except (OSError, subprocess.SubprocessError) as exc:
    print(f"the deployment map that is policy for this sha could not be read: {exc}")
    sys.exit(5)
try:
    doc = json.loads(text, object_pairs_hook=no_case_twins)
except ValueError as exc:
    where = "the deployed sha's committed .crew/verify.json" if source == "sha" \
        else ".crew/verify.json"
    print(f"{where} does not parse as a deployment map: {exc}")
    sys.exit(5)
out = []

rows = ""
if os.path.exists(".work/PROMOTIONS.md"):
    rows = open(".work/PROMOTIONS.md", encoding="utf-8", errors="replace").read()

# L-0703: a row is THIS commit's only when its sha cell is the full 40-hex
# sha (case ignored). `startswith(sha[:7])` admitted a PASS row for any other
# commit sharing the first 7 characters. A strict prefix of the full sha is a
# short row: never counted (no back-compat - resolving it re-opens the hole
# whenever the row's own commit is gone from the object store), but named, so
# the block says what to fix.
def row_sha(cell, full):
    cell = cell.strip().lower()
    if cell == full:
        return "full"
    if 0 < len(cell) < len(full) and full.startswith(cell):
        return "short"
    return None


shorts = {}


def passed(name, full):
    """The NEWEST row for `name` and THIS sha decides (L-0665): rows are appended,
    so file order is time order, and a later pass clears an earlier failure
    while a later failure revokes an earlier pass. Only a full-sha row is this
    sha's (L-0703); a short one is noted in `shorts` and never decides. True /
    False for that row all-pass or not; None when there is no full-sha row."""
    newest = None
    for line in rows.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        # when | env | sha | smoke | regression | verify | by
        kind = row_sha(cells[2], full) if cells[1] == name else None
        if kind == "short":
            shorts.setdefault(name, []).append(cells[2])
        if kind == "full":
            newest = all(c.lower() == "pass" for c in cells[3:6])
    return newest

# The union rule: every matched environment's requirements, each in its own
# terms (its upstreams, its runbook, its approval marker). With several, each
# reason names the environment it comes from.
for env in envs:
    declared = doc.get("ENVIRONMENTS", {})
    if source == "sha" and fold(env) not in declared:
        # Matched by the project dir's map, absent from the map that is
        # policy: its requirements cannot be told, so they are not "none".
        out.append(f"'{env}' is a deploy by the project dir's .crew/verify.json, but the map "
                   f"committed in the deployed sha {full} does not declare it, so its "
                   "requirements cannot be told. Deploy a sha whose committed map declares "
                   f"'{env}'.")
        if len(envs) > 1:
            out[-1] = f"[{env}] {out[-1]}"
        continue
    cfg = declared.get(fold(env), {})
    before = len(out)
    for upstream in cfg.get("REQUIRES", []):
        verdict = passed(upstream, full)
        if verdict is None:
            short = "".join(f" (.work/PROMOTIONS.md records the short sha {s} for '{upstream}': "
                            "a row counts only with the full 40-character sha - re-run the "
                            "promotion, or rewrite the row with the full sha after checking it)"
                            for s in shorts.get(upstream, [])[:1])
            out.append(f"'{upstream}' has no all-pass row for sha {full} in .work/PROMOTIONS.md"
                       f"{short}. Run /crew:promote {upstream} first, and let it record the "
                       "result.")
        elif not verdict:
            out.append(f"'{upstream}' has rows for sha {full} in .work/PROMOTIONS.md, but the "
                       "newest row is not all-pass: a later failure revokes an earlier pass. "
                       f"Run /crew:promote {upstream} again, and let it record the result.")

    # Fail CLOSED: an absent "rollback" key used to mean "no rollback needed".
    # It now means "nobody said". The only way to deploy with no rollback plan is
    # an explicit rollback: "none" plus a rollbackReason explaining why.
    if "ROLLBACK" not in cfg:
        out.append(f"'{env}' has no 'rollback' key in .crew/verify.json. Add rollback: "
                   f"\"<path to a runbook>\", or rollback: \"none\" plus a rollbackReason "
                   f"string explaining why {env} does not need one. Fix: edit the "
                   f"'{env}' block in .crew/verify.json.")
    else:
        rb = cfg.get("ROLLBACK")
        if rb == "none":
            reason = str(cfg.get("ROLLBACKREASON") or "").strip()
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

    if cfg.get("REQUIREHUMAN"):
        marker = f".crew/.approved-{env}-{sha}"
        if not os.path.exists(marker):
            out.append(f"this environment requires explicit human approval. Show the sha, the diff summary and the "
                       f"last promotion, get a yes, then: touch {marker}")
    if len(envs) > 1:
        out[before:] = [f"[{env}] {r}" for r in out[before:]]

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
  [ -n "$VERDICT" ] && printf '    %s\n' "$VERDICT" >&2
  echo "    This is not a pass. Something in .crew/verify.json or a rollback" >&2
  echo "    runbook could not be read - a malformed 'last verified' date does" >&2
  echo "    exactly this. Fix the input and re-run; the traceback is above." >&2
  exit 2
fi

# 5. Review evidence (L-0703): an accepted review receipt whose reviewed head
# has THIS commit's tree, confirmed by review_ledger.check_receipt run in the
# deploying tree - for every matched environment unless it sets
# `requireReview: false` with a `reviewReason`. `requireHuman` does not waive
# it. _promote_review.py decides for BOTH flavours; it gets GATE_DEADLINE and
# kills its search when that passes. Its reasons join VERDICT, so the emergency lane and the
# message below treat them like every other unmet precondition; a non-zero
# exit is could-not-tell and blocks like the check above.
REVIEW=$("$PY" "$(dirname "${BASH_SOURCE[0]}")/_promote_review.py" "$TREE" "$FULL" \
  "$GATE_DEADLINE" "${ENVLIST[@]}")
REVIEW_STATUS=$?
if [ "$REVIEW_STATUS" -ne 0 ] && crew_incident_active; then
  # An open incident records a review check that could not run as a skip, like
  # every other unmet precondition: exiting 2 here, before the emergency lane
  # below, blocked the very deploys an incident exists to let through (L-0703
  # Codex r1). The twin is Deny-ReviewUnknown in promote-gate.ps1.
  REVIEW="the review-evidence check could not be evaluated (exit $REVIEW_STATUS): _promote_review.py failed or is missing. This is not a pass."
elif [ "$REVIEW_STATUS" -ne 0 ]; then
  echo "PROMOTION BLOCKED ($ENVNAME, sha $SHA, tree $TREE):" >&2
  echo "  - the review-evidence check could not be evaluated (exit $REVIEW_STATUS)." >&2
  echo "    This is not a pass. _promote_review.py failed or is missing; its" >&2
  echo "    reason is above." >&2
  exit 2
fi
if [ -n "$REVIEW" ]; then
  VERDICT="${VERDICT:+$VERDICT$'\036'}$REVIEW"
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
