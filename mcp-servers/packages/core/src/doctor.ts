import type { TokenCredential } from "@azure/identity";
import { GRAPH_DEFAULT_SCOPE } from "./graphClient.js";
import { decodeJwtPayload } from "./jwt.js";
import { logToStderr } from "./auth.js";

export interface DoctorResult {
  ok: boolean;
  mode: "delegated" | "app-only";
  tenantId?: string;
  identity?: string;
  scopesOrRoles: string[];
  expiresOn?: string;
  writesAllowed: boolean;
  error?: string;
}

/**
 * Every server's `doctor` subcommand calls this: acquires a real token,
 * decodes its claims, and reports what was actually granted -- a process
 * that starts cleanly proves nothing about whether auth works.
 */
export async function runDoctor(
  credential: TokenCredential,
  mode: "delegated" | "app-only",
  scopes: string[] = [GRAPH_DEFAULT_SCOPE]
): Promise<DoctorResult> {
  const writesAllowed = process.env.MCP_MS_ALLOW_WRITES === "1";
  try {
    const token = await credential.getToken(scopes);
    if (!token) {
      return { ok: false, mode, scopesOrRoles: [], writesAllowed, error: "getToken returned null" };
    }
    const claims = decodeJwtPayload(token.token);
    const scopesOrRoles =
      mode === "app-only"
        ? ((claims.roles as string[] | undefined) ?? [])
        : (((claims.scp as string | undefined) ?? "").split(" ").filter(Boolean));
    const identity =
      (claims.upn as string | undefined) ??
      (claims.preferred_username as string | undefined) ??
      (claims.appid as string | undefined) ??
      (claims.azp as string | undefined);

    return {
      ok: true,
      mode,
      tenantId: claims.tid as string | undefined,
      identity,
      scopesOrRoles,
      expiresOn: token.expiresOnTimestamp ? new Date(token.expiresOnTimestamp).toISOString() : undefined,
      writesAllowed,
    };
  } catch (err) {
    return {
      ok: false,
      mode,
      scopesOrRoles: [],
      writesAllowed,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export function printDoctorResult(serverName: string, result: DoctorResult): void {
  logToStderr(`\n${serverName} doctor`);
  logToStderr(`  auth mode:      ${result.mode}`);
  logToStderr(`  status:         ${result.ok ? "OK" : "FAILED"}`);
  if (result.error) logToStderr(`  error:          ${result.error}`);
  if (result.tenantId) logToStderr(`  tenant:         ${result.tenantId}`);
  if (result.identity) logToStderr(`  identity:       ${result.identity}`);
  logToStderr(`  granted ${result.mode === "app-only" ? "app roles" : "scopes"}: ${result.scopesOrRoles.join(", ") || "(none found in token)"}`);
  if (result.expiresOn) logToStderr(`  token expires:  ${result.expiresOn}`);
  logToStderr(`  writes allowed: ${result.writesAllowed ? "yes (MCP_MS_ALLOW_WRITES=1)" : "no (read-only)"}\n`);
}
