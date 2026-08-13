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
three of them instead of all nineteen. Hosts that cannot read a key press - ISE, a
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
                        -Select 'strix,claude-mem')
    -Skills 'a,b'       install only these of this repo's skills, no prompt
                        (-Skills 'all' | 'none' also work; implies the repo item)
    -TeamPlugins 'a,b'  install only these team plugins, no sub-picker
                        ('all' | 'none' | numbers like '1,3' also work)
    -CommunityPlugins 'a,b'
                        install only these community plugins, no sub-picker
    -NonInteractive     select the default set, no prompt (CI/unattended)
    -SkillUIGuide       print the SkillUI quick start after installing it, no prompt
    -NotifySetup        scaffold the notify config after installing it, no prompt
    -NoUpdate           never update an already-installed plugin, only report it
    -SkipBootstrap      narrow the selection to prerequisites + the Claude Code CLI
    -InstallScope       scope for marketplace/plugin installs: user (default), project, local
                        (accepts -PluginHubScope as an alias for backward compatibility)
#>

[CmdletBinding()]
param(
    [switch]$SkipBootstrap,   # narrow the selection to prerequisites + CLI
    [switch]$NonInteractive,  # take the default selection, no menu
    [switch]$NoUpdate,        # don't update already-installed plugins
    [switch]$All,             # select every menu item, no menu
    [string]$Select,          # explicit selection, no menu: '1,3,7-9' or 'strix,supabase'
    [string]$Skills,          # explicit skill subset, no sub-picker: 'cloudflare,drata' | 'all' | 'none'
    [string]$TeamPlugins,     # explicit team-plugin subset, no sub-picker
    [string]$CommunityPlugins,# explicit community-plugin subset, no sub-picker
    [switch]$SkillUIGuide,    # answer the SkillUI quick-start prompt up front
    [switch]$NotifySetup,     # answer the notify setup prompt up front
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

function Enable-ClaudePlugin {
    # $Spec is 'name@marketplace'. Installing a plugin and having it actually load are
    # two different things: a plugin switched off in settings.json is installed, at the
    # right scope, and completely inert - none of its skills or hooks are visible.
    # Best-effort by design; the plugin is installed either way, so this warns rather
    # than throwing. Tries the fully qualified spec first because the bare name is
    # ambiguous when two marketplaces publish it.
    param([string]$Spec)
    $name = $Spec.Split('@')[0]
    $existing = (Get-ClaudePlugins)[$name]
    if ($existing -and $existing.Enabled) { return }
    foreach ($target in @($Spec, $name)) {
        claude plugin enable $target --scope $InstallScope 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Get-ClaudePlugins -Refresh | Out-Null
            Write-Ok "enabled plugin '$name' (--scope $InstallScope)"
            return
        }
    }
    Write-Warn2 "plugin '$name' is installed but disabled and 'claude plugin enable' failed - run '/plugin' and enable it by hand."
}

function Install-ClaudePlugin {
    # $Spec is 'name@marketplace'. Detection is on the bare name, so a plugin already
    # installed from a *different* marketplace counts as present and is not duplicated.
    param([string]$Spec)
    $name = $Spec.Split('@')[0]
    $existing = (Get-ClaudePlugins)[$name]
    if ($existing) {
        if ($NoUpdate) {
            Write-Skip "plugin '$name' already installed ($($existing.Id), version $($existing.Version))"
            Enable-ClaudePlugin $Spec
            return
        }
        $before = $existing.Version
        claude plugin update $name | Out-Null
        # A failed *update* is not fatal - the plugin is already installed and usable,
        # and 'claude plugin update' legitimately fails when the marketplace it came
        # from has moved on. Report it and carry on; a failed *install* still throws.
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 "'claude plugin update $name' failed - keeping the installed version."
            Enable-ClaudePlugin $Spec
            return
        }
        $after = (Get-ClaudePlugins -Refresh)[$name].Version
        if ($after -ne $before) {
            $script:Summary.Updated++
            Write-Ok "plugin '$name' updated $before -> $after"
        } else {
            Write-Skip "plugin '$name' already current (version $after)"
        }
        Enable-ClaudePlugin $Spec
        return
    }
    claude plugin install $Spec --scope $InstallScope
    if ($LASTEXITCODE -ne 0) { throw "'claude plugin install $Spec' failed - see the output above." }
    Get-ClaudePlugins -Refresh | Out-Null
    $script:Summary.Installed++
    Write-Ok "installed plugin '$Spec'"
    Enable-ClaudePlugin $Spec
}

