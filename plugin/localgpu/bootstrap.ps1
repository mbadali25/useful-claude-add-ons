#Requires -Version 5.1
<#
localgpu bootstrap (Windows side). Twin of bootstrap.sh - same six steps, same order,
same flag names and meanings. Idempotent: every step detects before it acts and reports
"already installed" rather than reinstalling.

What it stands up:
  * an Ollama server on http://127.0.0.1:11434
  * a Python venv at $LOCALGPU_HOME\venv with numpy (plus mcp\requirements.txt)
  * the embedding model nomic-embed-text and the chat model
    qwen2.5-coder:7b-instruct-q4_K_M
  * OLLAMA_MAX_LOADED_MODELS=1, persistently, so two models never share the VRAM

The six steps, in this order:
  1. NVIDIA driver present, and report the compute capability
  2. Ollama installed
  3. venv + numpy
  4. both models pulled
  5. VRAM discipline env var
  6. VERIFY - a real embed request, then 'ollama ps' proving GPU and not CPU offload

Step 6 is the point of the whole script. On a Blackwell card (sm_120: the RTX 50xx
series) an Ollama built against a CUDA runtime older than 12.8 has no kernel for the
architecture and silently runs the model on the CPU instead. Everything still "works" -
it is just an order of magnitude slower - so this script fails loudly on that rather
than printing a green tick.

Usage: .\bootstrap.ps1 [options]
    -Yes                  assume yes to every prompt (unattended)
    -DryRun               print what each step would do, change nothing
    -SkipModels           skip step 4 (and the chat-model half of step 6)
    -VerifyOnly           run steps 1 and 6 only - no installing, no writing
    -InstallRoot <dir>    override $LOCALGPU_HOME
    -Help                 print this usage and exit

Install root: $env:LOCALGPU_HOME, defaulting to %LOCALAPPDATA%\localgpu. Index artifacts
live under $LOCALGPU_HOME\index, the venv under $LOCALGPU_HOME\venv.

Elevation is not required. winget installs Ollama per-user, and the VRAM setting is
written to the User environment scope, not Machine.
#>

[CmdletBinding()]
param(
    [switch]$Yes,             # assume yes to every prompt (unattended)
    [switch]$DryRun,          # print what each step would do, change nothing
    [switch]$SkipModels,      # skip step 4, and the chat-model half of step 6
    [switch]$VerifyOnly,      # run steps 1 and 6 only
    [string]$InstallRoot,     # override $LOCALGPU_HOME
    [switch]$Help             # print the usage banner and exit
)

# Under 'irm ... | iex' this runs in the caller's scope, so remember the old preference
# and put it back at the end rather than leaving every later command in that shell on
# 'Stop'. Same reasoning as scripts/install-prerequisites.ps1.
$script:PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Stop'

# #Requires is only honoured for script *files*, and the advertised one-liner pipes this
# text through Invoke-Expression where the directive is an inert comment. The version
# gate therefore has to be a real statement.
if ($PSVersionTable.PSVersion -lt [Version]'5.1') {
    throw "PowerShell 5.1 or newer is required (this host is $($PSVersionTable.PSVersion))."
}

$script:OllamaUrl  = 'http://127.0.0.1:11434'
$script:EmbedModel = 'nomic-embed-text'
$script:ChatModel  = 'qwen2.5-coder:7b-instruct-q4_K_M'

# --- Output -------------------------------------------------------------------
function Write-Step  { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Message) Write-Host "    OK: $Message" -ForegroundColor Green }
function Write-Warn2 { param([string]$Message) Write-Host "    WARN: $Message" -ForegroundColor Yellow }
function Write-Skip  { param([string]$Message) Write-Host "    SKIP: $Message" -ForegroundColor DarkGray }
function Write-Info  { param([string]$Message) Write-Host "    $Message" }
function Write-Note  { param([string]$Message) Write-Host "        $Message" }

# Everything that ends the run goes to the error stream, and the process exits 1.
# A failure that only ever reached stdout is a failure nobody sees when this is driven
# from CI or from another script.
# Write-Host would put the headline on *stdout* while the detail went to stderr, so a
# caller capturing only stderr got the explanation with no statement of what failed.
# $host.UI.WriteErrorLine is the error stream and still renders red at a console, which
# Write-Host -ForegroundColor cannot do off stdout.
function Stop-Bootstrap {
    param([string]$Message, [string[]]$Detail = @())
    $host.UI.WriteErrorLine('')
    $host.UI.WriteErrorLine("FAIL: $Message")
    foreach ($line in $Detail) { [Console]::Error.WriteLine("      $line") }
    $host.UI.WriteErrorLine('')
    $ErrorActionPreference = $script:PreviousErrorActionPreference
    exit 1
}

