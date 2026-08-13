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
# The menu is a cursor picker: Up/Down to move, Space to toggle, Enter to start. Rows
# whose label ends in '>' - this repo's skills, the team plugins, the community plugins -
# open a second picker on Right, so you can take three of this repo's skills instead of
# all twenty-one, or ppt-master without agent-browser. Terminals that cannot do raw input
# - no stty, a dumb TERM, a window under ten lines - get the original numbered prompt
# instead, and every non-interactive path (--all, --select, --skills, --team-plugins,
# --community-plugins, --non-interactive) bypasses both.
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
#                         --select strix,claude-mem)
#   --skills a,b,c        install only these of this repo's skills, no prompt
#                         (--skills all | none also work; implies the repo item)
#   --team-plugins a,b    install only these team plugins, no sub-picker
#                         (all | none | numbers like 1,3 also work)
#   --community-plugins a,b
#                         install only these community plugins, no sub-picker
#   --non-interactive     select the default set, no prompt (CI/unattended)
#   --skillui-guide       print the SkillUI quick start after installing it, no prompt
#   --notify-setup        scaffold the notify config after installing it, no prompt
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
TEAM_SPEC=""
COMMUNITY_SPEC=""
SKILLUI_GUIDE=""       # "1"/"0" once answered; empty means "ask"
NOTIFY_SETUP=""        # "1"/"0" once answered; empty means "ask"
INSTALL_SCOPE="user"   # machine-wide by default, not per-project

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-bootstrap)    SKIP_BOOTSTRAP=1 ;;
    --non-interactive)   NON_INTERACTIVE=1 ;;
    --no-update)         NO_UPDATE=1 ;;
    --all)               SELECT_ALL=1 ;;
    --select)            SELECT_SPEC="${2:-}"; shift ;;
    --skills)            SKILLS_SPEC="${2:-}"; shift ;;
    --team-plugins)      TEAM_SPEC="${2:-}"; shift ;;
    --community-plugins) COMMUNITY_SPEC="${2:-}"; shift ;;
    --skillui-guide)     SKILLUI_GUIDE=1 ;;
    --notify-setup)      NOTIFY_SETUP=1 ;;
    --scope)             INSTALL_SCOPE="${2:-user}"; shift ;;
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

ensure_plugin_enabled() {
  # $1 is 'name@marketplace'. Best-effort: the plugin is installed either way, so a
  # failure here warns rather than failing the step. Tries the fully qualified spec
  # first because the bare name is ambiguous when two marketplaces publish it.
  local spec="$1" name="${spec%%@*}"
  plugin_enabled "$name" && return 0
  if claude plugin enable "$spec" --scope "$INSTALL_SCOPE" >/dev/null 2>&1 \
     || claude plugin enable "$name" --scope "$INSTALL_SCOPE" >/dev/null 2>&1; then
    load_plugins
    ok "enabled plugin '$name' (--scope $INSTALL_SCOPE)"
  else
    warn "plugin '$name' is installed but disabled and 'claude plugin enable' failed - run '/plugin' and enable it by hand."
  fi
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
      ensure_plugin_enabled "$spec"
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
    ensure_plugin_enabled "$spec"
    return 0
  fi
  claude plugin install "$spec" --scope "$INSTALL_SCOPE" || return 1
  load_plugins
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "installed plugin '$spec'"
  ensure_plugin_enabled "$spec"
}

