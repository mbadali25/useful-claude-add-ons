# PreToolUse deploy gate for the PowerShell tool. Mirrors promote-gate.sh.
# Fires only on a command matching a `deploy` entry in .crew/verify.json
# -> environments. Exit 2 blocks.

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

$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cmd = $d.tool_input.command
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $root -ErrorAction SilentlyContinue
if (-not (Test-Path .crew/verify.json)) { exit 0 }

# Every way the map can be unreadable ends here, in one message, because the
# reader's next action is the same for all of them: look at the file.
function Deny-UnreadableMap([string]$Why) {
  [Console]::Error.WriteLine("PROMOTION BLOCKED: $Why")
  [Console]::Error.WriteLine("  This is NOT a pass. Crew cannot tell whether this command deploys, so it")
  [Console]::Error.WriteLine("  cannot tell whether a pre-deploy gate applies to it. Fix .crew/verify.json,")
  [Console]::Error.WriteLine("  or delete it if this repo should not be gated.")
  exit 2
}

# Fail CLOSED on a map that will not parse. An ABSENT verify.json (line 11) is
# a repo that opted out of gating; an UNPARSEABLE one is corruption, and the
# two are not the same fact. `catch { exit 0 }` treated them identically, so a
# single stray comma in verify.json silently removed every pre-deploy check
# while the deploy went ahead looking gated.
#
# `-ErrorAction Stop` is what makes the catch cover UNREADABLE as well as
# unparseable, and it is not decoration: Get-Content's failure is a
# NON-TERMINATING error, so without it a directory named .crew/verify.json left
# $vm null, the catch never fired, and `-not $vm.environments` two lines down
# read the corruption as "nothing declared" and exited 0. Measured, on Windows:
# exit 0 with a red Get-Content error on stderr and the deploy allowed.
#
# What this flavour CANNOT match is bash's strictness, and the difference is
# worth knowing rather than assuming away: PowerShell 7's ConvertFrom-Json
# ACCEPTS a trailing comma, which python's json rejects. So the stray comma
# that motivated this block is caught by promote-gate.sh and parses cleanly
# here. That asymmetry is safe in the direction that matters - this flavour
# still runs every check below on a map it could read - and closing it would
# mean shipping a second JSON parser.
try {
  $vm = Get-Content .crew/verify.json -Raw -ErrorAction Stop | ConvertFrom-Json
} catch {
  Deny-UnreadableMap ".crew/verify.json could not be read or parsed, so no pre-deploy check ran. $($_.Exception.Message)"
}
# The same absent/malformed split, one level in. `environments` ABSENT gates
# nothing, exactly like the bash flavour's `.get("environments", {})`.
# `environments` PRESENT and not an object is corruption: the property
# enumeration below finds no environment in it, so every deploy sailed through
# on "this command deploys nothing".
if ($vm -isnot [System.Management.Automation.PSCustomObject]) {
  Deny-UnreadableMap ".crew/verify.json does not hold a JSON object."
}
$envProperty = $vm.PSObject.Properties['environments']
if (-not $envProperty) { exit 0 }
if ($envProperty.Value -isnot [System.Management.Automation.PSCustomObject]) {
  Deny-UnreadableMap "``environments`` in .crew/verify.json is not an object, so no environment can be read out of it."
}

# Which environment does this command deploy to?
$envName = $null
foreach ($p in $vm.environments.PSObject.Properties) {
  if ($p.Value -isnot [System.Management.Automation.PSCustomObject]) {
    Deny-UnreadableMap "environment ``$($p.Name)`` in .crew/verify.json is not an object."
  }
  $declared = $p.Value.deploy
  if ($null -ne $declared) {
    # A bare string is ONE command. Stated rather than left to the `foreach`,
    # which already treats it that way, because promote-gate.sh has to
    # normalise it explicitly (it iterated the string's characters) and the two
    # flavours must be reading the same shape for the same reason.
    if ($declared -is [string]) { $declared = @($declared) }
    if ($declared -isnot [array] -or @($declared | Where-Object { $_ -isnot [string] }).Count -gt 0) {
      Deny-UnreadableMap "environment ``$($p.Name)`` in .crew/verify.json has a ``deploy`` that is not a command or a list of commands."
    }
    foreach ($dep in $declared) {
      if ($dep -and ($cmd -like "*$dep*" -or $dep -like "*$cmd*")) { $envName = $p.Name; break }
    }
  }
  if ($envName) { break }
}
if (-not $envName) { exit 0 }