function Test-Have {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Show-Usage {
    $banner = (Get-Content -LiteralPath $PSCommandPath -TotalCount 45) -join "`n"
    $start = $banner.IndexOf('<#')
    $end = $banner.IndexOf('#>')
    if ($start -ge 0 -and $end -gt $start) {
        Write-Host $banner.Substring($start + 2, $end - $start - 2).Trim()
    } else {
        Write-Host 'Usage: .\bootstrap.ps1 [-Yes] [-DryRun] [-SkipModels] [-VerifyOnly] [-InstallRoot <dir>] [-Help]'
    }
}

if ($Help) { Show-Usage; exit 0 }

# The registry environment is where winget's PATH edits land; this process never sees
# them. Replay Machine then User onto the current process so a just-installed ollama.exe
# resolves without opening a new shell.
#
# Merge, do not replace. This process's PATH can carry entries that exist nowhere in the
# registry - a venv, or a tool a parent shell put there - and overwriting it with the
# registry's copy drops them mid-run, which would take the python step 3 just resolved
# out from under the later steps.
function Sync-ProcessPath {
    $registry = @(
        [Environment]::GetEnvironmentVariable('Path', 'Machine')
        [Environment]::GetEnvironmentVariable('Path', 'User')
    ) | Where-Object { $_ } | ForEach-Object { $_ -split ';' } | Where-Object { $_ }
    $merged = @($env:Path -split ';' | Where-Object { $_ })
    foreach ($entry in $registry) {
        # -notcontains is case-insensitive for strings, which is what a Windows path needs.
        if ($merged -notcontains $entry) { $merged += $entry }
    }
    $env:Path = $merged -join ';'
}

# A shell that was already running when Ollama was installed never re-reads the registry
# PATH the installer edited, so 'ollama' can be missing from this process while Ollama is
# installed and serving on 11434. Believing PATH there reports "not installed" and step 2
# reinstalls it - exactly the non-idempotence every other step here avoids. Replay the
# registry, then fall back to the two places the installers actually put it.
function Resolve-OllamaOnPath {
    if (Test-Have 'ollama') { return $true }
    Sync-ProcessPath
    if (Test-Have 'ollama') { return $true }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Ollama')
        (Join-Path $env:ProgramFiles 'Ollama')
    ) | Where-Object { $_ }
    foreach ($dir in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $dir 'ollama.exe')) {
            $env:Path = "$dir;$($env:Path)"
            if (Test-Have 'ollama') { return $true }
        }
    }
    return $false
}

# --- Install root -------------------------------------------------------------
# The parameter is named -InstallRoot rather than -Home because $HOME is a read-only
# automatic variable: a param called Home cannot be bound.
if ($InstallRoot) {
    $script:LocalGpuHome = $InstallRoot
} elseif ($env:LOCALGPU_HOME) {
    $script:LocalGpuHome = $env:LOCALGPU_HOME
} else {
    $script:LocalGpuHome = Join-Path $env:LOCALAPPDATA 'localgpu'
}
$script:VenvDir  = Join-Path $script:LocalGpuHome 'venv'
$script:IndexDir = Join-Path $script:LocalGpuHome 'index'

$script:ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$script:Requirements = Join-Path $script:ScriptDir 'mcp\requirements.txt'

