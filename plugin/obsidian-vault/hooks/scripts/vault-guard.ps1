# PostToolUse hook. PowerShell twin of vault-guard.sh -- both delegate to
# vault_guard.py so neither can drift from the other. This hook can BLOCK
# (exit 2), so unlike bridge-status.ps1 the exit code is not silenced.
#
# No usable interpreter: stand down with exit 0 rather than fail closed (exit
# 2). The two contract rules - frontmatter and ASCII - ship OFF until a
# vault's own CLAUDE.md turns one on, so losing those is no worse than the
# guard never being configured. The canvas shape check does NOT: checkCanvas
# defaults ON (vault_guard.py:243), so a missing interpreter does drop one
# check that would otherwise be running.
#
# Exit 0 is still right, and PostToolUse is why: the write has already landed,
# so exit 2 would not prevent a malformed canvas - it would only report one
# the guard never checked for, on every write, because python is missing. A
# false report is worse than a loud stand-down, so it says so on stderr.
#
# This flavour is hardened with the .sh at the same time and for the same
# reason: the defect is Windows-only, and on Windows BOTH flavours of this
# hook are registered and run, so fixing one alone leaves the same hook on the
# same machine reaching different verdicts depending on which shell Claude
# Code happened to invoke. crew's `role-write-guard` records that exact
# divergence as a shipped bug. See vault-guard.sh's header for the
# reproduction (exit 49, zero bytes on stderr, from a MODELLED stub).
param(
  # Probe seam, the twin of crew's role-write-guard.ps1 -PrintPython: prints
  # the interpreter Resolve-VaultGuardPython would use and exits 0 without
  # touching stdin or running the guard. The hook's only real consumer pipes
  # JSON on stdin, so there is no interactive path to probe resolution.
  [switch]$PrintPython
)

# Flavour guard. Both flavours are registered for every event, so on a host
# that has BOTH interpreters both would otherwise run. Stand down only when
# we can positively prove this is not Windows.
#
# $env:OS is 'Windows_NT' on BOTH Windows PowerShell 5.1 and PowerShell 7,
# and unset on Linux/macOS. A bare `if (-not $IsWindows)` is WRONG: $IsWindows
# does not exist in 5.1, so it is $null there, `-not $null` is $true, and the
# hook stands down on the one platform it exists for. crew has already shipped
# that bug once - the guard stood down on Windows and blocked nothing there.
#
# It sits immediately after param() because param() must be the first
# statement, and before any side effect: this script resolves an interpreter
# and reads stdin, and neither may happen off Windows.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:VaultGuardRejected = @()

function Resolve-VaultGuardPython {
  # The PowerShell twin of vault-guard.sh's `_vault_guard_resolve_python`,
  # itself a near-copy of crew's `_resolve_role_write_python`
  # (plugin/crew/hooks/scripts/role-write-guard.sh:32-57). Why it is copied
  # rather than shared is argued in the .sh; the short form is that crew and
  # obsidian-vault install independently, so there is no file this one could
  # dot-source.
  #
  # `Get-Command $name | Select-Object -First 1`, never `-All`: bash's
  # `command -v` takes only the first match for a name and then moves to the
  # NEXT NAME. `-All` walks past a WindowsApps stub to a same-named real
  # python further down PATH, which bash never does - and the two flavours
  # then enforce different decisions on one machine. That is a reported crew
  # bug, not a hypothetical.
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { continue }
    if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) {
      # hooks.json registers this hook with no -NoProfile, so a
      # `function python { ... }` in a user profile is loaded and wins here.
      # Its Source is empty; saying so beats reporting "no python found" on a
      # machine that has python installed.
      $script:VaultGuardRejected += "$name (resolved to a $($cmd.CommandType), not an executable - a profile function or alias is shadowing it)"
      continue
    }
    # NOT a blanket "reject anything whose Source contains WindowsApps" - that
    # used to sit here (on both $cmd.Source above and $real below) and is a
    # location guess, not a stub detector. On a host where Python is installed
    # through the Microsoft Store, EVERY candidate's real interpreter genuinely
    # lives under
    # ...\WindowsApps\PythonSoftwareFoundation.Python.3.x_<hash>\python.exe -
    # so the blanket reject fired on a working Python 3.14 too, this resolver
    # returned '', and the caller's "no usable python" fallback stood the
    # guard down on a machine where python plainly works. Reported 2026-09-24
    # against a real PreToolUse-shaped Write payload; role-write-guard.ps1 hit
    # and fixed the identical bug the same day (see its Resolve-CrewPython
    # comment). Metadata alone is exactly what the Store alias ALSO passes:
    # Get-Command reports it as a real Application with a real Source. Launch
    # it and read back a token this script chose - only a python that parsed
    # and ran the -c program can emit the prefix; that proof does not need to
    # know WHERE the interpreter lives.
    #
    # No `continue` from inside the try/catch below: the loop-control
    # keywords behave inconsistently across PowerShell versions when they
    # cross a try/catch boundary, so the rejection reason is carried out in a
    # variable and acted on after it.
    $probe = $null
    $reason = ''
    $global:LASTEXITCODE = $null
    try {
      # Captured WHOLE, not piped through `Select-Object -First 1`: that
      # cmdlet can close the pipeline as soon as it has one object, racing
      # the native process's exit and leaving $LASTEXITCODE reflecting an
      # early termination rather than the candidate's real status.
      # Single-quoted python string literal, escaped for PowerShell's outer
      # single-quoted argument as `''...''` - NOT the double-quoted form this
      # line carried until this fix. Windows PowerShell 5.1 and pwsh <=7.2
      # (also pwsh 7.6 under `$PSNativeCommandArgumentPassing = 'Legacy'`,
      # which is how this was reproduced without a Windows machine) pass
      # native arguments the legacy way and STRIP embedded double quotes
      # before python ever sees them - `sys.stdout.write("vault-guard-python:"
      # + sys.executable)` arrived as `sys.stdout.write(vault-guard-python: +
      # sys.executable)`, a SyntaxError, exit 1, and every real interpreter
      # was rejected as "did not answer the interpreter probe". Single quotes
      # are not special to that legacy reconstruction, so this form has none
      # left to strip. See _test/test_ps1_legacy_args.sh.
      $output = & $cmd.Source -c 'import sys; sys.stdout.write(''vault-guard-python:'' + sys.executable)' 2>$null
      if ($LASTEXITCODE -ne 0) {
        $reason = "$($cmd.Source) (ran, but exited $LASTEXITCODE instead of answering the interpreter probe)"
      } elseif ($output) {
        $probe = @($output)[0]
      }
    } catch {
      $reason = "$($cmd.Source) (could not be launched: $($_.Exception.Message))"
    }
    if ($reason) {
      $script:VaultGuardRejected += $reason
      continue
    }
    if ($probe) { $probe = $probe.ToString().Trim() }
    if (-not $probe -or -not $probe.StartsWith('vault-guard-python:')) {
      $script:VaultGuardRejected += "$($cmd.Source) (ran, but did not answer the interpreter probe)"
      continue
    }
    $real = $probe.Substring('vault-guard-python:'.Length)
    if (-not $real) {
      # An embedded or frozen interpreter can report an empty sys.executable.
      # It answered honestly, and the answer is still unusable here.
      $script:VaultGuardRejected += "$($cmd.Source) (answered the probe with an empty sys.executable)"
      continue
    }
    # No post-execution WindowsApps check either, for the same reason: a real
    # Store-installed interpreter's OWN sys.executable lives under that path
    # too. The launch itself is already the proof that matters - a candidate
    # that could not be exec'd or did not answer the probe was already
    # rejected above; a printed, non-empty sys.executable came from an
    # interpreter that just ran successfully, which a path substring adds
    # nothing to.
    # sys.executable, not Source: the PATH-found name may be a shim that
    # re-execs elsewhere, and the probe already asked python where it lives.
    return $real
  }
  return ''
}

