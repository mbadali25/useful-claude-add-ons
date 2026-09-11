# bootstrap.ps1 - install Nuclei plus the eight other gizmoduck scanners on
# Windows.
#
# Each tool installs independently: a failure in one does not stop the rest
# (THDDEV multi-scanner routine work, 2026-09-10 plan Task 20). The ONE
# exception is the Nuclei template download, which still aborts the script -
# see Update-NucleiTemplates below for why.
#
# Run in PowerShell from the plugin folder:
#   powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
#
$ErrorActionPreference = "Stop"   # per-install Try-Install blocks catch this; nothing outside them relies on it

$script:Failed = @()
$ToolsDir = Join-Path $env:LOCALAPPDATA "Programs"
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

# Runs $Action (a scriptblock) and, on any terminating error, logs a warning
# and lets the script keep going instead of aborting - the restructure Task 20
# asks for. $ErrorActionPreference = Stop above is what makes an ordinary
# cmdlet failure land in the catch instead of being silently swallowed.
function Try-Install {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][scriptblock]$Action
  )
  Write-Host ">> installing $Name..."
  try {
    & $Action
    Write-Host ">> ${Name}: OK"
  } catch {
    Write-Host "!! ${Name}: install failed - continuing with the rest ($($_.Exception.Message))" -ForegroundColor Yellow
    $script:Failed += $Name
  }
}

function Test-WingetAvailable {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget is not available on this machine"
  }
}

