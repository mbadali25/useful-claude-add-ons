<#
.SYNOPSIS
  Query the ShipStation API (V2 by default, V1 fallback) from the command line.

.DESCRIPTION
  Thin, dependency-free wrapper over the ShipStation REST API that handles the
  three things that otherwise go wrong: the correct auth scheme per version,
  429 rate-limit backoff, and pagination.

  Credentials are read from environment variables - never pass keys on the
  command line, since that leaks them into shell history.

    V2 (default):  SHIPSTATION_API_KEY
    V1 (-V1):      SHIPSTATION_V1_API_KEY  +  SHIPSTATION_V1_API_SECRET

.PARAMETER Path
  Endpoint path. For V2 include the version prefix, e.g. /v2/shipments.
  For V1 use the bare path, e.g. /orders.

.PARAMETER Method
  HTTP method. Defaults to GET.

.PARAMETER Query
  Hashtable of query-string parameters, e.g. @{ page_size = 100 }

.PARAMETER Body
  Hashtable / object serialized to JSON for POST/PUT/PATCH.

.PARAMETER All
  Follow pagination and return every page's items merged together.
  V2 list responses use page/pages; V1 uses page/pages as well.

.PARAMETER MaxPages
  Safety cap when -All is used. Defaults to 50.

.PARAMETER Raw
  Emit raw JSON text instead of PowerShell objects.

.PARAMETER V1
  Target the legacy V1 API (https://ssapi.shipstation.com) with Basic auth.
  Needed for orders, customers and stores, which V2 does not expose.

.EXAMPLE
  .\ss.ps1 -Path /v2/carriers
  List connected carriers - the cheapest way to confirm your key works.

.EXAMPLE
  .\ss.ps1 -Path /v2/shipments -Query @{ shipment_status='shipped'; page_size=100 } -All
  Every shipped shipment, following pagination.

.EXAMPLE
  .\ss.ps1 -V1 -Path /orders -Query @{ orderStatus='awaiting_shipment' } -All
  Orders - V1 only.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]   $Path,

    [ValidateSet('GET', 'POST', 'PUT', 'PATCH', 'DELETE')]
    [string]   $Method = 'GET',

    [hashtable] $Query,
    $Body,
    [switch]   $All,
    [int]      $MaxPages = 50,
    [switch]   $Raw,
    [switch]   $V1
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 defaults to TLS 1.0 on some hosts; ShipStation requires 1.2+.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---------------------------------------------------------------- credentials
# Resolve a credential from Process scope first, then fall back to the User and
# Machine registry scopes.
#
# Why the fallback matters: a long-lived parent process (a shell, an editor, an
# agent host) captures the environment at launch. Variables created afterwards
# with setx or the System Properties dialog land in the registry but are NOT
# visible to that process or anything it spawns, so $env: lookups come back
# empty until the parent restarts. Reading the registry directly sidesteps that
# entirely - no restart required.
function Get-SSVar {
    param([string] $Name)

    $v = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if (-not [string]::IsNullOrWhiteSpace($v)) { return $v }
    foreach ($scope in @('User', 'Machine')) {
        try { $v = [Environment]::GetEnvironmentVariable($Name, $scope) } catch { $v = $null }
        if (-not [string]::IsNullOrWhiteSpace($v)) {
            Write-Verbose "$Name resolved from $scope scope (not in this process's environment)."
            return $v
        }
    }
    return $null
}

if ($V1) {
    $k = Get-SSVar 'SHIPSTATION_V1_API_KEY'
    $s = Get-SSVar 'SHIPSTATION_V1_API_SECRET'
    if ([string]::IsNullOrWhiteSpace($k) -or [string]::IsNullOrWhiteSpace($s)) {
        throw "V1 requires SHIPSTATION_V1_API_KEY and SHIPSTATION_V1_API_SECRET. Set them with: `$env:SHIPSTATION_V1_API_KEY='...'"
    }
    $pair    = [Text.Encoding]::UTF8.GetBytes("${k}:${s}")
    $headers = @{ Authorization = 'Basic ' + [Convert]::ToBase64String($pair) }
    $baseUri = 'https://ssapi.shipstation.com'
}
else {
    $k = Get-SSVar 'SHIPSTATION_API_KEY'
    if ([string]::IsNullOrWhiteSpace($k)) {
        throw "Missing SHIPSTATION_API_KEY. Generate a V2 key in ShipStation > Settings > Account > API Settings, then: `$env:SHIPSTATION_API_KEY='...'"
    }
    # V2 uses a custom API-Key header - NOT Basic auth and NOT a Bearer token.
    $headers = @{ 'API-Key' = $k }
    $baseUri = 'https://api.shipstation.com'
}
$headers['Accept'] = 'application/json'

# ------------------------------------------------------------------ url build
function Build-Uri {
    param([string] $EndpointPath, [hashtable] $Q)

    if (-not $EndpointPath.StartsWith('/')) { $EndpointPath = '/' + $EndpointPath }
    $uri = $baseUri + $EndpointPath
    if ($Q -and $Q.Count -gt 0) {
        $parts = foreach ($key in $Q.Keys) {
            $val = $Q[$key]
            if ($null -eq $val -or "$val" -eq '') { continue }
            [Uri]::EscapeDataString([string]$key) + '=' + [Uri]::EscapeDataString([string]$val)
        }
        if ($parts) { $uri += '?' + ($parts -join '&') }
    }
    return $uri
}

