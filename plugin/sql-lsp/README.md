# sql-lsp

SQL support for Claude Code through [`sqls`](https://github.com/sqls-server/sqls),
a SQL language server written in Go. The plugin registers one LSP server and
nothing else: no hooks, no commands, no agents, no skills, and **no database
connection**.

## Install

```
/plugin install sql-lsp --marketplace mbadali25/useful-claude-add-ons
```

or, from a shell:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
claude plugin install sql-lsp@useful-claude-add-ons --scope user
```

**The plugin does not install the language server.** Claude Code starts
whatever `sqls` it finds on `PATH`:

| You have | Do this |
|---|---|
| Go | `go install github.com/sqls-server/sqls@v0.2.48` (pinned; Go checks the module against its checksum database), then make sure `$(go env GOPATH)/bin` is on `PATH` |
| No Go | Download the archive for your platform from <https://github.com/sqls-server/sqls/releases>, compare its SHA-256 with the digest GitHub shows for that asset, and put `sqls` on `PATH` |

`sqls` is not in Homebrew core, Chocolatey or winget as of 2026-10-12, so
`scripts/install-prerequisites.sh` / `.ps1` install it from the **LSP plugins**
menu row only when Go is present. Without Go they stop and print the manual
route rather than download an unverified binary.

## What it registers

```json
"lspServers": {
  "sqls": {
    "command": "sqls",
    "extensionToLanguage": { ".sql": "sql" }
  }
}
```

`sqls` speaks LSP over stdio when run with no subcommand, so there are no
`args`. The block lives in `.claude-plugin/plugin.json`, not in a separate
`.lsp.json`, because `claude plugin validate` checks an inline block and does
not read `.lsp.json` at all.

## What works without a database, and what does not

Out of the box the server has no connection, and says so once
(`no database connection`). Measured that way:

| Works with no connection (measured) | Needs a connection |
|---|---|
| Keyword completion | Table, column and schema completion |
| Document formatting | Hover on a table or column (returned nothing without one) |
| | Go to definition, rename, signature help |

The right-hand column is what `sqls` builds from the database's catalogue. Only
the hover row was measured here; the rest follows from how the server works and
was not run, because no database was connected.

Be clear about what that means for Claude Code. `sqls` advertises nine
capabilities, and they do not include diagnostics, document symbols or
references. Without a connection, what Claude actually gains on a `.sql` file
is formatting and keyword completion. The schema-aware half is the reason to
install this, and it needs a connection you set up yourself.

## Connecting it to a database is your decision

This plugin ships no connection config and never will. To get schema-aware
answers, give `sqls` its own config file. It reads
`~/.config/sqls/config.yml` by default:

```yaml
# ~/.config/sqls/config.yml - placeholders only; replace every <...>
lowercaseKeywords: false
connections:
  - alias: <a-name-for-this-connection>
    driver: <mysql | postgresql | sqlite3 | mssql>
    dataSourceName: <your-driver's-connection-string>
```

Before you fill that in:

- **Which database you point it at is your call, and so is the risk.** `sqls`
  opens a live connection and reads the catalogue to learn the schema. It also
  exposes an "execute query" command, and whatever account you give it is the
  account that command runs as. Pointing it at production is a decision to make
  on purpose, not a default.
- **Use a read-only account** scoped to the schema you need, on a development
  or replica database where you have one.
- **The connection string is a credential.** Keep the file out of every
  repository, and restrict it to your own user (`chmod 600`).
- A project can also pass connection settings through LSP initialisation
  options. Do not commit those either.

## Verified, and not

Verified on Linux with sqls 0.2.48 (release binary, SHA-256 checked against the
digest GitHub publishes for the asset), with no config file and no database:

- `sqls` answers an LSP `initialize` request over stdio with 9 capabilities.
- Completion after `where` returned the keyword; formatting returned a
  reformatted statement; hover returned nothing.
- On `exit` the process panics with `close of closed channel` and exits 2,
  after it has already answered `shutdown`. The session is over by then, so
  nothing is lost, but expect the line in a debug log.

Not verified: anything with a database connected (none was configured, on
purpose), the `go install` route (this machine has no Go), Windows and macOS,
and a Claude Code session using the server.
