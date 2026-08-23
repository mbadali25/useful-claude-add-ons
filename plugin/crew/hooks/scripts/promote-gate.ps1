# PreToolUse deploy gate for the PowerShell tool. Mirrors promote-gate.sh.
# Fires only on a command matching a `deploy` entry in .crew/verify.json
# -> environments. Exit 2 blocks.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cmd = $d.tool_input.command
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $root -ErrorAction SilentlyContinue
if (-not (Test-Path .crew/verify.json)) { exit 0 }

try { $vm = Get-Content .crew/verify.json -Raw | ConvertFrom-Json } catch { exit 0 }
if (-not $vm.environments) { exit 0 }

# Which environment does this command deploy to?
$envName = $null
foreach ($p in $vm.environments.PSObject.Properties) {
  foreach ($dep in $p.Value.deploy) {
    if ($dep -and ($cmd -like "*$dep*" -or $dep -like "*$cmd*")) { $envName = $p.Name; break }
  }
  if ($envName) { break }
}
if (-not $envName) { exit 0 }

$cfg = $vm.environments.$envName
$sha = (git rev-parse --short HEAD 2>$null)
$problems = New-Object System.Collections.Generic.List[string]

if (-not $sha) {
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName): not a git repository - cannot establish what is being deployed.")
  exit 2
}
if ((git status --porcelain 2>$null)) {
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName): the working tree is dirty. You would be deploying $sha plus changes that are in no commit and no review.")
  exit 2
}

# requires: an all-pass row for THIS sha
function Test-Promoted([string]$name, [string]$sha) {
  if (-not (Test-Path .work/PROMOTIONS.md)) { return $false }
  foreach ($line in Get-Content .work/PROMOTIONS.md) {
    if ($line -notmatch '\|') { continue }
    $cells = ($line.Trim().Trim('|') -split '\|') | ForEach-Object { $_.Trim() }
    if ($cells.Count -lt 6) { continue }
    if ($cells[1] -eq $name -and $cells[2].StartsWith($sha.Substring(0, [Math]::Min(7, $sha.Length)))) {
      return ($cells[3] -ieq 'pass' -and $cells[4] -ieq 'pass' -and $cells[5] -ieq 'pass')
    }
  }
  return $false
}
foreach ($up in $cfg.requires) {
  if (-not (Test-Promoted $up $sha)) {
    $problems.Add("'$up' has no all-pass row for sha $sha in .work/PROMOTIONS.md. Run /crew:promote $up first, and let it record the result.")
  }
}

# rollback runbook: exists and verified inside 90 days
if ($cfg.rollback) {
  if (-not (Test-Path $cfg.rollback)) {
    $problems.Add("the rollback runbook '$($cfg.rollback)' does not exist. No verified rollback, no deploy.")
  } else {
    $txt = Get-Content $cfg.rollback -Raw
    $m = [regex]::Match($txt, 'last[ _-]?verified\s*[:=]\s*(\d{4}-\d{2}-\d{2})', 'IgnoreCase')
    if (-not $m.Success) {
      $problems.Add("'$($cfg.rollback)' has no 'last verified: YYYY-MM-DD' line. An unverified rollback is not a rollback.")
    } else {
      $age = (Get-Date).Date - [datetime]::ParseExact($m.Groups[1].Value, 'yyyy-MM-dd', $null)
      if ($age.Days -gt 90) {
        $problems.Add("'$($cfg.rollback)' was last verified $($age.Days) days ago (ceiling is 90). Re-run it against a real environment first.")
      }
    }
  }
}

if ($cfg.requireHuman) {
  $marker = ".crew/.approved-$envName-$sha"
  if (-not (Test-Path $marker)) {
    $problems.Add("this environment requires explicit human approval. Show the sha, the diff summary and the last promotion, get a yes, then create the marker: New-Item -ItemType File $marker")
  }
}

if ($problems.Count -gt 0) {
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName, sha $sha):")
  $problems | ForEach-Object { [Console]::Error.WriteLine("  - $_") }
  [Console]::Error.WriteLine("")
  [Console]::Error.WriteLine("These are the pre-deploy gates from .crew/verify.json. Fix them, or set")
  [Console]::Error.WriteLine("verifyGate:false in .crew/config.json if this repo should not be gated.")
  exit 2
}

New-Item -ItemType Directory -Path .crew -Force -ErrorAction SilentlyContinue | Out-Null
Set-Content -Path .crew/.deploy-in-flight -Value "$envName $sha" -Encoding ASCII
exit 0