# --- Emergency lane -------------------------------------------------------
#
# Twin of crew_incident_active / crew_incident_log in _common.sh, inline for
# the same reason as in verify-gate.ps1: a dot-sourced function is invisible
# to scripts/check-powershell.ps1's static call check. See
# hooks/scripts/crew_incident.py for the file format.
function Test-CrewIncidentActive {
  if (-not (Test-Path ".crew/incident.json")) { return $false }
  try {
    $c = Get-Content .crew/config.json -Raw -ErrorAction Stop | ConvertFrom-Json
    if ($c.emergency -and $c.emergency.standDown -eq $false) { return $false }
  } catch { }
  try { $inc = Get-Content .crew/incident.json -Raw -ErrorAction Stop | ConvertFrom-Json }
  catch { return $false }
  if (-not $inc.expiresAtEpoch) { return $false }
  return ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -lt [long]$inc.expiresAtEpoch)
}

function Write-CrewIncidentSkip([string]$Gate, [string]$Detail) {
  if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force | Out-Null }
  $log = ".crew/incident-skips.log"
  # The log is tab-separated and line-oriented, and a detail can carry an
  # environment name, a rollback path or a rollbackReason straight out of
  # .crew/verify.json - a tab or a newline in one would forge a row. _common.sh
  # and crew_incident.py normalise the same way.
  $Gate = $Gate -replace "[`t`r`n]", " "
  $Detail = $Detail -replace "[`t`r`n]", " "
  $row = "$Gate`t$Detail"
  # One row per gate+detail per incident, not per turn: the closing report is a
  # debt list, and the same unrun check is one debt however many turns declined
  # to run it. _common.sh applies the same rule.
  if (Test-Path $log) {
    foreach ($line in (Get-Content $log -ErrorAction SilentlyContinue)) {
      $parts = $line -split "`t", 2
      if ($parts.Count -eq 2 -and $parts[1] -eq $row) { return }
    }
  }
  $epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  Add-Content -Path $log -Value "$epoch`t$row" -Encoding utf8
}

# An open incident turns every block below into a recorded skip. The checks
# still RUN - they are file reads, not test suites, and the debt list is worth
# far more when it names the precondition that was unmet.
$incident = Test-CrewIncidentActive

$cfg = $vm.environments.$envName
$problems = New-Object System.Collections.Generic.List[string]
$sha = $null

# One refusal path for the tree checks below: a recorded skip during an
# incident, a block otherwise. Twin of block() in promote-gate.sh.
function Stop-Promotion([string]$Why) {
  $at = if ($script:sha) { $script:sha } else { "unknown-sha" }
  if ($incident) {
    Write-CrewIncidentSkip "promote" "$envName at ${at}: $Why"
    exit 0
  }
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName): $Why")
  exit 2
}

# WHICH tree (T-0505). Twin of the block in promote-gate.sh, whose header
# carries the full reasoning: the sha and the clean-tree check come from the
# tree the deploy RUNS FROM - the payload `cwd` (else the project dir), moved
# by a leading `cd`/`Set-Location` chain, named by any `git -C <dir>` - which
# must be a worktree of the SAME repository. Policy and state (.crew/verify.json,
# .work/PROMOTIONS.md, .crew/.approved-*, the rollback runbook, the incident
# files, .crew/.deploy-in-flight) stay in the project dir: they are
# per-checkout, gitignored state that a fresh worktree lacks and a throwaway
# one can forge. The rules here are PowerShell's, because this flavour judges
# PowerShell-tool commands; the branch between the twins is the tool.
$projectTop = (git rev-parse --show-toplevel 2>$null)
if (-not $projectTop) { Stop-Promotion "not a git repository - cannot establish what is being deployed." }

