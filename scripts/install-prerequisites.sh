#!/usr/bin/env bash
# Bootstraps a Linux machine for this repo's skills: git/nodejs/npm/python, the Claude
# Code CLI itself (with its path exported for future shells), and the team's standard
# Claude Code plugin marketplaces. Idempotent - safe to re-run.
#
# Everything is chosen from a menu up front, then installed unattended. The menu replaced
# a linear run of ~15 yes/no prompts, which meant you had to sit through the whole script
# to decline three things near the end. Every interactive answer (menu selection, API
# keys, the SkillUI quick start) is collected before the first install starts.
#
# The menu is a cursor picker: Up/Down to move, Space to toggle, Enter to start. On the
# repo's own row, Right opens a second picker for the individual skills, so you can take
# three of them instead of all twenty-five. Terminals that cannot do raw input - no stty, a
# dumb TERM, a window under ten lines - get the original numbered prompt instead, and
# every non-interactive path (--all, --select, --skills, --non-interactive) bypasses both.
#
# Everything is also detected before it is installed:
#   * OS packages         - only the ones whose command is actually missing get installed
#   * Marketplaces        - skipped when already registered (matched by name or repo)
#   * Plugins             - skipped when already installed; optionally updated
#
# Marketplaces and plugins are installed with the native 'claude plugin marketplace add'
# and 'claude plugin install' commands - no 'npx claudepluginhub' wrapper. The wrapper
# synthesized a local directory-backed marketplace per repo, producing marketplace names
# ('cpd-<repo>-user') that this script's detection could not match, so already-installed
# plugins were reinstalled on every run.
#
# Usage: ./scripts/install-prerequisites.sh [options]
#   --all                 select every menu item, no prompt
#   --select 1,3,7-9      select these menu items, no prompt (keys work too:
#                         --select strix,obsidian)
#   --skills a,b,c        install only these of this repo's skills, no prompt
#                         (--skills all | none also work; implies the repo item)
#   --team a,b            likewise for the team plugins (item 4)
#   --community a,b       likewise for the community plugins (item 6)
#   --plugins a,b         likewise for this repo's own plugins (item 19)
#                         every one of these accepts names, numbers, 'all' or 'none',
#                         and selecting any of them implies its parent menu item
#   --non-interactive     select the default set, no prompt (CI/unattended)
#   --skillui-guide       print the SkillUI quick start after installing it, no prompt
#   --notify-setup        scaffold the notify config after installing it, no prompt
#   --no-update           never update an already-installed plugin, only report it
#   --force-refresh       reinstall a plugin whose files changed in its marketplace
#                         but whose declared version did not (see 'content drift')
#   --dry-run             work out and print the selection, then stop without
#                         installing anything
#   --skip-bootstrap      narrow the selection to prerequisites + the Claude Code CLI
#   --scope <scope>       scope for marketplace/plugin installs: user|project|local (default: user)
#   --obsidian-repo-root <dir>
#   --obsidian-mcp-url <url>   vault-server MCP endpoint (default http://127.0.0.1:27123/mcp/)
#   --obsidian-mcp-key <key>   Local REST API key; without it the item explains and skips
#                         root the Obsidian item suggests for the vault (default: ~/repos)

set -uo pipefail

# Under the documented one-liner - 'curl -fsSL ... | bash' - the script itself arrives
# on stdin, so a bare 'read' consumes the next line of the script instead of the user's
# answer: the menu silently "answered" itself with 'show_selection'.
#
# The terminal therefore gets its own descriptor (fd 3) and every prompt reads from
# that, never from fd 0. Redirecting fd 0 instead would be worse than the bug: on the
# piped path bash is still reading the script from fd 0 and cannot seek backwards, so
# replacing it makes bash read the rest of the script off the terminal.
#
# With no terminal at all (CI, a container, nohup) the prompts cannot work, so fall
# back to the default selection rather than reading garbage.
TTY_FD=""
if [ -t 0 ]; then
  TTY_FD=0
elif [ -r /dev/tty ] && { exec 3</dev/tty; } 2>/dev/null; then
  TTY_FD=3
fi
NO_TTY=0
[ -z "$TTY_FD" ] && NO_TTY=1

SKIP_BOOTSTRAP=0
NON_INTERACTIVE=0
NO_UPDATE=0
FORCE_REFRESH=0
# Set once the selection came from the menu rather than a flag.
SELECTION_INTERACTIVE=0
# --dry-run: settle the selection, print it, install nothing.
DRY_RUN=0
SELECT_ALL=0
SELECT_SPEC=""
# One "--<group> a,b,c" spec per sub-picker group; empty means "not given".
GROUP_SPEC_SKILL=""
GROUP_SPEC_TEAM=""
GROUP_SPEC_COMMUNITY=""
GROUP_SPEC_PLUGIN=""
SKILLUI_GUIDE=""       # "1"/"0" once answered; empty means "ask"
NOTIFY_SETUP=""        # "1"/"0" once answered; empty means "ask"
INSTALL_SCOPE="user"   # machine-wide by default, not per-project
# Root the Obsidian item suggests for the vault. ~/repos is the Linux
# counterpart of the Windows default C:\repos.
OBSIDIAN_REPO_ROOT="${HOME}/repos"

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-bootstrap)  SKIP_BOOTSTRAP=1 ;;
    --non-interactive) NON_INTERACTIVE=1 ;;
    --no-update)       NO_UPDATE=1 ;;
    --force-refresh)   FORCE_REFRESH=1 ;;
    --dry-run)         DRY_RUN=1 ;;
    --all)             SELECT_ALL=1 ;;
    --select)          SELECT_SPEC="${2:-}"; shift ;;
    --skills)          GROUP_SPEC_SKILL="${2:-}"; shift ;;
    --team)            GROUP_SPEC_TEAM="${2:-}"; shift ;;
    --community)       GROUP_SPEC_COMMUNITY="${2:-}"; shift ;;
    --plugins)         GROUP_SPEC_PLUGIN="${2:-}"; shift ;;
    --skillui-guide)   SKILLUI_GUIDE=1 ;;
    --notify-setup)    NOTIFY_SETUP=1 ;;
    --scope)           INSTALL_SCOPE="${2:-user}"; shift ;;
    --obsidian-repo-root) OBSIDIAN_REPO_ROOT="${2:-$HOME/repos}"; shift ;;
    --obsidian-mcp-url)   OBSIDIAN_MCP_URL="${2:-}"; shift ;;
    --obsidian-mcp-key)   OBSIDIAN_MCP_KEY="${2:-}"; shift ;;
    *) echo "Unknown option: $1" >&2 ;;
  esac
  shift
done

# No terminal to prompt on and no explicit selection: take the defaults rather than
# blocking forever or reading whatever happens to be on stdin.
if [ "$NO_TTY" -eq 1 ] && [ "$SELECT_ALL" -eq 0 ] && [ -z "$SELECT_SPEC" ]; then
  NON_INTERACTIVE=1
fi

FAILED_STEPS=()
COUNT_INSTALLED=0
COUNT_UPDATED=0
COUNT_SKIPPED=0

step()   { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok()     { printf '    \033[32mOK:\033[0m %s\n' "$1"; }
warn()   { printf '    \033[33mWARN:\033[0m %s\n' "$1"; }
skip()   { printf '    \033[90mSKIP:\033[0m %s\n' "$1"; COUNT_SKIPPED=$((COUNT_SKIPPED+1)); }

run_step() {
  local name="$1"; shift
  step "$name"
  if ! "$@"; then
    warn "$name failed"
    FAILED_STEPS+=("$name")
    return 1
  fi
  return 0
}

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    warn "Not root and no sudo available - cannot run: $*"
    return 1
  fi
}

have() { command -v "$1" >/dev/null 2>&1; }

# --- JSON helper -------------------------------------------------------------
# Prefer jq; fall back to python3 (which this script installs). Reads stdin.
json_query() {
  # Both back ends emit CRLF when they run under Git Bash / WSL interop on Windows,
  # which leaves a stray \r on the last tab-separated field. Every caller compares
  # that field exactly ('$enabled' = "1", '$repo' = "$id"), so strip it once here
  # rather than in each read loop.
  local expr="$1"
  if have jq; then
    jq -r "$expr" 2>/dev/null | sed 's/\r$//'
  elif have python3; then
    python3 -c "$2" 2>/dev/null | sed 's/\r$//'
  else
    return 1
  fi
}

claude_available() { have claude; }
claude_config_root() { printf '%s' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; }

# --- PATH persistence ---------------------------------------------------------
persist_path_entry() {
  # Append a PATH export to the login shells' rc files, once. Used for both the
  # npm global bin (claude) and the per-user bin dir (strix).
  local bin_dir="$1" rc
  local marker="# Added by useful-claude-add-ons/scripts/install-prerequisites.sh"
  local export_line="export PATH=\"${bin_dir}:\$PATH\""
  for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$rc" ] || [ "$rc" = "$HOME/.bashrc" ]; then
      touch "$rc"
      if ! grep -qF "$export_line" "$rc" 2>/dev/null; then
        {
          echo ""
          echo "$marker"
          echo "$export_line"
        } >> "$rc"
        ok "Added '$bin_dir' to PATH in $rc"
      else
        skip "'$bin_dir' already exported in $rc"
      fi
    fi
  done
}

