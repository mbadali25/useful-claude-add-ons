#!/usr/bin/env bash
# Regression suite for three defects in BOTH halves of the matched pair
# (scripts/install-prerequisites.sh and scripts/install-prerequisites.ps1):
#
#   A. MCP registration reported success for servers that can never start.
#      `claude mcp add <name> -- <cmd> ...` WRITES CONFIG AND NEVER INVOKES <cmd>,
#      so six call sites (azure, playwright, perplexity and four mcp-* servers)
#      printed "added MCP server 'x'" whether or not npx/uvx resolved on PATH. The
#      failure then surfaced much later, inside a session, with nothing pointing
#      back at the step that caused it. Nothing in either script reads
#      Connected/Failed back out of `claude mcp list` - the name is taken off the
#      front of each line and nothing else - so there was no second chance.
#
#   B. Skill-level Python dependencies were never installed OR reported, on any OS.
#      `claude plugin install` copies a skill's files and nothing more, so
#      doc-builder's requirements.txt and its scripts/preflight.py had never been
#      run by either installer: grep for either name returned zero hits outside
#      comments. The fix REPORTS rather than installs, and these cases pin that
#      down in both directions - the report must reach stderr, and no install may
#      be attempted.
#
#   C. The community marketplace, eli5 and github. The trap is one string: the
#      resolved LOCAL NAME of anthropics/claude-plugins-community is
#      'claude-community'. Writing the repo name where the marketplace name goes
#      makes the idempotency probe look for a name that never exists, so the step
#      re-adds on every run while reporting success. And 'github' is published by
#      TWO marketplaces as two unrelated plugins, which the plugin cache used to
#      collapse onto the bare name - so installing one was read as proof of the
#      other.
#
# Needs: bash, coreutils, and jq or python3 for the end-to-end cases. pwsh is
# optional - without it the .ps1 parity cases SKIP loudly and say that half went
# unverified in that run.
#
# Installs NOTHING, registers no marketplace, adds no MCP server and touches no real
# config: every external command is a throwaway stub in a temp dir, CLAUDE_CONFIG_DIR
# points into that temp dir, and the end-to-end cases run the real script with a stub
# 'claude' that only records what it was asked to do.
#     ./scripts/_test/mcp-preflight-catalog.sh
# Exit status is 0 when every case passes, 1 otherwise. The run prints its own totals;
# re-measure from that line rather than trusting a count written into a comment.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO/scripts/install-prerequisites.sh"
PS1SCRIPT="$REPO/scripts/install-prerequisites.ps1"
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

BASH_ABS="$(command -v bash)"

# --- the real tools a fixture may need, COPIED into $TMP first ----------------
# Fixtures must never hold a link to a HOST BINARY in the directory stub() writes
# into. On 2026-09-22 that shape cost this host its coreutils twice - once from a
# missing rm -f in a sibling harness, and once from someone removing that rm
# deliberately to sabotage-test it and running the whole suite. 116 hardlinks into
# one uutils multicall binary, overwritten by a three-line shell stub.
#
# So the hazard is removed rather than guarded: every fixture link points at a COPY
# inside $TMP, and a write-through can only ever reach that copy. One copy per
# distinct INODE, not per name - those names are hardlinks into one 11 MB binary
# here, and uutils dispatches on argv[0], so a hardlink inside $TMP keeps the name.
# Case 0 asserts the invariant rather than trusting this comment.
REALBIN="$TMP/realbin"
mkrealbin() {
  mkdir -p "$REALBIN"
  local t src key rep seen=""
  for t in mktemp rm find sed tail dirname cat mkdir chmod sh sort wc; do
    src="$(command -v "$t" 2>/dev/null)" || continue
    [ -n "$src" ] || continue
    src="$(readlink -f "$src")"
    key="$(stat -c '%d:%i' "$src" 2>/dev/null || printf 'x%s' "$src")"
    rep=""
    case " $seen " in
      *" $key="*) rep="${seen##*"$key="}"; rep="${rep%% *}" ;;
    esac
    if [ -n "$rep" ] && [ -e "$REALBIN/$rep" ]; then
      ln "$REALBIN/$rep" "$REALBIN/$t" 2>/dev/null || cp "$src" "$REALBIN/$t"
    else
      cp "$src" "$REALBIN/$t"
      seen="$seen $key=$t"
    fi
    chmod +x "$REALBIN/$t"
  done
}
mkrealbin

mkfixture() {
  local fx="$TMP/$1" t
  rm -rf "$fx"
  mkdir -p "$fx/bin" "$fx/home" "$fx/cfg"
  : > "$fx/calls"
  # Only the plumbing the functions under test call directly. Everything they PROBE
  # for - claude, npx, uvx, python3, python, py, pip - is absent unless a case stubs
  # it, so "the host happened to have it" can never make a case pass.
  # $REALBIN, never /usr/bin: see mkrealbin above. Nothing in a fixture may resolve
  # to a host binary, and case 0 asserts that as a standing invariant.
  for t in mktemp rm find sed tail dirname cat mkdir chmod sh sort wc; do
    [ -e "$REALBIN/$t" ] && ln -s "$REALBIN/$t" "$fx/bin/$t"
  done
  printf '%s' "$fx"
}