function Install-Nuclei {
  # Install location on the user PATH (no admin needed)
  $BinDir = Join-Path $ToolsDir "nuclei"
  New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

  $arch = if ([Environment]::Is64BitOperatingSystem) { "amd64" } else { "386" }

  $rel = Invoke-RestMethod "https://api.github.com/repos/projectdiscovery/nuclei/releases/latest" `
          -Headers @{ "User-Agent" = "nuclei-bootstrap" }
  $ver = $rel.tag_name
  $num = $ver.TrimStart("v")
  $zip = "nuclei_${num}_windows_${arch}.zip"
  $url = "https://github.com/projectdiscovery/nuclei/releases/download/$ver/$zip"

  $tmp = Join-Path $env:TEMP $zip
  Invoke-WebRequest -Uri $url -OutFile $tmp -Headers @{ "User-Agent" = "nuclei-bootstrap" }
  Expand-Archive -Path $tmp -DestinationPath $BinDir -Force
  Remove-Item $tmp

  Add-ToUserPath $BinDir

  $nuclei = Join-Path $BinDir "nuclei.exe"
  Write-Host ">> installed: $(& $nuclei -version 2>&1 | Select-Object -First 1)"
}

function Update-NucleiTemplates {
  # NOT run through Try-Install, and this is deliberate - do not "fix" it into
  # a soft-fail like the others below. A template-less Nuclei still runs and
  # still exits 0, but silently finds nothing on every target, which is a
  # worse outcome than a loud bootstrap failure the operator actually sees.
  $BinDir = Join-Path $ToolsDir "nuclei"
  $nuclei = Join-Path $BinDir "nuclei.exe"
  Write-Host ">> downloading Nuclei community templates..."
  & $nuclei -update-templates -silent
  if ($LASTEXITCODE -ne 0) {
    Write-Host "!! template download failed. The engine is installed but has no templates," -ForegroundColor Red
    Write-Host "!! so a scan would report zero findings on every target." -ForegroundColor Red
    Write-Host "!! Re-run 'nuclei -update-templates' once the network allows it." -ForegroundColor Red
    exit 1
  }
}

function Add-ToUserPath {
  param([string]$Dir)
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if ($userPath -notlike "*$Dir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$Dir", "User")
    $env:Path += ";$Dir"
    Write-Host ">> added $Dir to your user PATH (restart terminals to pick it up)"
  }
}

function Install-Nmap {
  Test-WingetAvailable
  winget install --id Insecure.Nmap -e --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) { throw "winget exited $LASTEXITCODE" }
}

function Test-PerlHasXmlWriter {
  # Presence of *something* called perl on PATH is not evidence it can run
  # nikto. On a machine with Git for Windows installed, `Get-Command perl`
  # resolves to Git's own bundled MSYS perl - which, depending on the Git
  # for Windows build, can be missing XML::Writer (nikto's hard dependency)
  # with a CPAN that has no CPAN::Author/cpanm to install it with. The old
  # check here ("install Strawberry Perl only if no perl is found at all")
  # skipped the install on exactly that kind of machine and left nikto
  # permanently broken. Verify the capability, not just the binary's
  # existence. Takes an explicit $PerlExe so both the PATH perl and a
  # freshly-installed Strawberry Perl can be checked with the same function.
  param([string]$PerlExe = "perl")
  if ($PerlExe -eq "perl" -and -not (Get-Command perl -ErrorAction SilentlyContinue)) { return $false }
  & $PerlExe -MXML::Writer -e "1" *> $null
  return ($LASTEXITCODE -eq 0)
}

function Install-XmlWriterModule {
  # XML::Writer is pure Perl - no XS, no compiler needed - so the fix that
  # actually got nikto running on a Git-for-Windows perl (whose CPAN client
  # has no CPAN::Author/cpanm to install anything with) was to drop its one
  # file, Writer.pm, straight into that perl's own vendor_perl. No perl
  # reinstall, no working CPAN client required.
  param([Parameter(Mandatory)][string]$PerlExe)

  # Single-quoted so PowerShell passes '$Config::Config{vendorlib}' through
  # literally for perl to interpolate - a double-quoted string here gets
  # expanded (to nothing, since no such PowerShell variable exists) by
  # PowerShell itself before perl ever sees it.
  $vendorLib = (& $PerlExe -MConfig -e 'print $Config::Config{vendorlib}').Trim()
  if (-not $vendorLib) { throw "could not determine $PerlExe's vendorlib" }

  $meta = Invoke-RestMethod "https://fastapi.metacpan.org/v1/download_url/XML::Writer"
  if (-not $meta.download_url) { throw "could not resolve an XML::Writer release from MetaCPAN" }

  $tmp = Join-Path $env:TEMP "gizmoduck-xml-writer.tar.gz"
  Invoke-WebRequest -Uri $meta.download_url -OutFile $tmp

  $extractDir = Join-Path $env:TEMP "gizmoduck-xml-writer-extract"
  if (Test-Path $extractDir) { Remove-Item -Recurse -Force $extractDir }
  New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
  tar -xzf $tmp -C $extractDir
  if ($LASTEXITCODE -ne 0) { throw "failed to extract the XML::Writer release tarball" }

  # Verified against the actual current release (XML-Writer-0.900.tar.gz):
  # Writer.pm sits at the distribution root, not nested under lib/XML/ as
  # its `package XML::Writer;` declaration might suggest - so this matches
  # on filename alone rather than assuming a directory shape the real
  # tarball doesn't have.
  $writerPm = Get-ChildItem -Recurse -Path $extractDir -Filter "Writer.pm" | Select-Object -First 1
  if (-not $writerPm) { throw "Writer.pm not found inside the XML::Writer release" }

  $destDir = Join-Path $vendorLib "XML"
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null
  Copy-Item $writerPm.FullName (Join-Path $destDir "Writer.pm") -Force

  Remove-Item $tmp -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
}

function Install-Nikto {
  # Nikto is a Perl script with no native Windows package - it needs a Perl
  # runtime plus the script itself. The adapter (scanners/nikto.py) just
  # uses `base.which("perl")` - whichever perl ends up resolvable on PATH
  # after this function runs is what nikto will actually be launched with,
  # so the capability check and fix both have to happen here, not at scan
  # time.
  Test-WingetAvailable
  $perlCmd = Get-Command perl -ErrorAction SilentlyContinue
  if (-not $perlCmd) {
    winget install --id StrawberryPerl.StrawberryPerl -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget exited $LASTEXITCODE installing Strawberry Perl" }
  } elseif (-not (Test-PerlHasXmlWriter $perlCmd.Source)) {
    Write-Host ">> $($perlCmd.Source) is missing XML::Writer (nikto's hard dependency) - installing it..."
    try {
      Install-XmlWriterModule -PerlExe $perlCmd.Source
    } catch {
      Write-Host "!! could not add XML::Writer to $($perlCmd.Source): $($_.Exception.Message)" -ForegroundColor Yellow
      Write-Host "!! falling back to installing Strawberry Perl instead" -ForegroundColor Yellow
      winget install --id StrawberryPerl.StrawberryPerl -e --accept-package-agreements --accept-source-agreements
      if ($LASTEXITCODE -ne 0) { throw "winget exited $LASTEXITCODE installing Strawberry Perl" }
      # scanners/nikto.py just trusts `base.which("perl")` - if the perl
      # found above (still missing XML::Writer) stays ahead of this new
      # Strawberry install in PATH search order, nikto would keep resolving
      # to the broken one. Prepend Strawberry's bin dir so it wins.
      $strawberryBin = "C:\Strawberry\perl\bin"
      if (Test-Path (Join-Path $strawberryBin "perl.exe")) {
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        [Environment]::SetEnvironmentVariable("Path", "$strawberryBin;$userPath", "User")
        $env:Path = "$strawberryBin;$env:Path"
      }
    }
    if (-not (Test-PerlHasXmlWriter "perl")) {
      Write-Host "!! nikto may still fail: no perl on PATH could be confirmed to have XML::Writer" -ForegroundColor Yellow
      Write-Host "!! after this install. Re-run bootstrap once network/CPAN access is available." -ForegroundColor Yellow
    }
  }
  $dir = Join-Path $ToolsDir "nikto"
  if (Test-Path (Join-Path $dir ".git")) {
    git -C $dir pull --ff-only
  } else {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    git clone --depth 1 https://github.com/sullo/nikto.git $dir
  }
  if ($LASTEXITCODE -ne 0) { throw "git clone/pull failed for nikto" }
  Write-Host ">> nikto cloned to $dir - run via: perl `"$dir\program\nikto.pl`" -h <target>"
}