# --- Detection: marketplaces --------------------------------------------------
MARKETPLACES_CACHE=""
load_marketplaces() {
  MARKETPLACES_CACHE=""
  claude_available || return 0
  local raw
  raw="$(claude plugin marketplace list --json 2>/dev/null)" || return 0
  [ -z "$raw" ] && return 0
  # Emit one "name<TAB>repo" line per marketplace.
  MARKETPLACES_CACHE="$(printf '%s' "$raw" | json_query \
    '.[] | "\(.name)\t\(.repo // "")"' \
    'import json,sys
for m in json.load(sys.stdin):
    print("%s\t%s" % (m.get("name",""), m.get("repo","") or ""))')"
}

marketplace_installed() {
  # Accepts a marketplace name ('claude-plugins-official') or the GitHub 'owner/repo'
  # it was added from - the JSON carries both, and callers have one or the other.
  local id="$1" tail="${1##*/}" name repo
  [ -z "$MARKETPLACES_CACHE" ] && return 1
  while IFS=$'\t' read -r name repo; do
    [ -z "$name" ] && continue
    [ "$name" = "$id" ] && return 0
    [ -n "$repo" ] && [ "$repo" = "$id" ] && return 0
    case "$id" in */*) [ "$name" = "$tail" ] && return 0 ;; esac
  done <<< "$MARKETPLACES_CACHE"
  return 1
}

# --- Detection: plugins -------------------------------------------------------
PLUGINS_CACHE=""
load_plugins() {
  PLUGINS_CACHE=""
  claude_available || return 0
  local raw
  raw="$(claude plugin list --json 2>/dev/null)" || return 0
  [ -z "$raw" ] && return 0
  # Emit one "name<TAB>version<TAB>enabled" line per plugin; ids are 'name@marketplace'.
  # 'enabled' is tracked because installing a plugin and having it actually load are
  # two different things: a plugin switched off in settings.json is installed, at the
  # right scope, and completely inert - none of its skills or hooks are visible.
  PLUGINS_CACHE="$(printf '%s' "$raw" | json_query \
    '.[] | "\(.id | split("@")[0])\t\(.version // "unknown")\t\(if .enabled then "1" else "0" end)"' \
    'import json,sys
for p in json.load(sys.stdin):
    pid = p.get("id") or ""
    if pid:
        print("%s\t%s\t%s" % (pid.split("@")[0], p.get("version") or "unknown",
                              "1" if p.get("enabled") else "0"))')"
}

plugin_version() {
  local want="$1" name ver enabled
  [ -z "$PLUGINS_CACHE" ] && return 1
  while IFS=$'\t' read -r name ver enabled; do
    [ "$name" = "$want" ] && { printf '%s' "$ver"; return 0; }
  done <<< "$PLUGINS_CACHE"
  return 1
}

plugin_enabled() {
  # True when *any* installed copy of the bare name is enabled. Two marketplaces can
  # publish the same plugin, and one live copy is all that is needed - this keeps the
  # enablement check from fighting a plugin already loaded from another marketplace.
  local want="$1" name ver enabled
  [ -z "$PLUGINS_CACHE" ] && return 1
  while IFS=$'\t' read -r name ver enabled; do
    [ "$name" = "$want" ] && [ "$enabled" = "1" ] && return 0
  done <<< "$PLUGINS_CACHE"
  return 1
}

# --- Detection: what a marketplace clone and an installed plugin were built from ---
# A re-run used to spend one 'claude plugin update' spawn per plugin: 25 of this repo's
# skills meant 25 CLI launches that each re-checked the same marketplace and found
# nothing to do. Claude Code already records, per installed plugin, the marketplace
# commit it was installed from, and add_marketplace has just re-cloned that marketplace.
# When the two SHAs match there is nothing to update and the spawn can be skipped
# outright. Everything below is a file read; any failure reports "cannot tell", which
# install_plugin treats as "ask the CLI" so the slow path is still there when needed.
INSTALLED_SHAS_CACHE=""
INSTALLED_SHAS_LOADED=0
load_installed_shas() {
  INSTALLED_SHAS_LOADED=1
  INSTALLED_SHAS_CACHE=""
  local f
  f="$(claude_config_root)/plugins/installed_plugins.json"
  [ -r "$f" ] || return 0
  # Emit one "name@marketplace<TAB>sha" line per installed copy.
  INSTALLED_SHAS_CACHE="$(json_query \
    '(.plugins // {}) | to_entries[] | .key as $k | (.value[]? | "\($k)\t\(.gitCommitSha // "")")' \
    'import json,sys
for k, entries in (json.load(sys.stdin).get("plugins") or {}).items():
    for e in entries or []:
        print("%s\t%s" % (k, e.get("gitCommitSha") or ""))' < "$f")" || INSTALLED_SHAS_CACHE=""
  return 0
}

installed_plugin_sha() {
  local want="$1" id sha
  [ "$INSTALLED_SHAS_LOADED" -eq 1 ] || load_installed_shas
  [ -z "$INSTALLED_SHAS_CACHE" ] && return 1
  while IFS=$'\t' read -r id sha; do
    [ "$id" = "$want" ] && [ -n "$sha" ] && { printf '%s' "$sha"; return 0; }
  done <<< "$INSTALLED_SHAS_CACHE"
  return 1
}

# Where a marketplace's checkout actually lives. Usually
# '<config>/plugins/marketplaces/<name>', but a marketplace added from a local path is
# used in place and Claude Code records that in known_marketplaces.json, so read the
# recorded location and only fall back to the conventional one.
MARKETPLACE_DIR_CACHE=""
MARKETPLACE_DIR_LOADED=0
load_marketplace_dirs() {
  MARKETPLACE_DIR_LOADED=1
  MARKETPLACE_DIR_CACHE=""
  local f
  f="$(claude_config_root)/plugins/known_marketplaces.json"
  [ -r "$f" ] || return 0
  MARKETPLACE_DIR_CACHE="$(json_query \
    'to_entries[] | "\(.key)\t\(.value.installLocation // "")"' \
    'import json,sys
for k, v in (json.load(sys.stdin) or {}).items():
    print("%s\t%s" % (k, (v or {}).get("installLocation") or ""))' < "$f")" || MARKETPLACE_DIR_CACHE=""
  return 0
}

marketplace_dir() {
  local mkt="$1" key val
  [ "$MARKETPLACE_DIR_LOADED" -eq 1 ] || load_marketplace_dirs
  if [ -n "$MARKETPLACE_DIR_CACHE" ]; then
    while IFS=$'\t' read -r key val; do
      [ "$key" = "$mkt" ] && [ -n "$val" ] && { printf '%s' "$val"; return 0; }
    done <<< "$MARKETPLACE_DIR_CACHE"
  fi
  printf '%s/plugins/marketplaces/%s' "$(claude_config_root)" "$mkt"
}

# Cached per marketplace - all 25 of this repo's skills share one - and stored as a
# newline/tab string rather than an associative array so this still runs on bash 3.2.
# A marketplace whose SHA cannot be read is remembered as "-" so it is not re-probed.
MARKETPLACE_SHA_CACHE=""
marketplace_head_sha() {
  local mkt="$1" key val dir sha
  [ -z "$mkt" ] && return 1
  if [ -n "$MARKETPLACE_SHA_CACHE" ]; then
    while IFS=$'\t' read -r key val; do
      if [ "$key" = "$mkt" ]; then
        [ "$val" = "-" ] && return 1
        printf '%s' "$val"; return 0
      fi
    done <<< "$MARKETPLACE_SHA_CACHE"
  fi
  sha=""
  dir="$(marketplace_dir "$mkt")"
  if have git && [ -d "$dir/.git" ]; then
    sha="$(git -C "$dir" rev-parse HEAD 2>/dev/null)" || sha=""
  fi
  MARKETPLACE_SHA_CACHE="${MARKETPLACE_SHA_CACHE}${MARKETPLACE_SHA_CACHE:+$'\n'}${mkt}"$'\t'"${sha:--}"
  [ -z "$sha" ] && return 1
  printf '%s' "$sha"
}

force_refresh_plugin() {
  # The only way to make Claude Code re-copy a plugin whose files changed upstream but
  # whose declared version did not: uninstall and install again. '--keep-data' leaves
  # the plugin's persistent data directory alone, so this costs the user nothing beyond
  # the two CLI calls. Only ever reached with --force-refresh.
  local spec="$1"
  claude plugin uninstall "$spec" --keep-data --scope "$INSTALL_SCOPE" >/dev/null 2>&1 \
    || { warn "could not uninstall '$spec' to force a refresh - leaving the stale copy in place."; return 1; }
  # The install is deliberately NOT redirected, exactly as install_plugin runs it: the
  # CLI refuses a plugin whose marketplace declares an install command when stdout is
  # not a TTY, so swallowing the output here could fail the reinstall of a plugin this
  # function has already uninstalled.
  claude plugin install "$spec" --scope "$INSTALL_SCOPE" \
    || { warn "'$spec' was uninstalled but reinstalling it failed - run 'claude plugin install $spec' by hand."; return 1; }
  return 0
}

# name -> declared version and source path, read once per marketplace from the clone's
# own marketplace.json. The version fills the in-memory plugin cache after an install
# without paying for another 'claude plugin list --json'; the source path is what the
# drift check diffs.
MARKETPLACE_CATALOG_CACHE=""
load_marketplace_catalog() {
  # Lines are "marketplace<TAB>name<TAB>version<TAB>source". The marketplace column is
  # prefixed here rather than inside the jq/python expression so a marketplace name is
  # never interpolated into either program. Idempotent per marketplace.
  local mkt="$1" f rows
  [ -z "$mkt" ] && return 1
  case "$MARKETPLACE_CATALOG_CACHE" in
    "$mkt"$'\t'*|*$'\n'"$mkt"$'\t'*) return 0 ;;
  esac
  f="$(marketplace_dir "$mkt")/.claude-plugin/marketplace.json"
  rows=""
  if [ -r "$f" ]; then
    # 'source' is only useful when it is a path inside the clone; a marketplace entry
    # may instead carry an object (a git URL elsewhere), which is left empty so the
    # drift check reports "cannot tell" rather than diffing a path that is not there.
    rows="$(json_query \
      '(.plugins // [])[] | "\(.name)\t\(.version // "unknown")\t\(if (.source|type) == "string" then (.source | sub("^\\./";"")) else "" end)"' \
      'import json,sys
for p in (json.load(sys.stdin).get("plugins") or []):
    src = p.get("source")
    src = src[2:] if isinstance(src, str) and src.startswith("./") else (src if isinstance(src, str) else "")
    print("%s\t%s\t%s" % (p.get("name") or "", p.get("version") or "unknown", src))' < "$f" \
      | sed "s|^|${mkt}\t|")" || rows=""
  fi
  # The bare marker line goes in either way, so an unreadable or empty marketplace is
  # not re-parsed once per plugin.
  MARKETPLACE_CATALOG_CACHE="${MARKETPLACE_CATALOG_CACHE}${MARKETPLACE_CATALOG_CACHE:+$'\n'}${mkt}"$'\t\t\t'"${rows:+$'\n'}${rows}"
  return 0
}

marketplace_catalog_field() {
  # $1 marketplace, $2 plugin name, $3 field number (3 = version, 4 = source).
  local mkt="$1" want="$2" field="$3" mk key ver src val
  load_marketplace_catalog "$mkt" || return 1
  while IFS=$'\t' read -r mk key ver src; do
    [ "$mk" = "$mkt" ] && [ "$key" = "$want" ] || continue
    case "$field" in 3) val="$ver" ;; 4) val="$src" ;; *) val="" ;; esac
    [ -n "$val" ] && { printf '%s' "$val"; return 0; }
  done <<< "$MARKETPLACE_CATALOG_CACHE"
  return 1
}

marketplace_plugin_version() { marketplace_catalog_field "$1" "$2" 3; }
marketplace_plugin_source()  { marketplace_catalog_field "$1" "$2" 4; }

ensure_marketplace_caches() {
  # Every reader below is called as "$(...)", which runs in a subshell: an assignment
  # to a cache variable in there is discarded the moment the substitution ends. So the
  # caches are filled by *bare* calls here, in this shell, before anything reads them.
  # Without this the caching is silently a no-op - correct, but paying for a git and a
  # jq per plugin instead of one per marketplace.
  local mkt="$1"
  [ "$INSTALLED_SHAS_LOADED" -eq 1 ] || load_installed_shas
  [ -z "$mkt" ] && return 0
  [ "$MARKETPLACE_DIR_LOADED" -eq 1 ] || load_marketplace_dirs
  marketplace_head_sha "$mkt" >/dev/null 2>&1 || true
  load_marketplace_catalog "$mkt" || true
  return 0
}

plugin_source_changed() {
  # Did this plugin's own files change between two marketplace commits? Any commit in
  # the marketplace moves HEAD, so without this an unrelated edit anywhere in the repo
  # would drag every plugin in it back onto the slow path.
  #   0 = the plugin's files differ between the two commits
  #   1 = they do not
  #   2 = cannot tell (no git, a shallow clone, or a commit a force-push pruned)
  local mkt="$1" old="$2" new="$3" src="$4" dir rc
  [ -n "$src" ] || return 2
  have git || return 2
  dir="$(marketplace_dir "$mkt")"
  [ -d "$dir/.git" ] || return 2
  git -C "$dir" cat-file -e "${old}^{commit}" 2>/dev/null || return 2
  git -C "$dir" cat-file -e "${new}^{commit}" 2>/dev/null || return 2
  # 'git diff --quiet -- <path>' also exits 0 when the pathspec matches nothing, which
  # is indistinguishable from "unchanged" - so a plugin whose declared source is not a
  # real path in the clone would read as current forever. Check the path is there first.
  git -C "$dir" cat-file -e "${new}:${src}" 2>/dev/null || return 2
  git -C "$dir" diff --quiet "$old" "$new" -- "$src" 2>/dev/null
  rc=$?
  case "$rc" in
    0) return 1 ;;
    1) return 0 ;;
    *) return 2 ;;
  esac
}

plugin_cache_add() {
  # Record a just-installed plugin in the in-memory cache instead of reloading the
  # whole list. 'claude plugin install' enables what it installs, so it is live - and
  # trusting that is more accurate than re-reading, since a freshly installed plugin
  # can still read as disabled in 'claude plugin list --json' (see ensure_plugin_enabled).
  local name="$1" ver="${2:-unknown}"
  PLUGINS_CACHE="${PLUGINS_CACHE}${PLUGINS_CACHE:+$'\n'}${name}"$'\t'"${ver}"$'\t1'
}

ensure_plugin_enabled() {
  # $1 is 'name@marketplace'. For a plugin that was ALREADY installed before this run:
  # one switched off in settings.json is installed, at the right scope, and completely
  # inert - none of its skills or hooks are visible.
  #
  # Deliberately NOT called after a fresh install. 'claude plugin install' enables what
  # it installs, and on a new machine the just-installed plugin can still read as
  # disabled in 'claude plugin list --json' - so calling it there tries to enable every
  # plugin in the run and reports a benign "already enabled" as a failure.
  #
  # Never fails the step: the plugin is installed either way. Tries the fully qualified
  # spec first because the bare name is ambiguous when two marketplaces publish it.
  #
  # Success is judged from 'claude plugin list --json', not from the CLI's message:
  # 'claude plugin enable' reports "is already enabled at user scope" even for a plugin
  # that does not exist, so the text cannot tell success from failure. The plugin list can.
  # 'name' is assigned on its own line, not inside the 'local': bash declares every name
  # in a 'local' before expanding the values, so "${spec%%@*}" there reads the empty new
  # local rather than $1 and silently makes this whole function a no-op.
  local spec="$1" name target
  name="${spec%%@*}"
  plugin_version "$name" >/dev/null || return 0   # not installed - nothing to enable
  plugin_enabled "$name" && return 0              # already live
  for target in "$spec" "$name"; do
    claude plugin enable "$target" --scope "$INSTALL_SCOPE" >/dev/null 2>&1
    load_plugins
    if plugin_enabled "$name"; then
      ok "plugin '$name' is enabled (--scope $INSTALL_SCOPE)"
      return 0
    fi
  done
  warn "plugin '$name' may be installed but disabled - run '/plugin' and enable it by hand."
  return 0
}

# --- Detection: MCP servers ---------------------------------------------------
MCP_CACHE=""
load_mcp_servers() {
  # 'claude mcp list' prints one 'name: command args' line per server. There is no
  # --json flag for it, so the name is taken off the front of each line.
  MCP_CACHE=""
  claude_available || return 0
  MCP_CACHE="$(claude mcp list 2>/dev/null | sed -n 's/^[[:space:]]*\([A-Za-z0-9_.-][A-Za-z0-9_.-]*\)[[:space:]]*:.*/\1/p')"
  return 0
}

mcp_server_registered() {
  local want="$1" name
  [ -z "$MCP_CACHE" ] && return 1
  while read -r name; do
    [ "$name" = "$want" ] && return 0
  done <<< "$MCP_CACHE"
  return 1
}

add_mcp_server() {
  # add_mcp_server <name> <env-spec> <command...>
  # <env-spec> is "KEY=value" or "-" for none. Detect-then-act, same contract as
  # add_marketplace. The command goes after '--' so claude does not parse it.
  local name="$1" env_spec="$2"; shift 2
  if ! have claude; then
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' and re-run this script."
    return 1
  fi
  if mcp_server_registered "$name"; then
    skip "MCP server '$name' already registered"
    return 0
  fi
  if [ "$env_spec" = "-" ]; then
    claude mcp add --scope "$INSTALL_SCOPE" "$name" -- "$@" || return 1
  else
    claude mcp add --scope "$INSTALL_SCOPE" "$name" --env "$env_spec" -- "$@" || return 1
  fi
  load_mcp_servers
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "added MCP server '$name'"
}

add_mcp_http_server() {
  # add_mcp_http_server <name> <url> [<header> ...]
  # For a server that is ALREADY listening over HTTP: there is no command to
  # launch, claude takes the endpoint as a positional argument, and each header
  # is passed whole ("Authorization: Bearer x"). Same detect-then-act contract.
  local name="$1" url="$2"; shift 2
  if ! have claude; then
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' and re-run this script."
    return 1
  fi
  if mcp_server_registered "$name"; then
    skip "MCP server '$name' already registered"
    return 0
  fi
  local -a args=(mcp add --scope "$INSTALL_SCOPE" --transport http "$name" "$url")
  local h
  for h in "$@"; do args+=(--header "$h"); done
  claude "${args[@]}" || return 1
  load_mcp_servers
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "added MCP server '$name'"
}

# --- Detection: user-level skills --------------------------------------------
# Some things (the 'skills' CLI, task-observer) install as plain user-level skills
# rather than as Claude Code plugins, so they never appear in 'claude plugin list' -
# detection for those is a filesystem check against the user-level skills directory.
claude_skills_dir() { printf '%s/skills' "$(claude_config_root)"; }
user_skill_installed() { [ -f "$(claude_skills_dir)/$1/SKILL.md" ]; }

# --- Install wrappers (detect, then act) -------------------------------------
add_marketplace() {
  local source="$1" name="${2:-}" probe
  probe="${name:-$source}"
  if marketplace_installed "$probe"; then
    skip "marketplace '$probe' already registered"
    if [ "$NO_UPDATE" -eq 0 ] && [ -n "$name" ]; then
      claude plugin marketplace update "$name" >/dev/null 2>&1 \
        && ok "refreshed marketplace metadata for '$name'"
    fi
    return 0
  fi
  claude plugin marketplace add "$source" --scope "$INSTALL_SCOPE" || return 1
  load_marketplaces
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "added marketplace '$source'"
}

install_plugin() {
  # $1 is 'name@marketplace'. Detection is on the bare name, so a plugin already
  # installed from a *different* marketplace counts as present and is not duplicated.
  local spec="$1" name mkt before after target head_sha old_sha drift
  name="${spec%%@*}"
  case "$spec" in *@*) mkt="${spec#*@}" ;; *) mkt="" ;; esac
  # Warmed here, before either branch: every reader below runs inside "$(...)", and an
  # assignment in a subshell is discarded. Both paths need the marketplace catalog.
  ensure_marketplace_caches "$mkt"
  if before="$(plugin_version "$name")"; then
    if [ "$NO_UPDATE" -eq 1 ]; then
      skip "plugin '$name' already installed (version $before)"
      ensure_plugin_enabled "$spec"
      return 0
    fi
    # Claude Code records the marketplace commit each installed copy came from, and
    # add_marketplace has just re-cloned that marketplace. Comparing the two SHAs
    # answers "is there anything to update?" from two file reads instead of a CLI
    # launch - the whole reason a re-run of the 25-skill item finishes in seconds
    # rather than minutes. Anything unreadable leaves both empty, and the slow path
    # below runs exactly as it always did.
    head_sha=""; old_sha=""; drift=2
    if [ -n "$mkt" ]; then
      head_sha="$(marketplace_head_sha "$mkt")" || head_sha=""
      old_sha="$(installed_plugin_sha "$spec")" || old_sha=""
    fi
    if [ -n "$head_sha" ] && [ -n "$old_sha" ]; then
      if [ "$head_sha" = "$old_sha" ]; then
        skip "plugin '$name' already current (version $before)"
        ensure_plugin_enabled "$spec"
        return 0
      fi
      # The marketplace has moved, but that says nothing about *this* plugin: one
      # commit anywhere in the repo moves HEAD for every plugin it publishes. Ask git
      # whether this plugin's own files changed before paying for the CLI.
      plugin_source_changed "$mkt" "$old_sha" "$head_sha" \
        "$(marketplace_plugin_source "$mkt" "$name" || printf '')"
      drift=$?
      if [ "$drift" -eq 1 ]; then
        skip "plugin '$name' already current (version $before)"
        ensure_plugin_enabled "$spec"
        return 0
      fi
    fi
    # The fully qualified 'name@marketplace' is what 'claude plugin update' wants: a
    # bare name is rejected with 'Plugin "<name>" not found', which made every update
    # in a re-run fail and print a warning that read like a real problem.
    target="${mkt:+$spec}"
    target="${target:-$name}"
    # A failed update is not fatal: the plugin is installed and usable, and
    # 'claude plugin update' legitimately fails when its marketplace has moved on.
    claude plugin update "$target" >/dev/null 2>&1     || warn "'claude plugin update $target' failed - keeping the installed version."
    load_plugins
    after="$(plugin_version "$name" || echo "$before")"
    if [ "$after" != "$before" ]; then
      COUNT_UPDATED=$((COUNT_UPDATED+1))
      ok "plugin '$name' updated $before -> $after"
      ensure_plugin_enabled "$spec"
      return 0
    fi
    # Content drift: this plugin's files changed upstream and the update did not take.
    # 'claude plugin update' decides by declared version, so a marketplace that edits a
    # plugin without bumping its version leaves every installed copy silently stale -
    # the CLI cheerfully reports "already at the latest version" and copies nothing.
    # Say so plainly rather than reporting it as current.
    if [ "$drift" -eq 0 ]; then
      load_installed_shas   # bare, not in $( ): see ensure_marketplace_caches
      if [ "$(installed_plugin_sha "$spec" || printf '')" = "$head_sha" ]; then
        COUNT_UPDATED=$((COUNT_UPDATED+1))
        ok "plugin '$name' refreshed (version $after, marketplace moved to ${head_sha:0:7})"
      elif [ "$FORCE_REFRESH" -eq 1 ]; then
        # force_refresh_plugin uninstalls before installing, so a failure here can leave
        # the plugin *gone*, not merely stale. It says which half failed; this fails the
        # step so the run does not end with "All steps completed".
        force_refresh_plugin "$spec" || return 1
        load_plugins
        load_installed_shas
        COUNT_UPDATED=$((COUNT_UPDATED+1))
        ok "plugin '$name' reinstalled to pick up changed files (version $after, unbumped)"
        return 0
      else
        warn "plugin '$name' changed in its marketplace but still declares version $after, so 'claude plugin update' copied nothing - the installed copy is stale. Ask the marketplace to bump the version, or re-run with --force-refresh to reinstall it."
      fi
    else
      skip "plugin '$name' already current (version $after)"
    fi
    ensure_plugin_enabled "$spec"
    return 0
  fi
  claude plugin install "$spec" --scope "$INSTALL_SCOPE" || return 1
  # Add the new plugin to the in-memory cache rather than reloading the whole list:
  # a fresh run installs 25+ plugins, and 'claude plugin list --json' after each one
  # was a second CLI spawn per plugin that nothing in this run reads differently.
  plugin_cache_add "$name" "$(marketplace_plugin_version "$mkt" "$name" || printf 'unknown')"
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "installed plugin '$spec'"
  # No ensure_plugin_enabled here: 'claude plugin install' already enabled it. See the
  # comment on that function for why calling it on this path breaks a fresh machine.
}

