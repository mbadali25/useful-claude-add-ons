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
  # NOT byte-for-byte with verify-gate.ps1's/pm-pulse.ps1's copies any more
  # -- see tests/test_role_write_guard.py for why the parity discipline
  # changed shape rather than being dropped. Those two files' resolver only
  # needs to match `_common.sh`'s bare `crew_py()`; this one needs to match
  # role-write-guard.sh's OWN resolver, which does more than `crew_py()`
  # does, so this copy has to as well.
  #
  # Two bugs, reported together 2026-09-19 by a PowerShell-focused review of
  # THIS file specifically, on top of the WindowsApps/profile-shadow guards
  # this function already had:
  #
  #   1. Metadata alone (`.CommandType` / `.Source`) is exactly what a
  #      WindowsApps stub already passes -- `Get-Command` reports it as a
  #      real Application with a real Source. role-write-guard.sh's own
  #      resolver does not trust that either: it EXECUTES the candidate
  #      (`$cand -c "import sys;print(sys.executable)"`) and reads back
  #      what actually ran. This copy now does the same, rejecting a
  #      candidate that produces no output when actually launched.
  #   2. `Get-Command $name -All` walked every match for ONE name before
  #      moving to the next name -- so on `PATH=WindowsApps;RealDir` with
  #      only `python3` present anywhere (no `python`/`py` at all), the old
  #      code walked PAST the WindowsApps `python3` stub and found
  #      RealDir's `python3` further down PATH. Bash's `command -v
  #      python3` (role-write-guard.sh's resolver) takes only the FIRST
  #      match for a name; rejecting it moves to the NEXT NAME, never a
  #      second search of the same one -- so the .sh abandoned `python3`
  #      after the stub and never found a `python`/`py` that did not
  #      exist either. Same PATH, same machine: one shell flavour
  #      enforced `guards.roleWrites: block` and the other silently
  #      allowed the write unjudged. This copy now takes only the first
  #      match per name too, mirroring the .sh's name-order exactly.
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd -or $cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
    if ($cmd.Source -match 'WindowsApps') { continue }
    $real = $null
    $global:LASTEXITCODE = $null
    try {
      # Captured WHOLE, not piped through `Select-Object -First 1` --
      # that cmdlet can stop reading (and signal the pipeline to close)
      # as soon as it has one object, which races the native process's
      # own exit and can leave `$LASTEXITCODE` reflecting an early
      # termination rather than the candidate's real exit status. Letting
      # the candidate run to completion first is what makes the exit-code
      # check below trustworthy.
      $output = & $cmd.Source -c 'import sys; print(sys.executable)' 2>$null
      # NOT just "did it print something" -- a wrapper that prints a
      # plausible interpreter path and then exits nonzero must be
      # rejected too, matching role-write-guard.sh's own
      # `real=$(...) || continue`, which checks the candidate's exit
      # status. Reported 2026-09-19: this check was absent, so a
      # candidate bash correctly rejected (nonzero exit) was still
      # ACCEPTED here on output alone.
      if ($LASTEXITCODE -eq 0 -and $output) {
        $real = @($output)[0]
      }
    } catch {
      $real = $null
    }
    if ($real) { $real = $real.ToString().Trim() }
    if (-not $real -or $real -match 'WindowsApps') { continue }
    # Exit 0 and non-empty output is still not proof: a wrapper could print a
    # plausible-looking path to something that is not actually there. Confirm
    # the path EXISTS as a file before trusting it -- the bash-side parity
    # check is `[ -x "$real" ]`; Test-Path has no executable-bit concept on
    # Windows (an .exe's "executability" is its extension, not a mode bit),
    # so -PathType Leaf is the equivalent proof here.
    if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
    return $real
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
