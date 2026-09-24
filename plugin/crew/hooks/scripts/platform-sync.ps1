# SessionStart hook. PowerShell twin of platform-sync.sh -- both delegate to
# crew_platform.py so neither can drift from the other. A hook that WRITES
# config is the last place two implementations should be allowed to disagree.
param(
  # Probe seam, the twin of role-write-guard.ps1's -PrintPython: prints the
  # interpreter Resolve-CrewPython would use and exits 0 without touching
  # config.
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
if ($env:OS -ne 'Windows_NT') { exit 0 }

$ErrorActionPreference = 'SilentlyContinue'

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-CrewPython {
  # ONE probe, byte for byte in every crew .ps1 that runs python, asserted by
  # tests/test_ps1_python_probe.py. Inline rather than dot-sourced for the
  # reason verify-gate.ps1's emergency-lane note gives: a dot-sourced
  # function is invisible to scripts/check-powershell.ps1's static check.
  #
  # EVERY PATH match of every name is a candidate, and each is EXECUTED
  # before it is believed; where it lives never decides. A WindowsApps App
  # Execution Alias is tried like anything else: it forwards to a working
  # interpreter when Python is installed and fails the probe when it is not.
  # Windows burn-in 2026-09-23 (docs/review/06-windows-burn-in.md, 2c): the
  # previous copy skipped WindowsApps by path and took only the first match
  # per name, so on a host whose python, python3 and py were all working
  # WindowsApps aliases it discarded all three untested, never reached the
  # real python.exe further down PATH, and completion-audit.ps1 blocked
  # every Stop while its bash twin proceeded.
  #
  # The probe is bounded: it runs to completion or is killed at 3s, with
  # stdout and stderr read asynchronously so a chatty candidate cannot fill a
  # pipe and hang. A candidate is accepted only when it exits 0, reports
  # Python 3 or later, and prints a sys.executable that exists as a file.
  # No `continue` inside try/catch: loop control across that boundary
  # differs between PowerShell versions, so the verdict is carried out in
  # $real and acted on after it.
  foreach ($name in @('python3', 'python', 'py')) {
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
      $real = $null
      try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $cmd.Source
        $psi.Arguments = '-c "import sys; sys.version_info[0] >= 3 or sys.exit(1); print(sys.executable)"'
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $null = $proc.StandardError.ReadToEndAsync()
        if (-not $proc.WaitForExit(3000)) {
          try { $proc.Kill() } catch { }
        } elseif ($proc.ExitCode -eq 0 -and $outTask.Wait(1000)) {
          $real = @(($outTask.Result -split "`r?`n") | Where-Object { $_.Trim() })[0]
        }
      } catch {
        $real = $null
      }
      if ($real) { $real = $real.ToString().Trim() }
      if (-not $real) { continue }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
      return $real
    }
  }
  return ''
}

if ($PrintPython) {
  Write-Output (Resolve-CrewPython)
  exit 0
}

# crew_platform.py's own session claim STAYS, and is not made redundant by the
# flavour guard above. The guard decides which FLAVOUR runs; the claim decides
# which SessionStart FIRING does the work, and SessionStart fires once per
# source event (startup, clear, compact, resume, fork), not once per session.
#
# Note what the guard does NOT do: decide by interpreter. That would be unsound
# (on Windows, `bash` on PATH is normally the WSL launcher, which would detect
# Linux for a native-Windows session), which is why it tests the OS instead --
# and why crew_platform detects from python's own view of the machine, not from
# which shell reached it.
$py = Resolve-CrewPython
if (-not $py) {
  # Non-blocking hook -- still exit 0, but LOUD: a silent exit 0 here reads
  # as "nothing to repair", not as "the interpreter is broken".
  [Console]::Error.WriteLine("crew platform-sync: no usable python (stub or unusable interpreter) - the platform config will not be repaired")
  exit 0
}
& $py (Join-Path $dir 'crew_platform.py')
exit 0
