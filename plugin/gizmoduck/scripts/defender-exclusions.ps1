<#
.SYNOPSIS
  Register (or remove) the Windows Defender exclusions gizmoduck's scanners need.

.DESCRIPTION
  Five of gizmoduck's ten scanners are the same category of software Defender's
  HackTool family exists to catch, and they are CORRECT detections rather than
  false positives - nikto really is a scanner, sqlmap really does build SQL
  injection payloads, and Nuclei's template library really does ship working
  exploits. docs/antivirus-exclusions.md documents the detections that actually
  fired on a real install, with ThreatIDs. This script applies that same list
  instead of leaving it to be copied by hand.

  The failure it prevents is quiet. Defender deletes rather than quarantines
  here, so the symptom is a script that vanished or a download that never
  finished - which reads as a broken install, not as antivirus doing its job.

.PARAMETER Apply
  Actually register the exclusions. WITHOUT THIS THE SCRIPT ONLY PREVIEWS.
  The default is preview because every exclusion narrows the protection on a
  machine, and that should be a decision somebody makes on purpose.

.PARAMETER Remove
  Reverse it - remove exactly the exclusions this script adds, and nothing else.

.PARAMETER NoInterpreterExclusions
  Skip the two process exclusions for `perl.exe` and `java.exe`. Both are
  general-purpose interpreters rather than gizmoduck-specific binaries, so they
  are wider than the rest of the list. nikto needs perl and ZAP needs java, and
  a path exclusion alone has not been verified sufficient for either - so
  skipping these may leave those two tools being killed mid-scan.

.EXAMPLE
  .\defender-exclusions.ps1
  Preview. Shows exactly what would be added and what is already registered.

.EXAMPLE
  .\defender-exclusions.ps1 -Apply
  Register them. Needs an elevated prompt.

.NOTES
  Paths are derived from the same locations bootstrap.ps1 installs to, so the
  two cannot drift apart. Nothing here excludes a broad location: no drive
  root, no %USERPROFILE%, no Program Files as a whole. Every path is one
  tool's own directory, and the script refuses any entry that is not.
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$Remove,
    [switch]$NoInterpreterExclusions
)

$ErrorActionPreference = "Stop"

# --- what gets excluded, and why -------------------------------------------
#
# Derived from docs/antivirus-exclusions.md section 2/3 - the detections that
# actually fired, not a blanket "exclude everything gizmoduck touches" list.
# A tool with no observed detection (checkov, dependency-check) is absent on
# purpose; add it only if it starts happening.

$ToolsDir = Join-Path $env:LOCALAPPDATA "Programs"

$PathExclusions = @(
    @{ Path = Join-Path $ToolsDir "nuclei";      Why = "engine binary, flagged heuristically" }
    @{ Path = Join-Path $env:USERPROFILE "nuclei-templates";
       Why = "CVE PoC templates ship working exploits (ThreatID 2147959786)" }
    @{ Path = Join-Path $ToolsDir "nikto";       Why = "HackTool:Perl/NiktoSanner.A (ThreatID 2147794255)" }
    @{ Path = Join-Path $ToolsDir "sqlmap";      Why = "HackTool:Python/SqlMap!AMTB" }
    @{ Path = Join-Path $ToolsDir "zap";         Why = "Program:Java/Multiverze!rfn (ThreatID 453479), caught mid-download" }
    @{ Path = Join-Path $ToolsDir "testssl.sh";  Why = "precautionary - no detection observed" }
)

$ProcessExclusions = @(
    @{ Name = "nuclei.exe"; Why = "engine"; Broad = $false }
    @{ Name = "nikto.pl";   Why = "the flagged script itself"; Broad = $false }
    @{ Name = "nmap.exe";   Why = "flagged on some engines"; Broad = $false }
    @{ Name = "trivy.exe";  Why = "rarely - own binary or a scanned image layer"; Broad = $false }
    @{ Name = "sqlmap.py";  Why = "the flagged script itself"; Broad = $false }
    @{ Name = "perl.exe";   Why = "nikto's interpreter - WIDER than the rest"; Broad = $true }
    @{ Name = "java.exe";   Why = "ZAP's runtime - WIDER than the rest"; Broad = $true }
)

if ($NoInterpreterExclusions) {
    $ProcessExclusions = $ProcessExclusions | Where-Object { -not $_.Broad }
}

# --- guards ----------------------------------------------------------------

