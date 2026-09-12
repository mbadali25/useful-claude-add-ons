#!/usr/bin/env bash
# merge_gate.sh - export, remove and re-create the branch restrictions that make
# up a Bitbucket Cloud repo's merge gate.
#
# Usage:
#   merge_gate.sh export  <ws> <repo> <outfile>
#   merge_gate.sh disable <ws> <repo> [--branch NAME] [--export-to FILE]
#                                     [--branch-type LIST|none] [--dry-run]
#   merge_gate.sh enable  <ws> <repo> [--branch NAME] [--from-export FILE]
#
# Everything is one REST resource:
#   GET|POST        repositories/{ws}/{repo}/branch-restrictions
#   GET|PUT|DELETE  repositories/{ws}/{repo}/branch-restrictions/{id}
# A check is ON because an object exists and OFF because it does not. There is no
# falsey PUT: PUT only changes `value` on the four kinds that carry an integer.
#
# Transport is scripts/bb.sh, which owns auth and curl. Set BB_CMD to point at
# something else (the test suite points it at a fixture stub, so no credentials
# and no network are involved). Auth is deliberately NOT re-checked here - bb.sh
# already does it.
#
# Requires: jq. Needs the `repository:admin` scope for reads as well as writes;
# there is no read-only scope for branch restrictions.
set -uo pipefail

API_BASE="https://api.bitbucket.org/2.0"
HERE="$(cd "$(dirname "$0")" && pwd)"
BB="${BB_CMD:-$HERE/bb.sh}"

# Exit codes: 1 API/IO failure, 2 usage, 3 scope undetermined (nothing deleted),
# 4 one or more writes failed.
E_FAIL=1
E_USAGE=2
E_UNDETERMINED=3
E_WRITE=4

# The kinds this script treats as the merge gate. `push`, `force` and `delete`
# are branch write protection, not merge checks, and are deliberately excluded:
# `disable` must not quietly open a protected branch to direct pushes.
KINDS_MERGE_GATE="
restrict_merges
require_tasks_to_be_completed
require_approvals_to_merge
require_default_reviewer_approvals_to_merge
require_no_changes_requested
require_passing_builds_to_merge
require_commits_behind
reset_pullrequest_approvals_on_change
smart_reset_pullrequest_approvals
reset_pullrequest_changes_requested_on_change
require_all_dependencies_merged
enforce_merge_checks
allow_auto_merge_when_builds_pass
"
KINDS_WRITE_PROTECTION="push force delete"
# Atlassian documents these three as Premium-only. The script does not rely on
# this list to decide anything - it reports what the API answered - but names
# them when a write comes back as a plan limitation.
KINDS_PREMIUM_ONLY="reset_pullrequest_approvals_on_change smart_reset_pullrequest_approvals enforce_merge_checks"
# Kinds whose object carries an integer `value`. All others are presence-only.
KINDS_WITH_VALUE="require_approvals_to_merge require_default_reviewer_approvals_to_merge require_passing_builds_to_merge require_commits_behind"

# The preset `enable` applies when no --from-export is given. Everything not
# listed here is left absent, which is how a check is OFF.
PRESET='[
  {"kind":"require_approvals_to_merge","value":1},
  {"kind":"require_tasks_to_be_completed"},
  {"kind":"require_passing_builds_to_merge","value":1},
  {"kind":"enforce_merge_checks"}
]'

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
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

# ---------------------------------------------------------------- transport --

BB_STATUS=""
BB_BODY=""
BB_ERR=""

