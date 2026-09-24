#!/usr/bin/env bash
# PostToolUse hook. Thin wrapper - the logic lives in vault_guard.py so the
# bash and PowerShell paths cannot drift.
#
# No usable interpreter: stand down with exit 0 rather than fail closed (exit
# 2). The two contract rules - frontmatter and ASCII - ship OFF until a
# vault's own CLAUDE.md turns one on, so losing those is no worse than the
# guard never being configured. The canvas shape check does NOT: checkCanvas
# defaults ON (vault_guard.py:243), so a missing interpreter does drop one
# check that would otherwise be running.
#
# Exit 0 is still right, and PostToolUse is why: the write has already landed
# by the time this runs, so exit 2 does not prevent a malformed canvas - it
# only reports one. Failing closed here would report a violation the guard
# never actually checked for, on every write, because python is missing. A
# false report is worse than a loud stand-down, so it must say so on stderr
# rather than exiting silently.
#
# That last sentence is the promise this script broke until 2026-09-22, and
# the failure was the one CLAUDE.md names as this repo's recurring bug - an
# unknown collapsing into the safe-looking value. The resolver was
# `command -v python3 || command -v python || command -v py`, which answers
# "is there a FILE named python on PATH", not "is there a working
# interpreter". On Windows a WindowsApps App Execution Alias is a real,
# executable file, so `command -v python3` resolved it, the stand-down branch
# below was skipped, and `exec`-ing the stub gave:
#
#     exit 49, ZERO bytes on stderr
#
# (the alias prints its Microsoft Store message to STDOUT and exits 9009;
# 9009 & 0xFF = 49). PostToolUse treats any status other than 2 as
# non-blocking and shows only stderr, so the guard checked nothing, said
# nothing, and looked exactly like a clean pass. Reproduced 2026-09-22 against
# a modelled stub, byte-for-byte, and pinned in
# _test/test_vault_guard_sh.sh. The stub is MODELLED, not observed: it was
# built on Linux from the alias's documented behaviour, so the shape of the
# failure is verified and the Windows fixture behind it is not.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The bash twin of vault-guard.ps1's `Resolve-VaultGuardPython`, and a
# deliberate near-copy of crew's `_resolve_role_write_python`
# (plugin/crew/hooks/scripts/role-write-guard.sh:32-57), which is the same
# resolver for the same defect on the same machines -- except that since the
# crew 1.0 Windows burn-in this one walks EVERY PATH match of a name (as
# crew's shared .ps1 probe does) and has no WindowsApps path rule at all.
#
# NOT imported from there. crew and obsidian-vault are separate marketplace
# entries, installed independently: `${CLAUDE_PLUGIN_ROOT}` points at this
# plugin only, and a host with obsidian-vault and no crew is the ordinary
# case, so there is no path this script could source. A shared copy INSIDE
# obsidian-vault was the other option and was declined for now: the two other
# bash wrappers here (bridge-status.sh, vault-capture.sh) carry the same naive
# one-liner, and moving all three onto one resolver widens the blast radius
# from the one hook that can report a violation to every hook this plugin
# registers - which is the trade crew's own comment records declining for the
# identical reason. The guard against drift is behavioural, not textual: the
# stub cases in _test/test_vault_guard_sh.sh fail if this resolver is
# weakened, whatever it is weakened back to.
#
# Two answers, not one, because "found nothing named python" and "found
# something named python that is not an interpreter" send the reader to
# different places - the first to install python, the second to a shadowed
# PATH. Collapsing the second into the first is the same class of bug as
# collapsing it into success.
VAULT_GUARD_PY=""
VAULT_GUARD_REJECTED=""

_vault_guard_reject() {
  VAULT_GUARD_REJECTED="${VAULT_GUARD_REJECTED}${VAULT_GUARD_REJECTED:+; }$1"
}