# A venv built by a Windows python puts its interpreter in Scripts\; one built by a
# POSIX python on the same tree puts it in bin\. Resolve rather than assume, so
# -VerifyOnly works against either.
function Get-VenvPython {
    foreach ($rel in 'Scripts\python.exe', 'bin\python.exe', 'bin\python') {
        $candidate = Join-Path $script:VenvDir $rel
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

# The same resolution order as the bash twin: python3, then python, then py. On Windows
# 'python' is usually the real one and 'python3' is the App Execution Alias stub that
# opens the Store, so each candidate has to actually answer a version query before it
# counts.
function Resolve-SystemPython {
    foreach ($candidate in 'python3', 'python', 'py') {
        if (-not (Test-Have $candidate)) { continue }
        try {
            $probe = & $candidate -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0 -or -not $probe) { continue }
        $parts = "$probe".Trim().Split('.')
        if ($parts.Count -ge 2 -and [int]$parts[0] -ge 3 -and ([int]$parts[0] -gt 3 -or [int]$parts[1] -ge 9)) {
            return $candidate
        }
    }
    return $null
}

# =============================================================================
# The localgpu CLI's own PATH entry
# =============================================================================
# 'pip install -e' drops a working 'localgpu.exe' console script in $VenvDir\Scripts (or
# \bin, if the venv was built by a POSIX python found on this machine) - pip never puts
# either on PATH, so 'localgpu shell' resolves only from inside the venv. Reuses
# Resolve-OllamaOnPath's handling above rather than a second copy of it: PATH edits land
# in the registry User scope, which this process - and the smoke check right after it -
# never re-reads on its own.
function Add-LocalGpuVenvToPath {
    if ($DryRun) {
        Write-Info 'Would expose the venv''s script directory (Scripts or bin) on PATH, persistently'
        return
    }

    $vpy = Get-VenvPython
    if (-not $vpy) { return }
    $scriptsDir = Split-Path -Parent $vpy

    $hasScript = (Test-Path -LiteralPath (Join-Path $scriptsDir 'localgpu.exe')) `
        -or (Test-Path -LiteralPath (Join-Path $scriptsDir 'localgpu'))
    if (-not $hasScript) { return }

    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @($userPath -split ';' | Where-Object { $_ })
    # -contains is case-insensitive for strings, which is what a Windows path needs.
    if ($entries -contains $scriptsDir) {
        Write-Skip "localgpu already on PATH ($scriptsDir, User environment scope)"
    } else {
        $entries += $scriptsDir
        [Environment]::SetEnvironmentVariable('Path', ($entries -join ';'), 'User')
        Write-Ok "Added $scriptsDir to PATH (User environment scope)"
    }

    # This process needs it now too, so the smoke check right after this run can see it.
    if (($env:Path -split ';') -notcontains $scriptsDir) {
        $env:Path = "$scriptsDir;$($env:Path)"
    }

    if (Test-Have 'localgpu') {
        Write-Ok "localgpu resolves: $((Get-Command localgpu).Source)"
    }
}

# --- HTTP ---------------------------------------------------------------------
# Invoke-RestMethod would be tidier, but it throws on a non-2xx and hides the body,
# and the body is exactly what the failure messages here have to quote verbatim.
function Invoke-OllamaPost {
    param([string]$Path, [hashtable]$Body, [int]$TimeoutSec = 120)
    $json = $Body | ConvertTo-Json -Depth 6 -Compress
    try {
        $response = Invoke-WebRequest -Uri "$($script:OllamaUrl)$Path" -Method Post `
            -ContentType 'application/json' -Body $json -TimeoutSec $TimeoutSec `
            -UseBasicParsing -ErrorAction Stop
        return $response.Content
    } catch {
        $reply = $_.Exception.Response
        if ($reply) {
            try {
                $reader = New-Object System.IO.StreamReader($reply.GetResponseStream())
                return $reader.ReadToEnd()
            } catch { return $null }
        }
        return $null
    }
}

function Test-OllamaUp {
    try {
        $null = Invoke-WebRequest -Uri "$($script:OllamaUrl)/api/version" -TimeoutSec 3 `
            -UseBasicParsing -ErrorAction Stop
        return $true
    } catch { return $false }
}

Write-Host 'localgpu bootstrap' -ForegroundColor Cyan
Write-Info "install root : $($script:LocalGpuHome)"
Write-Info "venv         : $($script:VenvDir)"
Write-Info "index        : $($script:IndexDir)"
Write-Info "ollama       : $($script:OllamaUrl)"
if ($DryRun)     { Write-Info 'mode         : -DryRun (nothing will be changed)' }
if ($VerifyOnly) { Write-Info 'mode         : -VerifyOnly (steps 1 and 6 only)' }

# =============================================================================
# Step 1 - NVIDIA driver and compute capability
# =============================================================================
$script:GpuName = ''
$script:GpuCc = ''
$script:GpuDriver = ''
$script:GpuVram = ''
$script:IsBlackwell = $false

function Test-NvidiaDriver {
    Write-Step '1/6  NVIDIA driver'

    if (-not (Test-Have 'nvidia-smi')) {
        Stop-Bootstrap 'nvidia-smi is not on PATH, so there is no usable NVIDIA driver here.' @(
            'localgpu runs its models on the GPU; without a driver there is nothing to run'
            'them on, and Ollama would fall back to the CPU without telling you.'
            ''
            'Install the NVIDIA driver for this machine, reboot, confirm that "nvidia-smi"'
            'prints a table, then re-run this script.'
        )
    }

    $null = & nvidia-smi 2>&1
    if ($LASTEXITCODE -ne 0) {
        Stop-Bootstrap 'nvidia-smi is installed but returned an error.' @(
            'That usually means the kernel driver and the userspace driver are different'
            'versions - most often after an unattended driver upgrade without a reboot.'
            ''
            'Reboot, run "nvidia-smi" by hand, and re-run this script once it prints a table.'
        )
    }

    # compute_cap is a relatively recent query field. An older driver rejects it, which is
    # not fatal - we just cannot name the architecture in the step 6 diagnosis.
    $query = & nvidia-smi --query-gpu=name,compute_cap,driver_version,memory.total --format=csv,noheader,nounits 2>$null
    if ($query) {
        $fields = ("$(@($query)[0])".Trim() -split '\s*,\s*')
        if ($fields.Count -ge 4) {
            $script:GpuName   = $fields[0]
            $script:GpuCc     = $fields[1]
            $script:GpuDriver = $fields[2]
            $script:GpuVram   = $fields[3]
        }
    }

    if (-not $script:GpuName) {
        $script:GpuName = "$(@(& nvidia-smi --query-gpu=name --format=csv,noheader 2>$null)[0])".Trim()
        $script:GpuDriver = "$(@(& nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>$null)[0])".Trim()
        Write-Warn2 'This driver does not answer --query-gpu=compute_cap; compute capability unknown.'
    }

    if (-not $script:GpuName) {
        Stop-Bootstrap 'nvidia-smi ran but reported no GPU.' @(
            'Check that the card is visible to the OS and that nothing holds it exclusively.'
        )
    }

    $cc = if ($script:GpuCc) { $script:GpuCc } else { 'unknown' }
    $drv = if ($script:GpuDriver) { $script:GpuDriver } else { 'unknown' }
    $vram = if ($script:GpuVram) { "   VRAM: $($script:GpuVram) MiB" } else { '' }
    Write-Ok "GPU     : $($script:GpuName)"
    Write-Ok "driver  : $drv"
    Write-Ok "compute : $cc$vram"

    # sm_120 is the interesting case: new enough that an Ollama built against an older
    # CUDA runtime has no kernel for it and falls back to the CPU. Say so now, so the
    # step 6 diagnosis is not the first the reader hears of it.
    if ($script:GpuCc -like '12.*') {
        $script:IsBlackwell = $true
        Write-Info 'Compute capability 12.x is Blackwell (sm_120). Ollama needs to have been built'
        Write-Info 'against CUDA 12.8 or newer to have a kernel for it; older builds run the model'
        Write-Info 'on the CPU instead, silently. Step 6 checks for exactly that.'
    }
}

# =============================================================================
# Step 2 - Ollama
# =============================================================================
function Install-Ollama {
    Write-Step '2/6  Ollama'

    if (Test-Have 'ollama') {
        $version = "$(@(& ollama --version 2>&1)[0])".Trim()
        if (-not $version) { $version = 'version unknown' }
        Write-Skip "Ollama already installed - $version"
        return
    }

    if ($DryRun) {
        Write-Info 'Would install Ollama: winget install --id Ollama.Ollama -e'
        return
    }

    if (-not $Yes -and -not [Console]::IsInputRedirected) {
        $answer = Read-Host '    Ollama is not installed. Install it now with winget? [Y/n]'
        if ($answer -match '^[Nn]') {
            Stop-Bootstrap 'Ollama is required and was declined.' @(
                'Install it yourself from https://ollama.com/download, then re-run with'
                '-VerifyOnly to check the GPU path.'
            )
        }
    }

    if (-not (Test-Have 'winget')) {
        Stop-Bootstrap 'winget is not available, and it is how this script installs Ollama.' @(
            'winget ships with App Installer on Windows 11. Either install App Installer'
            'from the Microsoft Store, or install Ollama by hand from'
            'https://ollama.com/download and re-run this script - step 2 will then detect'
            'it and skip.'
        )
    }

    Write-Info 'Installing Ollama via winget ...'
    & winget install --id Ollama.Ollama -e --silent `
        --accept-source-agreements --accept-package-agreements
    # winget returns 0x8A150061 (-1978335135) for "no applicable upgrade / already
    # installed", which is a success for our purposes, not a failure.
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335135) {
        Stop-Bootstrap "winget exited $LASTEXITCODE installing Ollama.Ollama." @(
            'Re-run it by hand to see its output:'
            '  winget install --id Ollama.Ollama -e'
        )
    }

    # Replays the registry PATH winget just edited, then falls back to the per-user
    # install directory, which the PATH edit does not always reach in time.
    if (-not (Resolve-OllamaOnPath)) {
        Stop-Bootstrap 'winget reported success but "ollama" is still not on PATH.' @(
            'Open a new PowerShell window and re-run this script; the installer edits the'
            'user PATH, which an already-running shell does not always pick up.'
        )
    }

    Write-Ok "Installed Ollama - $(@(& ollama --version 2>&1)[0])"
}

# =============================================================================
# Step 3 - venv + numpy
# =============================================================================
function Install-LocalGpuVenv {
    Write-Step "3/6  Python venv at $($script:VenvDir)"

    $py = Resolve-SystemPython
    if (-not $py) {
        Stop-Bootstrap 'No usable Python found: tried python3, then python, then py.' @(
            'None of them is on PATH with a version of 3.9 or newer, or the only "python3"'
            'here is the Microsoft Store App Execution Alias, which answers no version query.'
            ''
            'Install Python 3.9+ from https://www.python.org/downloads/ (tick "Add python.exe'
            'to PATH") or "winget install --id Python.Python.3.13 -e", then re-run.'
        )
    }
    Write-Info "python: $py ($(& $py -c 'import sys; print(sys.version.split()[0])' 2>$null))"

    $vpy = Get-VenvPython
    if ($vpy) {
        Write-Skip "venv already exists at $($script:VenvDir)"
    } elseif ($DryRun) {
        Write-Info "Would create the venv: $py -m venv $($script:VenvDir)"
        Write-Info "Would create the index directory: $($script:IndexDir)"
        Write-Info "Would pip install numpy, and -r $($script:Requirements) if that file exists"
        Write-Info "Would pip install the localgpu CLI editable from $($script:ScriptDir), if pyproject.toml is there"
        return
    } else {
        $null = New-Item -ItemType Directory -Force -Path $script:LocalGpuHome -ErrorAction SilentlyContinue
        & $py -m venv $script:VenvDir
        if ($LASTEXITCODE -ne 0) {
            Stop-Bootstrap "'$py -m venv $($script:VenvDir)' failed." @(
                'Run it by hand to see the error. A venv failure on Windows is usually a'
                'path-length or permissions problem under LOCALAPPDATA.'
            )
        }
        $vpy = Get-VenvPython
        if (-not $vpy) {
            Stop-Bootstrap "The venv was created but no interpreter appeared under $($script:VenvDir)."
        }
        Write-Ok 'Created the venv'
    }

    if ($DryRun) {
        Write-Info "Would create the index directory: $($script:IndexDir)"
        Write-Info "Would pip install numpy, and -r $($script:Requirements) if that file exists"
        Write-Info "Would pip install the localgpu CLI editable from $($script:ScriptDir), if pyproject.toml is there"
        return
    }

    $null = New-Item -ItemType Directory -Force -Path $script:IndexDir -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $script:IndexDir) { Write-Ok "index directory: $($script:IndexDir)" }

    # Detect first: whether numpy imports is the thing that actually matters, and it is a
    # cheaper and truer question than parsing pip's output.
    $numpyVersion = "$(& $vpy -c 'import numpy; print(numpy.__version__)' 2>$null)".Trim()
    $haveRequirements = Test-Path -LiteralPath $script:Requirements

    if ($numpyVersion -and -not $haveRequirements) {
        Write-Skip "numpy already installed ($numpyVersion), and there is no mcp\requirements.txt yet"
        return
    }

    # pip's own idempotence is the detection for the requirements file, so compare the
    # frozen set before and after rather than trusting an exit code to mean "changed".
    $before = (& $vpy -m pip freeze 2>$null) -join "`n"

    if (-not $numpyVersion) {
        Write-Info 'Installing numpy into the venv ...'
        & $vpy -m pip install --quiet --upgrade pip 2>&1 | Out-Null
        & $vpy -m pip install --quiet numpy
        if ($LASTEXITCODE -ne 0) {
            Stop-Bootstrap "pip could not install numpy into $($script:VenvDir)." @(
                'Re-run it by hand to see the error:'
                "  $vpy -m pip install numpy"
            )
        }
    } else {
        Write-Skip "numpy already installed ($numpyVersion)"
    }

    if ($haveRequirements) {
        Write-Info "Installing $($script:Requirements) ..."
        & $vpy -m pip install --quiet -r $script:Requirements
        if ($LASTEXITCODE -ne 0) {
            Stop-Bootstrap "pip could not install $($script:Requirements)." @(
                'Re-run it by hand to see the error:'
                "  $vpy -m pip install -r $($script:Requirements)"
            )
        }
    } else {
        Write-Info 'No mcp\requirements.txt yet - installed numpy only.'
    }

    # The `localgpu` console script, which is what `localgpu shell` resolves to.
    # EDITABLE on purpose: cli\localgpu_cli.py finds its sibling mcp\ directory
    # relative to its own __file__, and a copied install puts that __file__ in
    # site-packages, where mcp\ does not exist. Do not drop the -e.
    $projectFile = Join-Path $script:ScriptDir 'pyproject.toml'
    if (Test-Path -LiteralPath $projectFile) {
        & $vpy -c 'import localgpu_cli' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Skip 'localgpu CLI already installed'
        } else {
            Write-Info 'Installing the localgpu CLI (editable) ...'
            & $vpy -m pip install --quiet -e $script:ScriptDir
            if ($LASTEXITCODE -ne 0) {
                Stop-Bootstrap "pip could not install the localgpu CLI from $($script:ScriptDir)." @(
                    'Re-run it by hand to see the error:'
                    "  $vpy -m pip install -e $($script:ScriptDir)"
                )
            }
        }
    } else {
        Write-Info 'No pyproject.toml next to this script - skipping the localgpu CLI.'
    }

    $after = (& $vpy -m pip freeze 2>$null) -join "`n"
    if ($before -eq $after) {
        Write-Skip 'Python dependencies already installed - pip changed nothing'
    } else {
        Write-Ok "Python dependencies installed (numpy $(& $vpy -c 'import numpy; print(numpy.__version__)' 2>$null))"
    }
}

