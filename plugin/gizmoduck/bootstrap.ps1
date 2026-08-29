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
  Write-Host "!! wkhtmltopdf not found. Install it (winget install wkhtmltopdf) for PDF reports; HTML works without it."
}

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " Nuclei is ready. Try:"
Write-Host "   nuclei -u https://example.com -severity critical,high"
Write-Host " Or drive it through the plugin:  /gizmoduck:scan https://your-site.com high"
Write-Host "------------------------------------------------------------"
