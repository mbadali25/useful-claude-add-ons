# bootstrap.ps1 - install Nuclei plus the eight other gizmoduck scanners on
# Windows.
#
# Each tool installs independently: a failure in one does not stop the rest
# (ACME multi-scanner routine work, 2026-09-10 plan Task 20). The ONE
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

# Returns the newest stable release tag (e.g. v3.11.1) of GitHub repo $Repo
# (owner/repo). Twin of bootstrap.sh's resolve_latest_tag - same order, same
# filter. The REST API (releases/latest) is tried first, as before. Some
# networks answer api.github.com with a 403 while still serving git and the
# versioned releases/download/<tag>/ assets, so on an API failure this falls
# back to `git ls-remote --tags`. Only plain X.Y.Z (optionally v-prefixed)
# tags count there: rc/beta/alpha/pre tags, ZAP's w2026-... weekly tags and
# oddities like nuclei's `v.1.0.0` are skipped, and the highest version wins.
# When both lookups fail it throws an error naming the tool, which
# Try-Install catches like any other install failure.
function Resolve-LatestTag {
  param(
    [Parameter(Mandatory)][string]$Repo,
    [Parameter(Mandatory)][string]$Tool
  )
  try {
    $rel = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" `
            -TimeoutSec 60 -Headers @{ "User-Agent" = "gizmoduck-bootstrap" }
    if ($rel.tag_name) { return [string]$rel.tag_name }
  } catch {
    # fall through to git tags
  }
  Write-Host ">> ${Tool}: GitHub API lookup failed - trying git tags of github.com/$Repo"
  $tags = @()
  if (Get-Command git -ErrorAction SilentlyContinue) {
    $tags = & {
      $ErrorActionPreference = "Continue"
      $env:GIT_HTTP_LOW_SPEED_LIMIT = "1000"; $env:GIT_HTTP_LOW_SPEED_TIME = "30"
      git ls-remote --tags --refs "https://github.com/$Repo.git" 2>$null
    }
  }
  $best = $tags |
    ForEach-Object { ($_ -split "refs/tags/", 2)[-1] } |
    Where-Object { $_ -match '^v?\d+\.\d+\.\d+$' } |
    Sort-Object { [version]($_.TrimStart("v")) } |
    Select-Object -Last 1
  if ($best) { return [string]$best }
  throw ("${Tool}: could not determine the latest version - both the GitHub API " +
         "(api.github.com/repos/$Repo/releases/latest) and " +
         "'git ls-remote --tags https://github.com/$Repo.git' failed or found no stable tag.")
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

  $ver = Resolve-LatestTag -Repo "projectdiscovery/nuclei" -Tool "nuclei"
  $num = $ver.TrimStart("v")
  $zip = "nuclei_${num}_windows_${arch}.zip"
  $sums = "nuclei_${num}_checksums.txt"
  $base = "https://github.com/projectdiscovery/nuclei/releases/download/$ver"
  $url = "$base/$zip"

  # Download straight into the (AV-excluded) install dir instead of %TEMP% -
  # %TEMP% is the most common malware drop location on Windows, so staging a
  # security tool's download through it defeats the point of excluding the
  # tool's own directory. See docs/antivirus-exclusions.md section 5.
  $tmp = Join-Path $BinDir $zip
  $sumsPath = Join-Path $BinDir $sums
  Invoke-WebRequest -Uri $url -OutFile $tmp -TimeoutSec 1800 -Headers @{ "User-Agent" = "nuclei-bootstrap" }
  Invoke-WebRequest -Uri "$base/$sums" -OutFile $sumsPath -TimeoutSec 60 -Headers @{ "User-Agent" = "nuclei-bootstrap" }
  try {
    # Twin of bootstrap.sh's verify_sha256: refuse on a missing line or a mismatch.
    Assert-Sha256 -File $tmp -SumsFile $sumsPath
  } catch {
    Remove-Item -Force $tmp, $sumsPath -ErrorAction SilentlyContinue
    throw
  }
  Expand-Archive -Path $tmp -DestinationPath $BinDir -Force
  Remove-Item $tmp, $sumsPath

  Add-ToUserPath $BinDir

  $nuclei = Join-Path $BinDir "nuclei.exe"
  # nuclei -version writes its banner to stderr (by design - that's normal
  # CLI behavior, not a failure). Piping stderr into the success stream via
  # 2>&1 while $ErrorActionPreference = "Stop" is in effect turns that banner
  # line into a terminating error the instant it's captured, which made a
  # fully-successful install get reported as "install failed" by Try-Install.
  # Scoping ErrorActionPreference to "Continue" inside a child block lets the
  # banner text through without promoting it to an error, and without
  # touching the "Stop" behavior anything else in this script relies on.
  $verLine = & {
    $ErrorActionPreference = "Continue"
    & $nuclei -version 2>&1 | Select-Object -First 1
  }
  Write-Host ">> installed: $verLine"
}