function Resolve-Dir([string]$Base, [string]$Tok) {
  $t = $Tok
  if ($t -eq '~') { $t = $HOME }
  elseif ($t.StartsWith('~/') -or $t.StartsWith('~\')) { $t = Join-Path $HOME $t.Substring(2) }
  $candidate = if ([System.IO.Path]::IsPathRooted($t)) { $t } else { Join-Path $Base $t }
  if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { return $null }
  return (Resolve-Path -LiteralPath $candidate).ProviderPath
}
# The common dir identifies the repository: every linked worktree shares it.
function Get-CommonDir([string]$Dir) {
  $c = (git -C $Dir rev-parse --git-common-dir 2>$null)
  if (-not $c) { return $null }
  $p = if ([System.IO.Path]::IsPathRooted($c)) { $c } else { Join-Path $Dir $c }
  if (-not (Test-Path -LiteralPath $p)) { return $null }
  return ((Resolve-Path -LiteralPath $p).ProviderPath).TrimEnd('\', '/')
}

$base = (Get-Location).ProviderPath
if (-not [string]::IsNullOrWhiteSpace($d.cwd)) {
  $base = Resolve-Dir $base "$($d.cwd)"
  if (-not $base) { Stop-Promotion "the command runs from '$($d.cwd)', which does not exist, so it is not inside a git worktree - cannot establish what is being deployed." }
}

# A token: double-quoted, single-quoted, or a word; `)` ends a word so
# `$(git -C dir rev-parse HEAD)` reads `dir`. `$` or a backtick in anything but
# single quotes is expanded by PowerShell, so the gate cannot know it.
$tokenRx = '(?:"([^"]*)"|''([^'']*)''|([^\s;&|()]+))'
function Get-TokenValue($m, [int]$first) {
  if ($m.Groups[$first + 1].Success) { return @($m.Groups[$first + 1].Value, $false) }
  $v = if ($m.Groups[$first].Success) { $m.Groups[$first].Value } else { $m.Groups[$first + 2].Value }
  return @($v, ($v.Contains('$') -or $v.Contains('`')))
}
$cdRx = [regex]('\G\s*(?:cd|chdir|sl|Set-Location|pushd|Push-Location)(?:\s+-(?:Literal)?Path)?\s+' + $tokenRx + '\s*(?:&&|;)')
$pos = 0
while ($true) {
  $m = $cdRx.Match($cmd, $pos)
  if (-not $m.Success) { break }
  $val = Get-TokenValue $m 1
  if ($val[1] -or $val[0] -eq '-') { Stop-Promotion "cannot tell which directory the deploy runs from: '$($val[0])' is expanded by the shell, and the gate will not guess what it names. Use a literal path." }
  $next = Resolve-Dir $base $val[0]
  if (-not $next) { Stop-Promotion "cannot tell which directory the deploy runs from: 'cd $($val[0])' does not resolve from '$base'." }
  $base = $next
  $pos = $m.Index + $m.Length
}
# A directory change AFTER the leading chain, or git pointed at a repository
# by --git-dir/--work-tree/GIT_DIR: the deploy may read a tree the chain does
# not name, so refuse rather than judge the wrong one.
$mid = [regex]::Match($cmd.Substring($pos), '(?:^|[;&|(`]|\$\()\s*(?:cd|chdir|sl|Set-Location|pushd|Push-Location)\b', 'IgnoreCase')
if ($mid.Success) {
  Stop-Promotion "cannot tell which directory the deploy runs from: the command changes directory after it starts ('$($mid.Value.Trim())'). Put the cd first - 'cd <dir>; <deploy>' - so the gate judges the tree the deploy runs in."
}
$gitDir = [regex]::Match($cmd, '--git-dir\b|--work-tree\b|\bGIT_DIR\b|\bGIT_WORK_TREE\b')
if ($gitDir.Success) {
  Stop-Promotion "cannot tell which tree the deploy reads: '$($gitDir.Value)' points git at a repository by a route the gate does not follow. Use 'cd <dir>;' or 'git -C <dir>'."
}
$trees = New-Object System.Collections.Generic.List[string]
$bare = $false
$gitRx = [regex]('(?:^|(?<=[\s(;&|/`]))git\b((?:\s+-c\s+\S+)*)(\s+-C\s*' + $tokenRx + ')?')
foreach ($m in $gitRx.Matches($cmd)) {
  if (-not $m.Groups[2].Success) { $bare = $true; continue }
  $val = Get-TokenValue $m 3
  if ($val[1]) { Stop-Promotion "cannot tell which directory the deploy runs from: '$($val[0])' is expanded by the shell, and the gate will not guess what it names. Use a literal path." }
  $dir = Resolve-Dir $base $val[0]
  if (-not $dir) { Stop-Promotion "cannot tell which directory the deploy runs from: 'git -C $($val[0])' does not resolve from '$base'." }
  $trees.Add($dir)
}
if ($trees.Count -eq 0 -or $bare) { $trees.Add($base) }

$tree = $null
foreach ($dir in $trees) {
  $top = (git -C $dir rev-parse --show-toplevel 2>$null)
  if (-not $top) { Stop-Promotion "the deploy runs from '$dir', which is not inside a git worktree - cannot establish what is being deployed." }
  if (-not $tree) { $tree = $top }
  elseif ($top -ne $tree) { Stop-Promotion "the deploy command names more than one tree ('$tree' and '$top'), so which sha is being deployed is ambiguous. Run it from one tree." }
}

$treeCommon = Get-CommonDir $tree
$projectCommon = Get-CommonDir $projectTop
# Two failed lookups compare equal as two nulls; that is "could not tell".
if (-not $treeCommon -or -not $projectCommon) {
  Stop-Promotion "could not read the git common dir of '$tree' or of '$projectTop', so the gate cannot tell whether the deploy runs from this repository."
}
if ($treeCommon -ne $projectCommon) {
  Stop-Promotion "the deploy runs from '$tree', which is a worktree of a different repository than this project ('$projectTop'). Its sha has no PASS row, marker or map here."
}

$sha = (git -C $tree rev-parse --short HEAD 2>$null)
$full = (git -C $tree rev-parse HEAD 2>$null)
if (-not $sha) { Stop-Promotion "'$tree' has no commit at HEAD - cannot establish what is being deployed." }

# The deploy map is read from the project dir, whose dirt no longer blocks a
# worktree deploy. An uncommitted edit to it must not become policy.
if ((git status --porcelain -- .crew/verify.json 2>$null)) {
  Stop-Promotion ".crew/verify.json in the project dir ('$projectTop') has uncommitted edits. The deploy map is policy; commit the change (it is then reviewed like any other) or revert it."
}

if ((git -C $tree status --porcelain 2>$null)) {
  Stop-Promotion "the tree this deploy runs from ('$tree') is dirty. You would be deploying $sha plus changes that are in no commit and no review. Commit or stash there first."
}

# A literal sha must be the tree's HEAD; a hex token naming no commit here is
# not a sha and is left alone.
foreach ($m in [regex]::Matches($cmd, '(?<![0-9A-Za-z])[0-9a-fA-F]{7,40}(?![0-9A-Za-z])')) {
  $h = $m.Value
  $resolved = (git -C $tree rev-parse -q --verify "$h^{commit}" 2>$null)
  if ($resolved -and $resolved -ne $full) {
    Stop-Promotion "the command names commit '$h', but the tree it runs from ('$tree') is at $sha. The gate checks the sha being deployed; run it from a tree at '$h', or drop the literal."
  }
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

# rollback runbook: required for every gated environment. Fail CLOSED - an
# absent key used to mean "no rollback needed"; now it blocks the deploy. The
# only way to opt out is rollback: "none" plus a rollbackReason.
if (-not ($cfg.PSObject.Properties.Name -contains 'rollback')) {
  $problems.Add("'$envName' has no 'rollback' key in .crew/verify.json. Add rollback: `"<path to a runbook>`", or rollback: `"none`" plus a rollbackReason string explaining why $envName does not need one. Fix: edit the '$envName' block in .crew/verify.json.")
} elseif ($cfg.rollback -eq 'none') {
  $reason = "$($cfg.rollbackReason)".Trim()
  if (-not $reason) {
    $problems.Add("'$envName' sets rollback: `"none`" but has no rollbackReason. State why $envName does not need a rollback plan. Fix: add a rollbackReason string next to rollback in .crew/verify.json.")
  }
} elseif (-not $cfg.rollback) {
  $problems.Add("'$envName' has an invalid rollback value. Fix: set rollback to a runbook path, or to the literal string `"none`" plus a rollbackReason.")
} elseif (-not (Test-Path $cfg.rollback)) {
  $problems.Add("the rollback runbook '$($cfg.rollback)' does not exist. No verified rollback, no deploy.")
} else {
  $txt = Get-Content $cfg.rollback -Raw
  $m = [regex]::Match($txt, 'last[ _-]?verified\s*[:=]\s*(\d{4}-\d{2}-\d{2})', 'IgnoreCase')
  if (-not $m.Success) {
    $problems.Add("'$($cfg.rollback)' has no 'last verified: YYYY-MM-DD' line. An unverified rollback is not a rollback.")
  } else {
    # A date-SHAPED string is not a date: the regex accepts `2026-99-99`, which
    # ParseExact throws on. Unhandled, that error left the deploy ALLOWED with
    # the in-flight marker written - the same fail-open as the bash twin, and
    # the reason both flavours are fixed in one change rather than one now and
    # the other when somebody next reads it.
    $verified = $null
    try {
      $verified = [datetime]::ParseExact($m.Groups[1].Value, 'yyyy-MM-dd', $null)
    } catch {
      $problems.Add("'$($cfg.rollback)' has 'last verified: $($m.Groups[1].Value)', which is date-shaped but not a real date. An unparseable verification date is not a verification.") | Out-Null
    }
    $age = if ($verified) { (Get-Date).Date - $verified } else { $null }
    if ($age -and $age.Days -gt 90) {
      $problems.Add("'$($cfg.rollback)' was last verified $($age.Days) days ago (ceiling is 90). Re-run it against a real environment first.")
    }
  }
}

if ($cfg.requireHuman) {
  $marker = ".crew/.approved-$envName-$sha"
  if (-not (Test-Path $marker)) {
    $problems.Add("this environment requires explicit human approval. Show the sha, the diff summary and the last promotion, get a yes, then create the marker: New-Item -ItemType File $marker")
  }
}

if ($problems.Count -gt 0 -and $incident) {
  # One row per unmet precondition, so the closing report names them all.
  $problems | ForEach-Object { Write-CrewIncidentSkip "promote" "$envName at ${sha}: $_" }
  $problems.Clear()
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