function Install-Testssl {
  # A bash script - relies on Git for Windows bundling Git Bash, which is a
  # safe assumption here because `git` itself is required just to clone it.
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required to install testssl.sh (and to run it via Git Bash)"
  }
  $dir = Join-Path $ToolsDir "testssl.sh"
  if (Test-Path (Join-Path $dir ".git")) {
    git -C $dir pull --ff-only
  } else {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    git clone --depth 1 https://github.com/drwetter/testssl.sh.git $dir
  }
  if ($LASTEXITCODE -ne 0) { throw "git clone/pull failed for testssl.sh" }
  Write-Host ">> testssl.sh cloned to $dir - run via Git Bash: bash `"$dir\testssl.sh`" <host>"
  # testssl.sh hard-requires `hexdump` and refuses to run at all without it
  # ("You need to install hexdump for this program to work."). Git Bash's
  # own usr/bin ships xxd and od but not hexdump. The adapter
  # (scanners/testssl.py's _hexdump_dir()) already works around this by
  # prepending an MSYS2 usr/bin to PATH for the scan subprocess if it finds
  # one at C:\tools\msys64\usr\bin, C:\msys64\usr\bin, or
  # $env:GIZMODUCK_MSYS2_BIN - install MSYS2 (or point that variable at an
  # existing one) if testssl scans fail with the hexdump error.
  if (-not (Get-Command hexdump -ErrorAction SilentlyContinue) -and
      -not (Test-Path "C:\tools\msys64\usr\bin\hexdump.exe") -and
      -not (Test-Path "C:\msys64\usr\bin\hexdump.exe")) {
    Write-Host "!! hexdump not found (needed by testssl.sh) and no MSYS2 install detected" -ForegroundColor Yellow
    Write-Host "!! at the usual locations. testssl scans will fail until either is present -" -ForegroundColor Yellow
    Write-Host "!! install MSYS2, or set GIZMODUCK_MSYS2_BIN to a directory containing hexdump.exe." -ForegroundColor Yellow
  }
}

function Install-Trivy {
  Test-WingetAvailable
  winget install --id AquaSecurity.Trivy -e --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) { throw "winget exited $LASTEXITCODE" }
}

function Install-Checkov {
  if (-not (Get-Command pip -ErrorAction SilentlyContinue) -and -not (Get-Command pip3 -ErrorAction SilentlyContinue)) {
    throw "pip (Python) is required to install checkov"
  }
  $pip = if (Get-Command pip3 -ErrorAction SilentlyContinue) { "pip3" } else { "pip" }
  & $pip install --user --upgrade checkov
  if ($LASTEXITCODE -ne 0) { throw "$pip exited $LASTEXITCODE" }
}

function Install-DependencyCheck {
  $rel = Invoke-RestMethod "https://api.github.com/repos/jeremylong/DependencyCheck/releases/latest" `
          -Headers @{ "User-Agent" = "gizmoduck-bootstrap" }
  $ver = $rel.tag_name
  $num = $ver.TrimStart("v")
  $zip = "dependency-check-${num}-release.zip"
  $url = "https://github.com/jeremylong/DependencyCheck/releases/download/$ver/$zip"

  $dir = Join-Path $ToolsDir "dependency-check"
  $tmp = Join-Path $env:TEMP $zip
  Invoke-WebRequest -Uri $url -OutFile $tmp -Headers @{ "User-Agent" = "gizmoduck-bootstrap" }
  if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
  Expand-Archive -Path $tmp -DestinationPath $ToolsDir -Force
  Remove-Item $tmp

  # Dependency-Check is a Java app; make sure something can run it. Reuses
  # the Temurin 17 JDK installed for ZAP if that ran first - either order works
  # since both just check for `java`.
  if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    Test-WingetAvailable
    winget install --id EclipseAdoptium.Temurin.17.JDK -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget exited $LASTEXITCODE installing a JRE for dependency-check" }
  }
  Write-Host ">> dependency-check installed to $dir - run via: $dir\dependency-check\bin\dependency-check.bat"
}

