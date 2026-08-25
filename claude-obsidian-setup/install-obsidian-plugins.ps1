<#
.SYNOPSIS
  Install the standard Obsidian community plugin set into a vault (Windows).

.DESCRIPTION
  Reads obsidian-plugin-profile.json and installs each community plugin from
  its GitHub release, then enables it and the standard core plugin set.

  Standards shared with the Linux script (install-obsidian-plugins.sh):
    * dry run by default; -Apply writes
    * every check reports PASS / FIX / FAIL with a stable check id
    * idempotent - a plugin already at the requested version is PASS, not FIX
    * exits non-zero if any check is still FAIL

  Additive. Config files are merged, never replaced, so a vault that is already
  in use keeps its own settings. community-plugins.json and core-plugins.json
  are unioned with what is already enabled.

  obsidian-local-rest-api is installed but its settings are never written: the
  plugin generates a per-machine API key on first load and overwriting it would
  break any MCP client already pointed at that vault.

.PARAMETER VaultPath
  Vault root - the directory containing .obsidian. Created if absent.

.PARAMETER Apply
  Actually write. Without it this previews and changes nothing.

.PARAMETER ProfilePath
  Plugin manifest. Defaults to obsidian-plugin-profile.json beside this script.

.PARAMETER Latest
  Install each plugin's latest release instead of the pinned version.

.PARAMETER Only
  Install just these plugin ids.

.EXAMPLE
  .\install-obsidian-plugins.ps1 -VaultPath C:\repos\Claude

.EXAMPLE
  .\install-obsidian-plugins.ps1 -VaultPath C:\repos\Claude -Apply

.EXAMPLE
  .\install-obsidian-plugins.ps1 -VaultPath C:\repos\Claude -Apply -Only dataview,templater-obsidian
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)] [string] $VaultPath,
  [switch]   $Apply,
  [string]   $ProfilePath,
  [switch]   $Latest,
  [string[]] $Only = @()
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:Failed = 0
function Pass($id, $msg) { Write-Host ("  PASS  {0,-28} {1}" -f $id, $msg) -ForegroundColor Green }
function Fix ($id, $msg) { Write-Host ("  FIX   {0,-28} {1}" -f $id, $msg) -ForegroundColor Yellow }
function Fail($id, $msg) { Write-Host ("  FAIL  {0,-28} {1}" -f $id, $msg) -ForegroundColor Red; $script:Failed = 1 }
function Head($t)        { Write-Host "`n== $t" -ForegroundColor Cyan }

# Generates a per-machine API key on first load. Install it, never write its settings.
$NoSettings = @('obsidian-local-rest-api')

$RegistryUrl   = 'https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master/community-plugins.json'
$RegistryCache = Join-Path $env:TEMP 'obsidian-community-plugins.json'
$Utf8NoBom     = New-Object System.Text.UTF8Encoding($false)

if (-not $ProfilePath) { $ProfilePath = Join-Path $PSScriptRoot 'obsidian-plugin-profile.json' }

Write-Host "obsidian community plugins"
Write-Host ("  vault   : {0}" -f $VaultPath)
Write-Host ("  profile : {0}" -f $ProfilePath)
Write-Host ("  mode    : {0}" -f $(if ($Apply) { 'APPLY' } else { 'dry run (add -Apply to write)' }))

# --- 1. Inputs -------------------------------------------------------------
Head "1. Inputs"

if (-not (Test-Path $ProfilePath)) { Fail "profile" "not found: $ProfilePath"; exit 1 }
$profile = Get-Content $ProfilePath -Raw | ConvertFrom-Json
Pass "profile" "$($profile.communityPlugins.Count) community, $($profile.enabledCorePlugins.Count) core"

$dotObsidian = Join-Path $VaultPath '.obsidian'
if (Test-Path $dotObsidian) {
  Pass "vault" "$VaultPath"
}
elseif ($Apply) {
  New-Item -ItemType Directory -Path $dotObsidian -Force | Out-Null
  Fix "vault" "created $dotObsidian"
}
else {
  Fix "vault" "would create $dotObsidian"
}
$pluginRoot = Join-Path $dotObsidian 'plugins'

