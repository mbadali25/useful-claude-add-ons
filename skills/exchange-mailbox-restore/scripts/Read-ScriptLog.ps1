#Requires -PSEdition Desktop
<#
.SYNOPSIS
    Read back a log or CSV the Exchange driver scripts wrote, decoding defensively.

.DESCRIPTION
    Reads a log or CSV a driver script wrote, decoding defensively. Windows PowerShell
    5.1 only, so the skill needs nothing but the in-box shell. Never touches the tenant.

    Under 5.1 the driver scripts write their *.csv with Export-Csv -Encoding UTF8
    (UTF-8 with a BOM) but their *.log with Add-Content and no -Encoding, which lands
    in the ANSI code page (cp1252). No parameter the skill prints can change that. A
    reader that assumes UTF-8 turns every accented display name, smart quote or em
    dash into mojibake silently, with no error.

    Decode order, same as the Python original:
      1. UTF-16 BOM (FF FE / FE FF)          - unambiguous, wins outright
      2. BOM-less UTF-16 by NUL position      - a stray '>' that lost its BOM; BEFORE UTF-8,
                                                because NUL is a valid UTF-8 byte
      3. UTF-8, strict, BOM optional          - what Export-Csv -Encoding UTF8 writes
      4. cp1252                               - what Add-Content writes; never fails, so last

    Output is UTF-8 on the console regardless of the code page, so the skill reads the
    same bytes back that were decoded.

.PARAMETER Path
    Log or CSV file, usually under C:\scripts\logs or C:\scripts\reports.

.PARAMETER Tail
    Only the last N lines.

.PARAMETER Grep
    Only lines containing this text, case-insensitive.

.PARAMETER AsJson
    Emit {path, encoding, lines} as JSON instead of plain lines.

.EXAMPLE
    powershell.exe -NoProfile -File .\Read-ScriptLog.ps1 -Path C:\scripts\logs\Invoke-M365OffboardingHold-20260910.log -Tail 40

.EXAMPLE
    powershell.exe -NoProfile -File .\Read-ScriptLog.ps1 -Path C:\scripts\logs\MailboxPreservation-202609101455.csv -Grep NotPreserved -AsJson

.OUTPUTS
    System.String - decoded lines (or one JSON document with -AsJson). A "# path (encoding)"
    summary goes to stderr. Exit 0 read and decoded, 2 file missing or unreadable.

.NOTES
    Version: 1.0   Author: Infrastructure Team   Date: 2026-09-10
    ASCII-only source on purpose: PSScriptAnalyzer's BOM rule and 5.1's Get-Content default
    both bite a UTF-8 file without a BOM.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [string]$Path,

    [int]$Tail,

    [string]$Grep,

    [switch]$AsJson
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Test-Utf16WithoutBom {
    # Return 'utf-16-le', 'utf-16-be' or $null by looking at where the NULs sit.
    # ASCII text in UTF-16LE is 'A\0B\0' - NULs at odd offsets; UTF-16BE puts them at even.
    param([byte[]]$Raw)
    $head = $Raw
    if ($Raw.Length -gt 4096) { $head = $Raw[0..4095] }
    if ($head.Length -lt 4) { return $null }
    if (-not ($head -contains 0)) { return $null }
    $odd = 0
    $even = 0
    for ($i = 0; $i -lt $head.Length; $i++) {
        if ($head[$i] -eq 0) {
            if ($i % 2 -eq 1) { $odd++ } else { $even++ }
        }
    }
    $half = [math]::Floor($head.Length / 2)
    if ($half -eq 0) { return $null }
    if (($odd / $half) -gt 0.3 -and $odd -gt $even) { return 'utf-16-le' }
    if (($even / $half) -gt 0.3 -and $even -gt $odd) { return 'utf-16-be' }
    return $null
}

function ConvertFrom-LogByte {
    # Returns @{ Text = ...; Encoding = ... }. Order matters; cp1252 never fails so it is last.
    param([byte[]]$Raw)

    if ($Raw.Length -ge 2 -and $Raw[0] -eq 0xFF -and $Raw[1] -eq 0xFE) {
        return @{ Text = [System.Text.Encoding]::Unicode.GetString($Raw, 2, $Raw.Length - 2); Encoding = 'utf-16' }
    }
    if ($Raw.Length -ge 2 -and $Raw[0] -eq 0xFE -and $Raw[1] -eq 0xFF) {
        return @{ Text = [System.Text.Encoding]::BigEndianUnicode.GetString($Raw, 2, $Raw.Length - 2); Encoding = 'utf-16' }
    }

    $offset = 0
    if ($Raw.Length -ge 3 -and $Raw[0] -eq 0xEF -and $Raw[1] -eq 0xBB -and $Raw[2] -eq 0xBF) { $offset = 3 }

    # BOM-less UTF-16 is tested BEFORE strict UTF-8 on purpose: NUL is a valid UTF-8 byte, so
    # 'h\0i\0' decodes as UTF-8 "successfully" into text riddled with NULs and nobody is told.
    if ($offset -eq 0) {
        $guess = Test-Utf16WithoutBom -Raw $Raw
        if ($guess -eq 'utf-16-le') {
            return @{ Text = [System.Text.Encoding]::Unicode.GetString($Raw); Encoding = 'utf-16-le' }
        }
        if ($guess -eq 'utf-16-be') {
            return @{ Text = [System.Text.Encoding]::BigEndianUnicode.GetString($Raw); Encoding = 'utf-16-be' }
        }
    }

    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)   # throwOnInvalidBytes
    try {
        return @{ Text = $strictUtf8.GetString($Raw, $offset, $Raw.Length - $offset); Encoding = 'utf-8-sig' }
    } catch [System.ArgumentException] {
        Write-Verbose -Message 'not valid UTF-8; falling back to cp1252'
    }

    return @{ Text = [System.Text.Encoding]::GetEncoding(1252).GetString($Raw); Encoding = 'cp1252' }
}

# Emit UTF-8 whatever the console code page is, or a cp1252 console re-mangles exactly the
# characters this script exists to decode. Same reason the Python version reconfigures stdout.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$resolved = $null
try {
    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).ProviderPath
    $raw = [System.IO.File]::ReadAllBytes($resolved)
} catch {
    Write-Error -Message "could not read $Path : $($_.Exception.Message)" -ErrorId 'LogUnreadable' -Category ReadError -ErrorAction Continue
    exit 2
}

$decoded = ConvertFrom-LogByte -Raw $raw
$lines = @($decoded.Text -split "`r?`n")
# a trailing newline yields one empty final element; drop it like splitlines() does
if ($lines.Count -gt 0 -and $lines[-1] -eq '') { $lines = @($lines[0..($lines.Count - 2)]) }

if ($Grep) {
    $lines = @($lines | Where-Object { $_.IndexOf($Grep, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 })
}
if ($Tail -gt 0 -and $lines.Count -gt $Tail) {
    $lines = @($lines[($lines.Count - $Tail)..($lines.Count - 1)])
}

if ($AsJson) {
    $doc = [ordered]@{ path = $resolved; encoding = $decoded.Encoding; lines = $lines }
    # -Depth matters on 5.1: the default of 2 would flatten nested objects without warning.
    Write-Output ($doc | ConvertTo-Json -Depth 4)
} else {
    # stderr on purpose, like the Python original: stdout carries only the decoded lines
    [Console]::Error.WriteLine("# $resolved  ($($decoded.Encoding), $($lines.Count) line(s) shown)")
    foreach ($line in $lines) { Write-Output $line }
}
exit 0
