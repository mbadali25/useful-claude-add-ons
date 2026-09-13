#!/usr/bin/env bash
# merge_gate.sh - export, remove and restore the branch protection that makes up
# a GitHub repository's merge gate.
#
# Usage:
#   merge_gate.sh status  <owner> <repo> [--branch NAME]
#   merge_gate.sh export  <owner> <repo> <outfile> [--branch NAME]
#   merge_gate.sh disable <owner> <repo> [--branch NAME] [--export-to FILE]
#                                        [--allow-inherited] [--dry-run]
#   merge_gate.sh enable  <owner> <repo> --from-export FILE
#
# GitHub gates a branch through TWO independent surfaces, and a repo may carry
# both at once:
#   classic   GET|PUT|DELETE repos/{o}/{r}/branches/{b}/protection
#   rulesets  GET|POST       repos/{o}/{r}/rulesets
#             GET|DELETE     repos/{o}/{r}/rulesets/{id}
# Every read here covers both. Neither surface is ever assumed empty because the
# other answered: "could not read" is its own outcome and stops the run.
#
# There is no preset. `enable` restores from an export or does nothing at all -
# a bare re-enable would silently drop whatever the export held.
#
# Transport is the `gh` CLI, which owns auth. Set GH_CMD to point at something
# else (the test suite points it at a fixture stub, so no credentials and no
# network are involved). Auth is deliberately NOT re-checked here - `gh` does it.
#
# Requires: jq, gh. Needs admin on the repository for every call below; there is
# no read-only scope for branch protection.
set -uo pipefail

API_BASE="${GITHUB_API_BASE:-https://api.github.com}"

# Exit codes: 1 API/IO failure, 2 usage, 3 undetermined (nothing deleted),
# 4 one or more writes failed.
E_FAIL=1
E_USAGE=2
E_UNDETERMINED=3
E_WRITE=4

GH="${GH_CMD:-gh}"

# A cap on how many 'next' links a paginated read will follow. The API is
# trusted for shape but not for termination: a cyclic or merely endless Link
# chain must not turn one export into an unbounded loop against a rate-limited
# API. Overridable only so the test suite can hit the cap without generating
# thousands of fixture pages - no supported reason to change it otherwise.
MAX_PAGES="${MERGE_GATE_MAX_PAGES:-1000}"

usage() {
  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
  exit "$E_USAGE"
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit "$E_FAIL"; }

command -v jq >/dev/null 2>&1 || die "jq is required but not on PATH."

WORK="$(mktemp -d)" || die "could not create a temp directory."
trap 'rm -rf "$WORK"' EXIT

in_list() { # $1 needle, $2 whitespace-separated haystack
  local item
  for item in $2; do [ "$item" = "$1" ] && return 0; done
  return 1
}

# Every `read` loop below strips a trailing CR, and it is load-bearing: jq's
# Windows build writes CRLF. `$(...)` hides that - bash strips the whole
# trailing newline - but `read` does not, so a loop fed by jq gets values with
# a trailing CR. That turns `refs/heads/main` into something no pattern matches
# and `11` into the path segment `11<CR>`, and both failures present as scope
# logic being wrong rather than as line endings.

# ---------------------------------------------------------------- transport --

GH_STATUS=""
GH_BODY=""
GH_LINK=""
GH_ERR=""

parse_response() { # <file holding `gh api -i` output> -> GH_STATUS, GH_BODY, GH_LINK
  local file="$1" line stripped state="head" body="" status="" link=""
  while IFS= read -r line || [ -n "$line" ]; do
    stripped="${line%$'\r'}"
    # A redirect chain prints header block, blank, header block, blank, body.
    # Re-entering the header state is only legal while nothing but whitespace
    # has been collected as body, so an `HTTP/...` line inside a JSON payload
    # cannot be mistaken for a new response.
    if [ "$state" = "body" ] && [ -z "${body//[$' \t\n\r']/}" ]; then
      case "$stripped" in HTTP/[0-9]*) state="head"; link="" ;; esac
    fi
    if [ "$state" = "head" ]; then
      case "$stripped" in
        HTTP/[0-9]*)
          status="${stripped#* }"; status="${status%% *}" ;;
        [Ll]ink:*)
          link="${stripped#*:}" ;;
      esac
      [ -n "$stripped" ] || state="body"
      continue
    fi
    body="$body$line"$'\n'
  done < "$file"
  GH_STATUS="$status"
  GH_LINK="$link"
  GH_BODY="$body"
}

gh_call() { # METHOD path [json-body] -> GH_STATUS, GH_BODY, GH_LINK; rc 0 on 2xx
  local method="$1" path="$2" body="${3:-}" rc=0
  local out="$WORK/gh.out" err="$WORK/gh.err"
  : > "$out"; : > "$err"
  # `gh api -i` is what makes the status code readable. Without it a 404 meaning
  # "not protected" and a 404 meaning "you cannot see this repo" are the same
  # non-zero exit, and the second would be read as the first.
  if [ -n "$body" ]; then
    printf '%s' "$body" | "$GH" api -i -X "$method" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      --input - "$path" >"$out" 2>"$err" || rc=$?
  else
    "$GH" api -i -X "$method" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "$path" >"$out" 2>"$err" || rc=$?
  fi
  GH_ERR="$(cat "$err")"
  parse_response "$out"
  if [ -z "$GH_STATUS" ]; then
    if [ "$rc" -eq 0 ]; then GH_STATUS="200"; else GH_STATUS="unknown"; fi
  fi
  return "$rc"
}

api_error_text() { # one-line, verbatim-as-possible account of the last failure
  local msg
  msg="$(printf '%s' "$GH_BODY" | jq -r '.message // empty' 2>/dev/null)"
  if [ -z "${msg// /}" ]; then
    msg="$(printf '%s' "$GH_BODY" | tr '\n' ' ' | cut -c1-300)"
  fi
  [ -n "${msg// /}" ] || msg="$(printf '%s' "$GH_ERR" | tr '\n' ' ' | cut -c1-300)"
  [ -n "${msg// /}" ] || msg="(no message)"
  printf 'HTTP %s: %s' "$GH_STATUS" "$msg"
}

