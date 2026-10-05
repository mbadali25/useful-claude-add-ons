#!/usr/bin/env bash
# Setup script for a Claude Code cloud environment (claude.ai/code) working on this repo.
#
# NOT a hook and not run by anything in this repo. Paste the line below into the
# environment's settings (environment menu in the session title bar -> Edit -> Setup script):
#
#     bash scripts/cloud-env-setup.sh
#
# It runs as root once per new container, before Claude starts. Every step is
# idempotent and reports "already installed" when there is nothing to do, so it is
# also safe to re-run by hand mid-session.
#
# Versions follow what CI pins (.github/workflows/pylint.yml, verify-gate.yml) and
# what .crew/verify.json's preReview linters call, so a local run agrees with CI.
#
# Codex sign-in is NOT done here: the device-code flow needs a person to approve it,
# and the setup script runs before anyone is watching. After the session starts:
#     codex login --device-auth
# Requires auth.openai.com, chatgpt.com and api.openai.com in the environment's
# allowed domains; the default "trusted" network policy denies them.
set -euo pipefail

RUFF_SPEC='ruff~=0.16.0'          # pylint.yml
PYLINT_SPEC='pylint~=4.0'         # pylint.yml, verify-gate.yml
PYTEST_SPEC='pytest~=8.0'         # every CI job that runs pytest
SHELLCHECK_SPEC='shellcheck-py==0.11.0.1'   # .crew/verify.json preReview
ACTIONLINT_SPEC='actionlint-py==1.7.12.25'  # .crew/verify.json preReview

log() { printf '[cloud-env-setup] %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---- git ---------------------------------------------------------------------
# rerere: record how a conflict was resolved and replay it next time the same
# hunk conflicts - the base-branch merges in the PR-driving loop hit the same
# hunks repeatedly. zdiff3 shows the common ancestor, which rerere's recorded
# resolutions are keyed on anyway.
git config --global rerere.enabled true
git config --global rerere.autoupdate true
git config --global merge.conflictStyle zdiff3
git config --global fetch.prune true
git config --global diff.algorithm histogram
log "git: rerere on (autoupdate), zdiff3, fetch.prune, histogram diff"

# ---- apt tools ---------------------------------------------------------------
apt_pkgs=()
have fdfind || apt_pkgs+=(fd-find)
have hyperfine || apt_pkgs+=(hyperfine)
have pwsh || need_pwsh=1
if [ "${#apt_pkgs[@]}" -gt 0 ] || [ "${need_pwsh:-0}" = 1 ]; then
  if [ "${need_pwsh:-0}" = 1 ]; then
    # Microsoft's apt repo; github.com release downloads are not on the proxy allowlist.
    . /etc/os-release
    curl -fsSL "https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb" \
      -o /tmp/packages-microsoft-prod.deb
    dpkg -i /tmp/packages-microsoft-prod.deb >/dev/null
    apt_pkgs+=(powershell)
  fi
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${apt_pkgs[@]}" >/dev/null
  log "apt: installed ${apt_pkgs[*]}"
else
  log "apt: fd-find, hyperfine, pwsh already installed"
fi
# Ubuntu names the binary fdfind; give it its usual name.
if have fdfind && ! have fd; then ln -sf "$(command -v fdfind)" /usr/local/bin/fd; fi

# ---- Python: CLIs as isolated uv tools ----------------------------------------
# One venv per tool, so pinning ruff for CI parity cannot fight another package.
uv_tool() {  # uv_tool <executable> <spec> [extra uv args...]
  local exe=$1 spec=$2; shift 2
  if uv tool list 2>/dev/null | grep -qE "^${spec%%[~=<>]*} v"; then
    uv tool install --quiet "$spec" "$@" >/dev/null   # re-pins if the spec moved
    log "uv tool: $spec already installed"
  else
    uv tool install --quiet --force "$spec" "$@" >/dev/null
    log "uv tool: installed $spec ($exe)"
  fi
}
uv_tool ruff "$RUFF_SPEC"
uv_tool pylint "$PYLINT_SPEC"
uv_tool shellcheck "$SHELLCHECK_SPEC"
uv_tool actionlint "$ACTIONLINT_SPEC"
uv_tool pre-commit pre-commit
uv_tool graphify graphifyy   # PyPI name has two y's; installs `graphify`

# ---- Python: libraries the suites import --------------------------------------
# .crew/verify.json runs `python3 -m pytest`, which needs pytest importable by the
# system python3, not just a pytest CLI on PATH. Same set as verify-gate.yml.
py_libs=("$PYTEST_SPEC" pytest-xdist pyyaml python-docx numpy pillow requests markdown)
if python3 -c 'import pytest, xdist, yaml, docx, numpy, PIL, requests, markdown' 2>/dev/null; then
  log "python3: suite libraries already importable"
else
  uv pip install --quiet --system --break-system-packages "${py_libs[@]}"
  log "python3: installed ${py_libs[*]}"
fi

# ---- Node ---------------------------------------------------------------------
if have codex; then
  log "codex: already installed ($(codex --version 2>/dev/null | head -1))"
else
  npm install -g --silent @openai/codex
  log "codex: installed ($(codex --version 2>/dev/null | head -1))"
fi

# uv tool installs land in ~/.local/bin; make sure every shell sees them.
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *)
  grep -qs 'local/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.bashrc";;
esac

log "done"
