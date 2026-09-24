# PreToolUse plan-approval + scope guard on Write|Edit|MultiEdit|NotebookEdit,
# and the approval-forgery check on Bash|PowerShell. PowerShell twin of
# scope-guard.sh -- both delegate to scope_guard.py, so neither can drift from
# the other. Exit 0 allows, exit 2 refuses. No python, or python not reaching
# a decision, fails CLOSED unless the config provably sets scope.mode off.
param(
  # Probe seam, the twin of role-write-guard.ps1's -PrintPython.
  [switch]$PrintPython
)

# Flavour guard, first executable statement: `$env:OS` is 'Windows_NT' on
# both Windows PowerShell 5.1 and PowerShell 7 and unset elsewhere. Not
# `$IsWindows`, which does not exist in 5.1.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# BYTE-FOR-BYTE the resolver in role-write-guard.ps1, asserted by the tests.
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

# Raw BYTES, not [Console]::In.ReadToEnd(), which decodes with the OEM
# codepage on 5.1 -- the reason role-write-guard.ps1 reads this way.
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$stdinBytes = $memStream.ToArray()
if ($stdinBytes.Length -ge 3 -and $stdinBytes[0] -eq 0xEF -and
    $stdinBytes[1] -eq 0xBB -and $stdinBytes[2] -eq 0xBF) {
  if ($stdinBytes.Length -gt 3) {
    $stdinBytes = $stdinBytes[3..($stdinBytes.Length - 1)]
  } else {
    $stdinBytes = [byte[]]@()
  }
}
$raw = [System.Text.Encoding]::UTF8.GetString($stdinBytes)

# BYTE-FOR-BYTE the copy in the other scope wrapper (asserted by the tests);
# the twin of the .sh `_scope_provably_off`. True only when
# `.crew/config.json` PROVABLY leaves the scope hooks off: the file is absent,
# or System.Text.Json (strict: no trailing commas, comments, single quotes or
# bare keys) parses it as one object with exactly one "scope" property, whose
# object has exactly one "mode" property, and that mode is the string "off".
# NOT ConvertFrom-Json: on PowerShell 7 it accepts `{"scope":{"mode":"off"},}`,
# which python reads as corrupt and therefore block. Where System.Text.Json is
# not loadable (Windows PowerShell 5.1) nothing is provable, so a present
# config fails closed until python is available. Every shape it cannot prove
# is NOT off: corrupt, an unknown mode, report, auto, block, or no scope key.
function Test-ScopeProvablyOff {
  $projectDir = $env:CLAUDE_PROJECT_DIR
  if (-not $projectDir) { $projectDir = (Get-Location).Path }
  $configPath = Join-Path (Join-Path $projectDir '.crew') 'config.json'
  $item = Get-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue
  if (-not $item -and -not (Test-Path -LiteralPath $configPath)) { return $true }
  if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { return $false }
  try {
    $text = [System.IO.File]::ReadAllText($configPath)
    if (([regex]::Matches($text, '"scope"')).Count -ne 1) { return $false }
    $doc = [System.Text.Json.JsonDocument]::Parse($text)
    try {
      $root = $doc.RootElement
      if ($root.ValueKind -ne [System.Text.Json.JsonValueKind]::Object) { return $false }
      $scopes = @($root.EnumerateObject() | Where-Object { $_.Name -ceq 'scope' })
      if ($scopes.Count -ne 1) { return $false }
      $scope = $scopes[0].Value
      if ($scope.ValueKind -ne [System.Text.Json.JsonValueKind]::Object) { return $false }
      $modes = @($scope.EnumerateObject() | Where-Object { $_.Name -ceq 'mode' })
      if ($modes.Count -ne 1) { return $false }
      $mode = $modes[0].Value
      if ($mode.ValueKind -ne [System.Text.Json.JsonValueKind]::String) { return $false }
      return ($mode.GetString() -ceq 'off')
    } finally {
      $doc.Dispose()
    }
  } catch {
    return $false
  }
}

$py = Resolve-CrewPython
if (-not $py) {
  if (Test-ScopeProvablyOff) {
    [Console]::Error.WriteLine("scope-guard: no usable python - not judged (scope.mode is off).")
    exit 0
  }
  [Console]::Error.WriteLine("SCOPE GUARD: no usable python - failing closed because .crew/config.json does not provably set scope.mode off.")
  exit 2
}

$prevConsoleEncoding = [Console]::OutputEncoding
$prevOutputEncodingVar = $OutputEncoding
$prevPythonUtf8 = $env:PYTHONUTF8
$prevPythonIoEncoding = $env:PYTHONIOENCODING
$exitCode = $null
try {
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  $global:LASTEXITCODE = $null
  $raw | & $py (Join-Path $dir 'scope_guard.py')
  $exitCode = $LASTEXITCODE
} catch {
  $exitCode = $null
} finally {
  [Console]::OutputEncoding = $prevConsoleEncoding
  $OutputEncoding = $prevOutputEncodingVar
  $env:PYTHONUTF8 = $prevPythonUtf8
  $env:PYTHONIOENCODING = $prevPythonIoEncoding
}

# scope_guard.py only ever exits 0 or 2. Anything else -- including no exit code
# at all, which `exit $LASTEXITCODE` would turn into a silent 0 -- means python
# never reached a decision.
if ($exitCode -ne 0 -and $exitCode -ne 2) {
  if (Test-ScopeProvablyOff) {
    [Console]::Error.WriteLine("scope-guard: scope_guard.py did not run to a decision (exit $exitCode); not judged (scope.mode is off).")
    exit 0
  }
  [Console]::Error.WriteLine("SCOPE GUARD: scope_guard.py did not run to a decision (exit $exitCode); failing closed because .crew/config.json does not provably set scope.mode off.")
  exit 2
}
exit $exitCode
