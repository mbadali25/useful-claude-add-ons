# PreToolUse cloud/destructive guard on the Bash AND PowerShell tools.
# PowerShell twin of cloud-guard.sh -- both hand the payload to cloud_guard.py,
# which reads `tool_name` and parses the command as bash or PowerShell by the
# TOOL that ran it, so neither flavour can judge a command differently from
# the other. Off unless `guards.cloudGuard` is `report` or `block`.

# Flavour guard. Both flavours are registered for the event, so on a host that
# has BOTH interpreters both would otherwise run. Stand down only when we can
# positively prove this is not Windows. `$env:OS` is 'Windows_NT' on BOTH
# Windows PowerShell 5.1 and PowerShell 7 and unset elsewhere; a bare
# `-not $IsWindows` stands down on 5.1, where `$IsWindows` does not exist.
# This line is the plugin-wide convention test_flavour_guard.py enforces; it
# is safe HERE because cloud-guard.sh judges every call off Windows. On
# Windows the split is by TOOL, not OS: this flavour judges PowerShell calls
# and stands down for Bash ones, which cloud-guard.sh always judges -- decided
# in cloud_guard.py `stands_down`, told the flavour by
# CREW_CLOUD_GUARD_FLAVOUR below.
if ($env:OS -ne 'Windows_NT') { exit 0 }

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

function Test-CloudGuardArmed {
  # Only consulted when python could not judge. Any `cloudGuard` value other
  # than "off", in the repo config or the machine-global one, counts as armed,
  # so a value this cannot parse fails closed. The twin of cloud-guard.sh's
  # `_cloud_guard_armed`.
  $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { '.' }
  $userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
  foreach ($cfg in @((Join-Path $root '.crew/config.json'),
                     (Join-Path $userHome '.claude/crew/config.json'))) {
    if (-not (Test-Path -LiteralPath $cfg -PathType Leaf)) { continue }
    $text = Get-Content -LiteralPath $cfg -Raw -ErrorAction SilentlyContinue
    if (-not $text) { continue }
    $m = [regex]::Match($text, '"cloudGuard"\s*:\s*([^,}]*)')
    if (-not $m.Success) { continue }
    $value = $m.Groups[1].Value -replace '["\s]', ''
    if ($value -and $value -ne 'off') { return $true }
  }
  return $false
}

# Raw BYTES, not `[Console]::In.ReadToEnd()`: that decodes with the OEM
# codepage on 5.1 and mangles anything outside ASCII (role-write-guard.ps1
# records the measurement). cloud_guard.py strips a BOM itself.
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$raw = [System.Text.Encoding]::UTF8.GetString($memStream.ToArray())

$py = Resolve-CrewPython
$scriptPath = Join-Path $dir 'cloud_guard.py'
if (-not $py -or -not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
  if (Test-CloudGuardArmed) {
    [Console]::Error.WriteLine("cloud-guard: cannot run cloud_guard.py, and guards.cloudGuard is armed - refusing rather than letting this command through unjudged.")
    exit 2
  }
  exit 0
}

$prevConsoleEncoding = [Console]::OutputEncoding
$prevOutputEncodingVar = $OutputEncoding
$prevPythonUtf8 = $env:PYTHONUTF8
$prevPythonIoEncoding = $env:PYTHONIOENCODING
$prevFlavour = $env:CREW_CLOUD_GUARD_FLAVOUR
$exitCode = $null
try {
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  $env:CREW_CLOUD_GUARD_FLAVOUR = 'powershell'
  $global:LASTEXITCODE = $null
  $raw | & $py $scriptPath
  $exitCode = $LASTEXITCODE
} catch {
  $exitCode = $null
} finally {
  [Console]::OutputEncoding = $prevConsoleEncoding
  $OutputEncoding = $prevOutputEncodingVar
  $env:PYTHONUTF8 = $prevPythonUtf8
  $env:PYTHONIOENCODING = $prevPythonIoEncoding
  $env:CREW_CLOUD_GUARD_FLAVOUR = $prevFlavour
}

# cloud_guard.py only ever exits 0 -- its decisions are JSON on stdout -- so a
# null or nonzero status means it never finished judging. `exit $null` would be
# exit 0, an allow nobody decided.
if ($exitCode -ne 0) {
  if (Test-CloudGuardArmed) {
    [Console]::Error.WriteLine("cloud-guard: cloud_guard.py did not finish (exit $exitCode) and guards.cloudGuard is armed - refusing.")
    exit 2
  }
  [Console]::Error.WriteLine("cloud-guard: cloud_guard.py did not finish (exit $exitCode); the guard is not armed, so the command is not judged.")
}
exit 0
