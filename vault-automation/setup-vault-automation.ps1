<#
.SYNOPSIS
    Install the self-feeding Claude/Obsidian vault automation layer on this machine.

.DESCRIPTION
    Recreates the "learns, grows, documents on its own" pipeline:
      1. Obsidian community plugins (Dataview, Obsidian Git, Excalidraw, Omnisearch, Kanban)
      2. Session capture: Claude Code SessionEnd + PreCompact hooks -> inbox/pending-reflect.md
      3. Nightly gardener: scheduled task running headless Claude to distill queued
         sessions into concepts/daily notes with provenance
      4. HOME.md Dataview dashboard + reflection queue
      5. OPTIONAL git layer (-UseGit / -GitRemote) for version history. Vaults synced by
         Obsidian Sync need no git; the gardener detects and adapts either way.

    DRY-RUN BY DEFAULT - nothing changes until you pass -Apply.
    Idempotent: safe to re-run; existing files/hooks are detected and skipped.

.PARAMETER VaultPath      Path to the Obsidian vault. Default C:\repos\claude-memories
.PARAMETER Apply          Actually make changes (otherwise: report what would happen)
.PARAMETER UseGit         Initialize git in the vault + configure obsidian-git auto-commit
.PARAMETER GitRemote      Optional git remote URL to add as origin and push (implies -UseGit)
.PARAMETER GardenerTime   Daily run time for the gardener task. Default 02:23
.PARAMETER SkipPlugins    Skip Obsidian community plugin installs
.PARAMETER SkipGardener   Skip the gardener script + scheduled task

.EXAMPLE
    .\setup-vault-automation.ps1                          # preview everything
    .\setup-vault-automation.ps1 -Apply                   # Obsidian-Sync-only vault
    .\setup-vault-automation.ps1 -Apply -UseGit -GitRemote git@github.com:me/claude-memories.git
#>
[CmdletBinding()]
param(
    [string]$VaultPath = 'C:\repos\claude-memories',
    [switch]$Apply,
    [switch]$UseGit,
    [string]$GitRemote,
    [string]$GardenerTime = '02:23',
    [switch]$SkipPlugins,
    [switch]$SkipGardener
)

