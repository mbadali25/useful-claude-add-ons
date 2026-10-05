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
# reported but exits 0. Steps run most-needed first. The last lines list every
# tool the steps install as "ok" or "MISSING", so one run doubles as a doctor.
#
# The gizmoduck step runs plugin/gizmoduck/bootstrap.sh, the slowest step by far.
# Skip it with SKIP_GIZMODUCK=1 (prefix the pasted line: SKIP_GIZMODUCK=1 bash ...).
#
# Network as measured in a cloud session (2026-10-05): api.github.com and
# github.com/*/releases/latest answer 403; versioned release downloads, git over
# https, apt, PyPI, npm and proxy.golang.org work. So a "latest" version is
# resolved with `git ls-remote --tags`, never the GitHub API.
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
MERMAID_VERSION='12.0.0'          # verify-gate.yml
PWSH_DIR='/opt/microsoft/powershell/7'

# This image ships /tmp as 755 root:root, so apt's _apt sandbox user cannot write
# its key-check temp files there and `apt-get update` fails. Run that step as root
# instead of loosening /tmp. The lock timeout waits out an apt run already going.
APT=(apt-get -o APT::Sandbox::User=root -o DPkg::Lock::Timeout=600)

# Session start waits on this script, so no download may hang it: curl gives up
# after 10 minutes, git when a transfer stalls under 1 KB/s for 30 seconds.
CURL=(curl -fsSL --connect-timeout 20 --max-time 600)
export GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=30
export DEBIAN_FRONTEND=noninteractive

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PATH="$HOME/.local/bin:$PATH"
LOG_DIR=$(mktemp -d)
failed=()
CORE=" git codex py-libs ruff pylint "

log() { printf '[cloud-env-setup] %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# latest_tag <owner/repo>: newest stable vX.Y.Z tag, through git (the API is 403).
latest_tag() {
  timeout 120 git ls-remote --tags --refs "https://github.com/$1.git" |
    sed 's#.*refs/tags/##' | grep -E '^v?[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n 1
}

# step <name> <function>: run it with its output captured; on failure print that
# output and carry on. No stdin: nothing here may stop to ask a question.
step() {
  local name=$1 out="$LOG_DIR/$1.log"; shift
  if "$@" </dev/null >"$out" 2>&1; then
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
# A pytest other than 8.x counts as missing, so the install re-pins it.
#
# The base image also ships pytest 9 as a uv tool in ~/.local/bin: isolated (no
# xdist) and ahead of this pytest on PATH, so `pytest -n auto` breaks. Drop it,
# then check what PATH actually resolves; a wrong pytest fails this CORE step.
py_libs() {
  local libs=("$PYTEST_SPEC" pytest-xdist pyyaml python-docx numpy pillow requests markdown) pv
  if python3 -c 'import pytest, xdist, yaml, docx, numpy, PIL, requests, markdown
assert pytest.__version__.startswith("8.")' 2>/dev/null; then
    log "python3: suite libraries already importable"
  else
    uv pip install --system --break-system-packages "${libs[@]}" && log "python3: installed ${libs[*]}" || return
  fi
  if uv tool list 2>/dev/null | grep -q '^pytest v'; then
    uv tool uninstall pytest && log "pytest: removed the image's uv-tool pytest (shadowed $PYTEST_SPEC)" || return
  fi
  hash -r
  pv=$(pytest --version 2>&1)
  case $pv in "pytest 8."*) ;; *) echo "pytest on PATH is not 8.x: $(command -v pytest): $pv" >&2; return 1;; esac
  log "python3: PATH resolves $pv"
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

# Check what PATH actually resolves: another ruff earlier on PATH fails this CORE
# step loudly rather than letting a local run disagree with CI.
ruff_tool() {
  uv_tool "$RUFF_SPEC" || return
  hash -r
  local rv
  rv=$(ruff --version 2>&1)
  case $rv in "ruff 0.16."*) ;; *) echo "ruff on PATH is not 0.16.x: $(command -v ruff): $rv" >&2; return 1;; esac
  log "ruff: PATH resolves $rv"
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
# apt_install <pkg>...: update, install, then clean - disk is a fixed per-session
# allowance, and the .deb cache is dead weight once installed.
apt_install() {
  "${APT[@]}" update -qq &&
  "${APT[@]}" install -y -qq "$@" &&
  log "apt: installed $*" || return
  apt-get clean || true
}