# --- 2. Registry -----------------------------------------------------------
Head "2. Plugin registry"
$fresh = (Test-Path $RegistryCache) -and ((Get-Item $RegistryCache).LastWriteTime -gt (Get-Date).AddHours(-1))
if (-not $fresh) {
  try { Invoke-WebRequest -Uri $RegistryUrl -OutFile $RegistryCache -UseBasicParsing }
  catch { Fail "registry" "could not fetch $RegistryUrl - $($_.Exception.Message)"; exit 1 }
}
$repoMap = @{}
foreach ($e in (Get-Content $RegistryCache -Raw | ConvertFrom-Json)) {
  if (-not $repoMap.ContainsKey($e.id)) { $repoMap[$e.id] = $e.repo }
}
Pass "registry" "$($repoMap.Count) plugins known"

# --- 3. Plugins ------------------------------------------------------------
Head "3. Community plugins"

function Get-PluginRelease {
  param([string]$Id, [string]$Want, [string]$Repo, [string]$Dest)
  $tags = @()
  if (-not $Latest -and $Want) { $tags += $Want; $tags += "v$Want" }
  $tags += '__latest__'
  foreach ($tag in $tags) {
    $base = if ($tag -eq '__latest__') { "https://github.com/$Repo/releases/latest/download" }
            else { "https://github.com/$Repo/releases/download/$tag" }
    try {
      Invoke-WebRequest "$base/manifest.json" -OutFile (Join-Path $Dest 'manifest.json') -UseBasicParsing -ErrorAction Stop
      Invoke-WebRequest "$base/main.js"       -OutFile (Join-Path $Dest 'main.js')       -UseBasicParsing -ErrorAction Stop
      try { Invoke-WebRequest "$base/styles.css" -OutFile (Join-Path $Dest 'styles.css') -UseBasicParsing -ErrorAction Stop } catch { }
      return $(if ($tag -eq '__latest__') { 'latest' } else { $tag })
    }
    catch { continue }
  }
  return $null
}

$targets = $profile.communityPlugins
if ($Only.Count -gt 0) { $targets = $targets | Where-Object { $Only -contains $_.id } }

$enabled = New-Object System.Collections.Generic.List[string]
foreach ($p in $targets) {
  if (-not $p.id) { continue }
  $enabled.Add($p.id) | Out-Null
  $dest = Join-Path $pluginRoot $p.id
  $manifest = Join-Path $dest 'manifest.json'

  if ((Test-Path $manifest) -and -not $Latest) {
    $have = (Get-Content $manifest -Raw | ConvertFrom-Json).version
    if ($have -eq $p.version) { Pass $p.id "$have"; continue }
  }

  $repo = if ($p.repo) { $p.repo } elseif ($repoMap.ContainsKey($p.id)) { $repoMap[$p.id] } else { $null }
  if (-not $repo) { Fail $p.id "not in the community registry"; continue }

  if (-not $Apply) { Fix $p.id "would install $($p.version) from $repo"; continue }

  # Download into a staging directory first. An existing install (upgrade case)
  # is only ever touched AFTER a full, validated download succeeds - a failed
  # or partial download (404, rate limit, network blip) must leave it untouched
  # rather than delete a working plugin.
  $staging = Join-Path $pluginRoot ("$($p.id).new-{0}" -f ([guid]::NewGuid().ToString('N')))
  New-Item -ItemType Directory -Path $staging -Force | Out-Null
  $tag = Get-PluginRelease -Id $p.id -Want $p.version -Repo $repo -Dest $staging
  $stagedManifest = Join-Path $staging 'manifest.json'
  $stagedMain = Join-Path $staging 'main.js'
  if ($tag -and (Test-Path $stagedManifest) -and (Test-Path $stagedMain)) {
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Move-Item $staging $dest -Force
    $got = (Get-Content $manifest -Raw | ConvertFrom-Json).version
    if ($tag -eq 'latest' -and $got -ne $p.version) { Fix $p.id "$got (pinned $($p.version) unavailable)" }
    else { Fix $p.id "installed $got" }
  }
  else {
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    Fail $p.id "no downloadable release from $repo - existing install left untouched"
  }
}

# --- 4. Enable -------------------------------------------------------------
Head "4. Enabling plugins"

