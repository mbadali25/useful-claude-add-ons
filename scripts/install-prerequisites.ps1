#Requires -Version 5.1
<#
Bootstraps a Windows machine for this repo's skills: Chocolatey, git/awscli/nodejs/python,
the Claude Code CLI itself (with its path exported to the user PATH), and the team's
standard Claude Code plugin marketplaces. Idempotent - safe to re-run.

Everything is chosen from a menu up front, then installed unattended. The menu replaced
a linear run of ~15 yes/no prompts, which meant you had to sit through the whole script
to decline three things near the end. Every interactive answer (menu selection, API
keys, the SkillUI quick start) is collected before the first install starts.

The menu is a cursor picker: Up/Down to move, Space to toggle, Enter to start. On the
repo's own row, Right opens a second picker for the individual skills, so you can take
three of them instead of all twenty-five. Hosts that cannot read a key press - ISE, a
redirected console, a window under ten lines - get the original numbered prompt instead,
and every non-interactive path (-All, -Select, -Skills, -NonInteractive) bypasses both.

Everything is also detected before it is installed:
  * Chocolatey packages   - skipped when the package is already present (or its
                            command already resolves, e.g. git installed outside choco)
  * Marketplaces          - skipped when already registered (matched by name or repo)
  * Plugins               - skipped when already installed; optionally updated

Marketplaces and plugins are installed with the native 'claude plugin marketplace add'
and 'claude plugin install' commands - no 'npx claudepluginhub' wrapper. The wrapper
synthesized a local directory-backed marketplace per repo, which failed on Windows and
produced marketplace names ('cpd-<repo>-user') that this script's detection could not
match, so already-installed plugins were reinstalled on every run.

Run from an elevated (Administrator) PowerShell prompt for the full setup:
    .\scripts\install-prerequisites.ps1

If run from a non-elevated prompt, Chocolatey and the Chocolatey packages
(git/awscli/nodejs/python) are skipped - everything else still runs.

Common switches:
    -All                select every menu item, no prompt
    -Select '1,3,7-9'   select these menu items, no prompt (also accepts keys:
                        -Select 'strix,obsidian')
    -Skills 'a,b'       install only these of this repo's skills, no prompt
    -Team / -Community / -Plugins   the same for menu items 4, 6 and 19
                        each accepts names, numbers, 'all' or 'none', and selecting any
                        of them implies its parent menu item
                        (-Skills 'all' | 'none' also work; implies the repo item)
    -NonInteractive     select the default set, no prompt (CI/unattended)
    -SkillUIGuide       print the SkillUI quick start after installing it, no prompt
    -NotifySetup        scaffold the notify config after installing it, no prompt
    -ObsidianRepoRoot   root the Obsidian item suggests for the vault (default: C:\repos)
    -NoUpdate           never update an already-installed plugin, only report it
    -ForceRefresh       reinstall a plugin whose files changed in its marketplace
                        but whose declared version did not (see 'content drift')
    -DryRun             work out and print the selection, then stop without
                        installing anything
    -SkipBootstrap      narrow the selection to prerequisites + the Claude Code CLI
    -InstallScope       scope for marketplace/plugin installs: user (default), project, local
                        (accepts -PluginHubScope as an alias for backward compatibility)
#>

[CmdletBinding()]
param(
    [switch]$SkipBootstrap,   # narrow the selection to prerequisites + CLI
    [switch]$NonInteractive,  # take the default selection, no menu
    [switch]$NoUpdate,        # don't update already-installed plugins
    [switch]$ForceRefresh,    # reinstall a plugin whose files changed upstream without a version bump
    [switch]$DryRun,          # work out and print the selection, then stop without installing
    [switch]$All,             # select every menu item, no menu
    [string]$Select,          # explicit selection, no menu: '1,3,7-9' or 'strix,supabase'
    [string]$Skills,          # explicit skill subset, no sub-picker: 'cloudflare,drata' | 'all' | 'none'
    [string]$Team,            # explicit team-plugin subset (menu item 4)
    [string]$Community,       # explicit community-plugin subset (menu item 6)
    [string]$Plugins,         # explicit subset of this repo's own plugins (menu item 19)
    [switch]$SkillUIGuide,    # answer the SkillUI quick-start prompt up front
    [switch]$NotifySetup,     # answer the notify setup prompt up front
    [string]$ObsidianRepoRoot = 'C:\repos',  # root the Obsidian item suggests for the vault
    [string]$ObsidianMcpUrl = 'http://127.0.0.1:27123/mcp/',  # vault-server MCP endpoint (through an SSH tunnel)
    [string]$ObsidianMcpKey,                 # Local REST API key; without it the item explains and skips
    [Alias('PluginHubScope')]
    [ValidateSet('user', 'project', 'local')]
    [string]$InstallScope = 'user'  # machine-wide by default, not per-project
)

# Under 'irm ... | iex' this runs in the caller's scope, so both of the following are
# the caller's session, not a private script scope: remember the old preference and put
# it back at the end rather than leaving every later command in that shell on 'Stop'.
$script:PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Stop'

# #Requires is only honoured for script *files*. The advertised one-liner pipes this
# text through Invoke-Expression, where the directive is an inert comment, so the
# version gate has to be a real statement or a PS 3/4 host would fail somewhere deep in.
if ($PSVersionTable.PSVersion -lt [Version]'5.1') {
    throw "PowerShell 5.1 or newer is required (this host is $($PSVersionTable.PSVersion))."
}

$script:FailedSteps = @()
$script:Summary = [ordered]@{ Installed = 0; Updated = 0; Skipped = 0 }

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "    OK: $Message" -ForegroundColor Green }
function Write-Warn2 { param([string]$Message) Write-Host "    WARN: $Message" -ForegroundColor Yellow }
function Write-Skip { param([string]$Message) Write-Host "    SKIP: $Message" -ForegroundColor DarkGray; $script:Summary.Skipped++ }

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Sync-SessionEnvironment {
    # Chocolatey/npm installers write to the registry environment but never touch this
    # running process. git is the worst offender: it adds its own PATH entries *and*
    # GIT_INSTALL_ROOT, both of which later steps (git clone, Git Bash) depend on.
    # Refresh the whole environment, not just PATH, so those steps don't fail.
    # Prefer Chocolatey's own refreshenv implementation when it's available.
    $chocoProfile = if ($env:ChocolateyInstall) {
        Join-Path $env:ChocolateyInstall 'helpers\chocolateyProfile.psm1'
    } else { $null }

    if ($chocoProfile -and (Test-Path $chocoProfile)) {
        try {
            Import-Module $chocoProfile -DisableNameChecking -Force -ErrorAction Stop
            Update-SessionEnvironment
            return
        } catch {
            Write-Warn2 "Chocolatey refreshenv unavailable ($($_.Exception.Message)) - falling back to a manual refresh."
        }
    }

    # Manual fallback: replay Machine then User scope onto the process, leaving the
    # vars that are process-owned by nature alone.
    $preserve = @('USERNAME', 'COMPUTERNAME', 'PROCESSOR_ARCHITECTURE', 'PSModulePath', 'Path')
    foreach ($scope in 'Machine', 'User') {
        $vars = [Environment]::GetEnvironmentVariables($scope)
        foreach ($name in $vars.Keys) {
            if ($preserve -contains $name) { continue }
            [Environment]::SetEnvironmentVariable($name, $vars[$name], 'Process')
        }
    }
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($machinePath, $userPath) | Where-Object { $_ }) -join ';'
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Step $Name
    try {
        & $Action
    } catch {
        Write-Warn2 "$Name failed: $($_.Exception.Message)"
        $script:FailedSteps += $Name
    }
}

# --- Detection helpers -------------------------------------------------------

function Test-ClaudeAvailable {
    return [bool](Get-Command claude -ErrorAction SilentlyContinue)
}

function Get-ClaudeConfigRoot {
    if ($env:CLAUDE_CONFIG_DIR) { return $env:CLAUDE_CONFIG_DIR }
    return (Join-Path $env:USERPROFILE '.claude')
}

$script:ChocoCache = $null
function Get-ChocoInstalled {
    # name -> version for every locally installed Chocolatey package.
    # 'choco list' is local-only in v2+; v1 needed --local-only, which v2 rejects.
    param([switch]$Refresh)
    if ($script:ChocoCache -and -not $Refresh) { return $script:ChocoCache }
    $map = @{}
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        # Not $args - that's an automatic variable inside a function.
        $chocoArgs = @('list', '--limit-output')
        $major = 0
        try { $major = [int](([string](choco --version)).Split('.')[0]) } catch { $major = 0 }
        if ($major -lt 2) { $chocoArgs += '--local-only' }
        try {
            foreach ($line in (& choco @chocoArgs)) {
                $parts = "$line".Split('|')
                if ($parts.Count -ge 2 -and $parts[0]) { $map[$parts[0].Trim().ToLower()] = $parts[1].Trim() }
            }
        } catch {
            Write-Warn2 "Could not enumerate Chocolatey packages: $($_.Exception.Message)"
        }
    }
    $script:ChocoCache = $map
    return $map
}

function Test-ChocoPackageInstalled {
    # A package counts as present if Chocolatey knows about it under its own name or
    # the '.install' variant (nodejs installs as nodejs.install), or - importantly -
    # if the command it provides already resolves, since plenty of machines have git
    # or python installed outside Chocolatey and reinstalling would be wrong.
    param([string]$Package, [string]$Probe)
    $installed = Get-ChocoInstalled
    $key = $Package.ToLower()
    foreach ($candidate in @($key, "$key.install")) {
        if ($installed.ContainsKey($candidate)) {
            return [pscustomobject]@{ Present = $true; How = "choco package '$candidate' $($installed[$candidate])" }
        }
    }
    if ($Probe) {
        $cmd = Get-Command $Probe -ErrorAction SilentlyContinue
        if ($cmd) {
            return [pscustomobject]@{ Present = $true; How = "'$Probe' already resolves at $($cmd.Source)" }
        }
    }
    return [pscustomobject]@{ Present = $false; How = $null }
}

$script:MarketplaceCache = $null
function Get-ClaudeMarketplaces {
    param([switch]$Refresh)
    if ($null -ne $script:MarketplaceCache -and -not $Refresh) { return $script:MarketplaceCache }
    $list = @()
    if (Test-ClaudeAvailable) {
        try {
            $raw = claude plugin marketplace list --json
            if ($raw) { $list = @($raw | ConvertFrom-Json) }
        } catch {
            Write-Warn2 "Could not read marketplace list: $($_.Exception.Message)"
        }
    }
    $script:MarketplaceCache = $list
    return $list
}

function Test-MarketplaceInstalled {
    # Accepts either a marketplace name ('claude-plugins-official') or the GitHub
    # 'owner/repo' it was added from - the JSON carries both, and callers have one
    # or the other depending on which command registered it.
    param([string]$Identifier)
    foreach ($m in (Get-ClaudeMarketplaces)) {
        if ($m.name -and $m.name -eq $Identifier) { return $true }
        if ($m.repo -and $m.repo -eq $Identifier) { return $true }
        # 'owner/repo' also matches a marketplace named after just the repo half
        if ($Identifier -match '/' -and $m.name -eq $Identifier.Split('/')[-1]) { return $true }
    }
    return $false
}

$script:PluginCache = $null
function Get-ClaudePlugins {
    # name -> version, keyed on the bare plugin name (ids are 'name@marketplace').
    param([switch]$Refresh)
    if ($null -ne $script:PluginCache -and -not $Refresh) { return $script:PluginCache }
    $map = @{}
    if (Test-ClaudeAvailable) {
        try {
            $raw = claude plugin list --json
            if ($raw) {
                foreach ($p in @($raw | ConvertFrom-Json)) {
                    if (-not $p.id) { continue }
                    $name = "$($p.id)".Split('@')[0]
                    # Two marketplaces can publish the same plugin, and the map is keyed
                    # on the bare name. Let an enabled copy win over a disabled one -
                    # plain last-write-wins would report 'superpowers' as disabled just
                    # because the disabled duplicate sorts later by id.
                    if ($map.ContainsKey($name) -and $map[$name].Enabled -and -not $p.enabled) { continue }
                    $map[$name] = [pscustomobject]@{ Id = $p.id; Version = $p.version; Enabled = $p.enabled }
                }
            }
        } catch {
            Write-Warn2 "Could not read plugin list: $($_.Exception.Message)"
        }
    }
    $script:PluginCache = $map
    return $map
}

$script:McpCache = $null
function Get-ClaudeMcpServers {
    # 'claude mcp list' prints one 'name: command args' line per server. There is no
    # --json flag for it, so the name is taken off the front of each line.
    param([switch]$Refresh)
    if ($null -ne $script:McpCache -and -not $Refresh) { return $script:McpCache }
    $names = @()
    if (Test-ClaudeAvailable) {
        try {
            foreach ($line in (claude mcp list 2>$null)) {
                if ("$line" -match '^\s*([A-Za-z0-9_.-]+)\s*:') { $names += $Matches[1] }
            }
        } catch {
            Write-Warn2 "Could not read the MCP server list: $($_.Exception.Message)"
        }
    }
    $script:McpCache = $names
    return $names
}

function Test-McpServerRegistered {
    param([string]$Name)
    return ((Get-ClaudeMcpServers) -contains $Name)
}

