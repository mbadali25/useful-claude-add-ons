<#
    Static checks on this repository's PowerShell that a syntax parse does not catch.

    Every .ps1 here is Windows-only end to end, so most of it cannot be exercised on
    a CI runner - which means a call to a function that does not exist parses cleanly,
    runs fine on Linux (never reached), and dies on the one platform that matters.
    That is exactly how a call to a mis-named picker function shipped: PowerShell
    resolves command names at *call* time, $ErrorActionPreference is 'Stop', and the
    caller swallows the exception, so the whole cursor menu just silently stopped
    working.

    With no -Path it checks every tracked .ps1, not just the installer. It used to
    default to install-prerequisites.ps1 alone, which left the crew plugin's hook
    scripts - the ones that run on somebody else's machine, from a hook, where a
    thrown exception is invisible - completely unguarded.

    A file that gets its functions by dot-sourcing another one will report them as
    unresolvable; there are none, and the crew hooks duplicate their helpers inline
    rather than dot-source precisely so this check keeps working.

    Exit 0 when clean, 1 otherwise.
#>
param([string]$Path)

if (-not $Path) {
    $repo = Split-Path $PSScriptRoot -Parent
    Push-Location $repo
    try { $files = @(git ls-files '*.ps1') } finally { Pop-Location }
    if (-not $files) {
        Write-Host "no .ps1 files tracked in $repo - nothing to check"
        exit 0
    }
    $failed = 0
    foreach ($f in $files) {
        & $PSCommandPath -Path (Join-Path $repo $f)
        if ($LASTEXITCODE -ne 0) { $failed++ }
    }
    if ($failed -gt 0) {
        Write-Host "$failed of $($files.Count) PowerShell file(s) failed the static check"
        exit 1
    }
    Write-Host "$($files.Count) PowerShell file(s) checked, all clean"
    exit 0
}

$resolvedPath = (Resolve-Path $Path).Path
# The path a scoped exemption is matched against. Normalised to forward slashes
# because this is invoked with both flavours - the no-Path branch above builds
# backslash paths with Join-Path, a hook or a shell invokes it with '/' - and a
# glob written one way must not silently stop matching the other.
$scopePath = $resolvedPath -replace '\\', '/'

$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $resolvedPath, [ref]$null, [ref]$errors)
if ($errors) {
    foreach ($e in $errors) {
        Write-Host "::error file=$Path,line=$($e.Extent.StartLineNumber)::$($e.Message)"
    }
    exit 1
}

# Functions the script defines itself.
$defined = [System.Collections.Generic.HashSet[string]]::new(
    [string[]]@($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true) |
        ForEach-Object { $_.Name }),
    [StringComparer]::OrdinalIgnoreCase)

# Everything the Exchange skills' scripts pull out of a session-materialised or
# RSAT-only module. Named once and shared by every entry scoped below, so the scope
# is stated in one place rather than repeated twenty-three times and drifting.
# Matched against a forward-slash path with -like, case-insensitively.
$exchangeSkillScripts = @(
    '*/skills/exchange-mailbox-cleanup/scripts/*'
    '*/skills/exchange-mailbox-restore/scripts/*'
)
$exoSession  = @{ Module = 'ExchangeOnlineManagement (session-materialised)'; Paths = $exchangeSkillScripts }
$exoManifest = @{ Module = 'ExchangeOnlineManagement (manifest-exported)';    Paths = $exchangeSkillScripts }
$graphSdk    = @{ Module = 'Microsoft.Graph (PowerShell SDK, not preinstalled)'; Paths = $exchangeSkillScripts }
$adRsat      = @{ Module = 'ActiveDirectory (RSAT, Windows-only)';            Paths = $exchangeSkillScripts }

