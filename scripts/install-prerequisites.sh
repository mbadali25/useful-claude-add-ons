#!/usr/bin/env bash
# Bootstraps a Linux machine for this repo's skills: git/nodejs/npm/python, the Claude
# Code CLI itself (with its path exported for future shells), and the team's standard
# Claude Code plugin marketplaces. Idempotent - safe to re-run.
#
# Everything is chosen from a menu up front, then installed unattended. The menu replaced
# a linear run of ~15 yes/no prompts, which meant you had to sit through the whole script
# to decline three things near the end. Every interactive answer (menu selection, Headroom
# mode) is collected before the first install starts.
#
# The menu is a cursor picker: Up/Down to move, Space to toggle, Enter to start. On the
# repo's own row, Right opens a second picker for the individual skills, so you can take
# three of them instead of all nineteen. Terminals that cannot do raw input - no stty, a
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
#                         --select headroom,claude-mem)
#   --skills a,b,c        install only these of this repo's skills, no prompt
#                         (--skills all | none also work; implies the repo item)
#   --non-interactive     select the default set, no prompt (CI/unattended)
#   --headroom-mode MODE  deploy|wrap|proxy|library|skip - skips the Headroom mode prompt
#   --no-update           never update an already-installed plugin, only report it
#   --skip-bootstrap      narrow the selection to prerequisites + the Claude Code CLI
#   --scope <scope>       scope for marketplace/plugin installs: user|project|local (default: user)

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
SELECT_ALL=0
SELECT_SPEC=""
SKILLS_SPEC=""
HEADROOM_MODE=""
INSTALL_SCOPE="user"   # machine-wide by default, not per-project

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-bootstrap)  SKIP_BOOTSTRAP=1 ;;
    --non-interactive) NON_INTERACTIVE=1 ;;
    --no-update)       NO_UPDATE=1 ;;
    --all)             SELECT_ALL=1 ;;
    --select)          SELECT_SPEC="${2:-}"; shift ;;
    --skills)          SKILLS_SPEC="${2:-}"; shift ;;
    --headroom-mode)   HEADROOM_MODE="${2:-deploy}"; shift ;;
    --scope)           INSTALL_SCOPE="${2:-user}"; shift ;;
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
  local expr="$1"
  if have jq; then
    jq -r "$expr" 2>/dev/null
  elif have python3; then
    python3 -c "$2" 2>/dev/null
  else
    return 1
  fi
}

claude_available() { have claude; }
claude_config_root() { printf '%s' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; }

