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
  # Memoized within this process: verify-gate.ps1 alone calls this up to
  # seven times in one run, and each call would otherwise re-walk and
  # re-probe PATH from scratch. Cached only for the life of THIS process --
  # a fresh hook invocation gets a fresh probe.
  if ($script:CrewPythonMemoDone) {
    return $script:CrewPythonMemoResult
  }
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
  # PROOF, not a printed line. The candidate must answer one JSON object
  # only a Python can build: {"v": [major, minor], "exe": sys.executable,
  # "impl": sys.implementation.name}. Accepted only when it exits 0, the
  # JSON parses, impl is cpython or pypy (the two implementations the hooks
  # are run under; anything else is rejected rather than guessed at), v is
  # at least [3, 8] (the floor crew's python targets), and exe exists as a
  # file. A program that ignores -c and prints some existing path -- which
  # the previous "print(sys.executable)" probe accepted -- fails the parse.
  #
  # The probe is bounded: it runs to completion or its WHOLE PROCESS TREE is
  # killed at 3s, with stdout and stderr read asynchronously so a chatty
  # candidate cannot fill a pipe and hang. The tree, not the candidate: a
  # py.exe-style launcher starts a child interpreter that inherits the
  # redirected handles, and killing only the launcher leaves that child
  # running. Kill($true) is the tree kill on PowerShell 7 (.NET Core 3+);
  # Windows PowerShell 5.1 has no such overload, so it falls back to
  # taskkill /T /F. No `continue` inside try/catch: loop control across that
  # boundary differs between PowerShell versions, so the verdict is carried
  # out in $real and acted on after it.
  # An OVERALL deadline on top of each candidate's own 3s probe bound: a
  # PATH with several hung candidates would otherwise cost 3s EACH, adding
  # up past the shortest hook timeout that calls this (bridge-status.ps1's
  # twin, 10s) even though every individual probe is bounded. Kept well
  # inside that.
  $crewPythonDeadline = [System.Diagnostics.Stopwatch]::StartNew()
  foreach ($name in @('python3', 'python', 'py')) {
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
      if ($crewPythonDeadline.Elapsed.TotalSeconds -ge 8) {
        $script:CrewPythonMemoDone = $true
        $script:CrewPythonMemoResult = ''
        return ''
      }
      $real = $null
      try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $probeArgs = '-c "import sys,json;print(json.dumps({''v'':list(sys.version_info[:2]),''exe'':sys.executable,''impl'':sys.implementation.name}))"'
        if ($cmd.Source -match '\.(cmd|bat)$') {
          # UseShellExecute=false hands FileName straight to CreateProcess,
          # which can only launch a real PE executable -- not a .cmd/.bat
          # shim (a pyenv-win install is exactly this shape). Route it
          # through cmd.exe /d /c instead of flipping UseShellExecute to
          # $true, which would resolve by shell file association rather
          # than run it as a command. Wrapping the whole command line in
          # one more pair of quotes defeats cmd's "exactly two quotes"
          # special case, so both the quoted shim path and the quoted -c
          # argument survive intact.
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
        if (-not $proc.WaitForExit(3000)) {
          try {
            $proc.Kill($true)
          } catch {
            try { & taskkill.exe /T /F /PID $proc.Id 2>&1 | Out-Null } catch { }
            try { $proc.Kill() } catch { }
          }
        } elseif ($proc.ExitCode -eq 0 -and $outTask.Wait(1000)) {
          $line = @(($outTask.Result -split "`r?`n") | Where-Object { $_.Trim() })[-1]
          $probe = $line | ConvertFrom-Json
          $v = @($probe.v)
          if ($probe.impl -in @('cpython', 'pypy') -and $v.Count -ge 2 -and
              ($v[0] -is [long] -or $v[0] -is [int]) -and ($v[1] -is [long] -or $v[1] -is [int]) -and
              ([int]$v[0] -gt 3 -or ([int]$v[0] -eq 3 -and [int]$v[1] -ge 8)) -and
              $probe.exe -is [string]) {
            $real = $probe.exe
          }
        }
      } catch {
        $real = $null
      }
      if ($real) { $real = $real.ToString().Trim() }
      if (-not $real) { continue }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
      $script:CrewPythonMemoDone = $true
      $script:CrewPythonMemoResult = $real
      return $real
    }
  }
  $script:CrewPythonMemoDone = $true
  $script:CrewPythonMemoResult = ''
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
