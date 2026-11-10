# css-lsp

CSS, SCSS and Less code intelligence for Claude Code, through
`vscode-css-language-server`, the CSS server from Visual Studio Code as
repackaged in the npm package
[`vscode-langservers-extracted`](https://www.npmjs.com/package/vscode-langservers-extracted).
The plugin registers one LSP server and nothing else: no hooks, no commands, no
agents, no skills.

## Install

```
/plugin install css-lsp --marketplace mbadali25/useful-claude-add-ons
```

or, from a shell:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
claude plugin install css-lsp@useful-claude-add-ons --scope user
```

**The plugin does not install the language server.** Claude Code starts whatever
`vscode-css-language-server` it finds on `PATH`, so install that separately. It
needs Node.js:

```bash
npm install -g vscode-langservers-extracted
```

`scripts/install-prerequisites.sh` / `.ps1` do both halves from the **LSP
plugins** menu row. Without `npm` on `PATH` they stop and say so.

The npm package is a community repackaging, not a Microsoft release, and it
also puts `vscode-html-language-server`, `vscode-json-language-server`,
`vscode-markdown-language-server` and `vscode-eslint-language-server` on `PATH`.
This plugin starts the CSS one only.

## What it registers

```json
"lspServers": {
  "css": {
    "command": "vscode-css-language-server",
    "args": ["--stdio"],
    "extensionToLanguage": { ".css": "css", ".scss": "scss", ".less": "less" }
  }
}
```

The block lives in `.claude-plugin/plugin.json`, not in a separate `.lsp.json`,
because `claude plugin validate` checks an inline block and does not read
`.lsp.json` at all: a malformed inline block fails this repository's gate, a
malformed `.lsp.json` passes it.

- `--stdio` is required. Run bare, the server throws
  `Connection input stream is not set` and never reads a request.
- `css`, `scss` and `less` are the three language IDs the server handles, one
  per extension.
- `.sass` (the indented syntax) is deliberately not mapped. The server parses
  SCSS, not indented Sass.

## What to expect

The server answers from the files alone and needs no project setup. A `.scss`
file is analysed, not compiled: the server does not run `sass`, and it does not
know whether a compiled `.css` beside it is stale.

## Verified, and not

Verified on Linux with `vscode-langservers-extracted` 4.10.0 on Node.js 22: the
server started from the exact command above in an empty directory, answered an
LSP `initialize` request over stdio with 15 capabilities (among them
`diagnosticProvider`, `hoverProvider`, `definitionProvider`,
`referencesProvider`, `documentSymbolProvider` and
`documentFormattingProvider`), answered `shutdown` and exited 0.

Not verified: any request beyond `initialize` and `shutdown` (no `.css`, `.scss`
or `.less` file was opened), a Claude Code session using the server, anything on
Windows or macOS, and any package version other than 4.10.0.