# --- PATH persistence ---------------------------------------------------------
persist_path_entry() {
  # Append a PATH export to the login shells' rc files, once. Used for both the
  # npm global bin (claude) and the pipx bin dir (headroom).
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
  # Accepts a marketplace name ('superpowers-marketplace') or the GitHub 'owner/repo'
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
  # Emit one "name<TAB>version" line per plugin; ids are 'name@marketplace'.
  PLUGINS_CACHE="$(printf '%s' "$raw" | json_query \
    '.[] | "\(.id | split("@")[0])\t\(.version // "unknown")"' \
    'import json,sys
for p in json.load(sys.stdin):
    pid = p.get("id") or ""
    if pid:
        print("%s\t%s" % (pid.split("@")[0], p.get("version") or "unknown"))')"
}

plugin_version() {
  local want="$1" name ver
  [ -z "$PLUGINS_CACHE" ] && return 1
  while IFS=$'\t' read -r name ver; do
    [ "$name" = "$want" ] && { printf '%s' "$ver"; return 0; }
  done <<< "$PLUGINS_CACHE"
  return 1
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

tcp_port_open() {
  # bash's /dev/tcp pseudo-device, so no netcat dependency.
  local host="${1:-127.0.0.1}" port="$2"
  (exec 3<>"/dev/tcp/$host/$port") >/dev/null 2>&1 || return 1
  exec 3<&- 3>&-
  return 0
}

add_mcp_http_server() {
  # add_mcp_http_server <name> <url>
  # For a server that is already listening over HTTP: there is no command to launch,
  # and claude takes the endpoint as a positional argument rather than after '--'.
  local name="$1" url="$2"
  if ! have claude; then
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' and re-run this script."
    return 1
  fi
  if mcp_server_registered "$name"; then
    skip "MCP server '$name' already registered"
    return 0
  fi
  claude mcp add --scope "$INSTALL_SCOPE" --transport http "$name" "$url" || return 1
  load_mcp_servers
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "added MCP server '$name' -> $url"
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
  local spec="$1" name before after
  name="${spec%%@*}"
  if before="$(plugin_version "$name")"; then
    if [ "$NO_UPDATE" -eq 1 ]; then
      skip "plugin '$name' already installed (version $before)"
      return 0
    fi
    # A failed update is not fatal: the plugin is installed and usable, and
    # 'claude plugin update' legitimately fails when its marketplace has moved on.
    claude plugin update "$name" >/dev/null 2>&1       || warn "'claude plugin update $name' failed - keeping the installed version."
    load_plugins
    after="$(plugin_version "$name" || echo "$before")"
    if [ "$after" != "$before" ]; then
      COUNT_UPDATED=$((COUNT_UPDATED+1))
      ok "plugin '$name' updated $before -> $after"
    else
      skip "plugin '$name' already current (version $after)"
    fi
    return 0
  fi
  claude plugin install "$spec" --scope "$INSTALL_SCOPE" || return 1
  load_plugins
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "installed plugin '$spec'"
}

# --- Install catalog and menu -------------------------------------------------
# Three parallel indexed arrays rather than one associative array: bash hashes have
# no defined iteration order, and the menu numbers have to be stable between runs.
# MENU_DEFAULT is what [D] (and --non-interactive) picks, chosen to match the prompt
# defaults this script used before it had a menu.
MENU_KEYS=(
  "prereqs" "cli" "own-skills" "team" "find-skills" "community"
  "claude-code-setup" "task-observer" "claude-mem" "gsd" "voltagent"
  "aws-mcp" "azure-mcp" "perplexity-mcp" "playwright-mcp" "firecrawl-mcp"
  "chrome-mcp" "glyph-mcp" "omniroute" "headroom"
)
MENU_DEFAULT=(1 1 1 1 1 1 1 1 1 1 1 0 0 0 0 0 0 0 0 0)
MENU_NAME=(
  "Prerequisites: git, nodejs, npm, python3, pip3 (needs root or sudo)"
  "Claude Code CLI (@anthropic-ai/claude-code) + PATH export"
  "This repo's marketplace + its skills"
  "Team plugins: superpowers, frontend-design, excalidraw-generator"
  "find-skills skill (vercel-labs/skills)"
  "Community marketplaces + plugins (adhd-output-style, azure-tools, ppt-master, ...)"
  "claude-code-setup plugin (anthropics/claude-plugins-official)"
  "task-observer skill (rebelytics/one-skill-to-rule-them-all)"
  "claude-mem memory plugin + CLAUDE_MEM_WORKER_PORT in settings.json"
  "GSD (@opengsd/gsd-core)"
  "VoltAgent subagents (10 plugins, 154 agents)"
  "MCP server: AWS (awslabs.aws-api-mcp-server)"
  "MCP server: Azure (@azure/mcp)"
  "MCP server: Perplexity (needs PERPLEXITY_API_KEY)"
  "MCP server: Playwright (@playwright/mcp)"
  "MCP server: Firecrawl (needs FIRECRAWL_API_KEY)"
  "MCP server: Chrome DevTools (chrome-devtools-mcp)"
  "MCP server: Glyphs font editor (needs macOS + Glyphs.app running)"
  "OmniRoute AI gateway (npm) + its MCP server, optional guided setup"
  "Headroom: pipx + headroom-ai[all] + mode setup + doctor"
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
  # --select headroom,claude-mem works without counting rows in the menu.
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
  "claude-code-defaults" "cloudflare" "drata" "i-have-adhd"
  "infra-work-ticketing" "intune-graph" "mermaid-svg-bitbucket" "repo-docs"
  "shipstation" "sophos-central" "terraform-docs-readme" "visio-diagrams"
  "wazuh-onprem" "web-testing-playwright" "work-log-reporter"
)
SKILL_NAME=(
  "aws-opensearch          - Amazon OpenSearch Service over SigV4"
  "bitbucket               - Bitbucket Cloud git auth + REST API"
  "checkpoint-email        - Check Point Email Security (ex-Avanan)"
  "cisco-meraki            - Meraki Dashboard API"
  "claude-code-defaults    - Claude Code settings, hooks, statusline"
  "cloudflare              - Cloudflare v4 API: DNS, WAF, Workers, Zero Trust"
  "drata                   - Drata compliance automation"
  "i-have-adhd             - ADHD-friendly output style"
  "infra-work-ticketing    - ServiceDesk Plus / Jira work notes"
  "intune-graph            - Intune via Microsoft Graph"
  "mermaid-svg-bitbucket   - Pre-render Mermaid to SVG for Bitbucket"
  "repo-docs               - Full documentation set for a codebase"
  "shipstation             - ShipStation API"
  "sophos-central          - Sophos Central endpoints, alerts, XDR"
  "terraform-docs-readme   - Regenerate Terraform module READMEs"
  "visio-diagrams          - Create and edit .vsdx diagrams"
  "wazuh-onprem            - Self-hosted Wazuh across all four surfaces"
  "web-testing-playwright  - Drive a real browser to test a site"
  "work-log-reporter       - Session work log + emailed PDF report"
)
SKILL_STATE=()
for _i in "${!SKILL_KEYS[@]}"; do SKILL_STATE+=(1); done
unset _i

skills_selected_count() {
  local i n=0
  for i in "${!SKILL_KEYS[@]}"; do [ "${SKILL_STATE[$i]}" -eq 1 ] && n=$((n+1)); done
  printf '%d' "$n"
}

skills_set_all() {
  local i
  for i in "${!SKILL_KEYS[@]}"; do SKILL_STATE[$i]="$1"; done
}

expand_skills_spec() {
  # 'cloudflare,drata' | '1,4-6' | 'all' | 'none' -> sets SKILL_STATE.
  local spec="$1" token n lo hi i found
  case "$spec" in
    [Aa][Ll][Ll])   skills_set_all 1; return 0 ;;
    [Nn][Oo][Nn][Ee]) skills_set_all 0; return 0 ;;
  esac
  skills_set_all 0
  spec="${spec//,/ }"
  for token in $spec; do
    if [[ "$token" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      lo="${BASH_REMATCH[1]}"; hi="${BASH_REMATCH[2]}"
      for (( n=lo; n<=hi; n++ )); do
        [ "$n" -ge 1 ] && [ "$n" -le "${#SKILL_KEYS[@]}" ] && SKILL_STATE[$((n-1))]=1
      done
    elif [[ "$token" =~ ^[0-9]+$ ]]; then
      n="$token"
      if [ "$n" -ge 1 ] && [ "$n" -le "${#SKILL_KEYS[@]}" ]; then
        SKILL_STATE[$((n-1))]=1
      else
        warn "ignoring out-of-range skill number '$token'"
      fi
    else
      found=0
      for i in "${!SKILL_KEYS[@]}"; do
        if [ "${SKILL_KEYS[$i]}" = "$token" ]; then SKILL_STATE[$i]=1; found=1; break; fi
      done
      [ "$found" -eq 0 ] && warn "ignoring unknown skill '$token'"
    fi
  done
}

menu_label() {
  # The repo row carries a live count, because "its 19 skills" stops being true the
  # moment someone opens the skills picker and unticks one.
  local i="$1"
  if [ "${MENU_KEYS[$i]}" = "own-skills" ]; then
    printf "This repo's marketplace + %s of %s skills  >" \
      "$(skills_selected_count)" "${#SKILL_KEYS[@]}"
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

pick_skills_interactive() {
  local i saved=()
  PICK_LABEL=(); PICK_STATE=(); PICK_SUB=(); PICK_DEFAULT=()
  for i in "${!SKILL_KEYS[@]}"; do
    PICK_LABEL+=("${SKILL_NAME[$i]}")
    PICK_STATE+=("${SKILL_STATE[$i]}")
    PICK_SUB+=(0)
    PICK_DEFAULT+=(1)
  done
  saved=("${SKILL_STATE[@]}")
  PICK_CURSOR=0; PICK_TOP=0
  PICK_TITLE="Pick individual skills from this repo"
  PICK_HINT="Enter or ← to go back to the main menu   Q to discard these changes"
  if ! picker_run; then
    return 1
  fi
  if [ "$PICK_ACTION" = "cancel" ]; then
    SKILL_STATE=("${saved[@]}")
    return 0
  fi
  for i in "${!SKILL_KEYS[@]}"; do SKILL_STATE[$i]="${PICK_STATE[$i]}"; done
  return 0
}

pick_menu_interactive() {
  local i
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
      if [ "${MENU_KEYS[$i]}" = "own-skills" ]; then PICK_SUB+=(1); else PICK_SUB+=(0); fi
    done
    PICK_TITLE="Select what to install"
    PICK_HINT="→ on the repo row picks individual skills"
    picker_run || return 1
    for i in "${!MENU_KEYS[@]}"; do MENU_STATE[$i]="${PICK_STATE[$i]}"; done
    case "$PICK_ACTION" in
      submenu)
        pick_skills_interactive || return 1
        # Opening the skills picker is a statement of intent: tick the repo row so a
        # careful sub-selection is not silently thrown away by an unticked parent.
        [ "$(skills_selected_count)" -gt 0 ] && MENU_STATE[$MENU_OWN_INDEX]=1
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
MENU_OWN_INDEX=0
for _i in "${!MENU_KEYS[@]}"; do
  MENU_STATE+=("${MENU_DEFAULT[$_i]}")
  [ "${MENU_KEYS[$_i]}" = "own-skills" ] && MENU_OWN_INDEX="$_i"
done
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
  printf '\033[90m  Individual skills: re-run with --skills cloudflare,drata\033[0m\n'
}

select_install_items() {
  local answer=""
  # --skills is a non-interactive answer in its own right: it settles the skill list
  # before anything is drawn, so it composes with --all and --non-interactive.
  if [ -n "$SKILLS_SPEC" ]; then
    expand_skills_spec "$SKILLS_SPEC"
    printf '\033[90mSkills from --skills "%s" (%d of %d).\033[0m\n' \
      "$SKILLS_SPEC" "$(skills_selected_count)" "${#SKILL_KEYS[@]}"
  fi

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
    :
  else
    # Reached either because the terminal never supported raw input, or because it
    # stopped part-way through. The second case is why this is a fall-through and not
    # an else on picker_supported alone: a picker that dies mid-draw must land on the
    # numbered prompt, not on an empty selection that looks like the user chose none.
    [ "$PICKER_FAILED" -eq 1 ] && warn "the cursor menu could not run here - falling back to the numbered menu."
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
  if is_selected "own-skills"; then
    local picked
    picked="$(skills_selected_count)"
    if [ "$picked" -eq 0 ]; then
      warn "no individual skills selected - the marketplace will be registered but no skill installed. Re-run with --skills all to get them."
    elif [ "$picked" -lt "${#SKILL_KEYS[@]}" ]; then
      printf '\033[36m      skills:\033[0m\n'
      for i in "${!SKILL_KEYS[@]}"; do
        [ "${SKILL_STATE[$i]}" -eq 1 ] && printf '        - %s\n' "${SKILL_KEYS[$i]}"
      done
    fi
  fi
}

PERPLEXITY_KEY=""
FIRECRAWL_KEY=""
read_mcp_api_key() {
  # read_mcp_api_key <VAR_NAME> <label> <signup-url>  -> prints the key on stdout.
  # An already-exported variable wins, so CI and anyone who keeps keys in their profile
  # is never prompted. Prints nothing when there is no key and no way to ask, which
  # makes the caller skip that server rather than register a broken one.
  local var="$1" label="$2" url="$3" existing answer
  existing="$(printenv "$var" 2>/dev/null || true)"
  if [ -n "$existing" ]; then
    printf '\033[90m  Using %s from the environment for %s.\033[0m\n' "$var" "$label" >&2
    printf '%s' "$existing"
    return 0
  fi
  if [ "$NON_INTERACTIVE" -eq 1 ] || [ "$SELECT_ALL" -eq 1 ] || [ -n "$SELECT_SPEC" ]; then
    warn "$var is not set - $label will be skipped. Export it and re-run." >&2
    return 0
  fi
  printf '\n\033[36m  %s needs an API key.\033[0m\n' "$label" >&2
  printf '\033[90m  Get one at %s, or press Enter to skip this server.\033[0m\n' "$url" >&2
  read -r -p "  $var " answer <&"$TTY_FD"
  printf '%s' "${answer:-}"
}

read_mcp_api_keys() {
  # Collected up front with the menu so the install run itself stays unattended.
  if is_selected "perplexity-mcp"; then
    PERPLEXITY_KEY="$(read_mcp_api_key PERPLEXITY_API_KEY 'Perplexity MCP' 'https://www.perplexity.ai/account/api/keys')"
  fi
  if is_selected "firecrawl-mcp"; then
    FIRECRAWL_KEY="$(read_mcp_api_key FIRECRAWL_API_KEY 'Firecrawl MCP' 'https://www.firecrawl.dev/app/api-keys')"
  fi
}

OMNIROUTE_GUIDED=0
select_omniroute_setup() {
  # Asked up front with the menu. The wizard itself is interactive and runs at the
  # end, which is the one place a prompt during the install is unavoidable.
  local answer
  is_selected "omniroute" || { printf '0'; return 0; }
  if [ "$NON_INTERACTIVE" -eq 1 ] || [ "$SELECT_ALL" -eq 1 ] || [ -n "$SELECT_SPEC" ]; then
    printf '0'; return 0
  fi
  printf "
[36m  OmniRoute ships a first-run wizard ('omniroute setup') that connects a[0m
" >&2
  printf '[90m  provider and mints an API key. It is interactive and runs at the end.[0m
' >&2
  read -r -p "  Walk through OmniRoute setup after installing? [y/N] " answer <&"$TTY_FD"
  case "${answer:-N}" in [Yy]*) printf '1' ;; *) printf '0' ;; esac
}

select_headroom_mode() {
  # Asked up front, alongside the menu, so the install run itself stays unattended.
  local answer
  if [ -n "$HEADROOM_MODE" ]; then printf '%s' "$HEADROOM_MODE"; return 0; fi
  if [ "$NON_INTERACTIVE" -eq 1 ] || [ "$SELECT_ALL" -eq 1 ] || [ -n "$SELECT_SPEC" ]; then
    printf 'deploy'; return 0
  fi
  printf '\n\033[36m  Headroom mode\033[0m\n' >&2
  printf '    1  deploy   turnkey local deployment + agent config  (recommended)\n' >&2
  printf '    2  wrap     wrap the claude coding agent\n' >&2
  printf '    3  proxy    drop-in proxy on port 8787, zero code changes\n' >&2
  printf "    4  library  no CLI wiring; use 'from headroom import compress'\n" >&2
  printf '    5  skip     install only, configure later\n' >&2
  read -r -p "  Mode [1] " answer <&"$TTY_FD"
  case "${answer:-1}" in
    2) printf 'wrap' ;;
    3) printf 'proxy' ;;
    4) printf 'library' ;;
    5) printf 'skip' ;;
    *) printf 'deploy' ;;
  esac
}

