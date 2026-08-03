#!/usr/bin/env bash
# Bootstraps a Linux machine for this repo's skills: git/nodejs/npm/python, the Claude
# Code CLI itself (with its path exported for future shells), and the team's standard
# Claude Code plugin marketplaces. Idempotent - safe to re-run.
#
# Everything is detected before it is installed:
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
#   --skip-bootstrap    skip all marketplace/plugin/optional bootstrap steps
#   --non-interactive   take the default answer for every prompt (CI/unattended)
#   --no-update         never update an already-installed plugin, only report it
#   --scope <scope>     scope for marketplace/plugin installs: user|project|local (default: user)

set -uo pipefail

SKIP_BOOTSTRAP=0
NON_INTERACTIVE=0
NO_UPDATE=0
INSTALL_SCOPE="user"   # machine-wide by default, not per-project

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-bootstrap)  SKIP_BOOTSTRAP=1 ;;
    --non-interactive) NON_INTERACTIVE=1 ;;
    --no-update)       NO_UPDATE=1 ;;
    --scope)           INSTALL_SCOPE="${2:-user}"; shift ;;
    *) echo "Unknown option: $1" >&2 ;;
  esac
  shift
done

FAILED_STEPS=()
COUNT_INSTALLED=0
COUNT_UPDATED=0
COUNT_SKIPPED=0

step()   { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok()     { printf '    \033[32mOK:\033[0m %s\n' "$1"; }
warn()   { printf '    \033[33mWARN:\033[0m %s\n' "$1"; }
skip()   { printf '    \033[90mSKIP:\033[0m %s\n' "$1"; COUNT_SKIPPED=$((COUNT_SKIPPED+1)); }

ask_yes_no() {
  local prompt="$1" default="${2:-N}" reply suffix="[y/N]"
  [ "$default" = "Y" ] && suffix="[Y/n]"
  if [ "$NON_INTERACTIVE" -eq 1 ]; then
    printf '\033[90m%s %s -> %s (non-interactive)\033[0m\n' "$prompt" "$suffix" "$default"
    [ "$default" = "Y" ] && return 0 || return 1
  fi
  read -r -p "$prompt $suffix " reply
  reply="${reply:-$default}"
  case "$reply" in
    [Yy]*) return 0 ;;
    *) return 1 ;;
  esac
}

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

# --- Detection: user-level skills --------------------------------------------
# Some things (the 'skills' CLI) install as plain user-level skills rather than as
# Claude Code plugins, so they never appear in 'claude plugin list' - detection for
# those is a filesystem check against the user-level skills directory.
claude_skills_dir() { printf '%s/skills' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; }
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
    claude plugin update "$name" >/dev/null 2>&1
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
run_step "Install git, nodejs, npm, python (missing only)" install_packages

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
run_step "Install Claude Code CLI" install_claude_cli

# --- 3. Export claude path ---------------------------------------------------
export_claude_path() {
  local npm_prefix bin_dir
  npm_prefix="$(npm config get prefix)"
  bin_dir="${npm_prefix}/bin"

  export PATH="${bin_dir}:${PATH}"

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

  if have claude; then
    ok "claude resolved at $(command -v claude)"
  else
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' (or open a new shell)."
  fi
}
run_step "Export Claude Code CLI path" export_claude_path

# --- Bootstrap ---------------------------------------------------------------
if [ "$SKIP_BOOTSTRAP" -eq 1 ]; then
  step "Skipping all marketplace/plugin bootstrap (--skip-bootstrap)"
elif ! claude_available; then
  step "Skipping marketplace/plugin bootstrap"
  warn "claude is not on PATH in this shell - run 'source ~/.bashrc' and re-run to install marketplaces and plugins."
