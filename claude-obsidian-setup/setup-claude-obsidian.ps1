<#
.SYNOPSIS
  Set up claude-obsidian on Windows with WSL.

.DESCRIPTION
  Standards shared with the Linux script (setup-claude-obsidian.sh):
    * dry-run by default; nothing changes without -Apply
    * every check reports PASS / FIX / FAIL with a stable check id
    * identical vault layout, marketplaces, plugins and verification
    * idempotent: safe to re-run; satisfied steps are skipped
    * exits non-zero if any check is still FAIL

  Windows-specific reality this script exists to handle:
    * Native Windows CANNOT write to a vault. Mutation safety is bound to POSIX
      directory descriptors and fcntl.flock; native Python has no fcntl, so the
      core refuses writes with UNSUPPORTED_PLATFORM. All mutation runs in WSL.
    * Windows ships no python3.exe. The name resolves to a Microsoft Store alias
      stub that prints an install advert instead of running Python, which breaks
      the plugin's hooks and every documented `python3 ...` command.
    * /mnt/c mounts without the `metadata` option by default, so chmod returns
      EPERM inside WSL and every transaction apply dies with
      CORRUPT_RUNTIME_STATE: cannot write confined bundle copy.
    * git config --global does not cross the Windows/WSL boundary, so checkpoint
      fails with GIT_FAILED: Author identity unknown unless identity is set
      repo-locally.

.EXAMPLE
  .\setup-claude-obsidian.ps1
  .\setup-claude-obsidian.ps1 -Apply
  .\setup-claude-obsidian.ps1 -Apply -VaultPath C:\repos\Claude
#>
[CmdletBinding()]
param(
  # Everything lives under one root so a single switch relocates the whole setup.
  # C:\repos is the default; -RepoRoot moves it, and -VaultPath / -ProductRoot
  # override either half individually if you want them somewhere unrelated.
  [string]$RepoRoot    = 'C:\repos',
  [string]$VaultPath,
  [string]$ProductRoot,
  [switch]$Apply,
  [string]$Distro      = 'Ubuntu-24.04',
  [switch]$SkipPlugins,
  [switch]$SkipObsidian
)

if (-not $VaultPath)   { $VaultPath   = Join-Path $RepoRoot 'Claude' }
if (-not $ProductRoot) { $ProductRoot = Join-Path $RepoRoot 'claude-obsidian' }

$script:Failed = 0
function Pass($id,$msg){ Write-Host ("  PASS  {0,-28} {1}" -f $id,$msg) -ForegroundColor Green }
function Fix ($id,$msg){ Write-Host ("  FIX   {0,-28} {1}" -f $id,$msg) -ForegroundColor Yellow }
function Fail($id,$msg){ Write-Host ("  FAIL  {0,-28} {1}" -f $id,$msg) -ForegroundColor Red; $script:Failed = 1 }
function Head($t){ Write-Host "`n== $t" -ForegroundColor Cyan }

# Translate C:\a\b -> /mnt/c/a/b for commands executed inside WSL.
function To-Wsl([string]$p){
  $full = [System.IO.Path]::GetFullPath($p)
  $drive = $full.Substring(0,1).ToLower()
  return "/mnt/$drive/" + ($full.Substring(3) -replace '\\','/')
}
# Invoke WSL from PowerShell, never from Git Bash: Git Bash rewrites /mnt/...
# arguments and silently mangles the command.
function Wsl { param([Parameter(ValueFromRemainingArguments=$true)]$Args)
  & wsl.exe -d $Distro @Args 2>&1 | Out-String
}

Write-Host "claude-obsidian setup (windows + wsl)"
Write-Host ("  mode    : " + $(if($Apply){"APPLY"}else{"DRY-RUN (pass -Apply to change anything)"}))
Write-Host "  root    : $RepoRoot   (change with -RepoRoot)"
Write-Host "  vault   : $VaultPath"
Write-Host "  product : $ProductRoot"
Write-Host "  distro  : $Distro"

# ==========================================================================
Head "1. WSL platform"
# ==========================================================================
$wslExe = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wslExe) {
  Fail "wsl" "not installed. Run (elevated): wsl --install -d $Distro  then reboot"
} else {
  Pass "wsl" $wslExe.Source

  # wsl -l -v emits UTF-16; strip NULs so matching works.
  $list = (& wsl.exe -l -v 2>&1 | Out-String) -replace "`0",""
  if ($list -match [regex]::Escape($Distro)) {
    Pass "distro" "$Distro present"
    $state = if ($list -match "$([regex]::Escape($Distro))\s+(\w+)") { $Matches[1] } else { "?" }
    Pass "distro-state" $state
  } else {
    if ($Apply) {
      Fix "distro" "installing $Distro (this can take several minutes)"
      & wsl.exe --install -d $Distro
      Fix "distro" "if this is a first install, REBOOT and re-run this script"
    } else {
      Fix "distro" "would run: wsl --install -d $Distro"
    }
  }
}