# bubblewrap (bwrap) is Codex's sandbox. Without it on PATH, every codex run warns
# and falls back to a bundled copy.
apt_tools() {
  local pkgs=()
  have bwrap || pkgs+=(bubblewrap)
  have fdfind || pkgs+=(fd-find)
  have hyperfine || pkgs+=(hyperfine)
  if [ "${#pkgs[@]}" -eq 0 ]; then
    log "apt: bubblewrap, fd-find, hyperfine already installed"
  else
    apt_install "${pkgs[@]}" || return
  fi
  # Ubuntu names the binary fdfind; give it its usual name.
  if have fdfind && ! have fd; then ln -sf "$(command -v fdfind)" /usr/local/bin/fd; fi
}

# ---- PowerShell 7 ------------------------------------------------------------
# crew's .ps1 hooks, install-prerequisites.ps1 and the suites' pwsh cases need it.
# The tarball from the newest stable tag's release, checked against that
# release's hashes.sha256 and unpacked where Microsoft's package puts it. If the
# download is refused (the setup phase's network can differ from the session's),
# the hash is missing or wrong, or the unpacked pwsh cannot start (no libicu, say),
# fall back to Microsoft's apt repo. Installed means pwsh reports a version.
# shellcheck disable=SC2016  # PowerShell's $, not bash's
pwsh_version() { "${1:-pwsh}" -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()' 2>/dev/null; }

# pwsh_tarball <tag> <ver> <arch>
pwsh_tarball() {
  local file="powershell-$2-linux-$3.tar.gz" base="https://github.com/PowerShell/PowerShell/releases/download/$1"
  local tgz="$LOG_DIR/powershell.tar.gz" want got rc
  "${CURL[@]}" -o "$tgz" "$base/$file" || return
  # hashes.sha256 is UTF-16LE with a BOM and CRLF line ends; lines read "<hash> *<file>".
  want=$("${CURL[@]}" "$base/hashes.sha256" | iconv -f UTF-16 -t UTF-8 | tr -d '\r' |
    awk -v f="$file" '{n=$2; sub(/^\*/, "", n)} n == f {print tolower($1)}')
  got=$(sha256sum "$tgz" | cut -d' ' -f1)
  if [ -z "$want" ] || [ "$want" != "$got" ]; then
    if [ -z "$want" ]; then echo "pwsh: no sha256 for $file in hashes.sha256" >&2
    else echo "pwsh: sha256 of $file is $got, hashes.sha256 says $want" >&2; fi
    rm -f "$tgz"; return 1
  fi
  mkdir -p "$PWSH_DIR" && tar -xzf "$tgz" -C "$PWSH_DIR" && chmod +x "$PWSH_DIR/pwsh"; rc=$?
  rm -f "$tgz"
  [ "$rc" -eq 0 ] || return "$rc"
  [ -n "$(pwsh_version "$PWSH_DIR/pwsh")" ] || { echo "pwsh: the unpacked $PWSH_DIR/pwsh does not start" >&2; return 1; }
  ln -sf "$PWSH_DIR/pwsh" /usr/local/bin/pwsh
}

pwsh_tool() {
  local v tag ver arch vid deb="$LOG_DIR/packages-microsoft-prod.deb"
  v=$(pwsh_version)
  if [ -n "$v" ]; then log "pwsh: already installed ($v)"; return; fi
  case $(uname -m) in x86_64|amd64) arch=x64;; aarch64|arm64) arch=arm64;; *) echo "unsupported arch $(uname -m)" >&2; return 1;; esac
  tag=$(latest_tag PowerShell/PowerShell); ver=${tag#v}
  if [ -n "$ver" ] && pwsh_tarball "$tag" "$ver" "$arch"; then
    hash -r
    log "pwsh: installed $(pwsh_version) from the $tag release tarball (sha256 checked)"
    return
  fi
  log "pwsh: release tarball for '${tag:-no tag resolved}' failed, trying Microsoft's apt repo"
  # A subshell, so a missing VERSION_ID cannot trip `set -u` in this script.
  # shellcheck disable=SC1091
  vid=$(. /etc/os-release 2>/dev/null && echo "${VERSION_ID:-}")
  [ -n "$vid" ] || { echo "pwsh: no VERSION_ID in /etc/os-release, cannot pick Microsoft's repo" >&2; return 1; }
  "${CURL[@]}" "https://packages.microsoft.com/config/ubuntu/${vid}/packages-microsoft-prod.deb" -o "$deb" &&
  dpkg -i "$deb" && apt_install powershell || return
  hash -r
  v=$(pwsh_version)
  [ -n "$v" ] || { echo "pwsh: installed from apt but does not start" >&2; return 1; }
  log "pwsh: installed $v from Microsoft's apt repo"
}

