#!/usr/bin/env bash
# Regression suite for the install scripts' plugin update path.
#
# The logic under test decides, without launching the Claude Code CLI where it can avoid
# it, whether an already-installed plugin needs anything doing to it. Getting that wrong
# is not loud: the failure mode is a machine that quietly keeps running a stale copy of a
# skill while the installer prints "already current". So each case below asserts on the
# exact line the script prints AND, where it matters, on the bytes actually on disk.
#
# Everything happens against a throwaway marketplace in a temp directory and a throwaway
# CLAUDE_CONFIG_DIR. The real config, the real marketplace, and the user's installed
# plugins are never touched.
#
# Needs: claude, git, jq or python3. Run it from anywhere:
#     ./scripts/_test/drift-detection.sh
# Exit status is 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO/scripts/install-prerequisites.sh"
PASS=0
FAIL=0

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

command -v claude >/dev/null 2>&1 || { echo "SKIP: the 'claude' CLI is not on PATH"; exit 0; }
command -v git    >/dev/null 2>&1 || { echo "SKIP: git is not on PATH"; exit 0; }

TMP="$(mktemp -d)"
MKT="$TMP/marketplace"
export CLAUDE_CONFIG_DIR="$TMP/config"
mkdir -p "$CLAUDE_CONFIG_DIR"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# --- a two-plugin marketplace, in git so the drift check has commits to diff ----
mkdir -p "$MKT/skills/alpha" "$MKT/skills/beta" "$MKT/.claude-plugin"
write_marketplace() {
  # $1 alpha version, $2 beta version
  cat > "$MKT/.claude-plugin/marketplace.json" <<JSON
{
  "name": "drifttest",
  "owner": { "name": "test" },
  "plugins": [
    { "name": "alpha", "source": "./skills/alpha", "description": "alpha", "version": "$1" },
    { "name": "beta",  "source": "./skills/beta",  "description": "beta",  "version": "$2" }
  ]
}
JSON
}
write_skill() { printf -- '---\nname: %s\ndescription: %s skill\n---\n\n%s\n' "$1" "$1" "$2" > "$MKT/skills/$1/SKILL.md"; }
commit() { git -C "$MKT" add -A && git -C "$MKT" -c user.email=t@t -c user.name=t commit -qm "$1"; }

write_marketplace 1.0.0 1.0.0
write_skill alpha ORIGINAL-ALPHA
write_skill beta  ORIGINAL-BETA
git -C "$MKT" init -q -b main
commit init

claude plugin marketplace add "$MKT" --scope user >/dev/null 2>&1
claude plugin install alpha@drifttest --scope user >/dev/null 2>&1
claude plugin install beta@drifttest  --scope user >/dev/null 2>&1

# --- load install_plugin and its helpers out of the real script ----------------
NO_UPDATE=0
FORCE_REFRESH=0
INSTALL_SCOPE=user
COUNT_INSTALLED=0
COUNT_UPDATED=0
COUNT_SKIPPED=0
OUT=""
ok()   { OUT="${OUT}OK|$1"$'\n'; }
skip() { OUT="${OUT}SKIP|$1"$'\n'; }
warn() { OUT="${OUT}WARN|$1"$'\n'; }
have() { command -v "$1" >/dev/null 2>&1; }
claude_available() { have claude; }
claude_config_root() { printf '%s' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; }
eval "$(sed -n '/^json_query()/,/^}/p' "$SCRIPT")"
eval "$(awk '/^PLUGINS_CACHE=""$/,/^# --- Detection: MCP servers/' "$SCRIPT" | sed '$d')"
eval "$(awk '/^install_plugin\(\) \{/,/^}/' "$SCRIPT")"

reset_caches() {
  PLUGINS_CACHE=""; INSTALLED_SHAS_CACHE=""; INSTALLED_SHAS_LOADED=0
  MARKETPLACE_SHA_CACHE=""; MARKETPLACE_CATALOG_CACHE=""
  MARKETPLACE_DIR_CACHE=""; MARKETPLACE_DIR_LOADED=0
  OUT=""
  load_plugins
}

run_both() { reset_caches; install_plugin alpha@drifttest; install_plugin beta@drifttest; }

assert_line() {
  # $1 human label, $2 expected "STATUS|substring", $3 the plugin the line is about
  local label="$1" want_status="${2%%|*}" want_text="${2#*|}" who="$3" line
  line="$(printf '%s' "$OUT" | grep -F "plugin '$who'" | head -1)"
  if [ "${line%%|*}" = "$want_status" ] && case "$line" in *"$want_text"*) true ;; *) false ;; esac; then
    green "  PASS  $label"; PASS=$((PASS+1))
  else
    red   "  FAIL  $label"
    red   "        wanted $want_status containing: $want_text"
    red   "        got:   ${line:-<no line for $who>}"
    FAIL=$((FAIL+1))
  fi
}