function Install-Sqlmap {
  # git clone is sqlmap's own documented install method - there is no PyPI
  # package (spec 13.9: no --report-json either, but that's a routine.py
  # adapter concern, not a bootstrap one).
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required to install sqlmap"
  }
  $dir = Join-Path $ToolsDir "sqlmap"
  if (Test-Path (Join-Path $dir ".git")) {
    git -C $dir pull --ff-only
  } else {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    git clone --depth 1 https://github.com/sqlmapproject/sqlmap.git $dir
  }
  if ($LASTEXITCODE -ne 0) { throw "git clone/pull failed for sqlmap" }
  Write-Host ">> sqlmap cloned to $dir - run via: python `"$dir\sqlmap.py`""
}

function Install-Zap {
  # ZAP 2.16+ requires Java 17 minimum on Windows (spec 13.3). A missing or
  # too-old JRE lets this install step "succeed" while ZAP itself never
  # starts later - which looks like a missing tool for reasons nobody can see
  # from `doctor`. Check for 17+ before doing anything else.
  $needsJava = $true
  if (Get-Command java -ErrorAction SilentlyContinue) {
    $verLine = (& java -version 2>&1 | Select-Object -First 1)
    if ($verLine -match '"(1\.)?(1[7-9]|[2-9][0-9])') { $needsJava = $false }
  }
  if ($needsJava) {
    Test-WingetAvailable
    winget install --id EclipseAdoptium.Temurin.17.JDK -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget exited $LASTEXITCODE installing Java 17 for ZAP" }
  }

  # The Crossplatform zip ships both zap.sh and zap.bat plus the Automation
  # Framework add-on (confirmed against the zaproxy/zaproxy release assets),
  # so a plain Expand-Archive is enough - no installer wizard to script. This
  # is NOT the docker `zaproxy/zap-stable` image: Docker is not installed on
  # the operator machine and using it here was explicitly ruled out. Do not
  # "fix" this back to a docker run.
  $rel = Invoke-RestMethod "https://api.github.com/repos/zaproxy/zaproxy/releases/latest" `
          -Headers @{ "User-Agent" = "gizmoduck-bootstrap" }
  $ver = $rel.tag_name
  $num = $ver.TrimStart("v")
  $zip = "ZAP_${num}_Crossplatform.zip"
  $url = "https://github.com/zaproxy/zaproxy/releases/download/$ver/$zip"

  $dir = Join-Path $ToolsDir "zap"
  $tmp = Join-Path $env:TEMP $zip
  Invoke-WebRequest -Uri $url -OutFile $tmp -Headers @{ "User-Agent" = "gizmoduck-bootstrap" }
  if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
  Expand-Archive -Path $tmp -DestinationPath $dir -Force
  Remove-Item $tmp
  Write-Host ">> ZAP unpacked to $dir - run via: $dir\zap.bat -cmd -autorun <plan>.yaml"
}