# Names that legitimately come from a module the script imports at runtime, so they
# cannot resolve on a CI runner. Keep this list short and say where each one comes from -
# an entry added to silence a genuine typo defeats the whole check.
#
# A value is either a plain string - the module, and the exemption applies to every
# file this checker scans - or a hashtable @{ Module = '...'; Paths = @(globs) },
# which exempts the name ONLY in files matching one of those globs. Prefer the scoped
# form for anything that is unresolvable because of where it is called from rather
# than on every machine: a flat global list meant a typo'd Get-ADUser in an unrelated
# script was exempt by a decision made about the Exchange skills.
$externallyProvided = @{
    # Chocolatey's helpers\chocolateyProfile.psm1, Import-Module'd a few lines above the
    # call and wrapped in try/catch for exactly the case where it is absent.
    'Update-SessionEnvironment' = 'chocolateyProfile.psm1'
    # The ScheduledTasks module ships with Windows and does not exist on Linux, so
    # these resolve for a developer running this check and not for the CI runner.
    # Listed by exact name rather than by a '*-ScheduledTask*' pattern, so a typo
    # in one of them is still caught. vault-automation/setup-vault-automation.ps1.
    'Get-ScheduledTask'             = 'ScheduledTasks (Windows-only)'
    'New-ScheduledTaskAction'       = 'ScheduledTasks (Windows-only)'
    'New-ScheduledTaskTrigger'      = 'ScheduledTasks (Windows-only)'
    'New-ScheduledTaskPrincipal'    = 'ScheduledTasks (Windows-only)'
    'New-ScheduledTaskSettingsSet'  = 'ScheduledTasks (Windows-only)'
    'Register-ScheduledTask'        = 'ScheduledTasks (Windows-only)'
    'Start-ScheduledTask'           = 'ScheduledTasks (Windows-only)'
    # Here for a DIFFERENT reason than everything above, which is why it is
    # commented separately: nvidia-smi is not a cmdlet from an unimportable
    # module, it is an ordinary external binary shipped with the NVIDIA driver.
    # The Verb-Noun filter below is what drags it in - `nvidia-smi` matches
    # '^[A-Za-z]+-[A-Za-z0-9]+$' as cleanly as `Get-ChildItem` does, so a bare
    # program with a hyphen in its name gets judged as a cmdlet. It resolves on
    # any machine with the driver and on no CI runner, so this check passed
    # locally and failed only on CI. plugin/localgpu/bootstrap.ps1.
    #
    # Fixing the filter to demand an approved verb (Get-Verb) would cover every
    # hyphenated binary at once - docker-compose, pip-compile - but it would
    # also stop judging a typo like 'Gett-ChildItem', whose verb is equally
    # unapproved. That trades one false positive for a class of false
    # negatives, so the name goes here instead.
    'nvidia-smi'                    = 'NVIDIA driver (external binary, not a cmdlet)'
    # ExchangeOnlineManagement, and here for a THIRD reason - not "the module is
    # absent" and not "this is a bare binary", but "the module is present and
    # still does not export these". EXO 3.x materialises its REST-backed cmdlets
    # into the session only after Connect-ExchangeOnline. Measured on 3.10.1: the
    # manifest exports 36 commands, Connect-ExchangeOnline among them, and NOT
    # ONE of the names below. So no static check can resolve them on any machine,
    # connected or not, and "install the module" is a fix that changes nothing -
    # which is the trap, because it is the obvious reading of the failure.
    # Re-measure with (Get-Module -ListAvailable ExchangeOnlineManagement).ExportedCommands
    # rather than trusting that count; it is a fact about one version.
    # Scoped, not global: unresolvable everywhere is a property of the module, but
    # being ACCEPTABLE is a property of the caller. These are only called from the
    # two Exchange skills, so that is where the exemption reaches.
    'Add-DistributionGroupMember'       = $exoSession
    'Add-eDiscoveryCaseAdmin'           = $exoSession
    'Add-MailboxPermission'             = $exoSession
    'Add-RoleGroupMember'               = $exoSession
    'Get-ComplianceSearch'              = $exoSession
    'Get-DistributionGroup'             = $exoSession
    'Get-DistributionGroupMember'       = $exoSession
    'Get-Mailbox'                       = $exoSession
    'Get-MailboxStatistics'             = $exoSession
    'Get-RoleGroup'                     = $exoSession
    'Get-RoleGroupMember'               = $exoSession
    'Get-User'                          = $exoSession
    'New-ComplianceSearch'              = $exoSession
    'New-DistributionGroup'             = $exoSession
    'Remove-ComplianceSearch'           = $exoSession
    'Set-DistributionGroup'             = $exoSession
    'Set-Mailbox'                       = $exoSession
    'Set-MailboxAutoReplyConfiguration' = $exoSession
    'Start-ComplianceSearch'            = $exoSession
    # ExchangeOnlineManagement again, and deliberately NOT folded into the block above,
    # because the reason is the opposite one and merging them would make that comment
    # false. These nine ARE exported by the manifest - the three Connect-/Disconnect-
    # names as Functions, the other six as Cmdlets - so they resolve after a bare
    # Import-Module, before any connection. Measured on 3.10.1 from
    # C:\Program Files\WindowsPowerShell\Modules\ExchangeOnlineManagement\3.10.1.
    #
    # That difference is the whole reason they went unnoticed: on a box with the module
    # installed they resolve and this check is silent, and on the CI runner the module
    # is absent entirely so all nine fail at once. So a green local run proves nothing
    # about them. Reproduce CI's view here with
    #   PSModulePath="" pwsh -NoProfile -File scripts/check-powershell.ps1
    # which drops the WindowsPowerShell compat path where the module lives; that is the
    # environment scripts/_test/check-powershell.sh runs their cases under, precisely
    # so an allow-case for them is not vacuous on the machine that resolves them.
    'Connect-ExchangeOnline'            = $exoManifest
    'Connect-IPPSSession'               = $exoManifest
    'Disconnect-ExchangeOnline'         = $exoManifest
    'Get-ConnectionInformation'         = $exoManifest
    'Get-EXOMailbox'                    = $exoManifest
    'Get-EXOMailboxPermission'          = $exoManifest
    'Get-EXOMailboxStatistics'          = $exoManifest
    'Get-EXORecipient'                  = $exoManifest
    'Get-EXORecipientPermission'        = $exoManifest
    # The Microsoft.Graph SDK, same shape as the manifest-exported names above -
    # ordinary exported cmdlets that resolve wherever the SDK is installed and nowhere
    # it is not, which on ubuntu-latest is nowhere. Found by running the CI-equivalent
    # command above rather than from the CI log, which named only the EXO nine; these
    # five fail identically and in the same four files, so fixing only the nine would
    # have left the step red and looked like the fix had not worked.
    # Callers: exo_preflight.ps1 and vendored/{Get-M365OffboardingStatus,
    # Invoke-M365OffboardingHold}.ps1 under both Exchange skills.
    'Get-MgSubscribedSku'               = $graphSdk
    'Get-MgUser'                        = $graphSdk
    'Get-MgUserMemberOf'                = $graphSdk
    'Revoke-MgUserSignInSession'        = $graphSdk
    'Set-MgUserLicense'                 = $graphSdk
    # The same SDK's authentication module, and listed after the five above because
    # they were found only on the SECOND pass, by a scrub that was wrong the first
    # time. Emptying PSModulePath from OUTSIDE pwsh does not stay empty: pwsh
    # repopulates three defaults at startup, one of them the per-user
    # Documents\PowerShell\Modules, which is where Microsoft.Graph.Authentication is
    # installed on this box while the other Graph modules are under
    # WindowsPowerShell\Modules. So the outside scrub hid those and left these
    # resolving, and the scan reported clean against a tree that still failed CI.
    # Setting $env:PSModulePath='' INSIDE the session is what actually empties it.
    # Verified 2.39.0: all three are Cmdlets in the module's ExportedCommands, so
    # they resolve after a bare Import-Module, exactly like the nine EXO names.
    'Connect-MgGraph'                   = $graphSdk
    'Disconnect-MgGraph'                = $graphSdk
    'Get-MgContext'                     = $graphSdk
    # The ActiveDirectory module ships in RSAT, so it is absent on a CI runner and
    # on any Windows box without the feature installed - the same shape as the
    # ScheduledTasks entries above, listed separately only because it is a
    # different module. Scoped to the same two skills as the EXO names.
    #
    # This comment used to read "skills/exchange-mailbox-restore/scripts/**", which
    # is wrong: every one of these four is called from
    # skills/exchange-mailbox-cleanup/scripts/vendored/Invoke-M365OffboardingHold.ps1
    # and from nothing under restore. Re-measure by parsing the call sites rather
    # than trusting either reading - a scope derived from a wrong comment would have
    # turned the genuine callers red.
    'Disable-ADAccount'                 = $adRsat
    'Get-ADDomain'                      = $adRsat
    'Get-ADUser'                        = $adRsat
    'Set-ADUser'                        = $adRsat
}

