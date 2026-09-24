#!/usr/bin/env bash
# Regression suite for the folded 'web-testing' install row (crew 1.0 web testing,
# lane B), in BOTH halves of the matched pair: install_web_testing in
# scripts/install-prerequisites.sh, and its Test-Selected 'web-testing' block in
# scripts/install-prerequisites.ps1. Replaces the old separate 'playwright-mcp' and
# 'playwright-cli' rows - this file supersedes nothing that tested those, because
# nothing did (they were single add_mcp_server / npm-install-g calls with no
# suite of their own).
#
# Idempotency is the point (CLAUDE.md: "both install scripts are idempotent - a new
# step needs a detection branch reporting 'already installed'"): the row has THREE
# detection branches - Node/npm/package.json guard rails, the devDependency-already-
# present message, and the Test-Agents-already-scaffolded skip - and each gets an
# absent case and a present case below. Neither script is run as a whole - only
# install_web_testing (and its mcp_* dependencies) are lifted out by awk, the same
# technique scripts/_test/lsp-stack-tools.sh uses - and exercised with every tool it
# calls stubbed in a throwaway PATH, so nothing here installs anything for real or
# reaches a network.
#
# Needs: bash, coreutils. pwsh is optional - without it the .ps1 case SKIPS loudly
# rather than passing for a reason that isn't real.
#     ./scripts/_test/web-testing.sh
# Exit status is 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO/scripts/install-prerequisites.sh"
PS1SCRIPT="$REPO/scripts/install-prerequisites.ps1"
REAL_PWSH="${PWSH:-}"
if [ -z "$REAL_PWSH" ]; then
  REAL_PWSH="$(command -v pwsh 2>/dev/null || true)"
  [ -n "$REAL_PWSH" ] || REAL_PWSH="C:/Program Files/PowerShell/7/pwsh.exe"
fi
PASS=0
FAIL=0
# newcase() below restricts PATH to a stub directory for the bash behavioural
# cases; the .ps1 structural section that runs after them needs the ambient
# PATH back (it uses awk), so the original is saved here and restored before it.
ORIGINAL_PATH="$PATH"
red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

check() {
  # $1 label, $2 expected, $3 actual
  if [ "$2" = "$3" ]; then
    green "  PASS  $1"; PASS=$((PASS+1))
  else
    red "  FAIL  $1"; red "        wanted: $2"; red "        got:    $3"; FAIL=$((FAIL+1))
  fi
}

