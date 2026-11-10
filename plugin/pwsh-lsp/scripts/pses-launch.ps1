# Start PowerShell Editor Services (PSES) as an LSP server on stdio.
#
# Shipped byte-identical in two plugins: pwsh-lsp runs it under PowerShell 7
# (pwsh) and powershell-lsp under Windows PowerShell 5.1 (powershell.exe).
# scripts/_test/lsp-stack-tools.sh fails when the two copies differ. Everything
# here therefore has to parse and run on 5.1: no ternary, no '??', no $IsWindows.
#
# PSES is not on the PowerShell Gallery and neither plugin vendors it (the
# release is about 20 MB). This file finds an unzipped release at start-up:
#
#   1. $env:PSES_BUNDLE_PATH, when set - the directory that CONTAINS the
#      'PowerShellEditorServices' folder. Set and wrong is an error, never a
#      silent fall-through to rule 2.
#   2. The per-user data directory of the operating system, which is also where
#      scripts/install-prerequisites.sh / .ps1 unzip the pinned release:
#        Windows       %LOCALAPPDATA%\powershell-editor-services
#        Linux, macOS  ~/.local/share/powershell-editor-services
#      XDG_DATA_HOME is deliberately not consulted: three files have to agree
#      on this path, and one fixed rule per platform is what keeps them agreed.
#
# Stdout belongs to the LSP stream. Nothing in this file writes to it: every
# message goes to stderr, and a failure is one line there and exit code 1.
#
# -SessionDetailsPath is always passed. Without it PSES writes
# 'PowerShellEditorServices.json' into the current directory, which is the
# user's project.

$ErrorActionPreference = 'Stop'

function Stop-Launch {
    param([string]$Message)
    [Console]::Error.WriteLine("pses-launch: $Message")
    exit 1
}

$fromEnv = $env:PSES_BUNDLE_PATH
if ($fromEnv) {
    $bundle = $fromEnv
    $origin = 'PSES_BUNDLE_PATH'
} elseif ($env:OS -eq 'Windows_NT' -and $env:LOCALAPPDATA) {
    $bundle = Join-Path $env:LOCALAPPDATA 'powershell-editor-services'
    $origin = 'the default location'
} else {
    $bundle = Join-Path (Join-Path (Join-Path $HOME '.local') 'share') 'powershell-editor-services'
    $origin = 'the default location'
}

$start = Join-Path (Join-Path $bundle 'PowerShellEditorServices') 'Start-EditorServices.ps1'
if (-not (Test-Path -LiteralPath $start -PathType Leaf)) {
    Stop-Launch "PowerShell Editor Services not found: '$start' does not exist ($origin). Unzip the PowerShellEditorServices.zip release into '$bundle', or run the 'LSP plugins' row of scripts/install-prerequisites, then reload."
}

$sessionFile = Join-Path ([System.IO.Path]::GetTempPath()) ("pses-session-{0}.json" -f $PID)

try {
    & $start -Stdio `
        -HostName 'Claude Code' -HostProfileId 'ClaudeCode' -HostVersion '1.0.0' `
        -BundledModulesPath $bundle `
        -LogLevel Error `
        -SessionDetailsPath $sessionFile
} catch {
    Stop-Launch "PowerShell Editor Services failed to start: $($_.Exception.Message)"
} finally {
    if (Test-Path -LiteralPath $sessionFile) {
        Remove-Item -LiteralPath $sessionFile -Force -ErrorAction SilentlyContinue
    }
}
