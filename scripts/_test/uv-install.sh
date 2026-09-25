#!/usr/bin/env bash
# Regression suite for the uv install path in BOTH halves of the matched pair:
# ensure_uv in scripts/install-prerequisites.sh, and Install-Uv in
# scripts/install-prerequisites.ps1.
#
# The defect this started as: on any distribution that enforces PEP 668 (Debian 12+,
# Ubuntu 23.04+, Fedora 38+) `pip3 install --user uv` exits 1 with
# "error: externally-managed-environment", and two of the three callers did not
# look at that exit status. The run then carried on and registered an MCP server
# whose uvx does not exist, with nothing pointing back at the step that failed.
#
# So the cases below assert these separately, because fixing one of them while
# leaving the others is what happened the first time, twice:
#   - the chain reaches a working uv without pip where PEP 668 is enforced;
#   - a total failure returns non-zero and says so on STDERR, not stdout;
#   - "could not tell whether PEP 668 applies" is its own outcome and is stated,
#     rather than collapsing into the safe-looking "it does not apply";
#   - the astral.sh installer is fetched over https only (redirects included), by
#     PINNED version, checked against a pinned sha256, and not run on a mismatch,
#     on a digest that could not be computed, or with no pin recorded;
#   - every label in the final "Tried:" list means what it says - in particular a
#     run in which curl was never invoked must not report the installer as tried;
#   - $HOME/.local/bin joins PATH only when the probe then succeeds, never twice,
#     and never at all when running as root with a HOME root does not own;
#   - the chain runs ONCE per run, not once per selected row;
#   - every package-manager arm of install_pipx_package, not just apt;
#   - and the .ps1 half's own rungs, including the winget rung that is this side's
#     equivalent of the standalone installer.
#
# Needs: bash, coreutils. pwsh is optional - without it cases 21-25 SKIP loudly and
# say that Install-Uv went unverified in that run.
#
# Installs NOTHING, downloads nothing, and touches no real config - every tool either
# function reaches for (pipx, pip3, pip, curl, wget, winget, apt-get, dnf, yum,
# pacman, zypper, apk, sudo, python3, mktemp, id, stat, sha256sum) is a throwaway stub
# in a temp dir, and PATH and HOME are pointed at that dir, so neither the host's
# package manager, its Python, nor astral.sh is ever reached.
#     ./scripts/_test/uv-install.sh
# Exit status is 0 when every case passes, 1 when any FAILED, and 77 when
# nothing failed but cases 21-25 (the .ps1 parity cases) SKIPPED for a
# missing pwsh - a run that did not check everything it claims to, which 0
# would not distinguish from a genuinely complete pass. The run prints its
# own totals; re-measure from that line rather than trusting a count
# written into a comment.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO/scripts/install-prerequisites.sh"
PASS=0
FAIL=0
# Set to 1 when a case is skipped for a MISSING TOOL (pwsh absent, cases 21-25
# below) rather than for anything this suite found wrong. FAIL==0 with this set
# used to still exit 0 - "PASSED" - even though five cases never ran at all;
# see the exit logic at the bottom of this file.
TOOL_SKIPPED=0
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
# Trapped IMMEDIATELY, before the pin check below can also exit 2. A TMP that
# mktemp DID create but that then fails the pin would otherwise leak forever -
# nothing would ever rm -rf it, since the trap that does that wasn't set yet.
trap 'rm -rf "$TMP"' EXIT
# Every guard below that bounds a write to "$TMP"/* becomes a no-op check against
# the literal pattern '/*' if $TMP is ever empty - it would match ANY absolute
# path, including the filesystem root, and a case's 'rm -rf "$fx"' or 'chmod' could
# then land outside this suite entirely, as root if the suite runs as root. The
# check above already refuses that specific case.
# The pin below is a SEPARATE hazard, and not "mktemp can succeed somewhere
# unexpected" - mktemp always succeeds wherever TMPDIR points, precisely as
# documented. The real reason: this suite does 'rm -rf' under $TMP (this trap,
# and every mkfixture's own 'rm -rf "$fx"'), and TMPDIR is caller-controlled -
# it could validly name this repo's own working tree, a parent of it, or
# (running as root) the filesystem root, all of which mktemp would honour
# without complaint. None of that requires $TMP to be empty; a plain
# ordinary-looking TMPDIR is enough on its own. So $TMP is pinned under a
# known-safe root explicitly, rather than trusted to have landed somewhere a
# runaway 'rm -rf' or glob cannot reach the repo or /.
_tmpdir="${TMPDIR:-/tmp}"
while [ "$_tmpdir" != "/" ] && [ "${_tmpdir: -1}" = "/" ]; do _tmpdir="${_tmpdir%/}"; done
case "$TMP" in
  "$_tmpdir"/*) ;;
  *)
    echo "FATAL: \$TMP ($TMP) is not under \${TMPDIR:-/tmp} ($_tmpdir) - refusing to run" >&2
    exit 2
    ;;
esac

# The exact list of tools mkrealbin copies and mkfixture links to - ONE variable,
# used by both plus the host baseline below, so a tool added to one can never
# drift out of sync with the others.
REALBIN_TOOLS="mktemp rm sh mkdir chmod cp id stat sha256sum"

# The pristine identity of every HOST tool in $REALBIN_TOOLS, captured before
# mkrealbin or anything else touches PATH. The "HOST tools are untouched" check
# near the end of this file compares against this per-tool baseline - path,
# content hash, mode, owner, group and ctime - rather than re-running a
# stubbable command like '--help', and rather than content alone: a chmod
# (exactly the incident this baseline exists for - mkrealbin's own guard chmod
# followed a sabotaged symlink and touched /usr/bin/find's mode and ctime)
# changes mode and ctime without touching content, and a hash-only check
# cannot see that. Every name in $REALBIN_TOOLS is covered, not just mktemp.
HOST_BASELINE="$TMP/host-baseline"
: > "$HOST_BASELINE"
for _t in $REALBIN_TOOLS; do
  _p="$(command -v "$_t" 2>/dev/null)" || continue
  [ -n "$_p" ] || continue
  _p="$(readlink -f "$_p")"
  _h="$(sha256sum "$_p" 2>/dev/null | awk '{print $1}')"
  _s="$(stat -c '%a %u %g %Z' "$_p" 2>/dev/null)"
  printf '%s\t%s\t%s\t%s\n' "$_t" "$_p" "$_h" "$_s" >> "$HOST_BASELINE"
done
unset _t _p _h _s _tmpdir

# Re-measures every tool in the baseline and reports EXACTLY what changed - which
# tool and which field (content, mode, owner, group or ctime) - rather than a
# bare yes/no, so a FAIL names the incident instead of merely flagging one.
host_tools_intact() {
  local t p h s h2 s2 old_mode old_uid old_gid old_ctime new_mode new_uid new_gid new_ctime bad=""
  while IFS=$'\t' read -r t p h s; do
    if [ ! -e "$p" ]; then bad="$bad tool=$t field=missing($p)"; continue; fi
    h2="$(sha256sum "$p" 2>/dev/null | awk '{print $1}')"
    s2="$(stat -c '%a %u %g %Z' "$p" 2>/dev/null)"
    [ "$h2" = "$h" ] || bad="$bad tool=$t field=content"
    if [ "$s2" != "$s" ]; then
      set -- $s;  old_mode=$1 old_uid=$2 old_gid=$3 old_ctime=$4
      set -- $s2; new_mode=$1 new_uid=$2 new_gid=$3 new_ctime=$4
      [ "$old_mode"  = "$new_mode"  ] || bad="$bad tool=$t field=mode(was=$old_mode now=$new_mode)"
      [ "$old_uid"   = "$new_uid"   ] || bad="$bad tool=$t field=owner(was=$old_uid now=$new_uid)"
      [ "$old_gid"   = "$new_gid"   ] || bad="$bad tool=$t field=group(was=$old_gid now=$new_gid)"
      [ "$old_ctime" = "$new_ctime" ] || bad="$bad tool=$t field=ctime(was=$old_ctime now=$new_ctime)"
    fi
  done < "$HOST_BASELINE"
  if [ -z "$bad" ]; then echo yes; else echo "CHANGED:$bad"; fi
}

# --- load the helper layer and the uv layer out of the real script ------------
# Same idiom as menu-groups.sh: the suite tests the shipped code, never a copy.
COUNT_INSTALLED=0
COUNT_SKIPPED=0
FAILED_STEPS=()
eval "$(awk '/^step\(\)/,/^have\(\) \{/' "$SCRIPT")"
eval "$(awk '/^# --- uv, under PEP 668/,/^# --- JSON helper/' "$SCRIPT" | sed '$d')"

# The two pin values AS SHIPPED. Cases below override the live variables to exercise
# the fetch-and-verify path; case 7d puts these back to assert what the committed
# script actually does, which is the security property - not what a fixture can do.
SHIPPED_UV_VERSION="$UV_INSTALLER_VERSION"
SHIPPED_UV_SHA256="$UV_INSTALLER_SHA256"

# --- fixtures ----------------------------------------------------------------
# A fixture is a bin dir that is the WHOLE of PATH, plus a HOME whose ~/.local/bin
# is where a successful install is expected to land. Only the three coreutils
# ensure_uv itself calls are linked in; everything else has to be stubbed
# explicitly, so "the host happened to have it" can never make a case pass.
BASH_ABS="$(command -v bash)"

# --- the real tools a fixture may need, COPIED into $TMP first ----------------
# Fixtures used to symlink straight at /usr/bin/<tool>. That put a link to a HOST
# BINARY inside the very directory stub() writes into, so the only thing standing
# between this suite and the host's coreutils was stub() remembering to rm -f first.
# On 2026-09-22 that was proven the hard way TWICE: once when the rm was missing, and
# again when someone removed it deliberately to sabotage-test the fix and ran the
# whole suite - 116 hardlinks into one uutils multicall binary, overwritten with a
# three-line shell stub, and every case after it failing for unrelated-looking
# reasons.
#
# So the hazard is removed rather than guarded: every fixture link now points at a
# COPY inside $TMP. A write-through can now only ever reach that copy, whether or not
# stub()'s rm -f is present, which is what makes the guard safe to sabotage-test at
# all. The rm -f stays - it is still correct, and case 26 still pins it - but it is no
# longer the only thing preventing damage.
#
# One copy per distinct INODE, not per name: on this host those nine names are
# hardlinks into one 11 MB multicall binary, so copying each would cost ~100 MB per
# run. uutils dispatches on argv[0], and a hardlink inside $TMP keeps the name, so
# the copies behave exactly as the originals do.
REALBIN="$TMP/realbin"
mkrealbin() {
  mkdir -p "$REALBIN"
  local t src key rep seen=""
  for t in $REALBIN_TOOLS; do
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
    # Never chmod through a symlink: chmod follows one to its target, and a $REALBIN
    # entry that is a symlink (mkrealbin reverted to 'ln -s', or 'ln' above fell
    # through to something unexpected) would silently set +x on whatever it points
    # at - which could be a host binary. This is what actually happened in review:
    # the 'else' branch was sabotaged back to 'ln -s' and this chmod touched the
    # host's /usr/bin/find. Refuse outright rather than rely on case 0 to catch it
    # after the fact.
    case "$REALBIN/$t" in
      "$TMP"/*) ;;
      *) red "REFUSING to chmod outside \$TMP: $REALBIN/$t"; exit 2 ;;
    esac
    if [ -f "$REALBIN/$t" ] && [ ! -L "$REALBIN/$t" ]; then
      chmod +x "$REALBIN/$t"
    else
      red "REFUSING to chmod $REALBIN/$t: not a plain regular file (mkrealbin may be symlinking again)"
      exit 2
    fi
  done
}
mkrealbin

mkfixture() {
  local fx="$TMP/$1" t
  rm -rf "$fx"
  mkdir -p "$fx/bin" "$fx/home/.local/bin"
  : > "$fx/calls"
  # Only the plumbing an install needs to be able to land a file at all. Every
  # tool ensure_uv actually PROBES for - uv, uvx, pipx, pip3, pip, curl, wget,
  # python3/python/py, apt-get and friends - is absent unless a case stubs it,
  # so "the host happened to have it" can never make a case pass.
  # id/stat back uv_home_is_safe and sha256sum backs the installer pin check; a case
  # that wants a different answer from any of them stubs it over the top.
  # $REALBIN, never /usr/bin: see mkrealbin above. Nothing in a fixture may resolve
  # to a host binary, and case 0 asserts that as a standing invariant.
  for t in $REALBIN_TOOLS; do
    [ -e "$REALBIN/$t" ] && ln -s "$REALBIN/$t" "$fx/bin/$t"
  done
  # as_root prefers sudo when not uid 0; stub it so the case behaves the same
  # whether the suite runs as root or not.
  stub "$1" sudo 'exec "$@"'
  printf '%s' "$fx"
}

stub() {
  # $1 fixture name, $2 tool, rest: body lines. Every stub records its own call.
  # The interpreter is named ABSOLUTELY: a '#!/usr/bin/env bash' shebang resolves
  # bash through the *caller's* PATH, which these fixtures deliberately empty of
  # everything, so every stub silently exited 127 and the suite reported 19 green
  # 'the tool was not called' assertions that proved nothing.
  local fx="$TMP/$1" name="$2"; shift 2
  # Refuse outright to write anywhere but the temp tree. This is SEPARATE from the
  # rm below and neither replaces the other: this one bounds the PATH, the rm bounds
  # what a symlink at that path can redirect the write to. Case 26 tests the second.
  case "$fx/bin/$name" in
    "$TMP"/*) ;;
    *) red "REFUSING to write a stub outside \$TMP: $fx/bin/$name"; exit 2 ;;
  esac
  # rm FIRST, and this is not tidiness. mkfixture symlinks the handful of coreutils
  # a fixture needs to their REALBIN COPIES in $fx/bin (never to the host directly -
  # see mkrealbin above); a case that stubs one of those names (mktemp, id, stat,
  # sha256sum) would otherwise have its '>' redirect FOLLOW the symlink and truncate
  # the copy it names. Before mkrealbin copied rather than linked, those links
  # pointed at the host's own binaries directly: on this repo's reference host those
  # names are hardlinks into one uutils multicall binary, so stubbing `mktemp` took
  # out ls, cat, cp, stat and 110 others in one redirect. Measured, not theorised -
  # it happened while this case was being written, on 2026-09-22.
  rm -f "$fx/bin/$name"
  {
    echo "#!$BASH_ABS"
    echo "printf '%s %s\\n' '$name' \"\$*\" >> '$fx/calls'"
    printf '%s\n' "$@"
  } > "$fx/bin/$name"
  chmod +x "$fx/bin/$name"
}

# A stub that behaves like a successful uv install: drops a uv into ~/.local/bin,
# which is exactly where pipx, pip --user and astral's installer all put it.
lands_uv='mkdir -p "$HOME/.local/bin"
printf "#!/bin/sh\nexit 0\n" > "$HOME/.local/bin/uv"
chmod +x "$HOME/.local/bin/uv"
exit 0'

run_case() {
  # $1 fixture name. Runs ensure_uv with PATH and HOME confined to the fixture.
  local fx="$TMP/$1"
  ( export HOME="$fx/home" PATH="$fx/bin"; ensure_uv ) >"$TMP/out" 2>"$TMP/err"
  RC=$?
}

run_case_twice() {
  # Two ensure_uv calls inside ONE shell, which is what a real run does: three
  # selectable rows call it in turn. Both results and the two counters come back on
  # fd 3 because stdout and stderr are what the assertions read.
  local fx="$TMP/$1" rc1 rc2
  ( export HOME="$fx/home" PATH="$fx/bin"
    ensure_uv; rc1=$?
    ensure_uv; rc2=$?
    printf 'RC1=%s\nRC2=%s\nSKIPPED=%s\nINSTALLED=%s\n' \
      "$rc1" "$rc2" "$COUNT_SKIPPED" "$COUNT_INSTALLED" >&3
  ) 3>"$TMP/memo" >"$TMP/out" 2>"$TMP/err"
  RC=$?
}

memo_field() { sed -n "s/^$1=//p" "$TMP/memo"; }

# -e, not a bare pattern: the strings looked for include '--break-system-packages'.
on_out()  { grep -qF -e "$1" "$TMP/out" && echo yes || echo no; }
on_err()  { grep -qF -e "$1" "$TMP/err" && echo yes || echo no; }
called()  { grep -q "^$1 " "$TMP/${FX}/calls" && echo yes || echo no; }

echo "0. no fixture can reach a host binary - the invariant, checked before anything runs"
# This case is first because it is the one that would have made 2026-09-22's two
# incidents impossible rather than merely survivable. It asserts a PROPERTY OF THE
# HARNESS, not of the install script: nothing reachable from a fixture's bin dir may
# resolve outside $TMP. Without it, "stub() has an rm -f" is a fact about one function
# that someone will eventually edit, and the blast radius is the host.
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
# The copies must still WORK - a copy of a multicall binary that cannot dispatch on
# its own name would make every later case fail for a reason nothing here explains.
check "and a copied multicall applet still runs" 0 \
  "$( "$REALBIN/mktemp" --help >/dev/null 2>&1; echo $? )"

echo "1. idempotence: uv already present is detected and nothing is done"
FX=have-uv; mkfixture "$FX" >/dev/null
stub "$FX" uv 'exit 0'
stub "$FX" pipx "$lands_uv"
stub "$FX" pip3 "$lands_uv"
stub "$FX" curl 'exit 0'
run_case "$FX"
check "returns 0"                        0   "$RC"
check "says 'already installed'"         yes "$(on_out 'uv already installed')"
check "uses the script's SKIP: prefix"   yes "$(on_out 'SKIP:')"
check "does not run pipx"                no  "$(called pipx)"
check "does not run pip3"                no  "$(called pip3)"
check "does not run curl"                no  "$(called curl)"

echo "2. idempotence: uvx alone counts too (uvx is what the MCP rows invoke)"
FX=have-uvx; mkfixture "$FX" >/dev/null
stub "$FX" uvx 'exit 0'
stub "$FX" pip3 "$lands_uv"
run_case "$FX"
check "returns 0"                        0   "$RC"
check "says 'already installed'"         yes "$(on_out 'uv already installed')"
check "does not run pip3"                no  "$(called pip3)"

echo "3. PEP 668 enforced, nothing else available: pip is NOT run, and it is loud"
FX=pep668; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" pip3 "$lands_uv"
run_case "$FX"
check "returns 1"                             1   "$RC"
check "names PEP 668 on stderr"               yes "$(on_err 'externally managed (PEP 668)')"
check "names the pip error string"            yes "$(on_err 'error: externally-managed-environment')"
check "does NOT run a pip install that cannot succeed" no "$(called pip3)"
check "reports total failure on stderr"       yes "$(on_err 'could not install uv by any available method')"
check "lists what it tried"                   yes "$(on_err 'Tried:')"
check "offers pipx as the manual fix"         yes "$(on_err 'pipx install uv')"
check "offers the astral.sh installer"        yes "$(on_err 'https://astral.sh/uv/install.sh')"
# The whole regression: a failure that only reaches stdout scrolls past and the
# run continues. Nothing from the failure path may land on stdout.
check "nothing on stdout at all"              0   "$(wc -c <"$TMP/out")"

echo "4. --break-system-packages is offered to the user and never executed"
check "named in the guidance"            yes "$(on_err '--break-system-packages')"
check "not passed to any command"        no  "$(grep -qF -e '--break-system-packages' "$TMP/$FX/calls" && echo yes || echo no)"

echo "5. pipx is preferred over pip when both are present"
FX=pipx-first; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" pipx "$lands_uv"
stub "$FX" pip3 "$lands_uv"
run_case "$FX"
check "returns 0"                        0   "$RC"
check "installed via pipx"               yes "$(on_out 'uv installed via pipx')"
check "pipx was run"                     yes "$(called pipx)"
check "pip3 was never reached"           no  "$(called pip3)"

echo "6. no pipx: it is installed from the package manager, PEP 668 or not"
FX=pipx-from-apt; mkfixture "$FX" >/dev/null
# The payload apt-get "installs". Written out here rather than heredoc'd inside
# the apt-get stub so the quoting stays readable.
{
  echo "#!$BASH_ABS"
  echo "printf '%s %s\\n' 'pipx' \"\$*\" >> '$TMP/pipx-from-apt/calls'"
  echo 'mkdir -p "$HOME/.local/bin"'
  echo 'printf "#!/bin/sh\nexit 0\n" > "$HOME/.local/bin/uv"'
  echo 'chmod +x "$HOME/.local/bin/uv"'
} > "$TMP/pipx-payload"
chmod +x "$TMP/pipx-payload"
stub "$FX" python3 'echo MANAGED'
stub "$FX" apt-get "case \"\$*\" in
  *install*pipx*) cp '$TMP/pipx-payload' '$TMP/pipx-from-apt/bin/pipx' ;;
esac
exit 0"
stub "$FX" pip3 "$lands_uv"
run_case "$FX"
check "returns 0"                        0   "$RC"
check "apt-get installed pipx"           yes "$(called apt-get)"
check "installed via pipx"               yes "$(on_out 'uv installed via pipx')"
check "pip3 was never reached"           no  "$(called pip3)"

echo "7. pipx fails: astral.sh's standalone installer is the next method"
# The pin is what the installer rung is gated on, so these cases set it. They set
# the harness's OWN copies of the two variables - the shipped values were snapshotted
# above and case 7d asserts them separately - and the payload's real sha256 is what
# gets pinned, so the verification below is exercised rather than stubbed out.
FX=installer; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" pipx 'exit 1'
# What astral.sh would serve. Prepared here, where quoting is plain, and copied
# into place by the curl stub.
{
  echo 'mkdir -p "$HOME/.local/bin"'
  echo 'printf "#!/bin/sh\nexit 0\n" > "$HOME/.local/bin/uv"'
  echo 'chmod +x "$HOME/.local/bin/uv"'
} > "$TMP/uv-installer-payload"
PAYLOAD_SHA="$(sha256sum "$TMP/uv-installer-payload" | cut -d' ' -f1)"
# A curl stub that honours -o and ignores everything else, so the flags under test
# reach the calls log without changing what it does.
curl_serves_payload="out=\"\"; prev=\"\"
for a in \"\$@\"; do [ \"\$prev\" = -o ] && out=\"\$a\"; prev=\"\$a\"; done
[ -n \"\$out\" ] || exit 1
cp '$TMP/uv-installer-payload' \"\$out\"
exit 0"
stub "$FX" curl "$curl_serves_payload"
stub "$FX" pip3 "$lands_uv"
UV_INSTALLER_VERSION="9.9.9-test"; UV_INSTALLER_SHA256="$PAYLOAD_SHA"
run_case "$FX"
check "returns 0"                             0   "$RC"
check "says the pipx attempt failed"          yes "$(on_err 'did not produce a usable uv')"
check "installed by the standalone installer" yes "$(on_out 'standalone installer from astral.sh')"
check "pip3 was never reached"                no  "$(called pip3)"

echo "7a. the fetch is pinned by version and forced onto https, both directions"
# -L follows redirects, so without --proto-redir one hop to http:// serves this file
# in the clear; and an unversioned URL is a 'latest' pointer, so the file that was
# reviewed and the file that runs need not be the same one.
check "curl was told https only"         yes "$(grep -qF -e "--proto =https" "$TMP/$FX/calls" && echo yes || echo no)"
check "and on redirects too"             yes "$(grep -qF -e "--proto-redir =https" "$TMP/$FX/calls" && echo yes || echo no)"
check "fetched the pinned version"       yes "$(grep -qF -e "https://astral.sh/uv/9.9.9-test/install.sh" "$TMP/$FX/calls" && echo yes || echo no)"
check "never the 'latest' pointer"       no  "$(grep -qF -e "https://astral.sh/uv/install.sh" "$TMP/$FX/calls" && echo yes || echo no)"

echo "7b. sha256 mismatch: downloaded, NOT executed, and said so"
FX=installer-tampered; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" curl "$curl_serves_payload"
UV_INSTALLER_VERSION="9.9.9-test"
UV_INSTALLER_SHA256="0000000000000000000000000000000000000000000000000000000000000000"
run_case "$FX"
check "returns 1"                        1   "$RC"
check "the file was fetched"             yes "$(called curl)"
check "the mismatch is named on stderr"  yes "$(on_err 'sha256 MISMATCH')"
check "both digests are shown"           yes "$(on_err "got $PAYLOAD_SHA")"
# The payload lands a uv in ~/.local/bin when it runs. It must not have run.
check "the installer was NOT executed"   no  "$([ -e "$TMP/$FX/home/.local/bin/uv" ] && echo yes || echo no)"
check "and the rejection is in Tried:"   yes "$(on_err 'sha256 did not match the pin')"

echo "7c. no digest tool on the box: refuse rather than run it unverified"
FX=installer-nodigest; mkfixture "$FX" >/dev/null
rm -f "$TMP/$FX/bin/sha256sum"
stub "$FX" python3 'echo MANAGED'
stub "$FX" curl "$curl_serves_payload"
UV_INSTALLER_VERSION="9.9.9-test"; UV_INSTALLER_SHA256="$PAYLOAD_SHA"
run_case "$FX"
check "returns 1"                        1   "$RC"
check "says the digest could not be computed" yes "$(on_err 'none of sha256sum, shasum or openssl')"
check "the installer was NOT executed"   no  "$([ -e "$TMP/$FX/home/.local/bin/uv" ] && echo yes || echo no)"

echo "7d. as SHIPPED the pin is empty, so the rung is skipped, not run unverified"
# Reads the two values out of the script itself, not the harness overrides above.
FX=installer-unpinned; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" curl "$curl_serves_payload"
UV_INSTALLER_VERSION="$SHIPPED_UV_VERSION"; UV_INSTALLER_SHA256="$SHIPPED_UV_SHA256"
run_case "$FX"
check "returns 1"                        1   "$RC"
check "nothing was downloaded"           no  "$(called curl)"
check "the skip is stated on stderr"     yes "$(on_err 'It will not run an unpinned, unverified installer')"
check "and labelled in Tried:"           yes "$(on_err 'no pinned version+sha256')"
BOTH_OR_NEITHER=no
if { [ -n "$SHIPPED_UV_VERSION" ] && [ -n "$SHIPPED_UV_SHA256" ]; } \
|| { [ -z "$SHIPPED_UV_VERSION" ] && [ -z "$SHIPPED_UV_SHA256" ]; }; then BOTH_OR_NEITHER=yes; fi
# Half a pin is the dangerous state: a version with no digest would fetch and run.
check "version and digest are pinned together, or not at all" yes "$BOTH_OR_NEITHER"

echo "7e. mktemp fails: its own label, and the installer is not reported as tried"
# The failure this catches: 'attempted' was appended BEFORE the download, so a run in
# which curl was never invoked still told the operator the installer had been tried.
FX=installer-notmp; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" mktemp 'exit 1'
stub "$FX" curl "$curl_serves_payload"
UV_INSTALLER_VERSION="9.9.9-test"; UV_INSTALLER_SHA256="$PAYLOAD_SHA"
run_case "$FX"
check "returns 1"                        1   "$RC"
check "curl was never invoked"           no  "$(called curl)"
check "the temp-file failure is stated"  yes "$(on_err 'could not create a temporary file')"
check "Tried: says WHICH way it skipped" yes "$(on_err 'astral.sh-installer(skipped: could not create a temporary file)')"
check "and does not claim it was tried"  no  "$(on_err 'Tried: pipx(no package manager, or the pipx package would not install) astral.sh-installer ')"

echo "7f. the wget-only branch: https forced, and wget still gets to say why it failed"
FX=installer-wget; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" wget "out=\"\"; prev=\"\"
for a in \"\$@\"; do [ \"\$prev\" = -O ] && out=\"\$a\"; prev=\"\$a\"; done
[ -n \"\$out\" ] || exit 1
cp '$TMP/uv-installer-payload' \"\$out\"
exit 0"
UV_INSTALLER_VERSION="9.9.9-test"; UV_INSTALLER_SHA256="$PAYLOAD_SHA"
run_case "$FX"
check "returns 0"                        0   "$RC"
check "wget was used"                    yes "$(called wget)"
check "https only, no http redirect"     yes "$(grep -qF -e "--https-only" "$TMP/$FX/calls" && echo yes || echo no)"
check "-nv, so wget's own error survives" yes "$(grep -qF -e "-nv" "$TMP/$FX/calls" && echo yes || echo no)"
check "-q is NOT used (it eats the reason)" no "$(grep -qE '^wget .*(^| )-q( |$)' "$TMP/$FX/calls" && echo yes || echo no)"
check "installed by the standalone installer" yes "$(on_out 'standalone installer from astral.sh')"

echo "8. a fetch that fails is not mistaken for an install (no curl | sh)"
FX=bad-fetch; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" curl 'exit 22'
UV_INSTALLER_VERSION="9.9.9-test"; UV_INSTALLER_SHA256="$PAYLOAD_SHA"
run_case "$FX"
check "returns 1"                        1   "$RC"
check "curl was tried"                   yes "$(called curl)"
check "the failed download has its own label" yes "$(on_err 'astral.sh-installer(download failed)')"
check "total failure is reported"        yes "$(on_err 'could not install uv by any available method')"

echo "9. PEP 668 NOT enforced: pip is the last resort and is allowed to run"
FX=pep668-free; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo FREE'
stub "$FX" pip3 "$lands_uv"
run_case "$FX"
check "returns 0"                        0   "$RC"
check "pip3 was run"                     yes "$(called pip3)"
check "installed via pip"                yes "$(on_out "uv installed via 'pip3 install --user uv'")"
check "no PEP 668 refusal was claimed"   no  "$(on_err 'externally managed (PEP 668)')"

echo "10. no interpreter to ask: 'could not tell' is stated, not assumed away"
FX=no-python; mkfixture "$FX" >/dev/null
stub "$FX" pip3 "$lands_uv"
run_case "$FX"
check "returns 0"                        0   "$RC"
check "says the check could not run"     yes "$(on_err 'could not determine whether this interpreter enforces PEP 668')"
check "attempts pip anyway and checks it" yes "$(called pip3)"
check "installed via pip"                yes "$(on_out "uv installed via 'pip3 install --user uv'")"

echo "11. pip present but failing: the failure is returned, not swallowed"
FX=pip-fails; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo FREE'
stub "$FX" pip3 'exit 1'
run_case "$FX"
check "returns 1"                        1   "$RC"
check "pip3 was run"                     yes "$(called pip3)"
check "the pip failure is on stderr"     yes "$(on_err "'pip3 install --user uv' did not produce a usable uv")"
check "nothing on stdout"                0   "$(wc -c <"$TMP/out")"

echo "12. pip 'succeeds' but uv is still not resolvable: still a failure"
FX=pip-lies; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo FREE'
stub "$FX" pip3 'exit 0'
run_case "$FX"
check "returns 1"                        1   "$RC"
check "the result was checked, not the exit code alone" yes "$(on_err "'pip3 install --user uv' did not produce a usable uv")"

echo "13. root with someone else's HOME: refused before anything is installed"
# Every rung installs into $HOME/.local/bin and then puts that on PATH. Run as root
# with HOME still pointing at an unprivileged account (sudo -E, an env_keep carrying
# HOME, su without -) that is root resolving binaries out of a user-writable dir,
# ahead of /usr/bin, for the rest of the script.
FX=root-foreign-home; mkfixture "$FX" >/dev/null
stub "$FX" id 'echo 0'
stub "$FX" stat 'echo 1000'
stub "$FX" pipx "$lands_uv"
stub "$FX" pip3 "$lands_uv"
stub "$FX" curl 'exit 0'
UV_INSTALLER_VERSION="9.9.9-test"; UV_INSTALLER_SHA256="$PAYLOAD_SHA"
run_case "$FX"
check "returns 1"                        1   "$RC"
check "says what it refused and why"     yes "$(on_err 'running as root with HOME=')"
check "names the consequence"            yes "$(on_err 'another user can write')"
check "tells the user what to do"        yes "$(on_err 'Run this script as your own user')"
check "pipx was never run"               no  "$(called pipx)"
check "pip3 was never run"               no  "$(called pip3)"
check "nothing was downloaded"           no  "$(called curl)"
check "nothing on stdout"                0   "$(wc -c <"$TMP/out")"

echo "14. root and the owner of HOME cannot be read: also refused"
# A check that could not run is not a check that passed - the same rule the PEP 668
# probe follows two rungs down.
FX=root-unknown-owner; mkfixture "$FX" >/dev/null
stub "$FX" id 'echo 0'
stub "$FX" stat 'exit 1'
stub "$FX" pipx "$lands_uv"
run_case "$FX"
check "returns 1"                        1   "$RC"
check "says the owner could not be read" yes "$(on_err 'whose owner could not be read')"
check "pipx was never run"               no  "$(called pipx)"

echo "15. root with root's OWN home is fine - this is not a blanket root refusal"
FX=root-own-home; mkfixture "$FX" >/dev/null
stub "$FX" id 'echo 0'
stub "$FX" stat 'echo 0'
stub "$FX" python3 'echo MANAGED'
stub "$FX" pipx "$lands_uv"
run_case "$FX"
check "returns 0"                        0   "$RC"
check "installed via pipx"               yes "$(on_out 'uv installed via pipx')"
check "no root refusal was printed"      no  "$(on_err 'running as root with HOME=')"

echo "16. PATH moves only when the probe succeeds, and never twice"
# uv_on_path used to prepend ~/.local/bin BEFORE probing and on every call, so three
# callers x up to three rungs left duplicates, and a run in which uv never installed
# still resolved claude/npm/node/python3 against a user-writable dir for the rest of
# the script.
FX=path-hygiene; mkfixture "$FX" >/dev/null
FXBIN="$TMP/$FX/bin"; FXHOME="$TMP/$FX/home"
PATH_AFTER_FAIL="$( export HOME="$FXHOME" PATH="$FXBIN"; uv_on_path >/dev/null 2>&1; printf '%s' "$PATH" )"
check "a failed probe leaves PATH exactly as it was" "$FXBIN" "$PATH_AFTER_FAIL"
printf '#!/bin/sh\nexit 0\n' > "$FXHOME/.local/bin/uv"; chmod +x "$FXHOME/.local/bin/uv"
PATH_AFTER_OK="$( export HOME="$FXHOME" PATH="$FXBIN"; uv_on_path >/dev/null 2>&1; uv_on_path >/dev/null 2>&1; uv_on_path >/dev/null 2>&1; printf '%s' "$PATH" )"
count_entry() { printf '%s' "$1" | tr ':' '\n' | grep -cFx "$2"; }
check "a successful probe puts ~/.local/bin on PATH" "$FXHOME/.local/bin:$FXBIN" "$PATH_AFTER_OK"
check "three calls add it exactly once"  1   "$(count_entry "$PATH_AFTER_OK" "$FXHOME/.local/bin")"

echo "17. memoised: the chain runs once per RUN, not once per selected row"
# ensure_uv is called by aws-mcp, aws-pricing-mcp and graphify. Without this, a host
# where uv will not install re-ran apt-get update as root, a pipx install, a download
# and a pip attempt three times, and printed the six-line failure block three times.
FX=memo-fail; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
stub "$FX" pipx 'exit 1'
run_case_twice "$FX"
check "first call returns 1"             1   "$(memo_field RC1)"
check "second call returns 1 too"        1   "$(memo_field RC2)"
check "pipx ran exactly once"            1   "$(grep -c '^pipx ' "$TMP/$FX/calls")"
check "the failure block is printed once" 1  "$(grep -c 'could not install uv by any available method' "$TMP/err")"
check "the second call says it is not repeating" yes "$(on_err 'is not being repeated')"

echo "18. memoised: an already-installed uv counts as one SKIP, not one per row"
FX=memo-skip; mkfixture "$FX" >/dev/null
stub "$FX" uv 'exit 0'
run_case_twice "$FX"
check "first call returns 0"             0   "$(memo_field RC1)"
check "second call returns 0"            0   "$(memo_field RC2)"
check "COUNT_SKIPPED moved by 1, not 2"  1   "$(memo_field SKIPPED)"
check "'already installed' printed once" 1   "$(grep -c 'uv already installed' "$TMP/out")"

echo "19. every package-manager arm of install_pipx_package, not just apt"
# QA exercised apt only. These drive dnf, yum, pacman, zypper and apk, which is also
# what makes 19a's pacman assertion a real check rather than a grep over source.
for MGR in dnf yum pacman zypper apk; do
  FX="mgr-$MGR"; mkfixture "$FX" >/dev/null
  {
    echo "#!$BASH_ABS"
    echo "printf '%s %s\\n' 'pipx' \"\$*\" >> '$TMP/$FX/calls'"
    echo 'mkdir -p "$HOME/.local/bin"'
    echo 'printf "#!/bin/sh\nexit 0\n" > "$HOME/.local/bin/uv"'
    echo 'chmod +x "$HOME/.local/bin/uv"'
  } > "$TMP/pipx-payload-$MGR"
  chmod +x "$TMP/pipx-payload-$MGR"
  stub "$FX" python3 'echo MANAGED'
  stub "$FX" "$MGR" "cp '$TMP/pipx-payload-$MGR' '$TMP/$FX/bin/pipx'
exit 0"
  run_case "$FX"
  check "$MGR: returns 0"                0   "$RC"
  check "$MGR: the manager was invoked"  yes "$(called "$MGR")"
  check "$MGR: uv came from pipx"        yes "$(on_out 'uv installed via pipx')"
done

echo "19a. pacman: -Sy without -u is a partial upgrade, and is not used"
# -Sy refreshes the package databases and then installs one package built against
# libraries the rest of the system has not been upgraded to. Reliability, on someone
# else's machine.
check "no bare -Sy refresh"              no  "$(grep -qE '^pacman .*-Sy' "$TMP/mgr-pacman/calls" && echo yes || echo no)"
check "installs with -S --needed"        yes "$(grep -qF -e 'pacman -S --needed --noconfirm python-pipx' "$TMP/mgr-pacman/calls" && echo yes || echo no)"

echo "20. no package manager at all: that is said, and is not a pipx failure"
FX=no-mgr; mkfixture "$FX" >/dev/null
stub "$FX" python3 'echo MANAGED'
run_case "$FX"
check "returns 1"                        1   "$RC"
check "names the missing package manager" yes "$(on_err 'pipx(no package manager')"

# --- the .ps1 half of the matched pair ----------------------------------------
# Until this section existed, NOTHING committed ran Install-Uv: ps-install-keys.sh is
# the only suite that drives install-prerequisites.ps1 and it SKIPs off Windows, so
# the .sh half had 49 cases and the .ps1 half had none - which is how the Windows side
# came to be missing the standalone-installer rung entirely while a comment explained
# only why the PEP 668 guard was absent.
#
# The whole .ps1 cannot be dot-sourced off Windows (it evaluates Test-Admin, i.e.
# [Security.Principal.WindowsIdentity], at top level), so the same idiom the .sh cases
# use applies: awk the shipped uv block and the shipped Write-* helpers out of the real
# file and run THOSE. The only thing shimmed is Sync-SessionEnvironment - see below.
#
# pwsh is named ABSOLUTELY (CLAUDE.md): a bare 'pwsh' that is not on PATH fails as
# "command not found", which reads as a failed check rather than a missing tool.
PS1SCRIPT="$REPO/scripts/install-prerequisites.ps1"
PWSH="${PWSH:-}"
if [ -z "$PWSH" ]; then
  for c in /snap/bin/pwsh /usr/bin/pwsh /usr/local/bin/pwsh /opt/microsoft/powershell/7/pwsh \
           "C:/Program Files/PowerShell/7/pwsh.exe"; do
    [ -x "$c" ] && { PWSH="$c"; break; }
  done
fi

ps_harness() {
  # $1 fixture name, $2 the case body. Builds a runnable script out of the SHIPPED
  # helper block and the SHIPPED uv block, plus one shim.
  local fx="$TMP/$1"
  {
    awk '/^\$script:FailedSteps = @\(\)/,/^function Write-Skip/' "$PS1SCRIPT"
    cat <<'SHIM'

# Sync-SessionEnvironment is deliberately NOT taken from the shipped script. It
# replays the Windows registry environment onto the process, and on Linux .NET
# returns nothing for the Machine and User scopes, so the real one sets $env:Path to
# the empty string mid-case and every later Get-Command then fails for a reason that
# has nothing to do with uv. The shim records that it was called, and that IS
# asserted - a rung that installs uv and forgets to refresh the environment is
# exactly the "installed but not on PATH" failure these cases exist for.
function Sync-SessionEnvironment {
    Add-Content -Path $env:UV_TEST_CALLS -Value 'Sync-SessionEnvironment called'
}
SHIM
    awk '/^# --- uv ---/,/^# --- Detection helpers ---/' "$PS1SCRIPT" | sed '$d'
    printf '%s\n' "$2"
  } > "$fx/harness.ps1"
}

PS_TAIL='
$err = ""
try { Install-Uv } catch { $err = $_.Exception.Message }
"ERR=$err"
"SKIPPED=$($script:Summary.Skipped)"
"INSTALLED=$($script:Summary.Installed)"
'

PS_TAIL_TWICE='
$err1 = ""; $err2 = ""
try { Install-Uv } catch { $err1 = $_.Exception.Message }
try { Install-Uv } catch { $err2 = $_.Exception.Message }
"ERR=$err1"
"ERR2=$err2"
"SKIPPED=$($script:Summary.Skipped)"
"INSTALLED=$($script:Summary.Installed)"
'

ps_run() {
  # $1 fixture name, $2 case body. PATH and HOME are the fixture's, so every external
  # command Install-Uv reaches for is a stub in $fx/bin or is genuinely absent.
  local fx="$TMP/$1"
  ps_harness "$1" "$2"
  ( env -u PSModulePath PATH="$fx/bin" HOME="$fx/home" UV_TEST_CALLS="$fx/calls" \
      "$PWSH" -NoProfile -NoLogo -File "$fx/harness.ps1" ) >"$TMP/out" 2>"$TMP/err"
  RC=$?
}
ps_field() { sed -n "s/^$1=//p" "$TMP/out"; }

if [ -z "$PWSH" ]; then
  printf '\033[90m%s\033[0m\n' "21-25. SKIPPED: no pwsh found at any of /snap/bin/pwsh, /usr/bin/pwsh,"
  printf '\033[90m%s\033[0m\n' "       /usr/local/bin/pwsh, /opt/microsoft/powershell/7/pwsh. That is a MISSING"
  printf '\033[90m%s\033[0m\n' "       TOOL, not a failed check - Install-Uv is BEHAVIOURALLY UNVERIFIED in"
  printf '\033[90m%s\033[0m\n' "       this run. Set PWSH=/absolute/path/to/pwsh to run these five cases."
  TOOL_SKIPPED=1
else
  # A uv that a Windows-side installer would drop somewhere already on PATH.
  printf '#!/bin/sh\nexit 0\n' > "$TMP/uv-payload-bin"; chmod +x "$TMP/uv-payload-bin"

  echo "21. .ps1 idempotence: uv already present is detected and nothing is run"
  FX=ps-have-uv; mkfixture "$FX" >/dev/null
  stub "$FX" uv 'exit 0'
  stub "$FX" pipx 'exit 0'
  stub "$FX" winget 'exit 0'
  stub "$FX" pip 'exit 0'
  ps_run "$FX" "$PS_TAIL"
  check "no error"                       ""  "$(ps_field ERR)"
  check "says 'already installed'"       yes "$(on_out 'uv already installed')"
  check "counted as one SKIP"            1   "$(ps_field SKIPPED)"
  check "pipx was not run"               no  "$(called pipx)"
  check "winget was not run"             no  "$(called winget)"
  check "pip was not run"                no  "$(called pip)"

  echo "22. .ps1 with no Python at all: winget is the rung that still works"
  # The defect: the standalone-installer rung was dropped from this side, so a Windows
  # box without Python got "pip not found; install Python first" for aws-api,
  # aws-pricing and graphify - three rows failing on a dependency uv does not have.
  FX=ps-winget; mkfixture "$FX" >/dev/null
  stub "$FX" winget "cp '$TMP/uv-payload-bin' '$TMP/$FX/bin/uv'
exit 0"
  ps_run "$FX" "$PS_TAIL"
  check "no error"                       ""  "$(ps_field ERR)"
  check "winget was run"                 yes "$(called winget)"
  check "installed via winget"           yes "$(on_out 'uv installed via winget')"
  check "counted as one install"         1   "$(ps_field INSTALLED)"
  check "the environment was refreshed"  yes "$(called Sync-SessionEnvironment)"
  check "the package id is astral's"     yes "$(grep -qF -e '--id astral-sh.uv' "$TMP/$FX/calls" && echo yes || echo no)"
  check "and it is not interactive"      yes "$(grep -qF -e '--silent' "$TMP/$FX/calls" && echo yes || echo no)"

  echo "23. .ps1 with nothing available: the failure names every rung it tried"
  FX=ps-nothing; mkfixture "$FX" >/dev/null
  ps_run "$FX" "$PS_TAIL"
  check "it throws"                      no  "$([ -z "$(ps_field ERR)" ] && echo yes || echo no)"
  check "names pipx as absent"           yes "$(on_out 'pipx (absent)')"
  check "names winget as absent"         yes "$(on_out 'winget (absent)')"
  check "names pip as absent"            yes "$(on_out 'pip (absent)')"
  check "points at the no-Python route"  yes "$(on_out 'winget install --id astral-sh.uv needs no Python')"
  check "nothing was counted as installed" 0 "$(ps_field INSTALLED)"

  echo "24. .ps1 memoised: three callers, one chain"
  FX=ps-memo; mkfixture "$FX" >/dev/null
  stub "$FX" pipx 'exit 1'
  ps_run "$FX" "$PS_TAIL_TWICE"
  check "the first call throws"          no  "$([ -z "$(ps_field ERR)" ] && echo yes || echo no)"
  check "the second throws the same thing" yes "$([ "$(ps_field ERR)" = "$(ps_field ERR2)" ] && echo yes || echo no)"
  check "pipx ran exactly once"          1   "$(grep -c '^pipx ' "$TMP/$FX/calls")"

  echo "25. .ps1 prefers pipx over winget, the same order the .sh uses"
  FX=ps-order; mkfixture "$FX" >/dev/null
  stub "$FX" pipx "cp '$TMP/uv-payload-bin' '$TMP/$FX/bin/uv'
exit 0"
  stub "$FX" winget 'exit 0'
  stub "$FX" pip 'exit 0'
  ps_run "$FX" "$PS_TAIL"
  check "no error"                       ""  "$(ps_field ERR)"
  check "installed via pipx"             yes "$(on_out 'uv installed via pipx')"
  check "winget was never reached"       no  "$(called winget)"
  check "pip was never reached"          no  "$(called pip)"
fi

echo "26. stub() writes a NEW file, never through a symlink"
# The defect this case exists for, and it is this harness's own, not the install
# script's: stub() used to redirect straight onto $fx/bin/<name>. mkfixture symlinks
# that directory's entries to the REALBIN copies (never to the host directly - see
# mkrealbin above), so stubbing one of those names sent the '>' THROUGH the link and
# truncated the copy it named. Before mkrealbin copied rather than linked, those
# links pointed at the host's own binaries directly: on this repo's reference host
# those names are hardlinks into one uutils multicall binary, so stubbing `mktemp`
# took out 114 coreutils in a single redirect on 2026-09-22. The fix was one line,
# `rm -f` before the write, and until now nothing would have gone red if it were
# removed again - which is the shape that lets a fix silently rot.
#
# This case CANNOT damage anything, and that is now true twice over rather than
# hoped for. Case 0 has already established that no fixture entry resolves outside
# $TMP, so even a whole-suite run with the rm removed can only reach copies. On top
# of that, the symlink this case stubs over points at a canary file INSIDE $TMP, and
# the containment is asserted immediately before the write, with the case refusing to
# run if it does not hold.
#
# The second layer exists because the first one was learned late: sabotage-testing
# this guard by removing the rm and running the suite is what destroyed the host
# coreutils the second time, on the same day, in the same repository. A guard whose
# regression test is itself destructive does not get re-tested, and then it rots.
echo
FX=stub-symlink; mkfixture "$FX" >/dev/null
CANARY="$TMP/$FX/canary"
printf 'ORIGINAL CONTENT - MUST SURVIVE\n' > "$CANARY"

# (a) The shape is real, not hypothetical: mkfixture genuinely leaves SYMLINKS in the
#     directory stub() writes into, which is what makes a write-through possible at
#     all. Read-only. This used to assert that the link pointed at a host binary -
#     which it did, and which was the design flaw; case 0 now forbids that, so what
#     is asserted here is the link-ness, and that its target is a copy inside $TMP.
check "mkfixture leaves a symlink in the stub directory" yes \
  "$([ -L "$TMP/$FX/bin/mktemp" ] && echo yes || echo no)"
prior_target="$(readlink -f "$TMP/$FX/bin/mktemp" 2>/dev/null || printf '')"
case "$prior_target" in
  "$TMP"/*) got=yes ;;
  *) got=no ;;
esac
check "and it points at a COPY inside \$TMP, not the host" yes "$got"

# (b) Now the containment: re-point one fixture bin entry at the canary. rm on a
#     symlink removes the link and never follows it, so this cannot touch the host
#     binary it currently names.
rm -f "$TMP/$FX/bin/mktemp"
ln -s "$CANARY" "$TMP/$FX/bin/mktemp"
canary_target="$(readlink -f "$TMP/$FX/bin/mktemp" 2>/dev/null || printf '')"
case "$canary_target" in
  "$TMP"/*) ;;
  *)
    red "  ABORT  case 26 would write outside \$TMP ($canary_target) - not running it"
    FAIL=$((FAIL+1))
    canary_target=""
    ;;
esac
if [ -n "$canary_target" ]; then
  check "the link under test resolves inside \$TMP" yes \
    "$([ "$canary_target" = "$CANARY" ] && echo yes || echo no)"
  stub "$FX" mktemp 'exit 0'
  check "the symlink target is byte-for-byte untouched" \
    "ORIGINAL CONTENT - MUST SURVIVE" "$(cat "$CANARY")"
  check "the stub replaced the link with a real file"   no \
    "$([ -L "$TMP/$FX/bin/mktemp" ] && echo yes || echo no)"
  check "and the stub is executable and runs"           0 \
    "$( "$TMP/$FX/bin/mktemp" >/dev/null 2>&1; echo $? )"
  # The copy the link USED to name is still there and still works - stated as a
  # result rather than assumed, because "nothing else was damaged" is the claim this
  # whole case exists to be able to make.
  check "the copy it formerly named still runs"         0 \
    "$( "$prior_target" --help >/dev/null 2>&1; echo $? )"
  # And every HOST tool $REALBIN_TOOLS names is untouched - not just mktemp, and
  # not just its content. host_tools_intact() compares content hash, mode, owner,
  # group and ctime against the baseline taken at suite start, and names the
  # tool and the specific field on a mismatch. Content hash ALONE would miss a
  # chmod (mode/ctime change, content unchanged) - which is exactly what the
  # incident this case exists for was: mkrealbin's own guard chmod followed a
  # sabotaged symlink and set +x on /usr/bin/find, leaving its content untouched
  # and its mode unchanged too (it was already 755), so only ctime moved. A bare
  # '--help' re-run (the previous form of this check) cannot see that at all - a
  # stub that replaced the host binary and exited 0 would satisfy it just as well
  # as the real thing.
  check "every HOST tool mkrealbin copies is untouched" yes "$(host_tools_intact)"
fi

echo
if [ "$FAIL" -ne 0 ]; then
  red "$PASS passed, $FAIL FAILED"
  exit 1
fi
if [ "$TOOL_SKIPPED" -ne 0 ]; then
  # A missing pwsh must not read as PASS: exit 77 (this repo's SKIP
  # convention) says "this run did not check everything it claims to",
  # which 0 does not. See mcp-preflight-catalog.sh's identical fix and
  # CLAUDE.md's note that render.sh does the same for a missing mmdc.
  green "$PASS passed, 0 failed (cases 21-25 SKIPPED - pwsh absent)"
  exit 77
fi
green "$PASS passed, 0 failed"
exit 0