# ==========================================================================
Head "2. Packages inside WSL"
# ==========================================================================
$wslOk = $false
if ($wslExe -and ((& wsl.exe -l -q 2>&1 | Out-String) -replace "`0","") -match [regex]::Escape($Distro)) {
  $wslOk = $true

  $pyv = (Wsl -- python3 -c "import sys;print('%d.%d'%sys.version_info[:2])").Trim()
  if ($pyv -match '^3\.(1[1-9]|[2-9]\d)') { Pass "wsl:python3" $pyv }
  elseif ($pyv) { Fail "wsl:python3" "$pyv found, 3.11+ required" }
  else { Fix "wsl:python3" "missing - will install" }

  $fcntl = (Wsl -- python3 -c "import fcntl;print('ok')").Trim()
  if ($fcntl -match 'ok') { Pass "wsl:fcntl" "available (vault writes supported)" }
  else { Fail "wsl:fcntl" "missing - vault writes will be refused" }

  $needPkgs = @()
  # python3 is version-checked above; only presence-check the rest here.
  foreach ($p in @("git","curl")) {
    $found = (Wsl -- sh -c "command -v $p || true").Trim()
    if ($found) { Pass "wsl:$p" $found } else { Fix "wsl:$p" "will install"; $needPkgs += $p }
  }
  if ($needPkgs.Count -gt 0) {
    if ($Apply) {
      Fix "wsl:packages" "installing: $($needPkgs -join ', ') (sudo may prompt)"
      & wsl.exe -d $Distro -- sudo apt-get update -qq
      & wsl.exe -d $Distro -- sudo apt-get install -y @needPkgs
    } else {
      Fix "wsl:packages" "would apt-get install: $($needPkgs -join ', ')"
    }
  }
}

# ==========================================================================
Head "3. /mnt/c metadata (required for vault writes on a Windows drive)"
# ==========================================================================
# Without the `metadata` automount option, chmod inside WSL returns EPERM on
# DrvFs and every transaction apply fails with CORRUPT_RUNTIME_STATE. This
# cannot be fixed by remounting live; it must be set in /etc/wsl.conf followed
# by a full `wsl --shutdown`.
$vaultOnWindowsDrive = $VaultPath -match '^[A-Za-z]:'
if (-not $wslOk) {
  Fix "wsl:metadata" "checked once WSL is available"
} elseif (-not $vaultOnWindowsDrive) {
  Pass "wsl:metadata" "vault is not on a Windows drive; not required"
} else {
  $mnt = (Wsl -- sh -c "mount | grep ' on /mnt/c ' || true")
  if ($mnt -match 'metadata') {
    Pass "wsl:metadata" "/mnt/c mounted with metadata"
  } else {
    if ($Apply) {
      Fix "wsl:metadata" "adding [automount] to /etc/wsl.conf (sudo may prompt)"
      $conf = 'grep -q "^\[automount\]" /etc/wsl.conf 2>/dev/null || printf "\n[automount]\noptions = \"metadata,uid=1000,gid=1000\"\n" | sudo tee -a /etc/wsl.conf >/dev/null'
      & wsl.exe -d $Distro -- sudo cp -n /etc/wsl.conf /etc/wsl.conf.bak-claude-obsidian 2>$null
      & wsl.exe -d $Distro -- bash -lc $conf
      Fix "wsl:metadata" "shutting WSL down so the new mount options take effect"
      & wsl.exe --shutdown
      Start-Sleep -Seconds 3
      $mnt2 = (Wsl -- sh -c "mount | grep ' on /mnt/c ' || true")
      if ($mnt2 -match 'metadata') { Pass "wsl:metadata" "verified after restart" }
      else { Fail "wsl:metadata" "still missing - inspect /etc/wsl.conf" }
    } else {
      Fix "wsl:metadata" "would add [automount] options=metadata,uid=1000,gid=1000 to /etc/wsl.conf + wsl --shutdown"
    }
  }
}

# ==========================================================================
Head "4. Windows-side tools"
# ==========================================================================
$py = Get-Command python.exe -ErrorAction SilentlyContinue
if ($py) { Pass "python" "$($py.Source)" } else { Fix "python" "install Python 3.11+ from python.org (needed for read-only/dry-run)" }

