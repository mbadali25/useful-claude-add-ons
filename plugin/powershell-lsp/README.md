# powershell-lsp

PowerShell code intelligence for Claude Code, through
[PowerShell Editor Services](https://github.com/PowerShell/PowerShellEditorServices)
(PSES) hosted in **Windows PowerShell 5.1** (`powershell.exe`). **Windows only**,
for machines that do not have PowerShell 7. The plugin registers one LSP server
and ships one launcher script. No hooks, no commands, no agents, no skills.

> **Nobody has run this plugin.** It was written on Linux, where Windows
> PowerShell 5.1 does not exist. Its launcher is the same file `pwsh-lsp` ships,
> and that file was run under PowerShell 7 only. Read "Verified, and not" before
> relying on it.

## Use pwsh-lsp instead if you can

Editor Services supports Windows PowerShell 5.1 "on a best-effort basis", in its
maintainers' words; PowerShell 7 is the host they target. If the machine has
`pwsh`, or can have it, install [`pwsh-lsp`](../pwsh-lsp).

This plugin and `pwsh-lsp` serve the same three extensions. Claude Code starts
one language server per file extension: the first plugin registered wins and
the other gets a warning. So a machine gets exactly one of them:

| The machine has | Install |
|---|---|
| PowerShell 7 (`pwsh` on `PATH`), any operating system | `pwsh-lsp` |
| Windows with only Windows PowerShell 5.1 | **`powershell-lsp`** |

`scripts/install-prerequisites.sh` / `.ps1` enforce this in both menu rows that
can install them. They install `powershell-lsp` only on Windows, only where
`pwsh` does not resolve, and only where `pwsh-lsp` is not already installed.
Everywhere else they refuse it and say why.

## Install

```powershell
claude plugin marketplace add mbadali25/useful-claude-add-ons
claude plugin install powershell-lsp@useful-claude-add-ons --scope user
```

**The plugin does not install Editor Services.** PSES is not on the PowerShell
Gallery; it is published as `PowerShellEditorServices.zip` on its GitHub
releases page. Unzip it into `%LOCALAPPDATA%\powershell-editor-services`, so
that `PowerShellEditorServices\Start-EditorServices.ps1` sits directly inside
it. To keep it somewhere else, set `PSES_BUNDLE_PATH` to the directory that
contains the `PowerShellEditorServices` folder.

The **LSP plugins** row of `install-prerequisites.ps1` does that step: it
downloads the v4.7.0 zip, checks it against a pinned sha256
(`5084f0326cc88539e9d880b08f6c52ce5be4672bb8ecee8921e35f8895a6b9d7`, the digest
GitHub publishes for that asset), refuses anything else, and unzips it there.

## What it registers

```json
"lspServers": {
  "powershell": {
    "command": "powershell",
    "args": ["-NoLogo", "-NoProfile", "-ExecutionPolicy", "RemoteSigned", "-File", "${CLAUDE_PLUGIN_ROOT}/scripts/pses-launch.ps1"],
    "extensionToLanguage": { ".ps1": "powershell", ".psm1": "powershell", ".psd1": "powershell" },
    "startupTimeout": 60000
  }
}
```

The block lives in `.claude-plugin/plugin.json`, not in a separate `.lsp.json`,
because `claude plugin validate` checks an inline block and does not read
`.lsp.json` at all.

### `-ExecutionPolicy RemoteSigned`, and what it changes

Windows PowerShell 5.1 on a Windows client ships with the execution policy
`Restricted`, under which `powershell -File` runs no script at all, the
launcher included. So this plugin starts its own server process with
`-ExecutionPolicy RemoteSigned`.

- It applies to **that one process**. It does not change the machine's or the
  user's policy, and nothing is written to the registry.
- `RemoteSigned`, not `Bypass`: scripts marked as downloaded from the internet
  still have to be signed. The launcher is a local file; the PSES release is
  signed by Microsoft.
- A policy set by Group Policy overrides the command line. On such a machine
  the server will not start, and that is the administrator's decision to make,
  not this plugin's.

If you would rather not have a plugin pass that flag, do not install this one.
`pwsh-lsp` passes no execution-policy flag.

## The launcher

`scripts/pses-launch.ps1` is the same file, byte for byte, that `pwsh-lsp`
ships; [`pwsh-lsp`'s README](../pwsh-lsp/README.md) explains what it does and
why. It is written for 5.1: no ternary, no `??`, no `$IsWindows`.
`scripts/_test/lsp-stack-tools.sh` fails when the two copies differ.

## Verified, and not

Verified: `claude plugin validate --strict` accepts the manifest. The launcher
parses and runs under PowerShell 7 on Linux, where `pwsh-lsp` was tested with
it. The install scripts' rule for choosing between the two plugins is covered by
the regression suite on Linux, with the Windows conditions simulated.

Not verified, which is everything that matters for this plugin:

- **That it starts at all.** No Windows machine was available. The launcher has
  never run under Windows PowerShell 5.1, PSES has never been loaded by it
  there, and no LSP `initialize` was ever answered through this plugin.
- **The `%LOCALAPPDATA%` branch of the launcher**, which only Windows takes.
- **`-ExecutionPolicy RemoteSigned` being sufficient** on a default Windows
  client, and the behaviour under a Group Policy.
- **`install-prerequisites.ps1` on Windows**: the real download through
  `Invoke-WebRequest` on 5.1, `Expand-Archive` there, and the 5.1-only pick.
  Those functions were run under PowerShell 7 on Linux.
- **A Claude Code session using the server.**

If you run it on Windows, the three things worth reporting are whether the
server answers, what `powershell -NoProfile -ExecutionPolicy RemoteSigned -File
<plugin>\scripts\pses-launch.ps1` prints on stderr when it does not, and the
Windows build.
