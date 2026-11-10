<!-- Moved verbatim from plugin/crew/README.md (13. Optional: Jira via MCP) by L-0726; the README keeps an index entry. -->

## 13. Optional: Jira via MCP

Only in repositories where Jira is actually the source of truth. `crew-setup` writes a project-scoped `.mcp.json`:

```json
{
  "mcpServers": {
    "atlassian": { "type": "http", "url": "https://mcp.atlassian.com/v1/mcp" }
  }
}
```

The older `/v1/sse` endpoint was retired in mid-2026. If you copy a configuration from a guide written before then, it will fail with an unhelpful connection error. If OAuth keeps dropping mid-session — a common complaint — switch to API token authentication.

Run `/mcp`, approve the server, authenticate. The cloud ID is then fetched once and cached in `.crew/config.json`, never looked up again.

**The cache is the actual strategy.** Tool *definitions* are less of a problem than they used to be; Claude Code defers MCP tool definitions automatically once they exceed roughly ten percent of the context window, which can turn tens of thousands of tokens into a few hundred. What deferral does not help with is *response* payloads, and a Jira issue is a fat one — rendered description, changelog, watchers, sprint metadata, custom fields.

So `/crew:jira-sync` keeps six fields and discards the rest, writing a compact local file that `/crew:implement` reads instead of calling the API. That is the difference between paying for a ticket once and paying for it on every pickup, retry, and context reset. Sync happens at two boundaries only: pickup and completion. Three Jira calls in one ticket means the cache is wrong.

One limitation to know rather than discover: plugin-shipped agents cannot declare `mcpServers` in frontmatter, for security reasons. Jira access therefore lives at session level. If you want it isolated in its own context window, that agent has to live in `~/.claude/agents/` outside the plugin.