# --- claude-mem settings.json patch ------------------------------------------
set_claude_mem_worker_port() {
  # claude-mem's own bootstrap writes CLAUDE_MEM_PROVIDER but not the worker port,
  # and the worker silently picks a different port without it. Patch the text with awk
  # rather than round-tripping through a JSON encoder, which reformats the whole file.
  local port="${1:-37790}" settings backup tmp
  settings="$(claude_config_root)/settings.json"

  if [ ! -f "$settings" ]; then
    warn "no settings.json at $settings yet - claude-mem writes it on first run; re-run this script afterwards to set CLAUDE_MEM_WORKER_PORT."
    return 0
  fi
  if grep -q '"CLAUDE_MEM_WORKER_PORT"' "$settings"; then
    skip "CLAUDE_MEM_WORKER_PORT already present in $settings"
    return 0
  fi

  backup="${settings}.bak"
  cp -f "$settings" "$backup" || return 1
  tmp="$(mktemp)" || return 1

  if grep -q '^[[:space:]]*"CLAUDE_MEM_PROVIDER"[[:space:]]*:' "$settings"; then
    awk -v port="$port" '
      !inserted && /^[[:space:]]*"CLAUDE_MEM_PROVIDER"[[:space:]]*:/ {
        match($0, /^[[:space:]]*/); indent = substr($0, 1, RLENGTH)
        line = $0
        sub(/[[:space:]]+$/, "", line)
        if (line ~ /,$/) {
          # Provider already has a trailing comma, so the new key needs one too.
          print line
          printf "%s\"CLAUDE_MEM_WORKER_PORT\": \"%s\",\n", indent, port
        } else {
          # Provider was the last key in its object - give it the comma instead.
          print line ","
          printf "%s\"CLAUDE_MEM_WORKER_PORT\": \"%s\"\n", indent, port
        }
        inserted = 1
        next
      }
      { print }
    ' "$settings" > "$tmp" || { rm -f "$tmp"; return 1; }
  elif have python3; then
    # No provider key to anchor to. Fall back to a structural edit of the env block,
    # writing both keys so the file ends up in the documented shape either way.
    if ! python3 - "$settings" "$port" > "$tmp" <<'PY'
import json
import sys

path, port = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
env = data.setdefault("env", {})
env.setdefault("CLAUDE_MEM_PROVIDER", "claude")
env["CLAUDE_MEM_WORKER_PORT"] = port
json.dump(data, sys.stdout, indent=2)
sys.stdout.write("\n")
PY
    then
      warn "could not rewrite $settings as JSON - left it untouched. Add \"CLAUDE_MEM_WORKER_PORT\": \"$port\" by hand."
      rm -f "$tmp"
      return 1
    fi
    warn "CLAUDE_MEM_PROVIDER was not in $settings - rewrote the file to add the env block (formatting may change; backup at $backup)."
  else
    warn "CLAUDE_MEM_PROVIDER not found in $settings and python3 is unavailable - add \"CLAUDE_MEM_WORKER_PORT\": \"$port\" by hand."
    rm -f "$tmp"
    return 0
  fi

  # Never leave a half-written settings.json behind. The original is still untouched
  # at this point, so bailing out here needs no restore - $tmp is simply discarded.
  if have python3 && ! python3 -m json.tool < "$tmp" >/dev/null 2>&1; then
    warn "the patched settings.json did not parse - leaving $settings as it was."
    rm -f "$tmp"
    return 1
  fi
  # Belt and braces: the awk branch is anchored, so a layout it does not recognise
  # would copy the file through unchanged and we would report a success that never
  # happened. Confirm the key is actually there before overwriting anything.
  if ! grep -q '"CLAUDE_MEM_WORKER_PORT"' "$tmp"; then
    warn "could not place CLAUDE_MEM_WORKER_PORT in $settings (unrecognised layout) - left it as it was. Add \"CLAUDE_MEM_WORKER_PORT\": \"$port\" by hand."
    rm -f "$tmp"
    return 1
  fi

  # Only now is the live file touched. A failed write restores from the backup rather
  # than leaving the truncation behind.
  if ! cat "$tmp" > "$settings"; then
    warn "writing $settings failed - restoring $backup."
    cp -f "$backup" "$settings"
    rm -f "$tmp"
    return 1
  fi
  rm -f "$tmp"
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "set CLAUDE_MEM_WORKER_PORT=$port in $settings (backup: $backup)"
}

