#Requires -PSEdition Desktop
<#
.SYNOPSIS
    Normalise operator input for the Exchange mailbox skills - one address or a CSV.

.DESCRIPTION
    Windows PowerShell 5.1 port of parse_user_input.py, so the skill needs nothing but
    the in-box shell. Never touches the tenant.

    Accepts a single email address / UPN, or the path to a CSV or text file, and writes
    the one-column CSV (header UserPrincipalName) that Invoke-M365OffboardingHold.ps1
    -UserList and Import-Csv both read correctly. Output is UTF-8 WITH a BOM: 5.1's
    Import-Csv assumes the ANSI code page without one and turns every accented name
    into mojibake.

    The input file is decoded defensively (UTF-16 BOM, BOM-less UTF-16, strict UTF-8,
    then cp1252), so an HR export saved from Excel as ANSI reads correctly too. The
    address column is auto-detected (UserPrincipalName, EmailAddress, Email,
    PrimarySmtpAddress, mail, upn ...). Bad rows are reported with their line number
    and reason rather than dropped - a curated leaver list that quietly lost a row is
    worse than one that refused to parse.

.PARAMETER Value
    A single address/UPN, or the path to a CSV or text file.

.PARAMETER EmailColumn
    CSV column holding the address. Auto-detected when omitted.

.PARAMETER OutPath
    Write the normalised one-column CSV here (UTF-8 with BOM, CRLF). Parent directory
    is created if missing.

.PARAMETER AsJson
    Print the summary as JSON.

.EXAMPLE
    powershell.exe -NoProfile -File .\Resolve-OperatorInput.ps1 -Value j.doe@contoso.com -OutPath C:\scripts\reports\holdlist.csv

.EXAMPLE
    powershell.exe -NoProfile -File .\Resolve-OperatorInput.ps1 -Value C:\temp\hr-export.csv -EmailColumn "Work Email" -AsJson

.OUTPUTS
    Summary text, or one JSON document with -AsJson. Exit codes:
      0  every row valid; output written if -OutPath given
      1  no valid addresses at all
      2  bad input: file missing, unreadable, no header, or no address column found
      3  valid rows written but at least one row rejected - show the operator the rejected
         rows and ask before proceeding with the subset

.NOTES
    Version: 1.0   Author: Infrastructure Team   Date: 2026-09-10
    ASCII-only source on purpose (see Read-ScriptLog.ps1).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [string]$Value,

    [string]$EmailColumn,

    [string]$OutPath,

    [switch]$AsJson
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$CandidateColumn = @(
    'UserPrincipalName', 'userPrincipalName', 'user_principal_name', 'upn', 'UPN',
    'EmailAddress', 'Email', 'email', 'mail', 'Mail', 'PrimarySmtpAddress',
    'primary_email', 'Work Email', 'WorkEmail'
)
# Deliberately loose: one @, no whitespace, a dotted domain. Exchange validates the rest.
$AddressPattern = '^[^@\s]+@[^@\s]+\.[^@\s]+$'

function ConvertFrom-InputByte {
    # Same decode order as Read-ScriptLog.ps1. Returns the text only.
    param([byte[]]$Raw)
    if ($Raw.Length -ge 2 -and $Raw[0] -eq 0xFF -and $Raw[1] -eq 0xFE) { return [System.Text.Encoding]::Unicode.GetString($Raw, 2, $Raw.Length - 2) }
    if ($Raw.Length -ge 2 -and $Raw[0] -eq 0xFE -and $Raw[1] -eq 0xFF) { return [System.Text.Encoding]::BigEndianUnicode.GetString($Raw, 2, $Raw.Length - 2) }
    $offset = 0
    if ($Raw.Length -ge 3 -and $Raw[0] -eq 0xEF -and $Raw[1] -eq 0xBB -and $Raw[2] -eq 0xBF) { $offset = 3 }
    # BOM-less UTF-16 must be tested BEFORE strict UTF-8: NUL is a valid UTF-8 byte, so
    # 'h\0i\0' decodes as UTF-8 "successfully" into text riddled with NULs.
    if ($offset -eq 0) {
        $nul = 0
        $limit = [math]::Min($Raw.Length, 4096)
        for ($i = 1; $i -lt $limit; $i += 2) { if ($Raw[$i] -eq 0) { $nul++ } }
        if ($limit -ge 4 -and ($nul / [math]::Floor($limit / 2)) -gt 0.3) { return [System.Text.Encoding]::Unicode.GetString($Raw) }
    }
    $strict = New-Object System.Text.UTF8Encoding($false, $true)
    try {
        return $strict.GetString($Raw, $offset, $Raw.Length - $offset)
    } catch [System.ArgumentException] {
        Write-Verbose -Message 'not valid UTF-8; falling back to cp1252'
    }
    return [System.Text.Encoding]::GetEncoding(1252).GetString($Raw)
}

