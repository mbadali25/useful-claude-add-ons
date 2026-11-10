# angular-lsp

Angular template intelligence for Claude Code, through the Angular team's own
language server, [`@angular/language-server`](https://www.npmjs.com/package/@angular/language-server)
(`ngserver`). The plugin registers one LSP server and ships one small launcher
script. No hooks, no commands, no agents, no skills.

Anthropic's official marketplace has no Angular entry, which is why this one
exists.

## Install

```
/plugin install angular-lsp --marketplace mbadali25/useful-claude-add-ons
```

or, from a shell:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
claude plugin install angular-lsp@useful-claude-add-ons --scope user
```

**The plugin does not install the language server.** It needs Node.js and a
global install of the server:

```bash
npm install -g @angular/language-server
```

`scripts/install-prerequisites.sh` / `.ps1` do both halves from the **LSP
plugins** menu row.

Install `typescript-lsp` (from `claude-plugins-official`) alongside it. This
plugin covers templates only; see "Why only `.html`" below.

## What it registers

```json
"lspServers": {
  "angular": {
    "command": "node",
    "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/ngserver-launch.js", "--stdio"],
    "extensionToLanguage": { ".html": "html" }
  }
}
```

The block lives in `.claude-plugin/plugin.json`, not in a separate `.lsp.json`,
because `claude plugin validate` checks an inline block and does not read
`.lsp.json` at all.

### Why a launcher and not `ngserver --stdio`

`ngserver` will not start on `--stdio` alone. It needs `--tsProbeLocations` and
`--ngProbeLocations`, each naming a directory from which `typescript` and
`@angular/language-service` can be resolved, and without them it exits before
it reads a single request:

```
Error: Failed to resolve 'typescript/lib/tsserverlibrary' with minimum version '5.0' from []
```

Passing `.` for both only moves the failure: it works inside a project whose
`node_modules` already holds both packages and dies the same way everywhere
else, including a fresh clone before `npm install`.

The server package bundles its own copy of both, so the reliable probe location
is the package's own directory. That path is different on every machine
(`/usr/local/lib/node_modules/...`, `%APPDATA%\npm\node_modules\...`, an nvm
directory), so it cannot be written into a static config.
`scripts/ngserver-launch.js` finds it when the server starts:

1. `ANGULAR_LANGUAGE_SERVER_DIR`, if you set it. Use this for a non-global
   install.
2. The `ngserver` shim on `PATH`, followed back to the package directory.
3. `npm root -g`.

It then passes two probe locations, in the order the VS Code extension uses:
the project directory first, so a project's own TypeScript and language service
win when they are installed, then the server's bundled copies. `ngserver` skips
a location whose package is too old and moves to the next.

`command` is `node`, not `ngserver`, so Claude Code starts a real executable on
every platform instead of an npm `.cmd` shim on Windows. The launcher loads the
server into its own process; there is no child process to leak.

### Why only `.html`

Claude Code gives each file extension to one LSP server, and `typescript-lsp`
already owns `.ts`. Two plugins claiming the same extension is reported as a
conflict and only one of them serves it. So this plugin maps `.html` and leaves
`.ts` alone.

The cost: Angular-specific analysis of an **inline** template (a `template:`
string inside a component's `.ts` file) is not available. Those files get
TypeScript intelligence from `typescript-lsp` and nothing from this server.
Templates in their own `.html` files are covered in full, and the server reads
the surrounding TypeScript project to type-check them.

The other cost: the server is started for any `.html` file, Angular or not. In
a project with no Angular it starts, finds no Angular project, and returns
nothing useful. If that bothers you, disable the plugin in that project.

## Verified, and not

Verified on Linux with `@angular/language-server` 22.2.2 and Node 22.22.1,
from an empty directory with no `node_modules`:

- `ngserver --stdio` exits 1 with the error quoted above.
- `ngserver --stdio --tsProbeLocations . --ngProbeLocations .` exits 1 the same way.
- `node scripts/ngserver-launch.js --stdio` answers an LSP `initialize` request
  over stdio with 15 capabilities and shuts down cleanly, both with `ngserver`
  on `PATH` and with only `npm` to find it by.
- With neither findable, the launcher exits 1 and says how to install the server.

Not verified:

- **Windows and macOS.** The shim-resolution code has a Windows branch
  (`ngserver.cmd` beside `node_modules`) that has only been read, never run.
- A Claude Code session using the server on a real Angular project. That
  `${CLAUDE_PLUGIN_ROOT}` is expanded in an LSP server's `args` was confirmed
  by reading the Claude Code 2.1.296 bundle, not by watching it spawn.
- A project directory with a comma in its path. `ngserver` splits its probe
  lists on commas with no escape, so the launcher drops that location and says
  so on stderr; the bundled copies are then the only ones tried.
- Node 22.22.1 is below the `^22.22.3` the server package declares. npm warned
  and the server ran.