$problems = @()
foreach ($call in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
    $name = $call.GetCommandName()
    if (-not $name) { continue }                 # invoked via & or a variable
    if ($defined.Contains($name)) { continue }
    if ($externallyProvided.ContainsKey($name)) {
        $entry = $externallyProvided[$name]
        # A plain string is a global exemption; a hashtable carries the globs it is
        # limited to. Out of scope falls through to the checks below and is reported
        # like any other unresolvable name.
        if ($entry -is [string]) { continue }
        $inScope = $false
        foreach ($glob in $entry.Paths) {
            if ($scopePath -like $glob) { $inScope = $true; break }
        }
        if ($inScope) { continue }
    }
    # Only judge Verb-Noun names: a bare 'git' or 'claude' is an external program, and
    # whether it exists is a runtime question, not a spelling one.
    if ($name -notmatch '^[A-Za-z]+-[A-Za-z0-9]+$') { continue }
    if (Get-Command $name -ErrorAction SilentlyContinue) { continue }
    $problems += "line $($call.Extent.StartLineNumber): calls '$name', which this script does not define and PowerShell cannot resolve"
}

if ($problems.Count -gt 0) {
    Write-Host "$Path"
    foreach ($p in ($problems | Sort-Object -Unique)) {
        Write-Host "  - $p"
        Write-Host "::error file=$Path::$p"
    }
    exit 1
}

Write-Host "$Path : parse ok, $($defined.Count) functions defined, every Verb-Noun call resolves"
exit 0