# --- Install catalog and menu -------------------------------------------------
# Three parallel indexed arrays rather than one associative array: bash hashes have
# no defined iteration order, and the menu numbers have to be stable between runs.
# MENU_DEFAULT is what [D] (and --non-interactive) picks, chosen to match the prompt
# defaults this script used before it had a menu.
MENU_KEYS=(
  "prereqs" "cli" "own-skills" "team" "find-skills" "community"
  "claude-code-setup" "task-observer"
  "aws-mcp" "azure-mcp" "playwright-mcp" "obsidian-mcp"
  "supabase" "context7" "playwright-cli" "skillui" "strix" "obsidian"
  "repo-plugins" "graphify" "ms-mcp"
)
MENU_DEFAULT=(1 1 1 1 1 1 1 1 0 0 0 0 0 0 0 0 0 0 0 0 0)
MENU_NAME=(
  "Prerequisites: git, nodejs, npm, python3, pip3 (needs root or sudo)"
  "Claude Code CLI (@anthropic-ai/claude-code) + PATH export + update check"
  "This repo's marketplace + its skills"
  "Team plugins: superpowers, frontend-design, excalidraw-generator"
  "find-skills skill (vercel-labs/skills)"
  "Community marketplaces + plugins (adhd-output-style, azure-tools, ppt-master, ...)"
  "claude-code-setup plugin (anthropics/claude-plugins-official)"
  "task-observer skill (rebelytics/one-skill-to-rule-them-all)"
  "MCP server: AWS (awslabs.aws-api-mcp-server)"
  "MCP server: Azure (@azure/mcp)"
  "MCP server: Playwright (@playwright/mcp)"
  "MCP server: Obsidian vault server (Local REST API over an SSH tunnel)"
  "Supabase plugin (supabase@claude-plugins-official)"
  "Context7 up-to-date library docs (npx ctx7 setup)"
  "Playwright CLI (@playwright/cli) - browser automation from the shell"
  "SkillUI (npm) + Playwright/Chromium - extract a design system from a URL"
  "Strix AI pentesting CLI (needs Docker + an LLM API key)"
  "Obsidian desktop + claude-obsidian + obsidian-skills plugins"
  "This repo's plugins: crew, obsidian-vault (agents, commands, hooks)"
  "graphify code graph (uv tool install graphifyy; per-repo, not global)"
  "Microsoft MCP servers (mcp-servers/): Graph, Intune, Office 365 user/admin - needs tenant credentials"
)