function Add-McpServer {
    # Detect-then-act, same contract as Add-ClaudeMarketplace. $CommandArgs is the
    # server's own command line, passed after '--' so claude does not try to parse it.
    # Pass -Url instead for a server that is already listening over HTTP, where there
    # is no command to launch and claude takes the endpoint as a positional argument.
    param(
        [string]$Name,
        [string[]]$CommandArgs,
        [string]$Url,
        [hashtable]$EnvVars,
        [hashtable]$Headers,
        [string]$Note
    )
    if (-not (Test-ClaudeAvailable)) {
        throw "claude not found on PATH in this session - open a new shell and re-run this script."
    }
    if (Test-McpServerRegistered $Name) {
        Write-Skip "MCP server '$Name' already registered"
        return
    }
    if ($Url) {
        $addArgs = @('mcp', 'add', '--scope', $InstallScope, '--transport', 'http', $Name, $Url)
        # Headers go after the URL. Used for endpoints that authenticate with a
        # bearer token rather than launching a command, e.g. the Obsidian vault
        # server's Local REST API.
        if ($Headers) {
            foreach ($k in $Headers.Keys) { $addArgs += @('--header', "${k}: $($Headers[$k])") }
        }
    } else {
        $addArgs = @('mcp', 'add', '--scope', $InstallScope, $Name)
        if ($EnvVars) {
            foreach ($k in $EnvVars.Keys) { $addArgs += @('--env', "$k=$($EnvVars[$k])") }
        }
        $addArgs += '--'
        $addArgs += $CommandArgs
    }
    & claude @addArgs
    if ($LASTEXITCODE -ne 0) { throw "'claude mcp add $Name' failed - see the output above." }
    Get-ClaudeMcpServers -Refresh | Out-Null
    $script:Summary.Installed++
    Write-Ok "added MCP server '$Name'"
    if ($Note) { Write-Ok $Note }
}

function Get-ClaudeSkillsDir {
    # Some things (the 'skills' CLI, task-observer) install as plain user-level skills
    # rather than as Claude Code plugins, so they never show up in 'claude plugin list' -
    # detection for those is a filesystem check against the user-level skills directory.
    return (Join-Path (Get-ClaudeConfigRoot) 'skills')
}

function Test-UserSkillInstalled {
    param([string]$Name)
    return (Test-Path (Join-Path (Join-Path (Get-ClaudeSkillsDir) $Name) 'SKILL.md'))
}

# --- Install wrappers (detect, then act) -------------------------------------

function Add-ClaudeMarketplace {
    param([string]$Source, [string]$Name)
    $probe = if ($Name) { $Name } else { $Source }
    if (Test-MarketplaceInstalled $probe) {
        Write-Skip "marketplace '$probe' already registered"
        if (-not $NoUpdate) {
            $mp = (Get-ClaudeMarketplaces) | Where-Object { $_.name -eq $probe -or $_.repo -eq $probe } | Select-Object -First 1
            if ($mp -and $mp.name) {
                claude plugin marketplace update $mp.name | Out-Null
                Write-Ok "refreshed marketplace metadata for '$($mp.name)'"
            }
        }
        return
    }
    claude plugin marketplace add $Source --scope $InstallScope
    # $ErrorActionPreference = 'Stop' does not apply to native commands, so a failed
    # 'claude' invocation has to be caught on its exit code or it is reported as OK.
    if ($LASTEXITCODE -ne 0) { throw "'claude plugin marketplace add $Source' failed - see the output above." }
    Get-ClaudeMarketplaces -Refresh | Out-Null
    $script:Summary.Installed++
    Write-Ok "added marketplace '$Source'"
}

# --- Detection: what a marketplace clone and an installed plugin were built from ---
# A re-run used to spend one 'claude plugin update' spawn per plugin: 25 of this repo's
# skills meant 25 CLI launches that each re-checked the same marketplace and found
# nothing to do. Claude Code already records, per installed plugin, the marketplace
# commit it was installed from, and Add-ClaudeMarketplace has just re-cloned that
# marketplace. When the two SHAs match there is nothing to update and the spawn can be
# skipped outright. Everything below is a file read; any failure reports "cannot tell",
# which Install-ClaudePlugin treats as "ask the CLI" so the slow path is still there.
$script:InstalledShaCache = $null
function Get-InstalledPluginShas {
    # 'name@marketplace' -> the marketplace commit that copy was installed from.
    if ($null -ne $script:InstalledShaCache) { return $script:InstalledShaCache }
    $map = @{}
    $file = Join-Path (Join-Path (Get-ClaudeConfigRoot) 'plugins') 'installed_plugins.json'
    if (Test-Path $file) {
        try {
            $data = Get-Content -Raw -Path $file | ConvertFrom-Json
            if ($data.plugins) {
                foreach ($entry in $data.plugins.PSObject.Properties) {
                    foreach ($copy in @($entry.Value)) {
                        if ($copy.gitCommitSha -and -not $map.ContainsKey($entry.Name)) {
                            $map[$entry.Name] = "$($copy.gitCommitSha)"
                        }
                    }
                }
            }
        } catch {
            # An unreadable or reshaped state file just means "cannot tell".
        }
    }
    $script:InstalledShaCache = $map
    return $map
}

# Where a marketplace's checkout actually lives. Usually
# '<config>/plugins/marketplaces/<name>', but a marketplace added from a local path is
# used in place and Claude Code records that in known_marketplaces.json, so read the
# recorded location and only fall back to the conventional one.
$script:MarketplaceDirCache = $null
function Get-MarketplaceDir {
    param([string]$Marketplace)
    if ($null -eq $script:MarketplaceDirCache) {
        $map = @{}
        $file = Join-Path (Join-Path (Get-ClaudeConfigRoot) 'plugins') 'known_marketplaces.json'
        if (Test-Path $file) {
            try {
                $data = Get-Content -Raw -Path $file | ConvertFrom-Json
                foreach ($entry in $data.PSObject.Properties) {
                    if ($entry.Value.installLocation) { $map[$entry.Name] = "$($entry.Value.installLocation)" }
                }
            } catch { }
        }
        $script:MarketplaceDirCache = $map
    }
    if ($Marketplace -and $script:MarketplaceDirCache.ContainsKey($Marketplace)) {
        return $script:MarketplaceDirCache[$Marketplace]
    }
    return (Join-Path (Join-Path (Join-Path (Get-ClaudeConfigRoot) 'plugins') 'marketplaces') $Marketplace)
}

# Cached per marketplace - all of this repo's skills share one. A marketplace whose SHA
# cannot be read is remembered as '' so it is not re-probed once per plugin.
$script:MarketplaceShaCache = @{}
function Get-MarketplaceHeadSha {
    param([string]$Marketplace)
    if (-not $Marketplace) { return '' }
    if ($script:MarketplaceShaCache.ContainsKey($Marketplace)) {
        return $script:MarketplaceShaCache[$Marketplace]
    }
    $sha = ''
    $dir = Get-MarketplaceDir $Marketplace
    if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $dir '.git'))) {
        try {
            $out = git -C $dir rev-parse HEAD 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) { $sha = "$out".Trim() }
        } catch { }
    }
    $script:MarketplaceShaCache[$Marketplace] = $sha
    return $sha
}

# name -> declared version and source path, read once per marketplace from the clone's
# own marketplace.json. The version fills the in-memory plugin cache after an install
# without paying for another 'claude plugin list --json'; the source path is what the
# drift check diffs.
$script:MarketplaceCatalogCache = @{}
function Get-MarketplaceCatalog {
    param([string]$Marketplace)
    if (-not $script:MarketplaceCatalogCache.ContainsKey($Marketplace)) {
        $map = @{}
        $file = Join-Path (Join-Path (Get-MarketplaceDir $Marketplace) '.claude-plugin') 'marketplace.json'
        if (Test-Path $file) {
            try {
                foreach ($p in @((Get-Content -Raw -Path $file | ConvertFrom-Json).plugins)) {
                    if (-not $p.name) { continue }
                    # 'source' is only useful when it is a path inside the checkout; an
                    # entry may instead carry an object (a git URL elsewhere), which is
                    # left empty so the drift check reports "cannot tell".
                    $src = ''
                    if ($p.source -is [string]) { $src = "$($p.source)" -replace '^\./', '' }
                    $map["$($p.name)"] = [pscustomobject]@{
                        Version = if ($p.version) { "$($p.version)" } else { 'unknown' }
                        Source  = $src
                    }
                }
            } catch { }
        }
        $script:MarketplaceCatalogCache[$Marketplace] = $map
    }
    return $script:MarketplaceCatalogCache[$Marketplace]
}

function Get-MarketplacePluginVersion {
    param([string]$Marketplace, [string]$Name)
    if (-not $Marketplace) { return 'unknown' }
    $e = (Get-MarketplaceCatalog $Marketplace)[$Name]
    if ($e -and $e.Version) { return $e.Version }
    return 'unknown'
}

function Get-MarketplacePluginSource {
    param([string]$Marketplace, [string]$Name)
    if (-not $Marketplace) { return '' }
    $e = (Get-MarketplaceCatalog $Marketplace)[$Name]
    if ($e) { return $e.Source }
    return ''
}

function Test-PluginSourceChanged {
    # Did this plugin's own files change between two marketplace commits? Any commit in
    # the marketplace moves HEAD, so without this an unrelated edit anywhere in the repo
    # would drag every plugin in it back onto the slow path. Returns 'changed', 'same',
    # or 'unknown' (no git, a shallow clone, or a commit a force-push pruned).
    #
    # Both preference variables are shadowed function-locally (PowerShell restores them
    # on return): a non-zero native exit under $PSNativeCommandUseErrorActionPreference,
    # or a stderr line under $ErrorActionPreference = 'Stop', becomes a *terminating*
    # error. 'git diff --quiet' exits 1 for "there are differences", which is the drift
    # case itself - the whole reason this function exists - so a throw there would take
    # the installer down on exactly the input it is meant to detect.
    param([string]$Marketplace, [string]$OldSha, [string]$NewSha, [string]$Source)
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    if (-not $Source) { return 'unknown' }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return 'unknown' }
    $dir = Get-MarketplaceDir $Marketplace
    if (-not (Test-Path (Join-Path $dir '.git'))) { return 'unknown' }
    try {
        foreach ($sha in @($OldSha, $NewSha)) {
            git -C $dir cat-file -e "$sha^{commit}" 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) { return 'unknown' }
        }
        # 'git diff --quiet -- <path>' also exits 0 when the pathspec matches nothing,
        # which is indistinguishable from "unchanged" - so a plugin whose declared source
        # is not a real path in the clone would read as current forever. Check first.
        git -C $dir cat-file -e "${NewSha}:${Source}" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { return 'unknown' }
        git -C $dir diff --quiet $OldSha $NewSha -- $Source 2>&1 | Out-Null
        switch ($LASTEXITCODE) {
            0       { return 'same' }
            1       { return 'changed' }
            default { return 'unknown' }
        }
    } catch {
        return 'unknown'
    }
}

function Invoke-ForcePluginRefresh {
    # The only way to make Claude Code re-copy a plugin whose files changed upstream but
    # whose declared version did not: uninstall and install again. '-KeepData' leaves the
    # plugin's persistent data directory alone, so this costs the user nothing beyond the
    # two CLI calls. Only ever reached with -ForceRefresh.
    #
    # Both preference variables are shadowed function-locally for the same reason as
    # Test-PluginSourceChanged: this inspects $LASTEXITCODE itself, so a native failure
    # must come back as an exit code rather than a terminating error.
    param([string]$Spec)
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    try {
        claude plugin uninstall $Spec --keep-data --scope $InstallScope 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "could not uninstall '$Spec' to force a refresh - leaving the stale copy in place."
            return $false
        }
        # The install is deliberately NOT redirected, exactly as Install-ClaudePlugin
        # runs it: the CLI refuses a plugin whose marketplace declares an install command
        # when stdout is not a TTY, so swallowing the output here could fail the reinstall
        # of a plugin this function has already uninstalled.
        claude plugin install $Spec --scope $InstallScope
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "'$Spec' was uninstalled but reinstalling it failed - run 'claude plugin install $Spec' by hand."
            return $false
        }
    } catch {
        Write-Warn2 "forcing a refresh of '$Spec' failed ($($_.Exception.Message)) - run 'claude plugin install $Spec' by hand."
        return $false
    }
    return $true
}

function Add-PluginToCache {
    # Record a just-installed plugin in the in-memory cache instead of reloading the
    # whole list. 'claude plugin install' enables what it installs, so the copy is live -
    # and trusting that is more accurate than re-reading, since a freshly installed
    # plugin can still read as disabled in 'claude plugin list --json' (see
    # Enable-ClaudePlugin).
    param([string]$Spec, [string]$Version)
    $name = $Spec.Split('@')[0]
    $cache = Get-ClaudePlugins
    $cache[$name] = [pscustomobject]@{ Id = $Spec; Version = $Version; Enabled = $true }
}

function Enable-ClaudePlugin {
    # $Spec is 'name@marketplace'. For a plugin that was ALREADY installed before this
    # run: one switched off in settings.json is installed, at the right scope, and
    # completely inert - none of its skills or hooks are visible.
    #
    # Deliberately NOT called after a fresh install. 'claude plugin install' enables what
    # it installs, and on a new machine the just-installed plugin can still read as
    # disabled in 'claude plugin list --json' - so calling it there tried to enable every
    # plugin in the run and turned a benign "already enabled at user scope" into 18
    # failed steps.
    #
    # Never throws. Both preference variables are shadowed function-locally (PowerShell
    # restores them on return) because a native stderr line under
    # $ErrorActionPreference = 'Stop' - or any non-zero exit when
    # $PSNativeCommandUseErrorActionPreference is $true - becomes a *terminating* error.
    # That is what turned this into 18 failed steps, and the throw preempted any attempt
    # to inspect the command's own output.
    #
    # Success is judged from 'claude plugin list --json', not from the CLI's message:
    # 'claude plugin enable' reports "is already enabled at user scope" even for a plugin
    # that does not exist, so the text cannot tell success from failure. The plugin list
    # can.
    param([string]$Spec)
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $name = $Spec.Split('@')[0]
    $existing = (Get-ClaudePlugins)[$name]
    if (-not $existing) { return }      # not installed - nothing to enable
    if ($existing.Enabled) { return }   # already live
    foreach ($target in @($Spec, $name)) {
        try { claude plugin enable $target --scope $InstallScope 2>&1 | Out-Null } catch { }
        if ((Get-ClaudePlugins -Refresh)[$name].Enabled) {
            Write-Ok "plugin '$name' is enabled (--scope $InstallScope)"
            return
        }
    }
    Write-Warn2 "plugin '$name' may be installed but disabled - run '/plugin' and enable it by hand."
}