# =============================================================================
# Step 4 - models
# =============================================================================
# 'ollama list' prints NAME first, and a bare 'nomic-embed-text' is listed as
# 'nomic-embed-text:latest' - so match the tag exactly if one was asked for, and allow
# the implicit :latest otherwise.
function Test-OllamaModelPresent {
    param([string]$Model)
    $listed = @(& ollama list 2>$null | Select-Object -Skip 1 |
        ForEach-Object { ($_ -split '\s+')[0] } | Where-Object { $_ })
    if (-not $listed) { return $false }
    if ($Model -like '*:*') { return [bool]($listed -contains $Model) }
    return [bool](($listed -contains $Model) -or ($listed -contains "${Model}:latest"))
}

function Install-OllamaModel {
    param([string]$Model)
    if (Test-OllamaModelPresent -Model $Model) {
        Write-Skip "$Model already installed"
        return
    }
    if ($DryRun) {
        Write-Info "Would pull: ollama pull $Model"
        return
    }
    Write-Info "Pulling $Model (a first run downloads gigabytes) ..."
    & ollama pull $Model
    if ($LASTEXITCODE -ne 0) {
        Stop-Bootstrap "'ollama pull $Model' failed." @(
            'Check that the Ollama server is running and that this machine can reach'
            'registry.ollama.ai, then re-run.'
        )
    }
    Write-Ok "Pulled $Model"
}