SELECTED=""
is_selected()     { case " $SELECTED " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
selection_add()   { is_selected "$1" || SELECTED="$SELECTED $1"; }
selection_drop()  { SELECTED=" $(printf '%s' " $SELECTED " | sed "s/ $1 / /g") "; }

default_keys() {
  local i out=""
  for i in "${!MENU_KEYS[@]}"; do
    [ "${MENU_DEFAULT[$i]}" -eq 1 ] && out="$out ${MENU_KEYS[$i]}"
  done
  printf '%s' "$out"
}

all_keys() { printf '%s' " ${MENU_KEYS[*]}"; }

expand_selection_spec() {
  # '1,3,7-9' -> the matching catalog keys. Item keys are accepted too, so
  # --select strix,obsidian works without counting rows in the menu.
  local spec="$1" token n lo hi i found out=""
  spec="${spec//,/ }"
  for token in $spec; do
    if [[ "$token" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      lo="${BASH_REMATCH[1]}"; hi="${BASH_REMATCH[2]}"
      for (( n=lo; n<=hi; n++ )); do
        if [ "$n" -ge 1 ] && [ "$n" -le "${#MENU_KEYS[@]}" ]; then
          out="$out ${MENU_KEYS[$((n-1))]}"
        fi
      done
    elif [[ "$token" =~ ^[0-9]+$ ]]; then
      n="$token"
      if [ "$n" -ge 1 ] && [ "$n" -le "${#MENU_KEYS[@]}" ]; then
        out="$out ${MENU_KEYS[$((n-1))]}"
      else
        # stderr, not stdout: this function's stdout is captured with $( ) as the
        # selection itself, so a warning printed there would vanish into SELECTED.
        warn "ignoring out-of-range menu number '$token'" >&2
      fi
    else
      found=0
      for i in "${!MENU_KEYS[@]}"; do
        if [ "${MENU_KEYS[$i]}" = "$token" ]; then out="$out $token"; found=1; break; fi
      done
      [ "$found" -eq 0 ] && warn "ignoring unknown menu item '$token'" >&2
    fi
  done
  printf '%s' "$out"
}

# --- This repo's individual skills --------------------------------------------
# Keep in sync with .claude-plugin/marketplace.json. Everything is on by default:
# picking a subset is the exception, and a fresh machine wants the lot.
SKILL_KEYS=(
  "aws-opensearch" "bitbucket" "checkpoint-email" "cisco-meraki"
  "claude-code-defaults" "claude-code-tuneup" "claude-memories-canvas"
  "claude-memories-vault" "cloudflare" "drata" "i-have-adhd"
  "infra-work-ticketing" "intune-graph" "mermaid-svg-bitbucket" "notify"
  "obsidian-canvas" "obsidian-vault-server"
  "repo-docs" "shipstation" "sophos-central" "terraform-docs-readme" "visio-diagrams"
  "wazuh-onprem" "web-testing-playwright" "work-log-reporter"
)
SKILL_NAME=(
  "aws-opensearch          - AWS OpenSearch: health, shards, reindex, ISM, snapshots"
  "bitbucket               - Bitbucket Cloud: git auth, PRs, pipelines, REST API"
  "checkpoint-email        - Check Point Email Security: phishing triage, quarantine"
  "cisco-meraki            - Meraki Dashboard API: inventory, events, config changes"
  "claude-code-defaults    - Claude Code config: settings.json, permissions, hooks"
  "claude-code-tuneup      - Audit a slow Claude Code setup: dupes, hooks, context"
  "claude-memories-canvas  - claude-memories vault: wiki/maps .canvas conventions"
  "claude-memories-vault   - claude-memories vault: layout, frontmatter, write lock"
  "cloudflare              - Cloudflare v4: DNS, WAF, cache, Workers, Zero Trust"
  "drata                   - Drata: controls, monitors, evidence, audit prep"
  "i-have-adhd             - ADHD-friendly output: next action first, numbered steps"
  "infra-work-ticketing    - ServiceDesk Plus / Jira: open tickets, log work notes"
  "intune-graph            - Intune via Graph: devices, compliance, app deployment"
  "mermaid-svg-bitbucket   - Pre-render Mermaid to SVG so Bitbucket displays it"
  "notify                  - Ping your phone or inbox: Telegram bot (two-way) or email"
  "obsidian-canvas         - Obsidian .canvas files as JSON: maps, boards, diagrams"
  "obsidian-vault-server   - Self-hosted Obsidian on Ubuntu: Sync, REST/MCP endpoint"
  "repo-docs               - Whole doc set: CLAUDE.md, READMEs, architecture, handoff"
  "shipstation             - ShipStation V2/V1/ShipEngine: labels, rates, orders"
  "sophos-central          - Sophos Central: isolate endpoints, triage alerts, XDR"
  "terraform-docs-readme   - Regenerate a Terraform module README with terraform-docs"
  "visio-diagrams          - Native .vsdx diagrams from a spec, or via Visio COM"
  "wazuh-onprem            - Self-hosted Wazuh: server, indexer, dashboards, ossec.conf"
  "web-testing-playwright  - Real-browser testing: screenshots, console, form flows"
  "work-log-reporter       - Session work log + emailed PDF report over SMTP"
)
SKILL_SPEC=()
for _i in "${!SKILL_KEYS[@]}"; do
  SKILL_SPEC+=("${SKILL_KEYS[$_i]}@useful-claude-add-ons|mbadali25/useful-claude-add-ons|useful-claude-add-ons")
done
SKILL_STATE=()
for _i in "${!SKILL_KEYS[@]}"; do SKILL_STATE+=(1); done
unset _i

# --- This repo's own plugins --------------------------------------------------
# Keep in sync with .claude-plugin/marketplace.json and plugin/README.md. Unlike the
# skills, these are off by default and have no sub-picker: a plugin can register hooks,
# and a hook runs whether or not Claude agrees with it, so it is opted into explicitly.
# Parallel arrays for the same reason SKILL_KEYS uses them - stable order.
PLUGIN_KEYS=(
  "crew"
  "obsidian-vault"
)
PLUGIN_NAME=(
  "crew                    - Virtual dev team: 10 agents, 21 commands, safety hooks"
  "obsidian-vault          - Multi-vault memory: gardener/reflector agents, bridge+guard hooks"
)
PLUGIN_SPEC=(
  "crew@useful-claude-add-ons|mbadali25/useful-claude-add-ons|useful-claude-add-ons"
  "obsidian-vault@useful-claude-add-ons|mbadali25/useful-claude-add-ons|useful-claude-add-ons"
)
PLUGIN_STATE=()
for _i in "${!PLUGIN_KEYS[@]}"; do PLUGIN_STATE+=(1); done
unset _i

# --- Team plugins (menu item 4) -----------------------------------------------
# <PREFIX>_SPEC entries are "plugin@marketplace|marketplace-source|marketplace-name":
# unlike the skills, these come from three different marketplaces, and only the ones
# behind a ticked plugin need registering.
TEAM_KEYS=("superpowers" "frontend-design" "excalidraw-generator")
TEAM_NAME=(
  "superpowers             - Workflow skills: brainstorm, plans, TDD, code review"
  "frontend-design         - Anthropic's frontend design skill"
  "excalidraw-generator    - Excalidraw diagrams from a description"
)
TEAM_SPEC=(
  "superpowers@claude-plugins-official|anthropics/claude-plugins-official|claude-plugins-official"
  "frontend-design@claude-code-plugins|anthropics/claude-code|claude-code-plugins"
  "excalidraw-generator@excalidraw-generator|lexiaoyao20/excalidraw-generator|excalidraw-generator"
)
TEAM_STATE=()
for _i in "${!TEAM_KEYS[@]}"; do TEAM_STATE+=(1); done
unset _i

# --- Community plugins (menu item 6) ------------------------------------------
COMMUNITY_KEYS=(
  "adhd-output-style" "azure-tools" "anthropic-office-skills" "agent-browser" "ppt-master"
)
COMMUNITY_NAME=(
  "adhd-output-style       - ADHD-friendly output style"
  "azure-tools             - Azure CLI/portal helpers"
  "anthropic-office-skills - Anthropic's docx/pptx/xlsx/pdf skills"
  "agent-browser           - vercel-labs browser agent"
  "ppt-master              - PowerPoint deck generation"
)
COMMUNITY_SPEC=(
  "adhd-output-style@claude-settings|fcakyon/claude-codex-settings|claude-settings"
  "azure-tools@claude-settings|fcakyon/claude-codex-settings|claude-settings"
  "anthropic-office-skills@claude-settings|fcakyon/claude-codex-settings|claude-settings"
  "agent-browser@agent-browser|vercel-labs/agent-browser|agent-browser"
  "ppt-master@ppt-master|hugohe3/ppt-master|ppt-master"
)
COMMUNITY_STATE=()
for _i in "${!COMMUNITY_KEYS[@]}"; do COMMUNITY_STATE+=(1); done
unset _i

# --- Generic sub-picker groups ------------------------------------------------
# Every menu row that installs more than one thing gets a sub-picker on -> , exactly
# like the repo's own skills row always had. A group is the parallel arrays
# <PREFIX>_KEYS / _NAME / _STATE (and _SPEC where the entries span marketplaces).
# Parallel arrays plus eval indirection rather than associative arrays or namerefs,
# because this has to keep running on bash 3.2.
GROUP_MENU_KEYS=("own-skills" "team"   "community"   "repo-plugins")
GROUP_PREFIXES=( "SKILL"      "TEAM"   "COMMUNITY"   "PLUGIN")
GROUP_FLAGS=(    "--skills"   "--team" "--community" "--plugins")
GROUP_NOUN=(     "skills"     "team plugins" "community plugins" "plugins")
# Singular, for "ignoring unknown <thing> 'x'" warnings.
GROUP_NOUN1=(    "skill"      "team plugin"  "community plugin"  "plugin")
# printf template for the menu row: selected, total.
GROUP_LABEL=(
  "This repo's marketplace + %s of %s skills  >"
  "Team plugins: %s of %s (superpowers, frontend-design, excalidraw)  >"
  "Community marketplaces + %s of %s plugins  >"
  "This repo's plugins: %s of %s (crew, obsidian-vault - agents, commands, hooks)  >"
)
GROUP_TITLE=(
  "Pick individual skills from this repo"
  "Pick team plugins"
  "Pick community plugins"
  "Pick plugins from this repo"
)

group_index_for() {
  # menu key -> index into the GROUP_* arrays, or failure when the row has no group.
  local key="$1" i
  for i in "${!GROUP_MENU_KEYS[@]}"; do
    [ "${GROUP_MENU_KEYS[$i]}" = "$key" ] && { printf '%s' "$i"; return 0; }
  done
  return 1
}
group_prefix_for() {
  local idx
  idx="$(group_index_for "$1")" || return 1
  printf '%s' "${GROUP_PREFIXES[$idx]}"
}

# Indirection helpers. '$1' is always the prefix; nothing else is ever eval'd, and the
# prefixes are literals from GROUP_PREFIXES, never user input.
group_count()  { eval "printf '%s' \"\${#${1}_KEYS[@]}\""; }
group_key()    { eval "printf '%s' \"\${${1}_KEYS[$2]}\""; }
group_name()   { eval "printf '%s' \"\${${1}_NAME[$2]}\""; }
group_state()  { eval "printf '%s' \"\${${1}_STATE[$2]}\""; }
group_spec()   { eval "printf '%s' \"\${${1}_SPEC[$2]:-}\""; }
group_set()    { eval "${1}_STATE[$2]=$3"; }

group_set_all() {
  local prefix="$1" value="$2" i n
  n="$(group_count "$prefix")"
  for (( i=0; i<n; i++ )); do group_set "$prefix" "$i" "$value"; done
}

group_selected_count() {
  local prefix="$1" i n c=0
  n="$(group_count "$prefix")"
  for (( i=0; i<n; i++ )); do [ "$(group_state "$prefix" "$i")" -eq 1 ] && c=$((c+1)); done
  printf '%d' "$c"
}

group_entry_selected() {
  # $1 prefix, $2 entry key. Only true when the parent menu row is selected too - an
  # entry ticked in a sub-picker whose parent is off installs nothing.
  local prefix="$1" want="$2" idx i n
  for idx in "${!GROUP_PREFIXES[@]}"; do
    if [ "${GROUP_PREFIXES[$idx]}" = "$prefix" ]; then
      is_selected "${GROUP_MENU_KEYS[$idx]}" || return 1
      break
    fi
  done
  n="$(group_count "$prefix")"
  for (( i=0; i<n; i++ )); do
    if [ "$(group_key "$prefix" "$i")" = "$want" ]; then
      [ "$(group_state "$prefix" "$i")" -eq 1 ] && return 0
      return 1
    fi
  done
  return 1
}

expand_group_spec() {
  # $1 prefix, $2 spec: 'cloudflare,drata' | '1,4-6' | 'all' | 'none'.
  local prefix="$1" spec="$2" token n lo hi i total found noun
  total="$(group_count "$prefix")"
  noun="$(group_noun_for "$prefix" single)"
  case "$spec" in
    [Aa][Ll][Ll])     group_set_all "$prefix" 1; return 0 ;;
    [Nn][Oo][Nn][Ee]) group_set_all "$prefix" 0; return 0 ;;
  esac
  group_set_all "$prefix" 0
  spec="${spec//,/ }"
  for token in $spec; do
    if [[ "$token" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      lo="${BASH_REMATCH[1]}"; hi="${BASH_REMATCH[2]}"
      # Rejected rather than silently reinterpreted: bash's for-loop selects nothing
      # from '3-1' while PowerShell's '..' counts down and selects three, so the same
      # command line would mean different things on the two platforms.
      if [ "$lo" -gt "$hi" ]; then
        warn "ignoring reversed $noun range '$token' - write it low-to-high"
      else
        for (( n=lo; n<=hi; n++ )); do
          [ "$n" -ge 1 ] && [ "$n" -le "$total" ] && group_set "$prefix" "$((n-1))" 1
        done
      fi
    elif [[ "$token" =~ ^[0-9]+$ ]]; then
      n="$token"
      if [ "$n" -ge 1 ] && [ "$n" -le "$total" ]; then
        group_set "$prefix" "$((n-1))" 1
      else
        warn "ignoring out-of-range $noun number '$token'"
      fi
    else
      found=0
      for (( i=0; i<total; i++ )); do
        # Match the catalog key, or the label the picker actually shows, which is the
        # only name the user ever sees. Every current catalog leads its label with the
        # key, but a group whose label differs still has to answer to what is on screen.
        if [ "$(group_key "$prefix" "$i")" = "$token" ] \
        || [ "$(group_display_name "$prefix" "$i")" = "$token" ]; then
          group_set "$prefix" "$i" 1; found=1; break
        fi
      done
      [ "$found" -eq 0 ] && warn "ignoring unknown $noun '$token'"
    fi
  done
}

group_display_name() {
  # The first word of the catalog label - what the picker shows in its left column.
  local name
  name="$(group_name "$1" "$2")"
  printf '%s' "${name%%[[:space:]]*}"
}

group_noun_for() {
  # $2 is 'plural' (default) or 'single'.
  local prefix="$1" form="${2:-plural}" i
  for i in "${!GROUP_PREFIXES[@]}"; do
    if [ "${GROUP_PREFIXES[$i]}" = "$prefix" ]; then
      case "$form" in
        single) printf '%s' "${GROUP_NOUN1[$i]}" ;;
        *)      printf '%s' "${GROUP_NOUN[$i]}" ;;
      esac
      return 0
    fi
  done
  printf 'item'
}

install_group() {
  # Install a group's ticked entries. Every sub-picker group goes through here, so the
  # catalog really is the single source it claims to be: the menu label, the picker,
  # the --<group> flag and this loop all read the same <PREFIX>_SPEC.
  #
  # Marketplaces are registered once each, before any plugin. Registering per plugin
  # meant three 'claude plugin marketplace update' runs against claude-settings on the
  # community row alone - and a marketplace refresh re-clones the repo.
  #
  # $2, if given, is a marketplace the caller has already registered.
  local prefix="$1" seen=" ${2:-} " i n spec plugin source mkt
  n="$(group_count "$prefix")"
  for (( i=0; i<n; i++ )); do
    [ "$(group_state "$prefix" "$i")" -eq 1 ] || continue
    spec="$(group_spec "$prefix" "$i")"
    [ -n "$spec" ] || continue
    spec="${spec#*|}"
    source="${spec%%|*}"; mkt="${spec#*|}"
    case "$seen" in
      *" $mkt "*) continue ;;
    esac
    seen="$seen$mkt "
    run_step "Marketplace: $source" add_marketplace "$source" "$mkt"
  done
  for (( i=0; i<n; i++ )); do
    [ "$(group_state "$prefix" "$i")" -eq 1 ] || continue
    spec="$(group_spec "$prefix" "$i")"
    [ -n "$spec" ] || continue
    plugin="${spec%%|*}"
    run_step "Plugin: $plugin" install_plugin "$plugin"
  done
}


skills_selected_count() { group_selected_count SKILL; }

skills_set_all() { group_set_all SKILL "$1"; }

expand_skills_spec() { expand_group_spec SKILL "$1"; }

menu_label() {
  # A grouped row carries a live count, because "its 25 skills" stops being true the
  # moment someone opens the sub-picker and unticks one.
  local i="$1" idx prefix
  if idx="$(group_index_for "${MENU_KEYS[$i]}")"; then
    prefix="${GROUP_PREFIXES[$idx]}"
    # shellcheck disable=SC2059 - the template is ours, from GROUP_LABEL.
    printf "${GROUP_LABEL[$idx]}" \
      "$(group_selected_count "$prefix")" "$(group_count "$prefix")"
  else
    printf '%s' "${MENU_NAME[$i]}"
  fi
}

# --- Cursor picker -------------------------------------------------------------
# Up/Down move, Space toggles, Enter starts, Right opens a sub-picker. Operates on
# three parallel globals rather than bash 4.3 namerefs, so it still runs on older
# bash: callers fill PICK_LABEL/PICK_STATE/PICK_SUB and read PICK_STATE back.
PICK_LABEL=()
PICK_STATE=()
PICK_SUB=()
PICK_DEFAULT=()
PICK_TITLE=""
PICK_HINT=""
PICK_CURSOR=0
PICK_TOP=0
PICK_DRAWN=0
PICK_ACTION=""
PICK_STTY_SAVED=""
PICKER_FAILED=0

term_lines() {
  local n="${LINES:-}"
  [ -z "$n" ] && have tput && n="$(tput lines 2>/dev/null)"
  [ -z "$n" ] && n="$(stty size <&"$TTY_FD" 2>/dev/null | cut -d' ' -f1)"
  case "$n" in ''|*[!0-9]*) n=0 ;; esac
  printf '%d' "$n"
}

term_cols() {
  local n="${COLUMNS:-}"
  [ -z "$n" ] && have tput && n="$(tput cols 2>/dev/null)"
  [ -z "$n" ] && n="$(stty size <&"$TTY_FD" 2>/dev/null | cut -d' ' -f2)"
  case "$n" in ''|*[!0-9]*) n=80 ;; esac
  [ "$n" -lt 40 ] && n=40
  printf '%d' "$n"
}

picker_supported() {
  # Every one of these is a real terminal this script has to survive: a pipe with no
  # tty, a container without stty, TERM=dumb in a CI log, a 6-line tmux pane.
  [ "$NO_TTY" -eq 0 ] || return 1
  have stty || return 1
  case "${TERM:-}" in ""|dumb) return 1 ;; esac
  stty -g <&"$TTY_FD" >/dev/null 2>&1 || return 1
  [ "$(term_lines)" -ge 10 ] || return 1
  return 0
}

picker_raw_off() {
  [ -n "$PICK_STTY_SAVED" ] && stty "$PICK_STTY_SAVED" <&"$TTY_FD" 2>/dev/null
  PICK_STTY_SAVED=""
  printf '\033[?25h'
  trap - INT TERM EXIT
}

picker_raw_on() {
  PICK_STTY_SAVED="$(stty -g <&"$TTY_FD" 2>/dev/null)" || return 1
  # Without the trap, Ctrl-C in the menu leaves the terminal with echo off and the
  # cursor hidden, which reads as "the installer broke my shell".
  trap 'picker_raw_off; exit 130' INT TERM
  trap 'picker_raw_off' EXIT
  stty -echo -icanon min 1 time 0 <&"$TTY_FD" 2>/dev/null || { picker_raw_off; return 1; }
  printf '\033[?25l'
  return 0
}

picker_key() {
  local k rest
  IFS= read -rsn1 -u "$TTY_FD" k 2>/dev/null || { printf 'cancel'; return; }
  case "$k" in
    '')  printf 'enter'; return ;;
    ' ') printf 'space'; return ;;
  esac
  if [ "$k" = $'\033' ]; then
    # A lone Escape and the start of a CSI arrow sequence are the same first byte;
    # the short timeout is what tells them apart.
    rest=""
    IFS= read -rsn2 -t 0.1 -u "$TTY_FD" rest 2>/dev/null
    case "$rest" in
      '[A') printf 'up' ;;
      '[B') printf 'down' ;;
      '[C') printf 'right' ;;
      '[D') printf 'left' ;;
      '')   printf 'cancel' ;;
      *)    printf 'ignore' ;;
    esac
    return
  fi
  case "$k" in
    k|K) printf 'up' ;;
    j|J) printf 'down' ;;
    l|L) printf 'right' ;;
    h|H) printf 'left' ;;
    a|A) printf 'all' ;;
    n|N) printf 'clear' ;;
    d|D) printf 'defaults' ;;
    q|Q) printf 'cancel' ;;
    *)   printf 'ignore' ;;
  esac
}