# ---- Node tools --------------------------------------------------------------
# mmdc renders docs/diagrams. Same version as verify-gate.yml; the image's
# Chromium is used, so puppeteer must not download its own.
mermaid_cli() {
  local cur
  cur=$(mmdc --version 2>/dev/null)
  if [ "$cur" = "$MERMAID_VERSION" ]; then
    log "mermaid-cli: already installed (mmdc $cur)"
  else
    PUPPETEER_SKIP_DOWNLOAD=1 npm install -g "@mermaid-js/mermaid-cli@$MERMAID_VERSION" &&
      log "mermaid-cli: installed mmdc $MERMAID_VERSION${cur:+ (was $cur)}"
  fi
}

# npm ci writes node_modules/.package-lock.json; a package-lock.json newer than
# that (a pull moved the deps) means node_modules is stale and npm ci reruns.
mcp_deps() {
  local d="$REPO/mcp-servers"
  if [ -f "$d/node_modules/.package-lock.json" ] && ! [ "$d/package-lock.json" -nt "$d/node_modules/.package-lock.json" ]; then
    log "mcp-servers: node_modules already installed"
  else
    (cd "$REPO/mcp-servers" && npm ci --no-audit --no-fund) && log "mcp-servers: npm ci done"
  fi
}

# ---- gizmoduck scanners ------------------------------------------------------
# bootstrap.sh reinstalls every scanner on each run, so skip it when all of them
# are already on PATH. Before the C-0008 fix (PR #506), bootstrap.sh looks up the
# Nuclei, dependency-check and ZAP versions through api.github.com, which answers
# 403 here. A failed Nuclei install then fails the template update, which exits 1
# and stops bootstrap before nmap, nikto, testssl.sh, trivy and the rest: on a
# fresh container this step installs almost nothing and is reported FAILED (it
# is optional, so setup still exits 0). After #506 (a git-tag fallback for the
# version, skip-if-present, a templates-on-disk check) Nuclei installs here and
# bootstrap runs to the end.
GIZMODUCK_TOOLS=(nuclei nmap nikto testssl.sh trivy checkov semgrep dependency-check sqlmap zap.sh)
gizmoduck_scanners() {
  local t missing=()
  for t in "${GIZMODUCK_TOOLS[@]}"; do have "$t" || missing+=("$t"); done
  if [ "${#missing[@]}" -eq 0 ]; then
    log "gizmoduck: scanners already installed (${GIZMODUCK_TOOLS[*]})"
  else
    local rc still=()
    bash "$REPO/plugin/gizmoduck/bootstrap.sh"; rc=$?
    hash -r
    for t in "${missing[@]}"; do have "$t" || still+=("$t"); done
    if [ "${#still[@]}" -eq 0 ] && [ "$rc" -eq 0 ]; then
      log "gizmoduck: bootstrap.sh installed ${missing[*]}"
      return
    fi
    log "gizmoduck: bootstrap.sh exited $rc; still missing: ${still[*]:-none}"
    [ "$rc" -ne 0 ] || rc=1
    return "$rc"
  fi
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
step ruff       ruff_tool           # also drops the image's shadowing uv-tool pytest
step pylint     uv_tool "$PYLINT_SPEC"
step path       path_setup
step shellcheck uv_tool "$SHELLCHECK_SPEC"
step actionlint actionlint_tool
step pre-commit uv_tool pre-commit
step graphify   uv_tool graphifyy   # PyPI name has two y's; installs `graphify`
step apt        apt_tools
step pwsh       pwsh_tool
step mermaid    mermaid_cli
step mcp-deps   mcp_deps
if [ "${SKIP_GIZMODUCK:-0}" = 1 ]; then
  log "gizmoduck: skipped (SKIP_GIZMODUCK=1)"
else
  step gizmoduck gizmoduck_scanners
fi

# Doctor: what is on PATH now, whatever the steps reported.
hash -r
log "tools:"
for t in git codex python3 uv pytest ruff pylint shellcheck actionlint pre-commit graphify \
         bwrap fd hyperfine pwsh node npm mmdc "${GIZMODUCK_TOOLS[@]}"; do
  if have "$t"; then printf '    ok       %s\n' "$t"; else printf '    MISSING  %s\n' "$t"; fi
done

if [ "${#failed[@]}" -gt 0 ]; then
  log "done with FAILURES: ${failed[*]} (full logs: $LOG_DIR)"
  for f in "${failed[@]}"; do case $CORE in *" $f "*) exit 1;; esac; done
  log "only optional tools failed; exiting 0"
  exit 0
fi
log "done, all steps OK"