function Install-LocalGpuModels {
    Write-Step '4/6  Models'
    if ($SkipModels) {
        Write-Skip "-SkipModels given - not pulling $($script:EmbedModel) or $($script:ChatModel)"
        return
    }
    if (-not (Test-Have 'ollama')) {
        if ($DryRun) {
            Write-Info "Would pull: ollama pull $($script:EmbedModel)"
            Write-Info "Would pull: ollama pull $($script:ChatModel)"
            return
        }
        Stop-Bootstrap 'Ollama is not on PATH, so no model can be pulled.'
    }
    Install-OllamaModel -Model $script:EmbedModel
    Install-OllamaModel -Model $script:ChatModel
}

# =============================================================================
# Step 5 - VRAM discipline
# =============================================================================
# 8 GB of VRAM does not hold a 7B chat model and an embedding model at once. With more
# than one loadable, Ollama keeps the idle one resident, runs out of VRAM, and spills
# whichever it is asked for next onto the CPU - which looks exactly like the Blackwell
# fallback step 6 hunts for, and is not it. Pinning the limit to 1 removes that whole
# class of confusion.
function Set-VramDiscipline {
    Write-Step '5/6  VRAM discipline (OLLAMA_MAX_LOADED_MODELS=1)'

    # Read it back first - an already-correct value is the "already installed" case.
    $current = [Environment]::GetEnvironmentVariable('OLLAMA_MAX_LOADED_MODELS', 'User')
    if ($current -eq '1') {
        Write-Skip 'OLLAMA_MAX_LOADED_MODELS is already 1 in the User environment scope'
    } elseif ($DryRun) {
        $shown = if ($current) { "'$current'" } else { '(unset)' }
        Write-Info "Would set the User environment variable OLLAMA_MAX_LOADED_MODELS=1 (currently $shown)"
    } else {
        [Environment]::SetEnvironmentVariable('OLLAMA_MAX_LOADED_MODELS', '1', 'User')
        Write-Ok 'Set OLLAMA_MAX_LOADED_MODELS=1 in the User environment scope'
        Write-Note 'The Ollama tray app reads this at startup, so restart it (or sign out and'
        Write-Note 'back in) for an already-running server to pick the change up.'
    }

    # Whatever the persistence story, this process and step 6 need it now.
    $env:OLLAMA_MAX_LOADED_MODELS = '1'

    Write-Info 'keep_alive: the MCP client sends a short keep_alive on every request - seconds for'
    Write-Info "an embedding call, minutes at most for a chat call - instead of Ollama's 5m default,"
    Write-Info 'so a model it has finished with releases its VRAM rather than squatting on it. That'
    Write-Info 'is what lets one 8 GB card serve both an embedding model and a 7B chat model;'
    Write-Info 'OLLAMA_MAX_LOADED_MODELS=1 is the backstop for when it does not.'
}