function Install-ClaudePlugin {
    # $Spec is 'name@marketplace'. Detection is on the bare name, so a plugin already
    # installed from a *different* marketplace counts as present and is not duplicated.
    #
    # Both preference variables are shadowed function-locally, as everywhere else on
    # this path: this function reads $LASTEXITCODE to decide whether an update failed
    # (documented as "not fatal"), and a terminating error there would skip the whole
    # drift branch below instead.
    param([string]$Spec)
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $name = $Spec.Split('@')[0]
    $existing = (Get-ClaudePlugins)[$name]
    if ($existing) {
        if ($NoUpdate) {
            Write-Skip "plugin '$name' already installed ($($existing.Id), version $($existing.Version))"
            Enable-ClaudePlugin $Spec
            return
        }
        $before = $existing.Version
        # Claude Code records the marketplace commit each installed copy came from, and
        # Add-ClaudeMarketplace has just re-cloned that marketplace. Comparing the two
        # SHAs answers "is there anything to update?" from two file reads instead of a
        # CLI launch - the whole reason a re-run of the 25-skill item finishes in
        # seconds rather than minutes. Anything unreadable leaves both empty, and the
        # slow path below runs exactly as it always did.
        $mkt = if ($Spec -match '@') { $Spec.Substring($Spec.IndexOf('@') + 1) } else { '' }
        $headSha = ''; $oldSha = ''; $drift = 'unknown'
        if ($mkt) {
            $headSha = Get-MarketplaceHeadSha $mkt
            $oldSha = (Get-InstalledPluginShas)[$Spec]
        }
        if ($headSha -and $oldSha) {
            if ($headSha -eq $oldSha) {
                Write-Skip "plugin '$name' already current (version $before)"
                Enable-ClaudePlugin $Spec
                return
            }
            # The marketplace has moved, but that says nothing about *this* plugin: one
            # commit anywhere in the repo moves HEAD for every plugin it publishes. Ask
            # git whether this plugin's own files changed before paying for the CLI.
            $drift = Test-PluginSourceChanged $mkt $oldSha $headSha (Get-MarketplacePluginSource $mkt $name)
            if ($drift -eq 'same') {
                Write-Skip "plugin '$name' already current (version $before)"
                Enable-ClaudePlugin $Spec
                return
            }
        }
        # The fully qualified 'name@marketplace' is what 'claude plugin update' wants:
        # a bare name is rejected with 'Plugin "<name>" not found', which made every
        # update in a re-run fail and print a warning that read like a real problem.
        $target = if ($Spec -match '@') { $Spec } else { $name }
        claude plugin update $target | Out-Null
        # A failed *update* is not fatal - the plugin is already installed and usable,
        # and 'claude plugin update' legitimately fails when the marketplace it came
        # from has moved on. Report it and carry on; a failed *install* still throws.
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "'claude plugin update $target' failed - keeping the installed version."
            Enable-ClaudePlugin $Spec
            return
        }
        $after = (Get-ClaudePlugins -Refresh)[$name].Version
        if ($after -ne $before) {
            $script:Summary.Updated++
            Write-Ok "plugin '$name' updated $before -> $after"
            Enable-ClaudePlugin $Spec
            return
        }
        # Content drift: this plugin's files changed upstream and the update did not
        # take. 'claude plugin update' decides by declared version, so a marketplace
        # that edits a plugin without bumping its version leaves every installed copy
        # silently stale - the CLI cheerfully reports "already at the latest version"
        # and copies nothing. Say so plainly rather than reporting it as current.
        if ($drift -eq 'changed') {
            $script:InstalledShaCache = $null
            if ((Get-InstalledPluginShas)[$Spec] -eq $headSha) {
                $script:Summary.Updated++
                Write-Ok "plugin '$name' refreshed (version $after, marketplace moved to $($headSha.Substring(0, [Math]::Min(7, $headSha.Length))))"
            } elseif ($ForceRefresh) {
                # Invoke-ForcePluginRefresh uninstalls before installing, so a failure
                # here can leave the plugin *gone*, not merely stale. It says which half
                # failed; throwing fails the step so the run does not end with "All
                # steps completed".
                if (-not (Invoke-ForcePluginRefresh $Spec)) {
                    throw "could not force-refresh '$Spec' - see the warning above."
                }
                Get-ClaudePlugins -Refresh | Out-Null
                $script:InstalledShaCache = $null
                $script:Summary.Updated++
                Write-Ok "plugin '$name' reinstalled to pick up changed files (version $after, unbumped)"
                return
            } else {
                Write-Warn2 "plugin '$name' changed in its marketplace but still declares version $after, so 'claude plugin update' copied nothing - the installed copy is stale. Ask the marketplace to bump the version, or re-run with -ForceRefresh to reinstall it."
            }
        } else {
            Write-Skip "plugin '$name' already current (version $after)"
        }
        Enable-ClaudePlugin $Spec
        return
    }
    claude plugin install $Spec --scope $InstallScope
    if ($LASTEXITCODE -ne 0) { throw "'claude plugin install $Spec' failed - see the output above." }
    # Add the new plugin to the in-memory cache rather than reloading the whole list:
    # a fresh run installs 25+ plugins, and 'claude plugin list --json' after each one
    # was a second CLI spawn per plugin that nothing in this run reads differently.
    $newMkt = if ($Spec -match '@') { $Spec.Substring($Spec.IndexOf('@') + 1) } else { '' }
    Add-PluginToCache $Spec (Get-MarketplacePluginVersion $newMkt $name)
    $script:Summary.Installed++
    Write-Ok "installed plugin '$Spec'"
    # No Enable-ClaudePlugin here: 'claude plugin install' already enabled it. See the
    # comment on that function for why calling it on this path breaks a fresh machine.
}

# --- Install catalog and menu -------------------------------------------------
# One ordered entry per selectable item. 'Key' is what the rest of the script tests
# with Test-Selected; 'Default' is what [D] (and -NonInteractive) picks, chosen to
# match the prompt defaults this script used before it had a menu.
$script:Catalog = @(
    [pscustomobject]@{ Key = 'prereqs';           Default = $true;  Name = 'Prerequisites: Chocolatey + git, awscli, nodejs, python (needs Administrator)' }
    [pscustomobject]@{ Key = 'cli';               Default = $true;  Name = 'Claude Code CLI (@anthropic-ai/claude-code) + PATH export + update check' }
    [pscustomobject]@{ Key = 'own-skills';        Default = $true;  Name = "This repo's marketplace + its skills" }
    [pscustomobject]@{ Key = 'team';              Default = $true;  Name = 'Team plugins: superpowers, frontend-design, excalidraw-generator' }
    [pscustomobject]@{ Key = 'find-skills';       Default = $true;  Name = 'find-skills skill (vercel-labs/skills)' }
    [pscustomobject]@{ Key = 'community';         Default = $true;  Name = 'Community marketplaces + plugins (adhd-output-style, azure-tools, ppt-master, ...)' }
    [pscustomobject]@{ Key = 'claude-code-setup'; Default = $true;  Name = 'claude-code-setup plugin (anthropics/claude-plugins-official)' }
    [pscustomobject]@{ Key = 'task-observer';     Default = $true;  Name = 'task-observer skill (rebelytics/one-skill-to-rule-them-all)' }
    [pscustomobject]@{ Key = 'aws-mcp';           Default = $false; Name = 'MCP server: AWS (awslabs.aws-api-mcp-server)' }
    [pscustomobject]@{ Key = 'azure-mcp';         Default = $false; Name = 'MCP server: Azure (@azure/mcp)' }
    [pscustomobject]@{ Key = 'playwright-mcp';    Default = $false; Name = 'MCP server: Playwright (@playwright/mcp)' }
    [pscustomobject]@{ Key = 'obsidian-mcp';      Default = $false; Name = 'MCP server: Obsidian vault server (Local REST API over an SSH tunnel)' }
    [pscustomobject]@{ Key = 'supabase';          Default = $false; Name = 'Supabase plugin (supabase@claude-plugins-official)' }
    [pscustomobject]@{ Key = 'context7';          Default = $false; Name = 'Context7 up-to-date library docs (npx ctx7 setup)' }
    [pscustomobject]@{ Key = 'playwright-cli';    Default = $false; Name = 'Playwright CLI (@playwright/cli) - browser automation from the shell' }
    [pscustomobject]@{ Key = 'skillui';           Default = $false; Name = 'SkillUI (npm) + Playwright/Chromium - extract a design system from a URL' }
    [pscustomobject]@{ Key = 'strix';             Default = $false; Name = 'Strix AI pentesting CLI (needs Docker + an LLM API key)' }
    [pscustomobject]@{ Key = 'obsidian';          Default = $false; Name = 'Obsidian desktop + claude-obsidian + obsidian-skills plugins' }
    [pscustomobject]@{ Key = 'repo-plugins';      Default = $false; Name = "This repo's plugins: crew (agents, commands, hooks)" }
    [pscustomobject]@{ Key = 'graphify';          Default = $false; Name = 'graphify code graph (uv tool install graphifyy; per-repo, not global)' }
)

$script:Selected = @{}
function Test-Selected { param([string]$Key) return [bool]$script:Selected[$Key] }

function Expand-SelectionSpec {
    # '1,3,7-9' -> the matching catalog keys. Item keys are accepted too, so
    # -Select 'strix,obsidian' works without counting rows in the menu.
    param([string]$Spec)
    $keys = @()
    foreach ($token in ($Spec -split '[,\s]+' | Where-Object { $_ })) {
        if ($token -match '^(\d+)\s*-\s*(\d+)$') {
            foreach ($n in [int]$Matches[1]..[int]$Matches[2]) {
                if ($n -ge 1 -and $n -le $script:Catalog.Count) { $keys += $script:Catalog[$n - 1].Key }
            }
        } elseif ($token -match '^\d+$') {
            $n = [int]$token
            if ($n -ge 1 -and $n -le $script:Catalog.Count) {
                $keys += $script:Catalog[$n - 1].Key
            } else {
                Write-Warn2 "ignoring out-of-range menu number '$token'"
            }
        } else {
            $hit = $script:Catalog | Where-Object { $_.Key -eq $token.ToLower() } | Select-Object -First 1
            if ($hit) { $keys += $hit.Key } else { Write-Warn2 "ignoring unknown menu item '$token'" }
        }
    }
    return $keys
}

# --- This repo's individual skills ---------------------------------------------
# Keep in sync with .claude-plugin/marketplace.json. Everything is on by default:
# picking a subset is the exception, and a fresh machine wants the lot.
$script:SkillCatalog = @(
    [pscustomobject]@{ Key = 'aws-opensearch';        Selected = $true; Name = 'aws-opensearch          - AWS OpenSearch: health, shards, reindex, ISM, snapshots' }
    [pscustomobject]@{ Key = 'bitbucket';             Selected = $true; Name = 'bitbucket               - Bitbucket Cloud: git auth, PRs, pipelines, REST API' }
    [pscustomobject]@{ Key = 'checkpoint-email';      Selected = $true; Name = 'checkpoint-email        - Check Point Email Security: phishing triage, quarantine' }
    [pscustomobject]@{ Key = 'cisco-meraki';          Selected = $true; Name = 'cisco-meraki            - Meraki Dashboard API: inventory, events, config changes' }
    [pscustomobject]@{ Key = 'claude-code-defaults';  Selected = $true; Name = 'claude-code-defaults    - Claude Code config: settings.json, permissions, hooks' }
    [pscustomobject]@{ Key = 'claude-code-tuneup';    Selected = $true; Name = 'claude-code-tuneup      - Audit a slow Claude Code setup: dupes, hooks, context' }
    [pscustomobject]@{ Key = 'claude-memories-canvas';Selected = $true; Name = 'claude-memories-canvas  - claude-memories vault: wiki/maps .canvas conventions' }
    [pscustomobject]@{ Key = 'claude-memories-vault'; Selected = $true; Name = 'claude-memories-vault   - claude-memories vault: layout, frontmatter, write lock' }
    [pscustomobject]@{ Key = 'cloudflare';            Selected = $true; Name = 'cloudflare              - Cloudflare v4: DNS, WAF, cache, Workers, Zero Trust' }
    [pscustomobject]@{ Key = 'drata';                 Selected = $true; Name = 'drata                   - Drata: controls, monitors, evidence, audit prep' }
    [pscustomobject]@{ Key = 'i-have-adhd';           Selected = $true; Name = 'i-have-adhd             - ADHD-friendly output: next action first, numbered steps' }
    [pscustomobject]@{ Key = 'infra-work-ticketing';  Selected = $true; Name = 'infra-work-ticketing    - ServiceDesk Plus / Jira: open tickets, log work notes' }
    [pscustomobject]@{ Key = 'intune-graph';          Selected = $true; Name = 'intune-graph            - Intune via Graph: devices, compliance, app deployment' }
    [pscustomobject]@{ Key = 'mermaid-svg-bitbucket'; Selected = $true; Name = 'mermaid-svg-bitbucket   - Pre-render Mermaid to SVG so Bitbucket displays it' }
    [pscustomobject]@{ Key = 'notify';                Selected = $true; Name = 'notify                  - Ping your phone or inbox: Telegram bot (two-way) or email' }
    [pscustomobject]@{ Key = 'obsidian-canvas';       Selected = $true; Name = 'obsidian-canvas         - Obsidian .canvas files as JSON: maps, boards, diagrams' }
    [pscustomobject]@{ Key = 'obsidian-vault-server'; Selected = $true; Name = 'obsidian-vault-server   - Self-hosted Obsidian on Ubuntu: Sync, REST/MCP endpoint' }
    [pscustomobject]@{ Key = 'repo-docs';             Selected = $true; Name = 'repo-docs               - Whole doc set: CLAUDE.md, READMEs, architecture, handoff' }
    [pscustomobject]@{ Key = 'shipstation';           Selected = $true; Name = 'shipstation             - ShipStation V2/V1/ShipEngine: labels, rates, orders' }
    [pscustomobject]@{ Key = 'sophos-central';        Selected = $true; Name = 'sophos-central          - Sophos Central: isolate endpoints, triage alerts, XDR' }
    [pscustomobject]@{ Key = 'terraform-docs-readme'; Selected = $true; Name = 'terraform-docs-readme   - Regenerate a Terraform module README with terraform-docs' }
    [pscustomobject]@{ Key = 'visio-diagrams';        Selected = $true; Name = 'visio-diagrams          - Native .vsdx diagrams from a spec, or via Visio COM' }
    [pscustomobject]@{ Key = 'wazuh-onprem';          Selected = $true; Name = 'wazuh-onprem            - Self-hosted Wazuh: server, indexer, dashboards, ossec.conf' }
    [pscustomobject]@{ Key = 'web-testing-playwright';Selected = $true; Name = 'web-testing-playwright  - Real-browser testing: screenshots, console, form flows' }
    [pscustomobject]@{ Key = 'work-log-reporter';     Selected = $true; Name = 'work-log-reporter       - Session work log + emailed PDF report over SMTP' }
)