bb_call() { # METHOD path [json-body] -> BB_STATUS, BB_BODY, BB_ERR; rc 0 on 2xx
  local method="$1" path="$2" body="${3:-}" rc=0
  local err="$WORK/bb.err"
  : > "$err"
  # Assignment and status are split on purpose: `local x=$(...)` returns local's
  # status, not the command's, and would swallow every failure here.
  if [ -n "$body" ]; then
    BB_BODY="$("$BB" "$method" "$path" "$body" 2>"$err")" || rc=$?
  else
    BB_BODY="$("$BB" "$method" "$path" 2>"$err")" || rc=$?
  fi
  BB_ERR="$(cat "$err")"
  # bb.sh writes `HTTP <code>` plus free-text hints to stderr; anchor the parse.
  BB_STATUS="$(sed -n 's/^HTTP \([0-9][0-9]*\).*/\1/p' "$err" | tail -n 1)"
  if [ -z "$BB_STATUS" ]; then
    if [ "$rc" -eq 0 ]; then BB_STATUS="200"; else BB_STATUS="unknown"; fi
  fi
  return "$rc"
}

api_error_text() { # one-line, verbatim-as-possible account of the last failure
  local msg
  msg="$(printf '%s' "$BB_BODY" | jq -r '.error.message // empty' 2>/dev/null)"
  local detail
  detail="$(printf '%s' "$BB_BODY" | jq -r '.error.detail // empty' 2>/dev/null)"
  [ -n "$detail" ] && msg="$msg | $detail"
  if [ -z "${msg// /}" ] || [ "$msg" = " | " ]; then
    msg="$(printf '%s' "$BB_BODY" | tr '\n' ' ' | cut -c1-300)"
  fi
  [ -n "${msg// /}" ] || msg="$(printf '%s' "$BB_ERR" | tr '\n' ' ')"
  printf 'HTTP %s: %s' "$BB_STATUS" "$msg"
}

plan_limited() { # $1 status, $2 body -> 0 when the API said "not on your plan"
  [ "$1" = "402" ] && return 0
  printf '%s' "$2" | grep -qiE \
    'premium|upgrade (your|to a)|not available (on|for|in) (your|this)|paid plan|plan does not (include|support)|requires an? [a-z]+ plan' \
    && return 0
  return 1
}

# ------------------------------------------------------------------- reads --

DECLARED_SIZE=""   # `size` from the first page: the total across all pages
HAD_NEXT=0