picker_erase() {
  [ "$PICK_DRAWN" -gt 0 ] && printf '\033[%dA\033[J' "$PICK_DRAWN"
  PICK_DRAWN=0
}

pick_fit() {
  # Clip a line to the window width. Every line the picker prints goes through this:
  # one wrapped line makes the cursor-up count wrong and the next redraw smears over
  # whatever was above the menu.
  local text="$1" width="$2"
  if [ "${#text}" -gt "$width" ]; then
    printf '%s…' "${text:0:$((width-1))}"
  else
    printf '%s' "$text"
  fi
}

picker_draw() {
  local total=${#PICK_LABEL[@]} i mark cursor label avail cols width shown=0
  cols="$(term_cols)"
  width=$((cols - 9))
  # 2 title lines + 1 scroll line + 2 hint lines, plus a line of slack so a full
  # window never scrolls: scrolling would invalidate the cursor-up redraw below.
  avail=$(( $(term_lines) - 6 ))
  [ "$avail" -lt 3 ] && avail=3
  [ "$avail" -gt "$total" ] && avail=$total

  [ "$PICK_CURSOR" -lt "$PICK_TOP" ] && PICK_TOP="$PICK_CURSOR"
  [ "$PICK_CURSOR" -ge $((PICK_TOP + avail)) ] && PICK_TOP=$((PICK_CURSOR - avail + 1))
  [ "$PICK_TOP" -lt 0 ] && PICK_TOP=0
  [ $((PICK_TOP + avail)) -gt "$total" ] && PICK_TOP=$((total - avail))
  [ "$PICK_TOP" -lt 0 ] && PICK_TOP=0

  picker_erase
  printf '\033[36m  %s\033[0m\n' "$(pick_fit "$PICK_TITLE" "$width")"
  printf '\033[36m  %s\033[0m\n' "$(printf '%*s' "${#PICK_TITLE}" '' | tr ' ' '-')"
  for (( i=PICK_TOP; i<PICK_TOP+avail; i++ )); do
    mark=" "; cursor="  "
    [ "${PICK_STATE[$i]}" -eq 1 ] && mark="x"
    [ "$i" -eq "$PICK_CURSOR" ] && cursor="\033[36m>\033[0m "
    label="$(pick_fit "${PICK_LABEL[$i]}" "$width")"
    if [ "$i" -eq "$PICK_CURSOR" ]; then
      printf '  %b[%s] \033[1m%s\033[0m\n' "$cursor" "$mark" "$label"
    else
      printf '  %b[%s] %s\n' "$cursor" "$mark" "$label"
    fi
    shown=$((shown+1))
  done
  if [ "$total" -gt "$avail" ]; then
    printf '\033[90m  showing %d-%d of %d\033[0m\n' \
      "$((PICK_TOP+1))" "$((PICK_TOP+avail))" "$total"
  else
    printf '\n'
  fi
  local keys="↑↓ move   Space toggle   Enter start   A all   N none   D defaults   Q cancel"
  [ "$cols" -lt 84 ] && keys="↑↓ move  Space pick  Enter go  A/N/D  Q quit"
  printf '\033[90m  %s\033[0m\n' "$(pick_fit "$keys" "$width")"
  printf '\033[90m  %s\033[0m\n' "$(pick_fit "$PICK_HINT" "$width")"
  # 2 title lines + the rows + the scroll line + 2 hint lines. This number is what
  # the next redraw walks back up, so it has to match the printfs above exactly.
  PICK_DRAWN=$((2 + shown + 3))
}

picker_run() {
  # 0 = the user finished with it (PICK_ACTION says how), 2 = no usable terminal.
  local key i
  if ! picker_raw_on; then
    PICKER_FAILED=1
    return 2
  fi
  PICK_DRAWN=0
  PICK_ACTION=""
  while :; do
    picker_draw
    key="$(picker_key)"
    case "$key" in
      up)    [ "$PICK_CURSOR" -gt 0 ] && PICK_CURSOR=$((PICK_CURSOR-1)) ;;
      down)  [ "$PICK_CURSOR" -lt $(( ${#PICK_LABEL[@]} - 1 )) ] && PICK_CURSOR=$((PICK_CURSOR+1)) ;;
      space) PICK_STATE[$PICK_CURSOR]=$(( 1 - PICK_STATE[PICK_CURSOR] )) ;;
      all)   for i in "${!PICK_STATE[@]}"; do PICK_STATE[$i]=1; done ;;
      clear) for i in "${!PICK_STATE[@]}"; do PICK_STATE[$i]=0; done ;;
      defaults)
             for i in "${!PICK_STATE[@]}"; do PICK_STATE[$i]="${PICK_DEFAULT[$i]:-0}"; done ;;
      right)
             if [ "${PICK_SUB[$PICK_CURSOR]}" -eq 1 ]; then
               PICK_ACTION="submenu"; picker_erase; picker_raw_off; return 0
             fi ;;
      left)  PICK_ACTION="back"; picker_erase; picker_raw_off; return 0 ;;
      enter) PICK_ACTION="confirm"; picker_erase; picker_raw_off; return 0 ;;
      cancel) PICK_ACTION="cancel"; picker_erase; picker_raw_off; return 0 ;;
    esac
  done
}

pick_group_interactive() {
  # $1 is the index into the GROUP_* arrays. Restores the previous ticks on Q, so
  # backing out of a sub-picker cannot silently rewrite a selection.
  local idx="$1" prefix i n saved=()
  prefix="${GROUP_PREFIXES[$idx]}"
  n="$(group_count "$prefix")"
  PICK_LABEL=(); PICK_STATE=(); PICK_SUB=(); PICK_DEFAULT=()
  for (( i=0; i<n; i++ )); do
    PICK_LABEL+=("$(group_name "$prefix" "$i")")
    PICK_STATE+=("$(group_state "$prefix" "$i")")
    PICK_SUB+=(0)
    PICK_DEFAULT+=(1)
    saved+=("$(group_state "$prefix" "$i")")
  done
  PICK_CURSOR=0; PICK_TOP=0
  PICK_TITLE="${GROUP_TITLE[$idx]}"
  PICK_HINT="Enter or ← to go back to the main menu   Q to discard these changes"
  if ! picker_run; then
    return 1
  fi
  if [ "$PICK_ACTION" = "cancel" ]; then
    for (( i=0; i<n; i++ )); do group_set "$prefix" "$i" "${saved[$i]}"; done
    return 0
  fi
  for (( i=0; i<n; i++ )); do group_set "$prefix" "$i" "${PICK_STATE[$i]}"; done
  return 0
}

pick_menu_interactive() {
  local i sub_idx parent_row menu_row=0
  while :; do
    PICK_LABEL=(); PICK_STATE=(); PICK_SUB=(); PICK_DEFAULT=()
    for i in "${!MENU_KEYS[@]}"; do
      PICK_LABEL+=("$(menu_label "$i")")
      PICK_DEFAULT+=("${MENU_DEFAULT[$i]}")
      if [ -n "${MENU_STATE[$i]:-}" ]; then
        PICK_STATE+=("${MENU_STATE[$i]}")
      else
        PICK_STATE+=("${MENU_DEFAULT[$i]}")
      fi
      if group_index_for "${MENU_KEYS[$i]}" >/dev/null; then PICK_SUB+=(1); else PICK_SUB+=(0); fi
    done
    PICK_TITLE="Select what to install"
    PICK_HINT="→ on a row marked > picks the individual items inside it"
    PICK_CURSOR="${menu_row:-0}"; PICK_TOP=0
    picker_run || return 1
    menu_row="$PICK_CURSOR"
    for i in "${!MENU_KEYS[@]}"; do MENU_STATE[$i]="${PICK_STATE[$i]}"; done
    case "$PICK_ACTION" in
      submenu)
        # Remember which main-menu row we descended from: pick_group_interactive runs
        # the same picker, so it overwrites PICK_CURSOR with the sub-picker's own row.
        parent_row="$PICK_CURSOR"
        sub_idx="$(group_index_for "${MENU_KEYS[$parent_row]}")" || continue
        pick_group_interactive "$sub_idx" || return 1
        # Opening a sub-picker is a statement of intent: tick the parent row so a
        # careful sub-selection is not silently thrown away by an unticked parent.
        [ "$(group_selected_count "${GROUP_PREFIXES[$sub_idx]}")" -gt 0 ] \
          && MENU_STATE[$parent_row]=1
        ;;
      cancel)
        SELECTED=""
        printf '\033[33m  Cancelled - nothing selected.\033[0m\n'
        return 0
        ;;
      *)
        SELECTED=""
        for i in "${!MENU_KEYS[@]}"; do
          [ "${MENU_STATE[$i]}" -eq 1 ] && selection_add "${MENU_KEYS[$i]}"
        done
        return 0
        ;;
    esac
  done
}

MENU_STATE=()
for _i in "${!MENU_KEYS[@]}"; do MENU_STATE+=("${MENU_DEFAULT[$_i]}"); done
unset _i

show_menu() {
  local i mark
  printf '\n\033[36m  Select what to install\033[0m\n'
  printf '\033[36m  ----------------------\033[0m\n'
  for i in "${!MENU_KEYS[@]}"; do
    mark=" "
    [ "${MENU_DEFAULT[$i]}" -eq 1 ] && mark="x"
    printf '  %2d  [%s]  %s\n' "$((i+1))" "$mark" "$(menu_label "$i")"
  done
  printf '\n\033[90m  [x] marks the default set.\033[0m\n'
  printf '\033[90m  A = all   D = defaults   N = none   or numbers like 1,3,7-9\033[0m\n'
  printf '\033[90m  Rows marked > hold several items; pick inside them with the arrow\033[0m\n'
  printf '\033[90m  keys, or non-interactively with --skills / --team / --community /\033[0m\n'
  printf '\033[90m  --plugins (names, numbers, all, none)\033[0m\n'
}

select_install_items() {
  local answer="" gi prefix spec
  # A --<group> spec is a non-interactive answer in its own right: it settles that
  # group's list before anything is drawn, so it composes with --all and
  # --non-interactive.
  for gi in "${!GROUP_PREFIXES[@]}"; do
    prefix="${GROUP_PREFIXES[$gi]}"
    eval "spec=\"\${GROUP_SPEC_${prefix}}\""
    [ -n "$spec" ] || continue
    expand_group_spec "$prefix" "$spec"
    printf '\033[90m%s from %s "%s" (%d of %d).\033[0m\n' \
      "${GROUP_NOUN[$gi]}" "${GROUP_FLAGS[$gi]}" "$spec" \
      "$(group_selected_count "$prefix")" "$(group_count "$prefix")"
  done

  if [ "$SELECT_ALL" -eq 1 ]; then
    SELECTED="$(all_keys)"
    printf '\033[90mSelecting every item (--all).\033[0m\n'
  elif [ -n "$SELECT_SPEC" ]; then
    SELECTED="$(expand_selection_spec "$SELECT_SPEC")"
    printf '\033[90mSelecting from --select "%s".\033[0m\n' "$SELECT_SPEC"
  elif [ "$NON_INTERACTIVE" -eq 1 ]; then
    SELECTED="$(default_keys)"
    printf '\033[90mSelecting the default set (--non-interactive).\033[0m\n'
  elif picker_supported && pick_menu_interactive; then
    SELECTION_INTERACTIVE=1
  else
    # Reached either because the terminal never supported raw input, or because it
    # stopped part-way through. The second case is why this is a fall-through and not
    # an else on picker_supported alone: a picker that dies mid-draw must land on the
    # numbered prompt, not on an empty selection that looks like the user chose none.
    [ "$PICKER_FAILED" -eq 1 ] && warn "the cursor menu could not run here - falling back to the numbered menu."
    SELECTION_INTERACTIVE=1
    show_menu
    read -r -p "  Select [D] " answer <&"$TTY_FD"
    answer="${answer:-D}"
    case "$answer" in
      [Aa]|[Aa][Ll][Ll])           SELECTED="$(all_keys)" ;;
      [Dd]|[Dd][Ee][Ff][Aa][Uu][Ll][Tt]|[Dd][Ee][Ff][Aa][Uu][Ll][Tt][Ss]) SELECTED="$(default_keys)" ;;
      [Nn]|[Nn][Oo][Nn][Ee])       SELECTED="" ;;
      *)                           SELECTED="$(expand_selection_spec "$answer")" ;;
    esac
  fi

  # A --<group> spec is also a statement that you want that row: naming plugins inside
  # a row that is off by default (--plugins crew) would otherwise print a tidy summary
  # and install nothing. Only when something in the group is actually ticked, so
  # '--plugins none' still means none - and never after the menu, where unticking the
  # row (or pressing Q) is a decision this must not quietly reverse.
  for gi in "${!GROUP_PREFIXES[@]}"; do
    [ "$SELECTION_INTERACTIVE" -eq 1 ] && break
    prefix="${GROUP_PREFIXES[$gi]}"
    eval "spec=\"\${GROUP_SPEC_${prefix}}\""
    [ -n "$spec" ] || continue
    [ "$(group_selected_count "$prefix")" -gt 0 ] || continue
    is_selected "${GROUP_MENU_KEYS[$gi]}" || {
      selection_add "${GROUP_MENU_KEYS[$gi]}"
      printf '\033[90mAlso selecting "%s" - %s names items inside it.\033[0m\n' \
        "${GROUP_MENU_KEYS[$gi]}" "${GROUP_FLAGS[$gi]}"
    }
  done

  if [ "$SKIP_BOOTSTRAP" -eq 1 ]; then
    # --skip-bootstrap predates the menu, where it meant "prerequisites and the CLI
    # only". Keep that meaning by intersecting the selection rather than replacing it.
    local i
    for i in "${!MENU_KEYS[@]}"; do
      case "${MENU_KEYS[$i]}" in
        prereqs|cli) ;;
        *) selection_drop "${MENU_KEYS[$i]}" ;;
      esac
    done
    printf '\033[90mNarrowed to prerequisites + CLI (--skip-bootstrap).\033[0m\n'
  fi
}

selection_count() {
  local i n=0
  for i in "${!MENU_KEYS[@]}"; do
    is_selected "${MENU_KEYS[$i]}" && n=$((n+1))
  done
  printf '%d' "$n"
}