foreach ($sk in $script:SkillCatalog) {
    $sk | Add-Member -NotePropertyName Spec -NotePropertyValue "$($sk.Key)@useful-claude-add-ons|mbadali25/useful-claude-add-ons|useful-claude-add-ons"
}

# --- This repo's own plugins --------------------------------------------------
# Keep in sync with .claude-plugin/marketplace.json and plugin/README.md. Unlike the
# skills, the menu row is off by default: a plugin can register hooks, and a hook runs
# whether or not Claude agrees with it, so it is opted into explicitly. 'Spec' is
# 'plugin@marketplace|marketplace-source|marketplace-name'.
$script:PluginCatalog = @(
    [pscustomobject]@{ Key = 'crew'; Selected = $true; Name = 'crew                    - Virtual dev team: 10 agents, 21 commands, safety hooks'; Spec = 'crew@useful-claude-add-ons|mbadali25/useful-claude-add-ons|useful-claude-add-ons' }
    [pscustomobject]@{ Key = 'obsidian-vault'; Selected = $true; Name = 'obsidian-vault          - Multi-vault memory: gardener/reflector agents, bridge+guard hooks'; Spec = 'obsidian-vault@useful-claude-add-ons|mbadali25/useful-claude-add-ons|useful-claude-add-ons' }
)

# --- Team plugins (menu item 4) -----------------------------------------------
# Unlike the skills these come from three different marketplaces, and only the ones
# behind a ticked plugin need registering. superpowers comes from
# anthropics/claude-plugins-official rather than obra's own marketplace: Install-
# ClaudePlugin detects on the bare name, so a machine that already had superpowers from
# the official marketplace would otherwise end up with an orphaned
# 'superpowers-marketplace' registration plus a second, disabled copy.
$script:TeamCatalog = @(
    [pscustomobject]@{ Key = 'superpowers';          Selected = $true; Name = 'superpowers             - Workflow skills: brainstorm, plans, TDD, code review'; Spec = 'superpowers@claude-plugins-official|anthropics/claude-plugins-official|claude-plugins-official' }
    [pscustomobject]@{ Key = 'frontend-design';      Selected = $true; Name = "frontend-design         - Anthropic's frontend design skill";                   Spec = 'frontend-design@claude-code-plugins|anthropics/claude-code|claude-code-plugins' }
    [pscustomobject]@{ Key = 'excalidraw-generator'; Selected = $true; Name = 'excalidraw-generator    - Excalidraw diagrams from a description';              Spec = 'excalidraw-generator@excalidraw-generator|lexiaoyao20/excalidraw-generator|excalidraw-generator' }
)

# --- Community plugins (menu item 6) ------------------------------------------
# Source repo -> marketplace name is *not* mechanical: fcakyon/claude-codex-settings
# publishes itself as 'claude-settings', and the last field is what
# 'plugin@marketplace' has to match.
$script:CommunityCatalog = @(
    [pscustomobject]@{ Key = 'adhd-output-style';       Selected = $true; Name = 'adhd-output-style       - ADHD-friendly output style';                Spec = 'adhd-output-style@claude-settings|fcakyon/claude-codex-settings|claude-settings' }
    [pscustomobject]@{ Key = 'azure-tools';             Selected = $true; Name = 'azure-tools             - Azure CLI/portal helpers';                  Spec = 'azure-tools@claude-settings|fcakyon/claude-codex-settings|claude-settings' }
    [pscustomobject]@{ Key = 'anthropic-office-skills'; Selected = $true; Name = "anthropic-office-skills - Anthropic's docx/pptx/xlsx/pdf skills";      Spec = 'anthropic-office-skills@claude-settings|fcakyon/claude-codex-settings|claude-settings' }
    [pscustomobject]@{ Key = 'agent-browser';           Selected = $true; Name = 'agent-browser           - vercel-labs browser agent';                 Spec = 'agent-browser@agent-browser|vercel-labs/agent-browser|agent-browser' }
    [pscustomobject]@{ Key = 'ppt-master';              Selected = $true; Name = 'ppt-master              - PowerPoint deck generation';                Spec = 'ppt-master@ppt-master|hugohe3/ppt-master|ppt-master' }
)

# --- Sub-picker groups --------------------------------------------------------
# Every menu row that installs more than one thing gets a sub-picker on the Right
# arrow, exactly like the repo's own skills row always had. 'Label' is a format string
# taking selected and total.
$script:Groups = @(
    [pscustomobject]@{ MenuKey = 'own-skills'; Single = 'skill';   Catalog = { $script:SkillCatalog };     Flag = '-Skills';    Noun = 'skills';            Title = 'Pick individual skills from this repo'; Label = "This repo's marketplace + {0} of {1} skills  >" }
    [pscustomobject]@{ MenuKey = 'team'; Single = 'team plugin';         Catalog = { $script:TeamCatalog };      Flag = '-Team';      Noun = 'team plugins';      Title = 'Pick team plugins';                     Label = 'Team plugins: {0} of {1} (superpowers, frontend-design, excalidraw)  >' }
    [pscustomobject]@{ MenuKey = 'community'; Single = 'community plugin';    Catalog = { $script:CommunityCatalog }; Flag = '-Community'; Noun = 'community plugins'; Title = 'Pick community plugins';                Label = 'Community marketplaces + {0} of {1} plugins  >' }
    [pscustomobject]@{ MenuKey = 'repo-plugins'; Single = 'plugin'; Catalog = { $script:PluginCatalog };    Flag = '-Plugins';   Noun = 'plugins';           Title = "Pick plugins from this repo";           Label = "This repo's plugins: {0} of {1} (crew, obsidian-vault - agents, commands, hooks)  >" }
)

function Get-Group {
    # Menu key -> its group descriptor, or $null when the row has no sub-picker.
    param([string]$MenuKey)
    return ($script:Groups | Where-Object { $_.MenuKey -eq $MenuKey } | Select-Object -First 1)
}

function Get-GroupCatalog {
    param($Group)
    return @(& $Group.Catalog)
}

function Get-GroupSelectedCount {
    param($Group)
    return @((Get-GroupCatalog $Group) | Where-Object { $_.Selected }).Count
}

function Set-AllInGroup {
    param($Group, [bool]$Value)
    foreach ($e in (Get-GroupCatalog $Group)) { $e.Selected = $Value }
}

function Test-GroupEntrySelected {
    # Only true when the parent menu row is selected too - an entry ticked in a
    # sub-picker whose parent is off installs nothing.
    param([string]$MenuKey, [string]$Key)
    if (-not (Test-Selected $MenuKey)) { return $false }
    $group = Get-Group $MenuKey
    if (-not $group) { return $false }
    $hit = (Get-GroupCatalog $group) | Where-Object { $_.Key -eq $Key } | Select-Object -First 1
    return [bool]($hit -and $hit.Selected)
}

function Expand-GroupSpec {
    # 'cloudflare,drata' | '1,4-6' | 'all' | 'none' -> sets .Selected on the catalog.
    param($Group, [string]$Spec)
    $catalog = Get-GroupCatalog $Group
    switch -Regex ($Spec) {
        '^(?i)all$'  { Set-AllInGroup $Group $true;  return }
        '^(?i)none$' { Set-AllInGroup $Group $false; return }
    }
    Set-AllInGroup $Group $false
    foreach ($token in ($Spec -split '[,\s]+' | Where-Object { $_ })) {
        if ($token -match '^(\d+)\s*-\s*(\d+)$') {
            $lo = [int]$Matches[1]; $hi = [int]$Matches[2]
            # Rejected rather than silently reinterpreted: PowerShell's '..' counts down
            # from '3-1' and would select three items while bash's for-loop selects none,
            # so the same command line would mean different things on the two platforms.
            if ($lo -gt $hi) {
                Write-Warn2 "ignoring reversed $($Group.Single) range '$token' - write it low-to-high"
            } else {
                foreach ($n in $lo..$hi) {
                    if ($n -ge 1 -and $n -le $catalog.Count) { $catalog[$n - 1].Selected = $true }
                }
            }
        } elseif ($token -match '^\d+$') {
            $n = [int]$token
            if ($n -ge 1 -and $n -le $catalog.Count) {
                $catalog[$n - 1].Selected = $true
            } else {
                Write-Warn2 "ignoring out-of-range $($Group.Single) number '$token'"
            }
        } else {
            # Match the catalog key, or the label the picker actually shows, which is
            # the only name the user ever sees. Every current catalog leads its label
            # with the key, but a group whose label differs still has to answer to
            # what is on screen.
            $want = $token.ToLower()
            $hit = $catalog | Where-Object {
                $_.Key -eq $want -or ($_.Name -split '\s+')[0].ToLower() -eq $want
            } | Select-Object -First 1
            if ($hit) { $hit.Selected = $true } else { Write-Warn2 "ignoring unknown $($Group.Single) '$token'" }
        }
    }
}

function Install-Group {
    # Install a group's ticked entries. Every sub-picker group goes through here, so the
    # catalog really is the single source it claims to be: the menu label, the picker,
    # the -<Group> flag and this loop all read the same Spec.
    #
    # Marketplaces are registered once each, before any plugin. Registering per plugin
    # meant three 'claude plugin marketplace update' runs against claude-settings on the
    # community row alone - and a marketplace refresh re-clones the repo.
    #
    # -AlreadyRegistered names a marketplace the caller has registered itself.
    #
    # The locals are named so they cannot collide with Invoke-Step's own parameters, and
    # the script blocks are closed over their values: PowerShell resolves a variable in a
    # script block against the *dynamic* scope it runs in, so a plain '$name' here would
    # pick up Invoke-Step's [string]$Name - the step label.
    param($Group, [string]$AlreadyRegistered = '')
    $entries = @((Get-GroupCatalog $Group) | Where-Object { $_.Selected -and $_.Spec })
    $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    if ($AlreadyRegistered) { $null = $seen.Add($AlreadyRegistered) }
    foreach ($entry in $entries) {
        $null, $entrySource, $entryMarketplace = $entry.Spec -split '\|', 3
        if (-not $seen.Add($entryMarketplace)) { continue }
        Invoke-Step "Marketplace: $entrySource" {
            Add-ClaudeMarketplace -Source $entrySource -Name $entryMarketplace
        }.GetNewClosure()
    }
    foreach ($entry in $entries) {
        $entryPlugin = ($entry.Spec -split '\|', 3)[0]
        Invoke-Step "Plugin: $entryPlugin" {
            Install-ClaudePlugin $entryPlugin
        }.GetNewClosure()
    }
}

function Get-SelectedSkillCount { return (Get-GroupSelectedCount (Get-Group 'own-skills')) }

function Set-AllSkills {
    param([bool]$Value)
    Set-AllInGroup (Get-Group 'own-skills') $Value
}

function Expand-SkillsSpec {
    param([string]$Spec)
    Expand-GroupSpec (Get-Group 'own-skills') $Spec
}

function Get-MenuLabel {
    # A grouped row carries a live count, because "its 25 skills" stops being true the
    # moment someone opens the sub-picker and unticks one.
    param([int]$Index)
    $item = $script:Catalog[$Index]
    $group = Get-Group $item.Key
    if ($group) {
        $catalog = Get-GroupCatalog $group
        return ($group.Label -f (Get-GroupSelectedCount $group), $catalog.Count)
    }
    return $item.Name
}

# --- Cursor picker ---------------------------------------------------------------
# Up/Down move, Space toggles, Enter starts, Right opens a sub-picker. Drawing is
# done with SetCursorPosition and space-padded lines rather than ANSI escapes,
# because VT processing is not on by default in every Windows PowerShell 5.1 console.
function Test-PickerSupported {
    try {
        if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) { return $false }
        if (-not $Host.UI.RawUI) { return $false }
        # ISE has no real console: ReadKey there throws rather than returning a key.
        if ($Host.Name -match 'ISE') { return $false }
        if ([Console]::WindowHeight -lt 10 -or [Console]::WindowWidth -lt 40) { return $false }
        # Prove ReadKey is reachable before committing the screen to a live redraw.
        [Console]::TreatControlCAsInput | Out-Null
    } catch {
        return $false
    }
    return $true
}

# Every console touch the picker makes goes through one of these three. They exist so
# the draw loop can be exercised without a console attached - a test dot-sources the
# script and replaces them - and so a host that throws on one of them fails in a single
# identifiable place rather than halfway through a repaint.
function Get-PickerConsole {
    return [pscustomobject]@{
        Height       = [Console]::WindowHeight
        Width        = [Console]::WindowWidth
        BufferHeight = [Console]::BufferHeight
        Top          = [Console]::CursorTop
    }
}

function Set-PickerCursor {
    param([int]$Row, [switch]$Reset)
    if ($Reset) { Clear-Host; return [Console]::CursorTop }
    [Console]::SetCursorPosition(0, $Row)
    return $Row
}

