# pwsh-lsp

PowerShell code intelligence for Claude Code, through
[PowerShell Editor Services](https://github.com/PowerShell/PowerShellEditorServices)
(PSES) hosted in **PowerShell 7** (`pwsh`). Windows, Linux and macOS. The plugin
registers one LSP server and ships one launcher script. No hooks, no commands,
no agents, no skills.

## Install one of pwsh-lsp and powershell-lsp, never both

This plugin and [`powershell-lsp`](../powershell-lsp) serve the same three
extensions. Claude Code starts one language server per file extension: the
first plugin registered wins and the other gets a warning. So a machine gets
exactly one of them:

| The machine has | Install |
|---|---|
| PowerShell 7 (`pwsh` on `PATH`), any operating system | **`pwsh-lsp`** |
| Windows with only Windows PowerShell 5.1 | `powershell-lsp` |

`scripts/install-prerequisites.sh` / `.ps1` enforce this in both menu rows that
can install them. Where `pwsh` resolves they install `pwsh-lsp` and refuse
`powershell-lsp`; where one of the two is already installed they do not add the
other, and say which command switches.

## Install

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
claude plugin install pwsh-lsp@useful-claude-add-ons --scope user
```

**The plugin installs neither PowerShell nor Editor Services.** It needs both:

1. `pwsh` (PowerShell 7) on `PATH`. See <https://aka.ms/powershell>.
2. An unzipped PSES release. PSES is not on the PowerShell Gallery; it is
   published as `PowerShellEditorServices.zip` on its GitHub releases page.
   Unzip it into the per-user directory the launcher reads:

   | Operating system | Directory |
   |---|---|
   | Linux, macOS | `~/.local/share/powershell-editor-services` |
   | Windows | `%LOCALAPPDATA%\powershell-editor-services` |

   so that `PowerShellEditorServices/Start-EditorServices.ps1` sits directly
   inside it. To keep it somewhere else, set `PSES_BUNDLE_PATH` to the directory
   that contains the `PowerShellEditorServices` folder.

The **LSP plugins** row of the install scripts does step 2: it downloads the
v4.7.0 zip, checks it against a pinned sha256
(`5084f0326cc88539e9d880b08f6c52ce5be4672bb8ecee8921e35f8895a6b9d7`, the digest
GitHub publishes for that asset), refuses anything else, and unzips it into the
directory above. It does **not** install PowerShell 7: without `pwsh` on Linux
or macOS it stops and says so.

## What it registers

```json
"lspServers": {
  "powershell": {
    "command": "pwsh",
    "args": ["-NoLogo", "-NoProfile", "-File", "${CLAUDE_PLUGIN_ROOT}/scripts/pses-launch.ps1"],
    "extensionToLanguage": { ".ps1": "powershell", ".psm1": "powershell", ".psd1": "powershell" },
    "startupTimeout": 60000
  }
}
```

The block lives in `.claude-plugin/plugin.json`, not in a separate `.lsp.json`,
because `claude plugin validate` checks an inline block and does not read
`.lsp.json` at all.

- `-NoProfile` keeps the user's profile script out of the server: anything a
  profile prints would land in the LSP stream.
- `startupTimeout` is 60 seconds. PSES loads the .NET runtime, PSScriptAnalyzer
  and PSReadLine before it answers; it took a few seconds where it was measured.

## Why a launcher

`scripts/pses-launch.ps1` exists for three reasons:

- **PSES is a directory, not a command.** Where it was unzipped differs per
  machine, so the path cannot be written into a static LSP config. The launcher
  resolves it at start-up: `PSES_BUNDLE_PATH`, then the per-user directory.
- **PSES writes a session file.** Started without `-SessionDetailsPath`,
  `Start-EditorServices.ps1` writes `PowerShellEditorServices.json` into the
  current directory, which is your project. The launcher always points it at a
  file in the temp directory and removes that file on exit.
- **Stdout is the LSP stream.** The launcher prints nothing to it. When PSES is
  missing it writes one line to stderr and exits 1.

The same file, byte for byte, ships in `powershell-lsp`. It is written for
Windows PowerShell 5.1 and runs unchanged on 7. `scripts/_test/lsp-stack-tools.sh`
fails when the two copies differ.

## Verified, and not

Verified on Linux, with PSES v4.7.0, under PowerShell 7.6.6 (Ubuntu 26.04) and
7.4.2 (the `mcr.microsoft.com/powershell` container image): the server started
from the exact command above in an empty directory, answered an LSP
`initialize` request over stdio, answered `shutdown` and exited 0. The first
bytes on stdout were the `Content-Length` header, stderr was empty, the project
directory was still empty afterwards, and no session file was left in the temp
directory. With `PSES_BUNDLE_PATH` pointing at nothing, the launcher wrote its
one line to stderr, nothing to stdout, and exited 1. In the container the
release was put in place by the install scripts themselves, both the `.sh` and
the `.ps1`, with a real download and a real sha256 check.

Not verified:

- **Windows and macOS.** Nothing here was run on either. That includes the
  `%LOCALAPPDATA%` branch of the launcher, which only a Windows machine takes.
- **Any request beyond `initialize` and `shutdown`.** No `.ps1` file was
  opened. The `initialize` reply lists three static capabilities
  (`textDocumentSync`, `workspace`, `experimental`): PSES registers hover,
  definition, references and the rest dynamically after start-up, and whether
  Claude Code's LSP client takes up those registrations was not tested.
- **A Claude Code session using the server.**
- **Any PSES release other than v4.7.0.**