show_selection() {
  local i n
  n="$(selection_count)"
  echo ""
  if [ "$n" -eq 0 ]; then
    printf '\033[33m  Nothing selected.\033[0m\n'
    return 0
  fi
  printf '\033[36m  Will install (%d item(s)):\033[0m\n' "$n"
  for i in "${!MENU_KEYS[@]}"; do
    is_selected "${MENU_KEYS[$i]}" && printf '    - %s\n' "$(menu_label "$i")"
  done
  # Spell out any sub-selection: a row that says "3 of 25" is not enough to review.
  local gi prefix picked total j
  for gi in "${!GROUP_MENU_KEYS[@]}"; do
    is_selected "${GROUP_MENU_KEYS[$gi]}" || continue
    prefix="${GROUP_PREFIXES[$gi]}"
    picked="$(group_selected_count "$prefix")"
    total="$(group_count "$prefix")"
    if [ "$picked" -eq 0 ]; then
      # Only this repo's own row registers its marketplace regardless; for the others
      # registration follows a ticked plugin, so an empty group installs and registers
      # nothing at all.
      if [ "${GROUP_MENU_KEYS[$gi]}" = "own-skills" ]; then
        warn "no ${GROUP_NOUN[$gi]} selected - the marketplace will be registered but nothing installed from it. Re-run with ${GROUP_FLAGS[$gi]} all to get them."
      else
        warn "no ${GROUP_NOUN[$gi]} selected - this item will install nothing and register no marketplace. Re-run with ${GROUP_FLAGS[$gi]} all to get them."
      fi
    elif [ "$picked" -lt "$total" ]; then
      printf '\033[36m      %s:\033[0m\n' "${GROUP_NOUN[$gi]}"
      for (( j=0; j<total; j++ )); do
        [ "$(group_state "$prefix" "$j")" -eq 1 ] && printf '        - %s\n' "$(group_key "$prefix" "$j")"
      done
    fi
  done
}

select_skillui_guide() {
  # Asked up front with the menu, like every other interactive answer, so the install
  # run itself stays unattended. The guide is printed at the end of the SkillUI step.
  local answer
  is_selected "skillui" || { printf '0'; return 0; }
  [ -n "$SKILLUI_GUIDE" ] && { printf '%s' "$SKILLUI_GUIDE"; return 0; }
  if [ "$NON_INTERACTIVE" -eq 1 ] || [ "$SELECT_ALL" -eq 1 ] || [ -n "$SELECT_SPEC" ]; then
    printf '1'; return 0
  fi
  printf '\n\033[36m  SkillUI extracts a design system from any URL into a folder\033[0m\n' >&2
  printf '\033[90m  Claude Code can build against. It ships a short quick start.\033[0m\n' >&2
  read -r -p "  Print the SkillUI quick start after installing? [Y/n] " answer <&"$TTY_FD"
  case "${answer:-Y}" in [Nn]*) printf '0' ;; *) printf '1' ;; esac
}

# --- notify skill setup -------------------------------------------------------
skill_selected() {
  # 'notify' is a sub-picker entry, not a top-level menu key, so is_selected() would
  # always say no. group_entry_selected looks it up in the skill catalog and only
  # counts it when this repo's marketplace row is itself ticked.
  group_entry_selected SKILL "$1"
}

notify_prereqs() {
  # Printed whether or not they opt into the config scaffold - a headless run should
  # still see what it owes. Callers inside $( ) must redirect this to stderr.
  printf '    Prerequisites:\n'
  printf '      1. Python 3.8+ on PATH. No pip packages - the scripts are stdlib only.\n'
  printf '      2. A Telegram bot: message @BotFather, send /newbot, keep the token.\n'
  printf '      3. Message your new bot once (it cannot open a chat with you first),\n'
  printf '         then run scripts/telegram_get_chat_id.py to read your chat_id.\n'
  printf '      4. export TELEGRAM_BOT_TOKEN=... in your shell - the config file only\n'
  printf '         names the env var, it never stores the token.\n'
  printf '      5. A config at ~/.config/notify/config.json (global) or ./.notify.json\n'
  printf '         (per project), holding telegram.chat_id.\n'
  printf '      6. Outbound HTTPS to api.telegram.org, and the bot in polling mode -\n'
  printf '         a webhook on the bot makes getUpdates return 409. One poller per bot.\n'
  printf '    Optional:\n'
  printf '      - topics mode (one thread per job): a forum supergroup with Topics on,\n'
  printf '        the bot an admin with Manage Topics, and notifyd.py kept running.\n'
  printf '        Bare free-text answers there also need Group Privacy off in BotFather;\n'
  printf '        button taps and reply-to work either way.\n'
  printf '      - email: backend smtp needs SMTP_USER/SMTP_PASS (an app password for\n'
  printf '        Gmail/M365); backend connector needs an M365 or Gmail MCP connector\n'
  printf '        and only works while a Claude session is driving.\n'
  printf '    Walkthroughs: references/get-bot-token.md, references/windows.md.\n'
}

select_notify_setup() {
  # Asked up front with the menu, like every other interactive answer. The prereq list
  # goes to stderr so only the 0/1 lands in the caller's command substitution.
  local answer
  skill_selected "notify" || { printf '0'; return 0; }
  printf '\n\033[36m  The notify skill pings your phone or inbox about a job - Telegram\033[0m\n' >&2
  printf '\033[90m  (two-way, so it can ask you a question and wait) or email.\033[0m\n' >&2
  notify_prereqs >&2
  if [ -n "$NOTIFY_SETUP" ]; then printf '%s' "$NOTIFY_SETUP"; return 0; fi
  if [ "$NON_INTERACTIVE" -eq 1 ] || [ "$SELECT_ALL" -eq 1 ] || [ -n "$SELECT_SPEC" ]; then
    printf '0'; return 0
  fi
  read -r -p "  Scaffold ~/.config/notify/config.json now? [y/N] " answer <&"$TTY_FD"
  case "${answer:-N}" in [Yy]*) printf '1' ;; *) printf '0' ;; esac
}

setup_notify() {
  # Deliberately writes no secrets: the config names TELEGRAM_BOT_TOKEN, the user
  # exports it. An existing config is never overwritten.
  local dir="$HOME/.config/notify" target="$dir/config.json" src="" py=""
  for py in python3 python; do have "$py" && break; py=""; done
  if [ -z "$py" ]; then
    warn "python3 is not on PATH - notify's scripts need it. Install it and re-run."
  else
    ok "python found at $(command -v "$py")"
  fi

  if [ -f "$target" ]; then
    skip "notify config already exists at $target - left as it is"
  else
    src="$(find "$(claude_config_root)/plugins" -path '*/notify/assets/config.example.json' -print -quit 2>/dev/null || true)"
    mkdir -p "$dir" || return 1
    if [ -n "$src" ] && [ -f "$src" ]; then
      cp "$src" "$target" || return 1
    else
      # Same key set as the skill's assets/config.example.json, but in 'dm' mode with a
      # placeholder chat_id: 'topics' would need a forum supergroup nobody has yet.
      cat > "$target" <<'JSON' || return 1
{
  "default_channel": "telegram",
  "telegram": { "bot_token_env": "TELEGRAM_BOT_TOKEN", "chat_id": "REPLACE_ME", "mode": "dm" },
  "dispatcher": { "enabled": false, "spool_dir": "~/.local/state/notify/spool", "close_topic_on_complete": true },
  "email": {
    "backend": "smtp", "to": "me@example.com", "from": "claude-jobs@example.com",
    "smtp": { "provider": "gmail", "username_env": "SMTP_USER", "password_env": "SMTP_PASS" }
  },
  "events": { "complete": true, "error": true, "question": true, "info": true },
  "reply": { "enabled": true, "timeout_seconds": 3600 }
}
JSON
    fi
    COUNT_INSTALLED=$((COUNT_INSTALLED+1))
    ok "wrote a starter config to $target"
  fi

  printf '\n\033[36m    Finish notify setup\033[0m\n'
  printf '    1. @BotFather -> /newbot -> copy the token, then:\n'
  printf '         export TELEGRAM_BOT_TOKEN="123456789:AAE..."\n'
  printf '    2. Message your bot once, then run telegram_get_chat_id.py and put the\n'
  printf '       printed chat_id into telegram.chat_id in %s\n' "$target"
  printf '    3. Test it:  python notify.py -e info -m "hello" --dry-run\n'
  printf '    Or let Claude do the whole thing for you: run /notify-setup in a session.\n'
  return 0
}

# --- Selection ----------------------------------------------------------------
select_install_items
show_selection