function Read-PickerKey {
    return [Console]::ReadKey($true)
}

function Format-PickerLine {
    # Clip to the window width. A line that wraps shifts everything below it and the
    # next redraw paints over the wrong rows.
    param([string]$Text, [int]$Width)
    if ($Text.Length -gt $Width) { return $Text.Substring(0, [Math]::Max(0, $Width - 1)) + '...' }
    return $Text.PadRight($Width)
}

function Invoke-Picker {
    <#
      Renders a checkbox list and returns a hashtable:
        Action = 'confirm' | 'cancel' | 'submenu' | 'back'
        State  = bool[] in the same order as -Labels
        Cursor = the row the user was on
      Rows flagged in -Sub open a sub-picker on Right instead of toggling.
    #>
    param(
        [string[]]$Labels,
        [bool[]]$State,
        [bool[]]$Sub,
        [bool[]]$Defaults,
        [string]$Title,
        [string]$Hint,
        [int]$Cursor = 0
    )
    $state = @($State)
    $total = $Labels.Count
    $top = 0
    $origin = -1
    $action = ''

    try {
        # Not every host implements this - a redirected or embedded console throws
        # "The handle is invalid". Hiding the cursor is cosmetic, so never let it stop
        # the menu from appearing.
        try { [Console]::CursorVisible = $false } catch { }
        while ($true) {
            $con = Get-PickerConsole
            $winH = $con.Height
            $winW = $con.Width
            $width = [Math]::Max(20, $winW - 10)
            # 2 title lines + rows + 1 scroll line + 2 hint lines, plus a line of slack.
            $avail = [Math]::Max(3, $winH - 6)
            if ($avail -gt $total) { $avail = $total }

            if ($Cursor -lt $top) { $top = $Cursor }
            if ($Cursor -ge $top + $avail) { $top = $Cursor - $avail + 1 }
            if ($top + $avail -gt $total) { $top = $total - $avail }
            if ($top -lt 0) { $top = 0 }

            $needed = $avail + 5
            if ($origin -lt 0 -or ($origin + $needed) -ge $con.BufferHeight) {
                # Repainting from a remembered row only works while that row is still on
                # screen; once the buffer would scroll, start clean instead of smearing.
                $origin = Set-PickerCursor -Reset
            }
            $null = Set-PickerCursor -Row $origin

            Write-Host (Format-PickerLine "  $Title" $winW).TrimEnd().PadRight($winW - 1) -ForegroundColor Cyan
            Write-Host ("  " + ('-' * $Title.Length)).PadRight($winW - 1) -ForegroundColor Cyan
            for ($i = $top; $i -lt $top + $avail; $i++) {
                $mark = if ($state[$i]) { 'x' } else { ' ' }
                $arrow = if ($i -eq $Cursor) { '>' } else { ' ' }
                $line = "  $arrow [$mark] " + (Format-PickerLine $Labels[$i] $width)
                if ($i -eq $Cursor) {
                    Write-Host $line.PadRight($winW - 1) -ForegroundColor Black -BackgroundColor Cyan
                } else {
                    Write-Host $line.PadRight($winW - 1)
                }
            }
            $scroll = if ($total -gt $avail) { "  showing $($top + 1)-$($top + $avail) of $total" } else { '' }
            Write-Host $scroll.PadRight($winW - 1) -ForegroundColor DarkGray
            $keys = if ($winW -lt 84) {
                '  Up/Dn move  Space pick  Enter go  A/N/D  Q quit'
            } else {
                '  Up/Down move   Space toggle   Enter start   A all   N none   D defaults   Q cancel'
            }
            Write-Host (Format-PickerLine $keys ($winW - 1)) -ForegroundColor DarkGray
            Write-Host (Format-PickerLine "  $Hint" ($winW - 1)) -ForegroundColor DarkGray

            $key = Read-PickerKey
            switch ($key.Key) {
                'UpArrow'    { if ($Cursor -gt 0)          { $Cursor-- } }
                'DownArrow'  { if ($Cursor -lt $total - 1) { $Cursor++ } }
                'Spacebar'   { $state[$Cursor] = -not $state[$Cursor] }
                'Enter'      { $action = 'confirm' }
                'RightArrow' { if ($Sub[$Cursor]) { $action = 'submenu' } }
                'LeftArrow'  { $action = 'back' }
                'Escape'     { $action = 'cancel' }
                default {
                    switch ("$($key.KeyChar)".ToLower()) {
                        'k' { if ($Cursor -gt 0)          { $Cursor-- } }
                        'j' { if ($Cursor -lt $total - 1) { $Cursor++ } }
                        'a' { for ($i = 0; $i -lt $total; $i++) { $state[$i] = $true } }
                        'n' { for ($i = 0; $i -lt $total; $i++) { $state[$i] = $false } }
                        'd' { for ($i = 0; $i -lt $total; $i++) { $state[$i] = [bool]$Defaults[$i] } }
                        'q' { $action = 'cancel' }
                    }
                }
            }
            if ($action) {
                return @{ Action = $action; State = $state; Cursor = $Cursor }
            }
        }
    } finally {
        # Without this the cursor stays hidden in the user's shell after Ctrl-C.
        try { [Console]::CursorVisible = $true } catch { }
        Write-Host ""
    }
}

function Select-GroupInteractive {
    # Restores the previous ticks on Q, so backing out of a sub-picker cannot silently
    # rewrite a selection.
    param($Group)
    $catalog = Get-GroupCatalog $Group
    $labels = @($catalog | ForEach-Object { $_.Name })
    $state = @($catalog | ForEach-Object { [bool]$_.Selected })
    $sub = @($catalog | ForEach-Object { $false })
    $defaults = @($catalog | ForEach-Object { $true })
    $saved = @($catalog | ForEach-Object { [bool]$_.Selected })
    $result = Invoke-Picker -Labels $labels -State $state -Sub $sub -Defaults $defaults `
        -Title $Group.Title `
        -Hint 'Enter or Left to go back to the main menu   Q to discard these changes'
    if ($result.Action -eq 'cancel') {
        for ($i = 0; $i -lt $catalog.Count; $i++) { $catalog[$i].Selected = $saved[$i] }
        return
    }
    for ($i = 0; $i -lt $catalog.Count; $i++) {
        $catalog[$i].Selected = [bool]$result.State[$i]
    }
}

function Select-MenuInteractive {
    $state = @($script:Catalog | ForEach-Object { [bool]$_.Default })
    $defaults = @($script:Catalog | ForEach-Object { [bool]$_.Default })
    $sub = @($script:Catalog | ForEach-Object { [bool](Get-Group $_.Key) })
    $cursor = 0

    while ($true) {
        $labels = @(for ($i = 0; $i -lt $script:Catalog.Count; $i++) { Get-MenuLabel $i })
        $result = Invoke-Picker -Labels $labels -State $state -Sub $sub -Defaults $defaults `
            -Title 'Select what to install' `
            -Hint 'Right on a row marked > picks the individual items inside it' -Cursor $cursor
        $state = @($result.State)
        $cursor = $result.Cursor
        if ($result.Action -eq 'submenu') {
            $group = Get-Group $script:Catalog[$cursor].Key
            if ($group) {
                Select-GroupInteractive $group
                # Opening a sub-picker is a statement of intent: tick the parent row so
                # a careful sub-selection is not silently thrown away by an unticked
                # parent.
                if ((Get-GroupSelectedCount $group) -gt 0) { $state[$cursor] = $true }
            }
            continue
        }
        if ($result.Action -eq 'cancel') {
            Write-Host "  Cancelled - nothing selected." -ForegroundColor Yellow
            return @()
        }
        $keys = @()
        for ($i = 0; $i -lt $script:Catalog.Count; $i++) {
            if ($state[$i]) { $keys += $script:Catalog[$i].Key }
        }
        return $keys
    }
}

function Select-MenuInteractiveSafe {
    <#
      Returns the selected keys, or $null if the picker failed part-way through.

      Test-PickerSupported only proves the picker can *start*. It can still die
      mid-draw - SetCursorPosition throws ArgumentOutOfRange if the window is
      resized smaller between frames - and $ErrorActionPreference is 'Stop' here,
      so an unguarded throw would take the whole installer with it. Returning $null
      lets the caller fall back to the numbered menu, which is what the docs promise.
    #>
    try {
        return ,@(Select-MenuInteractive)
    } catch {
        Write-Warn2 "the cursor menu stopped working ($($_.Exception.Message)) - falling back to the numbered menu."
        try { [Console]::CursorVisible = $true } catch { }
        return $null
    }
}

function Show-InstallMenu {
    Write-Host ""
    Write-Host "  Select what to install" -ForegroundColor Cyan
    Write-Host "  ----------------------" -ForegroundColor Cyan
    for ($i = 0; $i -lt $script:Catalog.Count; $i++) {
        $item = $script:Catalog[$i]
        $mark = if ($item.Default) { 'x' } else { ' ' }
        Write-Host ("  {0,2}  [{1}]  {2}" -f ($i + 1), $mark, (Get-MenuLabel $i))
    }
    Write-Host ""
    Write-Host "  [x] marks the default set." -ForegroundColor DarkGray
    Write-Host "  A = all   D = defaults   N = none   or numbers like 1,3,7-9" -ForegroundColor DarkGray
    Write-Host "  Rows marked > hold several items; pick inside them with the arrow" -ForegroundColor DarkGray
    Write-Host "  keys, or non-interactively with -Skills / -Team / -Community /" -ForegroundColor DarkGray
    Write-Host "  -Plugins (names, numbers, all, none)" -ForegroundColor DarkGray
}

function Select-InstallItems {
    $defaults = @($script:Catalog | Where-Object { $_.Default } | ForEach-Object { $_.Key })
    $everything = @($script:Catalog | ForEach-Object { $_.Key })

    # A -<Group> spec is a non-interactive answer in its own right: it settles that
    # group's list before anything is drawn, so it composes with -All and
    # -NonInteractive.
    $specs = @{ 'own-skills' = $Skills; 'team' = $Team; 'community' = $Community
                'repo-plugins' = $Plugins }
    foreach ($group in $script:Groups) {
        $spec = $specs[$group.MenuKey]
        if (-not $spec) { continue }
        Expand-GroupSpec $group $spec
        Write-Host ("{0} from {1} '{2}' ({3} of {4})." -f $group.Noun, $group.Flag, $spec,
            (Get-GroupSelectedCount $group), (Get-GroupCatalog $group).Count) -ForegroundColor DarkGray
    }

    $keys = @()
    $interactive = $false
    if ($All) {
        $keys = $everything
        Write-Host "Selecting every item (-All)." -ForegroundColor DarkGray
    } elseif ($Select) {
        $keys = Expand-SelectionSpec $Select
        Write-Host "Selecting from -Select '$Select'." -ForegroundColor DarkGray
    } elseif ($NonInteractive) {
        $keys = $defaults
        Write-Host "Selecting the default set (-NonInteractive)." -ForegroundColor DarkGray
    } elseif ((Test-PickerSupported) -and ($null -ne ($keys = Select-MenuInteractiveSafe))) {
        # Nothing more to do - Select-MenuInteractiveSafe returned a (possibly empty)
        # selection. It returns $null only when the picker itself failed, which drops
        # through to the numbered menu below rather than taking the script down.
        $interactive = $true
    } else {
        $interactive = $true
        Show-InstallMenu
        $answer = "$(Read-Host '  Select [D]')".Trim()
        if ([string]::IsNullOrWhiteSpace($answer)) { $answer = 'D' }
        switch -Regex ($answer) {
            '^(?i)a(ll)?$'       { $keys = $everything; break }
            '^(?i)d(efaults?)?$' { $keys = $defaults;   break }
            '^(?i)n(one)?$'      { $keys = @();         break }
            default              { $keys = Expand-SelectionSpec $answer }
        }
    }

    $script:Selected = @{}
    foreach ($k in $keys) { $script:Selected[$k] = $true }

    # A -<Group> spec is also a statement that you want that row: naming plugins inside
    # a row that is off by default (-Plugins crew) would otherwise print a tidy summary
    # and install nothing. Only when something in the group is actually ticked, so
    # '-Plugins none' still means none - and never after the menu, where unticking the
    # row (or pressing Q) is a decision this must not quietly reverse.
    foreach ($group in $script:Groups) {
        if ($interactive) { break }
        $spec = $specs[$group.MenuKey]
        if (-not $spec) { continue }
        if ((Get-GroupSelectedCount $group) -eq 0) { continue }
        if (-not $script:Selected[$group.MenuKey]) {
            $script:Selected[$group.MenuKey] = $true
            Write-Host ("Also selecting '{0}' - {1} names items inside it." -f $group.MenuKey, $group.Flag) -ForegroundColor DarkGray
        }
    }

    if ($SkipBootstrap) {
        # -SkipBootstrap predates the menu, where it meant "prerequisites and the CLI
        # only". Keep that meaning by intersecting the selection rather than replacing it.
        foreach ($item in $script:Catalog) {
            if ($item.Key -ne 'prereqs' -and $item.Key -ne 'cli') { $script:Selected.Remove($item.Key) }
        }
        Write-Host "Narrowed to prerequisites + CLI (-SkipBootstrap)." -ForegroundColor DarkGray
    }
}