$ErrorActionPreference = 'Stop'
if ($GitRemote) { $UseGit = $true }
# Paths get baked into Python raw strings and single-quoted PowerShell literals -
# normalize/reject shapes that would break either (trailing backslash, quotes).
if ($VaultPath.Length -gt 3) { $VaultPath = $VaultPath.TrimEnd('\') }  # keep drive roots like D:\ intact
if ($VaultPath -match "'" ) { throw "VaultPath must not contain a single quote: $VaultPath" }
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$claudeDir = Join-Path $env:USERPROFILE '.claude'
$mode = if ($Apply) { 'APPLY' } else { 'DRY-RUN (pass -Apply to execute)' }
Write-Host "== Vault automation setup [$mode] ==" -ForegroundColor Cyan
Write-Host "   Vault: $VaultPath"

function Step([string]$Name, [scriptblock]$Preview, [scriptblock]$Action) {
    Write-Host "-- $Name" -ForegroundColor Yellow
    & $Preview
    if ($Apply) { & $Action }
}

# ---------- Preflight ----------
if (-not (Test-Path $VaultPath)) { throw "Vault path not found: $VaultPath (create the vault first, or point -VaultPath at it)" }
$claudeExe = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
if (-not (Test-Path $claudeExe)) {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($cmd) { $claudeExe = $cmd.Source } else { throw 'claude CLI not found (install Claude Code first)' }
}
if ($claudeExe -match "'") { throw "claude path must not contain a single quote: $claudeExe" }
$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { throw 'python not found on PATH (required for the capture hook)' }
foreach ($skill in 'recall','reflect','canvas') {
    if (-not (Test-Path (Join-Path $claudeDir "skills\$skill\SKILL.md"))) {
        Write-Warning "Memory skill '$skill' not installed in ~/.claude/skills - the gardener references it. Copy your skills over for best results."
    }
}
Write-Host "   claude: $claudeExe"

# ---------- 1. Obsidian community plugins ----------
if (-not $SkipPlugins) {
    $plugins = @(
        @{ id='dataview';                   repo='blacksmithgu/obsidian-dataview' },
        @{ id='obsidian-git';               repo='Vinzent03/obsidian-git' },
        @{ id='obsidian-excalidraw-plugin'; repo='zsviczian/obsidian-excalidraw-plugin' },
        @{ id='omnisearch';                 repo='scambier/obsidian-omnisearch' },
        @{ id='obsidian-kanban';            repo='mgmeyers/obsidian-kanban' }
    )
    $plugRoot = Join-Path $VaultPath '.obsidian\plugins'
    Step 'Obsidian community plugins' {
        foreach ($p in $plugins) {
            $state = if (Test-Path (Join-Path $plugRoot "$($p.id)\manifest.json")) { 'present' } else { 'WILL INSTALL' }
            Write-Host "   $($p.id): $state"
        }
    } {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        New-Item -ItemType Directory -Force -Path $plugRoot | Out-Null
        foreach ($p in $plugins) {
            $dir = Join-Path $plugRoot $p.id
            if (Test-Path (Join-Path $dir 'manifest.json')) { continue }
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            foreach ($asset in 'main.js','manifest.json','styles.css') {
                try {
                    Invoke-WebRequest -Uri "https://github.com/$($p.repo)/releases/latest/download/$asset" `
                        -OutFile (Join-Path $dir $asset) -UseBasicParsing -ErrorAction Stop
                } catch { if ($asset -ne 'styles.css') { throw "download failed: $($p.id)/$asset - $($_.Exception.Message)" } }
            }
            Write-Host "   installed $($p.id)"
        }
        # Merge (union) into community-plugins.json
        $cpFile = Join-Path $VaultPath '.obsidian\community-plugins.json'
        $existing = @()
        if (Test-Path $cpFile) { $existing = @(Get-Content $cpFile -Raw | ConvertFrom-Json) }
        $merged = @($existing + ($plugins | ForEach-Object { $_.id }) | Select-Object -Unique)
        ConvertTo-Json $merged | Set-Content $cpFile -Encoding utf8
        Write-Host '   community-plugins.json merged'
    }
}

# ---------- 2. obsidian-git auto-commit (git vaults only) ----------
if ($UseGit) {
    $ogData = Join-Path $VaultPath '.obsidian\plugins\obsidian-git\data.json'
    Step 'obsidian-git auto-commit config (15 min commit+push)' {
        Write-Host "   $(if (Test-Path $ogData) { 'present - will leave as-is' } else { 'WILL WRITE' })"
    } {
        if (-not (Test-Path $ogData)) {
            # The plugin's own directory may not exist yet - normally step 1 creates it,
            # but -SkipPlugins skips step 1 entirely, so create it here too.
            New-Item -ItemType Directory -Force -Path (Split-Path $ogData) | Out-Null
            @{
                commitMessage = 'vault auto-backup: {{date}}'; commitDateFormat = 'YYYY-MM-DD HH:mm:ss'
                autoSaveInterval = 15; autoPushInterval = 15; autoPullInterval = 0
                pullBeforePush = $true; disablePush = $false; disablePopups = $true
                showStatusBar = $true; syncMethod = 'merge'
                autoCommitMessage = 'vault auto-backup: {{date}}'
            } | ConvertTo-Json | Set-Content $ogData -Encoding utf8
            Write-Host '   written'
        }
    }
}

# ---------- 3. Capture hook script ----------
$hookPy = Join-Path $claudeDir 'hooks\vault-capture.py'
Step 'Session capture hook script (~/.claude/hooks/vault-capture.py)' {
    Write-Host "   $(if (Test-Path $hookPy) { 'present - will overwrite with configured vault path' } else { 'WILL WRITE' })"
} {
    New-Item -ItemType Directory -Force -Path (Split-Path $hookPy) | Out-Null
    (Get-Content (Join-Path $here 'vault-capture.py') -Raw).Replace('__VAULT_PATH__', $VaultPath) |
        Set-Content $hookPy -Encoding utf8
    # Validation-only self-test: checks vault path + inbox writability, writes no queue entry
    python $hookPy --selftest
    if ($LASTEXITCODE -ne 0) { throw 'vault-capture.py self-test failed' }
    Write-Host '   written + self-tested'
}

# ---------- 4. Merge SessionEnd/PreCompact hooks into settings.json ----------
$settingsFile = Join-Path $claudeDir 'settings.json'
Step 'Claude Code hooks (SessionEnd + PreCompact) in ~/.claude/settings.json' {
    $has = (Test-Path $settingsFile) -and ((Get-Content $settingsFile -Raw) -match 'vault-capture')
    Write-Host "   $(if ($has) { 'already wired' } else { 'WILL MERGE (existing hooks preserved)' })"
} {
    $mergePy = @'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); hook_py = sys.argv[2].replace("\\", "/")
d = json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}
hooks = d.setdefault("hooks", {})
def entry(trigger):
    return {"type": "command", "command": f'python "{hook_py}" {trigger}', "timeout": 15}
se = hooks.setdefault("SessionEnd", [])
if not any("vault-capture" in h.get("command", "") for g in se for h in g.get("hooks", [])):
    se.append({"hooks": [entry("session-end")]})
pc = hooks.setdefault("PreCompact", [])
if not any("vault-capture" in h.get("command", "") for g in pc for h in g.get("hooks", [])):
    if pc: pc[0].setdefault("hooks", []).append(entry("pre-compact"))
    else: pc.append({"hooks": [entry("pre-compact")]})
p.write_text(json.dumps(d, indent=2), encoding="utf-8")
json.loads(p.read_text(encoding="utf-8"))  # validate
print("   hooks merged + validated")
'@
    $tmp = Join-Path $env:TEMP 'vault-hook-merge.py'
    Set-Content $tmp $mergePy -Encoding utf8
    python $tmp $settingsFile $hookPy
    if ($LASTEXITCODE -ne 0) { throw 'settings.json hook merge failed' }
    Remove-Item $tmp -Force
}

# ---------- 5. HOME dashboard + reflection queue ----------
Step 'HOME.md dashboard + inbox/pending-reflect.md' {
    Write-Host "   HOME.md: $(if (Test-Path (Join-Path $VaultPath 'HOME.md')) { 'present - skip' } else { 'WILL WRITE' })"
    Write-Host "   inbox:   $(if (Test-Path (Join-Path $VaultPath 'inbox\pending-reflect.md')) { 'present - skip' } else { 'WILL WRITE' })"
} {
    # Not $home - that collides with PowerShell's read-only $HOME automatic variable
    # and throws on every -Apply run before this step (and everything after it) runs.
    $homeNote = Join-Path $VaultPath 'HOME.md'
    if (-not (Test-Path $homeNote)) {
        Copy-Item (Join-Path $here 'HOME-template.md') $homeNote
        Write-Host '   HOME.md written'
    }
    $inbox = Join-Path $VaultPath 'inbox\pending-reflect.md'
    if (-not (Test-Path $inbox)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $inbox) | Out-Null
        Set-Content $inbox "# Pending reflection queue`n`nAppended automatically by vault-capture.py (SessionEnd/PreCompact hooks).`nThe nightly vault gardener processes unchecked entries and checks them off.`n" -Encoding utf8
        Write-Host '   inbox written'
    }
}

# ---------- 6. Gardener + scheduled task ----------
if (-not $SkipGardener) {
    $gardener = Join-Path $VaultPath '.claude\gardener.ps1'
    Step "Nightly gardener (scheduled task 'Claude Vault Gardener' @ $GardenerTime)" {
        Write-Host "   script: $(if (Test-Path $gardener) { 'present - will refresh' } else { 'WILL WRITE' })"
        $t = Get-ScheduledTask -TaskName 'Claude Vault Gardener' -ErrorAction SilentlyContinue
        Write-Host "   task:   $(if ($t) { 'present - will re-register' } else { 'WILL REGISTER' })"
    } {
        New-Item -ItemType Directory -Force -Path (Split-Path $gardener) | Out-Null
        # $gitEnabled is baked in from -UseGit as consented HERE, at setup time - the
        # installed gardener must never re-derive push consent from runtime repo state.
        $gitEnabledLiteral = if ($UseGit) { '$true' } else { '$false' }
        (Get-Content (Join-Path $here 'gardener-template.ps1') -Raw).
            Replace('__VAULT_PATH__', $VaultPath).Replace('__CLAUDE_EXE__', $claudeExe).
            Replace('__GIT_ENABLED__', $gitEnabledLiteral) |
            Set-Content $gardener -Encoding utf8
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$gardener`""
        $trigger = New-ScheduledTaskTrigger -Daily -At $GardenerTime
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
        $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -DontStopOnIdleEnd
        Register-ScheduledTask -TaskName 'Claude Vault Gardener' -Action $action -Trigger $trigger -Principal $principal -Settings $set `
            -Description 'Nightly Obsidian vault reflection: distills queued Claude sessions into concepts/daily notes, maintains provenance' -Force | Out-Null
        Write-Host '   gardener written + task registered'
    }
}

# ---------- 7. Optional git layer ----------
if ($UseGit) {
    Step 'Git layer (history/rollback; Obsidian Sync remains the sync/backup)' {
        $isRepo = Test-Path (Join-Path $VaultPath '.git')
        Write-Host "   repo:   $(if ($isRepo) { 'present' } else { 'WILL git init + initial commit' })"
        if ($GitRemote) { Write-Host "   remote: WILL set origin -> $GitRemote (must exist; private recommended)" }
    } {
        Push-Location $VaultPath
        try {
            if (-not (Test-Path '.git')) {
                if (-not (Test-Path '.gitignore')) {
                    Set-Content '.gitignore' ".obsidian/workspace.json`n.obsidian-mcp/`n.serena/`n.raw/`n.vault-meta/`n.claude/gardener-logs/`n" -Encoding utf8
                }
                git init | Out-Null
                git add -A
                git commit -m 'Initial vault commit (setup-vault-automation)' | Out-Null
                Write-Host '   initialized + committed'
            }
            if ($GitRemote) {
                git remote get-url origin 2>$null | Out-Null
                if ($LASTEXITCODE -ne 0) { git remote add origin $GitRemote } else { git remote set-url origin $GitRemote }
                git push -u origin HEAD
                Write-Host '   pushed to origin'
            }
        } finally { Pop-Location }
    }
}

Write-Host ''
Write-Host '== Done ==' -ForegroundColor Cyan
if (-not $Apply) { Write-Host 'Dry run only. Re-run with -Apply to execute.' -ForegroundColor Yellow }
else {
    Write-Host 'Manual follow-ups:'
    Write-Host '  1. Reload Obsidian (Ctrl+R); turn off Restricted mode if prompted (plugins are pre-enabled)'
    Write-Host '  2. Multi-machine: run the gardener task on ONE machine only (avoid double distillation)'
    Write-Host "  3. Test the pipeline: Start-ScheduledTask 'Claude Vault Gardener' after your next session ends"
}