# --- Install catalog and menu -------------------------------------------------
# One ordered entry per selectable item. 'Key' is what the rest of the script tests
# with Test-Selected; 'Default' is what [D] (and -NonInteractive) picks, chosen to
# match the prompt defaults this script used before it had a menu. 'Sub' names the
# sub-catalog a row expands into: those rows open a second picker on Right, and their
# Name is a -f template taking the ticked count and the catalog size, so the row shows
# a live count rather than a fixed claim.
$script:Catalog = @(
    [pscustomobject]@{ Key = 'prereqs';           Default = $true;  Name = 'Prerequisites: Chocolatey + git, awscli, nodejs, python (needs Administrator)' }
    [pscustomobject]@{ Key = 'cli';               Default = $true;  Name = 'Claude Code CLI (@anthropic-ai/claude-code) + PATH export + update check' }
    [pscustomobject]@{ Key = 'own-skills';        Default = $true;  Sub = 'SKILL';     Name = "This repo's marketplace + {0} of {1} skills  >" }
    [pscustomobject]@{ Key = 'team';              Default = $true;  Sub = 'TEAM';      Name = 'Team plugins - {0} of {1}: superpowers, frontend-design, excalidraw-generator  >' }
    [pscustomobject]@{ Key = 'find-skills';       Default = $true;  Name = 'find-skills skill (vercel-labs/skills)' }
    [pscustomobject]@{ Key = 'community';         Default = $true;  Sub = 'COMMUNITY'; Name = 'Community marketplaces + plugins - {0} of {1}: adhd-output-style, azure-tools, ...  >' }
    [pscustomobject]@{ Key = 'claude-code-setup'; Default = $true;  Name = 'claude-code-setup plugin (anthropics/claude-plugins-official)' }
    [pscustomobject]@{ Key = 'task-observer';     Default = $true;  Name = 'task-observer skill (rebelytics/one-skill-to-rule-them-all)' }
    [pscustomobject]@{ Key = 'claude-mem';        Default = $true;  Name = 'claude-mem memory plugin + CLAUDE_MEM_WORKER_PORT in settings.json' }
    [pscustomobject]@{ Key = 'voltagent';         Default = $true;  Name = 'VoltAgent subagents (10 plugins, 154 agents)' }
    [pscustomobject]@{ Key = 'aws-mcp';           Default = $false; Name = 'MCP server: AWS (awslabs.aws-api-mcp-server)' }
    [pscustomobject]@{ Key = 'azure-mcp';         Default = $false; Name = 'MCP server: Azure (@azure/mcp)' }
    [pscustomobject]@{ Key = 'playwright-mcp';    Default = $false; Name = 'MCP server: Playwright (@playwright/mcp)' }
    [pscustomobject]@{ Key = 'supabase';          Default = $false; Name = 'Supabase plugin (supabase@claude-plugins-official)' }
    [pscustomobject]@{ Key = 'context7';          Default = $false; Name = 'Context7 up-to-date library docs (npx ctx7 setup)' }
    [pscustomobject]@{ Key = 'playwright-cli';    Default = $false; Name = 'Playwright CLI (@playwright/cli) - browser automation from the shell' }
    [pscustomobject]@{ Key = 'skillui';           Default = $false; Name = 'SkillUI (npm) + Playwright/Chromium - extract a design system from a URL' }
    [pscustomobject]@{ Key = 'strix';             Default = $false; Name = 'Strix AI pentesting CLI (needs Docker + an LLM API key)' }
)

$script:Selected = @{}
function Test-Selected { param([string]$Key) return [bool]$script:Selected[$Key] }