# =============================================================================
# Step 6 - VERIFY
# =============================================================================
function Start-OllamaServer {
    if (Test-OllamaUp) { return $true }
    Write-Info "Ollama is not answering on $($script:OllamaUrl) - starting it ..."
    try {
        Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden | Out-Null
    } catch {
        return $false
    }
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 2
        if (Test-OllamaUp) { Write-Ok 'Ollama server is up'; return $true }
    }
    return $false
}

# Count the floats in an embed response. ConvertFrom-Json is in the box here, so unlike
# the bash twin there is no "no parser available" branch.
function Get-EmbedDimension {
    param([string]$Body)
    try { $payload = $Body | ConvertFrom-Json -ErrorAction Stop } catch { return $null }
    $vector = $null
    if ($payload.PSObject.Properties.Name -contains 'embeddings') { $vector = $payload.embeddings }
    if (-not $vector -and $payload.PSObject.Properties.Name -contains 'embedding') { $vector = $payload.embedding }
    if (-not $vector) { return $null }
    # /api/embed returns a list of vectors; /api/embeddings returns one flat vector.
    if ($vector.Count -gt 0 -and ($vector[0] -is [array] -or $vector[0] -is [System.Collections.IList])) {
        $vector = $vector[0]
    }
    if ($vector.Count -eq 0) { return $null }
    foreach ($value in $vector) {
        if ($value -isnot [double] -and $value -isnot [single] -and $value -isnot [int] -and $value -isnot [long] -and $value -isnot [decimal]) {
            return $null
        }
    }
    return $vector.Count
}

