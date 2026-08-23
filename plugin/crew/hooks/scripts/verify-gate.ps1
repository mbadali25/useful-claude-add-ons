# PowerShell end-of-turn gate for native Windows. Mirrors verify-gate.sh.
# Runs the checks the CHANGED FILES require, from .crew/verify.json. Exit 2 = not done.
$raw = [Console]::In.ReadToEnd()

# Claude Code re-fires Stop after a blocking Stop hook. Without this check the
# gate blocks its own retry forever and a failing check becomes a stuck session.
try { if (($raw | ConvertFrom-Json).stop_hook_active) { exit 0 } } catch { }

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
  # _verify/ is the canonical home; scripts/smoke.sh is honoured as legacy.
  $smoke = @("_verify/smoke.sh", "scripts/smoke.sh") | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($smoke) {
    $out = & bash $smoke 2>&1
    if ($LASTEXITCODE -ne 0) {
      [Console]::Error.WriteLine("Smoke FAILED. Work is not complete.")
      $out | Select-String -Pattern '^(FAIL|SMOKE:)' | ForEach-Object { [Console]::Error.WriteLine($_) }
      exit 2
    }
  }
  exit 0
}

# -like's * spans '/', so '**/*.tf' demands a literal slash and silently skips
# every root-level file. Test the '**/'-stripped form as well.
function Test-CrewPath([string]$Path, [string]$Pattern) {
  $cands = New-Object System.Collections.Generic.HashSet[string]
  [void]$cands.Add($Pattern)
  if ($Pattern.StartsWith('**/')) { [void]$cands.Add($Pattern.Substring(3)) }
  [void]$cands.Add(($Pattern -replace '/\*\*/', '/'))
  [void]$cands.Add(($Pattern -replace '\*\*', '*'))
  foreach ($c in $cands) { if ($Path -like $c) { return $true } }
  return $false
}

$vm = Get-Content .crew/verify.json -Raw | ConvertFrom-Json
$cmds = [System.Collections.ArrayList]@()
$unmapped = [System.Collections.ArrayList]@()

foreach ($f in $changed) {
  $hit = $false
  foreach ($r in $vm.rules) {
    foreach ($p in $r.paths) {
      if (Test-CrewPath $f $p) {
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
  # A cmdlet leaves $LASTEXITCODE at its previous value, so a stale 0 reads as a
  # pass and a stale nonzero reads as a failure. Reset it, and check $? as well
  # - that is the only signal a failing cmdlet gives.
  $global:LASTEXITCODE = 0
  $out = Invoke-Expression $c 2>&1
  $ok = $?
  if (-not $ok -or $LASTEXITCODE -ne 0) {
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
