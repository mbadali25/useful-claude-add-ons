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
if ($env:OS -ne 'Windows_NT') { exit 0 }

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-CrewPython {
  # role-write-guard.ps1's resolver, for role-write-guard.ps1's reasons: take
  # the FIRST match per name (as bash's `command -v` does), EXECUTE it and read
  # back `sys.executable`, reject a nonzero exit or a WindowsApps stub, and
  # require the printed path to exist.
  foreach ($name in @('python3', 'python', 'py')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd -or $cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
    if ($cmd.Source -match 'WindowsApps') { continue }
    $real = $null
    $global:LASTEXITCODE = $null
    try {
      $output = & $cmd.Source -c 'import sys; print(sys.executable)' 2>$null
      if ($LASTEXITCODE -eq 0 -and $output) { $real = @($output)[0] }
    } catch {
      $real = $null
    }
    if ($real) { $real = $real.ToString().Trim() }
    if (-not $real -or $real -match 'WindowsApps') { continue }
    if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
    return $real
  }
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
$exitCode = $null
try {
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
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