function Update-NucleiTemplates {
  # NOT run through Try-Install, and this is deliberate - do not "fix" it into
  # a soft-fail like the others below. A template-less Nuclei still runs and
  # still exits 0, but silently finds nothing on every target, which is a
  # worse outcome than a loud bootstrap failure the operator actually sees.
  $BinDir = Join-Path $ToolsDir "nuclei"
  $nuclei = Join-Path $BinDir "nuclei.exe"
  #
  # Success is judged by templates actually being on disk, not by the exit
  # code: where api.github.com is refused, `nuclei -update-templates` exits 0
  # having downloaded nothing (measured on Linux in the Claude Code cloud
  # sandbox, nuclei v3.11.1). Twin of bootstrap.sh: only when NO templates are
  # on disk is the same release cloned with git; a failed update over
  # existing templates keeps them.
  if (-not (Test-Path $nuclei)) {
    Write-Host "!! the nuclei engine is not installed ($nuclei), so there is nothing to fetch" -ForegroundColor Red
    Write-Host "!! templates for. Fix the nuclei install above and re-run." -ForegroundColor Red
    exit 1
  }
  Write-Host ">> downloading Nuclei community templates..."
  $tdir = Join-Path $HOME "nuclei-templates"
  & {
    $ErrorActionPreference = "Continue"
    & $nuclei -update-templates -silent
  }
  $updateRc = $LASTEXITCODE
  if (Test-NucleiTemplatesPresent $tdir) {
    if ($updateRc -ne 0) {
      Write-Host "!! nuclei -update-templates failed (exit $updateRc); keeping the existing templates in $tdir" -ForegroundColor Yellow
    }
    return
  }
  Write-Host ">> no templates in $tdir after nuclei -update-templates (exit $updateRc) - trying git clone"
  try {
    Install-NucleiTemplatesClone -Dir $tdir
  } catch {
    Write-Host "!! $($_.Exception.Message)" -ForegroundColor Red
  }
  if (-not (Test-NucleiTemplatesPresent $tdir)) {
    Write-Host "!! template download failed. The engine is installed but has no templates," -ForegroundColor Red
    Write-Host "!! so a scan would report zero findings on every target." -ForegroundColor Red
    Write-Host "!! Re-run 'nuclei -update-templates' once the network allows it." -ForegroundColor Red
    exit 1
  }
  Write-Host ">> nuclei templates cloned to $tdir"
}