TMP="$(mktemp -d)" && [ -n "$TMP" ] && [ -d "$TMP" ] || {
  echo "FATAL: mktemp -d failed to produce a directory - refusing to run" >&2
  exit 2
}
trap 'rm -rf "$TMP"' EXIT
_tmpdir="${TMPDIR:-/tmp}"
while [ "$_tmpdir" != "/" ] && [ "${_tmpdir: -1}" = "/" ]; do _tmpdir="${_tmpdir%/}"; done
case "$TMP" in
  "$_tmpdir"/*) ;;
  *)
    echo "FATAL: \$TMP ($TMP) is not under \${TMPDIR:-/tmp} ($_tmpdir) - refusing to run" >&2
    exit 2
    ;;
esac

echo "=== structural: the row is folded, not duplicated ==="
check "playwright-mcp key is gone"     0 "$(grep -c '"playwright-mcp"' "$SCRIPT")"
check "playwright-cli key is gone"     0 "$(grep -c '"playwright-cli"' "$SCRIPT")"
# Two occurrences on purpose: the MENU_KEYS entry and the 'is_selected "web-testing"'
# gate - not one, and not three (a third would mean a leftover reference somewhere).
check "web-testing key referenced exactly twice" 2 "$(grep -c '"web-testing"' "$SCRIPT")"
check "ps1: playwright-mcp key is gone" 0 "$(grep -c "Key = 'playwright-mcp'" "$PS1SCRIPT")"
check "ps1: playwright-cli key is gone" 0 "$(grep -c "Key = 'playwright-cli'" "$PS1SCRIPT")"
check "ps1: web-testing key exists once" 1 "$(grep -c "Key = 'web-testing'" "$PS1SCRIPT")"
# MENU_KEYS and MENU_DEFAULT must stay the same length - a fold that drops one
# array element but not the other silently shifts every row after it.
sh_keys="$(awk '/^MENU_KEYS=\(/,/^\)/' "$SCRIPT" | tr -s ' \t\n' ' ' | grep -oE '"[a-z0-9-]+"' | wc -l)"
sh_defaults="$(awk '/^MENU_DEFAULT=\(/{print; exit}' "$SCRIPT" | grep -oE '[01]' | wc -l)"
check "MENU_KEYS / MENU_DEFAULT same length" "$sh_keys" "$sh_defaults"
check "web-testing defaults ON in MENU_DEFAULT" yes \
  "$(python3 -c "
import re
src = open('$SCRIPT').read()
keys = re.search(r'MENU_KEYS=\((.*?)\n\)', src, re.S).group(1)
keys = re.findall(r'\"([a-z0-9-]+)\"', keys)
defaults = re.search(r'MENU_DEFAULT=\(([^)]*)\)', src).group(1).split()
i = keys.index('web-testing')
print('yes' if defaults[i] == '1' else 'no')
" 2>/dev/null || echo error)"
check "ps1: web-testing Default = \$true" 1 \
  "$(grep -c "Key = 'web-testing'.*Default = \$true" "$PS1SCRIPT")"

# --- Lift the real functions out of install-prerequisites.sh -----------------
eval "$(awk '/^step\(\)/,/^have\(\) \{/' "$SCRIPT")"
eval "$(awk '/^load_mcp_servers\(\) \{/,/^# --- Detection: user-level skills/' "$SCRIPT" | sed '$d')"
is_selected() { return 1; }
eval "$(awk '/^install_web_testing\(\) \{/,/^\}/' "$SCRIPT")"

FAILED_STEPS=()
COUNT_INSTALLED=0
COUNT_SKIPPED=0
INSTALL_SCOPE="user"

REALTOOLS="$TMP/realtools"
mkdir -p "$REALTOOLS"
for _t in mkdir chmod dirname id grep cat touch cp rm stat sed; do
  _src="$(command -v "$_t" 2>/dev/null)" || continue
  [ -n "$_src" ] && cp "$_src" "$REALTOOLS/$_t"
done
unset _t _src
# node is DELIBERATELY not copied into REALTOOLS: it must be absent from every
# case's PATH unless stub_node() puts a wrapper there, or the "no node -> fails"
# case would find the real one instead. The real binary's absolute path is kept
# here so stub_node()'s wrapper can still delegate to it for 'node -e ...'.
REAL_NODE="$(command -v node 2>/dev/null || true)"

WORK=""
newcase() {
  WORK="$TMP/case-$RANDOM"
  mkdir -p "$WORK/stubs" "$WORK/proj" "$WORK/home"
  export PATH="$WORK/stubs:$REALTOOLS"
  export HOME="$WORK/home"
  cd "$WORK/proj" || exit 2
  MCP_CACHE=""
}
stub() {
  # $1 name, $2.. body - a real new file, never a symlink (a stub PATH entry must
  # never resolve back onto a real host tool through a link).
  local name="$1"; shift
  printf '#!/bin/sh\n%s\n' "$*" > "$WORK/stubs/$name"
  chmod +x "$WORK/stubs/$name"
}
run_iwt() {
  # Runs install_web_testing WITHOUT a command-substitution subshell: "$(cmd)"
  # forks, so COUNT_INSTALLED/COUNT_SKIPPED updates the function makes would be
  # discarded the moment the subshell exits - the exact trap
  # scripts/_test/menu-groups.sh's 'warned()' comment describes. Captures via a
  # file instead, in the current shell, so the counters are still visible after.
  install_web_testing >"$WORK/out.log" 2>&1
  rc=$?
  out="$(cat "$WORK/out.log")"
}
stub_node() {
  # $1 the version string node -v should report (e.g. '20.19.0'); everything
  # else node is asked to do here ('node -e ...') is answered by the REAL node,
  # via a wrapper that only intercepts '-v'.
  local ver="$1"
  cat > "$WORK/stubs/node" <<EOF
#!/bin/sh
if [ "\$1" = "-v" ]; then echo "v$ver"; exit 0; fi
exec "$REAL_NODE" "\$@"
EOF
  chmod +x "$WORK/stubs/node"
}

echo
echo "=== install_web_testing: Node / npm / package.json guard rails ==="
if [ -z "$REAL_NODE" ]; then
  echo "SKIPPED: no real node on the host PATH - the guard-rail cases below need node -e to evaluate a real package.json; a stub cannot stand in for it without reimplementing require()."
else
  newcase
  run_iwt
  check "no node -> fails"           1 "$rc"
  check "no node -> names node"      yes "$(case "$out" in *"node not found"*) echo yes;; *) echo no;; esac)"

  newcase
  stub_node "20.10.0"
  run_iwt
  check "node 20.10 (too old) -> fails"      1 "$rc"
  check "node 20.10 -> names 20.19"          yes "$(case "$out" in *"20.19"*) echo yes;; *) echo no;; esac)"

  newcase
  stub_node "20.19.0"
  run_iwt
  check "node 20.19 exactly, no npm -> fails" 1 "$rc"
  check "no npm -> names npm"                 yes "$(case "$out" in *"npm not found"*) echo yes;; *) echo no;; esac)"

  newcase
  stub_node "22.12.0"
  stub npm 'exit 0'
  run_iwt
  check "node 22.12, npm ok, no package.json -> fails" 1 "$rc"
  check "no package.json -> names it"                   yes "$(case "$out" in *"package.json"*) echo yes;; *) echo no;; esac)"

  echo
  echo "=== install_web_testing: devDependency + browsers + Test Agents ==="
  newcase
  stub_node "20.19.0"
  cat > "$WORK/stubs/npm" <<'EOF'
#!/bin/sh
exit 0
EOF
  chmod +x "$WORK/stubs/npm"
  cat > "$WORK/stubs/npx" <<'EOF'
#!/bin/sh
echo "$@" >> "$NPX_LOG"
exit 0
EOF
  chmod +x "$WORK/stubs/npx"
  export NPX_LOG="$WORK/npx.log"; : > "$NPX_LOG"
  printf '{}\n' > package.json
  # No 'claude' stub: mcp_launcher_resolves only needs 'npx' to resolve, which it
  # does above, but add_mcp_server itself needs 'claude' - stub it to record calls.
  cat > "$WORK/stubs/claude" <<'EOF'
#!/bin/sh
echo "$@" >> "$CLAUDE_LOG"
exit 0
EOF
  chmod +x "$WORK/stubs/claude"
  export CLAUDE_LOG="$WORK/claude.log"; : > "$CLAUDE_LOG"
  COUNT_INSTALLED=0
  run_iwt
  check "happy path, package.json empty -> exits 0"        0 "$rc"
  # 3, not 1: the devDependency install AND each of the two add_mcp_server calls
  # (playwright, chrome-devtools) increment the same COUNT_INSTALLED - that is
  # add_mcp_server's own accounting, not a bug in this row.
  check "happy path -> counts three installs (deps + 2 MCP servers)" 3 "$COUNT_INSTALLED"
  check "happy path -> runs 'npx playwright install --with-deps chromium'" yes \
    "$(grep -qF 'playwright install --with-deps chromium' "$NPX_LOG" && echo yes || echo no)"
  check "no Test Agents scaffold -> runs the claude loop" yes \
    "$(grep -qF 'init-agents --loop=claude' "$NPX_LOG" && echo yes || echo no)"
  check "no Test Agents scaffold -> runs the codex loop"  yes \
    "$(grep -qF 'init-agents --loop=codex' "$NPX_LOG" && echo yes || echo no)"
  check "registers the playwright MCP server"    yes \
    "$(grep -qF 'playwright' "$CLAUDE_LOG" && echo yes || echo no)"
  check "registers the chrome-devtools MCP server" yes \
    "$(grep -qF 'chrome-devtools' "$CLAUDE_LOG" && echo yes || echo no)"
  unset NPX_LOG CLAUDE_LOG

  newcase
  stub_node "20.19.0"
  stub npm 'exit 0'
  cat > "$WORK/stubs/npx" <<'EOF'
#!/bin/sh
echo "$@" >> "$NPX_LOG"
exit 0
EOF
  chmod +x "$WORK/stubs/npx"
  export NPX_LOG="$WORK/npx2.log"; : > "$NPX_LOG"
  stub claude 'exit 0'
  printf '{}\n' > package.json
  # DETECTION BRANCH: Test Agents already scaffolded - the claude/codex loops must
  # not run again.
  mkdir -p .claude/agents
  touch .claude/agents/playwright-test-planner.md
  run_iwt
  check "Test Agents already scaffolded -> exits 0"     0 "$rc"
  check "-> says SKIP"                                  yes "$(case "$out" in *SKIP*) echo yes;; *) echo no;; esac)"
  check "-> does not re-run init-agents"                0  "$(grep -c 'init-agents' "$NPX_LOG")"
  unset NPX_LOG

  newcase
  stub_node "20.19.0"
  stub npm 'exit 0'
  stub npx 'exit 0'
  stub claude 'exit 0'
  # DETECTION BRANCH: @playwright/test already a devDependency - still reinstalls
  # the pin (this is a version-pin refresh, not a skip), but says so.
  printf '{"devDependencies":{"@playwright/test":"1.62.0"}}\n' > package.json
  run_iwt
  check "already a devDependency -> exits 0"            0 "$rc"
  check "already a devDependency -> says so"            yes \
    "$(case "$out" in *"already a devDependency"*) echo yes;; *) echo no;; esac)"

  echo
  echo "=== install_web_testing: Docker is a WARNING, never a blocker ==="
  newcase
  stub_node "20.19.0"
  stub npm 'exit 0'
  stub npx 'exit 0'
  stub claude 'exit 0'
  printf '{}\n' > package.json
  mkdir -p .claude/agents; touch .claude/agents/playwright-test-planner.md
  run_iwt
  check "no docker -> still exits 0"                    0 "$rc"
  check "no docker -> warns, does not fail the row"     yes \
    "$(case "$out" in *"Docker not found"*) echo yes;; *) echo no;; esac)"

  newcase
  stub_node "20.19.0"
  stub npm 'exit 0'
  stub npx 'exit 0'
  stub claude 'exit 0'
  stub docker 'exit 0'
  printf '{}\n' > package.json
  mkdir -p .claude/agents; touch .claude/agents/playwright-test-planner.md
  run_iwt
  check "docker present -> exits 0"                     0 "$rc"
  check "docker present -> names the pinned image"      yes \
    "$(case "$out" in *"mcr.microsoft.com/playwright:v1.63.0-noble"*) echo yes;; *) echo no;; esac)"
fi

cd "$REPO" || exit 2
export PATH="$ORIGINAL_PATH"

# --- The .ps1 half: structural checks, then one behavioural run if pwsh exists --
echo
echo "=== .ps1: structural checks (case 24-equivalent, no interpreter needed) ==="
case "$(awk "/Test-Selected 'web-testing'/,/^\}/" "$PS1SCRIPT")" in
  *'Get-Command node'*) got=yes ;; *) got=no ;;
esac
check ".ps1 web-testing checks for node"              yes "$got"
case "$(awk "/Test-Selected 'web-testing'/,/^\}/" "$PS1SCRIPT")" in
  *'package.json'*) got=yes ;; *) got=no ;;
esac
check ".ps1 web-testing checks for package.json"      yes "$got"
case "$(awk "/Test-Selected 'web-testing'/,/^\}/" "$PS1SCRIPT")" in
  *'playwright-test-planner.md'*) got=yes ;; *) got=no ;;
esac
check ".ps1 web-testing checks for the Test Agents scaffold" yes "$got"
case "$(awk "/Test-Selected 'web-testing'/,/^\}/" "$PS1SCRIPT")" in
  *'chrome-devtools-mcp@latest'*) got=yes ;; *) got=no ;;
esac
check ".ps1 web-testing registers chrome-devtools-mcp" yes "$got"
case "$(awk "/Test-Selected 'web-testing'/,/^\}/" "$PS1SCRIPT")" in
  *'Get-Command docker'*) got=yes ;; *) got=no ;;
esac
check ".ps1 web-testing checks for docker (warning only)" yes "$got"

if [ ! -x "$REAL_PWSH" ]; then
  printf '\033[90m%s\033[0m\n' "SKIPPED: pwsh not found at '$REAL_PWSH' - install-prerequisites.ps1's behavioural half of this suite went unverified in this run. That is a MISSING TOOL, not a failed check."
else
  echo
  echo "=== .ps1: install_web_testing behavioural equivalent ==="
  PWSHTMP="$TMP/ps1case"
  mkdir -p "$PWSHTMP/stubs" "$PWSHTMP/proj"
  cat > "$PWSHTMP/stubs/node" <<'STUB'
#!/bin/sh
if [ "$1" = "-v" ]; then echo "v20.19.0"; exit 0; fi
exit 0
STUB
  chmod +x "$PWSHTMP/stubs/node"
  for t in npm npx claude docker; do
    printf '#!/bin/sh\nexit 0\n' > "$PWSHTMP/stubs/$t"
    chmod +x "$PWSHTMP/stubs/$t"
  done
  printf '{}\n' > "$PWSHTMP/proj/package.json"
  mkdir -p "$PWSHTMP/proj/.claude/agents"
  touch "$PWSHTMP/proj/.claude/agents/playwright-test-planner.md"
  PSHARNESS="$TMP/webtest-harness.ps1"
  cat > "$PSHARNESS" <<'PS1EOF'
$ErrorActionPreference = 'Stop'
$src = Get-Content -Raw -Path $env:PS1SCRIPT
function Get-Block([string]$StartPattern, [string]$EndPattern) {
    $lines = $src -split "`n"
    $out = @(); $on = $false
    foreach ($l in $lines) {
        if ($l -match $StartPattern) { $on = $true }
        if ($on) { $out += $l }
        if ($on -and $l -match $EndPattern) { break }
    }
    return ($out -join "`n")
}
Invoke-Expression (Get-Block '^function Write-Step' '^function Write-Skip')
function Sync-SessionEnvironment { }
$script:Summary = @{ Installed = 0; Updated = 0; Skipped = 0 }
$script:FailedSteps = @()
$script:McpCache = $null
$InstallScope = 'user'
Invoke-Expression (Get-Block '^function Invoke-Step' '^\}')
Invoke-Expression (Get-Block '^function Test-ClaudeAvailable' '^\}')
Invoke-Expression (Get-Block '^function Get-ClaudeMcpServers' '^\}')
Invoke-Expression (Get-Block '^function Test-McpServerRegistered' '^\}')
Invoke-Expression (Get-Block '^function Add-McpServer' '^\}')
function Test-Selected { param([string]$Key) return ($Key -eq 'web-testing') }
$body = Get-Block "Test-Selected 'web-testing'" '^\}'
# Body is the whole 'if (Test-Selected ...) { Invoke-Step ... { ... } }' wrapper;
# invoke it directly rather than re-declaring it as a function.
Invoke-Expression $body
"INSTALLED=$($script:Summary.Installed)"
PS1EOF
  export PS1SCRIPT="$(cygpath -m "$PS1SCRIPT" 2>/dev/null || printf '%s' "$PS1SCRIPT")"
  out="$(cd "$PWSHTMP/proj" && env PATH="$PWSHTMP/stubs:$PATH" "$REAL_PWSH" -NoProfile -File "$PSHARNESS" 2>&1)"
  check ".ps1 web-testing happy path: exits without throwing" yes \
    "$(case "$out" in *"INSTALLED="*) echo yes;; *) echo no;; esac)"
  # 3, same reasoning as the .sh side: the devDependency install plus the two
  # Add-McpServer calls (playwright, chrome-devtools) each increment Installed.
  check ".ps1 web-testing happy path: counts three installs" yes \
    "$(case "$out" in *"INSTALLED=3"*) echo yes;; *) echo no;; esac)"
  unset PS1SCRIPT
fi

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1