function Show-Selection {
    $chosen = @($script:Catalog | Where-Object { Test-Selected $_.Key })
    Write-Host ""
    if ($chosen.Count -eq 0) {
        Write-Host "  Nothing selected." -ForegroundColor Yellow
        return
    }
    Write-Host "  Will install ($($chosen.Count) item(s)):" -ForegroundColor Cyan
    for ($i = 0; $i -lt $script:Catalog.Count; $i++) {
        if (Test-Selected $script:Catalog[$i].Key) { Write-Host "    - $(Get-MenuLabel $i)" }
    }
    # Spell out any sub-selection: a row that says "3 of 25" is not enough to review.
    foreach ($group in $script:Groups) {
        if (-not (Test-Selected $group.MenuKey)) { continue }
        $catalog = Get-GroupCatalog $group
        $picked = Get-GroupSelectedCount $group
        if ($picked -eq 0) {
            # Only this repo's own row registers its marketplace regardless; for the
            # others registration follows a ticked plugin, so an empty group installs
            # and registers nothing at all.
            if ($group.MenuKey -eq 'own-skills') {
                Write-Warn2 "no $($group.Noun) selected - the marketplace will be registered but nothing installed from it. Re-run with $($group.Flag) all to get them."
            } else {
                Write-Warn2 "no $($group.Noun) selected - this item will install nothing and register no marketplace. Re-run with $($group.Flag) all to get them."
            }
        } elseif ($picked -lt $catalog.Count) {
            Write-Host "      $($group.Noun):" -ForegroundColor Cyan
            foreach ($e in ($catalog | Where-Object { $_.Selected })) { Write-Host "        - $($e.Key)" }
        }
    }
}

function Select-SkillUIGuide {
    # Asked up front with the menu, like every other interactive answer, so the install
    # run itself stays unattended. The guide is printed at the end of the SkillUI step.
    if (-not (Test-Selected 'skillui')) { return $false }
    if ($SkillUIGuide) { return $true }
    if ($NonInteractive -or $All -or $Select) { return $true }
    Write-Host ""
    Write-Host "  SkillUI extracts a design system from any URL into a folder" -ForegroundColor Cyan
    Write-Host "  Claude Code can build against. It ships a short quick start." -ForegroundColor DarkGray
    $answer = "$(Read-Host '  Print the SkillUI quick start after installing? [Y/n]')".Trim()
    return (-not ($answer -match '^(?i)n(o)?$'))
}

# --- notify skill setup -------------------------------------------------------

function Test-SkillSelected {
    # 'notify' is a sub-picker entry, not a top-level menu key, so Test-Selected would
    # always say no. Look it up in the skill catalog instead, and only count it when
    # this repo's marketplace item is itself selected.
    param([string]$Key)
    if (-not (Test-Selected 'own-skills')) { return $false }
    return @($script:SkillCatalog | Where-Object { $_.Key -eq $Key -and $_.Selected }).Count -gt 0
}

function Show-NotifyPrereqs {
    # Printed whether or not they opt into the config scaffold - a headless run should
    # still see what it owes.
    Write-Host "    Prerequisites:"
    Write-Host "      1. Python 3.8+ on PATH. No pip packages - the scripts are stdlib only."
    Write-Host "      2. A Telegram bot: message @BotFather, send /newbot, keep the token."
    Write-Host "      3. Message your new bot once (it cannot open a chat with you first),"
    Write-Host "         then run scripts\telegram_get_chat_id.py to read your chat_id."
    Write-Host "      4. `$env:TELEGRAM_BOT_TOKEN set in your shell - the config file only"
    Write-Host "         names the env var, it never stores the token."
    Write-Host "      5. A config at $HOME\.config\notify\config.json (global) or .\.notify.json"
    Write-Host "         (per project), holding telegram.chat_id."
    Write-Host "      6. Outbound HTTPS to api.telegram.org, and the bot in polling mode -"
    Write-Host "         a webhook on the bot makes getUpdates return 409. One poller per bot."
    Write-Host "    Optional:"
    Write-Host "      - topics mode (one thread per job): a forum supergroup with Topics on,"
    Write-Host "        the bot an admin with Manage Topics, and notifyd.py kept running."
    Write-Host "        Bare free-text answers there also need Group Privacy off in BotFather;"
    Write-Host "        button taps and reply-to work either way."
    Write-Host "      - email: backend smtp needs SMTP_USER/SMTP_PASS (an app password for"
    Write-Host "        Gmail/M365); backend connector needs an M365 or Gmail MCP connector"
    Write-Host "        and only works while a Claude session is driving."
    Write-Host "    Walkthroughs: references\get-bot-token.md, references\windows.md."
}

function Select-NotifySetup {
    # Asked up front with the menu, like every other interactive answer.
    if (-not (Test-SkillSelected 'notify')) { return $false }
    Write-Host ""
    Write-Host "  The notify skill pings your phone or inbox about a job - Telegram" -ForegroundColor Cyan
    Write-Host "  (two-way, so it can ask you a question and wait) or email." -ForegroundColor DarkGray
    Show-NotifyPrereqs
    if ($NotifySetup) { return $true }
    if ($NonInteractive -or $All -or $Select) { return $false }
    $answer = "$(Read-Host "  Scaffold $HOME\.config\notify\config.json now? [y/N]")".Trim()
    return ($answer -match '^(?i)y(es)?$')
}

function Install-NotifyConfig {
    # Deliberately writes no secrets: the config names TELEGRAM_BOT_TOKEN, the user sets
    # it. An existing config is never overwritten. notify.py resolves the global config
    # with os.path.expanduser('~/.config/notify/config.json'), so on Windows that is
    # $HOME\.config\notify - not %APPDATA%.
    $dir = Join-Path $HOME '.config\notify'
    $target = Join-Path $dir 'config.json'

    $py = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
    if ($py) { Write-Ok "python found at $($py.Source)" }
    else { Write-Warn2 "python is not on PATH - notify's scripts need it. Install it and re-run." }

    if (Test-Path $target) {
        Write-Skip "notify config already exists at $target - left as it is"
    } else {
        $src = Get-ChildItem -Path (Join-Path (Get-ClaudeConfigRoot) 'plugins') -Filter 'config.example.json' -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '[\\/]notify[\\/]assets[\\/]' } | Select-Object -First 1
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        if ($src) {
            Copy-Item -Path $src.FullName -Destination $target
        } else {
            # Same key set as the skill's assets/config.example.json, but in 'dm' mode
            # with a placeholder chat_id: 'topics' needs a forum supergroup nobody has yet.
            $starter = @'
{
  "default_channel": "telegram",
  "telegram": { "bot_token_env": "TELEGRAM_BOT_TOKEN", "chat_id": "REPLACE_ME", "mode": "dm" },
  "dispatcher": { "enabled": false, "spool_dir": "~/.local/state/notify/spool", "close_topic_on_complete": true },
  "email": {
    "backend": "smtp", "to": "me@example.com", "from": "claude-jobs@example.com",
    "smtp": { "provider": "gmail", "username_env": "SMTP_USER", "password_env": "SMTP_PASS" }
  },
  "events": { "complete": true, "error": true, "question": true, "info": true },
  "reply": { "enabled": true, "timeout_seconds": 3600 }
}
'@
            Set-Content -Path $target -Value $starter -Encoding utf8
        }
        $script:Summary.Installed++
        Write-Ok "wrote a starter config to $target"
    }

    Write-Host ""
    Write-Host "    Finish notify setup" -ForegroundColor Cyan
    Write-Host "    1. @BotFather -> /newbot -> copy the token, then:"
    Write-Host "         `$env:TELEGRAM_BOT_TOKEN = '123456789:AAE...'      # this session"
    Write-Host "         setx TELEGRAM_BOT_TOKEN '123456789:AAE...'        # future shells"
    Write-Host "    2. Message your bot once, then run telegram_get_chat_id.py and put the"
    Write-Host "       printed chat_id into telegram.chat_id in $target"
    Write-Host "    3. Test it:  python notify.py -e info -m 'hello' --dry-run"
    Write-Host "    Or let Claude do the whole thing for you: run /notify-setup in a session."
}

# --- Claude Code CLI update check --------------------------------------------

function Get-ClaudeLocalVersion {
    # 'claude --version' prints '2.1.226 (Claude Code)', and anything wrapping it (a
    # proxy, a shell function) can print a banner first - take the last line and its
    # leading semver rather than the whole string.
    try {
        $out = @(claude --version 2>$null)
    } catch {
        return $null
    }
    if (-not $out) { return $null }
    $last = "$($out[-1])"
    if ($last -match '(\d+\.\d+\.\d+)') { return $Matches[1] }
    return $null
}