next_link() { # -> the Link header's rel="next" URL, or empty
  printf '%s' "$GH_LINK" | tr ',' '\n' \
    | sed -n 's|.*<\([^>]*\)>[[:space:]]*;[[:space:]]*rel="next".*|\1|p'
}

# ------------------------------------------------------------------- reads --

DEFAULT_BRANCH=""
DEFAULT_BRANCH_WHY=""

resolve_default_branch() { # <owner> <repo>; never fatal on its own
  DEFAULT_BRANCH=""
  if gh_call GET "repos/$1/$2"; then
    DEFAULT_BRANCH="$(printf '%s' "$GH_BODY" | jq -r '.default_branch // empty')"
    [ -n "$DEFAULT_BRANCH" ] || DEFAULT_BRANCH_WHY="the repo response has no .default_branch"
  else
    DEFAULT_BRANCH_WHY="$(api_error_text)"
  fi
}

# classic: one of present | absent | unreadable, and never inferred.
CLASSIC_STATE=""
CLASSIC_WHY=""

read_classic() { # <owner> <repo> <branch> -> $WORK/classic.json, CLASSIC_STATE
  local owner="$1" repo="$2" branch="$3"
  printf 'null' > "$WORK/classic.json"
  printf 'null' > "$WORK/signatures.json"
  if gh_call GET "repos/$owner/$repo/branches/$branch/protection"; then
    printf '%s' "$GH_BODY" | jq -e '.' > "$WORK/classic.json" 2>/dev/null || {
      CLASSIC_STATE="unreadable"
      CLASSIC_WHY="the 200 response to the classic protection read is not JSON"
      return
    }
    CLASSIC_STATE="present"
    CLASSIC_WHY="classic branch protection is configured on '$branch'"
    return
  fi
  local msg
  msg="$(printf '%s' "$GH_BODY" | jq -r '.message // empty' 2>/dev/null)"
  # This is the whole reason the status code is parsed. `cli/cli`'s trunk IS
  # protected, and reading it without admin answers 404 "Not Found" - the same
  # status as an unprotected branch, with a different message. Only the exact
  # "Branch not protected" body means there is nothing there.
  if [ "$GH_STATUS" = "404" ] && [ "$msg" = "Branch not protected" ]; then
    CLASSIC_STATE="absent"
    CLASSIC_WHY="the API answered 404 'Branch not protected'"
    return
  fi
  CLASSIC_STATE="unreadable"
  CLASSIC_WHY="$(api_error_text)"
}

SIG_STATE=""

read_signatures() { # <owner> <repo> <branch>; only meaningful when classic is present
  # "Require signed commits" is not part of the protection document - it has its
  # own endpoint, DELETE .../protection takes it down with everything else, and
  # PUT .../protection does not put it back. A failed read here is recorded as
  # unreadable rather than as `false`, which would restore a weaker gate than
  # the one that was removed while reporting a clean run.
  if gh_call GET "repos/$1/$2/branches/$3/protection/required_signatures"; then
    if printf '%s' "$GH_BODY" | jq -ce 'if has("enabled") then {state: "read", enabled: .enabled, detail: ""} else error("no .enabled") end' \
         > "$WORK/signatures.json" 2>/dev/null; then
      SIG_STATE="read"
      return
    fi
    SIG_STATE="unreadable"
    jq -nc --arg d "the required_signatures response has no .enabled" \
      '{state: "unreadable", enabled: null, detail: $d}' > "$WORK/signatures.json"
    return
  fi
  SIG_STATE="unreadable"
  jq -nc --arg d "$(api_error_text)" '{state: "unreadable", enabled: null, detail: $d}' \
    > "$WORK/signatures.json"
}

# rulesets: read | unreadable. A ruleset whose detail could not be fetched is
# recorded by id rather than dropped.
RULESETS_STATE=""
RULESETS_WHY=""
RULESETS_DECLARED=0