# Clones the newest stable nuclei-templates release and moves it to $Dir -
# only if $Dir is missing or holds no files. Twin of bootstrap.sh's
# clone_nuclei_templates: the clone goes to a sibling temp dir first, only
# empty directories under $Dir are removed, and if any file remains the clone
# is discarded and $Dir is left exactly as it was.
function Install-NucleiTemplatesClone {
  param([Parameter(Mandatory)][string]$Dir)
  $tag = Resolve-LatestTag -Repo "projectdiscovery/nuclei-templates" -Tool "nuclei templates"
  $parent = Split-Path -Parent $Dir
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $tmp = Join-Path $parent ("{0}.gizmoduck-clone.{1}" -f (Split-Path -Leaf $Dir), [guid]::NewGuid().ToString("N").Substring(0, 8))
  try {
    & {
      $ErrorActionPreference = "Continue"
      $env:GIT_HTTP_LOW_SPEED_LIMIT = "1000"; $env:GIT_HTTP_LOW_SPEED_TIME = "30"
      git -c advice.detachedHead=false clone -q --depth 1 --branch $tag `
        https://github.com/projectdiscovery/nuclei-templates.git $tmp 2>&1 | Out-Host
    }
    if ($LASTEXITCODE -ne 0) { throw "git clone of nuclei-templates $tag failed" }
    if (Test-Path -LiteralPath $Dir) {
      if (Get-ChildItem -LiteralPath $Dir -Recurse -Force -File -ErrorAction SilentlyContinue | Select-Object -First 1) {
        throw "$Dir holds files but no templates - not replacing it. Move them aside and re-run."
      }
      # Only empty directories are left; remove them deepest first, never a file.
      Get-ChildItem -LiteralPath $Dir -Recurse -Force -Directory | Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object { [System.IO.Directory]::Delete($_.FullName, $false) }
      [System.IO.Directory]::Delete($Dir, $false)
    }
    Move-Item -LiteralPath $tmp -Destination $Dir
  } finally {
    # Our own temp clone, never the user's directory.
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
  }
}

# Checks $File against its line in $SumsFile (sha256sum format), matching the
# exact file-name field. Throws on a missing line or a mismatch.
function Assert-Sha256 {
  param([Parameter(Mandatory)][string]$File, [Parameter(Mandatory)][string]$SumsFile)
  $name = Split-Path -Leaf $File
  $want = $null
  foreach ($line in (Get-Content -LiteralPath $SumsFile)) {
    $f = $line -split '\s+', 2
    if ($f.Count -eq 2 -and ($f[1] -ceq $name -or $f[1] -ceq "*$name")) { $want = $f[0].ToLowerInvariant(); break }
  }
  if (-not $want) { throw "${name}: no checksum line in $(Split-Path -Leaf $SumsFile) - refusing to install it" }
  $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $File).Hash.ToLowerInvariant()
  if ($got -ne $want) { throw "${name}: sha256 mismatch (expected $want, got $got) - refusing to install it" }
  Write-Host ">> ${name}: sha256 OK"
}

function Test-NucleiTemplatesPresent([string]$Dir) {
  if (-not (Test-Path $Dir)) { return $false }
  return [bool](Get-ChildItem -Path $Dir -Recurse -Filter *.yaml -File -ErrorAction SilentlyContinue |
                Select-Object -First 1)
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

  # Stage under ToolsDir instead of %TEMP% - not because this particular
  # destination (Perl's own vendorlib) is AV-excluded, but because %TEMP% is
  # the most common malware drop location on Windows and there's no reason
  # for any tool download to sit there even briefly. See
  # docs/antivirus-exclusions.md section 5.
  $stageDir = Join-Path $ToolsDir ".download\xml-writer"
  if (Test-Path $stageDir) { Remove-Item -Recurse -Force $stageDir }
  New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

  $tmp = Join-Path $stageDir "gizmoduck-xml-writer.tar.gz"
  Invoke-WebRequest -Uri $meta.download_url -OutFile $tmp

  $extractDir = Join-Path $stageDir "extract"
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

  Remove-Item -Recurse -Force $stageDir -ErrorAction SilentlyContinue
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

function Install-Semgrep {
  # Semgrep is the only source-reading tool here, and the only one that can
  # see a check that is MISSING - an authorization gate nobody wrote has no
  # signature, no CVE and no misconfigured resource to find. Native Windows
  # support was verified against 1.177.0; no WSL or Docker required.
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python is not available on this machine"
  }
  python -m pip install --user --upgrade semgrep
  if ($LASTEXITCODE -ne 0) { throw "pip exited $LASTEXITCODE" }
}

function Install-DependencyCheck {
  $ver = Resolve-LatestTag -Repo "jeremylong/DependencyCheck" -Tool "dependency-check"
  $num = $ver.TrimStart("v")
  $zip = "dependency-check-${num}-release.zip"
  $url = "https://github.com/jeremylong/DependencyCheck/releases/download/$ver/$zip"

  $dir = Join-Path $ToolsDir "dependency-check"
  # Stage next to the extraction target (ToolsDir) instead of %TEMP% - see
  # Install-Nuclei above for why. $dir itself gets wiped below, so the zip
  # has to live in the parent that survives that, not inside $dir.
  $tmp = Join-Path $ToolsDir $zip
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
    # java -version writes to stderr unconditionally - that's Java's own
    # convention, not an error. Same fix as Install-Nuclei above: without
    # scoping ErrorActionPreference to "Continue" here, capturing that
    # output via 2>&1 under the script's $ErrorActionPreference = "Stop"
    # turned a present, new-enough JRE into a false "ZAP install failed"
    # before the function got anywhere near actually installing ZAP.
    $verLine = & {
      $ErrorActionPreference = "Continue"
      & java -version 2>&1 | Select-Object -First 1
    }
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
  $ver = Resolve-LatestTag -Repo "zaproxy/zaproxy" -Tool "OWASP ZAP"
  $num = $ver.TrimStart("v")
  $zip = "ZAP_${num}_Crossplatform.zip"
  $url = "https://github.com/zaproxy/zaproxy/releases/download/$ver/$zip"

  $dir = Join-Path $ToolsDir "zap"
  # Stage next to the extraction target (ToolsDir) instead of %TEMP% - a
  # 286MB ZAP zip sitting in %TEMP% mid-download is exactly what got flagged
  # and quarantined by Defender. $dir itself gets wiped below, so the zip
  # has to live in the parent that survives that, not inside $dir.
  $tmp = Join-Path $ToolsDir $zip
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
Try-Install "semgrep"          { Install-Semgrep }
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
  Write-Host "!! If a failure looks like your AV/EDR deleted or quarantined a file (nikto," -ForegroundColor Yellow
  Write-Host "!! sqlmap, ZAP, a Nuclei template), see docs/antivirus-exclusions.md." -ForegroundColor Yellow
} else {
  Write-Host ">> all tools installed."
}

# --- Defender exclusions ---------------------------------------------------
#
# Run BEFORE the closing banner, because a missing exclusion is the most common
# reason a fresh install looks fine and then finds nothing: Defender deletes
# rather than quarantines here, so a flagged Nuclei template or a deleted
# nikto.pl presents as "the scan came back clean".
#
# Preview only. Registering an exclusion narrows the protection on a machine
# and needs elevation, so it stays a decision the operator makes on purpose -
# the bootstrap shows what is missing and prints the one command that fixes it.
$exclScript = Join-Path $PSScriptRoot "scripts\defender-exclusions.ps1"
if ((Get-Command Get-MpPreference -ErrorAction SilentlyContinue) -and (Test-Path $exclScript)) {
  Write-Host ""
  Write-Host ">> checking Windows Defender exclusions..."
  & $exclScript
  Write-Host ""
  Write-Host ">> to register any missing ones, from an ELEVATED prompt:" -ForegroundColor Cyan
  Write-Host "   powershell -ExecutionPolicy Bypass -File `"$exclScript`" -Apply" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " Nuclei is ready. Try:"
Write-Host "   nuclei -u https://example.com -severity critical,high"
Write-Host " Or drive it through the plugin:  /gizmoduck:scan https://your-site.com high"
Write-Host " For the full scanner routine across a manifest of targets:"
Write-Host "   python scripts\gizmoduck.py routine targets.yaml --scan-root .   (then /gizmoduck:doctor confirms what installed)"
Write-Host "------------------------------------------------------------"
