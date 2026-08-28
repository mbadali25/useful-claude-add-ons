import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  GraphClient,
  buildAdminCredential,
  assertWriteAllowed,
  textResult,
  pagedResult,
  withToolErrorHandling,
} from "@badali404/mcp-ms-core";

/**
 * Delegated Graph permissions this server needs -- only used by the admin
 * credential chain's device-code fallback (the secret and Azure CLI links
 * always request the resource .default scope instead; see
 * @badali404/mcp-ms-core's adminAuth.ts for why). Widens to include the write
 * scopes only when MCP_MS_ALLOW_WRITES=1, read at server startup.
 */
export function delegatedScopes(): string[] {
  const scopes = ["https://graph.microsoft.com/User.Read.All", "https://graph.microsoft.com/MailboxSettings.Read"];
  if (process.env.MCP_MS_ALLOW_WRITES === "1") {
    scopes.push("https://graph.microsoft.com/User.ReadWrite.All");
  }
  return scopes;
}

let _client: GraphClient | undefined;
export function getClient(): GraphClient {
  if (!_client) _client = new GraphClient(buildAdminCredential(delegatedScopes()), undefined, delegatedScopes());
  return _client;
}

export interface CreatedServer {
  server: McpServer;
  tools: Record<string, ReturnType<McpServer["registerTool"]>>;
}

export function createServer(client: GraphClient = getClient()): CreatedServer {
  const server = new McpServer({ name: "mcp-o365-admin", version: "0.1.0" });
  const tools: CreatedServer["tools"] = {};
  const reg: McpServer["registerTool"] = (name, config, handler) => {
    const t = server.registerTool(name, config as never, handler as never);
    tools[name] = t;
    return t;
  };

  reg(
    "list_mailboxes",
    {
      description: "List tenant users that have a mailbox (read-only). Requires User.Read.All.",
      inputSchema: { top: z.number().int().min(1).max(999).optional() },
    },
    withToolErrorHandling(async ({ top }) => {
      const page = await client.getAllPages("/users", {
        query: { $top: top ?? 25, $select: "id,displayName,mail,userPrincipalName,accountEnabled" },
        maxPages: 4,
      });
      return pagedResult(page);
    })
  );

  reg(
    "get_mailbox_settings",
    {
      description: "Get one user's mailbox settings (timezone, automatic replies, etc.) (read-only).",
      inputSchema: { userId: z.string() },
    },
    withToolErrorHandling(async ({ userId }) => {
      const settings = await client.get(`/users/${encodeURIComponent(userId)}/mailboxSettings`);
      return textResult(settings);
    })
  );

  reg(
    "list_licenses",
    {
      description: "List SKUs available in the tenant and their assigned/consumed counts (read-only).",
      inputSchema: {},
    },
    withToolErrorHandling(async () => {
      const page = await client.getAllPages("/subscribedSkus", { maxPages: 2 });
      return pagedResult(page);
    })
  );

  reg(
    "get_user_licenses",
    {
      description: "List the licenses assigned to one user (read-only).",
      inputSchema: { userId: z.string() },
    },
    withToolErrorHandling(async ({ userId }) => {
      const licenses = await client.get(`/users/${encodeURIComponent(userId)}/licenseDetails`);
      return textResult(licenses);
    })
  );

  reg(
    "reset_user_password",
    {
      description:
        "Force-reset a user's password and require change at next sign-in. WRITE tool: requires " +
        "MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: {
        userId: z.string(),
        newPassword: z.string().min(8),
        confirm: z.boolean().optional(),
      },
    },
    withToolErrorHandling(async ({ userId, newPassword, confirm }) => {
      assertWriteAllowed("reset_user_password", { confirm });
      await client.patch(`/users/${encodeURIComponent(userId)}`, {
        body: {
          passwordProfile: {
            forceChangePasswordNextSignIn: true,
            password: newPassword,
          },
        },
      });
      return textResult({ userId, passwordReset: true });
    })
  );

  reg(
    "assign_license",
    {
      description: "Assign a license SKU to a user. WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: { userId: z.string(), skuId: z.string(), confirm: z.boolean().optional() },
    },
    withToolErrorHandling(async ({ userId, skuId, confirm }) => {
      assertWriteAllowed("assign_license", { confirm });
      await client.post(`/users/${encodeURIComponent(userId)}/assignLicense`, {
        body: { addLicenses: [{ skuId }], removeLicenses: [] },
      });
      return textResult({ userId, assigned: skuId });
    })
  );

  reg(
    "delete_user",
    {
      description:
        "Delete a user from the tenant (recoverable for 30 days via the AAD recycle bin). DESTRUCTIVE WRITE tool: " +
        "requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: { userId: z.string(), confirm: z.boolean().optional() },
    },
    withToolErrorHandling(async ({ userId, confirm }) => {
      assertWriteAllowed("delete_user", { confirm });
      await client.delete(`/users/${encodeURIComponent(userId)}`);
      return textResult({ deleted: userId });
    })
  );

  return { server, tools };
}
