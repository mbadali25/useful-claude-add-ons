#!/usr/bin/env bash
# Regression suite for the install script's sub-picker groups.
#
# Every menu row that installs more than one thing is backed by a <PREFIX>_KEYS /
# _NAME / _STATE (/ _SPEC) catalog, and that catalog is the single source for the
# menu label, the picker, the --<group> flag and the install loop. These are the
# parts that can be checked without a terminal; the cursor behaviour itself needs a
# pty and is exercised by hand.
#
# Needs: bash. Installs nothing and touches no real config - the end-to-end cases run
# the script with --dry-run and CLAUDE_CONFIG_DIR pointed at a temp directory, so it
# settles the selection, prints it and stops.
#     ./scripts/_test/menu-groups.sh
# Exit status is 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO/scripts/install-prerequisites.sh"
PASS=0
FAIL=0
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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Capture a warning WITHOUT losing the state change: "$(cmd 2>&1)" runs cmd in a
# subshell, so the catalog edits it makes are discarded. That is the same subshell trap
# the script itself hit with its caches, and it made two of these cases pass by luck.
warned() {
  # $1 substring to look for; the rest is the command to run in *this* shell.
  # Both streams are redirected: a plain redirection does not fork, so the catalog
  # edits survive, but the message can arrive on either one.
  local want="$1"; shift
  "$@" >"$TMP/out" 2>&1
  grep -qF "$want" "$TMP/out"
}

# --- load the group layer out of the real script ------------------------------
warn() { printf 'WARN: %s\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }
is_selected() { case " ${SELECTED:-} " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
eval "$(awk '/^# --- This repo.s individual skills/,/^skills_selected_count\(\)/' "$SCRIPT" | sed '$d')"

echo "1. every group is non-empty and its arrays line up"
for i in "${!GROUP_PREFIXES[@]}"; do
  prefix="${GROUP_PREFIXES[$i]}"
  n="$(group_count "$prefix")"
  [ "$n" -gt 0 ] && ok=yes || ok=no
  check "${GROUP_MENU_KEYS[$i]} has entries" yes "$ok"
  eval "names=\${#${prefix}_NAME[@]}; states=\${#${prefix}_STATE[@]}"
  check "${GROUP_MENU_KEYS[$i]} KEYS/NAME/STATE same length" "$n $n" "$names $states"
done

echo "2. every group starts fully ticked"
for i in "${!GROUP_PREFIXES[@]}"; do
  prefix="${GROUP_PREFIXES[$i]}"
  check "${GROUP_MENU_KEYS[$i]} all on by default" \
    "$(group_count "$prefix")" "$(group_selected_count "$prefix")"
done

echo "3. --<group> specs: names, numbers, ranges, all, none"
expand_group_spec TEAM 'excalidraw-generator'
check "one name"            "1" "$(group_selected_count TEAM)"
expand_group_spec SKILL '1,3'
check "two numbers"         "2" "$(group_selected_count SKILL)"
expand_group_spec SKILL '2-5'
check "a range"             "4" "$(group_selected_count SKILL)"
expand_group_spec COMMUNITY 'none'
check "none"                "0" "$(group_selected_count COMMUNITY)"
expand_group_spec COMMUNITY 'all'
check "all"                 "7" "$(group_selected_count COMMUNITY)"
warned "ignoring unknown team plugin 'not-a-plugin'" \
  expand_group_spec TEAM 'superpowers,not-a-plugin' && got=yes || got=no
check "unknown name warns, in the singular"    yes "$got"
check "and the good name is still selected"    "1" "$(group_selected_count TEAM)"
warned "out-of-range skill number '99'" expand_group_spec SKILL '99' && got=yes || got=no
check "out-of-range number warns"              yes "$got"
check "and selects nothing"                    "0" "$(group_selected_count SKILL)"

echo "3b. a reversed range is rejected, not reinterpreted"
# bash's for-loop selects nothing from '3-1'; PowerShell's '..' counts down and selects
# three. Both scripts must refuse it, or the same command line means two things.
expand_group_spec SKILL 'all'
warned "reversed skill range '3-1'" expand_group_spec SKILL '3-1' && got=yes || got=no
check "reversed range warns"           yes "$got"
check "and selects nothing"            "0" "$(group_selected_count SKILL)"
expand_group_spec SKILL '1-3'
check "a forward range still works"    "3" "$(group_selected_count SKILL)"

echo "4. an entry only counts when its parent row is selected"
expand_group_spec PLUGIN 'all'
SELECTED="repo-plugins"
group_entry_selected PLUGIN crew && got=yes || got=no
check "crew with the row on"  yes "$got"
SELECTED=""
group_entry_selected PLUGIN crew && got=yes || got=no
check "crew with the row off" no  "$got"

echo "5. every SPEC entry is plugin@marketplace|source|name"
for prefix in SKILL TEAM COMMUNITY PLUGIN; do
  n="$(group_count "$prefix")"
  bad=0
  for (( j=0; j<n; j++ )); do
    spec="$(group_spec "$prefix" "$j")"
    case "$spec" in
      *"@"*"|"*"/"*"|"*) ;;
      *) bad=$((bad+1)); red "        malformed: $prefix[$j] = '$spec'" ;;
    esac
  done
  check "$prefix specs well-formed" "0" "$bad"