# The 'ollama ps' row for this model, or '' if it has no row.
function Get-OllamaProcessorRow {
    param([string]$Model)
    $base = ($Model -split ':')[0]
    $rows = @(& ollama ps 2>$null | Select-Object -Skip 1 | Where-Object { $_ -like "*$base*" })
    if ($rows.Count -eq 0) { return '' }
    return "$($rows[0])"
}

# The whole reason this script exists. Never returns on a GPU failure.
function Assert-ModelOnGpu {
    param([string]$Model, [string]$Label)

    $psOut = (& ollama ps 2>&1) -join "`n"
    $row = Get-OllamaProcessorRow -Model $Model

    if (-not $row) {
        Stop-Bootstrap "$Label ran, but 'ollama ps' does not list $Model as resident." @(
            'The request was sent with an explicit 60s keep_alive, so the model should still'
            'have been loaded when we looked. A model that is gone this fast means the server'
            'evicted it immediately - which on this hardware means it could not fit, or could'
            'not run, on the GPU.'
            ''
            "Verbatim 'ollama ps' output:"
            $psOut
        )
    }

    # PROCESSOR reads '100% GPU', '100% CPU', or a split like '38%/62% CPU/GPU'. Any
    # mention of CPU at all is an offload, and an offload is a failure here: a partial one
    # is still the slow path, and on 8 GB it is usually the prelude to a full one.
    #
    # The CPU test MUST stay above the GPU test. A split row contains both words, so
    # testing for GPU first reports '38%/62% CPU/GPU' as a pass - a green tick on the
    # exact condition this function exists to catch. Do not reorder these.
    if ($row -match 'CPU') {
        $archNote = if ($script:IsBlackwell) {
            "This is a Blackwell card (compute capability $($script:GpuCc), sm_120)."
        } else {
            $cc = if ($script:GpuCc) { $script:GpuCc } else { 'unknown' }
            "This GPU reports compute capability $cc."
        }
        $vram = if ($script:GpuVram) { "$($script:GpuVram) MiB" } else { "this card's VRAM" }
        Stop-Bootstrap "$Label is running on the CPU, not the GPU." @(
            "$archNote Ollama only has a kernel for sm_120 if it was built against CUDA"
            '12.8 or newer. An older build finds no usable kernel, says nothing about it,'
            'and quietly runs the model on the CPU instead - roughly an order of magnitude'
            'slower, and not what localgpu is for.'
            ''
            "Verbatim 'ollama ps' output:"
            $psOut
            ''
            'What to do:'
            '  1. Update Ollama to the newest release, then re-run with -VerifyOnly:'
            '       winget upgrade --id Ollama.Ollama -e'
            '  2. If it still offloads, check that nothing else is holding the VRAM:'
            '       nvidia-smi'
            "  3. A partial split ('38%/62% CPU/GPU') with a clean nvidia-smi means the model"
            "     does not fit in $vram - use a smaller quantisation."
        )
    } elseif ($row -match 'GPU') {
        Write-Ok "$Label is on the GPU - $row"
    } else {
        Stop-Bootstrap "${Label}: could not read a PROCESSOR column out of 'ollama ps'." @(
            'This script refuses to report a pass it did not actually observe.'
            ''
            "Verbatim 'ollama ps' output:"
            $psOut
        )
    }
}