assert_disk() {
  # $1 label, $2 plugin, $3 text the *installed* copy must contain
  local label="$1" who="$2" want="$3" ver dir
  ver="$(claude plugin list --json 2>/dev/null | json_query \
    ".[] | select(.id == \"$who@drifttest\") | .version" \
    "import json,sys
for p in json.load(sys.stdin):
    if p.get('id') == '$who@drifttest':
        print(p.get('version') or '')")"
  dir="$CLAUDE_CONFIG_DIR/plugins/cache/drifttest/$who/$ver"
  if [ -f "$dir/SKILL.md" ] && grep -qF "$want" "$dir/SKILL.md"; then
    green "  PASS  $label"; PASS=$((PASS+1))
  else
    red   "  FAIL  $label - '$want' is not in the installed copy ($dir)"
    FAIL=$((FAIL+1))
  fi
}

echo "1. nothing changed upstream - both skip, no CLI launched"
run_both
assert_line "alpha reported current" "SKIP|already current" alpha
assert_line "beta reported current"  "SKIP|already current" beta

echo "2. alpha's files change, its version does NOT - drift must be reported"
write_skill alpha CHANGED-ALPHA
commit "alpha content, no version bump"
claude plugin marketplace update drifttest >/dev/null 2>&1
run_both
assert_line "alpha flagged as stale"          "WARN|still declares version 1.0.0" alpha
assert_line "beta untouched by alpha's commit" "SKIP|already current"             beta
assert_disk "alpha on disk is still the old copy" alpha ORIGINAL-ALPHA

echo "3. --force-refresh reinstalls the drifted plugin"
FORCE_REFRESH=1 && run_both && FORCE_REFRESH=0
assert_line "alpha reinstalled"      "OK|reinstalled to pick up changed files" alpha
assert_disk "alpha on disk refreshed" alpha CHANGED-ALPHA

echo "4. the run after a refresh is quiet again"
run_both
assert_line "alpha current" "SKIP|already current" alpha
assert_line "beta current"  "SKIP|already current" beta

echo "5. beta changes WITH a version bump - the normal update path"
write_skill beta BETA-V2
write_marketplace 1.0.0 1.1.0
commit "beta content and version bump"
claude plugin marketplace update drifttest >/dev/null 2>&1
run_both
assert_line "beta updated"                 "OK|updated 1.0.0 -> 1.1.0" beta
assert_line "alpha untouched by beta's commit" "SKIP|already current"  alpha
assert_disk "beta on disk refreshed" beta BETA-V2

echo "6. quiet again afterwards"
run_both
assert_line "alpha current" "SKIP|already current" alpha
assert_line "beta current"  "SKIP|already current" beta

echo "7. a source path that is not in the clone reports 'cannot tell', not 'unchanged'"
# 'git diff --quiet -- <path>' exits 0 when the pathspec matches nothing, which is
# indistinguishable from "no differences" - so a plugin whose declared source does not
# exist would have read as current forever. plugin_source_changed must return 2.
head="$(git -C "$MKT" rev-parse HEAD)"
prev="$(git -C "$MKT" rev-parse HEAD~1)"
plugin_source_changed drifttest "$prev" "$head" "skills/alpha"; rc=$?
[ "$rc" -le 1 ] && got="answered" || got="cannot tell"
if [ "$got" = "answered" ]; then
  green "  PASS  a real source path gets a real answer"; PASS=$((PASS+1))
else
  red   "  FAIL  a real source path should not report 'cannot tell'"; FAIL=$((FAIL+1))
fi
plugin_source_changed drifttest "$prev" "$head" "skills/no-such-plugin"; rc=$?
if [ "$rc" -eq 2 ]; then
  green "  PASS  a missing source path reports 'cannot tell'"; PASS=$((PASS+1))
else
  red   "  FAIL  a missing source path returned $rc, wanted 2 (cannot tell)"; FAIL=$((FAIL+1))
fi

echo "8. --no-update reports without touching anything"
write_skill alpha ALPHA-V3
commit "alpha content again, still no bump"
claude plugin marketplace update drifttest >/dev/null 2>&1
NO_UPDATE=1 && run_both && NO_UPDATE=0
assert_line "alpha only reported" "SKIP|already installed" alpha

echo
if [ "$FAIL" -eq 0 ]; then
  green "$PASS passed, 0 failed"
  exit 0
fi
red "$PASS passed, $FAIL FAILED"
exit 1