done

echo "6. a --<group> flag selects its parent row, even one that defaults to off"
run_summary() {
  # --dry-run settles the selection, prints it, and stops. Without it these cases ran
  # the real installer - apt-get, npm -g, a ~/.bashrc edit - which is not something a
  # test suite may do to the machine it runs on.
  CLAUDE_CONFIG_DIR="$TMP/cfg" bash "$SCRIPT" --dry-run "$@" 2>&1
}
mkdir -p "$TMP/cfg"
# Assert on the outcome - the row actually appearing in the install list - not on the
# "Also selecting" message. A sabotage that dropped the selection but kept the message
# passed an earlier version of this test.
out="$(run_summary --plugins crew --non-interactive)"
# "1 of N": --plugins crew narrows the *selection*, not the catalog, exactly
# like --team below narrows selection within its own catalog. N is read from
# PLUGIN_KEYS rather than written out, because a hardcoded count turns every
# newly registered plugin into a failure in this file - which is the one place
# a reader would not think to look for it. Reading it from PLUGIN_KEYS means
# this case no longer independently checks the printed number; that property
# belongs to check-marketplace.py's check_catalogs, which compares PLUGIN_KEYS
# against marketplace.json. This case checks that the row was selected at all.
case "$out" in *"This repo's plugins: 1 of $(group_count PLUGIN)"*) got=yes ;; *) got=no ;; esac
check "--plugins crew puts repo-plugins in the install list" yes "$got"
out="$(run_summary --plugins none --non-interactive)"
case "$out" in *"This repo's plugins"*) got=yes ;; *) got=no ;; esac
check "--plugins none leaves it out"                         no  "$got"
out="$(run_summary --team superpowers --non-interactive)"
case "$out" in *"Team plugins: 1 of 3"*) got=yes ;; *) got=no ;; esac
check "--team narrows the row label"         yes "$got"

echo "7. a marketplace behind several plugins is registered once, not once per plugin"
# Three of the community row's seven plugins come from claude-settings, and two
# more share voltagent-subagents. Before
# install_group that was three separate "Marketplace:" steps, and a marketplace refresh
# re-clones the repo. A stub 'claude' makes this observable without installing anything.
mkdir -p "$TMP/bin"
printf '#!/bin/sh\nexit 0\n' > "$TMP/bin/claude"
chmod +x "$TMP/bin/claude"
steps="$(CLAUDE_CONFIG_DIR="$TMP/cfg" PATH="$TMP/bin:$PATH" \
  bash "$SCRIPT" --select community --community all 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -c '^==> Marketplace:')"
check "7 community plugins -> 4 marketplace steps" "4" "$steps"
plugins="$(CLAUDE_CONFIG_DIR="$TMP/cfg" PATH="$TMP/bin:$PATH" \
  bash "$SCRIPT" --select community --community all 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -c '^==> Plugin:')"
check "and 7 plugin steps"                         "7" "$plugins"
one="$(CLAUDE_CONFIG_DIR="$TMP/cfg" PATH="$TMP/bin:$PATH" \
  bash "$SCRIPT" --select community --community ppt-master 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -c '^==> Marketplace:')"
