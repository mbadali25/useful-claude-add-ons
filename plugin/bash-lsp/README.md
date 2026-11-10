# bash-lsp

Bash code intelligence for Claude Code, through
[`bash-language-server`](https://www.npmjs.com/package/bash-language-server).
The plugin registers one LSP server and nothing else: no hooks, no commands, no
agents, no skills.

## Install

```
/plugin install bash-lsp --marketplace mbadali25/useful-claude-add-ons
```

or, from a shell:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
claude plugin install bash-lsp@useful-claude-add-ons --scope user
```

**The plugin does not install the language server.** Claude Code starts whatever
`bash-language-server` it finds on `PATH`, so install that separately. It needs
Node.js 20 or newer (the package declares `engines.node >= 20`):

```bash
npm install -g bash-language-server
```

`scripts/install-prerequisites.sh` / `.ps1` do both halves from the **LSP
plugins** menu row. Without `npm` on `PATH` they stop and say so, and they
refuse on a Node.js older than 20 instead of installing a server that cannot
start.

## What it registers

```json
"lspServers": {
  "bash": {
    "command": "bash-language-server",
    "args": ["start"],
    "extensionToLanguage": { ".sh": "shellscript", ".bash": "shellscript" }
  }
}
```

The block lives in `.claude-plugin/plugin.json`, not in a separate `.lsp.json`,
because `claude plugin validate` checks an inline block and does not read
`.lsp.json` at all: a malformed inline block fails this repository's gate, a
malformed `.lsp.json` passes it.

- `start` is the subcommand that runs the server on stdio.
- `shellscript` is the language ID the server expects for both extensions.
- `.zsh` and `.ksh` are deliberately not mapped. The server parses Bash, and
  its diagnostics come from `shellcheck`, which does not support zsh.
- A script with no extension is not covered: Claude Code picks a server by file
  extension only.

## Diagnostics come from shellcheck

The server runs [`shellcheck`](https://github.com/koalaman/shellcheck) on each
file when it is on `PATH`, and reports its findings as diagnostics. Without
`shellcheck` the server still starts and still answers hover, definition,
references and symbols; it only has no lint findings to report. The **Stack
tooling** row of the install scripts installs `shellcheck`.

## Verified, and not

Verified on Linux with `bash-language-server` 5.8.1 on Node.js 22.22.1: the
server started from the exact command above in an empty directory, answered an
LSP `initialize` request over stdio with 11 capabilities (among them
`hoverProvider`, `definitionProvider`, `referencesProvider`,
`documentSymbolProvider`, `renameProvider` and `completionProvider`), answered
`shutdown` and exited 0.

Not verified: any request beyond `initialize` and `shutdown` (no `.sh` file was
opened, so no shellcheck diagnostic was seen), a Claude Code session using the
server, anything on Windows or macOS, and any package version other than 5.8.1.