read_rulesets() { # <owner> <repo> -> $WORK/rulesets.json, $WORK/ruleset-unreadable.json
  local owner="$1" repo="$2"
  local url="repos/$owner/$repo/rulesets?includes_parents=true&per_page=100"
  local pages=0 next
  printf '[]' > "$WORK/ruleset-list.json"
  printf '[]' > "$WORK/rulesets.json"
  printf '[]' > "$WORK/ruleset-unreadable.json"
  : > "$WORK/pages-seen.txt"
  : > "$WORK/list.jsonl"
  RULESETS_DECLARED=0

  while : ; do
    pages=$((pages + 1))
    if [ "$pages" -gt "$MAX_PAGES" ]; then
      RULESETS_STATE="unreadable"
      RULESETS_WHY="pagination exceeded $MAX_PAGES page(s) - refusing to follow 'next' further."
      return
    fi
    if grep -qxF "$url" "$WORK/pages-seen.txt" 2>/dev/null; then
      RULESETS_STATE="unreadable"
      RULESETS_WHY="pagination looped: $url was already fetched - the API's Link 'next' is cyclic."
      return
    fi
    printf '%s\n' "$url" >> "$WORK/pages-seen.txt"
    if ! gh_call GET "$url"; then
      RULESETS_STATE="unreadable"
      RULESETS_WHY="GET $url failed - $(api_error_text)"
      return
    fi
    if ! printf '%s' "$GH_BODY" | jq -ce 'if type == "array" then . else error("not an array") end' \
         >> "$WORK/list.jsonl" 2>/dev/null; then
      RULESETS_STATE="unreadable"
      RULESETS_WHY="the response to GET $url is not a JSON array"
      return
    fi
    next="$(next_link)"
    [ -n "$next" ] || break
    case "$next" in
      "$API_BASE"/*) url="${next#"$API_BASE"/}" ;;
      *)
        RULESETS_STATE="unreadable"
        RULESETS_WHY="pagination 'next' is not under $API_BASE: $next"
        return ;;
    esac
  done

  jq -s 'add // []' "$WORK/list.jsonl" > "$WORK/ruleset-list.json" \
    || { RULESETS_STATE="unreadable"; RULESETS_WHY="could not assemble the paginated ruleset list"; return; }
  RULESETS_DECLARED="$(jq 'length' "$WORK/ruleset-list.json")"

  # The list endpoint returns NO `rules` and NO `conditions` - verified against
  # repos/facebook/react/rulesets, whose rows carry only id/name/target/
  # enforcement/source. An export built from the list alone looks complete and
  # restores nothing, so every ruleset is fetched by id.
  local id name detail
  : > "$WORK/detail.jsonl"
  : > "$WORK/unreadable.jsonl"
  while IFS= read -r id; do
    id="${id%$'\r'}"
    [ -n "$id" ] || continue
    if gh_call GET "repos/$owner/$repo/rulesets/$id"; then
      detail="$(printf '%s' "$GH_BODY" | jq -c 'if type == "object" then . else empty end' 2>/dev/null)"
      if [ -n "$detail" ]; then
        printf '%s\n' "$detail" >> "$WORK/detail.jsonl"
        continue
      fi
    fi
    name="$(jq -r --argjson i "$id" '.[] | select(.id == $i) | .name // ""' "$WORK/ruleset-list.json")"
    jq -nc --argjson i "$id" --arg n "$name" --arg s "$GH_STATUS" --arg d "$(api_error_text)" \
      '{id: $i, name: $n, http_status: $s, detail: $d}' >> "$WORK/unreadable.jsonl"
  done < <(jq -r '.[].id // empty' "$WORK/ruleset-list.json")

  jq -s '.' "$WORK/detail.jsonl" > "$WORK/rulesets.json"
  jq -s '.' "$WORK/unreadable.jsonl" > "$WORK/ruleset-unreadable.json"
  if [ "$(jq 'length' "$WORK/ruleset-unreadable.json")" != "0" ]; then
    RULESETS_STATE="unreadable"
    RULESETS_WHY="$(jq -r 'length' "$WORK/ruleset-unreadable.json") ruleset(s) are listed but their rules could not be read"
    return
  fi
  RULESETS_STATE="read"
  RULESETS_WHY="$RULESETS_DECLARED ruleset(s) read in full"
}

read_all() { # <owner> <repo> <branch>
  SIG_STATE=""
  read_classic "$1" "$2" "$3"
  [ "$CLASSIC_STATE" = "present" ] && read_signatures "$1" "$2" "$3"
  read_rulesets "$1" "$2"
}

any_surface_unreadable() {
  [ "$CLASSIC_STATE" = "unreadable" ] && return 0
  [ "$RULESETS_STATE" = "unreadable" ] && return 0
  [ "$SIG_STATE" = "unreadable" ] && return 0
  return 1
}

# ------------------------------------------------------------------ export --

build_export_doc() { # the whole document, as text, before anything is opened
  jq -n \
    --arg owner "$OWNER" --arg repo "$REPO" --arg branch "$BRANCH" \
    --arg base "$API_BASE" \
    --arg default_branch "$DEFAULT_BRANCH" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg cstate "$CLASSIC_STATE" --arg cwhy "$CLASSIC_WHY" \
    --arg rstate "$RULESETS_STATE" --arg rwhy "$RULESETS_WHY" \
    --argjson declared "${RULESETS_DECLARED:-0}" \
    --slurpfile classic "$WORK/classic.json" \
    --slurpfile signatures "$WORK/signatures.json" \
    --slurpfile rulesets "$WORK/rulesets.json" \
    --slurpfile unreadable "$WORK/ruleset-unreadable.json" \
    '{tool: "merge_gate.sh", format: 1, exported_at: $ts,
      host: $base, owner: $owner, repository: $repo,
      branch: $branch, default_branch: (if $default_branch == "" then null else $default_branch end),
      note: "Both gate surfaces. classic.state and rulesets.state are present/absent/read/unreadable - an unreadable surface is NOT an empty one, and enable refuses to restore from an export that holds one.",
      classic: {state: $cstate, detail: $cwhy,
                protection: $classic[0],
                required_signatures: $signatures[0]},
      rulesets: {state: $rstate, detail: $rwhy,
                 declared: $declared,
                 count: ($rulesets[0] | length),
                 values: $rulesets[0],
                 unreadable: $unreadable[0]}}'
}

write_validated_export() { # <destination>
  local dest="$1" doc tmp read_count unread_count
  # Compute the full text first. A write whose argument expression raises must
  # never have truncated the destination already.
  doc="$(build_export_doc)" || { echo "ERROR: could not build the export document - nothing written." >&2; return 1; }
  [ -n "$doc" ] || { echo "ERROR: the export document came out empty - nothing written." >&2; return 1; }
  tmp="$WORK/export.json"
  printf '%s\n' "$doc" > "$tmp" || { echo "ERROR: could not write the temporary export." >&2; return 1; }
  # Re-read what actually landed on disk, not what we think we wrote.
  jq -e . "$tmp" >/dev/null 2>&1 || { echo "ERROR: the export did not re-read as JSON." >&2; return 1; }
  read_count="$(jq '.rulesets.values | length' "$tmp")"
  unread_count="$(jq '.rulesets.unreadable | length' "$tmp")"
  if [ "$((read_count + unread_count))" != "${RULESETS_DECLARED:-0}" ]; then
    echo "ERROR: the export accounts for $((read_count + unread_count)) ruleset(s) but the API listed ${RULESETS_DECLARED:-0}." >&2
    echo "       Refusing to continue: nothing was written and nothing was deleted." >&2
    return 1
  fi
  if [ "$(jq -r '.classic.state' "$tmp")" = "" ]; then
    echo "ERROR: the export records no classic state - nothing written." >&2
    return 1
  fi
  # The count check above covers the ruleset side. The classic side needs its own:
  # `state: "present"` with a null `.protection` validates clean, survives the
  # delete, and only fails hours later at restore time - the one shape where a
  # good-looking export is unrestorable. Catch it here, before anything is deleted.
  if [ "$(jq -r '.classic.state' "$tmp")" = "present" ] &&
     [ "$(jq -r '.classic.protection | type' "$tmp")" != "object" ]; then
    echo "ERROR: the export says classic protection is present but holds no protection object." >&2
    echo "       Refusing to continue: nothing was written and nothing was deleted." >&2
    return 1
  fi
  mv "$tmp" "$dest" || { echo "ERROR: could not move the export into place at $dest" >&2; return 1; }
  return 0
}

# ------------------------------------------------------- scope resolution --

COVER=""      # yes | no | undetermined | inherited
COVER_WHY=""

ref_matches() { # <json array of ref_name entries> <branch> -> yes|no|undetermined
  local entries="$1" branch="$2" entry saw_undetermined=0
  local ref="refs/heads/$branch"
  while IFS= read -r entry; do
    entry="${entry%$'\r'}"
    [ -n "$entry" ] || continue
    case "$entry" in
      '~ALL') printf 'yes'; return ;;
      '~DEFAULT_BRANCH')
        if [ -z "$DEFAULT_BRANCH" ]; then saw_undetermined=1; continue; fi
        [ "$DEFAULT_BRANCH" = "$branch" ] && { printf 'yes'; return; }
        continue ;;
      refs/heads/*)
        # Unquoted right-hand side on purpose: this is pattern matching, not a
        # string compare. Bash's `*` also crosses `/` where GitHub's fnmatch
        # does not, so the judgement is on the permissive side - every ruleset
        # judged covering is printed before it goes.
        # shellcheck disable=SC2053
        if [[ $ref == $entry ]]; then printf 'yes'; return; fi
        continue ;;
      refs/tags/*) continue ;;
      ~*) saw_undetermined=1; continue ;;
      *) saw_undetermined=1; continue ;;
    esac
  done < <(printf '%s' "$entries" | jq -r '.[]? // empty')
  if [ "$saw_undetermined" -eq 1 ]; then printf 'undetermined'; else printf 'no'; fi
}

classify_ruleset() { # <ruleset json> <branch>
  local obj="$1" branch="$2" target enforcement source_type include exclude hit
  target="$(printf '%s' "$obj" | jq -r '.target // "branch"')"
  enforcement="$(printf '%s' "$obj" | jq -r '.enforcement // empty')"
  source_type="$(printf '%s' "$obj" | jq -r '.source_type // empty')"

  if [ "$target" != "branch" ]; then
    COVER="no"; COVER_WHY="target '$target' is not a branch gate"; return
  fi
  case "$enforcement" in
    disabled) COVER="no"; COVER_WHY="enforcement is already 'disabled'"; return ;;
    evaluate) COVER="no"; COVER_WHY="enforcement 'evaluate' reports but does not block a merge"; return ;;
    active) : ;;
    *) COVER="undetermined"; COVER_WHY="unrecognised enforcement '$enforcement'"; return ;;
  esac
  if ! printf '%s' "$obj" | jq -e 'has("conditions")' >/dev/null 2>&1; then
    COVER="undetermined"; COVER_WHY="the ruleset carries no .conditions, so what it targets cannot be read"; return
  fi

  exclude="$(printf '%s' "$obj" | jq -c '.conditions.ref_name.exclude // []')"
  hit="$(ref_matches "$exclude" "$branch")"
  if [ "$hit" = "undetermined" ]; then
    COVER="undetermined"
    COVER_WHY="an entry in conditions.ref_name.exclude is not a form this script can evaluate"
    return
  fi
  if [ "$hit" = "yes" ]; then
    COVER="no"; COVER_WHY="conditions.ref_name.exclude matches '$branch'"; return
  fi

  include="$(printf '%s' "$obj" | jq -c '.conditions.ref_name.include // []')"
  hit="$(ref_matches "$include" "$branch")"
  case "$hit" in
    no) COVER="no"; COVER_WHY="conditions.ref_name.include does not match '$branch'"; return ;;
    undetermined)
      COVER="undetermined"
      COVER_WHY="an entry in conditions.ref_name.include is not a form this script can evaluate"
      [ -n "$DEFAULT_BRANCH" ] || COVER_WHY="$COVER_WHY (the default branch could not be resolved, so '~DEFAULT_BRANCH' cannot be judged: $DEFAULT_BRANCH_WHY)"
      return ;;
  esac

  if [ "$source_type" != "Repository" ]; then
    COVER="inherited"
    COVER_WHY="source_type '$source_type' - this ruleset is owned above the repository and cannot be removed through the repo endpoint"
    return
  fi
  COVER="yes"; COVER_WHY="conditions.ref_name.include matches '$branch'"
}

ruleset_label() { # <ruleset json>
  printf '%s' "$1" | jq -r '"\(.name // "?") [\(.target // "?")/\(.enforcement // "?")/\(.source_type // "?")]"'
}

# ------------------------------------------------------------------ status --

print_state() { # <branch>
  local branch="$1" obj id
  printf 'target branch: %s\n' "$branch"
  printf 'default branch: %s\n' "${DEFAULT_BRANCH:-<unresolved: $DEFAULT_BRANCH_WHY>}"
  printf '\nclassic branch protection: %s\n' "$CLASSIC_STATE"
  printf '  %s\n' "$CLASSIC_WHY"
  if [ -n "$SIG_STATE" ]; then
    printf '  required signed commits: %s (%s)\n' "$SIG_STATE" \
      "$(jq -r 'if .enabled == null then (.detail // "") else (.enabled | tostring) end' "$WORK/signatures.json")"
  fi
  printf '\nrulesets: %s\n' "$RULESETS_STATE"
  printf '  %s\n' "$RULESETS_WHY"
  while IFS= read -r obj; do
    obj="${obj%$'\r'}"
    [ -n "$obj" ] || continue
    id="$(printf '%s' "$obj" | jq -r '.id // empty')"
    classify_ruleset "$obj" "$branch"
    printf '  %-12s id=%-10s %-52s %s\n' "$COVER" "$id" "$(ruleset_label "$obj")" "$COVER_WHY"
  done < <(jq -c '.[]' "$WORK/rulesets.json" 2>/dev/null)
  while IFS= read -r obj; do
    obj="${obj%$'\r'}"
    [ -n "$obj" ] || continue
    printf '  %-12s id=%-10s %s\n' "UNREADABLE" \
      "$(printf '%s' "$obj" | jq -r '.id')" "$(printf '%s' "$obj" | jq -r '.detail')"
  done < <(jq -c '.[]' "$WORK/ruleset-unreadable.json" 2>/dev/null)
}

cmd_status() {
  [ "$#" -ge 2 ] || usage
  OWNER="$1"; REPO="$2"; shift 2
  BRANCH=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --branch) BRANCH="${2:?--branch needs a value}"; shift 2 ;;
      *) printf 'unknown option: %s\n' "$1" >&2; usage ;;
    esac
  done
  resolve_default_branch "$OWNER" "$REPO"
  [ -n "$BRANCH" ] || BRANCH="$DEFAULT_BRANCH"
  [ -n "$BRANCH" ] || die "could not resolve the repository's default branch ($DEFAULT_BRANCH_WHY) - pass --branch explicitly."
  read_all "$OWNER" "$REPO" "$BRANCH"
  print_state "$BRANCH"
  if any_surface_unreadable; then
    printf '\nAt least one gate surface could not be read. That is not "nothing configured".\n' >&2
    exit "$E_UNDETERMINED"
  fi
}

cmd_export() {
  [ "$#" -ge 3 ] || usage
  OWNER="$1"; REPO="$2"; local out="$3"; shift 3
  BRANCH=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --branch) BRANCH="${2:?--branch needs a value}"; shift 2 ;;
      *) printf 'unknown option: %s\n' "$1" >&2; usage ;;
    esac
  done
  resolve_default_branch "$OWNER" "$REPO"
  [ -n "$BRANCH" ] || BRANCH="$DEFAULT_BRANCH"
  [ -n "$BRANCH" ] || die "could not resolve the repository's default branch ($DEFAULT_BRANCH_WHY) - pass --branch explicitly."
  read_all "$OWNER" "$REPO" "$BRANCH"
  write_validated_export "$out" || exit "$E_FAIL"
  printf 'export: %s/%s branch %s written to %s\n' "$OWNER" "$REPO" "$BRANCH" "$out"
  printf '        classic: %s | rulesets: %s (%s read, %s unreadable)\n' \
    "$CLASSIC_STATE" "$RULESETS_STATE" \
    "$(jq '.rulesets.values | length' "$out")" "$(jq '.rulesets.unreadable | length' "$out")"
  if any_surface_unreadable; then
    printf '\nWARNING: the export records a surface it could not read. enable --from-export\n' >&2
    printf '         will refuse it rather than restore a partial picture.\n' >&2
    exit "$E_UNDETERMINED"
  fi
}

# ----------------------------------------------------------------- disable --

cmd_disable() {
  [ "$#" -ge 2 ] || usage
  OWNER="$1"; REPO="$2"; shift 2
  BRANCH=""
  local export_to="" dry_run=0 allow_inherited=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --branch) BRANCH="${2:?--branch needs a value}"; shift 2 ;;
      --export-to) export_to="${2:?--export-to needs a value}"; shift 2 ;;
      --allow-inherited) allow_inherited=1; shift ;;
      --dry-run) dry_run=1; shift ;;
      *) printf 'unknown option: %s\n' "$1" >&2; usage ;;
    esac
  done
  [ -n "$export_to" ] || export_to="merge-gate-${OWNER}-${REPO}-$(date -u +%Y%m%dT%H%M%SZ).json"

  # --dry-run runs NOTHING, the export included. It cannot enumerate live
  # objects, so it prints the call sequence instead of a per-object plan. That
  # is a deliberate divergence from the Bitbucket twin, whose --dry-run exports
  # first; do not "fix" it back.
  if [ "$dry_run" -eq 1 ]; then
    printf 'dry run: no request was sent and no file was written.\n\n'
    # No apostrophe in a ${x:-word} default: inside "${...}" bash still opens a
    # quote context on one, and the rest of the file parses as a string.
    printf 'would target: %s/%s branch %s\n' "$OWNER" "$REPO" "${BRANCH:-<the default branch>}"
    printf 'would write the export to: %s\n\n' "$export_to"
    printf 'would call, in order:\n'
    [ -n "$BRANCH" ] || printf '  GET    repos/%s/%s                                    (resolve .default_branch)\n' "$OWNER" "$REPO"
    printf '  GET    repos/%s/%s/branches/%s/protection\n' "$OWNER" "$REPO" "${BRANCH:-<branch>}"
    printf '  GET    repos/%s/%s/branches/%s/protection/required_signatures  (only when classic protection exists)\n' "$OWNER" "$REPO" "${BRANCH:-<branch>}"
    printf '  GET    repos/%s/%s/rulesets?includes_parents=true&per_page=100\n' "$OWNER" "$REPO"
    printf '  GET    repos/%s/%s/rulesets/{id}                      (once per listed ruleset)\n' "$OWNER" "$REPO"
    printf '  -- write the export, re-read it from disk, verify the counts --\n'
    printf '  DELETE repos/%s/%s/branches/%s/protection             (only when it exists)\n' "$OWNER" "$REPO" "${BRANCH:-<branch>}"
    printf '  DELETE repos/%s/%s/rulesets/{id}                      (once per covering repo-level ruleset)\n' "$OWNER" "$REPO"
    printf '\nNothing above ran. Re-run without --dry-run to see the per-object plan.\n'
    return 0
  fi

  resolve_default_branch "$OWNER" "$REPO"
  [ -n "$BRANCH" ] || BRANCH="$DEFAULT_BRANCH"
  [ -n "$BRANCH" ] || die "could not resolve the repository's default branch ($DEFAULT_BRANCH_WHY) - pass --branch explicitly."

  read_all "$OWNER" "$REPO" "$BRANCH"
  printf 'target branch: %s\n' "$BRANCH"
  write_validated_export "$export_to" || exit "$E_FAIL"
  printf 'backup: the gate state was exported and re-verified at %s\n\n' "$export_to"

  local blocked=0
  if [ "$CLASSIC_STATE" = "unreadable" ]; then
    printf '  UNREADABLE   classic branch protection - %s\n' "$CLASSIC_WHY"
    blocked=$((blocked + 1))
  fi
  if [ "$RULESETS_STATE" = "unreadable" ]; then
    printf '  UNREADABLE   rulesets - %s\n' "$RULESETS_WHY"
    blocked=$((blocked + 1))
  fi
  if [ "$SIG_STATE" = "unreadable" ]; then
    printf '  UNREADABLE   required signed commits - %s\n' "$(jq -r '.detail // ""' "$WORK/signatures.json")"
    blocked=$((blocked + 1))
  fi

  # Plan the whole thing before deleting anything.
  : > "$WORK/plan.delete"
  local skipped=0 undetermined=0 inherited=0 obj id label
  printf 'plan:\n'
  if [ "$CLASSIC_STATE" = "present" ]; then
    printf '  delete       %-63s %s\n' "classic branch protection" "$CLASSIC_WHY"
    printf 'classic\t-\tclassic branch protection\n' >> "$WORK/plan.delete"
  elif [ "$CLASSIC_STATE" = "absent" ]; then
    printf '  skip         %-63s %s\n' "classic branch protection" "$CLASSIC_WHY"
    skipped=$((skipped + 1))
  fi
  while IFS= read -r obj; do
    obj="${obj%$'\r'}"
    [ -n "$obj" ] || continue
    id="$(printf '%s' "$obj" | jq -r '.id // empty')"
    label="$(ruleset_label "$obj")"
    classify_ruleset "$obj" "$BRANCH"
    case "$COVER" in
      yes)
        printf '  delete       id=%-10s %-52s %s\n' "$id" "$label" "$COVER_WHY"
        printf 'ruleset\t%s\t%s\n' "$id" "$label" >> "$WORK/plan.delete" ;;
      no)
        printf '  skip         id=%-10s %-52s %s\n' "$id" "$label" "$COVER_WHY"
        skipped=$((skipped + 1)) ;;
      inherited)
        printf '  INHERITED    id=%-10s %-52s %s\n' "$id" "$label" "$COVER_WHY"
        inherited=$((inherited + 1)) ;;
      *)
        printf '  UNDETERMINED id=%-10s %-52s %s\n' "$id" "$label" "$COVER_WHY"
        undetermined=$((undetermined + 1)) ;;
    esac
  done < <(jq -c '.[]' "$WORK/rulesets.json")

  local to_delete
  to_delete="$(jq -R -s 'split("\n") | map(select(length > 0)) | length' < "$WORK/plan.delete")"

  if [ "$blocked" -gt 0 ]; then
    printf '\nERROR: %s gate surface(s) above could not be read, so what is on this branch\n' "$blocked" >&2
    printf '       is not known. Nothing was deleted. An unreadable surface is not an\n' >&2
    printf '       empty one - fix the access (admin on %s/%s is required for both) and\n' "$OWNER" "$REPO" >&2
    printf '       re-run. The export at %s records exactly what could and could not be read.\n' "$export_to" >&2
    exit "$E_UNDETERMINED"
  fi
  if [ "$undetermined" -gt 0 ]; then
    printf '\nERROR: %s ruleset(s) above could not be resolved against branch %s.\n' "$undetermined" "$BRANCH" >&2
    printf '       Nothing was deleted. Their conditions.ref_name entries are in a form\n' >&2
    printf '       this script does not evaluate, so it will not guess whether they gate\n' >&2
    printf '       this branch. The export at %s is complete and valid.\n' "$export_to" >&2
    exit "$E_UNDETERMINED"
  fi
  if [ "$inherited" -gt 0 ] && [ "$allow_inherited" -eq 0 ]; then
    printf '\nERROR: %s ruleset(s) above gate %s but are owned by the organization or\n' "$inherited" "$BRANCH" >&2
    printf '       enterprise, not this repository. DELETE on the repo endpoint cannot\n' >&2
    printf '       remove them, so disabling everything else would still leave the merge\n' >&2
    printf '       gate partly on while reporting success. Nothing was deleted.\n' >&2
    printf '       Turn them off where they are defined, or re-run with --allow-inherited\n' >&2
    printf '       to remove what this repo does own and accept that the rest stays.\n' >&2
    exit "$E_UNDETERMINED"
  fi

  printf '\n'
  local deleted=0 failed=0 kind
  : > "$WORK/landed.txt"
  while IFS=$'\t' read -r kind id label; do
    [ -n "$kind" ] || continue
    local path
    if [ "$kind" = "classic" ]; then
      path="repos/$OWNER/$REPO/branches/$BRANCH/protection"
    else
      path="repos/$OWNER/$REPO/rulesets/$id"
    fi
    if gh_call DELETE "$path"; then
      printf '  deleted  %-10s %s\n' "${id#-}" "$label"
      printf '%s\t%s\t%s\n' "$kind" "$id" "$label" >> "$WORK/landed.txt"
      deleted=$((deleted + 1))
    else
      printf '  FAILED   %-10s %s - %s\n' "${id#-}" "$label" "$(api_error_text)" >&2
      failed=$((failed + 1))
    fi
  done < "$WORK/plan.delete"

  printf '\ndisable: removed %s of %s planned object(s) gating %s in %s/%s.\n' \
    "$deleted" "$to_delete" "$BRANCH" "$OWNER" "$REPO"
  printf '         Skipped %s; inherited-and-left %s; failed %s.\n' "$skipped" "$inherited" "$failed"
  if [ "$failed" -gt 0 ]; then
    printf '         What actually landed:\n' >&2
    if [ -s "$WORK/landed.txt" ]; then
      while IFS=$'\t' read -r kind id label; do
        printf '           deleted %s %s (%s)\n' "$kind" "${id#-}" "$label" >&2
      done < "$WORK/landed.txt"
    else
      printf '           nothing - every planned delete failed.\n' >&2
    fi
  fi
  printf '         Restore with: %s enable %s %s --from-export %s\n' "$(basename "$0")" "$OWNER" "$REPO" "$export_to"
  if [ "$inherited" -gt 0 ] && [ "$allow_inherited" -eq 1 ]; then
    # --allow-inherited turns a refusal into a success, so the exit code alone now
    # says "done" on a branch that is still gated. A caller that checks only the
    # status - which is what an automated gate does - would read this as the gate
    # being off. The summary line above is on stdout; say it on stderr too, so a
    # run that logs only stderr still carries the caveat.
    printf 'WARNING: %s inherited ruleset(s) still gate %s in %s/%s. They are owned by\n' \
      "$inherited" "$BRANCH" "$OWNER" "$REPO" >&2
    printf '         the organization or enterprise and were left standing because\n' >&2
    printf '         --allow-inherited was passed. This run exited successfully; the\n' >&2
    printf '         merge gate is NOT fully off. Turn them off where they are defined.\n' >&2
  fi
  [ "$failed" -eq 0 ] || exit "$E_WRITE"
}

# ------------------------------------------------------------------ enable --

protection_put_body() { # <classic protection object as GET returned it>
  # The GET and PUT shapes are NOT the same document. GET returns actors as
  # objects and carries url/contexts_url keys PUT rejects; PUT wants logins and
  # slugs, and all four top-level keys present even when null. Round-tripping
  # the GET body answers 422.
  printf '%s' "$1" | jq -c '
    def actors: {
      users: [(.users // [])[] | .login // empty],
      teams: [(.teams // [])[] | .slug // empty],
      apps:  [(.apps  // [])[] | .slug // empty]
    };
    def flag(k): if (.[k] // null) == null then {} else {(k): (.[k].enabled // false)} end;
    {
      required_status_checks: (
        if (.required_status_checks // null) == null then null
        else {strict: (.required_status_checks.strict // false)}
             + (if (.required_status_checks.checks // null) != null
                then {checks: [.required_status_checks.checks[] | {context: .context, app_id: .app_id}]}
                else {contexts: (.required_status_checks.contexts // [])} end)
        end),
      enforce_admins: (if (.enforce_admins // null) == null then null else (.enforce_admins.enabled // false) end),
      required_pull_request_reviews: (
        if (.required_pull_request_reviews // null) == null then null
        else {
          dismiss_stale_reviews: (.required_pull_request_reviews.dismiss_stale_reviews // false),
          require_code_owner_reviews: (.required_pull_request_reviews.require_code_owner_reviews // false),
          required_approving_review_count: (.required_pull_request_reviews.required_approving_review_count // 0),
          require_last_push_approval: (.required_pull_request_reviews.require_last_push_approval // false)
        }
        + (if (.required_pull_request_reviews.dismissal_restrictions // null) == null then {}
           else {dismissal_restrictions: (.required_pull_request_reviews.dismissal_restrictions | actors)} end)
        + (if (.required_pull_request_reviews.bypass_pull_request_allowances // null) == null then {}
           else {bypass_pull_request_allowances: (.required_pull_request_reviews.bypass_pull_request_allowances | actors)} end)
        end),
      restrictions: (if (.restrictions // null) == null then null else (.restrictions | actors) end)
    }
    + flag("required_linear_history") + flag("allow_force_pushes") + flag("allow_deletions")
    + flag("block_creations") + flag("required_conversation_resolution")
    + flag("lock_branch") + flag("allow_fork_syncing")'
}

ruleset_post_body() { # <ruleset detail as GET returned it>
  # id, node_id, source, source_type, created_at, updated_at, _links and
  # current_user_can_bypass are server-owned. A restore POSTs a fresh object;
  # the id is not stable across delete/recreate and is never sent back.
  printf '%s' "$1" | jq -c '
    {name: .name, target: (.target // "branch"), enforcement: (.enforcement // "active"),
     conditions: (.conditions // {}), rules: (.rules // [])}
    + (if (.bypass_actors // null) == null then {}
       else {bypass_actors: [.bypass_actors[] | {actor_id, actor_type, bypass_mode}]} end)'
}

cmd_enable() {
  [ "$#" -ge 2 ] || usage
  OWNER="$1"; REPO="$2"; shift 2
  local from_export=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --from-export) from_export="${2:?--from-export needs a value}"; shift 2 ;;
      --branch) printf 'enable takes no --branch: every exported object carries its own scope.\n' >&2; usage ;;
      *) printf 'unknown option: %s\n' "$1" >&2; usage ;;
    esac
  done

  # There is no preset. A bare re-enable would invent a gate rather than put
  # back the one that was removed, and would silently drop everything the
  # export held - which is the whole reason this script exists.
  if [ -z "$from_export" ]; then
    printf 'ERROR: enable requires --from-export FILE.\n' >&2
    printf '       This script has no preset and will not invent a merge gate: the only\n' >&2
    printf '       restore is the export that disable wrote. Nothing was changed.\n' >&2
    exit "$E_USAGE"
  fi

  [ -f "$from_export" ] || die "no such export file: $from_export"
  jq -e . "$from_export" >/dev/null 2>&1 || die "$from_export is not valid JSON."
  # A missing key is a malformed or foreign export, not an empty one. An unknown
  # must never collapse into the safe-looking "0 restored, rc 0".
  jq -e 'has("classic") and has("rulesets") and (.rulesets | has("values"))' "$from_export" >/dev/null 2>&1 \
    || die "$from_export has no .classic and .rulesets.values - refusing to silently restore nothing."

  local cstate rstate sstate
  cstate="$(jq -r '.classic.state // ""' "$from_export")"
  rstate="$(jq -r '.rulesets.state // ""' "$from_export")"
  sstate="$(jq -r '.classic.required_signatures.state // ""' "$from_export")"
  if [ "$cstate" = "unreadable" ] || [ "$rstate" = "unreadable" ] || [ "$sstate" = "unreadable" ]; then
    printf 'ERROR: %s records a gate surface it could not read:\n' "$from_export" >&2
    [ "$cstate" = "unreadable" ] && printf '         classic: %s\n' "$(jq -r '.classic.detail // ""' "$from_export")" >&2
    [ "$rstate" = "unreadable" ] && printf '         rulesets: %s\n' "$(jq -r '.rulesets.detail // ""' "$from_export")" >&2
    [ "$sstate" = "unreadable" ] && printf '         required signed commits: %s\n' "$(jq -r '.classic.required_signatures.detail // ""' "$from_export")" >&2
    printf '       Restoring from it would put back a partial gate and report success.\n' >&2
    printf '       Nothing was changed.\n' >&2
    exit "$E_FAIL"
  fi

  local exp_owner exp_repo exp_branch
  exp_owner="$(jq -r '.owner // empty' "$from_export")"
  exp_repo="$(jq -r '.repository // empty' "$from_export")"
  exp_branch="$(jq -r '.branch // empty' "$from_export")"
  if [ -n "$exp_owner" ] && [ -n "$exp_repo" ] && { [ "$exp_owner" != "$OWNER" ] || [ "$exp_repo" != "$REPO" ]; }; then
    printf 'WARNING: %s was exported from %s/%s, not the target %s/%s - proceeding anyway.\n' \
      "$from_export" "$exp_owner" "$exp_repo" "$OWNER" "$REPO" >&2
  fi
  [ -n "$exp_branch" ] || die "$from_export records no .branch, so the classic protection has no target."

  # What is already there, so a re-run does not create a second ruleset with the
  # same name. Read BEFORE any write: if the live state cannot be read, this
  # run cannot tell a restore from a duplicate, and writing anyway is how you
  # end up with two gates where there was one.
  if ! gh_call GET "repos/$OWNER/$REPO/rulesets?per_page=100"; then
    die "could not list the repository's current rulesets - $(api_error_text). Nothing was changed."
  fi
  printf '%s' "$GH_BODY" \
    | jq -r '.[]? | select((.source_type // "Repository") == "Repository") | .name // empty' 2>/dev/null \
    | tr -d '\r' > "$WORK/existing-names.txt" || : > "$WORK/existing-names.txt"

  printf 'restoring %s/%s branch %s from %s\n' "$OWNER" "$REPO" "$exp_branch" "$from_export"
  printf '  classic: %s | rulesets: %s recorded\n\n' "$cstate" "$(jq '.rulesets.values | length' "$from_export")"

  local applied=0 failed=0 nothing=0
  : > "$WORK/landed.txt"

  if [ "$cstate" = "present" ]; then
    local protection body
    protection="$(jq -c '.classic.protection' "$from_export")"
    if [ -z "$protection" ] || [ "$protection" = "null" ]; then
      printf '  %-16s classic branch protection - the export says "present" but holds no object\n' "failed" >&2
      failed=$((failed + 1))
    else
      body="$(protection_put_body "$protection")"
      if [ -z "$body" ]; then
        printf '  %-16s classic branch protection - could not build a PUT body\n' "failed" >&2
        failed=$((failed + 1))
      elif gh_call PUT "repos/$OWNER/$REPO/branches/$exp_branch/protection" "$body"; then
        printf '  %-16s classic branch protection on %s\n' "applied" "$exp_branch"
        printf 'classic protection on %s\n' "$exp_branch" >> "$WORK/landed.txt"
        applied=$((applied + 1))
        local sigs
        sigs="$(jq -r 'if .classic.required_signatures == null then "null" else (.classic.required_signatures.enabled | tostring) end' "$from_export")"
        if [ "$sigs" = "true" ]; then
          if gh_call POST "repos/$OWNER/$REPO/branches/$exp_branch/protection/required_signatures"; then
            printf '  %-16s required signed commits\n' "applied"
            printf 'required signed commits on %s\n' "$exp_branch" >> "$WORK/landed.txt"
            applied=$((applied + 1))
          else
            printf '  %-16s required signed commits - %s\n' "failed" "$(api_error_text)" >&2
            failed=$((failed + 1))
          fi
        fi
      else
        printf '  %-16s classic branch protection - %s\n' "failed" "$(api_error_text)" >&2
        failed=$((failed + 1))
      fi
    fi
  elif [ "$cstate" = "absent" ]; then
    printf '  %-16s classic branch protection - the export recorded none, so none is created\n' "nothing-to-do"
    nothing=$((nothing + 1))
  else
    printf '  %-16s classic branch protection - the export records state %s\n' "failed" "${cstate:-<empty>}" >&2
    failed=$((failed + 1))
  fi

  local obj name body
  while IFS= read -r obj; do
    obj="${obj%$'\r'}"
    [ -n "$obj" ] || continue
    name="$(printf '%s' "$obj" | jq -r '.name // empty')"
    if [ -z "$name" ]; then
      printf '  %-16s a ruleset in the export has no name - nothing to recreate it as\n' "failed" >&2
      failed=$((failed + 1)); continue
    fi
    if ! printf '%s' "$obj" | jq -e 'has("rules")' >/dev/null 2>&1; then
      # The list endpoint's rows carry no `rules`. Restoring one would create an
      # empty ruleset with the right name and no protection at all.
      printf '  %-16s ruleset %s - the export entry carries no .rules, so it cannot be rebuilt\n' "failed" "$name" >&2
      failed=$((failed + 1)); continue
    fi
    if [ "$(printf '%s' "$obj" | jq -r '.source_type // ""')" != "Repository" ]; then
      printf '  %-16s ruleset %s - owned above this repository; it was never removed here\n' "nothing-to-do" "$name"
      nothing=$((nothing + 1)); continue
    fi
    if grep -qxF "$name" "$WORK/existing-names.txt" 2>/dev/null; then
      printf '  %-16s ruleset %s - a repo-level ruleset of that name is already there\n' "already-present" "$name"
      nothing=$((nothing + 1)); continue
    fi
    body="$(ruleset_post_body "$obj")"
    if [ -z "$body" ]; then
      printf '  %-16s ruleset %s - could not build a POST body\n' "failed" "$name" >&2
      failed=$((failed + 1)); continue
    fi
    if gh_call POST "repos/$OWNER/$REPO/rulesets" "$body"; then
      printf '  %-16s ruleset %s (new id %s)\n' "applied" "$name" \
        "$(printf '%s' "$GH_BODY" | jq -r '.id // "?"')"
      printf 'ruleset %s\n' "$name" >> "$WORK/landed.txt"
      applied=$((applied + 1))
    else
      printf '  %-16s ruleset %s - %s\n' "failed" "$name" "$(api_error_text)" >&2
      failed=$((failed + 1))
    fi
  done < <(jq -c '.rulesets.values[]' "$from_export")

  printf '\nenable: applied %s, nothing-to-do %s, failed %s\n' "$applied" "$nothing" "$failed"
  printf '        Ruleset ids are not stable across delete/recreate - every restored\n'
  printf '        ruleset is a fresh object, so anything that referenced the old id\n'
  printf '        (a required check, an audit query) has to be re-pointed.\n'
  if [ "$failed" -gt 0 ]; then
    printf '        What actually landed:\n' >&2
    if [ -s "$WORK/landed.txt" ]; then
      sed 's/^/          /' "$WORK/landed.txt" >&2
    else
      printf '          nothing - every restore failed.\n' >&2
    fi
  fi
  [ "$failed" -eq 0 ] || exit "$E_WRITE"
}

# -------------------------------------------------------------------- main --

OWNER=""; REPO=""; BRANCH=""

[ "$#" -ge 1 ] || usage
SUB="$1"; shift
case "$SUB" in
  status)  cmd_status "$@" ;;
  export)  cmd_export "$@" ;;
  disable) cmd_disable "$@" ;;
  enable)  cmd_enable "$@" ;;
  -h|--help|help) usage ;;
  *) printf 'unknown subcommand: %s\n' "$SUB" >&2; usage ;;
esac
