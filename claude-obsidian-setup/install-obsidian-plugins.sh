#!/usr/bin/env bash
#
# Install the standard Obsidian community plugin set into a vault (Linux/WSL).
#
# Standards shared with the Windows script (install-obsidian-plugins.ps1):
#   * dry run by default; --apply writes
#   * every check reports PASS / FIX / FAIL with a stable check id
#   * idempotent - a plugin already at the requested version is PASS, not FIX
#   * exits non-zero if any check is still FAIL
#
# Additive. Config files are merged, never replaced, so a vault already in use
# keeps its own settings. community-plugins.json and core-plugins.json are
# unioned with what is already enabled.
#
# obsidian-local-rest-api is installed but its settings are never written: the
# plugin generates a per-machine API key on first load and overwriting it would
# break any MCP client already pointed at that vault.
#
# Usage:
#   ./install-obsidian-plugins.sh --vault ~/repos/Claude
#   ./install-obsidian-plugins.sh --vault ~/repos/Claude --apply
#   ./install-obsidian-plugins.sh --vault ~/repos/Claude --apply --only dataview,templater-obsidian
#
set -uo pipefail

VAULT=""
APPLY=0
LATEST=0
ONLY=""
PROFILE=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_URL="https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master/community-plugins.json"
REGISTRY_CACHE="${TMPDIR:-/tmp}/obsidian-community-plugins.json"

# Generates a per-machine API key on first load. Install it, never write its settings.
NO_SETTINGS="obsidian-local-rest-api"

FAILED=0
if [ -t 1 ]; then
  C_G=$'\033[32m'; C_Y=$'\033[33m'; C_R=$'\033[31m'; C_C=$'\033[1;36m'; C_0=$'\033[0m'
else
  C_G=''; C_Y=''; C_R=''; C_C=''; C_0=''
fi
pass() { printf "  %sPASS%s  %-28s %s\n" "$C_G" "$C_0" "$1" "$2"; }
fixx() { printf "  %sFIX%s   %-28s %s\n" "$C_Y" "$C_0" "$1" "$2"; }
faill(){ printf "  %sFAIL%s  %-28s %s\n" "$C_R" "$C_0" "$1" "$2"; FAILED=1; }
head_(){ printf "\n%s== %s%s\n" "$C_C" "$1" "$C_0"; }

usage() { sed -n '3,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --vault)   VAULT="$2"; shift 2 ;;
    --apply)   APPLY=1; shift ;;
    --latest)  LATEST=1; shift ;;
    --only)    ONLY="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) printf 'unknown option %s\n' "$1" >&2; exit 2 ;;
  esac
done

[ -n "$VAULT" ] || { printf 'fail --vault is required (see --help)\n' >&2; exit 2; }
[ -n "$PROFILE" ] || PROFILE="$SCRIPT_DIR/obsidian-plugin-profile.json"
command -v jq   >/dev/null 2>&1 || { printf 'fail jq required\n' >&2; exit 2; }
command -v curl >/dev/null 2>&1 || { printf 'fail curl required\n' >&2; exit 2; }

printf 'obsidian community plugins\n'
printf '  vault   : %s\n' "$VAULT"
printf '  profile : %s\n' "$PROFILE"
printf '  mode    : %s\n' "$([ "$APPLY" -eq 1 ] && echo APPLY || echo 'dry run (add --apply to write)')"

# --- 1. Inputs -------------------------------------------------------------
head_ "1. Inputs"
[ -f "$PROFILE" ] || { faill "profile" "not found: $PROFILE"; exit 1; }
N_COMM="$(jq '.communityPlugins | length' "$PROFILE")"
N_CORE="$(jq '.enabledCorePlugins | length' "$PROFILE")"
pass "profile" "$N_COMM community, $N_CORE core"

DOTOBS="$VAULT/.obsidian"
if [ -d "$DOTOBS" ]; then
  pass "vault" "$VAULT"
