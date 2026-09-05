# MCP server updates

New MCP servers and capability added under `mcp-servers/`, newest first. For
fixes and internal changes, see [`CHANGELOG.md`](../CHANGELOG.md); this file is
only what is newly *possible*.

Mirrored into [`mcp-servers/README.md`](README.md) and the root
[`README.md`](../README.md) by `scripts/sync-updates.py`. Edit here, then run it.

## Unreleased

No new MCP servers this round.

One operational note that costs an afternoon if you hit it cold: when several
Obsidian vaults each run the Local REST API plugin, **every vault needs its own
HTTPS port as well as its own HTTP port**. Two vaults declaring the same HTTPS
port is not a partial failure — the second one to load fails to bind, and its
plugin then serves neither protocol, so the HTTP port you actually configured
goes silent too. The symptom looks like an auth or TLS problem and is not:
the surviving vault answers on the shared port with *its* API key and *its*
files. Compare `port` and `insecurePort` across every vault's
`.obsidian/plugins/obsidian-local-rest-api/data.json` before touching anything
else, and probe with `curl -k` on the HTTPS port, which works even where a
Node client rejects the self-signed certificate.
