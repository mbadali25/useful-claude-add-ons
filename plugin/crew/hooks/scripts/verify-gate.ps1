# PowerShell end-of-turn gate for native Windows. Mirrors verify-gate.sh.
# Runs the checks the CHANGED FILES require, from .crew/verify.json. Exit 2 = not done.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { $d = $null }

# Stop has no matcher, so this and verify-gate.sh both fire wherever both
# interpreters exist. Same hook name as verify-gate.sh so the two race for
# the same marker; only the winner runs the actual checks.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'hook_once.py') 'verify-gate' $d.session_id
if ($LASTEXITCODE -ne 0) { exit 0 }

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $root

if (Test-Path .crew/config.json) {
  $cfg = Get-Content .crew/config.json -Raw | ConvertFrom-Json
  if ($cfg.verifyGate -eq $false) { exit 0 }
}

$changed = @()
$changed += (git diff --name-only HEAD 2>$null)
$changed += (git ls-files --others --exclude-standard 2>$null)
$changed = $changed | Where-Object { $_ -and $_.Trim() }
if (-not $changed) { exit 0 }

if (-not (Test-Path .crew/verify.json)) {
  if (Test-Path scripts/smoke.sh) {
    $out = & bash ./scripts/smoke.sh 2>&1
    if ($LASTEXITCODE -ne 0) {
      [Console]::Error.WriteLine("Smoke FAILED. Work is not complete.")
      $out | Select-String -Pattern '^(FAIL|SMOKE:)' | ForEach-Object { [Console]::Error.WriteLine($_) }
      exit 2
    }
  }
  exit 0
}

$vm = Get-Content .crew/verify.json -Raw | ConvertFrom-Json
$cmds = [System.Collections.ArrayList]@()
$unmapped = [System.Collections.ArrayList]@()

foreach ($f in $changed) {
  $hit = $false
  foreach ($r in $vm.rules) {
    foreach ($p in $r.paths) {
      if ($f -like $p -or $f -like ($p -replace '\*\*','*')) {
        $hit = $true
        foreach ($c in $r.run) { if ($cmds -notcontains $c) { [void]$cmds.Add($c) } }
      }
    }
  }
  if (-not $hit) { [void]$unmapped.Add($f) }
}
foreach ($c in $vm.always) { if ($cmds -notcontains $c) { [void]$cmds.Add($c) } }
if ($cmds.Count -eq 0) { foreach ($c in $vm.default) { [void]$cmds.Add($c) } }

$failed = $false
foreach ($c in $cmds) {
  $out = Invoke-Expression $c 2>&1
  if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("VERIFY FAILED: $c")
    $out | Select-Object -Last 25 | ForEach-Object { [Console]::Error.WriteLine($_) }
    $failed = $true
  }
}

if ($unmapped.Count -gt 0 -and $vm.unmapped -eq "fail") {
  [Console]::Error.WriteLine("UNMAPPED CHANGES - .crew/verify.json has no rule for:")
  $unmapped | ForEach-Object { [Console]::Error.WriteLine($_) }
  [Console]::Error.WriteLine("Add a rule (or mark it deliberately unchecked) before reporting this complete.")
  $failed = $true
}

if ($failed) { exit 2 }
exit 0