Try-Install "nuclei"           { Install-Nuclei }
Update-NucleiTemplates         # hard-fail exception - see comment above, do not wrap in Try-Install
Try-Install "nmap"             { Install-Nmap }
Try-Install "nikto"            { Install-Nikto }
Try-Install "testssl.sh"       { Install-Testssl }
Try-Install "trivy"            { Install-Trivy }
Try-Install "checkov"          { Install-Checkov }
Try-Install "dependency-check" { Install-DependencyCheck }

# dependency-check's first run downloads the entire NVD CVE corpus. Without an
# API key, NIST rate-limits that sync to ~5 requests/30s - on a fresh machine
# that first run can take the better part of an hour and gives no progress
# output, which looks exactly like a hang. An API key raises the limit to
# ~50/30s (~10x). Printed unconditionally (not just on install success): it
# matters just as much if dependency-check gets installed by hand later.
# Non-interactive on purpose - do not prompt for the key here.
Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " Dependency-Check + NVD API key (optional, recommended):"
Write-Host " The first scan syncs the full NVD CVE database. Without an API"
Write-Host " key NIST rate-limits that to ~5 req/30s (~10x slower than with"
Write-Host " one) - the run can take a long time and print nothing, which"
Write-Host " looks hung but isn't."
Write-Host ""
Write-Host " Get a free key (no account, no cost - just an email + org):"
Write-Host "   https://nvd.nist.gov/developers/request-an-api-key"
Write-Host " NIST emails an ACTIVATION LINK, not the key itself - open that"
Write-Host " link, then copy the key shown on the page behind it."
Write-Host ""
Write-Host " Then set it before running dependency-check:"
Write-Host "   `$env:NVD_API_KEY = '<your key>'"
Write-Host "------------------------------------------------------------"

Try-Install "sqlmap"           { Install-Sqlmap }
Try-Install "OWASP ZAP"        { Install-Zap }

# Prereq reminders for the reporting side
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "!! Python not found. Install it (winget install Python.Python.3.12) for the report/ticket/routine CLI."
}
if (-not (Get-Command wkhtmltopdf -ErrorAction SilentlyContinue)) {
  Write-Host "!! wkhtmltopdf not found. Install it (winget install wkhtmltopdf) for PDF reports; HTML works without it."
}

Write-Host ""
if ($script:Failed.Count -gt 0) {
  Write-Host "!! $($script:Failed.Count) tool(s) failed to install: $($script:Failed -join ', ')" -ForegroundColor Yellow
  Write-Host "!! Re-run this script, or install them by hand, then check with:"
  Write-Host "!!   /gizmoduck:doctor"
} else {
  Write-Host ">> all tools installed."
}

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " Nuclei is ready. Try:"
Write-Host "   nuclei -u https://example.com -severity critical,high"
Write-Host " Or drive it through the plugin:  /gizmoduck:scan https://your-site.com high"
Write-Host " For the full nine-tool routine, confirm what installed with: /gizmoduck:doctor"
Write-Host "------------------------------------------------------------"