function Expand-SelectionSpec {
    # '1,3,7-9' -> the matching catalog keys. Item keys are accepted too, so
    # -Select 'strix,claude-mem' works without counting rows in the menu.
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

# --- Sub-catalogs ----------------------------------------------------------------
# Three menu rows expand into a checkbox list of their own, opened with Right. Each
# sub-catalog carries the strings the helpers need to talk about it (Title, Noun, Flag)
# plus its Items. The two plugin catalogs give each item a Plugin ('name@marketplace')
# and the Source/Marketplace pair that has to be registered before it can be installed,
# so a marketplace is only added when something ticked actually needs it.
#
# This repo's own skills. Keep in sync with .claude-plugin/marketplace.json. Everything
# is on by default: picking a subset is the exception, and a fresh machine wants the lot.
$script:SkillCatalog = @(
    [pscustomobject]@{ Key = 'aws-opensearch';        Selected = $true; Name = 'aws-opensearch          - AWS OpenSearch: health, shards, reindex, ISM, snapshots' }
    [pscustomobject]@{ Key = 'bitbucket';             Selected = $true; Name = 'bitbucket               - Bitbucket Cloud: git auth, PRs, pipelines, REST API' }
    [pscustomobject]@{ Key = 'checkpoint-email';      Selected = $true; Name = 'checkpoint-email        - Check Point Email Security: phishing triage, quarantine' }
    [pscustomobject]@{ Key = 'cisco-meraki';          Selected = $true; Name = 'cisco-meraki            - Meraki Dashboard API: inventory, events, config changes' }
    [pscustomobject]@{ Key = 'claude-code-defaults';  Selected = $true; Name = 'claude-code-defaults    - Claude Code config: settings.json, permissions, hooks' }
    [pscustomobject]@{ Key = 'claude-code-tuneup';    Selected = $true; Name = 'claude-code-tuneup      - Audit a slow Claude Code setup: dupes, hooks, context' }
    [pscustomobject]@{ Key = 'cloudflare';            Selected = $true; Name = 'cloudflare              - Cloudflare v4: DNS, WAF, cache, Workers, Zero Trust' }
    [pscustomobject]@{ Key = 'drata';                 Selected = $true; Name = 'drata                   - Drata: controls, monitors, evidence, audit prep' }
    [pscustomobject]@{ Key = 'i-have-adhd';           Selected = $true; Name = 'i-have-adhd             - ADHD-friendly output: next action first, numbered steps' }
    [pscustomobject]@{ Key = 'infra-work-ticketing';  Selected = $true; Name = 'infra-work-ticketing    - ServiceDesk Plus / Jira: open tickets, log work notes' }
    [pscustomobject]@{ Key = 'intune-graph';          Selected = $true; Name = 'intune-graph            - Intune via Graph: devices, compliance, app deployment' }
    [pscustomobject]@{ Key = 'mermaid-svg-bitbucket'; Selected = $true; Name = 'mermaid-svg-bitbucket   - Pre-render Mermaid to SVG so Bitbucket displays it' }
    [pscustomobject]@{ Key = 'notify';                Selected = $true; Name = 'notify                  - Ping your phone or inbox: Telegram bot (two-way) or email' }
    [pscustomobject]@{ Key = 'repo-docs';             Selected = $true; Name = 'repo-docs               - Whole doc set: CLAUDE.md, READMEs, architecture, handoff' }
    [pscustomobject]@{ Key = 'shipstation';           Selected = $true; Name = 'shipstation             - ShipStation V2/V1/ShipEngine: labels, rates, orders' }
    [pscustomobject]@{ Key = 'sophos-central';        Selected = $true; Name = 'sophos-central          - Sophos Central: isolate endpoints, triage alerts, XDR' }
    [pscustomobject]@{ Key = 'terraform-docs-readme'; Selected = $true; Name = 'terraform-docs-readme   - Regenerate a Terraform module README with terraform-docs' }
    [pscustomobject]@{ Key = 'visio-diagrams';        Selected = $true; Name = 'visio-diagrams          - Native .vsdx diagrams from a spec, or via Visio COM' }
    [pscustomobject]@{ Key = 'wazuh-onprem';          Selected = $true; Name = 'wazuh-onprem            - Self-hosted Wazuh: server, indexer, dashboards, ossec.conf' }
    [pscustomobject]@{ Key = 'web-testing-playwright';Selected = $true; Name = 'web-testing-playwright  - Real-browser testing: screenshots, console, form flows' }
    [pscustomobject]@{ Key = 'work-log-reporter';     Selected = $true; Name = 'work-log-reporter       - Session work log + emailed PDF report over SMTP' }
)

# Team plugins. superpowers comes from anthropics/claude-plugins-official, not obra's own
# marketplace: upstream publishes to both, but Install-ClaudePlugin detects on the bare
# name, so a machine that already had superpowers from the official marketplace skipped
# the install and was left with an orphaned 'superpowers-marketplace' registration plus a
# second, disabled copy of the plugin. One source per plugin avoids the duplicate.
$script:TeamCatalog = @(
    [pscustomobject]@{ Key = 'superpowers';          Selected = $true; Name = 'superpowers             - brainstorming, TDD, systematic debugging, plan execution'; Plugin = 'superpowers@claude-plugins-official';       Source = 'anthropics/claude-plugins-official'; Marketplace = 'claude-plugins-official' }
    [pscustomobject]@{ Key = 'frontend-design';      Selected = $true; Name = 'frontend-design         - distinctive UI: typography, colour, layout with intent';  Plugin = 'frontend-design@claude-code-plugins';       Source = 'anthropics/claude-code';               Marketplace = 'claude-code-plugins' }
    [pscustomobject]@{ Key = 'excalidraw-generator'; Selected = $true; Name = 'excalidraw-generator    - hand-drawn .excalidraw diagrams from a description';     Plugin = 'excalidraw-generator@excalidraw-generator'; Source = 'lexiaoyao20/excalidraw-generator';     Marketplace = 'excalidraw-generator' }
)

# Community plugins, from claudepluginhub.com. Source repo -> marketplace name is *not*
# mechanical: fcakyon/claude-codex-settings publishes itself as 'claude-settings'. Each
# Marketplace below is the "name" field in that repo's own .claude-plugin/marketplace.json,
# which is what 'plugin@marketplace' has to match.
$script:CommunityCatalog = @(
    [pscustomobject]@{ Key = 'adhd-output-style';       Selected = $true; Name = 'adhd-output-style       - ADHD-friendly output: short, numbered, action first'; Plugin = 'adhd-output-style@claude-settings';       Source = 'fcakyon/claude-codex-settings'; Marketplace = 'claude-settings' }
    [pscustomobject]@{ Key = 'azure-tools';             Selected = $true; Name = 'azure-tools             - Azure CLI and Bicep helpers, deployment commands';    Plugin = 'azure-tools@claude-settings';             Source = 'fcakyon/claude-codex-settings'; Marketplace = 'claude-settings' }
    [pscustomobject]@{ Key = 'anthropic-office-skills'; Selected = $true; Name = 'anthropic-office-skills - docx, xlsx, pptx and pdf authoring skills';           Plugin = 'anthropic-office-skills@claude-settings'; Source = 'fcakyon/claude-codex-settings'; Marketplace = 'claude-settings' }
    [pscustomobject]@{ Key = 'agent-browser';           Selected = $true; Name = 'agent-browser           - drive a real browser from an agent (vercel-labs)';    Plugin = 'agent-browser@agent-browser';             Source = 'vercel-labs/agent-browser';     Marketplace = 'agent-browser' }
    [pscustomobject]@{ Key = 'ppt-master';              Selected = $true; Name = 'ppt-master              - build and edit PowerPoint decks';                     Plugin = 'ppt-master@ppt-master';                   Source = 'hugohe3/ppt-master';            Marketplace = 'ppt-master' }
)

$script:SubCatalogs = @{
    SKILL     = [pscustomobject]@{ Title = 'Pick individual skills from this repo'; Noun = 'skill';            Flag = '-Skills';           Items = $script:SkillCatalog }
    TEAM      = [pscustomobject]@{ Title = 'Pick team plugins';                     Noun = 'team plugin';      Flag = '-TeamPlugins';      Items = $script:TeamCatalog }
    COMMUNITY = [pscustomobject]@{ Title = 'Pick community plugins';                Noun = 'community plugin'; Flag = '-CommunityPlugins'; Items = $script:CommunityCatalog }
}

function Get-SubCatalog {
    param([string]$Name)
    return $script:SubCatalogs[$Name]
}

function Get-SubSelectedCount {
    param([string]$Name)
    return @((Get-SubCatalog $Name).Items | Where-Object { $_.Selected }).Count
}

function Set-AllSubItems {
    param([string]$Name, [bool]$Value)
    foreach ($item in (Get-SubCatalog $Name).Items) { $item.Selected = $Value }
}

function Expand-SubSpec {
    # 'cloudflare,drata' | '1,4-6' | 'all' | 'none' -> sets .Selected on the sub-catalog.
    param([string]$Name, [string]$Spec)
    $cat = Get-SubCatalog $Name
    switch -Regex ($Spec) {
        '^(?i)all$'  { Set-AllSubItems $Name $true;  return }
        '^(?i)none$' { Set-AllSubItems $Name $false; return }
    }
    Set-AllSubItems $Name $false
    $items = $cat.Items
    foreach ($token in ($Spec -split '[,\s]+' | Where-Object { $_ })) {
        if ($token -match '^(\d+)\s*-\s*(\d+)$') {
            foreach ($n in [int]$Matches[1]..[int]$Matches[2]) {
                if ($n -ge 1 -and $n -le $items.Count) { $items[$n - 1].Selected = $true }
            }
        } elseif ($token -match '^\d+$') {
            $n = [int]$token
            if ($n -ge 1 -and $n -le $items.Count) {
                $items[$n - 1].Selected = $true
            } else {
                Write-Warn2 "ignoring out-of-range $($cat.Noun) number '$token'"
            }
        } else {
            $hit = $items | Where-Object { $_.Key -eq $token.ToLower() } | Select-Object -First 1
            if ($hit) { $hit.Selected = $true } else { Write-Warn2 "ignoring unknown $($cat.Noun) '$token'" }
        }
    }
}

function Test-SubKeySelected {
    param([string]$Name, [string]$Key)
    return @((Get-SubCatalog $Name).Items | Where-Object { $_.Key -eq $Key -and $_.Selected }).Count -gt 0
}

function Get-MenuLabel {
    # A sub-catalog row carries a live count, because "its 21 skills" stops being true the
    # moment someone opens the sub-picker and unticks one.
    param([int]$Index)
    $item = $script:Catalog[$Index]
    if ($item.Sub) {
        $cat = Get-SubCatalog $item.Sub
        return ($item.Name -f (Get-SubSelectedCount $item.Sub), $cat.Items.Count)
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

function Select-SubInteractive {
    # Only writes back on confirm, so Q discards the whole sub-selection by doing nothing.
    param([string]$Name)
    $cat = Get-SubCatalog $Name
    $items = $cat.Items
    $labels = @($items | ForEach-Object { $_.Name })
    $state = @($items | ForEach-Object { [bool]$_.Selected })
    $sub = @($items | ForEach-Object { $false })
    $defaults = @($items | ForEach-Object { $true })
    $result = Invoke-Picker -Labels $labels -State $state -Sub $sub -Defaults $defaults `
        -Title $cat.Title `
        -Hint 'Enter or Left to go back to the main menu   Q to discard these changes'
    if ($result.Action -eq 'cancel') { return }
    for ($i = 0; $i -lt $items.Count; $i++) {
        $items[$i].Selected = [bool]$result.State[$i]
    }
}

function Select-MenuInteractive {
    $state = @($script:Catalog | ForEach-Object { [bool]$_.Default })
    $defaults = @($script:Catalog | ForEach-Object { [bool]$_.Default })
    $sub = @($script:Catalog | ForEach-Object { [bool]$_.Sub })
    $cursor = 0

    while ($true) {
        $labels = @(for ($i = 0; $i -lt $script:Catalog.Count; $i++) { Get-MenuLabel $i })
        $result = Invoke-Picker -Labels $labels -State $state -Sub $sub -Defaults $defaults `
            -Title 'Select what to install' `
            -Hint 'Right on a row ending in > picks what goes into it' -Cursor $cursor
        $state = @($result.State)
        $cursor = $result.Cursor
        if ($result.Action -eq 'submenu') {
            $subName = $script:Catalog[$cursor].Sub
            Select-SubInteractive $subName
            # Opening a sub-picker is a statement of intent: tick the parent row so a
            # careful sub-selection is not silently thrown away by an unticked parent.
            if ((Get-SubSelectedCount $subName) -gt 0) { $state[$cursor] = $true }
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
    Write-Host "  Rows ending in > hold a list: -Skills 'cloudflare,drata'" -ForegroundColor DarkGray
    Write-Host "  -TeamPlugins 'superpowers'   -CommunityPlugins 'ppt-master'" -ForegroundColor DarkGray
}

function Select-InstallItems {
    $defaults = @($script:Catalog | Where-Object { $_.Default } | ForEach-Object { $_.Key })
    $everything = @($script:Catalog | ForEach-Object { $_.Key })

    # The sub-catalog switches are non-interactive answers in their own right: they settle
    # each list before anything is drawn, so they compose with -All and -NonInteractive.
    foreach ($pair in @(
        @{ Name = 'SKILL';     Spec = $Skills;          Label = 'Skills';            Flag = '-Skills' },
        @{ Name = 'TEAM';      Spec = $TeamPlugins;     Label = 'Team plugins';      Flag = '-TeamPlugins' },
        @{ Name = 'COMMUNITY'; Spec = $CommunityPlugins;Label = 'Community plugins'; Flag = '-CommunityPlugins' }
    )) {
        if (-not $pair.Spec) { continue }
        Expand-SubSpec $pair.Name $pair.Spec
        Write-Host ("{0} from {1} '{2}' ({3} of {4})." -f $pair.Label, $pair.Flag, $pair.Spec,
            (Get-SubSelectedCount $pair.Name), (Get-SubCatalog $pair.Name).Items.Count) -ForegroundColor DarkGray
    }

    $keys = @()
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
    } else {
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
        $item = $script:Catalog[$i]
        if (-not (Test-Selected $item.Key)) { continue }
        Write-Host "    - $(Get-MenuLabel $i)"
        if (-not $item.Sub) { continue }
        # Only worth spelling out when it is a subset - the row label already reads "N of N".
        $cat = Get-SubCatalog $item.Sub
        $picked = Get-SubSelectedCount $item.Sub
        if ($picked -eq 0) {
            Write-Warn2 "nothing ticked in this list - it will be skipped. Re-run with $($cat.Flag) all to get everything."
        } elseif ($picked -lt $cat.Items.Count) {
            foreach ($s in ($cat.Items | Where-Object { $_.Selected })) { Write-Host "        - $($s.Key)" }
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
    return (Test-SubKeySelected 'SKILL' $Key)
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

# --- claude-mem runtime: Bun --------------------------------------------------

function Install-Bun {
    # claude-mem's hooks run its worker under Bun (package.json declares engines.bun
    # >= 1.0.0) via scripts/bun-runner.js, which resolves the interpreter with
    # 'where bun' and only then falls back to $HOME\.bun\bin\bun.exe. Neither this
    # script nor the plugin ever installed it, so on a fresh machine every claude-mem
    # hook died with "Bun not found". Chocolatey's shim lands a real bun.exe on PATH,
    # which is exactly what bun-runner looks for first.
    $existing = Get-Command bun -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Skip "bun already present ($($existing.Source))"
        return
    }

    # choco install writes to C:\ProgramData and needs Administrator, so both halves of
    # the condition matter - a non-elevated run with choco on PATH would still fail.
    if ((Get-Command choco -ErrorAction SilentlyContinue) -and $script:IsElevated) {
        choco install bun -y --no-progress
        if ($LASTEXITCODE -ne 0) {
            throw "choco install bun failed with exit code $LASTEXITCODE - see the output above."
        }
    } else {
        # No Chocolatey, or not elevated. Bun's own installer is per-user and needs no
        # Administrator rights; it writes $HOME\.bun\bin\bun.exe, which is bun-runner's
        # documented fallback path when 'where bun' finds nothing.
        Write-Warn2 "Chocolatey unavailable or not elevated - using bun's per-user installer instead."
        Invoke-RestMethod https://bun.sh/install.ps1 | Invoke-Expression
    }

    Sync-SessionEnvironment
    if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
        $fallback = Join-Path $env:USERPROFILE '.bun\bin\bun.exe'
        if (Test-Path $fallback) {
            Write-Ok "installed bun at $fallback (not on PATH in this session - claude-mem finds it there anyway)"
            $script:Summary.Installed++
            return
        }
        throw "bun still not found after installing - open a new shell and re-run."
    }
    $script:Summary.Installed++
    Write-Ok "installed bun $((bun --version 2>$null) -join '')"
}

# --- claude-mem settings.json patch ------------------------------------------

function Set-ClaudeMemWorkerPort {
    # claude-mem's own bootstrap writes CLAUDE_MEM_PROVIDER but not the worker port,
    # and the worker silently picks a different port without it. Patch the text rather
    # than round-tripping through ConvertTo-Json, which reformats the entire file.
    param([string]$Port = '37790')

    $settings = Join-Path (Get-ClaudeConfigRoot) 'settings.json'
    if (-not (Test-Path $settings)) {
        Write-Warn2 "no settings.json at $settings yet - claude-mem writes it on first run; re-run this script afterwards to set CLAUDE_MEM_WORKER_PORT."
        return
    }

    $raw = Get-Content -Path $settings -Raw -Encoding UTF8
    if ($raw -match '"CLAUDE_MEM_WORKER_PORT"') {
        Write-Skip "CLAUDE_MEM_WORKER_PORT already present in $settings"
        return
    }

    $backup = "$settings.bak"
    Copy-Item -Path $settings -Destination $backup -Force

    $updated = $null
    $providerLine = '(?m)^([ \t]*)"CLAUDE_MEM_PROVIDER"[ \t]*:[ \t]*"[^"]*"[ \t]*(,?)[ \t]*\r?$'
    if ($raw -match $providerLine) {
        $updated = [regex]::Replace($raw, $providerLine, {
            param($m)
            $indent = $m.Groups[1].Value
            $line = $m.Value.TrimEnd()
            if ($m.Groups[2].Value -eq ',') {
                # Provider already has a trailing comma, so the new key needs one too.
                "$line`r`n$indent`"CLAUDE_MEM_WORKER_PORT`": `"$Port`","
            } else {
                # Provider was the last key in its object - give it the comma instead.
                "$line,`r`n$indent`"CLAUDE_MEM_WORKER_PORT`": `"$Port`""
            }
        }, 1)
    } else {
        # No provider key to anchor to. Fall back to a structural edit of the env block,
        # writing both keys so the file ends up in the documented shape either way.
        try {
            $json = $raw | ConvertFrom-Json
        } catch {
            Write-Warn2 "could not parse $settings as JSON ($($_.Exception.Message)) - left it untouched. Add `"CLAUDE_MEM_WORKER_PORT`": `"$Port`" by hand."
            Remove-Item $backup -Force -ErrorAction SilentlyContinue
            return
        }
        if (-not $json.PSObject.Properties['env']) {
            $json | Add-Member -NotePropertyName 'env' -NotePropertyValue ([pscustomobject]@{})
        }
        if (-not $json.env.PSObject.Properties['CLAUDE_MEM_PROVIDER']) {
            $json.env | Add-Member -NotePropertyName 'CLAUDE_MEM_PROVIDER' -NotePropertyValue 'claude' -Force
        }
        $json.env | Add-Member -NotePropertyName 'CLAUDE_MEM_WORKER_PORT' -NotePropertyValue $Port -Force
        $updated = $json | ConvertTo-Json -Depth 100
        Write-Warn2 "CLAUDE_MEM_PROVIDER was not in $settings - rewrote the file to add the env block (formatting may change; backup at $backup)."
    }

    # Never leave a half-written settings.json behind: validate, then restore on failure.
    try {
        $updated | ConvertFrom-Json | Out-Null
    } catch {
        Write-Warn2 "the patched settings.json did not parse ($($_.Exception.Message)) - restoring $backup."
        Copy-Item -Path $backup -Destination $settings -Force
        return
    }

    Set-Content -Path $settings -Value $updated -Encoding UTF8 -NoNewline
    $script:Summary.Installed++
    Write-Ok "set CLAUDE_MEM_WORKER_PORT=$Port in $settings (backup: $backup)"
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
        # Upstream's snippet opens with 'Set-ExecutionPolicy Bypass -Scope Process'. It is
        # deliberately not here: on a machine where the policy is set by Group Policy or
        # MDM that call throws, and with $ErrorActionPreference = 'Stop' it takes the whole
        # step down before Chocolatey is even downloaded. Nothing below needs it - the
        # installer arrives as a string and is run through Invoke-Expression, not as a .ps1
        # on disk. A host that really is locked down to AllSigned will say so, and the
        # answer there is a policy exemption, not a call this script is not allowed to make.
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
$claudeItems = @('own-skills', 'team', 'find-skills', 'community', 'claude-code-setup', 'claude-mem', 'voltagent', 'supabase')
$needsClaude = @($claudeItems | Where-Object { Test-Selected $_ }).Count -gt 0

if ($needsClaude -and -not (Test-ClaudeAvailable)) {
    Write-Step "Skipping marketplace/plugin items"
    Write-Warn2 "claude is not on PATH in this session - open a new shell and re-run to install them."
    foreach ($key in $claudeItems) { $script:Selected.Remove($key) }
}

# --- 3. This repo's own marketplace and skills -------------------------------
if (Test-Selected 'own-skills') {
    Invoke-Step "Add this repo as a Claude Code marketplace" {
        Add-ClaudeMarketplace -Source 'mbadali25/useful-claude-add-ons' -Name 'useful-claude-add-ons'
    }

    # The catalog itself lives in $script:SkillCatalog next to the menu; only the
    # ticked ones get installed, so -Skills and the sub-picker both land here.
    if ((Get-SubSelectedCount 'SKILL') -eq 0) {
        Write-Warn2 "no skills selected from this repo - marketplace registered, nothing installed."
    }
    $ownPlugins = @($script:SkillCatalog | Where-Object { $_.Selected } | ForEach-Object { $_.Key })
    foreach ($plugin in $ownPlugins) {
        Invoke-Step "Plugin: $plugin@useful-claude-add-ons" {
            Install-ClaudePlugin "$plugin@useful-claude-add-ons"
        }
    }

    # notify is the one skill with machine-level setup (a config file and a bot token),
    # so it gets a post-install step when the user asked for it up front.
    if ($script:NotifySetupChoice -and (Test-SkillSelected 'notify')) {
        Invoke-Step "Set up the notify skill" { Install-NotifyConfig }
    }
}

# --- 4. Team marketplaces and plugins ----------------------------------------
function Install-SubCatalog {
    # Registers only the marketplaces the ticked plugins actually need. Unticking every
    # plugin from one source leaves that source unregistered rather than dangling, and a
    # source shared by several plugins is still only added once. Add-ClaudeMarketplace is
    # a no-op when the marketplace is already there, so overlaps with other menu items
    # (claude-plugins-official is also registered by items 7 and 14) cost nothing.
    param([string]$Name)
    $cat = Get-SubCatalog $Name
    $added = @{}
    foreach ($item in ($cat.Items | Where-Object { $_.Selected })) {
        if (-not $added.ContainsKey($item.Marketplace)) {
            $source = $item.Source
            $market = $item.Marketplace
            Invoke-Step "Marketplace: $source" {
                Add-ClaudeMarketplace -Source $source -Name $market
            }
            $added[$item.Marketplace] = $true
        }
        $spec = $item.Plugin
        Invoke-Step "Plugin: $spec" {
            Install-ClaudePlugin $spec
        }
    }
}

if (Test-Selected 'team') {
    if ((Get-SubSelectedCount 'TEAM') -eq 0) {
        Write-Warn2 "no team plugins ticked - nothing to install for that item."
    }
    Install-SubCatalog 'TEAM'
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

# --- 6. Community marketplaces (from claudepluginhub.com) --------------------
# Installed with native 'claude plugin' commands, from $script:CommunityCatalog next to
# the menu - so unticking a plugin in the sub-picker also drops its marketplace when
# nothing else ticked needs it.
if (Test-Selected 'community') {
    if ((Get-SubSelectedCount 'COMMUNITY') -eq 0) {
        Write-Warn2 "no community plugins ticked - nothing to install for that item."
    }
    Install-SubCatalog 'COMMUNITY'
}

# --- 7. claude-code-setup ----------------------------------------------------
# Ships inside anthropics/claude-plugins-official, which the team item also registers -
# Add-ClaudeMarketplace is a no-op when it is already there, so this item works whether
# or not item 4 was selected.
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

# --- 9. claude-mem -----------------------------------------------------------
if (Test-Selected 'claude-mem') {
    # claude-mem supports the plugin-marketplace path as a first-class alternative to
    # its 'npx claude-mem install' bootstrapper (see its README) - the plugin's own
    # hooks handle worker/dependency setup on first run. Bun is the one dependency
    # those hooks cannot install for themselves, so it goes first.
    Invoke-Step "Install Bun (claude-mem worker runtime)" { Install-Bun }
    Invoke-Step "Marketplace: thedotmack/claude-mem" {
        Add-ClaudeMarketplace -Source 'thedotmack/claude-mem' -Name 'thedotmack'
    }
    Invoke-Step "Plugin: claude-mem@thedotmack" {
        Install-ClaudePlugin 'claude-mem@thedotmack'
    }
    Invoke-Step "Configure claude-mem worker port" {
        Set-ClaudeMemWorkerPort -Port '37790'
    }
}

# --- 10. VoltAgent subagents -------------------------------------------------
# The repo publishes itself as the 'voltagent-subagents' marketplace, with its
# 154 subagents split across ten category plugins. Installing them as plugins
# replaces the old 'git clone + bash install-agents.sh' path, which needed Git
# Bash on Windows (and failed outright when the script ran non-elevated, since
# Chocolatey - and therefore git - was skipped).
if (Test-Selected 'voltagent') {
    Invoke-Step "Marketplace: VoltAgent/awesome-claude-code-subagents" {
        Add-ClaudeMarketplace -Source 'VoltAgent/awesome-claude-code-subagents' -Name 'voltagent-subagents'
    }

    $voltAgentPlugins = @(
        'voltagent-core-dev',
        'voltagent-lang',
        'voltagent-infra',
        'voltagent-qa-sec',
        'voltagent-data-ai',
        'voltagent-dev-exp',
        'voltagent-domains',
        'voltagent-biz',
        'voltagent-meta',
        'voltagent-research'
    )
    foreach ($plugin in $voltAgentPlugins) {
        Invoke-Step "Plugin: $plugin@voltagent-subagents" {
            Install-ClaudePlugin "$plugin@voltagent-subagents"
        }
    }
}

# --- 11-13. Optional MCP servers ---------------------------------------------
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

# --- 14. Supabase ------------------------------------------------------------
# Ships inside anthropics/claude-plugins-official, the same marketplace items 4 and 7
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

# --- 15. Context7 ------------------------------------------------------------
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

# --- 16. Playwright CLI ------------------------------------------------------
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

# --- 17. SkillUI -------------------------------------------------------------
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

# --- 18. Strix ---------------------------------------------------------------
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