check "one plugin -> one marketplace step"         "1" "$one"

echo "8. the Perplexity row registers with a key, and never prints one"
# This row is the only one that takes a secret on the command line, so the cases that
# matter are: no key at all, a blank key, the environment fallback, and - the one that
# would be a real incident - the key turning up in the script's output.
#
# The stub records what it was asked for in a FILE, not on stdout: a stub that echoed
# its arguments would put the key in the captured output itself and make the
# "never printed" case pass or fail for the wrong reason.
cat > "$TMP/bin/claude" <<'STUB'
#!/bin/sh
printf '%s\n' "$*" >> "$CLAUDE_STUB_LOG"
if [ "$1" = "mcp" ] && [ "$2" = "list" ] && [ -n "${CLAUDE_STUB_MCP_LIST:-}" ]; then
  printf '%s\n' "$CLAUDE_STUB_MCP_LIST"
fi
exit 0
STUB
chmod +x "$TMP/bin/claude"
SENTINEL='PPLX-SENTINEL-DO-NOT-PRINT'
run_perplexity() {
  # $1 the value of PERPLEXITY_API_KEY for the run ('-' for unset); the rest are extra
  # flags. Leaves the run's output in $TMP/pplx.out and the stub's calls in $TMP/pplx.log.
  local envkey="$1"; shift
  : > "$TMP/pplx.log"
  if [ "$envkey" = "-" ]; then
    CLAUDE_CONFIG_DIR="$TMP/cfg" PATH="$TMP/bin:$PATH" \
      CLAUDE_STUB_LOG="$TMP/pplx.log" CLAUDE_STUB_MCP_LIST="${MCP_LIST:-}" \
      bash "$SCRIPT" --select perplexity-mcp "$@" >"$TMP/pplx.out" 2>&1
  else
    CLAUDE_CONFIG_DIR="$TMP/cfg" PATH="$TMP/bin:$PATH" \
      CLAUDE_STUB_LOG="$TMP/pplx.log" CLAUDE_STUB_MCP_LIST="${MCP_LIST:-}" \
      PERPLEXITY_API_KEY="$envkey" bash "$SCRIPT" --select perplexity-mcp "$@" >"$TMP/pplx.out" 2>&1
  fi
}
# -e is not decoration: one of the patterns below starts with '--env', which grep
# would otherwise read as an option and refuse, reporting a genuine match as 'no'.
saw()     { grep -qF -e "$1" "$TMP/pplx.out" && echo yes || echo no; }
logged()  { grep -qF -e "$1" "$TMP/pplx.log" && echo yes || echo no; }

MCP_LIST=""
run_perplexity -
check "no key at all: the row skips"        yes "$(saw 'no --perplexity-api-key given')"
check "and registers nothing"               no  "$(logged 'mcp add')"
check "and says where to get one"           yes "$(saw 'docs.perplexity.ai')"

run_perplexity '   '
check "a whitespace-only key counts as none" yes "$(saw 'no --perplexity-api-key given')"
check "and still registers nothing"          no  "$(logged 'mcp add')"

run_perplexity - --perplexity-api-key "$SENTINEL"
check "--perplexity-api-key registers the server" \
  yes "$(logged "mcp add --scope user perplexity --env PERPLEXITY_API_KEY=$SENTINEL -- npx -y @perplexity-ai/mcp-server")"
check "and the key is NOWHERE in the output"  no  "$(saw "$SENTINEL")"

run_perplexity "$SENTINEL"
check "PERPLEXITY_API_KEY is the fallback"    yes "$(logged "--env PERPLEXITY_API_KEY=$SENTINEL")"
check "and that key is not printed either"    no  "$(saw "$SENTINEL")"

# The real 'claude mcp list' puts a tick before "Connected"; the name is all the
# script's parser reads off the line, and this file stays ASCII.
MCP_LIST="perplexity: npx -y @perplexity-ai/mcp-server - Connected"
run_perplexity - --perplexity-api-key "$SENTINEL"
check "an already-registered server is skipped" yes "$(saw "MCP server 'perplexity' already registered")"
check "and is not re-added"                     no  "$(logged 'mcp add')"
MCP_LIST=""

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1
