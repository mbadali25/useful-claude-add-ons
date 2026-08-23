---
name: crew-cloud
description: Configure the official AWS and Azure MCP servers safely for a repo. Use when the user says set up AWS MCP, add the Azure MCP server, connect to my cloud account, look up AWS docs or pricing, or asks how to give the crew read access to cloud resources.
---

# Cloud MCP servers

Both clouds ship official MCP servers. Both authenticate as **you**, with your
existing credentials — which is the part that deserves care before the part
about which package to install.

---

## Read the risk first

An MCP server that reaches your account does so with whatever your credential
chain grants. If your default AWS profile is an admin role, so is the agent's.
There is no "read-only mode" flag that saves you; the constraint has to come from
the credential.

Three rules, and `crew-setup` should enforce them by asking:

1. **A dedicated profile, scoped read-only**, pointed at a non-production account
   wherever possible. Not your daily driver profile.
2. **Never `AWS_PROFILE=production`** or a subscription with write scope, in any
   repo where an agent runs unattended.
3. **Start with the documentation and pricing servers**, which touch no account
   at all, and only add account-reaching servers when a task actually needs one.

`guard.sh` already blocks `aws`/`az` commands mentioning prod, but a guard on the
shell does not cover an MCP tool call. The credential is the real boundary.

---

## AWS

AWS publishes a suite under `awslabs/mcp`, installed per-server with `uvx`.
Requires `uv` from Astral.

**No-account servers — start here:**

```bash
claude mcp add aws-docs uvx awslabs.aws-documentation-mcp-server@latest
claude mcp add aws-pricing uvx awslabs.aws-pricing-mcp-server@latest
```

Documentation and pricing lookups, no credentials involved. Genuinely useful for
the `analyst` and `planner` roles, and risk-free.

**Account-reaching servers — deliberate choice:**

```bash
claude mcp add aws-api uvx awslabs.aws-api-mcp-server@latest
claude mcp add aws-iac uvx awslabs.aws-iac-mcp-server@latest
```

These use the standard AWS credential chain — environment variables or
`~/.aws/credentials` — so scope the profile before you add them, not after.

There is also a single consolidated **AWS MCP Server** (generally available,
combining documentation, authenticated API access, and sandboxed script
execution) and managed remote servers such as AWS Knowledge MCP that need no
local infrastructure. Check the current AWS MCP Server User Guide for the
install line rather than trusting a snippet from here — this area has moved
repeatedly, including a rename of the package.

AWS has also introduced an **Agent Toolkit for AWS** positioned as the successor
to the Labs MCP servers, with IAM condition keys that distinguish agent actions
from human ones plus CloudTrail visibility. If you are wiring agents into a real
AWS account rather than experimenting, that attribution capability is worth more
than any convenience the older servers offer — check whether it fits before
committing to the Labs suite.

---

## Azure

One server covers 40+ services:

```bash
claude mcp add azure-mcp -- npx -y @azure/mcp@latest server start
```

Or install globally for faster startup: `npm install -g @azure/mcp@latest`.
Needs Node.js 20 LTS or later on `PATH`.

**Authenticate to Azure before starting the server** — it uses your Azure
identity via Entra ID, so `az login` (or an equivalent credential) must already
be in place. Starting it unauthenticated produces confusing tool failures rather
than a clear error.

Note the config-key difference if you write it by hand: Claude Code and most
clients use `mcpServers`, while Visual Studio and VS Code use `servers`. Copying
a snippet across clients is a common silent failure.

For Azure DevOps work items, that is a separate server from the Azure one.

---

## Scope it per repo, not globally

Put these in the repo's `.mcp.json`, in the repos that actually deploy to that
cloud. A terraform repo needs the IaC server; the AngularJS front end does not.

Claude Code defers MCP tool definitions once they grow past roughly ten percent
of the context window, so the standing token cost is smaller than it used to be.
The reason to scope anyway is blast radius and prompt clarity: fewer tools
available means fewer wrong tools chosen, and tool-selection accuracy degrades
noticeably once a session has dozens of options.

---

## Verifying

After adding, run `/mcp` and confirm the server connected and authenticated. Then
make one real read call — list a bucket, list a resource group — before relying
on it. A server that is present but unauthenticated fails at the moment you need
it, usually mid-task.

Record which servers this repo uses in its `CLAUDE.md`, one line, so the next
person knows why `.mcp.json` looks like that.
