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
  # Memoized within this process: a resolved (or exhausted) answer is not
  # re-derived by a second call in the same run, which would otherwise
  # re-walk and re-probe PATH from scratch. Cached only for the life of
  # THIS process -- a fresh hook invocation gets a fresh probe.
  if ($script:VaultGuardPyMemoDone) {
    $script:VaultGuardRejected = $script:VaultGuardPyMemoRejected
    return $script:VaultGuardPyMemoResult
  }
  # The PowerShell twin of vault-guard.sh's resolver, and the same algorithm as
  # crew's one shared Resolve-CrewPython: EVERY PATH match of every name is a
  # candidate, and each is EXECUTED (bounded, 3s) before it is believed.
  # Where it lives never decides. A WindowsApps App Execution Alias is tried
  # like anything else: it forwards to a working interpreter when Python is
  # installed and fails the probe when it is not. crew 1.0's Windows burn-in
  # found the old path rule plus first-match-per-name discarding three
  # WORKING aliases and never reaching the real python.exe behind them.
  #
  # Launched as a Process, not `& $cmd.Source -c ...`: the argument string
  # reaches the OS as written, so legacy native-argument passing (5.1, pwsh
  # <=7.2) has nothing to strip, and the probe can be timed out. The python
  # literal stays single-quoted all the same (_test/test_ps1_legacy_args.sh).
  # No `continue` inside try/catch: loop control across that boundary
  # differs between PowerShell versions, so the verdict leaves in variables.
  #
  # An OVERALL deadline on top of each candidate's own 3s probe bound: a
  # PATH with several hung candidates would otherwise cost 3s EACH, adding
  # up past this hook's own 10s timeout even though every individual probe
  # is bounded. Kept well inside that.
  $deadline = [System.Diagnostics.Stopwatch]::StartNew()
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    # hooks.json registers this hook with no -NoProfile, so a `function
    # python { ... }` in a user profile is loaded. It is reported, never run;
    # the executables behind it are still candidates.
    foreach ($shadow in @(Get-Command $name -All -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -ne 'Application' })) {
      $script:VaultGuardRejected += "$name (resolved to a $($shadow.CommandType), not an executable - a profile function or alias is shadowing it)"
    }
    foreach ($cmd in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
      if (-not $cmd.Source) { continue }
      # The remaining budget, not a flat 3000ms, bounds THIS candidate's
      # wait: checking the deadline only before launch and then waiting the
      # full 3s regardless can still overrun the deadline by up to 3s once
      # a candidate is entered, which on a run of several near-8s-but-under
      # candidates followed by one hung one can overrun both this deadline
      # and the 10s hook timeout it exists to stay inside.
      $vaultGuardRemainingMs = 8000 - [int]$deadline.Elapsed.TotalMilliseconds
      if ($vaultGuardRemainingMs -le 0) {
        $script:VaultGuardRejected += "PATH walk stopped: the overall resolver deadline was reached before every candidate could be probed"
        $script:VaultGuardPyMemoDone = $true
        $script:VaultGuardPyMemoResult = ''
        $script:VaultGuardPyMemoRejected = $script:VaultGuardRejected
        return ''
      }
      $vaultGuardWaitMs = [Math]::Min(3000, $vaultGuardRemainingMs)
      $probe = $null
      $reason = ''
      try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $probeArgs = '-c "import sys; v = sys.version_info; sys.stdout.write(''vault-guard-python:'' + ''%d:%d:%s:'' % (v[0], v[1], sys.implementation.name) + sys.executable)"'
        if ($cmd.Source -match '\.(cmd|bat)$') {
          # UseShellExecute=false hands FileName straight to CreateProcess,
          # which can only launch a real PE executable -- not a .cmd/.bat
          # shim (a pyenv-win install is exactly this shape). Route it
          # through cmd.exe /d /c instead of flipping UseShellExecute to
          # $true, which would resolve by shell file association rather
          # than run it as a command. Wrapping the whole command line in
          # one more pair of quotes defeats cmd's "exactly two quotes"
          # special case, so both the quoted shim path and the quoted -c
          # argument survive intact. Ported from crew's role-write-guard.ps1
          # (commit a39ac347), which fixed the same gap on the same
          # machines first.
          $psi.FileName = Join-Path $env:SystemRoot 'System32\cmd.exe'
          $psi.Arguments = '/d /c "' + '"' + $cmd.Source + '" ' + $probeArgs + '"'
        } else {
          $psi.FileName = $cmd.Source
          $psi.Arguments = $probeArgs
        }
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $null = $proc.StandardError.ReadToEndAsync()
        if (-not $proc.WaitForExit($vaultGuardWaitMs)) {
          # The whole tree, not the candidate: a py.exe-style launcher's child
          # inherits the redirected handles and outlives a plain Kill().
          # Kill($true) is PowerShell 7 (.NET Core 3+); 5.1 has no such
          # overload and falls back to taskkill /T /F.
          try {
            $proc.Kill($true)
          } catch {
            try { & taskkill.exe /T /F /PID $proc.Id 2>&1 | Out-Null } catch { }
            try { $proc.Kill() } catch { }
          }
          $reason = "$($cmd.Source) (did not answer the interpreter probe within 3s, and was killed)"
        } elseif ($proc.ExitCode -ne 0) {
          $reason = "$($cmd.Source) (ran, but exited $($proc.ExitCode) instead of answering the interpreter probe)"
        } elseif ($outTask.Wait(1000)) {
          $probe = $outTask.Result
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
      # `<major>:<minor>:<implementation>:<executable>` after the prefix, and
      # all four are checked: Python 3.8 or later, CPython or PyPy, and an
      # executable that exists -- the proof crew's Resolve-CrewPython
      # demands, and the one vault-guard.sh applies to the same answer.
      $answer = $probe.Substring('vault-guard-python:'.Length)
      if ($answer -notmatch '^(\d{1,4}):(\d{1,4}):([^:]*):(.*)$') {
        $script:VaultGuardRejected += "$($cmd.Source) (answered the probe without a version, implementation and executable)"
        continue
      }
      $major = [int]$Matches[1]
      $minor = [int]$Matches[2]
      $impl = $Matches[3]
      $real = $Matches[4]
      if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
        $script:VaultGuardRejected += "$($cmd.Source) (answered the probe as Python $major.$minor; 3.8 or later is required)"
        continue
      }
      if ($impl -notin @('cpython', 'pypy')) {
        $script:VaultGuardRejected += "$($cmd.Source) (answered the probe as implementation '$impl', not cpython or pypy)"
        continue
      }
      if (-not $real) {
        # An embedded or frozen interpreter can report an empty sys.executable.
        # It answered honestly, and the answer is still unusable here.
        $script:VaultGuardRejected += "$($cmd.Source) (answered the probe with an empty sys.executable)"
        continue
      }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) {
        $script:VaultGuardRejected += "$($cmd.Source) (answered the probe with a sys.executable that does not exist: $real)"
        continue
      }
      # sys.executable, not Source: the PATH-found name may be a shim that
      # re-execs elsewhere, and the probe already asked python where it lives.
      $script:VaultGuardPyMemoDone = $true
      $script:VaultGuardPyMemoResult = $real
      $script:VaultGuardPyMemoRejected = $script:VaultGuardRejected
      return $real
    }
  }
  $script:VaultGuardPyMemoDone = $true
  $script:VaultGuardPyMemoResult = ''
  $script:VaultGuardPyMemoRejected = $script:VaultGuardRejected
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
