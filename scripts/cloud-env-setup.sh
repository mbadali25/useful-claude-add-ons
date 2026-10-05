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
# One failing step does not stop the rest: each step's error is printed under a
# FAILED line and listed again in the summary. The script exits 1 only when a CORE
# step failed (git, codex, py-libs, ruff, pylint); an optional tool failing is
# reported but exits 0. Steps run most-needed first.
#
# Versions follow what CI pins (.github/workflows/pylint.yml, verify-gate.yml) and
# what .crew/verify.json's preReview linters call, so a local run agrees with CI.
#
# Codex sign-in is NOT done here: the device-code flow needs a person to approve it,
# and the setup script runs before anyone is watching. After the session starts:
#     codex login --device-auth
# Requires auth.openai.com, chatgpt.com and api.openai.com in the environment's
# allowed domains; the default "trusted" network policy denies them.
set -uo pipefail

RUFF_SPEC='ruff~=0.16.0'          # pylint.yml
PYLINT_SPEC='pylint~=4.0'         # pylint.yml
PYTEST_SPEC='pytest~=8.0'         # every CI job that runs pytest
SHELLCHECK_SPEC='shellcheck-py==0.11.0.1'   # .crew/verify.json preReview
ACTIONLINT_SPEC='actionlint-py==1.7.12.25'  # .crew/verify.json preReview
ACTIONLINT_GO='github.com/rhysd/actionlint/cmd/actionlint@v1.7.12'

export PATH="$HOME/.local/bin:$PATH"
LOG_DIR=$(mktemp -d)
failed=()
CORE=" git codex py-libs ruff pylint "

log() { printf '[cloud-env-setup] %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# step <name> <function>: run it with its output captured; on failure print that
# output and carry on.
step() {
  local name=$1 out="$LOG_DIR/$1.log"; shift
  if "$@" >"$out" 2>&1; then
    grep '^\[cloud-env-setup\]' "$out" || true
  else
    local rc=$?
    log "FAILED: $name (exit $rc) - last lines of its output:"
    tail -n 15 "$out" | sed 's/^/    /'
    failed+=("$name")
  fi
}

# ---- git ---------------------------------------------------------------------
# rerere: record how a conflict was resolved and replay it next time the same
# hunk conflicts - the base-branch merges in the PR-driving loop hit the same
# hunks repeatedly. zdiff3 shows the common ancestor of a conflict.
git_config() {
  git config --global rerere.enabled true &&
  git config --global rerere.autoupdate true &&
  git config --global merge.conflictStyle zdiff3 &&
  git config --global fetch.prune true &&
  git config --global diff.algorithm histogram &&
  log "git: rerere on (autoupdate), zdiff3, fetch.prune, histogram diff"
}

# ---- Node ---------------------------------------------------------------------
codex_cli() {
  if have codex; then
    log "codex: already installed ($(codex --version 2>/dev/null | head -1))"
  else
    npm install -g @openai/codex && log "codex: installed ($(codex --version 2>/dev/null | head -1))"
  fi
}

# ---- Python: libraries the suites import --------------------------------------
# .crew/verify.json runs `python3 -m pytest`, which needs pytest importable by the
# system python3, not just a pytest CLI on PATH. Same set as verify-gate.yml.
py_libs() {
  local libs=("$PYTEST_SPEC" pytest-xdist pyyaml python-docx numpy pillow requests markdown)
  if python3 -c 'import pytest, xdist, yaml, docx, numpy, PIL, requests, markdown' 2>/dev/null; then
    log "python3: suite libraries already importable"
  else
    uv pip install --system --break-system-packages "${libs[@]}" && log "python3: installed ${libs[*]}"
  fi
}

# ---- Python: CLIs as isolated uv tools ----------------------------------------
# One venv per tool, so pinning ruff for CI parity cannot fight another package.
# `uv tool install` on an installed tool re-pins it if the spec moved.
uv_tool() {  # uv_tool <spec>
  local spec=$1 pkg=${1%%[~=<>]*}
  if uv tool list 2>/dev/null | grep -q "^${pkg} v"; then
    uv tool install "$spec" && log "uv tool: $spec already installed"
  else
    uv tool install --force "$spec" && log "uv tool: installed $spec"
  fi
}

# actionlint-py has no wheel: building it downloads the binary from github.com
# release assets, which the setup phase's network can refuse. Fall back to
# building from source through proxy.golang.org, which the proxy always allows.
# Note .crew/verify.json's preReview calls `uvx --from actionlint-py` itself, so
# when the wheel route fails here it fails there too; this fallback only gives
# you an `actionlint` on PATH to run by hand.
actionlint_tool() {
  if have actionlint; then log "actionlint: already installed ($(actionlint --version | head -1))"; return; fi
  if uv_tool "$ACTIONLINT_SPEC"; then return; fi
  log "actionlint: $ACTIONLINT_SPEC failed to build, trying go install"
  have go && GOBIN="$HOME/.local/bin" go install "$ACTIONLINT_GO" &&
    log "actionlint: installed via go install $ACTIONLINT_GO"
}

# ---- apt tools ---------------------------------------------------------------
apt_tools() {
  local pkgs=() need_pwsh=0
  have fdfind || pkgs+=(fd-find)
  have hyperfine || pkgs+=(hyperfine)
  have pwsh || need_pwsh=1
  if [ "${#pkgs[@]}" -eq 0 ] && [ "$need_pwsh" = 0 ]; then
    log "apt: fd-find, hyperfine, pwsh already installed"
  else
    if [ "$need_pwsh" = 1 ]; then
      # Microsoft's apt repo; github.com release downloads are not on the proxy allowlist.
      # shellcheck disable=SC1091
      . /etc/os-release
      curl -fsSL "https://packages.microsoft.com/config/ubuntu/${VERSION_ID}/packages-microsoft-prod.deb" \
        -o /tmp/packages-microsoft-prod.deb &&
      dpkg -i /tmp/packages-microsoft-prod.deb || return
      pkgs+=(powershell)
    fi
    apt-get update -qq &&
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${pkgs[@]}" &&
    log "apt: installed ${pkgs[*]}" || return
  fi
  # Ubuntu names the binary fdfind; give it its usual name.
  if have fdfind && ! have fd; then ln -sf "$(command -v fdfind)" /usr/local/bin/fd; fi
}

path_setup() {
  # uv tool installs land in ~/.local/bin; make sure every shell sees them.
  grep -qs 'HOME/.local/bin' "$HOME/.bashrc" ||
    echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$HOME/.bashrc"
  log "path: ~/.local/bin on PATH for new shells"
}

# Most-needed first.
step git        git_config
step codex      codex_cli
step py-libs    py_libs
step ruff       uv_tool "$RUFF_SPEC"
step pylint     uv_tool "$PYLINT_SPEC"
step path       path_setup
step shellcheck uv_tool "$SHELLCHECK_SPEC"
step actionlint actionlint_tool
step pre-commit uv_tool pre-commit
step graphify   uv_tool graphifyy   # PyPI name has two y's; installs `graphify`
step apt        apt_tools

if [ "${#failed[@]}" -gt 0 ]; then
  log "done with FAILURES: ${failed[*]} (full logs: $LOG_DIR)"
  for f in "${failed[@]}"; do case $CORE in *" $f "*) exit 1;; esac; done
  log "only optional tools failed; exiting 0"
  exit 0
fi
log "done, all steps OK"