function Invoke-Verification {
    Write-Step '6/6  VERIFY - a real request, on the GPU'

    if ($DryRun) {
        Write-Info "Would POST an embed request for $($script:EmbedModel) to $($script:OllamaUrl)/api/embed"
        Write-Info "Would then require 'ollama ps' to show it on GPU with no CPU offload"
        if (-not $SkipModels) {
            Write-Info "Would do the same for $($script:ChatModel) via $($script:OllamaUrl)/api/generate"
        }
        return
    }

    if (-not (Test-Have 'ollama')) {
        Stop-Bootstrap 'Ollama is not on PATH, so nothing can be verified.'
    }
    if (-not (Start-OllamaServer)) {
        Stop-Bootstrap "Ollama is not answering on $($script:OllamaUrl) after 30 seconds." @(
            "Start it by hand ('ollama serve') and re-run with -VerifyOnly."
        )
    }

    # --- the embedding model ---
    Write-Info "Embedding a test string with $($script:EmbedModel) ..."
    # /api/embed is the current endpoint; /api/embeddings is the older one, still served.
    # Try the new one and fall back, so this works either side of that change.
    $body = Invoke-OllamaPost -Path '/api/embed' -TimeoutSec 180 -Body @{
        model      = $script:EmbedModel
        input      = 'localgpu bootstrap verification'
        keep_alive = '60s'
    }
    if (-not $body) {
        $body = Invoke-OllamaPost -Path '/api/embeddings' -TimeoutSec 180 -Body @{
            model      = $script:EmbedModel
            prompt     = 'localgpu bootstrap verification'
            keep_alive = '60s'
        }
    }
    if (-not $body) {
        Stop-Bootstrap "The embed request to $($script:OllamaUrl) returned nothing." @(
            'Reproduce it by hand:'
            "  curl.exe -s $($script:OllamaUrl)/api/embed -d '{\""model\"":\""$($script:EmbedModel)\"",\""input\"":\""hi\""}'"
        )
    }
    if ($body -match '"error"') {
        Stop-Bootstrap 'Ollama rejected the embed request.' @('Its reply, verbatim:', $body)
    }

    $dimension = Get-EmbedDimension -Body $body
    if ($dimension) {
        Write-Ok "Embedded - $($script:EmbedModel) returned $dimension dimensions"
    } else {
        Stop-Bootstrap 'The embed reply contained no usable embedding.' @('Its reply, verbatim:', $body)
    }

    Assert-ModelOnGpu -Model $script:EmbedModel -Label $script:EmbedModel

    # --- the chat model ---
    # Verifying only the 137M embedding model would be a false green: something that small
    # runs anywhere. The 7B chat model at q4_K_M is the one that has to fit and has to find
    # an sm_120 kernel, so it is the one worth asking.
    if ($SkipModels) {
        Write-Skip "-SkipModels given - not loading $($script:ChatModel) to check its placement"
    } else {
        Write-Info "Generating one token with $($script:ChatModel) (loads ~5 GB, give it a minute) ..."
        $body = Invoke-OllamaPost -Path '/api/generate' -TimeoutSec 600 -Body @{
            model      = $script:ChatModel
            prompt     = 'ok'
            stream     = $false
            options    = @{ num_predict = 1 }
            keep_alive = '60s'
        }
        if (-not $body) {
            Stop-Bootstrap "The generate request for $($script:ChatModel) returned nothing." @(
                'Reproduce it by hand:'
                "  ollama run $($script:ChatModel) ok"
            )
        }
        if ($body -match '"error"') {
            Stop-Bootstrap "Ollama rejected the generate request for $($script:ChatModel)." @(
                'Its reply, verbatim:', $body
            )
        }
        Write-Ok "$($script:ChatModel) answered"
        Assert-ModelOnGpu -Model $script:ChatModel -Label $script:ChatModel
    }

    Write-Host ''
    Write-Host 'Verified: every model checked loads on the GPU with no CPU offload.' -ForegroundColor Green
}

# =============================================================================
# Run
# =============================================================================
# Step 1 always runs: it only reads, and step 6's diagnosis needs its answers.
Test-NvidiaDriver

# Before anything asks "is Ollama installed?" - steps 2, 4 and 6 all do, and -VerifyOnly
# skips step 2 entirely, so this has to happen here rather than inside any one of them.
$null = Resolve-OllamaOnPath

if ($VerifyOnly) {
    Write-Skip '-VerifyOnly given - skipping steps 2-5'
    Invoke-Verification
} else {
    Install-Ollama
    Install-LocalGpuVenv
    Add-LocalGpuVenvToPath
    Install-LocalGpuModels
    Set-VramDiscipline
    Invoke-Verification
}

Write-Step 'Done'
Write-Ok "install root : $($script:LocalGpuHome)"
Write-Ok "venv         : $($script:VenvDir)"
Write-Ok "index        : $($script:IndexDir)"
Write-Ok "models       : $($script:EmbedModel), $($script:ChatModel)"
if ($DryRun) {
    Write-Info 'This was a -DryRun. Nothing was installed, written, or verified.'
} else {
    Write-Info 'Re-run any time; every step above detects before it acts.'
    Write-Info 'To re-check the GPU path alone: .\bootstrap.ps1 -VerifyOnly'
    if (-not $VerifyOnly) {
        Write-Info ''
        Write-Info 'IMPORTANT: this shell does not see the PATH change above - open a NEW'
        Write-Info 'PowerShell window before "localgpu" will resolve there.'
    }
}

$ErrorActionPreference = $script:PreviousErrorActionPreference
