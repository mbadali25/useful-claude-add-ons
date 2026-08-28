import {
  ClientSecretCredential,
  AzureCliCredential,
  type TokenCredential,
  type AccessToken,
  type GetTokenOptions,
} from "@azure/identity";
import { ConfigError, logToStderr, buildDeviceCodeCredential } from "./auth.js";
import { GRAPH_DEFAULT_SCOPE } from "./graphClient.js";

/** Microsoft's own first-party "Microsoft Azure CLI" app registration. Using it as
 * the device-code client id means a user with no app registration of their own can
 * still sign in -- the same client id `az login` itself uses. Its consented Graph
 * permissions are fixed and cannot be widened by the caller (see the module doc
 * comment below), which is why it's a fallback, not the primary path. */
export const AZURE_CLI_WELL_KNOWN_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46";

export type AdminAuthMode = "secret" | "cli" | "device";
export type TokenType = "app-only" | "delegated";

const VALID_AUTH_MODES = new Set(["secret", "cli", "device", "auto"]);

/** Exported so tests can construct a chain from fake credentials without ever
 * touching the real Azure SDK classes -- see test/adminAuth.test.ts. */
export interface ChainLink {
  mode: AdminAuthMode;
  tokenType: TokenType;
  build: () => TokenCredential;
  /** When set, this link ignores whatever scopes the caller asked for and always
   * requests these instead. Used by "secret" and "cli": an app-only client-credentials
   * token and an Azure CLI delegated token both only ever support the resource's
   * .default scope -- neither can negotiate a caller-supplied named scope list, so
   * asking for anything else just fails. "device" has no override: it uses whatever
   * scopes the caller (GraphClient's configured delegated scopes) actually asked for,
   * because device code against a real app registration CAN negotiate named scopes. */
  scopesOverride?: string[];
}

/**
 * A TokenCredential that tries each link in order and remembers which one worked,
 * so a caller (doctor, tests) can report which auth method actually authenticated --
 * "the process started" proves nothing about that. Once a link succeeds, later calls
 * reuse that same link's credential instance (so its own internal token cache keeps
 * working and the user is never re-prompted mid-process); earlier, higher-priority
 * links are not retried after that point even if they would now succeed, since
 * flipping auth methods mid-session would be surprising.
 */
export class AdminCredentialChain implements TokenCredential {
  private resolved?: { mode: AdminAuthMode; tokenType: TokenType; credential: TokenCredential };
  private readonly attempted = new Set<AdminAuthMode>();

  constructor(private readonly links: ChainLink[]) {
    if (links.length === 0) {
      throw new ConfigError(
        "No admin auth method configured. Set MS_ADMIN_TENANT_ID/MS_ADMIN_CLIENT_ID/MS_ADMIN_CLIENT_SECRET, " +
          'run "az login", or set MS_ADMIN_AUTH to force one method. See mcp-servers/README.md.'
      );
    }
  }

  get usedMode(): AdminAuthMode | undefined {
    return this.resolved?.mode;
  }

  get usedTokenType(): TokenType | undefined {
    return this.resolved?.tokenType;
  }

  /** The modes this chain was configured with, in try-order -- purely for
   * inspection/testing/logging; never triggers a build() or a network call. */
  get configuredModes(): AdminAuthMode[] {
    return this.links.map((l) => l.mode);
  }

