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
 * scopes only when MCP_MS_ALLOW_WRITES=1, read at server startup. Intune
 * management scopes are frequently NOT consented for the Azure CLI's own app
 * registration in a tenant -- if the "cli" link resolves but tools 403, set
 * MS_ADMIN_CLIENT_ID to a real public-client app registration with these
 * delegated permissions consented, so the device-code link can get them.
 */
export function delegatedScopes(): string[] {
  const scopes = [
    "https://graph.microsoft.com/DeviceManagementManagedDevices.Read.All",
    "https://graph.microsoft.com/DeviceManagementConfiguration.Read.All",
  ];
  if (process.env.MCP_MS_ALLOW_WRITES === "1") {
    scopes.push(
      "https://graph.microsoft.com/DeviceManagementManagedDevices.PrivilegedOperations.All",
      "https://graph.microsoft.com/DeviceManagementConfiguration.ReadWrite.All"
    );
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
  const server = new McpServer({ name: "mcp-intune", version: "0.1.0" });
  const tools: CreatedServer["tools"] = {};
  const reg: McpServer["registerTool"] = (name, config, handler) => {
    const t = server.registerTool(name, config as never, handler as never);
    tools[name] = t;
    return t;
  };

  reg(
    "list_managed_devices",
    {
      description:
        "List Intune-managed devices (read-only). Requires DeviceManagementManagedDevices.Read.All.",
      inputSchema: {
        top: z.number().int().min(1).max(999).optional(),
        filter: z.string().optional().describe("OData $filter, e.g. complianceState eq 'noncompliant'"),
      },
    },
    withToolErrorHandling(async ({ top, filter }) => {
      const page = await client.getAllPages("/deviceManagement/managedDevices", {
        query: { $top: top ?? 25, $filter: filter },
        maxPages: 4,
      });
      return pagedResult(page);
    })
  );

  reg(
    "get_managed_device",
    {
      description: "Get one Intune-managed device by id, including compliance/enrollment details (read-only).",
      inputSchema: { deviceId: z.string() },
    },
    withToolErrorHandling(async ({ deviceId }) => {
      const device = await client.get(`/deviceManagement/managedDevices/${encodeURIComponent(deviceId)}`);
      return textResult(device);
    })
  );

  reg(
    "list_compliance_policies",
    {
      description: "List device compliance policies (read-only). Requires DeviceManagementConfiguration.Read.All.",
      inputSchema: {},
    },
    withToolErrorHandling(async () => {
      const page = await client.getAllPages("/deviceManagement/deviceCompliancePolicies", { maxPages: 4 });
      return pagedResult(page);
    })
  );

  reg(
    "list_configuration_profiles",
    {
      description: "List device configuration profiles (read-only). Requires DeviceManagementConfiguration.Read.All.",
      inputSchema: {},
    },
    withToolErrorHandling(async () => {
      const page = await client.getAllPages("/deviceManagement/deviceConfigurations", { maxPages: 4 });
      return pagedResult(page);
    })
  );

  reg(
    "sync_device",
    {
      description:
        "Trigger an immediate Intune check-in/sync on a device. WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: { deviceId: z.string(), confirm: z.boolean().optional() },
    },
    withToolErrorHandling(async ({ deviceId, confirm }) => {
      assertWriteAllowed("sync_device", { confirm });
      await client.post(`/deviceManagement/managedDevices/${encodeURIComponent(deviceId)}/syncDevice`);
      return textResult({ synced: deviceId });
    })
  );

  reg(
    "retire_device",
    {
      description:
        "Retire a device: removes company data and management, leaves personal data. DESTRUCTIVE WRITE tool: " +
        "requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: { deviceId: z.string(), confirm: z.boolean().optional() },
    },
    withToolErrorHandling(async ({ deviceId, confirm }) => {
      assertWriteAllowed("retire_device", { confirm });
      await client.post(`/deviceManagement/managedDevices/${encodeURIComponent(deviceId)}/retire`);
      return textResult({ retired: deviceId });
    })
  );

  reg(
    "wipe_device",
    {
      description:
        "Factory-reset a device (full wipe). DESTRUCTIVE WRITE tool: requires MCP_MS_ALLOW_WRITES=1 and confirm:true.",
      inputSchema: {
        deviceId: z.string(),
        keepEnrollmentData: z.boolean().optional().default(false),
        keepUserData: z.boolean().optional().default(false),
        confirm: z.boolean().optional(),
      },
    },
    withToolErrorHandling(async ({ deviceId, keepEnrollmentData, keepUserData, confirm }) => {
      assertWriteAllowed("wipe_device", { confirm });
      await client.post(`/deviceManagement/managedDevices/${encodeURIComponent(deviceId)}/wipe`, {
        body: { keepEnrollmentData, keepUserData },
      });
      return textResult({ wiped: deviceId });
    })
  );

  reg(
    "update_compliance_policy",
    {
      description:
        "Apply a partial update (JSON merge patch) to a device compliance policy. POLICY CHANGE -- WRITE tool: " +
        "requires MCP_MS_ALLOW_WRITES=1 and confirm:true. Pass only the fields you want changed.",
      inputSchema: {
        policyId: z.string(),
        patch: z.record(z.string(), z.unknown()).describe("Fields to PATCH onto the policy object"),
        confirm: z.boolean().optional(),
      },
    },
    withToolErrorHandling(async ({ policyId, patch, confirm }) => {
      assertWriteAllowed("update_compliance_policy", { confirm });
      await client.patch(`/deviceManagement/deviceCompliancePolicies/${encodeURIComponent(policyId)}`, {
        body: patch,
      });
      return textResult({ updated: policyId, patch });
    })
  );

  return { server, tools };
}