elif [ "$APPLY" -eq 1 ]; then
  mkdir -p "$DOTOBS" && fixx "vault" "created $DOTOBS"
else
  fixx "vault" "would create $DOTOBS"
fi
PLUGIN_ROOT="$DOTOBS/plugins"

# --- 2. Registry -----------------------------------------------------------
head_ "2. Plugin registry"
if [ ! -s "$REGISTRY_CACHE" ] || [ -z "$(find "$REGISTRY_CACHE" -mmin -60 2>/dev/null)" ]; then
  curl -fsSL "$REGISTRY_URL" -o "$REGISTRY_CACHE" \
    || { faill "registry" "could not fetch $REGISTRY_URL"; exit 1; }
fi
pass "registry" "$(jq 'length' "$REGISTRY_CACHE") plugins known"

repo_for() { jq -r --arg id "$1" '.[] | select(.id==$id) | .repo' "$REGISTRY_CACHE" | sed -n 1p; }

# --- 3. Plugins ------------------------------------------------------------
head_ "3. Community plugins"

get_release() {
  local want="$1" repo="$2" dest="$3" tag base
  local -a tags=()
  [ "$LATEST" -eq 0 ] && [ -n "$want" ] && tags+=("$want" "v$want")
  tags+=("__latest__")
  for tag in "${tags[@]}"; do
    if [ "$tag" = "__latest__" ]; then
      base="https://github.com/$repo/releases/latest/download"
    else
      base="https://github.com/$repo/releases/download/$tag"
    fi
    if curl -fsSL "$base/manifest.json" -o "$dest/manifest.json" 2>/dev/null \
       && curl -fsSL "$base/main.js" -o "$dest/main.js" 2>/dev/null; then
      curl -fsSL "$base/styles.css" -o "$dest/styles.css" 2>/dev/null || true
      [ "$tag" = "__latest__" ] && printf 'latest\n' || printf '%s\n' "$tag"
      return 0
    fi
  done
  return 1
}

ENABLED=""
while IFS=$'\t' read -r id version repo; do
  [ -n "$id" ] || continue
  if [ -n "$ONLY" ] && ! printf '%s' ",$ONLY," | grep -q ",$id,"; then continue; fi
  ENABLED="$ENABLED $id"

  dest="$PLUGIN_ROOT/$id"
  if [ -f "$dest/manifest.json" ] && [ "$LATEST" -eq 0 ]; then
    have="$(jq -r '.version // ""' "$dest/manifest.json" 2>/dev/null)"
    if [ "$have" = "$version" ]; then pass "$id" "$have"; continue; fi
  fi

  [ -n "$repo" ] && [ "$repo" != "null" ] || repo="$(repo_for "$id")"
  if [ -z "$repo" ] || [ "$repo" = "null" ]; then faill "$id" "not in the community registry"; continue; fi

  if [ "$APPLY" -eq 0 ]; then fixx "$id" "would install $version from $repo"; continue; fi

  # Download into a staging directory first. An existing install (upgrade case)
  # is only ever touched AFTER a full, validated download succeeds - a failed
  # or partial download (404, rate limit, network blip) must leave it untouched
  # rather than delete a working plugin.
  mkdir -p "$PLUGIN_ROOT"
  staging="$(mktemp -d "${TMPDIR:-/tmp}/obs-plugin-${id}-XXXXXX")"
  if tag="$(get_release "$version" "$repo" "$staging")" \
      && [ -f "$staging/manifest.json" ] && [ -f "$staging/main.js" ]; then
    rm -rf "$dest"
    mv "$staging" "$dest"
    got="$(jq -r '.version // "?"' "$dest/manifest.json")"
    if [ "$tag" = "latest" ] && [ "$got" != "$version" ]; then
      fixx "$id" "$got (pinned $version unavailable)"
    else
      fixx "$id" "installed $got"
    fi
  else
    rm -rf "$staging"
    faill "$id" "no downloadable release from $repo - existing install left untouched"
  fi
  # tr -d '\r': jq built for Windows writes CRLF, which would otherwise leave a
  # carriage return on the last field and silently corrupt every URL built from
  # it. Harmless on Linux, essential under Git Bash / MSYS.