# --- Install catalog and menu -------------------------------------------------
# Three parallel indexed arrays rather than one associative array: bash hashes have
# no defined iteration order, and the menu numbers have to be stable between runs.
# MENU_DEFAULT is what [D] (and --non-interactive) picks, chosen to match the prompt
# defaults this script used before it had a menu.
MENU_KEYS=(
  "prereqs" "cli" "own-skills" "team" "find-skills" "community"
  "claude-code-setup" "task-observer" "claude-mem" "voltagent"
  "aws-mcp" "azure-mcp" "playwright-mcp"
  "supabase" "context7" "playwright-cli" "skillui" "strix"
)
MENU_DEFAULT=(1 1 1 1 1 1 1 1 1 1 0 0 0 0 0 0 0 0)
# A non-empty entry here names the sub-catalog that row expands into: the row opens a
# second picker on Right, and its MENU_NAME is a printf template taking "ticked" and
# "total" so the row shows a live count instead of a fixed claim.
MENU_SUB=(
  "" "" "SKILL" "TEAM" "" "COMMUNITY"
  "" "" "" ""
  "" "" ""
  "" "" "" "" ""
)
MENU_NAME=(
  "Prerequisites: git, nodejs, npm, python3, pip3 (needs root or sudo)"
  "Claude Code CLI (@anthropic-ai/claude-code) + PATH export + update check"
  "This repo's marketplace + %s of %s skills  >"
  "Team plugins - %s of %s: superpowers, frontend-design, excalidraw-generator  >"
  "find-skills skill (vercel-labs/skills)"
  "Community marketplaces + plugins - %s of %s: adhd-output-style, azure-tools, ...  >"
  "claude-code-setup plugin (anthropics/claude-plugins-official)"
  "task-observer skill (rebelytics/one-skill-to-rule-them-all)"
  "claude-mem memory plugin + CLAUDE_MEM_WORKER_PORT in settings.json"
  "VoltAgent subagents (10 plugins, 154 agents)"
  "MCP server: AWS (awslabs.aws-api-mcp-server)"
  "MCP server: Azure (@azure/mcp)"
  "MCP server: Playwright (@playwright/mcp)"
  "Supabase plugin (supabase@claude-plugins-official)"
  "Context7 up-to-date library docs (npx ctx7 setup)"
  "Playwright CLI (@playwright/cli) - browser automation from the shell"
  "SkillUI (npm) + Playwright/Chromium - extract a design system from a URL"
  "Strix AI pentesting CLI (needs Docker + an LLM API key)"
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
  # --select strix,claude-mem works without counting rows in the menu.
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

# --- Sub-catalogs --------------------------------------------------------------
# Three menu rows expand into a checkbox list of their own, opened with Right. Each is a
# set of parallel arrays named <PREFIX>_KEYS / _NAME / _STATE; the two plugin catalogs add
# _PLUGIN (the 'name@marketplace' spec) and _SOURCE ('owner/repo|marketplace-name', the
# marketplace that has to be registered before that plugin can be installed). bash 3.2 has
# neither namerefs nor ordered hashes, so the helpers below reach a catalog through eval on
# its prefix - every prefix in this file is a literal, never built from user input.

# This repo's own skills. Keep in sync with .claude-plugin/marketplace.json. Everything is
# on by default: picking a subset is the exception, and a fresh machine wants the lot.
SKILL_KEYS=(
  "aws-opensearch" "bitbucket" "checkpoint-email" "cisco-meraki"
  "claude-code-defaults" "claude-code-tuneup" "cloudflare" "drata" "i-have-adhd"
  "infra-work-ticketing" "intune-graph" "mermaid-svg-bitbucket" "notify"
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
  "cloudflare              - Cloudflare v4: DNS, WAF, cache, Workers, Zero Trust"
  "drata                   - Drata: controls, monitors, evidence, audit prep"
  "i-have-adhd             - ADHD-friendly output: next action first, numbered steps"
  "infra-work-ticketing    - ServiceDesk Plus / Jira: open tickets, log work notes"
  "intune-graph            - Intune via Graph: devices, compliance, app deployment"
  "mermaid-svg-bitbucket   - Pre-render Mermaid to SVG so Bitbucket displays it"
  "notify                  - Ping your phone or inbox: Telegram bot (two-way) or email"
  "repo-docs               - Whole doc set: CLAUDE.md, READMEs, architecture, handoff"
  "shipstation             - ShipStation V2/V1/ShipEngine: labels, rates, orders"
  "sophos-central          - Sophos Central: isolate endpoints, triage alerts, XDR"
  "terraform-docs-readme   - Regenerate a Terraform module README with terraform-docs"
  "visio-diagrams          - Native .vsdx diagrams from a spec, or via Visio COM"
  "wazuh-onprem            - Self-hosted Wazuh: server, indexer, dashboards, ossec.conf"
  "web-testing-playwright  - Real-browser testing: screenshots, console, form flows"
  "work-log-reporter       - Session work log + emailed PDF report over SMTP"
)

# Team plugins. superpowers comes from anthropics/claude-plugins-official, not obra's own
# marketplace: upstream publishes to both, but install_plugin detects on the bare name, so
# a machine that already had superpowers from the official marketplace skipped the install
# and was left with an orphaned 'superpowers-marketplace' registration plus a second,
# disabled copy of the plugin. One source per plugin avoids the duplicate.
TEAM_KEYS=(
  "superpowers" "frontend-design" "excalidraw-generator"
)
TEAM_NAME=(
  "superpowers             - brainstorming, TDD, systematic debugging, plan execution"
  "frontend-design         - distinctive UI: typography, colour, layout with intent"
  "excalidraw-generator    - hand-drawn .excalidraw diagrams from a description"
)
TEAM_PLUGIN=(
  "superpowers@claude-plugins-official"
  "frontend-design@claude-code-plugins"
  "excalidraw-generator@excalidraw-generator"
)
TEAM_SOURCE=(
  "anthropics/claude-plugins-official|claude-plugins-official"
  "anthropics/claude-code|claude-code-plugins"
  "lexiaoyao20/excalidraw-generator|excalidraw-generator"
)

# Community plugins, from claudepluginhub.com. Source repo -> marketplace name is *not*
# mechanical: fcakyon/claude-codex-settings publishes itself as 'claude-settings'. The
# name after the '|' is the "name" in that repo's own .claude-plugin/marketplace.json,
# which is what 'plugin@marketplace' has to match.
COMMUNITY_KEYS=(
  "adhd-output-style" "azure-tools" "anthropic-office-skills"
  "agent-browser" "ppt-master"
)
COMMUNITY_NAME=(
  "adhd-output-style       - ADHD-friendly output: short, numbered, action first"
  "azure-tools             - Azure CLI and Bicep helpers, deployment commands"
  "anthropic-office-skills - docx, xlsx, pptx and pdf authoring skills"
  "agent-browser           - drive a real browser from an agent (vercel-labs)"
  "ppt-master              - build and edit PowerPoint decks"
)
COMMUNITY_PLUGIN=(
  "adhd-output-style@claude-settings"
  "azure-tools@claude-settings"
  "anthropic-office-skills@claude-settings"
  "agent-browser@agent-browser"
  "ppt-master@ppt-master"
)
COMMUNITY_SOURCE=(
  "fcakyon/claude-codex-settings|claude-settings"
  "fcakyon/claude-codex-settings|claude-settings"
  "fcakyon/claude-codex-settings|claude-settings"
  "vercel-labs/agent-browser|agent-browser"
  "hugohe3/ppt-master|ppt-master"
)

SKILL_STATE=(); TEAM_STATE=(); COMMUNITY_STATE=()
for _i in "${!SKILL_KEYS[@]}";     do SKILL_STATE+=(1);     done
for _i in "${!TEAM_KEYS[@]}";      do TEAM_STATE+=(1);      done
for _i in "${!COMMUNITY_KEYS[@]}"; do COMMUNITY_STATE+=(1); done
unset _i

SUB_COUNT=0
SUB_TOTAL=0
sub_tally() {
  # Sets SUB_COUNT/SUB_TOTAL rather than printing them. The main menu recomputes this for
  # every sub-row on every keypress, and a command substitution here would fork a subshell
  # each time - which is slow enough to feel on a Windows-hosted bash.
  local v states=()
  eval "states=(\"\${${1}_STATE[@]}\")"
  SUB_TOTAL=${#states[@]}
  SUB_COUNT=0
  for v in "${states[@]}"; do [ "$v" -eq 1 ] && SUB_COUNT=$((SUB_COUNT+1)); done
  return 0
}

sub_title() {
  case "$1" in
    SKILL)     printf 'Pick individual skills from this repo' ;;
    TEAM)      printf 'Pick team plugins' ;;
    COMMUNITY) printf 'Pick community plugins' ;;
  esac
}

