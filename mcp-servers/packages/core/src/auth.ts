import { DeviceCodeCredential, type TokenCredential } from "@azure/identity";

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
 * Shared by getUserCredential() below (o365-user, always device code) and
 * adminAuth.ts's device-code chain link (the admin servers' last-resort
 * fallback) -- one place prints the sign-in prompt to stderr, never stdout,
 * since stdout is the MCP protocol channel and a stray line corrupts framing.
 */
export function buildDeviceCodeCredential(clientId: string, tenantId: string): TokenCredential {
  return new DeviceCodeCredential({
    clientId,
    tenantId,
    userPromptCallback: (info) => {
      logToStderr(`\n${info.message}\n`);
    },
  });
}

/**
 * Delegated, user-scoped credential (device code flow only -- no chain). Used
 * by o365-user. The signed-in user's own consented permissions apply -- this
 * credential can never reach tenant-wide data, and unlike the admin servers'
 * chain (adminAuth.ts) it never falls back to Azure CLI, which would widen
 * its scope to whatever the CLI's own app is consented for instead of this
 * server's deliberately narrow, /me-only USER_SCOPES.
 *
 * Env vars:
 *   MS_USER_CLIENT_ID   required -- app registration (public client, device code enabled)
 *   MS_USER_TENANT_ID   optional -- defaults to "organizations"
 */
export function getUserCredential(): TokenCredential {
  const clientId = requireEnv("MS_USER_CLIENT_ID");
  const tenantId = process.env.MS_USER_TENANT_ID?.trim() || "organizations";
  return buildDeviceCodeCredential(clientId, tenantId);
}