done < <(jq -r '.communityPlugins[] | [.id, (.version // ""), (.repo // "")] | @tsv' "$PROFILE" | tr -d '\r')

# --- 4. Enable -------------------------------------------------------------
head_ "4. Enabling plugins"

merge_array() {
  # Deliberately no process substitution: <(...) resolves to /proc/<pid>/fd/N,
  # which jq cannot open under MSYS/Git Bash. Everything goes through --argjson.
  local path="$1" id="$2"; shift 2
  local want existing merged n tmp

  if [ "$#" -eq 0 ]; then
    want='[]'
  else
    want="$(printf '%s\n' "$@" | jq -R . | jq -s 'map(select(length > 0))')"
  fi

  existing='[]'
  if [ -f "$path" ] && jq -e 'type == "array"' "$path" >/dev/null 2>&1; then
    existing="$(cat "$path")"
  fi

  merged="$(printf '%s' "$existing" | jq --argjson w "$want" '. + $w | unique')"
  n="$(printf '%s' "$merged" | jq 'length')"

  if [ "$(printf '%s' "$existing" | jq -S 'unique')" = "$(printf '%s' "$merged" | jq -S '.')" ]; then
    pass "$id" "$n already enabled"
    return
  fi
  if [ "$APPLY" -eq 0 ]; then
    fixx "$id" "would enable $n"
    return
  fi
  tmp="$(mktemp)"
  printf '%s\n' "$merged" > "$tmp" && mv "$tmp" "$path" \
    && fixx "$id" "enabled $n" \
    || faill "$id" "could not write $path"
}

# shellcheck disable=SC2086
merge_array "$DOTOBS/community-plugins.json" "community-plugins" $ENABLED

CORE="$DOTOBS/core-plugins.json"
mapfile -t WANT_CORE < <(jq -r '.enabledCorePlugins[]' "$PROFILE")
if [ -f "$CORE" ] && ! jq -e 'type == "array"' "$CORE" >/dev/null 2>&1; then
  # Newer vaults store core plugins as an object map rather than a list.
  add="$(jq -n --slurpfile cur "$CORE" --slurpfile prof "$PROFILE" \
        '[$prof[0].enabledCorePlugins[] | select(($cur[0][.] // false) != true)] | length')"
  if [ "$add" -eq 0 ]; then
    pass "core-plugins" "$N_CORE already enabled"
  elif [ "$APPLY" -eq 0 ]; then
    fixx "core-plugins" "would enable $add more"
  else
    tmp="$(mktemp)"
    jq --slurpfile prof "$PROFILE" \
       'reduce $prof[0].enabledCorePlugins[] as $k (.; .[$k] = true)' "$CORE" > "$tmp" \
      && mv "$tmp" "$CORE" && fixx "core-plugins" "enabled $add more" \
      || faill "core-plugins" "could not update $CORE"
  fi
else
  merge_array "$CORE" "core-plugins" "${WANT_CORE[@]}"
fi

for id in $NO_SETTINGS; do
  case " $ENABLED " in
    *" $id "*) pass "$id-settings" "not written (per-machine API key)" ;;
  esac
done

# --- 5. Summary ------------------------------------------------------------
head_ "5. Result"
if [ "$FAILED" -ne 0 ]; then
  printf '  %sone or more checks FAILED%s\n' "$C_R" "$C_0"
  exit 1
fi
if [ "$APPLY" -eq 0 ]; then
  printf '  %sdry run only - re-run with --apply to write%s\n' "$C_Y" "$C_0"
else
  printf '  %sdone. Reload Obsidian (Ctrl+P -> "Reload app without saving"),%s\n' "$C_G" "$C_0"
  printf '  %sthen Settings -> Community plugins to confirm Restricted Mode is off.%s\n' "$C_G" "$C_0"
fi
exit 0
