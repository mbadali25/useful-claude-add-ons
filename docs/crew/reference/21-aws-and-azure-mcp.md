<!-- Moved verbatim from plugin/crew/README.md (21. AWS and Azure MCP) by L-0726; the README keeps an index entry. -->

## 21. AWS and Azure MCP

Official servers for both, configured per repo — the terraform repo needs the
IaC server; the AngularJS front end does not.

**The credential is the boundary, not a flag.** These servers authenticate as
you, with whatever your credential chain grants. If your default profile is
admin, so is the agent. There is no read-only mode that substitutes for scoping
the profile, and the cloud guard judging `aws` shell commands does not cover an
MCP tool call.

So: a dedicated read-only profile against a non-production account, never
`AWS_PROFILE=production` in a repo where an agent runs unattended, and start with
the servers that touch no account at all.

**AWS** — installed per-server with `uvx` from the `awslabs/mcp` suite:

```bash
claude mcp add aws-docs uvx awslabs.aws-documentation-mcp-server@latest
claude mcp add aws-pricing uvx awslabs.aws-pricing-mcp-server@latest
# account-reaching, add deliberately:
claude mcp add aws-api uvx awslabs.aws-api-mcp-server@latest
```

Docs and pricing need no credentials and are genuinely useful to `researcher`
and to planning. There is also a consolidated AWS MCP Server now generally available,
and an Agent Toolkit for AWS positioned as the successor to the Labs servers,
with IAM condition keys distinguishing agent actions from human ones. If you are
wiring agents into a real account, that attribution is worth more than any
convenience the older suite offers — check the current guide before committing,
since this area has moved repeatedly.

**Azure** — one server, 40+ services:

```bash
claude mcp add azure-mcp -- npx -y @azure/mcp@latest server start
```

Needs Node 20 LTS or later, and you must authenticate to Azure *before* starting
it — an unauthenticated server produces confusing tool failures rather than a
clear error. Note that Claude Code uses the `mcpServers` config key while Visual
Studio and VS Code use `servers`; copying a snippet between them fails silently.
