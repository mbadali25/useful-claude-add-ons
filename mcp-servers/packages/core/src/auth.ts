import { DeviceCodeCredential, ClientSecretCredential, type TokenCredential } from "@azure/identity";

/**
 * Every stdio MCP server's stdout is the JSON-RPC channel. Never console.log
 * from this package or any server built on it -- diagnostics go to stderr.
 */
export function logToStderr(message: string): void {
  process.stderr.write(`${message}\n`);
}

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value || value.trim() === "") {
    throw new ConfigError(
      `Missing required environment variable ${name}. See mcp-servers/README.md for the full list.`
    );
  }
  return value;
}

/**
 * Delegated, user-scoped credential (device code flow). Used by o365-user.
 * The signed-in user's own consented permissions apply -- this credential
 * can never reach tenant-wide data.
 *
 * Env vars:
 *   MS_USER_CLIENT_ID   required -- app registration (public client, device code enabled)
 *   MS_USER_TENANT_ID   optional -- defaults to "organizations"
 */
export function getUserCredential(): TokenCredential {
  const clientId = requireEnv("MS_USER_CLIENT_ID");
  const tenantId = process.env.MS_USER_TENANT_ID?.trim() || "organizations";

  return new DeviceCodeCredential({
    clientId,
    tenantId,
    userPromptCallback: (info) => {
      logToStderr(`\n${info.message}\n`);
    },
  });
}

/**
 * App-only, tenant-wide credential (client credentials flow). Used by
 * intune, msgraph, and o365-admin. Requires application (not delegated)
 * Graph permissions granted admin consent in the tenant.
 *
 * Env vars:
 *   MS_ADMIN_TENANT_ID      required
 *   MS_ADMIN_CLIENT_ID      required
 *   MS_ADMIN_CLIENT_SECRET  required
 */
export function getAdminCredential(): TokenCredential {
  const tenantId = requireEnv("MS_ADMIN_TENANT_ID");
  const clientId = requireEnv("MS_ADMIN_CLIENT_ID");
  const clientSecret = requireEnv("MS_ADMIN_CLIENT_SECRET");

  return new ClientSecretCredential(tenantId, clientId, clientSecret);
}