function Test-ClaudeFromNpm {
    # Claude Code also ships a native installer. Reading the version tells us nothing
    # about which one put it there, and 'npm install -g' onto a native install lays a
    # second copy down beside the first. Only npm-owned installs get updated here.
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { return $false }
    try {
        npm ls -g --depth=0 '@anthropic-ai/claude-code' 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Update-ClaudeCli {
    # Runs when claude is already present. Never throws: a failed *update* leaves an
    # installed, working CLI behind, the same reasoning as Install-ClaudePlugin.
    param([string]$Source)
    $installed = Get-ClaudeLocalVersion
    if (-not $installed) {
        Write-Warn2 "could not read the installed Claude Code version - skipping the update check."
        return
    }
    if ($NoUpdate) {
        Write-Skip "Claude Code $installed installed at $Source (-NoUpdate set, not checking for a newer one)"
        return
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Warn2 "npm not found on PATH - cannot check whether Claude Code $installed is current."
        return
    }
    # Native commands write to stderr for ordinary progress noise, and under
    # $ErrorActionPreference = 'Stop' a redirected stderr line becomes a terminating
    # error - so this needs the try/catch, not just 2>$null.
    $latest = $null
    try {
        $latest = "$(npm view '@anthropic-ai/claude-code' version 2>&1 | Select-Object -Last 1)".Trim()
    } catch {
        $latest = $null
    }
    if (-not ($latest -match '^\d+\.\d+\.\d+')) {
        Write-Warn2 "could not reach the npm registry - skipping the Claude Code update check."
        return
    }
    # Equal, or local *ahead* (a prerelease, or a dist-tag that moved back): installing
    # @latest there would be a downgrade.
    $behind = $false
    try { $behind = ([version]$installed -lt [version]$latest) } catch { $behind = ($installed -ne $latest) }
    if (-not $behind) {
        Write-Skip "Claude Code $installed is up to date (npm latest: $latest)"
        return
    }
    if (-not (Test-ClaudeFromNpm)) {
        Write-Warn2 "Claude Code $installed -> $latest available, but this install did not come from npm ($Source) - update it the way you installed it."
        return
    }
    Write-Step "Claude Code $installed -> $latest available"
    npm install -g '@anthropic-ai/claude-code@latest'
    if ($LASTEXITCODE -ne 0) {
        Write-Warn2 "the Claude Code update failed - keeping $installed."
        return
    }
    Sync-SessionEnvironment
    $script:Summary.Updated++
    Write-Ok "Claude Code updated $installed -> $(Get-ClaudeLocalVersion)"
}

# --- Selection ----------------------------------------------------------------

$script:IsElevated = Test-Admin

Select-InstallItems
Show-Selection

$chosenCount = @($script:Catalog | Where-Object { Test-Selected $_.Key }).Count
if ($chosenCount -eq 0) {
    Write-Host "`nNothing to do." -ForegroundColor Yellow
    # Every exit path has to hand the caller's shell back (see the note at the top);
    # this early return would otherwise leave an iex'd session on 'Stop'.
    $ErrorActionPreference = $script:PreviousErrorActionPreference
    return
}

if ($DryRun) {
    Write-Host "`n-DryRun: stopping here. Nothing was installed." -ForegroundColor Yellow
    # Every exit path has to hand the caller's shell back (see the note at the top).
    $ErrorActionPreference = $script:PreviousErrorActionPreference
    return
}

$script:SkillUIGuideChoice = Select-SkillUIGuide
$script:NotifySetupChoice = Select-NotifySetup

if ((Test-Selected 'prereqs') -and -not $script:IsElevated) {
    Write-Step "Not running as Administrator"
    Write-Warn2 "Skipping Chocolatey and Chocolatey packages (git/awscli/nodejs/python)."
    Write-Warn2 "Re-run from an elevated prompt to install those. Every other selected item still runs."
}

# --- 1. Chocolatey + packages -------------------------------------------------
if ((Test-Selected 'prereqs') -and $script:IsElevated) {
    Invoke-Step "Install Chocolatey package manager" {
        if (Get-Command choco -ErrorAction SilentlyContinue) {
            Write-Skip "Chocolatey already installed ($(choco --version))"
            return
        }
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        Sync-SessionEnvironment
        $script:Summary.Installed++
        Write-Ok "Chocolatey installed"
    }

    $chocoPackages = @('git', 'awscli', 'nodejs', 'python')
    $packageProbe = @{ git = 'git'; awscli = 'aws'; nodejs = 'npm'; python = 'python' }
    foreach ($pkg in $chocoPackages) {
        $probe = $packageProbe[$pkg]
        Invoke-Step "Chocolatey package: $pkg" {
            $state = Test-ChocoPackageInstalled -Package $pkg -Probe $probe
            if ($state.Present) {
                Write-Skip "$pkg already installed - $($state.How)"
                return
            }
            choco install $pkg -y --no-progress
            # Refresh before the next package so this session picks up the new PATH
            # entries and vars - git especially, since later steps shell out to it.
            Sync-SessionEnvironment
            Get-ChocoInstalled -Refresh | Out-Null
            if ($probe -and -not (Get-Command $probe -ErrorAction SilentlyContinue)) {
                Write-Warn2 "$pkg installed but '$probe' is still not resolvable in this session - you may need a new shell."
            } else {
                Write-Ok "$pkg installed ('$probe' resolved)"
            }
            $script:Summary.Installed++
        }
    }
}

# --- 2. Claude Code CLI ------------------------------------------------------
if (Test-Selected 'cli') {
    Invoke-Step "Install Claude Code CLI" {
        Sync-SessionEnvironment
        $existing = Get-Command claude -ErrorAction SilentlyContinue
        if ($existing) {
            Update-ClaudeCli -Source $existing.Source
            return
        }
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw "npm not found on PATH after installing nodejs - open a new shell and re-run this script."
        }
        npm install -g @anthropic-ai/claude-code
        Sync-SessionEnvironment
        $script:Summary.Installed++
    }

    Invoke-Step "Export Claude Code CLI path to PATH" {
        $npmPrefix = (npm config get prefix).Trim()
        if (-not $npmPrefix) {
            throw "Could not resolve npm global prefix."
        }
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        if ($userPath -notlike "*$npmPrefix*") {
            $newPath = if ([string]::IsNullOrEmpty($userPath)) { $npmPrefix } else { "$userPath;$npmPrefix" }
            [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
            Write-Ok "Added '$npmPrefix' to the User PATH (persists across sessions)."
        } else {
            Write-Skip "'$npmPrefix' is already on the User PATH."
        }
        [Environment]::SetEnvironmentVariable('CLAUDE_CODE_HOME', $npmPrefix, 'User')
        Sync-SessionEnvironment

        $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
        if ($claudeCmd) {
            Write-Ok "claude resolved at $($claudeCmd.Source)"
        } else {
            Write-Warn2 "claude not found on PATH in this session - open a new shell for the PATH change to take effect."
        }
    }
}

# Everything from here to the MCP servers needs the claude CLI on PATH.
$claudeItems = @('own-skills', 'team', 'find-skills', 'community', 'claude-code-setup', 'supabase', 'repo-plugins')
$needsClaude = @($claudeItems | Where-Object { Test-Selected $_ }).Count -gt 0

if ($needsClaude -and -not (Test-ClaudeAvailable)) {
    Write-Step "Skipping marketplace/plugin items"
    Write-Warn2 "claude is not on PATH in this session - open a new shell and re-run to install them."
    foreach ($key in $claudeItems) { $script:Selected.Remove($key) }
}

# --- 3. This repo's own marketplace and skills -------------------------------
if (Test-Selected 'own-skills') {
    # Registered up front rather than left to Install-Group, so ticking zero skills
    # still leaves the marketplace available to browse with /plugin - which is what the
    # warning below promises. Install-Group is told about it so it is not added twice.
    Invoke-Step "Add this repo as a Claude Code marketplace" {
        Add-ClaudeMarketplace -Source 'mbadali25/useful-claude-add-ons' -Name 'useful-claude-add-ons'
    }

    # The catalog itself lives in $script:SkillCatalog next to the menu; only the ticked
    # ones get installed, so -Skills and the sub-picker both land here.
    if ((Get-SelectedSkillCount) -eq 0) {
        Write-Warn2 "no skills selected from this repo - marketplace registered, nothing installed. Re-run with -Skills all to get them."
    }
    Install-Group (Get-Group 'own-skills') -AlreadyRegistered 'useful-claude-add-ons'

    # notify is the one skill with machine-level setup (a config file and a bot token),
    # so it gets a post-install step when the user asked for it up front.
    if ($script:NotifySetupChoice -and (Test-SkillSelected 'notify')) {
        Invoke-Step "Set up the notify skill" { Install-NotifyConfig }
    }
}

# --- 4. Team marketplaces and plugins ----------------------------------------
# The catalog is $script:TeamCatalog next to the menu, so Right on the row (or -Team)
# narrows it. Each entry names its own marketplace, and only the ones behind a ticked
# plugin get registered; Add-ClaudeMarketplace is a no-op when one is already present.
if (Test-Selected 'team') {
    $group = Get-Group 'team'
    if ((Get-GroupSelectedCount $group) -eq 0) {
        Write-Warn2 "no team plugins selected - nothing installed for this item, and no marketplace registered."
    }
    Install-Group $group
}

# --- 5. find-skills ----------------------------------------------------------
if (Test-Selected 'find-skills') {
    Invoke-Step "Skill: find-skills (vercel-labs/skills)" {
        # find-skills is installed by the 'skills' CLI as a user-level skill, not as a
        # Claude Code plugin, so it is detected on disk rather than via 'claude plugin list'.
        $findSkillsDir = Join-Path (Get-ClaudeSkillsDir) 'find-skills'
        $present = Test-UserSkillInstalled 'find-skills'
        if ($present -and $NoUpdate) {
            Write-Skip "find-skills already installed at $findSkillsDir (-NoUpdate set)"
            return
        }
        npx -y skills add vercel-labs/skills --skill find-skills --agent claude-code
        if (-not (Test-UserSkillInstalled 'find-skills')) {
            throw "the installer finished but '$findSkillsDir\SKILL.md' was not created - see the output above."
        }
        if ($present) {
            Write-Ok "find-skills re-installed (now current)"
        } else {
            $script:Summary.Installed++
            Write-Ok "installed find-skills to $findSkillsDir"
        }
    }
}

# --- 6. Community marketplaces and plugins -----------------------------------
# The catalog is $script:CommunityCatalog next to the menu, so Right on the row (or
# -Community) narrows it. Source repo -> marketplace name is *not* mechanical:
# fcakyon/claude-codex-settings publishes itself as 'claude-settings'. The last field
# of each Spec is the "name" in that repo's own .claude-plugin/marketplace.json, which
# is what 'plugin@marketplace' must match.
if (Test-Selected 'community') {
    $group = Get-Group 'community'
    if ((Get-GroupSelectedCount $group) -eq 0) {
        Write-Warn2 "no community plugins selected - nothing installed for this item, and no marketplace registered."
    }
    Install-Group $group
}

# --- 7. claude-code-setup ----------------------------------------------------
# Ships inside anthropics/claude-plugins-official, which the community item also
# registers - Add-ClaudeMarketplace is a no-op when it is already there, so this
# item works whether or not item 6 was selected.
if (Test-Selected 'claude-code-setup') {
    Invoke-Step "Marketplace: anthropics/claude-plugins-official" {
        Add-ClaudeMarketplace -Source 'anthropics/claude-plugins-official' -Name 'claude-plugins-official'
    }
    Invoke-Step "Plugin: claude-code-setup@claude-plugins-official" {
        Install-ClaudePlugin 'claude-code-setup@claude-plugins-official'
    }
}

# --- 8. task-observer --------------------------------------------------------
if (Test-Selected 'task-observer') {
    Invoke-Step "Skill: task-observer (rebelytics/one-skill-to-rule-them-all)" {
        # This repo publishes no marketplace.json, so there is nothing for
        # 'claude plugin install' to consume - it is a plain skill directory.
        # SKILL.md and references/ are the whole skill; the README, USER-GUIDE and
        # two 1.5 MB PNGs in the repo are not part of it and are deliberately not copied.
        $dest = Join-Path (Get-ClaudeSkillsDir) 'task-observer'
        $present = Test-UserSkillInstalled 'task-observer'
        if ($present -and $NoUpdate) {
            Write-Skip "task-observer already installed at $dest (-NoUpdate set)"
            return
        }
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            throw "git not found on PATH - select the prerequisites item (or install git) and re-run."
        }
        $tmp = Join-Path ([IO.Path]::GetTempPath()) ("task-observer-" + [guid]::NewGuid().ToString('N'))
        try {
            git clone --depth 1 --quiet https://github.com/rebelytics/one-skill-to-rule-them-all.git $tmp
            if (-not (Test-Path (Join-Path $tmp 'SKILL.md'))) {
                throw "clone succeeded but SKILL.md was not found in $tmp - the upstream layout may have changed."
            }
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
            Copy-Item -Path (Join-Path $tmp 'SKILL.md') -Destination $dest -Force
            Copy-Item -Path (Join-Path $tmp 'references') -Destination $dest -Recurse -Force
        } finally {
            if (Test-Path $tmp) { Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue }
        }
        if ($present) {
            Write-Ok "task-observer re-installed (now current) at $dest"
        } else {
            $script:Summary.Installed++
            Write-Ok "installed task-observer to $dest"
        }
    }
}

# --- 9-12. Optional MCP servers ----------------------------------------------
if (Test-Selected 'aws-mcp') {
    Invoke-Step "Install AWS MCP server" {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue) -and -not (Get-Command uvx -ErrorAction SilentlyContinue)) {
            if (-not (Get-Command pip -ErrorAction SilentlyContinue)) {
                throw "pip not found - install Python first (choco install python), then re-run to install uv."
            }
            pip install --user uv
            Sync-SessionEnvironment
        }
        if (-not (Test-ClaudeAvailable)) {
            throw "claude not found on PATH in this session - open a new shell and re-run this script."
        }
        Add-McpServer -Name 'aws-api' -CommandArgs @('uvx', 'awslabs.aws-api-mcp-server@latest') `
            -Note "Make sure AWS credentials are configured (aws configure)."
    }
}

if (Test-Selected 'azure-mcp') {
    Invoke-Step "Install Azure MCP server" {
        if (-not (Test-ClaudeAvailable)) {
            throw "claude not found on PATH in this session - open a new shell and re-run this script."
        }
        Add-McpServer -Name 'azure' -CommandArgs @('npx', '-y', '@azure/mcp@latest', 'server', 'start') `
            -Note "Make sure you have run 'az login' before using it."
    }
}

if (Test-Selected 'playwright-mcp') {
    Invoke-Step "Install Playwright MCP server" {
        Add-McpServer -Name 'playwright' `
            -CommandArgs @('npx', '@playwright/mcp@latest') `
            -Note "Playwright downloads its browsers on first use; 'npx playwright install' does it ahead of time."
    }
}

if (Test-Selected 'obsidian-mcp') {
    Invoke-Step "Register the Obsidian vault server MCP endpoint" {
        # Not a launched command: the endpoint is the obsidian-local-rest-api
        # plugin already running inside the vault-server container. It listens on
        # the SERVER's loopback, so the URL is a local port forwarded by SSH.
        # The API key is per-deployment, so it cannot be baked in here.
        if (-not $ObsidianMcpKey) {
            Write-Skip "Obsidian MCP: no -ObsidianMcpKey given"
            Write-Host "        Get the key from the vault server:"
            Write-Host "          sudo ./obsidian-vault-server.sh apikey"
            Write-Host "        Open the tunnel, then re-run with the key:"
            Write-Host "          ssh -N -L 27123:127.0.0.1:27123 <user>@<server>"
            Write-Host "          .\install-prerequisites.ps1 -Select obsidian-mcp -ObsidianMcpKey <key>"
            Write-Host "        See the obsidian-vault-server skill for the whole setup."
            return
        }
        Add-McpServer -Name 'obsidian-server' -Url $ObsidianMcpUrl `
            -Headers @{ Authorization = "Bearer $ObsidianMcpKey" } `
            -Note "Requires an SSH tunnel to the vault server: ssh -N -L 27123:127.0.0.1:27123 <user>@<server>"
    }
}

# --- 13. Supabase ------------------------------------------------------------ ---
# Ships inside anthropics/claude-plugins-official, the same marketplace items 6 and 7
# register - Add-ClaudeMarketplace is a no-op when it is already there, so this item
# stands on its own. Install-ClaudePlugin does the "already installed?" check.
if (Test-Selected 'supabase') {
    Invoke-Step "Marketplace: anthropics/claude-plugins-official" {
        Add-ClaudeMarketplace -Source 'anthropics/claude-plugins-official' -Name 'claude-plugins-official'
    }
    Invoke-Step "Plugin: supabase@claude-plugins-official" {
        Install-ClaudePlugin 'supabase@claude-plugins-official'
    }
}

# --- 14. Context7 ------------------------------------------------------------ ---
if (Test-Selected 'context7') {
    Invoke-Step "Configure Context7 (npx ctx7 setup)" {
        # 'ctx7 setup' writes the Context7 MCP/skill config for whichever agents it
        # finds. It is interactive, so there is nothing to do when the console has been
        # redirected - print the command instead of hanging on a prompt nobody sees.
        if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
            throw "npx not found on PATH - select the prerequisites item (or install Node.js) and re-run."
        }
        if ([Console]::IsInputRedirected) {
            Write-Warn2 "no interactive console for 'ctx7 setup' - run 'npx ctx7 setup' by hand once this finishes."
            return
        }
        npx -y ctx7@latest setup
        if ($LASTEXITCODE -ne 0) { throw "'npx ctx7 setup' failed - see the output above." }
        $script:Summary.Installed++
        Write-Ok "Context7 configured. Free tier works without a key; higher limits: https://context7.com"
    }
}

# --- 15. Playwright CLI ------------------------------------------------------ ---
if (Test-Selected 'playwright-cli') {
    Invoke-Step "Install Playwright CLI (@playwright/cli)" {
        # Detection is on the binary the package provides ('playwright-cli'), which is
        # what a user actually cares about - it can also arrive via another manager.
        $existing = Get-Command playwright-cli -ErrorAction SilentlyContinue
        if ($existing -and $NoUpdate) {
            Write-Skip "playwright-cli already installed at $($existing.Source) (-NoUpdate set)"
            return
        }
        if ($existing) {
            Write-Ok "playwright-cli already installed - reinstalling @latest to pick up updates"
        }
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw "npm not found on PATH - select the prerequisites item (or install Node.js) and re-run."
        }
        npm install -g '@playwright/cli@latest'
        if ($LASTEXITCODE -ne 0) { throw "'npm install -g @playwright/cli@latest' failed - see the output above." }
        Sync-SessionEnvironment
        $cmd = Get-Command playwright-cli -ErrorAction SilentlyContinue
        if (-not $cmd) {
            throw "@playwright/cli installed but 'playwright-cli' is not resolvable in this session - open a new shell and try again."
        }
        $script:Summary.Installed++
        Write-Ok "playwright-cli installed at $($cmd.Source)"
    }
}

# --- 16. SkillUI ------------------------------------------------------------- ---
function Show-SkillUIQuickStart {
    Write-Host ""
    Write-Host "    SkillUI quick start  https://github.com/amaancoderx/npxskillui" -ForegroundColor Cyan
    Write-Host "    1. Extract a design system from any URL:" -ForegroundColor Gray
    Write-Host "         skillui --url https://notion.so" -ForegroundColor Gray
    Write-Host "    2. Open the output folder in Claude Code:" -ForegroundColor Gray
    Write-Host "         cd notion-design; claude" -ForegroundColor Gray
    Write-Host "    3. Ask for what you want built:" -ForegroundColor Gray
    Write-Host '         "Build me a landing page that matches this design system"' -ForegroundColor Gray
    Write-Host "    Claude reads the generated CLAUDE.md and SKILL.md on its own - no wiring up." -ForegroundColor Gray
    Write-Host "    Modes: --ultra (full extraction)   --dir <path>   --repo <url>" -ForegroundColor Gray
}