function Merge-JsonArray {
  param([string]$Path, [string[]]$Add, [string]$Id)

  # Assign the parse to a variable BEFORE wrapping. @(<pipeline>) does not
  # unroll: ConvertFrom-Json emits a JSON array as ONE object, so
  # @(Get-Content ... | ConvertFrom-Json) yields a 1-element array containing
  # the array. Every pre-existing entry then fails the -is [string] test and is
  # silently dropped. @($variable) on an existing array flattens correctly.
  $existing = @()
  if (Test-Path $Path) {
    $parsed = Get-Content $Path -Raw | ConvertFrom-Json
    if ($parsed -is [System.Array]) { $existing = $parsed }
    elseif ($null -ne $parsed)      { $existing = @($parsed) }
  }

  # Built with an explicit string set rather than `+ | Select-Object -Unique |
  # Sort-Object`. That pipeline re-wraps a nested array as a PSObject and emits
  # {"value":[...],"Count":N} into the middle of the JSON list - a corrupt file
  # that Obsidian silently ignores.
  $set = New-Object 'System.Collections.Generic.SortedSet[string]' (,[StringComparer]::Ordinal)
  foreach ($x in @($existing)) { if ($x -is [string] -and $x) { [void]$set.Add($x) } }
  foreach ($x in @($Add))      { if ($x)                      { [void]$set.Add([string]$x) } }
  $merged = @($set)

  # Parenthesise both sides. Without them, `-join` and `-eq` bind so the
  # expression compares a string to an array and then joins the RESULT, which
  # is always truthy - the merge silently never writes and every run reports
  # PASS while leaving the plugins installed but disabled.
  $beforeSet = New-Object 'System.Collections.Generic.SortedSet[string]' (,[StringComparer]::Ordinal)
  foreach ($x in @($existing)) { if ($x -is [string] -and $x) { [void]$beforeSet.Add($x) } }
  $before = (@($beforeSet)) -join ','
  $after  = (@($merged))    -join ','

  if ($before -eq $after) { Pass $Id "$($merged.Count) already enabled"; return }

  $new = $merged.Count - $beforeSet.Count
  if (-not $Apply) { Fix $Id "would enable $($merged.Count) ($new new)"; return }

  # ConvertTo-Json renders a 1-element array as a bare scalar; force the array.
  $json = if ($merged.Count -eq 1) { "[`n  ""$($merged[0])""`n]" }
          else { $merged | ConvertTo-Json -Depth 4 }
  [System.IO.File]::WriteAllText($Path, $json, $Utf8NoBom)
  Fix $Id "enabled $($merged.Count) ($new new)"
}

Merge-JsonArray -Path (Join-Path $dotObsidian 'community-plugins.json') -Add $enabled -Id 'community-plugins'

# core-plugins.json is an array in older vaults, an object map in newer ones.
$corePath = Join-Path $dotObsidian 'core-plugins.json'
$want = @($profile.enabledCorePlugins)
if ((Test-Path $corePath) -and ((Get-Content $corePath -Raw | ConvertFrom-Json) -isnot [System.Array])) {
  $obj = Get-Content $corePath -Raw | ConvertFrom-Json
  $h = @{}
  foreach ($prop in $obj.PSObject.Properties) { $h[$prop.Name] = $prop.Value }
  $added = @($want | Where-Object { -not $h.ContainsKey($_) -or -not $h[$_] })
  if ($added.Count -eq 0) { Pass "core-plugins" "$($want.Count) already enabled" }
  elseif (-not $Apply) { Fix "core-plugins" "would enable $($added.Count) more" }
  else {
    foreach ($k in $want) { $h[$k] = $true }
    [System.IO.File]::WriteAllText($corePath, ($h | ConvertTo-Json -Depth 4), $Utf8NoBom)
    Fix "core-plugins" "enabled $($added.Count) more"
  }
}
else {
  Merge-JsonArray -Path $corePath -Add $want -Id 'core-plugins'
}

foreach ($id in $NoSettings) {
  if ($enabled -contains $id) {
    Pass "$id-settings" "not written (per-machine API key)"
  }
}

# --- 5. Summary ------------------------------------------------------------
Head "5. Result"
if ($script:Failed -ne 0) {
  Write-Host "  one or more checks FAILED" -ForegroundColor Red
  exit 1
}
if (-not $Apply) {
  Write-Host "  dry run only - re-run with -Apply to write" -ForegroundColor Yellow
}
else {
  Write-Host "  done. Reload Obsidian (Ctrl+P -> 'Reload app without saving')," -ForegroundColor Green
  Write-Host "  then Settings -> Community plugins to confirm Restricted Mode is off." -ForegroundColor Green
}
exit 0
