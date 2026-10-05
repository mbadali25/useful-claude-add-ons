#!/usr/bin/env bash
# Suite for scripts/pwsh-isolated.sh (T-0506): every pwsh the repo's own gate
# scripts start gets a private, throwaway XDG_CACHE_HOME.
#
# Builds everything under mktemp. A stub named pwsh records its arguments and
# environment to a file and exits with the status a case chooses; it is run
# through PWSH=..., so the real ~/.cache is never read or written. One case
# uses a real pwsh where one is installed and says SKIPPED otherwise.
#     bash scripts/_test/pwsh-isolated.sh
# Exit status is 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LAUNCHER="$REPO/scripts/pwsh-isolated.sh"
PASS=0
FAIL=0
SKIP=0
ok()   { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  FAIL  %s\n        %s\n' "$1" "$2"; FAIL=$((FAIL+1)); }
skip() { printf '  SKIPPED: %s\n' "$1"; SKIP=$((SKIP+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# L-0557's guard: anything this suite starts that is named pwsh runs on a
# cache under TMP, never the shared one, even before the launcher assigns its own.
export XDG_CACHE_HOME="$TMP/ambient-cache"
AMBIENT="$XDG_CACHE_HOME"

REC="$TMP/record"
STUB="$TMP/bin/pwsh"
mkdir -p "$TMP/bin"
cat >"$STUB" <<'STUBEOF'
#!/usr/bin/env bash
{
  printf 'cache=%s\n' "$XDG_CACHE_HOME"
  if [ -d "$(dirname "$XDG_CACHE_HOME")" ]; then echo "parent=exists"; else echo "parent=missing"; fi
  printf 'argc=%s\n' "$#"
  for a in "$@"; do printf 'arg=%s\n' "$a"; done
  printf 'pid=%s\n' "$$"
} >"$STUB_REC"
case "${STUB_MODE:-}" in
  sleep) sleep 30 ;;
  cat) cat >/dev/null ;;
esac
exit "${STUB_STATUS:-0}"
STUBEOF
chmod +x "$STUB"

launch() {  # runs the launcher on the stub; sets ERR and RC
  rm -f "$REC"
  STUB_REC="$REC" PWSH="$STUB" sh "$LAUNCHER" "$@" >"$TMP/out" 2>"$TMP/err"
  RC=$?
  ERR=$(cat "$TMP/err")
}
field() { sed -n "s/^$1=//p" "$REC" | head -1; }

echo "pwsh-isolated.sh"

# the_stub_sees_a_private_cache
launch -NoProfile
cache=$(field cache)
if [ -n "$cache" ] && [ "$cache" != "$AMBIENT" ] && [ "$cache" != "$HOME/.cache" ] \
   && [ "$(field parent)" = exists ]; then
  ok the_stub_sees_a_private_cache
else
  bad the_stub_sees_a_private_cache "cache='$cache' parent=$(field parent) ambient='$AMBIENT'"
fi

# two_runs_get_two_caches
launch -NoProfile; first=$(field cache)
launch -NoProfile; second=$(field cache)
if [ -n "$first" ] && [ "$first" != "$second" ]; then ok two_runs_get_two_caches
else bad two_runs_get_two_caches "first='$first' second='$second'"; fi

# the_cache_is_removed_afterwards
gone=1
for st in 0 1; do
  STUB_STATUS=$st launch -NoProfile
  d=$(dirname "$(field cache)")
  [ -e "$d" ] && gone=0
done
if [ $gone = 1 ]; then ok the_cache_is_removed_afterwards
else bad the_cache_is_removed_afterwards "a private cache directory outlived its run"; fi

# arguments_arrive_unchanged
launch -NoProfile -File "a b.ps1" -Path "c d"
args=$(sed -n 's/^arg=//p' "$REC" | paste -sd '|' -)
if [ "$(field argc)" = 5 ] && [ "$args" = "-NoProfile|-File|a b.ps1|-Path|c d" ]; then
  ok arguments_arrive_unchanged
else bad arguments_arrive_unchanged "argc=$(field argc) args=$args"; fi

# status_is_forwarded
fwd=""
for st in 0 1 3; do
  STUB_STATUS=$st launch -NoProfile
  case "$ERR" in *"TOOL BROKEN"*) fwd="$fwd broken@$st" ;; esac
  [ "$RC" = "$st" ] || fwd="$fwd $st->$RC"
done
if [ -z "$fwd" ]; then ok status_is_forwarded; else bad status_is_forwarded "$fwd"; fi

# a_signal_death_is_labelled_and_still_fails
sig=""
for st in 134 139; do
  STUB_STATUS=$st launch -NoProfile
  n=$(printf '%s\n' "$ERR" | grep -c '^TOOL BROKEN: pwsh.*'"$st")
  [ "$RC" = "$st" ] && [ "$n" = 1 ] || sig="$sig $st:rc=$RC,lines=$n"
done
if [ -z "$sig" ]; then ok a_signal_death_is_labelled_and_still_fails
else bad a_signal_death_is_labelled_and_still_fails "$sig"; fi

# missing_pwsh_is_77_and_starts_nothing
rm -f "$REC"
STUB_REC="$REC" PWSH="$TMP/no-such-pwsh" sh "$LAUNCHER" -NoProfile >/dev/null 2>"$TMP/err"; rc1=$?
err1=$(cat "$TMP/err")
STUB_REC="$REC" PWSH="" PATH="$TMP/empty" "$(command -v sh)" "$LAUNCHER" -NoProfile >/dev/null 2>"$TMP/err"; rc2=$?
err2=$(cat "$TMP/err")
if [ $rc1 = 77 ] && [ $rc2 = 77 ] && [[ "$err1" == *"TOOL MISSING: pwsh"* ]] \
   && [[ "$err2" == *"TOOL MISSING: pwsh"* ]] && [ ! -e "$REC" ]; then
  ok missing_pwsh_is_77_and_starts_nothing
else bad missing_pwsh_is_77_and_starts_nothing "rc=$rc1/$rc2 record=$( [ -e "$REC" ] && echo written)"; fi

# no_cache_dir_means_no_run
: >"$TMP/a-file"
rm -f "$REC"
STUB_REC="$REC" PWSH="$STUB" TMPDIR="$TMP/a-file/sub" sh "$LAUNCHER" -NoProfile >/dev/null 2>"$TMP/err"; rc=$?
if [ $rc = 1 ] && grep -q '^TOOL BROKEN:' "$TMP/err" && [ ! -e "$REC" ]; then
  ok no_cache_dir_means_no_run
else bad no_cache_dir_means_no_run "rc=$rc err=$(cat "$TMP/err")"; fi

# a_timeout_ends_the_child
if command -v timeout >/dev/null 2>&1; then
  rm -f "$REC"
  start=$(date +%s)
  STUB_MODE=sleep STUB_REC="$REC" PWSH="$STUB" timeout 2 sh "$LAUNCHER" -NoProfile >/dev/null 2>&1; rc=$?
  took=$(( $(date +%s) - start ))
  sleep 1
  pid=$(field pid); d=$(dirname "$(field cache)")
  alive=no; [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && alive=yes
  if [ $rc = 124 ] && [ $took -lt 10 ] && [ $alive = no ] && [ ! -e "$d" ]; then
    ok a_timeout_ends_the_child
  else
    bad a_timeout_ends_the_child "rc=$rc took=${took}s child_alive=$alive cache_left=$( [ -e "$d" ] && echo yes || echo no)"
    [ $alive = yes ] && kill "$pid" 2>/dev/null
  fi
else
  skip "a_timeout_ends_the_child - no timeout(1) here"
fi

# stdin_is_not_consumed
n=0
while read -r _line; do
  STUB_MODE="cat" launch -NoProfile
  n=$((n+1))
done <<'LINES'
one
two
three
LINES
if [ $n = 3 ]; then ok stdin_is_not_consumed; else bad stdin_is_not_consumed "iterated $n times"; fi

# no_gate_site_launches_pwsh_directly (static)
# shellcheck disable=SC2016  # a literal "$PWSH" is the pattern
direct=$(grep -nE '^[^#]*"\$PWSH"[[:space:]]+-' "$REPO/_verify/smoke.sh" "$REPO/_verify/run-all.sh" || true)
rules=$(python3 - "$REPO/.crew/verify.json" <<'PY'
import json, re, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
bad, ps1 = [], None
for rule in doc.get("rules", []):
    for cmd in rule.get("run", []):
        # A command that starts pwsh names it as a word (pwsh, pwsh.exe, .../7/pwsh);
        # pwsh-isolated.sh and test_pwsh_cache_isolation.py only contain the letters.
        if re.search(r"\bpwsh(\.exe)?\b(?![-_.])", cmd) and "scripts/pwsh-isolated.sh" not in cmd:
            bad.append(cmd[:80])
    if "**/*.ps1" in rule.get("paths", []):
        ps1 = rule.get("run")
want = ["sh scripts/pwsh-isolated.sh -NoProfile -File ./scripts/check-powershell.ps1"]
if ps1 != want:
    bad.append(f"ps1 rule run is {ps1!r}")
print("\n".join(bad))
PY
)
if [ -z "$direct" ] && [ -z "$rules" ]; then ok no_gate_site_launches_pwsh_directly
else bad no_gate_site_launches_pwsh_directly "direct: ${direct:-none}; rules: ${rules:-none}"; fi

# real_pwsh_sees_the_private_cache
real=$(command -v pwsh 2>/dev/null || true)
if [ -n "$real" ]; then
  out=$(PWSH="$real" sh "$LAUNCHER" -NoProfile -Command 'Write-Output $env:XDG_CACHE_HOME' 2>&1); rc=$?
  path=$(printf '%s\n' "$out" | tail -1)
  if [ $rc = 0 ] && [ -n "$path" ] && [ "$path" != "$AMBIENT" ] && [ ! -e "$(dirname "$path")" ]; then
    ok real_pwsh_sees_the_private_cache
  else bad real_pwsh_sees_the_private_cache "rc=$rc out=$out"; fi
else
  skip "real_pwsh_sees_the_private_cache - pwsh not found"
fi

echo
echo "pwsh-isolated: $PASS passed, $FAIL failed, $SKIP skipped"
[ $FAIL = 0 ]