# --------------------------------------------------------------- the request
function Invoke-SS {
    param([string] $Uri)

    # Do not name this $args - that shadows the automatic variable.
    $reqArgs = @{
        Uri         = $Uri
        Method      = $Method
        Headers     = $headers
        TimeoutSec  = 120
        ErrorAction = 'Stop'
    }
    # $PSBoundParameters here would be this function's, not the script's - test the value.
    if ($null -ne $Body) {
        if ($Body -is [string]) { $reqArgs.Body = $Body }
        else                    { $reqArgs.Body = ($Body | ConvertTo-Json -Depth 20) }
        $reqArgs.ContentType = 'application/json'
    }

    # Retry on 429 (rate limit) and 5xx, honouring Retry-After when present.
    $maxAttempts = 5
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            return Invoke-RestMethod @reqArgs
        }
        catch {
            $resp   = $null
            $status = 0
            if ($_.Exception.PSObject.Properties['Response'] -and $_.Exception.Response) {
                $resp   = $_.Exception.Response
                $status = [int]$resp.StatusCode
            }

            if ($status -eq 401) {
                if ($V1) { throw "401 Unauthorized. Check SHIPSTATION_V1_API_KEY/SECRET (V1 uses Basic auth)." }
                throw "401 Unauthorized. Check SHIPSTATION_API_KEY - V2 expects it in the 'API-Key' header, and only one V2 key is active at a time."
            }
            if ($status -eq 403) {
                throw "403 Forbidden. This endpoint is likely gated by your ShipStation plan, or the key lacks scope."
            }
            if ($status -eq 404) {
                throw "404 Not Found for $Uri - verify the path against endpoints.md (V2 has no /v2/orders; use -V1 for orders)."
            }

            $retryable = ($status -eq 429 -or $status -ge 500)
            if (-not $retryable -or $attempt -eq $maxAttempts) {
                # Surface the API's own error body - ShipStation returns useful detail.
                $detail = ''
                try {
                    if ($resp) {
                        $sr = New-Object IO.StreamReader($resp.GetResponseStream())
                        $detail = $sr.ReadToEnd()
                        $sr.Dispose()
                    }
                } catch { }
                if ($detail) { throw "HTTP $status for $Uri`n$detail" }
                throw
            }

            # Prefer the server's Retry-After, else exponential backoff.
            $wait = 0
            try {
                if ($resp) {
                    $ra = $resp.Headers['Retry-After']
                    if ($ra) { [void][int]::TryParse($ra, [ref]$wait) }
                }
            } catch { }
            if ($wait -le 0) { $wait = [Math]::Pow(2, $attempt) }
            $hint = ''
            if ($status -eq 429) {
                if ($V1) { $hint = ' V1 has a lower request budget than V2 - slow down or narrow the query.' }
                else     { $hint = ' V2 allows ~200 req/min.' }
            }
            elseif ($status -ge 500) {
                $hint = ' Server-side error; may also mean this endpoint does not apply to this record (e.g. refresh status on a manual store).'
            }
            Write-Warning "HTTP $status - retrying in ${wait}s (attempt $attempt/$maxAttempts).$hint"
            Start-Sleep -Seconds $wait
        }
    }
}

# ------------------------------------------------------------------- dispatch
if (-not $All) {
    $result = Invoke-SS (Build-Uri $Path $Query)
    if ($Raw) { $result | ConvertTo-Json -Depth 30 } else { $result }
    return
}

# -All : walk pages and merge the array-valued payload property.
$q = @{}
if ($Query) { foreach ($key in $Query.Keys) { $q[$key] = $Query[$key] } }
if (-not $q.ContainsKey('page')) { $q['page'] = 1 }

$collected = New-Object System.Collections.Generic.List[object]
$pageNum   = [int]$q['page']
$listProp  = $null

while ($pageNum -le $MaxPages) {
    $q['page'] = $pageNum
    $page = Invoke-SS (Build-Uri $Path $q)

    # Identify the payload array once: the first array-valued property.
    if (-not $listProp) {
        foreach ($p in $page.PSObject.Properties) {
            if ($p.Value -is [Array]) { $listProp = $p.Name; break }
        }
    }
    if ($listProp) {
        $items = $page.$listProp
        if ($items) { foreach ($it in $items) { $collected.Add($it) } }
    }
    else {
        # Not a paginated envelope - return as-is.
        if ($Raw) { $page | ConvertTo-Json -Depth 30 } else { $page }
        return
    }

    $totalPages = 1
    if ($page.PSObject.Properties['pages'] -and $page.pages) { $totalPages = [int]$page.pages }
    Write-Verbose "page $pageNum/$totalPages - $($collected.Count) items so far"
    if ($pageNum -ge $totalPages) { break }
    $pageNum++
}

if ($pageNum -gt $MaxPages) {
    Write-Warning "Stopped at MaxPages=$MaxPages; results are TRUNCATED. Raise -MaxPages to fetch the rest."
}

if ($Raw) { $collected | ConvertTo-Json -Depth 30 } else { $collected }