sub_noun() {
  case "$1" in
    SKILL)     printf 'skill' ;;
    TEAM)      printf 'team plugin' ;;
    COMMUNITY) printf 'community plugin' ;;
  esac
}

sub_flag() {
  case "$1" in
    SKILL)     printf -- '--skills' ;;
    TEAM)      printf -- '--team-plugins' ;;
    COMMUNITY) printf -- '--community-plugins' ;;
  esac
}

sub_set_all() {
  local pfx="$1" val="$2" i total
  eval "total=\${#${pfx}_KEYS[@]}"
  for (( i=0; i<total; i++ )); do eval "${pfx}_STATE[$i]=$val"; done
}

sub_expand_spec() {
  # 'cloudflare,drata' | '1,4-6' | 'all' | 'none' -> sets <PREFIX>_STATE.
  local pfx="$1" spec="$2" noun token n lo hi i total found keys=()
  noun="$(sub_noun "$pfx")"
  case "$spec" in
    [Aa][Ll][Ll])     sub_set_all "$pfx" 1; return 0 ;;
    [Nn][Oo][Nn][Ee]) sub_set_all "$pfx" 0; return 0 ;;
  esac
  eval "keys=(\"\${${pfx}_KEYS[@]}\")"
  total=${#keys[@]}
  sub_set_all "$pfx" 0
  spec="${spec//,/ }"
  for token in $spec; do
    if [[ "$token" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      lo="${BASH_REMATCH[1]}"; hi="${BASH_REMATCH[2]}"
      for (( n=lo; n<=hi; n++ )); do
        [ "$n" -ge 1 ] && [ "$n" -le "$total" ] && eval "${pfx}_STATE[$((n-1))]=1"
      done
    elif [[ "$token" =~ ^[0-9]+$ ]]; then
      n="$token"
      if [ "$n" -ge 1 ] && [ "$n" -le "$total" ]; then
        eval "${pfx}_STATE[$((n-1))]=1"
      else
        warn "ignoring out-of-range $noun number '$token'"
      fi
    else
      found=0
      for i in "${!keys[@]}"; do
        if [ "${keys[$i]}" = "$token" ]; then eval "${pfx}_STATE[$i]=1"; found=1; break; fi
      done
      [ "$found" -eq 0 ] && warn "ignoring unknown $noun '$token'"
    fi
  done
  return 0
}

sub_key_selected() {
  local pfx="$1" key="$2" i keys=() states=()
  eval "keys=(\"\${${pfx}_KEYS[@]}\"); states=(\"\${${pfx}_STATE[@]}\")"
  for i in "${!keys[@]}"; do
    if [ "${keys[$i]}" = "$key" ]; then
      [ "${states[$i]}" -eq 1 ] && return 0
      return 1
    fi
  done
  return 1
}

menu_label() {
  # A sub-catalog row carries a live count, because "its 21 skills" stops being true the
  # moment someone opens the sub-picker and unticks one.
  local i="$1"
  if [ -n "${MENU_SUB[$i]}" ]; then
    sub_tally "${MENU_SUB[$i]}"
    # The template is a literal from MENU_NAME, never user input - the two %s are the
    # ticked count and the catalog size.
    # shellcheck disable=SC2059
    printf "${MENU_NAME[$i]}" "$SUB_COUNT" "$SUB_TOTAL"
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

pick_sub_interactive() {
  # Only writes back on confirm, so Q discards the whole sub-selection by doing nothing.
  local pfx="$1" i names=() states=()
  eval "names=(\"\${${pfx}_NAME[@]}\"); states=(\"\${${pfx}_STATE[@]}\")"
  PICK_LABEL=(); PICK_STATE=(); PICK_SUB=(); PICK_DEFAULT=()
  for i in "${!names[@]}"; do
    PICK_LABEL+=("${names[$i]}")
    PICK_STATE+=("${states[$i]}")
    PICK_SUB+=(0)
    PICK_DEFAULT+=(1)
  done
  PICK_CURSOR=0; PICK_TOP=0
  PICK_TITLE="$(sub_title "$pfx")"
  PICK_HINT="Enter or ← to go back to the main menu   Q to discard these changes"
  picker_run || return 1
  [ "$PICK_ACTION" = "cancel" ] && return 0
  for i in "${!PICK_STATE[@]}"; do eval "${pfx}_STATE[$i]=${PICK_STATE[$i]}"; done
  return 0
}

pick_menu_interactive() {
  local i row pfx
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
      if [ -n "${MENU_SUB[$i]}" ]; then PICK_SUB+=(1); else PICK_SUB+=(0); fi
    done
    PICK_TITLE="Select what to install"
    PICK_HINT="→ on a row ending in > picks what goes into it"
    picker_run || return 1
    for i in "${!MENU_KEYS[@]}"; do MENU_STATE[$i]="${PICK_STATE[$i]}"; done
    case "$PICK_ACTION" in
      submenu)
        # The sub-picker resets PICK_CURSOR, so remember the row first and put the cursor
        # back on it afterwards rather than dumping the user at the top of the menu.
        row="$PICK_CURSOR"
        pfx="${MENU_SUB[$row]}"
        pick_sub_interactive "$pfx" || return 1
        # Opening a sub-picker is a statement of intent: tick the parent row so a careful
        # sub-selection is not silently thrown away by an unticked parent.
        sub_tally "$pfx"
        [ "$SUB_COUNT" -gt 0 ] && MENU_STATE[$row]=1
        PICK_CURSOR="$row"
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
  printf '\033[90m  Rows ending in > hold a list: --skills cloudflare,drata\033[0m\n'
  printf '\033[90m  --team-plugins superpowers   --community-plugins ppt-master\033[0m\n'
}

select_install_items() {
  local answer=""
  # The sub-catalog flags are non-interactive answers in their own right: they settle
  # each list before anything is drawn, so they compose with --all and --non-interactive.
  if [ -n "$SKILLS_SPEC" ]; then
    sub_expand_spec SKILL "$SKILLS_SPEC"
    sub_tally SKILL
    printf '\033[90mSkills from --skills "%s" (%d of %d).\033[0m\n' \
      "$SKILLS_SPEC" "$SUB_COUNT" "$SUB_TOTAL"
  fi
  if [ -n "$TEAM_SPEC" ]; then
    sub_expand_spec TEAM "$TEAM_SPEC"
    sub_tally TEAM
    printf '\033[90mTeam plugins from --team-plugins "%s" (%d of %d).\033[0m\n' \
      "$TEAM_SPEC" "$SUB_COUNT" "$SUB_TOTAL"
  fi
  if [ -n "$COMMUNITY_SPEC" ]; then
    sub_expand_spec COMMUNITY "$COMMUNITY_SPEC"
    sub_tally COMMUNITY
    printf '\033[90mCommunity plugins from --community-plugins "%s" (%d of %d).\033[0m\n' \
      "$COMMUNITY_SPEC" "$SUB_COUNT" "$SUB_TOTAL"
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

show_sub_selection() {
  # Only worth spelling out when it is a subset - the row label already reads "N of N".
  local pfx="$1" i keys=() states=()
  sub_tally "$pfx"
  if [ "$SUB_COUNT" -eq 0 ]; then
    warn "nothing ticked in this list - it will be skipped. Re-run with $(sub_flag "$pfx") all to get everything."
    return 0
  fi
  [ "$SUB_COUNT" -eq "$SUB_TOTAL" ] && return 0
  eval "keys=(\"\${${pfx}_KEYS[@]}\"); states=(\"\${${pfx}_STATE[@]}\")"
  for i in "${!keys[@]}"; do
    [ "${states[$i]}" -eq 1 ] && printf '        - %s\n' "${keys[$i]}"
  done
  return 0
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
    is_selected "${MENU_KEYS[$i]}" || continue
    printf '    - %s\n' "$(menu_label "$i")"
    [ -n "${MENU_SUB[$i]}" ] && show_sub_selection "${MENU_SUB[$i]}"
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
  # always say no. Look it up in the skill catalog instead, and only count it when
  # this repo's marketplace item is itself selected.
  is_selected "own-skills" || return 1
  sub_key_selected SKILL "$1"
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
CLAUDE_ITEMS="own-skills team find-skills community claude-code-setup claude-mem voltagent supabase"
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
  sub_tally SKILL
  if [ "$SUB_COUNT" -eq 0 ]; then
    warn "no skills selected from this repo - marketplace registered, nothing installed."
  fi
  for idx in "${!SKILL_KEYS[@]}"; do
    [ "${SKILL_STATE[$idx]}" -eq 1 ] || continue
    plugin="${SKILL_KEYS[$idx]}"
    run_step "Plugin: ${plugin}@useful-claude-add-ons" install_plugin "${plugin}@useful-claude-add-ons"
  done

  # notify is the one skill with machine-level setup (a config file and a bot token),
  # so it gets a post-install step when the user asked for it up front.
  if [ "$NOTIFY_SETUP" = "1" ] && skill_selected "notify"; then
    run_step "Set up the notify skill" setup_notify
  fi
fi

# --- 4. Team marketplaces and plugins ----------------------------------------
install_sub_catalog() {
  # Registers only the marketplaces the ticked plugins actually need. Unticking every
  # plugin from one source leaves that source unregistered rather than dangling, and a
  # source shared by several plugins is still only added once. add_marketplace is a no-op
  # when the marketplace is already there, so overlaps with other menu items are free.
  local pfx="$1" i keys=() plugins=() sources=() states=() added=" " src name
  eval "keys=(\"\${${pfx}_KEYS[@]}\");     plugins=(\"\${${pfx}_PLUGIN[@]}\")"
  eval "sources=(\"\${${pfx}_SOURCE[@]}\"); states=(\"\${${pfx}_STATE[@]}\")"
  for i in "${!keys[@]}"; do
    [ "${states[$i]}" -eq 1 ] || continue
    src="${sources[$i]%%|*}"
    name="${sources[$i]#*|}"
    case "$added" in
      *" $name "*) ;;
      *) run_step "Marketplace: $src" add_marketplace "$src" "$name"
         added="$added$name " ;;
    esac
    run_step "Plugin: ${plugins[$i]}" install_plugin "${plugins[$i]}"
  done
}

if is_selected "team"; then
  sub_tally TEAM
  if [ "$SUB_COUNT" -eq 0 ]; then
    warn "no team plugins ticked - nothing to install for that item."
  fi
  install_sub_catalog TEAM
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
# Installed with native 'claude plugin' commands, from the COMMUNITY_* catalog next to
# the menu - so unticking a plugin in the sub-picker also drops its marketplace when
# nothing else needs it.
if is_selected "community"; then
  sub_tally COMMUNITY
  if [ "$SUB_COUNT" -eq 0 ]; then
    warn "no community plugins ticked - nothing to install for that item."
  fi
  install_sub_catalog COMMUNITY
fi

# --- 7. claude-code-setup ----------------------------------------------------
# Ships inside anthropics/claude-plugins-official, which the team item also registers -
# add_marketplace is a no-op when it is already there, so this item works whether or not
# item 4 was selected.
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
install_bun() {
  # claude-mem's hooks run its worker under Bun (package.json declares engines.bun
  # >= 1.0.0) via scripts/bun-runner.js, which resolves the interpreter from PATH and
  # only then falls back to $HOME/.bun/bin/bun. Neither this script nor the plugin ever
  # installed it, so on a fresh machine every claude-mem hook died with "Bun not found".
  if have bun; then
    skip "bun already present ($(command -v bun))"
    return 0
  fi
  # No distro ships a bun package, so there is no as_root path here: bun's own installer
  # is per-user and writes $HOME/.bun/bin/bun, which is bun-runner's fallback location.
  # npm -g is preferred when present because it keeps bun on the same PATH as node.
  if have npm; then
    npm install -g bun || return 1
  elif have curl; then
    curl -fsSL https://bun.sh/install | bash || return 1
  else
    warn "neither npm nor curl found - install bun manually (https://bun.sh) or claude-mem's hooks will fail."
    return 1
  fi
  export PATH="$HOME/.bun/bin:$PATH"
  if ! have bun && [ ! -x "$HOME/.bun/bin/bun" ]; then
    warn "bun still not found after installing - open a new shell and re-run."
    return 1
  fi
  COUNT_INSTALLED=$((COUNT_INSTALLED+1))
  ok "installed bun $(bun --version 2>/dev/null)"
}

if is_selected "claude-mem"; then
  # Bun is the one dependency claude-mem's own hooks cannot install for themselves.
  run_step "Install Bun (claude-mem worker runtime)" install_bun
  run_step "Marketplace: thedotmack/claude-mem" add_marketplace "thedotmack/claude-mem" "thedotmack"
  run_step "Plugin: claude-mem@thedotmack" install_plugin "claude-mem@thedotmack"
  run_step "Configure claude-mem worker port" set_claude_mem_worker_port "37790"
fi

# --- 10. VoltAgent subagents -------------------------------------------------
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

# --- 11-13. Optional MCP servers ---------------------------------------------
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

# --- 14. Supabase ------------------------------------------------------------
# Ships inside anthropics/claude-plugins-official, the same marketplace items 4 and 7
# register - add_marketplace is a no-op when it is already there, so this item stands
# on its own. install_plugin does the "already installed?" check.
if is_selected "supabase"; then
  run_step "Marketplace: anthropics/claude-plugins-official" \
    add_marketplace "anthropics/claude-plugins-official" "claude-plugins-official"
  run_step "Plugin: supabase@claude-plugins-official" \
    install_plugin "supabase@claude-plugins-official"
fi

# --- 15. Context7 ------------------------------------------------------------
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

# --- 16. Playwright CLI ------------------------------------------------------
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

# --- 17. SkillUI -------------------------------------------------------------
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

# --- 18. Strix ---------------------------------------------------------------
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
