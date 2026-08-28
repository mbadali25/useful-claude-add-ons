import type { TokenCredential } from "@azure/identity";
import { GRAPH_DEFAULT_SCOPE } from "./graphClient.js";
import { decodeJwtPayload } from "./jwt.js";
import { logToStderr } from "./auth.js";
import type { TokenType } from "./adminAuth.js";

export interface DoctorResult {
  ok: boolean;
  /** Which credential actually authenticated: "secret" | "cli" | "device" for the
   * admin chain, or "user-device" for o365-user's plain device-code credential. */
  authMode: string;
  tokenType: TokenType;
  tenantId?: string;
  identity?: string;
  scopesOrRoles: string[];
  expiresOn?: string;
  writesAllowed: boolean;
  error?: string;
}

/** Returns which credential/mode actually authenticated. For the admin chain this can
 * only be known AFTER a successful getToken() call (it tries links in order), so
 * runDoctor calls this after acquiring the token, not before. */
export type ResolveAuthMode = () => { authMode: string; tokenType: TokenType };

/**
 * Every server's `doctor` subcommand calls this: acquires a real token,
 * decodes its claims, and reports what was actually granted -- a process
 * that starts cleanly proves nothing about whether auth works.
 */
export async function runDoctor(
  credential: TokenCredential,
  resolveAuthMode: ResolveAuthMode,
  scopes: string[] = [GRAPH_DEFAULT_SCOPE]
): Promise<DoctorResult> {
  const writesAllowed = process.env.MCP_MS_ALLOW_WRITES === "1";
  try {
    const token = await credential.getToken(scopes);
    if (!token) {
      const { authMode, tokenType } = resolveAuthMode();
      return { ok: false, authMode, tokenType, scopesOrRoles: [], writesAllowed, error: "getToken returned null" };
    }
    const { authMode, tokenType } = resolveAuthMode();
    const claims = decodeJwtPayload(token.token);
    const scopesOrRoles =
      tokenType === "app-only"
        ? ((claims.roles as string[] | undefined) ?? [])
        : (((claims.scp as string | undefined) ?? "").split(" ").filter(Boolean));
    const identity =
      (claims.upn as string | undefined) ??
      (claims.preferred_username as string | undefined) ??
      (claims.appid as string | undefined) ??
      (claims.azp as string | undefined);

    return {
      ok: true,
      authMode,
      tokenType,
      tenantId: claims.tid as string | undefined,
      identity,
      scopesOrRoles,
      expiresOn: token.expiresOnTimestamp ? new Date(token.expiresOnTimestamp).toISOString() : undefined,
      writesAllowed,
    };
  } catch (err) {
    // The failure may have happened before any link resolved (e.g. every link in
    // the chain failed) -- resolveAuthMode() still returns a best-effort label
    // ("chain exhausted" for the admin chain) rather than throwing itself.
    const { authMode, tokenType } = resolveAuthMode();
    return {
      ok: false,
      authMode,
      tokenType,
      scopesOrRoles: [],
      writesAllowed,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export function printDoctorResult(serverName: string, result: DoctorResult): void {
  logToStderr(`\n${serverName} doctor`);
  logToStderr(`  auth method:    ${result.authMode}`);
  logToStderr(`  token type:     ${result.tokenType}`);
  logToStderr(`  status:         ${result.ok ? "OK" : "FAILED"}`);
  if (result.error) logToStderr(`  error:          ${result.error}`);
  if (result.tenantId) logToStderr(`  tenant:         ${result.tenantId}`);
  if (result.identity) logToStderr(`  identity:       ${result.identity}`);
  logToStderr(`  granted ${result.tokenType === "app-only" ? "app roles" : "scopes"}: ${result.scopesOrRoles.join(", ") || "(none found in token)"}`);
  if (result.expiresOn) logToStderr(`  token expires:  ${result.expiresOn}`);
  logToStderr(`  writes allowed: ${result.writesAllowed ? "yes (MCP_MS_ALLOW_WRITES=1)" : "no (read-only)"}\n`);
}