stub() {
  # $1 fixture name, $2 tool, rest: body lines. Every stub records its own call.
  #
  # Two guards, and neither is tidiness. mkfixture symlinks real coreutils into
  # $fx/bin; a case that stubs one of those names would otherwise have its '>'
  # redirect FOLLOW the symlink and truncate the host's own binary. On this repo's
  # reference host those names are hardlinks into one uutils multicall binary, so a
  # single unguarded redirect over `mktemp` took out 114 coreutils at once. Measured,
  # not theorised - it happened in this repo on 2026-09-22.
  #   1. the target path must be inside $TMP, so nothing here can write to the host;
  #   2. rm -f FIRST, then confirm the name is gone, so the write lands on a new
  #      file and never through a link.
  # The interpreter is named ABSOLUTELY: a '#!/usr/bin/env bash' shebang resolves
  # bash through the CALLER's PATH, which these fixtures deliberately empty.
  local fx="$TMP/$1" name="$2"; shift 2
  local target="$fx/bin/$name"
  case "$target" in
    "$TMP"/*) ;;
    *) red "REFUSING to write a stub outside \$TMP: $target"; exit 2 ;;
  esac
  rm -f "$target"
  if [ -e "$target" ] || [ -L "$target" ]; then
    red "stub target still present after 'rm -f': $target"; exit 2
  fi
  {
    echo "#!$BASH_ABS"
    echo "printf '%s %s\\n' '$name' \"\$*\" >> '$fx/calls'"
    printf '%s\n' "$@"
  } > "$target"
  chmod +x "$target"
}

on_out() { grep -qF -e "$1" "$TMP/out" && echo yes || echo no; }
on_err() { grep -qF -e "$1" "$TMP/err" && echo yes || echo no; }
called() { grep -qF -e "$1" "$TMP/${FX}/calls" && echo yes || echo no; }

# --- load the layers under test out of the real script ------------------------
# Same idiom as menu-groups.sh and uv-install.sh: the suite tests the shipped code,
# never a copy of it.
COUNT_INSTALLED=0
COUNT_SKIPPED=0
COUNT_UPDATED=0
FAILED_STEPS=()
INSTALL_SCOPE="user"
eval "$(awk '/^step\(\)/,/^have\(\) \{/' "$SCRIPT")"
eval "$(awk '/^# --- Detection: plugins/,/^# --- Detection: what a marketplace clone/' "$SCRIPT" | sed '$d')"
eval "$(awk '/^# --- Detection: MCP servers/,/^# --- Detection: user-level skills/' "$SCRIPT" | sed '$d')"
eval "$(awk '/^# --- Skill-level Python dependencies/,/^# --- 3\. This repo/' "$SCRIPT" | sed '$d')"
eval "$(awk '/^# --- This repo.s individual skills/,/^skills_selected_count\(\)/' "$SCRIPT" | sed '$d')"
claude_available() { have claude; }
claude_config_root() { printf '%s' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; }

run_mcp() {
  # $1 fixture, rest: the add_mcp_server/add_mcp_http_server call. PATH and HOME are
  # the fixture's, so every command the function probes for is a stub or is absent.
  local fx="$TMP/$1"; shift
  ( export HOME="$fx/home" PATH="$fx/bin" CLAUDE_CONFIG_DIR="$fx/cfg"; "$@" ) \
    >"$TMP/out" 2>"$TMP/err"
  RC=$?
}

echo "0. no fixture can reach a host binary - the invariant, checked before anything runs"
# First, because it is the one that makes 2026-09-22's two incidents impossible
# rather than merely survivable. It asserts a PROPERTY OF THE HARNESS: nothing
# reachable from a fixture's bin dir may resolve outside $TMP. Without it, "stub()
# has an rm -f" is a fact about one function that someone will eventually edit, and
# the blast radius is the host's coreutils.
FX=invariant; mkfixture "$FX" >/dev/null
escapes=0; entries=0
for _e in "$TMP/$FX/bin"/*; do
  [ -e "$_e" ] || continue
  entries=$((entries+1))
  _r="$(readlink -f "$_e" 2>/dev/null || printf '')"
  case "$_r" in
    "$TMP"/*) ;;
    *) escapes=$((escapes+1)); red "        escapes: $_e -> ${_r:-<unresolvable>}" ;;
  esac
done
check "the fixture has entries to check"      yes "$([ "$entries" -gt 0 ] && echo yes || echo no)"
check "and NONE of them resolves outside \$TMP" 0  "$escapes"
check "the real tools were copied, not linked to /usr" yes \
  "$([ -f "$REALBIN/mktemp" ] && [ ! -L "$REALBIN/mktemp" ] && echo yes || echo no)"
check "and a copied multicall applet still runs" 0 \
  "$( "$REALBIN/mktemp" --help >/dev/null 2>&1; echo $? )"
check "the HOST's mktemp is untouched and still runs" 0 \
  "$( "$(readlink -f "$(command -v mktemp)")" --help >/dev/null 2>&1; echo $? )"

echo "A. MCP registration verifies the launch command before it registers"

echo "1. a launcher that does not resolve is refused, loudly, and nothing is written"
FX=mcp-no-npx; mkfixture "$FX" >/dev/null
stub "$FX" claude 'exit 0'
MCP_CACHE=""
run_mcp "$FX" add_mcp_server "azure" "-" npx -y "@azure/mcp@latest"
check "returns non-zero"                    no  "$([ "$RC" -eq 0 ] && echo yes || echo no)"
check "names the command that is missing"   yes "$(on_err "'npx' does not resolve on PATH")"
check "says why registering anyway is wrong" yes "$(on_err 'records a command without running it')"
check "did NOT claim the server was added"  no  "$(on_out "added MCP server 'azure'")"
check "and never ran 'claude mcp add'"      no  "$(called 'mcp add')"

echo "2. the refusal is on STDERR, not stdout"
# The whole point of the fix is that this reaches an operator whose stdout is a log
# of 40 install steps. A WARN on stdout is the silence the defect already had.
check "nothing about it on stdout"          no  "$(on_out 'does not resolve on PATH')"
check "all of it on stderr"                 yes "$(on_err 'does not resolve on PATH')"

echo "3. a launcher that DOES resolve is registered"
FX=mcp-npx; mkfixture "$FX" >/dev/null
stub "$FX" claude 'exit 0'
stub "$FX" npx 'exit 0'
MCP_CACHE=""
run_mcp "$FX" add_mcp_server "azure" "-" npx -y "@azure/mcp@latest"
check "returns 0"                           0   "$RC"
check "reports the server as added"         yes "$(on_out "added MCP server 'azure'")"
check "ran 'claude mcp add'"                yes "$(called 'mcp add')"
check "with the command after '--'"         yes "$(called -- 'npx -y @azure/mcp@latest')"
check "nothing on stderr"                   no  "$(on_err 'WARN')"

echo "4. an ALREADY-REGISTERED server with a missing launcher is not called fine"
# The idempotent path is where this defect is most expensive: "already registered"
# reads as reassurance, and a server registered blind on an earlier run cannot start
# any more than one registered blind now.
FX=mcp-stale; mkfixture "$FX" >/dev/null
stub "$FX" claude 'exit 0'
MCP_CACHE="azure"
run_mcp "$FX" add_mcp_server "azure" "-" npx -y "@azure/mcp@latest"
check "returns non-zero"                    no  "$([ "$RC" -eq 0 ] && echo yes || echo no)"
check "does NOT print 'already registered'" no  "$(on_out 'already registered')"
check "warns on stderr instead"             yes "$(on_err "'npx' does not resolve")"

echo "5. and the idempotent skip still works when the launcher IS there"
FX=mcp-idem; mkfixture "$FX" >/dev/null
stub "$FX" claude 'exit 0'
stub "$FX" npx 'exit 0'
MCP_CACHE="azure"
run_mcp "$FX" add_mcp_server "azure" "-" npx -y "@azure/mcp@latest"
check "returns 0"                           0   "$RC"
check "reports 'already registered'"        yes "$(on_out "MCP server 'azure' already registered")"
check "and does not re-add it"              no  "$(called 'mcp add')"

echo "6. the HTTP form has no launcher to check and is left alone"
# These rows register a URL. There is no executable whose absence could be detected,
# and the equivalent check would make this installer's success depend on the network
# being up at install time.
FX=mcp-http; mkfixture "$FX" >/dev/null
stub "$FX" claude 'exit 0'
MCP_CACHE=""
run_mcp "$FX" add_mcp_http_server "aws-knowledge" "https://knowledge-mcp.global.api.aws/mcp"
check "returns 0 with no npx present"       0   "$RC"
check "registers the endpoint"              yes "$(on_out "added MCP server 'aws-knowledge'")"
check "as an http transport"                yes "$(called -- '--transport http')"

echo "7. every command-launched call site goes through the one check"
# Structural, and it is the sabotage anchor for cases 1-5: a future call site that
# reaches 'claude mcp add' without passing through add_mcp_server would reintroduce
# the defect for exactly one server, which no behavioural case above would notice.
body="$(awk '/^add_mcp_server\(\) \{/,/^\}/' "$SCRIPT")"
case "$body" in *mcp_launcher_resolves*) got=yes ;; *) got=no ;; esac
check "add_mcp_server calls mcp_launcher_resolves" yes "$got"
# Before the check, after the skip, would be wrong; case 4 asserts the behaviour and
# this asserts the ordering it depends on, so a reordering fails here too.
order_check="$(printf '%s' "$body" | grep -n 'mcp_launcher_resolves\|mcp_server_registered' | head -2 | tr '\n' ' ')"
case "$order_check" in *mcp_launcher_resolves*mcp_server_registered*) got=yes ;; *) got=no ;; esac
check "and calls it BEFORE the already-registered skip" yes "$got"
# Counted as INVOCATIONS - a line whose first word is `claude` - not as occurrences
# of the string, which also appears in seven comments and in the guidance this script
# prints for a by-hand registration. Grepping the bare string counts those too and
# makes the number meaningless as an invariant.
adds="$(grep -cE '^[[:space:]]*claude mcp add ' "$SCRIPT")"
check "only add_mcp_server invokes 'claude mcp add'" 2 "$adds"
# add_mcp_http_server builds its arguments in an array and invokes `claude "${args[@]}"`,
# so it is counted separately rather than folded into the number above.
httpadds="$(grep -cE '^[[:space:]]*claude "\$\{args\[@\]\}"' "$SCRIPT")"
check "and add_mcp_http_server is the only other caller" 1 "$httpadds"

echo "8. the four Microsoft servers are counted, not swallowed"
# They were bare calls: each returned non-zero into nothing, the trailing guidance
# printed, and run_step recorded the row as successful.
# A call may span two lines (perplexity's does, because its env-spec is long), so the
# backslash-continued form is joined before the check rather than counted as a call
# with no handler - which is what it looks like line by line.
bare="$(sed -e ':a' -e '/\\$/{N;s/\\\n//;ba' -e '}' "$SCRIPT" \
  | grep -E '^[[:space:]]*add_mcp_server ' | grep -vc '|| ')"
check "no add_mcp_server call ignores its result" 0 "$bare"
case "$(awk '/^install_ms_mcp\(\) \{/,/^\}/' "$SCRIPT")" in
  *'[ "$mcp_failures" -eq 0 ] || return 1'*) got=yes ;; *) got=no ;;
esac
check "install_ms_mcp fails the step when any server failed" yes "$got"

echo
echo "B. skill Python dependencies are reported, on every OS, and installed by nobody"

mkskill() {
  # A fake INSTALLED skill: $fx/cfg/plugins/cache/<mkt>/<skill>/<version>/... , which
  # is the shape 'claude plugin install' actually produces (the version is in the
  # path, which is why the script searches rather than reconstructing it).
  local fx="$TMP/$1" skill="$2" dir
  dir="$fx/cfg/plugins/cache/useful-claude-add-ons/$skill/9.9.9"
  mkdir -p "$dir/scripts"
  printf 'x\n' > "$dir/requirements.txt"
  printf 'x\n' > "$dir/scripts/preflight.py"
}

only_skill() {
  # Tick exactly one skill, so a case reads one preflight and not 36.
  local want="$1" i
  for (( i=0; i<${#SKILL_KEYS[@]}; i++ )); do
    if [ "${SKILL_KEYS[$i]}" = "$want" ]; then SKILL_STATE[$i]=1; else SKILL_STATE[$i]=0; fi
  done
}

run_preflights() {
  local fx="$TMP/$1"
  ( export HOME="$fx/home" PATH="$fx/bin" CLAUDE_CONFIG_DIR="$fx/cfg"; run_skill_preflights ) \
    >"$TMP/out" 2>"$TMP/err"
  RC=$?
}

only_skill doc-builder

echo "9. everything present is the 'already installed' branch"
FX=pf-ok; mkfixture "$FX" >/dev/null; mkskill "$FX" doc-builder
stub "$FX" python3 'exit 0'
run_preflights "$FX"
check "returns 0"                           0   "$RC"
check "reports it as already satisfied"     yes "$(on_out 'doc-builder: Python dependencies already satisfied')"
check "using the script's SKIP: prefix"     yes "$(on_out 'SKIP:')"
check "ran the skill's own preflight.py"    yes "$(called 'preflight.py')"

echo "10. missing packages are named on STDERR and the run is not failed"
FX=pf-missing; mkfixture "$FX" >/dev/null; mkskill "$FX" doc-builder
stub "$FX" python3 'printf "  MISSING python-docx  -> needed by build_sop\n"
printf "  MISSING numpy        -> needed by verify_borders\n"
exit 3'
run_preflights "$FX"
check "returns 0 - a missing dep is not an install failure" 0 "$RC"
check "says the dependencies are MISSING"   yes "$(on_err 'doc-builder: Python dependencies are MISSING')"
check "names python-docx"                   yes "$(on_err 'missing: python-docx')"
check "names numpy"                         yes "$(on_err 'missing: numpy')"
check "offers the distribution packages"    yes "$(on_err 'sudo apt install python3-docx')"
check "offers the venv the skill owns"      yes "$(on_err -- '--venv')"
check "offers pip --user, with its caveat"  yes "$(on_err -- '--break-system-packages')"
check "and none of it is on stdout"         no  "$(on_out 'MISSING')"

echo "11. it installs nothing - that is the whole design, not an accident"
# preflight.py --venv WOULD work under PEP 668 and is still wrong: it provisions an
# interpreter nothing tells Claude to use, so the packages would be installed, unused,
# and the skill would still fail while this step reported success.
check "no --install flag was passed"        no  "$(called -- '--install')"
check "no --venv was created"               no  "$(called -- 'preflight.py --venv')"
check "pip was never invoked"               no  "$(called 'pip ')"

echo "12. stdin is closed, so the preflight's prompt cannot eat the script"
# preflight.py offers to install what is missing and its confirm() reads stdin. Under
# 'curl | bash' fd 0 is the rest of THIS SCRIPT.
FX=pf-stdin; mkfixture "$FX" >/dev/null; mkskill "$FX" doc-builder
# The marker goes to a FILE, not to stdout: run_skill_preflights captures the
# preflight's own output into a temp file it then greps, so anything the stub prints
# is invisible to on_out/on_err by design.
stub "$FX" python3 'if IFS= read -r line; then printf "STDIN=%s\n" "$line" > '"'$TMP/$FX/stdin'"'; else printf "STDIN=EOF\n" > '"'$TMP/$FX/stdin'"'; fi
exit 3'
( export HOME="$TMP/$FX/home" PATH="$TMP/$FX/bin" CLAUDE_CONFIG_DIR="$TMP/$FX/cfg"
  printf 'THIS LINE MUST NOT BE EATEN\n' | run_skill_preflights ) >"$TMP/out" 2>"$TMP/err"
check "the preflight saw EOF immediately"   "STDIN=EOF" "$(cat "$TMP/$FX/stdin" 2>/dev/null)"
check "and not the caller's next line"      no  "$(grep -qF 'MUST NOT BE EATEN' "$TMP/$FX/stdin" 2>/dev/null && echo yes || echo no)"

echo "13. an unexpected exit code is UNCHECKED, never 'fine'"
# "Could not tell" has to survive as its own value. Collapsing it into the
# safe-looking one is this repo's named recurring bug.
FX=pf-broken; mkfixture "$FX" >/dev/null; mkskill "$FX" doc-builder
stub "$FX" python3 'printf "Traceback (most recent call last):\n" >&2
printf "ModuleNotFoundError: No module named %s\n" render_engine >&2
exit 1'
run_preflights "$FX"
check "returns 0"                           0   "$RC"
check "says UNCHECKED, not absent"          yes "$(on_err 'UNCHECKED - not absent, unchecked')"
check "names the exit code"                 yes "$(on_err 'preflight exited 1')"
check "and quotes what it printed"          yes "$(on_err 'ModuleNotFoundError')"
check "does not claim the deps are present" no  "$(on_out 'already satisfied')"

echo "13b. and so is preflight.py's OWN hard-failure code, 2"
# Not a duplicate of 13. The branch is a case default, and narrowing it to the one
# code a single case happens to use ('1)' instead of '*)') leaves every other status
# matching nothing and printing nothing - silence that reads exactly like success.
# Sabotaging 13 alone did not go red; this is the case that catches it. preflight.py
# returns 2 for "pip failed" and "could not create the venv".
FX=pf-rc2; mkfixture "$FX" >/dev/null; mkskill "$FX" doc-builder
stub "$FX" python3 'printf "FAILED: pip exited 1\n" >&2
exit 2'
run_preflights "$FX"
check "returns 0"                           0   "$RC"
check "says UNCHECKED, not absent"          yes "$(on_err 'UNCHECKED - not absent, unchecked')"
check "names the exit code"                 yes "$(on_err 'preflight exited 2')"
check "does not claim the deps are present" no  "$(on_out 'already satisfied')"
check "and says something at all"           yes "$(on_err 'doc-builder')"

echo "14. no Python at all is UNCHECKED too, and says which names it tried"
FX=pf-nopython; mkfixture "$FX" >/dev/null; mkskill "$FX" doc-builder
run_preflights "$FX"
check "returns 0"                           0   "$RC"
check "names python3, python and py"        yes "$(on_err 'none of python3, python or py is on PATH')"
check "says UNCHECKED, not absent"          yes "$(on_err 'UNCHECKED - not absent, unchecked')"
check "on stderr, not stdout"               no  "$(on_out 'none of python3')"

echo "15. idempotent: it reads the machine and writes nothing"
FX=pf-idem; mkfixture "$FX" >/dev/null; mkskill "$FX" doc-builder
stub "$FX" python3 'exit 0'
run_preflights "$FX"
first="$(cat "$TMP/out")"
before="$(find "$TMP/$FX/cfg" -type f | sort | tr '\n' ' ')"
run_preflights "$FX"
second="$(cat "$TMP/out")"
after="$(find "$TMP/$FX/cfg" -type f | sort | tr '\n' ' ')"
check "the second run says the same thing"  yes "$([ "$first" = "$second" ] && echo yes || echo no)"
check "and the skill tree is unchanged"     yes "$([ "$before" = "$after" ] && echo yes || echo no)"
check "no .venv was created"                no  "$(find "$TMP/$FX/cfg" -name '.venv' -print -quit | grep -q . && echo yes || echo no)"

echo "16. a skill with no preflight is not invented"
FX=pf-none; mkfixture "$FX" >/dev/null
stub "$FX" python3 'exit 0'
run_preflights "$FX"
check "returns 0"                           0   "$RC"
check "says there was nothing to check"     yes "$(on_out 'no selected skill ships a scripts/preflight.py')"
check "and python was never run"            no  "$(called 'preflight.py')"

echo
echo "C. the community marketplace, eli5 and github"

spec_for() {
  # $1 prefix, $2 key -> its <PREFIX>_SPEC entry, or the empty string.
  local prefix="$1" want="$2" i n
  n="$(group_count "$prefix")"
  for (( i=0; i<n; i++ )); do
    [ "$(group_key "$prefix" "$i")" = "$want" ] && { group_spec "$prefix" "$i"; return 0; }
  done
  return 1
}

echo "17. the community marketplace's LOCAL NAME is 'claude-community'"
# The trap this case exists for: add_marketplace probes by NAME, so the repo name in
# that field makes the probe look for something that never exists - the step re-adds
# the marketplace on every run while printing "added marketplace". Idempotence lost,
# silently, with a success message on top.
eli5="$(spec_for COMMUNITY eli5 || printf '')"
check "eli5 is in the community catalog"    yes "$([ -n "$eli5" ] && echo yes || echo no)"
check "its plugin@marketplace"              "eli5@claude-community"                  "${eli5%%|*}"
rest="${eli5#*|}"
check "its marketplace SOURCE is the repo"  "anthropics/claude-plugins-community"    "${rest%%|*}"
check "its marketplace NAME is the local one" "claude-community"                     "${rest#*|}"
check "the repo name is never used as a marketplace name" 0 \
  "$(grep -c '|claude-plugins-community$' "$SCRIPT")"

echo "18. github is ANTHROPIC'S plugin, and this repo's own github skill is untouched"
# The two readings of "github skills". Evidence for choosing this one: this repo's own
# 'github' is ALREADY installed by the own-skills row - it is in SKILL_KEYS and
# SKILL_SPEC builds 'github@useful-claude-add-ons' for it - so adding that would be a
# no-op that reads like a fix. anthropics/claude-plugins-official publishes a
# different plugin under the same bare name (the GitHub MCP server), and
# anthropics/claude-plugins-community publishes no 'github' at all.
gh="$(spec_for TEAM github || printf '')"
check "github is in the team catalog"       yes "$([ -n "$gh" ] && echo yes || echo no)"
check "from claude-plugins-official"        "github@claude-plugins-official"          "${gh%%|*}"
rest="${gh#*|}"
check "sourced from anthropics/"            "anthropics/claude-plugins-official"      "${rest%%|*}"
check "named claude-plugins-official"       "claude-plugins-official"                 "${rest#*|}"
present=no
for k in "${SKILL_KEYS[@]}"; do [ "$k" = "github" ] && present=yes; done
check "this repo's own github skill is still in SKILL_KEYS" yes "$present"
check "and is still sourced from this repo" yes \
  "$(spec_for SKILL github | grep -qF 'github@useful-claude-add-ons|' && echo yes || echo no)"

echo "19. the plugin cache no longer collapses two marketplaces onto one bare name"
# Without this, 'github@claude-plugins-official' on a machine that already has this
# repo's github printed "plugin 'github' already installed" and installed nothing -
# and the SKIP line IS the success path, so nothing downstream could catch it.
PLUGINS_CACHE="$(printf 'github\t1.0.0\t1\tuseful-claude-add-ons\nsuperpowers\t2.0.0\t1\tclaude-plugins-official')"
check "the installed copy is found by name"        "1.0.0" "$(plugin_version github)"
check "and from its own marketplace"               yes "$(plugin_installed_from github useful-claude-add-ons && echo yes || echo no)"
check "but NOT from the other one"                 no  "$(plugin_installed_from github claude-plugins-official && echo yes || echo no)"
check "an empty marketplace keeps the old answer"  yes "$(plugin_installed_from github '' && echo yes || echo no)"
check "a name nobody installed is still absent"    no  "$(plugin_installed_from eli5 claude-community && echo yes || echo no)"
check "the message can name where it came from"    "useful-claude-add-ons" "$(plugin_marketplaces github)"
PLUGINS_CACHE="$(printf 'github\t1.0.0\t1\tuseful-claude-add-ons\ngithub\t9.0.0\t1\tclaude-plugins-official')"
check "both copies are held at once"               yes "$(plugin_installed_from github claude-plugins-official && echo yes || echo no)"
check "and both are named"                         "useful-claude-add-ons, claude-plugins-official" "$(plugin_marketplaces github)"
case "$(awk '/^install_plugin\(\) \{/,/^\}/' "$SCRIPT")" in
  *'! plugin_installed_from "$name" "$mkt"'*) got=yes ;; *) got=no ;;
esac
check "install_plugin consults it"                 yes "$got"

echo "20. end to end: the eli5 row registers claude-community once, and only once"
# The real script, with a stub 'claude' that records what it was asked to do and a
# CLAUDE_CONFIG_DIR in the temp tree. Nothing is installed and no marketplace is added.
E2E="$TMP/e2e"; mkdir -p "$E2E/bin" "$E2E/cfg"
rm -f "$E2E/bin/claude"
{
  echo "#!$BASH_ABS"
  echo 'printf "%s\n" "$*" >> '"'$E2E/calls'"
  echo 'case "$*" in'
  echo '  "plugin list --json") echo "[]" ;;'
  echo '  "plugin marketplace list --json") echo "[]" ;;'
  echo '  "mcp list") : ;;'
  echo 'esac'
  echo 'exit 0'
} > "$E2E/bin/claude"
chmod +x "$E2E/bin/claude"
: > "$E2E/calls"
CLAUDE_CONFIG_DIR="$E2E/cfg" PATH="$E2E/bin:$PATH" \
  bash "$SCRIPT" --select community --community eli5 >"$TMP/out" 2>"$TMP/err"
check "the marketplace step names the source"   yes "$(on_out 'Marketplace: anthropics/claude-plugins-community')"
check "the plugin step names the local name"    yes "$(on_out 'Plugin: eli5@claude-community')"
check "one 'marketplace add' call, not two"     1   "$(grep -c 'plugin marketplace add anthropics/claude-plugins-community' "$E2E/calls")"
check "the add names the SOURCE, not the local name" 0 \
  "$(grep -c 'plugin marketplace add claude-community' "$E2E/calls")"
check "and eli5 is installed from claude-community" 1 \
  "$(grep -c 'plugin install eli5@claude-community' "$E2E/calls")"

echo "21. and a second run re-adds nothing"
# The marketplace probe reads 'claude plugin marketplace list --json'. Feeding it the
# registration the first run would have made is what makes idempotence observable
# without ever registering anything for real.
rm -f "$E2E/bin/claude"
{
  echo "#!$BASH_ABS"
  echo 'printf "%s\n" "$*" >> '"'$E2E/calls'"
  echo 'case "$*" in'
  echo '  "plugin list --json") echo "[{\"id\":\"eli5@claude-community\",\"version\":\"1.0.0\",\"enabled\":true}]" ;;'
  echo '  "plugin marketplace list --json") echo "[{\"name\":\"claude-community\",\"source\":\"github\",\"repo\":\"anthropics/claude-plugins-community\"}]" ;;'
  echo '  "mcp list") : ;;'
  echo 'esac'
  echo 'exit 0'
} > "$E2E/bin/claude"
chmod +x "$E2E/bin/claude"
: > "$E2E/calls"
CLAUDE_CONFIG_DIR="$E2E/cfg" PATH="$E2E/bin:$PATH" \
  bash "$SCRIPT" --select community --community eli5 >"$TMP/out" 2>"$TMP/err"
check "reports the marketplace as already registered" yes "$(on_out "marketplace 'claude-community' already registered")"
check "and adds it no second time"                    0   "$(grep -c 'plugin marketplace add' "$E2E/calls")"

echo
echo "D. both halves of the pair"

PWSH="${PWSH:-}"
if [ -z "$PWSH" ]; then
  # Absolute paths only: 'pwsh' is not on Git Bash's PATH, and a bare name fails as
  # "command not found", which reads as a FAILED CHECK rather than a missing tool.
  for c in /snap/bin/pwsh /usr/bin/pwsh /usr/local/bin/pwsh \
           /opt/microsoft/powershell/7/pwsh \
           "C:/Program Files/PowerShell/7/pwsh.exe"; do
    [ -x "$c" ] && { PWSH="$c"; break; }
  done
fi

echo "22. the .ps1 carries the same two catalog entries, character for character"
# check_group_parity in check-marketplace.py compares KEYS only; the Spec strings are
# read by nothing, so two halves can agree on keys and disagree on where a plugin
# comes from. That is the failure this case covers and the gate cannot.
ps_spec() {
  # $1 catalog name, $2 key -> the Spec string from the .ps1. Both awk variables are
  # built as plain shell locals first: the literal '$script:' and the single quotes
  # around a PowerShell key need no escaping that way, and getting that wrong is how
  # this returned the empty string for every key while the awk program was correct.
  local opener key
  opener="\$script:$1 = @("
  key="Key = '$2'"
  awk -v opener="$opener" -v key="$key" '
    index($0, opener) { inside = 1; next }
    inside && /^\)/ { inside = 0 }
    inside && index($0, key) {
      q = index($0, "Spec = ")
      if (q) {
        rest = substr($0, q + 8)
        e = index(rest, "\047")
        if (e) print substr(rest, 1, e - 1)
      }
    }
  ' "$PS1SCRIPT"
}
check "eli5's Spec matches the .sh"         "$eli5" "$(ps_spec CommunityCatalog eli5)"
check "github's Spec matches the .sh"       "$gh"   "$(ps_spec TeamCatalog github)"
check "the .ps1 never uses the repo name as a marketplace name" 0 \
  "$(grep -c "|claude-plugins-community'" "$PS1SCRIPT")"

echo "23. the .ps1 carries the same two fixes"
# Structural on this side too: the behavioural cases above run bash. Running the
# PowerShell equivalents needs pwsh and is case 24.
case "$(awk '/^function Add-McpServer/,/^}/' "$PS1SCRIPT")" in
  *'Get-Command $launcher'*) got=yes ;; *) got=no ;;
esac
check "Add-McpServer checks the launcher"   yes "$got"
case "$(awk '/^function Add-McpServer/,/^}/' "$PS1SCRIPT")" in
  *Write-WarnErr*) got=yes ;; *) got=no ;;
esac
check "and warns on stderr, like the .sh"   yes "$got"
case "$(awk '/^function Install-ClaudePlugin/,/^}/' "$PS1SCRIPT")" in
  *'Marketplaces) -notcontains $wantMkt'*) got=yes ;; *) got=no ;;
esac
check "Install-ClaudePlugin is marketplace-aware" yes "$got"
check "Invoke-SkillPreflights exists"       1 "$(grep -c '^function Invoke-SkillPreflights' "$PS1SCRIPT")"
check "and is wired into the own-skills row" 1 "$(grep -c 'Invoke-SkillPreflights$' "$PS1SCRIPT")"
check "it passes no --install"              0 "$(awk '/^function Invoke-SkillPreflights/,/^}/' "$PS1SCRIPT" | grep -c -- '--install')"
check "and redirects stdin from a file"     yes \
  "$(awk '/^function Invoke-SkillPreflights/,/^}/' "$PS1SCRIPT" | grep -q -- '-RedirectStandardInput' && echo yes || echo no)"

if [ -z "$PWSH" ]; then
  printf '\033[90m%s\033[0m\n' "24. SKIPPED: no pwsh found at any of /snap/bin/pwsh, /usr/bin/pwsh,"
  printf '\033[90m%s\033[0m\n' "    /usr/local/bin/pwsh, /opt/microsoft/powershell/7/pwsh. That is a MISSING"
  printf '\033[90m%s\033[0m\n' "    TOOL, not a failed check - the .ps1 half is structurally checked by case"
  printf '\033[90m%s\033[0m\n' "    23 above and BEHAVIOURALLY UNVERIFIED in this run. Set"
  printf '\033[90m%s\033[0m\n' "    PWSH=/absolute/path/to/pwsh to run it."
else
  echo "24. .ps1: Add-McpServer refuses a launcher that does not resolve"
  FX=ps-mcp; mkfixture "$FX" >/dev/null
  stub "$FX" claude 'exit 0'
  {
    awk '/^\$script:FailedSteps = @\(\)/,/^function Write-Skip/' "$PS1SCRIPT"
    awk '/^function Write-WarnErr/,/^}/' "$PS1SCRIPT"
    cat <<'SHIM'
$InstallScope = 'user'
function Test-ClaudeAvailable { return $true }
function Test-McpServerRegistered { param([string]$Name) return $false }
function Get-ClaudeMcpServers { param([switch]$Refresh) return @() }
SHIM
    awk '/^function Add-McpServer/,/^}/' "$PS1SCRIPT"
    cat <<'TAIL'
$err = ''
try { Add-McpServer -Name 'azure' -CommandArgs @('npx','-y','@azure/mcp@latest') } catch { $err = $_.Exception.Message }
"ERR=$err"
TAIL
  } > "$TMP/$FX/harness.ps1"
  ( env -u PSModulePath PATH="$TMP/$FX/bin" HOME="$TMP/$FX/home" \
      "$PWSH" -NoProfile -NoLogo -File "$TMP/$FX/harness.ps1" ) >"$TMP/out" 2>"$TMP/err"
  check "it throws rather than registering"  no  "$(grep -q '^ERR=$' "$TMP/out" && echo yes || echo no)"
  check "the message names npx"              yes "$(on_out "'npx' is not on PATH")"
  check "the WARN is on stderr"              yes "$(on_err 'does not resolve on PATH')"
  check "and not on stdout"                  no  "$(on_out 'does not resolve on PATH')"
  check "it never claimed the server was added" no "$(on_out "added MCP server")"

  echo "25. .ps1: a launcher that resolves is registered"
  stub "$FX" npx 'exit 0'
  ( env -u PSModulePath PATH="$TMP/$FX/bin" HOME="$TMP/$FX/home" \
      "$PWSH" -NoProfile -NoLogo -File "$TMP/$FX/harness.ps1" ) >"$TMP/out" 2>"$TMP/err"
  check "no error"                           yes "$(grep -q '^ERR=$' "$TMP/out" && echo yes || echo no)"
  check "reports the server as added"        yes "$(on_out "added MCP server 'azure'")"
  check "and ran 'claude mcp add'"           yes "$(called 'mcp add')"
fi

echo
if [ "$FAIL" -eq 0 ]; then green "$PASS passed, 0 failed"; exit 0; fi
red "$PASS passed, $FAIL FAILED"
exit 1
