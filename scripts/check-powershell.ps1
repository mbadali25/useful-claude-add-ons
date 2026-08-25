<#
    Static checks on install-prerequisites.ps1 that a syntax parse does not catch.

    The script is Windows-only end to end, so most of it cannot be exercised on a CI
    runner - which means a call to a function that does not exist parses cleanly, runs
    fine on Linux (never reached), and dies on the one platform that matters. That is
    exactly how a call to a mis-named picker function shipped: PowerShell resolves
    command names at *call* time, $ErrorActionPreference is 'Stop', and the caller
    swallows the exception, so the whole cursor menu just silently stopped working.

    Exit 0 when clean, 1 otherwise.
#>
param([string]$Path = (Join-Path $PSScriptRoot 'install-prerequisites.ps1'))

$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $Path), [ref]$null, [ref]$errors)
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

# Names that legitimately come from a module the script imports at runtime, so they
# cannot resolve on a CI runner. Keep this list short and say where each one comes from -
# an entry added to silence a genuine typo defeats the whole check.
$externallyProvided = @{
    # Chocolatey's helpers\chocolateyProfile.psm1, Import-Module'd a few lines above the
    # call and wrapped in try/catch for exactly the case where it is absent.
    'Update-SessionEnvironment' = 'chocolateyProfile.psm1'
}

$problems = @()
foreach ($call in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
    $name = $call.GetCommandName()
    if (-not $name) { continue }                 # invoked via & or a variable
    if ($defined.Contains($name)) { continue }
    if ($externallyProvided.ContainsKey($name)) { continue }
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
