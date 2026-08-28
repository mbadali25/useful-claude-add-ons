import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  GraphClient,
  getAdminCredential,
  assertWriteAllowed,
  textResult,
  withToolErrorHandling,
} from "@mbadali/mcp-ms-core";

let _client: GraphClient | undefined;
/** Lazily built so importing this module (e.g. for tests) never requires env vars. */
export function getClient(): GraphClient {
  if (!_client) _client = new GraphClient(getAdminCredential());
  return _client;
}

export interface CreatedServer {
  server: McpServer;
  /** Exposed for offline unit tests -- calls handlers directly, bypassing stdio transport. */
  tools: Record<string, ReturnType<McpServer["registerTool"]>>;
}

export function createServer(client: GraphClient = getClient()): CreatedServer {
  const server = new McpServer({ name: "mcp-msgraph", version: "0.1.0" });
  const tools: CreatedServer["tools"] = {};
  const reg: McpServer["registerTool"] = (name, config, handler) => {
    const t = server.registerTool(name, config as never, handler as never);
    tools[name] = t;
    return t;
  };

  reg(
    "list_users",
    {
      description: "List directory users (read-only). Requires User.Read.All or Directory.Read.All app permission.",
      inputSchema: {
        top: z.number().int().min(1).max(999).optional().describe("Page size, default 25"),
        filter: z.string().optional().describe("OData $filter, e.g. startswith(displayName,'Jane')"),
        select: z.string().optional().describe("Comma-separated fields, default id,displayName,mail,userPrincipalName"),
      },
    },
    withToolErrorHandling(async ({ top, filter, select }) => {
      const users = await client.getAllPages("/users", {
        query: {
          $top: top ?? 25,
          $filter: filter,
          $select: select ?? "id,displayName,mail,userPrincipalName,accountEnabled",
        },
        maxPages: 4,
      });
      return textResult(users);
    })
  );

  reg(
    "get_user",
    {
      description: "Get one directory user by id or userPrincipalName (read-only).",
      inputSchema: { userId: z.string().describe("Object id or userPrincipalName") },
    },
    withToolErrorHandling(async ({ userId }) => {
      const user = await client.get(`/users/${encodeURIComponent(userId)}`);
      return textResult(user);
    })
  );

  reg(
    "list_groups",
    {
      description: "List directory groups (read-only). Requires Group.Read.All or Directory.Read.All.",
      inputSchema: {
        top: z.number().int().min(1).max(999).optional(),
        filter: z.string().optional().describe("OData $filter, e.g. startswith(displayName,'Eng')"),
      },
    },
    withToolErrorHandling(async ({ top, filter }) => {
      const groups = await client.getAllPages("/groups", {
        query: { $top: top ?? 25, $filter: filter, $select: "id,displayName,mail,description" },
        maxPages: 4,
      });
      return textResult(groups);
    })
  );

  reg(
    "get_group_members",
    {
      description: "List the members of one group (read-only).",
      inputSchema: { groupId: z.string() },
    },
    withToolErrorHandling(async ({ groupId }) => {
      const members = await client.getAllPages(`/groups/${encodeURIComponent(groupId)}/members`, { maxPages: 4 });
      return textResult(members);
    })
  );

  reg(
    "search_directory",
    {
      description: "Search users by display name or mail prefix (read-only).",
      inputSchema: { query: z.string().describe("Prefix to match against displayName or mail") },
    },
    withToolErrorHandling(async ({ query }) => {
      const escaped = query.replace(/'/g, "''");
      const users = await client.getAllPages("/users", {
        query: {
          $filter: `startswith(displayName,'${escaped}') or startswith(mail,'${escaped}')`,
          $select: "id,displayName,mail,userPrincipalName",
          $top: 25,
        },
        maxPages: 2,
      });
      return textResult(users);
    })
  );

  reg(
    "update_user_profile",
    {
      description:
        "Update basic profile fields (displayName, jobTitle, department, officeLocation) on a user. " +
        "WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: {
        userId: z.string(),
        displayName: z.string().optional(),
        jobTitle: z.string().optional(),
        department: z.string().optional(),
        officeLocation: z.string().optional(),
        confirm: z.boolean().optional().describe("Must be true to execute"),
      },
    },
    withToolErrorHandling(async ({ userId, confirm, ...fields }) => {
      assertWriteAllowed("update_user_profile", { confirm });
      const body = Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined));
      if (Object.keys(body).length === 0) throw new Error("No fields supplied to update.");
      await client.patch(`/users/${encodeURIComponent(userId)}`, { body });
      return textResult({ updated: userId, fields: body });
    })
  );

  reg(
    "disable_user_account",
    {
      description:
        "Disable (accountEnabled:false) a user's sign-in. WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: { userId: z.string(), confirm: z.boolean().optional() },
    },
    withToolErrorHandling(async ({ userId, confirm }) => {
      assertWriteAllowed("disable_user_account", { confirm });
      await client.patch(`/users/${encodeURIComponent(userId)}`, { body: { accountEnabled: false } });
      return textResult({ disabled: userId });
    })
  );

  reg(
    "add_group_member",
    {
      description: "Add a user to a group. WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: { groupId: z.string(), userId: z.string(), confirm: z.boolean().optional() },
    },
    withToolErrorHandling(async ({ groupId, userId, confirm }) => {
      assertWriteAllowed("add_group_member", { confirm });
      await client.post(`/groups/${encodeURIComponent(groupId)}/members/$ref`, {
        body: { "@odata.id": `https://graph.microsoft.com/v1.0/directoryObjects/${userId}` },
      });
      return textResult({ group: groupId, added: userId });
    })
  );

  reg(
    "remove_group_member",
    {
      description: "Remove a user from a group. WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: { groupId: z.string(), userId: z.string(), confirm: z.boolean().optional() },
    },
    withToolErrorHandling(async ({ groupId, userId, confirm }) => {
      assertWriteAllowed("remove_group_member", { confirm });
      await client.delete(`/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(userId)}/$ref`);
      return textResult({ group: groupId, removed: userId });
    })
  );

  return { server, tools };
}
