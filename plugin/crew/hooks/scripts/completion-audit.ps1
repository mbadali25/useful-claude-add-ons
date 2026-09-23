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
# or it is one JSON object (crudely: starts `{`, ends `}`, braces balance)
# with exactly one "scope" key, whose object has exactly one "mode", and that
# mode is "off". Crude on purpose -- it runs only when python could not -- and
# every shape it cannot prove is NOT off: corrupt, an unknown mode, report,
# auto, block, or no scope key at all.
function Test-ScopeProvablyOff {
  $projectDir = $env:CLAUDE_PROJECT_DIR
  if (-not $projectDir) { $projectDir = (Get-Location).Path }
  $configPath = Join-Path (Join-Path $projectDir '.crew') 'config.json'
  $item = Get-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue
  if (-not $item -and -not (Test-Path -LiteralPath $configPath)) { return $true }
  if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { return $false }
  try {
    $text = ([System.IO.File]::ReadAllText($configPath) -replace '[\r\n]', '').Trim()
  } catch {
    return $false
  }
  if (-not ($text.StartsWith('{') -and $text.EndsWith('}'))) { return $false }
  if (([regex]::Matches($text, '\{')).Count -ne ([regex]::Matches($text, '\}')).Count) { return $false }
  if (([regex]::Matches($text, '"scope"')).Count -ne 1) { return $false }
  $m = [regex]::Match($text, '"scope"\s*:\s*(\{[^{}]*\})')
  if (-not $m.Success) { return $false }
  $obj = $m.Groups[1].Value
  if (([regex]::Matches($obj, '"mode"')).Count -ne 1) { return $false }
  return [bool]($obj -match '"mode"\s*:\s*"off"')
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
