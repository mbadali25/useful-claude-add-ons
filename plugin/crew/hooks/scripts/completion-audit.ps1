# Stop-time completion scope audit. PowerShell twin of completion-audit.sh --
# both delegate to completion_audit.py (0 lines on pass, <= 6 on fail, exit 2
# blocks the Stop).
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

# One marker per session and project, in the temp directory. Its presence
# means the previous Stop was blocked because nothing could be audited.
function Get-AuditMarker {
  $sid = 'nosession'
  $found = [regex]::Match($raw, '"session_id"\s*:\s*"([A-Za-z0-9._-]{1,128})"')
  if ($found.Success) { $sid = $found.Groups[1].Value }
  $projectDir = $env:CLAUDE_PROJECT_DIR
  if (-not $projectDir) { $projectDir = (Get-Location).Path }
  $sha = [System.Security.Cryptography.SHA256]::Create()
  $digest = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($projectDir))
  $proj = ($digest[0..5] | ForEach-Object { $_.ToString('x2') }) -join ''
  return (Join-Path ([System.IO.Path]::GetTempPath()) "crew-completion-audit.$sid-$proj")
}

# Block this Stop -- unless the previous one was already blocked for the same
# reason, or the marker cannot be written (then a block could repeat forever).
function Exit-BlockOnce([string]$message) {
  $marker = Get-AuditMarker
  if (Test-Path -LiteralPath $marker) {
    Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue
    [Console]::Error.WriteLine("completion audit: $message Not blocking again: the previous stop was already blocked for this.")
    exit 0
  }
  try {
    [System.IO.File]::WriteAllText($marker, '')
  } catch {
    [Console]::Error.WriteLine("completion audit: $message Not blocking: no marker could be written, so a block could loop.")
    exit 0
  }
  [Console]::Error.WriteLine("COMPLETION AUDIT: $message")
  exit 2
}

# `stop_hook_active` is honoured here as well as in python, so a continuation
# the audit caused is never blocked again even when python is broken. `\s`
# is any JSON whitespace, newlines included. A continuation also ends the
# "blocked once" count, so the next real turn is audited.
if ($raw -match '"stop_hook_active"\s*:\s*true') {
  Remove-Item -LiteralPath (Get-AuditMarker) -Force -ErrorAction SilentlyContinue
  exit 0
}

$py = Resolve-CrewPython
if (-not $py) {
  if (Test-ScopeProvablyOff) {
    [Console]::Error.WriteLine("completion audit: no usable python - not audited (scope.mode is off).")
    exit 0
  }
  Exit-BlockOnce "no usable python - the tree was not audited against the ticket's scope."
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
  $raw | & $py (Join-Path $dir 'completion_audit.py')
  $exitCode = $LASTEXITCODE
} catch {
  $exitCode = $null
} finally {
  [Console]::OutputEncoding = $prevConsoleEncoding
  $OutputEncoding = $prevOutputEncodingVar
  $env:PYTHONUTF8 = $prevPythonUtf8
  $env:PYTHONIOENCODING = $prevPythonIoEncoding
}

# completion_audit.py only ever exits 0 or 2. Anything else -- including no exit code
# at all, which `exit $LASTEXITCODE` would turn into a silent 0 -- means python
# never reached a decision.
if ($exitCode -ne 0 -and $exitCode -ne 2) {
  if (Test-ScopeProvablyOff) {
    [Console]::Error.WriteLine("completion audit: completion_audit.py did not run to a verdict (exit $exitCode); not audited (scope.mode is off).")
    exit 0
  }
  Exit-BlockOnce "completion_audit.py did not run to a verdict (exit $exitCode); nothing was audited."
}
# Python reached a verdict, so the next failure to run starts a fresh count.
Remove-Item -LiteralPath (Get-AuditMarker) -Force -ErrorAction SilentlyContinue
exit $exitCode