if (Test-Selected 'skillui') {
    Invoke-Step "Install SkillUI (+ Playwright and Chromium)" {
        # Three parts: the CLI, Playwright itself, and the Chromium build Playwright
        # drives. Playwright goes in globally rather than into the current directory -
        # this script can be run from anywhere, and 'npm install playwright' would
        # leave a node_modules tree wherever that happened to be.
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw "npm not found on PATH - select the prerequisites item (or install Node.js) and re-run."
        }
        $existing = Get-Command skillui -ErrorAction SilentlyContinue
        if ($existing -and $NoUpdate) {
            Write-Skip "skillui already installed at $($existing.Source) (-NoUpdate set)"
        } else {
            npm install -g skillui
            if ($LASTEXITCODE -ne 0) { throw "'npm install -g skillui' failed - see the output above." }
            $script:Summary.Installed++
            Write-Ok "skillui installed"
        }
        npm install -g playwright
        if ($LASTEXITCODE -ne 0) { Write-Warn2 "'npm install -g playwright' failed - skillui needs it to capture screenshots." }
        # Downloads the browser binary itself; skipping it leaves skillui able to start
        # and unable to render anything.
        npx -y playwright install chromium
        if ($LASTEXITCODE -ne 0) { Write-Warn2 "'npx playwright install chromium' failed - run it by hand before using skillui." }
        Sync-SessionEnvironment
        $cmd = Get-Command skillui -ErrorAction SilentlyContinue
        if (-not $cmd) {
            throw "skillui installed but is not resolvable in this session - open a new shell and try again."
        }
        Write-Ok "skillui ready at $($cmd.Source)"
        if ($script:SkillUIGuideChoice) { Show-SkillUIQuickStart }
    }
}

# --- 17. Strix --------------------------------------------------------------- ---
function Show-StrixNextSteps {
    Write-Host ""
    Write-Host "    Strix needs two more things before its first scan:" -ForegroundColor Yellow
    Write-Host "    1. Docker running - the first scan pulls the sandbox image." -ForegroundColor Gray
    Write-Host "    2. An LLM API key, set for your user:" -ForegroundColor Gray
    Write-Host '         setx STRIX_LLM "openai/gpt-5.4"     # or another supported provider' -ForegroundColor Gray
    Write-Host '         setx LLM_API_KEY "your-api-key"' -ForegroundColor Gray
    Write-Host "    Then: strix --target ./app-directory        Results: strix_runs/<run-name>" -ForegroundColor Gray
    Write-Host "    Providers and options: https://docs.strix.ai" -ForegroundColor Gray
}

if (Test-Selected 'strix') {
    Invoke-Step "Install Strix AI pentesting CLI" {
        # Upstream ships a POSIX shell installer rather than an npm/pip package
        # (https://github.com/usestrix/strix), so on Windows it has to run through a
        # bash: WSL first, then Git Bash, which the prerequisites item installs.
        if (Get-Command strix -ErrorAction SilentlyContinue) {
            if ($NoUpdate) {
                Write-Skip "strix already installed (-NoUpdate set)"
                Show-StrixNextSteps
                return
            }
            Write-Ok "strix already installed - running the installer again to pick up updates"
        }
        $installCmd = 'curl -sSL https://strix.ai/install | bash'
        $ran = $false
        if (Get-Command wsl -ErrorAction SilentlyContinue) {
            wsl -- bash -lc $installCmd
            if ($LASTEXITCODE -eq 0) {
                $ran = $true
                Write-Ok "strix installed inside WSL - run it from your WSL shell ('wsl strix --help')."
                $script:Summary.Installed++
            } else {
                Write-Warn2 "the Strix installer failed under WSL - trying Git Bash next."
            }
        }
        if (-not $ran) {
            $bash = Get-Command bash -ErrorAction SilentlyContinue
            if ($bash) {
                & $bash.Source -lc $installCmd
                if ($LASTEXITCODE -eq 0) {
                    $ran = $true
                    $script:Summary.Installed++
                    Write-Ok "strix installed via $($bash.Source)"
                }
            }
        }
        if (-not $ran) {
            Write-Warn2 "no WSL or bash found to run the Strix installer. Install WSL (wsl --install) or Git for Windows, then run: $installCmd"
        }
        Show-StrixNextSteps
    }
}

# --- 18. Obsidian + claude-obsidian ------------------------------------------ ---
function Show-ObsidianNextSteps {
    param([string]$VaultRoot)
    Write-Host ""
    Write-Host "    Obsidian is installed, but the vault is a separate step:" -ForegroundColor Yellow
    Write-Host "      claude-obsidian-setup\setup-claude-obsidian.ps1 -Apply -RepoRoot $VaultRoot" -ForegroundColor Gray
    Write-Host "    That creates and verifies the vault. Run it without -Apply first to preview." -ForegroundColor Gray
    Write-Host "    On Windows the vault is written through WSL - native Windows is read-only" -ForegroundColor Gray
    Write-Host "    for claude-obsidian, which the setup script detects and handles." -ForegroundColor Gray
    Write-Host "    Details: claude-obsidian-setup\README.md" -ForegroundColor Gray
}

if (Test-Selected 'obsidian') {
    Invoke-Step "Install Obsidian desktop + claude-obsidian and obsidian-skills plugins" {
        # Obsidian ships no npm/pip package, so this is a desktop installer:
        # Chocolatey first (the prerequisites item already installs it), then
        # winget for machines that have winget but not choco.
        $obsExe = @("$env:LOCALAPPDATA\Programs\Obsidian\Obsidian.exe",
                    "$env:ProgramFiles\Obsidian\Obsidian.exe") |
                  Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($obsExe) {
            Write-Skip "Obsidian already installed ($obsExe)"
        } elseif (Test-ChocoPackageInstalled 'obsidian') {
            Write-Skip "Obsidian already installed (Chocolatey package present)"
        } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
            if (-not (Test-Admin)) {
                Write-Warn2 "Obsidian needs an elevated prompt to install via Chocolatey - skipping the app, continuing with the plugins."
            } else {
                choco install obsidian -y --no-progress
                if ($LASTEXITCODE -ne 0) { throw "choco install obsidian failed with exit code $LASTEXITCODE - see the output above." }
                $script:Summary.Installed++
                Write-Ok "Obsidian installed via Chocolatey"
            }
        } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install --id Obsidian.Obsidian -e --accept-source-agreements --accept-package-agreements
            if ($LASTEXITCODE -eq 0) {
                $script:Summary.Installed++
                Write-Ok "Obsidian installed via winget"
            } else {
                Write-Warn2 "winget install Obsidian.Obsidian failed (exit $LASTEXITCODE) - install it from https://obsidian.md"
            }
        } else {
            Write-Warn2 "no Chocolatey or winget found - install Obsidian from https://obsidian.md, then re-run."
        }

        if (Test-ClaudeAvailable) {
            # The vault engine, and Obsidian's own upstream syntax skills
            # (Markdown, Bases, JSON Canvas, the Obsidian CLI, Defuddle).
            Add-ClaudeMarketplace 'AgriciDaniel/claude-obsidian'
            Install-ClaudePlugin  'claude-obsidian@agricidaniel-claude-obsidian'
            Add-ClaudeMarketplace 'kepano/obsidian-skills'
            Install-ClaudePlugin  'obsidian@obsidian-skills'
        } else {
            Write-Warn2 "'claude' is not on PATH yet - re-run with item 2 selected, or open a new shell and re-run this item."
        }

        Show-ObsidianNextSteps $ObsidianRepoRoot
    }
}

# --- 19. This repo's own plugins --------------------------------------------- ---
# Same marketplace as item 3, so Add-ClaudeMarketplace is a no-op when item 3 already
# ran - this item stands on its own. Install-ClaudePlugin does the "already installed?"
# check.
# crew vendors its own narrowly-triggered find-skills copy (Task 12 narrowed its
# description so it stops competing with crew's other skills). A *global* find-skills
# install (menu item 5, or a prior 'npx skills add') is a second, separate copy with the
# old broad trigger, and the two can both fire on the same prompt. Detect and explain it;
# never delete it - it is the user's own global Claude Code config, not this repo's.
function Test-GlobalFindSkillsCollision {
    $dir = Join-Path (Get-ClaudeSkillsDir) 'find-skills'
    if (-not (Test-UserSkillInstalled 'find-skills')) { return }
    Write-Warn2 "global find-skills skill found at $dir"
    Write-Host "      This is vercel-labs/skills' find-skills (installed by menu item 5, or by"
    Write-Host "      'npx skills add vercel-labs/skills --skill find-skills' directly) - a"
    Write-Host "      separate, global copy from the one crew vendors internally. Two active"
    Write-Host "      copies can both trigger on the same prompt."
    Write-Host "      This script will not remove it for you. To remove the global copy yourself:"
    Write-Host "        Remove-Item -Recurse -Force '$dir'"
}

function Show-CrewNextSteps {
    Write-Host ""
    Write-Step "crew: next steps"
    Write-Host "  Unlike a skill, crew registers hooks that run on their own:"
    Write-Host "    - PreToolUse on Bash/PowerShell blocks terraform apply/destroy, destructive"
    Write-Host "      DDL, force push, hard reset, and commands that would print a secret."
    Write-Host "    - Stop runs the checks your changed paths map to and fails the turn on red."
    Write-Host "  Set it up per repository before relying on either:"
    Write-Host "    cd <your repo>; claude"
    Write-Host "    /crew:init         # guided, resumable setup"
    Write-Host "    /crew:onboard      # build the code map"
    Write-Host "    /crew:verify       # build the change-to-check map the Stop gate needs"
    Write-Host "  Full guide: https://github.com/mbadali25/useful-claude-add-ons/blob/main/plugin/crew/README.md"
}
if (Test-Selected 'repo-plugins') {
    Invoke-Step "Add this repo as a Claude Code marketplace" {
        Add-ClaudeMarketplace -Source 'mbadali25/useful-claude-add-ons' -Name 'useful-claude-add-ons'
    }

    # The catalog lives in $script:PluginCatalog next to the menu; Right on the row
    # (or -Plugins) narrows it, the same as every other multi-item row.
    Install-Group (Get-Group 'repo-plugins') -AlreadyRegistered 'useful-claude-add-ons'

    # Only worth printing when crew is actually one of the ones installed.
    if (Test-GroupEntrySelected 'repo-plugins' 'crew') {
        Test-GlobalFindSkillsCollision
        Show-CrewNextSteps
    }
}

# --- 20. graphify -------------------------------------------------------------- ---
# graphifyy on PyPI (double-y) provides two executables: 'graphify' and
# 'graphify-mcp'. Other 'graphify*' packages on PyPI are unaffiliated - installing the
# wrong one fails silently, so the double-y package is named explicitly below and in
# every message this step prints.
function Show-GraphifyNextSteps {
    Write-Host ""
    Write-Step "graphify: next steps"
    Write-Host "  Build the code graph for a repo (--code-only is required whenever the repo"
    Write-Host "  has any docs in it - without it graphify errors instead of skipping them):"
    Write-Host "    cd <your repo>; graphify . --no-viz --code-only"
    Write-Host "  graphify-mcp is installed alongside it if you want to wire it up as an MCP server."
}

if (Test-Selected 'graphify') {
    Invoke-Step "Install graphify (uv tool install graphifyy; registers --project)" {
        $existing = Get-Command graphify -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Skip "graphify already installed ($($existing.Source))"
        } else {
            if (-not (Get-Command uv -ErrorAction SilentlyContinue) -and -not (Get-Command uvx -ErrorAction SilentlyContinue)) {
                if (-not (Get-Command pip -ErrorAction SilentlyContinue)) {
                    throw "pip not found - install Python first (choco install python), then re-run to install graphify."
                }
                pip install --user uv
                Sync-SessionEnvironment
            }
            if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                throw "uv still not found after attempting to install it - install it manually (https://docs.astral.sh/uv) and re-run."
            }
            uv tool install graphifyy
            if ($LASTEXITCODE -ne 0) { throw "'uv tool install graphifyy' failed - see the output above." }
            Sync-SessionEnvironment
            $cmd = Get-Command graphify -ErrorAction SilentlyContinue
            if (-not $cmd) {
                throw "graphify (from graphifyy) installed but not resolvable in this session - uv tool installs land under your user profile; open a new shell and re-run."
            }
            $script:Summary.Installed++
            Write-Ok "graphify installed at $($cmd.Source) (graphify-mcp alongside it)"
        }

        # Registered per-repo, never globally: a global graphify registration is the
        # same broad-global-skill collision Task 12 fixed by narrowing find-skills, above.
        graphify install --project
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "registered graphify for this repo (--project)"
        } else {
            Write-Warn2 "'graphify install --project' failed - run it by hand from inside the target repo."
        }
        Show-GraphifyNextSteps
    }
}

# --- Summary -----------------------------------------------------------------
Write-Host ""
Write-Host ("Installed: {0}   Updated: {1}   Already present: {2}" -f `
    $script:Summary.Installed, $script:Summary.Updated, $script:Summary.Skipped) -ForegroundColor Cyan
if ($script:FailedSteps.Count -eq 0) {
    Write-Host "All steps completed. Open a new shell if 'claude' is not yet recognized." -ForegroundColor Green
} else {
    Write-Host "Completed with $($script:FailedSteps.Count) failed step(s):" -ForegroundColor Yellow
    $script:FailedSteps | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "Re-run this script after resolving the above; earlier successful steps are safe to repeat." -ForegroundColor Yellow
}

# Hand the caller's shell back the way we found it (see the note at the top).
$ErrorActionPreference = $script:PreviousErrorActionPreference