# --- Selection ----------------------------------------------------------------
select_install_items
show_selection

if [ "$(selection_count)" -eq 0 ]; then
  printf '\n\033[33mNothing to do.\033[0m\n'
  exit 0
fi

read_mcp_api_keys
OMNIROUTE_GUIDED="$(select_omniroute_setup)"

HEADROOM_MODE_CHOICE="skip"
if is_selected "headroom"; then
  HEADROOM_MODE_CHOICE="$(select_headroom_mode)"
fi

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
install_claude_cli() {
  if ! have npm; then
    warn "npm not found on PATH - cannot install Claude Code CLI."
    return 1
  fi
  if have claude; then
    skip "claude already installed ($(claude --version 2>/dev/null || echo 'version unknown'))"
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
CLAUDE_ITEMS="own-skills team find-skills community claude-code-setup claude-mem gsd voltagent"
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
  run_step "Add this repo as a Claude Code marketplace" \
    add_marketplace "mbadali25/useful-claude-add-ons" "useful-claude-add-ons"

  # The catalog itself lives in SKILL_KEYS next to the menu; only the ticked ones
  # get installed, so --skills and the sub-picker both land here.
  if [ "$(skills_selected_count)" -eq 0 ]; then
    warn "no skills selected from this repo - marketplace registered, nothing installed."
  fi
  for idx in "${!SKILL_KEYS[@]}"; do
    [ "${SKILL_STATE[$idx]}" -eq 1 ] || continue
    plugin="${SKILL_KEYS[$idx]}"
    run_step "Plugin: ${plugin}@useful-claude-add-ons" install_plugin "${plugin}@useful-claude-add-ons"
  done
fi

# --- 4. Team marketplaces and plugins ----------------------------------------
if is_selected "team"; then
  run_step "Marketplace: obra/superpowers-marketplace" \
    add_marketplace "obra/superpowers-marketplace" "superpowers-marketplace"
  run_step "Marketplace: anthropics/claude-code" \
    add_marketplace "anthropics/claude-code" "claude-code-plugins"
  run_step "Marketplace: lexiaoyao20/excalidraw-generator" \
    add_marketplace "lexiaoyao20/excalidraw-generator" "excalidraw-generator"

  team_plugins=(
    "superpowers@superpowers-marketplace"
    "frontend-design@claude-code-plugins"
    "excalidraw-generator@excalidraw-generator"
  )
  for spec in "${team_plugins[@]}"; do
    run_step "Plugin: $spec" install_plugin "$spec"
  done
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

# --- 6. Community marketplaces (from claudepluginhub.com) --------------------
# Installed with native 'claude plugin' commands. Source repo -> marketplace name is
# *not* mechanical: fcakyon/claude-codex-settings publishes itself as 'claude-settings'.
# The second field below is the "name" in that repo's own .claude-plugin/marketplace.json,
# which is what 'plugin@marketplace' has to match.
if is_selected "community"; then
  # "source|marketplace-name" pairs
  community_marketplaces=(
    "anthropics/claude-plugins-official|claude-plugins-official"
    "vercel-labs/agent-browser|agent-browser"
    "fcakyon/claude-codex-settings|claude-settings"
    "hugohe3/ppt-master|ppt-master"
  )
  for entry in "${community_marketplaces[@]}"; do
    run_step "Marketplace: ${entry%%|*}" add_marketplace "${entry%%|*}" "${entry#*|}"
  done

  community_plugins=(
    "adhd-output-style@claude-settings"
    "azure-tools@claude-settings"
    "anthropic-office-skills@claude-settings"
    "agent-browser@agent-browser"
    "ppt-master@ppt-master"
  )
  for spec in "${community_plugins[@]}"; do
    run_step "Plugin: $spec" install_plugin "$spec"
  done
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

# --- 9. claude-mem -----------------------------------------------------------
# claude-mem supports the plugin-marketplace path as a first-class alternative to its
# 'npx claude-mem install' bootstrapper (see its README) - the plugin's own hooks handle
# worker/dependency setup on first run.
if is_selected "claude-mem"; then
  run_step "Marketplace: thedotmack/claude-mem" add_marketplace "thedotmack/claude-mem" "thedotmack"
  run_step "Plugin: claude-mem@thedotmack" install_plugin "claude-mem@thedotmack"
  run_step "Configure claude-mem worker port" set_claude_mem_worker_port "37790"
fi

# --- 10. GSD -----------------------------------------------------------------
install_gsd() {
  local state
  state="$(claude_config_root)/gsd-install-state.json"
  if [ -f "$state" ]; then
    if [ "$NO_UPDATE" -eq 1 ]; then
      skip "GSD already installed ($state present; --no-update set)"
      return 0
    fi
    ok "GSD already installed - running the installer again to pick up updates"
  fi
  npx -y @opengsd/gsd-core@latest || return 1
  [ -f "$state" ] || COUNT_INSTALLED=$((COUNT_INSTALLED+1))
}
if is_selected "gsd"; then
  run_step "Install GSD core" install_gsd
fi

# --- 11. VoltAgent subagents -------------------------------------------------
# The repo publishes itself as the 'voltagent-subagents' marketplace, with its 154
# subagents split across ten category plugins. Installing them as plugins replaces the
# old 'git clone + bash install-agents.sh' path, which needed an interactive TTY and a
# writable ~/repos checkout.
if is_selected "voltagent"; then
  run_step "Marketplace: VoltAgent/awesome-claude-code-subagents" \
    add_marketplace "VoltAgent/awesome-claude-code-subagents" "voltagent-subagents"

  voltagent_plugins=(
    "voltagent-core-dev"
    "voltagent-lang"
    "voltagent-infra"
    "voltagent-qa-sec"
    "voltagent-data-ai"
    "voltagent-dev-exp"
    "voltagent-domains"
    "voltagent-biz"
    "voltagent-meta"
    "voltagent-research"
  )
  for plugin in "${voltagent_plugins[@]}"; do
    run_step "Plugin: ${plugin}@voltagent-subagents" install_plugin "${plugin}@voltagent-subagents"
  done
fi

# --- 12/13. Optional MCP servers ---------------------------------------------
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

install_perplexity_mcp() {
  if [ -z "$PERPLEXITY_KEY" ]; then
    skip "Perplexity MCP (no PERPLEXITY_API_KEY supplied)"
    return 0
  fi
  add_mcp_server "perplexity" "PERPLEXITY_API_KEY=$PERPLEXITY_KEY" npx -y @perplexity-ai/mcp-server
}
if is_selected "perplexity-mcp"; then
  run_step "Install Perplexity MCP server" install_perplexity_mcp
fi

install_playwright_mcp() {
  add_mcp_server "playwright" "-" npx @playwright/mcp@latest || return 1
  ok "Playwright downloads its browsers on first use; 'npx playwright install' does it ahead of time."
}
if is_selected "playwright-mcp"; then
  run_step "Install Playwright MCP server" install_playwright_mcp
fi

install_firecrawl_mcp() {
  if [ -z "$FIRECRAWL_KEY" ]; then
    skip "Firecrawl MCP (no FIRECRAWL_API_KEY supplied)"
    return 0
  fi
  add_mcp_server "firecrawl" "FIRECRAWL_API_KEY=$FIRECRAWL_KEY" npx -y firecrawl-mcp
}
if is_selected "firecrawl-mcp"; then
  run_step "Install Firecrawl MCP server" install_firecrawl_mcp
fi

install_chrome_mcp() {
  # Drives a real Chrome over the DevTools protocol, so a stable Chrome has to be
  # installed. Usage statistics are on by default upstream; --no-usage-statistics turns
  # them off and is passed here rather than left to the user to discover.
  add_mcp_server "chrome-devtools" "-" npx chrome-devtools-mcp@latest --no-usage-statistics || return 1
  ok "Needs a stable Chrome installed. Drop --no-usage-statistics from the config to opt back in to upstream telemetry."
}
if is_selected "chrome-mcp"; then
  run_step "Install Chrome DevTools MCP server" install_chrome_mcp
fi

install_glyph_mcp() {
  # Unlike the others this launches nothing: the server lives inside the Glyphs
  # .glyphsPlugin bundle and is started from Edit > Glyphs MCP Server inside the app,
  # so all that is registered here is the endpoint it listens on. The plugin is
  # macOS-only (macOS 13+, Glyphs 3 or 4), so on Linux this only resolves when the
  # port is forwarded from a Mac that is running it.
  local url="http://127.0.0.1:9680/mcp/"
  if ! tcp_port_open 127.0.0.1 9680; then
    warn "nothing is listening on 127.0.0.1:9680 - registering anyway, but the server stays unreachable until Glyphs.app is running with Edit > Glyphs MCP Server started (or the port is forwarded from a Mac)."
  fi
  add_mcp_http_server "glyphs-mcp" "$url" || return 1
  ok "Verify with: curl -H 'Accept: application/json' $url"
}
if is_selected "glyph-mcp"; then
  run_step "Install Glyphs MCP server" install_glyph_mcp
fi

# --- 19. OmniRoute -----------------------------------------------------------
install_omniroute() {
  if have omniroute; then
    skip "omniroute already installed ($(omniroute --version 2>/dev/null || echo 'version unknown'))"
    return 0
  fi
  if ! have npm; then
    warn "npm not found on PATH - select the prerequisites item (or install Node.js) and re-run."
    return 1
  fi
  if ! npm install -g omniroute; then
    # The package builds better-sqlite3 and @swc/core natively; upstream documents
    # this escape hatch for machines without a toolchain.
    warn "npm install failed - retrying with OMNIROUTE_SKIP_POSTINSTALL=1 (skips the native build)."
    OMNIROUTE_SKIP_POSTINSTALL=1 npm install -g omniroute || return 1
  fi
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "omniroute installed"
}

omniroute_guided_setup() {
  if ! have omniroute; then
    warn "omniroute is not on PATH - open a new shell and run 'omniroute setup'."
    return 1
  fi
  printf '[90m    Starting the OmniRoute wizard. Answer its prompts, then come back here.[0m
'
  # The wizard reads its own prompts, so hand it the terminal rather than fd 0 -
  # on the 'curl | bash' path fd 0 is still the script.
  omniroute setup <&"$TTY_FD" || return 1
  ok "wizard finished"
}

register_omniroute_mcp() {
  # OmniRoute is a local gateway: the MCP endpoint only answers while it is running
  # ('omniroute' starts it, dashboard on :20128). Registering ahead of time is the
  # usual order, so a closed port is a warning rather than a stop.
  if ! tcp_port_open 127.0.0.1 20128; then
    warn "nothing is listening on 127.0.0.1:20128 - registering anyway. Start the gateway with 'omniroute' and the server becomes reachable."
  fi
  add_mcp_http_server "omniroute" "http://localhost:20128/api/mcp/stream"
}

omniroute_next_steps() {
  printf '    1. Start the gateway:      omniroute
'
  printf '    2. Open the dashboard:     http://localhost:20128
'
  printf '    3. Dashboard > Providers - connect a provider (keyless ones work immediately)
'
  printf '    4. Dashboard > Endpoints - copy your API key
'
  printf '    5. Point any OpenAI-compatible tool at:
'
  printf '         Base URL  http://localhost:20128/v1
'
  printf '         Model     auto
'
  printf '    Diagnostics: omniroute doctor    TUI chat: omniroute chat
'
}

if is_selected "omniroute"; then
  if run_step "Install OmniRoute (npm i -g omniroute)" install_omniroute; then
    [ "$OMNIROUTE_GUIDED" = "1" ] && [ "$NO_TTY" -eq 0 ]       && run_step "OmniRoute guided setup" omniroute_guided_setup
    run_step "Register the OmniRoute MCP server" register_omniroute_mcp
    run_step "OmniRoute next steps" omniroute_next_steps
  fi
fi

# --- 20. Headroom ------------------------------------------------------------
install_pipx() {
  if have pipx; then
    skip "pipx already installed ($(command -v pipx))"
    return 0
  fi
  local py="" c base bindir
  for c in python3 python; do
    have "$c" && { py="$c"; break; }
  done
  if [ -z "$py" ]; then
    warn "no python3 found - select the prerequisites item (or install python3) and re-run."
    return 1
  fi
  "$py" -m pip install --user pipx || return 1
  # 'pip install --user' drops console scripts in the per-user bin directory, which is
  # not on PATH until 'pipx ensurepath' runs *and* a new shell starts. Put it on this
  # shell's PATH so the pipx call below resolves, then persist it for future shells.
  base="$("$py" -m site --user-base 2>/dev/null)"
  if [ -n "$base" ] && [ -d "$base/bin" ]; then
    bindir="$base/bin"
    export PATH="$bindir:$PATH"
    persist_path_entry "$bindir"
  fi
  "$py" -m pipx ensurepath >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
  persist_path_entry "$HOME/.local/bin"

  if ! have pipx; then
    warn "pipx installed but is still not resolvable in this shell - run 'source ~/.bashrc' and re-run."
    return 1
  fi
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "pipx installed at $(command -v pipx)"
}

install_headroom() {
  if have headroom; then
    skip "headroom already installed ($(headroom --version 2>/dev/null || echo 'version unknown'))"
    return 0
  fi
  local -a pipx_args=(install)
  if have python3.14; then
    pipx_args+=(--python python3.14)
  else
    warn "python3.14 not found - installing headroom against the default interpreter."
  fi
  pipx_args+=("headroom-ai[all]")

  if ! pipx "${pipx_args[@]}"; then
    warn "pipx install failed - falling back to 'npm install -g headroom-ai'."
    if ! npm install -g headroom-ai; then
      warn "both the pipx and npm installs of headroom failed."
      return 1
    fi
  fi
  export PATH="$HOME/.local/bin:$PATH"
  if ! have headroom; then
    warn "headroom installed but is still not resolvable in this shell - run 'source ~/.bashrc' and re-run."
    return 1
  fi
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "headroom installed at $(command -v headroom)"
}

configure_headroom() {
  if ! have headroom; then
    warn "headroom is not on PATH - run 'source ~/.bashrc' and run the mode command by hand."
    return 1
  fi
  # Only 'deploy' is safe to run here. 'wrap' launches the agent and 'proxy' blocks in
  # the foreground serving requests, so either one would hang the install.
  case "$HEADROOM_MODE_CHOICE" in
    deploy)  headroom deploy && ok "ran 'headroom deploy'" ;;
    wrap)    ok "wrap mode selected - start your agent with: headroom wrap claude" ;;
    proxy)   ok "proxy mode selected - start the proxy with: headroom proxy --port 8787" ;;
    library) ok "library mode selected - use 'from headroom import compress' in your code" ;;
    *)       skip "headroom mode configuration (skip selected)" ;;
  esac
}

verify_headroom() {
  if ! have headroom; then
    warn "headroom is not on PATH - run 'source ~/.bashrc' and then 'headroom doctor'."
    return 1
  fi
  headroom doctor
  headroom perf
  ok "live savings dashboard: headroom dashboard (needs the proxy running)"
}

if is_selected "headroom"; then
  run_step "Install pipx (required for headroom)" install_pipx \
    && run_step "Install headroom-ai" install_headroom \
    && run_step "Configure headroom ($HEADROOM_MODE_CHOICE mode)" configure_headroom \
    && run_step "Verify headroom (doctor + perf)" verify_headroom
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
