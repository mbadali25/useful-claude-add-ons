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
  VAULT_GUARD_PY=""
  VAULT_GUARD_REJECTED=""
  for name in python3 python py; do
    # EVERY PATH match of the name, not only the first (`type -aP`, not
    # `command -v`), and each is executed before it is believed: where it
    # lives never decides. A WindowsApps alias is tried like anything else.
    # crew 1.0's Windows burn-in: a path rule plus first-match-per-name
    # discarded three WORKING aliases and never reached the real python.exe
    # behind them. vault-guard.ps1 walks the same order, so both flavours agree.
    while IFS= read -r candidate; do
      [ -n "$candidate" ] || continue
      # Running the candidate and reading back a token this script chose is
      # what tells a real interpreter from something wearing the name: only
      # a python that parsed and ran the -c program can emit the prefix. A
      # zero exit with other output (a wrapper that prints a line) fails it.
      probe=$("$candidate" -c 'import sys; sys.stdout.write("vault-guard-python:" + sys.executable)' 2>/dev/null) || {
        _vault_guard_reject "$candidate (ran, but exited nonzero instead of answering the interpreter probe)"
        continue; }
      case "$probe" in
        vault-guard-python:*) real="${probe#vault-guard-python:}" ;;
        *)
          _vault_guard_reject "$candidate (ran, but did not answer the interpreter probe)"
          continue ;;
      esac
      # An embedded or frozen interpreter can report an empty sys.executable.
      # It answered honestly, and the answer is still unusable here.
      [ -n "$real" ] || {
        _vault_guard_reject "$candidate (answered the probe with an empty sys.executable)"
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