fetch_restrictions() { # <ws> <repo> -> $WORK/values.json (a JSON array)
  local ws="$1" repo="$2"
  local path="repositories/$ws/$repo/branch-restrictions?pagelen=100"
  local first=1 next
  : > "$WORK/pages.jsonl"
  HAD_NEXT=0
  while : ; do
    bb_call GET "$path" || die "GET $path failed - $(api_error_text)"
    printf '%s' "$BB_BODY" | jq -c '.' >> "$WORK/pages.jsonl" \
      || die "the response to GET $path is not JSON."
    if [ "$first" -eq 1 ]; then
      DECLARED_SIZE="$(printf '%s' "$BB_BODY" | jq -r 'if has("size") then (.size|tostring) else "" end')"
      first=0
    fi
    next="$(printf '%s' "$BB_BODY" | jq -r '.next // empty')"
    [ -n "$next" ] || break
    case "$next" in
      "$API_BASE"/*) path="${next#"$API_BASE"/}" ;;
      *) die "pagination 'next' is not under $API_BASE: $next" ;;
    esac
    HAD_NEXT=1
  done
  jq -s '[.[] | .values[]?]' "$WORK/pages.jsonl" > "$WORK/values.json" \
    || die "could not assemble the paginated response."
}

expected_count() { # what the export must hold for it to be complete
  if [ -n "$DECLARED_SIZE" ]; then
    printf '%s' "$DECLARED_SIZE"
    return 0
  fi
  # No `size`. With no `next` either, the single page is the whole collection.
  # With a `next`, we have nothing to check a multi-page export against, and an
  # unverifiable export is a failed export.
  if [ "$HAD_NEXT" -eq 1 ]; then
    return 1
  fi
  jq 'length' "$WORK/values.json"
}

resolve_branch() { # <ws> <repo> -> the repo's main branch name
  bb_call GET "repositories/$1/$2" || die "GET repositories/$1/$2 failed - $(api_error_text)"
  local name
  name="$(printf '%s' "$BB_BODY" | jq -r '.mainbranch.name // empty')"
  [ -n "$name" ] || die "the repo has no .mainbranch.name - pass --branch explicitly."
  printf '%s' "$name"
}

# ------------------------------------------------------------------ export --

build_export_doc() { # the whole document, as text, before anything is opened
  jq -n \
    --arg ws "$WS" --arg repo "$REPO" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg size "${DECLARED_SIZE:-}" \
    --slurpfile v "$WORK/values.json" \
    '{tool: "merge_gate.sh", format: 1, exported_at: $ts,
      workspace: $ws, repository: $repo,
      endpoint: "branch-restrictions",
      note: "Unfiltered: every kind, both branch_match_kind schemes. Ids are recorded for reference only; a restore POSTs fresh objects.",
      api_size: (if $size == "" then null else ($size|tonumber) end),
      count: ($v[0] | length),
      values: $v[0]}'
}

write_validated_export() { # <destination> <expected count>
  local dest="$1" expected="$2" doc tmp actual
  # Compute the full text first. A write whose argument expression raises must
  # never have truncated the destination already.
  doc="$(build_export_doc)" || { echo "ERROR: could not build the export document - nothing written." >&2; return 1; }
  [ -n "$doc" ] || { echo "ERROR: the export document came out empty - nothing written." >&2; return 1; }
  tmp="$WORK/export.json"
  printf '%s\n' "$doc" > "$tmp" || { echo "ERROR: could not write the temporary export." >&2; return 1; }
  # Re-read what actually landed on disk, not what we think we wrote.
  jq -e . "$tmp" >/dev/null 2>&1 || { echo "ERROR: the export did not re-read as JSON." >&2; return 1; }
  actual="$(jq '.values | length' "$tmp")"
  if [ "$actual" != "$expected" ]; then
    echo "ERROR: the export holds $actual restriction(s) but the API reported $expected." >&2
    echo "       Refusing to continue: nothing was written and nothing was deleted." >&2
    return 1
  fi
  mv "$tmp" "$dest" || { echo "ERROR: could not move the export into place at $dest" >&2; return 1; }
  return 0
}

cmd_export() {
  [ "$#" -eq 3 ] || usage
  WS="$1"; REPO="$2"; local out="$3"
  fetch_restrictions "$WS" "$REPO"
  local expected
  expected="$(expected_count)" || die "the API paginated but reported no 'size', so the export cannot be verified complete."
  write_validated_export "$out" "$expected" || exit "$E_FAIL"
  printf 'export: %s restriction(s) from %s/%s written to %s\n' "$expected" "$WS" "$REPO" "$out"
  printf '        unfiltered - every kind, both glob and branching_model scopes.\n'
}

# ------------------------------------------------------- scope resolution --

COVER=""      # yes | no | undetermined
COVER_WHY=""

classify_scope() { # <branch_match_kind> <pattern> <branch_type> <branch>
  local bmk="$1" pattern="$2" btype="$3" branch="$4"
  if [ "$bmk" = "glob" ] || { [ -z "$bmk" ] && [ -n "$pattern" ]; }; then
    if [ -z "$pattern" ]; then
      COVER="undetermined"; COVER_WHY="glob scope with no pattern"
      return
    fi
    # Unquoted right-hand side on purpose: this is pattern matching, not a
    # string compare. Bash's `*` also crosses `/`, so the judgement is on the
    # permissive side - every object judged covering is printed before it goes.
    # shellcheck disable=SC2053
    if [[ $branch == $pattern ]]; then
      COVER="yes"; COVER_WHY="glob pattern '$pattern' matches '$branch'"
    else
      COVER="no"; COVER_WHY="glob pattern '$pattern' does not match '$branch'"
    fi
    return
  fi
  if [ "$bmk" = "branching_model" ]; then
    if [ -z "$BRANCH_TYPES_DECLARED" ]; then
      COVER="undetermined"
      COVER_WHY="branching_model scope (branch_type '$btype'): whether it governs '$branch' depends on this repo's branching model, which this script does not read - re-run with --branch-type"
      return
    fi
    if in_list "$btype" "$BRANCH_TYPES"; then
      COVER="yes"; COVER_WHY="branch_type '$btype' declared as covering '$branch' by --branch-type"
    else
      COVER="no"; COVER_WHY="branch_type '$btype' not listed in --branch-type"
    fi
    return
  fi
  COVER="undetermined"; COVER_WHY="unrecognised branch_match_kind '$bmk'"
}

scope_label() { # <branch_match_kind> <pattern> <branch_type>
  if [ "$1" = "branching_model" ]; then
    printf "branching_model:%s" "$3"
  else
    printf "glob:'%s'" "$2"
  fi
}

# ----------------------------------------------------------------- disable --

cmd_disable() {
  [ "$#" -ge 2 ] || usage
  WS="$1"; REPO="$2"; shift 2
  local branch="" export_to="" dry_run=0
  BRANCH_TYPES=""; BRANCH_TYPES_DECLARED=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --branch) branch="${2:?--branch needs a value}"; shift 2 ;;
      --export-to) export_to="${2:?--export-to needs a value}"; shift 2 ;;
      --branch-type)
        BRANCH_TYPES_DECLARED=1
        BRANCH_TYPES="$(printf '%s' "${2:?--branch-type needs a value}" | tr ',' ' ')"
        [ "$BRANCH_TYPES" = "none" ] && BRANCH_TYPES=""
        shift 2 ;;
      --dry-run) dry_run=1; shift ;;
      *) printf 'unknown option: %s\n' "$1" >&2; usage ;;
    esac
  done

  [ -n "$branch" ] || branch="$(resolve_branch "$WS" "$REPO")"
  [ -n "$export_to" ] || export_to="branch-restrictions-${WS}-${REPO}-$(date -u +%Y%m%dT%H%M%SZ).json"

  fetch_restrictions "$WS" "$REPO"
  local expected
  expected="$(expected_count)" || die "the API paginated but reported no 'size', so the export cannot be verified complete - nothing deleted."
  printf 'target branch: %s\n' "$branch"
  write_validated_export "$export_to" "$expected" || exit "$E_FAIL"
  printf 'backup: %s restriction(s) exported and re-verified at %s\n\n' "$expected" "$export_to"

  # Plan the whole thing before deleting anything.
  : > "$WORK/plan.delete"
  local undetermined=0 skipped=0 obj id kind pattern bmk btype
  printf 'plan:\n'
  while IFS= read -r obj; do
    [ -n "$obj" ] || continue
    id="$(printf '%s' "$obj" | jq -r '.id // empty')"
    kind="$(printf '%s' "$obj" | jq -r '.kind // empty')"
    pattern="$(printf '%s' "$obj" | jq -r '.pattern // empty')"
    bmk="$(printf '%s' "$obj" | jq -r '.branch_match_kind // empty')"
    btype="$(printf '%s' "$obj" | jq -r '.branch_type // empty')"
    local scope; scope="$(scope_label "$bmk" "$pattern" "$btype")"

    if in_list "$kind" "$KINDS_WRITE_PROTECTION"; then
      printf "  skip   id=%-8s %-46s %-28s kind '%s' is branch write protection, not a merge check\n" \
        "$id" "$kind" "$scope" "$kind"
      skipped=$((skipped + 1)); continue
    fi
    if ! in_list "$kind" "$KINDS_MERGE_GATE"; then
      printf "  skip   id=%-8s %-46s %-28s kind '%s' is not in this script's merge-gate list (the API's kind enum is not exhaustive) - left in place\n" \
        "$id" "$kind" "$scope" "$kind"
      skipped=$((skipped + 1)); continue
    fi

    classify_scope "$bmk" "$pattern" "$btype" "$branch"
    case "$COVER" in
      yes)
        printf "  delete id=%-8s %-46s %-28s %s\n" "$id" "$kind" "$scope" "$COVER_WHY"
        printf '%s\t%s\t%s\n' "$id" "$kind" "$scope" >> "$WORK/plan.delete" ;;
      no)
        printf "  skip   id=%-8s %-46s %-28s %s\n" "$id" "$kind" "$scope" "$COVER_WHY"
        skipped=$((skipped + 1)) ;;
      *)
        printf "  UNDETERMINED id=%-8s %-40s %-28s %s\n" "$id" "$kind" "$scope" "$COVER_WHY"
        undetermined=$((undetermined + 1)) ;;
    esac
  done < <(jq -c '.[]' "$WORK/values.json")

  local to_delete
  to_delete="$(jq -R -s 'split("\n") | map(select(length > 0)) | length' < "$WORK/plan.delete")"

  if [ "$undetermined" -gt 0 ]; then
    printf '\nERROR: %s restriction(s) above could not be resolved against branch %s.\n' "$undetermined" "$branch" >&2
    printf '       Nothing was deleted. Re-run with --branch-type listing the branch types\n' >&2
    printf '       that cover this branch in your branching model, or --branch-type none if\n' >&2
    printf '       none of them do. Your branching model is visible in repo Settings.\n' >&2
    printf '       The export at %s is complete and valid.\n' "$export_to" >&2
    exit "$E_UNDETERMINED"
  fi

  if [ "$dry_run" -eq 1 ]; then
    printf '\ndry run: would delete %s restriction(s), skip %s. Nothing was deleted.\n' "$to_delete" "$skipped"
    return 0
  fi

  printf '\n'
  local deleted=0 failed=0 line
  while IFS=$'\t' read -r id kind scope; do
    [ -n "$id" ] || continue
    if bb_call DELETE "repositories/$WS/$REPO/branch-restrictions/$id"; then
      printf '  deleted id=%-8s %-46s %s\n' "$id" "$kind" "$scope"
      deleted=$((deleted + 1))
    else
      printf '  FAILED  id=%-8s %-46s %s - %s\n' "$id" "$kind" "$scope" "$(api_error_text)" >&2
      failed=$((failed + 1))
    fi
  done < "$WORK/plan.delete"

  printf '\ndisable: removed %s branch restriction(s) of the merge-gate kinds this script\n' "$deleted"
  printf '         manages, covering branch %s in %s/%s. Skipped %s; failed %s.\n' "$branch" "$WS" "$REPO" "$skipped" "$failed"
  printf '         Restore with: %s enable %s %s --from-export %s\n' "$(basename "$0")" "$WS" "$REPO" "$export_to"
  [ "$failed" -eq 0 ] || exit "$E_WRITE"
}

# ------------------------------------------------------------------ enable --

find_existing() { # <desired obj> -> the matching live object, or empty
  jq -c --argjson d "$1" '
    map(select(
      .kind == $d.kind
      and ((.branch_match_kind // "glob") == (($d.branch_match_kind // "glob")))
      and (if (($d.branch_match_kind // "glob") == "branching_model")
           then (.branch_type // null) == ($d.branch_type // null)
           else (.pattern // null) == ($d.pattern // null) end)
    )) | .[0] // empty' "$WORK/values.json"
}

post_body() { # <desired obj> -> the POST payload, built from scratch, never an id
  printf '%s' "$1" | jq -c '
    {kind: .kind}
    + (if .value == null then {} else {value: .value} end)
    + (if (.branch_match_kind // "glob") == "branching_model"
       then {branch_match_kind: "branching_model", branch_type: .branch_type}
       else {branch_match_kind: "glob", pattern: .pattern} end)
    + (if .users == null then {} else {users: .users} end)
    + (if .groups == null then {} else {groups: .groups} end)'
}

cmd_enable() {
  [ "$#" -ge 2 ] || usage
  WS="$1"; REPO="$2"; shift 2
  local branch="" from_export=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --branch) branch="${2:?--branch needs a value}"; shift 2 ;;
      --from-export) from_export="${2:?--from-export needs a value}"; shift 2 ;;
      *) printf 'unknown option: %s\n' "$1" >&2; usage ;;
    esac
  done

  # Build the desired set.
  local desired="$WORK/desired.json"
  if [ -n "$from_export" ]; then
    [ -f "$from_export" ] || die "no such export file: $from_export"
    jq -e . "$from_export" >/dev/null 2>&1 || die "$from_export is not valid JSON."
    # A missing .values key is a malformed/foreign export, not an empty one. An
    # unknown must never collapse into the safe-looking "0 restored, rc 0".
    jq -e 'has("values")' "$from_export" >/dev/null 2>&1 \
      || die "$from_export has no top-level .values array - refusing to silently restore nothing."
    local exp_ws exp_repo
    exp_ws="$(jq -r '.workspace // empty' "$from_export")"
    exp_repo="$(jq -r '.repository // empty' "$from_export")"
    if [ -n "$exp_ws" ] && [ -n "$exp_repo" ] && { [ "$exp_ws" != "$WS" ] || [ "$exp_repo" != "$REPO" ]; }; then
      printf 'WARNING: %s was exported from %s/%s, not the target %s/%s - proceeding anyway.\n' \
        "$from_export" "$exp_ws" "$exp_repo" "$WS" "$REPO" >&2
    fi
    # Ids are not stable across delete/recreate, so they are dropped here rather
    # than trusted: a restore POSTs fresh objects. users/groups are carried
    # through as-is - they cannot be reconstructed from kind/scope alone.
    jq -c '[.values[] | {kind, value, branch_match_kind, pattern, branch_type, users, groups}]' \
      "$from_export" > "$desired" || die "could not read .values[] from $from_export"
    if [ -n "$branch" ]; then
      printf 'note: --branch is ignored with --from-export - each exported object carries its own scope.\n'
    fi
    printf 'restoring %s object(s) from %s\n\n' "$(jq 'length' "$desired")" "$from_export"
  else
    [ -n "$branch" ] || branch="$(resolve_branch "$WS" "$REPO")"
    printf '%s' "$PRESET" | jq -c --arg b "$branch" \
      '[.[] | {kind, value: (.value // null), branch_match_kind: "glob", pattern: $b, branch_type: null}]' \
      > "$desired" || die "could not build the preset."
    printf 'applying the preset to glob %s in %s/%s\n\n' "'$branch'" "$WS" "$REPO"
  fi

  # What is already there, so a re-run does not POST duplicates.
  fetch_restrictions "$WS" "$REPO"

  local applied=0 present=0 noplan=0 failed=0 obj kind value existing body
  while IFS= read -r obj; do
    [ -n "$obj" ] || continue
    kind="$(printf '%s' "$obj" | jq -r '.kind // empty')"
    value="$(printf '%s' "$obj" | jq -r 'if .value == null then "" else (.value|tostring) end')"
    local label scope bmk pat btype
    bmk="$(printf '%s' "$obj" | jq -r '.branch_match_kind // "glob"')"
    pat="$(printf '%s' "$obj" | jq -r '.pattern // empty')"
    btype="$(printf '%s' "$obj" | jq -r '.branch_type // empty')"
    scope="$(scope_label "$bmk" "$pat" "$btype")"
    label="$kind$([ -n "$value" ] && printf ' (value %s)' "$value") on $scope"

    if [ -z "$kind" ]; then
      printf '  %-28s %s\n' "failed" "an entry in the desired set has no kind" >&2
      failed=$((failed + 1)); continue
    fi
    # An incomplete desired object must not be matched against a live one or
    # POSTed as-is. A null pattern would match any other null-pattern object and
    # a null value would silently leave whatever integer is already set.
    if [ "$bmk" = "branching_model" ]; then
      if [ -z "$btype" ]; then
        printf '  %-28s %s - branching_model scope with no branch_type\n' "failed" "$label" >&2
        failed=$((failed + 1)); continue
      fi
    elif [ -z "$pat" ]; then
      printf '  %-28s %s - glob scope with no pattern\n' "failed" "$label" >&2
      failed=$((failed + 1)); continue
    fi
    if in_list "$kind" "$KINDS_WITH_VALUE" && [ -z "$value" ]; then
      printf '  %-28s %s - this kind carries an integer value and the desired set has none, so there is nothing to restore it to\n' \
        "failed" "$label" >&2
      failed=$((failed + 1)); continue
    fi

    existing="$(find_existing "$obj")"
    if [ -n "$existing" ]; then
      local live_value live_id
      live_id="$(printf '%s' "$existing" | jq -r '.id // empty')"
      live_value="$(printf '%s' "$existing" | jq -r 'if .value == null then "" else (.value|tostring) end')"
      if in_list "$kind" "$KINDS_WITH_VALUE" && [ -n "$value" ] && [ "$live_value" != "$value" ]; then
        # The one sanctioned use of PUT: change `value` on an existing object.
        if bb_call PUT "repositories/$WS/$REPO/branch-restrictions/$live_id" "{\"value\":$value}"; then
          printf '  %-28s %s (was %s)\n' "applied" "$label" "${live_value:-unset}"
          applied=$((applied + 1))
        elif plan_limited "$BB_STATUS" "$BB_BODY"; then
          printf '  %-28s %s - %s\n' "not-available-on-this-plan" "$label" "$(api_error_text)"
          noplan=$((noplan + 1))
        else
          printf '  %-28s %s - %s\n' "failed" "$label" "$(api_error_text)" >&2
          failed=$((failed + 1))
        fi
        continue
      fi
      printf '  %-28s %s\n' "already-present" "$label"
      present=$((present + 1))
      continue
    fi

    body="$(post_body "$obj")"
    if [ -z "$body" ]; then
      printf '  %-28s %s - could not build a POST body\n' "failed" "$label" >&2
      failed=$((failed + 1)); continue
    fi
    if bb_call POST "repositories/$WS/$REPO/branch-restrictions" "$body"; then
      printf '  %-28s %s\n' "applied" "$label"
      applied=$((applied + 1))
    elif plan_limited "$BB_STATUS" "$BB_BODY"; then
      printf '  %-28s %s - %s\n' "not-available-on-this-plan" "$label" "$(api_error_text)"
      noplan=$((noplan + 1))
    else
      printf '  %-28s %s - %s\n' "failed" "$label" "$(api_error_text)" >&2
      failed=$((failed + 1))
    fi
  done < <(jq -c '.[]' "$desired")

  printf '\nenable: applied %s, already-present %s, not-available-on-this-plan %s, failed %s\n' \
    "$applied" "$present" "$noplan" "$failed"
  if [ "$noplan" -gt 0 ]; then
    printf '        not-available-on-this-plan means the API refused the write as a plan\n'
    printf '        limitation, not that the setting is on. Premium-only kinds: %s\n' "$KINDS_PREMIUM_ONLY"
  fi
  if [ -z "$from_export" ]; then
    printf '        Preset only creates the four kinds listed in references/api.md; every\n'
    printf '        other check stays as it was. "No unresolved pull request comments" has\n'
    printf '        no API kind at all and cannot be set either way from here.\n'
  fi
  [ "$failed" -eq 0 ] || exit "$E_WRITE"
}

# -------------------------------------------------------------------- main --

WS=""; REPO=""
BRANCH_TYPES=""; BRANCH_TYPES_DECLARED=""

[ "$#" -ge 1 ] || usage
SUB="$1"; shift
case "$SUB" in
  export)  cmd_export "$@" ;;
  disable) cmd_disable "$@" ;;
  enable)  cmd_enable "$@" ;;
  -h|--help|help) usage ;;
  *) printf 'unknown subcommand: %s\n' "$SUB" >&2; usage ;;
esac