# python3 must not resolve to the Microsoft Store alias stub.
$py3 = Get-Command python3 -ErrorAction SilentlyContinue
$storeStub = $py3 -and ($py3.Source -like "*WindowsApps*")
if ($py3 -and -not $storeStub) {
  Pass "python3" $py3.Source
} elseif ($py) {
  $target = Join-Path (Split-Path $py.Source) "python3.exe"
  if ($Apply) {
    try {
      New-Item -ItemType HardLink -Path $target -Target $py.Source -ErrorAction Stop | Out-Null
      Fix "python3" "created hard link $target"
    } catch {
      try { Copy-Item $py.Source $target -ErrorAction Stop; Fix "python3" "copied to $target" }
      catch { Fail "python3" "could not create $target : $($_.Exception.Message)" }
    }
  } else {
    Fix "python3" "would hard-link $target -> $($py.Source) (currently: $(if($storeStub){'Microsoft Store stub'}else{'absent'}))"
  }
} else {
  Fail "python3" "no Windows Python to link from"
}

foreach ($c in @("git","node","npm")) {
  $g = Get-Command $c -ErrorAction SilentlyContinue
  if ($g) { Pass $c $g.Source } else { Fix $c "install it (node/npm are required by Claude Code)" }
}

$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($claude) {
  Pass "claude-code" ((& claude --version 2>&1 | Select-Object -First 1))
} elseif ($Apply -and (Get-Command npm -ErrorAction SilentlyContinue)) {
  Fix "claude-code" "installing"
  & npm install -g @anthropic-ai/claude-code
} else {
  Fix "claude-code" "would run: npm install -g @anthropic-ai/claude-code"
}

$obsPaths = @("$env:LOCALAPPDATA\Programs\Obsidian\Obsidian.exe",
              "$env:ProgramFiles\Obsidian\Obsidian.exe")
$obs = $obsPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($obs) {
  Pass "obsidian" $obs
} elseif ($SkipObsidian) {
  Pass "obsidian" "skipped (-SkipObsidian)"
} elseif ($Apply) {
  # Chocolatey is the only unattended route on Windows; winget is a fallback for
  # machines that have it but not choco. Both need an elevated prompt.
  if (Get-Command choco -ErrorAction SilentlyContinue) {
    & choco install obsidian -y --no-progress
    if ($LASTEXITCODE -eq 0) { Fix "obsidian" "installed via Chocolatey" }
    else { Fail "obsidian" "choco install obsidian failed (exit $LASTEXITCODE) - elevated prompt required" }
  } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    & winget install --id Obsidian.Obsidian -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -eq 0) { Fix "obsidian" "installed via winget" }
    else { Fail "obsidian" "winget install Obsidian.Obsidian failed (exit $LASTEXITCODE)" }
  } else {
    Fail "obsidian" "no choco or winget - install from https://obsidian.md"
  }
} else {
  Fix "obsidian" "would install via choco (or winget), or get it from https://obsidian.md"
}

# ==========================================================================
Head "5. Product checkout"
# ==========================================================================
$core = Join-Path $ProductRoot "scripts\claude-obsidian.py"
if (Test-Path $core) {
  Pass "product" $ProductRoot
} elseif ($Apply) {
  New-Item -ItemType Directory -Force -Path (Split-Path $ProductRoot) | Out-Null
  & git clone --depth 1 https://github.com/AgriciDaniel/claude-obsidian.git $ProductRoot
  if (Test-Path $core) { Fix "product" "cloned to $ProductRoot" } else { Fail "product" "clone failed" }
} else {
  Fix "product" "would clone AgriciDaniel/claude-obsidian to $ProductRoot"
}

# ==========================================================================
Head "6. Claude marketplaces and plugins"
# ==========================================================================
if ($SkipPlugins) {
  Pass "plugins" "skipped (-SkipPlugins)"
} elseif (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Fix "plugins" "would add marketplaces + install plugins once claude exists"
} else {
  $steps = @(
    @{ id="marketplace: claude-obsidian"; args=@("plugin","marketplace","add","AgriciDaniel/claude-obsidian") },
    @{ id="plugin: claude-obsidian";      args=@("plugin","install","claude-obsidian@agricidaniel-claude-obsidian") },
    @{ id="marketplace: obsidian-skills"; args=@("plugin","marketplace","add","kepano/obsidian-skills") },
    @{ id="plugin: obsidian";             args=@("plugin","install","obsidian@obsidian-skills") }
  )
  foreach ($st in $steps) {
    if ($Apply) {
      $o = & claude @($st.args) 2>&1 | Out-String
      if ($LASTEXITCODE -eq 0 -or $o -match 'already') { Fix $st.id "ok" } else { Fail $st.id ($o.Trim() -split "`n")[0] }
    } else {
      Fix $st.id ("would run: claude " + ($st.args -join ' '))
    }
  }
}

