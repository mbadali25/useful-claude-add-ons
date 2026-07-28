#!/usr/bin/env bash
# Bootstraps a Linux machine for this repo's skills: git/nodejs/npm/python, the Claude
# Code CLI itself (with its path exported for future shells), and the team's standard
# Claude Code plugin marketplaces. Idempotent - safe to re-run.
#
# Usage: ./scripts/install-prerequisites.sh [--skip-bootstrap]

set -uo pipefail

SKIP_BOOTSTRAP=0
for arg in "$@"; do
  case "$arg" in
    --skip-bootstrap) SKIP_BOOTSTRAP=1 ;;
  esac
done

FAILED_STEPS=()

step()   { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok()     { printf '    \033[32mOK:\033[0m %s\n' "$1"; }
warn()   { printf '    \033[33mWARN:\033[0m %s\n' "$1"; }

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

# --- 1. OS packages: git, nodejs, npm, python -------------------------------
install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    as_root apt-get update -y
    as_root apt-get install -y git nodejs npm python3 python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    as_root dnf install -y git nodejs npm python3 python3-pip
  elif command -v yum >/dev/null 2>&1; then
    as_root yum install -y git nodejs npm python3 python3-pip
  elif command -v pacman >/dev/null 2>&1; then
    as_root pacman -Sy --noconfirm git nodejs npm python python-pip
  elif command -v zypper >/dev/null 2>&1; then
    as_root zypper install -y git nodejs npm python3 python3-pip
  elif command -v apk >/dev/null 2>&1; then
    as_root apk add --no-cache git nodejs npm python3 py3-pip
  else
    warn "No supported package manager found (apt-get/dnf/yum/pacman/zypper/apk). Install git, nodejs, npm, and python manually."
    return 1
  fi
}
run_step "Install git, nodejs, npm, python" install_packages

# --- 2. Claude Code CLI ------------------------------------------------------
install_claude_cli() {
  if ! command -v npm >/dev/null 2>&1; then
    warn "npm not found on PATH - cannot install Claude Code CLI."
    return 1
  fi
  if command -v claude >/dev/null 2>&1; then
    ok "claude already installed ($(claude --version 2>/dev/null || echo 'version unknown'))"
    return 0
  fi
  local npm_prefix
  npm_prefix="$(npm config get prefix)"
  if [ -w "$npm_prefix" ]; then
    npm install -g @anthropic-ai/claude-code
  else
    as_root npm install -g @anthropic-ai/claude-code
  fi
}
run_step "Install Claude Code CLI" install_claude_cli

# --- 3. Export claude path -----------------------------------------------
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
        ok "'$bin_dir' already exported in $rc"
      fi
    fi
  done

  if command -v claude >/dev/null 2>&1; then
    ok "claude resolved at $(command -v claude)"
  else
    warn "claude not found on PATH in this shell - run 'source ~/.bashrc' (or open a new shell)."
  fi
}
run_step "Export Claude Code CLI path" export_claude_path

# --- 4. Team plugin/marketplace bootstrap -----------------------------------
if [ "$SKIP_BOOTSTRAP" -eq 1 ]; then
  step "Skipping plugin/marketplace bootstrap (--skip-bootstrap)"
else
  bootstrap_commands=(
    "claude plugin marketplace add obra/superpowers-marketplace"
    "claude plugin install superpowers@superpowers-marketplace"
    "npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code"
    "npx @opengsd/gsd-core@latest"
    "npx claude-mem install"
    "claude plugin marketplace add anthropics/claude-code"
    "claude plugin install frontend-design@claude-code-plugins"
    "claude plugin marketplace add lexiaoyao20/excalidraw-generator"
    "claude plugin install excalidraw-generator@excalidraw-generator"
    "claude plugin marketplace add obra/superpowers-marketplace"
    "claude plugin install superpowers@claude-plugins-official"
    "claude plugin marketplace add mbadali25/useful-claude-add-ons"
  )
  for cmd in "${bootstrap_commands[@]}"; do
    run_step "$cmd" bash -c "$cmd"
  done
fi

# --- Summary -----------------------------------------------------------------
echo ""
if [ ${#FAILED_STEPS[@]} -eq 0 ]; then
  printf '\033[32mAll steps completed. Run "source ~/.bashrc" or open a new shell to pick up PATH changes.\033[0m\n'
else
  printf '\033[33mCompleted with %d failed step(s):\033[0m\n' "${#FAILED_STEPS[@]}"
  for s in "${FAILED_STEPS[@]}"; do echo "  - $s"; done
  printf '\033[33mRe-run this script after resolving the above; earlier successful steps are safe to repeat.\033[0m\n'
fi