_vault_guard_resolve_python() {
  # NOT memoized. This hook has one call site (`if ! _vault_guard_resolve_python`
  # below), so a cache here would never see a second call to save -- an
  # earlier version carried one anyway, copied from crew's own (there,
  # actually dead: every crew call site invokes its resolver through a
  # `$(...)` subshell, which discards whatever the cache set). Removed here
  # too rather than kept as inert weight.
  VAULT_GUARD_PY=""
  VAULT_GUARD_REJECTED=""
  # An OVERALL deadline on top of each candidate's own 3s probe bound: a
  # PATH with several hung candidates would otherwise cost 3s EACH, adding
  # up past this hook's own timeout even though every individual probe is
  # bounded. Kept well inside the shortest hook timeout that resolves
  # python this way (bridge-status.ps1's twin, 10s).
  local _vault_guard_deadline=$((SECONDS + 8))
  local _vault_guard_remaining _vault_guard_probe_timeout
  for name in python3 python py; do
    # EVERY PATH match of the name, not only the first (`type -aP`, not
    # `command -v`), and each is executed before it is believed: where it
    # lives never decides. A WindowsApps alias is tried like anything else.
    # crew 1.0's Windows burn-in: a path rule plus first-match-per-name
    # discarded three WORKING aliases and never reached the real python.exe
    # behind them. vault-guard.ps1 walks the same order, so both flavours agree.
    while IFS= read -r candidate; do
      [ -n "$candidate" ] || continue
      # The remaining budget, not a flat 3s, bounds THIS candidate's probe: a
      # fixed 3s watchdog checked only before launch can still overrun the
      # deadline by up to 3s once entered, which on a run of several
      # near-8s-but-under candidates followed by one hung one can overrun
      # both this deadline and the 10s hook timeout it exists to stay inside.
      _vault_guard_remaining=$((_vault_guard_deadline - SECONDS))
      if [ "$_vault_guard_remaining" -le 0 ]; then
        _vault_guard_reject "PATH walk stopped: the overall resolver deadline was reached before every candidate could be probed"
        break 2
      fi
      _vault_guard_probe_timeout=$_vault_guard_remaining
      [ "$_vault_guard_probe_timeout" -le 3 ] || _vault_guard_probe_timeout=3
      # Running the candidate and reading back a token this script chose is
      # what tells a real interpreter from something wearing the name: only
      # a python that parsed and ran the -c program can emit the prefix. A
      # zero exit with other output (a wrapper that prints a line) fails it.
      # The answer is `<prefix><major>:<minor>:<implementation>:<executable>`
      # and all four are checked below: Python 3.8 or later, CPython or PyPy,
      # and an executable that exists -- the same proof crew's
      # Resolve-CrewPython demands. Python 2 has no sys.implementation, so it
      # exits nonzero here rather than answering.
      #
      # BOUNDED at 3s, process tree included, by the same watchdog crew's
      # `crew_py_strict` uses (`timeout` is absent on Git Bash): a candidate
      # that never exits would otherwise stall this hook forever, and a
      # launcher's child holding stdout would hang the `$()` after the
      # launcher itself died. `set -m` gives the candidate its own process
      # group for the kill; under MSYS `taskkill /T` takes the native tree
      # (MODELLED, not observed on Windows). No `sleep` means no watchdog.
      probe=$(
        set -m
        "$candidate" -c 'import sys; v = sys.version_info; sys.stdout.write("vault-guard-python:" + "%d:%d:%s:" % (v[0], v[1], sys.implementation.name) + sys.executable)' </dev/null 2>/dev/null &
        pid=$!
        (
          sleep "$_vault_guard_probe_timeout" 2>/dev/null || exit 0
          if [ -r "/proc/$pid/winpid" ] && read -r winpid < "/proc/$pid/winpid"; then
            MSYS2_ARG_CONV_EXCL='*' taskkill /F /T /PID "$winpid"
          fi
          kill -9 -- "-$pid" || kill -9 "$pid"
        ) </dev/null >/dev/null 2>&1 &
        watchdog=$!
        wait "$pid"
        status=$?
        kill -9 -- "-$watchdog" "-$pid" 2>/dev/null
        exit "$status"
      ) || {
        _vault_guard_reject "$candidate (ran, but exited nonzero or did not finish within 3s instead of answering the interpreter probe)"
        continue; }
      case "$probe" in
        vault-guard-python:*) answer="${probe#vault-guard-python:}" ;;
        *)
          _vault_guard_reject "$candidate (ran, but did not answer the interpreter probe)"
          continue ;;
      esac
      major="${answer%%:*}"; answer="${answer#*:}"
      minor="${answer%%:*}"; answer="${answer#*:}"
      impl="${answer%%:*}"; real="${answer#*:}"
      real=${real%$'\r'}
      case "$major:$minor" in
        *[!0-9:]*|:*|*:)
          _vault_guard_reject "$candidate (answered the probe without a version, implementation and executable)"
          continue ;;
      esac
      if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 8 ]; }; then
        _vault_guard_reject "$candidate (answered the probe as Python $major.$minor; 3.8 or later is required)"
        continue
      fi
      case "$impl" in
        cpython|pypy) ;;
        *)
          _vault_guard_reject "$candidate (answered the probe as implementation '$impl', not cpython or pypy)"
          continue ;;
      esac
      # An embedded or frozen interpreter can report an empty sys.executable.
      # It answered honestly, and the answer is still unusable here.
      [ -n "$real" ] || {
        _vault_guard_reject "$candidate (answered the probe with an empty sys.executable)"
        continue; }
      # A native Windows sys.executable (C:\...) is normalised to a path this
      # shell can stat -- `cygpath -u` when present, else the same /c/...
      # shape by hand -- exactly as crew's `crew_py_strict` does.
      case "$real" in
        [A-Za-z]:\\*|[A-Za-z]:/*)
          if command -v cygpath >/dev/null 2>&1; then
            real=$(cygpath -u "$real")
          else
            drive=$(printf '%s' "$real" | cut -c1 | tr '[:upper:]' '[:lower:]')
            rest=$(printf '%s' "$real" | cut -c3- | tr '\\\\' '/')
            real="/$drive$rest"
          fi
          ;;
      esac
      [ -x "$real" ] || {
        _vault_guard_reject "$candidate (answered the probe with a sys.executable that does not exist: $real)"
        continue; }
      # `sys.executable`, not `$candidate`: the PATH-found name may be a shim
      # that re-execs elsewhere, and the probe already paid the cost of asking
      # python where it actually lives.
      VAULT_GUARD_PY="$real"
      return 0
    done < <(type -aP "$name" 2>/dev/null)
  done
  return 1
}

if ! _vault_guard_resolve_python; then
  if [ -n "$VAULT_GUARD_REJECTED" ]; then
    echo "obsidian-vault vault-guard.sh: python was found on PATH but no candidate is a usable interpreter [$VAULT_GUARD_REJECTED] - guard is standing down for this write, which was NOT checked against the vault contract (exit 0, not fail-closed; see script comment)." >&2
  else
    echo "obsidian-vault vault-guard.sh: no python3/python/py interpreter found on PATH - guard is standing down for this write (exit 0, not fail-closed; see script comment)." >&2
  fi
  exit 0
fi

# Backstop, not the fix: vault_guard.py reads stdin as raw bytes and decodes
# them as UTF-8 explicitly, which never consults this variable at all - so it
# is correct with or without it. What this protects is everything else python
# does under the process's DEFAULT encoding when nothing more specific names
# one - stdout/stderr text writes included, e.g. a non-ASCII note title
# echoed back in a violation message. On Windows, absent this, that default
# is the console's ANSI code page, not UTF-8.
#
# Measured, and narrower than the first version of this comment claimed: an
# explicit `PYTHONIOENCODING` in the calling environment overrides
# PYTHONUTF8's encoding choice for every stream, stdin included, so this line
# is not a rescue for "some other override already picked the wrong
# encoding" - only for "nothing else picked one, so python fell back to the
# process's default locale". _test/test_vault_guard_sh.sh's non-ASCII
# round-trip section measured this directly (PYTHONUTF8=1 did NOT recover
# stdin decoded under a forced `PYTHONIOENCODING=cp1252`) before this comment
# was corrected to say so - a version of this comment that promised more was
# read here first and disproved by the sabotage test built to confirm it.
# Mirrored in vault-guard.ps1.
export PYTHONUTF8=1

# Not `exec`. vault_guard.py exits 0 or 2 and nothing else, so any other
# status means it never reached a verdict - resolved by the probe above and
# then deleted, made unexecutable, or killed part way - and PostToolUse treats
# every status but 2 as non-blocking. Under `exec` that landed as a bare
# numeric exit with whatever the interpreter happened to print, which is the
# silent shape this whole script exists to avoid. Same closure crew's twin
# made at plugin/crew/hooks/scripts/role-write-guard.sh:105-126, standing down
# rather than failing closed because this hook is PostToolUse and that one is
# PreToolUse.
"$VAULT_GUARD_PY" "$DIR/vault_guard.py"
status=$?
if [ "$status" -ne 0 ] && [ "$status" -ne 2 ]; then
  echo "obsidian-vault vault-guard.sh: the interpreter ($VAULT_GUARD_PY) did not complete the check (exit $status) - this write was NOT checked against the vault contract (standing down, exit 0; see script comment)." >&2
  exit 0
fi
exit "$status"
