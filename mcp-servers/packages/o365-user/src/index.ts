import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  GraphClient,
  getUserCredential,
  assertWriteAllowed,
  textResult,
  withToolErrorHandling,
} from "@mbadali/mcp-ms-core";

/**
 * Delegated permissions requested from the signed-in user via device code.
 * This is the entire boundary that keeps this server user-scoped: every
 * Graph call below runs as "me", using only what the signed-in user
 * consented to -- it can never reach another mailbox or tenant-wide data.
 */
export const USER_SCOPES = [
  "https://graph.microsoft.com/User.Read",
  "https://graph.microsoft.com/Mail.ReadWrite",
  "https://graph.microsoft.com/Mail.Send",
  "https://graph.microsoft.com/Calendars.ReadWrite",
  "https://graph.microsoft.com/Files.Read",
];

let _client: GraphClient | undefined;
export function getClient(): GraphClient {
  if (!_client) _client = new GraphClient(getUserCredential(), undefined, USER_SCOPES);
  return _client;
}

export interface CreatedServer {
  server: McpServer;
  tools: Record<string, ReturnType<McpServer["registerTool"]>>;
}

export function createServer(client: GraphClient = getClient()): CreatedServer {
  const server = new McpServer({ name: "mcp-o365-user", version: "0.1.0" });
  const tools: CreatedServer["tools"] = {};
  const reg: McpServer["registerTool"] = (name, config, handler) => {
    const t = server.registerTool(name, config as never, handler as never);
    tools[name] = t;
    return t;
  };

  reg(
    "get_my_profile",
    { description: "Get the signed-in user's own profile (read-only).", inputSchema: {} },
    withToolErrorHandling(async () => textResult(await client.get("/me")))
  );

  reg(
    "list_my_mail",
    {
      description: "List messages in the signed-in user's own mailbox (read-only, defaults to Inbox).",
      inputSchema: {
        folder: z.string().optional().describe("Well-known folder name, default 'inbox'"),
        top: z.number().int().min(1).max(200).optional(),
      },
    },
    withToolErrorHandling(async ({ folder, top }) => {
      const messages = await client.getAllPages(`/me/mailFolders/${folder ?? "inbox"}/messages`, {
        query: { $top: top ?? 25, $select: "id,subject,from,receivedDateTime,isRead" },
        maxPages: 2,
      });
      return textResult(messages);
    })
  );

  reg(
    "search_my_mail",
    {
      description: "Search the signed-in user's own mail (read-only).",
      inputSchema: { query: z.string() },
    },
    withToolErrorHandling(async ({ query }) => {
      const escaped = query.replace(/"/g, '\\"');
      const messages = await client.get("/me/messages", {
        query: { $search: `"${escaped}"`, $top: 25 },
      });
      return textResult(messages);
    })
  );

  reg(
    "list_my_calendar_events",
    {
      description: "List upcoming events on the signed-in user's own calendar (read-only).",
      inputSchema: { top: z.number().int().min(1).max(200).optional() },
    },
    withToolErrorHandling(async ({ top }) => {
      const events = await client.getAllPages("/me/events", {
        query: { $top: top ?? 25, $orderby: "start/dateTime" },
        maxPages: 2,
      });
      return textResult(events);
    })
  );

  reg(
    "list_my_files",
    {
      description: "List files at the root of the signed-in user's own OneDrive (read-only).",
      inputSchema: {},
    },
    withToolErrorHandling(async () => {
      const files = await client.getAllPages("/me/drive/root/children", { maxPages: 2 });
      return textResult(files);
    })
  );

  reg(
    "send_mail",
    {
      description:
        "Send an email as the signed-in user. WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: {
        to: z.array(z.string()).min(1).describe("Recipient email addresses"),
        subject: z.string(),
        body: z.string().describe("Plain-text or HTML body"),
        isHtml: z.boolean().optional().default(false),
        confirm: z.boolean().optional(),
      },
    },
    withToolErrorHandling(async ({ to, subject, body, isHtml, confirm }) => {
      assertWriteAllowed("send_mail", { confirm });
      await client.post("/me/sendMail", {
        body: {
          message: {
            subject,
            body: { contentType: isHtml ? "HTML" : "Text", content: body },
            toRecipients: to.map((address) => ({ emailAddress: { address } })),
          },
        },
      });
      return textResult({ sent: true, to, subject });
    })
  );

  reg(
    "create_calendar_event",
    {
      description:
        "Create a calendar event (sends invites to attendees). WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: {
        subject: z.string(),
        startDateTime: z.string().describe("ISO 8601, e.g. 2026-01-15T10:00:00"),
        endDateTime: z.string().describe("ISO 8601, e.g. 2026-01-15T10:30:00"),
        timeZone: z.string().optional().default("UTC"),
        attendees: z.array(z.string()).optional().describe("Attendee email addresses"),
        confirm: z.boolean().optional(),
      },
    },
    withToolErrorHandling(async ({ subject, startDateTime, endDateTime, timeZone, attendees, confirm }) => {
      assertWriteAllowed("create_calendar_event", { confirm });
      const event = await client.post("/me/events", {
        body: {
          subject,
          start: { dateTime: startDateTime, timeZone },
          end: { dateTime: endDateTime, timeZone },
          attendees: (attendees ?? []).map((address) => ({ emailAddress: { address }, type: "required" })),
        },
      });
      return textResult(event);
    })
  );

  reg(
    "delete_mail_message",
    {
      description: "Delete one message from the signed-in user's own mailbox. WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: { messageId: z.string(), confirm: z.boolean().optional() },
    },
    withToolErrorHandling(async ({ messageId, confirm }) => {
      assertWriteAllowed("delete_mail_message", { confirm });
      await client.delete(`/me/messages/${encodeURIComponent(messageId)}`);
      return textResult({ deleted: messageId });
    })
  );

  return { server, tools };
}
