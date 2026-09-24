# SessionEnd / PreCompact hook. PowerShell twin of vault-capture.sh -- both
# delegate to vault_capture.py so neither can drift from the other.
param([string]$Trigger = 'unknown')

# This hook cannot block: neither SessionEnd nor PreCompact has an exit code
# that stops anything the way PostToolUse's exit 2 does, so there is no
# fail-open/fail-closed choice to make here - only a loud/silent one. See
# vault-guard.ps1's header for the WindowsApps reproduction this
# PROVED-interpreter resolver defends against (the same defect, on the hook
# that CAN block).

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
# statement.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:VaultCaptureRejected = @()

function Resolve-VaultCapturePython {
  # The PowerShell twin of vault-capture.sh's resolver, and the same algorithm as
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
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    # hooks.json registers this hook with no -NoProfile, so a `function
    # python { ... }` in a user profile is loaded. It is reported, never run;
    # the executables behind it are still candidates.
    foreach ($shadow in @(Get-Command $name -All -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -ne 'Application' })) {
      $script:VaultCaptureRejected += "$name (resolved to a $($shadow.CommandType), not an executable - a profile function or alias is shadowing it)"
    }
    foreach ($cmd in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
      if (-not $cmd.Source) { continue }
      $probe = $null
      $reason = ''
      try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $cmd.Source
        $psi.Arguments = '-c "import sys; sys.stdout.write(''vault-capture-python:'' + sys.executable)"'
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $null = $proc.StandardError.ReadToEndAsync()
        if (-not $proc.WaitForExit(3000)) {
          try { $proc.Kill() } catch { }
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
        $script:VaultCaptureRejected += $reason
        continue
      }
      if ($probe) { $probe = $probe.ToString().Trim() }
      if (-not $probe -or -not $probe.StartsWith('vault-capture-python:')) {
        $script:VaultCaptureRejected += "$($cmd.Source) (ran, but did not answer the interpreter probe)"
        continue
      }
      $real = $probe.Substring('vault-capture-python:'.Length)
      if (-not $real) {
        # An embedded or frozen interpreter can report an empty sys.executable.
        # It answered honestly, and the answer is still unusable here.
        $script:VaultCaptureRejected += "$($cmd.Source) (answered the probe with an empty sys.executable)"
        continue
      }
      # sys.executable, not Source: the PATH-found name may be a shim that
      # re-execs elsewhere, and the probe already asked python where it lives.
      return $real
    }
  }
  return ''
}

$py = Resolve-VaultCapturePython

if (-not $py) {
    # Two answers, not one. "Found nothing named python" and "found something
    # named python that is not an interpreter" send the reader to different
    # places - the first to install python, the second to a shadowed PATH.
    if ($script:VaultCaptureRejected.Count -gt 0) {
        [Console]::Error.WriteLine("obsidian-vault vault-capture.ps1: python was found on PATH but no candidate is a usable interpreter [" + ($script:VaultCaptureRejected -join '; ') + "] - session capture skipped.")
    } else {
        [Console]::Error.WriteLine("obsidian-vault vault-capture.ps1: no python3/python/py interpreter found on PATH - session capture skipped.")
    }
    exit 0
}

try {
    & $py (Join-Path $dir 'vault_capture.py') $Trigger
} catch {
    [Console]::Error.WriteLine("obsidian-vault vault-capture.ps1: the interpreter ($py) could not be launched ($($_.Exception.Message)) - session capture skipped.")
}
exit 0
