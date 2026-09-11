# bootstrap.ps1 - install Nuclei + templates on Windows.
# Downloads the prebuilt nuclei.exe, puts it on your user PATH, updates templates.
#
# Run in PowerShell from the plugin folder:
#   powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
#
$ErrorActionPreference = "Stop"

# Install location on the user PATH (no admin needed)
$BinDir = Join-Path $env:LOCALAPPDATA "Programs\nuclei"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# arch
$arch = if ([Environment]::Is64BitOperatingSystem) { "amd64" } else { "386" }

Write-Host ">> finding latest Nuclei release..."
$rel = Invoke-RestMethod "https://api.github.com/repos/projectdiscovery/nuclei/releases/latest" `
        -Headers @{ "User-Agent" = "nuclei-bootstrap" }
$ver = $rel.tag_name
$num = $ver.TrimStart("v")
$zip = "nuclei_${num}_windows_${arch}.zip"
$url = "https://github.com/projectdiscovery/nuclei/releases/download/$ver/$zip"

Write-Host ">> downloading $zip ..."
$tmp = Join-Path $env:TEMP $zip
Invoke-WebRequest -Uri $url -OutFile $tmp -Headers @{ "User-Agent" = "nuclei-bootstrap" }
Expand-Archive -Path $tmp -DestinationPath $BinDir -Force
Remove-Item $tmp

# Add to user PATH if missing
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$BinDir", "User")
  $env:Path += ";$BinDir"
  Write-Host ">> added $BinDir to your user PATH (restart terminals to pick it up)"
}

$nuclei = Join-Path $BinDir "nuclei.exe"
Write-Host ">> installed: $(& $nuclei -version 2>&1 | Select-Object -First 1)"
Write-Host ">> downloading community templates..."
# Not swallowed. Nuclei with no templates finds nothing and exits 0, which is
# indistinguishable from a clean scan - so a bootstrap that ignores this leaves
# behind a scanner that reports every target as healthy.
& $nuclei -update-templates -silent
if ($LASTEXITCODE -ne 0) {
  Write-Host "!! template download failed. The engine is installed but has no templates," -ForegroundColor Red
  Write-Host "!! so a scan would report zero findings on every target." -ForegroundColor Red
  Write-Host "!! Re-run 'nuclei -update-templates' once the network allows it." -ForegroundColor Red
  exit 1
}

# Prereq reminders for the reporting side
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "!! Python not found. Install it (winget install Python.Python.3.12) for the report/ticket CLI."
}
if (-not (Get-Command wkhtmltopdf -ErrorAction SilentlyContinue)) {
  Write-Host "!! wkhtmltopdf not found. Installing it for PDF reports..."
  winget install --id wkhtmltopdf.wkhtmltox --accept-source-agreements --accept-package-agreements --disable-interactivity 2>&1 | Out-Null
  # winget installs it but does not put it on PATH, so a later `doctor` reports
  # it missing and the PDF half of every report is silently skipped.
  $wkDir = "C:\Program Files\wkhtmltopdf\bin"
  if ((Test-Path (Join-Path $wkDir "wkhtmltopdf.exe")) -and
      (([Environment]::GetEnvironmentVariable("Path","User") -split ';') -notcontains $wkDir)) {
    [Environment]::SetEnvironmentVariable(
      "Path", "$([Environment]::GetEnvironmentVariable('Path','User'));$wkDir", "User")
    $env:Path += ";$wkDir"
    Write-Host ">> added $wkDir to your user PATH"
  }
}

# ---------------------------------------------------------------------------
# The rest of the scanner suite.
#
# Nuclei is a known-issue template scanner. On its own it finds almost nothing
# on an authenticated app behind a WAF - a real sweep of 18 such endpoints
# returned 294 findings, every one of them Info-severity fingerprinting. These
# four cover what it structurally cannot: TLS configuration, dependency CVEs,
# committed secrets, IaC misconfiguration, and source-level flaws such as a
# missing authorization check.
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host ">> installing the scanner suite..."

if (-not (Get-Command trivy -ErrorAction SilentlyContinue)) {
  Write-Host ">> trivy (dependency CVEs, committed secrets, Terraform misconfiguration)"
  winget install --id AquaSecurity.Trivy --accept-source-agreements --accept-package-agreements --disable-interactivity 2>&1 | Out-Null
}

# sslyze and semgrep are Python tools. Installed with --user so they land on
# PATH for the account running scans rather than inside whatever virtualenv
# happens to be active when this script runs.
if (Get-Command python -ErrorAction SilentlyContinue) {
  foreach ($pkg in @(
    @{ name = "sslyze";  why = "TLS protocol and certificate posture" },
    @{ name = "semgrep"; why = "static analysis; the only tool here that sees a missing auth gate" }
  )) {
    if (-not (Get-Command $pkg.name -ErrorAction SilentlyContinue)) {
      Write-Host ">> $($pkg.name) ($($pkg.why))"
      python -m pip install --user --quiet $pkg.name 2>&1 | Out-Null
    }
  }
}

Write-Host ""
Write-Host ">> optional, not installed by default:"
Write-Host "   OWASP ZAP  - authenticated crawler-driven DAST. Minutes per target."
Write-Host "                Install, then scan with --with-zap."
Write-Host "   checkov    - more IaC checks than trivy, but checkov OSS returns no"
Write-Host "                severity, so its findings are floored at Low and will not"
Write-Host "                appear in a Medium-and-above report. Scan with --with-checkov."

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " Run 'gizmoduck.py doctor' to confirm every tool resolved."
Write-Host " Then:  /gizmoduck:scan https://your-site.com"
Write-Host " Add --source <dir> so trivy and semgrep have a tree to read;"
Write-Host " without it they report as SKIPPED, not clean."
Write-Host "------------------------------------------------------------"