# ==========================================================================
Head "7. Vault (created inside WSL - native Windows cannot write)"
# ==========================================================================
$vaultCfg = Join-Path $VaultPath ".claude-obsidian.json"
if (Test-Path $vaultCfg) {
  Pass "vault" "$VaultPath (already initialised)"
} elseif (-not (Test-Path $core) -or -not $wslOk) {
  Fix "vault" "waiting on product checkout and WSL"
} elseif ($Apply) {
  New-Item -ItemType Directory -Force -Path $VaultPath | Out-Null
  $wCore  = To-Wsl $core
  $wVault = To-Wsl $VaultPath
  $stamp  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
  # Preview and apply in the SAME environment: the approval hash binds to the
  # reviewing environment's filesystem identity, so a hash produced natively
  # cannot be replayed from WSL.
  $plan = Wsl -- python3 $wCore init $wVault --generated-at $stamp --operation-id init-reviewed
  $hash = ([regex]'"approved_plan_sha256": "([a-f0-9]{64})"').Match($plan).Groups[1].Value
  if (-not $hash) {
    Fail "vault init" "dry-run produced no approval hash"
    Write-Host ("        " + ($plan.Trim() -split "`n")[0])
  } else {
    $paths = ([regex]'"changed_paths": \[(?s)(.*?)\]').Match($plan).Groups[1].Value
    Write-Host "        changed paths:"; Write-Host $paths
    $out = Wsl -- python3 $wCore init $wVault --generated-at $stamp --operation-id init-reviewed --approved-plan-sha256 $hash --apply
    if ($out -match '"status":\s*"complete"') { Fix "vault init" "created $VaultPath" }
    else { Fail "vault init" (($out.Trim() -split "`n")[0]) }
  }
} else {
  Fix "vault init" "would init $VaultPath inside WSL (preview, then apply with its hash)"
}

# ==========================================================================
Head "8. Git identity (checkpoint runs in WSL, which has no global identity)"
# ==========================================================================
if (Test-Path (Join-Path $VaultPath ".git")) {
  $email = (& git -C $VaultPath config user.email 2>$null)
  if ($email) {
    Pass "git identity" $email
  } else {
    $ge = (& git config --global user.email 2>$null)
    if ($Apply -and $ge) {
      & git -C $VaultPath config user.email $ge
      & git -C $VaultPath config user.name  (& git config --global user.name)
      & git -C $VaultPath config core.fileMode false
      Fix "git identity" "copied global identity into the vault repo"
    } else {
      Fail "git identity" "set repo-locally: git -C $VaultPath config user.email you@example.com"
    }
  }
} else {
  Pass "git" "vault is not a repo (optional; checkpoint needs one)"
}

# ==========================================================================
Head "9. Verify"
# ==========================================================================
if ((Test-Path $core) -and (Test-Path $vaultCfg) -and $wslOk) {
  $wCore = To-Wsl $core; $wVault = To-Wsl $VaultPath
  $doc = Wsl -- python3 $wCore doctor --vault $wVault
  if ($doc -match '"ok":\s*true') { Pass "doctor" "ok" } else { Fail "doctor" "not ok" }
  $lint = Wsl -- python3 $wCore lint --vault $wVault
  $m = [regex]::Match($lint,'"issues_found":\s*(\d+)')
  if ($m.Success) {
    if ($m.Groups[1].Value -eq "0") { Pass "lint" "0 issues" } else { Fail "lint" "$($m.Groups[1].Value) issue(s)" }
  } else { Fail "lint" "did not run" }
} else {
  Fix "verify" "runs once product, WSL and vault exist"
}

Head "Next"
@"
  Obsidian    : open $VaultPath via the vault picker
  Templates   : Settings > Templates > Template folder location = wiki/templates
  Daily notes : Settings > Daily notes > New file location = wiki/daily,
                date format YYYY-MM-DD
  CLI (opt.)  : Settings > General > enable "Command line interface"
  Skills      : /claude-obsidian:wiki

  Remember on Windows: reads and dry-runs work natively, but every WRITE must
  run inside WSL. Checkpoint each operation immediately after it completes -
  anything that touches those paths afterwards (including Obsidian, which
  re-serialises .base files it opens) makes the checkpoint refuse.
"@ | Write-Host

if (-not $Apply) { Write-Host "`n  DRY RUN - nothing changed. Re-run with -Apply." -ForegroundColor Yellow }
exit $script:Failed