if [ "$(selection_count)" -eq 0 ]; then
  printf '\n\033[33mNothing to do.\033[0m\n'
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n\033[33m--dry-run: stopping here. Nothing was installed.\033[0m\n'
  exit 0
fi

SKILLUI_GUIDE="$(select_skillui_guide)"
NOTIFY_SETUP="$(select_notify_setup)"

# --- 1. OS packages: only what's actually missing ----------------------------
install_packages() {
  local mgr="" missing=()
  if   have apt-get; then mgr=apt
  elif have dnf;     then mgr=dnf
  elif have yum;     then mgr=yum
  elif have pacman;  then mgr=pacman
  elif have zypper;  then mgr=zypper
  elif have apk;     then mgr=apk
  else
    warn "No supported package manager found (apt-get/dnf/yum/pacman/zypper/apk). Install git, nodejs, npm, and python manually."
    return 1
  fi

  # component:probe -> package name per manager
  local -a components=(git node npm python3 pip3)
  local comp pkg
  for comp in "${components[@]}"; do
    if have "$comp"; then
      skip "$comp already present ($(command -v "$comp"))"
      continue
    fi
    case "$comp:$mgr" in
      git:*)            pkg=git ;;
      node:pacman)      pkg=nodejs ;;
      node:*)           pkg=nodejs ;;
      npm:*)            pkg=npm ;;
      python3:pacman)   pkg=python ;;
      python3:apk)      pkg=python3 ;;
      python3:*)        pkg=python3 ;;
      pip3:pacman)      pkg=python-pip ;;
      pip3:apk)         pkg=py3-pip ;;
      pip3:*)           pkg=python3-pip ;;
      *)                pkg="$comp" ;;
    esac
    missing+=("$pkg")
  done

  if [ ${#missing[@]} -eq 0 ]; then
    ok "all base packages already installed - nothing to do"
    return 0
  fi

  step "Installing missing packages: ${missing[*]}"
  case "$mgr" in
    apt)    as_root apt-get update -y && as_root apt-get install -y "${missing[@]}" ;;
    dnf)    as_root dnf install -y "${missing[@]}" ;;
    yum)    as_root yum install -y "${missing[@]}" ;;
    pacman) as_root pacman -Sy --noconfirm "${missing[@]}" ;;
    zypper) as_root zypper install -y "${missing[@]}" ;;
    apk)    as_root apk add --no-cache "${missing[@]}" ;;
  esac
  local rc=$?
  [ $rc -eq 0 ] && COUNT_INSTALLED=$((COUNT_INSTALLED+${#missing[@]}))
  return $rc
}
if is_selected "prereqs"; then
  run_step "Install git, nodejs, npm, python (missing only)" install_packages
fi

# --- 2. Claude Code CLI ------------------------------------------------------
claude_local_version() {
  # 'claude --version' prints '2.1.226 (Claude Code)', and anything wrapping it (a
  # proxy, a shell function) can print a banner first - take the last line and its
  # leading semver rather than the whole string.
  claude --version 2>/dev/null | tail -n 1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1
}

version_lt() {
  # True when $1 is strictly older than $2. 'sort -V' does the comparison so a
  # prerelease or a two-component version does not have to be special-cased.
  [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n 1)" = "$1" ]
}

claude_from_npm() {
  # Claude Code also ships a native installer. Reading the version tells us nothing
  # about which one put it there, and 'npm install -g' onto a native install lays a
  # second copy down beside the first. Only npm-owned installs get updated here.
  have npm || return 1
  npm ls -g --depth=0 @anthropic-ai/claude-code >/dev/null 2>&1
}

update_claude_cli() {
  # Runs when claude is already present. Never returns non-zero: a failed *update*
  # leaves an installed, working CLI behind, same reasoning as install_plugin.
  local local_ver latest
  local_ver="$(claude_local_version)"
  if [ -z "$local_ver" ]; then
    warn "could not read the installed Claude Code version - skipping the update check."
    return 0
  fi
  if [ "$NO_UPDATE" -eq 1 ]; then
    skip "Claude Code $local_ver installed (--no-update set, not checking for a newer one)"
    return 0
  fi
  if ! have npm; then
    warn "npm not found on PATH - cannot check whether Claude Code $local_ver is current."
    return 0
  fi
  latest="$(npm view @anthropic-ai/claude-code version 2>/dev/null | tr -d '[:space:]')"
  if [ -z "$latest" ]; then
    warn "could not reach the npm registry - skipping the Claude Code update check."
    return 0
  fi
  if ! version_lt "$local_ver" "$latest"; then
    # Equal, or local is *ahead* - a prerelease, or a dist-tag that has moved back.
    # Installing @latest there would be a downgrade.
    skip "Claude Code $local_ver is up to date (npm latest: $latest)"
    return 0
  fi
  if ! claude_from_npm; then
    warn "Claude Code $local_ver -> $latest available, but this install did not come from npm ($(command -v claude)) - update it the way you installed it."
    return 0
  fi
  step "Claude Code $local_ver -> $latest available"
  local npm_prefix
  npm_prefix="$(npm config get prefix)"
  if [ -w "$npm_prefix" ]; then
    npm install -g @anthropic-ai/claude-code@latest || { warn "the Claude Code update failed - keeping $local_ver."; return 0; }
  else
    as_root npm install -g @anthropic-ai/claude-code@latest || { warn "the Claude Code update failed - keeping $local_ver."; return 0; }
  fi
  COUNT_UPDATED=$((COUNT_UPDATED+1))
  ok "Claude Code updated $local_ver -> $(claude_local_version)"
}

install_claude_cli() {
  if ! have npm; then
    warn "npm not found on PATH - cannot install Claude Code CLI."
    return 1
  fi
  if have claude; then
    update_claude_cli
    return 0
  fi
  local npm_prefix
  npm_prefix="$(npm config get prefix)"
  if [ -w "$npm_prefix" ]; then
    npm install -g @anthropic-ai/claude-code
  else
    as_root npm install -g @anthropic-ai/claude-code
  fi
  local rc=$?
  [ $rc -eq 0 ] && COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  return $rc
}

export_claude_path() {
  local npm_prefix bin_dir
  npm_prefix="$(npm config get prefix)"
  bin_dir="${npm_prefix}/bin"
  export PATH="${bin_dir}:${PATH}"
  persist_path_entry "$bin_dir"

  if have claude; then
    ok "claude resolved at $(command -v claude)"
  else
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' (or open a new shell)."
  fi
}

if is_selected "cli"; then
  run_step "Install Claude Code CLI" install_claude_cli
  run_step "Export Claude Code CLI path" export_claude_path
fi

# Everything from here to the MCP servers needs the claude CLI on PATH.
CLAUDE_ITEMS="own-skills team find-skills community claude-code-setup supabase repo-plugins"
NEEDS_CLAUDE=0
for key in $CLAUDE_ITEMS; do
  is_selected "$key" && NEEDS_CLAUDE=1
done

if [ "$NEEDS_CLAUDE" -eq 1 ] && ! claude_available; then
  step "Skipping marketplace/plugin items"
  warn "claude is not on PATH in this shell - run 'source ~/.bashrc' and re-run to install them."
  for key in $CLAUDE_ITEMS; do selection_drop "$key"; done
fi

load_marketplaces
load_plugins

# --- 3. This repo's own marketplace and skills -------------------------------
if is_selected "own-skills"; then
  # Registered up front rather than left to install_group, so ticking zero skills still
  # leaves the marketplace available to browse with /plugin - which is what the warning
  # below promises. install_group is told about it so it is not added twice.
  run_step "Add this repo as a Claude Code marketplace" \
    add_marketplace "mbadali25/useful-claude-add-ons" "useful-claude-add-ons"

  # The catalog itself lives in SKILL_KEYS next to the menu; only the ticked ones get
  # installed, so --skills and the sub-picker both land here.
  if [ "$(skills_selected_count)" -eq 0 ]; then
    warn "no skills selected from this repo - marketplace registered, nothing installed. Re-run with --skills all to get them."
  fi
  install_group SKILL "useful-claude-add-ons"

  # notify is the one skill with machine-level setup (a config file and a bot token),
  # so it gets a post-install step when the user asked for it up front.
  if [ "$NOTIFY_SETUP" = "1" ] && skill_selected "notify"; then
    run_step "Set up the notify skill" setup_notify
  fi
fi

# --- 4. Team marketplaces and plugins ----------------------------------------
# The catalog is TEAM_KEYS/TEAM_SPEC next to the menu, so -> on the row (or --team)
# narrows it. Each entry names its own marketplace: superpowers comes from
# anthropics/claude-plugins-official rather than obra's own marketplace, because
# install_plugin detects on the bare name - a machine that already had superpowers
# from the official marketplace would otherwise end up with an orphaned
# 'superpowers-marketplace' registration plus a second, disabled copy. Only the
# marketplaces behind a ticked plugin get registered, and add_marketplace is a no-op
# when one is already present.
if is_selected "team"; then
  if [ "$(group_selected_count TEAM)" -eq 0 ]; then
    warn "no team plugins selected - nothing installed for this item, and no marketplace registered."
  fi
  install_group TEAM
fi

# --- 5. find-skills ----------------------------------------------------------
install_find_skills() {
  local dir present=0
  dir="$(claude_skills_dir)/find-skills"
  user_skill_installed "find-skills" && present=1
  if [ "$present" -eq 1 ] && [ "$NO_UPDATE" -eq 1 ]; then
    skip "find-skills already installed at $dir (--no-update set)"
    return 0
  fi
  npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code || return 1
  if ! user_skill_installed "find-skills"; then
    warn "the installer finished but '$dir/SKILL.md' was not created - see the output above."
    return 1
  fi
  if [ "$present" -eq 1 ]; then
    ok "find-skills re-installed (now current)"
  else
    COUNT_INSTALLED=$((COUNT_INSTALLED+1))
    ok "installed find-skills to $dir"
  fi
}
if is_selected "find-skills"; then
  run_step "Skill: find-skills (vercel-labs/skills)" install_find_skills
fi

# --- 6. Community marketplaces and plugins -----------------------------------
# The catalog is COMMUNITY_KEYS/COMMUNITY_SPEC next to the menu, so -> on the row (or
# --community) narrows it. Source repo -> marketplace name is *not* mechanical:
# fcakyon/claude-codex-settings publishes itself as 'claude-settings'. The middle
# field of each spec is the source, the last is the "name" in that repo's own
# .claude-plugin/marketplace.json, which is what 'plugin@marketplace' has to match.
if is_selected "community"; then
  if [ "$(group_selected_count COMMUNITY)" -eq 0 ]; then
    warn "no community plugins selected - nothing installed for this item, and no marketplace registered."
  fi
  install_group COMMUNITY
fi

# --- 7. claude-code-setup ----------------------------------------------------
# Ships inside anthropics/claude-plugins-official, which the community item also
# registers - add_marketplace is a no-op when it is already there, so this item works
# whether or not item 6 was selected.
if is_selected "claude-code-setup"; then
  run_step "Marketplace: anthropics/claude-plugins-official" \
    add_marketplace "anthropics/claude-plugins-official" "claude-plugins-official"
  run_step "Plugin: claude-code-setup@claude-plugins-official" \
    install_plugin "claude-code-setup@claude-plugins-official"
fi

# --- 8. task-observer --------------------------------------------------------
install_task_observer() {
  # This repo publishes no marketplace.json, so there is nothing for
  # 'claude plugin install' to consume - it is a plain skill directory. SKILL.md and
  # references/ are the whole skill; the README, USER-GUIDE and two 1.5 MB PNGs in the
  # repo are not part of it and are deliberately not copied.
  local dest tmp present=0
  dest="$(claude_skills_dir)/task-observer"
  user_skill_installed "task-observer" && present=1
  if [ "$present" -eq 1 ] && [ "$NO_UPDATE" -eq 1 ]; then
    skip "task-observer already installed at $dest (--no-update set)"
    return 0
  fi
  if ! have git; then
    warn "git not found on PATH - select the prerequisites item (or install git) and re-run."
    return 1
  fi
  tmp="$(mktemp -d)" || return 1
  if ! git clone --depth 1 --quiet https://github.com/rebelytics/one-skill-to-rule-them-all.git "$tmp"; then
    rm -rf "$tmp"
    return 1
  fi
  if [ ! -f "$tmp/SKILL.md" ]; then
    warn "clone succeeded but SKILL.md was not found in $tmp - the upstream layout may have changed."
    rm -rf "$tmp"
    return 1
  fi
  mkdir -p "$dest" || { rm -rf "$tmp"; return 1; }
  cp -f "$tmp/SKILL.md" "$dest/"
  rm -rf "$dest/references"
  cp -R "$tmp/references" "$dest/"
  rm -rf "$tmp"
  if [ "$present" -eq 1 ]; then
    ok "task-observer re-installed (now current) at $dest"
  else
    COUNT_INSTALLED=$((COUNT_INSTALLED+1))
    ok "installed task-observer to $dest"
  fi
}
if is_selected "task-observer"; then
  run_step "Skill: task-observer (rebelytics/one-skill-to-rule-them-all)" install_task_observer
fi

# --- 9-12. Optional MCP servers ----------------------------------------------
# Warm the cache before the first add_mcp_server call so duplicate detection works.
load_mcp_servers

install_aws_mcp() {
  if ! have uv && ! have uvx; then
    if have pip3; then
      pip3 install --user uv
    elif have pip; then
      pip install --user uv
    else
      warn "pip not found - install python3-pip first, then re-run to install uv."
      return 1
    fi
    export PATH="$HOME/.local/bin:$PATH"
  fi
  if ! have claude; then
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' and re-run this script."
    return 1
  fi
  add_mcp_server "aws-api" "-" uvx awslabs.aws-api-mcp-server@latest || return 1
  ok "Make sure AWS credentials are configured (aws configure)."
}
if is_selected "aws-mcp"; then
  run_step "Install AWS MCP server" install_aws_mcp
fi

install_azure_mcp() {
  if ! have claude; then
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' and re-run this script."
    return 1
  fi
  add_mcp_server "azure" "-" npx -y @azure/mcp@latest server start || return 1
  ok "Make sure you have run 'az login' before using it."
}
if is_selected "azure-mcp"; then
  run_step "Install Azure MCP server" install_azure_mcp
fi

install_playwright_mcp() {
  add_mcp_server "playwright" "-" npx @playwright/mcp@latest || return 1
  ok "Playwright downloads its browsers on first use; 'npx playwright install' does it ahead of time."
}
if is_selected "playwright-mcp"; then
  run_step "Install Playwright MCP server" install_playwright_mcp
fi

install_obsidian_mcp() {
  # Not a launched command: the endpoint is the obsidian-local-rest-api plugin
  # already running inside the vault-server container. It listens on the SERVER's
  # loopback, so the URL is a local port forwarded by SSH. The API key is
  # per-deployment and cannot be baked in.
  if [ -z "${OBSIDIAN_MCP_KEY:-}" ]; then
    skip "Obsidian MCP: no --obsidian-mcp-key given"
    printf '        Get the key from the vault server:
'
    printf '          sudo ./obsidian-vault-server.sh apikey
'
    printf '        Open the tunnel, then re-run with the key:
'
    printf '          ssh -N -L 27123:127.0.0.1:27123 <user>@<server>
'
    printf '          ./install-prerequisites.sh --select obsidian-mcp --obsidian-mcp-key <key>
'
    printf '        See the obsidian-vault-server skill for the whole setup.
'
    return 0
  fi
  add_mcp_http_server "obsidian-server" "${OBSIDIAN_MCP_URL:-http://127.0.0.1:27123/mcp/}"     "Authorization: Bearer ${OBSIDIAN_MCP_KEY}" || return 1
  ok "Requires an SSH tunnel: ssh -N -L 27123:127.0.0.1:27123 <user>@<server>"
}
if is_selected "obsidian-mcp"; then
  run_step "Register the Obsidian vault server MCP endpoint" install_obsidian_mcp
fi


# --- 13. Supabase -------------------------------------------------------------
# Ships inside anthropics/claude-plugins-official, the same marketplace items 6 and 7
# register - add_marketplace is a no-op when it is already there, so this item stands
# on its own. install_plugin does the "already installed?" check.
if is_selected "supabase"; then
  run_step "Marketplace: anthropics/claude-plugins-official" \
    add_marketplace "anthropics/claude-plugins-official" "claude-plugins-official"
  run_step "Plugin: supabase@claude-plugins-official" \
    install_plugin "supabase@claude-plugins-official"
fi

# --- 14. Context7 -------------------------------------------------------------
install_context7() {
  # 'ctx7 setup' writes the Context7 MCP/skill config for whichever agents it finds.
  # It is interactive, so it gets the terminal explicitly: under 'curl | bash' fd 0 is
  # still the script and the wizard would eat the next line of it.
  if ! have npx; then
    warn "npx not found on PATH - select the prerequisites item (or install Node.js) and re-run."
    return 1
  fi
  if [ "$NO_TTY" -eq 1 ]; then
    warn "no terminal available for 'ctx7 setup' - run 'npx ctx7 setup' by hand once this finishes."
    return 0
  fi
  npx -y ctx7@latest setup <&"$TTY_FD" || return 1
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "Context7 configured. Free tier works without a key; higher limits: https://context7.com"
}
if is_selected "context7"; then
  run_step "Configure Context7 (npx ctx7 setup)" install_context7
fi

# --- 15. Playwright CLI -------------------------------------------------------
install_playwright_cli() {
  # Detection is on the binary the package provides ('playwright-cli'), which is what
  # a user actually cares about - the package can also arrive via another manager.
  if have playwright-cli; then
    if [ "$NO_UPDATE" -eq 1 ]; then
      skip "playwright-cli already installed ($(command -v playwright-cli))"
      return 0
    fi
    ok "playwright-cli already installed - reinstalling @latest to pick up updates"
  fi
  if ! have npm; then
    warn "npm not found on PATH - select the prerequisites item (or install Node.js) and re-run."
    return 1
  fi
  npm install -g @playwright/cli@latest || return 1
  if ! have playwright-cli; then
    warn "@playwright/cli installed but 'playwright-cli' is not resolvable in this shell - run 'source ~/.bashrc' and try again."
    return 1
  fi
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "playwright-cli installed at $(command -v playwright-cli)"
}
if is_selected "playwright-cli"; then
  run_step "Install Playwright CLI (@playwright/cli)" install_playwright_cli
fi

# --- 16. SkillUI --------------------------------------------------------------
skillui_quick_start() {
  printf '\n\033[36m    SkillUI quick start\033[0m  https://github.com/amaancoderx/npxskillui\n'
  printf '    1. Extract a design system from any URL:\n'
  printf '         skillui --url https://notion.so\n'
  printf '    2. Open the output folder in Claude Code:\n'
  printf '         cd notion-design && claude\n'
  printf '    3. Ask for what you want built:\n'
  printf '         "Build me a landing page that matches this design system"\n'
  printf '    Claude reads the generated CLAUDE.md and SKILL.md on its own - no wiring up.\n'
  printf '    Modes: --ultra (full extraction)   --dir <path>   --repo <url>\n'
}

install_skillui() {
  # Three parts: the CLI, Playwright itself, and the Chromium build Playwright drives.
  # Playwright goes in globally rather than into the current directory - this script
  # can be run from anywhere, and 'npm install playwright' would leave a node_modules
  # tree wherever that happened to be.
  if ! have npm; then
    warn "npm not found on PATH - select the prerequisites item (or install Node.js) and re-run."
    return 1
  fi
  if have skillui && [ "$NO_UPDATE" -eq 1 ]; then
    skip "skillui already installed ($(command -v skillui); --no-update set)"
  else
    npm install -g skillui || return 1
    COUNT_INSTALLED=$((COUNT_INSTALLED+1))
    ok "skillui installed"
  fi
  npm install -g playwright || warn "'npm install -g playwright' failed - skillui needs it to capture screenshots."
  # Downloads the browser binary itself; skipping it leaves skillui able to start and
  # unable to render anything.
  npx -y playwright install chromium || warn "'npx playwright install chromium' failed - run it by hand before using skillui."
  if ! have skillui; then
    warn "skillui installed but is not resolvable in this shell - run 'source ~/.bashrc' and try again."
    return 1
  fi
  ok "skillui ready at $(command -v skillui)"
  [ "$SKILLUI_GUIDE" = "1" ] && skillui_quick_start
  return 0
}
if is_selected "skillui"; then
  run_step "Install SkillUI (+ Playwright and Chromium)" install_skillui
fi

# --- 17. Strix ----------------------------------------------------------------
strix_next_steps() {
  printf '\n\033[33m    Strix needs two more things before its first scan:\033[0m\n'
  printf '    1. Docker running - the first scan pulls the sandbox image.\n'
  printf '    2. An LLM API key, exported in your shell profile:\n'
  printf '         export STRIX_LLM="openai/gpt-5.4"     # or another supported provider\n'
  printf '         export LLM_API_KEY="your-api-key"\n'
  printf '    Then: strix --target ./app-directory        Results: strix_runs/<run-name>\n'
  printf '    Providers and options: https://docs.strix.ai\n'
}

install_strix() {
  # Upstream ships a shell installer rather than an npm/pip package, so this is the
  # documented path (https://github.com/usestrix/strix). Nothing here configures it -
  # Strix cannot run without Docker and an LLM key, which strix_next_steps spells out.
  if have strix; then
    if [ "$NO_UPDATE" -eq 1 ]; then
      skip "strix already installed ($(command -v strix); --no-update set)"
      strix_next_steps
      return 0
    fi
    ok "strix already installed - running the installer again to pick up updates"
  fi
  if ! have curl; then
    warn "curl not found on PATH - install curl, or follow https://docs.strix.ai by hand."
    return 1
  fi
  curl -sSL https://strix.ai/install | bash || return 1
  # Upstream does not document where the binary lands. ~/.local/bin is the usual answer
  # for this kind of installer, so try it for *this* shell only - guessing wrong there
  # costs nothing, whereas writing the guess into ~/.bashrc would be permanent.
  [ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"
  if ! have strix; then
    warn "the Strix installer finished but 'strix' is not resolvable in this shell - open a new shell and try 'strix --help'; the installer prints where it put the binary."
  else
    COUNT_INSTALLED=$((COUNT_INSTALLED+1))
    ok "strix installed at $(command -v strix)"
  fi
  strix_next_steps
}
if is_selected "strix"; then
  run_step "Install Strix AI pentesting CLI" install_strix
fi

# --- 18. Obsidian + claude-obsidian -------------------------------------------
obsidian_next_steps() {
  echo ""
  printf '\033[33m    Obsidian is installed, but the vault is a separate step:\033[0m\n'
  printf '      claude-obsidian-setup/setup-claude-obsidian.sh --apply --repo-root %s\n' "$OBSIDIAN_REPO_ROOT"
  echo "    That creates and verifies the vault. Run it without --apply first to preview."
  echo "    Details: claude-obsidian-setup/README.md"
}

install_obsidian() {
  # Obsidian ships no npm/pip package. Upstream publishes to Flathub and Snap,
  # plus raw AppImage/.deb; distro repos generally do not carry it at all.
  if have obsidian || flatpak info md.obsidian.Obsidian >/dev/null 2>&1 || [ -d /snap/obsidian ]; then
    skip "Obsidian already installed"
  elif have flatpak; then
    flatpak install -y flathub md.obsidian.Obsidian || return 1
    COUNT_INSTALLED=$((COUNT_INSTALLED+1))
    ok "Obsidian installed via flatpak"
  elif have snap; then
    as_root snap install obsidian --classic || return 1
    COUNT_INSTALLED=$((COUNT_INSTALLED+1))
    ok "Obsidian installed via snap"
  else
    warn "no flatpak or snap found - install Obsidian from https://obsidian.md (AppImage or .deb), then re-run."
  fi

  if claude_available; then
    # The vault engine, and Obsidian's own upstream syntax skills (Markdown,
    # Bases, JSON Canvas, the Obsidian CLI, Defuddle).
    add_marketplace "AgriciDaniel/claude-obsidian"
    install_plugin  "claude-obsidian@agricidaniel-claude-obsidian"
    add_marketplace "kepano/obsidian-skills"
    install_plugin  "obsidian@obsidian-skills"
  else
    warn "'claude' is not on PATH yet - re-run with item 2 selected, or open a new shell and re-run this item."
  fi

  obsidian_next_steps
}
if is_selected "obsidian"; then
  run_step "Install Obsidian desktop + claude-obsidian and obsidian-skills plugins" install_obsidian
fi

# --- 19. This repo's own plugins ----------------------------------------------
# Same marketplace as item 3, so add_marketplace is a no-op when item 3 already ran -
# this item stands on its own. install_plugin does the "already installed?" check.
# crew vendors its own narrowly-triggered find-skills copy (Task 12 narrowed its
# description so it stops competing with crew's other skills). A *global* find-skills
# install (menu item 5, or a prior 'npx skills add') is a second, separate copy with the
# old broad trigger, and the two can both fire on the same prompt. Detect and explain it;
# never delete it - it is the user's own global Claude Code config, not this repo's.
check_global_find_skills_collision() {
  local dir
  dir="$(claude_skills_dir)/find-skills"
  user_skill_installed "find-skills" || return 0
  warn "global find-skills skill found at $dir"
  echo "      This is vercel-labs/skills' find-skills (installed by menu item 5, or by"
  echo "      'npx skills add vercel-labs/skills --skill find-skills' directly) - a"
  echo "      separate, global copy from the one crew vendors internally. Two active"
  echo "      copies can both trigger on the same prompt."
  echo "      This script will not remove it for you. To remove the global copy yourself:"
  echo "        rm -rf \"$dir\""
}

crew_next_steps() {
  echo ""
  step "crew: next steps"
  echo "  Unlike a skill, crew registers hooks that run on their own:"
  echo "    - PreToolUse on Bash/PowerShell blocks terraform apply/destroy, destructive"
  echo "      DDL, force push, hard reset, and commands that would print a secret."
  echo "    - Stop runs the checks your changed paths map to and fails the turn on red."
  echo "  Set it up per repository before relying on either:"
  echo "    cd <your repo> && claude"
  echo "    /crew:init         # guided, resumable setup"
  echo "    /crew:onboard      # build the code map"
  echo "    /crew:verify       # build the change-to-check map the Stop gate needs"
  echo "  Full guide: https://github.com/mbadali25/useful-claude-add-ons/blob/main/plugin/crew/README.md"
}
if is_selected "repo-plugins"; then
  run_step "Add this repo as a Claude Code marketplace"     add_marketplace "mbadali25/useful-claude-add-ons" "useful-claude-add-ons"

  # The catalog lives in PLUGIN_KEYS next to the menu; -> on the row (or --plugins)
  # narrows it, the same as every other multi-item row.
  install_group PLUGIN "useful-claude-add-ons"

  # Only worth printing when crew is actually one of the ones installed.
  if group_entry_selected PLUGIN "crew"; then
    check_global_find_skills_collision
    crew_next_steps
  fi
fi

# --- 20. graphify -------------------------------------------------------------
# graphifyy on PyPI (double-y) provides two executables: 'graphify' and
# 'graphify-mcp'. Other 'graphify*' packages on PyPI are unaffiliated - installing the
# wrong one fails silently, so the double-y package is named explicitly below and in
# every message this step prints.
graphify_next_steps() {
  echo ""
  step "graphify: next steps"
  echo "  Build the code graph for a repo (--code-only is required whenever the repo"
  echo "  has any docs in it - without it graphify errors instead of skipping them):"
  echo "    cd <your repo> && graphify . --no-viz --code-only"
  echo "  graphify-mcp is installed alongside it if you want to wire it up as an MCP server."
}

install_graphify() {
  if have graphify; then
    skip "graphify already installed ($(command -v graphify))"
  else
    if ! have uv && ! have uvx; then
      if have pip3; then
        pip3 install --user uv
      elif have pip; then
        pip install --user uv
      else
        warn "pip not found - install python3-pip first, then re-run to install graphify."
        return 1
      fi
      export PATH="$HOME/.local/bin:$PATH"
    fi
    if ! have uv; then
      warn "uv still not found after attempting to install it - install it manually (https://docs.astral.sh/uv) and re-run."
      return 1
    fi
    uv tool install graphifyy || return 1
    export PATH="$HOME/.local/bin:$PATH"
    if ! have graphify; then
      warn "graphify (from graphifyy) installed but not resolvable in this shell - uv tool installs land in ~/.local/bin; run 'source ~/.bashrc' and re-run."
      return 1
    fi
    COUNT_INSTALLED=$((COUNT_INSTALLED+1))
    ok "graphify installed at $(command -v graphify) (graphify-mcp alongside it)"
  fi

  # Registered per-repo, never globally: a global graphify registration is the same
  # broad-global-skill collision Task 12 fixed by narrowing find-skills, above.
  if graphify install --project; then
    ok "registered graphify for this repo (--project)"
  else
    warn "'graphify install --project' failed - run it by hand from inside the target repo."
  fi
  graphify_next_steps
}
if is_selected "graphify"; then
  run_step "Install graphify (uv tool install graphifyy; registers --project)" install_graphify
fi

# --- 21. Microsoft MCP servers (mcp-servers/) ---------------------------------
# Not published to npm yet, so unlike the item-9-12 MCP servers this cannot just
# 'npx -y <pkg>@latest' - it needs a local clone (this script never resolves its own
# path; run it from inside a checkout, see README.md's two install modes) plus real
# Azure AD app registrations. See mcp-servers/README.md for the whole auth model.
#
# Interim form, works today: 'npm install -g .' inside each server package. Because
# these are npm workspace members, that global install is a symlink back into this
# clone whose module resolution still finds @mbadali/mcp-ms-core and every dependency
# via mcp-servers/node_modules (hoisted there by the 'npm install' below) - it does
# NOT try to fetch mcp-ms-core from the registry, which would 404 pre-publish. That
# also means the global bin only keeps working as long as this clone stays put; it is
# a dev-workspace link, not a real package install. Once published, item 21 (this same
# menu key, on a future run) switches to 'npx -y @mbadali/<pkg>@latest' - registration
# is bare either way ('-- <command>', no --env): claude mcp add --env persists the
# value into ~/.claude.json, and this repo's rule is secrets from env only, never
# written anywhere by this script. So these servers only work once MS_ADMIN_*/MS_USER_*
# are exported wherever the 'claude' process itself gets launched (shell profile,
# service manager, etc.) - this step just prints that.
install_ms_mcp() {
  local have_admin=0 have_user=0
  if [ -n "${MS_ADMIN_TENANT_ID:-}" ] && [ -n "${MS_ADMIN_CLIENT_ID:-}" ] && [ -n "${MS_ADMIN_CLIENT_SECRET:-}" ]; then
    have_admin=1
  fi
  [ -n "${MS_USER_CLIENT_ID:-}" ] && have_user=1

  if [ "$have_admin" -eq 0 ] && [ "$have_user" -eq 0 ]; then
    skip "Microsoft MCP servers: no MS_ADMIN_* or MS_USER_CLIENT_ID in the environment"
    printf '        These need real Azure AD app registrations first - see mcp-servers/README.md.\n'
    printf '        Then export the credentials this shell will pass through and re-run:\n'
    printf '          export MS_ADMIN_TENANT_ID=... MS_ADMIN_CLIENT_ID=... MS_ADMIN_CLIENT_SECRET=...  # msgraph/intune/o365-admin\n'
    printf '          export MS_USER_CLIENT_ID=...                                                     # o365-user (device code)\n'
    printf '          ./install-prerequisites.sh --select ms-mcp\n'
    return 0
  fi
  if ! have claude; then
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' and re-run this script."
    return 1
  fi
  if [ ! -f "./mcp-servers/package.json" ]; then
    skip "Microsoft MCP servers: mcp-servers/ not found under the current directory"
    printf '        Not published to npm yet - run this from inside a clone of the repo:\n'
    printf '          git clone https://github.com/mbadali25/useful-claude-add-ons\n'
    printf '          cd useful-claude-add-ons\n'
    printf '          ./scripts/install-prerequisites.sh --select ms-mcp\n'
    return 0
  fi
  if ! have node; then
    warn "node not found on PATH - install Node.js first (item 1), then re-run."
    return 1
  fi
  ( cd mcp-servers && npm install && npm run build ) || { warn "mcp-servers build failed - see output above."; return 1; }

  local root; root="$(pwd)/mcp-servers"
  if [ "$have_admin" -eq 1 ]; then
    ( cd "$root/packages/graph" && npm install -g . ) || { warn "'npm install -g' failed for mcp-msgraph - see output above."; return 1; }
    ( cd "$root/packages/intune" && npm install -g . ) || { warn "'npm install -g' failed for mcp-intune - see output above."; return 1; }
    ( cd "$root/packages/o365-admin" && npm install -g . ) || { warn "'npm install -g' failed for mcp-o365-admin - see output above."; return 1; }
    add_mcp_server "mcp-msgraph" "-" mcp-msgraph
    add_mcp_server "mcp-intune" "-" mcp-intune
    add_mcp_server "mcp-o365-admin" "-" mcp-o365-admin
  else
    skip "mcp-msgraph/mcp-intune/mcp-o365-admin: no MS_ADMIN_* credentials given"
  fi
  if [ "$have_user" -eq 1 ]; then
    ( cd "$root/packages/o365-user" && npm install -g . ) || { warn "'npm install -g' failed for mcp-o365-user - see output above."; return 1; }
    add_mcp_server "mcp-o365-user" "-" mcp-o365-user
  else
    skip "mcp-o365-user: no MS_USER_CLIENT_ID given"
  fi
  ok "Registered via 'npm install -g' (global bin names mcp-msgraph/mcp-intune/mcp-o365-admin/mcp-o365-user) - no secrets were written to ~/.claude.json. Export MS_ADMIN_TENANT_ID/MS_ADMIN_CLIENT_ID/MS_ADMIN_CLIENT_SECRET and/or MS_USER_CLIENT_ID (+ optional MS_USER_TENANT_ID) in the shell/profile that launches 'claude' itself, or these servers will fail to authenticate. Every server is read-only until MCP_MS_ALLOW_WRITES=1 is also set there. Run '<name> doctor' (e.g. 'mcp-msgraph doctor') to verify auth. After these packages are published, swap the registered command for 'npx -y @mbadali/<pkg>@latest' - see mcp-servers/README.md."
}
if is_selected "ms-mcp"; then
  run_step "Register Microsoft MCP servers (mcp-servers/)" install_ms_mcp
fi

# --- Summary -----------------------------------------------------------------
echo ""
printf '\033[36mInstalled: %d   Updated: %d   Already present: %d\033[0m\n' \
  "$COUNT_INSTALLED" "$COUNT_UPDATED" "$COUNT_SKIPPED"
if [ ${#FAILED_STEPS[@]} -eq 0 ]; then
  printf '\033[32mAll steps completed. Run "source ~/.bashrc" or open a new shell to pick up PATH changes.\033[0m\n'
else
  printf '\033[33mCompleted with %d failed step(s):\033[0m\n' "${#FAILED_STEPS[@]}"
  for s in "${FAILED_STEPS[@]}"; do echo "  - $s"; done
  printf '\033[33mRe-run this script after resolving the above; earlier successful steps are safe to repeat.\033[0m\n'
fi