$py = Resolve-VaultGuardPython

if ($PrintPython) {
    Write-Output $py
    exit 0
}

if (-not $py) {
    # Two answers, not one. "Found nothing named python" and "found something
    # named python that is not an interpreter" send the reader to different
    # places - the first to install python, the second to a shadowed PATH.
    if ($script:VaultGuardRejected.Count -gt 0) {
        [Console]::Error.WriteLine("obsidian-vault vault-guard.ps1: python was found on PATH but no candidate is a usable interpreter [" + ($script:VaultGuardRejected -join '; ') + "] - guard is standing down for this write, which was NOT checked against the vault contract (exit 0, not fail-closed; see script comment).")
    } else {
        [Console]::Error.WriteLine("obsidian-vault vault-guard.ps1: no python3/python/py interpreter found on PATH - guard is standing down for this write (exit 0, not fail-closed; see script comment).")
    }
    exit 0
}

# Backstop, not the fix: vault_guard.py reads stdin as raw bytes and decodes
# them as UTF-8 explicitly, which never consults this variable - so it is
# correct with or without it. What this protects is everything else python
# does under the process's DEFAULT encoding when nothing more specific names
# one - stdout/stderr text writes included. On Windows, absent this, that
# default is the console's ANSI code page rather than UTF-8.
#
# Measured, and narrower than a first version of this comment claimed: an
# explicit PYTHONIOENCODING in the calling environment overrides PYTHONUTF8's
# encoding choice for every stream, stdin included - see vault-guard.sh's
# twin of this comment for how the .sh suite's sabotage test caught that
# overclaim directly. Mirrored in vault-guard.sh.
$env:PYTHONUTF8 = "1"

$global:LASTEXITCODE = $null
try {
    & $py (Join-Path $dir 'vault_guard.py')
} catch {
    [Console]::Error.WriteLine("obsidian-vault vault-guard.ps1: the interpreter ($py) could not be launched ($($_.Exception.Message)) - this write was NOT checked against the vault contract (standing down, exit 0; see script comment).")
    exit 0
}
$status = $LASTEXITCODE

# vault_guard.py exits 0 or 2 and nothing else, so any other status means it
# never reached a verdict. `$null` is its own case and the dangerous one: a
# launch failure leaves $LASTEXITCODE unset and a bare `exit $LASTEXITCODE`
# evaluates to 0 - a silent clean pass for a check that never ran. That is the
# round-4 finding against crew's twin, closed here before it could ship.
if ($null -eq $status) {
    [Console]::Error.WriteLine("obsidian-vault vault-guard.ps1: the interpreter ($py) reported no exit status, so the check never ran - this write was NOT checked against the vault contract (standing down, exit 0; see script comment).")
    exit 0
}
if ($status -ne 0 -and $status -ne 2) {
    [Console]::Error.WriteLine("obsidian-vault vault-guard.ps1: the interpreter ($py) did not complete the check (exit $status) - this write was NOT checked against the vault contract (standing down, exit 0; see script comment).")
    exit 0
}
exit $status