else
  load_marketplaces
  load_plugins

  # --- 4. This repo's own marketplace and skills -----------------------------
  run_step "Add this repo as a Claude Code marketplace" \
    add_marketplace "mbadali25/useful-claude-add-ons" "useful-claude-add-ons"

  # Keep in sync with .claude-plugin/marketplace.json.
  own_plugins=(
    "aws-opensearch"
    "bitbucket"
    "checkpoint-email"
    "cisco-meraki"
    "claude-code-defaults"
    "cloudflare"
    "drata"
    "i-have-adhd"
    "infra-work-ticketing"
    "intune-graph"
    "mermaid-svg-bitbucket"
    "repo-docs"
    "shipstation"
    "sophos-central"
    "terraform-docs-readme"
    "visio-diagrams"
    "wazuh-onprem"
    "web-testing-playwright"
    "work-log-reporter"
  )
  for plugin in "${own_plugins[@]}"; do
    run_step "Plugin: ${plugin}@useful-claude-add-ons" install_plugin "${plugin}@useful-claude-add-ons"
  done

  # --- 5. Team marketplaces and plugins --------------------------------------
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

  install_find_skills() {
    local dir present=0 prompt
    dir="$(claude_skills_dir)/find-skills"
    user_skill_installed "find-skills" && present=1
    if [ "$present" -eq 1 ] && [ "$NO_UPDATE" -eq 1 ]; then
      skip "find-skills already installed at $dir (--no-update set)"
      return 0
    fi
    if [ "$present" -eq 1 ]; then
      prompt="find-skills is already installed at $dir. Re-run its installer to pick up updates?"
    else
      prompt="Install the find-skills skill (vercel-labs/skills)?"
    fi
    if ! ask_yes_no "$prompt" "Y"; then
      skip "find-skills"
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
  run_step "Skill: find-skills (vercel-labs/skills)" install_find_skills

  # --- 6. Community marketplaces (from claudepluginhub.com) ------------------
  # Installed with native 'claude plugin' commands. Source repo -> marketplace name is
  # *not* mechanical: fcakyon/claude-codex-settings publishes itself as 'claude-settings'.
  # The second field below is the "name" in that repo's own .claude-plugin/marketplace.json,
  # which is what 'plugin@marketplace' has to match.
  if ask_yes_no "Install the community marketplaces and plugins (claudepluginhub.com)?" "Y"; then
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
  else
    skip "community marketplaces and plugins"
  fi

  # --- 7. Optional tooling ---------------------------------------------------
  # claude-mem supports the plugin-marketplace path as a first-class alternative to its
  # 'npx claude-mem install' bootstrapper (see its README) - the plugin's own hooks handle
  # worker/dependency setup on first run.
  if ask_yes_no "Install claude-mem (persistent cross-session memory)?" "Y"; then
    run_step "Marketplace: thedotmack/claude-mem" add_marketplace "thedotmack/claude-mem" "thedotmack"
    run_step "Plugin: claude-mem@thedotmack" install_plugin "claude-mem@thedotmack"
  else
    skip "claude-mem"
  fi

  install_gsd() {
    local state="$HOME/.claude/gsd-install-state.json"
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
  if ask_yes_no "Install GSD (@opengsd/gsd-core)?" "Y"; then
    run_step "Install GSD core" install_gsd
  else
    skip "GSD"
  fi

  # The repo publishes itself as the 'voltagent-subagents' marketplace, with its 154
  # subagents split across ten category plugins. Installing them as plugins replaces the
  # old 'git clone + bash install-agents.sh' path, which needed an interactive TTY and a
  # writable ~/repos checkout.
  if ask_yes_no "Install the VoltAgent awesome-claude-code-subagents collection?" "Y"; then
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
  else
    skip "VoltAgent awesome-claude-code-subagents"
  fi
fi

# --- 8. Optional MCP servers -------------------------------------------------
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
  claude mcp add aws-api -- uvx awslabs.aws-api-mcp-server@latest
  ok "Added aws-api MCP server. Make sure AWS credentials are configured (aws configure)."
}
if ask_yes_no "Install the AWS MCP server (awslabs.aws-api-mcp-server) and register it with Claude Code?"; then
  run_step "Install AWS MCP server" install_aws_mcp
fi

install_azure_mcp() {
  if ! have claude; then
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' and re-run this script."
    return 1
  fi
  claude mcp add azure -- npx -y @azure/mcp@latest server start
  ok "Added azure MCP server. Make sure you have run 'az login' before using it."
}
if ask_yes_no "Install the Azure MCP server (@azure/mcp) and register it with Claude Code?"; then
  run_step "Install Azure MCP server" install_azure_mcp
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