function Test-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Assert-NarrowPath {
    # A typo or an unset environment variable could turn one of the paths above
    # into something catastrophic - "$env:LOCALAPPDATA\Programs" with
    # LOCALAPPDATA empty becomes "\Programs", and a drive root or profile root
    # exclusion would disable Defender across everything underneath it. Refuse
    # rather than trust the construction.
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    $full = [IO.Path]::GetFullPath($Path)
    $forbidden = @(
        $env:USERPROFILE, $env:LOCALAPPDATA, $env:APPDATA, $env:ProgramFiles,
        ${env:ProgramFiles(x86)}, $env:SystemRoot, $env:SystemDrive,
        "$env:SystemDrive\", (Join-Path $env:LOCALAPPDATA "Programs")
    ) | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('\') }
    if ($forbidden -contains $full.TrimEnd('\')) { return $false }
    # At least three path segments - C:\Users\x is two and still far too broad.
    if (($full.TrimEnd('\') -split '\\').Count -lt 3) { return $false }
    return $true
}

if (-not (Get-Command Get-MpPreference -ErrorAction SilentlyContinue)) {
    Write-Host "!! Defender cmdlets are not available on this machine." -ForegroundColor Yellow
    Write-Host "   This is normal on Windows Server without the Defender feature, or" -ForegroundColor Yellow
    Write-Host "   where a third-party AV has replaced it. See section 4 of" -ForegroundColor Yellow
    Write-Host "   docs/antivirus-exclusions.md for CrowdStrike / SentinelOne / MDE." -ForegroundColor Yellow
    exit 2
}

# Reject any path that failed the narrowness guard, loudly - never silently.
$bad = $PathExclusions | Where-Object { -not (Assert-NarrowPath $_.Path) }
if ($bad) {
    Write-Host "!! Refusing to run: these paths are too broad to exclude safely." -ForegroundColor Red
    $bad | ForEach-Object { Write-Host "   $($_.Path)" -ForegroundColor Red }
    Write-Host "   That usually means an environment variable is unset." -ForegroundColor Red
    exit 1
}

$current = Get-MpPreference
$havePath = @($current.ExclusionPath)
$haveProc = @($current.ExclusionProcess)

# --- preview / apply / remove ----------------------------------------------

$mode = if ($Remove) { "REMOVE" } elseif ($Apply) { "APPLY" } else { "PREVIEW" }
Write-Host ""
Write-Host "gizmoduck Defender exclusions - $mode" -ForegroundColor Cyan
Write-Host ("-" * 72)

if ($mode -ne "PREVIEW" -and -not (Test-Elevated)) {
    Write-Host "!! Add-MpPreference needs an elevated prompt. Re-run as Administrator." -ForegroundColor Red
    exit 1
}

$changed = 0

foreach ($e in $PathExclusions) {
    $present = $havePath -contains $e.Path
    switch ($mode) {
        "PREVIEW" {
            $state = if ($present) { "already set" } else { "would add " }
            Write-Host ("  path  {0}  {1}" -f $state, $e.Path)
            Write-Host ("         reason: {0}" -f $e.Why) -ForegroundColor DarkGray
        }
        "APPLY" {
            if ($present) { Write-Host ("  path  already set  {0}" -f $e.Path) }
            else {
                Add-MpPreference -ExclusionPath $e.Path
                Write-Host ("  path  ADDED       {0}" -f $e.Path) -ForegroundColor Green
                $changed++
            }
        }
        "REMOVE" {
            if (-not $present) { Write-Host ("  path  not set     {0}" -f $e.Path) }
            else {
                Remove-MpPreference -ExclusionPath $e.Path
                Write-Host ("  path  REMOVED     {0}" -f $e.Path) -ForegroundColor Yellow
                $changed++
            }
        }
    }
}

foreach ($e in $ProcessExclusions) {
    $present = $haveProc -contains $e.Name
    $tag = if ($e.Broad) { " [WIDE]" } else { "" }
    switch ($mode) {
        "PREVIEW" {
            $state = if ($present) { "already set" } else { "would add " }
            Write-Host ("  proc  {0}  {1}{2}" -f $state, $e.Name, $tag)
            Write-Host ("         reason: {0}" -f $e.Why) -ForegroundColor DarkGray
        }
        "APPLY" {
            if ($present) { Write-Host ("  proc  already set  {0}{1}" -f $e.Name, $tag) }
            else {
                Add-MpPreference -ExclusionProcess $e.Name
                Write-Host ("  proc  ADDED       {0}{1}" -f $e.Name, $tag) -ForegroundColor Green
                $changed++
            }
        }
        "REMOVE" {
            if (-not $present) { Write-Host ("  proc  not set     {0}" -f $e.Name) }
            else {
                Remove-MpPreference -ExclusionProcess $e.Name
                Write-Host ("  proc  REMOVED     {0}{1}" -f $e.Name, $tag) -ForegroundColor Yellow
                $changed++
            }
        }
    }
}

Write-Host ("-" * 72)

if (-not $NoInterpreterExclusions) {
    Write-Host ""
    Write-Host "NOTE: perl.exe and java.exe are general-purpose interpreters, so those two" -ForegroundColor Yellow
    Write-Host "      exclusions are wider than the rest - anything run through them is" -ForegroundColor Yellow
    Write-Host "      excluded, not just nikto and ZAP. Re-run with -NoInterpreterExclusions" -ForegroundColor Yellow
    Write-Host "      to skip them, but expect nikto and ZAP to be killed mid-scan." -ForegroundColor Yellow
}

if ($mode -eq "PREVIEW") {
    Write-Host ""
    Write-Host "Nothing was changed. Re-run with -Apply (elevated) to register these." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "$changed exclusion(s) changed. Verify with:" -ForegroundColor Cyan
    Write-Host "  Get-MpPreference | Select-Object -ExpandProperty ExclusionPath"
    Write-Host "  Get-MpPreference | Select-Object -ExpandProperty ExclusionProcess"
}