  async getToken(scopes: string | string[], options?: GetTokenOptions): Promise<AccessToken | null> {
    if (this.resolved) {
      const requested = this.scopesFor(this.resolved.mode, scopes);
      return this.resolved.credential.getToken(requested, options);
    }

    const errors: string[] = [];
    for (const link of this.links) {
      this.attempted.add(link.mode);
      try {
        const credential = link.build();
        const requested = this.scopesFor(link.mode, scopes);
        const token = await credential.getToken(requested, options);
        if (token) {
          this.resolved = { mode: link.mode, tokenType: link.tokenType, credential };
          logToStderr(`mcp-ms-core: authenticated via "${link.mode}" (${link.tokenType}).`);
          return token;
        }
        errors.push(`${link.mode}: getToken returned null`);
      } catch (err) {
        errors.push(`${link.mode}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    throw new ConfigError(
      `No admin auth method succeeded (tried: ${[...this.attempted].join(", ")}). ${errors.join(" | ")} ` +
        "See mcp-servers/README.md for the auth chain and how to fix each method."
    );
  }

  private scopesFor(mode: AdminAuthMode, requested: string | string[]): string | string[] {
    const link = this.links.find((l) => l.mode === mode);
    return link?.scopesOverride ?? requested;
  }
}

function requireAll(names: string[]): Record<string, string> | undefined {
  const values: Record<string, string> = {};
  for (const name of names) {
    const value = process.env[name]?.trim();
    if (!value) return undefined;
    values[name] = value;
  }
  return values;
}

function buildSecretLink(): ChainLink | undefined {
  const env = requireAll(["MS_ADMIN_TENANT_ID", "MS_ADMIN_CLIENT_ID", "MS_ADMIN_CLIENT_SECRET"]);
  if (!env) return undefined;
  return {
    mode: "secret",
    tokenType: "app-only",
    scopesOverride: [GRAPH_DEFAULT_SCOPE],
    build: () =>
      new ClientSecretCredential(env.MS_ADMIN_TENANT_ID, env.MS_ADMIN_CLIENT_ID, env.MS_ADMIN_CLIENT_SECRET),
  };
}

function buildCliLink(): ChainLink {
  const tenantId = process.env.MS_ADMIN_TENANT_ID?.trim() || undefined;
  return {
    mode: "cli",
    tokenType: "delegated",
    // AzureCliCredential (like `az account get-access-token`) can only ever request
    // a resource's .default scope -- it hands back whatever Graph permissions the
    // signed-in user has for the "Microsoft Azure CLI" app, and that set cannot be
    // widened per-call. This is the documented, honest limitation, not a bug: some
    // tenants' consent for that app does not include Intune management scopes, in
    // which case the fix is the device-code link below with a real app registration.
    scopesOverride: [GRAPH_DEFAULT_SCOPE],
    build: () => new AzureCliCredential(tenantId ? { tenantId } : undefined),
  };
}

function buildDeviceLink(delegatedScopes: string[]): ChainLink {
  const clientId = process.env.MS_ADMIN_CLIENT_ID?.trim() || AZURE_CLI_WELL_KNOWN_CLIENT_ID;
  const tenantId = process.env.MS_ADMIN_TENANT_ID?.trim() || "organizations";
  return {
    mode: "device",
    tokenType: "delegated",
    // No override: uses the real per-server delegated scopes passed in by the
    // caller. Falling back to the CLI's well-known client id inherits the same
    // consent limits as the "cli" link above -- register a real public-client app
    // and set MS_ADMIN_CLIENT_ID to it for scopes that app doesn't have.
    build: () => buildDeviceCodeCredential(clientId, tenantId),
  };
}

/**
 * Builds the app-only/admin credential chain described in mcp-servers/README.md:
 *   1. client secret (MS_ADMIN_TENANT_ID/CLIENT_ID/CLIENT_SECRET all set) -- app-only, unchanged from before this chain existed.
 *   2. Azure CLI credential (`az login`) -- delegated, zero prompts if already signed in.
 *   3. device code -- delegated, last resort, prompts once per process.
 *
 * MS_ADMIN_AUTH overrides the chain to force exactly one link: "secret" | "cli" | "device".
 * Unset or "auto" runs the chain above in order.
 *
 * `delegatedScopes` are the named Graph delegated permissions this server needs
 * (e.g. User.Read.All) -- only the device-code link can actually request them;
 * secret and cli always request the resource .default scope regardless.
 */
export function buildAdminCredential(delegatedScopes: string[]): AdminCredentialChain {
  const forced = process.env.MS_ADMIN_AUTH?.trim().toLowerCase();
  if (forced && !VALID_AUTH_MODES.has(forced)) {
    throw new ConfigError(
      `MS_ADMIN_AUTH="${forced}" is not valid. Use one of: secret, cli, device, auto.`
    );
  }

  if (forced === "secret") {
    const link = buildSecretLink();
    if (!link) {
      throw new ConfigError(
        "MS_ADMIN_AUTH=secret requires MS_ADMIN_TENANT_ID, MS_ADMIN_CLIENT_ID, and MS_ADMIN_CLIENT_SECRET all set."
      );
    }
    return new AdminCredentialChain([link]);
  }
  if (forced === "cli") {
    return new AdminCredentialChain([buildCliLink()]);
  }
  if (forced === "device") {
    return new AdminCredentialChain([buildDeviceLink(delegatedScopes)]);
  }

  // auto (default): secret if fully configured, else CLI, else device code.
  const links: ChainLink[] = [];
  const secretLink = buildSecretLink();
  if (secretLink) links.push(secretLink);
  links.push(buildCliLink());
  links.push(buildDeviceLink(delegatedScopes));
  return new AdminCredentialChain(links);
}