function Test-Address {
    # Returns @{ Address = <normalised>; Reason = $null } or @{ Address = $null; Reason = <why> }
    param([string]$Raw)
    $v = ''
    if ($null -ne $Raw) { $v = $Raw.Trim().Trim('"').Trim("'") }
    if ($v -eq '') { return @{ Address = $null; Reason = 'empty' } }
    # @( ) matters under StrictMode: a single match is a scalar [char] with no .Count on 5.1.
    $at = @($v.ToCharArray() | Where-Object { $_ -eq '@' }).Count
    if ($at -ne 1) { return @{ Address = $null; Reason = "expected exactly one '@', got $at" } }
    if ($v -match '\s') { return @{ Address = $null; Reason = 'contains whitespace' } }
    if ($v -notmatch $AddressPattern) { return @{ Address = $null; Reason = 'not shaped like user@domain.tld' } }
    return @{ Address = $v.ToLowerInvariant(); Reason = $null }
}

function Find-AddressColumn {
    param([string[]]$Header, [string]$Explicit)
    if ($Explicit) {
        return ($Header | Where-Object { $_.Trim().ToLowerInvariant() -eq $Explicit.Trim().ToLowerInvariant() } | Select-Object -First 1)
    }
    foreach ($cand in $CandidateColumn) {
        $hit = $Header | Where-Object { $_.Trim().ToLowerInvariant() -eq $cand.ToLowerInvariant() } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    return $null
}

function Read-InputFile {
    # Returns @{ Rows = @(@{ Line = n; Value = s }, ...); Column = <name or description> }.
    # Throws with a plain message on a structural problem.
    param([string]$FilePath, [string]$Explicit)
    $raw = [System.IO.File]::ReadAllBytes($FilePath)
    $text = ConvertFrom-InputByte -Raw $raw
    $lines = @($text -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
    if ($lines.Count -eq 0) { throw "$FilePath is empty" }

    $sample = $text
    if ($text.Length -gt 4096) { $sample = $text.Substring(0, 4096) }
    $delimiter = $null
    foreach ($d in @(',', ';', "`t")) { if ($sample.IndexOf($d) -ge 0) { $delimiter = $d; break } }

    if ($null -eq $delimiter) {
        # One column: a bare address list, or a one-column CSV whose only line without an
        # '@' is a recognised header. Skip that header rather than reporting it as a bad row.
        $rows = @()
        for ($i = 0; $i -lt $lines.Count; $i++) { $rows += @{ Line = $i + 1; Value = $lines[$i] } }
        $first = $lines[0].Trim().Trim('"')
        $isHeader = ($first.IndexOf('@') -lt 0) -and (($CandidateColumn | ForEach-Object { $_.ToLowerInvariant() }) -contains $first.ToLowerInvariant())
        if ($isHeader) {
            if ($rows.Count -gt 1) { return @{ Rows = @($rows[1..($rows.Count - 1)]); Column = $first } }
            return @{ Rows = @(); Column = $first }
        }
        return @{ Rows = $rows; Column = '(one address per line)' }
    }

    $parsed = @($lines | ConvertFrom-Csv -Delimiter $delimiter)
    $header = @(($lines[0] -split [regex]::Escape($delimiter)) | ForEach-Object { $_.Trim().Trim('"') })
    if ($header.Count -eq 0) { throw "$FilePath has no header row" }
    $column = Find-AddressColumn -Header $header -Explicit $Explicit
    if ($null -eq $column) {
        if ($Explicit) { throw "column '$Explicit' not in $FilePath. Columns present: $($header -join ', ')" }
        throw "could not find an address column in $FilePath. Columns present: $($header -join ', '). Specify one with -EmailColumn."
    }
    $rows = @()
    for ($i = 0; $i -lt $parsed.Count; $i++) {
        $cell = ''
        # PSObject.Properties[] rather than .$column: a ragged row lacks the property and
        # StrictMode would throw PropertyNotFoundStrict instead of reporting the bad row.
        $prop = $parsed[$i].PSObject.Properties[$column]
        if ($null -ne $prop -and $null -ne $prop.Value) { $cell = [string]$prop.Value }
        # ConvertFrom-Csv consumed the header as line 1; data starts at line 2.
        $rows += @{ Line = $i + 2; Value = $cell }
    }
    return @{ Rows = $rows; Column = $column }
}

[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$trimmed = $Value.Trim()
$source = ''
$column = $null
$rows = @()

if ((Test-Path -LiteralPath $trimmed -PathType Leaf)) {
    try {
        $parsedFile = Read-InputFile -FilePath (Resolve-Path -LiteralPath $trimmed).ProviderPath -Explicit $EmailColumn
    } catch {
        Write-Error -Message $_.Exception.Message -ErrorId 'InputUnreadable' -Category InvalidData -ErrorAction Continue
        exit 2
    }
    $rows = @($parsedFile.Rows)
    $column = $parsedFile.Column
    $source = (Resolve-Path -LiteralPath $trimmed).ProviderPath
} elseif ($trimmed.IndexOf('@') -ge 0) {
    $rows = @(@{ Line = 1; Value = $trimmed })
    $source = '(single address)'
} else {
    Write-Error -Message "'$trimmed' is neither an existing file nor an email address" -ErrorId 'InputUnrecognised' -Category InvalidArgument -ErrorAction Continue
    exit 2
}

$valid = New-Object System.Collections.ArrayList
$seen = @{}
$rejected = New-Object System.Collections.ArrayList
$duplicate = New-Object System.Collections.ArrayList
foreach ($row in $rows) {
    $check = Test-Address -Raw $row.Value
    if ($null -eq $check.Address) {
        $shown = ''
        if ($null -ne $row.Value) { $shown = ([string]$row.Value).Trim() }
        [void]$rejected.Add([ordered]@{ line = $row.Line; value = $shown; reason = $check.Reason })
        continue
    }
    if ($seen.ContainsKey($check.Address)) {
        [void]$duplicate.Add([ordered]@{ line = $row.Line; value = $check.Address })
        continue
    }
    $seen[$check.Address] = $true
    [void]$valid.Add($check.Address)
}

$written = $null
if ($valid.Count -gt 0 -and $OutPath) {
    try {
        $parent = Split-Path -Parent $OutPath
        if ($parent -and -not (Test-Path -LiteralPath $parent -PathType Container)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        $body = "UserPrincipalName`r`n" + (($valid | ForEach-Object { $_ }) -join "`r`n") + "`r`n"
        # UTF-8 WITH BOM on purpose: 5.1's Import-Csv assumes ANSI without one.
        [System.IO.File]::WriteAllText($OutPath, $body, (New-Object System.Text.UTF8Encoding($true)))
        $written = (Resolve-Path -LiteralPath $OutPath).ProviderPath
    } catch {
        Write-Error -Message "could not write $OutPath : $($_.Exception.Message)" -ErrorId 'OutputUnwritable' -Category WriteError -ErrorAction Continue
        exit 2
    }
}

$summary = [ordered]@{
    source = $source
    column = $column
    count = $valid.Count
    addresses = @($valid)
    rejected = @($rejected)
    duplicates_dropped = @($duplicate)
    out = $written
}

if ($AsJson) {
    Write-Output ($summary | ConvertTo-Json -Depth 4)
} else {
    Write-Output "Source:    $source"
    if ($column) { Write-Output "Column:    $column" }
    Write-Output "Valid:     $($valid.Count)"
    foreach ($a in $valid) { Write-Output "  $a" }
    if ($duplicate.Count -gt 0) {
        Write-Output "Duplicates dropped: $($duplicate.Count)"
        foreach ($d in $duplicate) { Write-Output "  line $($d.line): $($d.value)" }
    }
    if ($rejected.Count -gt 0) {
        Write-Output "Rejected:  $($rejected.Count)"
        foreach ($r in $rejected) { Write-Output "  line $($r.line): '$($r.value)' - $($r.reason)" }
    }
    if ($written) { Write-Output "Written:   $written" }
}

if ($valid.Count -eq 0) {
    # stderr on purpose: powershell.exe writes the warning stream to STDOUT, which would trail the JSON
    [Console]::Error.WriteLine('WARNING  no valid addresses')
    exit 1
}
if ($rejected.Count -gt 0) {
    [Console]::Error.WriteLine("WARNING  $($rejected.Count) row(s) rejected - confirm with the operator before proceeding")
    exit 3
}
exit 0
